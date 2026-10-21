---
name: 用 git worktree 隔离脏工作区提交
description: 当目标分支与当前脏工作区冲突时，用 git worktree 从目标分支检出新工作区单独提交推送，不触碰原工作区
type: feedback
from: Agent
---

当想把独立改动（如 README、清理提交）推到 `main`，但当前工作区在另一分支（如 `delivery`）且是脏状态、含大量无关的历史遗留修改时：**用 `git worktree` 从目标分支检出到临时目录（如 `../fastapi-v2-mainclean`），在隔离工作区内提交并推送，完全不动原工作区。**

**Why:** 2026-10-09 发布 OpenStudy/fastapi-v2 到 GitCode main 时，`delivery` 工作区有 59 个与本任务无关的未提交修改；直接在该工作区切换分支/提交会把无关改动污染进公开历史。用户接受了这种 worktree 隔离的方案。
**How to apply:** 凡"往 A 分支提交、但当前在 B 分支且有无关脏改动"的场景，优先 worktree 隔离；不要用 stash/checkout 洗工作区。worktree add 后 remote 会被继承，注意用无 token 的干净 URL。
**在 bash 沙箱环境把改动搬进 worktree 时，优先考虑用 `Read` 读主工作区文件 + `Write` 写入 worktree（最稳）；或用 `git diff` 生成 patch 后 `git apply`，而非 `cp`（`cp` 在此环境不稳定）。** 应用前先用 `git diff <目标分支> -- <file>` 逐文件核对差异是否纯属自己的改动、有无混入历史遗留。

**Why:** 2026-10-09 实测 bash 沙箱对 `>` 重定向（即使输出到项目内路径）、多文件参数的命令都反复报 Sandbox Error；单文件 `git diff <branch> -- <file> > x.patch` 可行，PowerShell 生成多文件 patch 也被拦。重定向与「参数过多/多路径」两者都会触发拦截。
**How to apply:** 需要产出/搬运文件时，用 `read`/`write`/`edit` 内置工具，或一次只跑一个文件、避开 shell 重定向；不要把多路径一次塞给 bash。

**已验证可用的组合（2026-10-09 实操成功）：** 三个 patch（p1/p2/p3）在沙箱工具中生成成功，再在 worktree 内应用三个 patch 成功（务必用**绝对路径**，如 worktree 在 `<PROJECT>/_wt_ingest`、patch 在 `<PROJECT>/_p1.patch`，相对路径会失败）；新文件（工具、探针、方案文档）改用 **PowerShell `Copy-Item`** 拷入 worktree 成功。
**Why:** `cp` 在本 bash 沙箱环境不稳定（反复失败），但 PowerShell `Copy-Item` 可用；patch 应用一度因相对路径失败，改绝对路径即成功。
**How to apply:** 搬运多文件进 worktree 时，首选 PowerShell `Copy-Item`；patch 路径一律写绝对路径；落实前先确认 worktree 内目标目录（如 `docs/`）存在。

**worktree 从 main 检出时，main 基线的 `.gitignore` 是旧版，会挡住本次要新增的探针/文件——须把主工作区修正后的 `.gitignore` 一并同步进 worktree，否则新文件不入库。**（2026-10-09 实例：main 旧 `.gitignore` 含过宽 `tests/_probe_*.py` 规则，挡住 `_probe_knowledge_ingest.py`。）

**本环境 `git status` 显示 `M` 但 `git diff`/`--stat`/`--numstat` 均空时，是行尾符(CRLF/LF)或编码/属性差异，内容实际相同，提交时不会被记录——不必强改，可略过。**

**在 bash 沙箱里 `git fetch`（远程）会被拦（报 Sandbox Network Error），须改用 PowerShell 非沙箱执行。**（2026-10-09 发布时 fetch 最新 main 即被拦，改 PowerShell 成功。）
**How to apply:** 本环境任何需要访问网络的 git 操作（fetch/push）一律走 PowerShell 非沙箱；bounded 的本地操作（rebase/commit/diff）可留在沙箱内。

