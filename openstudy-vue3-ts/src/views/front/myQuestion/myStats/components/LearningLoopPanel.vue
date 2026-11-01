<template>
  <section class="panel loop-panel">
    <div v-if="loading" class="loop-loading">
      <el-icon class="is-loading" :size="18"><Loading /></el-icon>
      <span>正在整理你的学习闭环…</span>
    </div>

    <div v-else-if="!data || !data.hasData" class="loop-empty">
      <div class="loop-empty-mark">
        <el-icon :size="24"><TrendCharts /></el-icon>
      </div>
      <div>
        <div class="loop-empty-title">学习闭环还没有启动</div>
        <div class="loop-empty-desc">先做几道题，系统会根据你的作答记录生成今日处方和知识体检。</div>
      </div>
      <el-button type="primary" plain @click="emit('practice')">去题库练习</el-button>
    </div>

    <template v-else>
      <div class="loop-head">
        <div class="loop-head-main">
          <div class="loop-head-title">
            <h2>今日学习处方</h2>
            <span class="loop-head-chip">今日</span>
          </div>
          <p>{{ data.headline }}</p>
        </div>
        <div class="loop-head-meta">
          <span><b>{{ data.todayPlan.length }}</b> 个动作</span>
          <span class="loop-head-divider"></span>
          <span>预计 {{ todayMinutes }} 分钟</span>
        </div>
      </div>

      <div class="loop-plan">
        <article
          v-for="(task, index) in data.todayPlan"
          :key="task.id"
          class="loop-task"
          role="button"
          tabindex="0"
          @click="emit('openQuestion', task)"
          @keyup.enter="emit('openQuestion', task)"
        >
          <span class="loop-task-index">0{{ index + 1 }}</span>
          <div class="loop-task-body">
            <div class="loop-task-title" v-html="renderQuestionContent(task.title)"></div>
            <div class="loop-task-reason">{{ task.reason }}</div>
            <div v-if="task.advice" class="loop-task-advice">{{ task.advice }}</div>
          </div>
          <div class="loop-task-side">
            <span class="loop-task-time">{{ task.estimatedMinutes }} 分钟</span>
            <span class="loop-task-go">开始 <el-icon><ArrowRight /></el-icon></span>
          </div>
        </article>
        <div v-if="!data.todayPlan.length" class="loop-no-task">
          当前没有需要立即处理的薄弱题，继续保持节奏。
        </div>
      </div>

      <div class="loop-columns">
        <div class="loop-card health-card">
          <div class="loop-card-head">
            <div>
              <h3>知识体检图</h3>
              <span>圆环是正确率，红色标记是需要优先处理的科目</span>
            </div>
            <span class="loop-card-meta">{{ healthNodes.length }} 个科目</span>
          </div>

          <div v-if="healthNodes.length" class="health-grid">
            <button
              v-for="node in healthNodes"
              :key="node.subject"
              type="button"
              class="health-node"
              :class="[`is-${node.status}`, { 'is-active': activeHealthNode?.subject === node.subject }]"
              @click="pickSubject(node)"
            >
              <div class="health-node-head">
                <span class="health-node-name">{{ node.subject }}</span>
                <span class="health-node-status">{{ node.statusText }}</span>
              </div>
              <div class="health-node-main">
                <div class="health-ring-wrap">
                  <svg class="health-ring" viewBox="0 0 56 56" aria-hidden="true">
                    <circle class="health-ring-track" cx="28" cy="28" r="24" />
                    <circle
                      class="health-ring-value"
                      cx="28"
                      cy="28"
                      r="24"
                      :stroke="node.color"
                      :stroke-dasharray="ringDash(node.accuracy)"
                    />
                  </svg>
                  <span class="health-ring-num">{{ node.accuracy }}<i>%</i></span>
                </div>
                <div class="health-node-facts">
                  <span><b>{{ node.questions }}</b> 道题做过</span>
                  <span><b :style="{ color: node.color }">{{ node.weakCount }}</b> 个待攻克</span>
                </div>
              </div>
            </button>
          </div>
          <div v-else class="loop-card-empty">还没有足够的科目数据来生成体检图</div>

          <div v-if="activeHealthNode" class="health-detail">
            <div class="health-detail-head">
              <span class="health-detail-subject">
                <i class="health-detail-dot" :style="{ background: activeHealthNode.color }"></i>
                {{ activeHealthNode.subject }} · 最该先处理的
              </span>
              <span class="health-detail-meta">{{ activeHealthNode.weakCount }} 个薄弱点</span>
            </div>
            <div v-if="activeHealthNode.weakQuestions?.length" class="health-detail-list">
              <div
                v-for="weak in activeHealthNode.weakQuestions"
                :key="weak.questionId"
                class="health-detail-item"
                role="button"
                tabindex="0"
                @click="emit('openQuestion', weak)"
                @keyup.enter="emit('openQuestion', weak)"
              >
                <span class="health-detail-level">{{ weak.levelText }}</span>
                <span class="health-detail-text" v-html="renderQuestionContent(weak.questionText)"></span>
                <el-icon class="health-detail-go"><ArrowRight /></el-icon>
              </div>
            </div>
            <div v-else class="health-detail-empty">这一科暂时没有需要立刻处理的题</div>
          </div>

          <div v-if="healthNodes.length" class="health-legend">
            <span><i class="dot is-strong"></i>稳固</span>
            <span><i class="dot is-watch"></i>观察中</span>
            <span><i class="dot is-weak"></i>待攻克</span>
            <span class="health-tip">点击科目切换，点击题目直接开练</span>
          </div>
        </div>

        <div class="loop-card battle-card">
          <div class="loop-card-head">
            <div>
              <h3>错题歼灭战</h3>
              <span>把“错过”变成“不会再错”</span>
            </div>
            <span class="battle-progress-text">{{ data.errorBattle.progress }}%</span>
          </div>

          <div class="battle-progress">
            <div class="battle-progress-fill" :style="{ width: `${Math.min(data.errorBattle.progress, 100)}%` }"></div>
          </div>
          <div class="battle-stats">
            <span><b class="is-cleared">{{ data.errorBattle.cleared }}</b> 已歼灭</span>
            <span><b class="is-observing">{{ data.errorBattle.observing }}</b> 观察期</span>
            <span><b class="is-active">{{ data.errorBattle.active }}</b> 待攻克</span>
          </div>

          <div v-if="battleTargets.length" class="battle-list">
            <div
              v-for="target in battleTargets"
              :key="target.questionId"
              class="battle-item"
              role="button"
              tabindex="0"
              @click="emit('openQuestion', target)"
              @keyup.enter="emit('openQuestion', target)"
            >
              <span
                class="battle-level"
                :class="target.stage === 'observing' ? 'is-observing' : `is-${target.level}`"
              >{{ target.stage === 'observing' ? '观察中' : target.levelText }}</span>
              <span class="battle-text" v-html="renderQuestionContent(target.questionText)"></span>
              <span v-if="target.stage === 'observing'" class="battle-streak">连对 {{ target.streak }}</span>
              <el-icon class="battle-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
          <div v-else class="loop-card-empty">暂时没有待攻克错题</div>

          <div class="battle-foot">
            <span class="battle-foot-dot"></span>
            连续答对 2 次进入观察期，连续答对 4 次判定为已歼灭
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Loading, TrendCharts, ArrowRight } from '@element-plus/icons-vue'
import {
  getLearningLoop,
  type LearningLoopHealthNode,
  type LearningLoopResult
} from '@/api/userStats/userStats'
import { renderQuestionContent } from '@/utils/latex'

