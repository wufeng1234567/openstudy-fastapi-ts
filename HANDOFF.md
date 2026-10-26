# OpenStudy 交接提示词

> 把下面整段内容复制给接手的 AI。它的目的是让新 AI 在 10 分钟内能干活，
> 而不是把项目重读一遍。

---

## 一、你在做什么

`D:\OpenStudy\apps\fastapi-v2` —— 一个叫 **OpenStudy** 的学习平台。
核心链路：**上传资料（PDF/Word/MD/图片）→ AI 解析成结构化题目 → 自动建题库 → 刷题 → 错题诊断 → 再出题**。
外加一个垂直的英语模块（拍照识词 → 词库 → 听写 → 阅读 → 记忆曲线统计）。

技术栈：FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16(pgvector) / Vue 3.4 + TS + Vite 5 + Element Plus。

**用户是项目作者**，中文交流。他要的是能真跑、能演示的东西，不是"看起来写完了"。

---

## 二、环境事实（照抄，别猜）

### 服务

| 什么 | 值 |
|---|---|
| 后端 | `http://127.0.0.1:9101`，**带 `--reload`，改 Python 会自动重载** |
| 前端 | `http://127.0.0.1:3167`，Vite dev server，HMR |
| 数据库 | Docker 容器 `pgsql`，库 `openstudy_v2_pgsql`，用户 `root` / `123456` |
| 前端代理 | 前端调后端走 `/dev-api` 前缀 |

⚠️ **后端有热重载**。改完 Python 等 3~5 秒再测，别立刻断言"没生效"。
（上一任接手者为此误判两次，让用户白重启了两回。）

### 命令

```powershell
# 后端 venv（系统 python 是坏的 Windows Store stub，绝不能用 python）
openstudy-fastapi\.venv\Scripts\python.exe

# 前端构建验证（必须用这个，别用 npm run build）
cd openstudy-vue3-ts
$env:TEMP='D:\Temp'; $env:TMP='D:\Temp'
npx vite build --outDir dist-verify
# 正常输出 "✓ built in ..."，末尾的 remove D:\Temp\esbuild-...: Access is denied 是无害的

# 数据库
docker exec pgsql psql -U root -d openstudy_v2_pgsql -c "..."
```

### Git

三个远程，一次 `git push gitee main` 推三处（`pushurl` 配了三条）：

```powershell
git push gitee main      # GitHub + Gitee + GitCode 一起推
```

**GitHub 必须走代理**，已配置：

```
http.https://github.com.proxy = http://127.0.0.1:7897
```

如果 GitHub 推送失败，先查梯子端口变没变：

```powershell
(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').ProxyServer
```

只给 github.com 配了代理，Gitee/GitCode 直连（国内站走梯子反而更慢）。

---

## 三、铁律（违反了会出事）

### 1. 提交信息不能出现这些词

`赛事 / 比赛 / 评分 / 评委 / 参赛 / 大赛 / 路演 / 答辩 / 评审`

项目对外是一个独立产品，提交历史里不能有任何赛事痕迹。
提交前自己扫一遍再 commit。

### 2. 不要造假数据、假指标

用户明确说过讨厌这个。做不到就说做不到，没数据就说没数据。
智能体的提示词里就写死了这条：「该用户还没有任何练习记录。请如实告知，
不要说『你练得不错』这类无依据的话。」

### 3. 不要动这两个目录

- `doc/dev-process/sessions/` —— 历史归档，只读
- `doc/dev-process/memory/` —— 当前指导，可以加注，不要重写

### 4. 删数据前必须确认

**上一任真的误删过 22 个真实单词**，原因：SQL 里 `_` 是通配符，
`delete from words where word like '__%'` 把两个下划线开头的词
连同整批真词一起删了。要匹配字面下划线必须转义成 `\_`。

**任何删数据的操作，先 SELECT 看一眼要删什么，再 DELETE。**

### 5. 测试造的脏数据自己清

练完手要清掉：`english_practice_log`、`word_learning_state`、自己建的测试题库。
真实数据不要碰：词书 3 本 / 单词 42 个。

---

## 四、这个项目踩过的坑（省你几个小时）

### A. CDP 自动化测试（最坑的一个）

用 Chrome + `--remote-debugging-port` 做浏览器自动化时，**必须**加：

```js
await send('Emulation.setFocusEmulationEnabled', { enabled: true })
```

否则页面处于 `visibility: hidden`（后台标签页），Chrome 会**丢弃所有
`Input.dispatchMouseEvent`** —— 点击"点了没反应"、动画 `currentTime` 永远是 0、
`document.addEventListener('click')` 一条都收不到。

上一任为此查了 5 轮，差点误报 3 个不存在的 bug。

**判断方法**：`document.visibilityState` 是不是 `hidden`。

### B. Vue keep-alive（踩了 4 次，同一个坑）

路由带 `keepAlive: true` 的页面，**换参数导航到同一路由时**：

- `onMounted` **不触发**（组件被复用）
- `onActivated` **也不一定触发**

灾难后果：`seedConsumed` / `isPracticing` 还是上一次的值，URL 参数根本没读。

**唯一可靠解法**：

```js
watch(() => route.query.xxx, (nv) => { /* 重置状态后重新走一遍链路 */ })
```

四次受害者：智能体预填问题、听写页错词种子、统计页 tab 参数、听写页 URL 自动开练。

**记住这句话：凡是要"根据外部传参改变已缓存页面的状态"，都不能只依赖生命周期钩子。**

### C. SCSS 嵌套层级与 DOM 不符（也踩了 4 次）

模板里把某块移出去之后，**样式还留在原来的父级花括号里**，
编译成 `.parent .child` 但 DOM 里是兄弟关系 → 选择器一条都不匹配。

