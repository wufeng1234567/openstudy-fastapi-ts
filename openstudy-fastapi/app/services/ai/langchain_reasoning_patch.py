"""让 LangChain 把「深度思考」正文透出来（reasoning_content 注入补丁）

## 为什么需要这个补丁

`langchain-openai 0.2.14` 的流式分片转换函数 `_convert_delta_to_message_chunk`
用**白名单**构造 `additional_kwargs`，只认 `function_call` 与 `tool_calls`：

    additional_kwargs: Dict = {}
    if _dict.get("function_call"): ...
    if raw_tool_calls := _dict.get("tool_calls"): ...
    # ← reasoning_content 到这里被静默丢弃，谁都拿不到

实测（真实 `api.deepseek.com` 请求，绑定工具、开启思考）：
原始 SSE 的 delta 里**明明带着** `reasoning_content`（66~116 字），
但经 LangChain 后 `chunk.additional_kwargs` 里只有 `tool_calls` —— 思考正文凭空消失。

所以这不是「后端忘了读」，而是**读不到**。本模块在 `additional_kwargs` 上
补回这个字段，`agent/loop.py` 才能把它发成 `thinking` 事件。

## 设计要点

- **provider 无关**：`_SRC_KEYS` 覆盖各家放思考正文的常见字段名，谁发了就取谁的；
  一个都没发（不支持思考的接口）就什么都不做，UI 已容忍「整场没有 thinking 事件」。
- **优雅降级**：langchain 内部结构一变（函数被改名/删除），这里只记 warning 不抛异常 ——
  退化成「没有思考卡片」，其余功能完全不受影响。
- **幂等**：给包装函数打标，重复 import 不会套娃。
- **不改第三方源码**：只在运行时替换模块级函数引用，`.venv` 里保持原样。

⚠️ 升级 langchain-openai 前先跑 `tests/` 下的补丁自检用例：
若上游开始原生支持 `reasoning_content`，本模块可整文件删除。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Tuple

logger = logging.getLogger(__name__)

#: 各家流式 delta 里放「思考正文」的字段名，按优先级取第一个非空值。
#: - `reasoning_content`：DeepSeek / 智谱 / 多数 OpenAI 兼容网关
#: - `reasoning`：部分 OpenAI 系网关
#: 遇到新的写法在这里追加即可（不影响已有行为）。
_SRC_KEYS: Tuple[str, ...] = ("reasoning_content", "reasoning")

#: 统一归一化到这个键，`loop.py` 只需认这一个名字。
_CANON_KEY = "reasoning_content"

#: 打在包装函数上的标记，用于防重复安装
_MARKER = "_openstudy_reasoning_patched"

#: 本模块的安装结果，供自检用例断言
INSTALLED: bool = False


def _try_import_base() -> Any:
    """拿到 langchain_openai 的 chat_models.base 模块；拿不到就返回 None"""
    try:
        import langchain_openai.chat_models.base as base  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001 - 装不上就降级，不该拖垮启动
        logger.warning("[reasoning-patch] 无法导入 langchain_openai.chat_models.base: %s", e)
        return None
    return base


def install() -> bool:
    """安装补丁；返回是否「本次真的装上了」（重复调用返回 False 但不报错）

    幂等：第二次调用会因 `_MARKER` 命中而直接返回 False。
    """
    global INSTALLED

    base = _try_import_base()
    if base is None:
        INSTALLED = False
        return False

    original: Callable[..., Any] | None = getattr(
        base, "_convert_delta_to_message_chunk", None
    )
    if original is None:
        # 上游改名/删除了 → 不装，功能降级为「没有思考卡片」
        logger.warning(
            "[reasoning-patch] 未找到 _convert_delta_to_message_chunk（langchain-openai 版本已变），"
            "深度思考将以「不下发」的形式降级，其余功能不受影响"
        )
        INSTALLED = False
        return False

    if getattr(original, _MARKER, False):
        # 已经装过（可能是别的模块先 import 了本模块）
        INSTALLED = True
        return False

    def _patched(_dict: Any, default_class: Any) -> Any:
        chunk = original(_dict, default_class)
        # 只对模型侧分片动手；Human/Tool 等分片没有思考正文
        if _dict and hasattr(chunk, "additional_kwargs"):
            for key in _SRC_KEYS:
                value = _dict.get(key)
                if isinstance(value, str) and value:
                    chunk.additional_kwargs[_CANON_KEY] = value
                    break
        return chunk

    setattr(_patched, _MARKER, True)
    base._convert_delta_to_message_chunk = _patched
    INSTALLED = True
    logger.info(
        "[reasoning-patch] 已安装：流式分片的 %s 将被注入 additional_kwargs['%s']",
        "/".join(_SRC_KEYS),
        _CANON_KEY,
    )
    return True


# import 即安装（`db_config` 在顶部 import 本模块 —— 所有 LLM 都经那个工厂构造）
install()


__all__ = ["INSTALLED", "install"]
