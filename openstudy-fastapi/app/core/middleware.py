"""
中间件（**纯 ASGI 实现**）

⚠️ 为什么不用 `BaseHTTPMiddleware`
================================
Starlette 的 `BaseHTTPMiddleware` 会为每个请求**另起一个 task + 内存队列**来搬运响应体 ——
它**无法逐块透传流式响应**：`await call_next(request)` 拿到的是一个"包装后"的响应，真正
的字节要经它内部队列中转；当中间件（如日志）不消费 body 时，上游 `StreamingResponse`
的 chunk 会被**攒批**，表现就是「先出来几个字 → 卡住不动 → 等整个流结束才一次性刷出」。

本项目大量使用 **SSE / 流式响应**（智能体 `/ai/agent/stream`、聊天 `stream_turn`、
ds-free 各类流），深度思考/正文的"流式观感"全依赖逐块下发 —— 用 `BaseHTTPMiddleware`
会把它毁掉（用户 2026-10-11 报「深度思考先出几个字、卡住、最后才全刷出来」的根因）。

故这里把三个中间件全部改成**纯 ASGI 中间件**：直接包裹 `send`，把 `http.response.body`
的**每一个 chunk 原样、即时**转发给下游，零缓冲。
"""

import time
import uuid

from loguru import logger


class RequestIdMiddleware:
    """请求 ID 中间件（纯 ASGI）

    给每个请求生成 `request_id`，写入 ASGI `scope["state"]`（= `request.state`，供下游读取），
    并在响应头回填 `X-Request-ID`。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        # ASGI 约定的 per-request 状态容器：Starlette 把它暴露为 `request.state`。
        # 只在缺失时初始化，避免覆盖上游已建好的 dict。
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            # ⚠️ 逐条原样转发：http.response.body 的每个 chunk 立即下发，不攒批
            await send(message)

        await self.app(scope, receive, send_wrapper)


class LogMiddleware:
    """访问日志中间件（纯 ASGI）

    记录「方法 路径 状态码 耗时」，并在响应头回填 `X-Process-Time`。
    耗时口径：收到请求 → 响应头开始发送（`http.response.start`），
    这与"首个字节"对齐，流式接口下不会因为 body 还在流而把耗时算得虚高。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                process_time = time.time() - start_time
                logger.info(
                    f"{scope['method']} {scope['path']} "
                    f"status={message['status']} "
                    f"duration={process_time:.3f}s"
                )
                headers = message.setdefault("headers", [])
                headers.append((b"x-process-time", f"{process_time:.3f}".encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_wrapper)


class OperationLogMiddleware:
    """操作日志中间件（纯 ASGI，简化版）

    只记录写操作（POST/PUT/DELETE）。放在 `http.response.start` 时记录状态码即可 ——
    不需要读 body（读 body 正是 `BaseHTTPMiddleware` 会缓冲流式的原因）。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and method in ("POST", "PUT", "DELETE"):
                logger.info(
                    f"Operation: {method} {scope['path']} status={message['status']}"
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
