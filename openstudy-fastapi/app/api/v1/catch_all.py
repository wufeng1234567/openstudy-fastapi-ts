"""
Catch-all 路由 - 只处理未匹配的 API 请求
浏览器导航请求（Accept: text/html）返回 404，让 Nginx 拦截后 serve index.html
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.core.response import success, paginate

router = APIRouter()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path: str):
    """处理所有未匹配的 API 路由"""
    # 浏览器导航请求（Accept 包含 text/html）返回 404
    # Nginx 拦截 404 后直接 serve index.html（静态文件，WAF 不拦截）
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # 未匹配的写接口必须明确失败：此前 POST/PUT/DELETE 拼错路径也会返回
    # `code=200 操作成功`，删除/改名/点赞等操作看起来成功、实际没有落库。
    # GET 保留旧兼容兜底（部分历史页面依赖空列表），写请求直接 404。
    if request.method != "GET":
        return JSONResponse(
            status_code=404,
            content={"code": 404, "msg": "接口不存在", "data": None},
        )

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
