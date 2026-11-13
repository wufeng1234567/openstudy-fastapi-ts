"""RAG 知识库对象的纯响应格式化。

从 ``rag.py`` 抽出的 3 个纯函数：只把 ORM 对象拼成响应 dict，
不连数据库、不做权限判断、不参与事务、不碰 ``success`` 封装。
字段、顺序与 ``kb_disabled_flag`` 调用逐字照搬原内联字典。
"""

from app.services.rag import rag_write_service


def kb_created_payload(kb) -> dict:
    """创建资料夹的返回对象（新库恒为启用，但 disabled 照样下发）。"""
    return {
        "kbId": kb.id,
        "name": kb.name,
        "description": kb.description,
        "docCount": kb.doc_count,
        "chunkCount": kb.chunk_count,
        # 新库恒为启用；照样下发（同一份 `kb_disabled_flag`）是为了让
        # 「凡是返回知识库对象的响应都带 disabled」这条口径没有例外 ——
        # 少一处，前端那一行就可能绑到 undefined（见 kb_disabled_flag 的说明）。
        "disabled": rag_write_service.kb_disabled_flag(kb),
    }


def kb_detail_payload(kb) -> dict:
    """资料夹详情的返回对象。

    ⚠️ 与 `_kb_brief`（列表）**必须同时有**：详情是手写出来的另一份，
       只改一处就会出现「列表知道它被屏蔽了、详情不知道」。
       归一走同一个函数（整数 0/1，永不 null / 字符串）—— 见
       `rag_write_service.kb_disabled_flag` 的 el-switch 说明。
    """
    return {
        "kbId": kb.id,
        "name": kb.name,
        "description": kb.description,
        "docCount": kb.doc_count,
        "chunkCount": kb.chunk_count,
        "disabled": rag_write_service.kb_disabled_flag(kb),
        "embeddingModel": kb.embedding_model,
        "chunkSize": kb.chunk_size,
        "chunkOverlap": kb.chunk_overlap,
        "createTime": kb.create_time.isoformat(sep=" ") if kb.create_time else None,
    }


def kb_updated_payload(kb) -> dict:
    """更新资料夹后的回显（前端关掉开关后要立刻能从响应里确认状态）。"""
    # 回显 disabled：前端关掉开关后要立刻能从响应里确认状态，
    # 而不是再发一次 GET 去猜（不 echo 的话「点了没反应」看不出是写失败还是没写）。
    return {
        "kbId": kb.id,
        "name": kb.name,
        "disabled": rag_write_service.kb_disabled_flag(kb),
    }
