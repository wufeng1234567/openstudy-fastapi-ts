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
    <header class="rd-head">
      <button type="button" class="rd-back" @click="goBack">
        <OsIcon name="arrow-left" :size="16" />
        <span>英语学习</span>
      </button>
      <div class="rd-head__main">
        <h1 class="rd-head__title">阅读练习</h1>
        <p class="rd-head__desc">
          说一句你想练什么，AI 会写一篇短文并出几道题。
        </p>
      </div>
    </header>

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
        // 短文可能挂在题目上（composite 形态），也可能单独给
        const first = list[0] || {}
        passage.value = String(first.passage || first.title || '')
        questions.value = list.map((q: any) => ({
          ...q,
          // 没有 passage 的题目就是普通题，短文留空即可
          title: q.title || ''
        }))

        // 如果所有题都没有 passage，说明后端只给了纯题目
        if (!passage.value) {
          const anyWithPassage = list.find((q: any) => q.passage)
          if (anyWithPassage) passage.value = String(anyWithPassage.passage)
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
}

function goBack() {
  cacheStore.setLastVisited('english', 'home')
  router.push('/front/english/home')
}
</script>

<style scoped lang="scss">
.rd-page {
  max-width: 820px;
  margin: 0 auto;
  padding: 20px 20px 60px;
}

.rd-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
}

.rd-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 10px;
  flex: none;
  font-size: 13px;
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

.rd-head__main {
  flex: 1;
  min-width: 0;
}

.rd-head__title {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.rd-head__desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

/* ---------- 设置 ---------- */
.rd-setup {
  padding: 18px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
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
