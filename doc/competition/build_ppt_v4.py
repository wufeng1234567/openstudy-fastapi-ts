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
GRAPH_FULL = os.path.join(HERE, "user-graph-hover-2026-11-15.png")
GRAPH_TYPES = os.path.join(HERE, "user-graph-all-labels-2026-11-15.png")
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
    text(s, M_L, 1.02, 6.10, 1.90, "告别“赛博仓鼠”\n把吃灰的资料\n变成随时能用的知识资产", size=30, bold=True, color=INK, line_spacing=1.08)
    line(s, M_L, 3.16, M_L + 1.15, 3.16, color=MINT, width=2.5)
    text(s, M_L, 3.36, 5.95, 0.88,
         "能查、能练、能追到原文——\n不是再建一个收藏夹。",
         size=14, color=GRAY, line_spacing=1.45)
    chip(s, M_L, 4.38, 1.55, 0.36, "收进来", MINT_L, MINT_D, 9.5)
    chip(s, M_L + 1.75, 4.38, 1.55, 0.36, "连起来", MINT_L, MINT_D, 9.5)
    chip(s, M_L + 3.50, 4.38, 1.55, 0.36, "用起来", MINT_L, MINT_D, 9.5)
    line(s, M_L, 5.52, 6.3, 5.52, color=LINE, width=0.5)
    text(s, M_L, 5.68, 6.2, 0.24, "华为云码道 CodeArts 开发  ·  GitCode 开源  ·  FastAPI + Vue 3", size=9.5, color=GRAY2)
    text(s, M_L, 6.18, 6.2, 0.24, "gitcode.com/qi142410131/openstudy-fastapi-ts", size=9, color=MINT_D)
    pic_contain(s, GRAPH_TYPES, 7.00, 1.02, 5.70, 3.95, caption="当前演示图谱：26 个主题各有类型、来源和原文")
    footer(s, 1)


# ================= P2 用户与问题 =================
def p2():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  一个真实用户", "高数 Word 导进题库，一晚上一道题没刷成",
           "理工科备考者，周六晚上想先刷二重积分：公式全乱码，区域图留在原文，题目对不上知识点。")
    pic_card(s, WORD, M_L, 1.86, 4.20, 3.10, caption="演示资料：高等数学·综合练习（第三章）")
    x = 5.35
    text(s, x, 1.88, 7.00, 0.24, "一个晚上，一条因果链", size=9.5, bold=True, color=MINT_D, spc=60)
    text(s, x, 2.18, 7.00, 0.28, "资料进不了题，存多少都没用。", size=15.5, bold=True, color=INK)
    chain = [
        ("01", "公式丢结构", "二重积分公式进题库就变乱码"),
        ("02", "图题分家", "区域图还留在原文，题干旁边看不到"),
        ("03", "题找不到知识点", "做错也不知道对应哪一节、哪段原文"),
        ("04", "这道题刷不了", "一晚上过去，一道题没刷成"),
    ]
    yy = 2.78
    for i, (n, t, d) in enumerate(chain):
        card = rect(s, x, yy, 7.00, 0.62, fill=AMBER_L if i == 3 else WHITE, line=AMBER if i == 3 else LINE, lw=0.75, radius=0.05)
        text(s, x + 0.16, yy + 0.10, 0.38, 0.24, n, size=9, bold=True, color=AMBER if i == 3 else MINT_D)
        text(s, x + 0.58, yy + 0.08, 2.35, 0.24, t, size=11.6, bold=True, color=AMBER if i == 3 else INK)
        text(s, x + 2.95, yy + 0.10, 3.78, 0.30, d, size=9.2, color=AMBER if i == 3 else GRAY)
        if i < 3:
            text(s, x + 3.28, yy + 0.58, 0.30, 0.16, "↓", size=11, bold=True, color=MINT)
        yy += 0.76
    strip = rect(s, M_L, 5.24, 4.20, 0.38, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.14, 5.33, 3.90, 0.20, "一晚上，一道题没刷成。", size=9.2, bold=True, color=MINT_D)
    footer(s, 2)


