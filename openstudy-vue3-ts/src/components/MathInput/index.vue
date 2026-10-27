<!--
  ============================================================================
  带公式按钮的文本输入框（2026-10-27，v2：源码默认折叠）
  ============================================================================

  ## 为什么需要它

  高等数学题的题干里有 `\frac{\partial f}{\partial x}`。原来的 `el-input`
  只能显示 LaTeX 源码 —— 让用户手写这些命令不现实。

  ## v1 的问题（用户 2026-10-27 指出）

  v1 的做法是「文本框 + 下面加一行预览」，于是屏幕上同时出现两坨内容：

      求极限：$\frac{-b \pm \sqrt{b^2-4ac}}{2a}$      ← 天书
      求极限：      -b±√(b²-4ac)/2a                   ← 真正想看的

  用户的原话是「默认折叠、点开才展开源码」。这是对的：
  用户 95% 的时间是在**检查 AI 出的题对不对**，不需要看源码。

  ## v2 的设计

  ┌──────────────────────────────────────────────┐
  │ 题干                        [ƒx 公式] [编辑] │
  ├──────────────────────────────────────────────┤
  │ 求极限：  -b ± √(b² − 4ac) / 2a              │  ← 默认：只有排版结果
  └──────────────────────────────────────────────┘

  点「编辑」后：

  ┌──────────────────────────────────────────────┐
  │ 题干                        [ƒx 公式] [完成] │
  ├──────────────────────────────────────────────┤
  │ [ textarea：求极限：$\frac{-b...}$ ]          │  ← 源码
  ├──────────────────────────────────────────────┤
  │ 预览： 求极限：  -b ± √(b² − 4ac) / 2a        │  ← 下方实时对照
  └──────────────────────────────────────────────┘

  ## 初始状态怎么定

    · 内容**本来就有公式** → 进预览态（用户是来看结果的）
    · 内容是空的 / 纯文字 → 进编辑态（用户是来打字的）

  ⚠️ 不能在打字过程中自动切到预览态 —— 用户插完一个公式，
     接着还要敲"的值等于"这些字，突然收起文本框会让人失去焦点。

  ## 为什么是「包一层」而不是改造 el-input

  后台题库管理、智能体确认卡片、工作室建题页三处的输入框形态各不相同
  （有的 v-model 绑定对象字段，有的绑数组元素）。包一层意味着：

      <el-input v-model="form.questionText" />
      ↓ 只改标签名，其他一行不动
      <MathInput v-model="form.questionText" />

  零迁移成本，且没用到公式功能的老页面完全不受影响。
-->
<template>
    <div class="math-input" :class="{ 'is-single': !isTextarea }">
        <!-- 顶栏：标签 + 公式按钮 + 编辑/完成切换 -->
        <div class="mi-head">
            <span v-if="label" class="mi-label">{{ label }}</span>
            <div class="mi-actions">
                <button type="button" class="mi-btn" :disabled="disabled"
                    :title="editing ? '插入公式（点击打开符号面板）' : '需要修改内容时先点右侧「编辑」'"
                    @click="openEditor">
                    <span class="mi-btn-icon">ƒx</span>
                    <span class="mi-btn-text">公式</span>
                </button>
                <!-- 只有含公式时才给「编辑/完成」：纯文字字段本来就是普通输入框，
                     多一个切换按钮只会让人困惑 -->
                <button v-if="hasMath || editing" type="button" class="mi-toggle" :disabled="disabled"
                    :title="editing ? '收起源码，回到排版预览' : '展开源码进行编辑'"
                    @click="toggleEditing">
                    {{ editing ? '完成' : '编辑' }}
                </button>
            </div>
        </div>

        <!-- ════════ 预览态：只显示排版结果 ════════ -->
        <div v-if="!editing" class="mi-render" :class="{ 'is-empty': !modelValue }" @click="startEditing">
            <span v-if="!modelValue" class="mi-placeholder">{{ placeholder || '点击编辑内容' }}</span>
            <span v-else v-html="previewHtml"></span>
            <!-- 悬停提示：让它看起来"可点"，否则用户不知道能点进来改 -->
            <span class="mi-render-hint">点击编辑</span>
        </div>

        <!-- ════════ 编辑态：源码 + 实时预览 ════════ -->
        <template v-else>
            <!-- ⚠️ `resize` 只有 textarea 能接受；单行 input 传了会被 Element Plus
                 当成非法属性（控制台警告）。用 `isTextarea` 判断后再绑。 -->
            <el-input ref="inputRef" :model-value="modelValue" :type="type" :rows="isTextarea ? rows : undefined"
                :disabled="disabled" :placeholder="placeholder" :size="size"
                :resize="isTextarea ? 'vertical' : undefined"
                @update:model-value="onInput" />

            <!-- 编辑态才给对照预览：此时用户需要确认改对没有 -->
            <div v-if="hasMath" class="mi-preview" v-html="previewHtml" />
        </template>

        <MathEditor ref="mathEditorRef" title="插入公式" @confirm="onInsert" />
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
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
        /**
         * 强制初始为编辑态
         *
         * 默认行为：含公式 → 预览态；不含公式 → 编辑态。
         * 极少数场景（比如"新建"表单，用户马上要打字）可以传 true 让它直接可编辑。
         */
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

