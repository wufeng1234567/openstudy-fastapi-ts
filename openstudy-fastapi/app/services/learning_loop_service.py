"""学习闭环：今日处方、知识体检、错题歼灭战。

数据全部来自 `study_diagnosis_service.diagnose()` 的逐题诊断结果，不在这里重新
计算掌握度，也不调用模型。这样同一个用户同一天看到的计划、地图、歼灭进度是
确定性的，不会因为换一次对话而改变。

产物只服务于展示与导航，真正跳到题目/资料仍由前端完成：
· `todayPlan`  —— 最多 3 条今天最该做的事
· `healthMap`  —— 按科目聚合的体检节点 + 该科目最该处理的题（前端画关系图）
· `errorBattle` —— 错题歼灭三阶段：待攻克 / 观察期 / 已歼灭

⚠️ 练习流水刻意不设外键，题目被物理删除后流水还在。诊断结果里会出现
「题目内容已不可用」的占位条目 —— 这类题不能进处方、不能进体检图、更不能
进歼灭战，否则用户会看到一条点进去什么都没的「幽灵任务」。这里统一过滤。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_diagnosis_service as sds

ATTENTION_LEVELS = {"repeated_failure", "lapsing", "overdue", "due_soon"}
LEVEL_ORDER = {
    "repeated_failure": 0,
    "lapsing": 1,
    "overdue": 2,
    "due_soon": 3,
    "on_track": 4,
    "mastered": 5,
    "fresh": 6,
}
DELETED_PLACEHOLDER = "（题目内容已不可用，可能已被删除）"


def _is_available(item: Dict[str, Any]) -> bool:
    """题目是否还活着（能点开、能作答）"""
    text = str(item.get("questionText") or "").strip()
    if not text or text == DELETED_PLACEHOLDER:
        return False
    # 题目被物理删除时，meta 查不到 → 题库名 / 题型都为空
    if not item.get("bankName") and item.get("questionType") is None:
        return False
    return True


def _attention_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected = [item for item in items if item.get("level") in ATTENTION_LEVELS]
    selected.sort(
        key=lambda item: (
            LEVEL_ORDER.get(str(item.get("level")), 99),
            -int(item.get("errorCount") or 0),
            int(item.get("questionId") or 0),
        )
    )
    return selected


def _headline(items: List[Dict[str, Any]]) -> str:
    """一句话结论只统计**还活着**的题，不能把已删除题也说得像任务。"""
    overdue = sum(1 for item in items if item.get("level") == "overdue")
    repeated = sum(1 for item in items if item.get("level") == "repeated_failure")
    attention = sum(1 for item in items if item.get("level") in ATTENTION_LEVELS)
    if repeated:
        return f"有 {repeated} 道题反复失守，先停下来补前置知识，比继续刷更有效"
    if overdue:
        return f"有 {overdue} 道题已经过了复习窗口，现在练它们效果最好"
    if attention:
        return f"有 {attention} 道题需要关注，今天先把它们过一遍"
    return "当前没有需要立刻处理的薄弱题，保持现在的节奏"


def _task_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    level = str(item.get("level") or "")
    if level in ("overdue", "due_soon"):
        verb = "复习"
        minutes = 8 if level == "overdue" else 5
        reason = (
            f"已经超过建议复习时间 {item.get('overdueDays')} 天"
            if int(item.get("overdueDays") or 0) > 0
            else "复习窗口快到了，趁现在巩固一下"
        )
    elif level == "repeated_failure":
        verb = "攻克"
        minutes = 12
        reason = f"最近 {item.get('attempts') or 0} 次作答只答对 {item.get('correctCount') or 0} 次"
    else:
        verb = "练一练"
        minutes = 8
        reason = "最近的状态有点不稳定，再做几道确认一下"
    return {
        "id": f"q:{item.get('questionId')}",
        "type": "question",
        "questionId": item.get("questionId"),
        "bankName": item.get("bankName") or "",
        "subject": item.get("subject") or "",
        "questionText": item.get("questionText") or "",
        # 标题不在这里截断：截断会把 LaTeX 命令切成半截（如 P(\overline{A} \…），
        # 前端拿到完整题干后用 CSS 两行省略，KaTeX 才有机会正确渲染。
        "title": f"{verb}「{item.get('questionText') or ''}」",
        "reason": reason,
        "advice": item.get("advice") or "",
        "level": level,
        "levelText": item.get("levelText") or "",
        "estimatedMinutes": minutes,
    }


def _build_health_map(
    items: List[Dict[str, Any]], attention: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """按科目聚合的体检节点。

    ⚠️ 不用 `diag.bySubject`：那份聚合把已删除题也算进了分母，会出现一个
    67 道题的「未分类」巨块。这里只统计还活着的题，并按「待攻克题数」把
    最该看的科目排在前面。
    """
    weak_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for item in attention:
        subject = str(item.get("subject") or "未分类")
        weak_by_subject.setdefault(subject, []).append(item)

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        subject = str(item.get("subject") or "未分类")
        row = grouped.setdefault(
            subject,
            {"subject": subject, "questions": 0, "attempts": 0, "correct": 0},
        )
        row["questions"] += 1
        row["attempts"] += int(item.get("attempts") or 0)
        row["correct"] += int(item.get("correctCount") or 0)

    nodes: List[Dict[str, Any]] = []
    for subject, row in grouped.items():
        attempts = int(row["attempts"] or 0)
        accuracy = round(row["correct"] / attempts * 100, 1) if attempts else 0.0
        weak_items = weak_by_subject.get(subject, [])
        weak = len(weak_items)
        if accuracy >= 85 and weak == 0:
            status, status_text, color = "strong", "稳固", "#3fa06a"
        elif weak >= 2 or accuracy < 60:
            status, status_text, color = "weak", "待攻克", "#e5534b"
        else:
            status, status_text, color = "watch", "观察中", "#e8a33a"
        nodes.append(
            {
                "subject": subject,
                "accuracy": accuracy,
                "questions": int(row["questions"]),
                "weakCount": weak,
                "status": status,
                "statusText": status_text,
                "color": color,
                "size": max(30, min(60, 28 + int(row["questions"]) * 2)),
                "weakQuestions": [
                    {
                        "questionId": item.get("questionId"),
                        "questionText": item.get("questionText") or "",
                        "level": item.get("level"),
                        "levelText": item.get("levelText") or "",
                        "accuracy": item.get("accuracy"),
                    }
                    for item in weak_items[:3]
                ],
            }
        )
    nodes.sort(key=lambda n: (n["status"] != "weak", -n["weakCount"], n["accuracy"]))
    return nodes


def _build_error_battle(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """错题歼灭战：只统计「曾经做错过的题」。

    三个阶段对应真实可验证的行为，不是拍出来的进度条：
    · 待攻克  —— 最近一次仍错，或连对不足 2 次
    · 观察期  —— 已经连对 2~3 次，但还没达到毕业线
    · 已歼灭  —— 诊断判定为 mastered（连续答对 4 次以上）
    """
    ever_wrong = [item for item in items if int(item.get("attempts") or 0) > int(item.get("correctCount") or 0)]
    cleared = [i for i in ever_wrong if i.get("level") == "mastered"]
    observing = [
        i for i in ever_wrong
        if i.get("level") != "mastered" and int(i.get("streak") or 0) >= 2
    ]
    active = [
        i for i in ever_wrong
        if i.get("level") != "mastered" and int(i.get("streak") or 0) < 2
    ]
    active.sort(
        key=lambda item: (
            LEVEL_ORDER.get(str(item.get("level")), 99),
            -int(item.get("errorCount") or 0),
        )
    )
    total = len(ever_wrong)
    progress = round(len(cleared) / total * 100, 1) if total else 0.0

    targets = [
        {
            "questionId": item.get("questionId"),
            "bankName": item.get("bankName") or "",
            "subject": item.get("subject") or "",
            "questionText": item.get("questionText") or "",
            "level": item.get("level"),
            "levelText": item.get("levelText") or "",
            "errorCount": int(item.get("errorCount") or 0),
            "streak": int(item.get("streak") or 0),
            "stage": "observing" if item in observing else "active",
            "advice": item.get("advice") or "",
        }
        for item in (active + observing)[:6]
    ]

    return {
        "total": total,
        # 兼容旧字段：mastered 即 cleared
        "mastered": len(cleared),
        "cleared": len(cleared),
        "observing": len(observing),
        "active": len(active),
        "progress": progress,
        "targets": targets,
    }


async def build_learning_loop(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    diag = await sds.diagnose(db, user_id, limit=50)
    if not diag.get("hasData"):
        return {
            "hasData": False,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "headline": diag.get("headline") or "还没有足够的作答记录",
            "todayPlan": [],
            "healthMap": [],
            "errorBattle": {
                "total": 0,
                "mastered": 0,
                "cleared": 0,
                "observing": 0,
                "active": 0,
                "progress": 0,
                "targets": [],
            },
        }

    items = [item for item in (diag.get("items") or []) if _is_available(item)]
    attention = _attention_items(items)

    # 题目全被删了的极端情况：不要硬凑一张空图，直接告诉用户去练新题
    if not items:
        return {
            "hasData": False,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "headline": "之前的练习记录对应题目已不可用，重新做几道题就能生成新的学习闭环",
            "todayPlan": [],
            "healthMap": [],
            "errorBattle": {
                "total": 0,
                "mastered": 0,
                "cleared": 0,
                "observing": 0,
                "active": 0,
                "progress": 0,
                "targets": [],
            },
        }

    return {
        "hasData": True,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "headline": _headline(items),
        "todayPlan": [_task_from_item(item) for item in attention[:3]],
        "healthMap": _build_health_map(items, attention),
        "errorBattle": _build_error_battle(items),
    }


__all__ = ["build_learning_loop"]
