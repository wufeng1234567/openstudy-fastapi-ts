"""资料知识地图的纯规则测试。"""

from types import SimpleNamespace

from app.services.rag.knowledge_map_service import _clean, _section_nodes


def _doc(raw):
    return SimpleNamespace(
        id=7,
        kb_id=3,
        file_name="概率论讲义.md",
        user_note="",
        raw_content=raw,
    )


def test_section_nodes_caps_visible_sections_and_keeps_offsets():
    raw = "\n".join(
        f"第{i}节 主题{i}\n" + ("内容" * 100) for i in range(1, 13)
    )
    nodes, total = _section_nodes(_doc(raw))
    assert total == 12
    assert len(nodes) == 8
    assert nodes[0]["type"] == "section"
    assert nodes[0]["meta"]["start"] == 0
    assert nodes[0]["meta"]["end"] > nodes[0]["meta"]["start"]
    assert "主题1" in nodes[0]["label"]


def test_single_section_document_does_not_create_noise_nodes():
    nodes, total = _section_nodes(_doc("只有一段正文，没有章节。"))
    assert nodes == []
    assert total <= 1


def test_clean_removes_image_markers_and_normalizes_space():
    assert _clean("这是【图2】 一段\n正文", 20) == "这是 一段 正文"
