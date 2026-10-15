"""
统一响应格式
保持与若依前端兼容的响应格式
"""

from typing import Any, Optional


def success(data: Any = None, msg: str = "操作成功") -> dict:
    """成功响应"""
    return {
        "code": 200,
        "msg": msg,
        "data": data,
    }


def error(msg: str = "操作失败", code: int = 500) -> dict:
    """错误响应"""
    return {
        "code": code,
        "msg": msg,
        "data": None,
    }


def paginate(total: int, rows: list, msg: str = "查询成功") -> dict:
    """分页响应"""
    return {
        "code": 200,
        "msg": msg,
        "total": total,
        "rows": rows,
    }


def warn(msg: str, data: Any = None) -> dict:
    """警告响应"""
    return {
        "code": 301,
        "msg": msg,
        "data": data,
    }


def unauthorized(msg: str = "未登录或登录已过期") -> dict:
    """未授权响应"""
    return {
        "code": 401,
        "msg": msg,
        "data": None,
    }


def forbidden(msg: str = "权限不足") -> dict:
    """禁止访问响应"""
    return {
        "code": 403,
        "msg": msg,
        "data": None,
    }
