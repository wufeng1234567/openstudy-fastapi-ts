# -*- coding: utf-8 -*-
"""OpenStudy 10 页比赛版（0.8.0）· 知识资产主线 · 码道开发证据

运行：
  openstudy-fastapi/.venv/Scripts/python.exe doc/competition/build_ppt_v4.py
"""
import os
import sys

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SHOTS = os.path.join(ROOT, "doc", "screenshots")
SCREENSHOT_2026 = os.path.join(SHOTS, "readme-workspace-2026-11-14.png")
GRAPH = os.path.join(SHOTS, "readme-knowledge-graph-focus-2026-11-14.png")
GRAPH_DETAIL = os.path.join(SHOTS, "readme-knowledge-graph-detail-2026-11-14.png")
DIAGNOSIS = os.path.join(HERE, "diagnosis-health-2026-11-15.png")
PLANNING = os.path.join(SHOTS, "28-study-prescription.png")
AGENT = os.path.join(SHOTS, "01-agent-chat.png")
BRUSH = os.path.join(HERE, "brush-math-question-core-2026-11-15.png")
WORD = os.path.join(HERE, "word-source-math-v2-core-2026-11-15.png")
GRAPH_FULL = os.path.join(HERE, "demo-graph-hover-2026-11-15.png")
GRAPH_TYPES = os.path.join(HERE, "graph-types-core-2026-11-15.png")
GRAPH_DETAIL_REAL = os.path.join(HERE, "graph-detail-real-2026-11-15.png")
CODEARTS_PLAN = os.path.join(HERE, "codearts-plan-clean-2026-11-15.png")
CODEARTS_FILELINE = os.path.join(HERE, "codearts-fileline-2026-11-15.png")

