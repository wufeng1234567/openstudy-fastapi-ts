# OpenStudy v3 现有资产盘点

> 盘点日期：2026-10-26　仓库根：`D:\OpenStudy\apps\fastapi-v2`
> 全部结论均由 `read` / `grep` / `pwsh` 实测得出，每条带 `file:line`。
> 本次为**只读**审查，未修改任何业务代码、未重启服务、未连数据库执行写操作。
>
> **勘误（与任务书给定的字节数不同，以实测为准）**：行数实测如下
> `bank_export_service.py`=**1253** 行（任务书写 52KB）、`file_parser.py`=**802** 行、
> `diagnosis_report_service.py`=**318** 行、`study_diagnosis_service.py`=**974** 行、
> `mathml_omml.py`=**456** 行、`loop.py` 未逐行统计。

---

## 0. 一句话结论

**家底是「深」而不是「宽」**：后端工具体系、 demonstrates 确定性诊断算法、题库导出的 Word/PDF
渲染这三块是**真的跑通了**，而且工程密度高于一般参赛项目（有逆转热源:
成品的内 Project Management 细节属性例如 undo_plan / preview / confirm_policy / 越权修复日期都在代码里）。

但**「腰椎」是断的**：

1. **结构信息在入口就被压平了** —— 解析器把 Word 表格降级成 Markdown 字符串（`file_parser.py:717`），
   知识库入库只存 `raw_content` 纯文本（`knowledge_ingest.py:318`），知识检索返回扁平 chunk（`knowledge_search.py:229`）。
   **所以「生成原生表格」在上游就无米可放。**
2. **导出侧没有表格渲染能力** —— `bank_export_service.py` 全文只有 `add_paragraph` / `add_picture`，
   PDF 侧只 import 了 `Paragraph, SimpleDocTemplate, Spacer`（`:1133`），**无 `add_table` / `Table`**。
   实测证实任务书说的「零命中」属实。
3. **前端消息块只有 8 种类型，流式通道只认文本** —— `text` 事件一路到 `v-html`，
   没有图表 / 思维导图 / 表格的挂载点。`AiChatStream` 全文无 `echarts` / `mermaid` 引用。

**结论：v3 的亮点必须补「结构」这一层，否则用户那两段话术兑不了现。**

---

## 1. 后端 17 个智能体工具逐个盘点

### 1.0 统一契约（先于逐个判断）

| 项 | 结论 | 证据 |
|---|---|---|
| 返回结构 | **统一**。`ok(**payload)` → `{"success":True,...}`；`fail(error,hint,**payload)` → `{"success":False,"error","hint"}` | `base.py:137-139` / `base.py:164-175` |
| 注册 | 集中式、幂等，17 个全在 `registry.register(...)` | `tools/__init__.py:35-81` |
| 双语言隔离 | `name/description/parameters` 英文（给模型）；`label/description_zh` 中文（只给界面），且有 CJK 守卫测试 | `base.py:193-211` |
| action 非法值 | 全部返回 `fail(...)` 并给出可选 action 清单，**无一个是沉默通过** | 逐个文件核实（见下表） |
| 占位 / TODO | **0 处**。`TODO|FIXME|NotImplemented|pass #|mock|假数据` 全部 grep 下来只有 5 个命中，且全 CJK 出现在注释里的无关词汇 | `tools/` 全目录 grep |

**这一层非常扎实**：这不是「17 个半成品」，而是一套有纪律的工具框架。

### 1.1 逐个清单

| # | 工具名 | 行数 | action 数 | 真实能力 | 是否残缺 | jumpUrl |
|---|---|---|---|---|---|---|
| 1 | `question_manage` | 1294 | 9 | 题目全 CRUD + **batch_import（AI 建库主通道）** | ✅ 完整 | ✅ `:696` `:875` |
| 2 | `question_flag_manage` | 726 | 4 | 错题本/收藏/斩题三合一（`flag_type` 区分） | ✅ 完整 | ❌ 无 |
| 3 | `bank_manage` | 665 | 7 | 题库 CRUD + `delete_by_name` / `delete_many` | ✅ 完整 | ✅ `:470` |
| 4 | `bank_export` | 468 | 1(隐含) | 导出 Word/PDF，`format`×`with_answers` 两开关 | ✅ 完整 | ❌（用 downloadUrl `:316`） |
| 5 | `bank_share_manage` | 595 | 5 | 分享 / 撤销 / 领取 / 复制 / 列清单 | ✅ 完整 | ❌ 无 |
| 6 | `agent_manage` | 360 | 4 | 自定义智能体 CRUD + 工具白名单校验 | ✅ 完整 | ❌ 无 |
| 7 | `knowledge_base_manage` | 760 | 7 | 知识库 + 文档管理，`disabled` 屏蔽位 | ✅ 完整 | ❌ 无 |
| 8 | `knowledge_ingest` | 453 | 2 | 文本/附件写入知识库，**后台向量化** | ⚠️ 见 §1.2 | ✅ `:355` |
| 9 | `knowledge_search` | 313 | 2 | 混合检索（关键词+向量），双路打分 | ⚠️ 见 §1.2 | ❌ 无 |
| 10 | `workspace_search` | 170 | 2 | 按文件名/备注/正文找「那份资料」 | ✅ 完整 | ❌ 无 |
| 11 | `memory_manage` | 399 | 3 | 记忆分类计数 / 遗忘 / 清空 | ✅ 完整 | ❌ 无 |
| 12 | `memory_search` | 181 | 2 | 长期记忆检索 | ✅ 完整 | ❌ 无 |
| 13 | `note_manage` | 862 | 9 | 笔记 CRUD + 分类 + **草稿** | ✅ 完整 | ❌ 无（见 §1.2） |
| 14 | `learning_stats` | 447 | 8 | 5 个聚合 + `diagnose` / `plan_review` / `diagnose_report` | ✅ 完整 | ❌（report 用 downloadUrl `:438`） |
| 15 | `english_wordbook` | 677 | 10 | 词书 / 单词 CRUD + 批量加词 | ✅ 完整 | ✅ 多处 `:336,372,475,496,546,609` |
| 16 | `english_practice` | 761 | 5 | 练习记录统计 + **生成带参练习链接** | ✅ 完整 | ✅ `:339,406,459,466,491,582,620` |
| 17 | `delegate_task` | 150 | 1 | 派给专家子代理（**真并发**） | ✅ 完整 | ❌ 无 |

