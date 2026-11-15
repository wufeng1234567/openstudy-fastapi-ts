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
GRAPH_FULL = os.path.join(HERE, "graph-pian-daoshu-core-2026-11-15.png")
GRAPH_TYPES = os.path.join(HERE, "user-graph-all-labels-2026-11-15.png")
CHAT_HOME = os.path.join(HERE, "chat-home-2026-11-15.png")
EXAM_MATERIALS = os.path.join(HERE, "exam-week-materials-dense-2026-11-15.png")
P3_QUESTION = os.path.join(HERE, "question-knowledge-core-2026-11-15.png")
PLANNING_GRAPH = os.path.join(HERE, "planning-graph-2026-11-15.png")
ENCYCLOPEDIA = os.path.join(HERE, "knowledge-encyclopedia-pian-daoshu-2026-11-15.png")
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
    text(slide, W - M_L - 3.95, 7.10, 2.25, 0.18, "Agent · 理解 → 工具 → 回执", size=7.2, color=GRAY2, align=PP_ALIGN.RIGHT)
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
    text(s, M_L, 0.66, 6.2, 0.24, "OPENSTUDY  ·  0.8.0  ·  AI+ 知识资产系统", size=10, bold=True, color=MINT_D, spc=160)
    text(s, M_L, 1.02, 6.10, 1.90, "告别“赛博仓鼠”\n把吃灰的资料\n变成随时能用的知识资产", size=30, bold=True, color=INK, line_spacing=1.08)
    line(s, M_L, 3.16, M_L + 1.15, 3.16, color=MINT, width=2.5)
    text(s, M_L, 3.36, 5.95, 0.88,
         "能查、能练、能追到原文——\n一个会调用工具的 Agent。",
         size=14, color=GRAY, line_spacing=1.45)
    chip(s, M_L, 4.38, 1.55, 0.36, "收进来", MINT_L, MINT_D, 9.5)
    chip(s, M_L + 1.75, 4.38, 1.55, 0.36, "连起来", MINT_L, MINT_D, 9.5)
    chip(s, M_L + 3.50, 4.38, 1.55, 0.36, "用起来", MINT_L, MINT_D, 9.5)
    agent = rect(s, M_L, 4.88, 5.05, 0.42, fill=MINT_L2, line=None, radius=0.06)
    text(s, M_L + 0.16, 4.98, 4.80, 0.24, "Agent：读资料 · 建题库 · 连图谱 · 排计划", size=10.4, bold=True, color=MINT_D)
    line(s, M_L, 5.52, 6.3, 5.52, color=LINE, width=0.5)
    text(s, M_L, 5.68, 6.2, 0.24, "团队：码上有为  ·  华为云码道 CodeArts 开发  ·  GitCode 开源", size=10.2, bold=True, color=MINT_D)
    text(s, M_L, 6.18, 6.2, 0.24, "FastAPI + Vue 3  ·  gitcode.com/qi142410131/openstudy-fastapi-ts", size=8.8, color=GRAY2)
    pic_contain(s, CHAT_HOME, 7.00, 1.02, 5.70, 3.95,
                caption="Agent 入口：把资料交给它，也可以在对话里调用题库、图谱和计划")
    footer(s, 1)