# ---------------- 设计令牌 ----------------
INK = RGBColor(0x0B, 0x2B, 0x22)
INK2 = RGBColor(0x22, 0x45, 0x3B)
GRAY = RGBColor(0x5F, 0x6F, 0x69)
GRAY2 = RGBColor(0x8A, 0x9A, 0x94)
LINE = RGBColor(0xDD, 0xEF, 0xE7)
BG = RGBColor(0xFB, 0xFD, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MINT = RGBColor(0x10, 0xB9, 0x81)
MINT_D = RGBColor(0x0B, 0x7A, 0x5B)
MINT_L = RGBColor(0xE8, 0xF8, 0xF1)
MINT_L2 = RGBColor(0xF3, 0xFB, 0xF7)
AMBER = RGBColor(0xD9, 0x77, 0x06)
AMBER_L = RGBColor(0xFF, 0xF6, 0xE8)

FONT = "微软雅黑"
FONT_L = "微软雅黑 Light"
W, H = 13.333, 7.5
M_L = 0.78
CW = W - 2 * M_L


def fs(size):
    """统一放大字号。"""
    if size <= 8.5:
        return 10.5
    if size <= 9.5:
        return 11.5
    if size <= 10.5:
        return 12.5
    if size <= 11.5:
        return 13.5
    if size <= 12.5:
        return 14.5
    if size <= 13.5:
        return 15.5
    if size <= 15:
        return 17
    if size <= 17:
        return 18.5
    if size <= 20:
        return 21
    if size <= 24:
        return 25
    if size <= 28:
        return 31
    if size <= 32:
        return 35
    return size


def _no_shadow(shp):
    try:
        shp.shadow.inherit = False
    except Exception:
        pass


def rect(slide, x, y, w, h, fill=None, line=None, lw=0.75, radius=None, shape=None):
    st = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE)
    shp = slide.shapes.add_shape(st, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None and st == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(lw)
    _no_shadow(shp)
    shp.text_frame.word_wrap = True
    return shp


def text(slide, x, y, w, h, s, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
         font=FONT, line_spacing=None, anchor=MSO_ANCHOR.TOP, margins=(0, 0, 0, 0), spc=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(margins[0]); tf.margin_right = Inches(margins[1])
    tf.margin_top = Inches(margins[2]); tf.margin_bottom = Inches(margins[3])
    tf.vertical_anchor = anchor
    for i, ln in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing:
            p.line_spacing = line_spacing
        r = p.add_run(); r.text = ln
        r.font.name = font; r.font.size = Pt(fs(size)); r.font.bold = bold
        r.font.color.rgb = color
        if spc:
            rPr = r._r.get_or_add_rPr(); rPr.set("spc", str(int(spc)))
    return tb


def fill_text(shape, parts, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, margins=(0.18, 0.14, 0.14, 0.12), spacing=None):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(margins[0]); tf.margin_right = Inches(margins[1])
    tf.margin_top = Inches(margins[2]); tf.margin_bottom = Inches(margins[3])
    tf.vertical_anchor = anchor
    for i, it in enumerate(parts):
        txt, size, bold, color = it
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_before = Pt(spacing)
        r = p.add_run(); r.text = txt
        r.font.name = FONT; r.font.size = Pt(fs(size)); r.font.bold = bold
        r.font.color.rgb = color


def line(slide, x1, y1, x2, y2, color=LINE, width=0.75):
    from pptx.enum.shapes import MSO_CONNECTOR
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)


def bg(slide, color=BG):
    b = rect(slide, 0, 0, W, H, fill=color)
    sp = b._element
    sp.getparent().remove(sp)
    slide.shapes._spTree.insert(2, sp)


def header(slide, kicker, title, lede=None):
    text(slide, M_L, 0.44, CW, 0.24, kicker, size=10, bold=True, color=MINT_D, spc=150)
    text(slide, M_L, 0.74, CW, 0.72, title, size=28, bold=True, color=INK, line_spacing=1.05)
    if lede:
        text(slide, M_L, 1.50, CW, 0.36, lede, size=13, color=GRAY, line_spacing=1.2)


def footer(slide, idx):
    line(slide, M_L, 7.02, W - M_L, 7.02, color=LINE, width=0.5)
    text(slide, M_L, 7.10, 7.5, 0.18, "OpenStudy · 把信息来源，整理成可用的知识资产", size=8, color=GRAY2)
    text(slide, W - M_L - 1.3, 7.10, 1.3, 0.18, f"{idx:02d} / 10", size=8, color=GRAY2, align=PP_ALIGN.RIGHT)


def pic_card(slide, path, x, y, w, h, caption=None, border=True, crop=True):
    """截图卡片：默认中心裁切；crop=False 时按 contain 放进白底卡片。"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    cache = os.path.join(HERE, "_crop_cache_v4")
    os.makedirs(cache, exist_ok=True)
    key = f"{os.path.basename(path)}_{w:.2f}_{h:.2f}_{crop}"
    dst = os.path.join(cache, key + ".jpg")
    im = Image.open(path).convert("RGB")
    iw, ih = im.size
    if crop:
        target = w / h
        if iw / ih > target:
            nw = int(ih * target); left = (iw - nw) // 2; box = (left, 0, left + nw, ih)
        else:
            nh = int(iw / target); top = (ih - nh) // 2; box = (0, top, iw, top + nh)
        im.crop(box).save(dst, quality=92)
    else:
        im.save(dst, quality=92)
    pic = slide.shapes.add_picture(dst, Inches(x), Inches(y), Inches(w), Inches(h))
    if border:
        rect(slide, x, y, w, h, fill=None, line=LINE, lw=0.75, radius=0.02)
    if caption:
        text(slide, x, y + h + 0.07, w, 0.20, caption, size=8.5, color=GRAY2)
    return pic


def pic_contain(slide, path, x, y, w, h, caption=None, border=True):
    """按原比例完整放入卡片，不裁切关键内容。"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    im = Image.open(path)
    iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    rect(slide, x, y, w, h, fill=WHITE, line=LINE, lw=0.75, radius=0.02)
    slide.shapes.add_picture(path, Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
    if caption:
        text(slide, x, y + h + 0.07, w, 0.20, caption, size=8.5, color=GRAY2)


def chip(slide, x, y, w, h, label, fill=MINT_L, fg=MINT_D, size=9):
    shp = rect(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    fill_text(shp, [(label, size, True, fg)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
              margins=(0.04, 0.04, 0.01, 0.01))
    return shp


def section_label(slide, x, y, label, color=MINT_D):
    text(slide, x, y, 2.0, 0.22, label, size=9, bold=True, color=color, spc=80)


prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]


# ================= P1 封面 =================
def p1():
    s = prs.slides.add_slide(BLANK); bg(s)
    rect(s, 10.6, -2.0, 5.2, 5.2, fill=None, line=RGBColor(0xE3, 0xF4, 0xEC), lw=1.0, radius=0.5)
    rect(s, 11.9, 3.15, 3.6, 3.6, fill=None, line=RGBColor(0xEF, 0xF9, 0xF4), lw=1.0, radius=0.5)
    text(s, M_L, 0.66, 6.2, 0.24, "OPENSTUDY  ·  0.8.0  ·  知识资产系统", size=10, bold=True, color=MINT_D, spc=160)
    text(s, M_L, 1.02, 6.10, 1.55, "知识不是一堆文件，\n是一张能继续用的地图", size=31, bold=True, color=INK, line_spacing=1.08)
    line(s, M_L, 3.00, M_L + 1.15, 3.00, color=MINT, width=2.5)
    text(s, M_L, 3.20, 5.95, 0.88,
         "主题有类型，节点有来源；\n点开一个主题，关系、题目和原文都还在。",
         size=14, color=GRAY, line_spacing=1.45)
    text(s, M_L, 4.38, 6.0, 0.42, "一张图，从主题追到来源和下一步。", size=23, bold=True, color=INK)
    text(s, M_L, 4.90, 6.1, 0.32, "概念/实体 · 方法/公式 · 综合/概览 · 对比", size=13, color=GRAY2)
    line(s, M_L, 5.52, 6.3, 5.52, color=LINE, width=0.5)
    text(s, M_L, 5.68, 6.2, 0.24, "华为云码道 CodeArts 开发  ·  GitCode 开源  ·  FastAPI + Vue 3", size=9.5, color=GRAY2)
    text(s, M_L, 6.18, 6.2, 0.24, "gitcode.com/qi142410131/openstudy-fastapi-ts", size=9, color=MINT_D)
    pic_card(s, GRAPH_TYPES, 7.00, 1.02, 5.70, 3.95, caption="当前演示图谱：主题节点按类型着色，关系可追踪")
    chip(s, 7.00, 5.24, 1.65, 0.34, "主题有类型", MINT_L, MINT_D, 9)
    chip(s, 8.82, 5.24, 1.80, 0.34, "节点有来源", MINT_L, MINT_D, 9)
    chip(s, 10.80, 5.24, 1.55, 0.34, "关系可追踪", MINT_L, MINT_D, 9)
    footer(s, 1)


# ================= P2 用户与问题 =================
def p2():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  用户与问题", "不是资料不够，是资料回不到题上",
           "以一个理工科备考者为样本：一份带公式和插图的资料，看起来完整，却很难直接变成练习。")
    pic_card(s, WORD, M_L, 1.90, 4.50, 3.20, caption="原始资料：Word 里的公式、区域图与章节")
    x = 5.45
    text(s, x, 1.90, 6.95, 0.24, "一个典型场景", size=9.5, bold=True, color=MINT_D, spc=60)
    text(s, x, 2.22, 6.95, 0.64, "理工科备考者：\n资料看起来完整，题却做不起来", size=20, bold=True, color=INK, line_spacing=1.12)
    failures = [
        ("01", "公式进题库变乱码", "Word 里的二重积分公式，导入后失去结构，题目无法直接刷。"),
        ("02", "图片和题目分家", "区域图还在原文里，刷题页看不到，题目就少了一半信息。"),
        ("03", "题目找不到知识点", "做完题也不知道对应哪一节、哪段原文，下一次仍然从零开始。"),
    ]
    yy = 3.06
    for n, t, d in failures:
        card = rect(s, x, yy, 6.95, 0.74, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        fill_text(card, [(f"{n}  {t}", 12.0, True, INK), (d, 9.5, False, GRAY)],
                  margins=(0.20, 0.14, 0.08, 0.06), spacing=2)
        yy += 0.86
    quote = rect(s, x, 5.72, 6.95, 0.58, fill=AMBER_L, line=None, radius=0.06)
    text(s, x + 0.20, 5.82, 6.60, 0.34, "资料存着，学习动作没有发生。", size=13, bold=True, color=AMBER)
    footer(s, 2)


# ================= P3 产品主线 =================
def p3():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "05  /  核心能力 · 资料到题库", "从资料到刷题：公式、图片、知识点都不丢",
           "一份带公式和插图的 Word/PDF，导入后直接变成可刷的题，原文依据和知识点跟着走。")
    steps = [
        ("01", "导入文档", "Word / PDF\n含公式、插图"),
        ("02", "解析", "公式转 LaTeX\n图片保留"),
        ("03", "生成题库", "单选 / 多选\n解答题"),
        ("04", "刷题", "题目 + 图\n原位显示"),
        ("05", "知识点", "题目 → 主题页\n→ 原文 chunk"),
    ]
    sw = 1.82; gap = (CW - 5 * sw) / 4
    x = M_L
    line(s, M_L + 0.18, 2.32, W - M_L - 0.18, 2.32, color=RGBColor(0xC9, 0xEC, 0xDD), width=1.2)
    for i, (n, t, d) in enumerate(steps):
        active = i in (2, 3, 4)
        card = rect(s, x, 1.92, sw, 1.28, fill=MINT if active else WHITE, line=None if active else LINE, lw=0.75, radius=0.06)
        tc = WHITE if active else INK
        dc = RGBColor(0xDD, 0xF7, 0xEC) if active else GRAY
        text(s, x + 0.14, 2.04, 0.40, 0.22, n, size=9, bold=True, color=dc if active else MINT_D)
        text(s, x + 0.14, 2.30, sw - 0.28, 0.26, t, size=13.5, bold=True, color=tc)
        text(s, x + 0.14, 2.64, sw - 0.28, 0.42, d, size=9.0, color=dc, line_spacing=1.2)
        x += sw + gap
    pic_card(s, BRUSH, M_L, 3.40, 7.05, 3.42, caption="真实练习页：题干公式、区域图、知识点和题源同时可见")
    right = rect(s, 8.02, 3.40, 4.50, 3.42, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 8.24, 3.58, 4.05, 0.26, "题库不是纯文本", size=15, bold=True, color=INK)
    bullets = [
        ("公式", "Word 公式转 LaTeX，在题目里原样渲染"),
        ("图片", "文档插图跟着题走，不丢图、不贴错位置"),
        ("知识点 / 图谱", "题目挂到知识主题，知识图谱展示主题关系、相关题目与原文"),
        ("题源", "来源资料 #693 / 第 2294 段，可回到原文"),
    ]
    yy = 3.98
    for t, d in bullets:
        text(s, 8.24, yy, 0.72, 0.22, t, size=9.8, bold=True, color=MINT_D)
        text(s, 9.02, yy - 0.01, 3.22, 0.42, d, size=9.5, color=GRAY, line_spacing=1.25)
        yy += 0.62
    text(s, 8.24, 6.40, 4.05, 0.22, "演示题库：高等数学 · 综合练习（第三章）", size=8.5, color=GRAY2)
    footer(s, 6)


# ================= P4 资料诊疗室 =================
def p4():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  核心能力 · 资料诊疗室", "资料诊疗室：先看问题，再回原文",
           "同一份资料只有一个入口：体检、原文阅读、智能报告都在同一间诊疗室完成。")
    pic_card(s, DIAGNOSIS, M_L, 1.84, 7.55, 3.74, caption="演示样例（文本型资料）：综合分、四维评分、问题清单与章节覆盖热力图")
    x, y, w, h = 8.58, 1.84, 3.96, 4.58
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "先看问题，再决定怎么整理", size=15.0, bold=True, color=INK)
    metrics = [
        ("四维体检", "结构 90 · 图文 100 · 知识 63 · 可学习 48"),
        ("问题清单", "2 项待处理：25 章缺练习 / 10 章内容过薄"),
        ("章节覆盖", "热力图区分讲解、练习与内容过薄"),
        ("智能报告", "把问题转成整理目标、改进项和下一步"),
    ]
    yy = y + 0.62
    for t, d in metrics:
        rect(s, x + 0.22, yy, 0.07, 0.52, fill=MINT, line=None, radius=0.2)
        text(s, x + 0.42, yy, w - 0.62, 0.24, t, size=11.3, bold=True, color=INK)
        text(s, x + 0.42, yy + 0.24, w - 0.62, 0.36, d, size=8.8, color=GRAY, line_spacing=1.2)
        yy += 0.68
    note = rect(s, x + 0.22, y + 3.54, w - 0.44, 0.64, fill=MINT_L2, line=None, radius=0.06)
    fill_text(note, [("综合分 75 · 基本可用", 10.8, True, MINT_D), ("原文是事实来源，AI 只做整理和解释", 9.0, False, GRAY)],
              margins=(0.18, 0.12, 0.10, 0.06), spacing=3)
    text(s, M_L, 6.00, 7.4, 0.26, "体检 → 读原文 → 智能报告：一个入口完成，不用在三个功能间来回找。",
         size=12.5, bold=True, color=MINT_D)
    text(s, M_L, 6.32, 7.4, 0.22, "综合分、问题清单和章节热力图，最终都落到可执行的整理动作。", size=10.2, color=GRAY)
    footer(s, 3)


