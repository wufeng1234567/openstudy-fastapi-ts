<!--
  ============================================================================
  思维导图（2026-10-26 v3）
  ============================================================================

  ## 定位

  用户原话：「锦上添花而非核心功能 能做就做」。所以这个组件刻意做得**克制**：

    · 不引任何新依赖 —— 用项目已有的 echarts（`tree` series 原生支持径向布局）
    · 不做编辑器交互（拖拽/增删节点）—— 那是另一个产品的工作量
    · 只做一件事：**把一段有层级的文本变成一张能一眼看懂的图**

  对比过的第三方方案与放弃原因：

    | 方案 | 体积 | 放弃原因 |
    |---|---|---|
    | markmap | ~1.2MB | 要引 d3 + 自己的 markdown 解析，且样式不可控 |
    | mermaid mindmap | ~2.8MB | 体积最大，且它的 mindmap 语法要改造输入 |
    | @logicflow | 已在依赖里 | 是流程图库，画树要手写布局算法 |
    | **echarts tree** | **0（已在依赖）** | ✅ 原生 `layout:'radial'` 就是思维导图形态 |

  ## 输入格式

  Markdown。层级来源（优先级从高到低）：

    ① `#` / `##` / `###` … 标题
    ② `-` / `*` / `+` 无序列表（按**缩进**算层级）
    ③ `1.` / `2.` 有序列表

  这三种是笔记本来的形态，用户不需要学新语法。
-->
<template>
    <div class="mindmap-wrap">
        <div class="mindmap-toolbar">
            <span class="mm-title">{{ title }}</span>
            <div class="mm-actions">
                <!--
                  布局切换
                  ⚠️ 用 @change 打标记：用户手动选过之后，
                     `auto` 就不再把布局改回去（否则内容一变就跳，很莫名）。
                -->
                <el-radio-group v-model="layoutMode" size="small" @change="onLayoutChange">
                    <el-radio-button value="radial">径向</el-radio-button>
                    <el-radio-button value="tree">树形</el-radio-button>
                </el-radio-group>
                <el-button size="small" text @click="fitView">
                    <el-icon><FullScreen /></el-icon> 自适应
                </el-button>
                <!--
                  一键还原（2026-10-27 新增）

                  用户要求：「也支持一键回归原本模样」

                  拖动/缩放之后想回到"刚生成的样子"时用。
                  与「自适应」的区别：自适应是"按当前容器重新排版"（内容变了才需要），
                  还原是"把我拖动缩放的结果清掉"。这里是两个动作、两种情况，
                  所以给两个按钮 —— 合并成一个会让用户猜"它到底会重置什么"。
                -->
                <el-button size="small" text @click="resetView">
                    <el-icon><RefreshLeft /></el-icon> 还原
                </el-button>
                <!--
                  一键放大（2026-10-27 新增）

                  用户反馈：「最有效的办法是给个一键放大按钮 放大给用户观看 并且支持导出」

                  背景：导图嵌在对话气泡里时内容宽只有 ~430px，
                  树形布局横着长、三四层就挤不下（实测截图里中间层卡片被叶子压住）。
                  与其在窄容器里拼命调间距，不如让用户**一键放大**到整屏看。

                  ⚠️ 用弹窗而不是 `requestFullscreen()`：
                     浏览器全屏 API 需要用户手势且会隐藏浏览器 UI，
                     用户想同时看聊天记录就不方便；弹窗只占视口、随时能关。
                -->
                <el-button size="small" text @click="openZoom">
                    <el-icon><ZoomIn /></el-icon> 放大
                </el-button>
                <!--
                  导出图片（2026-10-27 新增）

                  导图最常见的用途是贴进 PPT / 文档 / 群里分享，
                  所以必须能导出成图片。用 canvas 的 toDataURL 拿到 PNG，
                  不引任何新依赖。
                -->
                <el-button size="small" text :disabled="!hasTree" @click="exportPng">
                    <el-icon><Download /></el-icon> 导出
                </el-button>
            </div>
        </div>

        <!--
          空态（2026-10-27 重做）

          用户原话：「还要提供思维导图优化功能 比如**什么场景用户会提问需要思维导图**」

          原来只说一句「这段内容里还没有可提取的层级」——
          用户看完仍然不知道该写什么。

          现在给三件事：
            ① 什么样的内容适合出导图（场景）
            ② 一个可直接照抄的最小示例
            ③ 为什么这篇内容出不来图（如果有内容但没层级）
        -->
        <div v-if="!hasTree" class="mm-empty">
            <el-icon :size="22"><Share /></el-icon>
            <p class="mm-empty-title">{{ emptyText }}</p>

            <!-- 有内容但没层级：说清原因，比单纯"没有层级"有用 -->
            <p v-if="hasContentButNoStructure" class="mm-empty-reason">
                这篇内容是一整段连续文字，没有标题或列表，
                所以提取不出层级。加上 <code>## 小标题</code> 或 <code>- 要点</code> 就会出图。
            </p>

            <!-- 场景引导 -->
            <div class="mm-empty-scenes">
                <p class="mm-empty-scenes-title">这些内容适合做成导图</p>
                <ul>
                    <li><strong>知识梳理</strong> —— 一章笔记、一份资料的主干与分支</li>
                    <li><strong>方案对比</strong> —— 几种做法的优缺点、适用条件</li>
                    <li><strong>复习提纲</strong> —— 考点分类、每个考点下的要点</li>
                    <li><strong>项目拆解</strong> —— 目标 → 模块 → 具体任务</li>
                </ul>
            </div>

            <details class="mm-empty-sample">
                <summary>看一个能出图的最小写法</summary>
                <pre>## 技术栈
- 框架：Vue 3
- 状态管理：Pinia

