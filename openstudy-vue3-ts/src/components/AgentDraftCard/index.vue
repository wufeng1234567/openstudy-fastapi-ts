<!-- components/AgentDraftCard/index.vue -->
<!--
  建库导入「可编辑草稿」卡片（需求二）

  确认卡片不再只是「看着预览点确认」——用户在导入前可以直接改题库信息、每一道题
  （含组合题的子题），还能给 AI 留一句修改意见让它重新生成。

  草稿来源：后端 `question_manage._build_import_draft` 挂在确认预览的 `preview.draft` 上
  （形状 `{ kind, bank, questions }`，camelCase）。用户在卡片里的改动通过 `resolve`
  事件回传，最终随 `POST /ai/agent/confirm` 的 `edited` 送到服务端覆盖工具参数再执行。
  ⚠️ 服务端会**重新校验**这份 `edited`（见 `loop._apply_edited_params`），所以这里只管
  收集用户输入，不做业务校验。

  事件载荷（`resolve`）：
    · 确认导入 → `{ approved: true, edited: { bank, questions } }`
    · 取消     → `{ approved: false }`
    · 重新生成 → `{ approved: false, regenerate: true, opinion }`（由页面转为取消 + 追问一轮）
-->
<template>
  <div class="agent-draft" :class="`is-${status}`">
    <div class="ad-head">
      <span class="ad-icon">
        <span v-if="status === 'running'">✎</span>
        <span v-else-if="status === 'ok'">✓</span>
        <span v-else>×</span>
      </span>
      <span class="ad-title">导入预览（可编辑）</span>
      <span class="ad-count">{{ questions.length }} 题</span>
    </div>

    <!-- 题库信息 -->
    <div class="ad-bank">
      <div class="ad-field">
        <label class="ad-label">题库名称</label>
        <el-input v-model="bank.bankName" :disabled="readonly" size="small" placeholder="题库名称" />
      </div>
      <div class="ad-field-row">
        <div class="ad-field ad-field--grow">
          <label class="ad-label">科目</label>
          <el-input v-model="bank.subject" :disabled="readonly" size="small" placeholder="科目" />
        </div>
        <div class="ad-field ad-field--narrow">
          <label class="ad-label">可见性</label>
          <el-select v-model="bank.isPublic" :disabled="readonly" size="small" style="width: 100%">
            <el-option :value="0" label="公开" />
            <el-option :value="1" label="私密" />
          </el-select>
        </div>
      </div>
      <div class="ad-field">
        <label class="ad-label">简介</label>
        <el-input
          v-model="bank.description"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          size="small"
          placeholder="简介"
        />
      </div>
      <div v-if="!bank.bankId" class="ad-bank-new">新题库（导入时创建）</div>
    </div>

    <!-- 题目清单 -->
    <div class="ad-questions">
      <div v-for="(q, qi) in questions" :key="qi" class="ad-q">
        <div class="ad-q-head">
          <span class="ad-q-no">第 {{ qi + 1 }} 题</span>
          <el-select
            v-model="q.questionType"
            :disabled="readonly"
            size="small"
            class="ad-type"
            @change="onTypeChange(q)"
          >
            <el-option v-for="t in QUESTION_TYPES" :key="t.value" :value="t.value" :label="t.label" />
          </el-select>
          <button type="button" class="ad-del" :disabled="readonly" @click="removeQuestion(qi)">删除</button>
        </div>

        <el-input
          v-model="q.questionText"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          size="small"
          placeholder="题干"
        />

        <!-- 选项（单选 / 多选） -->
        <div v-if="showOptions(q)" class="ad-options">
          <div v-for="(opt, oi) in q.options" :key="oi" class="ad-opt">
            <span class="ad-opt-no">{{ optionLabel(oi) }}</span>
            <el-input v-model="q.options[oi]" :disabled="readonly" size="small" />
            <button type="button" class="ad-opt-del" :disabled="readonly" @click="removeOption(q, oi)">×</button>
          </div>
          <button type="button" class="ad-add-opt" :disabled="readonly" @click="addOption(q)">＋ 选项</button>
        </div>

        <div class="ad-answer">
          <label class="ad-label">答案</label>
          <el-input v-model="q.answer" :disabled="readonly" size="small" placeholder="答案" />
        </div>

        <el-input
          v-model="q.analysis"
          :disabled="readonly"
          type="textarea"
          :rows="1"
          size="small"
          placeholder="解析（可选）"
        />

        <!-- 组合题：子题清单 -->
        <div v-if="isComposite(q)" class="ad-subs">
          <div class="ad-subs-head">子题（{{ q.subQuestions.length }}）</div>
          <div v-for="(sub, si) in q.subQuestions" :key="si" class="ad-sub">
            <div class="ad-sub-head">
              <span class="ad-q-no">{{ qi + 1 }}.{{ si + 1 }}</span>
              <el-select v-model="sub.questionType" :disabled="readonly" size="small" class="ad-type" @change="onSubTypeChange(sub)">
                <el-option v-for="t in QUESTION_TYPES" :key="t.value" :value="t.value" :label="t.label" />
              </el-select>
              <button type="button" class="ad-sub-up" :disabled="readonly || si === 0" @click="moveSub(q, si, -1)">↑</button>
              <button type="button" class="ad-sub-down" :disabled="readonly || si === q.subQuestions.length - 1" @click="moveSub(q, si, 1)">↓</button>
              <button type="button" class="ad-del" :disabled="readonly" @click="removeSub(q, si)">删除</button>
            </div>
            <el-input v-model="sub.questionText" :disabled="readonly" type="textarea" :rows="2" size="small" placeholder="子题题干" />
            <div v-if="showOptions(sub)" class="ad-options">
              <div v-for="(opt, oi) in sub.options" :key="oi" class="ad-opt">
                <span class="ad-opt-no">{{ optionLabel(oi) }}</span>
                <el-input v-model="sub.options[oi]" :disabled="readonly" size="small" />
                <button type="button" class="ad-opt-del" :disabled="readonly" @click="removeOption(sub, oi)">×</button>
              </div>
              <button type="button" class="ad-add-opt" :disabled="readonly" @click="addOption(sub)">＋ 选项</button>
            </div>
            <div class="ad-answer">
              <label class="ad-label">答案</label>
              <el-input v-model="sub.answer" :disabled="readonly" size="small" placeholder="答案" />
            </div>
            <el-input v-model="sub.analysis" :disabled="readonly" type="textarea" :rows="1" size="small" placeholder="解析（可选）" />
          </div>
          <button type="button" class="ad-add-sub" :disabled="readonly" @click="addSub(q)">＋ 子题</button>
        </div>
      </div>

      <button type="button" class="ad-add-q" :disabled="readonly" @click="addQuestion">＋ 添加题目</button>
    </div>

    <!-- 修改意见（给 AI，可选）：非空才允许「重新生成」 -->
    <div v-if="status === 'running'" class="ad-opinion">
      <el-input
        v-model="opinion"
        type="textarea"
        :rows="2"
        size="small"
        placeholder="给 AI 的修改意见（可选）：例如「题干再简洁些」「换一批更简单的题」…"
      />
    </div>

    <div v-if="status === 'running'" class="ad-actions">
      <button type="button" class="ad-btn ad-cancel" @click="onCancel">取消</button>
      <button type="button" class="ad-btn ad-regen" :disabled="!opinion.trim()" @click="onRegenerate">
        让 AI 重新生成
      </button>
      <button type="button" class="ad-btn ad-ok" @click="onConfirm">确认导入</button>
    </div>
    <div v-else class="ad-result">{{ status === 'ok' ? '已确认导入' : '已取消' }}</div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'

