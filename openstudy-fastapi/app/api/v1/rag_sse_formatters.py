"""RAG 两处 SSE 流式响应的纯格式化辅助与响应头常量。

从 ``rag.py`` 抽出：SSE ``data:`` 帧字符串、整理计划的 stage 事件负载、
两处 ``StreamingResponse`` 的响应头。全部只做字符串/字典拼装，
不含 async、不含计时（``await asyncio.sleep`` 与 ``async for`` 仍留在路由），
不改变事件顺序与字节内容。
"""

import json


#: 资料装配（study-pack）流式响应的响应头。
SSE_STUDY_PACK_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

#: 智能整理计划轮询流的响应头。
SSE_ORGANIZE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_data(payload) -> str:
    """SSE 单个 data 帧：与原来的 ``"data: " + json.dumps(...) + "\\n\\n"`` 完全一致。"""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _organize_stage_payload(payload: dict) -> dict:
    """整理计划 stage 事件只回这 4 个字段（逐字照搬原内联字典）。"""
    return {
        "status": payload["status"],
        "stage": payload["stage"],
        "progress": payload["progress"],
        "summary": payload["summary"],
    }