**重要更正（任务书隐含假设"这些工具很可能半截"）**：实测 **17 个工具没有一个是不完整的**。
全部有完整 parameters schema、全部覆盖非法 action、大部分写操作都实现了 `undo_plan` / `preview` /
`needs_confirmation` / `is_destructive` 四个钩子。这个完成度高于预期。

### 1.2 三条「不是残缺、但会卡住 v3」的判断

**(a) `knowledge_ingest` 只存纯文本 —— 这是「原生表格」的第一个断点**

```python
# knowledge_ingest.py:313-319
doc = await rws.create_document(
    db, ctx.user_id, kb_id,
    file_name=file_name,
    raw_content=text,          # ← 只有 str，无段落/图/表/层级
    file_type="text",
    status=DOC_PENDING,
)
```
`from_attachment` 取的也是已经压平的 `att["text"]`（`knowledge_ingest.py:420`）。
**结论**：入库即失结构。下游无论多聪明都拼不回「哪几行是一张表」。

**(b) `knowledge_search` 返回扁平 chunk —— 第二个断点**

```python
# knowledge_search.py:219-238
hits.append({
    "chunkId", "docId", "docName", "chunkIndex", "kbId", "source",
    "content": content,        # ← 扁平文本
    "keywordScore", "vectorScore",
    "images": images,          # ← 有图
})
```
有 `images`（这点好），但**没有** 标题层级 / 页码 / 表格标记。
**结论**：`content` 里的表格此刻已经是 Markdown 竖线文本（被 `file_parser` 压过一轮）。

**(c) `note_manage` 写成功却不给跳转 —— 闭环缺口（可低成本补）**

`_create` 的回执（`note_manage.py:674-678`）只有 `note` + `message`，**没有 `jumpUrl`**。
而 `bank_manage._create`（`bank_manage.py:470`）明明已经有了。
```python
# note_manage.py:674-678
return ok(
    action="create",
    note=nws.note_brief(note),
    message=f"笔记「{note.title}」已保存...",
    # ← 没有 jumpUrl
)
```
前端契约是**输出驱动**的（`AgentToolResult/index.vue:685-695`：有 `jumpUrl` 就出卡），
所以只要补一个字段就能闭环 —— 这是 v3 最便宜的一笔投资。

### 1.3 jumpUrl 覆盖率：5 / 17

- **有**：`bank_manage`(1 处) / `question_manage`(2) / `english_wordbook`(6) / `english_practice`(7) / `knowledge_ingest`(1)
- **无**：其余 12 个

`english_practice(action=start)` 是全项目**闭环最深**的一处 —— 它拼的是**带参深链**：
```python
# english_practice.py:589-596
jump = (f"/front/english/listening?auto=1&bookId={book_id}&mode={mode}"
        f"&scope={scope}&words={quote(seed, safe=',')}")
```
用户说「帮我生成一组听力练习」→ 智能体挑词（真查 `WordLearningState.due_date`，
`english_practice.py:647-676`）→ 返回点击即练的链接。**这条链路已经完全打通，
是 v3 应当复用的范式。**

---

## 2. 文档解析：`file_parser.py`（802 行）

### 2.1 输出数据结构（实测字段）

```python
# file_parser.py:371-377  ( _BlockBuilder.result() )
{
    "textContent": "\n".join(self._text_parts),   # 纯文本（老调用方降级用）
    "blocks": [ ... ],                            # 有序块
    "images": [ {"orderIndex","imageUrl","imageName"} ],
    "totalTextLength": int,
}
# file_parser.py:450  主入口再补一个 fileName
result["fileName"] = filename
```

**`blocks` 里只有两种 type（这是本章最重要的发现）**：
```python
{"type":"text",  "content": "...", "orderIndex": n}        # file_parser.py:333-335
{"type":"image", "content":"", "orderIndex": n,            # file_parser.py:352-359
 "imageUrl": "data:...", "imageName": "image1.png"}
```
**没有 `"table"` 类型。** 全文件 `"type":` 的取值经 grep 确认只有 `text` / `image` 两种。

### 2.2 表格怎么被处理的 —— 降级成 Markdown 字符串

```python
# file_parser.py:667  _emit_table()
def _emit_table(builder, tbl_elem, image_blobs) -> None:
    """输出一个表格为**标准 Markdown 表格**（用户 2026-10-11 方案 A）"""
    ...
    lines.append("| " + " | ".join(cells) + " |")        # :712
    if i == 0:
        lines.append("| " + " | ".join(["---"]*ncol)+" |")  # :715 表头分隔行
    builder.add_text("\n".join(lines))                   # :717 ← 塞进 text 块
```

它**认得出**表格（`r` 是与\neg 二维结构都读对了：`tr` / `tc` / 嵌套 `tbl` 都处理了，`:680-702`），
有一套很用心的 `_md_cell()` 清洗（折叠换行、转义单元格内竖线，`:655-664`），
甚至「**前置吐槽」Aware**：docstring（`:670-676`）明确写了「以前只输出 `a|b|c` 纯文本 → 前端 marked 认不出
→ 用户看到一串竖线」，于是加了表头分隔行让 `marked` 能渲染。

