<!--
  ============================================================================
  符号面板（2026-10-27）
  ============================================================================

  ## 用途

  配合 MathLive 的 `<math-field>` 使用：点一个符号按钮，
  对应的 LaTeX 结构就插到**当前光标所在的槽位**。

      用户在编辑器里点进根号内部 → 点面板的「分式」
      → 分式插在根号里（不是追加到末尾）

  这正是用户要的"针对符号编辑"而非"针对代码编辑"的落点。

  ## 为什么用自己的面板而不是 MathLive 自带虚拟键盘

  MathLive 自带一个完整的数学键盘（含 Tab 分层、手势输入等），但：

    · 它默认是**全屏浮层**，一点就盖住整屏，在确认卡片这种小区域里
      体验很糟（用户会看不到自己改的是哪道题）
    · 它有两百多个键，学习成本高；我们实际需要的就是高数那几十个

  所以关掉自带键盘（`mathVirtualKeyboardPolicy = 'manual'`），
  用这个贴合业务的紧凑面板。

  ## 占位符约定

  `#0` `#1` 是 **MathLive 的占位符语法**：插入后光标自动落在 `#0`。
  所以 `\frac{#0}{#1}` 插进去，用户直接就能打分子 —— 不用再点一次。

  其他渲染器（KaTeX）不认识 `#0`，所以按钮上的预览用**不带占位符**的版本。
-->
<template>
    <div class="msp-wrap">
        <div class="msp-tabs">
            <button v-for="g in GROUPS" :key="g.key" type="button" class="msp-tab"
                :class="{ 'is-active': active === g.key }" @click="active = g.key">
                {{ g.label }}
            </button>
        </div>
        <div class="msp-symbols">
            <button v-for="s in activeGroup.items" :key="s.latex" type="button" class="msp-sym" :title="s.tip"
                @click="emit('pick', s.latex)">
                <span v-if="s.preview" class="msp-icon" v-html="renderPreview(s.preview)"></span>
                <span v-else class="msp-text">{{ s.label }}</span>
            </button>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import katex from 'katex'

defineOptions({ name: 'MathSymbolPalette' })

withDefaults(defineProps<{ visible?: boolean }>(), { visible: true })

const emit = defineEmits<{ (e: 'pick', latex: string): void }>()

const active = ref('basic')

interface SymbolItem {
    /** 插入的 LaTeX；`#0` `#1` 是 MathLive 的占位槽 */
    latex: string
    label?: string
    preview?: string
    tip?: string
}

/**
 * 符号表
 *
 * 组织按**数学含义**（用户想的是"我要一个积分"，不是"我要 \int"）。
 * 每条都带 `#n` 占位符 —— 插入后光标自动落进第一个空槽，
 * 用户不用再点一次位置。
 */
