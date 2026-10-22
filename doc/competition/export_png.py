# -*- coding: utf-8 -*-
"""用 PowerPoint COM 把 pptx 导出为 PNG，便于逐页视觉核对。"""
import os
import sys
import glob
import shutil

ppt_path = os.path.abspath(sys.argv[1])
out_dir = os.path.abspath(sys.argv[2])
os.makedirs(out_dir, exist_ok=True)
for f in glob.glob(os.path.join(out_dir, "*.png")):
    os.remove(f)

import win32com.client as win32  # noqa

app = win32.Dispatch("PowerPoint.Application")
app.Visible = 1
pres = app.Presentations.Open(ppt_path, WithWindow=False)
pres.SaveAs(out_dir, 18)  # ppSaveAsPNG
pres.Close()
app.Quit()
print("exported to", out_dir)
print(sorted(os.listdir(out_dir)))
