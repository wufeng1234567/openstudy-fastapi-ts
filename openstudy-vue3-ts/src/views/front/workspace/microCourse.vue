<template>
  <div class="micro-page">
    <div class="micro-topbar">
      <el-button text class="back-btn" @click="goWorkspace">
        <el-icon><ArrowLeft /></el-icon>
        我的资料
      </el-button>
      <span v-if="result" class="micro-topbar-name">{{ result.document.fileName }}</span>
    </div>

    <div v-if="loading" class="micro-loading">
      <div class="micro-loading-mark">AI</div>
      <h2>正在围绕这份资料生成教学课件</h2>
      <p>整理章节、提炼要点、生成可直接演示的 HTML…</p>
      <div class="micro-loading-bar"><span></span></div>
    </div>

    <div v-else-if="!result" class="micro-empty">
      <h3>这份资料暂时打不开</h3>
      <p>{{ errorMsg || '它可能已被删除，或者你还没有阅读权限。' }}</p>
      <el-button type="primary" @click="goWorkspace">回到我的资料</el-button>
    </div>

    <template v-else>
      <section class="micro-head">
        <div class="micro-head-main">
          <div class="micro-eyebrow">资料 · 教学微课</div>
          <h1>{{ result.document.fileName }}</h1>
          <div class="micro-meta">
            <span>{{ result.slides }} 页课件</span>
            <span>{{ result.document.subject || '综合' }}</span>
            <span>{{ result.document.wordCount }} 字</span>
            <span class="micro-meta-ai">{{ result.aiGenerated === false ? '资料结构生成' : 'AI 生成' }}</span>
          </div>
          <div v-if="result.changeSummary" class="micro-change-summary">
            本版特点：{{ result.changeSummary }}
          </div>
        </div>
        <div class="micro-actions">
          <el-button :disabled="result.status === 'generating'" @click="editorVisible = true">
            <el-icon><EditPen /></el-icon>
            编辑页面
          </el-button>
          <el-button @click="historyVisible = true">
            <el-icon><Clock /></el-icon>
            历史版本
          </el-button>
          <el-button @click="importVisible = true">
            <el-icon><Document /></el-icon>
            导入 HTML
          </el-button>
          <el-button v-if="result.status !== 'generating'" :loading="generating" @click="generateHtml(true, promptText)">重新生成</el-button>
          <el-dropdown trigger="click" @command="handleExport">
            <el-button type="primary" :loading="exporting" :disabled="result.status === 'generating'">
              <el-icon><Download /></el-icon>
              导出
              <el-icon class="micro-export-caret"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="html">
                  <el-icon><Document /></el-icon>
                  导出 HTML
                </el-dropdown-item>
                <el-dropdown-item command="pptx">
                  <el-icon><Download /></el-icon>
                  导出 PPT
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </section>

      <div class="micro-tip">
        <span class="micro-tip-dot"></span>
        HTML 课件可以直接全屏演示；鼠标滚轮也可以翻页。下载 PPT 时会把当前 HTML 的页面结构转成幻灯片。
      </div>

      <div class="micro-prompt">
        <el-input v-model="promptText" type="textarea" :rows="2" maxlength="500" show-word-limit
          placeholder="告诉 AI 怎么改：例如「加入一张架构图」「把第 3 页改成表格」「减少文字，增加图表」" />
        <el-button type="primary" plain :loading="generating" @click="applyPrompt">按提示词修改</el-button>
      </div>

      <section class="micro-stage">
        <div v-if="generationStage" class="micro-generation-stage">
          <div class="micro-generation-stage__head">
            <div>
              <div class="micro-generation-stage__title">
                <span class="micro-generation-stage__pulse"></span>
                {{ generationStarting ? '正在准备课件页面' : (result.progress?.phase || '正在生成教学页面') }}
              </div>
              <div class="micro-generation-stage__sub">
                AI 正在逐页生成，页面会按顺序出现在下方；全部完成后自动切换为正式课件。
              </div>
            </div>
            <div class="micro-generation-stage__percent">{{ generationProgress }}%</div>
          </div>
          <div class="micro-generation-stage__bar"><span :style="{ width: generationProgress + '%' }"></span></div>
          <TransitionGroup name="micro-page-in" tag="div" class="micro-generation-grid">
            <div v-for="(page, index) in generationPages" :key="index" class="micro-generation-page"
              :class="{ 'is-ready': !!page }">
              <div class="micro-generation-paper">
                <div class="micro-generation-paper__eyebrow">{{ page?.eyebrow || 'AI 课件' }}</div>
                <div v-if="page" class="micro-generation-paper__title">{{ page.title || '未命名页面' }}</div>
                <div v-else class="micro-generation-paper__placeholder">
                  <i></i><i></i><i></i>
                </div>
                <ul v-if="page?.bullets?.length">
                  <li v-for="(bullet, bi) in page.bullets.slice(0, 3)" :key="bi">{{ bullet }}</li>
                </ul>
                <div v-else-if="!page" class="micro-generation-paper__shimmer"></div>
              </div>
              <span class="micro-generation-page__number">第 {{ index + 1 }} 页</span>
            </div>
          </TransitionGroup>
        </div>
        <div v-else ref="stageRef" class="micro-frame-wrap">
          <iframe
            :key="frameKey"
            :srcdoc="result.html"
            class="micro-frame"
            title="教学课件"
            sandbox="allow-scripts allow-same-origin allow-presentation"
          ></iframe>
          <button type="button" class="micro-fullscreen" title="全屏演示" @click="enterFullscreen">
            <el-icon><FullScreen /></el-icon>
            全屏演示
          </button>
        </div>
      </section>

      <section class="micro-foot">
        <div>
          <h3>这份课件从哪里来？</h3>
          <p>系统读取资料原文的章节和正文，生成教学课件；不编造资料里没有的内容。</p>
        </div>
        <span class="micro-foot-meta">共 {{ result.slides }} 页 · {{ result.version ? `第 ${result.version} 版` : '当前版本' }} · 可直接投屏</span>
      </section>

      <el-drawer v-model="historyVisible" title="微课历史版本" size="420px" append-to-body>
        <div v-if="!historyItems.length" class="micro-history-empty">还没有历史版本</div>
        <div v-else class="micro-history-list">
          <div v-for="item in historyItems" :key="item.recordId" class="micro-history-item"
            :class="{ 'is-current': result.recordId === item.recordId }" @click="loadRecord(item)">
            <div class="micro-history-item__main">
              <div class="micro-history-item__title">
                <span>第 {{ item.version }} 版</span>
                <span class="micro-history-item__badge">{{ item.aiGenerated ? 'AI 生成' : '结构生成' }}</span>
              </div>
              <div class="micro-history-item__title-text">{{ item.title }}</div>
              <div v-if="item.changeSummary" class="micro-history-item__change">{{ item.changeSummary }}</div>
              <div class="micro-history-item__meta">{{ formatTime(item.createdAt) }} · {{ item.slides }} 页</div>
            </div>
            <el-icon class="micro-history-item__arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-drawer>

      <MicroCourseSlideEditor v-model="editorVisible" :result="result" @updated="onEditorUpdated" />

      <el-dialog v-model="importVisible" title="导入 HTML 课件" width="760px" append-to-body :close-on-click-modal="false">
        <p class="micro-import-tip">可以粘贴 HTML 代码，或直接选择本地 .html 文件。导入后会保存为一个新的历史版本，不会覆盖原有版本。</p>
        <el-upload :auto-upload="false" :show-file-list="false" accept=".html,.htm,text/html" action="#"
          :before-upload="readHtmlFile">
          <el-button plain>选择 HTML 文件</el-button>
        </el-upload>
        <el-input v-model="importHtml" type="textarea" :rows="14" placeholder="在这里粘贴 HTML 代码..." />
        <template #footer>
          <el-button @click="importVisible = false">取消</el-button>
          <el-button type="primary" :loading="importing" @click="doImport">导入为新版本</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowLeft, ArrowRight, Clock, Document, Download, EditPen, FullScreen } from '@element-plus/icons-vue'
