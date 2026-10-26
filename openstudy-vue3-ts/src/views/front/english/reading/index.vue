<!--
  英语阅读练习
  ============================================================================
  2026-10-23 从空壳做成真功能。

  原来这个页面只有一句"阅读功能开发中..."。但后端
  `GET /ai/generate/reading/stream`（scene=reading）**一直是可用的**，
  前端也早就有 `generateReadingComprehensionStream()` 封装 ——
  两边都在，就是没人接起来。

  现在接上：用户描述想练什么 → AI 生成短文 + 阅读理解题 → 就地做题、看解析。
-->
<template>
  <div class="rd-page">
    <!--
      2026-10-26：整行返回按钮已删除（用户：「返回功能不需要了」）。
      顶栏已显示 `英语学习 · 阅读练习`，层级清晰。
      生成设置卡片直接作为页面主体，居中并限制最大宽度。
    -->

    <!-- 生成设置 -->
    <section v-if="!passage" class="rd-setup">
      <div class="rd-field">
        <label class="rd-label">想练什么？</label>
        <el-input
          v-model="requirement"
          type="textarea"
          :rows="3"
          placeholder="例如：四级水平，关于环境保护的科普短文 / 高中难度，讲人工智能对教育的影响"
          maxlength="300"
          show-word-limit
        />
      </div>

      <div class="rd-field rd-field--inline">
        <label class="rd-label">题目数量</label>
        <el-radio-group v-model="questionCount" size="small">
          <el-radio-button :value="3">3 题</el-radio-button>
          <el-radio-button :value="5">5 题</el-radio-button>
          <el-radio-button :value="8">8 题</el-radio-button>
        </el-radio-group>
      </div>

      <button
        type="button"
        class="rd-generate"
        :disabled="generating || !requirement.trim()"
        @click="generate"
      >
        <OsIcon name="sparkles" :size="15" />
        <span>{{ generating ? '正在生成…' : '生成一篇' }}</span>
      </button>

      <p v-if="error" class="rd-error">{{ error }}</p>
    </section>

    <!-- 生成中 -->
    <section v-if="generating && !passage" class="rd-loading">
      <div class="rd-loading__spinner" />
      <p class="rd-loading__title">AI 正在写这篇短文…</p>
      <p class="rd-loading__hint">通常十几秒，出完会自动显示</p>
    </section>

    <!-- 生成结果：短文 + 题目 -->
    <section v-if="passage" class="rd-article">
      <div class="rd-article__head">
        <span class="rd-article__title">{{ articleTitle }}</span>
        <button type="button" class="rd-btn" @click="reset">换一篇</button>
      </div>
      <div class="rd-article__body">
        <p v-for="(p, i) in passageParagraphs" :key="i" class="rd-para">{{ p }}</p>
      </div>
    </section>

    <!--
      成绩汇总（2026-10-26 闭环）
      -----------------------------------------------------------------
      用户反馈过「阅读练习做完就没了」。改前答完每题只显示单题对错，
      整篇练完既没有总分也没有任何留存，关掉页面什么也不剩。

      现在：答完任意一题就出现这条汇总（实时更新），全部答完后
      自动落库到 `english_practice_log`（mode=reading），
      并给出「再练一篇 / 去听写 / 让 AI 分析」三个出口。
    -->
    <section v-if="questions.length && answeredCount > 0" class="rd-summary">
      <div class="rd-summary__main">
        <div class="rd-summary__score">
          <span class="rd-summary__pct">{{ accuracy }}<i>%</i></span>
          <span class="rd-summary__label">本篇正确率</span>
        </div>
        <div class="rd-summary__nums">
          <span>已答 {{ answeredCount }} / {{ questions.length }}</span>
          <span class="is-ok">对 {{ correctCount }}</span>
          <span class="is-bad">错 {{ answeredCount - correctCount }}</span>
        </div>
      </div>

      <div class="rd-summary__actions">
        <el-button v-if="answeredCount === questions.length" type="primary" @click="retryWrongReading">
          只重做错题（{{ wrongQuestions.length }}）
        </el-button>
        <el-button @click="reset">换一篇</el-button>
        <el-button text @click="askAiForReadingAnalysis">让 AI 分析这篇</el-button>
      </div>

      <p v-if="answeredCount === questions.length && savedToHistory" class="rd-summary__saved">
        <el-icon :size="13"><CircleCheck /></el-icon>
        这次成绩已保存，可以在「学习统计」里看到
      </p>
    </section>

    <section v-if="questions.length" class="rd-questions">
      <div v-for="(q, qi) in questions" :key="qi" class="rd-q">
        <div class="rd-q__head">
          <span class="rd-q__idx">{{ qi + 1 }}</span>
          <span class="rd-q__text">{{ q.questionText || q.title }}</span>
        </div>

        <div v-if="q.options && q.options.length" class="rd-q__options">
          <button
            v-for="(opt, oi) in q.options"
            :key="oi"
            type="button"
            class="rd-opt"
            :class="optClass(qi, oi, q)"
            :disabled="revealed[qi]"
            @click="choose(qi, oi)"
          >
            <span class="rd-opt__key">{{ String.fromCharCode(65 + oi) }}</span>
            <span class="rd-opt__text">{{ stripOptionPrefix(opt) }}</span>
          </button>
        </div>

        <div v-if="revealed[qi]" class="rd-q__answer">
          <div class="rd-q__verdict" :class="isCorrect(qi, q) ? 'is-right' : 'is-wrong'">
            {{ isCorrect(qi, q) ? '答对了' : '答错了' }}
            <span v-if="!isCorrect(qi, q)" class="rd-q__correct">
              · 正确答案：{{ answerText(q) }}
            </span>
          </div>
          <div v-if="q.analysis" class="rd-q__analysis">{{ q.analysis }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishReading' })
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import { generateReadingComprehensionStream } from '@/api/ai/ai'
// 阅读成绩落库（2026-10-26）：与听写共用同一张 english_practice_log
import { submitPractice } from '@/api/words/words'
import { CircleCheck } from '@element-plus/icons-vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const requirement = ref('')
const questionCount = ref(5)
const generating = ref(false)
const error = ref('')

const passage = ref('')
const questions = ref<any[]>([])
const picks = ref<Record<number, number>>({})
const revealed = ref<Record<number, boolean>>({})

const articleTitle = computed(() => {
  // 后端有的题型会给 title，没有就用一句话代替
  const t = questions.value.find((q) => q.title)?.title
  return t || '阅读材料'
})

const passageParagraphs = computed(() =>
  String(passage.value || '')
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean)
)

