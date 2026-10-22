# -*- coding: utf-8 -*-
"""把 10 页渲染图拼成一张 contact sheet，便于一次性核对。"""
import os
import sys
from PIL import Image

src = sys.argv[1]
out = sys.argv[2]
files = [os.path.join(src, f"s{i:02d}.png") for i in range(1, 11)]
imgs = [Image.open(f).convert("RGB") for f in files]
tw, th = 640, 360
pad = 8
cols, rows = 2, 5
W = cols * tw + (cols + 1) * pad
H = rows * th + (rows + 1) * pad
sheet = Image.new("RGB", (W, H), (230, 232, 236))
for i, im in enumerate(imgs):
    im = im.resize((tw, th), Image.LANCZOS)
    r, c = divmod(i, cols)
    x = pad + c * (tw + pad)
    y = pad + r * (th + pad)
    sheet.paste(im, (x, y))
sheet.save(out, quality=95)
print("saved", out, sheet.size)