# ================= P3 产品主线 =================
def p3():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  收进来 · 资料到题库", "同一份 Word，导进题库就能刷",
           "公式转 LaTeX、区域图随题、题目挂知识点、题源回到第 2294 段——四样都在。")
    strip = rect(s, M_L, 1.82, CW, 0.36, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.16, 1.89, CW - 0.32, 0.20,
         "先看体检结论：3 章 · 3 题 · 1 图 · 第三章缺练习，先补 2 题。", size=9.2, bold=True, color=MINT_D)
    steps = [
        ("01", "导入", "Word / PDF\n公式 + 插图"),
        ("02", "解析", "公式转 LaTeX\n图片保留"),
        ("03", "结构化", "题目 + 选项\n题干结构"),
        ("04", "入库", "3/3 入库\n可刷题"),
        ("05", "回源", "题源 #693\n第 2294 段"),
    ]
    sw = 1.78; gap = (CW - 5 * sw) / 4
    x = M_L
    for i, (n, t, d) in enumerate(steps):
        active = i in (2, 3, 4)
        card = rect(s, x, 2.36, sw, 0.96, fill=MINT if active else WHITE, line=None if active else LINE, lw=0.75, radius=0.06)
        tc = WHITE if active else INK
        dc = RGBColor(0xDD, 0xF7, 0xEC) if active else GRAY
        text(s, x + 0.12, 2.45, 0.34, 0.20, n, size=8.5, bold=True, color=dc if active else MINT_D)
        text(s, x + 0.12, 2.68, sw - 0.24, 0.24, t, size=12.0, bold=True, color=tc)
        text(s, x + 0.12, 2.97, sw - 0.24, 0.32, d, size=8.2, color=dc, line_spacing=1.15)
        x += sw + gap
    pic_card(s, BRUSH, M_L, 3.56, 7.05, 3.30, caption="真实练习页：同一道二重积分，公式、区域图、知识点和题源同时可见")
    right = rect(s, 8.02, 3.56, 4.50, 3.30, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 8.24, 3.72, 4.05, 0.26, "这份题为什么能刷？", size=15, bold=True, color=INK)
    bullets = [
        ("公式", "Word 公式转 LaTeX，在题目里原样渲染"),
        ("图片", "区域图跟着题走，不丢图、不贴错位置"),
        ("知识点", "题目挂到「二重积分」主题，下面能继续回原文"),
        ("题源", "来源资料 #693 / 第 2294 段，可点开原文"),
    ]
    yy = 4.12
    for t, d in bullets:
        text(s, 8.24, yy, 0.72, 0.22, t, size=9.8, bold=True, color=MINT_D)
        text(s, 9.02, yy - 0.01, 3.22, 0.40, d, size=9.3, color=GRAY, line_spacing=1.2)
        yy += 0.60
    text(s, 8.24, 6.52, 4.05, 0.20, "演示题库：高等数学 · 综合练习（第三章）", size=8.4, color=GRAY2)
    footer(s, 3)


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
    header(s, "03  /  连起来 · 知识百科与知识图谱", "做错一道题，点回知识点和原文",
           "题目 → 知识点 → 同名主题页 → 原文段落；一条链能走到底。")
    pic_card(s, GRAPH_FULL, M_L, 1.82, 6.05, 3.25, caption="演示资料夹：26 个微积分主题，选中「导数」")
    x, y, w, h = 7.05, 1.82, 5.45, 3.25
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.34, "导数", size=19, bold=True, color=INK)
    text(s, x + 0.22, y + 0.62, w - 0.44, 0.24, "1 份来源 · 6 个出链 · 12 个反链", size=10.2, bold=True, color=MINT_D)
    rows = [
        ("来源", "微积分知识地图 · 3 个原文片段"),
        ("相关题目", "点开题目，能回到这道二重积分"),
        ("相邻主题", "极限 / 微分 / 连续性 / 泰勒公式"),
    ]
    yy = y + 1.10
    for t, d in rows:
        text(s, x + 0.22, yy, 1.02, 0.22, t, size=9.8, bold=True, color=MINT_D)
        text(s, x + 1.30, yy, w - 1.52, 0.26, d, size=9.5, color=GRAY)
        yy += 0.48
    text(s, x + 0.22, y + 2.84, w - 0.44, 0.24, "「导数」与左图选中节点一致，来源/关系能对上。", size=8.8, color=GRAY2)
    strip = rect(s, M_L, 5.42, CW, 0.68, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.24, 5.56, CW - 0.48, 0.24,
         "做错题不只记一个错号：它还能告诉你考的是哪一节、原文在哪一段。", size=11.2, bold=True, color=MINT_D)
    text(s, M_L, 6.34, CW, 0.22, "知识百科讲清一个主题，知识图谱把题目、来源和关系连起来。", size=9.4, color=GRAY)
    footer(s, 4)