**worktree 里 HEAD 常为 detached（如基于旧 tip 的提交），要推 main 前先 `git fetch` 拿到远程 tip，再在 worktree 内 `git rebase <远程分支>` 把提交挪到最新 tip 上，避免 non-fast-forward 被拒；不要用 `--force` 覆盖远程。**（2026-10-09 实例：`b34ea5f` 基于 `ea73465`，远程已是 `7e39264`，rebase 后新 HEAD `ea53081` 推送成功。）

**提交前先逐一核对哪些文件属本次任务、哪些混入了历史遗留：先 `git fetch` 拿远程真实 tip（本地 `gitcode/main` 常滞后，如本地 `7e39264` 但远程已 `ea53081`），再对每个本次文件 `git diff <远程分支> -- <file>` 确认差异纯净后才搬运。** 工作区常有数十个（如 59 个）与本任务无关的历史未提交改动，绝不能 `git add -A`。**同一文件同时含上一任务（如 token 优化）与本任务（如多智能体）改动且都未提交过时，一起提交是正确的**（无法拆分，两者都是真实待交付内容）。
**注意基线 `.gitignore` 版本：** worktree 从 main 检出时其 `.gitignore` 可能是旧版、会挡住要新增的探针/文件；若远程 tip 已含 `.gitignore` 修正（如 `ea53081` 已含），则无需再同步。

**搬运进 worktree 时，新增文件与修改文件必须区分处理：新增文件可整份 `Copy-Item`（纯净）；被修改的文件绝不能整份覆盖，因为同一文件常同时含本次改动与历史遗留——只能搬"本次的那几行"。**（2026-10-09 实例：`database.py` 本次只加 1 行 import `agent_config`，但文件里还混着一大块 `user_practice_log.client_token` 的历史遗留改动；整份拷贝会把历史遗留一并带上。正解：被改文件用 `git diff` 生成只含本次 hunk 的 patch，或直接在 worktree 内手工 `edit` 那一行。）
**Why:** `delivery` 工作区有数十个（如 59 个）历史遗留未提交改动，很多会落在与本次相同的文件里；按文件粒度搬运会夹带。
**How to apply:** 搬运前对每个被改文件 `git diff <目标分支> -- <file>` 逐块核对 hunk 归属（如确认 `ai.py` 的 +175 全在 Agent 区域属本次）；新增文件用 `Copy-Item`，被改文件用 patch 或手工 edit 只落本次改动。

**worktree 是干净检出，里面没有 `.venv`（虚拟环境只存在于主工作区）——在 worktree 编译验证时，须改用主工作区 venv 里 python 的绝对路径去编译 worktree 的文件，且需在对应目录下运行（`py_compile` 依赖相对目录）。**（2026-10-09 提交多智能体改动时，worktree 内无 venv，改用主 venv 绝对路径编译 worktree 文件成功。）

**多行中文提交信息一律用 `git commit -F <文件>`，不要用 `-m` 拼多行。** 提交说明需含详细「功能说明」（用户要求"写好说明"）。（2026-10-09 提交 14 文件多智能体改动时采用。）

**"相对远程无差异"不等于漏搬运：可能是该改动在上一轮已经推送进 main。**（2026-10-09 实例：`tools/__init__.py`、`check_file_parser.py`、`.gitignore` 相对 `gitcode/main` `git diff` **无输出**，因为 `ea53081` 已包含上一轮 knowledge_ingest 的相关改动；非遗漏。）

**在 worktree 工作区内判断文件是否有改动时，不要只信 `git status` 的 `??`（未跟踪）——若这些文件上轮是经 worktree 直接推到 main、而当前主工作区分支从未提交过它们，`git status` 相对 index 会显示 `??`，但相对本地 ref `gitcode/main`（如 6a2820a）其实是「已存在且内容有更新」。** 此时用 `git diff gitcode/main -- <file>` 判定；注意 bash 下该命令可能**静默失败无输出**，须改用 PowerShell 复核，勿把"无输出"误判为"内容相同/该文件不在 main 上"。（2026-10-09 删 memory 角色后提交时遇到。）

