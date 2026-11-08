"""知识百科纯函数测试：不连数据库、不调用模型。"""

from app.services.rag.hybrid_search import ChunkHit, reciprocal_rank_fusion
from app.services.rag.wiki_service import (
    _asset_source_ref,
    _display_title,
    _manual_sections,
    _normalize_title,
    _parse_page_payload,
    _render_markdown,
    _validate_page_payload,
    build_learning_snapshot,
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
        wiki_stale=True,
    )
    fused = reciprocal_rank_fusion([[doc], [wiki]], top_k=10)
    assert len(fused) == 2
    assert {hit.fusion_key for hit in fused} == {"doc:1", "wiki:1"}
    assert any(hit.wiki_hit for hit in fused)
    assert any(hit.wiki_stale for hit in fused)


def test_manual_sections_drops_unknown_source_chunk_ids():
    sections = _manual_sections(
        [
            {"heading": "要点", "body": "正文", "sourceChunkIds": [11, 999]},
            {"heading": "无来源", "body": "用户自己写的内容"},
        ],
        allowed_chunk_ids=[11],
    )
    assert sections[0]["sourceChunkIds"] == [11]
    assert sections[1]["sourceChunkIds"] == []


def test_asset_source_ref_parses_doc_and_chat_keys():
    assert _asset_source_ref("doc:123:2") == ("document_image", 123, "2")
    assert _asset_source_ref("chat:45") == ("chat_image", 45, None)
    try:
        _asset_source_ref("bad-key")
    except ValueError:
        pass
    else:
        raise AssertionError("bad asset key should fail")


def test_learning_snapshot_distinguishes_unread_read_and_practiced():
    assert build_learning_snapshot()["level"] == "unread"
    assert build_learning_snapshot()["masteryScore"] == 0

    reading = build_learning_snapshot(view_count=2)
    assert reading["level"] == "reading"
    assert reading["masteryScore"] == 25

    practicing = build_learning_snapshot(view_count=1, practice_count=1, correct_count=1)
    assert practicing["level"] == "practicing"
    assert practicing["accuracy"] == 100.0
    assert 25 < practicing["masteryScore"] < 80


def test_learning_snapshot_mastery_requires_practice_volume_and_accuracy():
    mastered = build_learning_snapshot(view_count=2, practice_count=5, correct_count=5)
    assert mastered["level"] == "mastered"
    assert mastered["masteryScore"] == 100

    weak = build_learning_snapshot(view_count=2, practice_count=5, correct_count=2)
    assert weak["level"] == "practicing"
    assert weak["accuracy"] == 40.0
    assert weak["wrongCount"] == 3
    assert weak["masteryScore"] < 80
