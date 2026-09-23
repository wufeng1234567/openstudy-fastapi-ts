"""
模型能力登记表（视觉 / 仅文本）

为什么单独一个模块：
  - 「哪个模型能识图」这件事，后端（构造多模态消息、决定是否回退）和前端
    （下拉框切换、上传提示）都要用同一套口径。写死在两处必然漂移。
  - `sys_ai_config` 表里没有能力字段，加列需要迁移 + 后台表单配套；
    目前模型就那么几个，用常量集合更轻、更好改，也便于按需扩展。

口径（与前端 `src/utils/ai-model-capability.ts` 保持一致，改一边要改另一边）：

| model            | 识图 | 说明                                              |
|------------------|------|---------------------------------------------------|
| deepseek-flash   | ✅   | 多模态，本系统默认模型，可传图片                  |
| deepseek-free    | ✅   | DS 官网 Web 版（扩展直连），网页端本身支持传图    |
| deepseek-v4-pro  | ❌   | 仅文本；传图片会报错，需回退到 deepseek-flash     |

**未登记的模型一律视为「可识图」**（宽松放行）：用户自定义的新模型（例如
自己接的 gpt-4o / qwen-vl）不该被这张表挡住；真不支持时上游会返回明确报错，
比在本地静默丢图更好排查。
"""

from typing import List, Optional

#: 默认的视觉模型（需要回退时用它）
DEFAULT_VISION_MODEL = "deepseek-flash"

#: 明确支持图片输入的模型
VISION_MODELS = frozenset({"deepseek-flash", "deepseek-free"})

#: 明确只支持文本的模型
TEXT_ONLY_MODELS = frozenset({"deepseek-v4-pro"})


def _norm(model: Optional[str]) -> str:
    return (model or "").strip().lower()


def supports_vision(model: Optional[str]) -> bool:
    """该模型是否能接收图片输入。

    - 命中 VISION_MODELS → True
    - 命中 TEXT_ONLY_MODELS → False
    - 其它（含空值、未知模型）→ True（宽松放行，理由见模块 docstring）
    """
    key = _norm(model)
    if key in VISION_MODELS:
        return True
    if key in TEXT_ONLY_MODELS:
        return False
    return True


def is_text_only(model: Optional[str]) -> bool:
    """该模型是否「明确只支持文本」——前端据此提示用户并自动切换模型。"""
    return _norm(model) in TEXT_ONLY_MODELS


def vision_model_names() -> List[str]:
    """下发给前端的可识图模型名单（保持稳定顺序）"""
    return [DEFAULT_VISION_MODEL] + sorted(VISION_MODELS - {DEFAULT_VISION_MODEL})


__all__ = [
    "DEFAULT_VISION_MODEL",
    "VISION_MODELS",
    "TEXT_ONLY_MODELS",
    "supports_vision",
    "is_text_only",
    "vision_model_names",
]
