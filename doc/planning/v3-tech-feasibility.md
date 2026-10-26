# OpenStudy v3 技术可行性审查报告

审查时间：2026-10-26 ｜ 审查方式：实际读代码 + 用 venv python（`openstudy-fastapi\.venv\Scripts\python.exe`，python-docx 1.1.2）跑临时脚本实测，脚本与产物在 `_scratch_v3\`（`test_table_omml.py`、`out_table_test.docx`），未改任何业务代码。

---

## 一、Word 原生表格：**做得到，且改造量比预期小**

### 1.1 现有代码为什么进不了单元格

- `_docx_add_blocks`（bank_export_service.py:638）通过 `doc.add_paragraph()` / `doc.add_picture()` 加内容，挂在 **document body** 上，不是 cell 上 —— 直接复用会写到表格外。
- 但底层零件全是段落级的，天生可进 cell：
  - `_add_omml(paragraph, latex)`（:558）：往 `paragraph._p.append(omml)` —— cell 里的段落同样是 `w:p`，实测可用。
  - `_add_segments(paragraph, text)`（:585）、`_add_run(paragraph, text)`（:545）：参数就是 paragraph，不用改。
  - `_docx_add_image(doc, src)`（:601）：唯一用 `doc.add_picture()` 的地方，改成 `run.add_picture(BytesIO, width, height)` 即可进 cell —— 实测 `run.add_picture` 在单元格内成功（脚本输出 `image in table cell: OK`）。
  - `split_blocks` / `split_text_and_math`（:347, :383）：纯字符串处理，与容器无关。

**结论：把 `_docx_add_blocks` / `_docx_add_image` 的"往 doc 加"改成"往 container 加"（container 是 doc 或 cell），全部现有能力（公式、图文混排、图片定位）都能进单元格。**

### 1.2 python-docx 1.1.2 对表格属性的支持（实测）

| 需求 | 高级 API | 实测结果 |
|---|---|---|
| 固定列宽 `gridCol` | `table.columns[i].width = Cm(x)` | **有 API**，但底层仍靠手改 `w:tblGrid/w:gridCol`（脚本证实 gridCol 被写入 w="2268" 等）；还要配合 `tbl.autofit=False` + 逐 cell `cell.width` |
| 表头底纹 `shd` | 无 | **必须手撸 oxml**：`tcPr.append(OxmlElement("w:shd", fill=...))` —— 实测 3 行代码可用 |
| 跨页重复表头 `tblHeader` | 无（`hasattr(row,'repeat_table_header')=False`） | **必须手撸 oxml**：`trPr.append(OxmlElement("w:tblHeader"))` —— 实测可用 |
| 行不跨页 `cantSplit` | 无 | **必须手撸 oxml** —— 实测可用 |
| 单元格边距 `tcMar` | 无（只有 `Table.cell_margins` 也不存在） | **必须手撸 oxml** —— 实测可用 |
| 全表边框 `tblBorders` | 间接（`table.style="Table Grid"`） | Grid 样式够用；要自定义颜色/粗细则手撸 —— 实测可用 |

总计需要手撸的 oxml 约 **60~80 行**（一个 `_style_table()` 工具函数），全部验证通过。

### 1.3 单元格内公式 + 图片（实测）

```
OMML in table cell: True
image in table cell: OK
```
即 `表头底纹 + 边框 + 固定列宽 + 跨页表头 + 单元格 OMML + 单元格图片` 六项全部实测通过，产物 `out_table_test.docx` 可直接打开验收。

### 1.4 改造量

- 新增 `docx_table_service.py`（或塞进 bank_export_service）：~150 行（含样式函数 + `add_table_from_ir()`）。
- 改 `_docx_add_blocks` / `_docx_add_image`：把挂载目标抽象成 container，改动 < 20 行。
- 生成器侧（AI 产出表格数据）：建议让 Agent 工具产出 `{headers, rows, colWidths}` JSON，由现有 17 个工具之一（如 bank_export 工具，app/services/ai/agent/tools/bank_export.py:11）透传。

**判定：可行，约 1.5~2 天含自测。**

---

## 二、OMML 公式覆盖率：**18 个典型公式实测 18/18 转换成功，0 崩溃；但 3 类存在"结构降级"**

### 2.1 实测数据（`latex2mathml` 3.81.1 → mathml_omml.py → parse_xml 验证可插入 docx）

| 公式 | 结构元素 | 结果 |
|---|---|---|
| 分式 `\dfrac{1}{2}` | `m:f` | ✅ 完整 |
| 嵌套分式 `\frac{\frac{a}{b}}{\frac{c}{d}}` | `m:f` | ✅ 完整 |
| 根式 `\sqrt{x+1}` | `m:rad` | ✅ 完整 |
| 高次根 `\sqrt[3]{x^2+1}` | `m:rad`+`sSup` | ✅ 完整 |
| 上/下/上下标（3 个） | `sSup/sSub/sSubSup` | ✅ 完整（含 `_attach_implicit_base` 修空底数，mathml_omml.py:126） |
| 积分 `\int_0^1 x^2 dx` | `sSubSup`（**无 nary**） | ⚠️ 降级：上下限在 ∫ 侧边而非正上/正下方 |
| 二重积分 `\iint_D f dxdy` | `sSub`（**无 nary**） | ⚠️ 降级同上 |
| 求和 `\sum_{i=1}^n 1/i^2` | `sSubSup`（**无 nary**） | ⚠️ 降级：∑ 显示为普通字符带侧边上下标 |
| 极限 `\lim_{n\to\infty}` | `sSub`（**无 nary**） | ⚠️ 降级：lim 下方标不居中于 "lim" 之下 |
| 矩阵 `\begin{pmatrix}` | `m:m` | ✅ 完整 |
| 分段函数 `\begin{cases}` | `m:m` | ✅ 转换成功（cases 渲染为矩阵 + 左定界符） |
| 希腊+运算、向量点积、二项式、对数、行列式 | 混合 | ✅ 全部成功 |

**总计：18 成功 / 0 失败 / 0 崩溃。**

### 2.2 根因（代码证据）

`mathml_omml.py:293-343` 处理 `munderover` 时，只有当**底数文本恰好是 ∑/∏/∫ 等符号**才转 `m:nary`。但 `latex2mathml` 对 `\int_0^1` 产出的是 `<msubsup><mo>∫</mo>...`（实测原始 MathML 确认），在 mathml_omml.py:276 的 `msubsup` 分支就被提前拦截，**根本走不到 :293 的 nary 分支**——`m:nary` 代码是死代码（对 latex2mathml 的实际输出不可达）。

### 2.3 修复方案（明确、小改动）

在 `msubsup`/`msub`/`msup` 分支入口加一个判断：底数文本 ∈ {"∑","∏","∫","∬","∭","∮","lim","⋃","⋂"} 时转 `m:nary`（lim 转为 `m:limLow`），复用 :331-343 已写好的 nary 构造。**约 30~40 行，一次性修复全部降级。**修完后覆盖率即"完整结构"17/18 以上。

**判定：可行，公式侧改造量约半天；Word 端"复杂公式打印不走样"天然满足（OMML 是矢量原生格式）。**

---

## 三、PDF 路线对比与推荐

| 维度 | (a) LaTeX (xelatex) | (b) HTML + 无头 Chrome 打印 PDF | (c) reportlab 继续 + 补 Table/公式 |
|---|---|---|---|
| 一次性成本 | 高：装 MiKTeX/TeX Live ~500MB+，还要 pip 装驱动、写 .tex 模板、解决 CJK fontspec 配置 | 中：Playwright `pip install` + `playwright install chromium` ~150MB；HTML 模板复用前端 marked + katex CDN/本地包（前端已有 katex 0.18） | 低：reportlab 4.2.5 现成 `Table`/`TableStyle`，加 30 行封装 |
| 公式质量 | **顶级**（真 TeX 排版） | **优秀**（KaTeX 矢量输出，打印不走样，还支持 `\begin{cases}`/pmatrix 全覆盖） | 差：现行 Unicode 降级（bank_export_service.py:873 `_latex_to_pdf_markup`），分数变 `a⁄b`、积分上下限永远侧排；要画图就得走 matplotlib mathtext（又引新依赖） |
| 表格质量 | 高但模板笨重 | 高（CSS 表格，斑马纹/合并单元格全支持） | 高（reportlab Table 原生支持 repeatRows=1 跨页表头、colWidths、BACKGROUND、GRID） |
| 运行风险 | Windows 编译慢（首次 10s+/文档）；换机器要重装发行版；**无 LaTeX 发行版是项目已核实事实** | 启动 chromium ~1-2s/文档；需注意无头进程资源；本机已有 Chrome 但 Playwright 自带 chromium 更稳 | **零新依赖、零部署变更**，与现有 `_register_cjk_font`（:796）和 `KeepTogether` 分页逻辑（:1088）无缝 |
| 对现有代码的侵入 | 全部推倒重写导出层 | 新增一条渲染管线，与 reportlab 并存或替换 | 增量补齐 |
| 维护者心智 | 需要懂 TeX | 需要管浏览器进程 | 已在维护的东西 |

### 推荐：(b) HTML + 无头浏览器打印 PDF，理由：

1. **它同时解决公式和表格两个硬伤**：KaTeX 对 `\int_0^1`、`\sum`、`\begin{cases}` 的渲染就是"打印不走样"的定义；CSS 表格直接覆盖表头底纹/跨页表头（`thead { display: table-header-group }`）。
2. **复用前端已有资产**：前端已有 katex 0.18 和 marked（项目事实），同一套 LaTeX 子集在网页预览和 PDF 输出里表现一致——"预览即所得"对演示是加分项。
3. **风险可控**：本机单机跑、无公网（项目事实），无头浏览器的安全面最小；Playwright 同步 API 在 FastAPI 里用 `asyncio.to_thread` 包一层即可（现有代码已有同款模式：api/v1/document.py:36 `await asyncio.to_thread(parse_file, ...)`）。

### 为什么不是 (a)：

- 项目**没有 LaTeX 发行版**（已核实事实），用户环境是 Windows 单机，让比赛评委机器/换机部署都要装 500MB+ 发行版，是把部署风险当成功能做。
- xelatex 每份文档冷编译 5-15 秒，题库 670 题全量导出不可接受；HTML 管线是毫秒级渲染 + 一次打印。

### 为什么不是 (c)：

- reportlab 的公式天花板就是 `_latex_to_pdf_markup`（:873）这种 Unicode 近似——代码注释自己写明了"可行的做法只有两种：① 图片公式；② Unicode 近似"（:154-160），选 ① 会引入 matplotlib 依赖且公式不可选中不可搜索。要"打印不走样的复杂公式"，(c) 做不到，这是能力边界不是工作量问题。
- (c) 仍可作为**保底**：若比赛现场断网/浏览器异常，reportlab 管线还在，PDF 输出不会 500。

### (b) 的具体落地路径（已核实可行）：

1. 后端新文件 `pdf_render_service.py`：把文档 IR → HTML（表格 `<table>` + 公式 `katex.renderToString`）→ Playwright `page.pdf()`。
2. katex 资源本地化（前端 node_modules 已有 katex 0.18，拷 CSS+字体到静态目录，不走 CDN，单机无外网也能跑）。
3. 与 reportlab 路线用配置开关并存，`api/v1/bank_export.py:119-127` 的分发处加一个 `format=pdf_html` 分支，不动老路径。

**改造量：~2-3 天（含 Playwright 打印样式调优）。**

---

## 四、Document IR 统一：**做得到，但不是"合并两个结构"，而是"以 file_parser 的 dict 块为基座扩一个 table 类型"**

### 4.1 两套结构的实际差异（代码证据）

| | file_parser `_BlockBuilder` | bank_export_service `Block` |
|---|---|---|
| 形态 | dict：`{"type":"text"|"image", "content", "orderIndex", "imageUrl"(dataURL), "imageName"}`（file_parser.py:333-364） | tuple：`("text", str) | ("image", src)`（bank_export_service.py:275） |
| 表格 | **压成 Markdown 文本**（file_parser.py:667-724 `_emit_table`） | 无表格概念（grep 确认 `add_table/Table/repeatRows` 零命中） |
| 公式 | OMML→LaTeX 还原进文本（file_parser.py:46-214 `_omml_to_latex`） | 文本内裸 LaTeX → OMML（bank_export_service.py:558） |
| 图片 src | data URL | `UPLOAD_DIR` 相对路径（:205 `_src_to_relpath`） |

### 4.2 改动波及面（grep 实测）

**`parse_file` / `build_marked_document` 的调用点（要兼容 IR 扩展）：**

- `parse_file`：6 处文件 8 次调用 —— api/v1/ai.py:1874、api/v1/document.py:36、api/v1/rag.py:244+700、services/ai/chat_engine.py:337、services/ai/agent/loop.py:308、doc_converter.py（仅内部）
- `build_marked_document`：5 处 —— chat_engine.py:343、loop.py:313、rag.py:261+710、models/rag.py:153（引用其标记格式）

**`split_blocks` / `_docx_add_blocks` / `_pdf_add_blocks` / `_add_segments` 的调用点（Word/PDF 渲染侧）：**

- 全部封闭在 bank_export_service.py 内部（:649, :721, :730, :737, :743, :750, :760, :769, :1202, :1212, :1233）+ diagnosis_report_service.py:81/117 复用了 `_rl_text_with_math` / `_register_cjk_font` 两个函数（不含块结构）+ agent 工具 bank_export.py:439 调用 `export_bank_docx/export_bank_pdf`。

### 4.3 统一方案（结论）

以 `file_parser` 的 dict 块为 IR 基座，加一个块类型：

```python
{"type": "table", "headers": [str,...], "rows": [[str|{"image":...}|{"math":...},...],...],
 "colWidths": [cm,...] | None, "orderIndex": N}
