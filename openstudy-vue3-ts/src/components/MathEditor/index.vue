<!--
  ============================================================================
  公式编辑器（2026-10-27）
  ============================================================================

  ## 解决什么问题

  高等数学题的题干里有 `\frac{\partial f}{\partial x}`、`\int_{0}^{1}x^2dx`
  这种内容。让用户**手写 LaTeX 不现实** —— 那等于要求他用一个命令语言编程。

  所以这里提供一个**纯鼠标操作**的符号面板：

      点「分式」→ 自动插入 `\frac{}{}` → 光标落在第一个花括号里
      点「积分」→ 自动插入 `\int_{}^{} ` → 光标落在下限里
      点「α」  → 插入 `\alpha`（不用记命令名）

  用户全程只点鼠标，看不到也不需要懂 LaTeX 语法。

  ## 为什么是弹窗而不是内嵌

  项目里的编辑控件有两种形态：
    · `el-input` 纯文本（后台、智能体卡片）—— 根本插不了富文本节点
    · Tiptap 富文本（工作室）—— 能插，但要给每一处都改写 schema

  做成**独立的弹窗组件**，对两种形态都只需要挂一个「ƒx」按钮：
  弹窗里编辑 LaTeX 源码 + 实时预览，确定后把结果写回原来的 v-model。
  这样不动现有编辑器的任何结构，回归风险最小。

  ## 交互设计要点

  1. **实时预览**：右侧用 KaTeX 渲染，一边点一边看结果
  2. **光标插入**：点符号插在**光标处**，不是追加到末尾
  3. **定位占位**：插入 `\frac{}{}` 后光标落在第一个 `{}` 内（继续打字即可）
  4. **符号分类**：分式/根式、上下标、积分、求和连乘、希腊字母、关系符、箭头、矩阵
  5. **常用模板**：整条公式级别的模板（如二次方程求根公式），一次插入

  ## 依赖

  零新增。KaTeX 项目里已有，弹窗用 Element Plus 的 `el-dialog`。
-->
<template>
    <el-dialog v-model="visible" :title="title" width="900px" append-to-body class="math-editor-dialog"
        destroy-on-close @opened="onOpened">
        <div class="me-wrap">
            <!-- 左：符号面板 -->
            <div class="me-palette">
                <el-tabs v-model="activeTab" class="me-tabs">
                    <el-tab-pane v-for="g in GROUPS" :key="g.key" :label="g.label" :name="g.key">
                        <div class="me-symbols">
                            <button v-for="s in g.items" :key="s.insert" type="button" class="me-sym" :title="s.tip || s.insert"
                                @click="insert(s)">
                                <!-- 有 preview 的用 KaTeX 显示符号本身，比文字直观 -->
                                <span v-if="s.preview" class="me-sym-tex" v-html="renderSymbol(s.preview)"></span>
                                <span v-else class="me-sym-text">{{ s.label }}</span>
                            </button>
                        </div>
                    </el-tab-pane>
                </el-tabs>
            </div>

            <!-- 右：源码 + 预览 -->
            <div class="me-right">
                <div class="me-block">
                    <div class="me-label">
                        LaTeX 源码
                        <span class="me-hint">点左侧符号即可插入；不会写也没关系，面板覆盖了常用符号</span>
                    </div>
                    <el-input ref="inputRef" v-model="draft" type="textarea" :rows="5" class="me-source"
                        placeholder="例如：\frac{-b\pm\sqrt{b^2-4ac}}{2a}" @input="onInput" />
                </div>

                <div class="me-block">
                    <div class="me-label">实时预览</div>
                    <div class="me-preview" :class="{ 'is-error': previewError }">
                        <span v-if="!draft.trim()" class="me-preview-empty">（输入后这里显示排版效果）</span>
                        <span v-else-if="previewError" class="me-preview-err">{{ previewError }}</span>
                        <span v-else v-html="previewHtml"></span>
                    </div>
                </div>

                <!-- 模板：整条公式一次插入，省得一步步拼 -->
                <div class="me-block">
                    <div class="me-label">常用公式模板</div>
                    <div class="me-temps">
                        <button v-for="t in TEMPLATES" :key="t.name" type="button" class="me-temp" @click="insertWhole(t)">
                            {{ t.name }}
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <template #footer>
            <div class="me-footer">
                <span class="me-footer-tip">插入后是 LaTeX 源码，导出 Word/PDF 时会变成原生公式</span>
                <div>
                    <el-button size="small" @click="visible = false">取消</el-button>
                    <el-button size="small" type="danger" plain @click="clearDraft">清空</el-button>
                    <el-button size="small" type="primary" @click="confirm">确定插入</el-button>
                </div>
            </div>
        </template>
    </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import katex from 'katex'

