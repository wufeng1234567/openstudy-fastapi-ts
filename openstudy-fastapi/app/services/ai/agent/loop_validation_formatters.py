"""Agent 工具参数校验失败信封的统一格式化（从 loop.py 抽出的重复实现）。

loop.py 里 `_prepare_tool_call` 与 `run_agent_stream` 各手写了一份完全相同的
fail("参数校验失败：" + "；".join(errors), "；".join(hints), validationErrors=errors)。
这里收拢成一个纯函数：只拼装信封，不碰事件 / 循环 / 确认 / 回滚时序。
"""

from app.services.ai.agent.base import fail


def params_validation_failure(errors, hints):
    """参数校验不过时回灌给模型的 fail 信封（逐字照搬原两处调用）。"""
    return fail(
        "参数校验失败：" + "；".join(errors),
        "；".join(hints),
        validationErrors=errors,
    )