# ================= P5 知识百科 + 图谱 =================
def p5():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "03  /  核心能力 · 知识百科与知识图谱", "知识百科 × 知识图谱：节点有类型，来源有落点",
           "主题页按概念/方法/综合分色；点开节点，来源、相关题目和原文都能继续追。")
    pic_card(s, GRAPH_FULL, M_L, 1.82, 5.95, 3.18, caption="当前图谱：概念/实体 · 方法/公式 · 综合/概览按颜色区分")
    pic_contain(s, GRAPH_DETAIL_REAL, 6.95, 1.82, 3.02, 3.55, caption="主题详情：1 条来源 · 8 个出链 · 19 个反链")
    right = rect(s, 10.18, 1.82, 2.38, 3.55, fill=MINT_L2, line=None, radius=0.06)
    fill_text(right, [
        ("五类来源", 12.5, True, MINT_D),
        ("题库", 10.8, False, INK),
        ("资料", 10.8, False, INK),
        ("网页", 10.8, False, INK),
        ("笔记", 10.8, False, INK),
        ("图片", 10.8, False, INK),
        ("→ 归并成知识主题", 9.4, True, MINT_D),
    ], margins=(0.20, 0.14, 0.18, 0.10), spacing=5)
    left_bottom = rect(s, M_L, 5.72, 5.95, 0.92, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, M_L + 0.20, 5.86, 5.55, 0.24, "知识百科", size=12.5, bold=True, color=INK)
    text(s, M_L + 0.20, 6.14, 5.55, 0.24, "主题页有来源、版本、出链与反链；点来源回到原文。", size=9.6, color=GRAY)
    right_bottom = rect(s, 6.95, 5.72, 5.61, 0.92, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 7.15, 5.86, 5.20, 0.24, "知识图谱", size=12.5, bold=True, color=INK)
    text(s, 7.15, 6.14, 5.20, 0.24, "首层只画知识主题；详情里展开来源、相关题目和相邻关系。", size=9.6, color=GRAY)
    footer(s, 4)


