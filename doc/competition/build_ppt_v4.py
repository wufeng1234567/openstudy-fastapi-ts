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
DIAGNOSIS = os.path.join(SHOTS, "readme-diagnosis-2026-11-14.png")
PLANNING = os.path.join(SHOTS, "readme-planning-advice.png")
AGENT = os.path.join(SHOTS, "01-agent-chat.png")

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
    text(s, M_L, 0.66, 8.0, 0.24, "OPENSTUDY  ·  0.8.0  ·  知识资产系统", size=10, bold=True, color=MINT_D, spc=160)
    text(s, M_L, 1.02, 7.30, 1.55, "把信息来源，\n整理成可用的知识资产", size=36, bold=True, color=INK, line_spacing=1.06)
    line(s, M_L, 3.02, M_L + 1.15, 3.02, color=MINT, width=2.5)
    text(s, M_L, 3.22, 7.00, 0.82,
         "网页、文档、图片、题库、笔记和网页收藏，\n不再散落成一次性材料。",
         size=14, color=GRAY, line_spacing=1.45)
    text(s, M_L, 4.30, 7.0, 0.42, "对话是入口，知识资产是结果。", size=24, bold=True, color=INK)
    text(s, M_L, 4.82, 7.2, 0.32, "资料诊疗室  /  知识百科  /  知识图谱  /  规划建议", size=13, color=GRAY2)
    line(s, M_L, 5.52, 7.10, 5.52, color=LINE, width=0.5)
    text(s, M_L, 5.68, 7.1, 0.24, "华为云码道 CodeArts 开发  ·  GitCode 开源  ·  FastAPI + Vue 3", size=9.5, color=GRAY2)
    text(s, M_L, 6.18, 7.1, 0.24, "gitcode.com/qi142410131/openstudy-fastapi-ts", size=9, color=MINT_D)
    pic_contain(s, GRAPH, 7.35, 1.10, 5.25, 3.55, caption="真实运行界面 · 主题之间的关系图（点节点可看详情）")
    chip(s, 7.35, 4.88, 1.58, 0.34, "看主题关系", MINT_L, MINT_D, 9)
    chip(s, 9.06, 4.88, 1.86, 0.34, "点节点看来源", MINT_L, MINT_D, 9)
    chip(s, 11.05, 4.88, 1.55, 0.34, "沿关系做规划", MINT_L, MINT_D, 9)
    footer(s, 1)


