"""统一图谱的纯规则测试（不连数据库）。"""

from types import SimpleNamespace

from app.services.rag.study_map_service import (
    _add_edge,
    _build_groups,
    _image_asset_title,
    _parse_source_types,
    _topic_id,
    _trim_to_limit,
)


def test_parse_source_types_defaults_and_filters():
    assert _parse_source_types(None) == {"wiki", "bank"}
    assert _parse_source_types("wiki,bank,unknown") == {"wiki", "bank"}
    assert _parse_source_types(["document", "web"]) == {"document", "web"}


def test_trim_keeps_seed_and_neighbor_before_limit():
    nodes = [
        {"id": "topic:1", "kind": "topic", "title": "a", "metrics": {"degree": 2}},
        {"id": "topic:2", "kind": "topic", "title": "b", "metrics": {"degree": 1}},
        {"id": "bank:9", "kind": "bank", "title": "c", "metrics": {"degree": 0}},
    ]
    edges = [{"id": "e", "source": "topic:1", "target": "topic:2", "kind": "prerequisite"}]
    kept, kept_edges = _trim_to_limit(nodes, edges, seed_node_id="topic:1", limit=2)
    assert {node["id"] for node in kept} == {"topic:1", "topic:2"}
    assert len(kept_edges) == 1


def test_topic_id_is_namespaced():
    assert _topic_id(12) == "topic:12"


def test_edge_id_is_content_derived_and_stable():
    edges = []
    seen = set()
    _add_edge(
        edges,
        seen,
        source="topic:1",
        target="bank:2",
        kind="same_source",
        label="同源",
    )
    _add_edge(
        edges,
        seen,
        source="topic:1",
        target="bank:2",
        kind="same_source",
        label="同源",
    )
    assert len(edges) == 1
    assert edges[0]["id"].startswith("e:same_source:")
    # 同一组 source/target/kind 在新的构建里必须得到同一个边 ID
    edges2 = []
    _add_edge(
        edges2,
        set(),
        source="topic:1",
        target="bank:2",
        kind="same_source",
        label="同源",
    )
    assert edges2[0]["id"] == edges[0]["id"]


def test_groups_cover_six_entity_kinds():
    nodes = [
        {"id": "topic:1", "kind": "topic"},
        {"id": "bank:2", "kind": "bank"},
        {"id": "doc:3", "kind": "document"},
        {"id": "web:4", "kind": "web"},
        {"id": "note:5", "kind": "note"},
        {"id": "image:6", "kind": "image"},
    ]
    groups = _build_groups(nodes)
    assert [group["kind"] for group in groups] == [
        "topic",
        "bank",
        "document",
        "web",
        "note",
        "image",
    ]
    assert {node_id for group in groups for node_id in group["nodeIds"]} == {
        "topic:1",
        "bank:2",
        "doc:3",
        "web:4",
        "note:5",
        "image:6",
    }


def test_image_asset_title_prefers_caption_then_document_fallback():
    doc = SimpleNamespace(file_name="智能体实操.docx")
    captioned = SimpleNamespace(
        id=1,
        asset_key="doc:9:0",
        caption="一张智能体工具调用流程图",
        ocr_text="",
        keywords=[],
        file_name="doc:9:0",
    )
    assert _image_asset_title(captioned, doc)[0] == "一张智能体工具调用流程图"
    fallback = SimpleNamespace(
        id=2,
        asset_key="doc:9:2",
        caption="",
        ocr_text="",
        keywords=[],
        file_name="",
    )
    assert _image_asset_title(fallback, doc)[0] == "智能体实操.docx-图3"
    standalone = SimpleNamespace(
        id=3,
        asset_key="chat:88",
        caption="",
        ocr_text="",
        keywords=[],
        file_name="独立架构图.png",
    )
    assert _image_asset_title(standalone, None)[0] == "独立架构图.png"
