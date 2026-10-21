---
name: ts.transpileModule 等语法级校验不查未定义变量，删声明易漏网
description: 本环境用 ts.transpileModule 校验 TS/Vue 时只做语法转译、不做语义检查；删代码时误删的变量声明（如 const interval=500）不会被报错，须靠人工回读逐项确认关键符号仍在且定义在使用之前
type: feedback
from: Agent
---

**在本环境用 `ts.transpileModule`（`_v.cjs` 等脚本）校验 TS / Vue 的 `<script lang="ts">` 时，它只做「语法转译」，不解析引用、不做语义/类型检查。** 因此像 `const interval = 500` 这种「变量声明被误删、但使用点仍在」的**未定义变量错误不会被报出**——校验会静默通过，而代码运行时会抛 `ReferenceError`。

**Why:** 2026-10-11 改 `openstudy-vue3-ts\src\utils\request.ts` 的防重拦截器时，为清理旧注释块把 `const interval = 500` 一起删掉了；`ts.transpileModule` 校验仍通过（无语法错），但 `interval` 在被使用前已无定义、**会运行时报错**。靠人工回读才确认丢失并补回。

**How to apply:**
- 删改含**声明/赋值**的代码块（尤其删"注释块 + 相邻声明"这类整块删除）后，**必须人工回读该区域，逐个确认被引用到的关键符号（变量/常量/函数）仍有定义，且定义在首次使用之前**；不要只凭 `_v.cjs` 通过就认为安全。
- 对本次改动的文件，扫一遍「所有被使用的标识符是否都已声明」——语法校验给不了这层保证。
- 相关：`_v.cjs` 单文件校验见 feedback-frontend-validate-per-file；本环境不查语义是工具固有局限，非配置问题。
