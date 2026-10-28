<!--
  ============================================================================
  思维导图（2026-10-28 v4：echarts → mind-elixir）
  ============================================================================

  ## 为什么换渲染引擎

  旧实现用 echarts tree series 画卡片，实测在 40+ 节点的压力场景下
  内嵌视图与放大弹窗都会出现卡片互相压住（重叠对 30+）、叶子被容器裁掉
  （详见 _scratch_v3/e2e/mindmap_geometry_baseline.md）。echarts tree 的
  布局把坐标归一化到容器宽高，容器不够大就直接把卡片叠起来，没有出路。

  现改用 mind-elixir@5.8.3：DOM 布局（.me-tpc 真实卡片），按内容撑开、
  间距可调，46 节点两种尺寸实测 0 重叠，拖拽/缩放/导出开箱即用。
  渲染引擎：mind-elixir v5.8.3（MIT），https://github.com/SSShooter/mind-elixir-core

  ## 对调用方的兼容承诺

  · props：markdown / treeData / title / emptyText / defaultLayout / height 不变
  · defineExpose：fitView / nodeCount / openZoom / exportPng 不变
  · 空态 UI 与文案不变
  · 工具栏按钮文案「自适应 / 还原 / 放大 / 导出」不变
    （布局切换从「径向/树形」改为「双向/右向」—— mind-elixir 只有这两种方向）
  ============================================================================
-->
<template>
    <div class="mindmap-wrap">
        <div class="mindmap-toolbar">
            <span class="mm-title">{{ title }}</span>
            <div class="mm-actions">
                <!-- 布局切换：双向（根居中左右分布）/ 右向（根在左，向右生长） -->
                <el-radio-group v-model="layoutMode" size="small" @change="onLayoutChange">
                    <el-radio-button value="bidirectional">双向</el-radio-button>
                    <el-radio-button value="right">右向</el-radio-button>
                </el-radio-group>
                <el-button size="small" text @click="zoomStep(-0.2)">
                    <el-icon><Minus /></el-icon>
                </el-button>
                <el-button size="small" text @click="zoomStep(0.2)">
                    <el-icon><Plus /></el-icon>
                </el-button>
                <el-button size="small" text @click="fitView">
                    <el-icon><FullScreen /></el-icon> 自适应
                </el-button>
                <!-- 一键还原：清掉用户拖动/缩放的结果，回到初始视图 -->
                <el-button size="small" text @click="resetView">
                    <el-icon><RefreshLeft /></el-icon> 还原
                </el-button>
                <!-- 一键放大：独立实例的整屏弹窗，随时可关 -->
                <el-button size="small" text @click="openZoom">
                    <el-icon><ZoomIn /></el-icon> 放大
                </el-button>
                <el-button size="small" text :disabled="!hasTree" @click="exportPng">
                    <el-icon><Download /></el-icon> 导出
                </el-button>
            </div>
        </div>

        <!-- 空态：保留原有的场景引导与最小示例 -->
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

        <!-- mind-elixir 渲染容器（真实 DOM 卡片，非 canvas） -->
        <div v-show="hasTree" ref="chartRef" class="mm-chart" :style="{ height: height + 'px' }"
            @wheel.prevent.stop="onWheelZoom"></div>
    </div>

    <!-- 放大查看弹窗：独立 mind-elixir 实例，关闭时 dispose，防泄漏 -->
    <el-dialog v-model="zoomVisible" :title="title" width="92%" top="3vh" append-to-body
        class="mm-zoom-dialog" destroy-on-close @closed="disposeZoom">
        <div ref="zoomChartRef" class="mm-chart mm-chart-zoom" @wheel.prevent.stop="onWheelZoom"></div>
        <template #footer>
            <div class="mm-zoom-foot">
                <span class="mm-zoom-hint">可拖动平移、滚轮缩放；导出会保留你调整后的样子</span>
                <div>
                    <el-button size="small" @click="zoomStep(-0.2, 'zoom')">－</el-button>
                    <el-button size="small" @click="zoomStep(0.2, 'zoom')">＋</el-button>
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
import { FullScreen, Share, ZoomIn, Download, RefreshLeft, Minus, Plus } from '@element-plus/icons-vue'
import MindElixir from 'mind-elixir'
import type { MindElixirInstance } from 'mind-elixir'
import 'mind-elixir/style.css'
import {
    parseMarkdownToTree,
    toMindElixirData,
    countMindNodes,
    type TreeNode,
} from '@/utils/mindmapData'

