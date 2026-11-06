import os, re
from PIL import Image, ImageDraw, ImageFont

src = r'D:\OpenStudy\apps\fastapi-v2\doc\competition\_preview_061'
files = [f for f in os.listdir(src) if f.lower().endswith('.png')]
def num(f):
    m = re.search(r'(\d+)', f)
    return int(m.group(1)) if m else 0
files.sort(key=num)

TW, TH = 480, 270
GAP = 16
LABEL = 34
cols, rows = 5, 2
W = GAP + cols * (TW + GAP)
H = GAP + rows * (TH + LABEL + GAP)
sheet = Image.new('RGB', (W, H), '#F5FAF8')
d = ImageDraw.Draw(sheet)
font_path = r'C:\Windows\Fonts\msyh.ttc'
font = ImageFont.truetype(font_path, 18)

for i, f in enumerate(files[:10]):
    im = Image.open(os.path.join(src, f)).convert('RGB').resize((TW, TH), Image.LANCZOS)
    col = i % cols; row = i // cols
    x = GAP + col * (TW + GAP)
    y = GAP + row * (TH + LABEL + GAP)
    sheet.paste(im, (x, y))
    d.rectangle([x, y, x + TW, y + TH], outline='#DDEFE7', width=2)
    label = f'P{i+1}'
    d.text((x + 2, y + TH + 6), label, font=font, fill='#0B2B22')

out = r'D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-0.6.1-预览.png'
sheet.save(out, 'PNG')
print('saved', out, sheet.size, len(files))