import { saveAs } from 'file-saver'
import MicroCourseSlideEditor from './components/MicroCourseSlideEditor.vue'
import {
  downloadMicroCoursePptx,
  getMicroCourseHtml,
  getMicroCourseRecord,
  importMicroCourseHtml,
  listMicroCourseHistory,
  type MicroCourseHistoryItem,
  type MicroCourseHtmlResult,
  getMicroCourseStatus,
} from '@/api/ai/workspace'

defineOptions({ name: 'MicroCourse' })

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const generating = ref(false)
const exporting = ref(false)
const errorMsg = ref('')
const result = ref<MicroCourseHtmlResult | null>(null)
const frameKey = ref(0)
const stageRef = ref<HTMLElement | null>(null)
const historyVisible = ref(false)
const editorVisible = ref(false)
const historyItems = ref<MicroCourseHistoryItem[]>([])
const promptText = ref('')
const importVisible = ref(false)
const importing = ref(false)
const importHtml = ref('')
const generationPollTimer = ref<number | null>(null)
const generationStage = ref(false)
const generationStarting = ref(false)

const generationProgress = computed(() => {
  if (generationStarting.value) return 8
  const current = Number(result.value?.progress?.current || 0)
  const total = Number(result.value?.progress?.total || 0)
  if (!total) return 8
  return Math.max(8, Math.min(96, Math.round((current / total) * 100)))
})