defineOptions({ name: 'MathEditor' })

const props = withDefaults(
    defineProps<{
        /** 弹窗标题 */
        title?: string
        /** 初始内容（打开时回填，通常是光标所在的已有公式） */
        initial?: string
        /** 是否用 `$...$` 包裹（行内公式写进正文时需要；纯源码编辑不需要） */
        wrapDollar?: boolean
    }>(),
    { title: '插入公式', initial: '', wrapDollar: true },
)

const emit = defineEmits<{
    (e: 'confirm', latex: string): void
}>()

const visible = ref(false)
const draft = ref('')
const activeTab = ref('frac')
const previewError = ref('')
const inputRef = ref<any>()

/* ────────────────────────────────────────────────────────────
 * 符号表
 * ──────────────────────────────────────────────────────────── */

interface SymbolItem {
    /** 插入的 LaTeX 片段 */
    insert: string
    /** 按钮上显示的文本（没有 preview 时用） */
    label?: string
    /** 按钮上用 KaTeX 渲染的片段（比文字直观） */
    preview?: string
    /** 悬停提示 */
    tip?: string
    /** 插入后光标相对插入点的偏移位置（用于定位到第一个花括号内） */
    caretOffset?: number
}

interface SymbolGroup {
    key: string
    label: string
    items: SymbolItem[]
}

/**
 * 符号分类
 *
 * 组织原则：按**数学含义**分组，不按 LaTeX 命令字母序
 * （用户想的是"我要一个积分"，不是"我要 \\int"）。
 *
 * `caretOffset` 的用法：插入 `\frac{}{}`（长度 10）后，
 * 光标应落在第一个 `{}` 内，即相对起点 +7。
 */
