"""规划建议导出：PDF / Markdown / TXT。

建议对象没有任务/完成态；只导出标题、结论、阶段、依据、替代方案和风险。
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, Tuple


def _text(value: Any, limit: int = 2000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_filename(value: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "规划建议")).strip(" ._")
    return (stem or "规划建议")[:80]


def _markdown(advice: Dict[str, Any]) -> str:
    lines = [f"# {_text(advice.get('title') or '规划建议', 120)}", ""]
    if advice.get("summary"):
        lines.extend([_text(advice.get("summary"), 600), ""])
    lines.extend(["## 阶段建议", ""])
    for phase in advice.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        lines.append(f"### {_text(phase.get('title') or '阶段', 80)}（约 {int(phase.get('estimatedMinutes') or 0)} 分钟）")
        if phase.get("goal"):
            lines.append(f"目标：{_text(phase.get('goal'), 300)}")
        if phase.get("reason"):
            lines.append(f"依据：{_text(phase.get('reason'), 600)}")
        lines.append("")
    if advice.get("alternatives"):
        lines.extend(["## 另一种选择", ""])
        for item in advice["alternatives"]:
            if isinstance(item, dict):
                lines.append(f"- {_text(item.get('title') or '替代路径', 80)}：{_text(item.get('summary'), 400)}")
                if item.get("tradeoff"):
                    lines.append(f"  取舍：{_text(item.get('tradeoff'), 300)}")
        lines.append("")
    if advice.get("risks"):
        lines.extend(["## 需要注意", ""])
        lines.extend(f"- {_text(item, 300)}" for item in advice["risks"])
        lines.append("")
    lines.append(f"> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("> 这是规划建议，不是任务清单。")
    return "\n".join(lines).strip() + "\n"


def _plain(advice: Dict[str, Any]) -> str:
    lines = [_text(advice.get("title") or "规划建议", 120), "=" * 32, ""]
    if advice.get("summary"):
        lines.extend([_text(advice.get("summary"), 600), ""])
    lines.append("阶段建议")
    for phase in advice.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        lines.append(f"- {_text(phase.get('title') or '阶段', 80)}（约 {int(phase.get('estimatedMinutes') or 0)} 分钟）")
        if phase.get("goal"):
            lines.append(f"  目标：{_text(phase.get('goal'), 300)}")
        if phase.get("reason"):
            lines.append(f"  依据：{_text(phase.get('reason'), 600)}")
    if advice.get("alternatives"):
        lines.extend(["", "另一种选择"])
        for item in advice["alternatives"]:
            if isinstance(item, dict):
                lines.append(f"- {_text(item.get('title') or '替代路径', 80)}：{_text(item.get('summary'), 400)}")
    if advice.get("risks"):
        lines.extend(["", "需要注意"])
        lines.extend(f"- {_text(item, 300)}" for item in advice["risks"])
    lines.extend(["", f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", "这是规划建议，不是任务清单。"])
    return "\n".join(lines).strip() + "\n"


def _pdf(advice: Dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    from app.services.bank_export_service import _register_cjk_font, _rl_text_with_math

    font = _register_cjk_font()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    title_style = ParagraphStyle("AdviceTitle", fontName=font, fontSize=18, leading=24, spaceAfter=10)
    body_style = ParagraphStyle("AdviceBody", fontName=font, fontSize=10.5, leading=16, spaceAfter=8)
    head_style = ParagraphStyle("AdviceHead", fontName=font, fontSize=12, leading=18, spaceBefore=10, spaceAfter=6)
    story = [Paragraph(_rl_text_with_math(_text(advice.get("title") or "规划建议", 120), font, 18), title_style)]
    if advice.get("summary"):
        story.append(Paragraph(_rl_text_with_math(_text(advice.get("summary"), 600), font), body_style))
    story.append(Paragraph("阶段建议", head_style))
    for phase in advice.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        story.append(
            Paragraph(
                _rl_text_with_math(
                    f"{_text(phase.get('title') or '阶段', 80)}（约 {int(phase.get('estimatedMinutes') or 0)} 分钟）",
                    font,
                ),
                body_style,
            )
        )
        if phase.get("goal"):
            story.append(Paragraph(_rl_text_with_math(f"目标：{_text(phase.get('goal'), 300)}", font), body_style))
        if phase.get("reason"):
            story.append(Paragraph(_rl_text_with_math(f"依据：{_text(phase.get('reason'), 600)}", font), body_style))
    if advice.get("alternatives"):
        story.append(Paragraph("另一种选择", head_style))
        for item in advice["alternatives"]:
            if isinstance(item, dict):
                story.append(
                    Paragraph(
                        _rl_text_with_math(
                            f"· {_text(item.get('title') or '替代路径', 80)}：{_text(item.get('summary'), 400)}",
                            font,
                        ),
                        body_style,
                    )
                )
    if advice.get("risks"):
        story.append(Paragraph("需要注意", head_style))
        for item in advice["risks"]:
            story.append(Paragraph(_rl_text_with_math(f"· {_text(item, 300)}", font), body_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style))
    story.append(Paragraph("这是规划建议，不是任务清单。", body_style))
    doc.build(story)
    return buffer.getvalue()


def _escape(value: Any) -> str:
    text = _text(value, 2000)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def export_advice(advice: Dict[str, Any], fmt: str) -> Tuple[bytes, str, str]:
    format_value = str(fmt or "pdf").lower()
    stem = _safe_filename(str(advice.get("title") or "规划建议"))
    if format_value == "pdf":
        return _pdf(advice), f"{stem}.pdf", "application/pdf"
    if format_value == "md":
        return _markdown(advice).encode("utf-8"), f"{stem}.md", "text/markdown; charset=utf-8"
    if format_value in {"txt", "text"}:
        return _plain(advice).encode("utf-8"), f"{stem}.txt", "text/plain; charset=utf-8"
    raise ValueError("导出格式只支持 pdf / txt / md")


__all__ = ["export_advice"]
