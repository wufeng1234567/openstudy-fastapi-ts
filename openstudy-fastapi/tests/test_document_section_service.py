"""资料阅读器分段的纯函数测试：不连数据库、不调用模型。"""

from app.services.document_section_service import (
    _normalize_sections,
    _parse_llm_sections,
    _rule_sections,
)


def test_rule_sections_returns_empty_without_headings():
    assert _rule_sections("这是一段没有标题的普通正文。\n继续写一点内容。") == []


def test_rule_sections_keeps_markdown_heading_offsets():
    raw = "# 第一章\n正文一\n## 1.1 小节\n正文二"
    sections = _rule_sections(raw)
    assert [item["title"] for item in sections] == ["第一章", "1.1 小节"]
    assert sections[0]["start"] == 0
    assert sections[0]["end"] == sections[1]["start"]


def test_normalize_sections_covers_gap_before_first_heading():
    raw = "封面\n# 第一章\n正文\n## 1.1 小节\n内容"
    sections = _normalize_sections(
        raw,
        [
            {"title": "第一章", "level": 1, "start_line": 2},
            {"title": "1.1 小节", "level": 2, "start_line": 4},
        ],
        source="llm",
    )
    assert sections[0]["title"] == "开篇"
    assert sections[0]["start"] == 0
    assert sections[1]["title"] == "第一章"
    assert sections[-1]["end"] == len(raw)


def test_parse_llm_sections_accepts_fenced_json():
    payload = _parse_llm_sections(
        """```json
        {"sections":[{"title":"第一章","level":1,"start_line":1}]}
        ```"""
    )
    assert payload[0]["title"] == "第一章"
