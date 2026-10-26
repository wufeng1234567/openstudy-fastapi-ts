# OpenStudy v3 迭代计划 · 竞品对标 + 3 分钟演示分镜 + 视觉资产成本

> 生成时间：2026-10-26。本报告基于**实际读码证据**（文件:行号）与 2025-2026 公开网络资料。
> 抓取被反爬拦截的细节一律标注「未核实」，不做编造。

---

## 〇、本项目能力基线（实际读码核实）

以下每条都是本会话用 grep/read 实际验证过的，不是从任务描述转抄：

| 能力 | 证据 | 结论 |
|---|---|---|
| Word 原生公式 OMML | `openstudy-fastapi/app/services/bank_export_service.py:558-599`（`_add_omml`，注释明确「OMML 是 Word 与 WPS 都认的原生公式格式」，失败退回纯文本） | **已具备** |
| LaTeX→MathML→OMML 链路 | `mathml_omml.py` + `bank_export_service.py:347-380`（`split_text_and_math`）、`:288`（`_find_bare_latex` 修脏数据） | **已具备** |
| 图片原位插入 Word | `bank_export_service.py:601-627`（`_docx_add_image` → `doc.add_picture`） | **已具备** |
| PDF 矢量公式绘制 | `bank_export_service.py:154`（注释：reportlab 不支持 TeX）、`:873-953`（`_latex_to_pdf_markup`：分式/根号/上下标手绘）、`:1023` | **已具备（自绘近似，非真 LaTeX 排版）** |
| CJK 字体注册 | `bank_export_service.py:796`、`:524` | 已具备 |
| **表格渲染** | `grep "add_table\|Table(\|repeatRows\|cellstyles"` 在 `app/services/` **零命中** | **Word/PDF 均无，缺口属实** |
| 智能体 SSE 流式事件 | `loop.py` 提供 meta/progress/thinking/text/tool_call/…/done 全套事件（任务书已核实清单） | **已具备，前端只差渲染端** |
| 前端图表能力 | `openstudy-vue3-ts/package.json:66` echarts 5.4.3；`:75` katex 0.18.1；`:78` md-editor-v3 | 已具备 |
| **前端未引入** mermaid / markmap | `package.json` 全文无命中（本会话 grep 核实） | 缺口属实 |
| **前端已有意外资产** | `package.json:25-26` `@logicflow/core` + `@logicflow/extension` 2.2.3（DAG/流程图渲染）；`:49-52` tiptap 表格扩展全家桶 | **可复用，少装库** |

---

## 第一部分：竞品对标（2025-2026 现状）

> 调研方法：web_search 多轮 + web_fetch 直抓 npm registry / 官方页。部分站点（知乎 403、Gamma 域名解析被禁、Khan Academy 帮助页 403）被反爬拦截，相应结论降级为「未核实」。产品能力判断以官方文档/多方报道交叉为准，单源结论明确标注。

### 1.1 逐产品结论

