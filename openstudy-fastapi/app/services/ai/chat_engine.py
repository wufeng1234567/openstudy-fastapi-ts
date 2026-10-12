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
    thinking: Optional[bool] = None
    temperature: float = 0.7
    #: 对话会话 id；非空才写历史（且会带上历史上下文）
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    #: 显式覆盖系统提示词
    system_prompt: Optional[str] = None
    #: 场景模板变量（count / knowledge_point / requirement / question …）
    variables: Dict[str, Any] = field(default_factory=dict)

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

    # 只处理本站 /profile/ 下的相对路径
    rel = value
    if rel.startswith("/profile/"):
        rel = rel[len("/profile/"):]
    rel = rel.lstrip("/").replace("\\", "/")
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
            db, turn.provider, turn.model, user_id=turn.user_id
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

    # ① 附件 → 正文文本 + 文档内嵌图片
    #    编号顺序必须是「用户上传的图片在前、文档插图在后」，
    #    所以 offset 用筛过的用户图片数量（不能直接用 len(turn.images)，里面可能有空串）
    #
    #    ⚠️ 丢到线程池里执行：文档解析是同步的，老版 .doc 还会借 Word COM 转换
    #       （1~3s，最坏 CONVERT_TIMEOUT_SECONDS）。直接在事件循环里跑会把整个后端冻住。
    user_images = [u for u in (turn.images or []) if u]
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
    context = ""
    if turn.persist:
        context = await conversation_service.build_context_prompt(user_id, session_id)
        history_text = typed or conversation_service.ATTACHMENT_PLACEHOLDER
        await conversation_service.save_message(
            user_id,
            session_id,
            "user",
            history_text,
            attachments=[a for a in (turn.attachments or []) if a] or None,
        )

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

    # ⑥ 有图片时改用多模态内容块（纯文本仍用字符串，尽量少改上游行为）
    effective_model, effective_provider = await _resolve_vision_safe_model(
        db, turn, bool(image_urls), session_id
    )
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
    try:
        async for chunk in db_config.stream_with_config(
            db,
            messages,
            provider=effective_provider,
            temperature=turn.temperature,
            thinking=turn.thinking,
            model=effective_model,
            # ⚠️ 必须带上，否则「个人中心 → 我的模型」里加的自定义模型永远选不中
            #   （无 user_id = 只可见系统行）
            user_id=turn.user_id,
        ):
            full_response += chunk
            yield chunk
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