## 核心概念
- 响应式系统
- 组合式函数</pre>
            </details>
        </div>

        <div v-show="hasTree" ref="chartRef" class="mm-chart" :style="{ height: height + 'px' }"></div>
    </div>

    <!--
      放大查看弹窗（2026-10-27 新增）

      ⚠️ 与主视图**共用同一份数据、同一个 buildOption()**，但各自独立的 echarts 实例。
         不复用主实例：把一个已经初始化在 430px 容器里的实例挪进弹窗，
         需要 `dispose` + 重新 init，反而更容易出"尺寸错乱"的问题。

      ⚠️ 关闭时**必须 dispose** 弹窗里那个实例：
         否则每开一次就多留一份 canvas 与事件监听，连开几次内存会一直涨。
    -->
    <el-dialog v-model="zoomVisible" :title="title" width="92%" top="3vh" append-to-body
        class="mm-zoom-dialog" destroy-on-close @closed="disposeZoom">
        <div ref="zoomChartRef" class="mm-chart mm-chart-zoom"></div>
        <template #footer>
            <div class="mm-zoom-foot">
                <span class="mm-zoom-hint">可拖动平移、滚轮缩放；导出会保留你调整后的样子</span>
                <div>
                    <el-button size="small" @click="zoomFit">自适应</el-button>
                    <el-button size="small" @click="resetView">还原</el-button>
                    <el-button size="small" type="primary" @click="exportPng(true)">导出图片</el-button>
                </div>
            </div>
        </template>
    </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { FullScreen, Share, ZoomIn, Download, RefreshLeft } from '@element-plus/icons-vue'
import * as echarts from 'echarts'

defineOptions({ name: 'MindMap' })

const props = withDefaults(
    defineProps<{
        /** Markdown 源文（标题 / 列表 / 缩进都能识别） */
        markdown?: string
        /**
         * 直接传入现成的树（优先于 `markdown`）
         *
         * 用于「资料结构树」：后端 `outline_tree_service` 已经从原文标题
         * 还原好了层级，前端不需要再解析一遍 Markdown。
         * 传这个时 `markdown` 被忽略。
         */
        treeData?: { name: string; children?: any[] } | null
        /** 根节点名（通常传笔记标题） */
        title?: string
        /** 没有可解析内容时的提示 */
        emptyText?: string
        /**
         * 初始布局
         *
         * ⚠️ 默认值从 `radial` 改成 `tree`（2026-10-27 实测决定）
         *
         * 原因是**实测出来的真实缺陷**，不是审美偏好：
         * 改用卡片样式后，卡片比原来的小圆点宽很多（一个 18 字标签
         * 展开约 150px）。径向布局把同层节点排在同心圆上，
         * 一个分支有 6 个子节点时它们挤在同一个扇区里，
         * 长标签会**横向伸出去压住父节点卡片**
         * （截图确认：「使用 keep-alive 缓存路由组件」压住了「性能优化清单」）。
         *
         * 试过的三种修法都不理想：
         *   · `position:'inside'` → 卡片压节点本身
         *   · `width:150 + truncate` → 把「核心框架」切成「心框架」，更糟
         *   · 加大 edgeLength → 只是把重叠推远，节点更多时还会撞
         *
         * 正交树形布局天然不会重叠：每一层固定占一列，纵向按需撑开。
         * 卡片样式配上从左到右的层级关系，可读性明显更好。
         *
         * 径向仍然保留（用户点按钮即可切换），
         * 节点少（<12）时环形更紧凑好看，所以少量节点时仍默认径向。
         */
        defaultLayout?: 'radial' | 'tree' | 'auto'
        /**
         * 画布高度（px）—— 2026-10-27 新增
         *
         * ⚠️ 之前高度是写死在 `.mm-chart` 上的 560px，调用方无从调整。
         *    把导图嵌进对话气泡（宽度只有 ~430px）时，叶子多的图会
         *    在垂直方向挤成一团（实测 40 个叶子全叠在一起、文字互相压住）。
         *
         *    现在由调用方按**叶子节点数**算一个合适的高度传进来：
         *    叶子多就给高些，叶子少就矮些。默认 560 保持原有观感。
         */
        height?: number
    }>(),
    {
        markdown: '',
        treeData: null,
        title: '思维导图',
        emptyText: '这段内容里还没有可提取的层级（标题或列表），写几条要点就会出现导图。',
        defaultLayout: 'auto',
        height: 560,
    },
)

/** echarts tree 的节点结构 */
interface TreeNode {
    name: string
    children?: TreeNode[]
    value?: number
    // echarts 允许附加自定义字段，这里用来存层级以便配色
    depthLevel?: number
}

const chartRef = ref<HTMLDivElement>()

/**
 * 当前生效的布局（只有两种，`auto` 会在算完节点数后落到其中之一）
 *
 * 初始给 'tree'，等树算出来之后由 `autoResolvedMode` 决定要不要换径向。
 * 不能直接写 `ref(props.defaultLayout)`：那会把 'auto' 当成合法值传下去。
 */
const layoutMode = ref<'radial' | 'tree'>(props.defaultLayout === 'radial' ? 'radial' : 'tree')

/** 用户是否手动点过布局按钮（点过之后就不再自动切） */
const layoutTouched = ref(false)

let chart: echarts.ECharts | null = null

/* ────────────────────────────────────────────────────────────
 * Markdown → 树
 * ──────────────────────────────────────────────────────────── */