const generationPages = computed<any[]>(() => {
  const slides = ((result.value?.deck as any)?.slides || []) as any[]
  let parsed = slides
  // 兼容只有 HTML、没有 deck 的导入版本：优先解析每一页的 data-page-* 标记。
  if (!parsed.length && result.value?.html) {
    parsed = []
    const sectionRe = /<section[^>]*class="[^"]*slide[^"]*"[^>]*>([\s\S]*?)<\/section>/gi
    let match: RegExpExecArray | null
    while ((match = sectionRe.exec(result.value.html))) {
      const tag = match[0].slice(0, match[0].indexOf('>') + 1)
      const titleMatch = tag.match(/data-page-title="([^"]*)"/i) || match[1].match(/<h[1-2][^>]*>([\s\S]*?)<\/h[1-2]>/i)
      const plain = (value: string) => value.replace(/<[^>]+>/g, '').trim()
      const bullets = Array.from(match[1].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)).map((m) => plain(m[1]))
      parsed.push({
        title: plain(titleMatch?.[1] || ''),
        bullets,
        eyebrow: 'AI 课件',
      })
    }
  }
  const total = Number(result.value?.progress?.total || parsed.length || 0)
  const length = Math.max(generationStarting.value ? 6 : 0, total, parsed.length, 1)
  return Array.from({ length }, (_, index) => (generationStarting.value ? null : parsed[index] || null))
})

const docId = computed(() => String(route.query.docId || ''))

async function generateHtml(refresh = false, prompt = '') {
  if (!docId.value) {
    loading.value = false
    return
  }
  stopGenerationPoll()
  generating.value = true
  generationStarting.value = true
  generationStage.value = Boolean(refresh || prompt || !result.value)
  errorMsg.value = ''
  try {
    const res: any = await getMicroCourseHtml(docId.value, refresh, prompt)
    if (res.code === 200 && res.data) {
      result.value = res.data
      generationStarting.value = false
      generationStage.value = res.data.status === 'generating'
      frameKey.value += 1
      await loadHistory()
      if (res.data.status === 'generating') {
        startGenerationPoll()
      }
    } else {
      generationStarting.value = false
      generationStage.value = false
      errorMsg.value = res.msg || '生成失败，请稍后重试'
      result.value = null
    }
  } catch (e: any) {
    generationStarting.value = false
    generationStage.value = false
    errorMsg.value = e?.message || '生成失败，请稍后重试'
    result.value = null
  } finally {
    loading.value = false
    generating.value = false
  }
}

function stopGenerationPoll() {
  if (generationPollTimer.value !== null) {
    window.clearInterval(generationPollTimer.value)
    generationPollTimer.value = null
  }
}

function startGenerationPoll() {
  stopGenerationPoll()
  generationPollTimer.value = window.setInterval(async () => {
    try {
      const res: any = await getMicroCourseStatus(docId.value)
      if (res.code !== 200 || !res.data) return
      const next = res.data
      const previousHtml = result.value?.html
      result.value = next
      if (next.html !== previousHtml) frameKey.value += 1
      if (next.status === 'ready') {
        generationStage.value = false
        generationStarting.value = false
        stopGenerationPoll()
        await loadHistory()
        ElMessage.success('微课页面生成完成')
      } else if (next.status === 'failed') {
        generationStage.value = false
        generationStarting.value = false
        stopGenerationPoll()
        ElMessage.error(next.errorMsg || '生成失败，已保留可编辑的初始页面')
      }
    } catch {
      // 单次轮询失败不打断；下一次继续
    }
  }, 650)
}

