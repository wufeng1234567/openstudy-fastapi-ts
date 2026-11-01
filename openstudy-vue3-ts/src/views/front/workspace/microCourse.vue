<template>
  <div class="micro-page">
    <div class="micro-topbar">
      <el-button text class="back-btn" @click="goWorkspace">
        <el-icon><ArrowLeft /></el-icon>
        我的资料
      </el-button>
      <span class="micro-topbar-hint">按原文结构生成 · 不编造资料里没有的内容</span>
    </div>

    <div v-if="loading" class="micro-loading" v-loading="true"></div>

    <div v-else-if="!data" class="micro-empty">
      <h3>这份资料暂时打不开</h3>
      <p>它可能已被删除，或者你还没有阅读权限。</p>
      <el-button type="primary" @click="goWorkspace">回到我的资料</el-button>
    </div>

    <template v-else>
      <section class="micro-head">
        <div class="micro-head-main">
          <div class="micro-eyebrow">MATERIAL TO MICRO-COURSE · 资料变微课</div>
          <h1>{{ data.document.fileName }}</h1>
          <div class="micro-meta">
            <span>{{ data.overview.stationCount }} 站</span>
            <span>约 {{ data.overview.totalMinutes }} 分钟</span>
            <span>{{ data.document.wordCount }} 字</span>
            <span v-if="data.document.chunkCount">{{ data.document.chunkCount }} 个片段</span>
            <span v-if="data.document.subject">{{ data.document.subject }}</span>
          </div>
        </div>
        <div class="micro-progress-card">
          <div class="micro-progress-num">{{ completedCount }}<i>/{{ data.overview.stationCount }}</i></div>
          <div class="micro-progress-label">已走完的站</div>
          <div class="micro-progress-track">
            <div class="micro-progress-fill" :style="{ width: `${progressPct}%` }"></div>
          </div>
        </div>
      </section>

      <div v-if="!data.document.hasOutline" class="micro-fallback-note">
        这份资料没有可识别的章节标题，系统按段落切成了 {{ data.overview.stationCount }} 站。
      </div>

      <div class="micro-layout">
        <aside class="station-rail">
          <div
            v-for="station in data.stations"
            :key="station.id"
            class="station-item"
            :class="{
              'is-active': currentIndex === station.index - 1,
              'is-done': isDone(station.id),
            }"
            role="button"
            tabindex="0"
            @click="currentIndex = station.index - 1"
            @keyup.enter="currentIndex = station.index - 1"
          >
            <span class="station-dot">
              <el-icon v-if="isDone(station.id)"><Check /></el-icon>
              <template v-else>{{ station.index }}</template>
            </span>
            <span class="station-line"></span>
            <div class="station-copy">
              <div class="station-title">{{ station.title }}</div>
              <div class="station-sub">{{ station.minutes }} 分钟 · 检查点</div>
            </div>
          </div>
        </aside>

        <main v-if="currentStation" class="station-main">
          <div class="station-card">
            <div class="station-card-head">
              <span class="station-eyebrow">STATION {{ String(currentStation.index).padStart(2, '0') }} / {{ String(data.overview.stationCount).padStart(2, '0') }}</span>
              <span v-if="isDone(currentStation.id)" class="station-done-tag">已完成</span>
            </div>
            <h2>{{ currentStation.title }}</h2>
            <div class="station-card-meta">约 {{ currentStation.minutes }} 分钟 · 先读原文，再合上资料复述</div>

            <div class="station-section">
              <div class="station-section-title">
                <span>01</span> 原文导读
              </div>
              <p class="station-summary">{{ currentStation.summary }}</p>
            </div>

            <div v-if="currentStation.points.length" class="station-section">
              <div class="station-section-title">
                <span>02</span> 这一节讲了哪些点
              </div>
              <ul class="station-points">
                <li v-for="(point, i) in currentStation.points" :key="i">{{ point }}</li>
              </ul>
            </div>

            <div class="station-section station-checkpoint">
              <div class="station-section-title">
                <span>03</span> 检查点：用自己的话讲一遍
              </div>
              <p class="checkpoint-question">{{ currentStation.checkpoint }}</p>
              <el-input
                v-model="notes[currentStation.id]"
                type="textarea"
                :rows="3"
                maxlength="500"
                show-word-limit
                placeholder="写下你的复述。不用写得漂亮，能讲清楚就行。"
                @input="saveNotes"
              />
              <div class="checkpoint-actions">
                <el-button
                  :type="isDone(currentStation.id) ? 'success' : 'primary'"
                  plain
                  @click="toggleDone(currentStation.id)"
                >
                  <el-icon><Check /></el-icon>
                  {{ isDone(currentStation.id) ? '已标记完成，点击取消' : '我讲完了，标记完成' }}
                </el-button>
                <el-button v-if="currentIndex < data.stations.length - 1" @click="nextStation">
                  下一站 <el-icon><ArrowRight /></el-icon>
                </el-button>
              </div>
            </div>
          </div>

          <div v-if="data.relatedBanks.length" class="related-card">
            <div>
              <h3>学完这一份，去做几道相关的题</h3>
              <p>系统按资料科目/名称匹配的题库，不是自动生成的假题。</p>
            </div>
            <div class="related-list">
              <el-button
                v-for="bank in data.relatedBanks"
                :key="bank.id"
                plain
                @click="goBank(bank.id)"
              >
                {{ bank.name }}<span v-if="bank.subject" class="related-subject">{{ bank.subject }}</span>
              </el-button>
            </div>
          </div>

          <div v-if="allDone" class="micro-finish">
            <div class="micro-finish-mark"><el-icon><Trophy /></el-icon></div>
            <div>
              <h3>这份资料，你走完了。</h3>
              <p>共 {{ data.overview.stationCount }} 站、约 {{ data.overview.totalMinutes }} 分钟。接下来用练习题确认一下。</p>
            </div>
            <el-button type="primary" @click="goBank(data.relatedBanks[0]?.id)">去练相关题</el-button>
          </div>
        </main>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Check, Trophy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getMicroCourse, type MicroCourseResult } from '@/api/ai/workspace'

