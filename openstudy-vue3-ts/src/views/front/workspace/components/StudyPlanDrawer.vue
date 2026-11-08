<!--
  知航 · 活计划抽屉
  ---------------------------------------------------------------------------
  这是「学习处方 / 今日处方 / 考前计划」统一后的唯一计划视图：
  · 航线站点、按天任务、真实进度都来自同一份 StudyPlan；
  · 只有一个主操作「开始今日任务」和一个轻量「调整」；
  · 不在前端勾选完成 —— 答完题/读完页后由后端真实流水重算。
-->
<template>
  <Teleport to="body">
    <div v-if="modelValue" class="spd-mask" @click.self="close">
      <aside class="spd" role="dialog" aria-label="知航 · 活计划">
        <header class="spd__head">
          <div class="spd__title-wrap">
            <span class="spd__eyebrow">知航 · 活计划</span>
            <h2>{{ plan?.route?.targetTitle ? `目标：${plan.route.targetTitle}` : '按知识图谱排好的学习计划' }}</h2>
          </div>
          <button type="button" class="spd__close" aria-label="关闭" @click="close">×</button>
        </header>

        <div v-if="loading" class="spd__loading">正在按最新学习状态重算…</div>

        <template v-else-if="plan">
          <div class="spd__progress">
            <div class="spd__progress-top">
              <span>{{ plan.route?.headline || '按图谱顺序继续学习' }}</span>
              <b>{{ plan.progress?.doneTasks || 0 }}/{{ plan.progress?.totalTasks || 0 }}</b>
            </div>
            <div class="spd__bar"><i :style="{ width: `${plan.progress?.percent || 0}%` }"></i></div>
            <div class="spd__progress-meta">
              <span>{{ plan.progress?.doneMinutes || 0 }} / {{ plan.progress?.plannedMinutes || 0 }} 分钟</span>
              <span>{{ plan.window?.start }} → {{ plan.window?.end }}</span>
            </div>
          </div>

          <div v-if="stops.length" class="spd__route">
            <button v-for="(stop, index) in stops" :key="stop.pageId" type="button" class="spd__stop"
              :class="[`is-${stop.status || 'next'}`]" @click="emit('select-stop', stop.pageId)">
              <i>{{ index + 1 }}</i>
              <span>{{ stop.title }}</span>
            </button>
          </div>

          <div v-if="plan.days?.length" class="spd__days">
            <section v-for="day in plan.days" :key="day.date" class="spd__day">
              <header class="spd__day-head">
                <div>
                  <b>{{ dayLabel(day.date) }}</b>
                  <span v-if="day.overloaded" class="spd__overload">任务较多</span>
                </div>
                <span>{{ day.minutes }} 分钟</span>
              </header>
              <button v-for="task in day.tasks" :key="task.id" type="button" class="spd__task"
                :class="[`is-${task.status || 'next'}`]" @click="emit('open-task', task)">
                <span class="spd__task-state">{{ task.status === 'done' ? '✓' : task.status === 'current' ? '▶' : '○' }}</span>
                <span class="spd__task-main">
                  <span class="spd__task-title">{{ task.title }}</span>
                  <span class="spd__task-reason">{{ task.reason }}</span>
                </span>
                <span class="spd__task-min">{{ task.minutes }}′</span>
              </button>
            </section>
          </div>
          <div v-else class="spd__empty">
            当前航线暂时没有可执行任务。先读一个主题页或做一道题，计划会随真实学习数据自动长出来。
          </div>

          <div class="spd__actions">
            <button type="button" class="spd__primary" :disabled="!primaryTask" @click="primaryTask && emit('open-task', primaryTask)">
              {{ primaryTask ? '开始今日任务' : '今天已完成' }}
              <span v-if="primaryTask">· {{ primaryTask.minutes }}′</span>
            </button>
            <button type="button" class="spd__adjust" @click="adjustOpen = !adjustOpen">调整</button>
          </div>

          <div v-if="adjustOpen" class="spd__form">
            <div class="spd__form-row">
              <label>目标</label>
              <el-select v-model="draft.goal" size="small">
                <el-option label="补弱" value="weakness" />
                <el-option label="打基础" value="foundation" />
                <el-option label="拓展" value="explore" />
                <el-option label="考试倒计时" value="exam" />
                <el-option label="只看今天" value="today" />
              </el-select>
            </div>
            <div v-if="draft.goal === 'exam'" class="spd__form-row">
              <label>考试日期</label>
              <el-date-picker v-model="draft.examDate" type="date" value-format="YYYY-MM-DD" size="small" placeholder="选择考试日" />
            </div>
            <div class="spd__form-row">
              <label>每日分钟</label>
              <el-input-number v-model="draft.dailyMinutes" :min="10" :max="240" :step="10" size="small" />
            </div>
            <div class="spd__form-row">
              <label>计划天数</label>
              <el-input-number v-model="draft.horizonDays" :min="1" :max="30" size="small" />
            </div>
            <div class="spd__form-actions">
              <el-button size="small" @click="adjustOpen = false">取消</el-button>
              <el-button size="small" type="primary" :loading="loading" @click="submitAdjust">重新生成</el-button>
            </div>
          </div>

          <footer class="spd__foot">
            <span>完成状态来自真实答题/阅读记录，不需要手动勾选</span>
            <span v-if="plan.degraded?.noQuestionSource">当前资料还没有可反查的题目标注，先以阅读为主</span>
          </footer>
        </template>
      </aside>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: boolean
  plan: any | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'open-task', task: any): void
  (e: 'select-stop', pageId: number): void
  (e: 'adjust', payload: any): void
}>()

