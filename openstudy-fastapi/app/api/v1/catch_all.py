"""
Catch-all 路由 - 只处理未匹配的 API 请求
浏览器导航请求（Accept: text/html）不走兜底，交给前端路由
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.core.response import success, paginate

router = APIRouter()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path: str):
    """处理所有未匹配的 API 路由"""
    # 浏览器导航请求（Accept 包含 text/html）不走兜底，返回 HTML 让前端路由处理
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        # 返回空 HTML，让前端路由接管
        return HTMLResponse(content="<!DOCTYPE html><html><head></head><body></body></html>")

    # API 请求返回合理的默认数据
    if "list" in path:
        return paginate(0, [])
    elif "all" in path or "tree" in path or "select" in path:
        return success([])
    elif "count" in path or "stats" in path or "stat" in path:
        return success({"count": 0})
    elif "check" in path or "exists" in path:
        return success(False)
    else:
        return success(None)
