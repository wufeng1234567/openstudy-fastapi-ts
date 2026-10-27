<!--
  ============================================================================
  文档编排页面（2026-10-27）
  ============================================================================

  ## 为什么需要这个页面

  用户需求：
    「加入一个独立的"文档编排"页面 让用户可以自己手动修改或者ai修改
      给不喜欢对话的用户提供更好的操作空间」

  聊天里生成文档的问题：
    · 想改一个错别字，要说一整句「把第三段那个字改成 X」
    · 说三遍模型可能给三个不同的版本，越改越乱
    · 看不到"当前内容到底是什么"，只能反复下载打开

  这个页面把「内容」直接摆在用户面前：
    左边写 / 改，右边随时看排版效果，满意了再下载。

  ## 布局

      ┌──────────────────────────────────────────────────────┐
      │ 标题 [____] 主题 [▾]  ☐封面 ☐目录   [AI 优化] [下载] │
      ├───────────────────────┬──────────────────────────────┤
      │ Markdown 源码          │ 实时预览（docx-preview）     │
      │                       │                              │
      │ # 标题                 │ ┌──────────────────┐        │
      │ 正文含 $公式$          │ │  排版好的页面     │        │
      │ | 表 | 格 |            │ └──────────────────┘        │
      └───────────────────────┴──────────────────────────────┘

  ## 关键交互设计

  ① **预览是"按需渲染"而不是每次敲键都渲**
     渲染一次 docx-preview 要 200~600ms。每次 input 都渲会让打字卡顿。
     所以：输入停止 900ms 后才自动渲染（防抖），另给一个手动「刷新预览」。

  ② **AI 优化是"可撤销"的**
     AI 改完直接覆盖用户的手写内容会让人不敢点。所以保留上一版，
     顶部出现「撤销 AI 修改」—— 用户敢试了，功能才用得上。

  ③ **主题切换立刻重渲**
     主题只影响排版，不影响内容，所以切换后马上重渲，用户能直观对比。

  ④ **字数与块数实时显示**
     用户不知道"多少字会排成几页"，给个粗略提示（约 N 字/页）。
-->
<template>
    <div class="doc-compose-page">
        <!-- ========== 顶栏 ========== -->
        <div class="dc-topbar">
            <div class="dc-field">
                <label>标题</label>
                <el-input v-model="title" size="small" placeholder="文档标题（也会用作文件名）"
                    class="dc-title-input" @input="schedulePreview" />
            </div>

            <div class="dc-field">
                <label>主题</label>
                <el-select v-model="theme" size="small" class="dc-theme-select" @change="onThemeChange">
                    <el-option v-for="t in themes" :key="t.value" :value="t.value" :label="t.label" />
                </el-select>
            </div>

            <el-checkbox v-model="cover" size="small" @change="renderNow">封面</el-checkbox>
            <el-checkbox v-model="toc" size="small" @change="renderNow">目录</el-checkbox>

            <div class="dc-spacer" />

            <!-- AI 操作 -->
            <el-button size="small" :loading="polishing" :disabled="!markdown.trim()" @click="onPolish">
                <span class="dc-ai-icon">✦</span> AI 优化
            </el-button>

            <!-- 下载 -->
            <el-button size="small" type="primary" :loading="downloading" :disabled="!markdown.trim()"
                @click="onDownload">
                下载 Word
            </el-button>
            <el-button size="small" :loading="downloading" :disabled="!markdown.trim()" @click="onDownloadPdf">
                下载 PDF
            </el-button>
        </div>

        <!-- AI 撤销条 -->
        <div v-if="snapshotBeforeAi" class="dc-undo-bar">
            <span class="dc-undo-text">已应用 AI 优化。原内容已暂存。</span>
            <button type="button" class="dc-undo-btn" @click="undoAi">撤销 AI 修改</button>
        </div>

        <!-- ========== 主体：左编辑 / 右预览 ========== -->
        <div class="dc-main">
            <!-- 左：编辑器 -->
            <div class="dc-pane dc-pane--edit">
                <div class="dc-pane-head">
                    <span>内容（支持 Markdown）</span>
                    <span class="dc-stats">{{ charCount }} 字 · 约 {{ estPages }} 页</span>
                </div>

                <!-- 快捷插入工具栏 -->
                <div class="dc-quickbar">
                    <button v-for="q in QUICK_INSERTS" :key="q.label" type="button" class="dc-quick-btn"
                        :title="q.tip" @click="insertSnippet(q.text)">
                        {{ q.label }}
                    </button>
                </div>

                <textarea v-model="markdown" class="dc-editor" spellcheck="false"
                    placeholder="在这里写内容，或把已有文字粘进来。

