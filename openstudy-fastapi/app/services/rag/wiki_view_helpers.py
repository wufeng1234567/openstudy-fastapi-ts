"""Wiki 列表 / 图谱的**载荷构造与统计**（从 `wiki_service.py` 抽出）。

这些函数把「数据库里的行」翻译成「前端要的载荷」，**只算、不查库**：

  · `count_link_degree` —— 链接的出入度统计（列表与图谱**共用同一份口径**）
  · `count_by_page_type` —— 按页面类型计数
  · `count_learning_stats` —— 已读 / 已练 / 已掌握三个计数
  · `build_page_list_item` —— 列表里的一行
  · `build_graph_node` / `build_graph_edges` / `build_mention_edges` —— 图谱的节点与边
  · `build_out_links` / `build_in_links` / `link_sort_key` / `build_link_stats`
    —— 页面正文里的出链 / 反链

⚠ 依赖方向单向：`wiki_service.py` → 本模块；本模块**不反向依赖**它
   （`wiki_link_service` 只依赖标准库），因此不会形成循环依赖。

⚠ **响应形状一个字段都没改** —— 这里只是把「形状怎么算」挪到了可以单独读、
   单独测的地方；async 的落库 / 检索 / LLM 流程与返回的 dict 形状、字段顺序
   全部保持原样。

⚠ 里面几段统计（出入度、类型计数、学习态计数）在 `wiki_service.py` 里**本来就
   写了两遍**（列表一处、图谱一处）—— 现在收敛到同一份实现，口径不会再漂。
"""

from __future__ import annotations

from app.services.rag.wiki_link_service import (
    extract_wiki_links,
    page_text_blocks,
    strip_wiki_tokens,
)


def count_link_degree(links) -> dict[int, int]:
    """链接的出入度统计（一条链接给两端各 +1）"""
    degree: dict[int, int] = {}
    for link in links:
        degree[int(link.from_page_id)] = degree.get(int(link.from_page_id), 0) + 1
        degree[int(link.to_page_id)] = degree.get(int(link.to_page_id), 0) + 1
    return degree


def count_by_page_type(items) -> dict[str, int]:
    """按页面类型计数（没有类型的算 `concept`）"""
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("pageType") or "concept")
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_learning_stats(items) -> dict[str, int]:
    """已读 / 已练 / 已掌握三个计数"""
    return {
        "readCount": sum(1 for item in items if item["learning"]["viewCount"] > 0),
        "practicedCount": sum(1 for item in items if item["learning"]["practiceCount"] > 0),
        "masteredCount": sum(1 for item in items if item["learning"]["level"] == "mastered"),
    }


def build_page_list_item(page, link_counts: dict[int, int], learning) -> dict:
    """列表里的一行（`list_wiki_pages` 的 items 元素）"""
    return {
        "pageId": int(page.id),
        "kbId": int(page.kb_id),
        "title": page.title,
        "pageType": page.page_type,
        "aliases": page.aliases or [],
        "summary": strip_wiki_tokens(page.summary),
        "status": page.status,
        "version": int(page.version or 1),
        "sourceCount": len(page.source_chunk_ids or page.source_refs or []),
        "docCount": len(page.source_doc_ids or []),
        "sectionCount": len(page.sections or []),
        "relatedCount": link_counts.get(int(page.id), 0),
        "entityIds": page.entity_ids or [],
        "generatedBy": page.generated_by or "llm",
        "learning": learning,
        "updateTime": page.update_time.isoformat(sep=" ") if page.update_time else None,
    }


def build_graph_node(page, doc_names: dict[int, str], degree: dict[int, int], learning) -> dict:
    """图谱里的一个节点

    ⚠️ `sourceType` / `sourceId` / `sourceName` 的来源判定：优先用页面自带的
    `generation_meta`；没有就退到「该页的第一个来源文档」。
    """
    meta = page.generation_meta or {}
    source_type = str(meta.get("sourceType") or "").strip()
    try:
        source_id = int(meta.get("sourceId") or 0)
    except (TypeError, ValueError):
        source_id = 0
    source_name = str(meta.get("sourceName") or "").strip()
    page_doc_ids = [int(x) for x in (page.source_doc_ids or []) if str(x).isdigit()]
    if not source_type and page_doc_ids:
        source_type = "document"
        source_id = page_doc_ids[0]
        source_name = doc_names.get(page_doc_ids[0], "")
    return {
        "id": str(page.id),
        "pageId": int(page.id),
        "title": page.title,
        "pageType": page.page_type,
        "aliases": page.aliases or [],
        "docIds": page.source_doc_ids or [],
        "sourceType": source_type or "unknown",
        "sourceId": source_id,
        "sourceName": source_name,
        "summary": strip_wiki_tokens(page.summary),
        "status": page.status,
        "degree": degree.get(int(page.id), 0),
        "sectionCount": len(page.sections or []),
        "learning": learning,
    }


