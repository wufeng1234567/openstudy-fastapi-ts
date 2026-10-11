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
