"""学习建议 / 智能报告的纯规则测试（不连数据库、不调模型）。"""

from app.services.document_smart_report_service import build_template_report
from app.services.study_advice_service import _trace_from_graph, build_template_advice, focus_graph


def _graph():
    nodes = [
        {"id": "topic:1", "kind": "topic", "title": "极限", "metrics": {"weakCount": 0, "degree": 1}, "detail": {}},
        {"id": "topic:2", "kind": "topic", "title": "导数", "metrics": {"weakCount": 0, "degree": 1}, "detail": {}},
        {"id": "bank:9", "kind": "bank", "title": "题库", "metrics": {"weakCount": 3, "degree": 1}, "detail": {}},
    ]
    edges = [
        {"id": "e:1", "source": "topic:1", "target": "topic:2", "kind": "prerequisite", "label": "前置", "weight": 5},
        {"id": "e:2", "source": "bank:9", "target": "topic:2", "kind": "question_source", "label": "题源", "weight": 2},
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {"topicCount": 2, "bankCount": 1, "weakQuestionCount": 3},
        "degraded": {},
    }


def test_trace_follows_real_edges_and_is_deterministic():
    trace = _trace_from_graph(_graph(), seed_node_id="topic:1")
    assert trace["seedNodeId"] == "topic:1"
    assert trace["steps"]
    assert trace["steps"][0]["from"] == "topic:1"
    assert trace["steps"][0]["to"] == "topic:2"
    assert trace["steps"][0]["edgeId"] == "e:1"
    # 同一输入重算，traceId 不变
    again = _trace_from_graph(_graph(), seed_node_id="topic:1")
    assert again["traceId"] == trace["traceId"]


def test_template_advice_has_no_task_completion_fields():
    trace = _trace_from_graph(_graph(), seed_node_id="topic:1")
    facts = {
        "seed": {"id": "topic:1", "title": "极限", "kind": "topic"},
        "visitedNodes": _graph()["nodes"][:2],
        "nodes": _graph()["nodes"],
        "edges": _graph()["edges"],
        "stats": {"topicCount": 2, "bankCount": 1, "weakQuestionCount": 3},
        "degraded": {},
    }
    advice = build_template_advice(facts, trace)
    assert advice["title"]
    assert advice["phases"]
    assert "tasks" not in advice
    assert "days" not in advice
    assert "status" not in advice
    assert "progress" not in advice
    assert advice["degraded"]["llmFallback"] is True


def test_template_report_uses_real_health_issues():
    report = {
        "fileName": "demo.md",
        "score": 61,
        "grade": {"label": "待改进"},
        "stats": {"sectionCount": 3, "wordCount": 1200, "questionCount": 0},
        "metrics": [{"key": "learnability", "label": "可学习化程度", "score": 40}],
        "issues": [
            {"severity": "P0", "title": "缺少练习", "detail": "第 2 章没有题目", "sectionTitle": "第 2 章"}
        ],
    }
    result = build_template_report(report)
    assert result["updateGoal"]
    assert result["improvements"]
    assert result["improvements"][0]["priority"] == "P0"
    assert "tasks" not in result
    assert result["degraded"]["llmFallback"] is True


def test_focus_graph_keeps_seed_and_one_hop_neighbors():
    focused = focus_graph(_graph(), ["topic:1"])
    assert {node["id"] for node in focused["nodes"]} == {"topic:1", "topic:2"}
    assert len(focused["edges"]) == 1