const props = defineProps({
  /** 后端草稿：`{ kind:'question_bank_import', bank, questions }` */
  draft: { type: Object as () => Record<string, any> | null, default: null },
  /** running=可编辑待确认；ok=已确认；fail=已取消 */
  status: { type: String, default: 'running' },
  /** 外部强制禁用（例如整轮已在跑别的） */
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['resolve'])

/** 题型（与后端 `question_write_service.QUESTION_TYPE_TEXT` 一致，含 6/7 的细分名） */
const QUESTION_TYPES = [
  { value: 1, label: '单选题' },
  { value: 2, label: '多选题' },
  { value: 3, label: '判断题' },
  { value: 4, label: '填空题' },
  { value: 5, label: '简答题' },
  { value: 6, label: '阅读理解（组合题）' },
  { value: 7, label: '完形填空（组合题）' }
]

const OPTION_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

/** 选项：数组原样、JSON 串解析、逗号串拆分；空 → [] */
function normalizeOptions(raw: any): string[] {
  if (Array.isArray(raw)) return raw.filter((x) => x !== null && x !== undefined).map(String)
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return []
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed)) return parsed.map(String)
    } catch {
      /* 退化成逗号分隔 */
    }
    return text.split(/[,\n;，；]+/).map((s) => s.trim()).filter(Boolean)
  }
  return []
}

/** 答案统一成字符串（后端 `_batch_import` 也是 `str(answer)`）；数组 → 逗号串 */
function normalizeAnswer(raw: any): string {
  if (raw === null || raw === undefined) return ''
  if (Array.isArray(raw)) return raw.join(',')
  return String(raw)
}

