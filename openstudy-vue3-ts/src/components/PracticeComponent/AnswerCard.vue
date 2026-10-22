<template>
  <div class="answer-card">
    <div class="card-header">
      <!-- 左列：标题 -->
      <div class="header-left">
        <h4>答题卡</h4>
      </div>

      <!-- 中列：模式标签 + 切换图标 -->
      <div class="header-center">
        <div class="mode-group">
          <el-tag size="small" :type="isOverviewMode ? 'primary' : 'info'" effect="plain" round>
            {{ isOverviewMode ? '整体浏览' : '逐题模式' }}
          </el-tag>
          <el-tooltip :content="isOverviewMode ? '切换为逐题模式' : '切换为整体浏览'" placement="top">
            <el-button :icon="isOverviewMode ? List : Grid" circle size="small" @click="$emit('toggle-overview')" />
          </el-tooltip>
        </div>
      </div>

      <!-- 右列：重新练习（「暂存」已移到面板底部，见下方 .card-footer） -->
      <div class="header-right">
        <el-button text size="small" @click="$emit('reset-practice')">重新练习</el-button>
      </div>
    </div>

    <!-- 正常模式：题号网格（原样保留） -->
    <template v-if="!isOverviewMode">
      <div class="question-grid">
        <div v-for="(item, index) in questions" :key="index" class="grid-item" :class="{
          answered: item.answered,
          correct: !isExamMode && item.correct && item.answered,
          wrong: !isExamMode && !item.correct && item.answered,
          current: index === currentQuestionIndex
        }" @click="$emit('go-to-question', index)">
          <!-- 题号跨波顺延：波内下标 + 本波起点偏移（用户 2026-10-18） -->
          {{ numberBase + index + 1 }}
        </div>
      </div>

      <div class="stats">
        <!-- 刷题模式：显示进度 -->
        <template v-if="isPracticeMode">
          <div class="progress-text">已刷：{{ answeredCount }} / {{ totalCount }} 题</div>
          <div class="progress-hint" v-if="remainingCount > 0">剩余 {{ remainingCount }} 题待练习</div>
        </template>

        <!-- 考试模式：显示总分 -->
        <template v-else-if="isExamMode && showExamResult">
          <div class="total-score">总分：{{ totalScore }} 分</div>
          <el-button v-if="moduleType === 'mock'" type="primary" size="small" @click="$emit('finish-exam')">
            结束考试
          </el-button>
        </template>

        <!-- 模拟考试提交后（非考试模式）：显示结束按钮 -->
        <template v-else-if="moduleType === 'mock' && showExamResult">
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
          <el-button type="primary" size="small" @click="$emit('finish-exam')">
            结束考试
          </el-button>
        </template>

        <!--
          考试模式：分数区
          ⚠️ 交卷按钮已经移到下面 footer 的考试态区块（2026-10-20），
             这里只保留分数占位，避免同一屏出现两个「交卷」。
          ⚠️ 原来这里是 `v-else-if="isExamMode && !isLastQuestion"` ——
             意味着**最后一题时交卷按钮消失**，用户做到最后一题反而没法交卷，
             只能再点一遍"下一题"去触发别的路径。这是明显的逻辑漏洞，
             现在交卷放在 footer 常驻（考试态一直可见），不再依赖"是不是最后一题"。
        -->
        <template v-else-if="isExamMode && !showExamResult">
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
        </template>

        <!-- 默认统计（预览模式等） -->
        <template v-else>
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
        </template>
      </div>
    </template>

    <!-- 整体浏览模式：分组展示 -->
    <template v-else>
      <div class="overview-card-body">
        <div v-for="group in questionGroups" :key="group.typeName" class="group-section">
          <div class="group-title">{{ group.typeLabel }}（共 {{ group.items.length }} 题）</div>
          <div class="group-grid">
            <div v-for="q in group.items" :key="q.index" :ref="el => setGridItemRef(el, q.index)"
              class="grid-item overview-grid-item" :class="getOverviewItemClass(q.index)"
              @click="$emit('go-to-question', q.index)">
              {{ numberBase + q.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </template>

    <!--
      底部区块：练习态显示「暂存」，考试态显示「交卷引导」
      ================================================================
      ⚠️ 为什么模拟考试**不能**有暂存按钮（2026-10-20 用户反馈：
         「模拟考试不该出现暂存按钮 需要进行单独的优化」）：

        暂存按钮传达的是「你可以随时中断，进度会留着，回头接着做」——
        这是**练习**的语义。而模拟考试考的是"限时、一次成型"：
          · 有倒计时，中断了时间不会停；
          · 中途可存 → 用户可以无限次暂停、翻书、查资料再回来，考试失去意义；
          · 「进度会自动保存」这句话在考试里更是误导 ——
            用户会以为自己能"先做一半，明天继续考"。

        所以考试态：
          · **不显示**暂存按钮与"自动保存"文案；
          · 改成一枚中性的考试提示 + 「交卷」按钮（把唯一有意义的动作放到这里）。

        ⚠️ 但底层的**答案保护**仍然保留（`PracticeComponent` 里的 draftSaver 照常工作）：
          考试中途刷新/误关页面，回来答案还在。这是"技术上的防丢"，
          不是"产品上的暂存功能" —— 不告诉用户，也不提供手动入口。
          两者别混为一谈：前者是兜底，后者是承诺。
    -->
    <!--
      选项乱序开关（2026-10-22）
      ==================================================================
      需求口径：模拟考试的答题卡**不出现**这个开关（考试规则在开考前一次性定好，
                考场中途不该让用户改"选项要不要乱"——那等于允许作弊性调整）；
                顺序 / 随机 / 错题练习三个入口的答题卡**要出现**，供用户实时打乱。

      ⚠️ 位置放在 footer **之前**、答题卡主体之后：
        它不是"操作按钮"，而是"显示偏好"，跟着答题卡走更符合语义；
        放 footer 里会和「交卷 / 暂存」混成一排，看不出它属于"显示设置"。
    -->
    <div v-if="showShuffleToggle" class="shuffle-row">
      <span class="shuffle-label">
        <el-icon><Sort /></el-icon>
        选项乱序
      </span>
      <el-switch :model-value="shuffleOptions" size="small" @update:model-value="onShuffleChange" />
      <span class="shuffle-hint">{{ shuffleOptions ? '已打乱，避免凭位置记答案' : '按题库原始顺序' }}</span>
    </div>

    <div class="card-footer" v-if="isExamMode && !showExamResult">
      <span class="draft-hint is-exam">
        <el-icon><Timer /></el-icon>
        考试进行中，中途离开不会暂停计时
      </span>
      <el-button size="small" type="primary" @click="$emit('submit-exam')">交卷</el-button>
    </div>
    <div class="card-footer" v-else-if="!isExamMode">
      <span class="draft-hint" v-if="draftState === 'saved'">进度已自动保存</span>
      <span class="draft-hint is-failed" v-else-if="draftState === 'failed'">保存失败，请检查浏览器存储</span>
      <span class="draft-hint" v-else>答题进度会自动保存</span>
      <el-button size="small" :loading="draftState === 'saving'" @click="$emit('save-draft')">
        {{ draftButtonText }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import type { PropType } from 'vue'
import { Grid, List, Sort, Timer } from '@element-plus/icons-vue'

interface QuestionItem {
  id?: number | string
  type?: string
  answered?: boolean
  correct?: boolean
  [key: string]: any
}

interface QuestionGroup {
  typeLabel: string
  typeName: string
  startIndex: number
  endIndex: number
  items: Array<QuestionItem & { index: number }>
}

interface Stats {
  correctCount: number
  wrongCount: number
  accuracy: number
  [key: string]: any
}

const props = defineProps({
  questions: { type: Array as PropType<QuestionItem[]>, default: () => [] },
  currentQuestionIndex: { type: Number, default: 0 },
  stats: { type: Object as PropType<Stats>, default: () => ({ correctCount: 0, wrongCount: 0, accuracy: 0 }) },
  isExamMode: { type: Boolean, default: false },
  isPracticeMode: { type: Boolean, default: false },
  isLastQuestion: { type: Boolean, default: false },
  questionGroups: { type: Array as PropType<QuestionGroup[]>, default: () => [] },
  markedQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  favoritedQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  errorQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  isOverviewMode: { type: Boolean, default: false },
  currentHighlightIndex: { type: Number, default: 0 },
  showExamResult: { type: Boolean, default: false },
  totalScore: { type: Number, default: 0 },
  answeredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  remainingCount: { type: Number, default: 0 },
  moduleType: { type: String, default: '' },
  /** 暂存状态：驱动「暂存」按钮的文案与 loading（见 PracticeComponent 的 draftState） */
  draftState: { type: String, default: 'idle' },
  /** 暂存按钮文案（由父组件按状态生成，避免子组件重复一套文案） */
  draftButtonText: { type: String, default: '暂存' },
  /**
   * 题号偏移（= 本波第一题之前的题目数）
   *
   * 分波刷题时 `questions` 只是切片，波内下标每波从 0 起；
   * 题号要跨波顺延，就得加上这个偏移（用户 2026-10-18：
   * 「点下一波还是 1 到 20，应该要顺延」）。
   */
  numberBase: { type: Number, default: 0 },
  /**
   * 是否打乱选项（受控值，由父组件从 store 读取）
   *
   * 为什么把值放在父组件而不是本组件内部：
   *   真正的乱序发生在 `useQuestionPractice.displayOptions`（它按这个开关决定
   *   是否用打乱后的顺序渲染）。答题卡只是**入口**，不掌握状态 —— 否则
   *   卡片里的开关和题目的实际顺序会各说各话。
   */
  shuffleOptions: { type: Boolean, default: false }
})

const emit = defineEmits([
  'go-to-question',
  'reset-practice',
  'submit-exam',
  'toggle-overview',
  'finish-exam',
  /** 手动暂存当前练习进度 */
  'save-draft',
  /** 切换选项乱序（2026-10-22，仅非考试模块可用） */
  'update:shuffle-options'
])

/**
 * 是否显示「选项乱序」开关
 *
 * 只排除模拟考试；顺序 / 随机 / 错题练习都显示。
 * ⚠️ 注意不要顺手用 `isExamMode` 判断：`isExamMode` 是"练习模式选成了考试"，
 *    而「自定义/错题练习」里用户也可能把模式切到考试 —— 那种情况下同理不该给开关。
 *    所以判据 = "不是模拟考试模块，且当前不在考试模式"。
 */
const showShuffleToggle = computed(() => props.moduleType !== 'mock' && !props.isExamMode)

function onShuffleChange(val: boolean | string | number) {
  emit('update:shuffle-options', Boolean(val))
}

const isMounted = ref(false)
const gridItemRefs = ref<Record<number, HTMLElement>>({})

onMounted(() => {
  isMounted.value = true
})

const setGridItemRef = (el: any, index: number) => {
  if (el) {
    gridItemRefs.value[index] = el
  }
}

// 状态判断辅助函数（基于题目 ID）
const getOverviewItemClass = (index: number) => {
  const q = props.questions[index]
  const isHighlighted = index === props.currentHighlightIndex
  const isCorrect = !props.isExamMode && q && q.correct && q.answered
  const isWrong = !props.isExamMode && !isCorrect && q && q.answered

  if (isHighlighted) return 'current'
  if (isCorrect) return 'correct'
  if (isWrong) return 'wrong'
  if (q && q.answered) return 'answered'
  return ''
}
</script>

<style scoped>
.answer-card {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid #e5e7eb;
  position: sticky;
  top: 20px;
  height: fit-content;
}

.card-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  margin-bottom: 8px;
}

/*
 * 选项乱序开关行（2026-10-22）
 * 与 footer 用同一条发丝线分隔，但在 footer **之上**：
 * 它属于"显示设置"，不属于"提交动作"。
 */
.shuffle-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));

  .shuffle-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 500;
    color: var(--os-text-2, #4b5563);
    flex: none;
  }

  .shuffle-hint {
    font-size: 11.5px;
    color: var(--os-text-4, #9ca3af);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/*
 * 底部暂存区（用户 2026-10-18：「位置不对，要改到底部去」）
 * 一条发丝线把"题号网格"和"进度操作"分开，右侧是动作、左侧是状态说明。
 */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));

  .draft-hint {
    font-size: 12px;
    line-height: 1.5;
    color: var(--os-text-4, #9ca3af);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &.is-failed {
      color: var(--el-color-danger, #f56c6c);
    }

    /*
     * 考试态提示：比普通 draft-hint 更"实"一些
     *
     * 练习态的提示是「进度已自动保存」—— 中性、可忽略。
     * 考试态这句「中途离开不会暂停计时」是**用户需要知道的事实**，
     * 所以给图标 + 略深的字色，让它有存在感但不喧宾夺主（不用警告色）。
     */
    &.is-exam {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--os-text-3, #6b7280);
    }
  }

  :deep(.el-button) {
    flex: none;
  }
}

