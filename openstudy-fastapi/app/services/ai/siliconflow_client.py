"""
硅基流动客户端（使用 LangChain）
"""

from typing import List, AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.ai.base_client import (
    BaseAiClient,
    ChatMessage,
    ChatResponse,
    to_lc_content,
    to_lc_text,
)
from app.config import settings


class SiliconFlowClient(BaseAiClient):
    """硅基流动客户端"""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or settings.SILICONFLOW_API_KEY

    @property
    def provider(self) -> str:
        return "siliconflow"

    def _effective_api_key(self) -> str:
        """当前生效的 Key。

        优先级：
          1. 构造时显式传入的 key（老行为，保持兼容）
          2. 后台「知识库向量化」页填的 `rag.embedding.cloudApiKey`（运行时）
          3. `.env` 的 `SILICONFLOW_API_KEY`

        ⚠️ 为什么需要运行时读取（2026-10-22）：
          原来只在 `__init__` 里读一次 `.env`，后台改了 Key 必须重启才生效。
          但用户是在页面上填 Key 的，不能要求他填完再重启服务。
        """
        if (self._api_key or "").strip():
            return self._api_key.strip()
        try:
            from app.services.rag.rag_config_service import get_runtime_cloud_api_key

            k = get_runtime_cloud_api_key()
            if k:
                return k
        except Exception:
            pass
        return (settings.SILICONFLOW_API_KEY or "").strip()

    @property
    def supported_models(self) -> List[str]:
        return [
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-14B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "deepseek-ai/DeepSeek-V2-Chat",
            "THUDM/glm-4-9b-chat",
            # ---- Embedding 模型 ----
            # RAG 靠这些向量化。DeepSeek 官方**没有** embeddings 接口（实测 /embeddings 全 404），
            # 智谱 key 余额不足，所以 RAG 的向量化实际由硅基流动承担。
            # ⚠️ 三者都是 1024 维，与 rag_document_chunk.embedding 的 vector(1024) 及
            #    models/rag.py: EMBEDDING_DIM 必须保持一致 —— 换维度等于换索引。
            "BAAI/bge-m3",
            "BAAI/bge-large-zh-v1.5",
            "Qwen/Qwen3-Embedding-0.6B",
        ]

    def _get_llm(self, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
        """获取 LangChain LLM 实例"""
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=self._api_key,
            openai_api_base="https://api.siliconflow.cn/v1",
        )

    def _convert_messages(self, messages: List[ChatMessage]) -> list:
        """转换消息格式

        多模态块必须走 `to_lc_content()`（pydantic 模型 → dict），
        否则 HumanMessage 构造时会被 pydantic 打回。
        """
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=to_lc_text(msg.content)))
            elif msg.role == "user":
                lc_messages.append(HumanMessage(content=to_lc_content(msg.content)))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=to_lc_text(msg.content)))
        return lc_messages

    async def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> ChatResponse:
        llm = self._get_llm(model, temperature, max_tokens)
        lc_messages = self._convert_messages(messages)

        response = await llm.ainvoke(lc_messages)

        return ChatResponse(
            content=response.content,
            usage=response.response_metadata.get("token_usage"),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> AsyncIterator[str]:
        llm = self._get_llm(model, temperature, max_tokens)
        lc_messages = self._convert_messages(messages)

        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    async def embeddings(
        self,
        texts: List[str],
        model: str = None,
    ) -> List[List[float]]:
        from langchain_openai import OpenAIEmbeddings

        # 缺 Key 时给**明确**的中文提示，而不是让 SDK 抛含糊的
        # 「api_key client option must be set」——用户看到不知道是哪把 key。
        api_key = self._effective_api_key()
        if not api_key:
            raise RuntimeError(
                f"RAG 向量化需要硅基流动 API Key（模型 {model or 'BAAI/bge-m3'}），"
                "但还没有配置。请到「系统管理 → 知识库向量化」页面填写 Key，保存后立即生效。"
            )

        embeddings_model = OpenAIEmbeddings(
            model=model or "BAAI/bge-m3",
            openai_api_key=api_key,
            openai_api_base="https://api.siliconflow.cn/v1",
        )
        return await embeddings_model.aembed_documents(texts)


# 注册到 DynamicAI
from app.services.ai.dynamic_ai import dynamic_ai

# ⚠️ 无论 key 是否配置都注册：否则 key 为空时 `get_client_for_model("BAAI/bge-m3")`
#    找不到 SiliconFlow 客户端，会 fallback 到默认 provider，抛出含糊的
#    「api_key client option must be set」——用户根本不知道是「硅基流动 Key 没配」。
#    注册进来后，`embeddings()` 会抛**明确**的中文提示（见下）。
dynamic_ai.register_client(SiliconFlowClient())
