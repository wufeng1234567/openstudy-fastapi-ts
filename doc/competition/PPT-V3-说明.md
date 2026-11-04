# OpenStudy 10 页方案 V3 · 码道版说明

> 产物：
> - `OpenStudy-10页-V3-码道版.pptx`（可编辑，含动画）
> - `OpenStudy-10页-V3-码道版.pdf`（静态预览）
> - `OpenStudy-V3-预览.png`（10 页缩略图）
> - `_preview_v3/`（逐页 PNG）

## 一、设计基调

- 浅色：底 `#FBFDFC`、卡片纯白、发丝描边 `#DDEFE7`
- 主色：薄荷绿 `#10B981`，深绿文字 `#0B2B22`，强调橙 `#D97706`
- 字体：微软雅黑（标题加粗、正文常规）
- 原则：大标题、少字、卡片化、真实截图点缀；不用深色底、不堆原始聊天记录

## 二、10 页结构

| 页 | 内容 | 重点 |
|---|---|---|
| P1 | 封面：把不会的，问到会 | 一句话定位 + 真实截图 |
| P2 | 场景与痛点 | 资料散、只用一次、AI 只会聊 |
| P3 | **我的资料空间** | 双入口收集 · 拆成资产 · 资料夹与分享（真实界面） |
| P4 | **一切皆对话：一句话，四种产出** | 真实对话 + 题库 / 讲义 / 资料微课 / 教学微课 |
| P5 | **Word 题库导入** | Word 原文 vs 导入后：复杂公式 + 图 + 解析都保留 |
| **P6** | **码道开发总览** | **8 环节流水线 + 支撑能力 + 真实数据** |
| **P7** | **码道能力 → 系统模块** | **6 张卡：功能 → 模块 → 怎么用 → 结果** |
| **P8** | **真实案例：一个安全缺陷** | **测试 → 审查 → 修复 → 提交** |
| P9 | 现场演示 | 3 分钟四步：收集 → 资产 → 产出 → 分享 |
| P10 | 迭代与团队 | 30/90 天 + 分工 |

## 三、动画

已用 PowerPoint COM 写入真实切换效果：

- 全篇：**Push Left（横向推入）翻页**，Fast 速度、约 0.45 秒
- **取消逐元素动画**：每页打开即完整呈现，不再等一串淡入
- 翻页方向统一，接近纸质翻页；`pdf` 为静态版

打开 `pptx` 后按 `F5` 放映即可看到。

## 四、重建方式

```powershell
# 1) 生成 pptx
openstudy-fastapi\.venv\Scripts\python.exe doc\competition\build_ppt_v3.py

# 2) 加动画（需要本机安装 PowerPoint）
pwsh -NoProfile -File doc\competition\animate_v3.ps1

# 3) 导出逐页 PNG 预览
pwsh -NoProfile -File doc\competition\export_v3.ps1

# 4) 导出 PDF
pwsh -NoProfile -File doc\competition\pdf_v3.ps1

# 5) 生成缩略图
openstudy-fastapi\.venv\Scripts\python.exe doc\competition\make_contact_sheet_v3.py
```