# ================= P6 规划建议 + Agent =================
def p6():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "04  /  用起来 · 规划建议", "接下来 7 天，每天先做什么？",
           "按这份高数资料的缺口和错题排：每天 30 分钟，先看哪段、再做哪几题。")
    left = rect(s, M_L, 1.82, 7.25, 4.55, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, M_L + 0.24, 1.98, 3.0, 0.26, "7 天处方", size=15, bold=True, color=INK)
    text(s, M_L + 0.24, 2.28, 6.7, 0.22, "每天都从这道题的错因和第三章缺口开始。", size=9.5, color=GRAY)
    days = [
        ("Day 1", "第三章 · 二重积分", "精读 20 分钟 + 2 题"),
        ("Day 2", "极限与连续", "1 题 + 回看公式"),
        ("Day 3", "偏导数", "1 题 + 订正错题"),
        ("Day 4", "二重积分错题", "重做 + 回原文"),
        ("Day 5", "变上限积分求导", "精读 + 2 题"),
        ("Day 6", "第三章综合", "3 题混合练习"),
        ("Day 7", "复盘", "错题 + 自测"),
    ]
    yy = 2.62
    for i, (d, t, r) in enumerate(days):
        if i == 0:
            row = rect(s, M_L + 0.24, yy - 0.04, 6.72, 0.44, fill=MINT_L, line=None, radius=0.04)
        text(s, M_L + 0.36, yy, 0.68, 0.20, d, size=8.6, bold=True, color=MINT_D)
        text(s, M_L + 1.10, yy, 2.80, 0.20, t, size=9.4, bold=True, color=INK)
        text(s, M_L + 4.18, yy, 2.62, 0.20, r, size=8.5, color=GRAY)
        yy += 0.48
    right = rect(s, 8.25, 1.82, 4.27, 4.55, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, 8.47, 1.98, 3.85, 0.26, "这份计划从哪里来？", size=15, bold=True, color=INK)
    items = [
        ("资料体检", "第三章缺练习，先补缺得最多的一章"),
        ("题库", "第 3 题错 1 次，今天先重做同型题"),
        ("时间", "每天 30 分钟，排得下再排"),
        ("可回看", "每一项都能点回原文和练习"),
    ]
    yy = 2.52
    for t, d in items:
        line(s, 8.47, yy + 0.22, 8.78, yy + 0.22, color=MINT, width=1.2)
        text(s, 8.90, yy, 3.30, 0.22, t, size=10.2, bold=True, color=INK)
        text(s, 8.90, yy + 0.22, 3.30, 0.32, d, size=8.7, color=GRAY, line_spacing=1.2)
        yy += 0.72
    strip = rect(s, 8.47, 5.52, 3.80, 0.44, fill=AMBER_L, line=None, radius=0.05)
    text(s, 8.60, 5.62, 3.55, 0.24, "明晚打开，第一道题已经排好。", size=9.2, bold=True, color=AMBER)
    text(s, M_L, 6.55, CW, 0.22, "演示计划基于高等数学·综合练习（第三章）生成；按本题库和资料缺口排序。", size=8.8, color=GRAY2)
    footer(s, 5)


