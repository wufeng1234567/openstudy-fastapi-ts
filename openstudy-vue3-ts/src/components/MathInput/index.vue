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
        <!-- 顶栏：标签 + 可选的符号面板开关 -->
        <div v-if="label || showEditButton" class="mi-head">
            <span v-if="label" class="mi-label">{{ label }}</span>
            <button v-if="showEditButton" type="button" class="mi-edit-btn" :disabled="disabled"
                :title="paletteOpen ? '收起符号面板' : '展开符号面板'"
                :class="{ 'is-active': paletteOpen }" @click="paletteOpen = !paletteOpen">
                {{ paletteOpen ? '收起符号' : '符号' }}
            </button>
        </div>

        <!--
          真正的编辑器：MathLive 的 <math-field>
          所见即所得，点结构内部即可编辑。
        -->
        <math-field ref="fieldRef" class="mi-field" :style="{ minHeight: `${fieldMinHeight}px` }"
            @input="onInput" @focus="onFocus" @blur="onBlur"></math-field>

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
import { stripMathPlaceholders } from '@/utils/latex'

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
        /** 是否显示自身的按钮（确认卡片里由头部统一控制时传 false） */
        showEditButton?: boolean
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
        startEditing: false,
        editable: true,
    },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const fieldRef = ref<any>(null)
const paletteOpen = ref(false)
const focused = ref(false)

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

onMounted(async () => {
    // 等自定义元素注册完成（MathLive 的 import 是异步注册的）
    try {
        await customElements.whenDefined('math-field')
    } catch {
        /* 老浏览器没有 whenDefined，直接继续 */
    }
    const el = fieldRef.value
    if (!el) return

    // 关掉 MathLive 自带的虚拟键盘：
    // 我们用项目自己的符号面板（只放需要的符号，且不会盖住整屏）
    el.mathVirtualKeyboardPolicy = 'manual'

    // 回填初始值
    if (props.modelValue) el.value = props.modelValue
    el.readOnly = isReadOnly.value

    // 占位符：MathLive 通过 placeholder 属性显示空态提示
    if (props.placeholder) el.setAttribute('placeholder', props.placeholder)
})

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
 */
function onInput() {
    if (syncing) return
    syncing = true
    emit('update:modelValue', stripMathPlaceholders(fieldRef.value?.value ?? ''))
    syncing = false
}

function onFocus() {
    focused.value = true
}

function onBlur() {
    focused.value = false
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
    if (!el || props.disabled) return
    el.focus()
    el.insert(latex)
}

defineExpose({
    /** 聚焦编辑器 */
    focus: () => fieldRef.value?.focus(),
    /** 插入一段 LaTeX（供外部按钮调用） */
    insert: (latex: string) => insertLatex(latex),
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

/* 单行模式（选项/答案）：字号略小、内边距更紧 */
.is-single .mi-field {
    font-size: 16px;
    padding: 4px 9px;
}
</style>
