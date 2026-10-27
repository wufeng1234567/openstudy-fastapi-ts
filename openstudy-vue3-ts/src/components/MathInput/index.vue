<!--
  ============================================================================
  带公式按钮的文本输入框（2026-10-27）
  ============================================================================

  ## 为什么需要它

  高等数学题的题干里有 `\frac{\partial f}{\partial x}`。原来的 `el-input`
  只能显示 LaTeX 源码 —— 让用户手写这些命令不现实。

  这个组件的做法：在 `el-input` 旁边挂一个「ƒx」按钮，
  点开就是公式面板（`MathEditor`），用户全程鼠标操作，结果插回光标处。

  ## 为什么是"包一层"而不是改造 el-input

  后台题库管理、智能体确认卡片、工作室建题页三处的输入框形态各不相同
  （有的 v-model 绑定对象字段，有的绑数组元素）。包一层意味着：

      <el-input v-model="form.questionText" />
      ↓ 只改标签名，其他一行不动
      <MathInput v-model="form.questionText" />

  零迁移成本，且没用到公式功能的老页面完全不受影响。

  ## 与预览的区别

  之前只加了「只读预览」——用户能看到公式长什么样，但改不了内容。
  现在「ƒx」按钮让他能真的改：点符号插入、实时预览、确定写回。
-->
<template>
    <div class="math-input">
        <div class="mi-head">
            <span v-if="label" class="mi-label">{{ label }}</span>
            <button type="button" class="mi-btn" :disabled="disabled" :title="`插入公式（点击打开符号面板）`"
                @click="openEditor">
                <span class="mi-btn-icon">ƒx</span>
                <span class="mi-btn-text">公式</span>
            </button>
        </div>

        <!-- ⚠️ `resize` 只有 textarea 能接受；单行 input 传了会被 Element Plus
             当成非法属性（控制台警告）。用 `isTextarea` 判断后再绑。 -->
        <el-input ref="inputRef" :model-value="modelValue" :type="type" :rows="isTextarea ? rows : undefined"
            :disabled="disabled" :placeholder="placeholder" :size="size" :resize="isTextarea ? 'vertical' : undefined"
            @update:model-value="(v: string) => emit('update:modelValue', v)" />

        <!-- 含公式时给一行预览：源码与排版对照，减少"改错了却看不出来" -->
        <div v-if="hasMath" class="mi-preview" v-html="previewHtml" />

        <MathEditor ref="mathEditorRef" title="插入公式" @confirm="onInsert" />
    </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import MathEditor from '@/components/MathEditor/index.vue'
import { renderMarkdownWithLatex } from '@/utils/latex'

defineOptions({ name: 'MathInput' })

