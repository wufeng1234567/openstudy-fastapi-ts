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
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'

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
        emit('rendered', { pages: pageCount.value, ms: renderMs.value })
    } catch (e: any) {
        err.value = `预览失败：${e?.message || e}`
    } finally {
        loading.value = false
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

onBeforeUnmount(() => {
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
