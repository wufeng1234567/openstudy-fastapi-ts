<!-- src/components/LatexRenderer/LatexRenderer.vue -->
<template>
  <div class="latex-content" v-html="renderedContent"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderLatexSafe, renderLatexPlainText, renderQuestionContent, renderMarkdownContent } from '@/utils/latex'

const props = defineProps({
  content: { type: String, default: '' },
  // 是否将内容视为 HTML（保留已有 HTML 标签，仅渲染 LaTeX 公式）
  // 默认 false：先转义 HTML 再渲染 LaTeX（适用于纯文本场景如选项）
  // true：保留 HTML 标签并渲染 LaTeX，用 DOMPurify 做 XSS 防护（适用于原 v-html 内容）
  rawHtml: { type: Boolean, default: false },
  // 是否渲染 Markdown（表格、列表等）
  markdown: { type: Boolean, default: false },
  // 是否渲染原始 LaTeX 命令（如 \overline{}、\frac{} 等，无需 $ 包裹）
  rawLatex: { type: Boolean, default: true }
})

const renderedContent = computed(() => {
  if (!props.content) return ''

  // 如果有原始 LaTeX 命令（如 \overline{}），先渲染它们
  if (props.rawLatex) {
    if (props.markdown) {
      return renderMarkdownContent(props.content)
    }
    return renderQuestionContent(props.content, { renderMarkdown: props.markdown })
  }

  // 否则只渲染 $...$ 公式
  if (props.rawHtml) {
    return renderLatexSafe(props.content)
  }
  return renderLatexPlainText(props.content)
})
</script>