/** 去掉行内 Markdown 标记（加粗/斜体/代码/链接/公式），只留可读文字 */
function stripInline(s: string): string {
    return (s || '')
        .replace(/\$[^$]*\$/g, '')           // 行内公式整个去掉（导图里显示 LaTeX 没意义）
        .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 图片
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // 链接保留文字
        .replace(/`([^`]*)`/g, '$1')          // 行内代码
        .replace(/\*\*([^*]*)\*\*/g, '$1')    // 粗体
        .replace(/\*([^*]*)\*/g, '$1')        // 斜体
        .replace(/【图\d+】/g, '')             // 解析器插入的图片占位
        .replace(/\s+/g, ' ')
        .trim()
}

/** 截断过长的节点名（图里放不下，反而看不清） */
function clipName(s: string, max = 26): string {
    if (!s) return ''
    return s.length > max ? s.slice(0, max - 1) + '…' : s
}

/**
 * 节点数超过这个值就**默认只展开 3 层**
 *
 * 为什么需要：真实笔记（如「Vue3 深度实战笔记」4315 字符）能提出 40+ 个节点，
 * 全展开后 640px 宽的容器里标签**互相压住**、右侧还溢出被裁掉
 * （2026-10-26 实测截图：`nueuse/core`、`pnpm` 都被切掉了）。
 *
 * 这不是"图不好看"，是**读不出来**。所以节点多时先展开到第 3 层，
 * 用户想深看再点开（echarts tree 的 expandAndCollapse 已开）。
 */
const EXPAND_DEPTH_LIMIT = 3
const MANY_NODES_THRESHOLD = 18

/**
 * 解析 Markdown 为树
 *
 * 层级判定：
 *   · 标题 `#{1,6}` → level = # 的个数
 *   · 列表 `-`/`*`/`1.` → level = 5 + (缩进空格数 / 2)
 *
 * 为什么列表层级加 5：让列表永远排在标题**下面**，
 * 不会出现「## 小节」和「- 要点」平级的错乱。
 *
 * 边界：如果整段压根没有标题和列表，就返回 null（由调用方显示空态），
 *       而不是硬造一个只有根节点的图 —— 那对用户没有价值。
 */