# ================= P7 技术架构 =================
def p7():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "05  /  技术可信", "四个“不丢”，靠一条可核对的技术链路",
           "公式不丢、图片不丢、知识点不丢、题源不丢；每一步都有回执，失败有降级。")
    cards = [
        ("公式不丢", "OMML / Word 公式解析", "转成 LaTeX，进题库仍原样渲染"),
        ("图片不丢", "图片锚点绑定题干", "图随题走，不丢图、不贴错位置"),
        ("知识点不丢", "题目 → 知识点", "挂到主题页，能看关系和相邻概念"),
        ("题源不丢", "chunk → 原文", "题源 #693 / 第 2294 段，可回查"),
    ]
    cw = (CW - 3 * 0.16) / 4
    for i, (t, tech, d) in enumerate(cards):
        x = M_L + i * (cw + 0.16)
        card = rect(s, x, 1.92, cw, 1.72, fill=MINT_L2 if i == 0 else WHITE, line=LINE, lw=0.8, radius=0.06)
        text(s, x + 0.18, 2.08, cw - 0.36, 0.26, t, size=14.0, bold=True, color=INK)
        text(s, x + 0.18, 2.44, cw - 0.36, 0.22, tech, size=9.5, bold=True, color=MINT_D)
        text(s, x + 0.18, 2.74, cw - 0.36, 0.54, d, size=8.8, color=GRAY, line_spacing=1.25)
    line(s, M_L, 4.10, W - M_L, 4.10, color=LINE, width=0.6)
    steps = ["Word", "解析", "结构化", "入库", "刷题"]
    sx = M_L
    for i, label in enumerate(steps):
        if i:
            text(s, sx - 0.16, 4.30, 0.30, 0.24, "→", size=13, bold=True, color=MINT)
        text(s, sx, 4.28, 1.9, 0.26, label, size=10.2, bold=True, color=INK)
        sx += 2.35
    text(s, M_L, 5.12, 5.40, 0.24, "轻量自研：Vue 3 · FastAPI · PostgreSQL + pgvector · Redis", size=9.5, color=GRAY2)
    text(s, M_L, 5.50, 7.5, 0.22, "路由零 LLM 先分流；检索用 RRF；所有结果回到真实来源。", size=9.2, color=GRAY)
    evidence = rect(s, M_L, 5.92, CW, 0.52, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.22, 6.04, CW - 0.44, 0.24,
         "可核对：pytest 109 项 · ruff 通过 · 前端 build 通过 · 关键链路有探针", size=9.4, bold=True, color=MINT_D)
    footer(s, 6)


# ================= P8 码道开发 =================
def p8():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "06  /  码道 · 方法", "码道把工程流程带进系统",
           "让它读仓库、拆任务、跑测试、做 review，再把改动交付到系统。")
    chip(s, W - M_L - 2.20, 0.45, 2.20, 0.34, "华为云 · 码道 CodeArts", MINT_L, MINT_D, 9)
    pic_contain(s, CODEARTS_PLAN, M_L, 1.82, 6.70, 2.35,
                caption="真实工作区：需求被拆成 4 个可验收步骤，当前正在修改 hover 覆盖层")
    text(s, M_L, 4.48, 6.70, 0.24, "读码定位：KnowledgeWikiPanel.vue / useWikiMapDisplay.ts / style1.css", size=9.8, bold=True, color=MINT_D)
    text(s, M_L, 4.80, 6.70, 0.24, "验证路径：build:prod + 只读 review（P0/P1/P2）", size=9.8, color=GRAY)
    text(s, M_L, 5.24, 6.70, 0.28, "结果：一块能演示的系统能力。", size=11.2, bold=True, color=INK)
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
    footer(s, 7)