function stripOptionPrefix(opt: any): string {
  // 模型有时会把 "A. xxx" 一起返回，去掉前缀避免和左侧字母重复
  return String(opt ?? '').replace(/^\s*[A-Da-d][.、:：)]\s*/, '')
}

async function generate() {
  const req = requirement.value.trim()
  if (!req) return
  generating.value = true
  error.value = ''
  passage.value = ''
  questions.value = []
  picks.value = {}
  revealed.value = {}
  // 新的一篇 = 新的一次记录，放开幂等标记
  readingSubmitted = false
  savedToHistory.value = false

  try {
    await generateReadingComprehensionStream(
      req,
      questionCount.value,
      '',
      undefined,
      (data: any) => {
        const list = Array.isArray(data) ? data : data?.questions || []
        if (!list.length) {
          error.value = 'AI 这次没生成出题目，换个说法再试一次'
          return
        }

        /*
         * ⚠️ 2026-10-26 修「只出题、没有短文」：
         *
         *    后端 `_build_reading` 现在返回的是**对象**
         *        { "passage": "短文正文", "questions": [...] }
         *    而这里原来只从 `list[0].passage` 取正文 —— 拿不到，
         *    于是 `passage` 为空，页面的 `.rd-article`（短文区）整块不渲染，
         *    用户看到的就是"直接给了一堆题，却没有文章"。
         *
         *    三种形态都要兼容（历史数据 / composite 场景 / 新格式）：
         *      ① `data.passage`            —— 新格式（当前后端）
         *      ② `data.passage` 挂在每题上  —— composite 形态
         *      ③ 纯数组                    —— 旧格式，没有正文
         */
        const topPassage = String(data?.passage || '').trim()
        passage.value = topPassage

        questions.value = list.map((q: any) => ({
          ...q,
          // 没有 passage 的题目就是普通题，短文留空即可
          title: q.title || ''
        }))

        // 顶层没给正文时，再看题目上有没有挂
        if (!passage.value) {
          const anyWithPassage = list.find((q: any) => q.passage)
          if (anyWithPassage) passage.value = String(anyWithPassage.passage)
        }
        // 最后退回标题（有些模型会把短文放在 title 里）
        if (!passage.value) {
          passage.value = String(list[0]?.title || '')
        }
      },
      (e: any) => {
        error.value = '生成失败：' + (e?.message || e)
      }
    )
  } catch (e: any) {
    error.value = '生成失败：' + (e?.message || e)
    ElMessage.error(error.value)
  } finally {
    generating.value = false
  }
}