# ================= P6 规划建议 + Agent =================
def p6():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "04  /  核心能力 · 规划建议", "规划建议：把下一步拆成每天能做的动作",
           "不是让模型凭空写计划：先看资料和题库证据，再按天拆成精读、练习、复习。")
    pic_card(s, PLANNING, M_L, 1.82, 6.78, 4.72, caption="真实界面：概率论 7 天学习处方，按天拆到精读 / 练习 / 复习")
    x, y, w, h = 7.78, 1.82, 4.75, 4.72
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "建议从哪里来", size=15.5, bold=True, color=INK)
    items = [
        ("证据起点", "从资料体检和题库薄弱点出发"),
        ("按天拆解", "把薄弱章节拆成精读、练习、复习"),
        ("可回看", "每项都能查看原文、回到练习"),
        ("不是任务清单", "不强制打卡，只给下一步建议"),
    ]
    yy = y + 0.66
    for t, d in items:
        line(s, x + 0.22, yy + 0.28, x + 0.56, yy + 0.28, color=MINT, width=1.2)
        text(s, x + 0.70, yy, w - 0.92, 0.24, t, size=11.3, bold=True, color=INK)
        text(s, x + 0.70, yy + 0.24, w - 0.92, 0.26, d, size=9.3, color=GRAY, line_spacing=1.2)
        yy += 0.70
    strip = rect(s, x + 0.22, y + 3.66, w - 0.44, 0.64, fill=AMBER_L, line=None, radius=0.06)
    text(s, x + 0.36, y + 3.76, w - 0.70, 0.44,
         "建议不是任务清单；每条都能回到资料与题目。", size=9.6, bold=True, color=AMBER)
    footer(s, 5)


