"""
`chat_file_manage` —— 取用用户在对话里上传过的文件与图片（2026-10-27）

============================================================================
它解决什么
============================================================================

用户反馈原话：

    「图片 文件类的东西 ai他无法进行持久化操作
      比如我上传了一个word给他排版 他无法获得到里面的图片
      并且无法让图片可以插入到我们的题库、笔记、word之类的里面
      文件类数据持久化也没有做到
      比如用户第一次询问 然后第二次让他插入图片 他也没办法获取到
      用户之前上传过的图片
      需要一个合理的方案解决这个问题
      比如需要给ai提供一个接口让他可以获取到当前聊天记录上传过的文件
      包括图片 、 文档等等
      不仅仅是可以阅读 是要可以进行操作
      就是指挥调用这些系统内已经储存好了的用户文件」

典型对话：

    用户：（传 题库测试.docx）「整理一下」
    AI：  (排版，但图片丢了)

    用户：「你没有获得到 word 里面的图片吗」
    AI：  「确实没有拿到」        ← 修复前只能这样答

    用户：「把那张手写解答图插到第 4 题解析里」
    AI：  调用本工具 → 拿到 `/profile/chat-images/...png`
         → 交给 question_manage 写进解析

============================================================================
与 `workspace_search` 的分工
============================================================================

    `workspace_search` 找的是**「我的空间」/ 知识库**里的文档（有 docId、可语义检索）；
    本工具找的是**「这次聊天窗口里传给我的」**文件和图（保真、按文件与图片粒度）。

    两者数据源完全不同，不能互相替代：
      · 知识库文档是"要长期检索的语料"，会被切块；
      · 聊天附件是"用户这次给我的素材"，必须原样能取回。

============================================================================
"不仅仅可以阅读，要可以操作"
============================================================================

所以 `action` 除了 list/get，还提供：

    · get_image   —— 拿到单张图的 URL，可直接塞进题目解析 / 笔记 / 文档
    · get_text    —— 拿到纯文本，直接给模型读
    · get_parsed  —— 拿到结构化 blocks（重新排版时用）

拿到的 `url` 是 `/profile/...` 形式，`document_compose` 的 image 块、
`question_manage` 的解析字段、`note_manage` 的图片字段都能直接吃。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy import select

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.models.chat_upload import ChatUploadFile


class ChatFileManageTool(AgentTool):
    name = "chat_file_manage"
    label = "对话文件"
    description = (
        "Access files and images the user uploaded **in this chat window** (earlier turns "
        "included). Use this whenever the user refers to something they attached before: "
        "'the Word file I sent', 'that image in my document', 'insert the handwritten "
        "solution photo', 'use the picture I uploaded'. "
        "\n"
        "Actions:\n"
        "  · list       — list uploaded files (id, name, size, image count). Call this FIRST "
        "when you are not sure what the user uploaded.\n"
        "  · get        — one file's full text plus the list of images embedded in it.\n"
        "  · get_image  — a single image by imageId, returns a URL you can pass to "
        "document_compose / question_manage / note_manage to actually USE the image.\n"
        "  · list_images — all images the user uploaded, optionally filtered by fileId.\n"
        "  · get_parsed — the structured block list of a file (headings/paragraphs/tables/"
        "images) for re-layout work.\n"
        "\n"
        "IMPORTANT: the returned `url` values (/profile/...) are directly usable as image "
        "sources in other tools. Do NOT ask the user to re-upload — the file is already here."
    )
    description_zh = (
        "取用用户在**本次对话**里上传过的文件和图片（含之前轮次）。"
        "当用户提到「我传的那份 Word」「我文档里的那张图」「把手写解答图插进去」时用它。"
        "list 先看有哪些；get 取正文+图片清单；get_image 取单张图的 URL，"
        "可直接用于题库解析 / 笔记 / 文档编排；get_parsed 取结构化块用于重新排版。"
        "返回的 URL 能直接喂给其他工具，不要让用户重新上传。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "get_image", "list_images", "get_parsed"],
                "description": "What to fetch.",
            },
            "file_id": {
                "type": "integer",
                "description": "Target file id (from action=list). Required for get/get_parsed.",
            },
            "image_id": {
                "type": "integer",
                "description": "Target image id (from action=list_images or a file's images).",
            },
            "include_other_sessions": {
                "type": "boolean",
                "description": (
                    "For action=list: also list files uploaded in OTHER conversations. "
                    "Default true — users rarely remember which chat they uploaded in."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max items to return (default 20).",
            },
        },
        "required": ["action"],
    }

    #: 只读查询，不写用户数据
    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext):
        from app.services import chat_upload_service as svc

        action = str(params.get("action") or "").strip().lower()
        user_id = int(getattr(ctx, "user_id", 0) or 0)
        if not user_id:
            return fail("缺少用户身份，无法读取上传文件")

        session_id = str(getattr(ctx, "session_id", "") or "")
        limit = _as_int(params.get("limit"), 20)

        # ⚠️ 这里**总是自建 session**，不复用 `ctx.db`（2026-10-27 实测踩坑）
        #
        # 工具是在 `run_agent_stream` 这个**流式生成器**里被调用的，
        # 那时 `get_db()` 的 `yield` 早已返回、它的 `commit()` 也跑完了。
        # 用 `ctx.db` 读到的是那一刻之后的连接状态，
        # 而本工具要读的是**本轮刚持久化**的附件 —— 用独立 session 才拿得准。
        #
        # 只读查询，多开一条连接的成本可以忽略。
        from app.database import async_session_factory

        async with async_session_factory() as db:
            return await self._dispatch(db, svc, action=action, user_id=user_id,
                                        session_id=session_id, limit=limit,
                                        params=params)

    async def _dispatch(self, db, svc, *, action: str, user_id: int,
                        session_id: str, limit: int, params: Dict[str, Any]):
        if action == "list":
            include_other = _as_bool(params.get("include_other_sessions"), default=True)
            files = await svc.list_files(
                db, user_id=user_id, session_id=session_id,
                include_other_sessions=include_other, limit=limit,
            )
            if not files:
                return ok(
                    message="这个对话里还没有上传过文件。",
                    data={"files": [], "count": 0},
                )
            total_imgs = sum(f["imageCount"] for f in files)
            return ok(
                message=(
                    f"找到 {len(files)} 个上传文件"
                    + (f"，内含 {total_imgs} 张图片" if total_imgs else "")
                    + "。"
                ),
                data={"files": files, "count": len(files), "totalImages": total_imgs},
            )

        if action == "get":
            fid = _as_int(params.get("file_id"), 0)
            if not fid:
                return fail("请提供 file_id（先用 action=list 查有哪些文件）")
            info = await svc.get_file(db, user_id=user_id, file_id=fid)
            if not info:
                return fail(
                    f"找不到文件 id={fid}（可能已被删除，或者不属于当前用户）",
                    hint="先 action=list 看当前有哪些文件。",
                )
            text = info.get("text") or ""
            truncated = len(text) > 20000
            return ok(
                message=(
                    f"已读取《{info['fileName']}》"
                    f"（{_human(info['size'])}，正文 {len(text)} 字"
                    + (f"，{info['imageCount']} 张图片" if info["imageCount"] else "")
                    + "）。"
                ),
                data={
                    "fileId": info["fileId"],
                    "fileName": info["fileName"],
                    "url": info["url"],
                    "size": info["size"],
                    "text": text[:20000],
                    "textTruncated": truncated,
                    "textLength": len(text),
                    "images": info.get("images") or [],
                    "imageCount": info["imageCount"],
                },
            )

        if action == "get_image":
            iid = _as_int(params.get("image_id"), 0)
            if not iid:
                return fail("请提供 image_id（先用 action=list_images 查）")
            imgs = await svc.list_images(db, user_id=user_id, limit=100)
            target = next((x for x in imgs if x["imageId"] == iid), None)
            if not target:
                return fail(f"找不到图片 id={iid}")
            return ok(
                message=(
                    f"图片 {target['imageName']}（{_human(target['size'])}）。"
                    "它的 url 可以直接用于题目解析、笔记图片或文档编排。"
                ),
                data={
                    **target,
                    "usableAsImageSource": True,
                    "usage": (
                        "把这个 url 直接传给 document_compose 的 image 块、"
                        "question_manage 的解析字段、或 note_manage 的图片字段。"
                    ),
                },
            )

        if action == "list_images":
            fid = params.get("file_id")
            fid_int = _as_int(fid, -1) if fid is not None else None
            imgs = await svc.list_images(
                db, user_id=user_id,
                file_id=(fid_int if fid_int is not None and fid_int >= 0 else None),
                limit=limit,
            )
            if not imgs:
                return ok(message="没有找到图片。", data={"images": [], "count": 0})
            return ok(message=f"找到 {len(imgs)} 张图片。", data={"images": imgs, "count": len(imgs)})

        if action == "get_parsed":
            fid = _as_int(params.get("file_id"), 0)
            if not fid:
                return fail("请提供 file_id")
            info = await svc.get_file(db, user_id=user_id, file_id=fid)
            if not info:
                return fail(f"找不到文件 id={fid}")
            blocks = await _load_blocks(db, user_id=user_id, file_id=fid)
            return ok(
                message=(
                    f"《{info['fileName']}》共 {len(blocks)} 个内容块"
                    f"（含 {info['imageCount']} 张图片）。"
                ),
                data={
                    "fileId": fid,
                    "fileName": info["fileName"],
                    "blocks": blocks,
                    "blockCount": len(blocks),
                    "images": info.get("images") or [],
                },
            )

        return fail(
            f"未知 action：{action}",
            hint="action 只能是 list / get / get_image / list_images / get_parsed",
        )


async def _load_blocks(db, *, user_id: int, file_id: int) -> List[Dict[str, Any]]:
    """从 `parsed_json` 取出结构化块

    ⚠️ 不存在时返回空列表而不是报错：这份文件可能是纯图片（没有 blocks），
       或者当初解析失败了。空列表让模型能说"这个文件没有可提取的结构"。
    """
    stmt = select(ChatUploadFile).where(
        ChatUploadFile.id == file_id,
        ChatUploadFile.user_id == user_id,
        ChatUploadFile.deleted == 0,
    )
    row = (await db.execute(stmt)).scalars().first()
    if not row or not row.parsed_json:
        return []
    try:
        parsed = json.loads(row.parsed_json)
    except (json.JSONDecodeError, TypeError):
        return []
    blocks = parsed.get("blocks")
    return blocks if isinstance(blocks, list) else []


def _human(size: int) -> str:
    n = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_bool(v: Any, *, default: bool) -> bool:
    """把模型给的各种真假值写法统一"""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ("", "null", "none"):
        return default
    return s not in ("false", "0", "no", "off", "否")