# ================= P2 用户与问题 =================
def p2():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  用户与问题", "不是缺工具，是信息来源用不起来",
           "先服务三类人：他们手里都有资料，但资料没有变成可复用的知识资产。")
    people = [
        ("01", "边工作边学习、\n需要持续产出的人", "产品 / 研发 / 运营 / 设计 / 研究",
         "资料散在网盘、浏览器和笔记里；写方案找不到原文，AI 回答没出处。", MINT),
        ("02", "高强度备考者", "考研 / 考证 / 公考 / 专业课",
         "题库、错题和资料分家；练完不知道错在哪里，更不知道该补哪一章。", AMBER),
        ("03", "管理团队共享资料的人", "小团队负责人 / 教研 / 项目负责人",
         "版本混乱、重复资料多；新人找不到上下文，关键知识只存在某个人脑子里。", RGBColor(0x5B, 0x7C, 0xD6)),
    ]
    x = M_L; cw = (CW - 2 * 0.22) / 3
    for i, (num, title, roles, pain, col) in enumerate(people):
        card = rect(s, x, 1.94, cw, 2.98, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        text(s, x + 0.24, 2.12, 0.40, 0.28, num, size=12, bold=True, color=col, spc=60)
        text(s, x + 0.24, 2.50, cw - 0.48, 0.58, title, size=16.5, bold=True, color=INK, line_spacing=1.12)
        text(s, x + 0.24, 3.28, cw - 0.48, 0.28, roles, size=9.4, bold=True, color=col, line_spacing=1.15)
        text(s, x + 0.24, 3.70, cw - 0.48, 0.82, pain, size=10.8, color=GRAY, line_spacing=1.4)
        x += cw + 0.22
    quote = rect(s, M_L, 5.10, CW, 0.78, fill=MINT_L2, line=None, radius=0.06)
    rect(s, M_L, 5.10, 0.07, 0.78, fill=MINT)
    text(s, M_L + 0.30, 5.24, 2.0, 0.22, "共同问题", size=9.5, bold=True, color=MINT_D, spc=60)
    text(s, M_L + 1.32, 5.20, CW - 1.65, 0.48,
         "他们不是缺一个聊天框，而是缺一条「获取信息 → 整理 → 验证 → 继续使用」的稳定路径。",
         size=14, bold=True, color=INK, line_spacing=1.2)
    outs = [("可检查", "每条结论能回到原文"), ("可追溯", "每个主题有真实来源"), ("可复用", "资料能进入下一次工作")]
    x = M_L; ow = (CW - 2 * 0.20) / 3
    for t, d in outs:
        line(s, x, 6.24, x + ow - 0.22, 6.24, color=MINT, width=1.2)
        text(s, x, 6.32, ow - 0.22, 0.24, t, size=12, bold=True, color=INK)
        text(s, x, 6.60, ow - 0.22, 0.22, d, size=10, color=GRAY2)
        x += ow + 0.20
    footer(s, 2)


# ================= P3 产品主线 =================
def p3():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  产品方案", "一条从信息来源到知识资产的链路",
           "不靠一个万能聊天框：每一步都有真实数据、真实来源和可继续操作的结果。")
    steps = [
        ("01", "收集", "网页 / 文档 / 图片\n题库 / 笔记"),
        ("02", "解析", "分块 / 章节\n图片 / 向量"),
        ("03", "体检", "四维检查\n问题回原文"),
        ("04", "知识百科", "主题页 / 小节\n来源与版本"),
        ("05", "知识图谱", "五类来源抽取\n主题关系"),
        ("06", "规划建议", "沿真实路径\n给出下一步"),
    ]
    sw = 1.82; gap = (CW - 6 * sw) / 5
    x = M_L
    line(s, M_L + 0.18, 2.30, W - M_L - 0.18, 2.30, color=RGBColor(0xC9, 0xEC, 0xDD), width=1.2)
    for i, (n, t, d) in enumerate(steps):
        active = i in (3, 4, 5)
        card = rect(s, x, 1.90, sw, 1.38, fill=MINT if active else WHITE, line=None if active else LINE, lw=0.75, radius=0.06)
        tc = WHITE if active else INK
        dc = RGBColor(0xDD, 0xF7, 0xEC) if active else GRAY
        text(s, x + 0.14, 2.02, 0.40, 0.22, n, size=9, bold=True, color=dc if active else MINT_D)
        text(s, x + 0.14, 2.28, sw - 0.28, 0.26, t, size=13.5, bold=True, color=tc)
        text(s, x + 0.14, 2.62, sw - 0.28, 0.50, d, size=9.2, color=dc, line_spacing=1.25)
        x += sw + gap
    pic_card(s, SCREENSHOT_2026, M_L, 3.62, 5.75, 2.94, caption="我的资料：资料夹、文档、题库与笔记的统一入口")
    right = rect(s, 6.82, 3.62, 5.72, 2.94, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 7.05, 3.80, 5.25, 0.26, "智能体贯穿全流程", size=15, bold=True, color=INK)
    bullets = [
        "对话里上传的资料，自动进入我的资料，下一次还能继续用。",
        "知识百科的每个主题页保留来源、版本和反向链接。",
        "知识图谱首层只展示知识主题，来源实体在主题详情里展开。",
        "规划建议读取真实图谱关系，不生成不存在的节点和连线。",
    ]
    yy = 4.26
    for b in bullets:
        text(s, 7.08, yy, 0.16, 0.22, "·", size=13, bold=True, color=MINT)
        text(s, 7.30, yy, 4.95, 0.42, b, size=10.4, color=GRAY, line_spacing=1.35)
        yy += 0.48
    footer(s, 3)


