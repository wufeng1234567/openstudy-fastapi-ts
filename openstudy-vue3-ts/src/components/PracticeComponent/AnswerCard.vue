<template>
  <div class="answer-card">
    <!--
      头部（2026-10-22 重做对齐）
      ==================================================================
      用户反馈：「里面的按钮组件要对齐 文字简洁」，并附了截图，暴露出三个问题：

        ① 标题「答题卡」被挤成**两行**（"答题 / 卡"）。
           根因是头部原本用 `grid-template-columns: auto 1fr auto`，
           卡片只有 25% 宽时三列互相挤压，`h4` 没有 `nowrap` 就按字符折行了。

        ② 三种控件形态混排、基线不齐：`el-tag`（胶囊）+ `el-button circle`（圆钮）
           + `el-button text`（文字按钮）。三者高度/内边距各不相同，
           中间那列还 `justify-content: center`，于是视觉上横着一串、高低错落。

        ③ 文案冗长：模式标签「整体浏览」+ 圆形切换按钮其实在说同一件事，
           等于**两个控件表达一个状态**。

      现在改为一条 flex 行：左边标题（nowrap 不换行），右边一组**同规格文字按钮**。
        · 模式标签与圆形切换按钮合并成一个按钮：显示当前模式、点击即切换
          （「逐题」/「浏览」），控件数 3 → 2，且不再有圆钮这种异形；
        · 两个按钮都用 `el-button text size="small"`，高度/字号/内边距天然一致，
          右对齐落在同一条基线上。
    -->
    <div class="card-header">
      <h4 class="card-title">答题卡</h4>
      <div class="card-tools">
        <el-tooltip :content="isOverviewMode ? '切换为逐题模式' : '切换为整体浏览'" placement="top">
          <el-button text size="small" :icon="isOverviewMode ? List : Grid" @click="$emit('toggle-overview')">
            {{ isOverviewMode ? '浏览' : '逐题' }}
          </el-button>
        </el-tooltip>
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
        <!-- 刷题模式：显示进度（文案收紧，2026-10-22） -->
        <template v-if="isPracticeMode">
          <div class="progress-text">
            已答 <b>{{ answeredCount }}</b> / {{ totalCount }}
          </div>
          <div class="progress-hint" v-if="remainingCount > 0">剩 {{ remainingCount }} 题</div>
        </template>

        <!-- 考试模式：显示总分 -->
        <template v-else-if="isExamMode && showExamResult">
          <div class="total-score">{{ totalScore }} 分</div>
          <el-button v-if="moduleType === 'mock'" type="primary" size="small" @click="$emit('finish-exam')">
            结束考试
          </el-button>
        </template>

        <!-- 模拟考试提交后（非考试模式）：显示结束按钮 -->
        <template v-else-if="moduleType === 'mock' && showExamResult">
          <div class="stat-line">
            <span>答对 <b class="correct">{{ stats.correctCount }}</b></span>
            <span>答错 <b class="wrong">{{ stats.wrongCount }}</b></span>
            <span>正确率 <b class="rate">{{ stats.accuracy }}%</b></span>
          </div>
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
          <div class="stat-line">
            <span>答对 <b class="correct">{{ stats.correctCount }}</b></span>
            <span>答错 <b class="wrong">{{ stats.wrongCount }}</b></span>
            <span>正确率 <b class="rate">{{ stats.accuracy }}%</b></span>
          </div>
        </template>

        <!-- 默认统计（预览模式等） -->
        <template v-else>
          <div class="stat-line">
            <span>答对 <b class="correct">{{ stats.correctCount }}</b></span>
            <span>答错 <b class="wrong">{{ stats.wrongCount }}</b></span>
            <span>正确率 <b class="rate">{{ stats.accuracy }}%</b></span>
          </div>
        </template>
      </div>
    </template>

    <!-- 整体浏览模式：分组展示 -->
    <template v-else>
      <div class="overview-card-body">
        <div v-for="group in questionGroups" :key="group.typeName" class="group-section">
          <!--
            分组标题只留「题型 + 数量」（2026-10-22 文案收紧）
            原来写「单选题（共 4 题）」——「选择题」三个字里已经含"题"，
            后面再补"（共 4 题）"是重复计量的啰嗦。改成「单选题 4」：
            题型名 + 数量，一眼扫过就够，且与右侧网格左对齐、不折行。
          -->
          <div class="group-title">
            <span class="group-name">{{ group.typeLabel }}</span>
            <span class="group-count">{{ group.items.length }}</span>
          </div>
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
      底部区块：练习态显示「自动保存状态」，考试态显示「交卷引导」
      ================================================================
      ⚠️ 为什么模拟考试**不显示任何"自动保存 / 暂存"相关信息**（2026-10-20）：
         「模拟考试不该出现暂存按钮 需要进行单独的优化」。

        自动保存这类文案传达的是「你可以随时中断，进度会留着，回头接着做」——
        这是**练习**的语义。而模拟考试考的是"限时、一次成型"：
          · 有倒计时，中断了时间不会停；
          · 「进度会自动保存」在考试里是误导 ——
            用户会以为自己能"先做一半，明天继续考"。

        所以考试态只给一枚中性的考试提示 + 「交卷」按钮
        （把唯一有意义的动作放在这里）。

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
        放 footer 里会和「交卷」混成一排，看不出它属于"显示设置"。
    -->
    <div v-if="showShuffleToggle" class="shuffle-row">
      <span class="shuffle-label">
        <el-icon><Sort /></el-icon>
        乱序
      </span>
      <el-switch :model-value="shuffleOptions" size="small" @update:model-value="onShuffleChange" />
      <!--
        提示语收紧（2026-10-22）
        原：「已打乱，避免凭位置记答案」/「按题库原始顺序」—— 两句都太长，
        在 25% 宽的卡片里会把开关挤出可用区。
        现在只留 4 个字的状态本身：开 =「已打乱」，关 =「原顺序」。
        "为什么要打乱"属于解释性文案，不该常驻在一个控制面板里。
      -->
      <span class="shuffle-hint">{{ shuffleOptions ? '已打乱' : '原顺序' }}</span>
    </div>

    <!--
      滚动锚点行（2026-10-22）
      ==================================================================
      用户需求演进（三版）：
        ① 初版：视口右下角一个悬浮「一键滚动」球 + 全局悬浮 AI 助手
                → 两个浮层在右下角**叠在一起**，还压住了答题卡。
        ② 方案A（已回滚）：用 `avoidSelector` 动态测量、把两个浮层上下错开
                → 用户判定「不行这样做 没有解决不美观的问题」。
                   错开只是挪位置，右侧仍然挂着一串浮层，整体不简洁。
        ③ 现行（本段）：**练习页不放任何常驻浮层**。
                滚动能力收进答题卡这个"控制列"里，变成一行静态文本按钮。

      为什么放在这里（而不是继续浮着）：
        · 答题卡本身就是这一屏的"控制面板"（题号、进度、乱序、自动保存、交卷都在里面）
          —— 滚动导航属于同一类操作，天生该在这儿；
        · 它 `position: sticky`，右侧这一列始终在视野内，按钮不会找不到；
        · 不再有 fixed 元素去和答题卡抢右缘，右下角彻底干净。

      为什么是**两个**静态按钮（而不是原来那个自动翻向的单球）：
        浮球需要"猜用户想往上还是往下"（靠 delta 判断），静态按钮不需要猜 ——
        用户点哪个就是哪个，零歧义。这也正好绕开了上一版方向判定的全部复杂度。

      ⚠️ 显示条件（`scrollable`）由父组件算：只有当前滚动宿主真的溢出时才渲染。
         · 逐题模式 + 普通单选题（一题一屏）→ 不溢出 → **整行不出现**，保持极简；
         · 逐题模式 + 长组合题/长解析 → 溢出 → 出现；
         · 整体浏览（瀑布流）→ 几乎总溢出 → 出现（正是最需要的时候）。

      ⚠️⚠️ 两个按钮**永远可点，不做 disabled/置灰**（2026-10-22 实测踩到）：
        第一版按"是否已在端点"置灰，结果在后台标签页里 Chrome **不派发 scroll 事件**，
        状态停在初始值 → 「回到顶部」永久 disabled → 用户点了完全没反应
        （探针里复现：跳到底部后回不到顶部）。
        只要按钮可用性依赖滚动事件，就必然存在"事件没到 → 按钮废掉"的失败模式。
        而这两个动作**本身就是幂等的**：已经在顶部再点一次回到顶部，
        毫无副作用。所以直接去掉置灰，既消掉整个失败模式，视觉也更干净
        （用户嫌的本来就是"元素太多不简洁"，一排灰按钮只会更吵）。
    -->
    <div v-if="scrollable" class="scroll-anchors">
      <button type="button" class="scroll-anchor" @click="$emit('scroll-top')">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m18 15-6-6-6 6" />
        </svg>
        顶部
      </button>
      <span class="scroll-anchors__divider" aria-hidden="true"></span>
      <button type="button" class="scroll-anchor" @click="$emit('scroll-bottom')">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
        底部
      </button>
    </div>

    <div class="card-footer" v-if="isExamMode && !showExamResult">
      <span class="draft-hint is-exam">
        <el-icon><Timer /></el-icon>
        考试进行中，中途离开不会暂停计时
      </span>
      <el-button size="small" type="primary" @click="$emit('submit-exam')">交卷</el-button>
    </div>

    <!--
      练习态底行：**只剩一句静默状态说明，没有按钮**（2026-10-22）
      ==================================================================
      用户：「进度是不是一直会自动保存 如果会的话 那就把暂存按钮去掉吧
             彻底搞成静默自动保存用户刷题记录」

      确认：确实是**一直**自动保存 —— 每次作答 / 判分 / 换题 / 换波后都会
      静默写一次 localStorage（`draftSaver.schedule()`，600ms 节流），
      离开页面时还会 `flush()` 立刻落盘一次。
      所以那个「暂存」按钮纯属多余：它做的 `flush()` 与自动保存是**同一个写盘动作**
      （见 `utils/practiceDraft.ts` 的 `createDraftSaver`），
      用户不需要为了"保住进度"去点任何东西。

      那为什么还留这一行字？因为**静默不能等于无感**：
        · 正常态：一句极浅的「进度自动保存」，让人心里有底，且完全不抢注意力；
        · 失败态：必须显性提示（配额满 / 隐私模式 / 无痕窗口），
                  否则用户以为存上了、关掉页面才发现全丢 —— 这是真实的数据损失。
      所以：常态是 11.5px 的 `--os-text-4`，失败才升到警示色 + 图标。
    -->
    <div class="card-footer" v-else-if="!isExamMode">
      <span class="draft-hint is-failed" v-if="draftState === 'failed'">
        <el-icon><WarningFilled /></el-icon>
        自动保存失败，进度可能丢失
      </span>
      <span class="draft-hint" v-else>
        <el-icon><CircleCheck /></el-icon>
        进度自动保存
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import type { PropType } from 'vue'
import { Grid, List, Sort, Timer, CircleCheck, WarningFilled } from '@element-plus/icons-vue'

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
  /**
   * 自动保存状态（`idle` / `saving` / `saved` / `failed`）
   *
   * 只用来决定底行那句提示的**语气**（正常 / 失败），
   * 不再驱动任何按钮 —— 手动「暂存」按钮已删除（2026-10-22）。
   */
  draftState: { type: String, default: 'idle' },
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
  shuffleOptions: { type: Boolean, default: false },
  /**
   * 当前滚动宿主是否真的能滚（有溢出）
   *
   * 由父组件探测（见 `PracticeComponent` 的 `scrollable`），因为真正的滚动容器
   * 是外壳 `.os-content`，子组件自己"向上找"会找到答题卡内部、判错。
   * 为 false 时整行锚点不渲染 —— 这是"一题一屏、不需要滚动"时保持极简的关键。
   */
  scrollable: { type: Boolean, default: false }
})