支持 Markdown：
  # 一级标题     ## 二级标题
  - 无序列表     1. 有序列表
  | 表 | 格 |     |---|---|
  $行内公式$      $$独立公式$$
  > 引用块        ![图注](图片地址)"
                    @input="schedulePreview"></textarea>
            </div>

            <!-- 右：预览 -->
            <div class="dc-pane dc-pane--preview">
                <DocxPreview :url="previewUrl" :title="title || '预览'" :height="previewHeight"
                    @rendered="onPreviewRendered" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DocxPreview from '@/components/DocxPreview/index.vue'
import {
    renderDocCompose,
    previewDocCompose,
    polishDocCompose,
    getDocComposeTemplates,
    type DocComposeTheme,
} from '@/api/ai/docCompose'

defineOptions({ name: 'DocCompose' })

/* ────────────────────────────────────────────────────────────
 * 状态
 * ──────────────────────────────────────────────────────────── */

const title = ref('未命名文档')
const markdown = ref(DEFAULT_MARKDOWN)
const theme = ref('clean')
const cover = ref(false)
const toc = ref(false)

const themes = ref<DocComposeTheme[]>([
    { value: 'clean', label: '简洁现代' },
    { value: 'academic', label: '学术论文' },
    { value: 'report', label: '正式报告' },
])

/** 预览文件 URL（后端返回的 /profile/export/...） */
const previewUrl = ref('')
const previewHeight = ref(560)
const polishing = ref(false)
const downloading = ref(false)
const previewInfo = ref<{ pages: number; ms: number } | null>(null)

/** AI 修改前的快照（用于撤销） */
const snapshotBeforeAi = ref('')

let previewTimer: ReturnType<typeof setTimeout> | null = null

/* ────────────────────────────────────────────────────────────
 * 计算属性
 * ──────────────────────────────────────────────────────────── */

const charCount = computed(() => markdown.value.length)

/**
 * 预估页数
 *
 * 粗略按每页 900 字（含标题、列表占位）估算。
 * 不精确是故意的：给一个量级提示就够了，精确页数要渲染后才知道。
 */
const estPages = computed(() => Math.max(1, Math.ceil(charCount.value / 900)))

/* ────────────────────────────────────────────────────────────
 * 快捷插入
 * ──────────────────────────────────────────────────────────── */

const QUICK_INSERTS = [
    { label: 'H1', text: '\n# 标题\n', tip: '一级标题' },
    { label: 'H2', text: '\n## 标题\n', tip: '二级标题' },
    { label: 'H3', text: '\n### 标题\n', tip: '三级标题' },
    { label: '正文', text: '\n正文段落。\n', tip: '普通段落' },
    { label: '列表', text: '\n- 第一项\n- 第二项\n', tip: '无序列表' },
    { label: '有序', text: '\n1. 第一项\n2. 第二项\n', tip: '有序列表' },
    { label: '表格', text: '\n| 列一 | 列二 |\n|------|------|\n| 内容 | 内容 |\n', tip: '插入表格' },
    { label: '公式', text: '\n$$E = mc^2$$\n', tip: '独立公式块' },
    { label: '行内公式', text: '$x^2$', tip: '行内公式' },
    { label: '引用', text: '\n> 引用内容\n', tip: '引用块' },
    { label: '提示', text: '\n> [!WARNING]\n> 需要注意的地方\n', tip: '提示框' },
    { label: '图片', text: '\n![图 1  说明](/profile/图片路径.png)\n', tip: '插入图片' },
    { label: '分隔线', text: '\n---\n', tip: '分隔线' },
]

function insertSnippet(text: string) {
    markdown.value += text
    schedulePreview()
}

/* ────────────────────────────────────────────────────────────
 * 预览
 * ──────────────────────────────────────────────────────────── */

/**
 * 防抖预览
 *
 * ⚠️ 为什么是 900ms 而不是即时：
 *    docx 渲染一次要 200~600ms（含后端生成 + docx-preview 解析），
 *    每次敲键都渲会让输入明显卡顿。停手 900ms 再渲是体感与实时的平衡点。
 */
function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => { renderNow() }, 900)
}

async function renderNow() {
    if (!markdown.value.trim()) {
        previewUrl.value = ''
        return
    }
    try {
        const res: any = await previewDocCompose({
            markdown: markdown.value,
            title: title.value || '未命名文档',
            theme: theme.value,
            cover: cover.value,
            toc: toc.value,
        })
        if (res?.code === 200 && res.data?.url) {
            // 加时间戳破缓存：同一 URL 内容变了但路径可能复用
            previewUrl.value = withCacheBust(res.data.url)
        } else if (res?.code !== 200) {
            ElMessage.error(res?.msg || '预览生成失败')
        }
    } catch (e: any) {
        ElMessage.error('预览生成失败：' + (e?.message || e))
    }
}