function choose(qi: number, oi: number) {
  picks.value = { ...picks.value, [qi]: oi }
  revealed.value = { ...revealed.value, [qi]: true }
  // 答完最后一题自动落库（幂等：`readingSubmitted` 保证只提交一次）
  if (Object.keys(picks.value).length === questions.value.length) {
    void saveReadingRecord()
  }
}

/* ============================================================================
 * 阅读成绩闭环（2026-10-26）
 *
 * 改前：答完只显示单题对错，整篇练完没有总分、没有任何留存 ——
 *       关掉页面就什么都不剩，也无法回顾「这篇我错在哪」。
 *
 * 改后：
 *   · 已答 > 0 就出现实时汇总条（正确率 / 对几错几）；
 *   · 全部答完自动 POST 到 `/words/practice/submit`（mode=reading）；
 *   · 提交内容带逐题明细，智能体 `english_practice` 工具能读出
 *     「阅读正确率趋势」和「常错题型」。
 * ========================================================================== */

const answeredCount = computed(() => Object.keys(picks.value).length)

const correctCount = computed(
  () => questions.value.filter((q: any, qi: number) => isCorrect(qi, q)).length
)

const accuracy = computed(() =>
  answeredCount.value ? Math.round((correctCount.value * 100) / answeredCount.value) : 0
)

/** 答错的题（重做/分析用） */
const wrongQuestions = computed(() =>
  questions.value
    .map((q: any, qi: number) => ({ q, qi }))
    .filter(({ q, qi }) => revealed.value[qi] && !isCorrect(qi, q))
)

/** 是否已落库（避免重复提交） */
const savedToHistory = ref(false)
let readingSubmitted = false

/** 提交本次阅读成绩 */
async function saveReadingRecord() {
  if (readingSubmitted) return
  if (!questions.value.length) return
  readingSubmitted = true

  const total = questions.value.length
  const correct = correctCount.value
  try {
    await submitPractice({
      mode: 'reading',
      title: requirement.value.trim().slice(0, 60) || '阅读练习',
      total,
      correct,
      detail: questions.value.map((q: any, qi: number) => ({
        word: String(q.questionText || q.title || `第 ${qi + 1} 题`).slice(0, 120),
        input: picks.value[qi] !== undefined ? String.fromCharCode(65 + picks.value[qi]) : '',
        ok: isCorrect(qi, q)
      }))
    })
    savedToHistory.value = true
  } catch (e) {
    // 保存失败不影响用户看结果
    readingSubmitted = false
    console.warn('[reading] 成绩保存失败', e)
  }
}

/** 只重做错题：清掉错题的作答记录，其余保留 */
function retryWrongReading() {
  const nextPicks = { ...picks.value }
  const nextRevealed = { ...revealed.value }
  wrongQuestions.value.forEach(({ qi }) => {
    delete nextPicks[qi]
    delete nextRevealed[qi]
  })
  picks.value = nextPicks
  revealed.value = nextRevealed
  // 重做算新的一次，允许再次落库
  readingSubmitted = false
  savedToHistory.value = false
  ElMessage.success(`已清空 ${wrongQuestions.value.length} 道错题，可以重新作答`)
}

