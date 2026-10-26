"""
复习卷生成服务（v3 · D2）

## 这个模块解决什么问题

`study_diagnosis_service.diagnose()` 会把「哪些题该先复习、为什么」算得很准，
但结果只能从 AI 对话里喊出来看一眼 —— **看完就没了，带不走**。

这里把诊断结果直接变成一份可打印的 Word 复习卷：

    题号/题型  →  题干（含原生表格与公式）  →  作答空间
    卷首：考点 × 分档 真表格
    卷尾：未来 7 天的复习计划表

## 为什么不复用 `export_bank_docx`

那个函数是「题库 → 整卷导出」，封面与正文结构都是题库语义
（题库名 / 题目数 / 全量题目）。

复习卷的语义不同：
  · 卷首要放**分档统计表**（诊断结果独有）
  · 卷尾要放**复习计划表**（诊断结果独有）
  · 正文是**按优先级挑出来的子集**，还要留作答空间

硬塞进去会让 `export_bank_docx` 长出一堆 `if mode == "review"` 分支，
污染「题库导出」这条被 26 项测试覆盖的路径。

所以这里**复用零件、不复用函数**：
  · `split_blocks()` / `_docx_add_blocks()` / `_docx_add_table()` —— 保证公式与表格正确
  · `normalize_answer()` / `_option_rows()` —— 保证答案与选项格式一致

## 表数据从哪来

`diagnose()` 返回的 `byLevel` 是 `{level: {count, text}}`，
`bySubject` 是 `[{subject, questions, attempts, accuracy}]`。
这两个正好是「分档 × 学科」的二维交叉 —— 也就是卷首那张表。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

#: 卷尾计划表排几天
PLAN_DAYS = 7


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _level_rows(diag: Dict[str, Any]) -> List[List[str]]:
    """
    「掌握度分档」表行：[分档, 题数, 占比, 建议]

    这是卷首第一张表。数据直接来自 `diagnose()["byLevel"]`。
    """
    by_level = diag.get("byLevel") or {}
    total = sum(_as_int((v or {}).get("count")) for v in by_level.values()) or 0

    # 建议文案：不同档位的处置方式不同，这是诊断服务的价值所在
    ADVICE = {
        "new": "先做一遍，建立初始印象",
        "learning": "重点复习，多做到能独立复述",
        "shaky": "重点复习，注意易错点",
        "familiar": "保持节奏，隔几天回看",
        "proficient": "少量回顾即可",
        "mastered": "基本不用再花时间",
        "archived": "已掌握，可归档",
    }

    rows: List[List[str]] = []
    for lv, info in by_level.items():
        count = _as_int((info or {}).get("count"))
        text = (info or {}).get("text") or lv
        pct = f"{round(count * 100 / total, 1)}%" if total else "—"
        rows.append([str(text), str(count), pct, ADVICE.get(lv, "按计划复习")])
    return rows


def _subject_rows(diag: Dict[str, Any]) -> List[List[str]]:
    """「学科正确率」表行：[学科, 题目数, 作答次数, 正确率, 判断]"""
    rows: List[List[str]] = []
    for s in diag.get("bySubject") or []:
        acc = s.get("accuracy")
        try:
            acc_f = float(acc)
        except (TypeError, ValueError):
            acc_f = 0.0
        # 60% 是「及格线」的常识值，低于它必须点出来
        verdict = "需加强" if acc_f < 60 else "正常"
        rows.append(
            [
                str(s.get("subject") or "未分类"),
                str(_as_int(s.get("questions"))),
                str(_as_int(s.get("attempts"))),
                f"{round(acc_f, 1)}%",
                verdict,
            ]
        )
    return rows


def _plan_rows(diag: Dict[str, Any], *, days: int = PLAN_DAYS) -> List[List[str]]:
    """
    「未来 N 天复习计划」表行：[日期, 星期, 建议题量, 重点]

    分配逻辑：
      · 逾期题优先排在最近两天（它们已经拖了）
      · 其余按 `recommendedIntervalDays` 铺开
      · 题量按剩余题数均摊，至少 3 道（太少不成"一次学习"）

    刻意做成**简单可解释**的分配，而不是什么算法 ——
    用户看一眼就能理解"为什么今天 6 道"，比复杂最优解更有用。
    """
    items = diag.get("items") or []
    today = datetime.now().date()

    # 逾期题单独拎出来（overdueDays > 0）
    overdue = [it for it in items if _as_int(it.get("overdueDays")) > 0]
    normal = [it for it in items if _as_int(it.get("overdueDays")) <= 0]

    # 把题分到 days 天里：逾期题优先塞进前一天，其余均摊
    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(days)]
    for it in overdue:
        buckets[0].append(it)
    if normal:
        per = max(1, (len(normal) + days - 1) // days)
        for i, it in enumerate(normal):
            idx = min(days - 1, i // per)
            buckets[idx].append(it)

    WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    rows: List[List[str]] = []
    for i in range(days):
        d = today + timedelta(days=i)
        b = buckets[i]
        # 这天的重点：取题量最多的分档
        levels: Dict[str, int] = {}
        for it in b:
            lv = str(it.get("levelText") or it.get("level") or "综合")
            levels[lv] = levels.get(lv, 0) + 1
        focus = "、".join(
            f"{k}×{v}" for k, v in sorted(levels.items(), key=lambda kv: -kv[1])
        ) or "—"
        rows.append(
            [
                d.strftime("%m-%d"),
                WEEK[d.weekday()],
                f"{max(3, len(b))} 道" if b else "巩固已学",
                focus,
            ]
        )
    return rows


def build_review_sheet(diag: Dict[str, Any], questions: Sequence[Dict[str, Any]]) -> bytes:
    """
    生成复习卷 .docx 字节

    :param diag: `study_diagnosis_service.diagnose()` 的返回
    :param questions: 已按优先级排好序的完整题目（`format_question()` 的输出）
    :return: .docx 字节

    结构：
        标题
        元信息（生成时间 / 题量 / 整体正确率）
        一、掌握度分档      ← 真表格
        二、学科情况        ← 真表格
        三、复习题目        ← 复用题库导出的题干渲染（公式 + 表格都正确）
        四、复习计划        ← 真表格
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    from app.services.bank_export_service import (
        _add_run,
        _add_segments,
        _docx_add_blocks,
        _docx_add_table,
        _option_rows,
        split_blocks,
    )

    doc = Document()

    # 版心与题库导出保持一致（用户会把两者一起打印，页边距必须一样）
    section = doc.sections[0]
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)

    now = datetime.now()
    summary = diag.get("summary") or {}

    # ── 标题 ──
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(tp, "薄弱点复习卷", size=20, bold=True)

    # ── 元信息 ──
    meta_bits = [f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}"]
    meta_bits.append(f"题量：{len(questions)}")
    if summary.get("overallAccuracy") is not None:
        meta_bits.append(f"整体正确率：{summary['overallAccuracy']}%")
    if summary.get("needsAttention"):
        meta_bits.append(f"待加强：{summary['needsAttention']} 题")
    mp = doc.add_paragraph()
    mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(mp, "　·　".join(meta_bits), size=9, color=(0x66, 0x66, 0x66))

    headline = diag.get("headline")
    if headline:
        hp = doc.add_paragraph()
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(hp, str(headline), size=9.5, color=(0x77, 0x77, 0x77))

    doc.add_paragraph()

    # ── 一、掌握度分档（真表格） ──
    lv_rows = _level_rows(diag)
    if lv_rows:
        h = doc.add_paragraph()
        _add_run(h, "一、掌握度分档", size=12.5, bold=True)
        _docx_add_table(
            doc,
            {"headers": ["掌握度", "题数", "占比", "建议"], "rows": lv_rows},
        )
        doc.add_paragraph()

    # ── 二、学科情况（真表格） ──
    sub_rows = _subject_rows(diag)
    if sub_rows:
        h = doc.add_paragraph()
        _add_run(h, "二、学科情况", size=12.5, bold=True)
        _docx_add_table(
            doc,
            {"headers": ["学科", "题目数", "作答次数", "正确率", "判断"], "rows": sub_rows},
        )
        doc.add_paragraph()

    # ── 三、复习题目 ──
    h = doc.add_paragraph()
    _add_run(h, "三、复习题目", size=12.5, bold=True)
    note = doc.add_paragraph()
    _add_run(
        note,
        "按「该先处理谁」排序。每题下方留了作答空间，建议先独立完成再看答案。",
        size=9,
        color=(0x88, 0x88, 0x88),
    )

    for idx, q in enumerate(questions, start=1):
        qtype = _as_int(q.get("questionType"), 1)
        type_text = q.get("questionTypeText") or ""

        head = doc.add_paragraph()
        head.paragraph_format.space_before = Pt(8)
        _add_run(head, f"{idx}. ", size=11, bold=True)
        if type_text:
            _add_run(head, f"［{type_text}］", size=8.5, color=(0x88, 0x88, 0x88))
        # 分档标签：让用户知道这题为什么被选进来
        lv_text = q.get("_levelText")
        if lv_text:
            _add_run(head, f"　{lv_text}", size=8.5, color=(0xC0, 0x60, 0x20))

        # 题干（复用题库导出的渲染器 → 表格/公式/图片全部正确）
        stem = q.get("questionText") or q.get("content") or ""
        _docx_add_blocks(doc, split_blocks(stem), indent_cm=0.45)

        # 选项（复习卷**不显示**"哪一个是答案"，但选项本身要给）
        for letter, text in _option_rows(q.get("options"), qtype):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.space_after = Pt(2)
            _add_run(p, f"{letter}. ", size=10.5, bold=True)
            # ⚠️ 不能用 `_docx_add_blocks(split_blocks(text))`：那是「题干」的渲染器，
            #    它按换行把文本拆成**多个段落**，选项会被拆成"A."和"am"两行。
            #    选项是单行短文本，用 `_add_segments`（行内渲染，公式照常转 OMML）。
            _add_segments(p, text, size=10.5)

        # 作答空间：简答题留 3 行空行，选择题不需要
        if qtype in (4, 5):
            for _ in range(3):
                doc.add_paragraph()

    # ── 四、复习计划（真表格） ──
    doc.add_page_break()
    h2 = doc.add_paragraph()
    _add_run(h2, "四、未来七天复习计划", size=12.5, bold=True)
    plan = _plan_rows(diag)
    if plan:
        _docx_add_table(
            doc,
            {"headers": ["日期", "星期", "建议题量", "重点"], "rows": plan},
        )

    tail = doc.add_paragraph()
    tail.paragraph_format.space_before = Pt(10)
    _add_run(
        tail,
        "说明：题量按掌握度与逾期情况分配；「重点」列出当天主要涉及的分档。",
        size=9,
        color=(0x88, 0x88, 0x88),
    )

    # ── 答案（单独起页，方便只打印正文时裁掉） ──
    if questions:
        doc.add_page_break()
        ah = doc.add_paragraph()
        _add_run(ah, "答案与解析", size=12.5, bold=True)
        for idx, q in enumerate(questions, start=1):
            from app.services.bank_export_service import normalize_answer

            qtype = _as_int(q.get("questionType"), 1)
            opts = _option_rows(q.get("options"), qtype)
            ans = normalize_answer(q.get("answer"), qtype, len(opts))
            ap = doc.add_paragraph()
            ap.paragraph_format.space_before = Pt(6)
            _add_run(ap, f"{idx}. ", size=10.5, bold=True)
            if ans:
                _add_run(ap, "答案：", size=10.5, bold=True, color=(0x0F, 0x7A, 0x3D))
                _add_run(ap, ans, size=10.5, color=(0x0F, 0x7A, 0x3D))
            else:
                _add_run(ap, "（此题暂无标准答案）", size=10, color=(0x99, 0x99, 0x99))

            ana = q.get("analysis") or q.get("questionAnalysis") or ""
            if ana:
                lbl = doc.add_paragraph()
                lbl.paragraph_format.left_indent = Cm(0.45)
                _add_run(lbl, "解析：", size=10, bold=True, color=(0x55, 0x55, 0x55))
                _docx_add_blocks(doc, split_blocks(ana), indent_cm=0.45)

    import io

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
