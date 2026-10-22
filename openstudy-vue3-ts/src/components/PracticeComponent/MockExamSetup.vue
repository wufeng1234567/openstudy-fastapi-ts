<!--
  模拟考试配置页（2026-10-22）

  为什么单独一页而不是塞进「刷题设置」弹窗：
    一场考试要定的是**本次考试**的题量结构、分值、时长、及格线 ——
    这是"出一份卷子"，和刷题的"偏好"不是一回事。
    塞进设置弹窗会让它变成十来个字段的长表单，用户根本不知道自己配的是什么。

  设计取舍：
    · 左侧配置、右侧实时汇总是两栏：用户每改一个数字，立刻能看见
      「共 N 题 / 满分 M 分 / 及格 K 分」，不需要自己心算；
    · 题型行按题库实际拥有的题量给上限提示，避免"想抽 70 道但库里有 10 道"的空卷；
    · 满分不写死 100：用户可能就想出 50 分的卷子。及格分按满分的百分比校验。
-->
<template>
  <div class="mock-setup">
    <!-- 顶部：返回 + 标题 + 历史入口 -->
    <header class="setup-head">
      <button class="back-btn" type="button" @click="$emit('cancel')">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </button>
      <div class="head-main">
        <h2>模拟考试</h2>
        <p class="head-sub">{{ bankName }} · 自定义题量与分值，限时作答</p>
      </div>
      <button class="history-btn" type="button" @click="$emit('open-history')">
        <el-icon><Notebook /></el-icon>
        <span>考试记录</span>
        <span v-if="historyCount > 0" class="history-count">{{ historyCount }}</span>
      </button>
    </header>

    <div class="setup-grid">
      <!-- ============ 左：试卷结构 ============ -->
      <section class="panel panel-types">
        <div class="panel-head">
          <h3>试卷结构</h3>
          <span class="panel-hint">按题型设置题量与每题分值；题库里没有的题型会自动跳过</span>
        </div>

        <div class="type-table">
          <div class="type-row type-head">
            <span class="c-type">题型</span>
            <span class="c-count">题数</span>
            <span class="c-score">每题分值</span>
            <span class="c-sub">小计</span>
          </div>

          <div v-for="row in rows" :key="row.type" class="type-row" :class="{ 'is-empty': available[row.type] === 0 }">
            <span class="c-type">
              <span class="type-dot" :class="row.type"></span>
              {{ typeLabel(row.type) }}
              <em class="avail">/ {{ available[row.type] }} 道</em>
            </span>

            <span class="c-count">
              <el-input-number
                v-model="row.count"
                :min="0"
                :max="Math.max(0, available[row.type])"
                :step="1"
                :disabled="available[row.type] === 0"
                controls-position="right"
                size="default"
                @change="normalizeRow(row)"
              />
            </span>

            <span class="c-score">
              <el-input-number
                v-model="row.score"
                :min="0"
                :max="100"
                :step="0.5"
                :precision="1"
                :disabled="available[row.type] === 0 || row.count === 0"
                controls-position="right"
                size="default"
              />
            </span>

            <span class="c-sub">{{ formatScore(row.count * row.score) }} 分</span>
          </div>
        </div>

        <p v-if="totalCount === 0" class="empty-tip">
          <el-icon><WarningFilled /></el-icon>
          当前题库还没有可用题目，请先到题库里添加题目再来考试。
        </p>
      </section>

      <!-- ============ 右：考试规则 + 汇总 ============ -->
      <div class="right-col">
        <section class="panel">
          <div class="panel-head">
            <h3>考试规则</h3>
          </div>

          <div class="rule-row">
            <div class="rule-info">
              <span class="rule-label">考试时长</span>
              <span class="rule-desc">倒计时结束自动交卷</span>
            </div>
            <div class="rule-ctrl">
              <el-input-number v-model="form.timeLimit" :min="1" :max="600" :step="5" controls-position="right" size="default" />
              <span class="unit">分钟</span>
            </div>
          </div>

          <div class="rule-row">
            <div class="rule-info">
              <span class="rule-label">及格分</span>
              <span class="rule-desc">满分 {{ formatScore(totalScore) }} 分，及格线 {{ passPercent }}%</span>
            </div>
            <div class="rule-ctrl">
              <!--
                `:min="1"` 而不是 0（2026-10-22）：
                及格分设为 0 时「一分没得也算通过」，在考试场景里没有任何意义，
                还会让用户误以为系统判错了。要么定个真实分数线，要么就别开考。
              -->
              <el-input-number v-model="form.passScore" :min="1" :max="totalScore" :step="1" :precision="0" controls-position="right" size="default" />
              <span class="unit">分</span>
            </div>
          </div>

          <div class="rule-row">
            <div class="rule-info">
              <span class="rule-label">选项乱序</span>
              <span class="rule-desc">打乱每道题选项顺序，避免凭位置记忆</span>
            </div>
            <el-switch v-model="form.shuffleOptions" />
          </div>

          <div class="rule-row rule-row-col">
            <div class="rule-info">
              <span class="rule-label">多选题得分</span>
              <span class="rule-desc">漏选时如何计分</span>
            </div>
            <div class="mode-seg">
              <button type="button" :class="['seg', { active: form.multipleMode === 'strict' }]"
                @click="form.multipleMode = 'strict'">
                <strong>全对才得分</strong>
                <small>少选、错选均 0 分</small>
              </button>
              <button type="button" :class="['seg', { active: form.multipleMode === 'partial' }]"
                @click="form.multipleMode = 'partial'">
                <strong>漏选按比例得分</strong>
                <small>错选仍 0 分</small>
              </button>
            </div>
            <div v-if="form.multipleMode === 'partial'" class="ratio-row">
              <span class="ratio-label">每个正确选项得该题分值的</span>
              <el-select v-model="form.partialRatio" style="width: 96px" size="default">
                <el-option :value="0.25" label="25%" />
                <el-option :value="0.5" label="50%" />
                <el-option :value="0.75" label="75%" />
              </el-select>
            </div>
          </div>
        </section>

        <!-- 汇总卡 -->
        <section class="panel summary-panel">
          <div class="summary-grid">
            <div class="sum-item">
              <div class="sum-num">{{ totalCount }}</div>
              <div class="sum-label">总题数</div>
            </div>
            <div class="sum-item">
              <div class="sum-num">{{ formatScore(totalScore) }}</div>
              <div class="sum-label">满分</div>
            </div>
            <div class="sum-item">
              <div class="sum-num">{{ form.timeLimit }}</div>
              <div class="sum-label">分钟</div>
            </div>
          </div>

          <button class="start-btn" type="button" :disabled="!canStart" @click="handleStart">
            <el-icon><VideoPlay /></el-icon>
            <span>{{ canStart ? '开始考试' : '请先设置题目数量' }}</span>
          </button>

          <p class="summary-tip">
            开考后计时器立即启动；交卷后可在「考试记录」里回看每道题的作答与解析。
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ArrowLeft, Notebook, VideoPlay, WarningFilled } from '@element-plus/icons-vue'
import usePracticeSettingsStore, { DEFAULT_MOCK_EXAM } from '@/store/modules/practiceSettings'
import type { MockExamConfig, MockExamTypeRow, QuestionType } from '@/types'

