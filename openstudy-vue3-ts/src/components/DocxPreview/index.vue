<!--
  ============================================================================
  文档预览（2026-10-27）
  ============================================================================

  ## 为什么需要

  用户需求：
    「还要提供一个实时预览功能 比如智能体完成了输出一份word 或者pdf
      可以点击实时预览」

  在此之前，AI 生成文档后只能"下载下来用 Word 打开看" ——
  改一个字就要重新生成、重新下载、重新打开。用户根本没法快速迭代内容。

  ## 技术方案：docx-preview

  把 .docx 直接在浏览器渲染成 HTML（`docx-preview`，0.9MB，只依赖 jszip）。

  为什么不用其他方案：

    · PDF.js（33MB）—— 只能在 PDF 上工作，而我们主产物是 **docx**
      （docx 用户能继续在 Word 里改，PDF 不能）。为了预览再多产一份 PDF 贵且慢。
    · mammoth —— 只输出"语义 HTML"（标题/段落/表格），
      **丢掉所有排版**（字体、字号、颜色、缩进）。预览出来的样子和最终 Word
      不一样，等于没预览。
    · 后端转 HTML —— 项目里的 LibreOffice kit 实测不支持 docx→html
      （`unsupported-format`）。

  docx-preview 的优势是**保真**：字体、字号、表格边框、底纹、分页都能还原，
  和用户最终打开 Word 看到的一致。

  ## 已知限制：公式

  docx-preview **不解析 OMML 公式**（`m:oMath`），会把公式块渲染成空白。
  这是它的已知短板。

  处理方式：不假装没问题，而是明确提示 ——
  组件顶部有一行说明"公式在预览中不显示，下载后用 Word 查看"。
  隐藏这个缺陷会让用户以为公式丢了。

  ## 用法

      <DocxPreview :url="docxUrl" :height="600" />
-->
<template>
    <div class="docx-preview-wrap">
        <!-- 工具条 -->
        <div class="dp-toolbar">
            <span class="dp-title">{{ title || '文档预览' }}</span>
            <span class="dp-meta">
                <span v-if="pageCount">{{ pageCount }} 页</span>
                <span v-if="renderMs">渲染 {{ renderMs }}ms</span>
            </span>
            <div class="dp-actions">
                <!--
                  缩放档位（2026-10-27 加）

                  ⚠️ 为什么需要：窄面板里必须把 A4 整页缩小才能看全版式
                     （1100px 视口下缩到 48%），但缩到这个比例**字看不清**。
                     用户想读某一句时必须能切回原始大小横向滚动查看。

                  两档够用：
                    · 适应宽度 —— 看整体版式（默认）
                    · 实际大小 —— 看具体文字，允许横向滚动
                -->
                <button
                    type="button"
                    class="dp-btn"
                    :disabled="!url"
                    :title="fitMode === 'width' ? '切换到实际大小（可横向滚动）' : '切换到适应宽度'"
                    @click="toggleFitMode"
                >
                    {{ fitMode === 'width' ? '适应宽度' : '实际大小' }}
                </button>
                <button type="button" class="dp-btn" :disabled="!url" @click="rerender" title="重新渲染">
                    刷新
                </button>
                <button type="button" class="dp-btn dp-btn--primary" :disabled="!url" @click="download">
                    下载
                </button>
            </div>
        </div>

        <!-- 公式提示：docx-preview 不解析 OMML，必须明说 -->
        <div v-if="hasFormulaWarning" class="dp-warn">
            预览不显示公式（docx-preview 限制），下载后用 Word / WPS 查看公式正常。
        </div>

        <!-- 渲染区 -->
        <div ref="hostRef" class="dp-body" :style="{ height: heightPx }">
            <div v-if="loading" class="dp-loading">
                <span class="dp-spinner"></span>
                正在渲染文档…
            </div>
            <div v-else-if="err" class="dp-error">{{ err }}</div>
            <div v-else-if="!url" class="dp-empty">还没有生成文档</div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, onMounted, nextTick } from 'vue'

defineOptions({ name: 'DocxPreview' })

const props = withDefaults(
    defineProps<{
        /** docx 的可访问 URL（后端返回的 `url`，形如 /profile/export/...） */
        url?: string
        title?: string
        /** 渲染区高度（px） */
        height?: number
    }>(),
    { url: '', title: '', height: 560 },
)

const emit = defineEmits<{ (e: 'rendered', info: { pages: number; ms: number }): void }>()

const hostRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const err = ref('')
const pageCount = ref(0)
const renderMs = ref(0)

/** 是否显示"公式不显示"的提示 */
const hasFormulaWarning = ref(false)

const heightPx = computed(() => `${props.height}px`)

/**
 * 缩放档位（2026-10-27 加）
 *
 * `width` —— 适应宽度（默认）：整页缩到面板宽，看整体版式
 * `actual` —— 实际大小（100%）：字清楚，允许横向滚动
 *
 * ⚠️ 两档都必要：1100px 视口下文档编排的预览面板只有 407px，
 *    适应宽度得缩到 48% —— 版式看得全，但**字看不清**。
 *    用户想读正文时必须能切回 100%。
 */
