"""
中间件
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger


class RequestIdMiddleware(BaseHTTPMiddleware):
    """请求 ID 中间件"""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LogMiddleware(BaseHTTPMiddleware):
    """日志中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={process_time:.3f}s"
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response


class OperationLogMiddleware(BaseHTTPMiddleware):
    """操作日志中间件（简化版）"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 只记录写操作
        if request.method in ("POST", "PUT", "DELETE"):
            logger.info(
                f"Operation: {request.method} {request.url.path} "
                f"status={response.status_code}"
            )

        return response
