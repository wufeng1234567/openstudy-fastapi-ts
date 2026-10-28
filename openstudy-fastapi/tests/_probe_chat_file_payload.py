"""对话文件结构化块的上下文安全回归（2026-10-28）

用户重新导入历史文档时遇到：
  This model's maximum context length is 1048576 tokens. However, you requested
  1338194 tokens...
根因：`chat_file_manage.get_parsed` 把 `parsed_json` 里的图片 data URL 原样返回，
一份 96 块、13 张图的 docx 序列化后接近 2MB，直接撑爆模型上下文。

本探针用最近一份「大 parsed_json」的真实上传文件验证：
  · 返回的 blocks 不含 `data:image`;
  · 图片改成可访问的 `/profile/chat-images/...` URL；
  · 序列化体积 < 200KB（真实文件 18 当前约 10KB）。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401
import app.models.menu  # noqa: F401
import app.models.role  # noqa: F401
import app.models.user  # noqa: F401
from sqlalchemy import select

from app.database import async_session_factory
from app.models.chat_upload import ChatUploadFile
from app.services.ai.agent.base import ToolContext
from app.services.ai.agent.tools.chat_file_manage import ChatFileManageTool


async def main():
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(ChatUploadFile)
                .where(ChatUploadFile.deleted == 0)
                .order_by(ChatUploadFile.id.desc())
            )
        ).scalars().all()
    target = next((r for r in rows if len(r.parsed_json or "") > 100_000), None)
    if target is None:
        print("SKIP：库里没有大 parsed_json 的上传文件可测")
        return

    result = await ChatFileManageTool().execute(
        {"action": "get_parsed", "file_id": target.id},
        ToolContext(user_id=target.user_id, session_id=target.session_id),
    )
    assert result.get("success") is True, result
    data = result.get("data") or {}
    blocks = data.get("blocks") or []
    raw = json.dumps(blocks, ensure_ascii=False)
    images = [b for b in blocks if isinstance(b, dict) and b.get("type") == "image"]

    checks = [
        ("返回 blocks", len(blocks) > 0),
        ("不含 data:image", "data:image" not in raw),
        ("序列化 < 200KB", len(raw) < 200_000),
        ("返回 relPath", bool(data.get("relPath"))),
    ]
    for name, ok in checks:
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if images:
        print("  image sample:", {k: images[0].get(k) for k in ("imageId", "imageName", "imageUrl")})
        assert str(images[0].get("imageUrl", "")).startswith("/profile/chat-images/")
    assert all(ok for _, ok in checks)
    print(f"结果：{len(checks)} / {len(checks)} 项通过（file {target.id}，{len(raw)} chars）")


if __name__ == "__main__":
    asyncio.run(main())
