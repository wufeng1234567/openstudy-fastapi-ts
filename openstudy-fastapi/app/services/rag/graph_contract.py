"""图谱节点/边的最小共享契约。

当前仓库仍有 `knowledge_map_service` / `knowledge_graph_service` /
`study_graph_service` / `study_map_service` 四套实现；本模块先统一
节点/边字段与边 ID 生成规则，后续再逐步把旧服务迁到同一契约。
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Set, TypedDict


class GraphNode(TypedDict, total=False):
    id: str
    kind: str
    title: str
    subtitle: str
    metrics: Dict[str, Any]
    evidence: Dict[str, Any]


class GraphEdge(TypedDict, total=False):
    id: str
    source: str
    target: str
    kind: str
    label: str
    weight: int
    evidence: Dict[str, Any]


def stable_edge_id(kind: str, source: str, target: str) -> str:
    """边 ID 由 source/target/kind 派生，跨请求稳定。"""
    digest = hashlib.sha1(f"{source}->{target}".encode("utf-8")).hexdigest()[:16]
    return f"e:{kind}:{digest}"


def add_edge(
    edges: List[GraphEdge],
    seen: Set[tuple],
    *,
    source: str,
    target: str,
    kind: str,
    label: str,
    weight: int = 5,
    evidence: Dict[str, Any] | None = None,
) -> None:
    """按统一契约追加一条去重边；空节点/自环直接忽略。"""
    if not source or not target or source == target:
        return
    key = (source, target, kind)
    if key in seen:
        return
    seen.add(key)
    edges.append(
        {
            "id": stable_edge_id(kind, source, target),
            "source": source,
            "target": target,
            "kind": kind,
            "label": label,
            "weight": int(weight or 5),
            "evidence": evidence or {},
        }
    )


__all__ = ["GraphNode", "GraphEdge", "stable_edge_id", "add_edge"]