/** 是否处于编辑态（显示源码） */
const editing = ref(false)

/** 是 textarea 还是单行 input（决定能不能传 rows / resize） */
const isTextarea = computed(() => props.type === 'textarea')

/**
 * 这段内容是否含公式
 *
 * 与 markdown.ts / AgentToolDetail 用同一套判据（含 `\(...\)` 原生定界符）。
 * 刻意放宽：误判只会多显示一次预览，漏判会让用户看到满屏 `\frac{a}{b}`。
 */
function mayContainMath(text: string | undefined): boolean {
    const s = text || ''
    if (!s) return false
    if (s.indexOf('$') !== -1) return true
    if (s.indexOf('\\(') !== -1 || s.indexOf('\\[') !== -1) return true
    return /\\[a-zA-Z]{2,}/.test(s)
}

const hasMath = computed(() => mayContainMath(props.modelValue))

const previewHtml = computed(() =>
    props.modelValue ? renderMarkdownWithLatex(props.modelValue) : '',
)

/**
 * 标记「这次 modelValue 变化是我们自己 emit 出去的」
 *
 * 用途：区分"用户在本组件里打字"和"外部换了一整条内容"
 * （后台表单切换题目时，modelValue 会被整体替换）。
 * 后者应该回到预览态 —— 用户是来看新那道题的。
 */
let selfEmitted = false

watch(
    () => props.modelValue,
    (val) => {
        if (selfEmitted) {
            selfEmitted = false
            return
        }
        // 外部整体替换了内容 → 按新内容重新决定初始态
        editing.value = props.startEditing || !mayContainMath(val)
    },
)

onMounted(() => {
    // 初始态：含公式就折叠源码（用户是来核对结果的），否则直接可编辑
    editing.value = props.startEditing || !mayContainMath(props.modelValue)
})

/* ────────────────────────────────────────────────────────────
 * 编辑态切换
 * ──────────────────────────────────────────────────────────── */

function toggleEditing() {
    editing.value = !editing.value
    if (editing.value) {
        // 展开后把焦点放到文本框末尾，符合"我要接着改"的预期
        requestAnimationFrame(() => {
            const el = innerEl()
            if (el) {
                el.focus()
                const n = (props.modelValue || '').length
                el.setSelectionRange(n, n)
            }
        })
    }
}

/** 点预览区进入编辑态（预览区看起来像文本，点一下就能改，符合直觉） */
function startEditing() {
    if (props.disabled || editing.value) return
    editing.value = true
    requestAnimationFrame(() => {
        const el = innerEl()
        if (el) {
            el.focus()
            const n = (props.modelValue || '').length
            el.setSelectionRange(n, n)
        }
    })
}

function onInput(v: string) {
    selfEmitted = true
    emit('update:modelValue', v)
}

/* ────────────────────────────────────────────────────────────
 * 公式插入
 * ──────────────────────────────────────────────────────────── */

/** 取内层真实输入元素（el-input 的 ref 不是 DOM） */
function innerEl(): HTMLInputElement | HTMLTextAreaElement | null {
    const root = inputRef.value?.$el as HTMLElement | undefined
    return (root?.querySelector('textarea, input') as HTMLTextAreaElement) || null
}

/**
 * 打开公式面板
 *
 * ⚠️ 预览态下没有输入框（DOM 里压根不存在），必须先切到编辑态、
 *    等下一帧文本框渲染出来，才能取光标位置。所以这里是异步的。
 *
 * 另一种做法是"先在后台记住上次光标位置"，但那个状态很容易和
 * 用户真实操作错位（他可能刚点了别的地方），不如实打实等 DOM 就绪。
 */