**推送成功后本地 `gitcode/main` ref 不会自动更新——下一轮用它做基线比较前，必须重新 `git fetch`。**（2026-10-09：推完 `6a2820a` 后本地 ref 仍滞后，查 `roles.py` 误得 rc=128，`git diff gitcode/main -- roles.py` 误得 `0 201`＝整文件被删；fetch 后 ref 更新至 `6a2820a`，文件确实存在于 main。）
**Why:** 用主工作区的未跟踪文件对比滞后的本地 ref，会生成「文件不存在/被删除」的假象，进而误判搬运方向。
**How to apply:** 每次进入 worktree 搬运流程前，先 PowerShell `git fetch gitcode main` 并确认本地 `gitcode/main` = 远程真实 tip，再做任何 `git diff <branch> -- <file>` 判定。

**核对 hunk 纯净性的高效判据：** `git diff <远程分支> -- <file>` 的块数与落点是否全在本次改动区域。若块少且都在预期区域（如 `chat.vue` 9 块全部落在 Agent 相关 toolbar/script/handleSend/onBeforeUnmount/style），即可判定纯净、可整文件搬运。（2026-10-09 实例：`chat.vue` +296/-3 全部落在 Agent 区。）

**同一文件混历史遗留的情况不会总出现——若某文件自身的上一轮改动已推 main、本轮只在其上追加本次改动，则该文件相对 main 差异可完全纯净、允许整文件 `Copy-Item`。** 判据仍是逐文件 `git diff <远程分支> -- <file>` 看块是否全在本次区域。（2026-10-09 实例：`loop.py` 上一轮多智能体改动已推 main，本轮只加指挥家，故 loop.py、tools/__init__.py、prompts.py、agent.ts 4 个「修改文件」相对 main 差异全纯净，可与新增文件一样整文件拷入 worktree。）

**worktree 内编译验证后跑关键探针的实操口径：** 用**主工作区 venv 的 python 绝对路径** + worktree 的 cwd（而非 worktree 内不存在的 .venv）；拷贝正确性可直接以「编译通过 + 探针全绿」为准（2026-10-09：worktree 内编译通过 + 指挥家探针 23/23）。

**收尾清单（每轮 worktree 推送后必做）：** 推送成功后清理临时 worktree、删除临时文件（patch/commit 消息文件），再用 PowerShell 非沙箱 `git ls-remote`/fetch 核对远程 main tip 与推送一致、确认无残留。（2026-10-09 指挥家推送 `8e08bb6` 后核对远程 main 一致、无残留。）

**流程顺序（2026-10-10 再次确认）：** 先 `git fetch` 拿最新远程 tip → 建 worktree 并拷入本次改动 → 校验/探针 → 提交推送。**混合命令易踩沙箱坑**（如「建 worktree + 拷入」拼成一条命令被 Sandbox Error 拦），应拆成单步执行。

**改一处 UI 也走完整流程、并复查相关注释是否仍准确：** 2026-10-10 把知识库由右侧 rtl 改为左侧 ltr（仅 1 个文件改），走 worktree 提交；同时复查 `chat.vue` 第 25 行注释——它写「与知识库抽屉同款交互」，因两者现已同为左侧 ltr，注释仍准确，**无需改**（不要见到「同款交互」就贸然改动，先判定描述是否仍成立）。

**worktree 内跑探针勿用 `2>$null` 吞输出：** 2026-10-10 在 worktree 跑探针时用 `2>$null` 抑制 stderr，结果探针输出被整体吞掉、看不到结果——须重跑不加该重定向。本环境保留探针原始输出（stdout/stderr）以便判读。（另：PowerShell 管道也可能整体吞掉探针输出，改用 `Select-Object -Last` 只取末尾。）