# ================= P7 技术架构 =================
def p7():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "06  /  技术实现", "轻量自研，把可信写进架构",
           "没有重型编排框架：路由尽量不花模型调用，检索用 RRF，所有结果尽量回到来源。")
    layers = [
        ("前端", "Vue 3 · TypeScript · Vite", "资料空间 / 知识百科 / 知识图谱 / 对话", MINT),
        ("Agent Runtime", "Orchestrator + 多专家 + 29 个工具", "规则路由 · 工具回执 · 写操作确认", MINT_D),
        ("RAG", "解析 / 分块 / bge-m3 / HNSW", "向量 + 关键词 → RRF（k=60）", RGBColor(0x5B, 0x7C, 0xD6)),
        ("图谱", "五类来源抽取 → 知识主题", "主题首层 · 来源详情 · 真实边", AMBER),
        ("数据层", "PostgreSQL + pgvector · Redis", "文档、题库、笔记、来源、会话", GRAY),
    ]
    y = 1.90
    for i, (name, tech, role, col) in enumerate(layers):
        card = rect(s, M_L, y, 8.40, 0.84, fill=MINT_L2 if i in (1, 3) else WHITE, line=LINE, lw=0.75, radius=0.05)
        rect(s, M_L, y, 0.07, 0.84, fill=col, line=None, radius=0.2)
        text(s, M_L + 0.22, y + 0.10, 1.80, 0.24, name, size=11.2, bold=True, color=col)
        text(s, M_L + 1.98, y + 0.08, 3.70, 0.28, tech, size=10.0, bold=True, color=INK)
        text(s, M_L + 1.98, y + 0.40, 6.10, 0.26, role, size=9.0, color=GRAY)
        y += 0.92
    text(s, 9.50, 1.90, 3.0, 0.24, "三个取舍", size=10, bold=True, color=GRAY2, spc=60)
    choices = [
        ("01", "路由零 LLM", "关键词规则先分流，少一次模型调用就少一份不确定性。"),
        ("02", "检索用 RRF", "只看排名，不拍脑袋定「向量 0.8、关键词 0.6」。"),
        ("03", "来源优先", "主题小节、题目依据、对话引用都回到真实数据。"),
    ]
    yy = 2.26
    for n, t, d in choices:
        text(s, 9.50, yy, 0.40, 0.22, n, size=9, bold=True, color=MINT, spc=40)
        text(s, 9.90, yy - 0.02, 2.62, 0.24, t, size=11.2, bold=True, color=INK)
        text(s, 9.90, yy + 0.26, 2.62, 0.68, d, size=9.0, color=GRAY, line_spacing=1.35)
        yy += 1.08
    line(s, M_L, 6.46, W - M_L, 6.46, color=LINE, width=0.5)
    text(s, M_L, 6.56, 4.2, 0.22, "可核对的工程证据", size=9.5, bold=True, color=MINT_D)
    text(s, M_L + 1.95, 6.55, 7.8, 0.24, "pytest 109 项 · ruff 通过 · 前端 build 通过 · 关键链路有探针", size=9.2, color=GRAY)
    footer(s, 7)