/**
 * 给 URL 加时间戳
 *
 * ⚠️ 后端每次生成都用 uuid 前缀，理论上不会重复；
 *    但 docx-preview 内部会缓存 ArrayBuffer（按 URL），
 *    保险起见还是加一个 query，避免"改了内容预览没变"。
 */
function withCacheBust(url: string): string {
    return url + (url.includes('?') ? '&' : '?') + 't=' + Date.now()
}

function onThemeChange() {
    renderNow()
}

function onPreviewRendered(info: { pages: number; ms: number }) {
    previewInfo.value = info
}

/* ────────────────────────────────────────────────────────────
 * AI 优化
 * ──────────────────────────────────────────────────────────── */

async function onPolish() {
    if (!markdown.value.trim()) return

    let instruction = '整理这段内容的排版结构'
    try {
        const r = await ElMessageBox.prompt(
            '想让 AI 怎么整理？（只调整结构，不会改写内容与数字）',
            'AI 优化',
            {
                inputValue: instruction,
                confirmButtonText: '开始优化',
                cancelButtonText: '取消',
                inputPlaceholder: '例如：把并列信息整理成列表 / 给每一节补上小标题',
            },
        )
        instruction = r.value || instruction
    } catch {
        return // 用户取消
    }

    polishing.value = true
    // 先存快照：AI 覆盖用户手写内容必须可撤销，否则用户不敢用
    snapshotBeforeAi.value = markdown.value

    try {
        const res: any = await polishDocCompose({
            markdown: markdown.value,
            instruction,
            theme: theme.value,
        })
        if (res?.code === 200 && res.data?.markdown) {
            markdown.value = res.data.markdown
            ElMessage.success('已优化排版结构')
            renderNow()
        } else {
            snapshotBeforeAi.value = ''
            ElMessage.error(res?.msg || 'AI 优化失败')
        }
    } catch (e: any) {
        snapshotBeforeAi.value = ''
        ElMessage.error('AI 优化失败：' + (e?.message || e))
    } finally {
        polishing.value = false
    }
}

function undoAi() {
    if (!snapshotBeforeAi.value) return
    markdown.value = snapshotBeforeAi.value
    snapshotBeforeAi.value = ''
    ElMessage.info('已恢复到 AI 优化前的内容')
    renderNow()
}

/* ────────────────────────────────────────────────────────────
 * 下载
 * ──────────────────────────────────────────────────────────── */

async function doDownload(wantPdf: boolean) {
    if (!markdown.value.trim()) {
        ElMessage.warning('内容为空')
        return
    }
    downloading.value = true
    try {
        const res: any = await renderDocCompose({
            markdown: markdown.value,
            title: title.value || '未命名文档',
            theme: theme.value,
            cover: cover.value,
            toc: toc.value,
            wantPdf,
        })
        if (res?.code !== 200) {
            ElMessage.error(res?.msg || '生成失败')
            return
        }

        const data = res.data || {}
        const target = wantPdf ? data.files?.find((f: any) => f.type === 'pdf') : data.files?.find((f: any) => f.type === 'docx')
        if (!target) {
            ElMessage.error(wantPdf ? (data.pdfError || 'PDF 生成失败') : '文件生成失败')
            return
        }

        triggerDownload(target.url, target.name)
        ElMessage.success('已开始下载')
    } catch (e: any) {
        ElMessage.error('生成失败：' + (e?.message || e))
    } finally {
        downloading.value = false
    }
}

function onDownload() {
    doDownload(false)
}

function onDownloadPdf() {
    doDownload(true)
}

function triggerDownload(url: string, name: string) {
    const a = document.createElement('a')
    a.href = url
    a.download = name || 'document'
    document.body.appendChild(a)
    a.click()
    a.remove()
}

/* ────────────────────────────────────────────────────────────
 * 生命周期
 * ──────────────────────────────────────────────────────────── */

onMounted(async () => {
    // 预览区高度跟随视口：编辑器与预览要等高才好用
    previewHeight.value = Math.max(420, window.innerHeight - 260)

    try {
        const res: any = await getDocComposeTemplates()
        if (res?.code === 200 && Array.isArray(res.data?.items) && res.data.items.length) {
            themes.value = res.data.items
        }
    } catch {
        /* 主题列表拿不到就用内置默认，不阻塞页面 */
    }

    // 进页面先渲一次，让用户看到"这里能出东西"
    renderNow()
})