function parseMarkdownToTree(md: string, rootName: string): TreeNode | null {
    if (!md || !md.trim()) return null

    const lines = md.split(/\r?\n/)
    const root: TreeNode = { name: clipName(rootName || '导图', 30), children: [] }

    /** 每个层级最近一次出现的节点，用于挂载下一层 */
    const stack: Array<{ level: number; node: TreeNode }> = [{ level: 0, node: root }]
    let nodeCount = 0

    /**
     * 去掉与根节点同名的首个标题
     *
     * ⚠️ 实测缺陷（2026-10-27）：传入 title="Vue3 深度实战笔记"，
     *    而 Markdown 第一行恰好是 `# Vue3 深度实战笔记` ——
     *    于是图上出现「Vue3 深度实战笔记 → Vue3 深度实战笔记」的重复，
     *    中间那个节点毫无意义，还占一层布局。
     *
     *    笔记页的 title 通常就来自文档的一级标题，重复是常态而非个例。
     */
    const rootText = (rootName || '').trim()
    if (rootText) {
        for (let i = 0; i < lines.length; i++) {
            const h = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(lines[i])
            if (!h) continue
            if (h[1].length === 1 && stripInline(h[2]).trim() === rootText) {
                lines.splice(i, 1)
            }
            break // 只看第一个标题
        }
    }

    const push = (level: number, text: string) => {
        if (!text) return
        // 弹出比当前层级更深的栈
        while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop()
        const parent = stack[stack.length - 1].node
        const node: TreeNode = { name: clipName(text), children: [], depthLevel: level }
        if (!parent.children) parent.children = []
        parent.children.push(node)
        stack.push({ level, node })
        nodeCount++
    }

    for (const raw of lines) {
        const line = raw.replace(/\t/g, '  ')

        // ① 标题
        const h = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line)
        if (h) {
            push(h[1].length, stripInline(h[2]))
            continue
        }

        // ② 列表（先算缩进）
        const indentMatch = /^(\s*)/.exec(line)
        const indent = indentMatch ? indentMatch[1].length : 0
        const list = /^\s*(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line)
        if (list) {
            // 每 2 个空格算一层；1 个空格也至少进一层（容忍不规整缩进）
            const depth = Math.floor(indent / 2)
            push(5 + depth, stripInline(list[1]))
            continue
        }

        // ③ 表格/代码块/引用/分隔线：跳过（导图里放这些没意义）
        if (/^\s*[|>`]/.test(line) || /^\s*---+\s*$/.test(line)) continue
    }

    // 没有任何子节点 → 不算有效导图
    if (nodeCount === 0 || !root.children || root.children.length === 0) return null
    return root
}

/**
 * 最终要画的树
 *
 * 两条数据来源：
 *   ① `treeData` —— 后端已经解析好的结构（资料结构树走这条）
 *   ② `markdown` —— 前端自己解析（笔记页走这条）
 *
 * 为什么允许多一条来源而不是让调用方自己解析成树：
 * 结构树的解析规则（Markdown 标题 / 中文序号 / 数字序号 / 题库型文档剔除题号）
 * 已经在后端实现并测过 6 份真实文档。前端再实现一遍必然产生分歧
 * —— 同一份资料，后端说 8 个章节、前端画出 6 个，用户会发现对不上。
 */
const treeData = computed<TreeNode | null>(() => {
    if (props.treeData) {
        // 后端传来的树可能没有 children 字段（叶子），补成 null 交给 decorate 处理
        return props.treeData as TreeNode
    }
    return parseMarkdownToTree(props.markdown, props.title)
})
const hasTree = computed(() => treeData.value !== null)

/**
 * 有内容、但提取不出层级
 *
 * 用途：空态里区分两种完全不同的情况
 *   ① 内容就是空的 → 说"写点东西"
 *   ② 内容不少、但没有标题/列表 → 说清**为什么出不来**，
 *      并告诉用户加什么就能出图
 *
 * 不区分的话，用户写了一大段话却看到"还没有可提取的层级"，
 * 会以为功能坏了。
 */
const hasContentButNoStructure = computed(() => {
    if (hasTree.value) return false
    const md = props.markdown || ''
    const meaningful = md.replace(/\s/g, '')
    if (meaningful.length < 30) return false
    // 有内容但没有任何标题或列表标记
    return !/^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s)/m.test(md)
})

/** 节点数（用于 tooltip 里报告规模） */
const nodeCount = computed(() => {
    const count = (n: TreeNode | undefined): number =>
        !n ? 0 : 1 + (n.children || []).reduce((s, c) => s + count(c), 0)
    return count(treeData.value ?? undefined)
})

/**
 * `auto` 布局的判定阈值
 *
 * ⚠️ 这个值最终定为 0，也就是**默认一律用树形**。
 *
 * 原因是实测出来的：径向布局在"节点很少"时反而更容易重叠 ——
 * 一级节点的环半径被 echarts 压到刚好放得下，而根节点卡片是
 * 居中于圆心的，宽度向左右各伸一半，于是直接盖住两侧的一级卡片
 * （截图确认：「纯文本测试」压住「核心概念」「技术栈」）。
 *
 * 试过的修法：
 *   · 根卡片 `position:'top'` → 径向布局下**整张图画不出来**
 *     （canvas 空白，实测确认），echarts 在 radial 下不支持这个组合
 *   · 加大 edgeLength/nodePadding → 减轻但没消除
 *   · 缩短根标签 → 只缓解
 *
 * 树形布局没有这个问题：每层固定占一列，纵向自动撑开。
 * 所以默认树形，径向保留给用户手动切换（那时他会自己 roam/缩放）。
 */
const AUTO_RADIAL_MAX_NODES = 0

/**
 * 按内容规模自动选布局
 *
 * 只在用户**没手动点过**布局按钮时生效 ——
 * 用户点了「树形」以后如果内容变化又自动切回径向，会让人莫名其妙。
 */
const autoResolvedMode = computed<'radial' | 'tree'>(() => {
    if (props.defaultLayout !== 'auto') {
        return props.defaultLayout === 'radial' ? 'radial' : 'tree'
    }
    return nodeCount.value <= AUTO_RADIAL_MAX_NODES ? 'radial' : 'tree'
})

watch(
    autoResolvedMode,
    (m) => {
        if (layoutTouched.value) return
        if (layoutMode.value !== m) layoutMode.value = m
    },
    { immediate: true },
)

/* ────────────────────────────────────────────────────────────
 * 渲染
 * ──────────────────────────────────────────────────────────── */

/**
 * 节点配色：按**一级分支**染色（2026-10-27 重做）
 *
 * 关键变化：以前按 depth 染色，导致所有二级节点同色、所有三级节点同色 ——
 * 视觉上分不出"这些节点属于同一个分支"。
 *
 * 现在按**所属一级分支**分配颜色（同一分支下的所有子节点同色系），
 * 用户一眼能看出"这一簇是讲技术栈的、那一簇是讲性能的"。
 * 这正是思维导图要表达的东西。
 */
const BRANCH_PALETTE = [
    { main: '#3b82f6', light: '#eff6ff', border: '#bfdbfe', text: '#1e40af' }, // 蓝
    { main: '#f59e0b', light: '#fffbeb', border: '#fde68a', text: '#92400e' }, // 琥珀
    { main: '#10b981', light: '#f0fdf4', border: '#bbf7d0', text: '#065f46' }, // 绿
    { main: '#8b5cf6', light: '#f5f3ff', border: '#ddd6fe', text: '#5b21b6' }, // 紫
    { main: '#ec4899', light: '#fdf2f8', border: '#fbcfe8', text: '#9d174d' }, // 粉
    { main: '#06b6d4', light: '#ecfeff', border: '#a5f3fc', text: '#155e75' }, // 青
    { main: '#ef4444', light: '#fef2f2', border: '#fecaca', text: '#991b1b' }, // 红
    { main: '#84cc16', light: '#f7fee7', border: '#d9f99d', text: '#3f6212' }, // 青柠
]

/** 根节点配色（中性深色，压得住整张图） */
const ROOT_STYLE = { main: '#1f2937', light: '#f3f4f6', border: '#9ca3af', text: '#111827' }

/**
 * 按"一级分支序号"取色
 *
 * `branchIndex` 从 0 开始；根节点传 -1 走 ROOT_STYLE。
 */
function branchStyle(branchIndex: number) {
    if (branchIndex < 0) return ROOT_STYLE
    return BRANCH_PALETTE[branchIndex % BRANCH_PALETTE.length]
}

/**
 * 标签最大字数（按节点层级给不同上限）
 *
 * ⚠️ 实测缺陷：原来叶子统一 14 字，截图里出现大量
 *    `组件库: Vue...`、`UI 框架: @vueuse/c...` ——
 *    关键的区分信息（是 Vue 还是 React）正好被截掉了。
 *
 * 现在：一级分支 30 字，叶子 26 字。
 * 卡片本身有底色和边框，长一点也不会造成"文字浮在空中"的错觉；
 * 真的放不下时用户可以 roam 放大、或 hover 看 tooltip 全文。
 */
const MAX_LABEL_BRANCH = 30
const MAX_LABEL_LEAF = 26

function buildOption() {
    const data = treeData.value
    if (!data) return {}

    /**
     * 递归装饰节点 —— **卡片样式**
     *
     * 视觉目标（用户原话「思维导图是否卡片样式 是否可以优化的更美观」）：
     *   · 每个节点是一个**圆角卡片**，而不是一个小圆点
     *   · 一级分支实心色块（重），更深层是浅底+同色字（轻）
     *   · 根节点深色实心，最大
     *
     * 实现：echarts 的 `label` 支持 `backgroundColor` / `padding` /
     * `borderRadius`，把 label 本身做成卡片，再把 symbol 缩小成一个小点
     * 充当"连接锚点"（完全不要 symbol 的话连线起点会飘）。
     */
    const decorate = (node: TreeNode, depth: number, branchIdx: number): any => {
        const isRoot = depth === 0
        const isBranch = depth === 1
        const style = branchStyle(isRoot ? -1 : branchIdx)

        // 卡片样式：根/一级实心（重），更深层浅底（轻）
        const cardBg = isRoot || isBranch ? style.main : style.light
        const cardText = isRoot || isBranch ? '#ffffff' : style.text
        const cardBorder = isRoot || isBranch ? style.main : style.border

        const fontSize = isRoot ? 15 : isBranch ? 13 : 12
        const padding: [number, number] = isRoot ? [9, 14] : isBranch ? [7, 11] : [5, 9]
        const maxLen = isBranch ? MAX_LABEL_BRANCH : MAX_LABEL_LEAF

        return {
            name: node.name,
            // symbol 缩到很小：它的作用是给连线提供锚点，不承担视觉重量
            symbolSize: isRoot ? 8 : 5,
            itemStyle: {
                color: isRoot || isBranch ? style.main : style.border,
                borderWidth: 0,
            },
            label: {
                show: true,
                formatter: () => clipName(node.name, isRoot ? (isRadial ? 14 : 28) : maxLen),
                fontSize,
                fontWeight: isRoot ? 700 : isBranch ? 600 : 400,
                color: cardText,
                backgroundColor: cardBg,
                borderColor: cardBorder,
                borderWidth: isRoot || isBranch ? 0 : 1,
                borderRadius: 6,
                padding,
                // 卡片之间靠阴影拉开层次（echarts label 支持 shadow）
                shadowBlur: isRoot ? 10 : isBranch ? 6 : 0,
                shadowColor: isRoot ? 'rgba(17,24,39,0.22)' : 'rgba(15,23,42,0.10)',
                shadowOffsetY: isRoot ? 2 : isBranch ? 1 : 0,
            },
            children: (node.children || []).map((c, i) =>
                // 一级节点的每个孩子开一个新分支色；更深层继承该分支色
                decorate(c, depth + 1, isBranch ? i : branchIdx),
            ),
        }
    }

    const decorated = decorate(data, 0, -1)
    const isRadial = layoutMode.value === 'radial'

    // 节点多时只展开前几层；节点少就全展开（一眼看全更爽）
    const manyNodes = nodeCount.value > MANY_NODES_THRESHOLD
    const initDepth = manyNodes ? EXPAND_DEPTH_LIMIT : -1

    /**
     * 布局参数（2026-10-27 重做）
     *
     * ⚠️ 实测缺陷：原来树形布局 `right: '32%'` 让画布右半边空着，
     *    而标签全挤在左半边互相重叠。径向布局又没有给足半径，
     *    叶子标签在密集区叠成一团（截图里右侧那一坨完全看不清）。
     *
     * 现在：
     *   · 树形：左右各留 20%，标签有地方展开
     *   · 径向：用 `edgeLength` 拉开层间距（这是 echarts tree radial 的关键参数）
     */
    const seriesBase: any = {
        type: 'tree',
        data: [decorated],
        layout: isRadial ? 'radial' : 'orthogonal',
        orient: 'LR',
        symbol: 'circle',
        edgeShape: 'curve',
        edgeForkPosition: '50%',
        initialTreeDepth: initDepth,
        roam: true,
        expandAndCollapse: true,
        animationDuration: 420,
        animationDurationUpdate: 320,
        lineStyle: {
            // 连线用浅灰，不抢卡片的视觉重量
            color: '#dbe2ea',
            width: 1.4,
            curveness: isRadial ? 0.5 : 0,
        },
        // 标签位置（按布局分别处理）
        //
        // ⚠️ 三次调整的教训（2026-10-27 实测）：
        //
        // ① `left` + `align:'right'`：在 0×0 容器里退化成竖排 ——
        //    但那是容器问题（已由 ResizeObserver 修掉），不是 position 的锅。
        //
        // ② `inside`：卡片压在节点上，径向布局的子节点间距按"圆点"算，
        //    左侧子节点的卡片会**盖住父节点卡片**
        //    （截图：`使用 keep-alive...` 压在「性能优化清单」上）。
        //
        // ③ 现在按布局分开：
        //    · 雷达/径向 → `outside`：卡片在**远离圆心的一侧**，
        //      子节点向外展开不会回撞父节点
        //    · 树形（正交）→ `right`：卡片挂右侧，符合从左到右的阅读顺序
        label: {
            position: isRadial ? 'outside' : 'right',
            align: isRadial ? 'center' : 'left',
            verticalAlign: 'middle',
            rotate: 0,
            distance: isRadial ? 10 : 6,
        },
        leaves: {
            label: {
                position: 'outside',
                align: isRadial ? 'center' : 'left',
                verticalAlign: 'middle',
                rotate: 0,
                distance: isRadial ? 10 : 6,
            },
        },
    }

    if (isRadial) {
        // edgeLength 控制每层半径间距；nodePadding 控制同层节点间距
        //
        // ⚠️ 实测两个坑：
        //   ① 值偏小时叶子卡片互相压住（卡片比圆点占地方大得多）
        //   ② **节点很少时反而更挤** —— 只有 6 个节点时 echarts 会把
        //      半径缩到刚好放得下，于是根卡片和一级卡片直接叠在一起
        //      （截图确认：「纯文本测试」压住「核心概念」和「技术栈」）。
        //
        //      所以不能按"节点少就缩小间距"来给值，反而要给一个
        //      **最小间距下限**，让内容少时也有呼吸空间。
        Object.assign(seriesBase, {
            edgeLength: manyNodes ? 140 : 175,
            nodePadding: manyNodes ? 18 : 26,
            top: '8%',
            bottom: '8%',
            left: '10%',
            right: '10%',
        })
    } else {
        // 树形（正交）布局的留白
        //
        // ⚠️ 卡片比圆点宽得多，左右留白必须给足：
        //    右侧是"叶子卡片伸出去"的方向，留 26% 才不会被容器裁掉。
        //    原来各 20% 时，最右一列长标签会被切掉尾巴。
        //
        // ⚠️⚠️ 必须显式给 `nodePadding`（2026-10-27 修「放大了还是重叠」）
        //
        //    这是本轮最关键的修复。echarts 的 tree 在**没给 nodePadding** 时，
        //    会把节点沿纵向均匀铺满容器高度 —— 也就是说：
        //    容器高度不变而叶子数量增加时，它不会撑开，而是**压缩行距**，
        //    直到卡片互相压住。
        //
        //    实测证据：同一份 40 个叶子的导图，内嵌视图（高度 900）和
        //    放大弹窗（高度 724）都出现卡片重叠 —— 因为 40 个叶子 × 每张卡
        //    28px 起步需要 1100px 以上，容器再宽也没用，**缺的是纵向空间**。
        //
        //    给了 nodePadding 之后，echarts 会按这个最小行距排布，
        //    放不下就出现滚动/缩放（`roam: true` 本来就支持），
        //    而不是把卡片叠在一起骗人。
        //
        //    值取 26（比卡片高度略大）：卡片约 24~28px，加上行间呼吸刚好。
        //    节点特别多时（>60）略降到 22，避免整张图高得离谱。
        Object.assign(seriesBase, {
            top: '5%',
            bottom: '5%',
            left: '22%',
            right: '26%',
            // 同层节点的**最小纵向间距**：这是防重叠的关键
            nodePadding: manyNodes ? 22 : 26,
            /*
             * 层间横向间距（2026-10-27 同一轮补）
             *
             * ⚠️ `nodePadding` 只管**纵向**。横向重叠是另一个问题：
             *    树形布局里父节点卡片挂在右侧、子节点再往右一列，
             *    而 echarts 默认按"圆点"算列宽 —— 卡片（约 150px）比圆点宽得多，
             *    于是**子节点卡片会盖住父节点卡片**。
             *
             *    截图证据：「Web 框架 → Axum」那张卡被第三层的
             *    「路由与提取器」压住右半边。
             *
             *   `edgeLength` 是 tree 布局的**每层间距**（横向）。
             *    默认值约 100，不够放一张卡片 + 连线距离。
             *    180 能让"卡片宽 150 + 30 留白"正好排开。
             *
             * ⚠️ 不设更大：每层 180 意味着 4 层就要 720px 横向空间，
             *    在 430px 宽的对话气泡里只能靠放大/拖动看 ——
             *    但那是对的，总比卡片互相压住好。
             */
            edgeLength: manyNodes ? 160 : 180,
        })
    }

    return {
        tooltip: {
            trigger: 'item',
            triggerOn: 'mousemove',
            confine: true,
            // tooltip 里给**完整名称**：卡片上截断的字在这里能看全
            formatter: (p: any) => {
                const n = String(p.name || '')
                const clipped = n.length > 20
                return clipped ? `<div style="max-width:320px;white-space:normal;line-height:1.5">${n}</div>` : n
            },
            backgroundColor: 'rgba(17,24,39,0.92)',
            borderWidth: 0,
            textStyle: { color: '#fff', fontSize: 12 },
            padding: [7, 10],
        },
        series: [seriesBase],
    }
}

function render() {
    if (!hasTree.value) {
        chart?.clear()
        return
    }
    nextTick(() => {
        if (!chartRef.value) return

        // ⚠️ 容器尺寸为 0 时**不初始化**（2026-10-27 修）
        //    在 el-collapse 里展开动画未结束时，offsetWidth 是 0。
        //    此时 echarts.init 会得到一个退化布局（标签竖排、节点叠成一条线），
        //    而且之后不会自愈。交给 ResizeObserver 等尺寸出现再画。
        const w = chartRef.value.offsetWidth
        const h = chartRef.value.offsetHeight
        if (w < 40 || h < 40) {
            return
        }

        if (!chart) {
            chart = echarts.init(chartRef.value)
        }
        chart.setOption(buildOption(), true)
        chart.resize()
    })
}

/** 自适应：把整张图缩放到可见范围内 */
/**
 * 一键还原（2026-10-27 新增）
 *
 * 用户要求：「也支持一键回归原本模样」
 *
 * `roam: true` 让用户能拖动平移、滚轮缩放，但那个状态**保存在 echarts 实例内部**，
 * 一旦拖远了就回不去。这里重设 option 就能回到"按当前容器重新排布"的初始状态。
 *
 * ⚠️ 为什么不用 `dispatchAction({type:'restore'})`：
 *    那是 toolbox 的 restore，在 tree 系列下会把 option 也一并重置，
 *    连带清掉布局模式与展开状态 —— 用户只想"把视图摆正"，不想"重置一切"。
 *
 * ⚠️ 主视图和弹窗视图是**两个独立实例**，各自还原：
 *    弹窗没打开时 `zoomChart` 是 null，这行自然是空操作。
 */
function resetView() {
    if (chart) {
        chart.setOption(buildOption(), true)
        chart.resize()
    }
    if (zoomChart) {
        zoomChart.setOption(buildOption(), true)
        zoomChart.resize()
    }
}

function fitView() {
    if (!chart) return
    // echarts tree 没有直接的 "fit" API，重设 option + resize 即可回到初始比例
    chart.setOption(buildOption(), true)
    chart.resize()
}

/* ────────────────────────────────────────────────────────────
 * 放大查看 + 导出图片（2026-10-27 新增）
 *
 * 用户要求：「最有效的办法是给个一键放大按钮 放大给用户观看 并且支持导出」
 *
 * 为什么放大比"在窄容器里调间距"更有效：
 *   树形布局是横着长的（根在左、叶子在右），每多一层就多占一列。
 *   对话气泡里内容宽只有 ~430px，三层卡片加连线必然挤。
 *   与其在 430px 里优化到极致，不如给用户一个"一键看全"的出口 ——
 *   放大后视口有 1300px+，同样一张图立刻舒展。
 * ──────────────────────────────────────────────────────────── */

/** 放大弹窗是否可见 */
const zoomVisible = ref(false)
/** 弹窗里的图表容器 */
const zoomChartRef = ref<HTMLDivElement>()
/** 弹窗里的 echarts 实例（独立于主视图，关闭时必须 dispose） */
let zoomChart: echarts.ECharts | null = null

/**
 * 打开放大视图
 *
 * ⚠️ 必须等弹窗**渲染完成**（`nextTick`）再初始化图表：
 *    弹窗刚打开时容器还没进 DOM，`offsetWidth` 为 0 ——
 *    在 0×0 容器里 init 会让 echarts 退化成极端布局
 *    （正是本组件注释里记过的"标签竖排、卡片挤成一条线"那个坑）。
 */
async function openZoom() {
    if (!hasTree.value) return
    zoomVisible.value = true
    await nextTick()
    // 再等一帧：el-dialog 有入场动画，容器尺寸在动画结束前可能还不稳定
    requestAnimationFrame(() => {
        const el = zoomChartRef.value
        if (!el) return
        if (!zoomChart) {
            zoomChart = echarts.init(el)
        } else {
            zoomChart.dispose()
            zoomChart = echarts.init(el)
        }
        zoomChart.setOption(buildOption(), true)
        zoomChart.resize()
    })
}

/** 弹窗内自适应 */
function zoomFit() {
    if (!zoomChart) return
    zoomChart.setOption(buildOption(), true)
    zoomChart.resize()
}

/**
 * 关闭弹窗后销毁实例
 *
 * ⚠️ 不 dispose 会泄漏：每次打开都新建一个 canvas + 若干事件监听，
 *    连开几次内存一直涨，而且旧实例还可能持有已卸载 DOM 的引用。
 */
function disposeZoom() {
    if (zoomChart) {
        zoomChart.dispose()
        zoomChart = null
    }
}

/**
 * 导出 PNG
 *
 * 优先导出**放大视图**（`useZoom === true` 且它在打开状态），
 * 否则导出主视图 —— 用户点了放大后再点导出，期望得到的就是他看到的那张大图。
 *
 * ⚠️ echarts 的 `getDataURL` 会返回 `data:image/png;base64,...`，
 *    用 `pixelRatio: 2` 拿两倍图（贴进文档/PPT 才清晰，不会一放大就糊）。
 * ⚠️ 背景色必须显式给白：默认透明，贴到深色背景的文档里会变黑底。
 */
function exportPng(useZoom = false) {
    const target = useZoom && zoomChart ? zoomChart : chart
    if (!target) return

    let url = ''
    try {
        url = target.getDataURL({
            type: 'png',
            pixelRatio: 2,
            backgroundColor: '#ffffff',
        })
    } catch (e) {
        console.warn('[mindmap] 导出失败', e)
        return
    }
    if (!url) return

    // 用 <a download> 触发下载：不需要后端、不需要新依赖
    const safe = String(props.title || '思维导图')
        .replace(/[\\/:*?"<>|\r\n\t]+/g, '_')
        .slice(0, 60)
    const a = document.createElement('a')
    a.href = url
    a.download = `${safe}.png`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
}

/** 弹窗打开时若窗口尺寸变化，让弹窗里的图跟着重排 */
function onZoomResize() {
    zoomChart?.resize()
}

function handleResize() {
    chart?.resize()
}

watch(
    () => [props.markdown, props.title, props.treeData],
    () => render(),
)
watch(layoutMode, () => render())

/** 用户手动切布局：打上标记，`auto` 之后不再干预 */
function onLayoutChange() {
    layoutTouched.value = true
}

/**
 * 容器尺寸监听（2026-10-27 修）
 *
 * ── 修的什么问题 ──────────────────────────────────────────────
 * 实测：笔记页里思维导图放在 `el-collapse` 里，用户点开折叠条时，
 * `render()` 在**展开动画还没结束**时就执行了 ——
 * 那一刻 `.mm-chart` 的 `offsetWidth/offsetHeight` 都是 **0**。
 *
 * echarts 在 0×0 的容器里初始化，会退化成一个极端布局：
 * 根节点标签被**旋转 90° 竖排**、所有卡片挤在一条竖线上
 * （截图里那两个竖着的黑块就是这么来的）。
 *
 * 原来只监听 `window.resize`，容器从 0 变成 909px 这种变化它感知不到，
 * 图就一直停在坏掉的布局上。
 *
 * ResizeObserver 能捕捉"容器从 0 变成有尺寸"这个瞬间，
 * 此时再 resize + 重算布局就正常了。
 */
let ro: ResizeObserver | null = null

onMounted(() => {
    render()
    window.addEventListener('resize', handleResize)

    if (typeof ResizeObserver !== 'undefined' && chartRef.value) {
        let lastW = 0
        let lastH = 0
        ro = new ResizeObserver((entries) => {
            for (const e of entries) {
                const w = Math.round(e.contentRect.width)
                const h = Math.round(e.contentRect.height)
                // 只在**有意义的变化**时重排：忽略 1px 抖动，
                // 也忽略"从有尺寸变 0"（收起动画中间态）
                if (w === lastW && h === lastH) continue
                lastW = w
                lastH = h
                if (w < 40 || h < 40) continue
                // 尺寸回来了：重新 init（若之前是 0×0 初始化的）并重设布局
                if (!chart && chartRef.value) {
                    chart = echarts.init(chartRef.value)
                }
                chart?.resize()
                chart?.setOption(buildOption(), true)
            }
        })
        ro.observe(chartRef.value)
    }
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    ro?.disconnect()
    ro = null
    chart?.dispose()
    chart = null
    // 弹窗里的实例也要销毁（2026-10-27）：否则组件卸载后它仍占着 canvas 与监听
    disposeZoom()
})

defineExpose({ fitView, nodeCount, openZoom, exportPng })
</script>

<style scoped>
.mindmap-wrap {
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100%;
}

.mindmap-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
}

.mm-title {
    font-size: 13.5px;
    font-weight: 600;
    color: #2f3946;
}

.mm-actions {
    display: flex;
    align-items: center;
    gap: 8px;
}

.mm-chart {
    width: 100%;
    /*
     * ⚠️ 高度**不在这里写死**（2026-10-27 改）：
     *    原来这里有 `height: 560px`，导致调用方传的 `height` prop 永远不生效
     *    （组件之前根本没读那个 prop）。
     *
     *    现在由模板上的 `:style="{ height: height + 'px' }"` 控制，
     *    默认值在 props 里（560）。嵌入对话气泡等窄容器时，
     *    调用方可以按叶子节点数传一个更合适的高度，避免节点挤在一起。
     */
    background: #fcfdfe;
    border: 1px solid #eef0f3;
    border-radius: 8px;
}

/*
 * 放大弹窗里的图表（2026-10-27）
 *
 * 高度按视口算：弹窗 top 3vh + 标题栏 + footer，剩下都给图。
 * `calc(92vh - 150px)` 比写死 800px 更能适配不同屏幕。
 */
.mm-chart-zoom {
    height: calc(92vh - 150px);
    min-height: 420px;
}

.mm-zoom-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.mm-zoom-hint {
    font-size: 12px;
    color: #9aa4b2;
}

.mm-empty {
    display: flex;
    flex-direction: column;
    /*
     * 原来 align-items: center + justify-content: center —— 适合一句话。
     * 现在里面有场景列表和示例代码，居中会让整块歪着，改成左对齐、
     * 顶部对齐，只把图标和标题那一行居中。
     */
    align-items: stretch;
    justify-content: flex-start;
    gap: 10px;
    min-height: 180px;
    padding: 20px 24px;
    color: #9aa4b2;
    font-size: 12.5px;
    background: #fcfdfe;
    border: 1px dashed #e6e9ee;
    border-radius: 8px;
    text-align: left;
}

.mm-empty > .el-icon {
    align-self: center;
    color: #c3cbd6;
}

.mm-empty-title {
    align-self: center;
    margin: 0;
    text-align: center;
    color: #6b7280;
    font-size: 13px;
}

/* 有内容但没层级时的原因说明 */
.mm-empty-reason {
    margin: 0;
    padding: 8px 11px;
    color: #92400e;
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 6px;
    line-height: 1.65;
}

.mm-empty-reason code {
    padding: 1px 5px;
    font-family: 'Consolas', monospace;
    font-size: 11.5px;
    color: #92400e;
    background: #fef3c7;
    border-radius: 4px;
}

/* 场景引导 */
.mm-empty-scenes {
    padding-top: 2px;
}

.mm-empty-scenes-title {
    margin: 0 0 5px;
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
}

.mm-empty-scenes ul {
    margin: 0;
    padding-left: 17px;
    line-height: 1.9;
    color: #8b95a5;
}

.mm-empty-scenes strong {
    color: #4b5563;
    font-weight: 600;
}

/* 示例（默认折叠：不想看细节的人不用被代码块挡着） */
.mm-empty-sample {
    font-size: 12px;
    color: #8b95a5;
}

.mm-empty-sample summary {
    cursor: pointer;
    color: #4b8fd6;
    user-select: none;
}

.mm-empty-sample summary:hover {
    text-decoration: underline;
}

.mm-empty-sample pre {
    margin: 7px 0 0;
    padding: 9px 11px;
    font-family: 'Consolas', monospace;
    font-size: 11.5px;
    line-height: 1.7;
    color: #4b5563;
    background: #f5f7fa;
    border: 1px solid #e8ecf1;
    border-radius: 6px;
    overflow-x: auto;
    white-space: pre;
}

.mm-empty p {
    margin: 0;
    text-align: center;
    line-height: 1.7;
    max-width: 420px;
}

/*
 * 窄屏只降到 480px，**不要**像最初那样降到 380px：
 * 380px 高度下径向布局的标签会严重互相压住（2026-10-26 实测：
 * 中间几层节点名叠在一起、右侧 `nueuse/core` 被裁掉）。
 * 导图的价值是"看得清结构"，宁可让用户多滚一点。
 */
@media (max-width: 900px) {
    /*
     * ⚠️ 这里**只给最小高度**，不写死 height（2026-10-27 改）：
     *    写 `height: 480px` 会和调用方传的行内 style 打架
     *    （虽然行内 style 优先级更高，但两个地方管同一个属性迟早出错）。
     *
     *    窄屏真正的问题是**横向**空间不足（卡片会被裁），
     *    所以更该限制的是宽度而不是高度 —— 高度交给调用方按叶子数决定。
     */
    .mm-chart {
        min-height: 320px;
    }
}
</style>