症状：宽度失控、内容被裁切、布局全塌，但**控制台零报错**。

四次受害者：`live-settings`、`start-empty`、`practice-settings`、`scope-row`。

**改模板层级时，必须同步检查 style 块里的嵌套深度。**

自查脚本思路（用花括号深度算每条规则的实际父级）：

```python
import re, io
lines = io.open(路径, encoding='utf-8').read().split('\n')
start = next(i for i,l in enumerate(lines) if l.strip().startswith('<style'))
depth = 0
for i in range(start, len(lines)):
    l = lines[i]
    m = re.match(r'^(\s*)(\.[\w-]+)\s*\{\s*$', l)
    if m and len(m.group(1)) == 4:   # 缩进 4 = 顶层
        print(f'{i+1}: {m.group(2)}')
    depth += l.count('{') - l.count('}')
```

### D. Element Plus 的坑

- `el-button :loading` 会**同时设 disabled 且 handleClick 直接 return** →
  用于开关类按钮会导致按钮永久死掉。开关不要用 `:loading`。
- `el-select` 在 2.x **不暴露 value 到 `input.value`**，读选项要看
  `.el-select__placeholder` 的 textContent。
- `el-card` 上绑 `@click` 有效，但要注意内部 `.el-card__body` 的实际宽度
  可能小于卡片（flex + `align-items: center` 会收缩子元素）。

### E. 后端

- **`/api/v1` 前缀不存在**。真实路由是 `/login`、`/rag/...`、`/wordBooks/...`、`/words/words/list`。
- `catch_all.py` 会 **给所有未匹配路由返回假的 `200 + data:null`**。
  所以"接口返回 200 但数据是 null"极可能是**路由写错了**，不是业务问题。
  上一任就因为调 `/ocr/recognize/stream`（不存在）排查了半天"识别失败"。
- 响应信封：`{code, msg, data}`；分页：`{code, msg, total, rows}`。
- `pageSize` 上限 100/200，超了直接 422。

### F. 数据库表名不直观

```
rag_knowledge_base     知识库
user_practice_log      刷题记录（不是 practice_record）
english_practice_log   英语练习记录
word_learning_state    记忆曲线状态
question_main          题目
```

主键多是 `id`，**不是** `xxx_id`。比如 `EnglishPracticeLog.id`，
写 `log_id` 会 `AttributeError`。

---

## 五、用户怎么干活（重要）

他从这个角度判断你的工作质量：

| 他讨厌 | 他想要 |
|---|---|
| 表面补丁（加点 padding 遮一下） | **根因修复**（查清楚为什么，再改对） |
| 假指标、假数据 | 如实说"这里还没做" |
| 只写不测 | 改完必须实测跑通，附上证据 |
| 长篇解释 | 简洁说清结论 + 关键数据 |
| 频繁问他 | 明确说了「你自己进行合理操作 不用询问我」 |

**他给了无限 token 预算**，明确说过"不要吝惜 Token，我正在极限测试"。
所以：不确定就多查几轮，不要猜。

**他的真实需求是"能做出来能演示"，不是"代码写完了"。**
改完一定跑一遍真实路径，把页面截图或接口返回贴出来。

### 汇报格式他喜欢

- 先说结论（改好了/没改好）
- 关键数字用表格
- 踩的坑单独列出来（他会当成技术深度的素材）
- 不要写"完成了以下工作"这种空话

---

## 六、当前状态

### 已经做完的

- 智能体 17 个工具（题库/题目/知识库/笔记/英语/记忆/委派）
- 闭环：一句话建库→出题→刷题→错题→诊断
- 英语模块：拍照识词 / 词库（可导出 Anki/Excel/Word）/ 听写（3 模式 × 3 播报内容 ×
  题目范围）/ 阅读 / 学习统计（7-30 天趋势、错词一键重练）
- 记忆曲线：SM-2 简化版，29 条单元测试，`word_learning_state` 表
- 两个「学习统计」已合并成一个页面（tab 切换题库/英语）
- 智能体可生成听力练习并给一键跳转按钮
- 词库页有进度条（已掌握/学习中/未学）+「开始听写」+「练新词」

### 数据规模（真实）

```
题库 33 · 题目 670 · 知识库 21 · 词书 3 · 单词 42 · 刷题 333 · 错题 115
```

### 已知待办

1. 公开演示环境（现在只能本地跑）
2. 记忆曲线的「新词每日配额」还没做（现在点练新词会一次给全部）
3. 部分智能体工具仍无 `jumpUrl`（note_manage、question_mark_manage 等）

---

## 七、改完怎么验证（照这个流程）

```
1. Python 改动   → 等 5 秒 → 直接 curl 接口看返回
2. Vue 改动      → npx vite build --outDir dist-verify 确认 "✓ built"
3. 页面改动      → 用 CDP 打开真页面，截图 + 读 DOM 状态
4. 任何改动      → git status 看清改了哪些文件 → 扫禁用词 → commit
```

CDP 测试模板（关键三行）：

```js
await send('Emulation.setFocusEmulationEnabled', { enabled: true })   // 必须
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false })
await send('Runtime.enable'); await send('Page.enable')
```

登录用快登：

```js
const n = Array.from(document.querySelectorAll('.quick-name')).find(x => /演示用户1/.test(x.textContent||''))
n.closest('li,[class*=quick]').click()
```

用户：admin(1) / user1(105) / user2(106) / guest(111)，密码都是 `123456`。

---

## 八、一句话总结

**这个项目的价值不在功能多，在于闭环真的通**：资料进得去、题目出得来、
练习能判分、错题能回练、进步看得见。你改任何东西，先问自己一句：
**这一步断了没有？**