# ================= P2 用户与问题 =================
def p2():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  考试周的真实场景", "考试周，资料存了一堆，却凑不出一套能刷的题",
           "手头有笔记、课件截图、概念清单和聊天记录里的答案；想复习时，能翻的很多，能练的很少。")
    pic_card(s, EXAM_MATERIALS, M_L, 1.86, 4.55, 4.50)
    text(s, M_L, 6.42, 4.55, 0.42, "这份资料：文字、截图、公式、图表混在一起，章节顺序和图题位置也没有统一。", size=10.5, color=GRAY, line_spacing=1.2)
    x = 5.55
    text(s, x, 1.88, 6.80, 0.24, "手头有资料，复习却没有练习", size=10.5, bold=True, color=MINT_D, spc=60)
    text(s, x, 2.18, 6.80, 0.32, "资料很多，题很少。", size=18.0, bold=True, color=INK)
    cards = [
        ("01", "手头是资料", "笔记、课件截图、概念清单、聊天答案散在不同地方。"),
        ("02", "题目要自己拼", "从聊天网站拿答案，只能截图或复制，再手动整理成题。"),
        ("03", "学完串不起来", "每道题是孤立的，换一道就不会，也没法按知识点复习。"),
    ]
    yy = 2.82
    for n, t, d in cards:
        card = rect(s, x, yy, 6.80, 0.92, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        text(s, x + 0.16, yy + 0.14, 0.38, 0.24, n, size=10, bold=True, color=MINT_D)
        text(s, x + 0.64, yy + 0.10, 2.80, 0.26, t, size=12.5, bold=True, color=INK)
        text(s, x + 0.64, yy + 0.40, 5.80, 0.34, d, size=10.0, color=GRAY, line_spacing=1.2)
        yy += 1.02
    strip = rect(s, x, 5.95, 6.80, 0.62, fill=MINT_L, line=None, radius=0.06)
    text(s, x + 0.20, 6.06, 6.40, 0.32, "资料在，能反复练的题不在。", size=14.0, bold=True, color=MINT_D)
    footer(s, 2)


# ================= P3 产品主线 =================
def p3():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  导入后 · 智能生成题库", "资料导入后，智能体自动提炼成能刷的题库",
           "支持 Word / PDF / Markdown / 网页 / 图片；智能体自动识别题目、公式和图片，提炼成可刷题库。")
    strip = rect(s, M_L, 1.82, CW, 0.36, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.16, 1.89, CW - 0.32, 0.20,
         "智能体流程：识别题目 → 解析公式/图片 → 结构化 → 关联知识点 → 生成题库。", size=9.2, bold=True, color=MINT_D)
    steps = [
        ("01", "导入", "Word / PDF\n网页 / 图片"),
        ("02", "智能识别", "题目 / 公式\n图片 / 表格"),
        ("03", "提炼题目", "题干 + 选项\n解析结构"),
        ("04", "关联知识点", "自动挂主题"),
        ("05", "生成题库", "可刷 / 可导出"),
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
        if i < 4:
            text(s, x + sw + 0.18, 2.70, 0.30, 0.24, "→", size=16, bold=True, color=MINT)
        x += sw + gap
    pic_contain(s, P3_QUESTION, M_L, 3.46, 7.05, 3.24,
                caption="真实题目：顶部知识点 chips、来源 #693 / 第 2294 段和题干在同一屏")
    right = rect(s, 8.02, 3.56, 4.50, 3.30, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 8.24, 3.72, 4.05, 0.26, "题库里有什么？", size=15, bold=True, color=INK)
    bullets = [
        ("图文混排", "题干、选项、解析、图片保持原版排版"),
        ("公式渲染", "OMML / LaTeX 原样显示，公式能看能算"),
        ("知识点", "每道题挂到「二重积分」主题，可按知识点筛选"),
        ("导出", "题库可导出、可分享，不只停在本机"),
    ]
    yy = 4.12
    for t, d in bullets:
        text(s, 8.24, yy, 0.96, 0.22, t, size=9.8, bold=True, color=MINT_D)
        text(s, 9.26, yy - 0.01, 3.00, 0.40, d, size=9.3, color=GRAY, line_spacing=1.2)
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
    header(s, "03  /  连起来 · 知识图谱自动抽取节点", "资料进来，Agent 先长出一张知识图谱",
           "自动抽取知识节点、关系和来源；图谱是题库的上游，也是知识百科的骨架。")
    pic_card(s, GRAPH_FULL, M_L, 1.82, 6.00, 3.35, caption="选中「偏导数」：节点、相邻关系和来源入口在同一屏")
    x, y, w, h = 7.02, 1.82, 5.48, 4.30
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.28, "知识图谱做了什么？", size=14.8, bold=True, color=INK)
    rows = [
        ("自动抽取", "从 Word / PDF / 网页 / 图片里识别概念、方法、实体"),
        ("关系连线", "前置 / 相关 / 对比 / 包含，自动建立主题关系"),
        ("类型分层", "概念·实体 / 方法·公式 / 综合·概览 / 对比"),
        ("来源回查", "每个节点保留 source chunk，能回到原文"),
        ("承接题库", "题目的知识点落到同一张图，后续可继续追题"),
    ]
    yy = y + 0.66
    for t, d in rows:
        rect(s, x + 0.22, yy, 0.07, 0.48, fill=MINT, line=None, radius=0.2)
        text(s, x + 0.42, yy, 1.05, 0.22, t, size=10.2, bold=True, color=INK)
        text(s, x + 1.52, yy, w - 1.70, 0.44, d, size=9.8, color=GRAY, line_spacing=1.2)
        yy += 0.66
    text(s, x + 0.22, y + 4.02, w - 0.44, 0.22, "下一步：每个节点交给 LLM 整理成知识百科。", size=9.5, bold=True, color=MINT_D)
    strip = rect(s, M_L, 6.20, CW, 0.38, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.24, 6.28, CW - 0.48, 0.22,
         "题库解决“能刷”，知识图谱解决“为什么错、和谁相关、原文在哪”。", size=10.4, bold=True, color=MINT_D)
    footer(s, 4)


