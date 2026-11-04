# 云码道开发任务单

> 全部在「华为云 → AI 开发者空间 → 码道 CodeArts 工作台（在线）」里完成，本机 CLI 不参与。
> 每个任务做完就提交，提交信息用中文。产出物按文末「归位」放置。

---

## 任务 1 · 项目规则 + 代码审查

**做法**
1. 仓库里已有 `.codeartsdoer/rule/openstudy-project.md`，确认云上工作区能看到。
2. 改完任务 2 的代码后，在 Space 模式切到 **AgentTeam**，发送：

```text
使用 code-reviewer 检视当前代码修改，按 P0/P1/P2 分级，给出 file:line 与修复建议。重点看 SQL 注入、越权、异常兜底、事务边界、类型标注。
```

3. 按报告把 P0/P1 修完，再提交。

**产出**：`.codeartsdoer/review/<时间>/report/review.json`

---

## 任务 2 · 单元测试（内置「单元测试」技能）

```text
使用单元测试技能，为 openstudy-fastapi/app/utils/html_sanitize.py 生成 pytest 用例：
1) 覆盖 <script>、onerror、javascript:、data: 链接、正常 HTML 保留、超长输入；
2) 覆盖 nh3 缺失时的正则降级分支（monkeypatch nh3=None）；
3) 只新增 openstudy-fastapi/tests/test_html_sanitize.py，不改业务代码；
4) 生成后运行 pytest 并贴出结果。
```

**产出**：`openstudy-fastapi/tests/test_html_sanitize.py` + pytest 输出

---

## 任务 3 · PostgreSQL MCP 核对字典表

在码道「设置 → MCP」添加只读 PostgreSQL MCP，然后：

```text
用 postgres-ro 只读连接本地库，核对 deploy/db-init/28_dict_tables.sql 与 app/models/dict.py 的表、字段是否一致，按「缺表/缺字段/类型不符/默认值不符」输出差异表，附 file:line，不要改库。
```

**产出**：一份核对结论（写进 `doc/quality/dict-schema-check.md`）

---

## 任务 4 · 代码库索引 + 知识文档

在云工作台终端执行：

```bash
codearts codebase --init
codearts codebase --detail      # 等 success 计数上涨再截图
codearts codebase --update
codearts codebase-knowledge     # 生成知识文档
```

**产出**：`doc/codebase/` 下的知识 markdown；`codebase --detail` 的 success 计数截图

---

## 任务 5 · 390px 页面走查（补完剩余页面）

```text
用内置浏览器打开 http://127.0.0.1:3167（user1/123456），以 390×844 和 1440×900 截题库练习、个人中心、消息中心、学习统计，检查横向截断/按钮遮挡/答题卡溢出，输出问题清单并把截图存到 doc/闭环检查/evidence/390px-audit/。能修的直接修，修完重新截图。
```

**产出**：截图 + `390px-audit/问题清单.md` + 修复提交

---

## 任务 6（可选）· 定时跑探针

Space 模式 → 定时任务 → 每天 09:00：

```text
在 openstudy-fastapi 目录运行 tests/_probe*.py，失败则列出失败项与最后 20 行日志。
```

---

## 产出物归位

| 类型 | 路径 |
|---|---|
| 规则 | `.codeartsdoer/rule/` |
| 技能 | `.codeartsdoer/skills/` |
| 审查报告 | `.codeartsdoer/review/` → 复制到 `doc/quality/reviews/<日期>/` |
| 单测 | `openstudy-fastapi/tests/` |
| 索引知识 | `doc/codebase/` |
| 走查截图 | `doc/闭环检查/evidence/390px-audit/` |
| 开发过程 | `doc/dev-process/` |

## 提交规范

```bash
git add -A
git commit -m "test: 补充 html_sanitize 单元测试"
git push origin feat/codearts-iteration
```
