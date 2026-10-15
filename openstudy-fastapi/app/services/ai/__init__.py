"""
AI 服务模块
初始化 DynamicAI 并注册所有客户端

⚠️ ds-free（DeepSeek 官网 Web 版）自 v2 起改由**浏览器扩展**实现
（apps/deepseek-proxy 代发 chat.deepseek.com 请求），后端不再走 HTTP 反代，
因此这里**刻意不注册 DeepSeekWebClient**，启动时也不会再打印反代风控告警。

历史实现（DeepSeekWebClient + pow_wasm/）保留在
`app/services/ai/deepseek_web_client.py` 备查，仅被
`app/api/v1/ai_config.py` 的「连通性测试」显式引用，不参与运行时路由。
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