# ================= P8b 码道真实证据 =================
def p8b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "07  /  码道 · 真实证据", "一次真实改动，能看到每一步证据",
           "从 prompt 到 file:line、4 个 todos、测试和只读 review：每一步都能对上。")
    pic_contain(s, CODEARTS_FILELINE, M_L, 1.82, 7.10, 2.18,
                caption="文件定位：KnowledgeWikiPanel.vue:83 / 144–155 / 1195–1209；useWikiMapDisplay.ts:52–104")
    note = rect(s, M_L, 4.48, 7.10, 1.10, fill=MINT_L2, line=LINE, lw=0.7, radius=0.05)
    text(s, M_L + 0.20, 4.64, 6.70, 0.24, "读码结论", size=11.0, bold=True, color=MINT_D)
    text(s, M_L + 0.20, 4.92, 6.70, 0.46, "覆盖层上限 30 节点 / 80 边，当前节点可能被裁；先定位问题，再改 CSS 和显示层。",
         size=9.0, color=GRAY, line_spacing=1.2)
    x, y, w, h = 8.10, 1.82, 4.42, 4.42
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "四类证据", size=15.0, bold=True, color=INK)
    rows = [
        ("Prompt", "一句话说清目标、验收标准和不要动的地方"),
        ("File:line", "先读后写，定位到具体文件和行"),
        ("Todos", "拆成 4 个可验收步骤，改完逐项检查"),
        ("Review", "只读审查 P0/P1/P2，修复后再交付"),
    ]
    yy = y + 0.62
    for t, d in rows:
        rect(s, x + 0.22, yy, 0.07, 0.50, fill=MINT, line=None, radius=0.2)
        text(s, x + 0.42, yy, w - 0.62, 0.24, t, size=10.8, bold=True, color=INK)
        text(s, x + 0.42, yy + 0.24, w - 0.62, 0.32, d, size=8.8, color=GRAY, line_spacing=1.2)
        yy += 0.82
    line(s, x + 0.22, y + 3.76, x + w - 0.22, y + 3.76, color=LINE, width=0.5)
    text(s, x + 0.22, y + 3.86, w - 0.44, 0.22, "输出：一次可复核的真实改动。", size=9.0, color=GRAY2)
    strip = rect(s, M_L, 6.30, CW, 0.42, fill=MINT_L, line=None, radius=0.08)
    text(s, M_L + 0.24, 6.37, CW - 0.48, 0.24,
         "结果：能指到文件、能跑测试、能被 review 的真实工程改动。",
         size=9.8, bold=True, color=MINT_D)
    footer(s, 8)


# ================= P9 现场演示 =================
def p9():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "08  /  现场演示", "3 分钟，重走一份 Word 的真实链路",
           "不巡游功能，只让评委看见：同一条链路从问题走到今天能做什么。")
    stages = [
        ("0:00–0:20", "打开 Word", "3 小问 · 3 公式 · 1 张区域图"),
        ("0:20–0:50", "看体检", "3 题 · 1 图 · 第三章缺练习"),
        ("0:50–1:30", "变成题", "3/3 入库；公式、图、题源都在"),
        ("1:30–2:15", "追原文", "第 3 题 → 导数 → 第 2294 段"),
        ("2:15–2:50", "排计划", "Day1 第三章 + 2 题"),
    ]
    cw = (CW - 4 * 0.12) / 5
    for i, (t, h, res) in enumerate(stages):
        x = M_L + i * (cw + 0.12)
        card = rect(s, x, 1.94, cw, 2.96, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        text(s, x + 0.16, 2.10, cw - 0.32, 0.20, t, size=8.8, bold=True, color=MINT_D)
        text(s, x + 0.16, 2.40, cw - 0.32, 0.52, h, size=13.2, bold=True, color=INK)
        text(s, x + 0.16, 3.18, cw - 0.32, 1.16, res, size=9.2, color=GRAY, line_spacing=1.4)
    strip = rect(s, M_L, 5.22, CW, 0.44, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.20, 5.33, CW - 0.40, 0.24,
         "2:50–3:00 收束：一份资料从“能看”变成“能刷、能追、能计划”。", size=9.8, bold=True, color=MINT_D)
    guards = [("预置数据", "资料、题库、笔记和作答记录提前准备"), ("提前热身", "模型与检索预热，首字等待压到 3 秒内"), ("双保险", "网络异常切本地录屏，关键探针提前跑")]
    x = M_L; gw = (CW - 2 * 0.18) / 3
    for t, d in guards:
        text(s, x, 5.86, gw, 0.24, "· " + t, size=10.0, bold=True, color=INK)
        text(s, x + 0.16, 6.14, gw - 0.16, 0.40, d, size=8.8, color=GRAY, line_spacing=1.3)
        x += gw + 0.18
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


for fn in (p1, p2, p3, p5, p6, p7, p8, p8b, p9, p10):
    fn()

out = os.path.join(HERE, "OpenStudy-10页-码道版.pptx")
prs.save(out)
print("saved:", out, os.path.getsize(out))

