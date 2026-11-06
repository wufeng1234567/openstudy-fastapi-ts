"""Wiki 页面内链纯函数测试：不连数据库、不调用模型。"""

from app.services.rag.wiki_link_service import (
    extract_wiki_links,
    linkify_content,
    normalize_wiki_tokens,
    page_text_blocks,
    strip_wiki_tokens,
)


def test_linkify_prefers_longest_title_and_links_each_target_once():
    refs = [
        {"pageId": 1, "matchText": "智能体"},
        {"pageId": 2, "matchText": "LLM 智能体"},
    ]
    text = "LLM 智能体是智能体的一种；后面不再出现第二个智能体。"
    linked, count = linkify_content(text, refs, self_page_id=99)
    assert count == 2
    assert "[[page:2|LLM 智能体]]" in linked
    assert "[[page:1|智能体]]" in linked
    assert linked.count("[[page:2|") == 1
    assert linked.count("[[page:1|") == 1


def test_linkify_skips_code_existing_tokens_and_math():
    text = "正文 `智能体` 和 $智能体$ 以及 [[page:8|智能体]] 都不应重复插入。"
    linked, count = linkify_content(
        text,
        [{"pageId": 1, "matchText": "智能体"}],
        self_page_id=99,
    )
    assert count == 0
    assert linked == text


def test_linkify_never_links_single_han_character_or_self():
    text = "风沙与核心，智能体。"
    linked, count = linkify_content(
        text,
        [
            {"pageId": 1, "matchText": "风"},
            {"pageId": 2, "matchText": "智能体"},
        ],
        self_page_id=2,
    )
    assert count == 0
    assert linked == text


def test_normalize_wiki_tokens_maps_title_and_drops_unknown_or_self():
    text = "[[智能体|它]] 和 [[记忆机制|记忆]] 以及 [[不存在]] 还有 [[page:3|工具]]"
    normalized = normalize_wiki_tokens(
        text,
        {
            "智能体": {"pageId": 1, "title": "智能体"},
            "记忆机制": {"pageId": 2, "title": "记忆机制"},
        },
        [1, 2, 3],
        self_page_id=1,
    )
    assert "[[page:2|记忆]]" in normalized
    assert "[[page:1|它]]" not in normalized
    assert "它 和" in normalized
    assert "不存在" in normalized
    assert "[[page:3|工具]]" in normalized


def test_extract_and_strip_wiki_links():
    text = "先看 [[page:11|智能体]]，再看 [[page:12|记忆机制]]。"
    links = extract_wiki_links(text, section_index=2)
    assert [item["pageId"] for item in links] == [11, 12]
    assert links[0]["anchorText"] == "智能体"
    assert links[0]["sectionIndex"] == 2
    assert strip_wiki_tokens(text) == "先看 智能体，再看 记忆机制。"


def test_page_text_blocks_marks_summary_as_minus_one():
    blocks = page_text_blocks(
        "摘要",
        [
            {"heading": "一", "body": "正文一"},
            {"heading": "二", "body": "正文二"},
        ],
    )
    assert [item["sectionIndex"] for item in blocks] == [-1, 0, 1]
    assert blocks[0]["text"] == "摘要"