**worktree 是干净检出、里面没有 `.env`——依赖数据库密码的探针在 worktree 内跑会读不到 PG 密码而失败（`app.database` 读的是 cwd 下的 `.env`）。**（2026-10-10 实例：在 worktree 内跑 metrics 探针，因 worktree 无 `.env` 连不上 DB；改到**主工作区**跑即 10/10。）
**How to apply:** 需要真实 DB 的探针一律在**主工作区**跑（主工作区有 `.env`）；worktree 内只做**编译验证**（如 py_compile），拷入正确性以「主工作区探针全绿 + worktree 编译通过」合起来判定。

**判断"本轮实际改了哪些文件"要相对远程 main（或本地 `gitcode/main` ref）比对，不能只看工作区 `git status`：** 工作区 ` M` 标记是相对当前分支 index，可能把**上轮已推 main** 的文件也显示为已修改。（2026-10-10 实例：本工作区 `chat.vue` 显示 ` M`，但 `git diff gitcode/main -- chat.vue` 输出为空＝与 `8cd8391` 一致，本轮真正变更只有 `AiModelSelector` 一个文件。）

**"本轮是否干净可提交"要相对远程 main 判定，勿只看工作区 `git status`（2026-10-10 再次确认）：** 提交前 `git diff gitcode/main -- <file>` 为空 → 该文件与远程一致、无需再动；只提交真正变更的那一个文件。**How to apply:** 每轮改完先 `git diff <远程main> -- <本次文件>` 复核，再建 worktree 提交；单文件改动整文件 `Copy-Item` 即可、干净。

**合并多主题到一个提交是可接受的（2026-10-10）：** 当多处改动同属本轮且无法/不应拆分时（如 metrics 持久化 + 删底部状态条 + loop.py 并行优化），用户认可合并为**单个提交**。**How to apply:** 多主题合并时，提交说明里要写清各主题；但要确保「用户真正要的主体」（如"删状态条"）是提交的主体，附带的后端能力改动作为说明中的次要项，不要让主体被淹没。

**"记忆索引里的基线 tip 可能过期"——建 worktree 前务必以实际 `fetch` 结果为准（2026-10-10 再次确认）：** 本轮开始时记忆索引写"fetch 得 gitcode/main=61af866 后建 worktree 待提交"，但实际 fetch 得 `gitcode/main`=`ee78533`（因为上一轮 ee78533 已推送）；**以实际 fetch 为准、不要采信记忆里记的旧 tip**。**How to apply:** 每轮 worktree 流程第一步 fetch 后，用拿到的真实 tip 覆盖记忆中的旧值再动手。

**worktree 一旦基于滞后的基点建好，才发现落后时要"先删该 worktree、fetch 更新本地 ref、再重建"，不能就地提交（否则 non-ff）（2026-10-11 实例）：** 本轮建 worktree 后才发现其基点 `eb841c4` 已是一轮前，而上一轮实际已推 `133e129` 到远程 main——若基于旧点 `eb841c4` 提交推送会 non-fast-forward。正解=删掉该 worktree → `git fetch` 更新本地 `gitcode/main` → 在新 tip（`133e129`）上重建 worktree 再提交。**How to apply:** 建 worktree 前先 fetch 拿真实 tip 并核对基点；若已建好才发现基点落后，别就地提交，走"删/fetch/重建"。

**`git diff <远程main> -- <file>` 显示整文件被删（如 `0 309`/`0 182`）时，多半是"未跟踪文件假象"而非真删除（2026-10-10 再次确认）：** 这些文件（如 `roles.py`/`orchestrator.py`）在主工作区 `git status` 里是 `??`（未跟踪），而 `git diff gitcode/main` 比的是 HEAD/index vs main → 显示"整个文件被删除"。**这是已知现象，worktree 流程不受影响（直接拷文件即可），不要据此误判文件不在 main 上。**
**How to apply:** 见 `0 309`/`0 182` 这类"全删"输出时，先想"是否该文件在本分支 index 里就是未跟踪"，而非真去查 main 上文件是否存在。