**但这是一个 Arbeiten-around，不是结构保留**：
- `blocks` 里它是 `type:"text"`，任何消费方拿到都不知道「这里原本是一张表」；
- 表格里的单元格图只好移到表格块之后补发（`:719-724`），**位置信息已经丢失**；
- 合并单元格 / 列宽 / 表头样式全部不存在。

**对 v3 的含义**：用户要的「生成原生表格」在解析这一侧**不是不能做**，
而是要在 `_emit_table` 里**并列**加一条 `builder.add_table(rows)`（产出 `type:"table"` 块），
保留二维结构到下游。**这是一处 ~40 行的增量，是全 v3 性价比最高的改动之一。**

### 2.3 OMML 与 LaTeX 两条路径

| 来源 | 处理 | 产出 | 证据 |
|---|---|---|---|
| DOCX **OMML**（Word 原生公式 `<m:oMath>`） | `_omml_to_latex()` 手写 OMML→LaTeX 转换器 | 行内 `$...$` / 行间 `$$...$$` | `:584-591`，实现见 `:46` `_omml_to_latex`、`:55` `_convert_element`、`:161` `_run_text`、`:188` `_get_nary_char`、`:199` `_nary_char_to_latex`、`:214` `_get_delimiter` |
| 纯 LaTeX | 不转换，**原样透传** | 原字符串 | —— |

```python
# file_parser.py:583-591
if tag == "oMath":
    latex = _omml_to_latex(child)
    if latex: yield ("text", f"${latex}$")
elif tag == "oMathPara":
    for omath in child.iter(_qn(M_NS,"oMath")):
        latex = _omml_to_latex(omath)
        if latex: yield ("text", f"$${latex}$$")
```

**关键判断**：OMML 进来 → **退化成 LaTeX 字符串**。这条路在导出侧能救回来（`bank_export_service._add_omml`
用 `latex2mathml` 再转 OMML，`bank_export_service.py:558`），**但 DOM 走了两次有损转换**
（OMML → LaTeX → MathML → OMML）。这条链路的可逆性**未核实**（未实测提取后再导出的公式群是否等价）。

### 2.4 图片与段落对齐 + `【图N】` 怎么用

**三重顺序保证**（这部分做得很好）：
1. `_iter_paragraph_parts()`（`:570-604`）按**原始 XML 文档顺序**产出 `('text',...)` / `('image',rId)`，
   docstring（`:571-575`）明确写了为什么不用旧函数：「那个会把整段文本拼在一起、图片再统一抽，
   于是『文字在前、图在后』的段落会把图排到文字前面」。
2. `_BlockBuilder` 用同一个 `len(self.blocks)` 作为 `orderIndex`，图文**共用一个自增序号**（`:334` / `:356`）。
3. `build_marked_document()`（`:510-554`）把 blocks 渲染成**正文里嵌 `【图N】` 标记**的形式。

```python
# file_parser.py:507
IMAGE_MARKER_TMPL = "【图{}】"
# file_parser.py:532-534
if block.get("type") == "image" and block.get("imageUrl"):
    parts.append(IMAGE_MARKER_TMPL.format(offset + len(image_urls)))
    image_urls.append(block["imageUrl"])
```

**用法链条**：模型把 `【图N】` 原样写进题干 → 工具侧正则替换成 `<img>`：
```python
# question_manage.py:55
_IMAGE_MARKER = re.compile(r"【图(\d+)】")
# question_manage.py:74-84  _sub(): N 号图存在就换成 <img>，不存在就丢掉并记录 dropped
```
】, 在 `_create`（`question_manage.py:673`）和 `_batch_import`（`:811,:814`）都接了，
 `droppedMarkers` / `droppedImageMarkers` 会回报丢失的标记（`:694` / `:866`）。

**一个不一致（次要）**：`_update`（`question_manage.py:878-925`）写 `question_text` 时
**没有**走 `_replace_image_markers`（`:888` 直接赋值），与 `_create` 口径不一致。

**mark privileged**：标记模板带着一句很硬的注释（`:502-506`）：
「这是**数据标记**，不是提示词文案 —— 即使系统提示词全英文，它也保持中文。
别为了『全英文』把它改成 `[IMAGE_N]`，那会让整条图片链路失效。」

### 2.5 已实现的健壮性（值得一提）

- **文件头嗅探**（`:389-398`）：按魔数 ZIP/OLE2/PDF 判真身，纠「docx 改名成 .doc」。
- **PDF 插图**（`:751-773`）：pypdf `page.images` 抽，精度到「页」（docstring 承认定位是页级近似）。
- **嵌套容器**（`:727-736`）：`sdt` / `sdtContent` / `body` 递归。
- **VML 老图**（`:599-604`）：除了 DrawingML 的 `blip`，还认 `w:pict` → `v:imagedata`。

---

## 3. 导出：`bank_export_service.py`（1253 行）+ `diagnosis_report_service.py`（318 行）

### 3.1 Word 版式（实测推断）

```python
# bank_export_service.py:674-704
doc = Document()
section.left_margin = Cm(2.4);  section.right_margin = Cm(2.4)
section.top_margin  = Cm(2.2);  section.bottom_margin = Cm(2.0)
# 封面区
title_p = doc.add_paragraph(); 居中; 20pt bold            ← 题库名
meta_p  = 居中 9pt 灰「科目 · 题目数 · 创建时间 · 版本」
desc_p  = 居中 9.5pt 灰
# 题目正文（:709-783）
```