const emit = defineEmits<{
  (e: 'practice'): void
  (e: 'openQuestion', item: { questionId: number }): void
}>()

const loading = ref(true)
const data = ref<LearningLoopResult | null>(null)
const selectedSubject = ref('')

const healthNodes = computed<LearningLoopHealthNode[]>(() => data.value?.healthMap || [])
const battleTargets = computed(() => data.value?.errorBattle.targets || [])
const todayMinutes = computed(() =>
  (data.value?.todayPlan || []).reduce((sum, task) => sum + (task.estimatedMinutes || 0), 0)
)
const activeHealthNode = computed<LearningLoopHealthNode | null>(() => {
  const nodes = healthNodes.value
  if (!nodes.length) return null
  return nodes.find((node) => node.subject === selectedSubject.value) || nodes[0]
})

function pickSubject(node: LearningLoopHealthNode) {
  selectedSubject.value = node.subject
}

/** 圆环周长 = 2π × 24 ≈ 150.8 */
function ringDash(accuracy: number) {
  const value = Math.max(0, Math.min(100, Number(accuracy) || 0))
  return `${(value / 100) * 150.8} 151`
}

async function load() {
  loading.value = true
  try {
    const res: any = await getLearningLoop()
    if (res.code === 200) {
      data.value = res.data
      selectedSubject.value = res.data?.healthMap?.[0]?.subject || ''
    }
  } catch (e: any) {
    console.warn('[学习闭环] 加载失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.loop-panel {
  position: relative;
  overflow: hidden;
}

.loop-loading,
.loop-empty {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 120px;
  padding: 22px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
  color: var(--os-text-4, #adb2b8);
}

.loop-empty-mark {
  display: grid;
  width: 44px;
  height: 44px;
  flex: none;
  place-items: center;
  border-radius: var(--os-radius-sm, 8px);
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
}

.loop-empty-title {
  color: var(--os-text, #0f1115);
  font-weight: 600;
}

.loop-empty-desc {
  margin-top: 3px;
  font-size: 12px;
}

.loop-empty .el-button {
  margin-left: auto;
}

.loop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
}

.loop-head-main {
  min-width: 0;
}

.loop-head-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loop-head-title h2 {
  margin: 0;
  color: var(--os-text, #0f1115);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.loop-head-chip {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--os-accent-soft, #edf3fe);
  color: var(--dsw-static-blue-800, #1e40af);
  font-size: 10px;
  line-height: 1.4;
}

.loop-head-main p {
  margin: 6px 0 0;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  line-height: 1.6;
}

.loop-head-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  white-space: nowrap;
}

.loop-head-meta b {
  color: var(--os-text, #0f1115);
  font-size: 14px;
  font-weight: 600;
}

.loop-head-divider {
  width: 1px;
  height: 12px;
  background: var(--os-border-strong, rgba(0, 0, 0, 0.1));
}

.loop-plan {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.loop-task {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 108px;
  padding: 14px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius-sm, 8px);
  background: #fff;
  cursor: pointer;
  transition: border-color var(--ds-duration-fast, 0.15s) ease, background-color var(--ds-duration-fast, 0.15s) ease;
}

.loop-task:hover {
  border-color: var(--os-border-strong, rgba(0, 0, 0, 0.1));
  background: var(--os-bg-subtle, #f9fafb);
}

.loop-task-index {
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.loop-task-body {
  min-width: 0;
  flex: 1;
}

.loop-task-title {
  display: -webkit-box;
  overflow: hidden;
  color: var(--os-text, #111827);
  font-size: 13px;
  font-weight: 600;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.5;
}

.loop-task-title :deep(.katex),
.health-detail-text :deep(.katex),
.battle-text :deep(.katex) {
  font-size: 1em;
}

.loop-task-reason,
.loop-task-advice {
  display: -webkit-box;
  overflow: hidden;
  margin-top: 6px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.loop-task-advice {
  color: #2563eb;
}

.loop-task-side {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  justify-content: space-between;
  align-self: stretch;
}

.loop-task-time {
  color: #94a3b8;
  font-size: 10px;
  white-space: nowrap;
}

.loop-task-go {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #2563eb;
  font-size: 11px;
  white-space: nowrap;
}

.loop-no-task {
  grid-column: 1 / -1;
  padding: 20px;
  border: 1px dashed var(--os-border-strong, rgba(0, 0, 0, 0.1));
  border-radius: var(--os-radius-sm, 8px);
  color: var(--os-text-4, #adb2b8);
  font-size: 12px;
  text-align: center;
}

.loop-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  gap: 12px;
  margin-top: 12px;
}

.loop-card {
  padding: 16px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius-sm, 8px);
  background: #fff;
}

.loop-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.loop-card-head h3 {
  margin: 0;
  color: var(--os-text, #0f1115);
  font-size: 14px;
  font-weight: 600;
}

.loop-card-head span {
  display: block;
  margin-top: 3px;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.loop-card-meta {
  margin-top: 0 !important;
  color: var(--os-text-3, #81858c) !important;
  white-space: nowrap;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.health-node {
  display: block;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius-sm, 8px);
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--ds-duration-fast, 0.15s) ease, background-color var(--ds-duration-fast, 0.15s) ease;
}

.health-node:hover {
  border-color: var(--os-border-strong, rgba(0, 0, 0, 0.1));
  background: var(--os-bg-subtle, #f9fafb);
}

.health-node.is-active {
  border-color: var(--os-accent, #4176e6);
  background: var(--os-accent-soft, #edf3fe);
}

.health-node-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.health-node-name {
  overflow: hidden;
  color: #1f2937;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-node-status {
  flex: none;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
}

.health-node.is-weak .health-node-status { background: #fff1f0; color: #cf1322; }
.health-node.is-watch .health-node-status { background: #fff7e6; color: #d46b08; }
.health-node.is-strong .health-node-status { background: #ecfdf5; color: #047857; }

.health-node-main {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.health-ring-wrap {
  position: relative;
  width: 58px;
  height: 58px;
  flex: none;
}

.health-ring {
  width: 58px;
  height: 58px;
  transform: rotate(-90deg);
}

.health-ring-track,
.health-ring-value {
  fill: none;
  stroke-width: 6;
}

.health-ring-track { stroke: #eef2f7; }

.health-ring-value {
  stroke-linecap: round;
  transition: stroke-dasharray 0.5s ease;
}

.health-ring-num {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #1f2937;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.health-ring-num i {
  margin-left: 1px;
  color: #94a3b8;
  font-size: 9px;
  font-style: normal;
}

.health-node-facts {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  color: #64748b;
  font-size: 11px;
}

.health-node-facts b {
  color: #1f2937;
  font-size: 13px;
}

.health-detail {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
}

.health-detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.health-detail-subject {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
}

.health-detail-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.health-detail-meta {
  color: #94a3b8;
  font-size: 10px;
  white-space: nowrap;
}

.health-detail-list {
  margin-top: 6px;
}

.health-detail-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 0;
  border-top: 1px solid #eef2f7;
  cursor: pointer;
}

.health-detail-item:hover .health-detail-text {
  color: #2563eb;
}

.health-detail-level {
  flex: none;
  padding: 1px 5px;
  border-radius: 3px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 9px;
}

.health-detail-text {
  overflow: hidden;
  flex: 1;
  color: #475569;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-detail-go {
  flex: none;
  color: #cbd5e1;
  font-size: 11px;
}

.health-detail-empty {
  padding-top: 6px;
  color: #94a3b8;
  font-size: 11px;
}

.health-legend {
  display: flex;
  align-items: center;
  gap: 13px;
  margin-top: 10px;
  color: #64748b;
  font-size: 10px;
}

.health-legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.health-legend .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot.is-strong { background: #3fa06a; }
.dot.is-watch { background: #e8a33a; }
.dot.is-weak { background: #e5534b; }

.health-tip {
  margin-left: auto;
  color: #94a3b8;
}

.loop-card-empty {
  display: flex;
  min-height: 150px;
  align-items: center;
  justify-content: center;
  color: var(--os-text-4, #adb2b8);
  font-size: 12px;
}

.battle-progress-text {
  color: var(--os-text, #0f1115) !important;
  font-size: 16px !important;
  font-weight: 600;
}

.battle-progress {
  height: 6px;
  margin-top: 16px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--os-border-soft, #f1f3f5);
}

.battle-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--os-accent, #4176e6);
  transition: width 0.4s ease;
}

.battle-stats {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  color: var(--os-text-3, #81858c);
  font-size: 11px;
}

.battle-stats b {
  color: #111827;
  font-size: 14px;
}

.battle-stats b.is-cleared { color: #3fa06a; }
.battle-stats b.is-observing { color: #d97706; }
.battle-stats b.is-active { color: #dc2626; }

.battle-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 15px;
}

.battle-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-top: 1px solid #f1f5f9;
  cursor: pointer;
}

.battle-item:hover .battle-text {
  color: #2563eb;
}

.battle-level {
  flex: none;
  max-width: 62px;
  overflow: hidden;
  padding: 2px 6px;
  border-radius: 4px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.battle-level.is-lapsing { background: #fff7e6; color: #d46b08; }
.battle-level.is-overdue { background: #fffbe6; color: #ad8b00; }
.battle-level.is-due_soon { background: #f0f5ff; color: #2f54eb; }
.battle-level.is-observing { background: #ecfdf5; color: #047857; }

.battle-streak {
  flex: none;
  color: #059669;
  font-size: 10px;
  white-space: nowrap;
}

.battle-text {
  display: -webkit-box;
  overflow: hidden;
  flex: 1;
  color: #334155;
  font-size: 11px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.battle-arrow {
  flex: none;
  color: #cbd5e1;
}

.battle-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed #eef2f7;
  color: #94a3b8;
  font-size: 10px;
}

.battle-foot-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #60a5fa;
}

@media (max-width: 980px) {
  .loop-plan,
  .loop-columns {
    grid-template-columns: 1fr;
  }
}
</style>