const GROUPS = [
    {
        key: 'basic',
        label: '常用',
        items: [
            { latex: '\\frac{#0}{#1}', preview: '\\frac{a}{b}', tip: '分式' },
            { latex: '\\sqrt{#0}', preview: '\\sqrt{x}', tip: '平方根' },
            { latex: '\\sqrt[#0]{#1}', preview: '\\sqrt[3]{x}', tip: 'n 次根' },
            { latex: '^{#0}', preview: 'x^{2}', tip: '上标' },
            { latex: '_{#0}', preview: 'x_{i}', tip: '下标' },
            { latex: '\\left(#0\\right)', preview: '(x)', tip: '括号' },
            { latex: '\\left|#0\\right|', preview: '|x|', tip: '绝对值' },
            { latex: '\\overline{#0}', preview: '\\overline{AB}', tip: '上划线' },
            { latex: '\\vec{#0}', preview: '\\vec{v}', tip: '向量' },
            { latex: '#0!', preview: 'n!', tip: '阶乘' },
            { latex: '\\pm', preview: '\\pm', tip: '正负' },
            { latex: '\\%', label: '%', tip: '百分号' },
        ] as SymbolItem[],
    },
    {
        key: 'calculus',
        label: '微积分',
        items: [
            { latex: '\\int_{#0}^{#1}#2\\,dx', preview: '\\int_{a}^{b}', tip: '定积分' },
            { latex: '\\int#0\\,dx', preview: '\\int', tip: '不定积分' },
            { latex: '\\iint_{#0}', preview: '\\iint', tip: '二重积分' },
            { latex: '\\iiint_{#0}', preview: '\\iiint', tip: '三重积分' },
            { latex: '\\oint#0', preview: '\\oint', tip: '环路积分' },
            { latex: '\\lim_{#0\\to #1}#2', preview: '\\lim_{x \\to 0}', tip: '极限' },
            { latex: '\\frac{d}{dx}#0', preview: '\\frac{d}{dx}', tip: '导数' },
            { latex: '\\frac{\\partial #0}{\\partial #1}', preview: '\\frac{\\partial}{\\partial x}', tip: '偏导' },
            { latex: '\\sum_{#0}^{#1}#2', preview: '\\sum_{i=1}^{n}', tip: '求和' },
            { latex: '\\prod_{#0}^{#1}#2', preview: '\\prod_{i=1}^{n}', tip: '连乘' },
            { latex: "f'(#0)", preview: "f'(x)", tip: '导数撇' },
            { latex: '\\infty', preview: '\\infty', tip: '无穷' },
        ] as SymbolItem[],
    },
    {
        key: 'greek',
        label: '希腊字母',
        items: [
            { latex: '\\alpha', preview: '\\alpha', tip: 'alpha' },
            { latex: '\\beta', preview: '\\beta', tip: 'beta' },
            { latex: '\\gamma', preview: '\\gamma', tip: 'gamma' },
            { latex: '\\delta', preview: '\\delta', tip: 'delta' },
            { latex: '\\varepsilon', preview: '\\varepsilon', tip: 'epsilon' },
            { latex: '\\theta', preview: '\\theta', tip: 'theta' },
            { latex: '\\lambda', preview: '\\lambda', tip: 'lambda' },
            { latex: '\\mu', preview: '\\mu', tip: 'mu' },
            { latex: '\\pi', preview: '\\pi', tip: 'pi' },
            { latex: '\\rho', preview: '\\rho', tip: 'rho' },
            { latex: '\\sigma', preview: '\\sigma', tip: 'sigma' },
            { latex: '\\xi', preview: '\\xi', tip: 'xi' },
            { latex: '\\eta', preview: '\\eta', tip: 'eta' },
            { latex: '\\varphi', preview: '\\varphi', tip: 'phi' },
            { latex: '\\omega', preview: '\\omega', tip: 'omega' },
            { latex: '\\Delta', preview: '\\Delta', tip: 'Delta' },
            { latex: '\\Sigma', preview: '\\Sigma', tip: 'Sigma' },
            { latex: '\\Omega', preview: '\\Omega', tip: 'Omega' },
        ] as SymbolItem[],
    },
    {
        key: 'relation',
        label: '关系/运算',
        items: [
            { latex: '\\le', preview: '\\le', tip: '≤' },
            { latex: '\\ge', preview: '\\ge', tip: '≥' },
            { latex: '\\ne', preview: '\\ne', tip: '≠' },
            { latex: '\\approx', preview: '\\approx', tip: '≈' },
            { latex: '\\equiv', preview: '\\equiv', tip: '≡' },
            { latex: '\\times', preview: '\\times', tip: '×' },
            { latex: '\\div', preview: '\\div', tip: '÷' },
            { latex: '\\cdot', preview: '\\cdot', tip: '·' },
            { latex: '\\in', preview: '\\in', tip: '∈' },
            { latex: '\\notin', preview: '\\notin', tip: '∉' },
            { latex: '\\subset', preview: '\\subset', tip: '⊂' },
            { latex: '\\cup', preview: '\\cup', tip: '∪' },
            { latex: '\\cap', preview: '\\cap', tip: '∩' },
            { latex: '\\emptyset', preview: '\\emptyset', tip: '空集' },
            { latex: '\\to', preview: '\\to', tip: '→' },
            { latex: '\\Rightarrow', preview: '\\Rightarrow', tip: '⇒' },
            { latex: '\\Leftrightarrow', preview: '\\Leftrightarrow', tip: '⇔' },
            { latex: '\\sim', preview: '\\sim', tip: '∼ 等价' },
        ] as SymbolItem[],
    },
    {
        key: 'matrix',
        label: '矩阵/分段',
        items: [
            { latex: '\\begin{pmatrix}#0 & #1 \\\\ #2 & #3\\end{pmatrix}', label: '2×2', tip: '2×2 矩阵' },
            { latex: '\\begin{vmatrix}#0 & #1 \\\\ #2 & #3\\end{vmatrix}', label: '行列式', tip: '行列式' },
            { latex: '\\begin{cases}#0 & #1 \\\\ #2 & #3\\end{cases}', label: '分段', tip: '分段函数' },
            { latex: '\\begin{aligned}#0 \\\\ #1\\end{aligned}', label: '对齐', tip: '多行对齐' },
        ] as SymbolItem[],
    },
]

const activeGroup = computed(() => GROUPS.find((g) => g.key === active.value) || GROUPS[0])

/** 面板按钮上的符号预览（小尺寸 KaTeX） */
function renderPreview(tex: string): string {
    try {
        return katex.renderToString(tex, { throwOnError: false, displayMode: false })
    } catch {
        return tex
    }
}
</script>

<style scoped>
.msp-wrap {
    border: 1px solid #eef0f3;
    border-radius: 8px;
    background: #fcfdfe;
    overflow: hidden;
}

.msp-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    padding: 5px 6px 0;
    border-bottom: 1px solid #eef0f3;
}

.msp-tab {
    padding: 3px 9px;
    font-size: 12px;
    color: #6b7280;
    background: transparent;
    border: none;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    transition: color 0.12s, background 0.12s;
}

.msp-tab:hover {
    color: #409eff;
    background: #f2f8ff;
}

.msp-tab.is-active {
    color: #409eff;
    font-weight: 600;
    background: #fff;
    box-shadow: inset 0 -2px 0 #409eff;
}

.msp-symbols {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(50px, 1fr));
    gap: 5px;
    padding: 8px;
    max-height: 150px;
    overflow-y: auto;
}

.msp-sym {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 36px;
    padding: 3px 2px;
    background: #fff;
    border: 1px solid #e6e9ee;
    border-radius: 6px;
    cursor: pointer;
    transition: border-color 0.12s, background 0.12s;
    overflow: hidden;
}

.msp-sym:hover {
    border-color: #409eff;
    background: #f2f8ff;
}

.msp-icon :deep(.katex) {
    font-size: 0.85em;
}

.msp-text {
    font-size: 12px;
    color: #3a4452;
}
</style>
