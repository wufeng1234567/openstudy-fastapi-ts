"""
自定义异常处理
"""

from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
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


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求体/查询参数校验失败统一成项目信封。

    FastAPI 默认返回 HTTP 422 + `{"detail":[...]}`，前端按 `body.code !== 200`
    判断就会走到“未知错误”，页面只看到“操作失败”。这里转成
    HTTP 200 + `{code:422,msg:"参数校验失败: ..."}`，既保留字段名线索，
    也不破坏前端统一的业务码处理。
    """
    messages = []
    for item in exc.errors()[:5]:
        loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
        msg = item.get("msg") or "参数不合法"
        messages.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(
        status_code=422,
        content=error("参数校验失败：" + "；".join(messages), code=422),
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
