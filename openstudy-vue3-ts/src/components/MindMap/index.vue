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
                <el-radio-group v-model="layoutMode" size="small">
                    <el-radio-button value="radial">径向</el-radio-button>
                    <el-radio-button value="tree">树形</el-radio-button>
                </el-radio-group>
                <el-button size="small" text @click="fitView">
                    <el-icon><FullScreen /></el-icon> 自适应
                </el-button>
            </div>
        </div>

        <!-- 空态：说人话，不画空图 -->
        <div v-if="!hasTree" class="mm-empty">
            <el-icon :size="22"><Share /></el-icon>
            <p>{{ emptyText }}</p>
        </div>

        <div v-show="hasTree" ref="chartRef" class="mm-chart"></div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { FullScreen, Share } from '@element-plus/icons-vue'
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
        /** 初始布局 */
        defaultLayout?: 'radial' | 'tree'
    }>(),
    {
        markdown: '',
        treeData: null,
        title: '思维导图',
        emptyText: '这段内容里还没有可提取的层级（标题或列表），写几条要点就会出现导图。',
        defaultLayout: 'radial',
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
const layoutMode = ref<'radial' | 'tree'>(props.defaultLayout)
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

/** 节点数（用于 tooltip 里报告规模） */
const nodeCount = computed(() => {
    const count = (n: TreeNode | undefined): number =>
        !n ? 0 : 1 + (n.children || []).reduce((s, c) => s + count(c), 0)
    return count(treeData.value ?? undefined)
})

/* ────────────────────────────────────────────────────────────
 * 渲染
 * ──────────────────────────────────────────────────────────── */

/**
 * 节点配色：按**深度**分配
 *
 * 用一组低饱和度的色，避免导图变成彩虹（那样反而看不出结构）。
 * 一级分支用区分度最高的几个色，二三级统一用浅灰蓝。
 */
const DEPTH_COLORS = ['#4c8fd6', '#e8833a', '#3fa06a', '#9b6fd6', '#e5a33a', '#4ca8a0']
function branchColor(depth: number): string {
    if (depth <= 1) return DEPTH_COLORS[0]
    return DEPTH_COLORS[(depth - 1) % DEPTH_COLORS.length]
}

function buildOption() {
    const data = treeData.value
    if (!data) return {}

    // 递归给节点打上颜色/大小（echarts tree 支持在 data 上挂 itemStyle）
    const decorate = (node: TreeNode, depth: number): any => {
        const isRoot = depth === 0
        const isBranch = depth <= 1
        return {
            name: node.name,
            // 根节点显示大一点，叶子小一点
            symbolSize: isRoot ? 14 : isBranch ? 9 : 6,
            itemStyle: {
                color: isRoot ? '#2f3946' : branchColor(depth),
            },
            label: {
                show: true,
                // 叶子节点名可能长，缩到 12px；分支名更重要，给 13px
                fontSize: isBranch ? 13 : 12,
                color: isRoot ? '#2f3946' : '#3a4452',
                fontWeight: isRoot || isBranch ? 500 : 400,
                // 叶子节点截更狠（14 字）：它们是标签重叠的主要来源
                formatter: (p: any) => clipName(p.name, isBranch ? 20 : 14),
            },
            children: (node.children || []).map((c) => decorate(c, depth + 1)),
        }
    }

    const decorated = decorate(data, 0)
    const isRadial = layoutMode.value === 'radial'

    // 节点多时只展开前几层；节点少就全展开（一眼看全更爽）
    const manyNodes = nodeCount.value > MANY_NODES_THRESHOLD
    const initDepth = manyNodes ? EXPAND_DEPTH_LIMIT : -1

    return {
        tooltip: {
            trigger: 'item',
            triggerOn: 'mousemove',
            formatter: (p: any) => `${p.name}`,
        },
        series: [
            {
                type: 'tree',
                data: [decorated],
                // 径向布局是思维导图形态；tree 是传统组织架构形态
                layout: isRadial ? 'radial' : 'orthogonal',
                orient: 'LR',
                // 根节点放中间（径向布局）
                ...(isRadial ? {} : { top: '4%', bottom: '4%', left: '6%', right: '32%' }),
                symbol: 'circle',
                // 连线：曲线更柔，直线更"教科书"；导图用曲线
                edgeShape: 'curve',
                edgeForkPosition: '50%',
                // ⚠️ 节点多时必须限制初始深度（见 EXPAND_DEPTH_LIMIT 的说明）
                initialTreeDepth: initDepth,
                // 允许收起/展开：用户想深看时点节点即可
                roam: true,
                expandAndCollapse: true,
                animationDuration: 420,
                animationDurationUpdate: 320,
                lineStyle: {
                    color: '#d6dbe3',
                    width: 1.2,
                    curveness: isRadial ? 0.5 : 0,
                },
                label: {
                    position: isRadial ? 'outside' : 'left',
                    verticalAlign: 'middle',
                    align: isRadial ? 'center' : 'right',
                    distance: 6,
                },
                leaves: {
                    label: {
                        position: isRadial ? 'outside' : 'right',
                        align: isRadial ? 'center' : 'left',
                    },
                },
            },
        ],
    }
}

function render() {
    if (!hasTree.value) {
        chart?.clear()
        return
    }
    nextTick(() => {
        if (!chartRef.value) return
        if (!chart) {
            chart = echarts.init(chartRef.value)
        }
        chart.setOption(buildOption(), true)
        chart.resize()
    })
}

/** 自适应：把整张图缩放到可见范围内 */
function fitView() {
    if (!chart) return
    // echarts tree 没有直接的 "fit" API，重设 option + resize 即可回到初始比例
    chart.setOption(buildOption(), true)
    chart.resize()
}

function handleResize() {
    chart?.resize()
}

watch(
    () => [props.markdown, props.title, props.treeData],
    () => render(),
)
watch(layoutMode, () => render())

onMounted(() => {
    render()
    window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    chart?.dispose()
    chart = null
})

defineExpose({ fitView, nodeCount })
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
     * 高度不用 460px 而是 560px：
     * 径向布局的标签是沿圆周向外排的，垂直空间不够时上下两侧的标签会互相压住
     * （实测 460px 时中间几层节点名叠在一起）。560px 是"能看清且不占满屏"的折中。
     */
    height: 560px;
    background: #fcfdfe;
    border: 1px solid #eef0f3;
    border-radius: 8px;
}

.mm-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 180px;
    padding: 24px;
    color: #9aa4b2;
    font-size: 12.5px;
    background: #fcfdfe;
    border: 1px dashed #e6e9ee;
    border-radius: 8px;
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
    .mm-chart {
        height: 480px;
    }
}
</style>
