"""
AI 服务模块
初始化 DynamicAI 并注册所有客户端
"""

from app.services.ai.dynamic_ai import dynamic_ai
from app.config import settings

# 导入客户端以触发注册
from app.services.ai.deepseek_client import DeepSeekClient
from app.services.ai.zhipu_client import ZhipuAiClient
from app.services.ai.siliconflow_client import SiliconFlowClient

# 设置默认提供商
if settings.AI_DEFAULT_PROVIDER in dynamic_ai.list_providers():
    dynamic_ai.set_default_provider(settings.AI_DEFAULT_PROVIDER)
elif dynamic_ai.list_providers():
    dynamic_ai.set_default_provider(dynamic_ai.list_providers()[0])

__all__ = ["dynamic_ai"]