defineOptions({ name: 'MindMap' })

const props = withDefaults(
    defineProps<{
        /** Markdown 源文（标题 / 列表 / 缩进都能识别） */
        markdown?: string
        /** 直接传入现成的树（优先于 `markdown`），用于资料结构树等后端已解析场景 */
        treeData?: { name: string; children?: any[] } | null
        /** 根节点名（通常传笔记标题） */
        title?: string
        /** 没有可解析内容时的提示 */
        emptyText?: string
        /**
         * 初始布局
         *
         * 兼容保留：旧值 'radial' | 'tree' | 'auto' 都映射到「双向」
         * （mind-elixir 只有 SIDE / RIGHT 两种方向，径向已不存在）。
         */
        defaultLayout?: 'radial' | 'tree' | 'auto' | 'bidirectional' | 'right'
        /** 画布高度（px），由调用方按内容规模决定，默认 560 */
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

const chartRef = ref<HTMLDivElement>()

/** 当前布局：双向 = mind-elixir SIDE，右向 = RIGHT */
const layoutMode = ref<'bidirectional' | 'right'>(
    props.defaultLayout === 'right' ? 'right' : 'bidirectional',
)

let mind: MindElixirInstance | null = null

/* ────────────────────────────────────────────────────────────
 * 数据：Markdown / treeData → 树 → mind-elixir 数据
 * ──────────────────────────────────────────────────────────── */

const treeData = computed<TreeNode | null>(() => {
    if (props.treeData) return props.treeData as TreeNode
    return parseMarkdownToTree(props.markdown, props.title)
})
const hasTree = computed(() => treeData.value !== null)
const nodeCount = computed(() => countMindNodes(treeData.value))

/** 有内容但提取不出层级（空态里给出针对性原因说明） */
const hasContentButNoStructure = computed(() => {
    if (hasTree.value) return false
    const md = props.markdown || ''
    const meaningful = md.replace(/\s/g, '')
    if (meaningful.length < 30) return false
    return !/^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s)/m.test(md)
})

/** 浅色卡片主题：根深色、一级分支实心色块、更深层浅底 */
function buildTheme(): any {
    return {
        name: 'OpenStudyLight',
        type: 'light',
        palette: ['#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#ec4899', '#06b6d4', '#ef4444', '#84cc16'],
        cssVar: {
            '--node-gap-x': '36px',
            '--node-gap-y': '14px',
            '--main-gap-x': '72px',
            '--main-gap-y': '52px',
            '--main-color': '#3b82f6',
            '--main-bgcolor': '#eff6ff',
            '--main-bgcolor-transparent': 'rgba(239, 246, 255, 0.85)',
            '--color': '#334155',
            '--bgcolor': '#f8fafc',
            '--selected': '#dbeafe',
            '--accent-color': '#2563eb',
            '--root-color': '#ffffff',
            '--root-bgcolor': '#1f2937',
            '--root-border-color': '#111827',
            '--root-radius': '8px',
            '--main-radius': '6px',
            '--topic-padding': '6px 10px',
            '--panel-color': '#334155',
            '--panel-bgcolor': '#ffffff',
            '--panel-border-color': '#e2e8f0',
            '--map-padding': '40px',
        },
    }
}

/* ────────────────────────────────────────────────────────────
 * 渲染
 * ──────────────────────────────────────────────────────────── */

/**
 * 在指定容器上创建一个 mind-elixir 实例
 *
 * 选项说明：
 *   · editable:true 是节点拖拽的前提；
 *     `before.beginEdit: () => false` 拦掉所有进入文本编辑的入口 ——
 *     拖拽可用、误触不会改文本。
 *   · toolBar/contextMenu/keypress 全关：只读展示，不要编辑器 UI。
 *   · overflowHidden:true 超出容器裁剪（配合 scaleFit 使用）。
 */
function createInstance(el: HTMLElement, data: any) {
    const m = new MindElixir({
        el,
        direction: layoutMode.value === 'right' ? (MindElixir as any).RIGHT : (MindElixir as any).SIDE,
        editable: true,
        before: { beginEdit: () => false },
        toolBar: false,
        contextMenu: false,
        keypress: false,
        overflowHidden: true,
        scaleMin: 0.1,
        scaleMax: 3,
        /*
         * 滚轮缩放由组件自己的 `@wheel.prevent.stop` 处理（见 onWheelZoom）。
         * mind-elixir 的默认 handler 是「普通滚轮平移」，这里传空函数把它顶掉；
         * 传 false 会 fallback 回默认 M（平移），所以必须传函数。
         */
        handleWheel: () => {},
        theme: buildTheme() as any,
    })
    m.init(data)
    return m
}

/** 渲染主视图（尺寸未就绪时交给 ResizeObserver 兜底） */
function render() {
    const data = toMindElixirData(treeData.value)
    if (!data) {
        // 空树：清空并释放实例
        if (mind) {
            mind.destroy?.()
            mind = null
        }
        return
    }
    nextTick(() => {
        const el = chartRef.value
        if (!el) return
        // 容器 0 尺寸时不初始化（el-collapse 展开动画中间态），等 ResizeObserver
        if (el.offsetWidth < 40 || el.offsetHeight < 40) return

        if (mind) {
            mind.refresh(data)
            mind.toCenter()
            mind.scaleFit()
        } else {
            mind = createInstance(el, data)
            mind.toCenter()
            mind.scaleFit()
        }
    })
}

/** 自适应：整图缩放到容器可见范围 */
function fitView() {
    if (!mind) return
    mind.toCenter()
    mind.scaleFit()
}

/**
 * 按步长缩放
 *
 * @param delta  缩放增量（正数放大、负数缩小），绝对值而非倍率 ——
 *               在 0.1 的近景和 2.5 的远景下手感一致
 * @param target 'main' 主视图 / 'zoom' 放大弹窗
 */
function zoomStep(delta: number, target: 'main' | 'zoom' = 'main') {
    const inst = target === 'zoom' ? zoomMind : mind
    const el = target === 'zoom' ? zoomChartRef.value : chartRef.value
    if (!inst) return
    const rect = el?.getBoundingClientRect()
    const center = rect
        ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
        : { x: 0, y: 0 }
    const next = Math.min(3, Math.max(0.1, inst.scaleVal + delta))
    inst.scale(next, center)
}

/**
 * 滚轮自由缩放（以鼠标位置为中心）
 *
 * mind-elixir 默认「普通滚轮 = 平移、Ctrl+滚轮 = 缩放」，用户反馈“没法自由缩放”。
 * 这里在容器上直接接管 wheel：普通滚轮缩放、Shift+滚轮横向平移；`.prevent` 阻止
 * 页面跟着滚，`.stop` 防止事件冒泡到聊天滚动区。
 */
function onWheelZoom(e: WheelEvent) {
    const target = e.currentTarget as HTMLElement | null
    const isZoomView = !!target && target === zoomChartRef.value
    const inst = isZoomView ? zoomMind : mind
    if (!inst) return

    if (e.shiftKey) {
        inst.move(-e.deltaY, 0)
        return
    }
    const rect = target?.getBoundingClientRect()
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
    const next = Math.min(3, Math.max(0.1, inst.scaleVal * factor))
    inst.scale(next, {
        x: e.clientX || (rect ? rect.left + rect.width / 2 : 0),
        y: e.clientY || (rect ? rect.top + rect.height / 2 : 0),
    })
}

/** 还原：重放数据回到初始视图（清掉拖动/缩放痕迹） */
function resetView() {
    const data = toMindElixirData(treeData.value)
    if (!data) return
    if (mind) {
        mind.refresh(data)
        mind.toCenter()
        mind.scaleFit()
    }
    if (zoomMind) {
        zoomMind.refresh(data)
        zoomMind.toCenter()
        zoomMind.scaleFit()
    }
}

/* ────────────────────────────────────────────────────────────
 * 放大查看 + 导出
 * ──────────────────────────────────────────────────────────── */

const zoomVisible = ref(false)
const zoomChartRef = ref<HTMLDivElement>()
let zoomMind: MindElixirInstance | null = null

async function openZoom() {
    if (!hasTree.value) return
    zoomVisible.value = true
    await nextTick()
    // 等一帧：el-dialog 入场动画期间容器尺寸可能不稳
    requestAnimationFrame(async () => {
        const el = zoomChartRef.value
        const data = toMindElixirData(treeData.value)
        if (!el || !data) return
        if (zoomMind) {
            zoomMind.destroy?.()
            zoomMind = null
        }
        zoomMind = createInstance(el, data)
        zoomMind.toCenter()
        zoomMind.scaleFit()
    })
}

function zoomFit() {
    if (!zoomMind) return
    zoomMind.toCenter()
    zoomMind.scaleFit()
}

/** 关闭弹窗后销毁实例（不 dispose 会泄漏 DOM/事件） */
function disposeZoom() {
    if (zoomMind) {
        zoomMind.destroy?.()
        zoomMind = null
    }
}

/**
 * 导出 PNG：mind.exportPng() 返回 Blob，用 <a download> 触发下载。
 * 弹窗打开时优先导出弹窗里的实例（用户看到的那张）。
 */
async function exportPng(useZoom = false) {
    const target = useZoom && zoomMind ? zoomMind : mind
    if (!target) return
    try {
        const blob = await (target as any).exportPng()
        if (!blob) return
        const url = URL.createObjectURL(blob)
        const safe = String(props.title || '思维导图')
            .replace(/[\\/:*?"<>|\r\n\t]+/g, '_')
            .slice(0, 60)
        const a = document.createElement('a')
        a.href = url
        a.download = `${safe}.png`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        setTimeout(() => URL.revokeObjectURL(url), 3000)
    } catch (e) {
        console.warn('[mindmap] 导出失败', e)
    }
}

/* ────────────────────────────────────────────────────────────
 * 生命周期
 * ──────────────────────────────────────────────────────────── */

watch(
    () => [props.markdown, props.title, props.treeData],
    () => render(),
)
watch(layoutMode, () => render())

/** 用户手动切布局：mind-elixir 不支持运行时切方向，重建实例最稳 */
function onLayoutChange() {
    if (mind) {
        mind.destroy?.()
        mind = null
    }
    render()
}

/**
 * 容器尺寸监听：折叠面板展开（0 → 有尺寸）或窗口变化时重排。
 * 防抖 120ms：布局动画期间ResizeObserver 会连发多次，没必要每次都 refresh。
 */
let ro: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
    render()
    if (typeof ResizeObserver !== 'undefined' && chartRef.value) {
        let lastW = 0
        let lastH = 0
        ro = new ResizeObserver((entries) => {
            for (const e of entries) {
                const w = Math.round(e.contentRect.width)
                const h = Math.round(e.contentRect.height)
                if (w === lastW && h === lastH) continue
                lastW = w
                lastH = h
                if (w < 40 || h < 40) continue
                if (resizeTimer) clearTimeout(resizeTimer)
                resizeTimer = setTimeout(() => {
                    if (!mind && chartRef.value) render()
                    else {
                        mind?.refresh()
                        mind?.toCenter()
                        mind?.scaleFit()
                    }
                    zoomMind?.refresh()
                    zoomMind?.scaleFit()
                }, 120)
            }
        })
        ro.observe(chartRef.value)
    }
})

onUnmounted(() => {
    if (resizeTimer) clearTimeout(resizeTimer)
    ro?.disconnect()
    ro = null
    mind?.destroy?.()
    mind = null
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

/*
 * mind-elixir 容器：高度由 props.height 控制（模板行内 style），
 * 宽度自适应父容器；overflowHidden 选项负责裁剪超出部分。
 */
.mm-chart {
    width: 100%;
    background: #fcfdfe;
    border: 1px solid #eef0f3;
    border-radius: 8px;
    overflow: hidden;
}

.mm-chart :deep(.map-container) {
    background: transparent;
}

/* 放大弹窗里的容器：高度按视口算，适配不同屏幕 */
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

/* 示例（默认折叠） */
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

/* 窄屏只给最小高度，高度仍由调用方决定 */
@media (max-width: 900px) {
    .mm-chart {
        min-height: 320px;
    }
}
</style>
