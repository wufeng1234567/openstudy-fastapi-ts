"""
自定义静态文件处理器 - 文件不存在时返回占位图
"""
import os
import logging
from pathlib import Path
from starlette.staticfiles import StaticFiles
from starlette.responses import Response, FileResponse
from starlette.types import Scope
from app.config import settings

logger = logging.getLogger(__name__)


class StaticFilesWithPlaceholder(StaticFiles):
    """文件不存在时返回占位图而非 404"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        full_path = os.path.join(self.directory, path.lstrip('/'))
        logger.debug(f"[StaticFiles] path={path!r} full={full_path!r} exists={os.path.exists(full_path)}")
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            logger.warning(f"[StaticFiles] 404 for path={path!r} full={full_path!r}")
            placeholder = Path(__file__).parent / "static" / "placeholder.png"
            if placeholder.exists():
                return FileResponse(placeholder, media_type="image/png")
        return response