const props = withDefaults(
    defineProps<{
        modelValue?: string
        label?: string
        placeholder?: string
        /** textarea 用 'textarea'，单行用 'text' */
        type?: 'text' | 'textarea'
        rows?: number
        disabled?: boolean
        size?: 'small' | 'default' | 'large'
    }>(),
    {
        modelValue: '',
        label: '',
        placeholder: '',
        type: 'textarea',
        rows: 2,
        disabled: false,
        size: 'small',
    },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const inputRef = ref<any>()
const mathEditorRef = ref<InstanceType<typeof MathEditor> | null>(null)

/** 是 textarea 还是单行 input（决定能不能传 rows / resize） */
const isTextarea = computed(() => props.type === 'textarea')

/** 这段内容是否含公式（决定要不要显示预览行） */
const hasMath = computed(() => {
    const s = props.modelValue || ''
    if (!s) return false
    if (s.indexOf('$') !== -1) return true
    if (s.indexOf('\\(') !== -1 || s.indexOf('\\[') !== -1) return true
    return /\\[a-zA-Z]{2,}/.test(s)
})

const previewHtml = computed(() =>
    hasMath.value ? renderMarkdownWithLatex(props.modelValue || '') : '',
)

/* ────────────────────────────────────────────────────────────
 * 插入位置：光标所在的公式，或直接插在光标处
 * ──────────────────────────────────────────────────────────── */

/** 取内层真实输入元素（el-input 的 ref 不是 DOM） */
function innerEl(): HTMLInputElement | HTMLTextAreaElement | null {
    const root = inputRef.value?.$el as HTMLElement | undefined
    return (root?.querySelector('textarea, input') as HTMLTextAreaElement) || null
}

/**
 * 打开公式面板，并把光标所在的已有公式作为初始内容
 *
 * 为什么要探测"光标是否在一个已有公式里"：
 * 用户很可能想改一个已经存在的公式（AI 生成的不完全对），
 * 而不是再插一个新的。若光标落在 `$...$` 内部，就把那段内容填进面板，
 * 确定后**替换**该公式；否则在光标处插入新公式。
 */
function openEditor() {
    const el = innerEl()
    const text = props.modelValue || ''
    let initial = ''
    if (el) {
        const pos = el.selectionStart ?? text.length
        const span = findFormulaAt(text, pos)
        if (span) initial = span.body
    }
    mathEditorRef.value?.open(initial)
}

/** 找出光标位置所在的 `$...$` 公式；返回区间与内部文本 */
function findFormulaAt(text: string, pos: number): { start: number; end: number; body: string } | null {
    // 简化处理：只认 `$...$`（不与 `$$` 混淆），逐个扫
    let i = 0
    while (i < text.length) {
        if (text[i] === '$' && text[i + 1] !== '$') {
            const close = text.indexOf('$', i + 1)
            if (close === -1) break
            if (i < pos && pos <= close) {
                return { start: i, end: close + 1, body: text.slice(i + 1, close) }
            }
            i = close + 1
        } else if (text[i] === '$' && text[i + 1] === '$') {
            const close = text.indexOf('$$', i + 2)
            if (close === -1) break
            if (i < pos && pos <= close + 1) {
                return { start: i, end: close + 2, body: text.slice(i + 2, close) }
            }
            i = close + 2
        } else {
            i++
        }
    }
    // 没找到：若光标前紧邻一个 `$`，说明用户刚敲了 `$` 想写公式
    return null
}

/** 面板确认：替换光标所在公式，或在光标处插入 */
function onInsert(latex: string) {
    const el = innerEl()
    const text = props.modelValue || ''
    if (!el) {
        emit('update:modelValue', text + latex)
        return
    }
    const pos = el.selectionStart ?? text.length
    const span = findFormulaAt(text, pos)
    if (span) {
        // 替换已有公式
        emit('update:modelValue', text.slice(0, span.start) + latex + text.slice(span.end))
    } else {
        // 光标处插入
        const start = el.selectionStart ?? text.length
        const end = el.selectionEnd ?? start
        emit('update:modelValue', text.slice(0, start) + latex + text.slice(end))
    }
}
</script>

<style scoped>
.math-input {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
    min-width: 0;
}

.mi-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    min-height: 20px;
}

.mi-label {
    font-size: 12px;
    color: #6b7280;
}

.mi-btn {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 1px 7px;
    font-size: 11px;
    color: #409eff;
    background: #f2f8ff;
    border: 1px solid #cfe3fb;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.12s;
}

.mi-btn:hover:not(:disabled) {
    background: #e4f1ff;
    border-color: #409eff;
}

.mi-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.mi-btn-icon {
    font-style: italic;
    font-weight: 600;
    font-size: 11.5px;
}

/* 预览：与编辑框同宽，浅底虚线框，读起来像"这道题长这样" */
.mi-preview {
    padding: 5px 9px;
    border: 1px dashed #e3e7ee;
    border-radius: 6px;
    background: #f8f9fb;
    font-size: 12.5px;
    line-height: 1.85;
    color: #1f2329;
    overflow-x: auto;
    word-break: break-word;
}

/* ⚠️ 必须 :deep()：v-html 注入的节点没有 scoped 属性 */
.mi-preview :deep(.katex) {
    font-size: 1em;
}

.mi-preview :deep(.katex-display) {
    margin: 4px 0;
}
</style>