# ================= P6 规划建议 + Agent =================
def p6():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "04  /  知识百科 · LLM 扩写", "每个知识节点，都有一页能用的知识百科",
           "图谱只给关系；LLM 自动整理定义、要点、例子、相关题和来源，生成用户能读能问的知识页。")
    pic_card(s, ENCYCLOPEDIA, M_L, 1.82, 7.25, 4.55,
             caption="真实界面：左侧知识图谱 + 右侧「偏导数」知识详情；来源和相关主题都在同一页")
    x, y, w, h = 8.25, 1.82, 4.28, 4.55
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.26, "知识百科能做什么？", size=14.5, bold=True, color=INK)
    items = [
        ("读懂", "定义、核心要点、例子，不用反复翻原文"),
        ("看关系", "前置 / 相关 / 对比，一眼知道接在哪"),
        ("做题", "相关题目和题源，学完就能练"),
        ("追问", "在智能对话里继续问，Agent 调用工具"),
    ]
    yy = y + 0.66
    for t, d in items:
        line(s, x + 0.22, yy + 0.22, x + 0.54, yy + 0.22, color=MINT, width=1.2)
        text(s, x + 0.68, yy, w - 0.90, 0.24, t, size=11.0, bold=True, color=INK)
        text(s, x + 0.68, yy + 0.24, w - 0.90, 0.34, d, size=9.8, color=GRAY, line_spacing=1.2)
        yy += 0.78
    strip = rect(s, x + 0.22, y + 3.64, w - 0.44, 0.58, fill=AMBER_L, line=None, radius=0.06)
    text(s, x + 0.34, y + 3.74, w - 0.64, 0.38, "图谱给结构，百科给内容；只有节点没有解释，用户还是学不会。",
         size=8.9, bold=True, color=AMBER, line_spacing=1.2)
    footer(s, 5)


# ================= P7 技术架构 =================
def p7():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "05  /  系统基石 · Agent Runtime", "Agent 是 OpenStudy 的基石：一切皆对话",
           "把一句话拆成：角色选择 → 工具调用 → 结果回执 → 记忆与回滚。")
    left = rect(s, M_L, 1.82, 5.55, 4.35, fill=MINT_L2, line=None, radius=0.06)
    text(s, M_L + 0.24, 1.98, 4.8, 0.26, "一条 Agent Loop", size=15.0, bold=True, color=INK)
    steps = [
        ("01", "理解意图", "判断你在问题库、资料、图谱还是计划"),
        ("02", "选择角色", "题库 / 笔记 / 资料 / 统计 / 自定义专家"),
        ("03", "调用工具", "29 个真实业务工具，不只是回文字"),
        ("04", "执行回执", "tool_start / tool_result / 失败自纠正"),
        ("05", "记忆与回滚", "写操作落记忆；可回滚、可追踪"),
    ]
    yy = 2.42
    for n, t, d in steps:
        text(s, M_L + 0.26, yy, 0.34, 0.22, n, size=9, bold=True, color=MINT_D)
        text(s, M_L + 0.66, yy - 0.02, 1.42, 0.24, t, size=11.6, bold=True, color=INK)
        text(s, M_L + 2.05, yy, 3.08, 0.46, d, size=8.9, color=GRAY, line_spacing=1.2)
        yy += 0.76
    x = 6.65
    cards = [
        ("角色编排", "关键词 / 显式指定\n零 LLM 路由 · 可关闭专家"),
        ("29 个真实工具", "建题库 / 查资料 / 读图谱\n排计划 / 导出 / 搜索 / 写文档"),
        ("指挥家 + 子代理", "delegate_task 分派任务\n子代理独立上下文，最多 6 轮"),
        ("可控执行", "写操作 confirmTicket 180 秒\n角色白名单 · 可回滚"),
    ]
    cw = 2.83; ch = 2.05
    for i, (t, d) in enumerate(cards):
        col = i % 2; row = i // 2
        cx = x + col * (cw + 0.20); cy = 1.82 + row * (ch + 0.16)
        card = rect(s, cx, cy, cw, ch, fill=WHITE, line=LINE, lw=0.8, radius=0.06)
        text(s, cx + 0.18, cy + 0.18, cw - 0.36, 0.28, t, size=12.8, bold=True, color=INK)
        text(s, cx + 0.18, cy + 0.60, cw - 0.36, 1.16, d, size=9.1, color=GRAY, line_spacing=1.35)
    strip = rect(s, M_L, 6.30, CW, 0.58, fill=MINT_L, line=None, radius=0.06)
    text(s, M_L + 0.22, 6.36, CW - 0.44, 0.20,
         "一切皆对话：在智能对话里进入题库 / 资料 / 知识图谱 / 规划，系统数据都能被 Agent 调用。",
         size=8.8, bold=True, color=MINT_D)
    text(s, M_L + 0.22, 6.58, CW - 0.44, 0.20,
         "29 个工具 · 5 类官方专家 + 自定义智能体 · 6 步子代理 · 180 秒写确认",
         size=8.2, color=GRAY)
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
    text(s, M_L, 4.82, CW, 0.22,
         "后续评估：Agent 编排从自研 Loop → LangGraph / 更成熟框架；工具协议、确认和回滚边界保持不变。",
         size=8.6, bold=True, color=MINT_D)
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