defineOptions({ name: 'MicroCourse' })

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const data = ref<MicroCourseResult | null>(null)
const currentIndex = ref(0)
const doneIds = ref<string[]>([])
const notes = reactive<Record<string, string>>({})

const docId = computed(() => String(route.query.docId || ''))
const currentStation = computed(() => data.value?.stations?.[currentIndex.value] || null)
const completedCount = computed(() => doneIds.value.length)
const progressPct = computed(() => {
  const total = data.value?.overview.stationCount || 0
  return total ? Math.round((completedCount.value / total) * 100) : 0
})
const allDone = computed(() => !!data.value && completedCount.value >= (data.value.overview.stationCount || 0))

const progressKey = computed(() => `os_micro_progress_${docId.value}`)
const notesKey = computed(() => `os_micro_notes_${docId.value}`)

function loadLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem(progressKey.value) || '[]')
    if (Array.isArray(saved)) doneIds.value = saved.map(String)
    const savedNotes = JSON.parse(localStorage.getItem(notesKey.value) || '{}')
    if (savedNotes && typeof savedNotes === 'object') {
      Object.keys(savedNotes).forEach((key) => (notes[key] = String(savedNotes[key] ?? '')))
    }
  } catch {
    doneIds.value = []
  }
}

function saveDone() {
  localStorage.setItem(progressKey.value, JSON.stringify(doneIds.value))
}
function saveNotes() {
  localStorage.setItem(notesKey.value, JSON.stringify(notes))
}
function isDone(id: string) {
  return doneIds.value.includes(id)
}
function toggleDone(id: string) {
  if (isDone(id)) {
    doneIds.value = doneIds.value.filter((x) => x !== id)
  } else {
    doneIds.value = [...doneIds.value, id]
    ElMessage.success('已记录这一站，继续下一站吧')
  }
  saveDone()
}
function nextStation() {
  if (currentIndex.value < (data.value?.stations.length || 0) - 1) currentIndex.value += 1
}

async function load() {
  loading.value = true
  try {
    if (!docId.value) {
      data.value = null
      return
    }
    const res: any = await getMicroCourse(docId.value)
    if (res.code === 200 && res.data) {
      data.value = res.data
      loadLocal()
      const firstUndone = res.data.stations.findIndex((s: any) => !doneIds.value.includes(s.id))
      currentIndex.value = firstUndone >= 0 ? firstUndone : 0
    }
  } catch (e: any) {
    console.warn('[资料变微课] 加载失败', e)
  } finally {
    loading.value = false
  }
}

const goWorkspace = () => router.push('/front/workspace')
function goBank(bankId?: number) {
  if (!bankId) return
  router.push(`/front/questionPractice/${bankId}`)
}

onMounted(load)
</script>

<style scoped>
.micro-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 20px 60px;
}

.micro-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.back-btn {
  color: #64748b;
  font-size: 13px;
}

.micro-topbar-hint {
  color: #9ca3af;
  font-size: 11px;
}

.micro-loading {
  height: 480px;
  border-radius: 18px;
  background: #fff;
}

.micro-empty {
  padding: 70px 24px;
  border: 1px solid #eef2f7;
  border-radius: 18px;
  background: #fff;
  text-align: center;
}

.micro-empty h3 {
  margin: 0 0 8px;
  color: #1f2937;
  font-size: 18px;
}

.micro-empty p {
  margin: 0 0 18px;
  color: #64748b;
  font-size: 12px;
}

