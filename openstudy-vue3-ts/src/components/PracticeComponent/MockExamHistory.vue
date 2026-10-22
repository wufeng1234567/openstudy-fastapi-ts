<!--
  模拟考试历史记录（2026-10-22）

  布局取舍：列表用「卡片 + 左侧对错条」，而不是表格。
    表格适合字段对齐（管理员场景），但这里的核心信息是"这次考得怎么样"——
    一个数字 + 一条对错占比条，比 6 列表格更容易一眼看完。
    卡片在窄屏也能自然堆叠，不需要横向滚动。

  交互：点卡片 → 复用 `ExamSummary` 回看该次考试的完整结果。
    不另写一套"历史详情"页面：总结页本来就是"展示一场考试的结果"，
    它接受的只是一个 `MockExamRecord`，历史点的也是同一份结构。
-->
<template>
  <div class="exam-history">
    <header class="history-head">
      <button class="back-btn" type="button" @click="$emit('cancel')">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </button>
      <div class="head-main">
        <h2>考试记录</h2>
        <p class="head-sub">共 {{ records.length }} 次考试<template v-if="bankName"> · {{ bankName }}</template></p>
      </div>
      <button v-if="records.length" class="danger-btn" type="button" @click="handleClearAll">
        <el-icon><Delete /></el-icon>
        <span>清空记录</span>
      </button>
    </header>

    <!-- 空态 -->
    <div v-if="!records.length" class="empty-state">
      <div class="empty-icon">
        <el-icon><Notebook /></el-icon>
      </div>
      <p class="empty-title">还没有考试记录</p>
      <p class="empty-desc">完成一次模拟考试并交卷后，这里会保留你的成绩与错题明细，方便复盘。</p>
    </div>

    <!-- 列表 -->
    <div v-else class="record-list">
      <article
        v-for="r in records"
        :key="r.id"
        class="record-card"
        :class="{ 'is-pass': r.passed }"
        @click="$emit('open-record', r)"
      >
        <!-- 左：对错占比条（竖向） -->
        <div class="rc-bar" :title="`答对 ${r.correctCount} / 共 ${r.totalQuestions}`">
          <div class="rc-bar-ok" :style="{ height: correctPercent(r) + '%' }"></div>
        </div>

        <!-- 中：主信息 -->
        <div class="rc-main">
          <div class="rc-top">
            <span class="rc-badge" :class="r.passed ? 'is-pass' : 'is-fail'">
              {{ r.passed ? '通过' : '未通过' }}
            </span>
            <span class="rc-score">{{ formatScore(r.gotScore) }}<em>/{{ formatScore(r.fullScore) }} 分</em></span>
            <span class="rc-time">{{ formatTime(r.submittedAt) }}</span>
          </div>
          <div class="rc-meta">
            <span>{{ r.totalQuestions }} 题</span>
            <span class="dot">·</span>
            <span>正确率 {{ accuracy(r) }}%</span>
            <span class="dot">·</span>
            <span>用时 {{ formatDuration(r.durationSec) }}</span>
            <span v-if="r.wrongCount > 0" class="dot">·</span>
            <span v-if="r.wrongCount > 0" class="rc-wrong">{{ r.wrongCount }} 道错题</span>
          </div>
        </div>

        <!-- 右：操作 -->
        <div class="rc-actions">
          <button class="rc-open" type="button" @click.stop="$emit('open-record', r)">
            查看详情
            <el-icon><ArrowRight /></el-icon>
          </button>
          <button class="rc-del" type="button" title="删除这条记录" @click.stop="handleRemove(r)">
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Delete, Notebook } from '@element-plus/icons-vue'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import type { MockExamRecord } from '@/types'

const props = defineProps({
  bankId: { type: [Number, String], default: null },
  bankName: { type: String, default: '' }
})

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'open-record', record: MockExamRecord): void
}>()

const store = usePracticeSettingsStore()

/**
 * 记录列表
 *
 * 传了 `bankId` 就只看这个题库的；没传则看全部。
 * 这个筛选放在前端做：历史本来就全在 localStorage 里，不需要额外接口。
 */
const records = computed<MockExamRecord[]>(() => {
  const all = (store.mockExamHistory || []) as MockExamRecord[]
  const sorted = [...all].sort((a, b) => b.submittedAt - a.submittedAt)
  if (props.bankId === null || props.bankId === undefined || props.bankId === '') return sorted
  return sorted.filter((r) => String(r.bankId) === String(props.bankId))
})