| 元素 | 实现 | 证据 |
|---|---|---|
| **封面** | ✅ 有（题库名 + 元数据行 + 描述） | `:683-706` |
| **目录（TOC）** | ❌ **无**（全文无 TOC 字段/指令） | 缺失 |
| **页眉页脚 / 页码** | ❌ **无**（无 `sections[0].footer` / 页码域） | 缺失 |
| **题型分组** | ❌ **无**（按 `sort_order` 一条平铺，题间画 `─`×34 分隔线） | `:709` 单循环、`:780-783` |
| **题号 + 题型徽标** | ✅ `{idx}.` + `［题型］` 灰色小字 | `:714-717` |
| **选项** | ✅ 字母 A/B/C，缩进 0.75cm | `:724-730` |
| **子题（组合题）** | ✅ 支持，`(n)` 编号 + 独立选项与答案 | `:733-750` |
| **答案/解析** | ✅ 绿色加粗「答案：」+「解析：」 | `:752-769` |
| **学生卷（无答案）** | ✅ 简答题留 3 个空段 | `:770-777` |
| **图片原位** | ✅ `_docx_add_blocks` 按 HTML 块顺序插图 | `:601-656`、`:721` |
| **原生公式 OMML** | ✅ `_add_omml`（latex→MathML→OMML） | `:558-583` |
| **CJK 字体** | ✅ 微软雅黑 | `:524` `_docx_set_cjk_font` |
| **表格** | ❌ **无** | 全文无 `add_table` |

**答复「导出的 Word 到底长什么样」**：
一页语文科目verture —— **封面 + 题目流水**，每道题是「加粗题号 + 灰色题型徽标 + 题干（可含图与公式）
+ 选项 + 答案 + 解析 + 一条灰色分隔线」。版心规整、CJK 与 OMML 都处理了，
**但它是一份"题目列表"，不是一份"讲义/试卷"**：没有按题型分节、没有答题区表格、没有页脚页码。

### 3.2 PDF 版式

```python
# bank_export_service.py:1138-1143
doc = SimpleDocTemplate(buf, pagesize=A4,
    leftMargin=2.4*cm, rightMargin=2.4*cm,
    topMargin=2.2*cm, bottomMargin=2.0*cm,
    title=...)                       # ← 只设了 title 元数据
# :1133
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer   # ← 没有 Table
```
同样的「封面 + 平铺」结构。有一个巧思：`_keep_together_if_fits`（`:1088`, `:1250`）
先量高度再决定是否 `KeepTogether`，避免「题干和配图被拆到两页」——
注释（`:1247-1249`）说清了为什么不能直接 KeepTogether（长题会让 reportlab 反复重排失败）。

**PDF 也确认无表格、无页眉页脚、无 TOC。**

### 3.3 LaTeX 脏数据修复 —— 它说明了什么历史问题

```python
# bank_export_service.py:71-86
#: 实测（题库 172）：
#:   · `\times` 被存成了 `<TAB>imes`  —— `\t` 整体被当成制表符落库
#:   · `\frac`  被存成了 `<FF>rac`    —— `\f` 整体被当成换页符落库
_ESCAPE_LETTER = {"\t":"t", "\f":"f", "\v":"v"}
```
```python
# bank_export_service.py:128-135
#: ⚠️ 存量数据里确实有：题库 172 的解析就带 0x0C/0x09，
#:    直接塞进 python-docx 会抛 ValueError: All strings must be XML compatible
```

**这段修复揭穿了三件事**（这是本次盘点最有价值的史料之一）：

1. **历史上真实存在过一批" LaTeX 被 Python 转义序列吃掉了反斜杠"的脏数据**。
   `\times` → `\t` + `imes`：反斜杠在某次序列化/反序列化环节被当成了转义符。
   **文件名命名了 "题库 172"** —— 是当时的真实生产数据，不是作者臆想。
2. **当时的导出会因为 XML 非法控制字符直接 500**（Excel 导出早先已经踩过一次，
   注释里点名同源 `utils/excel_util.ILLEGAL_CHARACTERS_RE`）。
3. **修复姿势是"白名单 + 顺序敏感"的**：
   - 白名单（`:51-69` 近 80 个命令名）是为了不误伤 `col1<TAB>col2` 这种正常排版（`:48-50` 明说：
     「宁可漏还原（顶多排版不完美），也不能把正常文字改坏 —— 后者是内容错误」）；
   - **顺序**（`:134`）：必须先 `_repair_pseudo_escapes` 再剔除控制字符，「否则反斜杠就没得还原了」。

**给 v3 的教训（重要）**：这个项目历史上不止一次出现「**上层 LLM / 序列化把 LaTeX 弄脏，
只能在导出层兜**」的模式。`diagnosis_report_service.py:70-88` 也是同一个套路
（题干里大量 Word/WPS 导入的裸 LaTeX，直接印出来就是一串反斜杠）。
**如果 v3 要打「复杂公式打印不走样」这张牌，得先问：脏数据是在哪一环产生的？
能不能在入口就钉死，而不是继续在导出层打补丁。**（当前策略是打补丁，作者自己也知道。）

补充：`diagnosis_report_service.py:18-23` 里有一条很清醒的排版取舍
——「不用 reportlab 的 Table 画列：中文长文本自动折行很别扭，activities 要么撑破列宽要么被截断」。
**这条注释恰好预言了 v3 的难点**：不是「该不该用表格」，而是「中文 + 长文本 + 表格」在 reportlab 里难处理。
同注释还写了「PDF 可能被黑白打印 —— 只靠颜色区分的报告打印出来就废了」（`:22-23`，
实现见 `:36-46` 每档都有中文标签）。

### 3.4 `diagnosis_report_service.py` —— 只有 PDF，没有 Word（任务书说法属实）

全文 318 行，只有 `export_diagnosis_pdf()`（`:91`）一个导出函数，`docstring:25-26` 写明
「本模块**不重新计算任何诊断**：它只消费 `study_diagnosis_service.diagnose()` 的返回值」——
这个设计是对的（单一数据源）。**Word 版缺失属实。**

