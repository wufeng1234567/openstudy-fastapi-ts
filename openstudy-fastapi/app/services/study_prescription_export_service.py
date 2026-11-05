"""学习处方导出：Word / PDF / Markdown / TXT。

处方本身是结构化 JSON，导出时重新排版成“可打印的学习计划”，不是把
模型原始 JSON 直接丢给用户。任务详情里的 LaTeX 继续沿用平台已有导出链：
  · Word：复用 `bank_export_service._add_segments`，公式走 OMML；
  · PDF：复用 CJK 字体与 LaTeX→Unicode 降级，保证中文不方块、公式不原样泄漏；
  · MD/TXT：输出稳定可编辑的纯文本。
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from typing import Any, Dict, Tuple

from app.services.document_export_service import _make_docx, content_disposition

FORMAT_ALIASES = {
    "word": "docx",
    "docx": "docx",
    "pdf": "pdf",
    "md": "md",
    "markdown": "md",
    "txt": "txt",
    "text": "txt",
}
MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}
TASK_LABELS = {"read": "精读", "practice": "练习", "review": "复习", "recheck": "复测"}


def normalize_format(value: str) -> str:
    fmt = FORMAT_ALIASES.get(str(value or "").strip().lower())
    if not fmt:
        raise ValueError("导出格式只支持 pdf / word / md / txt")
    return fmt


def _text(value: Any, limit: int = 2000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_filename(value: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "学习处方")).strip(" ._")
    return (stem or "学习处方")[:80]


def _plan_days(plan: Dict[str, Any]) -> list:
    if not isinstance(plan, dict):
        raise ValueError("学习处方数据格式不正确")
    days = plan.get("days")
    if not isinstance(days, list) or not days:
        raise ValueError("学习处方没有可导出的学习任务")
    return [day for day in days if isinstance(day, dict)]


def _task_line(task: Dict[str, Any], *, markdown: bool = True) -> str:
    label = TASK_LABELS.get(str(task.get("type") or ""), "任务")
    done = bool(task.get("done"))
    mark = "[x]" if (markdown and done) else ("[ ]" if markdown else ("已完成" if done else "未完成"))
    title = _text(task.get("title") or "学习任务", 300)
    minutes = int(task.get("minutes") or 0)
    question_count = int(task.get("questionCount") or 0)
    line = f"- {mark} **{label}** {title}（{minutes} 分钟"
    if question_count:
        line += f" · {question_count} 道题"
    line += "）"
    return line


def _markdown(plan: Dict[str, Any], doc_name: str, meta: Dict[str, Any]) -> str:
    title = _text(plan.get("title") or "学习处方", 120)
    lines = [f"# {title}", ""]
    if plan.get("summary"):
        lines.extend([_text(plan.get("summary"), 500), ""])
    goal = _text(meta.get("goalLabel") or meta.get("goal") or "未设置", 60)
    days = int(meta.get("days") or len(_plan_days(plan)))
    daily = int(meta.get("dailyMinutes") or 0)
    lines.extend([
        f"> 资料：{_text(doc_name or meta.get('docName') or '未命名资料', 160)}",
        f"> 学习目标：{goal}",
        f"> 计划周期：{days} 天" + (f" · 每天约 {daily} 分钟" if daily else ""),
        f"> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 每日计划",
        "",
    ])
    for day in _plan_days(plan):
        day_no = int(day.get("day") or 0)
        theme = _text(day.get("theme") or f"第 {day_no} 天", 160)
        minutes = int(day.get("minutes") or 0)
        lines.append(f"### 第 {day_no} 天 · {theme}" + (f"（{minutes} 分钟）" if minutes else ""))
        lines.append("")
        for task in day.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            lines.append(_task_line(task, markdown=True))
            detail = _text(task.get("detail"), 1200)
            if detail:
                lines.append(f"  {detail}")
            section = _text(task.get("sectionTitle"), 200)
            if section:
                lines.append(f"  原文：{section}")
            lines.append("")
    checkpoints = [str(x).strip() for x in (plan.get("checkpoints") or []) if str(x).strip()]
    if checkpoints:
        lines.extend(["## 复诊节点", ""])
        lines.extend(f"- {item}" for item in checkpoints)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _plain_text(plan: Dict[str, Any], doc_name: str, meta: Dict[str, Any]) -> str:
    title = _text(plan.get("title") or "学习处方", 120)
    lines = [title, "=" * min(36, max(8, len(title))), ""]
    if plan.get("summary"):
        lines.extend([_text(plan.get("summary"), 500), ""])
    goal = _text(meta.get("goalLabel") or meta.get("goal") or "未设置", 60)
    lines.append(f"资料：{_text(doc_name or meta.get('docName') or '未命名资料', 160)}")
    lines.append(f"学习目标：{goal}")
    lines.append(f"计划周期：{int(meta.get('days') or len(_plan_days(plan)))} 天")
    if meta.get("dailyMinutes"):
        lines.append(f"每天可用：约 {int(meta['dailyMinutes'])} 分钟")
    lines.append("")
    for day in _plan_days(plan):
        day_no = int(day.get("day") or 0)
        theme = _text(day.get("theme") or f"第 {day_no} 天", 160)
        minutes = int(day.get("minutes") or 0)
        lines.append(f"第 {day_no} 天 · {theme}" + (f"（{minutes} 分钟）" if minutes else ""))
        for task in day.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            label = TASK_LABELS.get(str(task.get("type") or ""), "任务")
            done = "已完成" if task.get("done") else "未完成"
            title_text = _text(task.get("title") or "学习任务", 300)
            minutes_text = int(task.get("minutes") or 0)
            lines.append(f"  [{done}] {label}：{title_text}（{minutes_text} 分钟）")
            detail = _text(task.get("detail"), 1200)
            if detail:
                lines.append(f"    {detail}")
            section = _text(task.get("sectionTitle"), 200)
            if section:
                lines.append(f"    原文：{section}")
        lines.append("")
    checkpoints = [str(x).strip() for x in (plan.get("checkpoints") or []) if str(x).strip()]
    if checkpoints:
        lines.append("复诊节点")
        lines.extend(f"  - {item}" for item in checkpoints)
    return "\n".join(lines).strip() + "\n"


def _docx_markdown(plan: Dict[str, Any], doc_name: str, meta: Dict[str, Any]) -> str:
    """给 `_make_docx` 用的 Markdown：标题由 docx 自己加，任务状态用文字。"""
    title = _text(plan.get("title") or "学习处方", 120)
    lines: list[str] = []
    if plan.get("summary"):
        lines.extend([_text(plan.get("summary"), 500), ""])
    lines.extend([
        f"资料：{_text(doc_name or meta.get('docName') or '未命名资料', 160)}",
        f"学习目标：{_text(meta.get('goalLabel') or meta.get('goal') or '未设置', 60)}",
        f"计划周期：{int(meta.get('days') or len(_plan_days(plan)))} 天",
        "",
    ])
    for day in _plan_days(plan):
        day_no = int(day.get("day") or 0)
        lines.extend([f"## 第 {day_no} 天 · {_text(day.get('theme') or '', 160)}", ""])
        for task in day.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            label = TASK_LABELS.get(str(task.get("type") or ""), "任务")
            status = "已完成" if task.get("done") else "未完成"
            lines.append(f"- [{status}] {label}：{_text(task.get('title') or '学习任务', 300)}（{int(task.get('minutes') or 0)} 分钟）")
            detail = _text(task.get("detail"), 1200)
            if detail:
                lines.append(f"  {detail}")
            section = _text(task.get("sectionTitle"), 200)
            if section:
                lines.append(f"  原文：{section}")
        lines.append("")
    checkpoints = [str(x).strip() for x in (plan.get("checkpoints") or []) if str(x).strip()]
    if checkpoints:
        lines.append("## 复诊节点")
        lines.extend(f"- {item}" for item in checkpoints)
    return "\n".join(lines).strip() + "\n"


def _pdf(plan: Dict[str, Any], doc_name: str, meta: Dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    from app.services.bank_export_service import _register_cjk_font, _rl_text_with_math

    font = _register_cjk_font()
    title_style = ParagraphStyle("rp_title", fontName=font, fontSize=20, leading=27, spaceAfter=8)
    body_style = ParagraphStyle("rp_body", fontName=font, fontSize=10.5, leading=16, spaceAfter=4)
    meta_style = ParagraphStyle("rp_meta", fontName=font, fontSize=9.5, leading=14, textColor="#666666")
    day_style = ParagraphStyle("rp_day", fontName=font, fontSize=13, leading=19, spaceBefore=10, spaceAfter=5, textColor="#222222")
    task_style = ParagraphStyle("rp_task", fontName=font, fontSize=10.5, leading=16, leftIndent=12, spaceAfter=3)
    detail_style = ParagraphStyle("rp_detail", fontName=font, fontSize=9.5, leading=14, leftIndent=24, textColor="#555555")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    story = [Paragraph(_rl_text_with_math(_text(plan.get("title") or "学习处方", 120), font, 20), title_style)]
    if plan.get("summary"):
        story.append(Paragraph(_rl_text_with_math(_text(plan.get("summary"), 500), font), body_style))
    story.extend([
        Paragraph(_rl_text_with_math(f"资料：{_text(doc_name or meta.get('docName') or '未命名资料', 160)}", font), meta_style),
        Paragraph(_rl_text_with_math(f"学习目标：{_text(meta.get('goalLabel') or meta.get('goal') or '未设置', 60)}", font), meta_style),
        Paragraph(_rl_text_with_math(f"计划周期：{int(meta.get('days') or len(_plan_days(plan)))} 天", font), meta_style),
        Spacer(1, 8),
    ])
    for day in _plan_days(plan):
        day_no = int(day.get("day") or 0)
        theme = _text(day.get("theme") or f"第 {day_no} 天", 160)
        story.append(Paragraph(_rl_text_with_math(f"第 {day_no} 天 · {theme}", font), day_style))
        for task in day.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            label = TASK_LABELS.get(str(task.get("type") or ""), "任务")
            status = "已完成" if task.get("done") else "未完成"
            title_text = _text(task.get("title") or "学习任务", 300)
            minutes = int(task.get("minutes") or 0)
            story.append(Paragraph(_rl_text_with_math(f"[{status}] {label}：{title_text}（{minutes} 分钟）", font), task_style))
            detail = _text(task.get("detail"), 1200)
            if detail:
                story.append(Paragraph(_rl_text_with_math(detail, font), detail_style))
            section = _text(task.get("sectionTitle"), 200)
            if section:
                story.append(Paragraph(_rl_text_with_math(f"原文：{section}", font), detail_style))
        story.append(Spacer(1, 4))
    checkpoints = [str(x).strip() for x in (plan.get("checkpoints") or []) if str(x).strip()]
    if checkpoints:
        story.append(Paragraph("复诊节点", day_style))
        for item in checkpoints:
            story.append(Paragraph(_rl_text_with_math(f"· {item}", font), task_style))
    doc.build(story)
    return buf.getvalue()


def export_prescription(
    *,
    doc_name: str,
    plan: Dict[str, Any],
    fmt: str,
    meta: Dict[str, Any] | None = None,
) -> Tuple[bytes, str, str]:
    meta = meta or {}
    normalized = normalize_format(fmt)
    title = _text(plan.get("title") or "学习处方", 120)
    stem = _safe_filename(f"{doc_name or '资料'}-学习处方")
    if normalized == "md":
        return _markdown(plan, doc_name, meta).encode("utf-8"), f"{stem}.md", MEDIA_TYPES["md"]
    if normalized == "txt":
        return _plain_text(plan, doc_name, meta).encode("utf-8"), f"{stem}.txt", MEDIA_TYPES["txt"]
    if normalized == "docx":
        return _make_docx(_docx_markdown(plan, doc_name, meta), {}, title), f"{stem}.docx", MEDIA_TYPES["docx"]
    return _pdf(plan, doc_name, meta), f"{stem}.pdf", MEDIA_TYPES["pdf"]


__all__ = ["normalize_format", "export_prescription", "content_disposition"]
