"""资料智能报告：基于资料体检事实，告诉用户“这份资料可以哪里做得更好”。

不排任务、不勾完成；只输出更新目标、优势、改进项和下一步建议。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

MAX_IMPROVEMENTS = 6


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _strip_json_fence(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    return value


def _section_refs(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = [s for s in (report.get("sections") or []) if isinstance(s, dict)]
    return [
        {
            "index": _safe_int(s.get("index"), -1),
            "title": str(s.get("title") or "未命名章节"),
            "coverage": str(s.get("coverage") or ""),
            "chars": _safe_int(s.get("chars")),
            "questions": _safe_int(s.get("questions")),
            "images": _safe_int(s.get("images")),
            "start": _safe_int(s.get("start")),
        }
        for s in sections
        if _safe_int(s.get("index"), -1) >= 0
    ]


def build_smart_report_prompt(
    *,
    doc_name: str,
    report: Dict[str, Any],
    instruction: str = "",
) -> str:
    sections = _section_refs(report)
    issues = [
        {
            "severity": str(item.get("severity") or ""),
            "title": str(item.get("title") or ""),
            "detail": str(item.get("detail") or ""),
            "sectionTitle": str(item.get("sectionTitle") or ""),
            "fixAction": str(item.get("fixAction") or ""),
        }
        for item in (report.get("issues") or [])[:8]
        if isinstance(item, dict)
    ]
    metrics = [
        {
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "score": _safe_int(item.get("score")),
            "detail": str(item.get("detail") or ""),
        }
        for item in (report.get("metrics") or [])
        if isinstance(item, dict)
    ]
    payload = {
        "docName": doc_name,
        "score": _safe_int(report.get("score")),
        "grade": report.get("grade") or {},
        "stats": report.get("stats") or {},
        "metrics": metrics,
        "issues": issues,
        "sections": sections,
        "instruction": str(instruction or "").strip() or "没有额外要求。",
        "outputSchema": {
            "title": "《资料名》智能报告",
            "verdict": "一句话结论",
            "updateGoal": "这份资料下一步应该变成什么（一句话）",
            "strengths": ["已有优势"],
            "improvements": [
                {
                    "priority": "P0/P1/P2",
                    "sectionIndex": 1,
                    "sectionTitle": "章节标题",
                    "problem": "哪里不够好",
                    "action": "建议怎么改",
                    "evidence": "来自体检的真实依据",
                }
            ],
            "nextSteps": ["建议下一步"],
            "risks": ["风险或不确定点"],
        },
    }
    return (
        "请为下面这份资料写一份「智能报告」，帮助用户判断这份资料可以哪里做得更好。\n"
        "只依据给出的资料体检事实，不要编造章节、分数或题目数量。\n"
        "不要输出按天任务、checkbox、完成态或学习处方。\n"
        "improvements 必须引用 sections 里存在的 sectionIndex；不知道就省略 sectionIndex。\n"
        "只输出一个 JSON 对象，不要代码围栏，不要解释文字。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _clean_improvement(item: Dict[str, Any], sections: Dict[int, Dict[str, Any]], by_title: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    section_index = _safe_int(item.get("sectionIndex"), -1)
    section = sections.get(section_index) or by_title.get(str(item.get("sectionTitle") or "").strip())
    if not section:
        section_index = -1
        section_title = str(item.get("sectionTitle") or "").strip()
    else:
        section_index = _safe_int(section.get("index"), -1)
        section_title = str(section.get("title") or "")
    problem = _safe_text(item.get("problem"), 240)
    action = _safe_text(item.get("action"), 240)
    if not problem and not action:
        return None
    return {
        "priority": str(item.get("priority") or "P1").upper() if str(item.get("priority") or "").upper() in {"P0", "P1", "P2"} else "P1",
        "sectionIndex": section_index,
        "sectionTitle": section_title,
        "start": _safe_int((section or {}).get("start"), 0),
        "problem": problem,
        "action": action,
        "evidence": _safe_text(item.get("evidence"), 200),
    }


def normalize_smart_report(raw: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    section_list = _section_refs(report)
    sections = {item["index"]: item for item in section_list}
    by_title = {item["title"]: item for item in section_list}
    improvements: List[Dict[str, Any]] = []
    for item in raw.get("improvements") or []:
        if not isinstance(item, dict):
            continue
        cleaned = _clean_improvement(item, sections, by_title)
        if cleaned:
            improvements.append(cleaned)
        if len(improvements) >= MAX_IMPROVEMENTS:
            break
    if not improvements:
        improvements = build_template_report(report).get("improvements") or []
    return {
        "title": _safe_text(raw.get("title"), 120) or f"《{report.get('fileName') or '这份资料'}》智能报告",
        "verdict": _safe_text(raw.get("verdict"), 260),
        "updateGoal": _safe_text(raw.get("updateGoal"), 200),
        "strengths": [_safe_text(x, 160) for x in (raw.get("strengths") or []) if str(x).strip()][:6],
        "improvements": improvements,
        "nextSteps": [_safe_text(x, 160) for x in (raw.get("nextSteps") or []) if str(x).strip()][:6],
        "risks": [_safe_text(x, 160) for x in (raw.get("risks") or []) if str(x).strip()][:6],
        "score": _safe_int(report.get("score")),
        "grade": report.get("grade") or {},
        "generatedAt": __import__("datetime").datetime.now().isoformat(sep=" ", timespec="seconds"),
        "degraded": {"llmFallback": False},
    }


def build_template_report(report: Dict[str, Any]) -> Dict[str, Any]:
    issues = [item for item in (report.get("issues") or []) if isinstance(item, dict)]
    improvements: List[Dict[str, Any]] = []
    for item in issues[:MAX_IMPROVEMENTS]:
        improvements.append(
            {
                "priority": str(item.get("severity") or "P1").upper() if str(item.get("severity") or "").upper() in {"P0", "P1", "P2"} else "P1",
                "sectionIndex": _safe_int(item.get("sectionIndex"), -1),
                "sectionTitle": str(item.get("sectionTitle") or ""),
                "problem": _safe_text(item.get("title"), 160),
                "action": _safe_text(item.get("detail"), 200),
                "evidence": _safe_text(item.get("detail"), 180),
            }
        )
    if not improvements:
        improvements = [
            {
                "priority": "P2",
                "sectionIndex": -1,
                "sectionTitle": "",
                "problem": "资料结构基本可用，暂未发现必须处理的问题。",
                "action": "可以补充章节练习或图片说明，让它更适合学习。",
                "evidence": "体检未发现 P0/P1 问题",
            }
        ]
    lowest = sorted(
        [m for m in (report.get("metrics") or []) if isinstance(m, dict)],
        key=lambda m: _safe_int(m.get("score"), 100),
    )
    goal = (
        f"把「{lowest[0].get('label')}」补强到可学习水平"
        if lowest
        else "把这份资料整理成讲解—练习—复习闭环"
    )
    return {
        "title": f"《{report.get('fileName') or '这份资料'}》智能报告",
        "verdict": f"综合分 {report.get('score', '—')}，共 {len(issues)} 项待处理。",
        "updateGoal": goal,
        "strengths": [
            f"{report.get('stats', {}).get('sectionCount', 0)} 个章节",
            f"{report.get('stats', {}).get('wordCount', 0)} 字",
            f"{report.get('stats', {}).get('questionCount', 0)} 道题",
        ],
        "improvements": improvements,
        "nextSteps": ["先处理 P0/P1 问题", "再补章节练习与图片说明"],
        "risks": ["模板报告只依据体检规则，未调用模型。"],
        "score": _safe_int(report.get("score")),
        "grade": report.get("grade") or {},
        "generatedAt": __import__("datetime").datetime.now().isoformat(sep=" ", timespec="seconds"),
        "degraded": {"llmFallback": True},
    }


async def generate_smart_report(
    db,
    *,
    doc_name: str,
    report: Dict[str, Any],
    instruction: str = "",
    use_llm: bool = True,
) -> Dict[str, Any]:
    if not use_llm:
        return build_template_report({**report, "fileName": doc_name})
    try:
        from app.services.ai.base_client import ChatMessage
        from app.services.ai.db_config import chat_with_config

        prompt = build_smart_report_prompt(doc_name=doc_name, report=report, instruction=instruction)
        response = await chat_with_config(
            db,
            [ChatMessage(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=3000,
            thinking=False,
        )
        raw = json.loads(_strip_json_fence(response.content or ""))
        if not isinstance(raw, dict):
            raise ValueError("智能报告不是 JSON 对象")
        return normalize_smart_report({**raw, "fileName": doc_name}, {**report, "fileName": doc_name})
    except Exception:
        return build_template_report({**report, "fileName": doc_name})


__all__ = [
    "build_smart_report_prompt",
    "normalize_smart_report",
    "build_template_report",
    "generate_smart_report",
]