---

## 4. 前端流式渲染（关键）

### 4.1 SSE text delta 的真实链路（三层）

任务书猜的是「`views/front/` 下约 78KB 的 chat 页面」。实测** chat.vue 自己不处理 SSE**，
链路是三层：

```
① transport ：src/api/ai/agent.ts:579  postAgentStream()
                 :656  const reader = response.body.getReader()
                 :657  const decoder = new TextDecoder('utf-8')
                 :662-684  handleLine()：按 \n 切分，'{' 开头就 JSON.parse→emit
                 :686-695  for(;;) await reader.read() 主循环
                 :588-600  emit()：text 累加 answer / done 收尾 / error 置 failed
                 └─ :671  emit(JSON.parse(line) as AgentEvent)   ← **text delta 到这里的准确位置**

② dispatch ：src/composables/useAgentChat.ts:1237  handleEvent(event)  ← switch(event.type)
                 :1246-1248   case 'text': appendText(event.content || '')
                 :1239-1244   case 'meta'  : tools/model/warnings/imageCount
                 :1257-1260   case 'progress': upsertProgressStep(event)
                 :1262-1278   case 'tool_confirm'
                 :1302-1309   case 'tool_start' / 'tool_result'
                 :1313-1324   case 'delegate_start' / 'delegate_done' / 'subagent_event'
                 :1331-1355   case 'metrics'
                 :1366-1369   case 'error'
                 :1371-1382   case 'done'
                 └─ :1384-1385  default: break   ← **未知事件类型被静默丢弃**

③ render   ：src/views/front/agent/chat.vue:108   <AiChatStream :messages="messages">
              └─ src/components/AiChatStream/index.vue（1865 行）
                   :182  <div class="message-text rendered-md" v-html="renderAgentMarkdown(msg.content)">
                   :275  import { renderAgentMarkdown } from '@/utils/markdown'
```

> chat.vue 实测 **1918 行 / 76.8KB**（任务书说 78KB，接近）。它只是把 `messages` 交给 `AiChatStream`。
> 另有并行链路 `src/api/ai/agentDsFree.ts`（ds-free 浏览器桥），契约与 `agent.ts` **逐字一致**
> （`agentDsFree.ts:9` 明说「事件契约与 `agent.ts` 的 `postAgentStream` 完全一致」），
> 消费方同为 `useAgentChat.handleEvent`（`agentDsFree.ts:1318`）。**两条链路共用第②③层。**

### 4.2 现在支持哪几种消息块（实测 8 种）

类型联合声明确切位置：
```ts
// src/composables/useAgentChat.ts:198
type?: 'tool_result' | 'agent_note' | 'thinking' | 'reasoning'
     | 'tool_confirm' | 'turn_end' | 'experts' | 'progress'
```
渲染分支（`AiChatStream/index.vue`）：

| type | 渲染位置 | 作用 |
|---|---|---|
| `tool_confirm` | `:27-31` | 写操作二次确认卡（走 `#tool-confirm` 插槽） |
| `tool_result` | `:33-37` | 工具结果（走 `#tool-result` 插槽 → `AgentToolResult`） |
| `reasoning` | `:45-47` | 深度思考折叠块（**不暴露推理正文**，只有一个等待动画） |
| `progress` / `thinking` | `:62-81` | 步骤清单（三点抖动 +  steps 列表） |
| `agent_note` | `:86-98` | 纠正/告警/错误提示条 |
| `turn_end` | `:114-118` | 轮末动作条（回退/复制挂这里） |
| `experts` | `:125-134+` | 专家工作组卡片（多专家并行） |
| *(缺省)* | `:182` | **正文 Markdown**，`v-html="renderAgentMarkdown(msg.content)"` |

**回答「支持 markdown？公式？工具卡片？图片？」**：
- **markdown** ✅ 正文走 `renderAgentMarkdown`
- **公式** ✅ 由 markdown 渲染链路里的 katex 负责（/`utils/latex.ts` 24KB / `src/components/LatexRenderer/LatexRenderer.vue` 3.7KB）
- **工具卡片** ✅ `tool_result` → `AgentToolResult`（1475 行，能渲染产物卡 / 跳转卡 / 勾选卡）
- **图片** ⚠️ 正文 HTML 里的 `<img>` 能显示（html 富文本），但没有独立的「图片块」类型

### 4.3 加一种全新消息块（如图表/思维导图）要改几处

**答案：最少 4 处，加 SSE 事件则是 5 处。**

| # | 文件:行 | 改什么 | 必要性 |
|---|---|---|---|
| 1 | `src/api/ai/agent.ts:20` `AgentEventType` | 加新事件类型字面量（如 `'chart'`） | 若走新 SSE 事件则必需 |
| 2 | `src/composables/useAgentChat.ts:198` | 往 `type?` 联合里加一个新成员 | **必需** |
| 3 | `src/composables/useAgentChat.ts:1237` `handleEvent` switch | 加一个 `case 'chart':` 分支，`messages.value.push({...})` | **必需**（否则 `default: break` 静默丢弃） |
| 4 | `src/components/AiChatStream/index.vue:27-134` 的 `v-if` 链 | 插入一个新 `v-else-if="msg.type === 'chart'"` 分支 | **必需** |
| 5 | 新组件（如 `src/components/AgentChartBlock/index.vue`）+ import | 实际渲染 | **必需** |

**顺序有坑**（`AiChatStream/index.vue:103-106` 有原文警告）：
> ⚠️ 这个分支**必须排在下面 `msg.role === 'assistant'` 那个正文分支之前**。
> `turn_end` 的 `role` 也是 assistant…排在正文分支后面就永远轮不到它

所以新分支要插在**正文缺省分支（`:182`）之前**。