function applyPrompt() {
  if (!promptText.value.trim()) {
    ElMessage.warning('先写一句修改要求，例如：加入图表、减少文字、增加图片')
    return
  }
  void generateHtml(true, promptText.value.trim())
}

function readHtmlFile(file: any) {
  const raw = file?.raw || file
  if (!raw) return false
  const reader = new FileReader()
  reader.onload = () => {
    importHtml.value = String(reader.result || '')
    ElMessage.success('已读取 HTML，可检查后导入')
  }
  reader.onerror = () => ElMessage.error('读取 HTML 文件失败')
  reader.readAsText(raw, 'utf-8')
  return false
}

async function doImport() {
  if (!importHtml.value.trim()) {
    ElMessage.warning('请先粘贴或选择 HTML')
    return
  }
  if (importing.value) return
  importing.value = true
  try {
    const res: any = await importMicroCourseHtml(docId.value, importHtml.value.trim(), result.value?.document.fileName)
    if (res.code === 200 && res.data) {
      result.value = res.data
      frameKey.value += 1
      await loadHistory()
      importVisible.value = false
      ElMessage.success('HTML 已导入为新版本')
    } else {
      ElMessage.error(res.msg || '导入失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败，请检查 HTML 内容')
  } finally {
    importing.value = false
  }
}

async function loadHistory() {
  if (!docId.value) return
  try {
    const res: any = await listMicroCourseHistory(docId.value)
    historyItems.value = res.code === 200 && Array.isArray(res.data) ? res.data : []
  } catch {
    historyItems.value = []
  }
}

async function loadRecord(item: MicroCourseHistoryItem) {
  try {
    const res: any = await getMicroCourseRecord(item.recordId)
    if (res.code === 200 && res.data) {
      result.value = res.data
      frameKey.value += 1
      historyVisible.value = false
      ElMessage.success(`已切换到第 ${item.version} 版`)
    } else {
      ElMessage.error(res.msg || '历史版本加载失败')
    }
  } catch {
    ElMessage.error('历史版本加载失败')
  }
}

function handleExport(command: string) {
  if (command === 'html') return exportHtml()
  if (command === 'pptx') return exportPpt()
}

function exportStem() {
  const raw = String(result.value?.title || result.value?.document.fileName || '教学课件')
  const stem = raw.replace(/[\\/:*?"<>|]/g, '_').replace(/\.[A-Za-z0-9]{1,6}$/, '')
  const version = result.value?.version ? `_第${result.value.version}版` : ''
  return `${stem}${version}`
}

function exportHtml() {
  if (!result.value) return
  saveAs(new Blob([result.value.html], { type: 'text/html;charset=utf-8' }), `${exportStem()}.html`)
  ElMessage.success('HTML 已开始下载')
}

async function exportPpt() {
  if (!result.value || exporting.value) return
  exporting.value = true
  try {
    const blob: any = await downloadMicroCoursePptx(docId.value, result.value.html, result.value.recordId)
    saveAs(new Blob([blob]), `${exportStem()}.pptx`)
    ElMessage.success('PPT 已开始下载')
  } catch {
    ElMessage.error('PPT 生成失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

function formatTime(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function onEditorUpdated(data: MicroCourseHtmlResult) {
  result.value = data
  frameKey.value += 1
  void loadHistory()
}

function enterFullscreen() {
  const node = stageRef.value
  if (!node) return
  if (node.requestFullscreen) node.requestFullscreen()
}

function goWorkspace() {
  router.push('/front/workspace')
}

onMounted(() => {
  void generateHtml(false)
  void loadHistory()
})

onBeforeUnmount(() => {
  stopGenerationPoll()
})

</script>

<style scoped>
.micro-page {
  max-width: 1220px;
  margin: 0 auto;
  padding: 0 20px 56px;
}

.micro-generating {
  margin: 2px 0 14px;
  padding: 11px 14px;
  border: 1px solid #dbe7ff;
  border-radius: 10px;
  background: linear-gradient(90deg, #f4f8ff 0%, #edf3fe 100%);
}

.micro-generating__head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
}

.micro-generating__head b {
  margin-left: auto;
  color: var(--os-accent, #4176e6);
  font-size: 12px;
}

.micro-generating__pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--os-accent, #4176e6);
  box-shadow: 0 0 0 0 rgba(65, 118, 230, 0.35);
  animation: micro-pulse 1.4s ease-out infinite;
}

.micro-generating__bar {
  height: 3px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 99px;
  background: #dce8fb;
}

.micro-generating__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--os-accent, #4176e6);
  transition: width 0.35s ease;
}

.micro-generating__hint {
  margin-top: 7px;
  color: var(--os-text-4, #9ca3af);
  font-size: 10px;
}

.micro-generation-stage {
  min-height: 460px;
  padding: 26px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.05));
  border-radius: 16px;
  background:
    radial-gradient(circle at 86% 8%, #eef5ff 0, transparent 34%),
    #f8fafc;
}

.micro-generation-stage__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.micro-generation-stage__title {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--os-text, #111827);
  font-size: 16px;
  font-weight: 600;
}

.micro-generation-stage__pulse {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: var(--os-accent, #4176e6);
  animation: micro-pulse 1.4s ease-out infinite;
}

.micro-generation-stage__sub {
  margin-top: 7px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.micro-generation-stage__percent {
  color: var(--os-accent, #4176e6);
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -1px;
}

.micro-generation-stage__bar {
  height: 4px;
  margin-top: 18px;
  overflow: hidden;
  border-radius: 99px;
  background: #dce8fb;
}

.micro-generation-stage__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #6c9bf0, #4176e6);
  transition: width 0.4s ease;
}

.micro-generation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(205px, 1fr));
  gap: 16px;
  max-height: 510px;
  margin-top: 24px;
  padding: 2px;
  overflow: auto;
}

.micro-generation-page {
  min-width: 0;
  opacity: 0.58;
  transform: translateY(8px);
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.micro-generation-page.is-ready {
  opacity: 1;
  transform: translateY(0);
}

.micro-generation-paper {
  aspect-ratio: 16 / 9;
  padding: 17px;
  overflow: hidden;
  border: 1px solid #e4eaf3;
  border-radius: 9px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(31, 64, 122, 0.08);
}

.micro-generation-paper__eyebrow {
  color: var(--os-accent, #4176e6);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
}

.micro-generation-paper__title {
  margin-top: 16px;
  color: #1f2937;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}

.micro-generation-paper ul {
  margin: 11px 0 0;
  padding-left: 14px;
}

.micro-generation-paper li {
  margin: 4px 0;
  color: #6b7280;
  font-size: 9px;
  line-height: 1.45;
}

.micro-generation-paper__placeholder {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 22px;
}

.micro-generation-paper__placeholder i {
  display: block;
  width: 86%;
  height: 7px;
  border-radius: 4px;
  background: #edf1f6;
}

.micro-generation-paper__placeholder i:nth-child(2) { width: 64%; }
.micro-generation-paper__placeholder i:nth-child(3) { width: 74%; }

.micro-generation-paper__shimmer {
  width: 68%;
  height: 45px;
  margin-top: 10px;
  border-radius: 7px;
  background: linear-gradient(100deg, #f1f5fb 20%, #e5edf9 40%, #f1f5fb 60%);
  background-size: 200% 100%;
  animation: micro-shimmer 1.3s ease-in-out infinite;
}

.micro-generation-page__number {
  display: block;
  margin-top: 7px;
  color: var(--os-text-4, #9ca3af);
  font-size: 10px;
}

.micro-page-in-enter-active {
  transition: opacity 0.45s ease, transform 0.45s ease;
}

.micro-page-in-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.985);
}

@keyframes micro-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

@keyframes micro-pulse {
  0% { box-shadow: 0 0 0 0 rgba(65, 118, 230, 0.35); }
  70% { box-shadow: 0 0 0 7px rgba(65, 118, 230, 0); }
  100% { box-shadow: 0 0 0 0 rgba(65, 118, 230, 0); }
}

.micro-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
}

.back-btn {
  color: var(--os-text-3, #81858c);
}

.micro-topbar-name {
  overflow: hidden;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.micro-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 520px;
  text-align: center;
}

.micro-loading-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--os-accent-soft, #edf3fe);
  color: var(--os-accent, #4176e6);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1px;
}

.micro-loading h2 {
  margin: 20px 0 8px;
  color: var(--os-text, #0f1115);
  font-size: 20px;
}

.micro-loading p {
  margin: 0;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.micro-loading-bar {
  width: 220px;
  height: 3px;
  margin-top: 22px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf0f4;
}

.micro-loading-bar span {
  display: block;
  width: 45%;
  height: 100%;
  border-radius: inherit;
  background: var(--os-accent, #4176e6);
  animation: micro-loading 1.2s ease-in-out infinite;
}

@keyframes micro-loading {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(250%); }
}

.micro-empty {
  padding: 80px 20px;
  text-align: center;
}

.micro-empty h3 {
  margin: 0 0 8px;
  color: var(--os-text, #0f1115);
  font-size: 20px;
}

.micro-empty p {
  margin: 0 0 18px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.micro-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 30px 2px 22px;
}

.micro-eyebrow {
  margin-bottom: 10px;
  color: var(--os-accent, #4176e6);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}

.micro-head h1 {
  margin: 0 0 12px;
  color: var(--os-text, #0f1115);
  font-size: clamp(24px, 3.2vw, 36px);
  line-height: 1.2;
  letter-spacing: -0.5px;
}

.micro-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.micro-meta-ai {
  color: var(--os-accent, #4176e6);
  font-weight: 600;
}

.micro-change-summary {
  max-width: 820px;
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--os-accent-soft, #edf3fe);
  color: var(--os-text-3, #64748b);
  font-size: 11px;
  line-height: 1.55;
}

.micro-actions {
  display: flex;
  flex: none;
  gap: 8px;
}

.micro-export-caret {
  margin-left: 2px;
  font-size: 11px;
}

.micro-history-empty {
  padding: 40px 12px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  text-align: center;
}

.micro-history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.micro-history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.05));
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.micro-history-item:hover,
.micro-history-item.is-current {
  border-color: var(--os-accent-soft, #dbe7ff);
  background: var(--os-accent-soft, #edf3fe);
}

.micro-history-item__main {
  flex: 1;
  min-width: 0;
}

.micro-history-item__title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--os-text, #0f1115);
  font-size: 12px;
  font-weight: 600;
}

.micro-history-item__badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: #fff;
  color: var(--os-accent, #4176e6);
  font-size: 10px;
  font-weight: 500;
}

.micro-history-item__title-text {
  overflow: hidden;
  margin-top: 4px;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.micro-history-item__change {
  overflow: hidden;
  margin-top: 3px;
  color: var(--os-text-3, #81858c);
  font-size: 10.5px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.micro-history-item__meta {
  margin-top: 4px;
  color: var(--os-text-4, #adb2b8);
  font-size: 10px;
}

.micro-history-item__arrow {
  flex: none;
  color: var(--os-text-4, #adb2b8);
}

.micro-prompt {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin: 0 0 14px;
  padding: 12px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.05));
  border-radius: 10px;
  background: #fff;
}

.micro-prompt .el-textarea {
  flex: 1;
}

.micro-prompt :deep(.el-textarea__inner) {
  border: 0;
  box-shadow: none;
  resize: none;
}

.micro-import-tip {
  margin: 0 0 12px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  line-height: 1.6;
}

.micro-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 11px;
}

.micro-tip-dot {
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: 50%;
  background: var(--os-accent, #4176e6);
}

.micro-stage {
  padding: 12px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.05));
  border-radius: 16px;
  background: #eef2f7;
}

.micro-frame-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 10px;
  background: #fff;
}

.micro-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

.micro-fullscreen {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  border-radius: 999px;
  padding: 7px 12px;
  background: rgba(17, 24, 39, 0.78);
  color: #fff;
  cursor: pointer;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.2s;
}

.micro-frame-wrap:hover .micro-fullscreen {
  opacity: 1;
}

.micro-foot {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 2px 0;
}

.micro-foot h3 {
  margin: 0 0 6px;
  color: var(--os-text, #0f1115);
  font-size: 13px;
}

.micro-foot p,
.micro-foot-meta {
  margin: 0;
  color: var(--os-text-3, #81858c);
  font-size: 11px;
  line-height: 1.7;
}

@media (max-width: 720px) {
  .micro-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .micro-stage {
    padding: 6px;
  }
}
</style>
