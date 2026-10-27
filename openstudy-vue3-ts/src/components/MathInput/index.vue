<!--
  ============================================================================
  公式输入框（2026-10-27，v4：MathLive 直接编辑符号）
  ============================================================================

  ## 用户最终的要求（原话）

    「只保留一个编辑按钮 用户点击后 生成前面的fx编辑框 可以插入各种符号
      同时要支持编辑当前这个题目
      ... 我们要支持的是高等数学符号直接编辑 针对这个符号而言
      而不是针对他们的代码编辑 像word那样好编辑
      比如一个根号 用户可以直接编辑根号下面的数字
      比如一个积分上下限 可以直接编辑 上下限
      而不是编辑一个 sqrt 代码」

  ## 前三版为什么都不对

    v1 文本框 + 预览        —— 同时看到源码和结果，源码是"天书"
    v2 源码默认折叠         —— 折叠了还是要展开才有法改，改的还是代码
    v3 点公式 → 面板改源码   —— 定位更准了，但仍然是**在改代码**

  三版的共同错误：把"编辑公式"理解成"编辑 LaTeX 字符串"。
  用户要的是编辑**符号结构**：点根号里面、点积分下限，
  光标就进到那个槽位，直接打字。

  ## v4 = MathLive

  `<math-field>` 是真正的 WYSIWYG 公式编辑器：

      · 屏幕上就是排版好的公式（跟 Word 公式编辑器一样）
      · 点根号内部 → 光标进根号，直接打数字
      · 点积分下限 → 光标进下限槽
      · 上下键可以在分子/分母/上下限之间跳
      · Tab 跳到下一个槽位
      · 内部维持 LaTeX 语义 → `.value` 直接拿到 `\frac{a}{b}`

  **存储格式不变**：v-model 仍是 LaTeX 字符串。
  所以父组件、后端、导出链路全都不用改 —— 只换编辑体验。

  ## 不再是"预览 / 编辑"两态

  MathLive 本身就是所见即所得，不存在"看的时候是排版、改的时候是代码"。
  所以 v2/v3 的折叠切换逻辑全部删掉。

  ## 仍然保留的能力

    · `showEditButton`：外部（确认卡片头部）统一控制时隐藏自身按钮 —— 保留
    · 符号面板：点一下插到**当前光标所在的槽位** —— 保留，比 MathLive
      自带的虚拟键盘更贴合我们只需要的那批符号（且不会盖住整屏）
-->
<template>
    <div class="math-input" :class="{ 'is-single': !isTextarea }">
        <!-- 顶栏：只放标签（「符号」按钮挪到字段右侧，见下） -->
        <div v-if="label" class="mi-head">
            <span class="mi-label">{{ label }}</span>
        </div>

        <!--
          编辑区：字段 + 右侧符号按钮
          ⚠️ 符号按钮**内联在字段右边**而不是单独占一行 ——
             选项/答案这类字段没有 label，若按钮独占一行，
             选项 A~D 就会多出四行按钮，把卡片撑得很乱。

          ⚠️ 2026-10-27 性能修复（用户报"刷新后要等十几秒"）
             纯展示时（disabled 且不可编辑）**不实例化 MathLive**，
             改用 KaTeX 渲染。

             实测：一条历史消息里的「导入预览」草稿卡有 15 道题、
             每道题 4~5 个字段 → 单条消息 81 个 <math-field>。
             36 条历史消息 = 数百个 MathLive 实例，
             每个都要建 shadow DOM + 载入数学字体，
             主线程被阻塞 3133ms，页面总耗时 7000ms。

             历史消息里的卡片已经确认/取消，用户**不需要再编辑**，
             没必要为它付出 MathLive 的代价。
        -->
        <div class="mi-body">
            <!-- 纯展示：KaTeX 静态渲染，零组件实例 -->
            <div v-if="isReadonlyView" class="mi-static" :style="{ minHeight: `${fieldMinHeight}px` }"
                v-html="staticHtml"></div>

            <!-- 可编辑：MathLive 的 <math-field>，所见即所得 -->
            <math-field v-else ref="fieldRef" class="mi-field" :style="{ minHeight: `${fieldMinHeight}px` }"
                @input="onInput" @focus="onFocus" @blur="onBlur"></math-field>

            <button v-if="showSymbolButton && !isReadonlyView" type="button" class="mi-sym-btn"
                :disabled="disabled || !editable"
                :title="paletteOpen ? '收起符号面板' : '插入数学符号（求和/根号/积分等）'"
                :class="{ 'is-active': paletteOpen }"
                @mousedown.prevent="onSymBtnMouseDown"
                @click="togglePalette">
                ƒx
            </button>
        </div>

        <!-- 符号面板：插到当前光标所在槽位 -->
        <MathSymbolPalette v-if="paletteOpen" :visible="paletteOpen" @pick="insertLatex" />
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
// MathLive：注册 <math-field> 自定义元素 + 字体
import 'mathlive'
import 'mathlive/fonts.css'
import MathSymbolPalette from '@/components/MathSymbolPalette/index.vue'
import { stripMathPlaceholders, restoreMathDelimiters, renderMarkdownWithLatex } from '@/utils/latex'

