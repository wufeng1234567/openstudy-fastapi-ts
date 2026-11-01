"""学习统计的轻量图表协议。

这里只把**已经算好的统计数据**整理成前端可直接渲染的 chart spec，不查库、不调
模型、不生成任何新数字。前端 `LearningChart` 负责把它变成 ECharts option。

spec 形状（稳定契约）::

    {
      "kind": "line" | "bar",
      "title": "最近 7 天学习趋势",
      "subtitle": "练习总量 / 答对 / 答错",
      "xAxis": ["10-25", ...],
      "series": [{"name": "练习总量", "data": [1, 2], "color": "#409eff"}],
      "yAxisName": "次"
    }

图表类型由工具的 `chart_type` 参数决定；`auto` 由每种统计选择默认类型。
"""

from __future__ import annotations

from typing import Any, Iterable, Optional


def chart_kind(requested: Any, default: str = "line") -> str:
    value = str(requested or "auto").strip().lower()
    if value in ("line", "bar"):
        return value
    return default


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _series(name: str, values: Iterable[Any], color: str) -> dict[str, Any]:
    return {"name": name, "data": [_number(v) for v in values], "color": color}


def build_overview_chart(data: dict, requested: Any = "auto") -> Optional[dict]:
    items = [
        ("收藏题目", _number(data.get("totalQuestions")), "#409eff"),
        ("错题", _number(data.get("totalErrors")), "#f56c6c"),
        ("斩题", _number(data.get("totalMarked")), "#e6a23c"),
        ("练习", _number(data.get("totalPracticeCount")), "#67c23a"),
    ]
    if not any(value for _, value, _ in items):
        return None
    # 总览的四个数字量级差异可能很大，但作为一眼概览仍比纯文字直观。
    return {
        "kind": chart_kind(requested, "bar"),
        "title": "学习总览",
        "subtitle": "收藏 / 错题 / 斩题 / 练习次数",
        "xAxis": [name for name, _, _ in items],
        "series": [
            {
                "name": "数量",
                "data": [value for _, value, _ in items],
                "color": "#409eff",
            }
        ],
        "yAxisName": "数量",
    }


def build_trend_chart(rows: list[dict], requested: Any = "auto") -> Optional[dict]:
    if not rows:
        return None
    return {
        "kind": chart_kind(requested, "line"),
        "title": f"最近 {len(rows)} 天学习趋势",
        "subtitle": "练习总量 / 答对 / 答错 / 斩题",
        "xAxis": [str(row.get("date") or "")[5:] for row in rows],
        "series": [
            _series("练习总量", [row.get("practiceCount") for row in rows], "#409eff"),
            _series("答对", [row.get("correctCount") for row in rows], "#67c23a"),
            _series("答错", [row.get("errorCount") for row in rows], "#f56c6c"),
            _series("斩题", [row.get("markedCount") for row in rows], "#e6a23c"),
        ],
        "yAxisName": "次",
    }


def build_subject_chart(rows: list[dict], requested: Any = "auto") -> Optional[dict]:
    if not rows:
        return None
    has_value = any(
        _number(row.get("bankCount"))
        or _number(row.get("questionCount"))
        or _number(row.get("errorCount"))
        or _number(row.get("markedCount"))
        for row in rows
    )
    if not has_value:
        return None
    return {
        "kind": chart_kind(requested, "bar"),
        "title": "各科目学习分布",
        "subtitle": "收藏题目 / 错题 / 斩题",
        "xAxis": [str(row.get("subject") or "未分类") for row in rows],
        "series": [
            _series("收藏题目", [row.get("questionCount") for row in rows], "#409eff"),
            _series("错题", [row.get("errorCount") for row in rows], "#f56c6c"),
            _series("斩题", [row.get("markedCount") for row in rows], "#e6a23c"),
        ],
        "yAxisName": "道",
    }


def build_error_chart(data: dict, requested: Any = "auto") -> Optional[dict]:
    rows = data.get("byDifficulty") or []
    if not rows:
        return None
    labels = {1: "简单", 2: "中等", 3: "困难"}
    ordered = sorted(rows, key=lambda row: _number(row.get("difficulty")))
    return {
        "kind": chart_kind(requested, "bar"),
        "title": "错题难度分布",
        "subtitle": "按难度统计当前错题",
        "xAxis": [labels.get(_number(row.get("difficulty")), f"难度{_number(row.get('difficulty'))}") for row in ordered],
        "series": [_series("错题数", [row.get("count") for row in ordered], "#f56c6c")],
        "yAxisName": "道",
    }


def build_diagnose_chart(diagnosis: dict, requested: Any = "auto") -> Optional[dict]:
    activity = diagnosis.get("activity") or {}
    rows = activity.get("daily") or []
    if not rows:
        return None
    return {
        "kind": chart_kind(requested, "line"),
        "title": f"最近 {activity.get('windowDays') or len(rows)} 天学习活动",
        "subtitle": "练习总量 / 答对次数",
        "xAxis": [str(row.get("date") or "")[5:] for row in rows],
        "series": [
            _series("练习总量", [row.get("practiceCount") for row in rows], "#409eff"),
            _series("答对", [row.get("correctCount") for row in rows], "#67c23a"),
        ],
        "yAxisName": "次",
    }
