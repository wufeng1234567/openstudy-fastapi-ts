"""
自定义异常处理
"""

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.core.response import error, unauthorized
from loguru import logger


class ServiceException(Exception):
    """业务服务异常"""

    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)


class UnauthorizedException(HTTPException):
    """未授权异常"""

    def __init__(self, detail: str = "未登录或登录已过期"):
        super().__init__(status_code=401, detail=detail)


class ForbiddenException(HTTPException):
    """禁止访问异常"""

    def __init__(self, detail: str = "权限不足"):
        super().__init__(status_code=403, detail=detail)


class NotFoundException(HTTPException):
    """资源不存在异常"""

    def __init__(self, detail: str = "资源不存在"):
        super().__init__(status_code=404, detail=detail)


async def service_exception_handler(request: Request, exc: ServiceException):
    """业务异常处理器"""
    logger.warning(f"ServiceException: {exc.message}")
    return JSONResponse(
        status_code=200,
        content=error(exc.message, exc.code),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理器"""
    if exc.status_code == 401:
        return JSONResponse(
            status_code=200,
            content=unauthorized(str(exc.detail)),
        )
    elif exc.status_code == 403:
        return JSONResponse(
            status_code=200,
            content=error(str(exc.detail), 403),
        )
    elif exc.status_code == 404:
        return JSONResponse(
            status_code=200,
            content=error(str(exc.detail), 404),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=error(str(exc.detail)),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    error_type = type(exc).__name__
    error_msg = str(exc) or error_type
    logger.error(f"[ERROR] {error_type}: {error_msg}")
    return JSONResponse(
        status_code=200,
        content=error(f"服务器内部错误: {error_type}: {error_msg}"),
    )