# ================= P4 资料诊疗室 =================
def p4():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "03  /  核心能力 · 资料诊疗室", "资料诊疗室：先看问题，再回原文",
           "同一份资料只有一个入口：体检、原文阅读、智能报告都在同一间诊疗室完成。")
    pic_card(s, DIAGNOSIS, M_L, 1.84, 7.55, 3.74, caption="真实运行界面：章节导航、原文阅读、问题清单与报告入口")
    x, y, w, h = 8.58, 1.84, 3.96, 4.58
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "资料先被看懂，再被使用", size=15.5, bold=True, color=INK)
    metrics = [
        ("四维体检", "结构 / 图文 / 知识覆盖 / 可学习化"),
        ("问题清单", "按优先级列出，每条回到原文"),
        ("章节覆盖", "热力图定位内容过薄章节"),
        ("智能报告", "目标 / 优势 / 改进项 / 下一步"),
    ]
    yy = y + 0.62
    for t, d in metrics:
        rect(s, x + 0.22, yy, 0.07, 0.49, fill=MINT, line=None, radius=0.2)
        text(s, x + 0.42, yy, w - 0.62, 0.24, t, size=11.5, bold=True, color=INK)
        text(s, x + 0.42, yy + 0.24, w - 0.62, 0.32, d, size=9.0, color=GRAY, line_spacing=1.2)
        yy += 0.66
    note = rect(s, x + 0.22, y + 3.50, w - 0.44, 0.70, fill=MINT_L2, line=None, radius=0.06)
    fill_text(note, [("原文是事实来源", 11, True, MINT_D), ("AI 只做整理、解释和下一步建议", 9.2, False, GRAY)],
              margins=(0.18, 0.12, 0.10, 0.06), spacing=3)
    text(s, M_L, 6.00, 7.4, 0.26, "体检 → 读原文 → 智能报告：一个入口完成，不用在三个功能间来回找。",
         size=12.5, bold=True, color=MINT_D)
    text(s, M_L, 6.32, 7.4, 0.22, "问题、证据、下一步都在同一份资料上。", size=10.2, color=GRAY)
    footer(s, 4)


# ================= P5 知识百科 + 图谱 =================
def p5():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "04  /  核心能力 · 知识百科与知识图谱", "知识百科 × 知识图谱：让知识看得见关系",
           "知识百科负责读、改、追溯；知识图谱负责把主题之间的关系变成可操作的地图。")
    pic_card(s, GRAPH, M_L, 1.82, 5.95, 3.18, caption="知识主题图：首层只展示知识主题")
    pic_card(s, GRAPH_DETAIL, 6.95, 1.82, 3.02, 3.55, caption="主题详情：来源、相关主题、页面链接")
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
    text(s, M_L + 0.20, 6.14, 5.55, 0.24, "主题页可编辑、有版本、有反链；点开一节能回到原文 chunk。", size=9.6, color=GRAY)
    right_bottom = rect(s, 6.95, 5.72, 5.61, 0.92, fill=WHITE, line=LINE, lw=0.8, radius=0.05)
    text(s, 7.15, 5.86, 5.20, 0.24, "知识图谱", size=12.5, bold=True, color=INK)
    text(s, 7.15, 6.14, 5.20, 0.24, "首层只画知识主题；点击节点查看来源、相关题目和相邻关系。", size=9.6, color=GRAY)
    footer(s, 5)