function cloneSub(raw: any) {
  const src = raw && typeof raw === 'object' ? raw : {}
  return {
    questionType: Number(src.questionType ?? src.question_type ?? 1) || 1,
    questionText: String(src.questionText ?? src.question_text ?? ''),
    options: normalizeOptions(src.options),
    answer: normalizeAnswer(src.answer),
    analysis: String(src.analysis ?? ''),
    _src: src
  }
}

function cloneQuestion(raw: any) {
  const src = raw && typeof raw === 'object' ? raw : {}
  const subsRaw = src.subQuestions ?? src.sub_questions ?? src.questionSubList
  return {
    questionType: Number(src.questionType ?? src.question_type ?? 1) || 1,
    questionText: String(src.questionText ?? src.question_text ?? ''),
    options: normalizeOptions(src.options),
    answer: normalizeAnswer(src.answer),
    analysis: String(src.analysis ?? ''),
    subQuestions: Array.isArray(subsRaw) ? subsRaw.map(cloneSub) : [],
    _src: src
  }
}

const bank = reactive({
  bankId: null as number | null,
  bankName: '',
  subject: '',
  description: '',
  isPublic: 0 as number
})
const questions = ref<ReturnType<typeof cloneQuestion>[]>([])
const opinion = ref('')

function reset() {
  const d = props.draft || {}
  const b = (d.bank || {}) as Record<string, any>
  bank.bankId = b.bankId ?? null
  bank.bankName = String(b.bankName ?? '')
  bank.subject = String(b.subject ?? '')
  bank.description = String(b.description ?? '')
  bank.isPublic = Number(b.isPublic) === 1 ? 1 : 0
  questions.value = (Array.isArray(d.questions) ? d.questions : []).map(cloneQuestion)
}
reset()

const readonly = computed(() => props.status !== 'running' || props.disabled)

function isComposite(q: { questionType: number }): boolean {
  return q.questionType === 6 || q.questionType === 7
}

/** 选项编辑器只对单选 / 多选露出（判断题选项固定、其余无选项） */
function showOptions(q: { questionType: number }): boolean {
  return q.questionType === 1 || q.questionType === 2
}

function optionLabel(i: number): string {
  return OPTION_LETTERS[i] || String(i + 1)
}

function ensureOptions(q: any) {
  if (!Array.isArray(q.options)) q.options = []
}

function onTypeChange(q: any) {
  if (q.questionType === 3) {
    q.options = ['正确', '错误']
  } else if (showOptions(q)) {
    ensureOptions(q)
    while (q.options.length < 2) q.options.push('')
  }
}

function onSubTypeChange(sub: any) {
  onTypeChange(sub)
}

function addOption(q: any) {
  ensureOptions(q)
  q.options.push('')
}

function removeOption(q: any, i: number) {
  ensureOptions(q)
  q.options.splice(i, 1)
}

function addQuestion() {
  questions.value.push(cloneQuestion({}))
}

function removeQuestion(i: number) {
  questions.value.splice(i, 1)
}

function addSub(q: any) {
  if (!Array.isArray(q.subQuestions)) q.subQuestions = []
  q.subQuestions.push(cloneSub({}))
}

function removeSub(q: any, i: number) {
  q.subQuestions.splice(i, 1)
}

function moveSub(q: any, i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= q.subQuestions.length) return
  const [item] = q.subQuestions.splice(i, 1)
  q.subQuestions.splice(j, 0, item)
}

/** 子题出参：保留原始未知字段（content / score…），覆盖可编辑字段 */
function buildSub(sub: any) {
  const out = { ...(sub._src || {}) }
  delete out.sub_questions
  out.questionType = sub.questionType
  out.questionText = sub.questionText
  out.options = normalizeOptions(sub.options)
  out.answer = normalizeAnswer(sub.answer)
  out.analysis = sub.analysis
  return out
}

/** 题目出参：同上；组合题带上 `subQuestions`（并清掉可能存在的旧 `sub_questions`） */
function buildQuestion(q: any) {
  const out = { ...(q._src || {}) }
  out.questionType = q.questionType
  out.questionText = q.questionText
  out.options = normalizeOptions(q.options)
  out.answer = normalizeAnswer(q.answer)
  out.analysis = q.analysis
  if (isComposite(q)) {
    out.subQuestions = (q.subQuestions || []).map(buildSub)
    delete out.sub_questions
  } else {
    delete out.subQuestions
    delete out.sub_questions
  }
  return out
}

