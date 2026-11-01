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
        </div>
        <div class="micro-actions">
          <el-button :loading="generating" @click="generateHtml">重新生成</el-button>
          <el-button type="primary" :loading="downloading" @click="downloadPpt">
            <el-icon><Download /></el-icon>
            下载 PPT
          </el-button>
        </div>
      </section>

      <div class="micro-tip">
        <span class="micro-tip-dot"></span>
        HTML 课件可以直接全屏演示；下载 PPT 时会把当前 HTML 的页面结构转成幻灯片。
      </div>

      <section class="micro-stage">
        <div ref="stageRef" class="micro-frame-wrap">
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
        <span class="micro-foot-meta">共 {{ result.slides }} 页 · 可直接投屏</span>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, FullScreen } from '@element-plus/icons-vue'
import { saveAs } from 'file-saver'
import { downloadMicroCoursePptx, getMicroCourseHtml, type MicroCourseHtmlResult } from '@/api/ai/workspace'

defineOptions({ name: 'MicroCourse' })

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const generating = ref(false)
const downloading = ref(false)
const errorMsg = ref('')
const result = ref<MicroCourseHtmlResult | null>(null)
const frameKey = ref(0)
const stageRef = ref<HTMLElement | null>(null)

const docId = computed(() => String(route.query.docId || ''))

async function generateHtml() {
  if (!docId.value) {
    loading.value = false
    return
  }
  generating.value = true
  errorMsg.value = ''
  try {
    const res: any = await getMicroCourseHtml(docId.value)
    if (res.code === 200 && res.data) {
      result.value = res.data
      frameKey.value += 1
    } else {
      errorMsg.value = res.msg || '生成失败，请稍后重试'
      result.value = null
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '生成失败，请稍后重试'
    result.value = null
  } finally {
    loading.value = false
    generating.value = false
  }
}

async function downloadPpt() {
  if (!result.value || downloading.value) return
  downloading.value = true
  try {
    const blob: any = await downloadMicroCoursePptx(docId.value, result.value.html)
    const stem = String(result.value.document.fileName || '教学课件').replace(/\.[^.]+$/, '')
    saveAs(new Blob([blob]), `${stem}.pptx`)
    ElMessage.success('PPT 已开始下载')
  } catch {
    ElMessage.error('PPT 生成失败，请稍后重试')
  } finally {
    downloading.value = false
  }
}

function enterFullscreen() {
  const node = stageRef.value
  if (!node) return
  if (node.requestFullscreen) node.requestFullscreen()
}

function goWorkspace() {
  router.push('/front/workspace')
}

onMounted(generateHtml)
</script>

<style scoped>
.micro-page {
  max-width: 1220px;
  margin: 0 auto;
  padding: 0 20px 56px;
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

.micro-actions {
  display: flex;
  flex: none;
  gap: 8px;
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
