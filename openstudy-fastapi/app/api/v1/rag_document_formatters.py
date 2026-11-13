"""RAG 文档相关接口的纯响应格式化。

从 ``rag.py`` 抽出的 3 个纯函数：只把已算好的值拼成 ``success`` 的 data dict，
不连数据库、不做权限判断、不参与事务、不触碰响应封装。
字段、顺序、条件表达式与注释逐字照搬原内联字典，响应行为不变。
"""


def outline_payload(doc, sections, tree, needs_ai) -> dict:
    """资料结构树（getDocumentOutline）的返回对象。"""
    return {
        "docId": doc.id,
        "fileName": doc.file_name,
        "hasOutline": len(sections) > 1,
        "tree": tree,
        "sections": sections,
        "needsAiOutline": bool(needs_ai),
        "reason": "" if tree else "这份资料没有可识别的章节标题，已按分块生成可导航的分段目录。",
        "chunkCount": getattr(doc, "chunk_count", 0) or 0,
    }


def outline_rebuild_payload(doc, sections) -> dict:
    """AI 目录整理（rebuildDocumentOutline）的返回对象。"""
    return {
        "docId": doc.id,
        "fileName": doc.file_name,
        "sections": sections,
        "count": len(sections),
    }


def workspace_search_payload(q, hits, result, limit, group_hits_by_file) -> dict:
    """工作空间自然语言找文件（searchWorkspace）的返回对象。

    ``group_hits_by_file`` 由调用方传入（即 ``rag_formatters._group_hits_by_file``），
    本模块因此保持零 import，不产生任何循环依赖。
    """
    return {
        "query": q,
        "hits": hits,
        "knowledgeBases": result.get("knowledgeBases") or [],
        "files": group_hits_by_file(hits, limit),
        "reason": result.get("reason") or "",
        # 两路都没关键词命中 = 结果可能不相关（见 rag_query_service.search 的说明）
        "lowConfidence": bool(result.get("lowConfidence")),
    }