/** 交给智能体分析这篇阅读 */
function askAiForReadingAnalysis() {
  const wrongWords = wrongQuestions.value
    .map(({ q, qi }) => `第${qi + 1}题「${String(q.questionText || q.title || '').slice(0, 40)}」`)
    .join('；')
  router.push({
    path: '/front/agent/chat',
    state: {
      seedQuestion:
        `我刚做完一篇英语阅读练习，正确率 ${accuracy.value}%（${correctCount.value}/${answeredCount.value}）。` +
        (wrongWords ? `做错的是：${wrongWords}。` : '全部答对了。') +
        '帮我分析一下我的薄弱点，以及接下来该练什么。'
    } as any
  })
}

/** 后端 answer 对选择题是「选项下标（0 起）」也可能是字母/文本，这里统一判 */
function correctIndex(q: any): number {
  const a = q?.answer
  if (typeof a === 'number') return a
  const s = String(a ?? '').trim()
  if (/^[A-Da-d]$/.test(s)) return s.toUpperCase().charCodeAt(0) - 65
  const n = Number(s)
  if (Number.isInteger(n) && n >= 0) return n
  // 文本型答案：回到选项里找
  const idx = (q?.options || []).findIndex(
    (o: any) => stripOptionPrefix(o).trim() === s
  )
  return idx
}

function isCorrect(qi: number, q: any) {
  const pick = picks.value[qi]
  const right = correctIndex(q)
  return pick !== undefined && right >= 0 && pick === right
}

function answerText(q: any) {
  const idx = correctIndex(q)
  if (idx >= 0 && q?.options?.[idx] !== undefined) {
    return `${String.fromCharCode(65 + idx)}. ${stripOptionPrefix(q.options[idx])}`
  }
  return String(q?.answer ?? '（未提供）')
}

function optClass(qi: number, oi: number, q: any) {
  if (!revealed.value[qi]) {
    return { 'is-picked': picks.value[qi] === oi }
  }
  const right = correctIndex(q)
  if (oi === right) return { 'is-right': true }
  if (picks.value[qi] === oi) return { 'is-wrong': true }
  return {}
}

function reset() {
  passage.value = ''
  questions.value = []
  picks.value = {}
  revealed.value = {}
  error.value = ''
  // 重置闭环状态，否则下一篇会被当成「已提交」而不再落库
  readingSubmitted = false
  savedToHistory.value = false
}

// ⚠️ 2026-10-26：「英语学习」的入口首页已下线，返回目标改成「我的词库」。
/*
 * 原 `goBack()` 已删除（2026-10-26）：返回按钮已从模板移除，没有调用方。
 */
</script>

<style scoped lang="scss">
/*
 * 2026-10-26 视觉改造
 * ---------------------------------------------------------------------------
 * 改前：返回按钮占一行，设置卡片贴着顶部，下方约 600px 全是空白。
 * 改后：
 *   · 去掉 `.rd-head`（返回栏已从模板删除）；
 *   · 卡片居中、最大宽度收到 720px，读起来不散；
 *   · 空状态下把设置卡片垂直居中，页面不再是"顶部一小块"。
 *
 * ⚠️ 不能用 `align-items: center` + `justify-content: center` 一起写在小容器上：
 *    `max-width` + `margin: 0 auto` 已经负责水平居中，
 *    再加 `align-items:center` 会把子元素按内容宽度收窄，反而偏右。
 *    这里只做垂直居中。
 */
.rd-page {
  max-width: 720px;
  margin: 0 auto;
  padding: clamp(20px, 3vw, 36px) 20px 48px;
  min-height: calc(100vh - 52px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  /* 卡片撑满容器宽度，而不是按内容收缩 */
  align-items: stretch;
}

/* ---------- 设置 ---------- */
.rd-setup {
  padding: 24px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
}

.rd-field {
  margin-bottom: 14px;
}

.rd-field--inline {
  display: flex;
  align-items: center;
  gap: 12px;
}

.rd-label {
  display: block;
  margin-bottom: 7px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);

  .rd-field--inline & {
    margin-bottom: 0;
  }
}

