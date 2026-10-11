# -*- coding: utf-8 -*-
"""多模态文档图片探针 —— 验证「智能体也能看到文档内嵌插图」（用户 2026-10-11）

覆盖：
  MD-01~05：`loop.py` 多模态组块用 `image_urls`（含文档图），不再只遍历 `req.images`
  MD-06~08：视觉模型兜底（不支持视觉时回退 DEFAULT_VISION_MODEL）
  MD-09~11：system_notes 统一编号提示（含文档插图、总数、编号区间）
  MD-12~14：模型能力表口径（deepseek-flash 支持视觉、v4-pro 不支持）

纯静态/源码级 + 模块级断言，不依赖 DB/网络。
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.ai import model_capabilities
from app.services.ai.agent import loop as loop_mod

rows = []


def check(cid, title, cond, actual=""):
    rows.append((cid, title, bool(cond), actual))


src = inspect.getsource(loop_mod.run_agent_stream)

# ---- 1. 多模态组块：用 vision_images（含文档图、data URL），不再只用 req.images ----
check("MD-01", "多模态组块条件用 vision_images", "if vision_images:" in src)
check(
    "MD-02",
    "遍历的是 vision_images 而非 req.images",
    "for url in vision_images:" in src and "for url in req.images:" not in src,
)
check(
    "MD-03a",
    "vision_images 含文档图（req.images + doc_images）",
    "[u for u in (req.images or []) if u] + doc_images" in src,
)
check("MD-03b", "vision_images = 原始图列表（data URL）", "vision_images = list(all_images)" in src)
# ⚠️ 本轮 400 修复：喂模型必须 data URL；落盘路径只用于回插
check(
    "MD-16",
    "喂模型用 vision_images（data URL）而非 image_urls（落盘路径）",
    "for url in vision_images:" in src and "for url in image_urls:" not in src,
)
check(
    "MD-17",
    "落盘 image_urls 仍供回插（ctx.extra）",
    '"image_urls": image_urls,' in src,
)
check("MD-04", "文档图先落盘成 URL（persist_agent_images）", "persist_agent_images(all_images)" in src)
# 无图仍走纯文本（不破坏纯文本场景）
check("MD-05", "无图时仍 append 纯文本 HumanMessage", "HumanMessage(content=human_text)" in src)

# ---- 2. 视觉模型兜底 ----
check("MD-06", "loop 导入 model_capabilities", "model_capabilities" in src)
check(
    "MD-07",
    "含图且模型不支持视觉时回退 DEFAULT_VISION_MODEL",
    "model_capabilities.DEFAULT_VISION_MODEL" in src and "supports_vision(using_model)" in src,
)
check("MD-08", "兜底按需重建 llm（build_agent_llm 二次调用）", src.count("build_agent_llm(") >= 2)

# ---- 3. system_notes 统一编号提示 ----
check("MD-09", "编号提示按 vision_images 生成", "if vision_images:" in src and "Image Attachments (all viewable)" in src)
check("MD-10", "提示里说明文档插图可被看到", "SEE all of them" in src or "SEE all" in src)
check(
    "MD-11",
    "提示里要求按图片内容出题",
    "image CONTENT" in src or "the image content" in src.lower(),
)

# ---- 4. 模型能力表口径 ----
check("MD-12", "deepseek-flash 支持视觉", model_capabilities.supports_vision("deepseek-flash"))
check("MD-13", "deepseek-v4-pro 不支持视觉", not model_capabilities.supports_vision("deepseek-v4-pro"))
check("MD-14", "DEFAULT_VISION_MODEL 是 deepseek-flash", model_capabilities.DEFAULT_VISION_MODEL == "deepseek-flash")
# 未知模型宽松放行（不误伤用户自接的多模态模型）
check("MD-15", "未知模型宽松放行（可识图）", model_capabilities.supports_vision("my-gpt-4o"))

print("\n---- 多模态文档图片探针 ----")
red = 0
for cid, title, ok, actual in rows:
    if not ok:
        red += 1
    tail = "" if ok else f" | 实际: {actual}"
    print(f"  [{'通过' if ok else '失败'}] {cid} {title}{tail}")
print(f"\n共 {len(rows)} 项；红的 = {[r[0] for r in rows if not r[2]] or '无'}")
sys.exit(1 if red else 0)