.micro-head {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 24px;
  padding: 26px 28px;
  border-radius: 20px;
  background:
    radial-gradient(circle at 92% 10%, rgba(96, 165, 250, 0.24), transparent 30%),
    linear-gradient(135deg, #0f172a, #1e3a5f 65%, #1d4ed8);
  color: #fff;
}

.micro-eyebrow {
  color: #93c5fd;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.micro-head h1 {
  margin: 10px 0 8px;
  color: #fff;
  font-size: 25px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.micro-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: rgba(255, 255, 255, 0.66);
  font-size: 11px;
}

.micro-meta span + span::before {
  content: '·';
  margin-right: 8px;
  color: rgba(255, 255, 255, 0.35);
}

.micro-progress-card {
  display: flex;
  width: 150px;
  flex: none;
  flex-direction: column;
  justify-content: center;
  padding-left: 22px;
  border-left: 1px solid rgba(255, 255, 255, 0.18);
}

.micro-progress-num {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
}

.micro-progress-num i {
  color: rgba(255, 255, 255, 0.55);
  font-size: 14px;
  font-style: normal;
  font-weight: 500;
}

.micro-progress-label {
  margin-top: 5px;
  color: #93c5fd;
  font-size: 10px;
}

.micro-progress-track {
  height: 5px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
}

.micro-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: #60a5fa;
  transition: width 0.35s ease;
}

.micro-fallback-note {
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  background: #fff7e6;
  color: #d46b08;
  font-size: 11px;
}

.micro-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  margin-top: 16px;
}

.station-rail {
  position: sticky;
  top: 16px;
  padding: 10px;
  border: 1px solid #e8edf5;
  border-radius: 16px;
  background: #fff;
}

.station-item {
  position: relative;
  display: flex;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.station-item:hover {
  background: #f8fafc;
}

.station-item.is-active {
  background: #eff6ff;
}

.station-dot {
  display: grid;
  width: 24px;
  height: 24px;
  flex: none;
  place-items: center;
  border: 1px solid #dbe2ea;
  border-radius: 50%;
  background: #fff;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  z-index: 1;
}

.station-item.is-active .station-dot {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

.station-item.is-done .station-dot {
  border-color: #10b981;
  background: #ecfdf5;
  color: #059669;
}

.station-line {
  position: absolute;
  top: 34px;
  left: 19px;
  width: 1px;
  height: calc(100% - 24px);
  background: #eef2f7;
}

.station-item:last-child .station-line {
  display: none;
}

.station-copy {
  min-width: 0;
  flex: 1;
}

.station-title {
  display: -webkit-box;
  overflow: hidden;
  color: #334155;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.station-item.is-active .station-title {
  color: #1d4ed8;
}

.station-sub {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 9px;
}

.station-main {
  min-width: 0;
}

.station-card {
  padding: 28px 30px;
  border: 1px solid #e8edf5;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.05);
}

.station-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.station-eyebrow {
  color: #2563eb;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.station-done-tag {
  padding: 3px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #059669;
  font-size: 10px;
  font-weight: 600;
}

.station-card h2 {
  margin: 12px 0 6px;
  color: #0f172a;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.station-card-meta {
  color: #94a3b8;
  font-size: 11px;
}

.station-section {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid #eef2f7;
}

.station-section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  color: #1f2937;
  font-size: 13px;
  font-weight: 700;
}

.station-section-title span {
  color: #2563eb;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.station-summary {
  margin: 0;
  max-height: 260px;
  overflow-y: auto;
  padding: 14px 16px;
  border-radius: 10px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  line-height: 1.85;
  white-space: pre-wrap;
}

.station-points {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  font-size: 12px;
  line-height: 1.9;
}

.station-points li::marker {
  color: #93c5fd;
}

.station-checkpoint {
  padding: 18px;
  border: 1px dashed #dbeafe;
  border-radius: 14px;
  background: #f8fbff;
}

.checkpoint-question {
  margin: 0 0 10px;
  color: #334155;
  font-size: 12px;
  line-height: 1.7;
}

.checkpoint-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.related-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 14px;
  padding: 16px 20px;
  border: 1px solid #e8edf5;
  border-radius: 14px;
  background: #fff;
}

.related-card h3 {
  margin: 0 0 4px;
  color: #1f2937;
  font-size: 13px;
}

.related-card p {
  margin: 0;
  color: #94a3b8;
  font-size: 10px;
}

.related-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.related-subject {
  margin-left: 5px;
  color: #94a3b8;
  font-size: 9px;
}

.micro-finish {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 14px;
  padding: 18px 20px;
  border-radius: 14px;
  background: linear-gradient(135deg, #ecfdf5, #f0fdf4);
  border: 1px solid #d1fae5;
}

.micro-finish-mark {
  display: grid;
  width: 42px;
  height: 42px;
  flex: none;
  place-items: center;
  border-radius: 12px;
  background: #10b981;
  color: #fff;
  font-size: 20px;
}

.micro-finish h3 {
  margin: 0 0 3px;
  color: #065f46;
  font-size: 14px;
}

.micro-finish p {
  margin: 0;
  color: #047857;
  font-size: 11px;
}

.micro-finish .el-button {
  margin-left: auto;
}

@media (max-width: 900px) {
  .micro-layout {
    grid-template-columns: 1fr;
  }
  .station-rail {
    position: static;
  }
  .micro-head {
    flex-wrap: wrap;
  }
  .related-card {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