**另一个坑**：懒加载与虚拟窗口。`AiChatStream` 只渲染最近 N 条
（`chat.vue:702` 提到 `RENDER_CHUNK=40`），新块组件要能在挂载时自己初始化
（参考 `myStats/index.vue:313` 的踩坑注释：「echarts 容器刚从 `display:none` 变可见，之前算的尺寸是错的」）。

### 4.4 `aiMarkdown.ts` / `latex.ts` / `LatexRenderer/` 各是什么角色

| 文件 | 实测 | 角色 |
|---|---|---|
| `src/utils/aiMarkdown.ts` | 2.5KB | 轻量侧工具（AI 场景专用） |
| `src/utils/markdown.ts` | 2.1KB | **正文实际走的是它** —— `AiChatStream:275` import 的 `renderAgentMarkdown` 来自这里 |
| `src/utils/latex.ts` | 24KB | LaTeX 识别/清洗/渲染的主力（公式的所有脏活） |
| `src/components/LatexRenderer/LatexRenderer.vue` | 3.7KB | 单个公式的 Vue 渲染组件（katex 封装） |

> **勘误**：任务书写 `src/components/LatexRenderer/` 是目录 —— 确认是目录，
> 但里面只有一个 `LatexRenderer.vue`（3.7KB），**没有 `index.vue`**
> （实测 `...\LatexRenderer\index.vue` = MISSING）。

### 4.5 依赖实况（决定 v3 用什么画图）

```json
// package.json
L66: "echarts": "5.4.3"        ✅ 已装
L75: "katex":  "^0.18.1"       ✅ 已装
L77: "marked": "^18.0.3"       ✅ 已装
L70: "html2canvas": "^1.4.1"   ✅ 已装
L49-52: @tiptap/extension-table{,-cell,-header,-row}  ✅ ** TipTap 已有完整表格扩展 **
```
```
mermaid / markmap / d3 / g6 / cytoscape / jointjs / xmind  →  全部未安装
```

**echarts 用在哪**（4 处，**没有一处是聊天流**）：
`views/monitor/cache/index.vue:69`、`views/admin/dashboard.vue:140`、
`components/PracticeComponent/ExamSummary.vue:265`、`views/front/myQuestion/myStats/index.vue:217`。

结论：**画图表零新增依赖**（echarts 已在 package.json），已经有 4 个页面证明它能跑；
**画思维导图需要新增依赖**（无 mermaid/markmap），这是「实时思维导图」这条产品线唯一的硬成本。

### 4.6 一个被低估的好设计：输出驱动的卡片契约

```ts
// src/components/AgentToolResult/index.vue:497-506
// 判据落在 `downloadUrl` 上，而不是「tool === 'bank_export'」：
// 将来任何工具只要回执里给 downloadUrl，就自动获得这张卡片，不必回来改这里
// 工具的**输出契约**比工具名稳定。
// src/components/AgentToolResult/index.vue:685-695
// 判据落在**输出契约**上：回执里有非空的 jumpUrl 字符串 → 出一张卡。
```
这对 v3 有直接意义：**如果新产物形态（比如可视化报告）也按「回执里带某个约定字段」来做，
后端加能力=前端零改动**。当前 §1.2(c) 说的 `note_manage` 缺 `jumpUrl`，
只要补一个字段，前端立刻出卡，不用改一行前端代码。这是现有架构留给 v3 的最好的礼物。

---

## 5. 数据底座

### 5.1 `study_diagnosis_service.diagnose()` 到底算了哪些指标

入口 `study_diagnosis_service.py:610`，**纯计算，零 LLM**（docstring:627-628：
「返回值**不含任何 LLM 生成的内容** —— 全是算出来的」）。

**返回大结构**（`:739-771`）：
```python
{
  "hasData": True,
  "generatedAt": ...,
  "summary": {...}, "items": [...], "byLevel": {...},
  "bySubject": [...], "activity": {...},
  "headline": "...", "suggestions": [...]
}
```

**(1) `summary` 六个数**（`:742-749`）

| 字段 | 含义 | 来源 |
|---|---|---|
| `questionsSeen` | 涉及题目数 | `:743` |
| `totalAttempts` | 总作答次数 | `:713` |
| `overallAccuracy` | 总正确率 % | `:715` |
| `needsAttention` | 需处理题数（三档之和） | `:717-719` |
| `canArchive` | 可毕业题数 | `:720` |
| `overdueCount` | 欠复习题数 | `:721` |

**(2) `items[]` 逐题 —— 每道题 20 个字段**（`:663-693`）
`questionId / bankName / subject / questionText（截 120 字）/ questionType / difficulty /
attempts / correctCount / accuracy / streak / level / levelText / overdueDays / dueInDays /
recommendedIntervalDays / lastPracticeTime / lastWrongTime / inErrorBook / errorCount / advice`
另有内部 `_score` 排序后 pop 掉（`:690-710`，注释：「让用户看了只会困惑」）。

**(3) 七档分类**（`:132-140`，机器码→中文）

| level | 中文 | 判据 | 优先级 |
|---|---|---|---|
| `repeated_failure` | 反复失守 | ≥3 次且准确率 <0.34 | 0 |
| `lapsing` | 一做就错 | ≥3 次且准确率 <0.6 | 1 |
| `overdue` | 欠复习 | 过了复习窗口 | 2 |
| `due_soon` | 该复习了 | 快到期 | 3 |
| `on_track` | 稳步推进 | 计划内 | 4 |
| `mastered` | 可以毕业 | 连续答对 ≥3 | 5 |
| `fresh` | 刚接触 | 做一两次看不出趋势 | 6 |

阈值常量在 `:153-162`；优先级在 `:143-151`。

