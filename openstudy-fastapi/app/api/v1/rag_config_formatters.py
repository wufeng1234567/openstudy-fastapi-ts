"""RAG 向量化配置更新接口的纯辅助：请求体 → 配置字典、重建索引提示文案。

从 ``rag.py`` 抽出的纯逻辑：只做字典拼装与字符串常量，不连数据库、
不做权限判断、不参与事务、不触碰响应封装。``rag_config_service`` 以参数
``cfg`` 传入（避免在本模块产生 app 层导入），其 KEY_* 常量只读。
"""

#: 模型变更后提示前端重建索引的文案（原样搬迁，行为不变）。
REINDEX_HINT = (
    "向量化模型已变更。已有文档的向量是用旧模型算的，与新向量不在同一空间，"
    "检索结果会不准。请到「我的资料」页面点「重建索引」，或重新上传文档。"
)


def build_rag_config_payload(data, cfg) -> dict:
    """把 RagConfigUpdate 的可更新项映射到 rag_config_service 的配置键。"""
    payload = {
        cfg.KEY_BACKEND: data.backend,
        cfg.KEY_MODEL: data.model,
        cfg.KEY_CHUNK_SIZE: data.chunkSize,
        cfg.KEY_CHUNK_OVERLAP: data.chunkOverlap,
        cfg.KEY_TOP_K: data.topK,
        cfg.KEY_RRF_K: data.rrfK,
        cfg.KEY_CLOUD_MODEL: data.cloudModel,
        cfg.KEY_AUTO_FALLBACK: data.autoFallback,
    }

    # ── 云端 API Key（2026-10-22 新增）───────────────────────────
    # 语义：不传 / 传空串 = 保持原值；传 "__CLEAR__" = 清空。
    # 为什么不接受「空串即清空」：前端回填的是掩码，用户没动就原样提交，
    # 若把空串当清空，用户只是改个分块大小就会把 Key 清掉。
    if data.cloudApiKey is not None:
        v = data.cloudApiKey.strip()
        if v == "__CLEAR__":
            payload[cfg.KEY_CLOUD_API_KEY] = ""
        elif v and "••••" not in v:
            # 前端把掩码回传时（含 ••••）视为未修改
            payload[cfg.KEY_CLOUD_API_KEY] = v

    return payload