defineOptions({ name: 'MathInput' })

const props = withDefaults(
    defineProps<{
        modelValue?: string
        label?: string
        placeholder?: string
        /** textarea 用 'textarea'（多行高度），单行用 'text' */
        type?: 'text' | 'textarea'
        /** 多行模式的最小高度（px）；单行模式忽略 */
        rows?: number
        disabled?: boolean
        size?: 'small' | 'default' | 'large'
        /**
         * 是否显示「编辑」按钮
         *
         * 确认卡片里一道题有题干/选项/答案/解析四个字段，
         * 但「编辑」按钮只有一个（在题目头部），所以传 false。
         */
        showEditButton?: boolean
        /**
         * 是否显示「符号」按钮（打开符号面板插入求和/根号/积分）
         *
         * ⚠️ 与 `showEditButton` **必须分开**（2026-10-27 踩过）：
         *    最初两者共用一个开关，卡片传 `show-edit-button=false`
         *    就把符号入口一起关掉了，用户在卡片里只能改现有数字、
         *    无法插入新的数学符号 —— 这是功能缺失，不是设计选择。
         *
         * 默认 true：任何可编辑的公式字段都应该能插符号。
         */
        showSymbolButton?: boolean
        /**
         * 是否可编辑（默认 true）
         *
         * ── 为什么需要"锁定"这个状态（2026-10-27）────────────────
         * 确认卡片里的「编辑」按钮要有**实际作用**，否则它只是个文字开关。
         *
         * 设计：卡片里所有 MathInput 默认 `editable=false`（只读、能看排版），
         * 点某题的「编辑」才把那一题的字段设为 `editable=true`。
         * 这样按钮的意义是"解除这一题的锁定"，用户不会误改别的题。
         *
         * ⚠️ 与 `disabled` 的区别：
         *    `disabled` = 整个卡片只读（已确认/已取消，永久不可改）
         *    `editable` = 当前是否处于"这道题正在被编辑"的状态
         */
        editable?: boolean
    }>(),
    {
        modelValue: '',
        label: '',
        placeholder: '',
        type: 'textarea',
        rows: 2,
        disabled: false,
        size: 'small',
        showEditButton: true,
        showSymbolButton: true,
        startEditing: false,
        editable: true,
    },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const fieldRef = ref<any>(null)
const paletteOpen = ref(false)
const focused = ref(false)

/**
 * 失焦瞬间记住的光标位置
 *
 * ── 为什么需要（2026-10-27）──────────────────────────────────
 * 用户想「点进根号里 → 点符号面板 → 插入一个分式」。
 *
 * 但点面板按钮会让编辑器失焦，MathLive 的 `focus()` 会把光标
 * 重置到**末尾**，于是分式插到了整条公式最后面，而不是根号里。
 *
 * 解决：失焦时用 `el.position` 记下当前位置，重新聚焦后还原。
 * 配合符号按钮上的 `@mousedown.prevent`（阻止焦点转移），
 * 大多数情况光标根本不会丢；这里是第二道保险。
 */
const savedOffset = ref<number | null>(null)

/**
 * 编辑开始时的**原始值**（还原 `$` 定界符的锚点来源）
 *
 * MathLive 编辑后会丢掉混排文字里的 `$`，还原时要靠
 * 「编辑前文字段」做锚点。所以聚焦那一刻就要把原值记下来
 * （详见 `restoreMathDelimiters`）。
 */
const originalForRestore = ref('')

const isTextarea = computed(() => props.type === 'textarea')

/**
 * 编辑器最小高度
 *
 * `rows` 是"行数"（el-input 的语义），这里换算成像素：
 * 每行约 26px（含行间距），最小 40px（单行模式）。
 */
const fieldMinHeight = computed(() => {
    if (!isTextarea.value) return 40
    const lines = Math.max(1, props.rows || 2)
    return Math.max(52, lines * 26 + 12)
})

/** 防止 input → emit → watch → setValue 的循环 */
let syncing = false

/* ────────────────────────────────────────────────────────────
 * 与 MathLive 实例同步
 * ──────────────────────────────────────────────────────────── */

/** 是否只读：卡片 disabled 或 当前题未进入编辑态 */
const isReadOnly = computed(() => props.disabled || !props.editable)

/**
 * 是否走「纯展示」路径（不实例化 MathLive）
 *
 * ── 为什么要这个分支（2026-10-27 性能修复）────────────────────
 * 用户报：「刷新后要等待起码十几秒钟才能刷新出来」。
 *
 * 实测数据（打开一个有 36 条历史消息的会话）：
 *
 *     后端接口   全部 < 90ms，总计 554ms
 *     前端耗时   总 7058ms，其中 Long Task 累计 6711ms
 *     单次最长   3133ms
 *
 * 罪魁：DOM 里 **270 个 KaTeX + 数百个 <math-field>**。
 * 一条「导入预览」草稿卡含 15 道题 × 4~5 字段 =
 * 单条消息 81 个 MathLive 实例；36 条消息就是几千个级别的开销。
 * 每个 MathLive 实例都要建 shadow DOM、载入数学字体、初始化光标引擎。
 *
 * 但历史消息里的卡片已经确认/取消了，**用户不需要再编辑**。
 * 所以：
 *   · `disabled && !editable`（已确认 / 已取消 / 只读展示）→ KaTeX 静态渲染
 *   · 其他情况（正在编辑、或本就要可编辑）→ 才建 MathLive
 *
 * 这样既保住了编辑体验，又把历史消息的渲染成本从
 * "数百个富组件"降到"纯 HTML"。
 */
const isReadonlyView = computed(() => props.disabled && !props.editable)

/** 纯展示模式下的 HTML（用 KaTeX 渲完直接铺进去） */
const staticHtml = computed(() => {
    const text = props.modelValue || ''
    if (!text) return `<span class="mi-static-empty">${escapeText(props.placeholder || '')}</span>`
    return renderMarkdownWithLatex(text)
})

/** 最小转义（只处理会破坏结构的字符） */
function escapeText(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

onMounted(async () => {
    // 等自定义元素注册完成（MathLive 的 import 是异步注册的）
    try {
        await customElements.whenDefined('math-field')
    } catch {
        /* 老浏览器没有 whenDefined，直接继续 */
    }
    const el = fieldRef.value
    if (!el) return

    killVirtualKeyboard(el)

    // 回填初始值
    if (props.modelValue) el.value = props.modelValue
    el.readOnly = isReadOnly.value

    // 占位符：MathLive 通过 placeholder 属性显示空态提示
    if (props.placeholder) el.setAttribute('placeholder', props.placeholder)
})

/**
 * 彻底关掉 MathLive 自带的虚拟键盘
 *
 * ── 为什么不能只设策略（2026-10-27 用户反馈）──────────────────
 * 用户截图：编辑公式时底部弹出全宽数学键盘，**点空白处不关闭、也不自动收**。
 *
 * 翻 MathLive 源码（mathlive.mjs:29054 / 29061）看清了机制：
 *
 *     focusin  → 仅当 policy==='auto'   才自动弹
 *     focusout → 仅当 policy!=='manual' 才在 300ms 后自动收
 *
 * 所以设成 `'manual'` 的结果是：**既不会自动弹、也不会自动收**。
 * 而键盘本身还有个**独立的打开入口** ——
 * 编辑器工具栏上的 ⌨ 图标（shadow DOM 里 `part="virtual-keyboard-toggle"`）。
 * 用户一旦点开它，就再也关不掉了，正是遇到的情况。
 *
 * ⚠️ 试过但**没用**的两条路（实测）：
 *    · `el.menuItems` 过滤 —— 键盘开关**不在** menuItems 里，
 *      它是 widget 上的一个独立 part，改菜单动不到它
 *    · `import('mathlive')` 取 `mathVirtualKeyboard` —— 模块没导出这个对象，
 *      它挂在 `window.mathVirtualKeyboard` 上
 *
 * 真正有效的三条（本函数 + 样式里各一条）：
 *    ① policy = 'manual'           禁掉自动弹出
 *    ② CSS 隐藏 virtual-keyboard-toggle part  去掉手动入口
 *    ③ 万一已被别处打开，主动 hide 一次
 *
 * 我们有自己的符号面板（MathSymbolPalette），
 * 不需要 MathLive 那套两百多个键、还盖住整屏的键盘。
 */
function killVirtualKeyboard(el: any) {
    // ① 禁止自动弹出
    el.mathVirtualKeyboardPolicy = 'manual'

    // ② 兜底：若全局键盘已被打开（比如用户在别的组件点过），关掉它
    const kb = (window as any).mathVirtualKeyboard
    if (kb) {
        try {
            if (kb.visible) {
                kb.hide?.()
                kb.visible = false
            }
        } catch {
            /* 忽略：老版本可能没有 hide() */
        }
    }
}

/**
 * 外部改动 → 同步进编辑器
 *
 * ── 这里有个会导致"输入跑错位置"的坑（2026-10-27 实测）────────
 * MathLive 的 `el.value = xxx` 会**把光标重置到末尾**。
 *
 * 于是会出现这种情况：用户插了一个 `\int_{#0}^{#1}`，光标本该在下限槽里，
 * 但因为我们把"清理过占位符的值"回写给了 `el.value`，光标被踢到末尾，
 * 用户接着输入 `0` 就跑到积分号后面去了：
 *
 *     \int_{\placeholder{}}^{\placeholder{}}   （原本光标在这里）
 *     \int_{}^{}\,dx0                          （0 跑到了末尾 —— 错）
 *
 * ## 修法
 *
 * ① **回写前先比对"未清理"的原始值**。
 *    编辑器里的原始值含 `\placeholder{}`，而 modelValue 是清理过的；
 *    两者永远不相等 → 每次都回写 → 每次都丢光标。
 *    所以要把 modelValue 还原成"带占位符"的形态再比，或者干脆
 *    只在**外部确实换了内容**（长度/结构明显不同）时才回写。
 *
 * ② 判断依据用"当前编辑器内容的**清理版**是否等于 modelValue"。
 *    相等 → 说明这次变化就是用户自己打字引起的，不回写（保住光标）。
 */
watch(
    () => props.modelValue,
    (val) => {
        const el = fieldRef.value
        if (!el || syncing) return

        const current = el.value || ''
        const currentStripped = stripMathPlaceholders(current)
        const next = val || ''

        // 编辑器里的值（清理后）已经等于外部值 → 是用户自己打字引起的
        // 变化，绝不能回写（回写会丢光标）
        if (currentStripped === next) return

        // 外部确实改了内容（切换题目 / 后端回填）→ 同步
        syncing = true
        el.value = next
        syncing = false
        // 锚点基准也要跟着换，否则还原时会用旧题目的文字段去匹配
        originalForRestore.value = next
    },
)

watch(
    () => props.disabled,
    (v) => {
        if (fieldRef.value) fieldRef.value.readOnly = v || !props.editable
    },
)

// 编辑态切换（卡片头部点「编辑」/「完成」时生效）
watch(
    () => props.editable,
    (v) => {
        const el = fieldRef.value
        if (!el) return
        el.readOnly = props.disabled || !v
        // 解锁时自动聚焦，用户可以立刻改
        if (v && !props.disabled) {
            nextTick(() => el.focus())
        }
    },
)

watch(
    () => props.placeholder,
    (v) => {
        if (fieldRef.value && v) fieldRef.value.setAttribute('placeholder', v)
    },
)

/**
 * 编辑内容变化 → 回传 LaTeX
 *
 * ⚠️ 回传前先 `stripMathPlaceholders`：MathLive 未填的槽是 `\placeholder{}`，
 *    而 KaTeX **不认识**这个命令（实测报 Undefined control sequence）。
 *    不清理的话，用户没填完就提交 → 脏数据入库 → 导出时公式崩掉。
 *
 * ⚠️ 这里**不**做 `wrapBareMath`（补回 `$`）：
 *    打字过程中每敲一个字符都重新包一遍会干扰输入法、
 *    也让光标位置不稳定。补 `$` 放在编辑结束时（失焦/完成）做。
 */
function onInput() {
    if (syncing) return
    syncing = true
    emit('update:modelValue', stripMathPlaceholders(fieldRef.value?.value ?? ''))
    syncing = false
}

function onFocus() {
    focused.value = true
    // 记下编辑前的原始值 —— 它是还原 `$` 定界符的锚点来源
    if (!originalForRestore.value) {
        originalForRestore.value = props.modelValue || ''
    }
}

/**
 * 编辑结束时的收尾：还原被 MathLive 吃掉的 `$` 定界符
 *
 * ── 问题（2026-10-27 实测）──────────────────────────────────
 * MathLive 把整段当成**一个公式**解析。用户编辑一次后，
 * 「文字 + $公式$ + 文字」会被重新序列化，`$` 全部消失：
 *
 *     编辑前：求极限 $\lim_{x\to 0}\frac{\sin x}{x}$ 的值
 *     编辑后：求极限\lim_{x\to0}\frac{\sin x}{x}的值
 *
 * 实测 8 个真实题干样本里 7 个会丢。丢了之后渲染管线失效：
 *
 *     \int_0^1x^2dx   → 0 个 KaTeX（整条原样露出 —— 用户最初报的 bug）
 *     方程的解为 x=1  → 0 个 KaTeX
 *
 * ## 怎么还原
 *
 * 不能用"猜裸公式边界"（实测会把 `\lim..\frac..` 切成两段、
 * 也认不出 `\int_0^1x^2dx`）。改用**文字锚点**：
 * 取编辑前文字段的 trim 版本来定位，锚点之间的就是公式。
 * 详见 `utils/latex.ts: restoreMathDelimiters`。
 *
 * 所以这里必须记住**编辑前的原始值**（`originalForRestore`），
 * 它就是锚点的来源。`onFocus` 时记录。
 *
 * ⚠️ 只在失焦 / 点「完成」时调用，不在每次 input 时调用 ——
 *    打字过程中重新包 `$` 会打断输入法、也让光标乱跳。
 */
function finalizeValue() {
    const el = fieldRef.value
    if (!el) return

    const raw = stripMathPlaceholders(el.value || '')
    const original = originalForRestore.value

    // 用编辑前的结构做锚点还原
    let restored: string | null = null
    if (original) {
        restored = restoreMathDelimiters(original, raw)
    }
    // 锚点对不上（用户大改了文字）→ 退化：直接返回清理后的值。
    // 宁可少还原，也不要把结构造错。
    if (restored === null) restored = raw

    if (restored !== (props.modelValue || '')) {
        syncing = true
        emit('update:modelValue', restored)
        syncing = false
    }

    // 把还原后的值写回编辑器，
    // 这样用户再点进来看到的就是带定界符的完整内容
    if (restored !== raw) {
        try {
            syncing = true
            el.value = restored
            syncing = false
        } catch {
            /* 忽略 */
        }
    }

    // 更新锚点基准：下次编辑以这次的结果为原始结构
    originalForRestore.value = restored
}

/**
 * 失焦
 *
 * ── 为什么这里要主动关键盘（2026-10-27 用户反馈）──────────────
 * 用户原话：「出现的那个键盘 没法很好的关闭 用户点击空白地方没反应
 *            不会自动关闭」
 *
 * 根因：policy 是 `'manual'` 时，MathLive 的 `focusout` 处理
 * （mathlive.mjs:29061）会**整个跳过**自动收起逻辑 ——
 * 它的设计假设是"manual 模式由调用方自己管键盘"。
 *
 * 我们既然不要那个键盘，就在失焦时主动收掉：
 * 用户点空白处 → 编辑器 blur → 键盘关闭。这符合直觉。
 *
 * 加上 CSS 隐藏了打开入口，正常情况下键盘根本不会出现；
 * 这里是第二道保险（比如用户在别处打开过全局键盘）。
 */
function onBlur() {
    focused.value = false

    // 记下失焦瞬间的光标位置（插入符号时要还原，否则会插到末尾）
    const el = fieldRef.value
    if (el) {
        try {
            const pos = el.position
            if (typeof pos === 'number') savedOffset.value = pos
        } catch {
            /* 忽略 */
        }
    }

    // 失焦 = 一次编辑结束 → 把被 MathLive 吃掉的 `$` 定界符补回来
    finalizeValue()
    const kb = (window as any).mathVirtualKeyboard
    if (kb?.visible) {
        try {
            kb.hide?.()
            kb.visible = false
        } catch {
            /* 忽略 */
        }
    }
}

/**
 * 从符号面板插入
 *
 * `insert()` 插到**当前光标所在的槽位** —— 这正是"点根号就进根号里"的关键。
 * 若光标不在编辑器内，MathLive 会追加到末尾并把光标放进新结构的第一个槽。
 *
 * ⚠️ 先 `focus()`：从面板按钮点过来时焦点在按钮上，
 *    不先聚焦编辑器，`insert` 的落点会不确定。
 */
function insertLatex(latex: string) {
    const el = fieldRef.value
    if (!el || props.disabled || !props.editable) return

    // ⚠️ 关键：如果刚才因为点面板按钮而失焦，这里要先把光标恢复回
    //    用户原本停留的槽位，否则 focus() 会把光标放到末尾，
    //    符号就插错地方了（用户点进根号里、插进去却跑到末尾）。
    //
    //    `savedOffset` 是失焦瞬间记下的位置（见 onBlur）。
    el.focus()
    if (savedOffset.value !== null) {
        try {
            el.position = savedOffset.value
        } catch {
            /* 老版本没有 position setter，退化为末尾插入 */
        }
        savedOffset.value = null
    }
    el.insert(latex)
}

/* ────────────────────────────────────────────────────────────
 * 符号面板开合（要点：不能弄丢光标）
 * ──────────────────────────────────────────────────────────── */

/**
 * 符号按钮按下时**阻止默认行为**
 *
 * 浏览器在 `mousedown` 时就会把焦点从编辑器移到按钮上，
 * 等到 `click` 触发时 MathLive 的光标已经没了。
 * `preventDefault()` 能阻止这个焦点转移 —— 编辑器保持聚焦，
 * 光标留在原来那个槽里，面板展开后点符号就能插对位置。
 */
function onSymBtnMouseDown(e: MouseEvent) {
    e.preventDefault()
}

function togglePalette() {
    paletteOpen.value = !paletteOpen.value
    // 面板展开后把焦点还给编辑器：用户可以继续在公式里移动光标，
    // 也可以直接点面板里的符号
    if (paletteOpen.value) {
        requestAnimationFrame(() => {
            const el = fieldRef.value
            if (!el) return
            el.focus()
            if (savedOffset.value !== null) {
                try {
                    el.position = savedOffset.value
                } catch { /* 忽略 */ }
                savedOffset.value = null
            }
        })
    }
}

defineExpose({
    /** 聚焦编辑器 */
    focus: () => fieldRef.value?.focus(),
    /** 插入一段 LaTeX（供外部按钮调用） */
    insert: (latex: string) => insertLatex(latex),
    /**
     * 收尾：补回被 MathLive 吃掉的 `$` 定界符
     *
     * 外部（确认卡片的「完成」按钮 / 提交前）应调用一次，
     * 确保提交的值带定界符。失焦时也会自动调用。
     */
    finalize: () => finalizeValue(),
    /** 兼容 v3 接口：外部统一控制时无实际作用 */
    setEditing: (_v: boolean) => {},
    isEditing: () => focused.value,
    togglePalette: () => { paletteOpen.value = !paletteOpen.value },
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

/* 编辑区：字段 + 右侧符号按钮 */
.mi-body {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    min-width: 0;
}

.mi-body .mi-field {
    flex: 1 1 auto;
    min-width: 0;
}

/*
 * 符号按钮
 *
 * 内联在字段右侧（不占整行）：选项 A~D 若各自多一行按钮会很乱。
 * 用 `align-self: flex-start` 让它贴顶，字段变高时按钮不会跟着往下跑。
 */
.mi-sym-btn {
    flex: none;
    align-self: flex-start;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
    font-style: italic;
    line-height: 1;
    color: #409eff;
    background: #f2f8ff;
    border: 1px solid #cfe3fb;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.12s;
}

.mi-sym-btn:hover:not(:disabled) {
    background: #e4f1ff;
    border-color: #409eff;
}

.mi-sym-btn.is-active {
    color: #fff;
    background: #409eff;
    border-color: #409eff;
}

.mi-sym-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

/* 旧的「编辑」按钮样式保留（其他页面仍在用） */
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

.mi-edit-btn.is-active {
    color: #fff;
    background: #409eff;
    border-color: #409eff;
}

.mi-edit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/*
 * 纯展示模式（历史消息里的已确认卡片）
 *
 * 用 KaTeX 静态渲染替代 MathLive 实例 —— 外观与编辑器保持一致，
 * 但没有 shadow DOM、没有字体加载、没有光标引擎。
 */
.mi-static {
    flex: 1 1 auto;
    min-width: 0;
    padding: 7px 11px;
    border: 1px solid #eef0f3;
    border-radius: 6px;
    background: #fafbfc;
    font-size: 15px;
    line-height: 1.7;
    color: #374151;
    box-sizing: border-box;
    word-break: break-word;
    overflow-x: auto;
}

.is-single .mi-static {
    padding: 4px 9px;
    font-size: 14px;
}

.mi-static-empty {
    color: #b6bdc9;
    font-size: 13px;
}

/* ⚠️ 必须 :deep()：v-html 注入的 KaTeX 节点拿不到 scoped 属性 */
.mi-static :deep(.katex) {
    font-size: 1.02em;
}

.mi-static :deep(.katex-display) {
    margin: 4px 0;
}

/*
 * <math-field> 是 MathLive 的自定义元素。
 *
 * ⚠️ 它内部是 shadow DOM，普通 scoped 样式打不进去；
 *    这里只控制宿主元素的外观（边框/内边距/字号），
 *    内部排版由 MathLive 自己负责（它用的是自己的字体与 CSS）。
 */
.mi-field {
    display: block;
    width: 100%;
    padding: 7px 11px;
    border: 1px solid #d8dde5;
    border-radius: 6px;
    background: #fff;
    font-size: 17px;
    box-sizing: border-box;
    transition: border-color 0.15s, box-shadow 0.15s;
}

.mi-field:focus-within {
    border-color: #409eff;
    box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12);
}

/*
 * 隐藏 MathLive 工具栏上的「虚拟键盘」按钮
 *
 * ── 为什么必须这么做（2026-10-27 用户反馈）────────────────────
 * 用户截图：点开公式编辑器后底部弹出全宽数学键盘，
 *          **点空白处不关闭、也不会自动收**，把题目盖住了。
 *
 * 那个键盘不是自动弹的（policy 已设 manual），
 * 而是用户（或误触）点了工具栏上这个 ⌨ 图标打开的。
 * 一旦打开，因为 policy 是 manual，`focusout` 的自动收起逻辑
 * 被跳过（看 mathlive.mjs:29061），于是再也关不掉。
 *
 * 实测过：这个按钮**不在** `menuItems` 里（改菜单动不到它），
 * 它是 widget 上的一个独立 part。只能从 CSS 下手。
 *
 * 我们有自己的符号面板，不需要它。
 */
.mi-field::part(virtual-keyboard-toggle) {
    display: none;
}

/* 顺手把菜单按钮也收掉：里面的功能（改颜色/加粗/矩阵编辑）
   是给独立编辑器用的，嵌在题目字段里没有意义，反而误触 */
.mi-field::part(menu-toggle) {
    display: none;
}

/* 单行模式（选项/答案）：字号略小、内边距更紧 */
.is-single .mi-field {
    font-size: 16px;
    padding: 4px 9px;
}
</style>