**(4) `bySubject[]`**（`:725-737`）
`subject / questions / attempts / accuracy`，排序键 `(accuracy↑, -attempts)`（`:737`：最该先处理的排前面）。

**(5) `activity` —— 学习节奏（这是做看板最有用的一块）**（`:524-576`）
```python
{
  "windowDays": 30, "activeDays": N, "totalPractice": N,
  "averagePerActiveDay": x.x, "peakDayCount": N, "looksLikeBurst": bool,
  "daily": [{"date":"2026-10-26","practiceCount":N,"correctCount":N}, ...]   # ← 时间序列！
}
```
`looksLikeBurst` 判据（`:564-566`）：`active_days>=1 and peak>=30 and average>0 and peak>=average*2.5`，
注释诚实地说「不是精确科学，是给用户一个『你是不是最近才突击』的提示，宁宽不严」。

**(6) SM-2 风格复习间隔**（`:117-126`）
```python
_STREAK_INTERVAL_DAYS = ((0,0),(1,1),(2,3),(3,7),(4,16))   # 连续答对 n 次 → 隔 n 天
_STREAK_MAX_INTERVAL_DAYS = 35                              # 封顶
```
注释（`:116`）解释为什么要整数：「报告里会写『建议 3 天后复习』，而 `2.7183 天` 只会让人怀疑系统」。

**答复任务书的问题**：**有真时间序列**（`activity.daily` 按天）、**有按科目分布**、**有七档分布**、
**有 PR philosophical 正确率 trend**。`learning_stats(action=trend)` 也能出 7 天曲线
（`learning_stats.py:240-255`）。**做学习看板的原料是齐的，不需要新建指标。**

**一个已知缺陷（作者自己记录，不要顺手改）**：
```python
# learning_stats.py:30-34
#: ⚠️ 一个**已知的历史口径问题**（不在本轮修，别顺手改）：trend
#: 用 datetime.now()（本地时间）与库里 create_time 做日期分组，而
#: user_practice_log.create_time 是应用层写进去的本地朴素时间、server_default
#: 那一路则是 PG 的 UTC —— 混着用会让「今天」的边界对不上 8 小时。
```
这个 8 小时偏移会直接影响看板的「今天」数据点，**v3 做看板时必须处理，或不复用 `trend` 而改用 `diagnose().activity.daily`**。

### 5.2 支撑「学习看板」的数据库表（实测 `app/models/*.py`）

| 表 | 模型 | 看板用途 |
|---|---|---|
| `user_practice_log` | `UserPracticeLog`（`question.py`） | **核心**：逐条作答流水 → 趋势/正确率/活跃天/突击判定 |
| `user_question_error` | `UserQuestionError` | 错题本 + `next_review_time` |
| `user_question_favorite` | `UserQuestionFavorite` | 收藏 |
| `user_question_marked` | `UserQuestionMarked` | 斩题 |
| `question_main` / `question_sub` / `question_bank` | 同文件 | 题目元数据（题型/难度/科目） |
| `rag_document` / `rag_document_chunk` | `rag.py` | 文档与切片 |
| `word_learning_state` / `english_practice_log` | `words.py` | **记忆曲线**：`due_date` / `wrong_count` / `lapses` |
| `ai_agent_op_log` | `agent_op_log.py` | 智能体写操作账本（回退用） |
| `note` / `note_category` | `note.py` | 笔记（`content` + `markdown_content` 双列） |

**注**：真实数据量（任务书给定）题库 33 / 题 670 / 知识库 21 / 词书 3 / 单词 42 / 刷题 333 / 错题 115。
**演示看板时数据密度足够**（115 道错题分布在 7 档里，每档 8 条上限正好撑满）。

---

## 6. 叙事断点：为什么这些能力串不成一个故事

### 6.0 一句话

**每一段都跑得通，但没有一段通向"一份能带走的东西"。**
真正缺的不是某个功能，而是**"结构"这一种介质**：它应该在闭环的上游产生，在下游被渲染，而项目在入口就把结构压平了。

### 6.1 断点一：**结构在入口就被摁平**（产品层 / 信息架构层，最致命）

```
Word 文档（有真表格）
   ↓ _emit_table → "| a | b |" 字符串            file_parser.py:717
}  paragraphs / images 两类块，无 table 块        file_parser.py:333,354
   ↓ raw_content=text（纯 str）                   knowledge_ingest.py:318
知识库存扁平 chunk                                 knowledge_search.py:229
   ↓ LLM 拿到的是"一段带竖线的文字"
   ↓ 要还原成原生表格？—— 无从下手
   × 导出侧又根本没有 add_table                   bank_export_service.py（全文）
```

**这解释了「原样复用到底为什么构不成 v3 亮点」**：不是不想做，是这三个环节各自丢了一点点结构，
叠加起来就没有了。**用户那句"别人只能把文件变成聊天框里的文字"，本项目的实际状况是
"我们也只能把文件变成聊天框里的文字"** —— 差别只在于我们的聊天框里还能显示 `<img>`。

**修复成本很低**：`_emit_table` 里并列加 `builder.add_table(rows)`（~40 行），
`blocks` 多一种 `type:"table"`，`knowledge_ingest` 存结构化 payload。
**这是把用户的第一段话术兑现的最小、最关键的改动。**

### 6.2 断点二：**有 ULTRA 好的候选者对 dimensions，但 listwa 没有挂载点**（视觉层 / 信息架构层）

- 后端 `diagnose()` 能算出**七个档位 + 每天曲线 + 科目分布 + 逐条建议**（真算法、可复现）；
- 前端已经有 echarts，且 4 个页面证明它能跑；
- `useAgentChat.handleEvent` 的 `switch` 遇到它不认识的事件类型是 **`default: break` 静默丢弃**（`:1384-1385`）；
- `AiChatStream` 的 8 个分支里**没有一个是给"看板/图表"留的**；
- `AgentToolResult` 虽有输出驱动的好契约，但它目前只认 `downloadUrl` / `jumpUrl` / `bankId` / `noteId`
  ——**不认 `byLevel` / `activity.daily` 这种"可视化载荷"**。

