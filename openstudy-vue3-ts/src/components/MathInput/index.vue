<!--
  ============================================================================
  公式输入框（2026-10-27，v3：单一「编辑」入口 + 点公式直接改）
  ============================================================================

  ## 演进过程（两次被用户推翻，记下来避免再走回头路）

  v1：文本框 + 下方预览
      问题：源码和预览两坨同时亮着，`\frac{-b\pm\sqrt{b^2-4ac}}{2a}`
            这串天书一直占着屏幕。

  v2：源码默认折叠 + 一个「ƒx 公式」按钮和一个「编辑」按钮
      问题（用户原话）：
        「第二个需要编辑按钮 直接和当前 fx 公式融合掉
          fx 公式你拿来干嘛用？用户根本看不懂 这两个按钮的区别
          ... 总之只给用户一个编辑按钮」

      说得对：两个按钮都在做"打开编辑"，职责完全重叠。
      而用户面对的是这个场景 ——
        存在 $\xi\in(a,b)$，使 $f(b)-f(a)=f'(\xi)(b-a)$
      一整段里有两个公式，他想改的是**其中一个字符**，
      点「编辑」看到的是整段源码，还得自己找 `\xi` 在哪。

  v3（本版）：
    · **只有一个「编辑」按钮**，删除 ƒx
    · 预览态里**每个公式都单独可点**，点哪个改哪个
    · 打开的面板只含那一个公式，改完精确替换回去

  ## 交互

  预览态（默认）：

      题干                              [编辑]
      ┌────────────────────────────────────────┐
      │ 存在 ⟨ξ ∈ (a,b)⟩，使 ⟨f(b)−f(a)=f′(ξ)(b−a)⟩ │  ← 两个公式都可点
      └────────────────────────────────────────┘

  点第一个公式 → 面板打开，里面只有 `\xi\in(a,b)`，右侧实时预览
  点右上角「编辑」→ 切到整段源码编辑（要改非公式文字时用）

  ## 初始态

    · 含公式 → 预览态（用户是来核对结果的）
    · 空 / 纯文字 → 直接可编辑（不需要折叠）
-->
<template>
    <div class="math-input" :class="{ 'is-single': !isTextarea }">
        <!-- 顶栏：标签 + 唯一入口「编辑」 -->
        <div class="mi-head">
            <span v-if="label" class="mi-label">{{ label }}</span>
            <button type="button" class="mi-edit-btn" :disabled="disabled"
                :title="editing ? '收起源码，回到排版预览' : '展开源码，修改文字或公式'" @click="toggleEditing">
                {{ editing ? '完成' : '编辑' }}
            </button>
        </div>

        <!-- ════════ 预览态：公式单独可点 ════════ -->
        <div v-if="!editing" class="mi-render" :class="{ 'is-empty': !hasContent }">
            <span v-if="!hasContent" class="mi-placeholder" @click="startEditing">
                {{ placeholder || '点击编辑内容' }}
            </span>
            <!--
              ⚠️ 这里是整个 v3 的核心：
                 不渲染成一整块，而是每段文字 / 每个公式单独成节点。
                 公式节点带 data-idx，点击时用它反查 latex 并只打开那一个。
            -->
            <span v-else v-html="clickableHtml" @click="onRenderClick"></span>
        </div>

        <!-- ════════ 编辑态：整段源码 ════════ -->
        <template v-else>
            <!-- ⚠️ `resize` 只有 textarea 能接受 -->
            <el-input ref="inputRef" :model-value="modelValue" :type="type" :rows="isTextarea ? rows : undefined"
                :disabled="disabled" :placeholder="placeholder" :size="size"
                :resize="isTextarea ? 'vertical' : undefined" @update:model-value="onInput" />
            <div v-if="hasMath" class="mi-preview" v-html="previewHtml" />
        </template>

        <!-- 公式面板：只编辑**一个**公式 -->
        <MathEditor ref="mathEditorRef" title="编辑公式" @confirm="onReplaceOne" />
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import MathEditor from '@/components/MathEditor/index.vue'
import {
    renderMarkdownWithLatex,
    renderClickableMath,
    splitMathSpans,
    type MathSpan,
} from '@/utils/latex'

defineOptions({ name: 'MathInput' })

