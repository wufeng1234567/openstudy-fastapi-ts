"""`gallery_manage` —— 在画廊里找图、取图（Agent 自封装，**只读**）

为什么需要它
============
画廊是文档插图与聊天图片的统一图片资产层：一张图有稳定的 `assetKey`
（文档图 `doc:{docId}:{seq}`，聊天图 `chat:{imageId}`）、可访问的 `url`、
来源章节和可选的描述/OCR。用户会说：

    「把画廊里那张受力分析图插到笔记里」
    「用资料里那张电路图给这份文档配图」
    「画廊里有没有概率论第三章的图？」

在此之前智能体只能看到文字检索结果里顺带返回的图片 URL；它没有入口
**主动列出 / 搜索 / 取用**画廊资产，也无法拿到 `assetKey`（知识百科
`wiki_manage.attach_image` 需要它）。本工具把这条路补上。

复用而不是重做
==============
数据读取全部复用 `services/rag/gallery_service.py`：
  · `list_gallery` —— 真实图片索引、统计、文档筛选项；
  · `get_asset_detail` —— 单张图的来源、描述、OCR、引用/使用记录。
本工具只做三件事：参数校验、把画廊对象压缩成模型/前端都能用的卡片、
给出诚实的“没找到 / 没描述”提示。

输出契约
========
`list` / `search` 返回 `images: [...]`，每项带 `assetKey` / `url` /
`imageName` / `caption` / `sourceName` / `sectionTitle` / `descriptionStatus`；
`get` 返回单张图的完整字段。`url` 是站内 `/profile/...` 相对路径，可直接
传给 `document_compose` 的 image block、`question_manage` 的解析图片字段；
`assetKey` 可传给 `wiki_manage(action=attach_image)`。

⚠️ 不伪造：图片没有描述时只按文件名/章节/关键词返回，并在 message 里明确
说明“没有描述，不要猜画面内容”。绝不用模型臆造 caption/OCR。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 一次最多返回多少张（模型上下文与前端卡片都要控制）
DEFAULT_LIMIT = 12
MAX_LIMIT = 30

#: 列表里每张图最多带多少描述/上下文；详情页再放宽
LIST_CAPTION_CHARS = 240
DETAIL_CAPTION_CHARS = 1200
DETAIL_OCR_CHARS = 1200
DETAIL_SURROUNDING_CHARS = 600

_VALID_SOURCES = {"all", "document", "chat"}
_VALID_STATUS = {"all", "pending", "processing", "done", "failed"}

_STATUS_TEXT = {
    "done": "已生成描述",
    "pending": "未生成描述",
    "processing": "描述生成中",
    "failed": "描述失败",
}


def _clip(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _limit_of(params: Dict[str, Any]) -> int:
    value = _as_int(params.get("limit"), DEFAULT_LIMIT)
    return max(1, min(MAX_LIMIT, value))


def _asset_to_card(item: Dict[str, Any], *, detail: bool = False) -> Dict[str, Any]:
    """把 `gallery_service` 的资产对象压成卡片/模型共用形状。

    ⚠️ 前端 `ChatFileAssetCard` 认的是 `images[]`（原来给 `chat_file_manage` 用），
    所以这里保留 `imageName` 这个键；不伪造不存在的 `imageId`。
    """
    asset_key = str(item.get("assetKey") or "").strip()
    file_name = str(item.get("fileName") or "").strip()
    source_name = str(item.get("sourceName") or "").strip()
    section_title = str(item.get("sectionTitle") or "").strip()
    caption = _clip(item.get("caption"), DETAIL_CAPTION_CHARS if detail else LIST_CAPTION_CHARS)
    status = str(item.get("descriptionStatus") or "pending").strip().lower()
    meta_parts = [part for part in (source_name, section_title) if part]
    card: Dict[str, Any] = {
        "assetKey": asset_key,
        "imageName": file_name or f"图片 {asset_key}",
        "url": str(item.get("url") or ""),
        "sourceType": str(item.get("sourceType") or ""),
        "sourceName": source_name,
        "docId": item.get("docId"),
        "kbId": item.get("kbId"),
        "sectionTitle": section_title,
        "offset": item.get("offset"),
        "caption": caption,
        "keywords": list(item.get("keywords") or [])[:8],
        "kind": str(item.get("kind") or "image"),
        "descriptionStatus": status,
        "descriptionStatusText": _STATUS_TEXT.get(status, status or "未知"),
        "usableAsImageSource": bool(str(item.get("url") or "").strip()),
        "meta": " · ".join(meta_parts),
        "createTime": str(item.get("createTime") or ""),
    }
    if detail:
        card["ocrText"] = _clip(item.get("ocrText"), DETAIL_OCR_CHARS)
        card["surroundingText"] = _clip(item.get("surroundingText"), DETAIL_SURROUNDING_CHARS)
        card["descriptionModel"] = str(item.get("descriptionModel") or "")
        card["describeError"] = str(item.get("describeError") or "")
        card["usedCount"] = int(item.get("usedCount") or 0)
        card["referenceCount"] = int(item.get("referenceCount") or 0)
        card["canLocate"] = bool(item.get("canLocate"))
    return card


def _has_description(card: Dict[str, Any]) -> bool:
    return bool(str(card.get("caption") or "").strip() or str(card.get("ocrText") or "").strip())


def _search_text(item: Dict[str, Any]) -> str:
    """把一张图的全部可检索字段拼成小写文本。"""
    return " ".join(
        str(part or "")
        for part in (
            item.get("caption"),
            item.get("ocrText"),
            item.get("fileName"),
            item.get("sourceName"),
            item.get("sectionTitle"),
            " ".join(str(x) for x in (item.get("keywords") or [])),
            item.get("kind"),
        )
    ).lower()


#: 2 字片段里纯连接/结构性的噪音（「模式下的分流」会被「的分」误命中）
_LOW_SIGNAL_GRAMS = {"的分", "章的", "论第", "的图", "和图", "的资"}
_CHAPTER_RE = re.compile(r"第[一二三四五六七八九十百千万零〇0-9]+章")


def _search_terms(query: str) -> List[str]:
    """把自然语言问题拆成可匹配的词。

    中文没有空格，整串子串匹配几乎必然搜不到（用户会说「概率论第三章的分布图」，
    而索引里分别只有「概率论」「分布图」）。所以：
      · 先按空白/标点切词；
      · 再对连续中文补 2 字片段（概率 / 率论 / 分布 / 布图 …）做覆盖率匹配；
      · 「第X章」单独保留，防止章节词被 2 字片段拆碎；
      · 过滤「的分」「章的」这类纯连接片段，否则「模式下的分流」会误命中图片。
    """
    raw = str(query or "").strip().lower()
    if not raw:
        return []
    terms = [x for x in re.split(r"[\s,，、;；:：/\\|·.。!！?？()（）\[\]【】]+", raw) if x]
    # 对每个较长的中文词再补 2 字片段；整串仍保留，精确命中会优先。
    extra: List[str] = list(_CHAPTER_RE.findall(raw))
    for term in terms:
        if len(term) >= 4 and re.search(r"[\u4e00-\u9fff]", term):
            for i in range(len(term) - 1):
                gram = term[i : i + 2]
                if gram in _LOW_SIGNAL_GRAMS:
                    continue
                # 章节词由 _CHAPTER_RE 完整保留，不再拆成「第三 / 三章」这种碎片
                if gram.startswith("第") and "章" in raw:
                    continue
                if gram.endswith("章") and _CHAPTER_RE.search(raw):
                    continue
                extra.append(gram)
    return list(dict.fromkeys(terms + extra))


def _search_score(item: Dict[str, Any], query: str) -> int:
    """按命中字段给图片打分；0 = 不相关。

    这不是语义向量检索，而是**可解释的元数据检索**：命中的是描述/OCR/文件名/
    来源/章节/关键词。没有描述的图片仍能按文件名和章节命中，但不会被当成
    「模型看过图」。
    """
    text = _search_text(item)
    raw = str(query or "").strip().lower()
    if not raw or not text:
        return 0
    score = 0
    if raw in text:
        score += 20
    for term in _search_terms(raw):
        if term and term in text:
            # 长词命中比 2 字片段更有信息量
            score += min(8, max(1, len(term)))
    return score


def _rank_items(items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    scored = [(_search_score(item, query), index, item) for index, item in enumerate(items)]
    matched = [row for row in scored if row[0] > 0]
    matched.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in matched]


def _filters(params: Dict[str, Any]) -> Dict[str, Any]:
    """读取/校验筛选参数。返回 `{ok, error, hint, ...}`，不抛异常。"""
    source = str(params.get("source") or "all").strip().lower() or "all"
    if source not in _VALID_SOURCES:
        return {"ok": False, "error": "source 只能是 all / document / chat"}
    status = str(params.get("status") or "all").strip().lower() or "all"
    if status not in _VALID_STATUS:
        return {"ok": False, "error": "status 只能是 all / pending / processing / done / failed"}

    doc_id = _as_int(params.get("doc_id"), 0) or None
    kb_id = _as_int(params.get("kb_id"), 0) or None
    if doc_id is not None and doc_id < 1:
        return {"ok": False, "error": "doc_id 必须是正整数"}
    if kb_id is not None and kb_id < 1:
        return {"ok": False, "error": "kb_id 必须是正整数"}

    return {
        "ok": True,
        "source": source,
        "status": status,
        "doc_id": doc_id,
        "kb_id": kb_id,
        # gallery_service 的 kbId 过滤只在 scope=current 时生效；这里保持同一口径。
        "scope": "current" if kb_id is not None else "all",
    }


class GalleryManageTool(AgentTool):
    name = "gallery_manage"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 / Function Calling）
    description = (
        "Browse and retrieve images from the user's Gallery — the unified image-asset "
        "layer built from their documents and chat uploads. Use this whenever the user "
        "refers to a picture they already have: 'the diagram in my materials', 'that "
        "circuit image in the gallery', 'find a picture about probability', 'use the "
        "third figure from that document', or 'put a gallery image into my document'. "
        "Actions:\n"
        "  · list   — recent gallery images; optional filters: source (all/document/chat), "
        "doc_id, kb_id, status, limit.\n"
        "  · search — find images by caption, OCR text, file name, source document or "
        "section title (requires `query`). This is metadata search; if an image has no "
        "description yet, only its file/section can match — never invent what it shows.\n"
        "  · get    — read one image by `asset_key`; returns its URL, source, description, "
        "OCR and usage records.\n"
        "IMPORTANT: returned `url` values (/profile/...) are directly usable as image "
        "sources in document_compose image blocks or question_manage image fields; "
        "`assetKey` is what wiki_manage action=attach_image expects. Call list/search "
        "first; never invent an asset_key. Do NOT ask the user to re-upload an image "
        "that is already in their gallery."
    )
    description_zh = (
        "在画廊里找图、取图：list=看最近的图片，search=按描述/OCR/文件名/章节搜，"
        "get=按 assetKey 取单张。返回的 url 可直接用于题目/文档配图，assetKey 可用于知识百科挂图。"
    )
    label = "画廊图片"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "get"],
                "description": "Operation to perform.",
            },
            "query": {
                "type": "string",
                "description": (
                    "What image the user is looking for, in their own words "
                    "(required for search; matches caption / OCR / file name / "
                    "source document / section title / keywords)."
                ),
            },
            "asset_key": {
                "type": "string",
                "description": (
                    "Gallery asset key returned by list/search, e.g. doc:123:0 or "
                    "chat:45 (required for get). Never invent it."
                ),
            },
            "source": {
                "type": "string",
                "description": "Filter by image source: all, document or chat (default all).",
                "enum": ["all", "document", "chat"],
            },
            "doc_id": {
                "type": "integer",
                "description": "Only images from this document ID (from workspace_search or list results).",
            },
            "kb_id": {
                "type": "integer",
                "description": "Only images from this knowledge-base ID.",
            },
            "status": {
                "type": "string",
                "description": "Filter by description status (default all).",
                "enum": ["all", "pending", "processing", "done", "failed"],
            },
            "limit": {
                "type": "integer",
                "description": f"Max images to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).",
            },
        },
        "required": ["action"],
    }
    #: 只读：不会写用户数据（gallery 同步只是索引缓存）
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "list").strip().lower()
        if action not in {"list", "search", "get"}:
            return fail(
                f"未知操作：{action}",
                "action 只能是 list / search / get",
            )
        if action == "search" and not str(params.get("query") or "").strip():
            return fail(
                "search 需要 query",
                "请把用户描述的图片内容放进 query，例如「概率论第三章的分布图」",
            )
        if action == "get" and not str(params.get("asset_key") or "").strip():
            return fail(
                "get 需要 asset_key",
                "请先 action=list 或 action=search 找到图片的 assetKey",
            )
        if action in {"list", "search"}:
            filters = _filters(params)
            if not filters.get("ok"):
                return fail(
                    str(filters["error"]),
                    "请检查 source / status / doc_id / kb_id 参数",
                )
        user_id = int(getattr(ctx, "user_id", 0) or 0)
        if not user_id:
            return fail("缺少用户身份，无法读取画廊")

        # 复用独立会话：画廊同步会写索引缓存（flush），且工具可能在流式生成器里
        # 晚于请求级 `get_db` 的生命周期执行。自建会话并显式 commit，行为与
        # `chat_file_manage` 一致（见那边的实测注释）。
        from app.database import async_session_factory

        async with async_session_factory() as db:
            if action == "get":
                return await self._get(db, user_id, params)
            return await self._list(db, user_id, params, action)

    async def _list(
        self,
        db,
        user_id: int,
        params: Dict[str, Any],
        action: str,
    ) -> Dict[str, Any]:
        query = str(params.get("query") or "").strip()
        if action == "search" and not query:
            return fail(
                "search 需要 query",
                "请把用户描述的图片内容放进 query，例如「概率论第三章的分布图」",
            )
        filters = _filters(params)
        if not filters.get("ok"):
            return fail(str(filters["error"]), "请检查 source / status / doc_id / kb_id 参数")

        from app.services.rag import gallery_service

        try:
            # search 先在服务端取回当前筛选范围内的图片，再用本工具的分词评分排序；
            # 直接依赖 `_matches_q` 的整串子串会把自然语言问题大量漏掉（见 _search_terms）。
            result = await gallery_service.list_gallery(
                db,
                user_id,
                scope=str(filters["scope"]),
                kb_id=filters["kb_id"],
                doc_id=filters["doc_id"],
                source=str(filters["source"]),
                status=str(filters["status"]),
                q="",
                limit=500 if action == "search" else _limit_of(params),
            )
            # 索引同步是 flush + 查询；这里显式提交，避免独立会话关闭后丢失补同步结果。
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - 工具层永远返回结构化 fail
            await db.rollback()
            return fail(
                f"读取画廊失败：{exc}",
                "请确认画廊已有图片；如果图片刚上传，稍后再试。",
            )

        raw_items = list(result.get("items") or [])
        if action == "search":
            raw_items = _rank_items(raw_items, query)[: _limit_of(params)]
        items: List[Dict[str, Any]] = [_asset_to_card(item) for item in raw_items]
        stats = result.get("stats") or {}
        total = int(stats.get("total") or 0)
        images = [item for item in items if item.get("assetKey") and item.get("url")]

        if action == "search":
            if images:
                best = images[0].get("imageName") or "图片"
                message = f"在画廊找到 {len(images)} 张和「{query}」相关的图片，最匹配的是「{best}」。"
            elif total == 0:
                message = "画廊里还没有图片。先让用户上传含图片的资料，或在聊天里发图。"
            else:
                message = (
                    f"画廊里有 {total} 张图，但没有匹配「{query}」的。"
                    "可能图片描述还没生成；可以让用户在画廊点「补全描述」，或者换个关键词。"
                )
        else:
            if images:
                message = f"画廊里共有 {total} 张图，当前显示 {len(images)} 张。"
            elif total == 0:
                message = "画廊里还没有图片。先让用户上传含图片的资料，或在聊天里发图。"
            else:
                message = f"画廊里共有 {total} 张图，但当前筛选条件没有可显示的图片。"

        if images and not any(_has_description(item) for item in images):
            message += "这些图片还没有生成描述，检索只匹配到文件名/章节；不要凭空猜测画面内容。"

        data: Dict[str, Any] = {
            "assetSource": "gallery",
            "count": len(images),
            "total": total,
            "stats": stats,
            "images": images,
            "documents": result.get("documents") or [],
            "galleryUrl": "/front/workspace?view=gallery",
            "note": (
                "Use the returned `url` directly as an image source in document_compose "
                "or question_manage. To link an image to a Knowledge Wiki page, pass "
                "its `assetKey` to wiki_manage action=attach_image. Never invent URL or assetKey."
            ),
        }
        if action == "search":
            data["query"] = query
        return ok(action=action, **data, message=message)

    async def _get(
        self,
        db,
        user_id: int,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        asset_key = str(params.get("asset_key") or "").strip()
        if not asset_key:
            return fail(
                "get 需要 asset_key",
                "请先 action=list 或 action=search 找到图片的 assetKey",
            )
        from app.services.rag import gallery_service

        try:
            detail = await gallery_service.get_asset_detail(db, user_id, asset_key)
            await db.commit()
        except ValueError as exc:
            return fail(str(exc), "请确认 assetKey 来自当前用户的画廊列表")
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            return fail(f"读取图片失败：{exc}", "请稍后重试，或先用 action=list 查看画廊")

        card = _asset_to_card(detail, detail=True)
        if _has_description(card):
            message = (
                f"已读取图片「{card['imageName']}」"
                + (f"：{card['caption']}" if card.get("caption") else "")
            )
        else:
            message = (
                f"已读取图片「{card['imageName']}」，但这张图还没有生成描述；"
                "目前只能依据来源和章节使用，不要猜测图片内容。"
            )

        return ok(
            action="get",
            assetSource="gallery",
            **card,
            images=[card],
            usage=(
                "把 `url` 直接传给 document_compose 的 image 块、"
                "question_manage 的图片字段；把 `assetKey` 传给 wiki_manage action=attach_image。"
            ),
            usages=(detail.get("usages") or [])[:8],
            references=(detail.get("references") or [])[:8],
            message=message,
        )


__all__ = ["GalleryManageTool"]