结果是：**用户现在问"我学得怎么样"，得到的是一段 Markdown 文字。**
而 `learning_stats.py:323-330` 里那段注释恰恰记录了这个问题曾经发生过的样子：
> 实测回答就变成了「整体状况：最近 30 天里你只有 2 天在练习，共做了 27 次题…」
> —— 又回到"复述聚合数字"那个老毛病上了。

作者用「把 `headline` 提到 `message` 第一句」来缓解（`:331-335`，很聪明的一招），
但**那仍然是文字**。**真正缺的是一个 `type:'dashboard'` 消息块。**

### 6.3 断点三：**"产物"只有两种形态，且互相不认识**（产品层）

现在能带走的东西只有：
1. 导出的 Word/PDF 题库文件（`bank_export` → `downloadUrl`）
2. 学情诊断报告 PDF（`diagnose_report` → `downloadUrl`，**只有 PDF，没有 Word**）

但这两条产物线**彼此独立**：导出器不知昼夜 summarize，报告生成器不负 Daten hash6 表格。
**"生成一份带图表的学习ʼ报告 Word"** 这种需求，当前两块能力拼不出来
（报告只有 PDF + reportlab 不用 Table；Word 导出器又没有表格）。

### 6.4 断点四：**入口厚重与出口贫瘠严重不对等**（信息架构层）

投入产出比失衡：
- **入口**：802 行解析器 + 456 行 OMML→LaTeX + jieba + pypdf + python-docx 多重兜底，
  OMML/VML/嵌套表格/文件头嗅探/图文原位对齐都处理了；
- **出口**：Word 只有 `add_paragraph` / `add_picture`；PDF 只有 `Paragraph` / `Spacer`。
  **无表格、无目录、无页眉页脚。**

用一句话概括：**「我们花了 800 行把文档读进来，只用 20 种能力把它写回去。」**
用户要求的"原生级创作"（真表格/复杂公式/图文混排），我们目前在"复杂公式"上做到了 Word 侧 OMML（`:558`），
"图文混排"做到了原位（`:601-656`），**"原生表格"是 0**。三缺一。

### 6.5 断点五：**闭环没有铺满**（产品层，但修复便宜）

`jumpUrl` 只覆盖 5/17 工具。已成闭环的（「说了就带你去」）与仍然断开的（「说了你自己找去」）混在一起：
- 成：`bank_manage create` → 去题库；`question_manage batch_import` → 去刷题；
  `english_practice start` → **带参深链直接开练**（最深的一个）
- 断：`note_manage create` 写了笔记不给链接（`:674-678`）；
  `knowledge_base_manage create` 建了库说"接下来需要用户自己上传文档"（`:615-618`）——
  **这句文案本身就记录了闭环缺口**；`question_flag_manage` 全无 jumpUrl。

作者自己在 `bank_manage.py:467-469` 写了这句话：
> 原来只有英语类工具带 jumpUrl，题库创建完用户还得自己去侧边栏找 ——
> 这是「智能体说建好了，但我看不到」的典型断点。

**这段话是对的，但它只被修了一半。**

### 6.6 汇总：六个断点按"能不能马上解決"排列

| 断点 | 层级 | 修起来 | 性价比 |
|---|---|---|---|
| ⑤ 闭环没铺满（jumpUrl 缺失） | 产品 | 每处加 1 个字段（前端零改动） | ★★★★★ |
| ① 结构在入口被压平 | 信息架构 | `_emit_table` 加 `add_table` ~40 行 | ★★★★★ |
| ② 看板没有挂载点 | 视觉/架构 | 5 处改动新增消息块（echarts 已装） | ★★★★☆ |
| ④ 出口 capability 贫瘠（表格/目录/页眉） | 产品 | 中等，reportlab Table 中文折行有坑 | ★★★☆☆ |
| ③ 两条产物线不认识 | 产品 | 需要重新设计产物层 | ★★☆☆☆ |
| （隐藏）LaTeX 脏数据靠导出层打补丁 | 架构 | 要往上游挪，牵动序列化层 | ★★☆☆☆ |

---

## 附：对 v3 三条"必做清单"的证据化答复

1. **「生成原生表格」能不能做到？**
   **能，但必须先动 `file_parser.py:667` 和 `bank_export_service.py` 两侧。**
   不是"加个渲染器"就行 —— 上游不保留结构，渲染器无事可做。
   Word 侧 python-docx 的 `add_table` 是标准能力，项目已装 python-docx 1.1.2，**无新依赖**。
   PDF 侧有作者已记录的中文折行坑（`diagnosis_report_service.py:18-23`），需要量体裁衣。

2. **「实时生成思维导图」能不能做到？**
   **前端需要新增依赖**（无 mermaid / markmap / d3 / g6）。这是唯一一条"必须装东西"的。
   可选的低成本路径：用**已有 echarts 的 tree / graph 系列**画（零新增依赖），
   代价是样式不如 markmap。

3. **「动态数据看板」能不能做到？**
   **能，且原料完全齐备、零新依赖。**
   `diagnose()` 已经返回 `byLevel`(7 档) / `bySubject` / `activity.daily`(30 天时间序列) /
   `summary`(6 数) / `items[]`(逐题 20 字段)；echarts 已在 package.json（L66）。
   **唯一的工作量是 §4.3 那 5 处改动，外加别踩 `trend` 的 8 小时时区坑**（`learning_stats.py:30-34`）。

---

*报告结束。所有结论均可在上述 `file:line` 复核。*
</content>