async function openEditor() {
    if (props.disabled) return

    if (!editing.value) {
        editing.value = true
        // 等一帧让 el-input 挂上，再取光标
        await new Promise<void>((r) => requestAnimationFrame(() => r()))
        await new Promise<void>((r) => requestAnimationFrame(() => r()))
    }

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

/** 找出光标位置所在的 `$...$`（或 `$$...$$`）公式；返回区间与内部文本 */
function findFormulaAt(text: string, pos: number): { start: number; end: number; body: string } | null {
    let i = 0
    while (i < text.length) {
        if (text[i] === '$' && text[i + 1] === '$') {
            const close = text.indexOf('$$', i + 2)
            if (close === -1) break
            if (i < pos && pos <= close + 1) {
                return { start: i, end: close + 2, body: text.slice(i + 2, close) }
            }
            i = close + 2
        } else if (text[i] === '$') {
            const close = text.indexOf('$', i + 1)
            if (close === -1) break
            if (i < pos && pos <= close) {
                return { start: i, end: close + 1, body: text.slice(i + 1, close) }
            }
            i = close + 1
        } else {
            i++
        }
    }
    return null
}

/** 面板确认：替换光标所在公式，或在光标处插入 */
function onInsert(latex: string) {
    if (!latex) return
    const text = props.modelValue || ''
    const el = innerEl()

    // 拿不到光标（极少见，比如组件还未挂载完）：追加到末尾，至少内容进去了
    if (!el) {
        selfEmitted = true
        emit('update:modelValue', text + latex)
        return
    }

    const start = el.selectionStart ?? text.length
    const end = el.selectionEnd ?? start
    const span = findFormulaAt(text, start)

    // 光标在某个已有公式里 → 替换整条公式；否则在光标处插入
    const next = span
        ? text.slice(0, span.start) + latex + text.slice(span.end)
        : text.slice(0, start) + latex + text.slice(end)

    selfEmitted = true
    emit('update:modelValue', next)

    // 插完把光标放到公式后面，用户可以接着打字
    requestAnimationFrame(() => {
        const node = innerEl()
        if (!node) return
        const pos = span ? span.start + latex.length : start + latex.length
        node.focus()
        node.setSelectionRange(pos, pos)
    })
}

defineExpose({ isEditing: () => editing.value, setEditing: (v: boolean) => { editing.value = v } })
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

.mi-actions {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-left: auto;
}

.mi-btn,
.mi-toggle {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 1px 7px;
    font-size: 11px;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.12s;
    background: #fff;
}

.mi-btn {
    color: #409eff;
    background: #f2f8ff;
    border: 1px solid #cfe3fb;
}

.mi-btn:hover:not(:disabled) {
    background: #e4f1ff;
    border-color: #409eff;
}

.mi-toggle {
    color: #6b7280;
    border: 1px solid #e6e9ee;
}

.mi-toggle:hover:not(:disabled) {
    color: #409eff;
    border-color: #409eff;
    background: #f2f8ff;
}

.mi-btn:disabled,
.mi-toggle:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.mi-btn-icon {
    font-style: italic;
    font-weight: 600;
    font-size: 11.5px;
}

/* ══════ 预览态 ══════ */
.mi-render {
    position: relative;
    min-height: 32px;
    padding: 6px 10px;
    border: 1px solid #e6e9ee;
    border-radius: 6px;
    background: #fff;
    font-size: 13px;
    line-height: 1.9;
    color: #1f2329;
    cursor: text;
    overflow-x: auto;
    word-break: break-word;
    transition: border-color 0.12s, background 0.12s;
}

.mi-render:hover {
    border-color: #b9d8fb;
    background: #fcfdff;
}

.mi-render.is-empty {
    color: #b6bdc9;
    cursor: pointer;
}

.mi-render-hint {
    position: absolute;
    top: 50%;
    right: 8px;
    transform: translateY(-50%);
    padding: 1px 6px;
    font-size: 10.5px;
    color: #409eff;
    background: #f2f8ff;
    border: 1px solid #cfe3fb;
    border-radius: 8px;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s;
    white-space: nowrap;
}

.mi-render:hover .mi-render-hint {
    opacity: 1;
}

.mi-placeholder {
    font-size: 12.5px;
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
