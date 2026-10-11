# -*- coding: utf-8 -*-
"""处理进度事件探针（用户 2026-10-11 方案 C：文档解析进度可视化）

守护：`loop.py` 在"文档处理段"发 `progress` 事件（解析前/后、落盘前/后），
且**不暴露思维链**（progress 只是阶段提示）。

纯源码级断言（不依赖 DB/网络）。
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.ai.agent import loop as loop_mod

rows = []


def check(cid, title, cond, actual=""):
    rows.append((cid, title, bool(cond), actual))


src = inspect.getsource(loop_mod.run_agent_stream)

# ---- progress 事件存在且用在文档处理段 ----
check("PG-01", '有 type="progress" 事件', '"type": "progress"' in src)
check("PG-02", "解析前发 doc_parse(running)", '"id": "doc_parse"' in src and "正在解析文档" in src)
check("PG-03", "解析后发 doc_parse(done)", '"state": "done"' in src and "文档解析完成" in src)
check("PG-04", "图片落盘前发 save_images", '"id": "save_images"' in src and "正在保存图片" in src)
check("PG-05", "图片落盘后有收口（已保存/失败）", "图片已保存" in src and "图片保存失败" in src)
# 三段结构：progress 必须夹在 to_thread(解析) 前后（事件在解析前后发）
check("PG-06", "解析事件夹在 to_thread 前后", src.index("正在解析文档") < src.index("_collect_attachments, req") and src.index("_collect_attachments, req") < src.index("文档解析完成"))
# 无附件时不发解析事件（条件守卫）
check("PG-07", "解析事件有 file_count 守卫", "if file_count:" in src)
check("PG-08", "落盘事件有 all_images 守卫", "if all_images:" in src)

print("\n---- 处理进度事件探针 ----")
red = 0
for cid, title, ok, actual in rows:
    if not ok:
        red += 1
    print(f"  [{'通过' if ok else '失败'}] {cid} {title}" + ("" if ok else f" | 实际: {actual}"))
print(f"\n共 {len(rows)} 项；红的 = {[r[0] for r in rows if not r[2]] or '无'}")
sys.exit(1 if red else 0)