# ================= P8 码道开发 =================
def p8():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "07  /  怎么用码道做出来", "码道不是补全插件，是把工程流程带进系统",
           "不是让它“生成一段代码”，而是让它读仓库、拆任务、跑测试、做 review，再交付到系统。")
    chip(s, W - M_L - 2.20, 0.45, 2.20, 0.34, "华为云 · 码道 CodeArts", MINT_L, MINT_D, 9)
    pic_contain(s, CODEARTS_PLAN, M_L, 1.82, 6.70, 2.35,
                caption="真实工作区：需求被拆成 4 个可验收步骤，当前正在修改 hover 覆盖层")
    text(s, M_L, 4.48, 6.70, 0.24, "读码定位：KnowledgeWikiPanel.vue / useWikiMapDisplay.ts / style1.css", size=9.8, bold=True, color=MINT_D)
    text(s, M_L, 4.80, 6.70, 0.24, "验证路径：build:prod + 只读 review（P0/P1/P2）", size=9.8, color=GRAY)
    text(s, M_L, 5.24, 6.70, 0.28, "结果不是一段代码，而是一块能演示的系统能力。", size=11.2, bold=True, color=INK)
    x, y, w, h = 7.55, 1.82, 5.00, 4.20
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "码道的优点，用在了哪里", size=15.0, bold=True, color=INK)
    rows = [
        ("先读后写", "CodeSemanticSearch / grep / read 定位 file:line，不靠猜 API"),
        ("计划拆解", "todowrite 把复杂改动拆成可验收步骤，避免一次性改崩"),
        ("子代理安排", "developer-test-agent 补测试；bug-fix-agent 修复；review 只读审查"),
        ("真实执行", "bash / pytest / build 自己跑验证，失败就修到通过"),
    ]
    yy = y + 0.58
    for t, d in rows:
        rect(s, x + 0.22, yy, 0.07, 0.50, fill=MINT, line=None, radius=0.2)
        text(s, x + 0.42, yy, w - 0.62, 0.24, t, size=10.8, bold=True, color=INK)
        text(s, x + 0.42, yy + 0.24, w - 0.62, 0.34, d, size=8.7, color=GRAY, line_spacing=1.2)
        yy += 0.84
    line(s, x + 0.22, y + 3.72, x + w - 0.22, y + 3.72, color=LINE, width=0.5)
    text(s, x + 0.22, y + 3.82, w - 0.44, 0.24, "输出：Agent Runtime / 知识图谱 / 题库，都能落到真实系统。",
         size=8.8, color=GRAY2)
    strip = rect(s, M_L, 6.30, CW, 0.42, fill=MINT_L, line=None, radius=0.08)
    text(s, M_L + 0.24, 6.37, CW - 0.48, 0.24,
         "评委不需要看工具次数，只需要看到：码道把复杂改动变成可拆解、可验证、可复用的工程过程。",
         size=9.8, bold=True, color=MINT_D)
    footer(s, 8)