.rd-generate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  font-size: 13.5px;
  font-weight: 500;
  font-family: inherit;
  border: none;
  border-radius: 8px;
  background: var(--os-text, #111827);
  color: #fff;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #000;
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

.rd-error {
  margin: 12px 0 0;
  font-size: 12.5px;
  color: #dc2626;
}

/* ---------- 生成中 ---------- */
.rd-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 56px 20px;
}

.rd-loading__spinner {
  width: 26px;
  height: 26px;
  border: 2.5px solid var(--os-border, #e5e7eb);
  border-top-color: var(--os-accent, #2563eb);
  border-radius: 50%;
  animation: rd-spin 0.8s linear infinite;
}

@keyframes rd-spin {
  to {
    transform: rotate(360deg);
  }
}

.rd-loading__title {
  margin: 4px 0 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.rd-loading__hint {
  margin: 0;
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);
}

/* ---------- 短文 ---------- */
.rd-article {
  margin-bottom: 18px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.rd-article__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--os-border-light, #f1f3f5);
  background: var(--os-bg-subtle, #fafafa);
}

.rd-article__title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.rd-btn {
  height: 28px;
  padding: 0 11px;
  font-size: 12.5px;
  font-family: inherit;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 7px;
  background: #fff;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }
}

.rd-article__body {
  padding: 16px;
}

.rd-para {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.85;
  color: var(--os-text, #1f2937);

  &:last-child {
    margin-bottom: 0;
  }
}

/* ---------- 题目 ---------- */
/*
 * 成绩汇总条（2026-10-26 闭环）
 * 答完任意一题就出现，实时更新；全部答完后下方追加"已保存"提示。
 */
.rd-summary {
  margin-bottom: 16px;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 14px;
}

.rd-summary__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.rd-summary__score {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rd-summary__pct {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  color: #111827;

  i {
    font-style: normal;
    font-size: 14px;
    font-weight: 600;
    color: #9ca3af;
    margin-left: 2px;
  }
}

.rd-summary__label {
  font-size: 12px;
  color: #9ca3af;
}

.rd-summary__nums {
  display: flex;
  gap: 14px;
  font-size: 13px;
  color: #6b7280;

  .is-ok {
    color: #10b981;
  }

  .is-bad {
    color: #ef4444;
  }
}

.rd-summary__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
}

.rd-summary__saved {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 10px 0 0;
  font-size: 12.5px;
  color: #10b981;
}

.rd-questions {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rd-q {
  padding: 15px 16px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
}

.rd-q__head {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-bottom: 10px;
}

.rd-q__idx {
  flex: none;
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--os-bg-subtle, #f3f4f6);
  font-size: 11px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.rd-q__text {
  font-size: 14px;
  line-height: 1.7;
  color: var(--os-text, #111827);
}

.rd-q__options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rd-opt {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  padding: 9px 11px;
  text-align: left;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 8px;
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  transition: all 0.15s;

  &:hover:not(:disabled) {
    border-color: var(--os-accent, #2563eb);
  }

  &.is-picked {
    border-color: var(--os-accent, #2563eb);
    background: var(--os-accent-50, #eff6ff);
  }

  &.is-right {
    border-color: #16a34a;
    background: #f0fdf4;
  }

  &.is-wrong {
    border-color: #ef4444;
    background: #fef2f2;
  }
}

.rd-opt__key {
  flex: none;
  width: 18px;
  font-weight: 600;
  color: var(--os-text-3, #9ca3af);
}

.rd-opt__text {
  flex: 1;
  min-width: 0;
}

.rd-q__answer {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--os-border, #e5e7eb);
}

.rd-q__verdict {
  font-size: 12.5px;
  font-weight: 600;

  &.is-right {
    color: #16a34a;
  }

  &.is-wrong {
    color: #dc2626;
  }
}

.rd-q__correct {
  font-weight: 400;
  color: var(--os-text-2, #4b5563);
}

.rd-q__analysis {
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--os-text-2, #4b5563);
  white-space: pre-wrap;
}
</style>
