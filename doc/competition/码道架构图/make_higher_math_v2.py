import os, sys, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

PROJECT = r'D:\OpenStudy\apps\fastapi-v2\openstudy-fastapi'
sys.path.insert(0, PROJECT)
from app.services.mathml_omml import latex_to_omml, omml_to_xml_string

OUT = r'D:\OpenStudy\apps\fastapi-v2\doc\competition\码道架构图'
UPLOAD = r'D:\OpenStudy\apps\fastapi-v2\openstudy-fastapi\data\uploadPath\upload\2026\11\04'
os.makedirs(UPLOAD, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

x = np.linspace(-1.1, 1.1, 500)
y1 = x ** 2
y2 = 2 - x ** 2
fig, ax = plt.subplots(figsize=(6.2, 4.0), dpi=220)
ax.fill_between(x, y1, y2, where=(y2 >= y1), color='#A7F3D0', alpha=0.65, label='区域 D')
ax.plot(x, y1, color='#0B7A5B', lw=2.2, label=r'$y=x^2$')
ax.plot(x, y2, color='#D97706', lw=2.2, label=r'$y=2-x^2$')
ax.axhline(0, color='#94A3B8', lw=0.8); ax.axvline(0, color='#94A3B8', lw=0.8)
ax.set_xlim(-1.15, 1.15); ax.set_ylim(-0.2, 2.15)
ax.set_xlabel('x'); ax.set_ylabel('y')
ax.set_title('区域 D：由 y=x² 与 y=2−x² 围成', fontsize=13, color='#0B2B22')
ax.legend(loc='upper right', fontsize=9, frameon=False); ax.grid(alpha=0.25)
fig.tight_layout()
region = os.path.join(UPLOAD, 'region.png'); fig.savefig(region, dpi=220, facecolor='white'); plt.close(fig)

X, Y = np.meshgrid(np.linspace(-1, 1, 80), np.linspace(0, 2, 80))
Z = X ** 2 + Y ** 2
mask = (Y >= X ** 2) & (Y <= 2 - X ** 2)
Z = np.where(mask, Z, np.nan)
fig = plt.figure(figsize=(5.0, 3.6), dpi=220)
ax = fig.add_subplot(111, projection='3d')
ax.plot_surface(X, Y, Z, cmap='viridis', alpha=0.9, linewidth=0, antialiased=True)
ax.set_title('f(x,y)=x²+y² 在 D 上的曲面', fontsize=11, color='#0B2B22', pad=2)
ax.set_xlabel('x', fontsize=8); ax.set_ylabel('y', fontsize=8); ax.set_zlabel('z', fontsize=8)
ax.tick_params(labelsize=7)
fig.tight_layout()
surface = os.path.join(UPLOAD, 'surface.png'); fig.savefig(surface, dpi=220, facecolor='white'); plt.close(fig)
print('images', region, surface)

doc = Document()
sec = doc.sections[0]
sec.top_margin = Cm(1.4); sec.bottom_margin = Cm(1.2)
sec.left_margin = Cm(1.8); sec.right_margin = Cm(1.8)
st = doc.styles['Normal']; st.font.name = '宋体'; st.font.size = Pt(10)
st.paragraph_format.space_after = Pt(0); st.paragraph_format.space_before = Pt(0); st.paragraph_format.line_spacing = 1.0

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('高等数学 · 综合练习（第三章）'); r.font.name = '宋体'; r.font.size = Pt(15); r.bold = True

def section(title):
    h = doc.add_heading(level=1)
    r = h.add_run(title); r.font.name = '宋体'; r.font.size = Pt(12); r.bold = True
    h.paragraph_format.space_before = Pt(4); h.paragraph_format.space_after = Pt(0)

def formula(latex):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    om = latex_to_omml(latex)
    if om is None:
        p.add_run(latex)
    else:
        el = parse_xml(omml_to_xml_string(om))
        half = str(int(round(15 * 2)))
        m_ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
        for r in el.iter(f"{{{m_ns}}}r"):
            old = r.find(qn("w:rPr"))
            if old is not None:
                r.remove(old)
            rpr = OxmlElement("w:rPr")
            for tag in ("w:sz", "w:szCs"):
                sz = OxmlElement(tag); sz.set(qn("w:val"), half); rpr.append(sz)
            r.insert(0, rpr)
        p._p.append(el)

section('一、极限与连续')
p = doc.add_paragraph(); r = p.add_run('（1）计算极限：'); r.font.name = '宋体'; r.font.size = Pt(10.5)
formula(r'\lim_{x\to 0}\dfrac{e^x-1-x}{x^2}')

section('二、偏导数与全微分')
p = doc.add_paragraph(); r = p.add_run('（2）设 z = arctan(y/x)，求：'); r.font.name = '宋体'; r.font.size = Pt(10.5)
formula(r'\dfrac{\partial^2 z}{\partial x\,\partial y}')

section('三、二重积分')
p = doc.add_paragraph(); r = p.add_run('（3）计算二重积分：'); r.font.name = '宋体'; r.font.size = Pt(10.5)
formula(r'\iint_{D}\left(x^2+y^2\right)\,dx\,dy')
p = doc.add_paragraph(); r = p.add_run('其中 D 由 y = x² 与 y = 2 − x² 围成（如图）。'); r.font.name = '宋体'; r.font.size = Pt(10.5)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
for i, img in enumerate([region]):
    cell = table.cell(0, i)
    par = cell.paragraphs[0]; par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.add_run().add_picture(img, width=Cm(7.0))

docx = os.path.join(OUT, 'word-source-math-v2.docx')
doc.save(docx)
print('docx', docx, os.path.getsize(docx))

