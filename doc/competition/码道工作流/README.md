# 云码道开发工作流（团队内部）

> 对外材料见 [云码道开发说明.md](../云码道开发说明.md)。本文件只给团队自己看。

## 一、现在先做的三件事（不然后面白干）

1. **把本地代码推到 GitCode**
   当前 `main` 领先 `gitcode/main` 41 个提交，且有未提交改动。云上 clone 的是远端，不先推就开发旧代码。

   ```bash
   git add -A
   git commit -m "chore: 同步本地最新改动"
   git push origin main
   ```

2. **确认规则和技能会随仓库上传**
   `.gitignore` 已放行 `.codeartsdoer/rule/` 与 `.codeartsdoer/skills/`，其余本地索引不入库。

3. **云上建分支**

   ```bash
   git clone https://gitcode.com/qi142410131/openstudy-fastapi-ts.git
   cd openstudy-fastapi-ts
   git checkout -b feat/codearts-iteration
   ```

   新开一个对话，问「本项目编码规范是什么」，能复述规则即说明 `.codeartsdoer/rule` 生效；输入 `/openstudy-release` 能加载即技能生效。

## 二、任务清单

见 [prompts.md](prompts.md) 的 5 个任务。每个任务一个提交，提交信息：

```
feat|fix|test|docs|chore: 简述
```

## 三、产出物放在哪

| 类型 | 路径 |
|---|---|
| 规则 | `.codeartsdoer/rule/` |
| 技能 | `.codeartsdoer/skills/` |
| 审查报告 | `.codeartsdoer/review/` → 复制到 `doc/quality/reviews/<日期>/` |
| 单测 | `openstudy-fastapi/tests/` |
| 索引知识 | `doc/codebase/` |
| 走查截图 | `doc/闭环检查/evidence/390px-audit/` |
| 开发过程 | `doc/dev-process/` |

## 四、数据口径

以 `doc/dev-process/会话统计.md` 为准（3,248 次工具调用 / 186 个文件 / 17 个会话）。
PPT 与讲稿里的旧数字（3,166 / 183 / 110）统一改成这组。

## 五、注意

- 只在云码道里开发，本机 CLI 不产出会话。
- 每次做完先 push，云工作区可能回收。
- 按日常工程记录来写即可，不要刻意写成给评委看的材料。
