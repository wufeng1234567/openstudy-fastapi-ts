"""学习处方：把一份资料排成可执行、可复诊的按天学习计划。

和「资料装配」的区别：
  · 装配交付的是一份静态文件；
  · 处方交付的是接下来每天做什么：读哪一节、练几道题、何时复习、哪里补强。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Tuple

GOAL_LABELS: Dict[str, str] = {
    "foundation": "打基础",
    "exam": "考前冲刺",
    "weakness": "先补薄弱章节",
}

GOAL_GUIDES: Dict[str, str] = {
    "foundation": "先保证讲解被读懂，再进入练习；每天安排少量新章节，留出回顾时间。",
    "exam": "按考试优先级推进，尽快进入练习与错题回顾；把高覆盖章节放在前面。",
    "weakness": "优先安排内容过薄、缺少练习、覆盖不足的章节，先补短板再扩展。",
}

TASK_TYPES = {"read", "practice", "review", "recheck"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _meaningful_sections(report: Dict[str, Any], section_indexes: Iterable[int] | None) -> List[Dict[str, Any]]:
    sections = [s for s in (report.get("sections") or []) if isinstance(s, dict)]
    wanted = {_safe_int(x, -1) for x in (section_indexes or [])}
    if wanted:
        return [s for s in sections if _safe_int(s.get("index"), -1) in wanted]
    meaningful = [s for s in sections if str(s.get("title") or "") != "开篇"]
    return meaningful or sections


def baseline_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "score": report.get("score"),
        "grade": report.get("grade"),
        "issueCount": len(report.get("issues") or []),
        "sectionCount": len(report.get("sections") or []),
        "metrics": report.get("metrics") or [],
    }


def build_prescription_prompt(
    *,
    doc_name: str,
    report: Dict[str, Any],
    days: int,
    daily_minutes: int,
    goal: str,
    section_indexes: Iterable[int] | None = None,
    instruction: str = "",
) -> Tuple[str, List[Dict[str, Any]]]:
    """组装学习处方生成任务，返回 (prompt, selected_sections)。"""
    selected = _meaningful_sections(report, section_indexes)
    if not selected:
        raise ValueError("没有可排入学习处方的章节")

    goal_key = (goal or "exam").strip().lower()
    if goal_key not in GOAL_LABELS:
        goal_key = "exam"
    extra = (instruction or "").strip() or "没有额外要求。"

    section_lines = []
    for s in selected:
        section_lines.append(
            "- 章节 index={index}，标题《{title}》，{chars} 字，"
            "{questions} 道题，{images} 张图，覆盖状态：{coverage}".format(
                index=_safe_int(s.get("index"), -1),
                title=str(s.get("title") or "未命名章节"),
                chars=_safe_int(s.get("chars"), 0),
                questions=_safe_int(s.get("questions"), 0),
                images=_safe_int(s.get("images"), 0),
                coverage=str(s.get("coverageLabel") or s.get("coverage") or "未知"),
            )
        )

    prompt = f"""请为下面这份资料设计一份{int(days)}天的学习处方。

资料名称：{doc_name or '未命名资料'}
学习目标：{GOAL_LABELS[goal_key]}
每天可用时间：约 {int(daily_minutes)} 分钟
用户额外要求：{extra}

【资料体检基线】
综合分：{report.get('score')}
待处理问题：{len(report.get('issues') or [])} 项
章节情况：
{chr(10).join(section_lines)}

【排布规则】
1. 覆盖上面列出的每一个章节，不要漏掉章节；章节用 sectionIndex 引用，不要虚构章节。
2. 每天的学习任务总时长不超过约 {int(daily_minutes)} 分钟；任务类型只能是 read（精读/理解）、practice（练习）、review（回忆/复习）、recheck（复测/检查）。
3. 每天要有明确主题；先读后练，练完安排复习；内容过薄或缺少练习的章节优先安排补强。
4. 任务描述要具体到“读哪一节、做什么、为什么”，不要写空泛的“复习本章”。
5. 只能依据资料体检信息排计划，不要编造资料没有的章节或题目数量。
6. 只输出一个 JSON 对象，不要代码围栏、不要解释文字。