# ================= P6 规划建议 + Agent =================
def p6():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "05  /  核心能力 · 规划建议", "从真实图谱路径，给出下一步",
           "不是让模型凭空写计划：先沿真实主题关系形成路径，再解释为什么这样建议。")
    pic_card(s, PLANNING, M_L, 1.82, 6.78, 4.72, caption="真实界面：左侧知识图谱路径，右侧可调整的阶段建议")
    x, y, w, h = 7.78, 1.82, 4.75, 4.72
    card = rect(s, x, y, w, h, fill=WHITE, line=LINE, lw=0.9, radius=0.06)
    text(s, x + 0.22, y + 0.18, w - 0.44, 0.24, "建议从哪里来", size=15.5, bold=True, color=INK)
    items = [
        ("真实关系", "先读取主题节点之间的语义关系与来源关联"),
        ("事实路径", "把路径节点、边和起点写进 trace"),
        ("可调整", "建议可保存、查看历史、导出"),
        ("不强迫", "不排打卡任务，不强制跳转刷题"),
    ]
    yy = y + 0.66
    for t, d in items:
        line(s, x + 0.22, yy + 0.28, x + 0.56, yy + 0.28, color=MINT, width=1.2)
        text(s, x + 0.70, yy, w - 0.92, 0.24, t, size=11.3, bold=True, color=INK)
        text(s, x + 0.70, yy + 0.24, w - 0.92, 0.26, d, size=9.5, color=GRAY, line_spacing=1.2)
        yy += 0.70
    strip = rect(s, x + 0.22, y + 3.66, w - 0.44, 0.64, fill=AMBER_L, line=None, radius=0.06)
    text(s, x + 0.36, y + 3.76, w - 0.70, 0.44,
         "没有题库证据时，不生成规划建议。", size=9.8, bold=True, color=AMBER)
    footer(s, 6)


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
    header(s, "07  /  怎么用码道做出来", "码道不是补全插件，是一条可核对的开发流水线",
           "需求进对话，先读后写，改完自测，失败自修，最后按规范提交。")
    chip(s, W - M_L - 2.20, 0.45, 2.20, 0.34, "华为云 · 码道 CodeArts", MINT_L, MINT_D, 9)
    steps = [
        ("①", "需求", "一句话目标\n+ 验收标准"),
        ("②", "接入", "git status\n分支确认"),
        ("③", "读码", "grep / read\n先定位再动手"),
        ("④", "写测", "developer-test-agent\n补测试"),
        ("⑤", "审查", "diff / 安全审查\nP0-P2 报告"),
        ("⑥", "修复", "/bugfix\n回归通过再提交"),
        ("⑦", "提交", "git commit / push\n中文提交信息"),
        ("⑧", "沉淀", "experience / export\n可复用记忆"),
    ]
    nw = 1.31; gap = 0.16
    total = 8 * nw + 7 * gap
    x = M_L + (CW - total) / 2
    y = 1.94
    for i, (num, t, d) in enumerate(steps):
        active = i in (4, 5)
        card = rect(s, x, y, nw, 1.66, fill=AMBER_L if active else WHITE, line=AMBER if active else LINE, lw=1.0, radius=0.06)
        text(s, x + 0.10, y + 0.12, 0.32, 0.28, num, size=14, bold=True, color=AMBER if active else MINT)
        text(s, x + 0.10, y + 0.46, nw - 0.20, 0.28, t, size=13, bold=True, color=INK)
        text(s, x + 0.10, y + 0.86, nw - 0.20, 0.62, d, size=8.0, color=GRAY, line_spacing=1.25)
        x += nw + gap
    sup = rect(s, M_L, 3.88, CW, 0.60, fill=MINT_L2, line=None, radius=0.08)
    text(s, M_L + 0.28, 4.03, CW - 0.56, 0.26,
         "支撑能力：规则 AGENTS.md  ·  技能 SKILL.md  ·  经验 experience  ·  沙箱 / 权限  ·  checkpoint / undo",
         size=11.2, bold=True, color=MINT_D)
    text(s, M_L, 4.72, CW, 0.28,
         "真实开发窗口：2026-10-08 → 10-12  ·  11 个项目会话  ·  134 轮需求  ·  3,248 次工具调用  ·  186 个文件改写  ·  50 次 Git 提交",
         size=10.3, bold=True, color=AMBER)
    ev = rect(s, M_L, 5.24, CW, 1.28, fill=WHITE, line=LINE, lw=0.8, radius=0.06)
    text(s, M_L + 0.26, 5.40, 4.0, 0.24, "过程记录可核对", size=11.5, bold=True, color=INK)
    evidence = [
        ("会话", "11 个项目会话，可导出原始对话"),
        ("工具", "629 次读 / 476 次改 / 1,658 次命令"),
        ("产物", "doc/dev-process/ 日志、决策、diff、提交"),
    ]
    x = M_L + 0.26
    for t, d in evidence:
        text(s, x, 5.76, 0.50, 0.22, t, size=9.3, bold=True, color=MINT_D)
        text(s, x + 0.54, 5.75, 3.30, 0.38, d, size=9.2, color=GRAY, line_spacing=1.2)
        x += 3.68
    text(s, M_L, 6.72, CW, 0.24, "人负责「对不对」：场景、判断、真机验收；码道负责「快不快」：读码、改写、自测、提交。",
         size=9.5, color=GRAY2)
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


for fn in (p1, p2, p3, p4, p5, p6, p7, p8, p9, p10):
    fn()

out = os.path.join(HERE, "OpenStudy-10页-码道版.pptx")
prs.save(out)
print("saved:", out, os.path.getsize(out))
