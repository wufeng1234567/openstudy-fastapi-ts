---
name: 多模态文档图片修复的探针与方案文档入口
description: 验证「智能体看得见文档图片」修复的源码级探针入口，及配套功能方案文档路径
type: reference
from: Agent
---

「智能体看得见文档图片」（loop.py 多模态组块用 `image_urls` + 视觉模型兜底 + `system_notes` 统一编号）修复的验证与文档入口：

- **验证探针**：`tests/_probe_multimodal_doc_images.py`（源码级 + 逻辑级）——验证 ① `loop.py` 多模态组块用 `image_urls` 而非 `req.images`；② 视觉兜底存在；③ `system_notes` 统一编号提示。**本地跑 15/15 全绿**；本环境探针一律在主工作区跑（依赖 DB 的尤须）。
- **配套功能方案文档**：`docs/fastapi_v2_智能体多模态文档图片方案.md`（worktree `.wt_mm` 内产出，已随修复提交 `99f8a98` 落入仓库）。

**2026-10-11 二次修复（`99f8a98` 后的 400）**：`99f8a98` 把**落盘相对路径** `/profile/upload/...` 直接喂模型 → 上游 400 `Unsupported image_url format`。已在 `loop.py` 新增 `vision_images`（原始 data URL，= `req.images` + `doc_images`）专供喂模型，落盘 `image_urls` 仅供回插；二者须长度/顺序一一对应。**详因见 `project-agent-vision-image-url-must-be-data-url`**。该探针须补一条断言：喂模型的图片块用 data URL、非 `/profile/` 相对路径。

**2026-10-11 二次修复探针进展**：探针须补的断言已着手落实——核实「喂模型的图片块走 `vision_images`（data URL）、非 `/profile/` 相对路径」，且 `ctx.extra["image_urls"]` 仍为落盘路径（回插用）；注意区分 `loop.py` 约 594 行另一函数（ds-free 单步链路）的同名 `image_urls`，勿误判为本轮断点。

**2026-10-11 探针口径已整体切换为 `vision_images`（二次修复收尾）**：MD-01~MD-04 断言口径由旧变量改断 `vision_images` + data URL 分流（喂模型块用 data URL、落盘路径不进模型）；新增 MD-16/MD-17 覆盖「data URL 分流语义」。**教训：改口径后必须整体回归——MD-09 因同批口径改动漏改而变红，已修正该断言**（口径类改动须逐条扫全探针，勿只改主断言）。

**2026-10-11 已推送 ✔**：提交 `99f8a98`（区间 `2df94ed..99f8a98 HEAD -> main`），3 文件 = `loop.py` + 新探针 + 新功能文档；推后 worktree `.wt_mm` 已清理。

**2026-10-11 二次修复提交阶段（400 `Unsupported image_url format` 分流修复）**：回归全绿（指挥家 23/23、toolpref 20/20、role 21/21、parallel 28/28 + `_probe_multimodal_doc_images.py` 18/18）✓；边界核实——`vision_images` 元素均为**非空** data URL（`build_marked_document` 已用 `block.get("imageUrl")` 过滤空值）✓；fetch 得 main tip = `99f8a98`；`loop.py` diff = `+24/-12`，与本轮 400 修复量吻合。

**2026-10-11 二次修复闭环已推 ✔**：提交 `a919e0d`（区间 `99f8a98..a919e0d HEAD -> main`），`loop.py` + 探针（新增 MD-16/MD-17，共 18/18 全绿）+ 文档；worktree 已清。探针口径 = 喂模型块用 `vision_images`（data URL）、落盘 `image_urls` 仅回插。**遗留：真实多模态调用须用户实机验证（沙箱无法真发图给 deepseek-flash）**。

**How to apply:** 改动 `loop.py` 的多模态消息组装 / 视觉模型兜底 / `system_notes` 编号提示，或改动 `model_capabilities.py` 时，须同步更新该探针与文档。