const props = defineProps({
  bankId: { type: [Number, String], required: true },
  bankName: { type: String, default: '题库' },
  /**
   * 各题型的可选题量，形如 `{ single: 262, multiple: 116, truefalse: 110 }`
   *
   * ⚠️ 由父组件（PracticeComponent）拉完全部题目后算出来传进来。
   *    本组件**不自己发请求**：考试配置页不该为了显示"最多能抽几道"
   *    再去把整个题库拉一遍。
   */
  available: { type: Object as () => Record<string, number>, default: () => ({}) }
})

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'open-history'): void
  (e: 'start', payload: MockExamConfig): void
}>()

const store = usePracticeSettingsStore()

/** 历史记录条数（用于入口角标） */
const historyCount = computed(() => (store.mockExamHistory || []).length)

const TYPE_LABELS: Record<string, string> = {
  single: '单选题',
  multiple: '多选题',
  truefalse: '判断题',
  fillblank: '填空题',
  essay: '问答题'
}

function typeLabel(t: string) {
  return TYPE_LABELS[t] || t
}

/** 题库里可选的题量（父组件传入，缺省 0） */
const available = computed(() => props.available || {})

/**
 * 可配置的题型清单
 *
 * 只列这五种：阅读/完形是组合题（含子题），把它的"子题"当独立题目抽出来
 * 会破坏题干与子题的从属关系，所以模拟考试不按这两种组卷。
 */
const ROW_TYPES: QuestionType[] = ['single', 'multiple', 'truefalse', 'fillblank', 'essay']

const rows = reactive<MockExamTypeRow[]>([])

/** 表单其余字段 */
const form = reactive({
  timeLimit: 60,
  passScore: 60,
  shuffleOptions: true,
  multipleMode: 'strict' as 'strict' | 'partial',
  partialRatio: 0.5
})