const emit = defineEmits([
  'go-to-question',
  'reset-practice',
  'submit-exam',
  'toggle-overview',
  'finish-exam',
  /** 切换选项乱序（2026-10-22，仅非考试模块可用） */
  'update:shuffle-options',
  /** 滚到页面顶部（2026-10-22，替代原右下角悬浮滚动球） */
  'scroll-top',
  /** 滚到页面底部（2026-10-22） */
  'scroll-bottom'
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

/*
 * 头部：一条 flex 行，左标题 + 右工具组（2026-10-22 重做）
 * ============================================================================
 * 原先是 `grid-template-columns: auto 1fr auto` 三列，中间那列装
 * 「标签 + 圆钮」。卡片只有 25% 宽时三列互相挤，`h4` 又没有 nowrap，
 * 于是「答题卡」被按字符折成「答题 / 卡」两行（用户截图里很明显）。
 *
 * 现在：
 *   · flex 单行 + `header` 不换行，标题自然占它需要的宽度；
 *   · 工具组 `margin-left: auto` 贴右，各项 `align-items: center` 同一基线；
 *   · 两个工具按钮都是 `el-button text size="small"`，
 *     高度/字号/内边距由 Element Plus 保证一致，不再出现"胶囊 + 圆钮 + 文字"
 *     三种形态混排。组内不用 gap 拉太开，保持紧凑。
 */
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  /* 头部任何情况都不折行：一折行就是"标题竖排"那种灾难 */
  flex-wrap: nowrap;
}

/* 标题：不换行、不压缩（挤压时宁可让工具组挤，也不让标题断字） */
.card-title {
  flex: none;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 20px;
  color: var(--os-text, #1f2937);
  white-space: nowrap;
  letter-spacing: 0.2px;
}

/*
 * 工具组：贴右，两个按钮同规格
 *
 * `margin-left: auto` 而不是 `justify-content: space-between`：
 * 后者在只有一个子元素时也会把它推到最右，语义上不如显式的 auto 清楚。
 */
.card-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;

  /*
   * 统一工具按钮的视觉重量
   *
   * Element Plus 的 text 按钮默认内边距偏大（左右各约 8px），
   * 两个并排时在 25% 宽卡片里会显得松散。这里把左右内边距收到 4px，
   * 并统一行高，让两个按钮看起来是"同一组控件"而不是两个独立按钮。
   */
  :deep(.el-button) {
    padding: 0 4px;
    height: 22px;
    font-size: 12px;
    font-weight: 500;
    color: var(--os-text-3, #6b7280);
  }

  :deep(.el-button:hover) {
    color: var(--os-accent, var(--os-primary, #0f1115));
    background: transparent;
  }

  :deep(.el-button .el-icon) {
    margin-right: 3px;
    font-size: 13px;
  }
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
 * 底部状态行
 * ----------------------------------------------------------------------------
 * 原先是「左侧状态说明 + 右侧暂存按钮」，`justify-content: space-between` 把
 * 文字和按钮拉到两端（用户 2026-10-18：「位置不对，要改到底部去」）。
 *
 * 2026-10-22 删掉手动暂存按钮后，这里**只剩一行字**，所以：
 *   · `space-between` → `flex-start`：单个子元素在 space-between 下也会贴左，
 *     但语义上留着一个"两端对齐"会误导后来者以为右边还有东西；
 *   · 常态提示降到 11.5px + `--os-text-4`：它现在是纯背景信息，
 *     存在感要低于题号与统计，只求"扫一眼有底"，不求被读到。
 */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));

  .draft-hint {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--os-text-4, #9ca3af);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    /*
     * 自动保存失败：这是**必须被看到**的一条
     *
     * 静默保存的前提是"它真的在保存"。一旦写盘失败（配额满 / 隐私模式 /
     * 无痕窗口），用户如果还以为存上了，关掉页面就是真实的数据丢失。
     * 所以失败态从"背景信息"升级为"警示"：危险色 + 图标 + 更实的字重。
     */
    &.is-failed {
      font-size: 12px;
      font-weight: 500;
      color: var(--el-color-danger, #f56c6c);
    }

    /*
     * 考试态提示：比普通 draft-hint 更"实"一些
     *
     * 练习态的提示是「进度自动保存」—— 中性、可忽略。
     * 考试态这句「中途离开不会暂停计时」是**用户需要知道的事实**，
     * 所以给图标 + 略深的字色，让它有存在感但不喧宾夺主（不用警告色）。
     */
    &.is-exam {
      font-size: 12px;
      color: var(--os-text-3, #6b7280);
    }
  }

  :deep(.el-button) {
    flex: none;
  }
}

/*
 * ⚠️ 旧头部规则已删除（2026-10-22）
 * ============================================================================
 * 这里原来有一整串 `.header-left h4`（写了两遍）、`.header-center`、
 * `.mode-group`、`.header-right`、`.header-actions`。
 * 头部重构后模板里已经没有 `header-left/center/right` 与 `mode-group` 这些元素，
 * 留着就是死代码 —— 而且它们**不是 scoped 之外就没影响**：
 * `PracticeComponent.css` 里也有一份同名的 `.card-header .header-*` 全局规则，
 * 两套并存在排查样式问题时极易误判（这次"标题竖排"就差点被误以为是全局样式覆盖）。
 * 现在头部只有 `.card-header` / `.card-title` / `.card-tools` 三个类。
 */

.question-grid {
  display: grid;
  /* 5 列等宽（36px）：卡片宽度变化时网格不跳，列与列之间用 gap 控制 */
  grid-template-columns: repeat(5, 36px);
  gap: 6px;
  margin-bottom: 16px;
  /* 靠左对齐，与头部标题、分组标题同一条左缘 */
  justify-content: flex-start;
}

/*
 * 题号格子
 * ----------------------------------------------------------------------------
 * `box-sizing: border-box` 必须显式写：全局 `PracticeComponent.css` 里的
 * `.grid-item` 也有 32px 的一版，而 scoped 这份是 36px + 1px 边框。
 * 不加 border-box 时 36+2=38px 会超出 5×36+gap 的列宽，网格右侧错位。
 */
.grid-item {
  box-sizing: border-box;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--os-text-3, #6b7280);
  background: #fff;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.grid-item:hover {
  border-color: var(--os-border-strong, #d1d5db);
  color: var(--os-text, #1f2937);
}

.grid-item.answered {
  background-color: #e8f0fe;
  border-color: #c5d9f5;
  color: #1a56db;
}

.grid-item.correct {
  background-color: #f0f9eb;
  border-color: #d6ecc4;
  color: #4e9e2a;
}

.grid-item.wrong {
  background-color: #fef2f2;
  border-color: #f6d5d5;
  color: #b45353;
}

/*
 * 当前题：用描边 + 加粗表示"你在这里"
 *
 * 底色刻意保持白色：`.current` 常与 `.answered / .correct / .wrong` 叠加，
 * 若也改底色就会把那三种语义色盖掉（用户看到"当前题"却看不出对错）。
 */
.grid-item.current {
  border-color: var(--os-primary, #0f1115);
  color: var(--os-text, #1f1115);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--os-primary, #0f1115);
}

.stats {
  margin-bottom: 16px;
}

/*
 * 一行三项统计（2026-10-22）
 * 原来三行「答对：x 题 / 答错：x 题 / 正确率：x%」在卡片里占了 3 行高度，
 * 而它们是最不常看的信息。改成一行，用间距分隔，高度从约 60px 压到 20px。
 */
.stat-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);

  b {
    font-weight: 600;
  }
}

.correct {
  color: #4e9e2a;
}

.wrong {
  color: #b45353;
}

.rate {
  color: var(--os-text, #1f2937);
}

.progress-text {
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
  margin-bottom: 2px;

  b {
    font-weight: 600;
    color: var(--os-text, #1f2937);
  }
}

.progress-hint {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--os-text-4, #9ca3af);
  margin-bottom: 0;
}

.total-score {
  font-size: 18px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
  margin-bottom: 8px;
}

/*
 * 滚动锚点行（2026-10-22）
 * ============================================================================
 * 形态取"文字按钮 + 发丝分隔线"，与 `.only-wrong-bar__action` 同一调性：
 *   · 不用 ElButton：这里是**辅助导航**，不该和「交卷」抢视觉重量；
 *   · 不用图标圆钮：圆钮会让人想起被回滚掉的那个浮球，形态上要拉开距离；
 *   · 分隔线只做"两个方向"的语义提示，不画整条边框。
 *
 * 位置：紧贴在 footer（自动保存状态 / 交卷）**之上**、乱序开关**之下** ——
 * 上面是"显示设置"，下面是"离开 / 提交"，滚动导航夹在中间正好属于"看内容"。
 */
.scroll-anchors {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
}

.scroll-anchor {
  appearance: none;
  border: 0;
  background: none;
  padding: 2px 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  line-height: 1;
  color: var(--os-text-3, #6b7280);
  border-radius: 4px;
  cursor: pointer;
  transition: color var(--ds-duration-fast, 0.15s) ease,
    background-color var(--ds-duration-fast, 0.15s) ease;
}

.scroll-anchor:hover:not(:disabled) {
  color: var(--os-accent, var(--os-primary, #0f1115));
  background: var(--os-bg-hover, rgba(0, 0, 0, 0.03));
}

.scroll-anchor:focus-visible {
  outline: 2px solid var(--os-primary, #0f1115);
  outline-offset: 2px;
}

/*
 * 已经在端点 → 不再置灰（见模板里那段注释）
 *
 * 这里只保留 hover / focus 的交互反馈；`:disabled` 样式一并去掉，
 * 因为按钮不再有 disabled 状态，留着会成为"永远不生效的死代码"。
 */
.scroll-anchor:active {
  background: var(--os-bg-hover, rgba(0, 0, 0, 0.05));
}

.scroll-anchors__divider {
  width: 1px;
  height: 10px;
  background: var(--os-border, #e5e7eb);
  flex: none;
}

/* ==================== 整体浏览模式 ==================== */

/*
 * 分组列表的滚动区
 *
 * `scrollbar-gutter: stable` 预留滚动条宽度，避免"有滚动条/没滚动条"时
 * 网格左右跳动；`margin-right: -10px` 把预留给滚动条的空间反向吃掉，
 * 让网格左缘仍与上方标题对齐（原来只写了 -10px，没写 gutter，两者要配套）。
 */
.overview-card-body {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  scrollbar-gutter: stable;
  margin-right: -10px;
  padding-right: 10px;
}

.group-section {
  margin-bottom: 12px;
}

.group-section:last-child {
  margin-bottom: 0;
}

/*
 * 分组标题：「题型」+「数量」
 *
 * 不再写「单选题（共 4 题）」——括号和"共…题"是重复计量。
 * 现在题型用常规字重、数量用更浅的颜色贴在后面，形成"标签 + 计数"的层级，
 * 一眼扫过就知道这组有多少题，而不需要读完一整句。
 */
.group-title {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin-bottom: 6px;
  font-size: 12px;
  line-height: 1.5;

  .group-name {
    font-weight: 600;
    color: var(--os-text-2, #4b5563);
    white-space: nowrap;
  }

  .group-count {
    font-size: 11px;
    color: var(--os-text-4, #9ca3af);
  }
}

.group-grid {
  display: grid;
  grid-template-columns: repeat(5, 36px);
  gap: 6px;
}

/*
 * 浏览模式的格子复用 `.grid-item` 的基础尺寸与配色，
 * 这里只覆盖圆角/悬停这类"模式差异"，避免两份样式各自漂移
 * （原来这里重复声明了 width/height/border/font-size，与 `.grid-item` 冲突）。
 */
.overview-grid-item {
  border-radius: 8px;
}

.overview-grid-item:hover {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
</style>