# -*- coding: utf-8 -*-
"""中间件流式透传探针 —— 验证改纯 ASGI 后不再攒批流式响应

背景（用户 2026-10-11 报）：「深度思考先出几个字、卡住不动、最后才一次性全刷出来」。
根因=`BaseHTTPMiddleware`（Starlette）会为每个请求另起 task + 内存队列搬运响应体，
**无法逐块透传流式响应** → SSE chunk 被攒批。修复=三个中间件改**纯 ASGI**（直接包裹 send）。

本探针用一个"会分多块发 body"的假 ASGI app，分别**直接调用**与**经中间件包裹**，
断言下游收到的 `http.response.body` **条数一致**（中间件不把多块合并/缓冲）。

用法
----
    .venv/Scripts/python.exe tests/_probe_middleware_stream.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def run_probe() -> int:
    from app.core.middleware import LogMiddleware, OperationLogMiddleware, RequestIdMiddleware

    # 假下游 app：分 3 块发 body（模拟 SSE 逐 chunk）
    async def fake_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for i in range(3):
            await send({"type": "http.response.body", "body": f"chunk{i}".encode(), "more_body": i < 2})

    async def drive(app):
        """跑一次请求，返回 (下游收到的 body 块数, response.start 的 headers)"""
        scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
        chunks = []
        start_headers = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body":
                chunks.append(message.get("body"))
            elif message["type"] == "http.response.start":
                start_headers.extend(message.get("headers", []))

        await app(scope, receive, send)
        return chunks, start_headers

    # 1) 基线：不包中间件
    base_chunks, _ = await drive(fake_app)
    check("MW-01", "基线：假 app 发出 3 块 body", len(base_chunks) == 3, f"chunks={len(base_chunks)}")

    # 2) 经 RequestIdMiddleware：body 块数不变（不攒批）
    c2, h2 = await drive(RequestIdMiddleware(fake_app))
    check("MW-02", "RequestId 中间件不攒批（body 块数不变）", len(c2) == 3, f"chunks={len(c2)}")
    check(
        "MW-03",
        "RequestId 回填 x-request-id 头",
        any(k.lower() == b"x-request-id" for k, _ in h2),
        str([k for k, _ in h2]),
    )

    # 3) 经 LogMiddleware：body 块数不变
    c3, h3 = await drive(LogMiddleware(fake_app))
    check("MW-04", "Log 中间件不攒批（body 块数不变）", len(c3) == 3, f"chunks={len(c3)}")
    check(
        "MW-05",
        "Log 回填 x-process-time 头",
        any(k.lower() == b"x-process-time" for k, _ in h3),
        str([k for k, _ in h3]),
    )

    # 4) 经 OperationLogMiddleware：body 块数不变
    c4, _ = await drive(OperationLogMiddleware(fake_app))
    check("MW-06", "OperationLog 中间件不攒批（body 块数不变）", len(c4) == 3, f"chunks={len(c4)}")

    # 5) 三层叠加
    stacked = RequestIdMiddleware(LogMiddleware(OperationLogMiddleware(fake_app)))
    c5, h5 = await drive(stacked)
    check("MW-07", "三层叠加仍逐块透传", len(c5) == 3, f"chunks={len(c5)}")
    check(
        "MW-08",
        "三层叠加仍带 request-id",
        any(k.lower() == b"x-request-id" for k, _ in h5),
        str([k for k, _ in h5]),
    )
    # 6) 中间件不基于 BaseHTTPMiddleware（源码级契约：**不允许出现其 import/继承**；
    #    文档字符串里为说明"为什么不用它"提到该名字是允许的，故只查 import/继承形态）
    import inspect

    src = inspect.getsource(sys.modules[RequestIdMiddleware.__module__])
    check(
        "MW-09",
        "middleware 未 import/继承 BaseHTTPMiddleware",
        "import BaseHTTPMiddleware" not in src and "BaseHTTPMiddleware)" not in src,
        "",
    )

    print("\n---- 中间件流式透传探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run_probe()))
    except OSError:
        # 沙箱/受限环境下 `asyncio.run` 无法建事件循环（socketpair 被拦）。
        # 本探针的协程只 await「立即完成」的协程（无真实 IO/sleep/future），
        # 故用一个极简 trampoline 手动驱动：维护协程栈，StopIteration 的返回值
        # 逐层 send 回上一层，直至顶层结束。
        def _drive(coro):
            stack = [coro]
            value = None
            while True:
                cur = stack[-1]
                try:
                    yielded = cur.send(value)
                except StopIteration as stop:
                    stack.pop()
                    if not stack:
                        return stop.value
                    value = stop.value
                    continue
                # 子协程（await 链）→ 压栈继续推；非协程对象（立即完成）→ 直接回传
                if hasattr(yielded, "send"):
                    stack.append(yielded)
                    value = None
                else:
                    value = yielded

        raise SystemExit(_drive(run_probe()))
