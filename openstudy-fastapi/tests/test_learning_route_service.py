"""知航学习航线纯函数测试：不连数据库，不调用模型。"""

from app.services.rag.learning_route_service import plan_learning_route
from app.services.rag.wiki_service import build_learning_snapshot


def _page(page_id: int, title: str, status: str = "ready"):
    return {
        "id": page_id,
        "title": title,
        "page_type": "concept",
        "status": status,
    }


def _link(source: int, target: int, link_type: str = "prerequisite", weight: int = 8):
    return {
        "from_page_id": source,
        "to_page_id": target,
        "link_type": link_type,
        "weight": weight,
    }


def _learning(**kwargs):
    return build_learning_snapshot(**kwargs)


def test_prerequisite_page_comes_before_weak_target():
    pages = [_page(1, "条件概率"), _page(2, "贝叶斯公式"), _page(3, "全概率公式")]
    links = [_link(1, 2)]
    learning = {
        1: _learning(),
        2: _learning(),
        3: _learning(),
    }
    signals = {2: {"weakCount": 2, "levelTexts": ["反复失守"]}}

    result = plan_learning_route(pages, links, learning, max_stops=3, page_signals=signals)

    assert result["pageIds"].index(1) < result["pageIds"].index(2)
    assert result["stops"][0]["role"] == "foundation"
    assert "前置" in result["stops"][0]["reason"]


def test_diagnosed_weak_page_is_preferred():
    pages = [_page(1, "普通概念"), _page(2, "薄弱概念")]
    learning = {1: _learning(), 2: _learning()}
    signals = {2: {"weakCount": 1, "levelTexts": ["反复失守"]}}

    result = plan_learning_route(pages, [], learning, max_stops=2, page_signals=signals)

    assert result["pageIds"][0] == 2
    assert result["stops"][0]["role"] == "repair"


def test_mastered_prerequisite_is_not_added_to_route():
    pages = [_page(1, "已掌握前置"), _page(2, "待学主题")]
    links = [_link(1, 2)]
    learning = {
        1: _learning(view_count=5, practice_count=5, correct_count=5),
        2: _learning(),
    }

    result = plan_learning_route(pages, links, learning, max_stops=2)

    assert 1 not in result["pageIds"]
    assert result["pageIds"][0] == 2


def test_no_prerequisite_edges_falls_back_to_learning_priority():
    pages = [_page(1, "概念 A"), _page(2, "概念 B")]
    links = [_link(1, 2, link_type="related", weight=5)]
    learning = {1: _learning(view_count=1), 2: _learning()}

    result = plan_learning_route(pages, links, learning, max_stops=2)

    assert result["mode"] == "fallback"
    assert result["stats"]["prerequisiteEdgeCount"] == 0
    assert result["pageIds"]


def test_all_mastered_returns_review_chain_without_fake_tasks():
    pages = [_page(1, "A"), _page(2, "B"), _page(3, "C")]
    links = [_link(1, 2), _link(2, 3)]
    learning = {
        1: _learning(view_count=2, practice_count=5, correct_count=5),
        2: _learning(view_count=2, practice_count=5, correct_count=5),
        3: _learning(view_count=2, practice_count=5, correct_count=5),
    }

    result = plan_learning_route(pages, links, learning, max_stops=3)

    assert len(result["pageIds"]) == 3
    assert all(stop["status"] == "review" for stop in result["stops"])


def test_max_stops_is_respected():
    pages = [_page(index, f"节点 {index}") for index in range(1, 7)]
    links = [_link(index, index + 1) for index in range(1, 6)]
    learning = {index: _learning() for index in range(1, 7)}

    result = plan_learning_route(pages, links, learning, max_stops=3)

    assert len(result["pageIds"]) <= 3
    assert len(result["stops"]) == len(result["pageIds"])


def test_prerequisite_cycle_does_not_loop_forever():
    pages = [_page(1, "A"), _page(2, "B")]
    links = [_link(1, 2), _link(2, 1)]
    learning = {1: _learning(), 2: _learning()}

    result = plan_learning_route(pages, links, learning, max_stops=3)

    assert set(result["pageIds"]) == {1, 2}


def test_empty_pages_returns_empty_route():
    result = plan_learning_route([], [], {}, max_stops=3)

    assert result["pageIds"] == []
    assert result["mode"] == "fallback"
    assert result["stats"]["totalPages"] == 0


def test_route_strategy_changes_plan_emphasis():
    pages = [_page(1, "基础"), _page(2, "核心"), _page(3, "拓展")]
    links = [_link(1, 2, link_type="related"), _link(2, 3, link_type="related")]
    learning = {1: _learning(), 2: _learning(), 3: _learning()}

    weakness = plan_learning_route(pages, links, learning, max_stops=3, strategy="weakness")
    foundation = plan_learning_route(pages, links, learning, max_stops=3, strategy="foundation")
    explore = plan_learning_route(pages, links, learning, max_stops=3, strategy="explore")

    assert weakness["strategy"] == "weakness"
    assert foundation["strategy"] == "foundation"
    assert explore["strategy"] == "explore"
    assert foundation["pageIds"][0] != explore["pageIds"][0]