/** 从 store 载入已有配置（用户上次调好的不该丢） */
function loadFromStore() {
  const cfg = store.getMockExamConfig()
  rows.splice(0, rows.length)
  for (const t of ROW_TYPES) {
    const found = (cfg.typeRows || []).find((r) => r.type === t)
    rows.push({
      type: t,
      count: found ? Number(found.count) || 0 : 0,
      score: found ? Number(found.score) || 0 : 1
    })
  }
  form.timeLimit = cfg.timeLimit ?? DEFAULT_MOCK_EXAM.timeLimit
  /*
   * 及格分兜底修复（2026-10-22）。
   *
   * 上一版有 bug：题数为 0 时 `watch(totalScore)` 会把及格分压成 0，再存盘。
   * 已经踩过的用户 localStorage 里就是 `passScore: 0` —— 光改 watch 不会
   * 自动修好他们盘上的存量数据，还得在这里读的时候纠正一次。
   *
   * 判定：`<= 0` 或非数字都视为"未设置"，回落到默认值（60）。
   */
  const savedPass = Number(cfg.passScore)
  form.passScore = Number.isFinite(savedPass) && savedPass > 0
    ? savedPass
    : DEFAULT_MOCK_EXAM.passScore
  form.shuffleOptions = cfg.shuffleOptions ?? true
  form.multipleMode = cfg.multipleMode ?? 'strict'
  form.partialRatio = cfg.partialRatio ?? 0.5
}

/**
 * 父组件传入可选题量后，把超出上限的题数收回来
 *
 * ⚠️ 「可选题量还没加载出来」和「这个题型一道题都没有」是两件事，
 *    不能都按 0 处理（2026-10-22 修的 bug）。
 *
 *    旧写法对 `cap === 0` 一律把 count 清零。而 `available` 初始是 `{}`，
 *    父组件要等一次网络往返才填上 —— 于是用户上次存好的配置
 *    （单选 20 道 / 多选 10 道…）在进入页面的一瞬间就被全部改写为 0，
 *    紧接着 `watch(totalScore)` 把及格分压成 0，再 `saveMockExamConfig`
 *    落盘。用户看到的就是「配置全没了、及格分变 0」。
 *
 *    现在：只在 `available` 里**确实有这个题型**时才夹取；
 *    没拿到（空对象）就整段跳过，等数据到了 `watch` 会再调一次。
 */
function clampToAvailable() {
  const avail = available.value || {}
  if (Object.keys(avail).length === 0) return
  for (const row of rows) {
    const cap = avail[row.type]
    if (cap === undefined) continue // 该题型没有数据，保持用户原值
    if (row.count > cap) row.count = cap
  }
}

function normalizeRow(row: MockExamTypeRow) {
  const cap = available.value[row.type] ?? 0
  if (row.count > cap) row.count = cap
  if (row.count < 0) row.count = 0
  // 有题数但没分值 → 给个 1 分兜底，否则小计恒为 0，用户会以为算错了
  if (row.count > 0 && (!row.score || row.score <= 0)) row.score = 1
}

watch(() => props.available, clampToAvailable, { deep: true })

const totalCount = computed(() => rows.reduce((s, r) => s + (Number(r.count) || 0), 0))
const totalScore = computed(() =>
  rows.reduce((s, r) => s + (Number(r.count) || 0) * (Number(r.score) || 0), 0)
)
const passPercent = computed(() =>
  totalScore.value > 0 ? Math.round((form.passScore / totalScore.value) * 100) : 0
)
const canStart = computed(() => totalCount.value > 0 && totalScore.value > 0)

