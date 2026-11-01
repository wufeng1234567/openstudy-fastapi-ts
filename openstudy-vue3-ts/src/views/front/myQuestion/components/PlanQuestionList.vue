<template>
  <div class="plan-question-page">
    <div v-if="!plan" class="plan-empty">
      <div class="plan-empty-mark">考</div>
      <h3>还没有考前计划</h3>
      <p>先在学习统计的「考前计划」里生成路线图，这里会自动收拢计划涉及的全部题目。</p>
      <el-button type="primary" @click="goExamPlan">去生成考前计划</el-button>
    </div>

    <template v-else>
      <div class="plan-head">
        <div>
          <div class="plan-title-row">
            <h3>{{ plan.exam?.name || '我的考试' }} · 计划题目</h3>
            <span class="plan-chip">{{ plan.days?.length || 0 }} 天</span>
          </div>
          <p class="plan-sub">
            共 {{ questionItems.length }} 道题 · 已完成 {{ completedCount }} 道 · 点击题目展开答案与解析
          </p>
        </div>
        <div class="plan-head-actions">
          <el-radio-group v-model="statusFilter" size="small">
            <el-radio-button label="all">全部</el-radio-button>
            <el-radio-button label="todo">未完成</el-radio-button>
            <el-radio-button label="done">已完成</el-radio-button>
          </el-radio-group>
          <el-button size="small" :loading="loading" @click="refresh">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="plan-progress-row">
        <span>计划完成度</span>
        <div class="plan-progress-track"><i :style="{ width: `${progressPercent}%` }"></i></div>
        <b>{{ completedCount }} / {{ questionItems.length }}</b>
      </div>

      <div v-if="filteredItems.length" class="plan-question-list">
        <article
          v-for="item in filteredItems"
          :key="item.questionId"
          class="plan-question-card"
          :class="{ 'is-done': item.done, 'is-open': expandedId === item.questionId }"
          @click="toggleExpand(item)"
        >
          <div class="plan-card-head">
            <div class="plan-card-tags">
              <span class="plan-type">{{ item.questionTypeText || '题目' }}</span>
              <span class="plan-bank">{{ item.bankName || '未分类' }}</span>
            </div>
            <span class="plan-state" :class="{ 'is-done': item.done }">
              {{ item.done ? '已完成' : '待完成' }}
            </span>
          </div>
          <div class="plan-question-text" v-html="renderQuestionContent(item.questionText)"></div>
          <div class="plan-card-meta">
            <span>计划出现：{{ item.dates.join('、') }}</span>
            <span v-if="item.occurrences > 1">需完成 {{ item.doneAttempts }} / {{ item.occurrences }} 次</span>
          </div>

          <div v-if="expandedId === item.questionId" class="plan-detail" @click.stop>
            <div v-if="optionEntries(item).length" class="plan-options">
              <div v-for="option in optionEntries(item)" :key="option.key" class="plan-option">
                <span class="plan-option-key">{{ option.key }}</span>
                <span v-html="renderQuestionContent(option.value)"></span>
              </div>
            </div>
            <div class="plan-answer">
              <span>答案</span>
              <div v-html="renderQuestionContent(item.answer || '暂无答案')"></div>
            </div>
            <div v-if="item.analysis" class="plan-answer">
              <span>解析</span>
              <div v-html="renderQuestionContent(item.analysis)"></div>
            </div>
            <div class="plan-detail-actions">
              <el-button size="small" @click="openQuestion(item)">去练这道</el-button>
            </div>
          </div>
        </article>
      </div>
      <el-empty v-else :description="emptyDescription" :image-size="80" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import { listPlanQuestions } from '@/api/questionMain/questionMain'
import { getPracticeProgress } from '@/api/userStats/userStats'
import { renderQuestionContent } from '@/utils/latex'

defineOptions({ name: 'PlanQuestionList' })

const emit = defineEmits<{ (e: 'total-change', payload: { total: number; loading: boolean }): void }>()

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const loading = ref(true)
const plan = ref<any>(null)
const planCreatedAt = ref(0)
const questionItems = ref<any[]>([])
const progressMap = ref<Record<number, number>>({})
const statusFilter = ref('all')
const expandedId = ref<number | null>(null)

const storageKey = computed(() => `os_exam_plan_v1_${userStore.id || 'anon'}`)

const completedCount = computed(() => questionItems.value.filter((item) => item.done).length)
const progressPercent = computed(() =>
  questionItems.value.length ? Math.round((completedCount.value / questionItems.value.length) * 100) : 0
)
const filteredItems = computed(() => {
  if (statusFilter.value === 'todo') return questionItems.value.filter((item) => !item.done)
  if (statusFilter.value === 'done') return questionItems.value.filter((item) => item.done)
  return questionItems.value
})
const emptyDescription = computed(() =>
  statusFilter.value === 'all' ? '计划里还没有可展示的题目' : '这个筛选下没有题目'
)

function readPlan() {
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return null
    const saved = JSON.parse(raw)
    if (!saved?.plan || !saved?.createdAt) return null
    planCreatedAt.value = Number(saved.createdAt)
    return saved.plan
  } catch {
    return null
  }
}

function occurrenceMap() {
  const map: Record<number, { dates: string[]; count: number }> = {}
  for (const day of plan.value?.days || []) {
    for (const task of day.tasks || []) {
      const qid = Number(task.questionId || 0)
      if (!qid) continue
      const row = map[qid] || { dates: [], count: 0 }
      row.count += 1
      if (!row.dates.includes(day.date.slice(5))) row.dates.push(day.date.slice(5))
      map[qid] = row
    }
  }
  return map
}

