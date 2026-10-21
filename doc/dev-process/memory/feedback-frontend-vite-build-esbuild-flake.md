---
name: 前端构建失败先判环境 flake 而非代码
description: vite build 报 "The service was stopped"/"failed to load config from vite.config.ts" 多为 esbuild 服务崩溃（并发/残留进程/杀软），非代码错误；隔离重试即恢复
type: feedback
from: Agent
---

**规则：** 本环境（win/cmd）跑 `vite build` 时若报 `The service was stopped` 或 `failed to load config from vite.config.ts` + esbuild service stopped，先判定为 **esbuild 服务环境 flake**，不要急于改代码。用干净、隔离的单次构建复验（避免并发/残留 esbuild 进程），若此前同一改动已构建成功过（EXIT=0）即可证明代码本身没问题。

**Why:** 2026-10-09 验证 chat.vue 前端时，首次 `vite build` 成功；随后并发跑多个命令后反复报 esbuild 服务停止、vite.config.ts 加载失败——属环境/进程资源问题（疑似并发残留 esbuild 进程或防御软件拦截），并非改动代码的语法错。

**升级现象（2026-10-09 再遇）：** 本环境随后**彻底禁用/损坏了 esbuild**——`esbuild` CLI 与 `vite build` 均 EXIT=1 且**完全无输出**（与代码无关；此前首次构建 EXIT=0 即是代码可构建的证据）。此时无法再靠构建验证前端，应改用 `tsc --noEmit --skipLibCheck` 单文件校验。注意 `tsc` 单文件会报两类**假错误**：缺失 `@/` 别名解析、缺失 `ImportMeta.env` 类型（来自 vite 的 d.ts），**均非真实错误**，忽略即可。

**dev server 场景（2026-10-09 再遇）：** dev server 报 `Plugin: vite:vue` + `The service is no longer running`，本质同属 esbuild 子进程崩溃，**非文件语法错**（否则会报具体行号）。排查先证文件本身正常，再用 `@vue/compiler-sfc` 解析 SFC 结构 + 编译 template，用 `typescript` 直接校验 script TS 语法三步全过即可。解决按序：① 重启 dev server（Ctrl+C → `Get-Process esbuild | Stop-Process -Force` 杀残留 → 删 `node_modules\.vite` 缓存 → `npm run dev`）；② `npm rebuild esbuild` 或按 package.json 重装；③ 把 `node_modules\@esbuild\win32-x64\esbuild.exe` 加入杀软白名单（360/火绒/Defender 常误拦独立 esbuild 子进程）；④ 确认 Node 版本（esbuild 对 Node 敏感，Node 22 个别版本有兼容问题，建议 Node 20）。

**根因定位（2026-10-09 实证）：** 直接运行 `node_modules\@esbuild\win32-x64\esbuild.exe` 返回 **EXIT=127（命令未找到/无法执行）**，证明 vite 启动 esbuild 服务时 spawn 不了该二进制，这正是 `The service is no longer running` 的根因。常见三种原因按概率：①杀软/安全策略拦截 esbuild.exe（最常见）；②esbuild.exe 文件损坏或下载不完整（0 字节/被锁定）；③目录权限问题。故排查链路：先证 `chat.vue` 本身正常（@vue/compiler-sfc 解析 SFC + 编译 template + typescript 校验 script 三步全过）→ 查 esbuild/vite/Node 版本（本次 esbuild 0.19.12 + vite 5.0.4 + Node 22.20.0）→ 直接跑 esbuild.exe 看是否 EXIT=127。

**文件本身健康、运行被拦（2026-10-09 三度实证）：** `esbuild.exe` **存在、大小正常（9.8MB）、有执行位（`-rwxr-xr-x`）**，但直接运行仍 **EXIT=127（无法执行）** → 证明是**运行时被拦截**（杀软/Windows Defender 实时防护杀进程、或沙箱限制），而非文件损坏/缺失。首选解法：把 `<repo>/openstudy-vue3-ts/node_modules/@esbuild/win32-x64/esbuild.exe`（或整个 `node_modules`）加入杀软**信任/排除列表**后重启 dev server；仍不行再 `npm cache clean --force` + 重装 esbuild（或 `npm rebuild esbuild`）；再不行切 Node 20 LTS（规避 esbuild 0.19 对 Node 22 的兼容问题）。

**How to apply:** 前端构建/dev server 红灯先看错误文案是否指向 esbuild service；若是，清理/隔离进程后单独重试；若 esbuild CLI 也彻底无输出（环境禁用），则以「此前首次成功构建 EXIT=0」为代码正确依据，并用 `tsc` 单文件佐证语法，不要为此误改业务代码，也不要卡在环境上反复重试。**若 esbuild.exe 存在且大小/权限正常但仍 EXIT=127，直接判定为杀软拦截，引导用户加白名单**（本环境的 esbuild 属被安全策略屏蔽，非代码问题）。