const fitMode = ref<'width' | 'actual'>('width')

function toggleFitMode() {
    fitMode.value = fitMode.value === 'width' ? 'actual' : 'width'
    applyFitScale()
}

/* ────────────────────────────────────────────────────────────
 * 渲染
 * ──────────────────────────────────────────────────────────── */

/**
 * 渲染当前 url
 *
 * ⚠️ 每次都要清空 host：docx-preview 是**追加**渲染，
 *    不清空会在同一个容器里堆出好几份文档（改一次多一份）。
 */
async function render() {
    const host = hostRef.value
    if (!host) return

    host.innerHTML = ''
    err.value = ''
    pageCount.value = 0
    renderMs.value = 0
    hasFormulaWarning.value = false

    if (!props.url) return

    loading.value = true
    const t0 = performance.now()

    try {
        // 动态 import：docx-preview 只在需要预览时加载，不拖慢主包
        const mod: any = await import('docx-preview')
        const renderAsync = mod.renderAsync || mod.default?.renderAsync
        if (typeof renderAsync !== 'function') {
            throw new Error('docx-preview 未正确加载')
        }

        const resp = await fetch(props.url, { credentials: 'include' })
        if (!resp.ok) {
            throw new Error(`文档下载失败（HTTP ${resp.status}）`)
        }
        const buf = await resp.arrayBuffer()

        // 粗判是否含公式：docx 是 zip，document.xml 里出现 oMath 即有公式。
        // 直接在二进制里找 ASCII 标记即可（zip 里 xml 是 deflate 压缩的，
        // 但 jszip 会在内存里解开，这里用更简单的方式：解压后找）
        hasFormulaWarning.value = await _mayContainFormula(buf)

        await renderAsync(buf, host, null, {
            className: 'docx',
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: true,
            renderHeaders: true,
            renderFooters: true,
            renderFootnotes: false,
            useBase64URL: true,
        })

        await nextTick()
        renderMs.value = Math.round(performance.now() - t0)
        pageCount.value = host.querySelectorAll('.docx-wrapper > section, .docx-wrapper > .docx').length

        // 页面渲染完立刻按可用宽度缩放（窄面板里必须缩，否则左半边被切掉）
        applyFitScale()

        emit('rendered', { pages: pageCount.value, ms: renderMs.value })
    } catch (e: any) {
        err.value = `预览失败：${e?.message || e}`
    } finally {
        loading.value = false
    }
}

/**
 * 按可用宽度缩放页面（2026-10-27 加）
 *
 * ⚠️ 修的问题：docx-preview 渲染的页面是 **A4 固定宽（21cm ≈ 794px）**。
 *    文档编排页左右分栏后，预览面板在 1100px 视口下只有 407px 宽 ——
 *    页面被切掉左半边（截图里标题只剩「档」字、小节标题全丢），
 *    下方还有横向滚动条。用户看到的是"排版坏了"。
 *
 * 做法：用 CSS transform 把整页等比缩小。
 *   · 先读第一页的真实宽度（docx-preview 输出的是 px）
 *   · 算 scale = 可用宽度 / 页面宽度，上限 1（不放大小文档）
 *   · 把 transform-origin 设成左上，再按缩放后的高度补下方留白
 *     （否则 transform 不改变布局盒，下面会空出一大块或被裁）
 *
 * ⚠️ 为什么用 transform 而不是 zoom：
 *     zoom 是非标准属性，Firefox 长期不支持；transform 全平台一致。
 */
function applyFitScale() {
    const host = hostRef.value
    if (!host) return

    const pages = host.querySelectorAll('.docx-wrapper > section, .docx-wrapper > .docx')
    if (!pages.length) return

    const first = pages[0] as HTMLElement
    const pageW = first.offsetWidth
    if (!pageW) return

    // 可用宽度：扣掉 dp-body 的左右 padding（14*2）
    const avail = host.clientWidth - 28
    // "实际大小"档位强制 1，允许横向滚动
    const scale = fitMode.value === 'actual' ? 1 : Math.min(1, avail / pageW)

    host.style.setProperty('--fit-scale', String(scale))

    for (const p of Array.from(pages) as HTMLElement[]) {
        if (scale >= 0.999) {
            // 不需要缩放：清掉内联样式
            p.style.transform = ''
            p.style.transformOrigin = ''
            p.style.marginBottom = ''
            continue
        }
        p.style.transformOrigin = 'top left'
        p.style.transform = `scale(${scale})`
        /*
         * transform 不改变布局盒 → 页面还是占原始高度，
         * 下面会空出一大块。用负 margin 把空白收掉：
         *
         *     实际视觉高度 = 原高 * scale
         *     需要收掉的 = 原高 * (1 - scale)
         */
        p.style.marginBottom = `${-p.offsetHeight * (1 - scale)}px`
    }
}
/**
 * 探测 docx 里是否含 OMML 公式
 *
 * ⚠️ 用 jszip 解出 document.xml 再找 `<m:oMath`。
 *   直接在原始字节里搜字符串是**不可靠**的：docx 是 zip，
 *   xml 被 deflate 压缩过，明文搜不到。
 */