**`git status` 里显示 `0 <N>`（如 `0 198`/`0 129`）的行数，往往是"未跟踪假象"而非真删除（2026-10-10 再次确认，同 `0 309`/`0 182` 类）：** 这些文件（如 `sub_agent.py`/`delegate.py`）在本分支 index 里是未跟踪，但已随上轮推送存在于 main → `git diff gitcode/main` 显示"整个文件被删除 N 行"。**可直接整文件 `Copy-Item` 拷入 worktree，勿据此误判文件不在 main 上。**（2026-10-10 推送 `26fc699` 并行委派时踩到。）

**worktree 内通常只做编译验证，不跑依赖 DB 的探针（2026-10-10 再次确认）：** worktree 是干净检出、无 `.env`，`app.database` 读 cwd 的 `.env`，故依赖数据库的探针在 worktree 内会读不到 PG 密码而失败——须回**主工作区**跑。（2026-10-10 推 `26fc699` 时 worktree 内仅 `py_compile` 通过。）

**hunk 落点是判断「相对 main 的 diff 是否全属本轮」的快判据（2026-10-11 再次实操）：** 若块数少且每块都落在本轮预期改动区域，即可判纯净、允许整文件 `Copy-Item`。（实例：`loop.py` 相对 main tip=`2df94ed` 得 `+63/-22`、4 块 @57/@879/@922/@1087 全属本轮多模态改动 → 整文件可拷。）

**worktree 内跑探针勿用 `2>$null` 吞输出（再次确认）**；另：`_probe_*.py` 探针可在**主工作区**跑（依赖 DB 的尤须回主工作区），worktree 内原则上只做 `py_compile`；探针跑绿后再进 worktree 流程，可避免"改完才发现搬运不干净"的返工。

**worktree 收尾=「暂存→复核暂存→提交→推送→移除 worktree→确认清理」六步逐条单跑（2026-10-11 再次实操确认，推 `99f8a98` 时全流程顺畅）**：'移除 worktree' 后要再跑一步确认无残留（`git worktree list`/目录不存在）。**How to apply:** 每轮推送成功即按此清单收尾，勿把「移 worktree」与「确认清理」合成一条（混合命令易被沙箱拦）。

**worktree 是干净检出、里面没有 `node_modules`——前端 SFC 校验脚本（`_v.cjs`，依赖 `@vue/compiler-sfc`）不能在 worktree 内跑，须在主工作区执行、并把 worktree 文件的绝对路径作为参数传入。**（2026-10-11 实例：校验 `.wt_draft` 内 `editor.vue` 时 worktree 无 node_modules，改从主工作区跑 `_v.cjs` + worktree 绝对路径，校验通过。）
**How to apply:** worktree 内只做「有无 node_modules 无关」的事（如 Python `py_compile`）；Node/前端校验一律回主工作区跑、目标文件给绝对路径。

**worktree 被中断遗留会变成 `locked` 状态，同一目录名无法直接重建——须先 `git worktree unlock` 再 `git worktree remove`（必要时配合清理主工作区残留的 worktree 目录），清理干净后才能在同名目录重新 `git worktree add`。**（2026-10-11 实例：`.wt_toast` 上一轮已提交 `56af46e` 但上次会话中断残留、状态 locked；本轮流程=①`git worktree unlock` 解锁 →②`git worktree remove` 移除 →③确认清理 + fetch 远程 main tip →④确认远程未变（仍 `56af46e`）→⑤在新 tip 上建 worktree。）
**Why:** 中断（会话结束/异常退出）会让 worktree 停留在 locked，`git worktree add <同名目录>` 会因目录已存在/被锁而失败；直接删目录也会留下 `.git/worktrees` 元数据残留。
**How to apply:** 每轮 worktree 流程开头若发现同名目录已存在或提示 locked，一律「unlock → remove → 确认无残留 → fetch 核对 tip → 再 add」，不要硬 add 或有残留就提交。