function correctPercent(r: MockExamRecord) {
  if (!r.totalQuestions) return 0
  return Math.max(0, Math.min(100, Math.round((r.correctCount / r.totalQuestions) * 100)))
}

function accuracy(r: MockExamRecord) {
  return correctPercent(r)
}

function formatScore(n: number) {
  const v = Math.round((Number(n) || 0) * 10) / 10
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

function formatDuration(sec: number) {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m} 分 ${r} 秒` : `${r} 秒`
}

function formatTime(ts: number) {
  try {
    const d = new Date(ts)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return ''
  }
}

async function handleRemove(r: MockExamRecord) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${formatTime(r.submittedAt)} 这场考试的记录吗？删除后无法恢复。`,
      '删除记录',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', closeOnClickModal: false }
    )
    store.removeMockExamRecord(r.id)
  } catch {
    /* 用户取消 */
  }
}

async function handleClearAll() {
  try {
    await ElMessageBox.confirm(
      `确定清空全部 ${records.value.length} 条考试记录吗？清空后无法恢复。`,
      '清空记录',
      { confirmButtonText: '清空', cancelButtonText: '取消', type: 'warning', closeOnClickModal: false }
    )
    if (props.bankId === null || props.bankId === undefined || props.bankId === '') {
      store.clearMockExamHistory()
    } else {
      // 只清当前题库的：逐条删，保留其他题库的记录
      for (const r of records.value) store.removeMockExamRecord(r.id)
    }
  } catch {
    /* 用户取消 */
  }
}
</script>

<style scoped>
.exam-history {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px 28px 48px;
  max-width: 980px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

/* ---------- 顶部 ---------- */
.history-head {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn,
.danger-btn {
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

.back-btn:hover {
  background: var(--os-bg-subtle, #f9fafb);
  border-color: var(--os-border-strong, #d1d5db);
}

.danger-btn {
  margin-left: auto;
  color: #b91c1c;
  border-color: #fecaca;
}

.danger-btn:hover {
  background: #fef2f2;
  border-color: #fca5a5;
}

.head-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.head-main h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.head-sub {
  margin: 0;
  font-size: 12.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 空态 ---------- */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 64px 24px;
  border: 1px dashed var(--os-border, #e5e7eb);
  border-radius: 16px;
  background: var(--os-bg-subtle, #fafbfc);
  text-align: center;
}

.empty-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #eef2ff;
  color: #6366f1;
  font-size: 24px;
  margin-bottom: 4px;
}

.empty-title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.empty-desc {
  margin: 0;
  max-width: 420px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 记录卡片 ---------- */
.record-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.record-card {
  display: flex;
  align-items: stretch;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 13px;
  background: var(--os-bg, #fff);
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.12s ease;
}

.record-card:hover {
  border-color: var(--os-border-strong, #d1d5db);
  box-shadow: 0 2px 12px rgba(15, 17, 21, 0.05);
  transform: translateY(-1px);
}

/* 左侧竖向对错占比条 */
.rc-bar {
  width: 5px;
  border-radius: 3px;
  background: #f1f3f5;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  flex: none;
}

.rc-bar-ok {
  width: 100%;
  background: #10b981;
  border-radius: 3px;
  transition: height 0.3s ease;
}

/* 中间主信息 */
.rc-main {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 0;
}

.rc-top {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.rc-badge {
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  flex: none;
}

.rc-badge.is-pass {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}

.rc-badge.is-fail {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.rc-score {
  font-size: 17px;
  font-weight: 650;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.rc-score em {
  font-style: normal;
  font-size: 12px;
  font-weight: 400;
  color: var(--os-text-4, #9ca3af);
  margin-left: 2px;
}

.rc-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
  font-variant-numeric: tabular-nums;
}

.rc-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--os-text-3, #6b7280);
  flex-wrap: wrap;
}

.rc-meta .dot {
  color: #d1d5db;
}

.rc-wrong {
  color: #b91c1c;
  font-weight: 500;
}

/* 右侧操作 */
.rc-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.rc-open {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: var(--os-bg, #fff);
  color: var(--os-text-2, #4b5563);
  font-size: 12.5px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.rc-open:hover {
  background: var(--os-bg-subtle, #f9fafb);
  border-color: var(--os-border-strong, #d1d5db);
}

.rc-del {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--os-text-4, #9ca3af);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.rc-del:hover {
  background: #fef2f2;
  color: #b91c1c;
}

@media (max-width: 640px) {
  .rc-actions {
    flex-direction: column;
  }
  .rc-time {
    margin-left: 0;
  }
}
</style>