function optionEntries(item: any) {
  const options = item.options
  if (!options) return []
  if (Array.isArray(options)) {
    return options.map((value, index) => ({ key: String.fromCharCode(65 + index), value: String(value) }))
  }
  if (typeof options === 'object') {
    return Object.entries(options).map(([key, value]) => ({ key, value: String(value) }))
  }
  return []
}

async function load() {
  loading.value = true
  emit('total-change', { total: 0, loading: true })
  try {
    plan.value = readPlan()
    if (!plan.value) {
      questionItems.value = []
      emit('total-change', { total: 0, loading: false })
      return
    }
    const occurrence = occurrenceMap()
    const ids = Object.keys(occurrence).map(Number)
    if (!ids.length) {
      questionItems.value = []
      emit('total-change', { total: 0, loading: false })
      return
    }

    const [questionsRes, progressRes] = await Promise.all([
      listPlanQuestions(ids),
      getPracticeProgress(planCreatedAt.value, ids)
    ])
    const rows = questionsRes.code === 200 ? questionsRes.data || [] : []
    const progress: Record<number, number> = {}
    if (progressRes.code === 200 && progressRes.data) {
      for (const item of progressRes.data.latest || []) {
        progress[Number(item.questionId)] = Number(item.attempts || 0)
      }
    }
    progressMap.value = progress
    questionItems.value = rows.map((item: any) => {
      const qid = Number(item.questionId || item.id)
      const occ = occurrence[qid] || { dates: [], count: 0 }
      const doneAttempts = progress[qid] || 0
      return {
        ...item,
        dates: occ.dates,
        occurrences: occ.count,
        doneAttempts,
        done: occ.count > 0 && doneAttempts >= occ.count
      }
    })
    const focus = Number(route.query.questionId || 0)
    if (focus && questionItems.value.some((item) => item.questionId === focus)) {
      expandedId.value = focus
    }
    emit('total-change', { total: questionItems.value.length, loading: false })
  } catch (e: any) {
    console.warn('[计划题目] 加载失败', e)
    emit('total-change', { total: 0, loading: false })
  } finally {
    loading.value = false
  }
}

function toggleExpand(item: any) {
  expandedId.value = expandedId.value === item.questionId ? null : item.questionId
}

function openQuestion(item: any) {
  router.push({
    path: '/front/myQuestion/wrongQuestion',
    query: { questionId: String(item.questionId), from: 'plan' }
  })
}

function goExamPlan() {
  router.push('/front/myQuestion/myStats?tab=exam')
}

const refresh = () => load()
defineExpose({ refresh })

watch(
  () => route.query.questionId,
  (value) => {
    const qid = Number(value || 0)
    if (qid && questionItems.value.some((item) => item.questionId === qid)) {
      expandedId.value = qid
    }
  }
)

onMounted(load)
</script>

<style scoped>
.plan-question-page {
  width: 100%;
}

.plan-empty {
  padding: 56px 24px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
  text-align: center;
}

.plan-empty-mark {
  display: inline-grid;
  width: 44px;
  height: 44px;
  margin-bottom: 12px;
  place-items: center;
  border-radius: var(--os-radius-sm, 8px);
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 16px;
}

.plan-empty h3 {
  margin: 0 0 6px;
  color: var(--os-text, #0f1115);
  font-size: 16px;
  font-weight: 600;
}

.plan-empty p {
  margin: 0 auto 16px;
  max-width: 440px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  line-height: 1.7;
}

.plan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
}

.plan-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-title-row h3 {
  margin: 0;
  color: var(--os-text, #0f1115);
  font-size: 15px;
  font-weight: 600;
}

.plan-chip {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.plan-sub {
  margin: 5px 0 0;
  color: var(--os-text-3, #81858c);
  font-size: 11px;
}

.plan-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.plan-progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.plan-progress-row b {
  color: var(--os-text, #0f1115);
  font-weight: 600;
}

.plan-progress-track {
  width: 160px;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: #f1f3f5;
}

.plan-progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--os-accent, #4176e6);
}

.plan-question-list {
  margin-top: 10px;
}

.plan-question-card {
  padding: 14px 16px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.plan-question-card + .plan-question-card {
  margin-top: 8px;
}

.plan-question-card:hover {
  border-color: var(--os-border-strong, rgba(0, 0, 0, 0.1));
  background: #fcfdff;
}

.plan-question-card.is-done {
  background: #fbfefc;
}

.plan-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.plan-card-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.plan-type,
.plan-bank {
  overflow: hidden;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-state {
  flex: none;
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.plan-state.is-done {
  color: #059669;
}

.plan-question-text {
  margin-top: 8px;
  color: var(--os-text, #0f1115);
  font-size: 12px;
  line-height: 1.65;
}

.plan-question-text :deep(.katex) {
  font-size: 1em;
}

.plan-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  color: var(--os-text-4, #adb2b8);
  font-size: 9px;
}

.plan-detail {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
}

.plan-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.plan-option {
  display: flex;
  gap: 6px;
  color: var(--os-text-2, #353638);
  font-size: 11px;
  line-height: 1.6;
}

.plan-option-key {
  flex: none;
  color: var(--os-text-3, #81858c);
  font-weight: 600;
}

.plan-answer {
  display: flex;
  gap: 8px;
  padding: 7px 9px;
  border-radius: 6px;
  background: #f9fafb;
  color: var(--os-text-2, #353638);
  font-size: 11px;
  line-height: 1.6;
}

.plan-answer + .plan-answer {
  margin-top: 5px;
}

.plan-answer > span {
  flex: none;
  color: var(--os-text-3, #81858c);
}

.plan-detail-actions {
  margin-top: 8px;
}

@media (max-width: 720px) {
  .plan-head {
    flex-direction: column;
  }
  .plan-head-actions {
    flex-wrap: wrap;
  }
}
</style>
