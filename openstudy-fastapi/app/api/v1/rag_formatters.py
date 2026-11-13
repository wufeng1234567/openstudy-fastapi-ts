"""RAG 检索结果的纯格式化辅助。

从 ``rag.py`` 抽出：按文件聚合分块命中、给命中补知识库名称。两者都只操作
内存中的 list / dict，不连数据库、不碰请求上下文。``rag.py`` 会把这两个
名字重新导入自己的模块命名空间，路由调用点保持不变。
"""


def _attach_kb_names(hits: list, knowledge_bases: list) -> None:
    """`ChunkHit.to_dict()` 只有 kbId，没有库名；从本次检索范围里补一张 id→name 表。"""
    kb_names = {
        int(k.get("kbId")): str(k.get("name") or "")
        for k in (knowledge_bases or [])
        if k.get("kbId") is not None
    }
    for h in hits:
        try:
            h["kbName"] = kb_names.get(int(h.get("kbId")), "")
        except (TypeError, ValueError):
            h["kbName"] = ""


def _group_hits_by_file(hits: list, limit: int) -> list:
    """把分块命中按**文件**聚合，供页面列表展示。

    为什么不直接返回分块：用户问「找下概率论那份资料」时想看的是**哪份文件**，
    而不是十几条零散片段。文件级列表 + 命中段数，才是这个页面该给的东西。
    组内保留第一段正文摘要，方便用户确认「就是这份」。
    """
    groups: dict[int, dict] = {}
    order: list[int] = []

    for h in hits:
        doc_id = h.get("docId")
        if doc_id is None:
            continue
        if doc_id not in groups:
            content = str(h.get("content") or "")
            groups[doc_id] = {
                "docId": doc_id,
                "kbId": h.get("kbId"),
                "kbName": h.get("kbName") or "",
                "fileName": h.get("docName") or h.get("fileName") or "未命名文档",
                "score": float(h.get("score") or 0),
                "hitCount": 0,
                "snippet": content[:120] + ("…" if len(content) > 120 else ""),
                "images": list(h.get("images") or [])[:3],
            }
            order.append(doc_id)
        groups[doc_id]["hitCount"] += 1

    return [groups[d] for d in order][:limit]