const props = withDefaults(
    defineProps<{
        modelValue?: string
        label?: string
        placeholder?: string
        type?: 'text' | 'textarea'
        rows?: number
        disabled?: boolean
        size?: 'small' | 'default' | 'large'
        /** 强制初始为编辑态（新建表单里用户马上要打字时可以传 true） */
        startEditing?: boolean
    }>(),
    {
        modelValue: '',
        label: '',
        placeholder: '',
        type: 'textarea',
        rows: 2,
        disabled: false,
        size: 'small',
        startEditing: false,
    },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const inputRef = ref<any>()
const mathEditorRef = ref<InstanceType<typeof MathEditor> | null>(null)

/** 是否处于源码编辑态 */
const editing = ref(false)

const isTextarea = computed(() => props.type === 'textarea')
const hasContent = computed(() => !!(props.modelValue || '').trim())

/** 这段内容是否含公式 */
function mayContainMath(text: string | undefined): boolean {
    const s = text || ''
    if (!s) return false
    if (s.indexOf('$') !== -1) return true
    if (s.indexOf('\\(') !== -1 || s.indexOf('\\[') !== -1) return true
    return /\\[a-zA-Z]{2,}/.test(s)
}
const hasMath = computed(() => mayContainMath(props.modelValue))

/** 整段预览（编辑态下方对照用） */
const previewHtml = computed(() =>
    props.modelValue ? renderMarkdownWithLatex(props.modelValue) : '',
)

/** 预览态：每个公式单独可点 */
const clickableHtml = computed(() =>
    props.modelValue ? renderClickableMath(props.modelValue) : '',
)

/**
 * 预览态下当前可点的公式列表
 *
 * 与 `splitMathSpans()` 的公式顺序一一对应（`data-idx` 就是这个数组的下标）。
 * 每次渲染重新算：`modelValue` 变了公式位置就会变，缓存反而出错。
 */
const spans = computed<MathSpan[]>(() =>
    (splitMathSpans(props.modelValue || '') || []).filter((s) => s.type !== 'text'),
)

/**
 * 区分"用户在本组件里打字"和"外部整体换了内容"
 *
 * 后者（后台切换题目）应该按新内容重新决定初始态。
 */
let selfEmitted = false

watch(
    () => props.modelValue,
    (val) => {
        if (selfEmitted) {
            selfEmitted = false
            return
        }
        editing.value = props.startEditing || !mayContainMath(val)
    },
)

onMounted(() => {
    editing.value = props.startEditing || !mayContainMath(props.modelValue)
})

/* ────────────────────────────────────────────────────────────
 * 点击渲染出来的公式 → 只编辑那一个
 * ──────────────────────────────────────────────────────────── */

function onRenderClick(e: MouseEvent) {
    if (props.disabled) return
    const target = e.target as HTMLElement | null
    if (!target) return

    // 事件可能落在公式内部的深层节点（KaTeX 生成一堆 span），用 closest 往上找
    const hit = target.closest('.math-hit') as HTMLElement | null
    if (hit) {
        const idx = Number(hit.getAttribute('data-idx'))
        const span = spans.value[idx]
        if (span) {
            e.stopPropagation()
            openEditorFor(span)
            return
        }
    }
    // 点的是普通文字 → 进整段编辑（符合"点哪都能改"的直觉）
    startEditing()
}

/**
 * 打开面板，只含指定的那一个公式
 *
 * ⚠️ 两个关键点：
 *  1. 传**纯 LaTeX**（不含 `$`）：MathEditor 把内容直接交给 KaTeX，
 *     带 `$` 会渲染报错。
 *  2. `wrapDollar=false`：原公式的定界符已经存在于正文里，
 *     面板若再包一层就成 `$$...$$`（实测踩过）。
 *     回传纯 LaTeX，由下面 `onReplaceOne` 精确替换原区间。
 */
function openEditorFor(span: MathSpan) {
    pendingSpan.value = span
    mathEditorRef.value?.open(span.latex, false)
}

/** 当前正在编辑哪个公式（null = 新建） */
const pendingSpan = ref<MathSpan | null>(null)

/**
 * 面板确认：替换那一个公式 / 或在光标处插入新公式
 *
 * 两种入参形态要分开处理：
 *   · 编辑已有公式（pendingSpan 非空）→ MathEditor 收到 wrapDollar=false，
 *     回传的是**纯 LaTeX**，需要按 span 原本的定界符重新包裹
 *   · 新建公式（pendingSpan 为空）→ 回传的**已带 `$`**，直接用
 */
function onReplaceOne(latex: string) {
    const text = props.modelValue || ''
    const span = pendingSpan.value
    pendingSpan.value = null
    const body = (latex || '').trim()

    // ① 修改已有公式
    if (span) {
        selfEmitted = true
        if (!body) {
            // 清空面板 = 删掉这个公式（连同它周围的定界符一起删）
            emit('update:modelValue', text.slice(0, span.start) + text.slice(span.end))
            return
        }
        // 按原定界符重新包裹：span.raw 形如 `$x^2$` 或 `$$x^2$$`
        const delim = span.raw.startsWith('$$')
            ? '$$'
            : span.raw.startsWith('\\[')
              ? ['\\[', '\\]']
              : span.raw.startsWith('\\(')
                ? ['\\(', '\\)']
                : '$'
        const wrapped = Array.isArray(delim) ? `${delim[0]}${body}${delim[1]}` : `${delim}${body}${delim}`
        emit('update:modelValue', text.slice(0, span.start) + wrapped + text.slice(span.end))
        return
    }

    // ② 新建公式 → 插到光标处（MathEditor 已包好 `$`）
    if (!body) return
    const el = innerEl()
    if (!el) {
        selfEmitted = true
        emit('update:modelValue', text + latex)
        return
    }
    const start = el.selectionStart ?? text.length
    const end = el.selectionEnd ?? start
    selfEmitted = true
    emit('update:modelValue', text.slice(0, start) + latex + text.slice(end))
    requestAnimationFrame(() => {
        const node = innerEl()
        if (!node) return
        const pos = start + latex.length
        node.focus()
        node.setSelectionRange(pos, pos)
    })
}

/* ────────────────────────────────────────────────────────────
 * 整段编辑
 * ──────────────────────────────────────────────────────────── */

function toggleEditing() {
    editing.value = !editing.value
    if (editing.value) focusEnd()
}

function startEditing() {
    if (props.disabled || editing.value) return
    editing.value = true
    focusEnd()
}

function focusEnd() {
    requestAnimationFrame(() => {
        const el = innerEl()
        if (!el) return
        el.focus()
        const n = (props.modelValue || '').length
        el.setSelectionRange(n, n)
    })
}

function onInput(v: string) {
    selfEmitted = true
    emit('update:modelValue', v)
}

/** 取内层真实输入元素（el-input 的 ref 不是 DOM） */
function innerEl(): HTMLInputElement | HTMLTextAreaElement | null {
    const root = inputRef.value?.$el as HTMLElement | undefined
    return (root?.querySelector('textarea, input') as HTMLTextAreaElement) || null
}

defineExpose({
    isEditing: () => editing.value,
    setEditing: (v: boolean) => { editing.value = v },
})
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

/* 唯一按钮：编辑 / 完成 */
.mi-edit-btn {
    margin-left: auto;
    padding: 1px 9px;
    font-size: 11px;
    color: #409eff;
    background: #f2f8ff;
    border: 1px solid #cfe3fb;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.12s;
}

.mi-edit-btn:hover:not(:disabled) {
    background: #e4f1ff;
    border-color: #409eff;
}

.mi-edit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* ══════ 预览态 ══════ */
.mi-render {
    min-height: 32px;
    padding: 6px 10px;
    border: 1px solid #e6e9ee;
    border-radius: 6px;
    background: #fff;
    font-size: 13px;
    line-height: 2;
    color: #1f2329;
    cursor: text;
    overflow-x: auto;
    word-break: break-word;
    transition: border-color 0.12s;
}

.mi-render:hover {
    border-color: #b9d8fb;
}

.mi-render.is-empty {
    color: #b6bdc9;
    cursor: pointer;
}

.mi-placeholder {
    font-size: 12.5px;
}

/*
 * 可点的公式：默认不加任何视觉噪音（保持"就是在看题目"的感觉），
 * 悬停时给淡蓝底 + 虚线下划线，提示"这里能点"。
 */
.mi-render :deep(.math-hit) {
    padding: 0 1px;
    border-radius: 3px;
    cursor: pointer;
    transition: background 0.1s, box-shadow 0.1s;
}

.mi-render :deep(.math-hit:hover) {
    background: #eef6ff;
    box-shadow: 0 0 0 1px #b9d8fb inset;
}

/* ══════ 编辑态预览 ══════ */
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

/* ⚠️ 必须 :deep()：v-html 注入的 KaTeX 节点拿不到 scoped 属性 */
.mi-render :deep(.katex),
.mi-preview :deep(.katex) {
    font-size: 1em;
}

.mi-render :deep(.katex-display),
.mi-preview :deep(.katex-display) {
    margin: 4px 0;
}

/* 单行模式（选项/答案）：压缩内边距 */
.is-single .mi-render {
    min-height: 30px;
    padding: 4px 9px;
    font-size: 12.5px;
}
</style>