.header-left h4 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-center {
  display: flex;
  justify-content: center;
}

.mode-group {
  display: flex;
  align-items: center;
  gap: 4px;
  /* 标签和图标紧贴 */
}

.header-right {
  display: flex;
  margin-right: -10px;
  justify-content: flex-end;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h4 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.question-grid {
  display: grid;
  grid-template-columns: repeat(5, 36px);
  gap: 6px 2px;
  margin-bottom: 20px;
  justify-content: center;
}

.grid-item {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.grid-item.answered {
  background-color: #e8f0fe;
  border-color: #c5d9f5;
  color: #1a56db;
}

.grid-item.correct {
  background-color: #f0f9eb;
  color: #67c23a;
}

.grid-item.wrong {
  background-color: #fef2f2;
  color: #b45353;
}

.grid-item.current {
  background-color: #f3f4f6;
  border-color: #d1d5db;
  font-weight: bold;
}

.stats {
  margin-bottom: 20px;
}

.stats div {
  margin-bottom: 5px;
  font-size: 14px;
  color: #6b7280;
}

.correct {
  color: #67c23a;
}

.wrong {
  color: #b45353;
}

.rate {
  font-weight: bold;
  color: #1f2937;
}

.progress-text {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 4px;
}

.progress-hint {
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.total-score {
  font-size: 20px;
  font-weight: bold;
  color: #1f2937;
  margin-bottom: 8px;
}

/* 整体浏览模式样式 */
.overview-card-body {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  scrollbar-gutter: stable;
  margin-right: -10px;
}

.group-section {
  margin-bottom: 12px;
}

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
  padding-left: 2px;
}

.group-grid {
  display: grid;
  grid-template-columns: repeat(5, 36px);
  gap: 6px 2px;
  max-width: calc(100% - 24px);
}

.overview-grid-item {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  font-size: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #6b7280;
  transition: all 0.2s ease;
}

.overview-grid-item:hover {
  border-color: #d1d5db;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
}

.overview-grid-item.answered {
  background: #e8f0fe;
  border-color: #c5d9f5;
  color: #1a56db;
}

.overview-grid-item.current {
  background-color: #f3f4f6;
  border-color: #d1d5db;
  font-weight: bold;
}

.overview-grid-item.correct {
  background-color: #f0f9eb;
  color: #67c23a;
}

.overview-grid-item.wrong {
  background-color: #fef2f2;
  color: #b45353;
}
</style>