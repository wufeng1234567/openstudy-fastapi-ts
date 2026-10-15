<!-- src/components/LatexRenderer/LatexRenderer.vue -->
<template>
  <div class="latex-content" v-html="renderedContent"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  renderLatexSafe,
  renderLatexPlainText,
  renderQuestionContent,
  renderMarkdownContent,
  renderMarkdownWithLatex
} from '@/utils/latex'

const props = defineProps({
  content: { type: String, default: '' },
  // 是否将内容视为 HTML（保留已有 HTML 标签，仅渲染 LaTeX 公式）
  // 默认 false：先转义 HTML 再渲染 LaTeX（适用于纯文本场景如选项）
  // true：保留 HTML 标签并渲染 LaTeX，用 DOMPurify 做 XSS 防护（适用于原 v-html 内容）
  rawHtml: { type: Boolean, default: false },
  // 是否渲染 Markdown（表格、列表等）
  markdown: { type: Boolean, default: false },
  // 是否渲染原始 LaTeX 命令（如 \overline{}、\frac{} 等，无需 $ 包裹）
  rawLatex: { type: Boolean, default: true },
  // ⭐ 统一富文本管线：同时渲染 `$...$` 公式 **与** Markdown 表格/列表（用户 2026-10-11 方案 A）
  //   默认 **true** —— 题目正文（Word 导入的数学题同时有公式和表格）必须两者都认；
  //   旧行为下 `rawLatex` 默认 true 会短路掉 `rawHtml`/`markdown`，导致 `$...$` 与表格都不渲染。
  //   需要"纯文本/仅公式"的调用方显式传 `:rich="false"`。
  rich: { type: Boolean, default: true }
})

const renderedContent = computed(() => {
  if (!props.content) return ''

  // 默认走统一管线：`$...$` 公式 + Markdown 表格一并渲染
  if (props.rich) {
    return renderMarkdownWithLatex(props.content)
  }

  // ---- 以下为显式 :rich="false" 时的旧行为（保持兼容）----
  if (props.rawLatex) {
    if (props.markdown) {
      return renderMarkdownContent(props.content)
    }
    return renderQuestionContent(props.content, { renderMarkdown: props.markdown })
  }

  if (props.rawHtml) {
    return renderLatexSafe(props.content)
  }
  return renderLatexPlainText(props.content)
})
</script>

<!--
  ⚠️ 必须用**非 scoped** 样式：内容经 `v-html` 注入，scoped 的 `[data-v-xxx]` 属性不会加到这些
  子节点上，scoped 规则对它们无效（这正是"表格渲染出来了却没边框、看着不像表格"的原因）。
  用 `.latex-content` 这个类做作用域前缀，避免污染全局其它元素。
-->
<style>
/*
 * Markdown 表格样式（用户 2026-10-11：Word 表格导入后要"像表格"）
 * `marked` 渲出的 `<table>` 默认无边框、无内边距，多列数字会挤成一团。这里给它
 * 描边框、表头底色、单元格留白、居中——贴近 Word 里的观感。
 * 只作用于 `.latex-content` 内部，所有接入 `LatexRenderer` 的页面（做题/预览/详情…）统一受益。
 */
.latex-content table {
  border-collapse: collapse;
  margin: 10px 0;
  max-width: 100%;
  /* 表格自己成块、允许横向滚动，避免宽表撑破容器 */
  display: inline-block;
  overflow-x: auto;
  font-size: 0.95em;
}

.latex-content table th,
.latex-content table td {
  border: 1px solid #d0d5dd;
  padding: 6px 12px;
  text-align: center;
  vertical-align: middle;
  line-height: 1.5;
  min-width: 32px;
}

.latex-content table thead th {
  background-color: #f2f4f7;
  font-weight: 600;
  color: #344054;
}

.latex-content table tbody tr:nth-child(even) {
  background-color: #fafbfc;
}

/* 表格内若嵌了公式/图片，居中且不溢出 */
.latex-content table td .katex,
.latex-content table th .katex {
  font-size: 1em;
}
.latex-content table img {
  max-width: 100%;
  height: auto;
}
</style>

