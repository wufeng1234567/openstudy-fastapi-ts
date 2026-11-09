"""图谱共享契约的纯函数测试。"""

from app.services.rag.graph_contract import add_edge, stable_edge_id


def test_stable_edge_id_is_deterministic_and_kind_scoped():
    first = stable_edge_id("prerequisite", "topic:1", "topic:2")
    second = stable_edge_id("prerequisite", "topic:1", "topic:2")
    other_kind = stable_edge_id("mention", "topic:1", "topic:2")
    assert first == second
    assert first.startswith("e:prerequisite:")
    assert first != other_kind


def test_add_edge_deduplicates_and_ignores_self_loop():
    edges = []
    seen = set()
    add_edge(edges, seen, source="topic:1", target="topic:2", kind="prerequisite", label="先修")
    add_edge(edges, seen, source="topic:1", target="topic:2", kind="prerequisite", label="先修")
    add_edge(edges, seen, source="topic:1", target="topic:1", kind="mention", label="自环")
    assert len(edges) == 1
    assert edges[0]["id"].startswith("e:prerequisite:")