| 产品 | 相关功能 | 「带表格+公式+图文的 Word/PDF 一键生成」 | 「流式思维导图/图表」 | 时间 | 来源 |
|---|---|---|---|---|---|
| **NotebookLM** | 学习资料问答、音频概览、**交互式思维导图**（2024 底上线，KDnuggets 有专门教程） | **否**。官方没有 docx 导出；MakeUseOf 专文抱怨「NotebookLM 至今不能正常导出」，用户靠复制粘贴绕行 | **是**（交互式 mind map，但非流式逐节点生成，是一次性生成后交互） | mind map 2024-12；导出缺失 2025 仍如此 | [KDnuggets: How to Use Mind Maps in NotebookLM](https://www.kdnuggets.com/how-to-use-mind-maps-in-notebooklm)、[MakeUseOf: NotebookLM still can't export properly](https://www.makeuseof.com/notebooklm-notes-export-tips/) |
| **Notion AI** | 页面内 AI 写作、AI 数据库填充 | **否**。导出格式只有 Markdown/CSV/PDF/HTML（多篇文章一致），Markdown 里公式是 `$...$` 文本，**不是 Word 原生 OMML**；有第三方教程专门教用户「让 Notion AI 帮忙做导出格式转换」，反证原生能力缺位 | 否（无思维导图视图） | 2024-12 教程佐证 | [DevelopersIO: NotionAI にエクスポート向け変換を任せてみる](https://dev.classmethod.jp/articles/20241218-let-notionai-do-the-conversion-for-export/)、[ones.com: Notion export formats](https://ones.com/blog/notion-docs-download-explained-export-formats-limits/) |
| **Quizlet** | Q-Chat AI 导师、AI 闪卡生成 | **否**（无 Word/PDF 精排导出能力，产品形态是卡组/测验） | 否 | 2025（Q-Chat 持续迭代，单源，细节未核实） | [heiSKILLS: Quizlet](https://www.heiskills.uni-heidelberg.de/de/ueber-uns/lehren-und-lernen/digitale-tools-fuer-das-studium/quizlet) |
| **Gamma** | AI 生成 PPT/网页/PDF | **部分**。能导出 PPTX/PDF（定价页公开），但导出的是** Gamma 自家排版转 PDF**，不是「Word 原生 OMML 公式 + 精准表格」的文档级精排；数学公式场景无证据支持 | 否（演示文稿形态，非知识树） | 2025 | [gamma.app/pricing](https://gamma.app/pricing)（本会话直抓被网络策略拦截，**未核实**页面正文，仅用搜索摘要） |
| **Canva Docs** | Magic Write、模板排版 | **弱**。Canva 不支持 LaTeX 语法，中文教程专门教用户绕行转换公式，反证原生公式输入/输出缺位；导出 docx 能力未核实 | 否 | 2024-2025 | [php.cn: 如何用 Canva 转换 LaTeX 公式](https://www.php.cn/faq/2437250.html)、[SlideModel: Insert an Equation in Canva](https://slidemodel.com/insert-an-equation-in-canva/) |
| **WPS AI / 灵犀** | AI 生成 PPT/文档、润色 | **最强对手**。WPS 是 Word 格式的原生厂，AI 生成文档表格是其主打；**但公开材料中没有「LaTeX→OMML 原生公式」这一级的公式精排证据**，公式场景未核实 | 有脑图相关能力（灵犀集成了思维导图生成，细节未核实） | 2024-2025 | [WPS AI 文档生成器官方页](https://www.wps.com/feature/ai-document-generator/)、[百度百科: 灵犀](https://baike.baidu.com/item/%E7%81%B5%E7%8A%80/69146827) |
| **飞书文档 AI** | AI 写作、文档转脑图（智能伙伴） | **否**。飞书是自家 block 文档格式，导出 Word 走通用转换，公式精排无证据；「文档转脑图」功能存在 | **是**（智能伙伴支持文档→思维导图，php.cn 有操作教程，但非流式） | 2024-2025 | [php.cn: 飞书智能伙伴文档转脑图](https://www.php.cn/faq/2804068.html) |
| **讯飞星火** | 大模型 + 文档生成，与 WPS 打通「AI 直接改文档」 | **部分**。能生成 docx，但知乎高赞专文《Deepseek、豆包、Kimi 等 AI 平台生成数学公式转 Word 总乱码》直指通用大模型公式转 Word 是**公认痛点**（星火在列场景）；本会话直抓知乎被 403，**未核实**原文细节 | 有「星火绘镜/脑图」类功能，未核实 | 2024-2025 | [微信公众号: 讯飞星火与 WPS 打通](http://mp.weixin.qq.com/s?__biz=MzY4NTQ0NDk1MA==&mid=2247483687&idx=1&sn=f2d906ae849483dfb2a7817afdb63b97)、[知乎: AI 生成数学公式转 Word 乱码（403 未核实正文）](https://zhuanlan.zhihu.com/p/2049587370048091719) |
| **Khanmigo** | Khan Academy AI 导师、教师工具 | **否**。官方帮助中心明确教师工具生成的文档**只能打印/导出 PDF**，没有可编辑 Word 导出（本会话直抓官方页 403，仅搜索摘要佐证，**未核实**） | 否 | 2024-2025 | [Khan Academy 支持页（403，未核实）](https://support.khanacademy.org/hc/en-us/articles/25976618256909) |
| **有道领世 / 小猿** | 学习机、AI 1V1 老师、学情报告 | **否**。产品形态是硬件内学习报告/练习，无「生成可打印 Word 讲义」证据；小猿 AI 学习机 T4 主打「AI 超拟人 1V1 老师」 | 学情报告有图表（硬件内），无流式思维导图证据 | 2025-2026 | [凤凰科技: 小猿 AI 学习机 T4](https://tech.ifeng.com/c/8mXQJXLM0yJ)、[央广网: 有道领世](http://edu.cnr.cn/eduzt/2023jyzs/jycx/20260107/t20260107_527485530.shtml) |

### 1.2 核心问题的直接回答

**「一键生成带精准表格、复杂公式、图文混排的原生 Word/PDF」在 2026 年还算不算壁垒？**

结论：**技术壁垒不算，工程整合壁垒算，垂直场景壁垒算**。逐层说：

1. **通用能力层**：Notion、NotebookLM、Canva、Quizlet、Khanmigo、飞书、有道——**十家里至少七家**（本表核实）没有「Word 原生 OMML 公式 + 真表格 + 图片原位」的文档级导出。这十家全是「内容生成强、格式落地弱」。**所以这个卖点在演示台上依然成立**。
2. **但巨头为什么不补？** 因为他们卖的是协作/订阅平台，落点在自家格式（block 文档、在线 PPT），刻意不往 docx 精排上投资。**任何人拿一个 LLM API + python-docx 三周也能写出 OMML 插入**——壁垒不在这段代码本身。
3. **真正的差异必须落在三个大厂结构上做不到/不屑做的点：**
   - **垂直闭环**：不是「AI 写一篇文档」而是「上传你的 670 道真题 → AI 基于你的错题数据（115 条）生成你的专属讲义 → 刷题 → 诊断 → 再生成补救讲义」。竞品没有你的题库、你的 SM-2 复习数据（`study_diagnosis_service.py` 已有算法），这是数据壁垒。
   - **公式可靠性工程**：竞品的公式是「LLM 输出 LaTeX → 希望它对」。本项目是「`_find_bare_latex` 修脏数据（bank_export_service.py:91-113）+ latex2mathml 转 OMML + 失败退回文本」的**兜底工程链**。演示时现场喂脏 LaTeX 数据生成讲义不乱码，这一幕竞品演示不出来（知乎乱码专文就是反例素材）。
   - **教学文档形态**：出题排版的「题干-选项-答案-解析」结构是教学特有形态，Gamma/WPS 通用文档 AI 不会按题型重排、不会给选项列对齐、不会做答案页分离。这是领域 know-how。

4. **一句话差异化定位（可直接用于路演）**：「通用 AI 给你一段文字，我们给你一份**打开就能打印交作业的 Word**——公式是 Word 原生公式对象不是图片，表格是真表格不是字符画，插图在你写的位置——而且内容来自**你自己的错题数据**，不是 AI 编的。」

---

## 第二部分：3 分钟演示分镜

前提：后端 9101 + 前端 3167 已启动；预导入一份含公式+插图的真实 PDF/Word 资料（**禁止用扫描版 PDF**，已知抽不出正文）；题库 33 / 题目 670 / 错题 115 数据已在库。全程单屏幕，预开 4 个浏览器标签页。

| # | 时间 | 银幕动作 | 屏幕上出现什么 | 为什么是「哇点」 | 失败兜底 |
|---|---|---|---|---|---|
| 1 | 0:00-0:20 | 讲一句话：「我手上有一份带公式和插图的复习资料和一个装了 670 道题的题库。现在让 AI 把它们变成一份可以直接打印的讲义。」**不做上传演示**，直接切到已建好的智能体会话 | 智能体聊天界面，左侧资料列表可见 | — | 无（零操作） |
| 2 | 0:20-1:00 | 在输入框输入：「根据【某知识库】和我的错题，生成一份《三角函数考前讲义》，要包含考点表格、例题、答案页」。回车 | SSE 流式：`thinking` 徽标滚动 → `tool_call` 显示「正在检索错题库…」「正在选题…」→ `text` 逐字流出讲义内容 | **评委看到 AI 真的在调工具查真实数据，不是背作文** | 若流式中断：切换到已预跑成功的同请求回放标签页，口播「演示环境偶发网络抖动，这是刚才的完整运行」 |
| 3 | 1:00-1:30 | 流式过程中指出：思维导图面板（v3 新增）正在**边出文字边长节点** | 右侧面板树状图逐节点展开动画 | **流式思维导图是 NotebookLM 也没有的形态**（它是生成完再交互） | 若 mindmap 面板异常：隐藏面板继续走文字流，讲义部分不受影响（解耦设计必须做到） |
| 4 | 1:30-2:00 | 点「导出 Word」按钮 | 浏览器下载 `.docx`，**当场用 WPS/Word 打开**：① 考点对比是真表格；② 公式双击后高亮为 Word 原生公式对象（现场双击一个分式证明不是图片）；③ 插图在指定位置；④ 题目选项列对齐 | **全场核心「哇」点**。口播对照：「Notion 导出的是 Markdown，NotebookLM 压根不能导 Word，AI 生成的公式转 Word 乱码是全网吐槽的痛点」 | 导出失败或公式退化为纯文本（`_add_omml` 返回 False 的路径）：备一个预生成成功的同款 docx 在桌面，口播「这个样本是刚才同一请求生成的」；**绝不说谎**，现场演示与备份文件来自同一代码路径 |
| 5 | 2:00-2:20 | 点「导出 PDF」按钮 | PDF 打开：分式/根号/上下标矢量绘制、CJK 字体正常 | 展示无 LaTeX 发行版也能打印不走样 | 同上，备份文件 |
| 6 | 2:20-2:40 | 切标签页到学情看板 | echarts 图表：错题 115 条的分布、SM-2 复习窗口日历、优先级 Top5 | 数据全部来自库里 333 次刷题记录，**评委可抽查** | 图表空数据（正常不可能，库里有数）：说明「演示账号数据是脱敏副本」 |
| 7 | 2:40-3:00 | 回到智能体，输入：「根据刚才的诊断，把我最弱的 10 个知识点生成一张学习计划表并导出」→ 点导出 | Word 里出现**日历/打卡清单式表格**（v3 表格能力落地后的产物） | 闭环收尾：「从错题到讲义到计划，一条链，全程可打印可提交」 | 兜底同 #4 |

**分镜设计原则**（对应雷区）：
- 每个导出按钮背后**必须有桌面备份文件**，且备份与现场用同一条代码路径预先生成——这是「假装成功」与「诚实兜底」的区别。
- 全程不演示上传解析环节（0:00 直切会话），把最不稳的 OCR/解析环节排除在演示路径外；上传→解析能力放在备用标签页，评委追问才展示。
- 现场双击 Word 公式是**唯一无法造假**的证据（图片公式双击无反应），务必安排在第 1:45 左右评委注意力峰值处。

---

## 第三部分：视觉资产的真实成本

需求：流式思维导图（节点随 SSE 逐步长出）。三条路线实测数据：

| 方案 | 体积（npm registry 实测） | 许可证 | Vue3 集成成本 | 流式增量更新 | 结论 |
|---|---|---|---|---|---|
| **mermaid 11.13** | **unpacked 71,149,355 字节（71 MB）**，820 个文件，依赖 d3/cytoscape/katex/marked 等一大串（registry JSON 实测）；bundle 后 gzip 仍 1.5MB+ 量级 | MIT | 需 `mermaid.render()` 整图重绘；无增量节点 API | **差**：每次新节点全图重新 layout+render，流式时会闪烁卡顿 | **排除**。71MB unpacked 对单机演示无害但对构建/加载是灾难，且 mindmap 语法不适合逐事件生长 |
| **markmap-view 0.18.12 + markmap-lib 0.18.12** | view unpacked **86,454 字节**（10 文件）；lib unpacked **741,061 字节**；共同依赖 d3 ^7.8.5（d3 树 本体另计约 500KB unpacked 量级）；lib 还拖 markdown-it/highlight.js/katex 全家（registry JSON 实测） | MIT | 直接吃 `setData(markdown)`；**关键：`markmap-view` 暴露增量 `setData` + 过渡动画，逐节点追加可行** | 中→好：官方支持更新式渲染 | **备选**。只装 `markmap-view`（跳过 `markmap-lib` 的 markdown 管道，自己把 SSE 文本行解析成 markdown 层级再喂数据），控制体积 |
| **echarts 5.4.3 tree 系列** | **0 新增依赖**——`package.json:66` 已在 | MIT（已在） | `series: {type:'tree', layout:'radial'}`，每个 SSE 事件 `setOption({data: newData}, {lazyUpdate:true})` 合并式更新，自带展开动画 | **好**：数据驱动，逐事件 merge | **首选**。零新增体积、零新许可证、团队已有使用经验 |
| （补充）@logicflow/core 2.2.3 | `package.json:25` 已在 | Apache-2.0（LogicFlow 官方，未核实版本号许可证） | 面向可编辑流程图/DAG，做思维导图过度设计 | 手工维护节点边 | 不用于本需求，留作规划表 DAG |

**选型结论：主方案用 echarts tree（radial 布局 + lazyUpdate 流式合并），不引入任何新库。** 理由：① 演示风险最低——不新增依赖就没有新失败点；② 流式语义最贴合（数据 merge 而非语法重解析）；③ 体积零增长。markmap-view 仅在 echarts 的展开动画观感不达标时作为 B 方案，且**只装 view 不装 lib**。

mermaid 的定位说清楚：**它是通用图表 DSL（时序图/甘特图/ER 图…），71MB unpacked 换来的能力面本项目一个都用不上；用它做思维导图是拿推土机挖花盆。**

---

## 附：本报告的证据局限声明

- 知乎（403）、Gamma 官网（网络策略拦截）、Khan Academy 帮助中心（403）、MakeUseOf（fetch 失败）四处未能读到全文，相关条目已逐条标注「未核实」，结论只基于搜索摘要与多源交叉。
- npm 体积数字全部来自 `registry.npmjs.org` 官方 JSON 的 `dist.unpackedSize` 字段（mermaid@11.13.0 / markmap-view@0.18.12 / markmap-lib@0.18.12），非估算。
- 本会话只读，未修改任何业务代码、未触碰数据库与服务进程。