**diff 行数异常放大时先判"纯移动"（2026-10-11）：** worktree 版 `notes.py` 路由前移修复的 diff stat 显示 **112 行变动**，但实际只是「删一处 + 插一处」的同一段代码移动（移动计两次）。**判据：核对 diff 内容/块，若删除块与新增块内容一致（仅位置不同）即为纯移动，不是大规模改写**——不要被行数吓到、不要据此判为"改得太多不可整文件搬运"。此处 `notes.py` 仅末尾 1 块（草稿端点）前移属本轮，仍可整文件处理。

**worktree 内 `app.main` 导入不了（无 `.env`）→ 改用源码级核对：** 2026-10-11 验证路由「顺序」修复时，worktree 无 `.env` 跑不了 `app.main`；改为直接读/查 worktree 版源码里的路由**行序**（确认草稿端点排在 `/notes/note/{...}` 动态路由之前）即可，无须连库/起应用。

**「整文件 diff stat 显示被删 N 行（如 `-64`）」也是未跟踪假象，判据不能只看 stat，要看「实际行数」：** 2026-10-11 案例——`_probe_note_draft.py` 在工作区 `git diff gitcode/main --stat` 显示 `-64`（像整文件被删），但对比实际行数发现 main 版 64 行、工作区版 78 行（本轮加了 ND-16/17/18），**真实差异是 +14 而非删除**。**How to apply:** 遇到 `-N` 这类"整文件删"输出，别直接信；用「main 版行数 vs 工作区版行数」或「worktree 内 `git add` 后看 status」交叉验证，勿据此误判搬运方向。

**一旦把本轮文件拷进 worktree 并 `git add`，status 从 `??`（未跟踪）变为 `M`（已跟踪）后，diff stat 即正常显示真实增删（如探针 `+22/-`），未跟踪假象自动消失。** 2026-10-11 案例——3 文件（`note_manage.py`〔相对 main +58 正常〕/`prompts.py`〔+5 正常〕/`_probe_note_draft.py`〔拷入前 `-64` 假象、拷入后 `+22/-` 正常〕）全部转为 `M`、diff 干净，验证搬运纯净。**How to apply:** worktree 内所有文件都显示 `M` 且增删规模与预期相符（非"整文件删"）＝可判定干净；这正是「走 worktree 流程时未跟踪假象自然解决」的原因。

**校验顺序（2026-10-11 实操口径）：worktree 内先在「主工作区 venv 的 python 绝对路径 + worktree cwd」下做后端 `py_compile`，再回主工作区跑 `_v.cjs` 校验 worktree 的 `.vue` 文件（传绝对路径）。** 另：**worktree 内 diff 规模用 `git diff --stat` 判「是否只含本轮」——放大差异收敛到本轮量级（如 `editor.vue` 由脏工作区 `+348/-...` 收敛到 `+115/-45`、`notes.py` 只剩 `+52`）即证明逐处锚点 edit 干净、无历史 hunk 混入。**

**「能否整文件搬进 worktree」必须逐文件看 `git diff <main> -- <file>` 的每个 hunk 落点，而非按文件整体或按直觉判断——同一文件可同时含本轮 hunk 与历史 hunk（如 `notes.py` 的 1351/1367/1410 是历史收藏权限改动、1492 才是本轮草稿端点）。**（2026-10-11 实例：`note.py` 仅 1 hunk 全本轮→整文件拷；`note_manage.py` 10 hunk 全本轮→整文件拷；`notes.py` 混历史→只能隔离本轮 hunk 落 worktree。）
**Why:** 整文件拷贝会把其它任务的历史未提交改动一并带进公开 main。
**How to apply:** 搬运前对每个文件逐 hunk 核对归属；「块少且都在预期区域」或「块多但全部对应本轮改动」→整文件 `Copy-Item`；只要含历史块→按锚点手工 edit 只落本轮改动。