onBeforeUnmount(() => {
    if (previewTimer) clearTimeout(previewTimer)
})

/* ────────────────────────────────────────────────────────────
 * 初始示例内容
 * ──────────────────────────────────────────────────────────── */

const DEFAULT_MARKDOWN = `# 文档标题

这里是正文。可以直接在左边修改，右边会实时显示排版效果。

## 一、这一段演示什么

- 支持 **Markdown** 语法
- 支持列表、表格、公式、图片
- 主题可以在顶部切换

## 二、示例表格

| 项目 | 说明 | 状态 |
|------|------|------|
| 排版 | 自动生成标题层级与目录 | 已完成 |
| 公式 | LaTeX 转成 Word 原生公式 | 已完成 |
| 图片 | 等比缩放、自动加图注 | 已完成 |

## 三、示例公式

行内公式：质能方程 $E = mc^2$，勾股定理 $a^2 + b^2 = c^2$。

独立公式：

$$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$$

$$\\int_{0}^{1} x^2 \\, dx = \\frac{1}{3}$$

> 提示：需要目录和封面时，勾选顶部对应选项。

---

写完后点右上角「下载 Word」或「下载 PDF」即可带走。
`
</script>

<style scoped>
.doc-compose-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: #f5f7fa;
}

/* ========== 顶栏 ========== */
.dc-topbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px;
    background: #fff;
    border-bottom: 1px solid #e8ecf1;
    flex-wrap: wrap;
}

.dc-field {
    display: flex;
    align-items: center;
    gap: 6px;
}

.dc-field label {
    font-size: 12px;
    color: #6b7280;
    white-space: nowrap;
}

.dc-title-input {
    width: 200px;
}

.dc-theme-select {
    width: 116px;
}

.dc-spacer {
    flex: 1 1 auto;
}

.dc-ai-icon {
    color: #8b5cf6;
}

/* AI 撤销条 */
.dc-undo-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 14px;
    background: #f5f3ff;
    border-bottom: 1px solid #ddd6fe;
}

.dc-undo-text {
    font-size: 12px;
    color: #5b21b6;
}

.dc-undo-btn {
    padding: 2px 9px;
    font-size: 11.5px;
    color: #5b21b6;
    background: #fff;
    border: 1px solid #c4b5fd;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.12s;
}

.dc-undo-btn:hover {
    background: #ede9fe;
}

/* ========== 主体 ========== */
.dc-main {
    flex: 1 1 auto;
    display: grid;
    grid-template-columns: minmax(340px, 1fr) minmax(400px, 1.15fr);
    gap: 12px;
    padding: 12px;
    min-height: 0;
}

.dc-pane {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: #fff;
    border: 1px solid #e8ecf1;
    border-radius: 10px;
    overflow: hidden;
}

.dc-pane-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid #eef0f3;
    font-size: 12.5px;
    font-weight: 600;
    color: #1f2329;
    background: #fafbfc;
}

.dc-stats {
    font-weight: 400;
    font-size: 11.5px;
    color: #8b95a5;
}

/* 快捷插入 */
.dc-quickbar {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 7px 10px;
    border-bottom: 1px solid #f0f2f5;
    background: #fcfdfe;
}

.dc-quick-btn {
    padding: 2px 7px;
    font-size: 11px;
    color: #4b5563;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.12s;
}

.dc-quick-btn:hover {
    color: #409eff;
    border-color: #bfdbfe;
    background: #f2f8ff;
}

/* 编辑器 */
.dc-editor {
    flex: 1 1 auto;
    width: 100%;
    min-height: 0;
    padding: 12px 14px;
    border: none;
    outline: none;
    resize: none;
    font-family: 'Consolas', 'Microsoft YaHei', monospace;
    font-size: 13px;
    line-height: 1.75;
    color: #1f2329;
    background: #fff;
    tab-size: 2;
}

.dc-editor::placeholder {
    color: #b6bdc9;
    font-family: 'Microsoft YaHei', sans-serif;
}

/* 预览面板：让 DocxPreview 填满 */
.dc-pane--preview {
    overflow: hidden;
}

.dc-pane--preview :deep(.docx-preview-wrap) {
    flex: 1 1 auto;
    min-height: 0;
    border: none;
    border-radius: 0;
}

/* 窄屏：上下堆叠 */
@media (max-width: 1080px) {
    .dc-main {
        grid-template-columns: 1fr;
        grid-template-rows: minmax(260px, 1fr) minmax(320px, 1fr);
    }
}
</style>
