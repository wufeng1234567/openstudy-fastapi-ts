import os, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = r'D:\OpenStudy\apps\fastapi-v2\doc\competition\码道架构图'
FIG = os.path.join(OUT, 'physics-figs'); os.makedirs(FIG, exist_ok=True)
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 1) 斜面受力图
fig, ax = plt.subplots(figsize=(6, 3.6), dpi=220)
ax.plot([0, 4.8], [0, 3.0], color='#0B7A5B', lw=2)
ax.plot([0, 4.8], [0, 0], color='#94A3B8', lw=1.2)
# 物块
bx, by = 2.35, 1.47
ax.add_patch(plt.Rectangle((bx-0.35, by-0.18), 0.75, 0.38, angle=32, facecolor='#E8F8F1', edgecolor='#0B7A5B', lw=1.5))
ax.annotate('', xy=(bx-0.25, by-0.8), xytext=(bx-0.25, by-0.15), arrowprops=dict(arrowstyle='-|>', color='#D97706', lw=2))
ax.text(bx-0.30, by-0.95, 'mg', color='#D97706', fontsize=10)
ax.annotate('', xy=(bx+0.45, by+0.55), xytext=(bx+0.30, by+0.10), arrowprops=dict(arrowstyle='-|>', color='#2563EB', lw=2))
ax.text(bx+0.50, by+0.58, 'N', color='#2563EB', fontsize=10)
ax.annotate('', xy=(bx-0.95, by+0.25), xytext=(bx-0.40, by+0.05), arrowprops=dict(arrowstyle='-|>', color='#7C3AED', lw=2))
ax.text(bx-1.05, by+0.28, 'f', color='#7C3AED', fontsize=10)
ax.set_xlim(-0.4, 5.2); ax.set_ylim(-0.6, 3.5); ax.axis('off')
ax.set_title('图 1  斜面上的物块受力分析', fontsize=12, color='#0B2B22')
fig.tight_layout(); f1 = os.path.join(FIG, 'force.png'); fig.savefig(f1, facecolor='white'); plt.close(fig)

# 2) v-t 图
fig, ax = plt.subplots(figsize=(6, 3.2), dpi=220)
t = np.array([0, 1, 2, 3, 4, 5])
v = np.array([0, 2, 4, 6, 6, 6])
ax.plot(t, v, color='#0B7A5B', lw=2.2, marker='o', ms=4)
ax.fill_between(t, 0, v, color='#A7F3D0', alpha=0.35)
ax.set_xlabel('时间 t / s'); ax.set_ylabel('速度 v / (m·s⁻¹)')
ax.set_title('图 2  小车运动的速度—时间图像', fontsize=12, color='#0B2B22')
ax.grid(alpha=0.25)
fig.tight_layout(); f2 = os.path.join(FIG, 'vt.png'); fig.savefig(f2, facecolor='white'); plt.close(fig)

# 3) 能量条形图
fig, ax = plt.subplots(figsize=(6, 3.2), dpi=220)
labels = ['动能', '重力势能', '内能']
vals = [42, 48, 10]
colors = ['#10B981', '#D97706', '#94A3B8']
bars = ax.bar(labels, vals, color=colors, width=0.55)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width()/2, v + 1.5, f'{v}%', ha='center', fontsize=10)
ax.set_ylim(0, 60); ax.set_ylabel('占比 / %')
ax.set_title('图 3  小球下滑过程中的能量转化', fontsize=12, color='#0B2B22')
ax.grid(axis='y', alpha=0.25)
fig.tight_layout(); f3 = os.path.join(FIG, 'energy.png'); fig.savefig(f3, facecolor='white'); plt.close(fig)
print('figs', f1, f2, f3)

doc = Document()
sec = doc.sections[0]
sec.top_margin = Cm(1.8); sec.bottom_margin = Cm(1.8)
sec.left_margin = Cm(2.2); sec.right_margin = Cm(2.2)
st = doc.styles['Normal']; st.font.name = '宋体'; st.font.size = Pt(10.5)
st.paragraph_format.space_after = Pt(2); st.paragraph_format.line_spacing = 1.25

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('高中物理 · 力学基础讲义'); r.font.name = '宋体'; r.font.size = Pt(16); r.bold = True

def h(text, level=1):
    x = doc.add_heading(level=level)
    r = x.add_run(text); r.font.name = '宋体'; r.font.size = Pt(13 if level == 1 else 11); r.bold = True

def para(text):
    p = doc.add_paragraph(); r = p.add_run(text); r.font.name = '宋体'; r.font.size = Pt(10.5)

def pic(path, width=13.5):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width))

h('第一章  运动的描述')
h('1.1  参考系与质点', 2)
para('描述物体的运动，先要选定参考系。研究一辆小车在平直轨道上的运动时，可以以地面为参考系，取轨道方向为正方向。')
para('当物体的形状和大小对研究问题影响很小时，可以把物体看成质点。质点是一种理想化模型，不是真实存在的点。')
h('1.2  位移与速度', 2)
para('位移描述位置的变化，是矢量；速度描述位置变化的快慢，等于位移与时间的比值。小车做匀加速直线运动时，速度随时间均匀增大。')
pic(f2, 13.0)

h('第二章  牛顿运动定律')
h('2.1  牛顿第一定律', 2)
para('一切物体总保持匀速直线运动状态或静止状态，直到有外力迫使它改变这种状态为止。惯性是物体保持原有运动状态的性质。')
h('2.2  牛顿第二定律', 2)
para('物体加速度的大小跟它受到的作用力成正比，跟它的质量成反比，加速度的方向跟作用力的方向相同，即 F = ma。')
pic(f1, 13.0)

h('第三章  机械能守恒')
h('3.1  动能与势能', 2)
para('物体由于运动而具有的能叫动能，由于被举高而具有的能叫重力势能。在只有重力做功的情况下，动能和势能相互转化，机械能总量保持不变。')
pic(f3, 12.5)

docx = os.path.join(OUT, 'physics-source.docx')
doc.save(docx)
print('docx', docx, os.path.getsize(docx))