const GROUPS: SymbolGroup[] = [
    {
        key: 'frac',
        label: '分式/根式',
        items: [
            { insert: '\\frac{}{}', preview: '\\frac{a}{b}', tip: '分式', caretOffset: 7 },
            { insert: '\\dfrac{}{}', preview: '\\dfrac{a}{b}', tip: '大号分式', caretOffset: 8 },
            { insert: '\\sqrt{}', preview: '\\sqrt{x}', tip: '平方根', caretOffset: 6 },
            { insert: '\\sqrt[3]{}', preview: '\\sqrt[3]{x}', tip: 'n 次根', caretOffset: 9 },
            { insert: '\\frac{\\partial }{\\partial }', preview: '\\frac{\\partial}{\\partial x}', tip: '偏导', caretOffset: 15 },
            { insert: '\\frac{d}{dx}', preview: '\\frac{d}{dx}', tip: '导数' },
        ],
    },
    {
        key: 'script',
        label: '上下标',
        items: [
            { insert: '^{}', preview: 'x^{2}', tip: '上标', caretOffset: 2 },
            { insert: '_{}', preview: 'x_{i}', tip: '下标', caretOffset: 2 },
            { insert: '^{}_{}', preview: 'x_{i}^{2}', tip: '上下标', caretOffset: 2 },
            { insert: '\\overline{}', preview: '\\overline{AB}', tip: '上划线', caretOffset: 10 },
            { insert: '\\vec{}', preview: '\\vec{v}', tip: '向量', caretOffset: 5 },
            { insert: '\\hat{}', preview: '\\hat{x}', tip: '估计值', caretOffset: 5 },
            { insert: '{}!', preview: 'n!', tip: '阶乘' },
        ],
    },
    {
        key: 'integral',
        label: '积分',
        items: [
            { insert: '\\int_{}^{} ', preview: '\\int_{0}^{1}', tip: '定积分', caretOffset: 6 },
            { insert: '\\int ', preview: '\\int', tip: '不定积分' },
            { insert: '\\iint ', preview: '\\iint', tip: '二重积分' },
            { insert: '\\iiint ', preview: '\\iiint', tip: '三重积分' },
            { insert: '\\oint ', preview: '\\oint', tip: '环路积分' },
            { insert: '\\lim_{ \\to }', preview: '\\lim_{x \\to 0}', tip: '极限', caretOffset: 10 },
        ],
    },
    {
        key: 'sum',
        label: '求和/连乘',
        items: [
            { insert: '\\sum_{}^{} ', preview: '\\sum_{i=1}^{n}', tip: '求和', caretOffset: 6 },
            { insert: '\\prod_{}^{} ', preview: '\\prod_{i=1}^{n}', tip: '连乘', caretOffset: 7 },
            { insert: '\\bigcup_{}^{} ', preview: '\\bigcup_{i=1}^{n}', tip: '并集', caretOffset: 9 },
            { insert: '\\bigcap_{}^{} ', preview: '\\bigcap_{i=1}^{n}', tip: '交集', caretOffset: 9 },
        ],
    },
    {
        key: 'greek',
        label: '希腊字母',
        items: [
            { insert: '\\alpha', preview: '\\alpha', tip: 'alpha' },
            { insert: '\\beta', preview: '\\beta', tip: 'beta' },
            { insert: '\\gamma', preview: '\\gamma', tip: 'gamma' },
            { insert: '\\delta', preview: '\\delta', tip: 'delta' },
            { insert: '\\varepsilon', preview: '\\varepsilon', tip: 'epsilon' },
            { insert: '\\theta', preview: '\\theta', tip: 'theta' },
            { insert: '\\lambda', preview: '\\lambda', tip: 'lambda' },
            { insert: '\\mu', preview: '\\mu', tip: 'mu' },
            { insert: '\\pi', preview: '\\pi', tip: 'pi' },
            { insert: '\\rho', preview: '\\rho', tip: 'rho' },
            { insert: '\\sigma', preview: '\\sigma', tip: 'sigma' },
            { insert: '\\varphi', preview: '\\varphi', tip: 'phi' },
            { insert: '\\omega', preview: '\\omega', tip: 'omega' },
            { insert: '\\Delta', preview: '\\Delta', tip: 'Delta' },
            { insert: '\\Sigma', preview: '\\Sigma', tip: 'Sigma' },
            { insert: '\\Omega', preview: '\\Omega', tip: 'Omega' },
        ],
    },
    {
        key: 'relation',
        label: '关系/运算',
        items: [
            { insert: '\\le ', preview: '\\le', tip: '≤' },
            { insert: '\\ge ', preview: '\\ge', tip: '≥' },
            { insert: '\\ne ', preview: '\\ne', tip: '≠' },
            { insert: '\\approx ', preview: '\\approx', tip: '≈' },
            { insert: '\\equiv ', preview: '\\equiv', tip: '≡' },
            { insert: '\\pm ', preview: '\\pm', tip: '±' },
            { insert: '\\times ', preview: '\\times', tip: '×' },
            { insert: '\\div ', preview: '\\div', tip: '÷' },
            { insert: '\\cdot ', preview: '\\cdot', tip: '·' },
            { insert: '\\infty', preview: '\\infty', tip: '∞' },
            { insert: '\\in ', preview: '\\in', tip: '∈' },
            { insert: '\\notin ', preview: '\\notin', tip: '∉' },
            { insert: '\\subset ', preview: '\\subset', tip: '⊂' },
            { insert: '\\cup ', preview: '\\cup', tip: '∪' },
            { insert: '\\cap ', preview: '\\cap', tip: '∩' },
            { insert: '\\emptyset', preview: '\\emptyset', tip: '空集' },
        ],
    },
    {
        key: 'arrow',
        label: '箭头',
        items: [
            { insert: '\\to ', preview: '\\to', tip: '→' },
            { insert: '\\Rightarrow ', preview: '\\Rightarrow', tip: '⇒' },
            { insert: '\\Leftrightarrow ', preview: '\\Leftrightarrow', tip: '⇔' },
            { insert: '\\leftrightarrow ', preview: '\\leftrightarrow', tip: '↔' },
            { insert: '\\uparrow ', preview: '\\uparrow', tip: '↑' },
        ],
    },
    {
        key: 'matrix',
        label: '矩阵/分段',
        items: [
            {
                insert: '\\begin{pmatrix} & \\\\ & \\end{pmatrix}',
                label: '2×2',
                tip: '2×2 矩阵',
            },
            {
                insert: '\\begin{cases} & \\\\ & \\end{cases}',
                label: '分段',
                tip: '分段函数',
            },
            {
                insert: '\\begin{aligned} & \\\\ & \\end{aligned}',
                label: '对齐',
                tip: '多行对齐',
            },
        ],
    },
]

