"""
学情诊断报告 → PDF

为什么要有它（2026-10-20）
==========================
诊断算出来之后，如果只能在对话里读一遍，它就还是个「聊天记录」——
关掉页面就没了，也没法给老师看、给家长看、打印出来贴在书桌上。

一份能下载的 PDF 把「一次对话」变成「一份可交付的学业资产」。这与题库导出
是同一个判断：**产物能被带走，才叫功能；只能被读到，只是回答。**

排版取舍（都是踩过的坑）
========================
· **中文字体必须显式注册**：reportlab 的默认 Helvetica 没有中文字形，
  不注册就是满页方框。复用 `bank_export_service._register_cjk_font()`
  —— 那里已经把 Windows / Linux(容器) / macOS 三条路径和 reportlab 内置
  CID 兜底都试过了，再写一份必然漂移。
· **不用 reportlab 的 Table 画列**：题库名 + 题干 + 数字混在一张表里时，
  中文长文本的自动折行很别扭（要么撑破列宽、要么被截断）。
  这里用「一段一块」的流式排版（Paragraph + Spacer），读起来像一份文档，
  而不是一张被塞满的表。
· **分档用颜色区分，但颜色不是唯一信号**：每档都有中文标签。
  PDF 可能被黑白打印 —— 只靠颜色区分的报告打印出来就废了。

⚠️ 本模块**不重新计算任何诊断**：它只消费 `study_diagnosis_service.diagnose()`
的返回值。数字只有一个来源，报告与对话不可能说出两套结论。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

#: 分档 → 标题色（RGB 0~1）。刻意都偏深：浅色在打印稿上会糊成一片。
#: ⚠️ 颜色只是**辅助**，每档的标题文字本身就写明了是什么档（见 `LEVEL_TEXT`）。
_LEVEL_COLOR: Dict[str, tuple] = {
    "repeated_failure": (0.72, 0.15, 0.15),  # 红：最该处理
    "lapsing": (0.78, 0.38, 0.10),           # 橙
    "overdue": (0.78, 0.55, 0.10),           # 琥珀
    "due_soon": (0.16, 0.44, 0.68),          # 蓝
    "on_track": (0.16, 0.50, 0.30),          # 绿
    "mastered": (0.16, 0.50, 0.30),          # 绿（同一色系：都是"好消息"）
    "fresh": (0.45, 0.45, 0.45),             # 灰
}

#: 报告里每种分档最多列几道题（与 `study_diagnosis_service.MAX_ITEMS_PER_LEVEL` 同量级）
_MAX_ITEMS_SHOWN = 8

#: 题干在报告里截到多少字（PDF 不是题目阅读器，完整题干请回题库看）
_MAX_STEM_CHARS = 90


def _clip(text: str, limit: int = _MAX_STEM_CHARS) -> str:
    s = (text or "").strip().replace("\n", " ")
    return s if len(s) <= limit else s[:limit] + "…"


def _esc(text: Any) -> str:
    """转义 reportlab Paragraph 的标记字符

    ⚠️ 题干里天然会有 `<` `>` `&`（数学公式、比较符、HTML 残留）。
    不转义会被当成内联标签 → 要么报错、要么把后半段吞掉。
    """
    s = str(text if text is not None else "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stem_markup(text: Any, font: str) -> str:
    """题干 → reportlab 标记（**公式要转成可读的符号**）

    ⚠️ 不能只 `_esc`：题库里的题干大量是**裸 LaTeX**（Word/WPS 导入时没写 `$`），
    直接印出来就是 `P(\\overline{A} \\overline{B})` —— 一串反斜杠和花括号。
    2026-10-20 实测就踩到了：诊断报告里的概率论题干原文输出了 `\\overline{A}`。

    复用 `bank_export_service._rl_text_with_math`（它已经把 `\\overline` → 上划线、
    `\\frac` → 分数斜线、`\\sqrt` → √、`x^{2}` → `<super>` 都处理了，并且顺手清洗
    了控制字符）。**不要再在这里写第二套转换** —— 那必然与题库导出漂移。
    """
    from app.services.bank_export_service import _rl_text_with_math

    raw = _clip(str(text or ""))
    try:
        return _rl_text_with_math(raw, font, body_size=9.5)
    except Exception:  # noqa: BLE001 - 公式转换失败绝不能把整份报告带崩
        logger.warning("[diagnosis-pdf] 题干公式转换失败，退化为纯文本转义")
        return _esc(raw)


def export_diagnosis_pdf(diagnosis: Dict[str, Any], *, user_name: str = "") -> bytes:
    """把诊断结果渲染成 PDF 字节

    Args:
        diagnosis: `study_diagnosis_service.diagnose()` 的返回值（原样传进来）。
        user_name: 报告抬头的姓名（可空 —— 空就不印那行，不留「姓名：」这种半截）。

    Returns:
        PDF 字节。

    ⚠️ 空数据（`hasData=False`）也要能出报告：一份写着「还没有作答记录 + 该怎么开始」
    的 PDF 比直接报错有用 —— 用户点下载时它至少给了下一步。
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    # 字体注册走 bank_export_service 的同一份实现（见模块 docstring）
    from app.services.bank_export_service import _register_cjk_font

    font = _register_cjk_font()

    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
        title="学情诊断报告",
        author="OpenStudy",
    )

    # ── 样式 ──
    title = ParagraphStyle(
        "T", fontName=font, fontSize=19, leading=26, alignment=TA_CENTER,
        spaceAfter=4, textColor=colors.HexColor("#1A1A1A"),
    )
    sub = ParagraphStyle(
        "S", fontName=font, fontSize=9, leading=14, alignment=TA_CENTER,
        textColor=colors.HexColor("#777777"), spaceAfter=2,
    )
    headline = ParagraphStyle(
        "H", fontName=font, fontSize=12.5, leading=20,
        textColor=colors.HexColor("#1A1A1A"), spaceBefore=6, spaceAfter=6,
    )
    section = ParagraphStyle(
        "SEC", fontName=font, fontSize=12, leading=18,
        textColor=colors.HexColor("#1A1A1A"), spaceBefore=12, spaceAfter=5,
    )
    body = ParagraphStyle(
        "B", fontName=font, fontSize=10, leading=16,
        textColor=colors.HexColor("#333333"), spaceAfter=3,
    )
    item_stem = ParagraphStyle(
        "IS", fontName=font, fontSize=9.5, leading=15,
        textColor=colors.HexColor("#2A2A2A"), leftIndent=10, spaceAfter=1,
    )
    item_meta = ParagraphStyle(
        "IM", fontName=font, fontSize=8.5, leading=13,
        textColor=colors.HexColor("#777777"), leftIndent=10, spaceAfter=3,
    )
    advice = ParagraphStyle(
        "AD", fontName=font, fontSize=8.5, leading=14,
        textColor=colors.HexColor("#555555"), leftIndent=10, spaceAfter=6,
    )

    story: List[Any] = []

    # ── 抬头 ──
    story.append(Paragraph("学情诊断报告", title))
    stamp = str(diagnosis.get("generatedAt") or "")[:19].replace("T", " ")
    meta_bits = []
    if user_name:
        meta_bits.append(f"学生：{_esc(user_name)}")
    if stamp:
        meta_bits.append(f"生成时间：{stamp}")
    meta_bits.append("OpenStudy")
    story.append(Paragraph("　·　".join(meta_bits), sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#DDDDDD")))
    story.append(Spacer(1, 8))

    # ── 一句话结论 ──
    story.append(Paragraph(_esc(diagnosis.get("headline") or ""), headline))

    if not diagnosis.get("hasData"):
        story.append(
            Paragraph(
                "这份报告暂时没有数据 —— 你还没有在这个平台上作答过任何题目。"
                "做够一部分题之后再回来，这里会给出逐题的诊断结论。",
                body,
            )
        )
        for s in diagnosis.get("suggestions") or []:
            story.append(Paragraph(f"· {_esc(s)}", body))
        doc.build(story)
        return buf.getvalue()

    # ── 总览数字 ──
    summary = diagnosis.get("summary") or {}
    story.append(Paragraph("总体情况", section))
    story.append(
        Paragraph(
            f"共诊断 {summary.get('questionsSeen', 0)} 道题、"
            f"{summary.get('totalAttempts', 0)} 次作答，"
            f"整体准确率 {summary.get('overallAccuracy', 0)}%；"
            f"其中 <b>{summary.get('needsAttention', 0)}</b> 道需要优先处理、"
            f"<b>{summary.get('overdueCount', 0)}</b> 道已过复习窗口、"
            f"<b>{summary.get('canArchive', 0)}</b> 道可以归档。",
            body,
        )
    )

    # ── 分档分布 ──
    by_level = diagnosis.get("byLevel") or {}
    if by_level:
        story.append(Paragraph("各档分布", section))
        for lv, info in by_level.items():
            story.append(
                Paragraph(
                    f"· {_esc(info.get('text') or lv)}："
                    f"<b>{info.get('count', 0)}</b> 道",
                    body,
                )
            )

    # ── 逐题诊断（按档分组，档内保持算法给的顺序）──
    items = diagnosis.get("items") or []
    if items:
        story.append(Paragraph("逐题诊断", section))
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            grouped.setdefault(str(it.get("level") or "fresh"), []).append(it)

        for lv, group in grouped.items():
            color = _LEVEL_COLOR.get(lv, (0.3, 0.3, 0.3))
            story.append(
                Paragraph(
                    f'<font color="#{int(color[0]*255):02X}{int(color[1]*255):02X}'
                    f'{int(color[2]*255):02X}">{_esc(group[0].get("levelText") or lv)}</font>',
                    ParagraphStyle(
                        "LV", fontName=font, fontSize=11, leading=17,
                        spaceBefore=8, spaceAfter=2,
                    ),
                )
            )
            for it in group[:_MAX_ITEMS_SHOWN]:
                # ⚠️ 题干走 `_stem_markup`（公式转换），不是 `_esc` —— 见那个函数的注释
                story.append(Paragraph(_stem_markup(it.get("questionText"), font), item_stem))
                meta_line = (
                    f"{_esc(it.get('bankName') or '未知题库')}　"
                    f"作答 {it.get('attempts', 0)} 次 / 对 {it.get('correctCount', 0)} 次"
                    f"　准确率 {it.get('accuracy', 0)}%"
                )
                if it.get("overdueDays"):
                    meta_line += f"　已欠复习 {it['overdueDays']} 天"
                if it.get("recommendedIntervalDays") is not None:
                    meta_line += f"　建议间隔 {it['recommendedIntervalDays']} 天"
                story.append(Paragraph(meta_line, item_meta))
                if it.get("advice"):
                    story.append(Paragraph(_esc(it["advice"]), advice))

    # ── 学科分布 ──
    by_subject = diagnosis.get("bySubject") or []
    if by_subject:
        story.append(Paragraph("学科分布", section))
        for s in by_subject[:10]:
            story.append(
                Paragraph(
                    f"· {_esc(s.get('subject'))}：{s.get('questions', 0)} 道题 / "
                    f"{s.get('attempts', 0)} 次作答，准确率 {s.get('accuracy', 0)}%",
                    body,
                )
            )

    # ── 学习节奏 ──
    activity = diagnosis.get("activity") or {}
    if activity.get("activeDays"):
        story.append(Paragraph("学习节奏（近 30 天）", section))
        rhythm = (
            f"活跃 {activity.get('activeDays', 0)} 天，共作答 "
            f"{activity.get('totalPractice', 0)} 次，"
            f"活跃日均 {activity.get('averagePerActiveDay', 0)} 次，"
            f"单日最高 {activity.get('peakDayCount', 0)} 次"
        )
        if activity.get("looksLikeBurst"):
            rhythm += "（偏突击式，记忆留存靠间隔不靠单次时长）"
        story.append(Paragraph(rhythm, body))

    # ── 建议 ──
    suggestions = diagnosis.get("suggestions") or []
    if suggestions:
        story.append(Paragraph("下一步建议", section))
        for i, s in enumerate(suggestions, 1):
            story.append(Paragraph(f"{i}. {_esc(s)}", body))

    # ── 脚注 ──
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E5E5")))
    story.append(
        Paragraph(
            "本报告的全部结论由 OpenStudy 依据你的逐题作答记录计算得出，"
            "不是大模型生成的内容 —— 同一份数据永远得到同一个结论。",
            sub,
        )
    )

    try:
        doc.build(story)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[diagnosis-pdf] 渲染失败: {}", exc)
        raise
    return buf.getvalue()


__all__ = ["export_diagnosis_pdf"]
