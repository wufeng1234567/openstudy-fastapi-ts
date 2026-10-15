"""
上下文长度档位（单一事实来源）

## 为什么需要这个模块

DeepSeek 官方**没有** `context_length` 这类请求参数 —— 上下文窗口是模型固有属性
（见官方 `GET /models` 元数据：`deepseek-flash` 与 `deepseek-v4-pro` **都是 1M**）。

`sys_ai_config.context_length` 存的不是"发给上游的参数"，而是**我们在应用层
喂多少历史对话进去的预算**。此前这个字段只写不读（`ai_config.py` 存取、
前端有下拉框，但没有任何一处消费它）—— 选了也是摆设。

本模块把它变成真正的预算，并作为唯一口径：

| key    | 展示名                | 窗口 token | 历史字符预算 | 单条字符上限 |
|--------|-----------------------|-----------|-------------|-------------|
| `200k` | 200K tokens（基础）   | 200000    | 160000      | 16000       |
| `1m`   | 1M tokens（完整）     | 1000000   | 800000      | 32000       |

**换算口径**（不做真分词，避免引入 tokenizer 依赖）：
  · 中文约 1 字 ≈ 1 token（最坏情况），故 `历史字符预算 = 窗口 token × 0.8`
    即按「1 字符 1 token」保守估算，且预留 20% 给系统提示词与输出。
  · 对英文（约 4 字符 1 token）是**高估** token 数 → 偏保守，不会把上下文算爆。

**兼容旧值**：历史下拉框曾提供 `32k / 128k`（且从未生效）。这些值统一归一到
默认档 `200k` —— 旧值是死配置，归一不会造成任何真实行为回退。
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ContextPreset:
    """一个上下文档位的全部口径"""

    #: 落库的值（`sys_ai_config.context_length`）
    key: str
    #: 前端展示名
    label: str
    #: 模型窗口的 token 总量（仅用于展示与换算，不发给上游）
    tokens: int
    #: 喂给模型的历史对话字符预算（`build_context_prompt` 的 `max_chars`）
    history_chars: int
    #: 单条历史消息的字符上限，超出只保留首尾（`_clip_single`）
    single_message_chars: int


#: 默认档位（用户口径：200k 为基础档）
DEFAULT_CONTEXT_LENGTH = "200k"

#: 全部档位（顺序即前端展示顺序：基础在前、完整在后）
CONTEXT_PRESETS: Dict[str, ContextPreset] = {
    "200k": ContextPreset(
        key="200k",
        label="200K tokens（基础）",
        tokens=200_000,
        history_chars=160_000,
        single_message_chars=16_000,
    ),
    "1m": ContextPreset(
        key="1m",
        label="1M tokens（完整）",
        tokens=1_000_000,
        history_chars=800_000,
        single_message_chars=32_000,
    ),
}


def normalize_context_length(value: object) -> str:
    """把任意输入归一为合法档位 key

    - 合法值（`200k` / `1m`，大小写与空白不敏感）→ 原样返回小写 key；
    - 空值 / 未知值 / 历史遗留值（`32k` / `128k` 等）→ `DEFAULT_CONTEXT_LENGTH`。
    """
    key = str(value or "").strip().lower()
    return key if key in CONTEXT_PRESETS else DEFAULT_CONTEXT_LENGTH


def get_preset(value: object) -> ContextPreset:
    """取档位定义（未知值回退默认档）"""
    return CONTEXT_PRESETS[normalize_context_length(value)]


def history_char_budget(value: object) -> int:
    """历史对话的字符预算 —— 供 `conversation_service.build_context_prompt(max_chars=...)`"""
    return get_preset(value).history_chars


def single_message_char_budget(value: object) -> int:
    """单条历史消息的字符上限 —— 供 `build_context_prompt(single_max_chars=...)`"""
    return get_preset(value).single_message_chars


def preset_options() -> List[dict]:
    """档位清单（供接口 / 前端下拉使用）"""
    return [
        {"key": p.key, "label": p.label, "tokens": p.tokens}
        for p in CONTEXT_PRESETS.values()
    ]


__all__ = [
    "DEFAULT_CONTEXT_LENGTH",
    "CONTEXT_PRESETS",
    "ContextPreset",
    "normalize_context_length",
    "get_preset",
    "history_char_budget",
    "single_message_char_budget",
    "preset_options",
]