const adjustOpen = ref(false)
const draft = reactive({
  goal: 'weakness',
  examDate: '',
  dailyMinutes: 40,
  horizonDays: 7
})

const stops = computed(() => props.plan?.route?.stops || [])
const allTasks = computed(() => (props.plan?.days || []).flatMap((day: any) => day.tasks || []))
const primaryTask = computed(() => {
  const tasks = allTasks.value
  return tasks.find((task: any) => task.status === 'current')
    || tasks.find((task: any) => task.status === 'blocked')
    || tasks.find((task: any) => task.status !== 'done')
    || null
})

function close() {
  emit('update:modelValue', false)
}

function dayLabel(value: string) {
  const today = new Date()
  const date = new Date(`${String(value || '').slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  const diff = Math.round((date.getTime() - new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  return `${value} · 周${'日一二三四五六'[date.getDay()]}`
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible && props.plan?.intent) {
      draft.goal = props.plan.intent.goal || 'weakness'
      draft.examDate = props.plan.intent.examDate || ''
      draft.dailyMinutes = Number(props.plan.window?.dailyMinutes || 40)
      draft.horizonDays = Number(props.plan.window?.horizonDays || 7)
      adjustOpen.value = false
    }
  }
)

function submitAdjust() {
  emit('adjust', { ...draft })
}
</script>

<style scoped>
.spd-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  justify-content: flex-end;
  background: rgba(20, 31, 52, 0.24);
}
.spd {
  display: flex;
  width: min(440px, 92vw);
  height: 100%;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 18px 18px 22px;
  border-left: 1px solid #e3e9f2;
  background: #fff;
  color: #253247;
  box-shadow: -12px 0 32px rgba(31, 47, 75, 0.12);
}
.spd__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.spd__eyebrow { color: #2f5fce; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }
.spd__head h2 { margin: 5px 0 0; font-size: 18px; line-height: 1.35; }
.spd__close { padding: 0 2px; border: 0; color: #8a91a0; background: transparent; cursor: pointer; font-size: 24px; line-height: 1; }
.spd__close:hover { color: #2f5fce; }
.spd__loading, .spd__empty { padding: 28px 4px; color: #8a91a0; font-size: 12px; line-height: 1.65; text-align: center; }
.spd__progress { padding: 10px 12px; border: 1px solid #e6ecf6; border-radius: 10px; background: #f8faff; }
.spd__progress-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: #5f6b7d; font-size: 11px; line-height: 1.5; }
.spd__progress-top b { flex: none; color: #2f5fce; font-size: 12px; }
.spd__bar { height: 5px; margin-top: 8px; border-radius: 99px; background: #e6ecf6; overflow: hidden; }
.spd__bar i { display: block; height: 100%; border-radius: inherit; background: #2f5fce; transition: width .2s ease; }
.spd__progress-meta { display: flex; justify-content: space-between; gap: 8px; margin-top: 6px; color: #9aa3b2; font-size: 10px; }
.spd__route { display: flex; gap: 4px; overflow-x: auto; padding: 3px 1px; }
.spd__stop { display: flex; min-width: 54px; flex: 1; flex-direction: column; align-items: center; gap: 3px; padding: 0; border: 0; background: transparent; color: #7d8596; cursor: pointer; font: inherit; text-align: center; }
.spd__stop i { display: inline-flex; width: 19px; height: 19px; align-items: center; justify-content: center; border: 1.5px solid #d7dfec; border-radius: 50%; background: #fff; font-size: 10px; font-style: normal; font-weight: 700; }
.spd__stop span { overflow: hidden; width: 100%; font-size: 10px; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.spd__stop.is-current i { border-color: #2f5fce; background: #2f5fce; color: #fff; }
.spd__stop.is-done i { border-color: #2f9e8f; background: #2f9e8f; color: #fff; }
.spd__days { display: flex; flex-direction: column; gap: 11px; }
.spd__day { border: 1px solid #e8edf5; border-radius: 10px; overflow: hidden; }
.spd__day-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; background: #f7f9fc; color: #8a91a0; font-size: 11px; }
.spd__day-head b { color: #38465c; font-size: 12px; }
.spd__overload { margin-left: 5px; padding: 1px 5px; border-radius: 4px; color: #b26b13; background: #fff3df; font-size: 9px; }
.spd__task { display: flex; width: 100%; align-items: flex-start; gap: 7px; padding: 9px 10px; border: 0; border-top: 1px solid #f0f3f8; background: #fff; color: inherit; cursor: pointer; font: inherit; text-align: left; }
.spd__task:hover { background: #f8faff; }
.spd__task-state { flex: none; width: 15px; color: #b3bac7; font-size: 12px; line-height: 1.5; }
.spd__task.is-current .spd__task-state { color: #2f5fce; }
.spd__task.is-done .spd__task-state { color: #2f9e8f; }
.spd__task-main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.spd__task-title { overflow: hidden; color: #38465c; font-size: 12px; font-weight: 600; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.spd__task-reason { display: -webkit-box; overflow: hidden; color: #8a91a0; font-size: 10px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.spd__task-min { flex: none; color: #9aa3b2; font-size: 10px; line-height: 1.5; }
.spd__actions { display: flex; gap: 8px; padding-top: 2px; }
.spd__primary { display: flex; height: 36px; flex: 1; align-items: center; justify-content: center; gap: 5px; border: 0; border-radius: 8px; background: #2f5fce; color: #fff; cursor: pointer; font: inherit; font-size: 13px; font-weight: 600; }
.spd__primary:hover { background: #2853b8; }
.spd__primary:disabled { opacity: .55; cursor: not-allowed; }
.spd__adjust { flex: none; padding: 0 12px; border: 1px solid #dfe6f1; border-radius: 8px; color: #5f6b7d; background: #fff; cursor: pointer; font: inherit; font-size: 12px; }
.spd__adjust:hover { border-color: #b9cdf3; color: #2f5fce; }
.spd__form { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid #e6ecf6; border-radius: 9px; background: #fafcff; }
.spd__form-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 12px; color: #697386; }
.spd__form-row :deep(.el-select), .spd__form-row :deep(.el-input-number), .spd__form-row :deep(.el-date-editor) { width: 180px; }
.spd__form-actions { display: flex; justify-content: flex-end; gap: 6px; }
.spd__foot { display: flex; flex-direction: column; gap: 3px; padding-top: 3px; color: #a0a8b6; font-size: 10px; line-height: 1.5; }
@media (max-width: 760px) {
  .spd { width: 100vw; padding: 14px 14px 18px; }
}
</style>