async function _mayContainFormula(buf: ArrayBuffer): Promise<boolean> {
    try {
        const JSZip = (await import('jszip')).default as any
        const zip = await JSZip.loadAsync(buf)
        const doc = zip.file('word/document.xml')
        if (!doc) return false
        const xml = await doc.async('string')
        return xml.includes('<m:oMath') || xml.includes(':oMath')
    } catch {
        return false
    }
}

function rerender() {
    render()
}

function download() {
    if (!props.url) return
    const a = document.createElement('a')
    a.href = props.url
    // 从 URL 里取文件名（后端生成时已带中文名）
    const name = decodeURIComponent(props.url.split('/').pop() || 'document.docx')
    a.download = name.replace(/^[0-9a-f]{12}_/, '')
    document.body.appendChild(a)
    a.click()
    a.remove()
}

watch(() => props.url, () => { render() }, { immediate: false })

// 首次挂载：等容器真正在 DOM 里再渲染
nextTick(() => { if (props.url) render() })

/**
 * 面板宽度变化时重算缩放
 *
 * 典型场景：文档编排页左右分栏，用户拖动窗口宽度、
 * 或从宽屏切到半屏 —— 缩放比例必须跟着变，否则又会切掉一半。
 */
let ro: ResizeObserver | null = null
onMounted(() => {
    if (typeof ResizeObserver === 'undefined' || !hostRef.value) return
    let lastW = 0
    ro = new ResizeObserver(() => {
        const w = hostRef.value?.clientWidth || 0
        if (w === lastW || w < 40) return
        lastW = w
        applyFitScale()
    })
    ro.observe(hostRef.value)
})

onBeforeUnmount(() => {
    ro?.disconnect()
    ro = null
    if (hostRef.value) hostRef.value.innerHTML = ''
})

defineExpose({ render })
</script>

<style scoped>
.docx-preview-wrap {
    display: flex;
    flex-direction: column;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    overflow: hidden;
    background: #fff;
}

.dp-toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid #eef0f3;
    background: #fafbfc;
}

.dp-title {
    font-size: 13px;
    font-weight: 600;
    color: #1f2329;
}

.dp-meta {
    display: flex;
    gap: 10px;
    font-size: 11.5px;
    color: #8b95a5;
}

.dp-actions {
    margin-left: auto;
    display: flex;
    gap: 6px;
}

.dp-btn {
    padding: 3px 10px;
    font-size: 12px;
    color: #4b5563;
    background: #fff;
    border: 1px solid #d8dde5;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.12s;
}

.dp-btn:hover:not(:disabled) {
    border-color: #9aa4b2;
    background: #f5f7fa;
}

.dp-btn--primary {
    color: #fff;
    background: #409eff;
    border-color: #409eff;
}

.dp-btn--primary:hover:not(:disabled) {
    background: #1d7fe0;
    border-color: #1d7fe0;
}

.dp-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.dp-warn {
    padding: 5px 12px;
    font-size: 11.5px;
    color: #92400e;
    background: #fffbeb;
    border-bottom: 1px solid #fde68a;
}

.dp-body {
    position: relative;
    overflow: auto;
    background: #f0f2f5;
    padding: 14px;
    /*
     * 缩放由 JS 算好写进 CSS 变量（见 `applyFitScale`）
     *
     * ⚠️ 不能用 `overflow:auto` 凑合（2026-10-27 实测）：
     *    docx-preview 渲染出的是 **A4 固定宽（21cm ≈ 794px）** 的页面。
     *    在 1100px 视口下文档编排的预览面板只有 407px 宽 ——
     *    实测截图里页面被切掉左半边（标题只剩「档」字、小节标题全丢），
     *    底部还挂一条横向滚动条，用户以为"排版坏了"。
     *
     *    正确处理是按可用宽度整体缩小，让用户一眼看到完整版式。
     */
    --fit-scale: 1;
}

.dp-loading,
.dp-error,
.dp-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 100%;
    font-size: 13px;
    color: #8b95a5;
}

.dp-error {
    color: #b91c1c;
}

.dp-spinner {
    width: 14px;
    height: 14px;
    border: 2px solid #cfe3fb;
    border-top-color: #409eff;
    border-radius: 50%;
    animation: dp-spin 0.8s linear infinite;
}

@keyframes dp-spin {
    to { transform: rotate(360deg); }
}

/*
 * docx-preview 输出的页面容器样式微调
 * ⚠️ 必须 :deep()：这段 DOM 是渲染时动态插进来的，拿不到 scoped 属性
 */
.dp-body :deep(.docx-wrapper) {
    background: transparent;
    padding: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
}

.dp-body :deep(.docx-wrapper > section.docx) {
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
    margin: 0;
    background: #fff;
}
</style>
