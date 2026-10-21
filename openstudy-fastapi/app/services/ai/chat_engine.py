"""
AI 对话底层引擎 —— **全平台唯一的流式出口**

## 为什么要有这一层

改造前，后端有 7 个「流式对话」接口，每个都在自己的路由里手写一遍
「取配置 → 组 messages → stream_with_config → yield 分片 → yield [DONE]」，
其中「带图片/附件」的能力还被写了两份（聊天助手一份、AI 搭建题库一份）。
典型症状就是：加个附件能力要改两处，改漏一处就出现「这边能用、那边不能用」。

现在收敛成一条链路：

    前端 → POST /ai/chat/stream（或旧的兼容路由）
         → **chat_engine.stream_turn()**          ← 唯一的流式出口
              ├─ 按 scene 取提示词        （prompts.build_scene_messages）
              ├─ 解析附件（图片 / 文档）  （file_parser）
              ├─ 组装多模态 messages      （TextBlock / ImageBlock）
              ├─ 视觉能力兜底             （model_capabilities）
              └─ 流式下发 + 可选落库       （conversation_service）
         → 统一事件契约：正文增量 / `Error: <原因>` / `[DONE]`

**新增 AI 能力时不要新开流式接口**：在 `prompts.py` 加一个 scene，
前端传 `scene` 即可；需要落历史就带上 `sessionId`，不需要就不带。

## 事件契约（前端 `api/ai/ai.ts` 的 `consumeAssistantStream` 依赖，改动要同步）

| 情况 | 下发的分片 |
|---|---|
| 请求本身不合法（没有任何可发送内容） | `Error: <原因>`（不落库） |
| 模型调用失败 | 已流出的半截正文 + `Error: <原因>`（落库时追加中断说明） |
| 正常结束 | 正文分片 + `[DONE]`（落库 assistant 行） |
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import conversation_service, db_config, model_capabilities, prompts
from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock

#: 只发了附件、没写文字时，替用户补一句可行动的指令（对齐 DS 网页端行为）
DEFAULT_ATTACHMENT_PROMPT = "请阅读我上传的附件（图片以及文档内容），并据此回答。"

#: 一个文档里最多抽多少张插图交给多模态模型（防止请求体过大被上游拒绝）
MAX_DOC_IMAGES = 8


# ============================================================
# 深度思考增量的传输标记（2026-10-20）
# ============================================================
#
# 为什么不用 JSON 事件行（像 `agent/loop.py` 那样）：
#   本接口（`/ai/assistant/stream`）的正文是**纯文本流** —— 前端直接
#   `fullContent += chunk` 拼接，只对 `Error: ` 和 `[DONE]` 做特判。
#   混入 `{"type":"thinking",...}` 这样的 JSON 行会被当成题目正文，
#   直接污染 JSON 解析。
#
# 所以用 ASCII **记录分隔符** `\x1e`(RS) 把思考增量包起来：
#     \x1e@@THINK@@<增量文本>\x1e
# 选 RS 的原因：
#   · 模型不会输出它（不可见控制字符），不会与正文歧义；
#   · 前端一眼能正则剥掉，剥不掉也绝不可能是合法题目文本。
#
# 前端对应实现见 `openstudy-vue3-ts/src/api/ai/ai.ts` 的 `consumeAssistantStream`。
THINK_OPEN = "\x1e@@THINK@@"
THINK_CLOSE = "\x1e"


@dataclass
class ChatTurn:
    """一次「AI 对话轮次」的完整入参（路由层只负责把 HTTP 参数搬到这里）

    落库规则：**只有 `session_id` 非空才写历史**。
    出题 / 阅读理解 / 组合题 / 题目解析 / AI 搭建题库都是一次性生成，
    不该往聊天历史表里塞数据，所以它们不传 session_id。
    """

    #: 场景，见 prompts.SCENE_*；决定系统提示词与用户模板
    scene: str = prompts.SCENE_ASSISTANT
    #: 调用方给的正文（聊天助手 = 用户输入；题库搭建 = 前端拼好的长指令）
    prompt: str = ""
    #: 图片附件（base64 data URL 数组）
    images: List[str] = field(default_factory=list)
    #: 文档附件（`{name, type, base64}`），由 file_parser 抽正文
    files: List[Any] = field(default_factory=list)
    #: 仅用于历史落库的缩略图元信息 `[{name, type, thumb}]`，不参与推理
    attachments: List[dict] = field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    # configId：精确指定选中哪条配置（区分同名模型）
    config_id: Optional[int] = None
    thinking: Optional[bool] = None
    temperature: float = 0.7
    #: 对话会话 id；非空才写历史（且会带上历史上下文）
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    #: 显式覆盖系统提示词
    system_prompt: Optional[str] = None
    #: 场景模板变量（count / knowledge_point / requirement / question …）
    variables: Dict[str, Any] = field(default_factory=dict)
    #: **知识库取材**（可选）：传了就在组装 messages 之前先检索这些知识库，
    #: 把命中的**原文片段**注入 prompt（出题类还会要求模型注明出处）。
    #: 这是「基于我的资料出题」的入口 —— 见 `_retrieve_kb_context`。
    #: 空 / None = 不检索（跟随原有行为）。
    kb_ids: Optional[List[int]] = None
    #: **是否把本轮正文投递为附件**（用户 2026-10-12 定案，仅 ds-free-nb 用）：
    #: 前端「注入历史记忆」开关打开时为 True → 后端把当前会话历史拼进正文，
    #: 并在请求里带 `asAttachment=true`，桥据此把正文写成 .md 附件上传（输入框只留短指令），
    #: 避免长历史灌进 DS 输入框导致网页卡死。非 ds-free-nb 端忽略此字段。
    inject_history: bool = False

    @property
    def persist(self) -> bool:
        return bool((self.session_id or "").strip())


# ============================================================
# 附件处理
# ============================================================


def data_url_to_bytes(raw: str) -> tuple:
    """data URL（或裸 base64 字符串）→ (bytes, mime)

    前端把附件读成 `data:application/pdf;base64,xxxx` 这种形式提交；
    扩展链路里也出现过只传裸 base64 的情况，这里两种都兼容。
    """
    import base64
    import re

    value = (raw or "").strip()
    mime = "application/octet-stream"
    if value.startswith("data:") and "," in value:
        head, value = value.split(",", 1)
        matched = re.match(r"data:([^;,]*)", head)
        if matched and matched.group(1):
            mime = matched.group(1)
        if ";base64" not in head:
            # 非 base64 的 data URL（例如 data:text/plain,hello）
            return value.encode("utf-8"), mime or "text/plain"
    # 补齐 base64 padding，容忍前端漏掉 '='
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded), mime


#: 图片文件扩展名 → MIME（读盘转 data URL 时用）
_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def stored_image_to_data_url(url: str) -> str:
    """把本站存储的图片 URL（`/profile/upload/...` 相对路径）读盘转成 data URL。

    为什么需要：题目里的图片以 `<img src="/profile/upload/...">` 形式**相对路径**存储
    （TEXT 列不可能塞 base64）。而 OpenAI 兼容多模态端点**只认 data URL 或 http(s)
    绝对 URL**，直接喂相对路径会 `400 Unsupported image_url format`（见 `loop.py` 的
    血泪注释）。故解析题目图片时，必须先把这些相对路径转成 data URL。

    - 已是 `data:` / `http(s)://` 的原样返回（前端本地上传时可能已是 data URL）；
    - 空串、读盘失败、非图片扩展名 → 返回 ""（由调用方跳过，单张失败不影响整体）。
    """
    import base64
    import os
    from app.config import settings

    value = (url or "").strip()
    if not value:
        return ""
    lower = value.lower()
    if lower.startswith("data:") or lower.startswith("http://") or lower.startswith("https://"):
        return value

    # 归一成本站上传目录下的相对路径。
    # ⚠️ 存库的 src 通常是 `/profile/upload/...`，但前端在开发/预发环境下会把
    #    `VITE_APP_BASE_API` 前缀拼进去（dev=`/dev-api`、staging=`/stage-api`），
    #    于是题干里可能出现 `/dev-api/profile/upload/...`（用户 2026-10-12 实测：
    #    AI 说「图片无法识别」正是这个前缀导致读盘路径错、图片被丢弃）。
    #    这里统一**截取到 `/profile/` 之后**，前缀无论是 `/dev-api` / `/stage-api`
    #    / 绝对域名都兼容。
    rel = value
    marker = "/profile/"
    idx = rel.find(marker)
    if idx >= 0:
        rel = rel[idx + len(marker):]
    else:
        # 兼容没有 `/profile/` 前缀、直接写成 `profile/upload/...` 或 `upload/...` 的形态
        rel = rel.lstrip("/")
        if rel.startswith("profile/"):
            rel = rel[len("profile/"):]
    rel = rel.replace("\\", "/")
    if not rel or ".." in rel:
        return ""

    ext = os.path.splitext(rel)[1].lower()
    mime = _IMAGE_MIME_BY_EXT.get(ext)
    if not mime:
        return ""

    try:
        full_path = os.path.join(settings.UPLOAD_DIR, rel)
        with open(full_path, "rb") as f:
            raw = f.read()
        if not raw:
            return ""
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:  # noqa: BLE001 - 单张图失败不影响整体
        logger.warning("[chat_engine] 题目图片读盘失败 {}: {}", url, e)
        return ""


_IMG_SRC_RE = None


def extract_image_urls_from_html(html: str) -> List[str]:
    """从 HTML 文本里按出现顺序抽取所有 `<img src="...">` 的 src。

    用于 AI 解析题目时，把题干/材料/小题正文里内嵌的图片都收集起来喂给多模态模型。
    只抽 src，不处理其它属性；去重保序。
    """
    global _IMG_SRC_RE
    if not html or "<img" not in html.lower():
        return []
    if _IMG_SRC_RE is None:
        import re
        _IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)

    seen = set()
    urls: List[str] = []
    for m in _IMG_SRC_RE.finditer(html):
        raw = (m.group(1) or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        urls.append(raw)
    return urls


def normalize_image_urls(urls: List[str]) -> List[str]:
    """把一组图片 URL 归一成可喂多模态模型的 data URL（相对路径读盘转换）。

    保留输入顺序；转换失败/非图片的项被丢弃（而不是塞空串，避免污染多模态块——
    空串会让上游 400「image_url 为空」）。
    """
    normalized: List[str] = []
    for u in urls or []:
        if not u:
            continue
        converted = stored_image_to_data_url(u)
        if converted:
            normalized.append(converted)
    return normalized


def _attachment_field(item: Any, key: str, default: str = "") -> str:
    """读附件字段：兼容 pydantic 模型（线上走 `AssistantAttachment`）与普通 dict

    `ai.py` 传进来的是 pydantic 模型；但纯逻辑测试 / 将来别的调用方可能直接给
    dict。只按属性读的话，dict 会静默落到默认值 → 附件"解码失败"却又看不出原因。
    """
    value = getattr(item, key, None)
    if value is None and isinstance(item, dict):
        value = item.get(key)
    return value if isinstance(value, str) else (default if value is None else str(value))


async def _targets_ds_bridge(db: AsyncSession, turn: "ChatTurn") -> bool:
    """本轮解析出的配置是不是「本机 DS 网页桥」（provider=ds-free-nb）。

    用途：文档附件对桥要**原样上传**（DS 网页自己解析），不走路由后端的
    `extract_attachments`（把文档拆成正文文本 + 内嵌图片）——否则重复投递、
    且 DS 侧要处理超大文本 + 多图，容易长时间无响应。

    解析不出配置（异常/无配置）时返回 False（保持旧行为，不影响其它 provider）。
    """
    try:
        cfg = await db_config.resolve_config(db, turn.provider, turn.model, user_id=turn.user_id)
        return bool(cfg and (cfg.provider or "").strip().lower() == "ds-free-nb")
    except Exception:  # noqa: BLE001 - 判断失败按"不是桥"处理，绝不因此影响主流程
        return False


def _extract_raw_files(files: List[Any]) -> List[dict]:
    """把本轮文档附件转成「原样上传」载荷 `[{name, mimeType, base64}]`。

    与 `extract_attachments`（解析成文本）不同：这里是**文件本体**，供 ds-free-nb 桥
    上传到 DS 网页，由网页自己解析（PDF/Word 等原生效果更好）。
    只保留「有 name 且有 base64」的项；base64 支持裸串或 data URL（桥会再归一）。
    """
    out: List[dict] = []
    for item in files or []:
        name = (_attachment_field(item, "name") or "").strip()
        b64 = _attachment_field(item, "base64")
        mime = (_attachment_field(item, "type") or "").strip()
        if not name or not b64:
            continue
        out.append({"name": name, "mimeType": mime or "application/octet-stream", "base64": b64})
    return out


def extract_attachments(files: List[Any], image_offset: int = 0) -> tuple:
    """文档附件 → (可喂给模型的文本, 文档内嵌图片 data URL, 告警)

    - 文本类附件（pdf / docx / txt / md…）用 `file_parser` 抽正文，按
      `【附件：文件名】` 分段拼接，模型据此就能「读到」文件；
    - 正文里的插图渲染成 `【图N】` 标记，**图片落在它原本所在的文字位置之间**，
      图片列表顺序与标记编号一一对应 —— 模型才能把「如下图」和具体那张图对上；
    - 解析不出来时收集告警，最终以 `> ⚠️` 追加在回复末尾，让用户看得见。

    Args:
        files: 文档附件列表（`{name, type, base64}`）
        image_offset: 图片编号起始值 —— 用户另外上传了图片时，文档插图要顺延编号
    """
    from app.services.file_parser import build_marked_document, parse_file

    sections: List[str] = []
    image_urls: List[str] = []
    warnings: List[str] = []

    for item in files or []:
        name = (_attachment_field(item, "name") or "file").strip() or "file"
        try:
            content, _mime = data_url_to_bytes(_attachment_field(item, "base64"))
        except Exception as e:
            warnings.append(f"附件 {name} 解码失败：{e}")
            continue
        try:
            parsed = parse_file(name, content)
        except Exception as e:
            warnings.append(f"附件 {name} 解析失败：{e}")
            continue

        error = parsed.get("error")
        marked, images = build_marked_document(parsed, image_offset + len(image_urls))
        kept = images[:MAX_DOC_IMAGES]

        if marked:
            sections.append(f"【附件：{name}】\n{marked}")
        if kept:
            image_urls.extend(kept)
            if not marked:
                sections.append(
                    f"【附件：{name}】\n（该附件没有可提取的文字，插图见下方图片）"
                )
            if len(images) > len(kept):
                warnings.append(
                    f"附件 {name}：插图较多，只把前 {MAX_DOC_IMAGES} 张交给模型"
                )
        if not marked and not kept:
            warnings.append(f"附件 {name}：{error or '没有提取到可用的文字或图片'}")

    return "\n\n".join(sections), image_urls, warnings



# ============================================================
# 主流程
# ============================================================


#: 知识库取材时，单段最大字符数（与 rag_query_service.MAX_CHUNK_CHARS 同口径）
KB_CONTEXT_CHUNK_CHARS = 1200
#: 知识库取材的总字符预算（与 rag_query_service.MAX_CONTEXT_CHARS 同口径）
KB_CONTEXT_MAX_CHARS = 6000
#: 知识库取材默认取回几条
KB_CONTEXT_TOP_K = 5

#: 知识库取材的超时（秒）——超过就放弃取材、直接出题
#:
#: 为什么是 20s 而不是更小：正常路径下（模型已预热）检索只要 ~0.15s，
#: 留足 20s 是为了容忍大库首次查询、冷页缓存、DB 抖动等偶发慢，不至于动不动就放弃取材。
#: 又必须封顶：`embed_query` 首次要加载 2.17GB 模型（实测冷启动 43.22s），
#: 若预热的那个后台任务还没跑完，这 43s 会全部堆在用户面前 —— 且发生在
#: **模型调用之前**，连"思考中"都看不到，体感就是"点了没反应"。
#: 20s 是"给足正常波动、又不让用户等一分钟"的折中。
KB_RETRIEVE_TIMEOUT_SEC = 20


async def _retrieve_kb_context(
    db: AsyncSession,
    turn: ChatTurn,
    query: str,
    top_k: int = KB_CONTEXT_TOP_K,
) -> tuple:
    """按 `turn.kb_ids` 检索知识库，返回 `(材料文本, 命中图片 URL 列表)`。

    用途：出题类场景（`question-generate` / `reading` / `composite`）用户选了
    「取材来源 = 我的知识库」时，由这里取原文 → 交给 prompts 模板 → 模型据此出题。
    命中片段若**夹带图片**（分块时按 `【图N】` 归属到 `chunk.meta_data`），
    图片 URL 一并返回，由调用方转成多模态图块喂模型 —— 否则模型只看到文字、
    看不到图里的公式/表格（这正是「知识库与图片」此前断裂之处）。

    设计要点：
      · **失败绝不抛**：检索挂了（embedding 不可用 / 库被删）不该让整轮出题失败，
        只是「这次没有材料」，退化成纯 AI 生成并留下可见的提示。
      · **带出处**：每段标 `【文档名 第N段】`，模型据此在解析里注明来源。
      · **预算封顶**：避免把上下文撑爆（与 rag_query_service 同口径）。
    """
    from app.services.rag import rag_query_service as rqs

    kb_ids = []
    for value in (turn.kb_ids or []):
        try:
            kb_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not kb_ids or not (query or "").strip():
        return "", []

    try:
        found = await rqs.search(db, turn.user_id or 0, query, kb_ids, top_k=top_k)
    except Exception as e:  # noqa: BLE001 - 取材是增强项，失败只记日志
        logger.warning("[chat_engine] 知识库取材失败（已跳过）: {}", e)
        return "", []

    hits = found.get("hits") or []
    parts: List[str] = []
    image_urls: List[str] = []
    used = 0
    for i, hit in enumerate(hits, start=1):
        content = (hit.get("content") or "").strip()
        # 该片段夹带的图：即使正文为空（纯图块）也要把图收上来，故先收图再判 content
        for url in (hit.get("images") or []):
            value = str(url or "").strip()
            if value and value not in image_urls:
                image_urls.append(value)
        if not content:
            continue
        if len(content) > KB_CONTEXT_CHUNK_CHARS:
            content = content[: KB_CONTEXT_CHUNK_CHARS - 1] + "…"
        source = hit.get("source") or hit.get("docName") or f"文档#{hit.get('docId')}"
        piece = f"【材料{i}｜来源：{source}】\n{content}"
        if used + len(piece) > KB_CONTEXT_MAX_CHARS:
            break
        parts.append(piece)
        used += len(piece)

    if not parts and not image_urls:
        logger.info("[chat_engine] 知识库取材：kb_ids={} 未检索到相关内容", kb_ids)
        return "", []
    logger.info(
        "[chat_engine] 知识库取材：kb_ids={} → {} 段 / {} 字符 / {} 张图",
        kb_ids, len(parts), used, len(image_urls),
    )
    return "\n\n".join(parts), image_urls


async def _resolve_vision_safe_model(
    db: AsyncSession,
    turn: ChatTurn,
    has_images: bool,
    session_id: str,
) -> tuple:
    """图片存在时保证「选中的模型能识图」

    pro（deepseek-v4-pro）这类仅文本模型收到图片会被上游直接打回，
    整轮请求就白费了。这里按 `model_capabilities` 的口径回退到视觉模型。
    前端在发送前也会做同样的切换并提示用户，本处是防御性兜底
    （防止其它调用方直接带图请求仅文本模型）。
    """
    if not has_images:
        return turn.model, turn.provider

    try:
        resolved = await db_config.resolve_config(
            db, turn.provider, turn.model, user_id=turn.user_id, config_id=turn.config_id
        )
        if resolved is not None and not model_capabilities.supports_vision(resolved.model):
            logger.info(
                "AI 多模态：{} 不支持图片，自动改用 {}（scene={} session={}）",
                resolved.model,
                model_capabilities.DEFAULT_VISION_MODEL,
                turn.scene,
                session_id or "-",
            )
            return model_capabilities.DEFAULT_VISION_MODEL, None
    except Exception as e:  # pragma: no cover - 兜底失败不阻断主流程
        logger.warning("解析模型配置失败，按原样发起请求：{}", e)
    return turn.model, turn.provider


async def _save_assistant(
    turn: ChatTurn, user_id: int, text: str, note: str, extra_note: str
) -> None:
    """把 AI 这一轮写进历史；失败只告警，绝不影响已经下发的流"""
    if not turn.persist:
        return
    suffix = "；".join(p for p in (note, extra_note) if p)
    content = (
        f"{text}\n\n> ⚠️ {suffix}"
        if (text and suffix)
        else (text or (f"> ⚠️ {suffix}" if suffix else ""))
    )
    try:
        await conversation_service.save_message(
            user_id, turn.session_id, "assistant", content
        )
    except Exception as e:  # pragma: no cover
        logger.exception("AI 回复落库失败 session={}: {}", turn.session_id, e)


async def stream_turn(db: AsyncSession, turn: ChatTurn) -> AsyncIterator[str]:
    """执行一轮 AI 对话并按统一契约流式下发

    这是全平台唯一的流式出口：所有 `/ai/**` 的流式接口最终都调它。
    """
    user_id = turn.user_id or 0
    session_id = (turn.session_id or "").strip()

    # 目标是不是「本机 DS 网页桥」（provider=ds-free-nb）？
    # 是的话：**文档本体直接上传给 DS 网页**（由它原生解析 Word/PDF），后端**不再**
    # 把文档拆成「正文文本 + 内嵌图片」——否则会重复投递、且 DS 要处理 25k 字+13 张图，
    # 表现为长时间无响应（用户 2026-10-12 实测 180s 超时）。
    send_files_to_bridge = await _targets_ds_bridge(db, turn)

    # ① 附件 → 正文文本 + 文档内嵌图片
    #    编号顺序必须是「用户上传的图片在前、文档插图在后」，
    #    所以 offset 用筛过的用户图片数量（不能直接用 len(turn.images)，里面可能有空串）
    #
    #    ⚠️ 丢到线程池里执行：文档解析是同步的，老版 .doc 还会借 Word COM 转换
    #       （1~3s，最坏 CONVERT_TIMEOUT_SECONDS）。直接在事件循环里跑会把整个后端冻住。
    user_images = [u for u in (turn.images or []) if u]
    if send_files_to_bridge and turn.files:
        # 走桥：文档本体原样上传，后端不解析（避免肢解成文本+图片）
        file_text, doc_images, warnings = "", [], []
    else:
        file_text, doc_images, warnings = await asyncio.to_thread(
            extract_attachments, turn.files, len(user_images)
        )
    # ⚠️ 归一成 data URL：题目解析会把题干里 `<img src="/profile/upload/...">` 的相对
    #    路径直接作为 images 传来；OpenAI 兼容多模态端点不认相对路径（会 400）。
    #    data: / http(s) 的原样保留，相对路径读盘转 base64。
    image_urls = normalize_image_urls(user_images + doc_images)

    # ② 组装这一轮给模型看的正文
    typed = (turn.prompt or "").strip()
    prompt_text = "\n\n".join(p for p in (typed, file_text) if p)
    if not prompt_text and image_urls:
        prompt_text = DEFAULT_ATTACHMENT_PROMPT
    # ⚠️ 走桥（ds-free-nb）时文档**原样上传给 DS 网页**、后端不解析 → `file_text` 恒空。
    #    此时「只传了附件、正文为空」不能算"没有可发送内容"：附件本身就是内容。
    _has_bridge_files = bool(send_files_to_bridge and turn.files)
    if not prompt_text and _has_bridge_files:
        prompt_text = DEFAULT_ATTACHMENT_PROMPT
    # 「有没有内容」要连模板变量一起判断：出题类接口只传 variables
    # （knowledge_point / requirement / question），不传正文是正常用法。
    if not prompt_text and not image_urls:
        if not prompts.has_scene_content(turn.scene, "", turn.variables):
            detail = (
                f"（{'；'.join(warnings)}）"
                if warnings
                else "请写一句文字，或上传图片 / 文档附件"
            )
            # 请求本身不合法：用统一契约告知，不落库（历史里不该出现空轮次）
            yield f"Error: 没有可发送的内容：{detail}"
            return

    # ③ 历史：先取上下文、再写本轮提问（反过来会把当前问题重复算进上下文）
    #
    # ⚠️ ds-free-nb（本机无头桥）**特殊**：默认**不**注入历史——DS 网页自己维护会话上下文，
    #    长历史灌进输入框会让网页卡死。只有在用户显式打开「注入历史记忆」开关
    #    （`turn.inject_history=True`）时，才把历史拼进正文，**并标记走附件投递**。
    #    其它 provider（API 端）保持原行为：有 session 就注入上下文。
    to_bridge = send_files_to_bridge
    inject_ctx = (not to_bridge) or bool(turn.inject_history)
    context = ""
    if turn.persist:
        if inject_ctx:
            # 历史预算按「该模型配置的上下文档位」定（200K/1M）—— 见 context_budget
            ctx_max, ctx_single = await db_config.resolve_context_limits(
                db,
                provider=turn.provider,
                model=turn.model,
                user_id=turn.user_id,
                config_id=turn.config_id,
            )
            context = await conversation_service.build_context_prompt(
                user_id, session_id, max_chars=ctx_max, single_max_chars=ctx_single
            )
        history_text = typed or conversation_service.ATTACHMENT_PLACEHOLDER
        await conversation_service.save_message(
            user_id,
            session_id,
            "user",
            history_text,
            attachments=[a for a in (turn.attachments or []) if a] or None,
        )
    # 历史注入是否走附件：仅当目标是桥、且用户开了开关、且确有历史可注入
    as_attachment = bool(to_bridge and turn.inject_history and context)

    # ③b 知识库取材：用户在出题类场景选了「取材来源 = 我的知识库」时，
    #     先检索出原文片段，作为 `source_context` 变量交给模板（模型据此出题）。
    #     ⚠️ 只对**出题类场景**注入 —— 聊天助手场景不该被强行塞材料（它自己有
    #        `knowledge_search` 工具按需检索，见 roles.py）。
    source_context = ""
    kb_image_urls: List[str] = []
    if turn.kb_ids and turn.scene in (
        prompts.SCENE_QUESTION_GENERATE,
        prompts.SCENE_READING,
        prompts.SCENE_COMPOSITE,
        prompts.SCENE_QUESTION_BANK,
    ):
        # 检索用的 query：优先用户的具体要求，其次知识点，最后正文兜底
        kb_query = (
            str(turn.variables.get("requirement") or "").strip()
            or str(turn.variables.get("knowledge_point") or "").strip()
            or prompt_text
        )
        # ★ 为什么这里必须加超时 ★（2026-10-21，用户报「第一次等 60 多秒」）
        #
        # 实测：知识库检索内部要调 `embed_query`，而它**首次会加载
        # BAAI/bge-m3（2.17GB），冷启动 43.22s**，之后 0.15s。
        #
        # 这段等待发生在**模型调用之前**，所以用户连"思考中"都看不到，
        # 感知就是"点了完全没反应"。这正是"第一次卡一分钟"的最大一块。
        #
        # 两层修复：
        #   ① `app/main.py` 的 lifespan 里**启动时后台预热** ——
        #      正常情况下这时模型早就加载好了，本函数只是 0.15s 的纯推理；
        #   ② 这里再加**超时兜底** —— 万一预热还没跑完（刚重启就有人点）、
        #      或检索卡死在别处，超时后**放弃取材继续出题**，
        #      而不是让用户干等一分钟。
        #
        # 为什么"放弃取材"而不是"等它"：
        #   取材是**增强项**（`_retrieve_kb_context` 的 docstring 也是这个口径），
        #   宁可这次没有材料，也不能让整个出题卡住。
        #   超时后 `source_context` 保持空串，模型照常按知识点出题。
        try:
            source_context, kb_image_urls = await asyncio.wait_for(
                _retrieve_kb_context(db, turn, kb_query),
                timeout=KB_RETRIEVE_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[chat_engine] 知识库检索超时（{}s），本次跳过取材直接出题 kb_ids={}",
                KB_RETRIEVE_TIMEOUT_SEC, turn.kb_ids,
            )
            source_context, kb_image_urls = "", []
        if source_context:
            turn.variables["source_context"] = source_context

    # ④ 按场景组装 messages（新增场景只改 prompts.py，不动这里）
    raw_messages = prompts.build_scene_messages(
        turn.scene,
        prompt=prompt_text,
        system_prompt=turn.system_prompt,
        **turn.variables,
    )
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in raw_messages]

    # ⑤ 把历史上下文并入最后一条 user 消息（只有「带 session 的聊天」才有上下文）
    if context and messages and messages[-1].role == "user":
        base = messages[-1].content
        base_text = base if isinstance(base, str) else prompt_text
        messages[-1] = ChatMessage(
            role="user", content=f"{context}\n【当前问题】\n{base_text}"
        )
    full_text = messages[-1].content if messages else prompt_text

    # ⑤b 知识库素材里夹带的图（`/profile/...`）读盘转成 data URL，与用户上传的图合并。
    #     多模态端点只认 data URL / http(s)，相对路径会被拒（见 `stored_image_to_data_url` 注释）。
    for url in kb_image_urls:
        data_url = stored_image_to_data_url(url)
        if data_url and data_url not in image_urls:
            image_urls.append(data_url)

    # ⑥ 有图片时改用多模态内容块（纯文本仍用字符串，尽量少改上游行为）
    effective_model, effective_provider = await _resolve_vision_safe_model(
        db, turn, bool(image_urls), session_id
    )
    # 视觉兜底会**换成另一个模型**；此时若还带着原 config_id 指定，会把它覆盖回去，
    # 兜底就白做了 —— 故仅在未换模型时透传 config_id（区分同名模型）。
    effective_config_id = turn.config_id if effective_model == turn.model else None
    if image_urls and isinstance(full_text, str):
        blocks: List[Any] = []
        if full_text:
            blocks.append(TextBlock(type="text", text=full_text))
        for url in image_urls:
            blocks.append(ImageBlock(type="image_url", image_url={"url": url}))
        messages[-1] = ChatMessage(role="user", content=blocks)

    # ⑦ 流式下发；成功与失败两条路径都保证 assistant 行成对落库
    extra_note = "；".join(warnings)
    full_response = ""
    # 原始文件附件（供 ds-free-nb 桥原样上传到 DS 网页，由网页自己解析）：
    # 后端 file_parser 已把正文并进了 full_text（保底），这里**额外**把文件本体也带上，
    # 让 DS 网页能做原生解析（PDF/Word 等效果更好）。
    raw_files = _extract_raw_files(turn.files)
    logger.info(
        "[chat_engine] 本轮附件: turn.files={} 个 → raw_files={} 个 ({})",
        len(turn.files or []),
        len(raw_files),
        ", ".join(f"{f['name']}({f['mimeType']},{len(f['base64'])})" for f in raw_files) or "-",
    )
    try:
        async for item in db_config.stream_with_config(
            db,
            messages,
            provider=effective_provider,
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=effective_config_id,
            temperature=turn.temperature,
            thinking=turn.thinking,
            model=effective_model,
            # ⚠️ 必须带上，否则「个人中心 → 我的模型」里加的自定义模型永远选不中
            #   （无 user_id = 只可见系统行）
            user_id=turn.user_id,
            files=raw_files,
            as_attachment=as_attachment,
            # ── 深度思考增量（2026-10-20）─────────────────────────────
            #
            # 用户口径：「要能够让用户看到 llm 深度思考的部分 目前 ai 获取数据后
            #   没法直接看到深度思考部分 必须等待好一会 才能看到正文内容
            #   就很影响用户等待体验」
            #
            # 开思考的模型要先推理几十秒才吐第一个正文字，这段时间前端一片空白。
            # 打开 include_reasoning 后本函数 yield `(kind, text)` 二元组，
            # 我们就能把思考实时转出去。
            #
            # ⚠️ 踩过的坑：上一版没开这个开关，却直接对 chunk 调
            #    `getattr(chunk, "additional_kwargs")` —— 而那时 chunk 是 str，
            #    永远取不到 reasoning，思考一个字节都发不出去（死代码）。
            #    跨层取字段前必须先确认上层 yield 的类型。
            include_reasoning=True,
        ):
            # ① 思考增量：只下发，**不进** full_response
            #    （否则思考会混进题目 JSON 污染解析、还会被写进聊天记录）
            if isinstance(item, tuple):
                kind, text = item
                if kind == "reasoning":
                    if text:
                        yield f"{THINK_OPEN}{text}{THINK_CLOSE}"
                    continue
                # kind == "answer"
                full_response += text or ""
                if text:
                    yield text
                continue

            # ② 兼容：万一某个分支仍返回裸字符串，按正文处理（不会丢内容）
            full_response += item
            yield item
    except Exception as e:
        reason = str(e)
        logger.exception(
            "AI 流式生成失败 scene={} session={} user={} provider={} model={}: {}",
            turn.scene,
            session_id or "-",
            user_id,
            effective_provider,
            effective_model,
            reason,
        )
        # 已经流出的半截回复保留下来 + 追加中断原因（与前端 onError 的口径一致）
        await _save_assistant(turn, user_id, full_response, f"生成中断：{reason}", extra_note)
        yield f"Error: {reason}"
        return

    # 正常结束：即使一个字都没拿到，也留下这一轮（历史里不会只剩提问）
    await _save_assistant(
        turn,
        user_id,
        full_response,
        "" if full_response.strip() else "本次没有收到回复内容",
        extra_note,
    )
    yield "[DONE]"


__all__ = [
    "ChatTurn",
    "DEFAULT_ATTACHMENT_PROMPT",
    "MAX_DOC_IMAGES",
    "data_url_to_bytes",
    "extract_attachments",
    "extract_image_urls_from_html",
    "normalize_image_urls",
    "stored_image_to_data_url",
    "stream_turn",
]