【输出 JSON 结构】
{{
  "title": "资料名 · 学习处方",
  "summary": "一句话说明这份处方怎么用",
  "days": [
    {{
      "day": 1,
      "theme": "今天的主题",
      "minutes": 25,
      "tasks": [
        {{
          "type": "read",
          "title": "任务标题",
          "detail": "具体做什么、为什么这么做",
          "sectionIndex": 1,
          "sectionTitle": "对应章节标题",
          "minutes": 8,
          "questionCount": 0
        }}
      ]
    }}
  ],
  "checkpoints": ["第3天：检查...", "第7天：复诊..."]
}}
"""
    return prompt, selected


def _strip_json_fence(text: str) -> str:
    value = (text or "").strip()
    # 兼容 chat_engine 的深度思考包裹标记（正常 thinking=False 不会出现，防御性处理）。
    value = re.sub(r"\x1e@@THINK@@[\s\S]*?\x1e", "", value)
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return value[start:end + 1]
    return value


def parse_prescription(text: str, *, selected_sections: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    """解析并校验 LLM 返回的 JSON，失败直接报错，不用算法凑一份假计划。"""
    payload = json.loads(_strip_json_fence(text))
    if not isinstance(payload, dict):
        raise ValueError("学习处方不是 JSON 对象")
    raw_days = payload.get("days")
    if not isinstance(raw_days, list) or not raw_days:
        raise ValueError("学习处方没有生成任何一天的任务")

    by_index = {_safe_int(s.get("index"), -1): s for s in selected_sections}
    clean_days: List[Dict[str, Any]] = []
    for day_index, day in enumerate(raw_days, start=1):
        if not isinstance(day, dict):
            continue
        tasks = day.get("tasks")
        if not isinstance(tasks, list):
            tasks = []
        clean_tasks: List[Dict[str, Any]] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_type = str(task.get("type") or "read").strip().lower()
            if task_type not in TASK_TYPES:
                task_type = "read"
            section_index = _safe_int(task.get("sectionIndex"), -1)
            section = by_index.get(section_index)
            if section is None:
                # 模型有时会漏 sectionIndex，用章节标题兜底匹配，仍然只认已选章节。
                by_title = {
                    str(s.get("title") or "").strip(): s for s in selected_sections
                }
                section = by_title.get(str(task.get("sectionTitle") or "").strip())
            if section is None:
                continue
            clean_tasks.append(
                {
                    "type": task_type,
                    "title": str(task.get("title") or "学习任务").strip(),
                    "detail": str(task.get("detail") or "").strip(),
                    "sectionIndex": _safe_int(section.get("index"), -1),
                    "sectionTitle": str(section.get("title") or "").strip(),
                    "minutes": max(1, _safe_int(task.get("minutes"), 10)),
                    "questionCount": max(0, _safe_int(task.get("questionCount"), 0)),
                }
            )
        if not clean_tasks:
            continue
        clean_days.append(
            {
                "day": day_index,
                "theme": str(day.get("theme") or f"第 {day_index} 天").strip(),
                "minutes": max(1, _safe_int(day.get("minutes"), 20)),
                "tasks": clean_tasks,
            }
        )

    if not clean_days:
        raise ValueError("学习处方没有可执行的任务")
    if len(clean_days) > max(1, int(days)):
        clean_days = clean_days[: int(days)]

    return {
        "title": str(payload.get("title") or "学习处方").strip(),
        "summary": str(payload.get("summary") or "").strip(),
        "days": clean_days,
        "checkpoints": [
            str(x).strip()
            for x in (payload.get("checkpoints") or [])
            if str(x).strip()
        ],
    }


__all__ = [
    "GOAL_LABELS",
    "GOAL_GUIDES",
    "baseline_from_report",
    "build_prescription_prompt",
    "parse_prescription",
]
