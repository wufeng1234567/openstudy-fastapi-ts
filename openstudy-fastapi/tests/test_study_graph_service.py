"""学习图谱纯规则测试：不连数据库、不调模型。"""

from app.services.rag.study_graph_service import (
    _bank_weak_questions,
    _page_source_maps,
    _weak_count_by_bank,
    is_legacy_exam_bank,
)


class _Page:
    def __init__(self, page_id: int, docs=None, chunks=None):
        self.id = page_id
        self.source_doc_ids = docs or []
        self.source_chunk_ids = chunks or []


def test_page_source_maps_are_real_doc_and_chunk_indexes():
    pages = [_Page(11, docs=[100], chunks=[900, 901]), _Page(12, docs=[100], chunks=[902])]
    doc_to_pages, chunk_to_pages = _page_source_maps(pages)

    assert doc_to_pages[100] == {11, 12}
    assert chunk_to_pages[900] == {11}
    assert chunk_to_pages[902] == {12}


def test_bank_weak_questions_skip_non_attention_levels_and_missing_bank():
    items = [
        {
            "questionId": 1,
            "bankId": 7,
            "bankName": "题库 A",
            "level": "repeated_failure",
            "levelText": "反复失守",
            "questionText": "题一",
            "attempts": 4,
            "accuracy": 20,
        },
        {
            "questionId": 2,
            "bankId": 7,
            "bankName": "题库 A",
            "level": "mastered",
            "levelText": "可以毕业",
            "questionText": "题二",
            "attempts": 4,
            "accuracy": 100,
        },
        {
            "questionId": 3,
            "bankId": 0,
            "bankName": "无归属",
            "level": "lapsing",
            "levelText": "一做就错",
            "questionText": "题三",
            "attempts": 3,
            "accuracy": 30,
        },
    ]
    grouped = _bank_weak_questions(items, limit=5)

    assert list(grouped) == [7]
    assert [item["questionId"] for item in grouped[7]] == [1]
    assert _weak_count_by_bank(items) == {7: 1}


def test_legacy_exam_bank_detection_is_name_based_only():
    assert is_legacy_exam_bank("考前计划·期末考试·题库") is True
    assert is_legacy_exam_bank("人工智能基础") is False
    assert is_legacy_exam_bank(None) is False