/** 整条公式模板（一次插入完整内容，替换当前草稿） */
const TEMPLATES = [
    { name: '二次方程求根', latex: '\\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}' },
    { name: '正态密度', latex: '\\frac{1}{\\sqrt{2\\pi}\\sigma}e^{-\\frac{(x-\\mu)^2}{2\\sigma^2}}' },
    { name: '定积分', latex: '\\int_{a}^{b} f(x) \\, dx' },
    { name: '泰勒展开', latex: 'f(x)=\\sum_{n=0}^{\\infty}\\frac{f^{(n)}(x_0)}{n!}(x-x_0)^n' },
    { name: '极限', latex: '\\lim_{x \\to 0}\\frac{\\sin x}{x}=1' },
    { name: '矩阵行列式', latex: '\\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix}=ad-bc' },
    { name: '组合数', latex: 'C_{n}^{k}=\\frac{n!}{k!(n-k)!}' },
    { name: '导数', latex: "f'(x)=\\lim_{\\Delta x \\to 0}\\frac{f(x+\\Delta x)-f(x)}{\\Delta x}" },
]

/* ────────────────────────────────────────────────────────────
 * 预览
 * ──────────────────────────────────────────────────────────── */

/** 面板按钮上的符号：小尺寸渲染，失败就退回文字 */
function renderSymbol(tex: string): string {
    try {
        return katex.renderToString(tex, { throwOnError: false, displayMode: false })
    } catch {
        return tex
    }
}

const previewHtml = computed(() => {
    previewError.value = ''
    const src = draft.value.trim()
    if (!src) return ''
    try {
        return katex.renderToString(src, { throwOnError: true, displayMode: false })
    } catch (e: any) {
        // KaTeX 的错误信息是英文技术描述，但比"什么都不显示"有用
        previewError.value = String(e?.message || e).slice(0, 200)
        return ''
    }
})

/* ────────────────────────────────────────────────────────────
 * 插入逻辑
 * ──────────────────────────────────────────────────────────── */

/**
 * 取 textarea 的真实 DOM 元素
 *
 * el-input 的 ref 不是 DOM，要穿透到内层 `<textarea>`。
 * 拿不到时退化为"追加到末尾"（功能不坏，只是光标位置不理想）。
 */
function textareaEl(): HTMLTextAreaElement | null {
    const root = inputRef.value?.$el as HTMLElement | undefined
    return (root?.querySelector('textarea') as HTMLTextAreaElement) || null
}

/** 在光标处插入片段，并按 caretOffset 定位新光标 */
function insert(item: SymbolItem) {
    const el = textareaEl()
    const piece = item.insert
    if (!el) {
        draft.value += piece
        return
    }
    const start = el.selectionStart ?? draft.value.length
    const end = el.selectionEnd ?? start
    const before = draft.value.slice(0, start)
    const after = draft.value.slice(end)
    draft.value = before + piece + after

    nextTick(() => {
        const off = item.caretOffset ?? piece.length
        const pos = start + off
        el.focus()
        el.setSelectionRange(pos, pos)
    })
}

/** 插入整条模板：替换全部内容（模板本身就是完整公式） */
function insertWhole(t: { name: string; latex: string }) {
    draft.value = t.latex
    nextTick(() => {
        const el = textareaEl()
        el?.focus()
        el?.setSelectionRange(t.latex.length, t.latex.length)
    })
}

function clearDraft() {
    draft.value = ''
    nextTick(() => textareaEl()?.focus())
}

