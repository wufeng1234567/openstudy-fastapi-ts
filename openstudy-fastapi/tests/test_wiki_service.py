"""知识百科纯函数测试：不连数据库、不调用模型。"""

from app.services.rag.hybrid_search import ChunkHit, reciprocal_rank_fusion
from app.services.rag.wiki_service import (
    _display_title,
    _normalize_title,
    _parse_page_payload,
    _render_markdown,
    _validate_page_payload,
)


def test_parse_page_payload_accepts_fenced_json():
    payload = _parse_page_payload(
        """```json
        {"summary":"智能体是能感知环境并行动的系统",
         "sections":[{"heading":"核心要点","body":"资料里的说明","sourceChunkIds":[11]}],
         "relatedTitles":["记忆机制"]}
        ```"""
    )
    assert payload["summary"].startswith("智能体")
    assert payload["sections"][0]["heading"] == "核心要点"


def test_validate_page_payload_drops_fake_source_and_keeps_real_one():
    payload = {
        "summary": "一句话",
        "sections": [
            {"heading": "有效", "body": "有来源", "sourceChunkIds": [11, 999]},
            {"heading": "无效", "body": "模型编的来源", "sourceChunkIds": [999]},
        ],
        "relatedTitles": ["记忆机制", "不存在的主题"],
    }
    validated = _validate_page_payload(payload, [11], ["记忆机制"], "默认摘要")
    assert len(validated["sections"]) == 1
    assert validated["sections"][0]["sourceChunkIds"] == [11]
    assert validated["relatedTitles"] == ["记忆机制"]


def test_normalize_title_merges_explanatory_suffix():
    assert _normalize_title("智能体定义") == _normalize_title("智能体")
    assert _normalize_title("函数图像") != _normalize_title("函数")


def test_display_title_removes_definition_suffix_but_keeps_case():
    assert _display_title("智能体定义") == "智能体"
    assert _display_title("LLM 智能体") == "LLM 智能体"
    assert _display_title("函数图像") == "函数图像"


def test_render_markdown_keeps_summary_and_sections():
    markdown = _render_markdown("一句话", [{"heading": "核心要点", "body": "正文"}])
    assert "一句话" in markdown
    assert "## 核心要点" in markdown
    assert "正文" in markdown


def test_wiki_and_document_chunk_ids_do_not_collide_in_rrf():
    doc = ChunkHit(chunk_id=1, doc_id=1, kb_id=1, chunk_index=0, content="原资料")
    wiki = ChunkHit(
        chunk_id=1,
        doc_id=0,
        kb_id=1,
        chunk_index=0,
        content="知识百科",
        wiki_hit=True,
        wiki_page_id=9,
        wiki_page_title="智能体",
    )
    fused = reciprocal_rank_fusion([[doc], [wiki]], top_k=10)
    assert len(fused) == 2
    assert {hit.fusion_key for hit in fused} == {"doc:1", "wiki:1"}
    assert any(hit.wiki_hit for hit in fused)