# ================= P9 现场演示 =================
def p9():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "08  /  现场演示", "3 分钟，走完一条真实链路",
           "不巡游功能，只让评委看见：一份资料怎样变成可检查、可追溯、可继续使用的知识资产。")
    stages = [
        ("0:00 – 0:40", "先看问题", "打开资料诊疗室", "体检报告：四维检查、问题清单、章节覆盖；每条都能回到原文。"),
        ("0:40 – 1:40", "再看知识", "打开知识百科主题页", "看主题页的摘要、小节、来源和反向链接；点来源回到原文 chunk。"),
        ("1:40 – 2:30", "看关系", "切到知识图谱，点一个主题", "首层只显示知识主题；节点详情展开五类来源、相关题目和相邻关系。"),
        ("2:30 – 3:00", "看下一步", "在主题详情里生成规划建议", "沿真实图谱路径给出阶段建议；保存、导出，不生成假节点。"),
    ]
    cw = (CW - 3 * 0.16) / 4
    for i, (t, h, act, res) in enumerate(stages):
        x = M_L + i * (cw + 0.16)
        card = rect(s, x, 1.94, cw, 3.42, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        text(s, x + 0.20, 2.10, cw - 0.40, 0.22, t, size=9, bold=True, color=MINT_D, spc=30)
        text(s, x + 0.20, 2.42, cw - 0.40, 0.34, h, size=15, bold=True, color=INK)
        text(s, x + 0.20, 2.88, cw - 0.40, 0.62, act, size=10.8, bold=True, color=INK2, line_spacing=1.3)
        line(s, x + 0.20, 3.64, x + cw - 0.20, 3.64, color=LINE, width=0.5)
        text(s, x + 0.20, 3.80, cw - 0.40, 1.20, res, size=9.8, color=GRAY, line_spacing=1.45)
    guards = [("预置数据", "资料、题库、笔记和作答记录提前准备"), ("提前热身", "模型与检索预热，首字等待压到 3 秒内"), ("双保险", "网络异常切本地录屏，关键探针提前跑")]
    x = M_L; gw = (CW - 2 * 0.18) / 3
    for t, d in guards:
        text(s, x, 5.72, gw, 0.24, "· " + t, size=10.5, bold=True, color=INK)
        text(s, x + 0.16, 6.02, gw - 0.16, 0.44, d, size=9.2, color=GRAY, line_spacing=1.3)
        x += gw + 0.18
    strip = rect(s, M_L, 6.58, CW, 0.32, fill=MINT_L, line=None, radius=0.08)
    text(s, M_L + 0.20, 6.64, CW - 0.4, 0.22, "一句话记住：先给结果，再讲技术；每按一次按钮，都要有一处数据变化被看见。",
         size=9.0, bold=True, color=MINT_D)
    footer(s, 9)


# ================= P10 迭代与团队 =================
def p10():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "09  /  迭代计划与团队", "下一步：把可演示，做成可日常使用",
           "迭代优先补真实边界：扫描件、超大图谱、图片检索和团队协作。")
    cols = [
        ("30 天", "补可用性", ["扫描版 PDF 接入 OCR", "图片参与向量检索", "大图谱按组加载与分页", "移动端适配"], MINT_D),
        ("90 天", "补规模", ["团队知识空间与权限", "OBS 对象存储直传", "题库 / 笔记 / 资料开放 API", "知识图谱 2D → 3D：增加空间维度，看清多层关系"], AMBER),
        ("持续", "补可信", ["每条结论回到来源", "每次建议可复核", "关键链路持续加探针", "把知识资产变成可迁移能力"], GRAY2),
    ]
    cw = (CW - 2 * 0.20) / 3
    for i, (tag, title, items, col) in enumerate(cols):
        x = M_L + i * (cw + 0.20)
        card = rect(s, x, 1.94, cw, 2.78, fill=MINT_L2 if i == 0 else WHITE, line=LINE, lw=0.75, radius=0.05)
        text(s, x + 0.24, 2.10, cw - 0.48, 0.22, tag, size=10, bold=True, color=col, spc=80)
        text(s, x + 0.24, 2.38, cw - 0.48, 0.30, title, size=16, bold=True, color=INK)
        y = 2.86
        for it in items:
            text(s, x + 0.24, y, 0.16, 0.22, "·", size=13, bold=True, color=col)
            text(s, x + 0.46, y, cw - 0.72, 0.44, it, size=10.8, color=GRAY, line_spacing=1.3)
            y += 0.42
    text(s, M_L, 5.12, 5.6, 0.24, "团队分工（按真实职责，可一人多岗）", size=10, bold=True, color=GRAY2, spc=40)
    roles = [
        ("产品 / 后端", "场景定义、Agent 与 RAG 后端、数据与部署"),
        ("前端 / 交互", "资料空间、知识百科、知识图谱、对话体验"),
        ("测试 / 演示", "探针与回归、演示脚本、材料与讲解"),
    ]
    rw = (CW - 2 * 0.18) / 3
    for i, (t, d) in enumerate(roles):
        x = M_L + i * (rw + 0.18)
        line(s, x, 5.48, x + rw - 0.18, 5.48, color=MINT, width=1.0)
        text(s, x, 5.58, rw - 0.18, 0.24, t, size=10.5, bold=True, color=INK)
        text(s, x, 5.86, rw - 0.18, 0.40, d, size=9.2, color=GRAY, line_spacing=1.3)
    line(s, M_L, 6.50, W - M_L, 6.50, color=LINE, width=0.5)
    text(s, M_L, 6.50, 7.2, 0.24, "谢谢。欢迎现场提问，也欢迎直接上手体验。", size=12.5, bold=True, color=INK)
    text(s, M_L, 6.78, 8.0, 0.16, "gitcode.com/qi142410131/openstudy-fastapi-ts", size=8.2, color=MINT_D)
    footer(s, 10)


for fn in (p1, p2, p4, p5, p6, p3, p7, p8, p9, p10):
    fn()

out = os.path.join(HERE, "OpenStudy-10页-码道版.pptx")
prs.save(out)
print("saved:", out, os.path.getsize(out))
