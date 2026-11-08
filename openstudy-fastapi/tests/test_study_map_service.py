"""统一图谱的纯规则测试（不连数据库）。"""

from app.services.rag.study_map_service import _parse_source_types, _topic_id, _trim_to_limit


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