/** 分值展示：整数不带小数点，有小数时最多一位 */
function formatScore(n: number) {
  const v = Math.round((Number(n) || 0) * 10) / 10
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

/**
 * 及格分与满分的联动
 *
 * ⚠️ 两条规则都踩过坑（2026-10-22）：
 *
 * ① **满分没算出来时不夹取**。
 *    `totalScore` 在题数全为 0 时也是 0，旧写法会把及格分直接压成 0，
 *    并被 `handleStart` 存进 localStorage —— 于是"一分没得也算通过"。
 *
 * ② **超出满分时回落到 60%，而不是夹到满分**。
 *    默认及格分是 60（按 100 分卷设计）。用户把卷子改成「5 道 × 2 分 = 10 分」后，
 *    若简单夹成 `10`，及格线就成了「必须满分」，等于不可能通过。
 *    按 60% 回落才是符合直觉的默认。
 */
watch(totalScore, (v) => {
  if (v <= 0) return
  if (form.passScore > v) form.passScore = Math.max(1, Math.round(v * 0.6))
})

function handleStart() {
  if (!canStart.value) return
  const cfg: MockExamConfig = {
    // 只保留有题数的题型，避免空行进入组卷逻辑
    typeRows: rows
      .filter((r) => (Number(r.count) || 0) > 0)
      .map((r) => ({ type: r.type, count: Number(r.count), score: Number(r.score) || 1 })),
    timeLimit: Number(form.timeLimit) || 60,
    /*
     * 及格分下限兜底：`|| 0` 会让"用户把输入框清空"变成 0 分及格。
     * 这里保底 1 分，并且不超过满分。
     */
    passScore: Math.min(
      Math.max(1, Number(form.passScore) || 1),
      Math.max(1, totalScore.value)
    ),
    shuffleOptions: !!form.shuffleOptions,
    multipleMode: form.multipleMode,
    partialRatio: Number(form.partialRatio) || 0.5
  }
  store.saveMockExamConfig(cfg)
  emit('start', cfg)
}

loadFromStore()
clampToAvailable()
</script>

<style scoped>
/* ============================================================================
 * 视觉口径：与全站 DSH 设计令牌一致（--os-*），不引入新的色板。
 * 布局：左「试卷结构」右「规则 + 汇总」，窄屏塌成单列。
 * ==========================================================================*/
.mock-setup {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px 28px 40px;
  max-width: 1180px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

/* ---------- 顶部 ---------- */
.setup-head {
  display: flex;
  align-items: center;
  gap: 18px;
}

.back-btn,
.history-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: var(--os-bg, #fff);
  color: var(--os-text-2, #4b5563);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  flex: none;
}

.back-btn:hover,
.history-btn:hover {
  background: var(--os-bg-subtle, #f9fafb);
  border-color: var(--os-border-strong, #d1d5db);
  color: var(--os-text, #111827);
}

.history-btn {
  margin-left: auto;
  position: relative;
}

.history-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--os-primary, #0f1115);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.head-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.head-main h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 600;
  color: var(--os-text, #111827);
  letter-spacing: -0.01em;
}

.head-sub {
  margin: 0;
  font-size: 12.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 两栏 ---------- */
.setup-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

@media (max-width: 900px) {
  .setup-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.right-col {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel {
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 14px;
  background: var(--os-bg, #fff);
  padding: 18px 20px 20px;
}

.panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.panel-head h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.panel-hint {
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 题型表 ---------- */
.type-table {
  display: flex;
  flex-direction: column;
}

.type-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.4fr) 130px 130px 90px;
  align-items: center;
  gap: 12px;
  padding: 9px 4px;
  border-bottom: 1px solid var(--os-border-subtle, #f1f3f5);
  font-size: 13px;
}

.type-row:last-child {
  border-bottom: none;
}

.type-head {
  padding-bottom: 6px;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
  font-weight: 500;
}

.type-row.is-empty {
  opacity: 0.55;
}

.c-type {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--os-text, #111827);
}

.type-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}

.type-dot.single {
  background: #3b82f6;
}

.type-dot.multiple {
  background: #8b5cf6;
}

.type-dot.truefalse {
  background: #10b981;
}

.type-dot.fillblank {
  background: #f59e0b;
}

.type-dot.essay {
  background: #ef4444;
}

.avail {
  font-size: 11.5px;
  font-style: normal;
  color: var(--os-text-4, #9ca3af);
}

.c-sub {
  font-size: 12.5px;
  color: var(--os-text-2, #4b5563);
  text-align: right;
}

.empty-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 14px 0 0;
  padding: 10px 12px;
  border-radius: 9px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
  font-size: 12.5px;
}

/* ---------- 规则行 ---------- */
.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid var(--os-border-subtle, #f1f3f5);
}

.rule-row:last-child {
  border-bottom: none;
}

.rule-row-col {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.rule-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.rule-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--os-text, #111827);
}

.rule-desc {
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

.rule-ctrl {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: none;
}

.unit {
  font-size: 12.5px;
  color: var(--os-text-3, #6b7280);
}

/* 多选得分模式分段器 */
.mode-seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.seg {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: var(--os-bg, #fff);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.seg strong {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.seg small {
  font-size: 11px;
  color: var(--os-text-4, #9ca3af);
}

.seg:hover {
  border-color: var(--os-border-strong, #d1d5db);
}

.seg.active {
  border-color: var(--os-primary, #0f1115);
  background: var(--os-bg-subtle, #f9fafb);
}

.ratio-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

/* ---------- 汇总 ---------- */
.summary-panel {
  position: sticky;
  top: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.sum-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 13px 6px;
  border-radius: 11px;
  background: var(--os-bg-subtle, #f9fafb);
  border: 1px solid var(--os-border-subtle, #f1f3f5);
}

.sum-num {
  font-size: 21px;
  font-weight: 650;
  line-height: 1.1;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.sum-label {
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

.start-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  height: 42px;
  border: none;
  border-radius: 11px;
  background: var(--os-primary, #0f1115);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease, transform 0.1s ease;
}

.start-btn:hover:not(:disabled) {
  opacity: 0.88;
}

.start-btn:active:not(:disabled) {
  transform: scale(0.995);
}

.start-btn:disabled {
  background: var(--os-border, #e5e7eb);
  color: var(--os-text-4, #9ca3af);
  cursor: not-allowed;
}

.summary-tip {
  margin: 11px 0 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--os-text-4, #9ca3af);
}
</style>