/** 源码变化时清掉上一次的错误 */
function onInput() {
    previewError.value = ''
}

/* ────────────────────────────────────────────────────────────
 * 对外接口
 * ──────────────────────────────────────────────────────────── */

function open(initial?: string) {
    draft.value = initial ?? props.initial ?? ''
    previewError.value = ''
    visible.value = true
}

function onOpened() {
    nextTick(() => textareaEl()?.focus())
}

function confirm() {
    const body = draft.value.trim()
    if (!body) {
        visible.value = false
        emit('confirm', '')
        return
    }
    // 是否包 `$`：正文里需要（否则不会被识别为公式），
    // 但若用户已经在编辑纯源码（如笔记 Markdown 的公式块）则不需要
    const text = props.wrapDollar ? `$${body}$` : body
    emit('confirm', text)
    visible.value = false
}

/** 父组件可以通过 ref 调用 `open()` */
defineExpose({ open })
</script>

<style scoped>
.me-wrap {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    min-height: 380px;
}

@media (max-width: 820px) {
    .me-wrap {
        grid-template-columns: 1fr;
    }
}

/* ===== 左：符号面板 ===== */
.me-palette {
    border: 1px solid #eef0f3;
    border-radius: 8px;
    padding: 4px 10px 10px;
    background: #fcfdfe;
    min-width: 0;
}

.me-tabs :deep(.el-tabs__header) {
    margin-bottom: 8px;
}

.me-tabs :deep(.el-tabs__item) {
    height: 32px;
    line-height: 32px;
    font-size: 12.5px;
    padding: 0 9px;
}

.me-symbols {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
    gap: 6px;
    max-height: 320px;
    overflow-y: auto;
    padding: 2px;
}

.me-sym {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 40px;
    padding: 4px 2px;
    background: #fff;
    border: 1px solid #e6e9ee;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.12s;
    overflow: hidden;
}

.me-sym:hover {
    border-color: #409eff;
    background: #f2f8ff;
    transform: translateY(-1px);
}

.me-sym:active {
    transform: translateY(0);
}

.me-sym-tex :deep(.katex) {
    font-size: 0.92em;
}

.me-sym-text {
    font-size: 12px;
    color: #3a4452;
}

/* ===== 右：源码 + 预览 ===== */
.me-right {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
}

.me-block {
    min-width: 0;
}

.me-label {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 5px;
    font-size: 12.5px;
    font-weight: 600;
    color: #2f3946;
}

.me-hint {
    font-weight: 400;
    font-size: 11px;
    color: #9aa4b2;
}

.me-source :deep(textarea) {
    font-family: 'Cascadia Code', Consolas, Monaco, monospace;
    font-size: 12.5px;
    line-height: 1.6;
}

.me-preview {
    min-height: 76px;
    padding: 10px 12px;
    border: 1px solid #eef0f3;
    border-radius: 8px;
    background: #fcfdfe;
    font-size: 14px;
    line-height: 2;
    overflow-x: auto;
}

/* ⚠️ 必须 :deep()：v-html 注入的 KaTeX 节点拿不到 scoped 属性 */
.me-preview :deep(.katex) {
    font-size: 1.05em;
}

.me-preview :deep(.katex-display) {
    margin: 6px 0;
}

.me-preview.is-error {
    border-color: #f5c2c0;
    background: #fff8f8;
}

.me-preview-empty {
    color: #b6bdc9;
    font-size: 12.5px;
}

.me-preview-err {
    font-size: 11.5px;
    color: #d9534f;
    line-height: 1.6;
    word-break: break-word;
}

/* ===== 模板 ===== */
.me-temps {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.me-temp {
    padding: 4px 10px;
    font-size: 12px;
    color: #3a4452;
    background: #fff;
    border: 1px solid #e6e9ee;
    border-radius: 14px;
    cursor: pointer;
    transition: all 0.12s;
}

.me-temp:hover {
    border-color: #409eff;
    color: #409eff;
    background: #f2f8ff;
}

/* ===== 底部 ===== */
.me-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
}

.me-footer-tip {
    font-size: 11.5px;
    color: #9aa4b2;
}
</style>