**worktree 的目录名每轮按主题变化、会反复新建/清理；提交前务必 `git diff --stat` 复核 worktree 版文件相对 main 的收敛行数，并在暂存后再 `git diff --cached` 确认只含目标文件**（2026-10-11 实例：本 bug 轮 worktree=`.wt_dup`，`editor.vue` 收敛 `+11`，暂存复核仅该文件 → 才提交推送。此前同类流程曾用 `.wt_draft`/`.wt_note`/`.wt_ui`/`.wt_metrics`/`_wt_ingest`。）

**提交前安全复核（2026-10-11 实操）：** 暂存后先核对「本次只含预期单文件 + 无敏感内容（token/.env/密钥）」，确认无误再提交推送。**Why:** 本轮 AgentReasoning 折叠修复即按此复核（单文件、无敏感内容）后才推。**How to apply:** 每次 commit 前扫一遍 staged 清单；发现混入无关文件或疑似凭据则停止。

**同一脏工作区文件会「反复」耦合历史改动——每轮都须重新判纯净，不能因上轮判过就沿用（2026-10-11 再次确认）：** `editor.vue` 上轮（含 `myNotes/index.vue`）已因历史未提交改动无法整文件搬运，本轮 `editor.vue` 又出现远超预期的放大差异 `+276/-56`，且本轮真实改动仅 6 处。**判据：`git diff <main> -- <file>` 的块数与总量远大于本轮预期 → 判定混历史遗留 → 放弃整文件 `Copy-Item`，改在 worktree（main 干净版）内用文本锚点（函数名/变量名，不依赖行号）手工 `edit` 只落本轮 hunk。** **Why:** 长驻脏工作区文件的历史遗留会不断累积，`git status` 的 ` M` 无法区分本次/历史。**How to apply:** 凡长驻脏文件（本仓实例：`notes/editor.vue`、`myNotes/index.vue`），每轮提交前逐文件 `git diff <远程main> -- <file>` 复核块数；放大即按锚点手工 edit，勿整份覆盖。

**「同一文件混本次+历史未提交改动」不能整文件搬，改为在干净 worktree 内手工 edit 只落本次改动；若能只靠后端治本则干脆不动前端（2026-10-11 实例）：** 本轮笔记空白修复整理提交时发现，`myNotes/index.vue` 相对 main 是 **+636/-46**（远超本次小改），`notes.py` 的 diff 也混着**收藏列表权限/作者昵称**等**历史未提交改动**（不止本轮兜底）——**`delivery` 工作区堆积了大批历史未提交改动，被改文件常同时含本次与历史 hunk**，整文件拷入 worktree 会把历史改动带进公开 main。**决策：worktree 检出自 main 的干净版本，在其中手工 `edit` 把文件恢复成「main + 仅本轮改动」**（如 `notes.py` 只加 `format_note` 的 content/markdownContent 互兜底、不加收藏权限那些）。**且本轮核心修复在后端即可治本（一处修覆盖所有前端读点），前端 `myNotes/index.vue` 的「草稿标签」耦合历史改动 → 本轮不提交、留待后续单独处理。** **How to apply:** 凡 worktree 内被改文件 diff 行数异常放大，先用 `git diff <目标分支> -- <file>` 看 hunk 归属；属于历史遗留的部分**不要搬**，在干净 worktree 内手工 edit 只恢复本次改动；若治本改动全在后端，宁可本轮不碰耦合历史的前端文件。