def build_graph_edges(links) -> list[dict]:
    """图谱里的边（只来自链接表）"""
    return [
        {
            "id": int(link.id),
            "source": str(link.from_page_id),
            "target": str(link.to_page_id),
            "type": link.link_type,
            "weight": int(link.weight or 5),
        }
        for link in links
    ]


def build_mention_edges(pages, page_ids, edges) -> list[dict]:
    """图谱里的「提及」边 —— 即使页面图还没重建，也把正文里的内链即时画出来。

    前端不需要等一次写库。⚠️ 返回**新列表**（不改入参）。
    """
    known_edges = {(str(edge["source"]), str(edge["target"])) for edge in edges}
    out = list(edges)
    for page in pages:
        for block in page_text_blocks(str(page.summary or ""), page.sections or []):
            for item in extract_wiki_links(str(block.get("text") or "")):
                source_id, target_id = str(page.id), str(item["pageId"])
                if target_id not in {str(x) for x in page_ids} or (source_id, target_id) in known_edges:
                    continue
                known_edges.add((source_id, target_id))
                out.append(
                    {
                        "id": f"mention-{source_id}-{target_id}",
                        "source": source_id,
                        "target": target_id,
                        "type": "mention",
                        "weight": 5,
                    }
                )
    return out


def build_out_links(page, page_by_id) -> list[dict]:
    """页面正文里的**出链**（去重 + 排序）"""
    out_links: list[dict] = []
    seen_out: set[tuple[int, int, str]] = set()
    for block in page_text_blocks(str(page.summary or ""), page.sections or []):
        for item in extract_wiki_links(str(block.get("text") or ""), int(block.get("sectionIndex", -1))):
            target = page_by_id.get(int(item["pageId"]))
            if not target or int(target.id) == int(page.id):
                continue
            key = (int(target.id), int(item["sectionIndex"]), str(item["anchorText"]))
            if key in seen_out:
                continue
            seen_out.add(key)
            out_links.append(
                {
                    "pageId": int(target.id),
                    "title": target.title,
                    "pageType": target.page_type,
                    "anchorText": item["anchorText"],
                    "sectionIndex": int(item["sectionIndex"]),
                    "startOffset": int(item["startOffset"]),
                    "endOffset": int(item["endOffset"]),
                    "source": "content",
                }
            )
    out_links.sort(key=link_sort_key)
    return out_links


def build_in_links(page, pages) -> list[dict]:
    """页面正文里的**反链**（别的页面链到了本页；去重 + 排序）"""
    in_links: list[dict] = []
    seen_in: set[tuple[int, int, str]] = set()
    for other in pages:
        if int(other.id) == int(page.id):
            continue
        for block in page_text_blocks(str(other.summary or ""), other.sections or []):
            for item in extract_wiki_links(str(block.get("text") or ""), int(block.get("sectionIndex", -1))):
                if int(item["pageId"]) != int(page.id):
                    continue
                key = (int(other.id), int(item["sectionIndex"]), str(item["anchorText"]))
                if key in seen_in:
                    continue
                seen_in.add(key)
                in_links.append(
                    {
                        "pageId": int(other.id),
                        "title": other.title,
                        "pageType": other.page_type,
                        "anchorText": item["anchorText"],
                        "sectionIndex": int(item["sectionIndex"]),
                    }
                )
    in_links.sort(key=link_sort_key)
    return in_links


def link_sort_key(item: dict) -> tuple[str, int, str]:
    """出链 / 反链的排序键（标题 → 小节 → 锚点）"""
    return (str(item.get("title") or ""), int(item.get("sectionIndex") or -1), str(item.get("anchorText") or ""))


def build_link_stats(out_links: list[dict], in_links: list[dict]) -> dict:
    """出链 / 反链的统计（条数 + 涉及多少个页面）"""
    return {
        "outCount": len(out_links),
        "inCount": len(in_links),
        "outPageCount": len({int(item["pageId"]) for item in out_links}),
        "inPageCount": len({int(item["pageId"]) for item in in_links}),
    }
