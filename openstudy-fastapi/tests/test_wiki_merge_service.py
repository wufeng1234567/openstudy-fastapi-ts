"""主题页/实体来源合并纯规则测试（不连数据库）。"""

from app.models.knowledge_graph import RagGraphEntity
from app.models.wiki import RagWikiPage
from app.services.rag.knowledge_graph_service import _connected_entity_groups
from app.services.rag.wiki_merge_service import (
    apply_source_to_page,
    merge_generation_sources,
    merge_sections,
    merge_source_refs,
)


def test_merge_source_refs_keeps_both_documents():
    refs = merge_source_refs(
        [{"docId": 1, "chunkId": 11, "docName": "理论文档", "quote": "定义"}],
        [{"docId": 2, "chunkId": 21, "docName": "实操文档", "quote": "步骤"}],
    )
    assert {item["docId"] for item in refs} == {1, 2}


def test_merge_sections_keeps_source_blocks_and_drops_duplicates():
    sections = merge_sections(
        [{"heading": "定义", "body": "理论定义", "sourceChunkIds": [11]}],
        [{"heading": "步骤", "body": "实操步骤", "sourceChunkIds": [21]}],
        source_type="document",
        source_id=2,
        source_name="实操文档",
    )
    assert [item["heading"] for item in sections] == ["定义", "步骤"]
    assert sections[1]["sourceType"] == "document"
    assert sections[1]["sourceId"] == 2


def test_merge_generation_sources_keeps_all_sources():
    meta = merge_generation_sources(
        {"sourceType": "document", "sourceId": 1, "sourceName": "理论文档"},
        source_type="document",
        source_id=2,
        source_name="实操文档",
    )
    assert {item["sourceId"] for item in meta["sources"]} == {1, 2}


def test_apply_source_to_page_does_not_overwrite_old_source():
    page = RagWikiPage(
        user_id=1,
        kb_id=2,
        title="智能体",
        normalized_title="智能体",
        page_type="concept",
        summary="理论定义",
        content_md="理论定义",
        sections=[{"heading": "理论", "body": "定义", "sourceChunkIds": [11]}],
        source_refs=[{"docId": 1, "chunkId": 11, "docName": "理论文档"}],
        source_doc_ids=[1],
        source_chunk_ids=[11],
        entity_ids=[10],
        aliases=["AI Agent"],
        generation_meta={"sourceType": "document", "sourceId": 1, "sourceName": "理论文档"},
    )
    apply_source_to_page(
        page,
        title="智能体",
        page_type="concept",
        summary="实操流程",
        sections=[{"heading": "实操", "body": "步骤", "sourceChunkIds": [21]}],
        source_refs=[{"docId": 2, "chunkId": 21, "docName": "实操文档"}],
        source_chunk_ids=[21],
        entity_ids=[10, 11],
        source_type="document",
        source_id=2,
        source_name="实操文档",
    )
    assert page.source_doc_ids == [1, 2]
    assert {item["docId"] for item in page.source_refs} == {1, 2}
    assert {item["heading"] for item in page.sections} == {"理论", "实操", "来源摘要 · 实操文档"}
    assert page.summary == "理论定义"
    assert {item["sourceId"] for item in page.generation_meta["sources"]} == {1, 2}


def test_connected_entity_groups_merges_alias_only_same_type():
    rows = [
        RagGraphEntity(id=1, name="智能体", type="概念", aliases=["AI Agent"]),
        RagGraphEntity(id=2, name="AI Agent", type="概念", aliases=[]),
        RagGraphEntity(id=3, name="智能体", type="工具", aliases=[]),
    ]
    groups = _connected_entity_groups(rows)
    assert len(groups) == 1
    assert {item.id for item in groups[0]} == {1, 2}