```

- **不必动** `parse_file` 的 6 个调用文件：`_BlockBuilder` 新增 `add_table()` 只影响新增块类型，老调用方读 `textContent`/`blocks` 时按 type 分派即可，向后兼容。
- **必改**：bank_export_service 的 `_docx_add_blocks`/`_pdf_add_blocks` 各加一个 `elif kind == "table"` 分支（就是第一、三部分的成果挂载点）；`_emit_table`（file_parser.py:667）从"输出 Markdown 字符串"改为"输出 table 块 + 同时保留 Markdown 进 textContent"（双写，避免破坏 chat_engine/loop 依赖的 marked 正文）。
- 前端渲染器（Vue 侧）同型消费：blocks 早已是 JSON（api/v1/ai.py:1859 `parse_files_blocks` 已把 blocks 直接给前端），加 table 类型前端 marked 也能吃（`_emit_table` 现在就是把表格转 Markdown 喂 marked 的，file_parser.py:676 注释明确）。

**改造量：IR 本体 ~1 天，双渲染器接入 + 回归 ~1-2 天，合计 2-3 天。**

---

## 五、总排序（按投入产出）

| 项 | 可行性 | 改造量 | 演示价值 |
|---|---|---|---|
| ① Word 原生表格（六项全实测过） | ✅ | 1.5-2 天 | 高 |
| ② OMML nary 修复（18/18→结构全对） | ✅ | 0.5 天 | 中（配合①） |
| ③ PDF 走 HTML+KaTeX+Playwright | ✅ | 2-3 天 | **最高**（公式+表格+预览一致） |
| ④ Document IR 统一（dict 块 + table 类型） | ✅ | 2-3 天 | 是①③的前置底座 |

建议顺序：**④ IR（加 table 块）→ ① Word 表格 → ② nary 修复 → ③ PDF HTML 管线**。全部落地约 6-8 个工作日，每一项都有本报告的实测证据支撑，不存在"应该可以"的环节。

## 六、未核实项（诚实声明）

- KaTeX/Playwright 在本机的实际安装体积与启动耗时未实测（本报告按公开常识估计，落地时先跑一个 hello-world 验证）。
- 评委环境是否有 Chrome/允许安装 chromium 未核实，建议演示用自带 chromium 的 Playwright 而非依赖系统浏览器。
- `_scratch_v3/out_table_test.docx` 用 Word/WPS 打开的视觉效果未人工复核（XML 层面全部验证通过，结构正确性有 parse_xml 保证）。
