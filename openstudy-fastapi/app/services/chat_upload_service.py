"""聊天上传文件的持久化服务（2026-10-27）

把「用户在这一轮对话里传了什么」从**内存态**变成**可追溯的数据库记录**。

============================================================================
调用方
============================================================================

  ① `loop.py._collect_attachments()` —— 每轮开始前把当轮附件落盘入库
  ② `chat_file_manage` 工具 —— AI 按需取用历史文件 / 图片
  ③ 未来的前端「本对话文件」面板（数据已备好，只差 UI）

============================================================================
为什么要「落盘 + 入库」两件事都做
============================================================================

  只入库不落盘 → 图片要存 data URL，一张截图 500KB，库会被撑爆，
                 而且 `document_compose` 的图片字段要的是可 fetch 的地址；
  只落盘不入库 → AI 不知道有哪些文件，用户也没法"引用第二次"。

  所以：字节进 `UPLOAD_DIR/chat/`，库里存**相对路径 + 可访问 URL + 解析文本**。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chat_upload import ChatUploadFile, ChatUploadImage

#: 单个文件上限（与前端上传限制、`file_parser` 的预期一致）
MAX_FILE_BYTES = 40 * 1024 * 1024

#: 一个文件最多拆出多少张内嵌图片
#:
#: 不是技术限制，是产品判断：超过这个数的文档已经不是"带插图的资料"，
#: 而是图册。逐张落盘会把磁盘和列表都撑爆，而用户真正要插进题目里的
#: 通常只有一两张。
MAX_IMAGES_PER_FILE = 40


def _chat_dir() -> str:
    """聊天附件目录（按年月分桶，避免单目录几十万文件）"""
    now = datetime.now()
    rel = os.path.join("chat", f"{now.year:04d}", f"{now.month:02d}")
    full = os.path.join(settings.UPLOAD_DIR, rel)
    os.makedirs(full, exist_ok=True)
    return rel


def _img_dir() -> str:
    """内嵌图片目录"""
    now = datetime.now()
    rel = os.path.join("chat-images", f"{now.year:04d}", f"{now.month:02d}")
    full = os.path.join(settings.UPLOAD_DIR, rel)
    os.makedirs(full, exist_ok=True)
    return rel


def _safe_name(name: str) -> str:
    """文件名清洗（只用于拼接，展示名另存）"""
    import re

    base = os.path.basename((name or "file").replace("\\", "/"))
    base = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", base).strip(" ._")
    return (base or "file")[:80]


def _ext_of(name: str) -> str:
    base = os.path.basename(name or "")
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()[:20]


def _mime_of(name: str, data: bytes) -> str:
    """MIME 推断：先看扩展名表，再退回 magic bytes"""
    ext = _ext_of(name)
    table = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "svg": "image/svg+xml",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain",
        "md": "text/markdown",
        "csv": "text/csv",
    }
    if ext in table:
        return table[ext]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:2] == b"PK":
        return table["docx"]
    if data[:4] == b"%PDF":
        return "application/pdf"
    return "application/octet-stream"


def _decode_data_url(data_url: str) -> bytes:
    """把 `data:...;base64,xxx` 解成字节

    复用 `chat_engine.data_url_to_bytes`（它已经处理了纯 base64、缺前缀、
    带 URL 转义等边角），避免两处各写一份解码逻辑。
    """
    from app.services.ai.chat_engine import data_url_to_bytes

    content, _mime = data_url_to_bytes(data_url)
    return content


def _write_bytes(rel_dir: str, filename: str, data: bytes) -> str:
    """落盘并返回**文件名**（带 uuid 前缀，防同名覆盖）"""
    unique = f"{uuid.uuid4().hex[:12]}_{filename}"
    full = os.path.join(settings.UPLOAD_DIR, rel_dir, unique)
    with open(full, "wb") as fh:
        fh.write(data)
    return unique


# ============================================================
# 入库
# ============================================================

async def persist_attachments(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: str,
    attachments: List[Any],
    images: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """把本轮附件持久化，返回每条记录的精简信息

    Args:
        attachments: `AssistantAttachment` 对象或等价 dict（含 name/type/base64）
        images: 用户直接贴的图片（data URL 列表，不来自文件）

    设计取舍：
      · **解析失败也要入库**：文件本身存下来了，下次还能取；
        只是没有文本内容。比"解析失败就整条丢掉"好。
      · 解析结果缓存在 `parsed_json`，`chat_file_manage` 取用时直接读，
        不必二次解析（老 .doc 走 Word COM 一次要几秒）。
    """
    saved: List[Dict[str, Any]] = []
    sid = (session_id or "").strip()

    for item in attachments or []:
        name = _attachment_field(item, "name") or "file"
        raw = _attachment_field(item, "base64")
        if not raw:
            continue
        try:
            data = _decode_data_url(raw)
        except Exception:  # noqa: BLE001
            continue
        if not data or len(data) > MAX_FILE_BYTES:
            continue

        saved.append(
            await _persist_one_file(db, user_id=user_id, session_id=sid,
                                    name=name, data=data)
        )

    # 用户直接贴的图片：没有外层文件，file_id=0
    for idx, data_url in enumerate(images or []):
        try:
            data = _decode_data_url(data_url)
        except Exception:  # noqa: BLE001
            continue
        if not data:
            continue
        saved.append(
            await _persist_loose_image(db, user_id=user_id, session_id=sid,
                                       seq=idx, data=data)
        )

    return saved


def _attachment_field(item: Any, key: str) -> str:
    """兼容 pydantic 对象与 dict 两种形态"""
    if isinstance(item, dict):
        return str(item.get(key) or "")
    return str(getattr(item, key, "") or "")


async def _persist_one_file(
    db: AsyncSession, *, user_id: int, session_id: str, name: str, data: bytes
) -> Dict[str, Any]:
    """落盘 + 入库一个文件，并把它内嵌的图片逐张拆出来"""
    # ⚠️ 必须在**本函数内**导入（2026-10-27 踩坑）：
    #    原来只在 `persist_attachments()` 里 `from ... import parse_file`，
    #    那是**局部名字**，本函数根本看不见 → NameError →
    #    被 `except` 吞成 `parsed = {}` → 文件入库了但正文和图片全是 0。
    #    线上表现："已保存 1 个附件"，但库里 text_content / parsed_json 都是空、
    #    图片表 0 条，而且没有任何报错。
    from app.services.file_parser import parse_file

    ext = _ext_of(name)
    rel_dir = _chat_dir()
    stored = _write_bytes(rel_dir, _safe_name(name), data)
    rel_path = f"{rel_dir.replace(os.sep, '/')}/{stored}"

    text_content = ""
    parsed_json = ""
    try:
        # ⚠️ 丢到线程池：`parse_file` 是**同步阻塞**的，老 .doc 还会借 Word COM（几秒）。
        #    直接在 async 函数里调会把整个事件循环冻住 ——
        #    这轮对话的 SSE 事件会全部卡在这里（用户看到"卡住不动"）。
        import asyncio as _asyncio

        parsed = await _asyncio.to_thread(parse_file, name, data)
        text_content = str(parsed.get("textContent") or "")
        # 只留必要的键，别把整个对象塞进库（里面有 data URL 大字段）
        slim = {
            "blocks": parsed.get("blocks") or [],
            "totalTextLength": parsed.get("totalTextLength") or 0,
            "error": parsed.get("error"),
        }
        parsed_json = json.dumps(slim, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        # ⚠️ 必须把原因打出来（2026-10-27 实测教训）
        #
        # 第一版写的是 `except: parsed = {}`，静默吞掉。
        # 结果线上出现「文件成功入库、但正文和图片都是 0」——
        # 库里有记录、却没有任何内容，查不出为什么。
        #
        # 落盘仍然继续（文件本身已经存下来了，下次还能重解析），
        # 但**必须留下可诊断的信息**。
        from loguru import logger

        logger.warning(f"[upload] 解析失败（文件已落盘，仅缺正文/图片）: {type(e).__name__}: {e}")
        parsed = {}

    row = ChatUploadFile(
        user_id=user_id,
        session_id=session_id,
        file_name=name,
        file_ext=ext,
        mime_type=_mime_of(name, data),
        size=len(data),
        rel_path=rel_path,
        url=f"/profile/{rel_path}",
        text_content=text_content,
        parsed_json=parsed_json,
    )
    db.add(row)
    await db.flush()  # 拿到 row.id

    # ── 拆内嵌图片 ──
    images_out: List[Dict[str, Any]] = []
    raw_images = parsed.get("images") if isinstance(parsed, dict) else None
    for seq, im in enumerate((raw_images or [])[:MAX_IMAGES_PER_FILE]):
        if not isinstance(im, dict):
            continue
        data_url = str(im.get("imageUrl") or "")
        if not data_url.startswith("data:"):
            continue
        try:
            img_bytes = _decode_data_url(data_url)
        except Exception:  # noqa: BLE001
            continue
        if not img_bytes:
            continue

        img_name = _safe_name(str(im.get("imageName") or f"image{seq + 1}.png"))
        img_dir = _img_dir()
        img_stored = _write_bytes(img_dir, img_name, img_bytes)
        img_rel = f"{img_dir.replace(os.sep, '/')}/{img_stored}"

        img_row = ChatUploadImage(
            user_id=user_id,
            file_id=row.id,
            seq=seq,
            image_name=img_name,
            mime_type=_mime_of(img_name, img_bytes),
            size=len(img_bytes),
            rel_path=img_rel,
            url=f"/profile/{img_rel}",
        )
        db.add(img_row)
        await db.flush()
        images_out.append({
            "imageId": img_row.id,
            "seq": seq,
            "imageName": img_name,
            "url": img_row.url,
            "size": len(img_bytes),
        })

    await db.commit()

    return {
        "fileId": row.id,
        "fileName": name,
        "ext": ext,
        "size": len(data),
        "url": row.url,
        "textLength": len(text_content),
        "imageCount": len(images_out),
        "images": images_out,
    }


async def _persist_loose_image(
    db: AsyncSession, *, user_id: int, session_id: str, seq: int, data: bytes
) -> Dict[str, Any]:
    """用户直接贴的图片（不属于任何文件）"""
    ext = "png"
    if data[:2] == b"\xff\xd8":
        ext = "jpg"
    elif data[:4] == b"RIFF":
        ext = "webp"
    img_name = f"pasted_{datetime.now():%H%M%S}_{seq}.{ext}"

    img_dir = _img_dir()
    stored = _write_bytes(img_dir, img_name, data)
    rel = f"{img_dir.replace(os.sep, '/')}/{stored}"

    img_row = ChatUploadImage(
        user_id=user_id,
        file_id=0,
        seq=seq,
        image_name=img_name,
        mime_type=_mime_of(img_name, data),
        size=len(data),
        rel_path=rel,
        url=f"/profile/{rel}",
    )
    db.add(img_row)
    await db.commit()

    return {
        "fileId": 0,
        "fileName": img_name,
        "ext": ext,
        "size": len(data),
        "url": img_row.url,
        "textLength": 0,
        "imageCount": 1,
        "images": [{
            "imageId": img_row.id, "seq": seq,
            "imageName": img_name, "url": img_row.url, "size": len(data),
        }],
    }


# ============================================================
# 查询
# ============================================================

async def list_files(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: str = "",
    include_other_sessions: bool = True,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """列出用户上传过文件

    Args:
        session_id: 当前会话 id
        include_other_sessions:
            True  —— 连**别的会话**传的也列出来（用户说"我之前传的那份"，
                     往往记不清是哪个对话）；
            False —— 只看当前会话。

    ⚠️ 默认 True 是刻意的：用户跨对话记不住文件传在哪儿，
       "我上次传的期末卷"可能在上周的对话里。宁可多给几条让模型挑，
       也不要因为限定当前会话而"找不到"。
    """
    stmt = select(ChatUploadFile).where(
        ChatUploadFile.user_id == user_id,
        ChatUploadFile.deleted == 0,
    )
    if session_id and not include_other_sessions:
        stmt = stmt.where(ChatUploadFile.session_id == session_id)
    stmt = stmt.order_by(ChatUploadFile.id.desc()).limit(max(1, min(limit, 50)))

    rows = (await db.execute(stmt)).scalars().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        img_count = await _count_images(db, file_id=r.id)
        out.append({
            "fileId": r.id,
            "fileName": r.file_name,
            "ext": r.file_ext,
            "size": r.size,
            "url": r.url,
            "sessionId": r.session_id,
            "textLength": len(r.text_content or ""),
            "imageCount": img_count,
            "createTime": r.create_time.strftime("%Y-%m-%d %H:%M") if r.create_time else "",
            "isCurrentSession": (r.session_id == session_id) if session_id else False,
        })
    return out


async def _count_images(db: AsyncSession, *, file_id: int) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(ChatUploadImage).where(
        ChatUploadImage.file_id == file_id,
        ChatUploadImage.deleted == 0,
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def list_images(
    db: AsyncSession,
    *,
    user_id: int,
    file_id: Optional[int] = None,
    session_id: str = "",
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """列出图片（可按来源文件过滤）"""
    stmt = select(ChatUploadImage).where(
        ChatUploadImage.user_id == user_id,
        ChatUploadImage.deleted == 0,
    )
    if file_id is not None:
        stmt = stmt.where(ChatUploadImage.file_id == file_id)
    stmt = stmt.order_by(ChatUploadImage.id.desc()).limit(max(1, min(limit, 100)))

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "imageId": r.id,
            "fileId": r.file_id,
            "seq": r.seq,
            "imageName": r.image_name,
            "mimeType": r.mime_type,
            "size": r.size,
            "url": r.url,
            "createTime": r.create_time.strftime("%Y-%m-%d %H:%M") if r.create_time else "",
        }
        for r in rows
    ]


async def get_file(
    db: AsyncSession, *, user_id: int, file_id: int
) -> Optional[Dict[str, Any]]:
    """取单个文件（含解析后的文本）"""
    stmt = select(ChatUploadFile).where(
        ChatUploadFile.id == file_id,
        ChatUploadFile.user_id == user_id,
        ChatUploadFile.deleted == 0,
    )
    r = (await db.execute(stmt)).scalars().first()
    if not r:
        return None

    imgs = await list_images(db, user_id=user_id, file_id=file_id)
    return {
        "fileId": r.id,
        "fileName": r.file_name,
        "ext": r.file_ext,
        "mimeType": r.mime_type,
        "size": r.size,
        "url": r.url,
        "relPath": r.rel_path,
        "sessionId": r.session_id,
        "text": r.text_content or "",
        "images": imgs,
        "imageCount": len(imgs),
        "createTime": r.create_time.strftime("%Y-%m-%d %H:%M") if r.create_time else "",
    }


async def soft_delete(db: AsyncSession, *, user_id: int, file_id: int) -> bool:
    """软删文件（连同它的图片）"""
    res = await db.execute(
        update(ChatUploadFile)
        .where(ChatUploadFile.id == file_id, ChatUploadFile.user_id == user_id)
        .values(deleted=1)
    )
    await db.execute(
        update(ChatUploadImage)
        .where(ChatUploadImage.file_id == file_id, ChatUploadImage.user_id == user_id)
        .values(deleted=1)
    )
    await db.commit()
    return bool(getattr(res, "rowcount", 0))
