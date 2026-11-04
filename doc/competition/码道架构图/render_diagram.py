from PIL import Image, ImageDraw, ImageFont
import math, os

S = 2
W, H = 1200, 600
img = Image.new('RGB', (W*S, H*S), 'white')
d = ImageDraw.Draw(img)

FONT = r'C:\Windows\Fonts\msyh.ttc'
FONTB = r'C:\Windows\Fonts\msyhbd.ttc'
if not os.path.exists(FONTB):
    FONTB = FONT
def f(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size*S)

GREEN = '#10B981'
DGREEN = '#065F46'
MINT = '#F0FDF9'
MINT2 = '#ECFDF5'
MINTL = '#A7F3D0'
AMBER = '#F59E0B'
AMBERBG = '#FFFBEB'
AMBERFG = '#92400E'
GRAY = '#6B7280'
LGRAY = '#9CA3AF'

def rr(x, y, w, h, r, fill, outline, width=2):
    d.rounded_rectangle([x*S, y*S, (x+w)*S, (y+h)*S], radius=r*S, fill=fill,
                        outline=outline, width=int(width*S))

def text_center(cx, cy, lines, fonts_colors):
    heights = []
    total = 0
    for txt, fo, _ in lines:
        bb = d.textbbox((0, 0), txt, font=fo)
        hh = bb[3]-bb[1]
        heights.append(hh); total += hh
    gap = 4*S
    total += gap*(len(lines)-1)
    y = cy - total/2
    for (txt, fo, col), hh in zip(lines, heights):
        bb = d.textbbox((0, 0), txt, font=fo)
        ww = bb[2]-bb[0]
        d.text((cx-ww/2, y-bb[1]), txt, font=fo, fill=col)
        y += hh + gap

def node(x, y, w, h, title, caption, amber=False):
    fill = AMBERBG if amber else 'white'
    outline = AMBER if amber else GREEN
    tcol = AMBERFG if amber else DGREEN
    rr(x, y, w, h, 10, fill, outline, 2)
    text_center((x+w/2)*S, (y+h/2)*S,
                [(title, f(15, True), tcol), (caption, f(10.5), tcol)],
                None)

def arrow(x1, y1, x2, y2, color=GREEN, dashed=False, width=2, label=None, loff=(0,0)):
    if dashed:
        # dashed straight line
        dist = math.hypot(x2-x1, y2-y1)
        steps = int(dist/10)+1
        for i in range(steps):
            if i % 2 == 0:
                xa = x1 + (x2-x1)*i/steps; ya = y1 + (y2-y1)*i/steps
                xb = x1 + (x2-x1)*(i+1)/steps; yb = y1 + (y2-y1)*(i+1)/steps
                d.line([xa*S, ya*S, xb*S, yb*S], fill=color, width=int(width*S))
    else:
        d.line([x1*S, y1*S, x2*S, y2*S], fill=color, width=int(width*S))
    ang = math.atan2(y2-y1, x2-x1)
    L = 10; spread = math.pi/7
    p1 = (x2*S, y2*S)
    p2 = ((x2 - L*math.cos(ang-spread))*S, (y2 - L*math.sin(ang-spread))*S)
    p3 = ((x2 - L*math.cos(ang+spread))*S, (y2 - L*math.sin(ang+spread))*S)
    d.polygon([p1, p2, p3], fill=color)
    if label:
        fo = f(10.5)
        bb = d.textbbox((0,0), label, font=fo)
        lx = (x1+x2)/2*S - (bb[2]-bb[0])/2 + loff[0]*S
        ly = (y1+y2)/2*S - (bb[3]-bb[1])/2 + loff[1]*S
        d.rectangle([lx-4, ly-3, lx+(bb[2]-bb[0])+4, ly+(bb[3]-bb[1])+3], fill='white')
        d.text((lx-bb[0], ly-bb[1]), label, font=fo, fill=AMBERFG if color==AMBER else '#047857')

# title
d.text((40*S, 16*S), '码道开发流程', font=f(26, True), fill=DGREEN)
d.text((40*S, 54*S), '从需求到沉淀的 AI 编码全流程', font=f(12.5), fill=GRAY)

# entry band
rr(40, 92, 1100, 46, 10, MINT, MINTL, 1.5)
text_center(590*S, 115*S, [('入口：自然语言需求 · 现有仓库 · GitCode', f(13), DGREEN)], None)

# nodes
names = [
    ('需求', '用户目标 · 一句话', False),
    ('接入', 'git status · 分支确认', False),
    ('读码', 'CodeSemanticSearch', False),
    ('写测', 'developer-test-agent', False),
    ('审查', 'git diff · security_audit', True),
    ('提交', 'git commit / push', False),
    ('沉淀', 'experience / export', False),
]
xs = [40, 200, 360, 520, 680, 840, 1000]
ys = 190; nh = 100; nw = 140
for (t, c, amb), x in zip(names, xs):
    node(x, ys, nw, nh, t, c, amb)

# 修复 node
node(680, 350, 140, 86, '修复', '/bugfix · bug-fix-agent', True)

# arrows
arrow(180, 240, 200, 240)
arrow(340, 240, 360, 240)
arrow(500, 240, 520, 240)
arrow(660, 240, 680, 240)
arrow(820, 240, 840, 240)
arrow(760, 290, 760, 350, color=AMBER, label='有 P0/P1', loff=(40, -14))
arrow(680, 393, 590, 290, color=AMBER, dashed=True, label='修完回归', loff=(-10, 8))
arrow(980, 240, 1000, 240)

# support band
rr(40, 470, 1100, 54, 10, MINT2, MINTL, 1.5)
text_center(590*S, 497*S, [('支撑能力：规则 AGENTS.md · 技能 SKILL.md · 经验 experience · 沙箱 / 权限 · checkpoint / undo', f(12.5), DGREEN)], None)
d.text((40*S, 542*S), '审查无 P0/P1 直接提交；有则修复并回归 · 任一步失败即停下说明，不绕过、不造假', font=f(11.5), fill=LGRAY)

out = r'D:\OpenStudy\apps\fastapi-v2\doc\competition\码道架构图\codearts-flow.png'
img.save(out, 'PNG')
print('saved', out, img.size)