function buildEdited() {
  return {
    bank: {
      bankId: bank.bankId,
      bankName: bank.bankName,
      subject: bank.subject,
      description: bank.description,
      isPublic: bank.isPublic
    },
    questions: questions.value.map(buildQuestion)
  }
}

function onConfirm() {
  if (readonly.value) return
  emit('resolve', { approved: true, edited: buildEdited() })
}

function onCancel() {
  if (readonly.value) return
  emit('resolve', { approved: false })
}

function onRegenerate() {
  if (readonly.value) return
  const text = opinion.value.trim()
  if (!text) return
  emit('resolve', { approved: false, regenerate: true, opinion: text })
}
</script>

<style scoped>
.agent-draft {
  border: 1px solid #e5e7eb;
  border-left: 3px solid #6366f1;
  border-radius: 10px;
  padding: 14px;
  background: #fff;
  max-width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-draft.is-ok {
  border-left-color: #22c55e;
}

.agent-draft.is-fail {
  border-left-color: #9ca3af;
}

.ad-head {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  font-size: 13.5px;
  line-height: 1.55;
}

.ad-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: #6366f1;
}

.is-ok .ad-icon {
  background: #22c55e;
}

.is-fail .ad-icon {
  background: #9ca3af;
}

.ad-title {
  font-weight: 600;
  color: #1f2937;
}

.is-ok .ad-title,
.is-fail .ad-title {
  color: #4b5563;
}

.ad-count {
  margin-left: auto;
  font-size: 11px;
  color: #4b5563;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  padding: 1px 8px;
  border-radius: 9px;
}

.ad-bank {
  padding: 12px;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
  box-sizing: border-box;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ad-field {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ad-field--grow {
  flex: 1 1 auto;
  min-width: 0;
}

.ad-field--narrow {
  flex: none;
  width: 168px;
}

.ad-field-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.ad-label {
  flex: none;
  width: 60px;
  font-size: 12px;
  color: #6b7280;
}

.ad-bank-new {
  font-size: 11px;
  color: #6366f1;
}

.ad-field :deep(.el-input),
.ad-opt :deep(.el-input),
.ad-answer :deep(.el-input) {
  min-width: 0;
}

.ad-questions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ad-q {
  padding: 12px;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
  box-sizing: border-box;
  max-width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ad-q-head,
.ad-sub-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.ad-q-no {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.ad-type {
  flex: 1 1 auto;
  min-width: 0;
}

.ad-del {
  flex: none;
  margin-left: auto;
  font-size: 12px;
  color: #b91c1c;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.ad-del:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #fca5a5;
}

.ad-del:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ad-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ad-opt {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.ad-opt-no {
  flex: none;
  width: 18px;
  text-align: center;
  font-size: 12px;
  color: #6b7280;
}

.ad-opt-del {
  flex: none;
  width: 22px;
  height: 22px;
  line-height: 1;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.ad-opt-del:hover:not(:disabled) {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #374151;
}

.ad-add-opt,
.ad-add-sub,
.ad-add-q {
  align-self: flex-start;
  font-size: 12px;
  color: #4f46e5;
  background: #fff;
  border: 1px dashed #c7d2fe;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.ad-add-opt:hover:not(:disabled),
.ad-add-sub:hover:not(:disabled),
.ad-add-q:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #a5b4fc;
}

.ad-add-q {
  align-self: stretch;
  text-align: center;
}

.ad-answer {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ad-subs {
  padding: 10px;
  border: 1px solid #e8eef5;
  border-radius: 8px;
  background: #f1f5f9;
  box-sizing: border-box;
  max-width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ad-subs-head {
  font-size: 12px;
  font-weight: 600;
  color: #4b5563;
}

.ad-sub {
  padding: 10px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  background: #fff;
  box-sizing: border-box;
  max-width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ad-sub-up,
.ad-sub-down {
  flex: none;
  width: 22px;
  height: 22px;
  line-height: 1;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.ad-sub-up:disabled,
.ad-sub-down:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ad-opinion {
  min-width: 0;
}

.ad-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.ad-btn {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 5px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.ad-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ad-cancel {
  background: #fff;
  border-color: #d1d5db;
  color: #4b5563;
}

.ad-cancel:hover:not(:disabled) {
  border-color: #9ca3af;
  color: #1f2937;
}

.ad-regen {
  background: #fff;
  border-color: #6366f1;
  color: #4f46e5;
}

.ad-regen:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #4f46e5;
}

.ad-ok {
  background: #4f46e5;
  color: #fff;
}

.ad-ok:hover:not(:disabled) {
  background: #4338ca;
}

.ad-result {
  font-size: 12px;
  color: #6b7280;
  text-align: right;
}
</style>
