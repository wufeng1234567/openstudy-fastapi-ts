"""知航：知识图谱学习航线（只读编排层）。

把「资料 → 实体/关系 → 知识百科主题页 → 同源题 → 练习流水 → 逐题诊断」
串成一条可执行的学习航线：

  · `RagWikiPageLink.link_type == "prerequisite"` 给出先学顺序；
  · `_wiki_learning_map()` 给出真实阅读/练习学习态；
  · `diagnose()` 的逐题 level 通过 `QuestionSource` 反查到主题页，形成页面级病灶；
  · 每次请求实时计算，不落库、不调 LLM。

边界
----
  · 没有 `QuestionSource` 的题不猜页面，老题不会凭空出现在航线里；
  · `diagnose()` 已过滤被物理删除的题，这里不制造幽灵站点；
  · 没有 prerequisite 边时降级为「学习态 + 连接度」排序；
  · 不改写任何已有关系、掌握度或页面内容。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionSource
from app.models.wiki import RagWikiPage, RagWikiPageLink
from app.services import study_diagnosis_service as sds
from app.services.rag import wiki_service

#: 需要优先处理的诊断等级；与 learning_loop_service.ATTENTION_LEVELS 保持一致。
ATTENTION_LEVELS = ("repeated_failure", "lapsing", "overdue")

DEFAULT_MAX_STOPS = 5
MAX_ALLOWED_STOPS = 8

ROLE_FOUNDATION = "foundation"
ROLE_REPAIR = "repair"
ROLE_EXPLORE = "explore"
ROLE_PRACTICE = "practice"
ROLE_WEAK = "weak"
ROLE_REVIEW = "review"

ROLE_LABELS = {
    ROLE_FOUNDATION: "补前置",
    ROLE_REPAIR: "补薄弱",
    ROLE_EXPLORE: "新知识",
    ROLE_PRACTICE: "去练习",
    ROLE_WEAK: "再巩固",
    ROLE_REVIEW: "复习",
}

STRATEGY_LABELS = {
    "weakness": "补弱",
    "foundation": "打基础",
    "explore": "拓展",
}

TASK_MINUTES = {
    "read": 8,
    "practice": 12,
    "ask-agent": 10,
    "review": 6,
}


def _value(item: Any, key: str, default: Any = None) -> Any:
    """同时兼容 ORM 对象和测试用 dict。"""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_int_list(values: Any) -> List[int]:
    result: List[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        result.append(number)
    return result


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _learning_of(learning_by_page: Dict[int, Dict[str, Any]], page_id: int) -> Dict[str, Any]:
    return learning_by_page.get(int(page_id)) or {}


def _signal_of(page_signals: Dict[int, Dict[str, Any]], page_id: int) -> Dict[str, Any]:
    return page_signals.get(int(page_id)) or {}


def _is_mastered(learning: Dict[str, Any]) -> bool:
    return str(learning.get("level") or "") == "mastered"


def _build_graph(
    pages: Sequence[Any],
    links: Sequence[Any],
) -> Tuple[
    Dict[int, Any],
    Dict[int, Set[int]],
    Dict[int, List[int]],
    Dict[int, List[int]],
    Dict[int, int],
    int,
]:
    """构造无向邻接（用于航线连接）与有向前置边（用于先学顺序）。

    Returns
    -------
    page_by_id, adjacency, incoming_prerequisite, outgoing_prerequisite, degree,
    prerequisite_edge_count
    """
    page_by_id: Dict[int, Any] = {}
    for page in pages:
        page_id = int(_value(page, "id", 0) or 0)
        if page_id > 0:
            page_by_id[page_id] = page

    adjacency: Dict[int, Set[int]] = {page_id: set() for page_id in page_by_id}
    incoming_prerequisite: Dict[int, List[int]] = {page_id: [] for page_id in page_by_id}
    outgoing_prerequisite: Dict[int, List[int]] = {page_id: [] for page_id in page_by_id}
    degree: Dict[int, int] = {page_id: 0 for page_id in page_by_id}
    prerequisite_edge_count = 0

    for link in links:
        source = int(_value(link, "from_page_id", 0) or 0)
        target = int(_value(link, "to_page_id", 0) or 0)
        if source not in page_by_id or target not in page_by_id or source == target:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
        degree[source] += 1
        degree[target] += 1
        if str(_value(link, "link_type", "") or "") == "prerequisite":
            incoming_prerequisite[target].append(source)
            outgoing_prerequisite[source].append(target)
            prerequisite_edge_count += 1

    return (
        page_by_id,
        adjacency,
        incoming_prerequisite,
        outgoing_prerequisite,
        degree,
        prerequisite_edge_count,
    )


def _components(adjacency: Dict[int, Set[int]]) -> List[List[int]]:
    visited: Set[int] = set()
    result: List[List[int]] = []
    for start in adjacency:
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        component: List[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        result.append(component)
    return result


def _priority(page_id: int, page_by_id: Dict[int, Any], degree: Dict[int, int],
              learning_by_page: Dict[int, Dict[str, Any]],
              page_signals: Dict[int, Dict[str, Any]],
              strategy: str = "weakness",
              unlock_count: Optional[Dict[int, int]] = None) -> float:
    """站点评分：确定性、可解释，不引入随机权重。

    strategy 只改变“先看什么”，不改变掌握度事实：
      · weakness  —— 诊断病灶 > 未读 > 已读未练 > 低正确率 > 连接度
      · foundation —— 未读的基础节点、能解锁更多后续主题的节点优先
      · explore   —— 从连接度高的核心节点向外拓展
    """
    learning = _learning_of(learning_by_page, page_id)
    if _is_mastered(learning):
        return 0.0

    signal = _signal_of(page_signals, page_id)
    weak_count = int(signal.get("weakCount") or 0)
    views = int(learning.get("viewCount") or 0)
    practices = int(learning.get("practiceCount") or 0)
    accuracy = _as_float(learning.get("accuracy"))
    unlocks = int((unlock_count or {}).get(page_id, 0))
    degree_value = int(degree.get(page_id, 0))

    if strategy == "foundation":
        score = 60.0 if views == 0 else (30.0 if practices == 0 else 8.0)
        score += min(80.0, unlocks * 20.0)
        score -= min(10.0, degree_value * 0.8)
        if weak_count > 0:
            score += 30.0 + min(40.0, weak_count * 10.0)
        if str(_value(page_by_id[page_id], "status", "") or "") == "stale":
            score -= 10.0
        return max(0.0, score)

    if strategy == "explore":
        score = 55.0 if views == 0 else 14.0
        score += min(36.0, degree_value * 2.2)
        if weak_count > 0:
            score += 18.0
        if str(_value(page_by_id[page_id], "status", "") or "") == "stale":
            score -= 10.0
        return score

    score = 0.0
    if weak_count > 0:
        score += 200.0 + min(120.0, weak_count * 40.0)
    if views == 0:
        score += 40.0
    if practices > 0:
        if accuracy < 60:
            score += 30.0
        elif accuracy < 80:
            score += 15.0
    else:
        score += 10.0
    score += min(20.0, float(degree_value))
    if str(_value(page_by_id[page_id], "status", "") or "") == "stale":
        score -= 10.0
    return score


def _collect_prerequisite_ancestors(
    page_id: int,
    incoming_prerequisite: Dict[int, List[int]],
    page_by_id: Dict[int, Any],
    learning_by_page: Dict[int, Dict[str, Any]],
    page_signals: Dict[int, Dict[str, Any]],
    degree: Dict[int, int],
    *,
    strategy: str = "weakness",
    unlock_count: Optional[Dict[int, int]] = None,
    seen: Optional[Set[int]] = None,
    depth: int = 2,
) -> List[int]:
    """收集未掌握的前置页，按「更深前置 → 近层前置」返回。"""
    if depth <= 0:
        return []
    visited = set(seen or set())
    result: List[int] = []
    candidates = [
        item
        for item in incoming_prerequisite.get(int(page_id), [])
        if item in page_by_id and item not in visited
    ]
    candidates.sort(
        key=lambda item: (
            _priority(item, page_by_id, degree, learning_by_page, page_signals, strategy, unlock_count),
            degree.get(item, 0),
        ),
        reverse=True,
    )
    for prerequisite in candidates:
        if prerequisite in visited:
            continue
        if _is_mastered(_learning_of(learning_by_page, prerequisite)):
            continue
        visited.add(prerequisite)
        result.extend(
            _collect_prerequisite_ancestors(
                prerequisite,
                incoming_prerequisite,
                page_by_id,
                learning_by_page,
                page_signals,
                degree,
                strategy=strategy,
                unlock_count=unlock_count,
                seen=visited,
                depth=depth - 1,
            )
        )
        result.append(prerequisite)
    return result


def _route_reason(
    page_id: int,
    role: str,
    page_by_id: Dict[int, Any],
    learning_by_page: Dict[int, Dict[str, Any]],
    page_signals: Dict[int, Dict[str, Any]],
    degree: Dict[int, int],
    children_with_signal: List[Dict[str, Any]],
) -> str:
    learning = _learning_of(learning_by_page, page_id)
    signal = _signal_of(page_signals, page_id)
    title = str(_value(page_by_id[page_id], "title", "主题页") or "主题页")

    if role == ROLE_FOUNDATION and children_with_signal:
        child = children_with_signal[0]
        return (
            f"《{child['title']}》有 {child['weakCount']} 道题处于"
            f"「{child['levelText']}」，而本页是它的前置，先补这一页"
        )
    if signal:
        level_text = str((signal.get("levelTexts") or ["需关注"])[0])
        return f"这页关联 {int(signal.get('weakCount') or 0)} 道「{level_text}」的题，建议先回看再练"
    views = int(learning.get("viewCount") or 0)
    practices = int(learning.get("practiceCount") or 0)
    accuracy = _as_float(learning.get("accuracy"))
    if role == ROLE_EXPLORE or views == 0:
        return f"还没读过 · 连接 {int(degree.get(page_id, 0))} 个主题"
    if practices == 0:
        return "已读但还没练过 · 用同源题检验"
    if accuracy < 60:
        return f"正确率 {accuracy}% · 建议回看后再练一轮"
    if accuracy < 80:
        return f"正确率 {accuracy}% · 再练一轮"
    if _is_mastered(learning):
        return "已掌握 · 可快速复习"
    return f"「{title}」与当前知识点相连，顺势巩固"


def plan_learning_route(
    pages: Sequence[Any],
    links: Sequence[Any],
    learning_by_page: Dict[int, Dict[str, Any]],
    *,
    max_stops: int = DEFAULT_MAX_STOPS,
    focus_page_id: Optional[int] = None,
    page_signals: Optional[Dict[int, Dict[str, Any]]] = None,
    strategy: str = "weakness",
) -> Dict[str, Any]:
    """纯函数：根据页面、页面边、学习态与诊断病灶生成学习航线。

    不访问数据库，不调 LLM，方便单测。
    """
    signals = page_signals or {}
    strategy = strategy if strategy in {"weakness", "foundation", "explore"} else "weakness"
    try:
        limit = max(1, min(int(max_stops or DEFAULT_MAX_STOPS), MAX_ALLOWED_STOPS))
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_STOPS

    (
        page_by_id,
        adjacency,
        incoming_prerequisite,
        outgoing_prerequisite,
        degree,
        prerequisite_edge_count,
    ) = _build_graph(pages, links)

    if not page_by_id:
        return {
            "pageIds": [],
            "stops": [],
            "mode": "fallback",
            "strategy": strategy,
            "stats": {
                "totalPages": 0,
                "routeCount": 0,
                "masteredCount": 0,
                "weakCount": 0,
                "prerequisiteEdgeCount": 0,
                "diagnosedPageCount": len(signals),
                "coverage": 0,
            },
        }

    unlock_count = {
        page_id: len(outgoing_prerequisite.get(page_id, []))
        for page_id in page_by_id
    }
    # 航线优先沿「前置」关系走；没有前置边时才退回全图邻接。
    # 这样课程类资料会形成清晰的知识链，不会被大量 mention 边带偏。
    route_adjacency: Dict[int, Set[int]] = {page_id: set() for page_id in page_by_id}
    if prerequisite_edge_count and strategy != "explore":
        for link in links:
            if str(_value(link, "link_type", "") or "") != "prerequisite":
                continue
            source = int(_value(link, "from_page_id", 0) or 0)
            target = int(_value(link, "to_page_id", 0) or 0)
            if source in page_by_id and target in page_by_id:
                route_adjacency[source].add(target)
                route_adjacency[target].add(source)
    else:
        route_adjacency = adjacency
    all_mastered = all(_is_mastered(_learning_of(learning_by_page, page_id)) for page_id in page_by_id)
    components = _components(route_adjacency)

    def rank(page_id: int) -> float:
        if all_mastered:
            return float(degree.get(page_id, 0))
        return _priority(
            page_id,
            page_by_id,
            degree,
            learning_by_page,
            signals,
            strategy,
            unlock_count,
        )

    focus_id = int(focus_page_id) if focus_page_id and int(focus_page_id) in page_by_id else None
    if focus_id is not None:
        component = next((item for item in components if focus_id in item), [focus_id])
        seed = focus_id
    else:
        connected_components = [item for item in components if len(item) >= 2] or components
        if strategy == "foundation":
            component = max(
                connected_components,
                key=lambda item: (len(item), sum(degree.get(page_id, 0) for page_id in item)),
            )
        else:
            component = max(
                connected_components,
                key=lambda item: (sum(rank(page_id) for page_id in item), len(item)),
            )
        if all_mastered:
            # 复习链从端点起步，才能沿邻接关系连续走过多站，而不是在中心点卡住。
            seed = min(component, key=lambda page_id: (degree.get(page_id, 0), page_id))
        else:
            seed = max(component, key=lambda page_id: (rank(page_id), degree.get(page_id, 0), -page_id))

    # 前置页必须先于目标站出现；若前置页本身已掌握则跳过。
    seen: Set[int] = {seed}
    ancestors = _collect_prerequisite_ancestors(
        seed,
        incoming_prerequisite,
        page_by_id,
        learning_by_page,
        signals,
        degree,
        strategy=strategy,
        unlock_count=unlock_count,
        seen=seen,
    )
    if len(ancestors) >= limit:
        ancestors = ancestors[-(limit - 1):] if limit > 1 else []
    route: List[int] = ancestors + [seed]

    while len(route) < limit:
        current_page = route[-1]
        if not all_mastered and strategy != "explore" and prerequisite_edge_count:
            # 补弱/打基础沿「前置 -> 后续」的有向边前进，避免把依赖页
            # 反向排到前置页后面（例如把“求导法则”排到“中值定理”之后）。
            next_page_ids = outgoing_prerequisite.get(current_page, [])
        else:
            next_page_ids = route_adjacency.get(current_page, set())
        candidates = [
            page_id
            for page_id in next_page_ids
            if page_id not in route and (all_mastered or rank(page_id) > 0)
        ]
        if not candidates:
            break
        next_page = max(
            candidates,
            key=lambda page_id: (rank(page_id), degree.get(page_id, 0), -page_id),
        )
        route.append(next_page)

    # 全部掌握时沿邻接关系补成复习链，不制造“假任务”。
    if all_mastered and len(route) == 1 and len(component) > 1:
        route = [seed]
        while len(route) < min(limit, len(component)):
            candidates = [
                page_id for page_id in route_adjacency.get(route[-1], set()) if page_id not in route
            ]
            if not candidates:
                break
            route.append(
                max(candidates, key=lambda page_id: (degree.get(page_id, 0), -page_id))
            )

    route_set = set(route)
    ancestor_set = set(ancestors)

    def children_with_signal(page_id: int) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for child_id in outgoing_prerequisite.get(page_id, []):
            child_signal = _signal_of(signals, child_id)
            if not child_signal:
                continue
            level_texts = child_signal.get("levelTexts") or ["需关注"]
            result.append(
                {
                    "pageId": int(child_id),
                    "title": str(_value(page_by_id[child_id], "title", "主题页") or "主题页"),
                    "weakCount": int(child_signal.get("weakCount") or 0),
                    "levelText": str(level_texts[0]),
                }
            )
        result.sort(key=lambda item: item["weakCount"], reverse=True)
        return result

    details: List[Dict[str, Any]] = []
    first_open_index: Optional[int] = None
    for index, page_id in enumerate(route):
        learning = _learning_of(learning_by_page, page_id)
        practiced = int(learning.get("practiceCount") or 0)
        if not _is_mastered(learning) and practiced == 0 and first_open_index is None:
            first_open_index = index

    for index, page_id in enumerate(route):
        learning = _learning_of(learning_by_page, page_id)
        signal = _signal_of(signals, page_id)
        views = int(learning.get("viewCount") or 0)
        practices = int(learning.get("practiceCount") or 0)
        accuracy = _as_float(learning.get("accuracy"))
        if page_id in ancestor_set:
            role = ROLE_FOUNDATION
        elif signal:
            role = ROLE_REPAIR
        elif _is_mastered(learning):
            role = ROLE_REVIEW
        elif views == 0:
            role = ROLE_EXPLORE
        elif practices == 0:
            role = ROLE_PRACTICE
        elif accuracy < 60:
            role = ROLE_WEAK
        else:
            role = ROLE_PRACTICE

        if first_open_index is None:
            status = "review"
        elif index < first_open_index:
            status = "done"
        elif index == first_open_index:
            status = "current"
        else:
            status = "next"

        prerequisites = [
            {
                "pageId": int(prerequisite),
                "title": str(_value(page_by_id[prerequisite], "title", "主题页") or "主题页"),
                "mastered": _is_mastered(_learning_of(learning_by_page, prerequisite)),
            }
            for prerequisite in incoming_prerequisite.get(page_id, [])
            if prerequisite in page_by_id
        ]
        unlocks = [
            {
                "pageId": int(child_id),
                "title": str(_value(page_by_id[child_id], "title", "主题页") or "主题页"),
                "mastered": _is_mastered(_learning_of(learning_by_page, child_id)),
            }
            for child_id in outgoing_prerequisite.get(page_id, [])
            if child_id in page_by_id
        ]
        details.append(
            {
                "pageId": int(page_id),
                "title": str(_value(page_by_id[page_id], "title", "主题页") or "主题页"),
                "pageType": str(_value(page_by_id[page_id], "page_type", "concept") or "concept"),
                "learning": learning,
                "weakCount": int(signal.get("weakCount") or 0),
                "weakQuestionIds": [int(x) for x in (signal.get("questionIds") or [])],
                "reason": _route_reason(
                    page_id,
                    role,
                    page_by_id,
                    learning_by_page,
                    signals,
                    degree,
                    children_with_signal(page_id),
                ),
                "role": role,
                "roleLabel": ROLE_LABELS.get(role, "学习"),
                "status": status,
                "prerequisites": prerequisites,
                "unlocks": unlocks,
            }
        )

    total_pages = len(page_by_id)
    read_count = sum(1 for page_id in page_by_id if int(_learning_of(learning_by_page, page_id).get("viewCount") or 0) > 0)
    practiced_count = sum(1 for page_id in page_by_id if int(_learning_of(learning_by_page, page_id).get("practiceCount") or 0) > 0)
    mastered_count = sum(1 for page_id in page_by_id if _is_mastered(_learning_of(learning_by_page, page_id)))
    weak_count = sum(1 for page_id in page_by_id if _signal_of(signals, page_id).get("weakCount"))

    return {
        "pageIds": route,
        "stops": details,
        "mode": "graph" if prerequisite_edge_count else "fallback",
        "strategy": strategy,
        "stats": {
            "totalPages": total_pages,
            "routeCount": len(route),
            "readCount": read_count,
            "practicedCount": practiced_count,
            "masteredCount": mastered_count,
            "weakCount": weak_count,
            "prerequisiteEdgeCount": prerequisite_edge_count,
            "diagnosedPageCount": len(signals),
            "coverage": round(read_count / total_pages * 100, 1) if total_pages else 0.0,
        },
    }


async def _load_diagnosis_page_signals(
    db: AsyncSession,
    user_id: int,
    pages: Sequence[RagWikiPage],
    *,
    diagnosis: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    """把逐题诊断反查到主题页，形成页面级病灶。

    只有真实 `QuestionSource` 锚点才参与；没有锚点的老题跳过。
    `diagnosis` 可由调用方复用，避免同一请求重复跑逐题诊断。
    """
    diagnosis = diagnosis or await sds.diagnose(db, user_id, limit=50)
    attention_items = [
        item
        for item in (diagnosis.get("items") or [])
        if str(item.get("level") or "") in ATTENTION_LEVELS
    ]
    if not attention_items:
        return {}, diagnosis

    chunk_to_pages: Dict[int, Set[int]] = {}
    doc_to_pages: Dict[int, Set[int]] = {}
    for page in pages:
        page_id = int(getattr(page, "id", 0) or 0)
        if not page_id:
            continue
        for chunk_id in _as_int_list(getattr(page, "source_chunk_ids", None)):
            chunk_to_pages.setdefault(chunk_id, set()).add(page_id)
        for doc_id in _as_int_list(getattr(page, "source_doc_ids", None)):
            doc_to_pages.setdefault(doc_id, set()).add(page_id)

    question_ids = sorted(
        {
            int(item.get("questionId") or 0)
            for item in attention_items
            if str(item.get("questionId") or "").isdigit()
        }
    )
    if not question_ids:
        return {}, diagnosis

    source_rows = (
        await db.execute(
            select(QuestionSource).where(
                QuestionSource.user_id == int(user_id),
                QuestionSource.question_id.in_(question_ids),
            )
        )
    ).scalars().all()
    source_by_question = {int(row.question_id): row for row in source_rows}

    signals: Dict[int, Dict[str, Any]] = {}
    for item in attention_items:
        try:
            question_id = int(item.get("questionId") or 0)
        except (TypeError, ValueError):
            continue
        source = source_by_question.get(question_id)
        if source is None:
            continue
        target_pages: Set[int] = set()
        chunk_id = int(source.chunk_id) if source.chunk_id is not None else 0
        if chunk_id:
            target_pages.update(chunk_to_pages.get(chunk_id, set()))
        if not target_pages:
            doc_id = int(source.doc_id) if source.doc_id is not None else 0
            if doc_id:
                target_pages.update(doc_to_pages.get(doc_id, set()))
        if not target_pages:
            continue
        for page_id in target_pages:
            signal = signals.setdefault(
                page_id,
                {"weakCount": 0, "levelTexts": [], "questionIds": []},
            )
            signal["weakCount"] += 1
            level_text = str(item.get("levelText") or "需关注")
            if level_text not in signal["levelTexts"]:
                signal["levelTexts"].append(level_text)
            signal["questionIds"].append(question_id)

    return signals, diagnosis


def _task_for_stop(
    stop: Dict[str, Any],
    practice: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    learning = stop.get("learning") or {}
    views = int(learning.get("viewCount") or 0)
    role = str(stop.get("role") or "")
    if views == 0:
        return {"type": "read", "label": "读主题页", "pageId": int(stop["pageId"])}
    if role == ROLE_REVIEW or str(learning.get("level") or "") == "mastered":
        return {"type": "review", "label": "快速复习", "pageId": int(stop["pageId"])}
    if practice and practice.get("bankId"):
        count = int(practice.get("questionCount") or 0)
        return {
            "type": "practice",
            "label": f"去练 {count} 题" if count else "去练同源题",
            "pageId": int(stop["pageId"]),
            "bankId": int(practice["bankId"]),
            "bankName": str(practice.get("bankName") or "题库"),
            "questionCount": count,
        }
    return {"type": "ask-agent", "label": "生成练习", "pageId": int(stop["pageId"])}


def _headline_for(
    diagnosis: Dict[str, Any],
    signals: Dict[int, Dict[str, Any]],
    prerequisite_edge_count: int,
    strategy: str = "weakness",
) -> str:
    if strategy == "foundation":
        return "从知识结构底层开始，先把基础打牢"
    if strategy == "explore":
        return "从核心主题出发，向外拓展知识网络"
    if signals and diagnosis.get("headline"):
        return str(diagnosis["headline"])
    if not diagnosis.get("hasData"):
        return "从图谱结构出发，先点亮第一颗星"
    if prerequisite_edge_count:
        return "按图谱前置关系为你排好了今天的学习航线"
    return "按图谱连接与学习态为你排好了今天的学习航线"


async def build_learning_route(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    max_stops: int = DEFAULT_MAX_STOPS,
    focus_page_id: Optional[int] = None,
    strategy: str = "weakness",
) -> Dict[str, Any]:
    """生成当前资料夹的「知航」学习航线（只读）。"""
    strategy = strategy if strategy in {"weakness", "foundation", "explore"} else "weakness"
    pages = (
        await db.execute(
            select(RagWikiPage)
            .where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_([wiki_service.WIKI_READY, wiki_service.WIKI_STALE]),
            )
            .order_by(RagWikiPage.id.asc())
        )
    ).scalars().all()
    if not pages:
        return {
            "hasRoute": False,
            "reason": "当前资料夹还没有知识百科主题页，先生成知识百科",
            "stops": [],
            "edges": [],
            "stats": {"totalPages": 0},
        }

    page_by_id = {int(page.id): page for page in pages}
    links = (
        await db.execute(
            select(RagWikiPageLink).where(
                RagWikiPageLink.user_id == int(user_id),
                RagWikiPageLink.kb_id == int(kb_id),
            )
        )
    ).scalars().all()

    learning_by_page = await wiki_service._wiki_learning_map(db, int(user_id), pages)
    signals, diagnosis = await _load_diagnosis_page_signals(db, int(user_id), pages)
    plan = plan_learning_route(
        pages,
        links,
        learning_by_page,
        max_stops=max_stops,
        focus_page_id=focus_page_id,
        page_signals=signals,
        strategy=strategy,
    )
    if not plan.get("pageIds"):
        return {
            "hasRoute": False,
            "reason": "当前资料夹还没有可规划的主题页",
            "stops": [],
            "edges": [],
            "stats": plan.get("stats") or {"totalPages": len(pages)},
        }

    stops: List[Dict[str, Any]] = []
    total_minutes = 0
    for stop in plan.get("stops") or []:
        page = page_by_id[int(stop["pageId"])]
        practice = await wiki_service._wiki_practice_bank(db, int(user_id), page)
        task = _task_for_stop(stop, practice)
        stop["practice"] = (
            {
                "bankId": int(practice["bankId"]),
                "bankName": str(practice.get("bankName") or "题库"),
                "questionCount": int(practice.get("questionCount") or 0),
                "questionIds": [int(x) for x in (practice.get("questionIds") or [])],
            }
            if practice and practice.get("bankId")
            else None
        )
        stop["task"] = task
        stop["estimatedMinutes"] = TASK_MINUTES.get(str(task.get("type") or ""), 8)
        total_minutes += int(stop["estimatedMinutes"])
        stops.append(stop)

    route_page_ids = {int(stop["pageId"]) for stop in stops}
    link_by_pair: Dict[Tuple[int, int], Any] = {}
    for link in links:
        source = int(link.from_page_id)
        target = int(link.to_page_id)
        if source not in route_page_ids or target not in route_page_ids:
            continue
        pair = (source, target)
        current = link_by_pair.get(pair)
        if current is None or int(link.weight or 5) > int(getattr(current, "weight", 0) or 0):
            link_by_pair[pair] = link
    route_edges: List[Dict[str, Any]] = []
    for previous, current in zip(stops, stops[1:]):
        source = int(previous["pageId"])
        target = int(current["pageId"])
        link = link_by_pair.get((source, target)) or link_by_pair.get((target, source))
        if link is None:
            current["edgeFromPrev"] = None
            continue
        edge = {
            "source": str(int(link.from_page_id)),
            "target": str(int(link.to_page_id)),
            "type": str(link.link_type or "related"),
            "weight": int(link.weight or 5),
        }
        route_edges.append(edge)
        current["edgeFromPrev"] = {
            "pageId": int(link.from_page_id),
            "type": edge["type"],
            "weight": edge["weight"],
        }
    if stops:
        stops[0]["edgeFromPrev"] = None

    stats = dict(plan.get("stats") or {})
    stats["estimatedMinutes"] = total_minutes
    stats["routeCount"] = len(stops)
    stats["weakCount"] = sum(1 for stop in stops if int(stop.get("weakCount") or 0) > 0)
    all_mastered = bool(stops) and all(
        str((stop.get("learning") or {}).get("level") or "") == "mastered" for stop in stops
    )
    degraded = {
        "noPracticeData": not bool(diagnosis.get("hasData")),
        "noQuestionSource": not bool(signals),
        "noPrerequisiteEdges": int(stats.get("prerequisiteEdgeCount") or 0) == 0,
        "allMastered": all_mastered,
    }

    return {
        "hasRoute": True,
        "mode": plan.get("mode") or "fallback",
        "strategy": strategy,
        "strategyLabel": STRATEGY_LABELS.get(strategy, "补弱"),
        "directionAssumed": bool(stats.get("prerequisiteEdgeCount")),
        "generatedAt": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "headline": _headline_for(
            diagnosis,
            signals,
            int(stats.get("prerequisiteEdgeCount") or 0),
            strategy,
        ),
        "targetPageId": int(focus_page_id) if focus_page_id and int(focus_page_id) in page_by_id else None,
        "targetTitle": (
            str(page_by_id[int(focus_page_id)].title)
            if focus_page_id and int(focus_page_id) in page_by_id
            else ""
        ),
        "summary": f"共 {len(stops)} 站 · 预计 {total_minutes} 分钟",
        "stops": stops,
        "edges": route_edges,
        "stats": stats,
        "degraded": degraded,
    }


__all__ = [
    "ATTENTION_LEVELS",
    "DEFAULT_MAX_STOPS",
    "MAX_ALLOWED_STOPS",
    "build_learning_route",
    "plan_learning_route",
]



