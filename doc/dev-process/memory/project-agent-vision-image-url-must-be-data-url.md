---
name: 喂多模态 API 的图片必须是绝对 URL 或 data URL（落盘相对路径会被上游 400 拒）
description: 2026-10-11 定案——OpenAI 兼容多模态接口只接受 http(s) 绝对 URL 或 data:image/...;base64,；落盘相对路径 /profile/upload/... 仅能回插题目、严禁直接喂模型
type: project
from: Agent
---

2026-10-11 报错与根因：模型调用返回 `Error code: 400 ... Unsupported image_url format (request_id: 5001b33c-...)`。

**根因**：`image_url` 的 `url` 字段收到**不被支持的值**。上一轮修复里把「落盘路径 URL」（**相对路径** `/profile/upload/...`，由 `persist_agent_images` 返回的 `result["fileUrl"]`）直接塞进了多模态消息的图片块；而 **OpenAI 兼容的多模态接口只接受 `http(s)://` 绝对 URL 或 `data:image/...;base64,`**，相对路径被上游直接拒。

**两条用途必须分流（关键设计）**：
- `image_urls`（落盘相对路径）→ **仅供回插题目**（前端 `<img src="/profile/...">` 浏览器能解析）+ `ctx.extra["image_urls"]` 回插用；**不可喂模型**。
- 新增 `vision_images`（**原始 data URL**）→ **供喂模型**，= `req.images`（用户直传的 base64 data URL）+ `doc_images`（`build_marked_document` 抽出的 data URL，本来原样就是 data URL）。

**强制不变量**：`image_urls` 与 `vision_images` **必须长度/顺序一一对应**（同一批图，一个落盘、一个原样），否则 `system_notes` 的编号与喂进去的图对不上。最稳做法=把 `vision_images` 作为 `all_images` 的**同源原始版本**。

**Why:** Agent 链路此前把「落盘 URL」当图片地址喂模型，撞上多模态接口格式校验；而 `chat_engine`（题库「AI 搭建」链路）喂的本来就是 `build_marked_document` 返回的**原样 data URL**，所以题库侧从来不走这个坑——这正是两条链路的差异所在。
**2026-10-11 分流落地进展**：`loop.py` 多模态组块已改为遍历 `vision_images`（现象级核实 `ctx.extra["image_urls"]` 仍持落盘路径、正确）。**注意区分同名变量**：同文件约 `loop.py:594` 的 `image_urls` 属**另一个函数**（ds-free「单步执行」链路，自有参数/局部变量），与主链路无关，改多模态组块时勿把它当同一变量误改。

**2026-10-11 二次修复收尾核实**：`vision_images` 元素**必为非空** data URL——`build_marked_document` 已用 `block.get("imageUrl")` 过滤空值（`all_images` 的 `req.images` 部分另有 `if u` 过滤）；回归全绿（23/23、20/20、21/21、28/28 + 18/18）；`loop.py` 本轮 diff `+24/-12`。

**2026-10-11 分流修复已推送 ✔**：提交 `a919e0d`（区间 `99f8a98..a919e0d HEAD -> main`），`loop.py` 图片两用途彻底分流（`vision_images` 喂模型 / `image_urls` 回插），`loop.py` diff `+24/-12`；worktree 已清。**待用户实机验证**——沙箱跑不了真实多模态调用，须重启后端后上传带插图 Word 实测：① 400 是否消失 ② 模型能否真"看到图"（如几何图/电路图内容）；若仍报错回传原文继续排（可能另有不兼容形态）。

**How to apply:** 任何「把图片喂给多模态模型」的改动（`loop.py` 多模态组块等）一律用 **data URL**（原始 base64）；**落盘 URL 只用于回插**。新增图片用途时先问「喂模型还是回插」，喂模型即取 data URL 形态。相关联：`project-word-image-extraction-to-questionbank`（方向 A）、`reference-multimodal-doc-image-probe-and-doc`。
