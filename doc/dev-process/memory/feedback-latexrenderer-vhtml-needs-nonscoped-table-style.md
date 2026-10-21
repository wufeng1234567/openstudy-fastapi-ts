---
name: LatexRenderer 无 style 致 v-html 表格零样式（须加非 scoped 表格 CSS）
description: 2026-10-11 实测——LatexRenderer.vue 完全没有 <style>，v-html 注入的 <table> 无边框/无内边距看起来"不像表格"；须加非 scoped（或 :deep）表格样式，且 v-html 内容不受 scoped 约束
type: feedback
from: Agent
---

**`LatexRenderer.vue` 自身没有任何 `<style>` → 它渲染出的 `<table>` 只有浏览器默认样式（无边框、无内边距、无对齐），视觉上像"一堆数字挤成一块"而非表格。**

**Why:** 2026-10-11 用户报"表格没渲染"，实测 `.question-title` 的 `outerHTML` **里确实有 `<table>`**（即 `renderMarkdownWithLatex` 跑通了、`<table>` 也没被 DOMPurify 滤掉）——问题不是"没渲染"，而是**渲染了但零样式**。`QuestionDisplay.vue:588` 的 `.question-title` 只写了 `:deep(img)`、`:deep(p)`，**没有 `:deep(table)`** → 表格无边框。

**How to apply:**
- **`v-html` 注入的 DOM 不受 `<style scoped>` 约束** → 给 `LatexRenderer` 加表格样式时须用**非 scoped 全局样式**，或 `:deep()`；本次选定非 scoped（简单可靠，且 `LatexRenderer` 是全局共用渲染容器，改它所有接入页面自动受益）。
- 排查"表格没渲染"类反馈时，**先取目标容器的 `outerHTML` 判定"是否真有 `<table>`"**：有 → 问题在样式/CSS；是纯文本带竖线 → 问题在渲染路径；为空 → 字段没传进来。**"有没有标签"与"看起来像不像表格"是两件事，勿混为一谈。**
