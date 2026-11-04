# -*- coding: utf-8 -*-
"""OpenStudy 10 页方案（V3）· 浅色高级感 · 突出码道 CodeArts 开发能力
运行：openstudy-fastapi/.venv/Scripts/python.exe build_ppt_v3.py
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(os.path.dirname(HERE), "screenshots")

# ---------------- 设计令牌（浅色 · 薄荷绿） ----------------
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
M_L = 0.85
CW = W - 2 * M_L


def fs(size):
    """统一放大字号：小字放大更多，标题小幅放大。"""
    if size <= 8.5:
        return 11
    if size <= 9.5:
        return 12
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
    if size <= 27:
        return 29
    if size <= 32:
        return 34
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
    """parts: [(text, size, bold, color), ...] 每项一段"""
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
    text(slide, M_L, 0.50, CW, 0.22, kicker, size=9.5, bold=True, color=MINT_D, spc=140)
    text(slide, M_L, 0.80, CW, 0.68, title, size=27, bold=True, color=INK, line_spacing=1.05)
    if lede:
        text(slide, M_L, 1.50, CW, 0.32, lede, size=11.5, color=GRAY, line_spacing=1.2)


def footer(slide, idx):
    line(slide, M_L, 6.98, W - M_L, 6.98, color=LINE, width=0.5)
    text(slide, M_L, 7.06, 6.0, 0.2, "OpenStudy · 把不会的问到会", size=8, color=GRAY2)
    text(slide, W - M_L - 1.2, 7.06, 1.2, 0.2, f"{idx:02d} / 10", size=8, color=GRAY2, align=PP_ALIGN.RIGHT)


def pic_card(slide, path, x, y, w, h, caption=None, border=True):
    key = (path, round(w, 3), round(h, 3))
    dst_dir = os.path.join(HERE, "_crop_cache_v3")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"crop_{abs(hash(key)) % 10**8}.jpg")
    if not os.path.exists(dst):
        im = Image.open(path).convert("RGB")
        iw, ih = im.size
        target = w / h
        if iw / ih > target:
            nw = int(ih * target); left = (iw - nw) // 2; box = (left, 0, left + nw, ih)
        else:
            nh = int(iw / target); top = (ih - nh) // 2; box = (0, top, iw, top + nh)
        im.crop(box).save(dst, quality=92)
    pic = slide.shapes.add_picture(dst, Inches(x), Inches(y), Inches(w), Inches(h))
    if border:
        rect(slide, x, y, w, h, fill=None, line=LINE, lw=0.75, radius=0.02)
    if caption:
        text(slide, x, y + h + 0.08, w, 0.2, caption, size=8, color=GRAY2)
    return pic


def chip(slide, x, y, w, h, label, fill=MINT_L, fg=MINT_D, size=8.5):
    shp = rect(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    fill_text(shp, [(label, size, True, fg)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
              margins=(0.04, 0.04, 0.02, 0.02))
    return shp


def anim(slide, name, shape):
    shape.name = name
    return shape


# ---------------- 构建 ----------------
prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]

S1 = os.path.join(SHOTS, "01-agent-chat.png")
S2 = os.path.join(SHOTS, "03-question-practice.png")
S3 = os.path.join(SHOTS, "05-stats.png")
S4 = os.path.join(SHOTS, "07-rag-config.png")
S5 = os.path.join(SHOTS, "04-bank-detail.png")
S6 = os.path.join(SHOTS, "18-workspace-folder-search.png")
S7 = os.path.join(SHOTS, "20-micro-course-html.png")


# ============ P1 封面 ============
def p1():
    s = prs.slides.add_slide(BLANK); bg(s)
    # 装饰
    rect(s, 10.6, -2.1, 5.4, 5.4, fill=None, line=RGBColor(0xE3, 0xF4, 0xEC), lw=1.0, radius=0.5)
    rect(s, 11.9, 3.3, 3.6, 3.6, fill=None, line=RGBColor(0xEF, 0xF9, 0xF4), lw=1.0, radius=0.5)
    text(s, M_L, 0.78, 7.0, 0.24, "OPENSTUDY  ·  AI 学习智能体", size=9.5, bold=True, color=MINT_D, spc=160)
    t1 = text(s, M_L, 1.18, 7.0, 1.55, "把不会的，\n问到会", size=46, bold=True, color=INK, line_spacing=1.08)
    anim(s, "p1_title", t1)
    line(s, M_L, 2.92, M_L + 1.15, 2.92, color=MINT, width=2.5)
    text(s, M_L, 3.16, 6.2, 0.95, "会读你资料的 AI 学习平台\n从一份 Word，到一套能刷的题、能讲的课、能打印的讲义",
         size=14, color=GRAY, line_spacing=1.5)

    stats = [("33", "份资料"), ("12", "个资料夹"), ("31", "个题库"), ("3,248", "次码道调用")]
    x = M_L
    for num, lab in stats:
        text(s, x, 4.58, 1.66, 0.52, num, size=25, bold=True, color=INK, font=FONT_L)
        text(s, x, 5.10, 1.66, 0.22, lab, size=9, color=GRAY2)
        x += 1.66
    line(s, M_L, 5.66, 6.9, 5.66, color=LINE, width=0.5)
    text(s, M_L, 5.82, 6.6, 0.24, "华为云码道 CodeArts 开发  ·  GitCode 开源  ·  FastAPI + Vue 3", size=9, color=GRAY2)
    text(s, M_L, 6.72, 6.6, 0.24, "gitcode.com/qi142410131/openstudy-fastapi-ts", size=8.5, color=MINT_D)
    # 截图
    sh = pic_card(s, S1, 7.42, 1.12, 5.05, 3.16, caption="真实运行界面  ·  对话即入口")
    anim(s, "p1_shot", sh)
    chip(s, 7.42, 4.72, 1.45, 0.34, "资料即资产", MINT_L, MINT_D, 9)
    chip(s, 8.99, 4.72, 2.02, 0.34, "一份资料四种产出", MINT_L, MINT_D, 9)
    chip(s, 11.13, 4.72, 1.35, 0.34, "对话即入口", MINT_L, MINT_D, 9)
    footer(s, 1)


# ============ P2 场景与痛点 ============
def p2():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  场景价值", "学生不缺题，缺的是「把资料变成题」",
           "面向高校学生与自学者：手里有课件、真题、教材，却没有一条把资料变成练习的路。")
    cards = [
        ("01", "资料在硬盘里，题在纸上", "Word / PDF / 扫描件占大多数；手动录 20 道题约 1 小时，公式和图还会丢。", "耗时"),
        ("02", "错题越积越多，掌握率起不来", "演示账号真实数据：累计作答 299 次、正确率 49.5%、待消灭错题 40 道、已掌握 0 道。", "无效"),
        ("03", "通用 AI 只会聊，不会「办事」", "能解释知识点，却不能建题库、不能出卷、不能改错题本——聊完还得自己动手。", "断层"),
    ]
    x = M_L; cw = (CW - 2 * 0.24) / 3
    for i, (num, t, d, tag) in enumerate(cards):
        card = rect(s, x, 2.02, cw, 2.55, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p2_card_{i+1}", card)
        text(s, x + 0.26, 2.22, 0.8, 0.28, num, size=11, bold=True, color=AMBER, spc=60)
        text(s, x + 0.26, 2.58, cw - 0.52, 0.62, t, size=15, bold=True, color=INK, line_spacing=1.22)
        text(s, x + 0.26, 3.28, cw - 0.52, 0.95, d, size=9.5, color=GRAY, line_spacing=1.45)
        chip(s, x + 0.26, 4.18, 0.62, 0.26, tag, AMBER_L, AMBER, 8)
        x += cw + 0.24
    # 用户原话
    q = rect(s, M_L, 4.94, CW, 0.78, fill=MINT_L2, line=None, radius=0.06)
    anim(s, "p2_quote", q)
    rect(s, M_L, 4.94, 0.06, 0.78, fill=MINT)
    text(s, M_L + 0.30, 5.10, 1.0, 0.24, "用户原话", size=8.5, bold=True, color=MINT_D, spc=70)
    text(s, M_L + 1.18, 5.06, CW - 1.5, 0.42, "“我只想把我自己的资料变成能刷的题，并且告诉我下一步练什么。”",
         size=13, bold=True, color=INK, line_spacing=1.2)
    # 三个结论
    outs = [("资料即题库", "上传即解析入库，AI 依据原文出题并标注出处"),
            ("练习即诊断", "每道错题进错题本，统计到知识点"),
            ("对话即操作", "一句话建库、组卷、排计划，全部落库")]
    x = M_L; ow = (CW - 2 * 0.2) / 3
    for t, d in outs:
        line(s, x, 6.02, x + ow - 0.2, 6.02, color=MINT, width=1.2)
        text(s, x, 6.10, ow - 0.2, 0.24, t, size=11, bold=True, color=INK)
        text(s, x, 6.38, ow - 0.2, 0.36, d, size=8.5, color=GRAY, line_spacing=1.3)
        x += ow + 0.2
    footer(s, 2)


# ============ P3 产品方案 ============
def p3():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  产品方案", "一份资料进，一套练习出",
           "不做又一个聊天框，也不做又一个题库——把 AI 接到真实业务表上，每一步都可执行。")
    steps = [
        ("①", "上传资料", "Word / PDF / MD\n含公式与内嵌图"),
        ("②", "解析入库", "分块 · 向量化\n混合检索可命中"),
        ("③", "建库出题", "按原文出题\n标注出处"),
        ("④", "刷题模考", "顺序 / 随机\n错题 / 模拟考"),
        ("⑤", "诊断计划", "薄弱点 TOP5\n下一步练什么"),
    ]
    sw = 2.02; gap = (CW - 5 * sw) / 4
    x = M_L
    line(s, M_L + 0.25, 2.42, W - M_L - 0.25, 2.42, color=RGBColor(0xC9, 0xEC, 0xDD), width=1.2)
    for i, (n, t, d) in enumerate(steps):
        fill = MINT if i == 2 else WHITE
        tc = WHITE if i == 2 else INK
        dc = RGBColor(0xDD, 0xF7, 0xEC) if i == 2 else GRAY
        card = rect(s, x, 1.98, sw, 1.25, fill=fill, line=None if i == 2 else LINE, lw=0.75, radius=0.06)
        anim(s, f"p3_step_{i+1}", card)
        fill_text(card, [(f"{n}  {t}", 13, True, tc), (d, 9, False, dc)],
                  margins=(0.18, 0.12, 0.12, 0.10), anchor=MSO_ANCHOR.MIDDLE)
        x += sw + gap
    # 两张产品图
    pic_card(s, S2, M_L, 3.48, 5.62, 3.15, caption="题库练习：随机 / 错题 / 模拟考，答题卡实时进度")
    pic_card(s, S3, 6.86, 3.48, 5.62, 3.15, caption="学习统计：正确率、趋势、薄弱点 TOP5")
    footer(s, 3)


# ============ P4 产品完成度 ============
def p4():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "03  /  产品完成度", "四条主线，现场都能走通",
           "不是功能清单堆砌——每条主线都闭环到「用户能拿到结果」，并且有探针守着不回归。")
    cards = [
        ("A", "题库与考试", "建库 / 组卷 / 顺序·随机·错题·模拟考；答题卡、自动判分、考试记录。", "20+ 接口"),
        ("B", "知识库 RAG", "Word/PDF/MD 解析 → 分块 → 向量化 → 混合检索；原文出题、标注出处。", "bge-m3 · 1024 维"),
        ("C", "学习闭环", "错题本、收藏、斩题、笔记草稿、学习统计、薄弱知识点 TOP5。", "31 题库 / 299 作答"),
        ("D", "智能体", "多专家并行、写操作二次确认、一键回退、跨会话长期记忆。", "20+ 工具 / 5 类专家"),
    ]
    x0 = M_L; y0 = 2.02; cw = 2.74; ch = 2.35; gap = 0.22
    for i, (tag, t, d, badge) in enumerate(cards):
        x = x0 + i * (cw + gap)
        card = rect(s, x, y0, cw, ch, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p4_card_{i+1}", card)
        text(s, x + 0.22, y0 + 0.18, 0.5, 0.30, tag, size=20, bold=True, color=MINT, font=FONT_L)
        text(s, x + 0.22, y0 + 0.62, cw - 0.44, 0.28, t, size=14, bold=True, color=INK)
        text(s, x + 0.22, y0 + 1.00, cw - 0.44, 1.00, d, size=9.3, color=GRAY, line_spacing=1.45)
        text(s, x + 0.22, y0 + 2.00, cw - 0.44, 0.22, badge, size=8.5, bold=True, color=MINT_D, spc=30)
    # 指标条
    strip = rect(s, M_L, 4.62, CW, 1.00, fill=MINT_L2, line=None, radius=0.06)
    anim(s, "p4_strip", strip)
    metrics = [("32", "个 API 模块"), ("156", "个后端源文件 · 4.9 万行"), ("45", "个自动化探针"), ("200+", "次 Git 提交")]
    x = M_L + 0.35
    for num, lab in metrics:
        text(s, x, 4.80, 2.5, 0.34, num, size=19, bold=True, color=INK, font=FONT_L)
        text(s, x, 5.20, 2.5, 0.2, lab, size=8.2, color=GRAY2)
        x += 2.86
    text(s, M_L, 6.10, CW, 0.24, "所有数字来自真实运行数据；关键链路都有探针，改完就跑、零 LLM 成本。", size=9, color=GRAY)
    footer(s, 4)


# ============ P5 技术架构 ============
def p5():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "04  /  技术实现", "轻量自研，把「可控」写进架构",
           "不引入重型编排框架：路由零 LLM 成本、工具契约统一、写操作可确认可回退。")
    bands = [
        ("前端  Vue 3 + TS", "对话页 / 题库 / 知识库抽屉 / 学习统计 · 单一设计令牌体系"),
        ("流式网关", "纯 ASGI 中间件 · SSE 逐字下发（修掉「攒批」造成的假流式）"),
        ("Agent Runtime", "Orchestrator（关键词路由，零 LLM）→ 5 类专家 → 20+ 工具"),
        ("RAG 检索", "解析 → jieba 分块 → bge-m3（1024 维）→ HNSW + tsvector → RRF（k=60）"),
        ("数据层", "PostgreSQL + pgvector · Redis · 本地/对象存储"),
    ]
    y = 1.96
    for i, (t, d) in enumerate(bands):
        b = rect(s, M_L, y, 7.20, 0.80, fill=MINT_L2 if i == 2 else WHITE, line=LINE, lw=0.75, radius=0.04)
        anim(s, f"p5_band_{i+1}", b)
        text(s, M_L + 0.22, y + 0.09, 1.55, 0.24, t, size=10, bold=True, color=MINT_D if i == 2 else INK)
        text(s, M_L + 1.80, y + 0.06, 5.20, 0.64, d, size=9.0, color=INK2 if i == 2 else GRAY, line_spacing=1.35)
        y += 0.87
    # 右侧创新
    text(s, 8.42, 1.94, 4.1, 0.24, "三个能讲清楚的创新点", size=9.5, bold=True, color=GRAY2, spc=60)
    inns = [
        ("01", "多专家并行，单专家隐身", "一轮里并发多个 delegate；≥2 个专家才展开工作组卡片，1 个就融进主答。"),
        ("02", "让知识库「看得见图」", "文档内嵌图按【图N】归属到分块；喂模型用 data URL，落盘路径只用于回插。"),
        ("03", "写操作可确认、可回退", "confirm_ticket 二次确认 + 四域整树快照；回退不了的操作明确告知。"),
    ]
    y = 2.30
    for n, t, d in inns:
        text(s, 8.42, y, 0.4, 0.24, n, size=9, bold=True, color=MINT, spc=40)
        text(s, 8.80, y - 0.03, 3.65, 0.26, t, size=12, bold=True, color=INK)
        text(s, 8.80, y + 0.28, 3.65, 0.80, d, size=8.8, color=GRAY, line_spacing=1.4)
        y += 1.18
    # 底部指标
    line(s, M_L, 6.50, W - M_L, 6.50, color=LINE, width=0.5)
    tech = [("0", "次 LLM 用于路由"), ("1,658", "次命令 / 5 天（码道）"), ("45", "个探针 · 零 LLM 成本"), ("20+", "个智能体工具")]
    x = M_L
    for n, l in tech:
        text(s, x, 6.58, 2.6, 0.24, n, size=12.5, bold=True, color=INK)
        text(s, x, 6.84, 2.6, 0.18, l, size=7.5, color=GRAY2)
        x += 2.9
    footer(s, 5)


# ============ P6 码道开发总览 ============
def p6():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "05  /  码道开发", "码道不是补全插件，是一条完整的 AI 编码流水线",
           "从需求到沉淀，8 个环节分别对应一项码道能力，每一步都有可核对的产物。")
    chip(s, W - M_L - 2.02, 0.52, 2.02, 0.34, "华为云 · 码道 CodeArts", MINT_L, MINT_D, 9)
    nodes = [
        ("①", "需求", "用户目标 · 一句话"),
        ("②", "接入", "git status · 分支"),
        ("③", "读码", "语义检索"),
        ("④", "写测", "developer-test-agent"),
        ("⑤", "审查", "diff · security_audit"),
        ("⑥", "修复", "/bugfix 修复专家"),
        ("⑦", "提交", "git commit / push"),
        ("⑧", "沉淀", "experience · export"),
    ]
    nw = 1.31; gap = 0.16
    total = 8 * nw + 7 * gap
    x = M_L + (CW - total) / 2
    y = 2.02
    for i, (num, t, d) in enumerate(nodes):
        fill = AMBER_L if i in (4, 5) else WHITE
        bd = AMBER if i in (4, 5) else LINE
        card = rect(s, x, y, nw, 1.75, fill=fill, line=bd, lw=1.0, radius=0.06)
        anim(s, f"p6_node_{i+1}", card)
        text(s, x + 0.10, y + 0.13, 0.36, 0.30, num, size=15, bold=True, color=AMBER if i in (4, 5) else MINT)
        text(s, x + 0.10, y + 0.50, nw - 0.20, 0.30, t, size=13.5, bold=True, color=INK)
        text(s, x + 0.10, y + 0.94, nw - 0.20, 0.66, d, size=7.4, color=GRAY, line_spacing=1.25)
        x += nw + gap
    # 支撑带
    sup = rect(s, M_L, 4.15, CW, 0.66, fill=MINT_L2, line=None, radius=0.08)
    anim(s, "p6_support", sup)
    text(s, M_L + 0.30, 4.31, CW - 0.6, 0.26,
         "支撑能力：规则 AGENTS.md  ·  技能 SKILL.md  ·  经验 experience  ·  沙箱 / 权限  ·  checkpoint / undo",
         size=11.5, bold=True, color=MINT_D)
    # 说明
    text(s, M_L, 5.02, 6.2, 0.26, "审查无 P0/P1 直接提交；有则修复并回归。任一步失败即停下说明。", size=9.5, color=GRAY)
    # 数据卡
    stats = [("3,248", "次工具调用"), ("186", "个文件被改写"), ("17", "个项目会话"), ("5", "天连续开发")]
    x = M_L
    for idx_stat, (num, lab) in enumerate(stats):
        b = rect(s, x, 5.46, 2.74, 0.98, fill=WHITE, line=LINE, lw=0.75, radius=0.06)
        anim(s, f"p6_stat_{idx_stat+1}", b)
        text(s, x + 0.22, 5.58, 2.2, 0.38, num, size=21, bold=True, color=INK, font=FONT_L)
        text(s, x + 0.22, 6.00, 2.2, 0.2, lab, size=8.6, color=GRAY2)
        x += 2.88
    footer(s, 6)


# ============ P7 能力 → 模块 ============
def p7():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "06  /  码道怎么用", "用码道的哪个能力，开发了哪块系统",
           "不是功能清单，是实际开发中的分工：每张卡都是「功能 → 模块 → 怎么用 → 结果」。")
    cards = [
        ("子代理 · 测试", "题库与考试链路", "developer-test-agent 生成 58 条单测，覆盖两条清洗路径。", "→ 58 passed"),
        ("修复专家", "智能体工具链", "/bugfix 按 bug 单定位并修复降级正则，回归通过后才提交。", "→ P1 修复"),
        ("语义检索 · 索引", "Agent Runtime / RAG", "CodeSemanticSearch + 代码库索引，先读后写，跨 200+ 文件定位。", "→ file:line"),
        ("规则 · 技能", "团队协作规范", "AGENTS.md 写规则、SKILL.md 写流程，随仓库分发，换人也能照着做。", "→ 8 步流程"),
        ("会话", "长任务调试", "/fork 从任意消息分叉，/timeline 回跳，/export 导出。", "→ 可追溯"),
        ("GitCode · git", "提交与交付", "分支开发、中文提交、推送远端，一次完成。", "→ 596959b"),
    ]
    cw = (CW - 2 * 0.22) / 3; ch = 1.95
    for i, (tag, title, desc, result) in enumerate(cards):
        col = i % 3; row = i // 3
        x = M_L + col * (cw + 0.22); y = 1.98 + row * (ch + 0.16)
        card = rect(s, x, y, cw, ch, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p7_card_{i+1}", card)
        chip(s, x + 0.22, y + 0.16, 1.34, 0.26, tag, MINT_L, MINT_D, 8)
        text(s, x + 0.22, y + 0.54, cw - 0.44, 0.28, title, size=13, bold=True, color=INK)
        text(s, x + 0.22, y + 0.90, cw - 0.44, 0.66, desc, size=9.0, color=GRAY, line_spacing=1.4)
        text(s, x + 0.22, y + 1.60, cw - 0.44, 0.22, result, size=9.0, bold=True, color=AMBER)
    strip = rect(s, M_L, 6.10, CW, 0.42, fill=MINT_L2, line=None, radius=0.08)
    text(s, M_L + 0.24, 6.19, CW - 0.48, 0.24,
         "一张卡就是一条链路：码道功能 → 开发的系统模块 → 怎么用 → 可核对结果。",
         size=9.2, bold=True, color=MINT_D)
    footer(s, 7)


# ============ P8 真实案例 ============
def p8():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "07  /  一个真实案例", "一个安全缺陷，从测试到提交",
           "html_sanitize 的降级正则漏检 data: 协议——AI 自己写测试、自己发现问题、自己修、自己验证。")
    nodes = [
        ("08:40", "提需求", "给 html_sanitize 补测试，覆盖两条清洗路径"),
        ("08:55", "读码", "定位 html_sanitize.py"),
        ("09:10", "写测", "57 passed, 1 xfailed"),
        ("09:20", "审查", "P1：data: 协议漏检"),
        ("09:35", "修复", "/bugfix 改协议分支"),
        ("09:50", "提交", "58 passed · 596959b"),
    ]
    nw = 1.78; gap = 0.18
    total = 6 * nw + 5 * gap
    x = M_L + (CW - total) / 2; y = 2.05
    line(s, x + 0.2, y + 0.30, x + total - 0.2, y + 0.30, color=RGBColor(0xC9, 0xEC, 0xDD), width=1.5)
    for i, (t, h, d) in enumerate(nodes):
        col = AMBER if i == 3 else MINT
        dot = rect(s, x + nw / 2 - 0.09, y + 0.21, 0.18, 0.18, fill=col, line=None, radius=0.5)
        anim(s, f"p8_dot_{i+1}", dot)
        card = rect(s, x, y + 0.58, nw, 1.55, fill=WHITE, line=AMBER if i == 3 else LINE, lw=1.0 if i == 3 else 0.75, radius=0.05)
        anim(s, f"p8_card_{i+1}", card)
        text(s, x + 0.14, y + 0.70, nw - 0.28, 0.20, t, size=8, bold=True, color=col, spc=20)
        text(s, x + 0.14, y + 0.94, nw - 0.28, 0.26, h, size=12, bold=True, color=INK)
        text(s, x + 0.14, y + 1.26, nw - 0.28, 0.74, d, size=8.6, color=GRAY, line_spacing=1.3)
        x += nw + gap
    # 底部对比数字
    band = rect(s, M_L, 4.45, CW, 1.45, fill=MINT_L2, line=None, radius=0.08)
    anim(s, "p8_band", band)
    nums = [("57", "个通过的用例"), ("1", "个 xfailed（真实缺陷）"), ("58", "修复后全部通过"), ("1", "次提交 + 推送")]
    x = M_L + 0.40
    for num, lab in nums:
        text(s, x, 4.64, 2.6, 0.46, num, size=26, bold=True, color=INK, font=FONT_L)
        text(s, x, 5.14, 2.6, 0.24, lab, size=8.8, color=GRAY2)
        x += 2.86
    text(s, M_L, 6.15, CW, 0.5,
         "过程产物：test_html_sanitize.py（315 行） · 修复 diff · 58 passed · commit 596959b——每一步都可核对。",
         size=9.5, color=GRAY)
    footer(s, 8)


# ============ P9 现场演示 ============
def p9():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "08  /  现场演示", "3 分钟，看四次「它真的动了」",
           "不追求功能全，只追求一件事：让观众在 3 分钟内看到「AI 真的动了我的数据」。")
    stages = [
        ("0:00 – 0:40", "看得见处理", "上传一份含公式与图片的 Word", "知识库面板实时显示解析进度；点开分块，公式与图片都在。"),
        ("0:40 – 1:30", "看得见结果", "一句话：「用这份资料建个题库，出 10 道题」", "两位专家并行，写操作先弹确认卡，确认后题目落库。"),
        ("1:30 – 2:20", "看得见闭环", "开考 → 交卷 → 错题本 → 学习统计", "自动判分；错题进本；薄弱点 TOP5 立刻更新。"),
        ("2:20 – 3:00", "看得见智能", "「按我的薄弱点排一周复习计划」", "读取真实统计，给出按天计划，一键写进错题本。"),
    ]
    cw = (CW - 3 * 0.18) / 4
    for i, (t, h, act, res) in enumerate(stages):
        x = M_L + i * (cw + 0.18)
        card = rect(s, x, 1.98, cw, 2.35, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p9_card_{i+1}", card)
        text(s, x + 0.22, 2.12, cw - 0.44, 0.22, t, size=8.4, bold=True, color=MINT_D, spc=30)
        text(s, x + 0.22, 2.38, cw - 0.44, 0.26, h, size=12.5, bold=True, color=INK)
        text(s, x + 0.22, 2.72, cw - 0.44, 0.70, act, size=9.0, color=INK2, line_spacing=1.4)
        line(s, x + 0.22, 3.44, x + cw - 0.22, 3.44, color=LINE, width=0.5)
        text(s, x + 0.22, 3.54, cw - 0.44, 0.72, res, size=8.7, color=GRAY, line_spacing=1.45)
    text(s, M_L, 4.58, 6.0, 0.24, "演示稳定性：把「万一」提前处理掉", size=9.5, bold=True, color=GRAY2, spc=40)
    guards = [("预置数据", "演示账号预置 31 个题库 / 299 条作答，开场即有内容"),
              ("提前热身", "演示前 2 小时跑 daily-start.sh，预热模型与检索（首字 45s → 2.8s）"),
              ("双保险", "网络异常切本地录屏；关键链路探针，演示前 10 分钟全跑一遍")]
    x = M_L; gw = (CW - 2 * 0.18) / 3
    for t, d in guards:
        text(s, x, 4.90, gw, 0.24, "· " + t, size=9, bold=True, color=INK)
        text(s, x + 0.14, 5.20, gw - 0.14, 0.60, d, size=8.2, color=GRAY, line_spacing=1.4)
        x += gw + 0.18
    strip = rect(s, M_L, 6.20, CW, 0.42, fill=MINT_L, line=None, radius=0.08)
    text(s, M_L + 0.20, 6.29, CW - 0.4, 0.24,
         "一句话记住：先给结果，再讲技术；每按一次按钮，都要有一处数据变化被看见。",
         size=9.0, bold=True, color=MINT_D)
    footer(s, 9)


# ============ P10 迭代与团队 ============
def p10():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "09  /  迭代与团队", "下一步：把「能用」做成「好用」",
           "30 天与 90 天的路线都来自真实使用中发现的边界，不是拍脑袋的功能清单。")
    cols = [
        ("已交付 · 本轮", "DONE", ["多智能体协同（指挥家 + 5 类专家）", "知识库图文解析与原文出题", "模拟考试、错题本、学情诊断", "写操作确认 + 四域回退"], INK),
        ("30 天 · 补能力", "NEXT", ["扫描版 PDF 接入 OCR", "多模态向量：以图搜图", "移动端适配与消息中心", "评测期限流与稳定性加固"], MINT_D),
        ("90 天 · 上规模", "LATER", ["校园版多租户与教师端", "对象存储直传（OBS）", "题库/笔记开放 API", "接入更多华为云能力"], GRAY2),
    ]
    cw = (CW - 2 * 0.20) / 3
    for i, (t, tag, items, col) in enumerate(cols):
        x = M_L + i * (cw + 0.20)
        card = rect(s, x, 1.96, cw, 2.85, fill=MINT_L2 if tag == "NEXT" else WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p10_col_{i+1}", card)
        text(s, x + 0.24, 2.12, cw - 0.48, 0.22, tag, size=7.5, bold=True, color=col, spc=80)
        text(s, x + 0.24, 2.38, cw - 0.48, 0.26, t, size=13, bold=True, color=INK)
        y = 2.82
        for it in items:
            text(s, x + 0.24, y, 0.16, 0.22, "·", size=9, color=col)
            text(s, x + 0.42, y, cw - 0.66, 0.44, it, size=8.7, color=GRAY, line_spacing=1.35)
            y += 0.47
    text(s, M_L, 5.18, 5.6, 0.24, "团队分工（按真实职责，可一人多岗）", size=9.5, bold=True, color=GRAY2, spc=40)
    roles = [("产品 / 后端", "场景定义、Agent 与 RAG 后端、数据与部署"),
             ("前端 / 交互", "对话体验、题库与知识库面板、设计令牌"),
             ("测试 / 演示", "探针与回归、演示脚本、材料与讲解")]
    rw = (CW - 2 * 0.18) / 3
    for i, (t, d) in enumerate(roles):
        x = M_L + i * (rw + 0.18)
        line(s, x, 5.50, x + rw - 0.18, 5.50, color=MINT, width=1.0)
        text(s, x, 5.58, rw - 0.18, 0.24, t, size=9.5, bold=True, color=INK)
        text(s, x, 5.84, rw - 0.18, 0.40, d, size=7.6, color=GRAY, line_spacing=1.35)
    line(s, M_L, 6.36, W - M_L, 6.36, color=LINE, width=0.5)
    text(s, M_L, 6.48, 6.6, 0.32, "谢谢。欢迎现场提问，也欢迎直接上手体验。", size=11.5, bold=True, color=INK)
    text(s, M_L, 6.84, 7.2, 0.20, "作品源码：gitcode.com/qi142410131/openstudy-fastapi-ts", size=8, color=GRAY2)
    b = rect(s, 9.55, 6.44, 3.05, 0.50, fill=MINT, line=None, radius=0.12)
    text(s, 9.55, 6.56, 3.05, 0.26, "OpenStudy · 把不会的问到会", size=8.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    footer(s, 10)


# ============ 迭代版：P2 / P3 / P4 / P9 / P10 ============
def p2b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "01  /  场景价值", "学生不缺资料，缺的是「把资料变成可用的资产」",
           "手里有课件、真题、聊天里传来的附件，却没有一条把资料变成题目、讲义、微课的路。")
    cards = [
        ("01", "资料散落，找不到", "文件名没信息、文件夹越建越乱、聊天附件用完就丢——想再用一次，只能重新翻。", "散"),
        ("02", "一份资料只用一次", "图片、公式、表格散落在文档里；想用到题目、讲义、微课，要重新找、重新截。", "断"),
        ("03", "通用 AI 只会聊", "能解释知识点，却不能建题库、不能做讲义、不能生成微课——聊完还得自己动手。", "空"),
    ]
    x = M_L; cw = (CW - 2 * 0.24) / 3
    for i, (num, t, d, tag) in enumerate(cards):
        card = rect(s, x, 2.02, cw, 2.52, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p2b_card_{i+1}", card)
        text(s, x + 0.26, 2.22, 0.8, 0.28, num, size=11, bold=True, color=AMBER, spc=60)
        text(s, x + 0.26, 2.58, cw - 0.52, 0.62, t, size=15, bold=True, color=INK, line_spacing=1.22)
        text(s, x + 0.26, 3.28, cw - 0.52, 0.95, d, size=9.5, color=GRAY, line_spacing=1.45)
        chip(s, x + 0.26, 4.14, 0.62, 0.26, tag, AMBER_L, AMBER, 8)
        x += cw + 0.24
    q = rect(s, M_L, 4.92, CW, 0.78, fill=MINT_L2, line=None, radius=0.06)
    anim(s, "p2b_quote", q)
    rect(s, M_L, 4.92, 0.06, 0.78, fill=MINT)
    text(s, M_L + 0.30, 5.08, 1.0, 0.24, "用户原话", size=8.5, bold=True, color=MINT_D, spc=70)
    text(s, M_L + 1.18, 5.04, CW - 1.5, 0.42, "“我只想把我自己的资料，变成能刷的题、能讲的课、能打印的讲义。”",
         size=13, bold=True, color=INK, line_spacing=1.2)
    outs = [("资料即资产", "上传就拆成标题、公式、表格、图片，每份都有来源"),
            ("一份资料多种产出", "题库、讲义、资料微课、教学微课，全都复用同一份资料"),
            ("对话即入口", "聊天里传过的资料，自动进「我的资料」，还能再用")]
    x = M_L; ow = (CW - 2 * 0.2) / 3
    for t, d in outs:
        line(s, x, 6.02, x + ow - 0.2, 6.02, color=MINT, width=1.2)
        text(s, x, 6.10, ow - 0.2, 0.24, t, size=11, bold=True, color=INK)
        text(s, x, 6.38, ow - 0.2, 0.38, d, size=8.5, color=GRAY, line_spacing=1.3)
        x += ow + 0.2
    footer(s, 2)


def p3b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "02  /  我的资料空间", "我的资料：把每份资料，变成可复用的资产",
           "不是文件管理器，也不是 RAG 问答框——先看懂一份资料，再让它被反复使用。")
    blocks = [
        ("01", "两个入口，一个资料库", "对话里传的附件自动进「我的资料」；页面也支持拖拽、批量上传。同一套解析、同一套整理。"),
        ("02", "拆成资产，记清去向", "拆出标题、公式、表格、图片；每张图知道来自哪份文件、被哪道题或笔记用过；自动命名、归类、归位。"),
        ("03", "资料夹与分享", "12 个资料夹按学科组织；AI 语义找资料；分享资料夹，领取方得到一份独立副本。"),
    ]
    y = 1.98
    for i, (n, t, d) in enumerate(blocks):
        card = rect(s, M_L, y, 5.72, 1.12, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p3b_block_{i+1}", card)
        text(s, M_L + 0.24, y + 0.14, 0.44, 0.26, n, size=11, bold=True, color=MINT, spc=40)
        text(s, M_L + 0.70, y + 0.12, 4.8, 0.26, t, size=13, bold=True, color=INK)
        text(s, M_L + 0.70, y + 0.44, 4.75, 0.56, d, size=8.8, color=GRAY, line_spacing=1.35)
        y += 1.20
    pic_card(s, S6, 6.95, 1.94, 5.52, 3.45, caption="我的资料：33 份资料 · 12 个资料夹 · AI 语义找资料")
    strip = rect(s, M_L, 5.78, CW, 0.80, fill=MINT_L2, line=None, radius=0.06)
    anim(s, "p3b_stats", strip)
    stats = [("33", "份资料"), ("12", "个资料夹"), ("5.1 MB", "总体积"), ("33", "份可检索")]
    x = M_L + 0.30
    for num, lab in stats:
        text(s, x, 5.92, 2.5, 0.30, num, size=17, bold=True, color=INK, font=FONT_L)
        text(s, x, 6.24, 2.5, 0.20, lab, size=8.2, color=GRAY2)
        x += 2.86
    text(s, M_L, 6.72, CW, 0.20, "对话里传过的资料，后面还能用——这是「资料空间」和「聊天附件」最大的区别。", size=8.8, color=GRAY)
    footer(s, 3)


def p4b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "03  /  资料复用", "一份资料，四种产出",
           "同一份资料，既能出题、也能做讲义、还能变成可讲的微课——复用一次，价值放大四次。")
    rows = [
        ("A", "题库练习", "建库 / 组卷 / 顺序·随机·错题·模拟考；答题卡、自动判分、考试记录。"),
        ("B", "讲义文档", "导出 Word / PDF：原生公式与表格，3 套主题，封面、目录、页码齐全。"),
        ("C", "资料微课", "按原文结构拆成 7 站学习路径，31 分钟，每站有检查点与复述。"),
        ("D", "教学微课", "11 页 HTML 课件，按提示词改页，一键导出 PPT，可分享给同学。"),
    ]
    y = 1.96
    for i, (tag, t, d) in enumerate(rows):
        card = rect(s, M_L, y, 5.92, 1.08, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p4b_row_{i+1}", card)
        fill_text(card, [(f"{tag}  ·  {t}", 13, True, MINT_D), (d, 8.8, False, GRAY)],
                  margins=(0.24, 0.16, 0.13, 0.10), spacing=3)
        y += 1.14
    pic_card(s, S7, 7.00, 1.94, 5.42, 3.39, caption="教学微课：11 页 HTML 课件 · 可改页 · 可导出 PPT")
    micro = rect(s, 7.00, 5.64, 5.42, 0.80, fill=AMBER_L, line=None, radius=0.06)
    anim(s, "p4b_micro", micro)
    text(s, 7.20, 5.74, 5.0, 0.26, "资料微课：7 站 · 31 分钟 · 8 片段", size=10.5, bold=True, color=AMBER)
    text(s, 7.20, 6.04, 5.0, 0.24, "把一份资料拆成「一站一站学」的路径，每站都有检查点。", size=8.2, color=GRAY)
    text(s, M_L, 6.62, CW, 0.22, "33 份资料 · 12 个资料夹 · 31 个题库 · 122 项验证——所有产出都来自同一份资料。", size=8.8, color=GRAY2)
    footer(s, 4)


def p9b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "08  /  现场演示", "3 分钟，看四次「它真的动了」",
           "不追求功能全，只追求一件事：让观众在 3 分钟内看到「AI 真的动了我的资料」。")
    stages = [
        ("0:00 – 0:40", "看得见收集", "在对话里传一份含公式与图片的 Word", "自动进入「我的资料」，解析、整理、归位，状态从待解析走到可检索。"),
        ("0:40 – 1:30", "看得见资产", "打开资料详情：结构、图片、公式、表格", "点一张图看到「来自《概率论》· 图 3」，一键插入题目，出现「已用于 1 道题」。"),
        ("1:30 – 2:20", "看得见产出", "同一份资料：建题库 / 做讲义 / 生成微课", "题库能刷、讲义能打印、微课能一站一站讲。"),
        ("2:20 – 3:00", "看得见分享", "分享资料夹或教学微课", "对方领到独立副本，自己的修改不影响原资料。"),
    ]
    cw = (CW - 3 * 0.18) / 4
    for i, (t, h, act, res) in enumerate(stages):
        x = M_L + i * (cw + 0.18)
        card = rect(s, x, 1.98, cw, 2.42, fill=WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p9b_card_{i+1}", card)
        text(s, x + 0.22, 2.12, cw - 0.44, 0.22, t, size=8.4, bold=True, color=MINT_D, spc=30)
        text(s, x + 0.22, 2.38, cw - 0.44, 0.26, h, size=12.5, bold=True, color=INK)
        text(s, x + 0.22, 2.72, cw - 0.44, 0.70, act, size=9.0, color=INK2, line_spacing=1.4)
        line(s, x + 0.22, 3.44, x + cw - 0.22, 3.44, color=LINE, width=0.5)
        text(s, x + 0.22, 3.54, cw - 0.44, 0.72, res, size=8.7, color=GRAY, line_spacing=1.45)
    text(s, M_L, 4.68, 6.0, 0.24, "演示稳定性：把「万一」提前处理掉", size=9.5, bold=True, color=GRAY2, spc=40)
    guards = [("预置数据", "演示账号预置 33 份资料 / 31 个题库 / 299 条作答，开场即有内容"),
              ("提前热身", "演示前 2 小时跑 daily-start.sh，预热模型与检索（首字 45s → 2.8s）"),
              ("双保险", "网络异常切本地录屏；关键链路探针，演示前 10 分钟全跑一遍")]
    x = M_L; gw = (CW - 2 * 0.18) / 3
    for t, d in guards:
        text(s, x, 5.00, gw, 0.24, "· " + t, size=9, bold=True, color=INK)
        text(s, x + 0.14, 5.30, gw - 0.14, 0.60, d, size=8.2, color=GRAY, line_spacing=1.4)
        x += gw + 0.18
    strip = rect(s, M_L, 6.22, CW, 0.42, fill=MINT_L, line=None, radius=0.08)
    text(s, M_L + 0.20, 6.31, CW - 0.4, 0.24,
         "一句话记住：先给结果，再讲技术；每按一次按钮，都要有一处数据变化被看见。", size=9.0, bold=True, color=MINT_D)
    footer(s, 9)


def p10b():
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, "09  /  迭代与团队", "下一步：把「能用」做成「好用」",
           "30 天与 90 天的路线都来自真实使用中发现的边界，不是拍脑袋的功能清单。")
    cols = [
        ("已交付 · 本轮", "DONE", ["资料空间：双入口收集 · 资料夹 · AI 找资料 · 分享副本", "资料微课 / 教学微课：逐站路径 + HTML 课件 + PPT 导出", "文档编排：Word/PDF 原生公式与表格", "题库 / 考试 / 学情诊断闭环"], INK),
        ("30 天 · 补能力", "NEXT", ["扫描版 PDF 接入 OCR", "多模态向量：以图搜图", "移动端适配与消息中心", "评测期限流与稳定性加固"], MINT_D),
        ("90 天 · 上规模", "LATER", ["校园版多租户与教师端", "对象存储直传（OBS）", "题库 / 笔记 / 资料开放 API", "接入更多华为云能力"], GRAY2),
    ]
    cw = (CW - 2 * 0.20) / 3
    for i, (t, tag, items, col) in enumerate(cols):
        x = M_L + i * (cw + 0.20)
        card = rect(s, x, 1.96, cw, 2.85, fill=MINT_L2 if tag == "NEXT" else WHITE, line=LINE, lw=0.75, radius=0.05)
        anim(s, f"p10b_col_{i+1}", card)
        text(s, x + 0.24, 2.12, cw - 0.48, 0.22, tag, size=7.5, bold=True, color=col, spc=80)
        text(s, x + 0.24, 2.38, cw - 0.48, 0.26, t, size=13, bold=True, color=INK)
        y = 2.80
        for it in items:
            text(s, x + 0.24, y, 0.16, 0.22, "·", size=9, color=col)
            text(s, x + 0.42, y, cw - 0.66, 0.70, it, size=8.3, color=GRAY, line_spacing=1.35)
            y += 0.50
    text(s, M_L, 5.08, 5.6, 0.24, "团队分工（按真实职责，可一人多岗）", size=9.5, bold=True, color=GRAY2, spc=40)
    roles = [("产品 / 后端", "场景定义、Agent 与 RAG 后端、数据与部署"),
             ("前端 / 交互", "对话体验、资料空间、题库与微课面板"),
             ("测试 / 演示", "探针与回归、演示脚本、材料与讲解")]
    rw = (CW - 2 * 0.18) / 3
    for i, (t, d) in enumerate(roles):
        x = M_L + i * (rw + 0.18)
        line(s, x, 5.40, x + rw - 0.18, 5.40, color=MINT, width=1.0)
        text(s, x, 5.48, rw - 0.18, 0.24, t, size=9.5, bold=True, color=INK)
        text(s, x, 5.74, rw - 0.18, 0.40, d, size=7.6, color=GRAY, line_spacing=1.35)
    line(s, M_L, 6.36, W - M_L, 6.36, color=LINE, width=0.5)
    text(s, M_L, 6.48, 6.6, 0.32, "谢谢。欢迎现场提问，也欢迎直接上手体验。", size=11.5, bold=True, color=INK)
    text(s, M_L, 6.84, 7.2, 0.20, "作品源码：gitcode.com/qi142410131/openstudy-fastapi-ts", size=8, color=GRAY2)
    b = rect(s, 9.55, 6.44, 3.05, 0.50, fill=MINT, line=None, radius=0.12)
    text(s, 9.55, 6.56, 3.05, 0.26, "OpenStudy · 把不会的问到会", size=8.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    footer(s, 10)


for fn in (p1, p2b, p3b, p4b, p5, p6, p7, p8, p9b, p10b):
    fn()

out = os.path.join(HERE, "OpenStudy-10页-V3-码道版.pptx")
prs.save(out)
print("saved:", out, os.path.getsize(out))