**多文件提交与校验序列（2026-10-11 实操，已被采纳）：** 本轮 `delegate_seq` 修复是 4 文件（3 后端/探针 + 1 前端）——流程=①逐文件 `git diff` 核对纯净（先后端 `loop.py` 再前端）；②写提交说明到 `.wt_idx\_commit_idx.txt`（暂存前先落文件）；③编译 worktree 后端文件；④分次 `git add` 各文件（`loop.py` / `_probe_parallel_delegate.py` / `_probe_delegate_index.py` / `useAgentChat.ts`）；⑤`git add --dry-run`/staged 清单确认 4 文件全部暂存；⑥提交 + 推送。**Why:** 多文件提交易漏暂存或混入无关文件，分步核对 + 暂存确认可避免。**How to apply:** 任何 >1 文件的 worktree 提交都按"核对 diff → 写说明文件 → 编译 → 逐文件 add → 确认 staged → commit"流程走；本环境 `git add` 可正常执行（未见沙箱拦截）。

**worktree 固定流程（2026-10-11 再次跑通，可照抄）：** ①`git fetch`（PowerShell 非沙箱）拿远程真实 tip；②从该 tip 建 worktree（如 `.wt_bug2`）；③拷入本次改动文件（新增文件可整拷、被改文件按 diff 只搬本次 hunk）；④`git status` 确认工作区"干净，仅 N 文件"；⑤逐文件 `git diff <远程main> -- <file>` 核对 diff 纯净（本轮 prompts.py + AiChatStream/index.vue 2 文件 diff 全落在本次区域＝纯净）；⑥用**主工作区 venv 的 python 绝对路径 + worktree cwd** 对拷入文件 `py_compile` 编译验证；⑦写提交说明到 worktree 内的 `_commit_*.txt`（多行中文用 `git commit -F`）；⑧`git add` 精确暂存本次文件 → 复核暂存清单 → 提交 → 推送。**How to apply:** 混合命令（如"建 worktree+拷入"拼一条）会被沙箱拦，须拆单步；推送走 PowerShell 非沙箱禁代理。

**推送收尾默认包含「清理主工作区可能残留的临时文件」——用户 2026-10-10 明确要求"顺手把主工作区可能残留的临时文件也清了"。** 即 worktree 推送完成后，除删临时 worktree、patch/commit 消息文件外，还要主动检查并清掉主工作区残留的临时产物（`_commit_*.txt`、`_p*.patch`、`_scratch_*` 等），勿留垃圾。（2026-10-10 推 `eb841c4` 前端专家卡片后用「清理worktree与临时文件 (Sandbox)」一并完成。）

**被改文件相对 main 的行数远多于本次实际改动 → 说明夹带历史遗留，必须逐块核对而非整份拷贝（2026-10-10 实例）：** `database.py` 相对 main 显示 `+28/-0`，但本轮实际只加 1 行（`agent_role_pref,` 注册）——多出的 27 行是历史遗留（`client_token` 相关既有改动）。`ai.py +104/-0`、`prompts.py +19/-15`、`loop.py +20/-5` 同样需先确认块落点是否全在本次区域（Agent/专家区）才可整拷。
**How to apply:** 对每个被改文件先 `git diff <远程main> -- <file>` 看块数与落点；若总增删数明显超本次改动量，则该文件含夹带——新增文件整份 `Copy-Item`，被改且夹带的文件只在 worktree 内手工 `edit` 本次那几行（如 `database.py` 就手工只加那一行）。

**「同一批改动含前端 + 后端、但沙箱 asyncio 全挂跑不了后端」时，验证口径（2026-10-11 笔记兜底修复实操）：** 前端逐文件用 `_v.cjs` 校验（拆单文件跑，见 feedback-frontend-validate-per-file）；后端不跑端到端（接口依赖 DB+async，沙箱挂），退化为「临时脚本模拟纯字段兜底逻辑 + 以修复逻辑正确为准 + 对历史数据现状做同步查库确认（如笔记 440 的 `content` 已有值）」。**提交前先删临时校验/查询脚本**（`_v.cjs`、临时查库脚本），再 `fetch` 拿远程真实 tip 建 worktree 拷入改动文件。（此轮 fetch 得 main tip=`021d384`，作当轮基线。）
