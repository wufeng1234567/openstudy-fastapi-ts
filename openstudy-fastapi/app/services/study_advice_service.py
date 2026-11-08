"""规划建议：真实图遍历 trace + LLM 解释 + 模板降级。

关键边界
========
· 先算事实（节点/边/题数/正确率/诊断），再让 LLM 写解释；
· LLM 不允许新增节点或边，未知 nodeId / edgeId 直接丢弃；
· 输出的是 `StudyAdvice`，没有 tasks/days/status/done/progress；
· trace 是确定性的，同一输入可复现，不依赖前端随机动画。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.base_client import ChatMessage
from app.services.ai.db_config import chat_with_config
from app.services.rag import study_map_service

MAX_TRACE_STEPS = 6
MAX_ADVICE_PHASES = 4
MAX_ADVICE_SUGGESTIONS = 6

_EDGE_PRIORITY = {
    "prerequisite": 0,
    "mention": 1,
    "related": 2,
    "part_of": 3,
    "contrast": 4,
    "question_source": 5,
    "source_doc": 6,
    "reference": 7,
    "image_source": 8,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _stable_id(payload: Dict[str, Any], prefix: str) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _pick_seed(nodes: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not nodes:
        return None
    topics = [n for n in nodes if n.get("kind") == "topic"]
    banks = [n for n in nodes if n.get("kind") == "bank"]

    def topic_key(node: Dict[str, Any]) -> tuple:
        metrics = node.get("metrics") or {}
        learning = (node.get("detail") or {}).get("learning") or {}
        return (
            -_safe_int(metrics.get("weakCount")),
            _safe_int(learning.get("viewCount")),
            -_safe_int(metrics.get("degree")),
        )

    if topics:
        return sorted(topics, key=topic_key)[0]
    if banks:
        return sorted(banks, key=lambda n: -_safe_int((n.get("metrics") or {}).get("weakCount")))[0]
    return nodes[0]


def _build_adjacency(edges: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    adjacency: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append({**edge, "_next": target, "_reverse": False})
        adjacency.setdefault(target, []).append({**edge, "_next": source, "_reverse": True})
    for items in adjacency.values():
        items.sort(key=lambda e: (_EDGE_PRIORITY.get(str(e.get("kind") or ""), 9), -_safe_int(e.get("weight"))))
    return adjacency


def _trace_from_graph(
    graph: Dict[str, Any],
    *,
    seed_node_id: str = "",
) -> Dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    by_id = {str(node["id"]): node for node in nodes}
    seed = by_id.get(seed_node_id) if seed_node_id else None
    if seed is None:
        seed = _pick_seed(nodes)
    if seed is None:
        return {
            "traceId": "tr:empty",
            "seedNodeId": "",
            "steps": [],
            "visitedNodeIds": [],
            "degraded": {"singleNode": True, "noEdges": True},
        }

    seed_id = str(seed["id"])
    adjacency = _build_adjacency(edges)
    visited: List[str] = [seed_id]
    seen: Set[str] = {seed_id}
    steps: List[Dict[str, Any]] = []
    current = seed_id
    while len(steps) < MAX_TRACE_STEPS:
        candidates = [item for item in adjacency.get(current, []) if str(item["_next"]) not in seen]
        if not candidates:
            break
        edge = candidates[0]
        next_id = str(edge["_next"])
        reason = _step_reason(edge, by_id.get(next_id) or {})
        steps.append(
            {
                "index": len(steps) + 1,
                "from": current,
                "to": next_id,
                "edgeId": str(edge.get("id") or ""),
                "kind": str(edge.get("kind") or "related"),
                "label": str(edge.get("label") or "关联"),
                "reason": reason,
                "durationMs": 550,
                "direction": "in" if edge.get("_reverse") else "out",
            }
        )
        visited.append(next_id)
        seen.add(next_id)
        current = next_id

    trace_id = _stable_id(
        {"seed": seed_id, "steps": [(s["from"], s["to"], s["edgeId"]) for s in steps]},
        "tr",
    )
    return {
        "traceId": trace_id,
        "seedNodeId": seed_id,
        "steps": steps,
        "visitedNodeIds": visited,
        "degraded": {"singleNode": not steps, "noEdges": len(edges) == 0},
    }


def _step_reason(edge: Dict[str, Any], node: Dict[str, Any]) -> str:
    label = str(edge.get("label") or "")
    kind = str(edge.get("kind") or "")
    title = str(node.get("title") or "这个节点")
    if kind == "prerequisite":
        return f"图谱里存在前置关系，先去理解「{title}」"
    if kind == "question_source":
        return f"这里有来自「{title}」的真实题目锚点，可以用题验证理解"
    if kind == "source_doc":
        return f"主题页的来源资料是「{title}」，可以从原文补充细节"
    if kind == "reference":
        return f"笔记/引用与「{title}」相连，适合作为补充材料"
    if kind == "image_source":
        return f"「{title}」里有图片资产，适合用图辅助理解"
    return f"沿着{label or '图谱关系'}继续看「{title}」"


def focus_graph(graph: Dict[str, Any], node_ids: Sequence[str]) -> Dict[str, Any]:
    """把图收窄到建议涉及的节点 + 1 跳邻居，用于“生成后自动重排/聚焦”。"""
    seed_ids = {str(item) for item in (node_ids or []) if str(item)}
    if not seed_ids:
        return graph
    keep = set(seed_ids)
    edges = list(graph.get("edges") or [])
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in seed_ids or target in seed_ids:
            if source:
                keep.add(source)
            if target:
                keep.add(target)
    nodes = [node for node in (graph.get("nodes") or []) if str(node.get("id")) in keep]
    kept_edges = [
        edge
        for edge in edges
        if str(edge.get("source")) in keep and str(edge.get("target")) in keep
    ]
    stats = {
        "topicCount": sum(1 for node in nodes if node.get("kind") == "topic"),
        "bankCount": sum(1 for node in nodes if node.get("kind") == "bank"),
        "documentCount": sum(1 for node in nodes if node.get("kind") == "document"),
        "webCount": sum(1 for node in nodes if node.get("kind") == "web"),
        "noteCount": sum(1 for node in nodes if node.get("kind") == "note"),
        "imageCount": sum(1 for node in nodes if node.get("kind") == "image"),
        "edgeCount": len(kept_edges),
        "weakQuestionCount": sum(
            int((node.get("metrics") or {}).get("weakCount") or 0)
            for node in nodes
            if node.get("kind") == "bank"
        ),
    }
    groups = []
    for group in graph.get("groups") or []:
        group_ids = [str(item) for item in (group.get("nodeIds") or []) if str(item) in keep]
        if group_ids:
            groups.append({**group, "nodeIds": group_ids})
    return {
        **graph,
        "nodes": nodes,
        "edges": kept_edges,
        "groups": groups,
        "stats": stats,
    }


def _facts_from_graph(
    graph: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    by_id = {str(node["id"]): node for node in nodes}
    visited = [by_id[item] for item in trace.get("visitedNodeIds") or [] if item in by_id]
    return {
        "seed": next((n for n in visited if str(n["id"]) == str(trace.get("seedNodeId"))), None),
        "visitedNodes": visited,
        "nodes": [
            {
                "id": node["id"],
                "kind": node.get("kind"),
                "title": node.get("title"),
                "metrics": node.get("metrics") or {},
                "detail": {
                    "summary": (node.get("detail") or {}).get("summary", ""),
                    "pageType": (node.get("detail") or {}).get("pageType", ""),
                },
            }
            for node in nodes
        ],
        "edges": list(graph.get("edges") or []),
        "stats": dict(graph.get("stats") or {}),
        "degraded": dict(graph.get("degraded") or {}),
        **(extra or {}),
    }


def build_template_advice(
    facts: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    instruction: str = "",
) -> Dict[str, Any]:
    visited = list(facts.get("visitedNodes") or [])
    seed = facts.get("seed") or (visited[0] if visited else None)
    stats = facts.get("stats") or {}
    if not seed:
        return {
            "title": "暂时没有足够的图谱信息",
            "summary": "这份范围里还没有可用的知识节点；先导入资料或建立题库后再生成建议。",
            "scope": {"nodeIds": [], "seedNodeId": ""},
            "phases": [],
            "suggestions": [],
            "alternatives": [],
            "risks": ["当前没有真实节点，系统不会用假数据凑一份建议。"],
            "degraded": {**(facts.get("degraded") or {}), "llmFallback": True},
        }

    seed_title = str(seed.get("title") or "这个主题")
    visited_titles = [str(node.get("title") or "") for node in visited if node.get("title")]
    phase_nodes = [str(node["id"]) for node in visited[:3]]
    suggestions = [
        {
            "nodeId": str(node["id"]),
            "title": str(node.get("title") or ""),
            "kind": str(node.get("kind") or ""),
            "why": _step_reason(
                next((edge for edge in facts.get("edges") or [] if str(edge.get("target")) == str(node["id"]) or str(edge.get("source")) == str(node["id"])), {}),
                node,
            ),
            "estimatedMinutes": 25,
        }
        for node in visited[:MAX_ADVICE_SUGGESTIONS]
    ]
    phases = [
        {
            "id": "phase:foundation",
            "title": "先把关键信息理清",
            "goal": f"围绕「{seed_title}」梳理重点、前置依赖和可执行步骤",
            "estimatedMinutes": max(20, min(120, 25 * max(1, len(visited)))),
            "nodeIds": phase_nodes,
            "reason": f"这次从「{seed_title}」出发，沿真实关联访问了 {max(0, len(visited) - 1)} 个相关内容。",
            "evidence": [{"edgeId": step.get("edgeId"), "type": step.get("kind")} for step in trace.get("steps") or []],
        }
    ]
    if stats.get("bankCount"):
        phases.append(
            {
                "id": "phase:practice",
                "title": "用题库验证",
                "goal": "用真实题库中的薄弱题检验理解，而不是只看懂",
                "estimatedMinutes": 35,
                "nodeIds": [
                    str(node["id"])
                    for node in facts.get("visitedNodes") or []
                    if node.get("kind") == "bank"
                ],
                "reason": f"当前范围有 {stats.get('bankCount')} 个题库、{stats.get('weakQuestionCount', 0)} 道薄弱题。",
                "evidence": [{"table": "question_source"}],
            }
        )
    return {
        "title": f"围绕「{seed_title}」的规划建议",
        "summary": (
            f"围绕「{seed_title}」，建议先梳理 {len(visited_titles[:3])} 个关键内容"
            + (f"，再用题库验证" if stats.get("bankCount") else "")
            + "。这是一份可调整的规划建议，不是任务清单。"
        ),
        "scope": {
            "kbId": _safe_int(facts.get("kbId")),
            "bankIds": [int(x) for x in (facts.get("bankIds") or [])],
            "seedNodeId": str(seed.get("id") or ""),
            "nodeIds": [str(node["id"]) for node in visited],
        },
        "phases": phases,
        "suggestions": suggestions,
        "alternatives": [
            {
                "title": "如果时间更紧",
                "summary": "先保留种子节点，直接用一个题库的薄弱题定位问题。",
                "tradeoff": "可能缺少前置理解，适合已有基础的人。",
            }
        ],
        "risks": [
            "没有真实图谱关系的节点不会被硬连；建议里只保留可解释的关系。",
        ],
        "degraded": {**(facts.get("degraded") or {}), "llmFallback": True},
        "generatedAt": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }


def _strip_json_fence(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    return value


def _humanize_advice_text(value: Any, title_map: Dict[str, str]) -> str:
    """Remove internal graph vocabulary from user-facing advice text."""
    text = str(value or "").strip()
    if not text:
        return ""

    def topic_title(match: re.Match) -> str:
        return title_map.get(match.group(0), "相关主题")

    # 去掉「标题（topic:xx）」里的重复括号 ID。
    text = re.sub(r"[（(]\s*topic:\d+\s*[）)]", "", text)
    text = re.sub(r"[（(]\s*(?:doc|bank):\d+\s*[）)]", "", text)
    text = re.sub(r"\btopic:\d+\b", topic_title, text)
    text = re.sub(r"\bdoc:\d+\b", "来源资料", text)
    text = re.sub(r"题库\s*bank:\d+", "题库", text)
    text = re.sub(r"\bbank:\d+\b", "题库", text)
    text = re.sub(r"\bpageId\s*=\s*\d+", "", text)
    text = re.sub(r"\bdegree\s*为\s*0", "关联较少", text)
    text = re.sub(r"\bdegree\s*为\s*(\d+)", r"关联数 \1", text)
    text = re.sub(r"\bviewCount\s*为\s*0", "暂无阅读", text)
    text = re.sub(r"\bviewCount\s*为\s*(\d+)", r"阅读次数 \1", text)
    text = re.sub(r"\bpracticeCount\s*为\s*0", "暂无练习", text)
    text = re.sub(r"\bpracticeCount\s*为\s*(\d+)", r"练习次数 \1", text)
    text = re.sub(r"\bmappedQuestionCount\s*为\s*0", "暂无对应题目", text)
    text = re.sub(r"\bmappedQuestionCount\b", "题目对应", text)
    text = re.sub(r"\bviewCount\b", "阅读次数", text)
    text = re.sub(r"\bpracticeCount\b", "练习次数", text)
    text = re.sub(r"\bdegree\b", "关联数", text)
    text = re.sub(r"\bquestionCount\b", "题目数量", text)
    text = re.sub(r"\bestimatedMinutes\b", "预计时长", text)
    text = re.sub(r"\bnodeId\b", "节点", text)
    text = re.sub(r"\bedgeId\b", "关系", text)
    text = re.sub(r"\bmention\b", "主题关系", text)
    text = re.sub(r"\bprerequisite\b", "前置关系", text)
    text = re.sub(r"\bpart_of\b", "归属关系", text)
    text = re.sub(r"\bsource_doc\b", "来源资料", text)
    text = re.sub(r"\bquestion_source\b", "题源关系", text)
    text = re.sub(r"\brelated\b", "相关关系", text)
    text = re.sub(r"\bcontrast\b", "对比关系", text)
    text = text.replace("但其 暂无对应题目", "但题目暂未对应")
    text = text.replace("其 暂无对应题目", "题目暂未对应")
    text = text.replace("无对应关系", "暂无对应关系")
    text = text.replace("节点 关联数", "节点关联数")
    text = text.replace("的 练习次数", "的练习次数")
    text = text.replace("的 预计时长", "的预计时长")
    text = text.replace("主题关系 关系", "主题关系")
    text = text.replace("前置关系 关系", "前置关系")
    text = text.replace("归属关系 关系", "归属关系")
    text = text.replace("练习次数 均为", "练习次数均为")
    text = text.replace("预计时长 仅", "预计时长仅")
    text = re.sub(r"(\d+)\s*条边", r"\1 条关联", text)
    text = text.replace("题库节点", "题库").replace("主题节点", "主题")
    text = re.sub(r"无直接映射|没有直接映射", "暂无对应题", text)
    text = re.sub(r"映射", "对应", text)
    text = re.sub(r"题库\s*有\s*\d+\s*道薄弱题(?:、题库\s*有\s*\d+\s*道)+", "题库还有一批薄弱题", text)
    text = text.replace("暂无对应题（暂无对应题目）", "暂无对应题目")
    text = text.replace("来源资料 原文", "来源资料原文")
    text = re.sub(r"以\s+来源资料原文", "以来源资料原文", text)
    text = re.sub(r"，除来源资料外缺少其他关联，其评分框架细节需以来源资料原文为准", "，评分框架细节需以来源资料原文为准", text)
    text = re.sub(r"题库\s+有", "题库有", text)
    text = re.sub(r"阅读次数\s+均为", "阅读次数均为", text)
    text = re.sub(r"在图中还有.*?等其他关联主题未在轨迹中出现，本建议未对其展开。", "还有几个关联主题未覆盖，本建议暂不展开。", text)
    text = re.sub(r"本次轨迹仅覆盖\s*(\d+)\s*个主题节点", r"本次只覆盖 \1 个主题", text)
    # 中文之间的排版空格去掉，读起来更紧凑自然。
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_advice(
    raw: Dict[str, Any],
    facts: Dict[str, Any],
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    node_ids = {str(node["id"]) for node in facts.get("nodes") or []}
    edge_ids = {str(edge.get("id")) for edge in facts.get("edges") or [] if edge.get("id")}
    title_map = {str(node.get("id")): str(node.get("title") or "") for node in facts.get("nodes") or []}
    template = build_template_advice(facts, trace)

    def clean_text(value: Any, fallback: str = "") -> str:
        text = _humanize_advice_text(value, title_map)
        return text or _humanize_advice_text(fallback, title_map)

    def clean_node_ids(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        return [str(item) for item in values if str(item) in node_ids]

    phases: List[Dict[str, Any]] = []
    for index, item in enumerate(raw.get("phases") or []):
        if not isinstance(item, dict):
            continue
        phase_nodes = clean_node_ids(item.get("nodeIds"))
        if not phase_nodes:
            continue
        evidence = []
        for ev in item.get("evidence") or []:
            if isinstance(ev, dict):
                edge_id = str(ev.get("edgeId") or "")
                if not edge_id or edge_id in edge_ids:
                    evidence.append(ev)
        phases.append(
            {
                "id": clean_text(item.get("id"), f"phase:{index + 1}"),
                "title": clean_text(item.get("title"), f"阶段 {index + 1}"),
                "goal": clean_text(item.get("goal")),
                "estimatedMinutes": max(5, _safe_int(item.get("estimatedMinutes"), 25)),
                "nodeIds": phase_nodes[:6],
                "reason": clean_text(item.get("reason")),
                "evidence": evidence[:6],
            }
        )
    suggestions: List[Dict[str, Any]] = []
    for item in raw.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("nodeId") or "")
        if node_id not in node_ids:
            continue
        node = next((n for n in facts.get("nodes") or [] if str(n["id"]) == node_id), {})
        suggestions.append(
            {
                "nodeId": node_id,
                "title": clean_text(item.get("title"), str(node.get("title") or "")),
                "kind": clean_text(item.get("kind"), str(node.get("kind") or "")),
                "why": clean_text(item.get("why")),
                "estimatedMinutes": max(1, _safe_int(item.get("estimatedMinutes"), 20)),
            }
        )
        if len(suggestions) >= MAX_ADVICE_SUGGESTIONS:
            break
    if not phases:
        phases = list(template.get("phases") or [])
    if not suggestions:
        suggestions = list(template.get("suggestions") or [])
    alternatives = []
    for item in raw.get("alternatives") or []:
        if isinstance(item, dict):
            alternatives.append(
                {
                    "title": clean_text(item.get("title"), "另一种选择"),
                    "summary": clean_text(item.get("summary")),
                    "tradeoff": clean_text(item.get("tradeoff")),
                }
            )
    return {
        "title": clean_text(raw.get("title"), str(template.get("title") or "")),
        "summary": clean_text(raw.get("summary"), str(template.get("summary") or "")),
        "scope": template.get("scope") or {},
        "phases": phases[:MAX_ADVICE_PHASES],
        "suggestions": suggestions,
        "alternatives": alternatives or template.get("alternatives") or [],
        "risks": [
            _humanize_advice_text(x, title_map)
            for x in (raw.get("risks") or [])
            if str(x).strip()
        ]
        or template.get("risks")
        or [],
        "degraded": {**(facts.get("degraded") or {}), "llmFallback": False},
        "generatedAt": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }


def _build_prompt(facts: Dict[str, Any], trace: Dict[str, Any], instruction: str) -> str:
    compact_nodes = []
    for node in facts.get("nodes") or []:
        if str(node["id"]) in {str(x) for x in trace.get("visitedNodeIds") or []} or node.get("kind") == "bank":
            compact_nodes.append(
                {
                    "id": node["id"],
                    "kind": node.get("kind"),
                    "title": node.get("title"),
                    "summary": (node.get("detail") or {}).get("summary", ""),
                    "metrics": node.get("metrics") or {},
                }
            )
    allowed_edges = [
        {"id": edge.get("id"), "source": edge.get("source"), "target": edge.get("target"), "kind": edge.get("kind")}
        for edge in facts.get("edges") or []
        if edge.get("id")
    ]
    payload = {
        "task": "请基于用户提供的真实内容（可能是比赛通知、活动信息、资料分析、学习材料、工作文档等）写一份可调整的规划建议。先判断内容类型和用户目标，再给阶段；只解释，不发明节点或关系。",
        "seedNodeId": trace.get("seedNodeId"),
        "trace": trace,
        "nodes": compact_nodes[:30],
        "edges": allowed_edges[:40],
        "stats": facts.get("stats") or {},
        "userInstruction": instruction or "没有额外要求。",
        "outputSchema": {
            "title": "一句话标题，必须体现内容类型（如比赛、资料分析、学习材料）",
            "summary": "一到两句结论，尽量 50 字以内，用中文自然表达",
            "phases": [
                {
                    "id": "phase:foundation",
                    "title": "阶段名",
                    "goal": "阶段目标，30 字以内",
                    "estimatedMinutes": 30,
                    "nodeIds": ["只能使用 nodes 里的 id"],
                    "reason": "一句话依据，最多 60 字",
                    "evidence": [{"edgeId": "只能使用 edges 里的 id", "type": "prerequisite"}],
                }
            ],
            "suggestions": [
                {"nodeId": "只能使用 nodes 里的 id", "title": "节点标题", "kind": "topic/bank/...", "why": "一句话为什么，最多 40 字", "estimatedMinutes": 20}
            ],
            "alternatives": [{"title": "替代路径", "summary": "替代方案", "tradeoff": "取舍"}],
            "risks": ["一条结论，最多 35 字"],
        },
        "fewShotExamples": [
            {
                "contentType": "比赛通知",
                "sampleInput": "华为比赛报名信息，包含报名截止时间、参赛资格、需要提交的材料。",
                "goodTitle": "华为比赛报名与备赛规划",
                "goodSummary": "先确认报名资格和截止时间，再准备参赛材料并安排赛前演练。",
                "goodPhaseTitles": ["确认报名条件", "准备参赛材料", "赛前演练与提交"],
                "goodRisk": "报名截止时间固定，错过无法补报。"
            },
            {
                "contentType": "资料分析",
                "sampleInput": "一份行业分析报告，用户想快速看懂结论、关键数据和可执行方向。",
                "goodTitle": "行业报告阅读与结论提炼",
                "goodSummary": "先看结论和统计口径，再核对关键数据，最后整理可执行建议。",
                "goodPhaseTitles": ["读结论与范围", "核对数据口径", "提炼行动建议"],
                "goodRisk": "报告数据口径不统一时，结论只能作为参考。"
            }
        ],
        "rules": [
            "不要输出 tasks/days/status/done/progress/todayTasks。",
            "不要出现“你今天必须/完成后/已为你安排任务”这类命令式措辞。",
            "先识别内容类型：比赛/活动/通知、资料分析、学习材料、工作文档；不要把所有内容都写成课程学习。",
            "标题和阶段必须贴合内容类型：比赛写报名、材料、演练、提交；资料分析写结论、口径、数据、行动；只有学习材料才写知识点和练习。",
            "不要新增 nodes 之外的 nodeId，不要新增 edges 之外的 edgeId。",
            "所有面向用户的文字必须用中文自然表达；不要出现 topic:/doc:/bank: 等内部 ID，也不要出现 degree/viewCount/practiceCount/mappedQuestionCount/edgeId/nodeId 等字段名。",
            "把内部数据翻译成用户能懂的话：例如「关联较少」「暂无阅读」「暂无练习」「题目暂未对应」。",
            "每条风险尽量控制在 35 个汉字以内，只说结论和影响，不展开技术细节。",
            "没有真实依据就写“暂无足够依据”，不要编造。",
            "只输出一个 JSON 对象，不要代码围栏，不要解释文字。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def generate_advice(
    db: AsyncSession,
    *,
    facts: Dict[str, Any],
    trace: Dict[str, Any],
    instruction: str = "",
    use_llm: bool = True,
) -> Dict[str, Any]:
    if not use_llm:
        return build_template_advice(facts, trace, instruction=instruction)
    try:
        prompt = _build_prompt(facts, trace, instruction)
        response = await chat_with_config(
            db,
            [ChatMessage(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=3500,
            thinking=False,
        )
        raw = json.loads(_strip_json_fence(response.content or ""))
        if not isinstance(raw, dict):
            raise ValueError("建议不是 JSON 对象")
        return _normalize_advice(raw, facts, trace)
    except Exception:
        return build_template_advice(facts, trace, instruction=instruction)


async def prepare_trace(
    db: AsyncSession,
    user_id: int,
    *,
    kb_id: int = 0,
    bank_ids: Optional[Sequence[int]] = None,
    source_types: Optional[Iterable[str] | str] = None,
    seed_node_id: str = "",
    goal: str = "weakness",
    daily_minutes: int = 30,
    horizon_days: int = 14,
    instruction: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    graph = await study_map_service.build_study_map(
        db,
        int(user_id),
        kb_id=int(kb_id or 0),
        bank_ids=bank_ids,
        source_types=source_types,
        seed_node_id=seed_node_id,
        depth=2,
        limit=80,
        now=now,
    )
    trace = _trace_from_graph(graph, seed_node_id=seed_node_id)
    facts = _facts_from_graph(
        graph,
        trace,
        extra={
            "kbId": int(kb_id or 0),
            "bankIds": [int(x) for x in (bank_ids or []) if _safe_int(x) > 0],
            "goal": goal,
            "dailyMinutes": int(daily_minutes or 30),
            "horizonDays": int(horizon_days or 14),
            "instruction": instruction,
        },
    )
    return {"trace": trace, "facts": facts, "graph": graph}


__all__ = [
    "prepare_trace",
    "generate_advice",
    "build_template_advice",
    "focus_graph",
    "MAX_TRACE_STEPS",
]
