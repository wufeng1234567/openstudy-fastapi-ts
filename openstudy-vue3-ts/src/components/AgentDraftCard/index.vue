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
  <div class="agent-draft" :class="[`is-${status}`, { 'has-sticky': shouldOfferCollapse }]">
    <!--
      批量删除卡（用户 2026-10-17 需求）

      背景：模型为了删 N 个对象会**循环调 N 次 delete**，于是弹 N 张确认卡 ——
      用户点 N 次、中途点错一张就只删了一半。现在后端提供 `delete_many`，
      一次调用生成**一张卡**，把每个对象逐条列出来，用户可以：
        · 逐条勾选（取消勾选 = 这一条不删，方便反悔）
        · 全选 / 全不选
        · 点「确认删除」→ 只删勾选的；一个都不勾 = 取消
      勾选结果随 `edited.selectedKeys` 回传，服务端据此收窄 `*_ids` 再执行
      （前端不自己调删除接口 —— 权限/级联/事务仍走工具层那一条路径）。
    -->
    <template v-if="isBatchDelete">
      <div class="ad-head">
        <span class="ad-icon">
          <OsIcon v-if="status === 'running'" name="alert" :size="14" />
          <OsIcon v-else-if="status === 'ok'" name="check" :size="14" />
          <OsIcon v-else name="close" :size="14" />
        </span>
        <span class="ad-title">批量删除{{ entityLabel }}</span>
        <span class="ad-count">已选 {{ selected.length }} / {{ items.length }}</span>
      </div>

      <div class="bd-toolbar">
        <label class="bd-selectall">
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="someSelected && !allSelected"
            :disabled="readonly"
            @change="toggleAll"
          />
          <span>全选</span>
        </label>
        <span class="bd-hint">取消勾选的不会被删除</span>
      </div>

      <div class="bd-list">
        <label
          v-for="item in items"
          :key="item.key"
          class="bd-item"
          :class="{ 'is-unchecked': !isChecked(item.key), 'is-disabled': readonly }"
        >
          <el-checkbox
            :model-value="isChecked(item.key)"
            :disabled="readonly"
            @change="(v) => toggleOne(item.key, v)"
          />
          <span class="bd-item-main">
            <span class="bd-item-title">{{ item.title }}</span>
            <span v-if="item.subtitle" class="bd-item-sub">{{ item.subtitle }}</span>
          </span>
        </label>
      </div>

      <div class="bd-warn">
        此操作不可撤销。将删除 {{ selected.length }} 个{{ entityLabel }}，未勾选的保留。
      </div>

      <div v-if="status === 'running'" class="ad-actions">
        <button type="button" class="ad-btn ad-cancel" @click="onBatchCancel">全部不删</button>
        <button
          type="button"
          class="ad-btn ad-ok"
          :disabled="!selected.length"
          @click="onBatchConfirm"
        >
          确认删除（{{ selected.length }}）
        </button>
      </div>
      <div v-else class="ad-result">
        {{ status === 'ok' ? `已删除 ${selected.length} 个${entityLabel}` : '已取消，未删除任何内容' }}
      </div>
    </template>

    <template v-else>
    <!--
      吸顶折叠条（2026-10-22）
      ==================================================================
      用户：一张导入预览卡里可能有 15 道题，「需要滚动很久才能看到底部
      或者看到卡片之前的消息」「用户往下滚动的时候可以直接看到那个卡片的按钮
      然后可以直接点击收起来，也可以一键展开」。

      为什么用 sticky 而不是"滚到某处才出现的浮层"：
        · 纯 CSS，浏览器自己算贴合位置，零监听、零边界情况；
        · 只要卡片还有任何一部分在视口内，这条就贴在消息流顶部 ——
          用户滚到卡片中间、甚至底部，按钮都还在手里。

      ⚠️ 必须放在卡片**最外层**、且是第一个子元素：sticky 的贴合范围是
         "最近的滚动祖先"，放进任何嵌套容器都会被那个容器的高度限制住。

      ⚠️ 折叠时**只藏内容、不藏这一条**：否则收起后按钮消失、再也展不开。
    -->
    <div v-if="shouldOfferCollapse" class="ad-sticky" :style="COLLAPSE_BAR_STYLE">
      <span class="ad-sticky-icon" :class="`is-${status}`">
        <OsIcon v-if="status === 'running'" name="pen-line" :size="13" />
        <OsIcon v-else-if="status === 'ok'" name="check" :size="13" />
        <OsIcon v-else name="close" :size="13" />
      </span>
      <span class="ad-sticky-title">导入预览（可编辑）</span>
      <span class="ad-sticky-meta">{{ questions.length }} 题</span>
      <button
        type="button"
        class="ad-sticky-toggle"
        :aria-expanded="!collapsed"
        :title="collapsed ? '展开这张卡片' : '收起这张卡片'"
        @click="toggleCollapse"
      >
        {{ collapsed ? '展开' : '收起' }}
        <span class="ad-sticky-caret" :class="{ 'is-collapsed': collapsed }">▾</span>
      </button>
    </div>

    <!-- 折叠时整块内容不渲染：比 max-height 动画更省，也不会留下可聚焦的隐藏控件 -->
    <template v-if="!collapsed">
    <!--
      ⚠️ 有吸顶条时**不再渲染这个 `.ad-head`**（2026-10-22 修）
      吸顶条已经写了「✎ 导入预览（可编辑）· 15 题」，再渲染一遍标题与数量
      就是完全重复的两行 —— 用户截图里正是「收起」条下面紧跟一行同样的标题。
      只有短卡片（不显示吸顶条）才需要它来提供头部。
    -->
    <div v-if="!shouldOfferCollapse" class="ad-head">
      <span class="ad-icon">
        <OsIcon v-if="status === 'running'" name="pen-line" :size="14" />
          <OsIcon v-else-if="status === 'ok'" name="check" :size="14" />
          <OsIcon v-else name="close" :size="14" />
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
    </template>
    <!--
      ⚠️ 收起时仍保留**动作区**（取消 / 确认导入）
      用户滚下去是为了"别再被这张卡挡住"，不是为了取消这次操作。
      把确认按钮一起藏起来会逼用户先展开再确认，多一步毫无意义。
      这也和吸顶条的分工一致：条上管"看/收"，这里管"定"。
    -->
    <div v-if="collapsed && status === 'running'" class="ad-actions ad-actions--collapsed">
      <button type="button" class="ad-btn ad-cancel" @click="onCancel">取消</button>
      <button type="button" class="ad-btn ad-ok" @click="onConfirm">确认导入</button>
    </div>
    <div v-else-if="collapsed" class="ad-result">
      {{ status === 'ok' ? '已确认导入' : '已取消' }}
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { useCollapseBar, COLLAPSE_BAR_STYLE } from '@/composables/useCollapseBar'

/*
 * 吸顶折叠条（2026-10-22）
 * ----------------------------------------------------------------------------
 * 阈值取 6：一张卡里 6 道题以上就值得给折叠条。
 * 实测一个「导入预览」典型是 10~20 题，卡片高度 1500~3000px，远超一屏；
 * 而 1~5 题的卡通常一屏能看完（或者只多一点点），加折叠条反而多一层干扰。
 */
const { collapsed, setContentLines, shouldOfferCollapse, toggle } = useCollapseBar({
  threshold: 6
})

/** 模板里用（避免把 composable 的返回整体解构进模板） */
const toggleCollapse = toggle

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

/* ============================================================
 * 批量删除模式（`draft.kind === 'batch_delete'`）
 * ============================================================ */

/** 是否走「批量删除勾选」那一套 UI（与建库导入草稿互斥） */
const isBatchDelete = computed(() => String((props.draft as any)?.kind || '') === 'batch_delete')

/** 被删对象的中文名（知识库 / 题库 / 题目 / 笔记） */
const entityLabel = computed(() => String((props.draft as any)?.entityLabel || '对象'))

interface BatchDeleteItem {
  key: string
  id: number
  title: string
  subtitle?: string
}

const items = computed<BatchDeleteItem[]>(() => {
  const raw = (props.draft as any)?.items
  if (!Array.isArray(raw)) return []
  return raw.map((it: any) => ({
    key: String(it?.key ?? `${it?.id ?? ''}`),
    id: Number(it?.id ?? 0),
    title: String(it?.title ?? ''),
    subtitle: it?.subtitle ? String(it.subtitle) : ''
  }))
})

/* ============================================================
 * 吸顶折叠条：内容量级上报
 * ============================================================ */

/**
 * 把"这张卡有多长"告诉折叠条
 *
 * ⚠️ 用**题目条数**而不是 DOM 高度：
 *    折叠后高度会变，若用高度判断"要不要折叠条"就会自相矛盾
 *    （收起 → 变矮 → 判定不需要 → 折叠条消失 → 用户再也展不开）。
 *    条数只随内容变化，与折叠状态无关。
 *
 * 批量删除模式按行数算（多条删除项同样会把卡片撑得很长）。
 * `immediate` 必须开：初始就有内容，不开的话第一帧不显示折叠条。
 */
watch(
  () => [questions.value.length, items.value.length] as const,
  () => {
    const n = isBatchDelete.value ? items.value.length : questions.value.length
    // 每题大约 12 行表单（题干/选项/答案/解析），换算成"行"的量级
    setContentLines(n * 12)
  },
  { immediate: true }
)

/**
 * 勾选状态（默认**全选**）
 *
 * 默认全选的理由：模型调 `delete_many` 时给的就是「用户说要删的那批」，
 * 卡片的作用是让用户**反悔掉个别项**，不是让他从头再选一遍。
 */
const checked = ref<Set<string>>(new Set())

/** 草稿变化（确认卡重渲染 / 新一批删除）→ 重置成全选 */
function resetBatchSelection() {
  checked.value = new Set(items.value.map((it) => it.key))
}
resetBatchSelection()

// 草稿换了（新一批删除请求）→ 重新全选。
// 注意比对的是 items 的 key 串：确认卡按 confirmId 渲染多条时互不干扰。
watch(
  () => items.value.map((it) => it.key).join(','),
  () => resetBatchSelection()
)

const isChecked = (key: string) => checked.value.has(key)
const selected = computed(() => items.value.filter((it) => checked.value.has(it.key)))
const allSelected = computed(() => items.value.length > 0 && selected.value.length === items.value.length)
const someSelected = computed(() => selected.value.length > 0 && !allSelected.value)

function toggleOne(key: string, on: boolean) {
  const next = new Set(checked.value)
  if (on) next.add(key)
  else next.delete(key)
  checked.value = next
}

function toggleAll(on: boolean) {
  checked.value = on ? new Set(items.value.map((it) => it.key)) : new Set()
}

/** 确认删除：只提交勾选的那些（一个都没勾时按钮是禁用的，兜底再判一次） */
function onBatchConfirm() {
  if (readonly.value) return
  const keys = selected.value.map((it) => it.key)
  if (!keys.length) return
  emit('resolve', { approved: true, edited: { selectedKeys: keys } })
}

/** 全部不删 = 取消（服务端会按 cancelled 处理，给模型一个「用户取消」的失败信封） */
function onBatchCancel() {
  if (readonly.value) return
  emit('resolve', { approved: false })
}

/* ============================================================
 * 建库导入草稿模式
 * ============================================================ */

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

/*
 * 有吸顶条时：顶部不留 padding（2026-10-22）
 * ----------------------------------------------------------------------------
 * 吸顶条要**贴到卡片边框内侧**，中间不能有缝。
 *
 * 上一版的做法是用 `margin-top: -14px` 去抵消卡片 14px 的 padding。
 * 数学上是对的，但实测会露出一条 1~2px 的缝：圆角 + 边框的抗锯齿让
 * "负边距刚好抵到边框"这件事并不可靠（不同缩放比下缝的宽度还会变）。
 *
 * 现在直接把卡片顶部 padding 归零，吸顶条天然填满顶部那一块 ——
 * 没有负边距、就没有"算不准"这回事。
 * 注意 `padding-bottom` / 左右保持不变，卡片其余部分的呼吸感不变。
 */
.agent-draft.has-sticky {
  padding-top: 0;
  /*
   * `gap` 也要在顶部这一处失效
   *
   * `.agent-draft` 是 flex 列 + `gap: 12px`。`gap` 加在**每两个子元素之间**，
   * 第一个子元素（吸顶条）与第二个子元素（内容）之间会因此多出 12px ——
   * 看起来就是"吸顶条下面悬空"。这里用负的 `margin-bottom` 让吸顶条
   * 自己吃掉那 12px，使内容紧贴分隔线。
   */
}

.agent-draft.has-sticky > .ad-sticky {
  margin-bottom: -12px;
}

.agent-draft.is-ok {
  border-left-color: #22c55e;
}

.agent-draft.is-fail {
  border-left-color: #9ca3af;
}

/* ============================================================
 * 吸顶折叠条（2026-10-22）
 * ============================================================ */

/*
 * 为什么用负边距 + 内边距"反向抵消"
 * ----------------------------------------------------------------------------
 * 卡片本身有 `padding: 14px`。如果那条直接放在内容流里，它会缩进 14px、
 * 左右留出空白 —— 滚动时底下的内容会从两侧透出来，看起来像"悬浮残影"。
 *
 * 用 `margin: -14px -14px 0` 把它拉到卡片边缘（宽出 padding 那一圈），
 * 再补回自己的左右内边距，得到一条**通栏、不透光**的吸附条。
 *
 * ⚠️ 2026-10-22 追加修复：卡片顶部改成 `padding-top: 0`（见 `.agent-draft`
 *    的 `.has-sticky` 变体），这条的 `margin-top` 也随之归零。
 *    原来的 `-14px` 负边距与 14px padding 相互抵消时，圆角与边框的
 *    抗锯齿会让吸附条**上沿露出一条 1~2px 的缝**（用户截图里能看到）。
 *    现在直接让卡片顶部没有 padding，吸附条天然贴在边框内侧 ——
 *    没有负边距、就不会算错。
 */
.ad-sticky {
  display: flex;
  align-items: center;
  gap: 8px;
  /* 左右仍用负边距抵消卡片 padding；顶部不用了（卡片已无 padding-top） */
  margin: 0 -14px 0;
  padding: 10px 14px;
  background: #fff;
  border-bottom: 1px solid #eef0f3;
  border-radius: 9px 9px 0 0;
  font-size: 12.5px;
  line-height: 1.4;
}

.ad-sticky-icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: #6366f1;
}

.ad-sticky-icon.is-ok {
  color: #22c55e;
}

.ad-sticky-icon.is-fail {
  color: #9ca3af;
}

.ad-sticky-title {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--os-text, #1f2937);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ad-sticky-meta {
  flex: none;
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--os-bg-subtle, #f5f6f8);
}

/*
 * 折叠按钮：贴右，文字 + 小箭头
 *
 * 用文字按钮而不是圆形图标：
 *   · 「收起 / 展开」两个字零歧义，图标（chevron / minus）在这个场景里
 *     容易被理解成"滚动到这里"或"删除这条"；
 *   · 与卡片内其它按钮（ad-del / ad-add-opt 均为文字）风格一致。
 */
.ad-sticky-toggle {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  line-height: 1.3;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.ad-sticky-toggle:hover {
  color: var(--os-accent, #6366f1);
  border-color: currentColor;
  background: var(--os-bg-hover, #f7f8fa);
}

.ad-sticky-toggle:focus-visible {
  outline: 2px solid var(--os-primary, #0f1115);
  outline-offset: 2px;
}

/* 箭头：展开朝下、收起朝上，用位移表达"内容的方向" */
.ad-sticky-caret {
  display: inline-block;
  font-size: 10px;
  line-height: 1;
  transition: transform 0.18s ease;
}

.ad-sticky-caret.is-collapsed {
  transform: rotate(180deg);
}

/* 收起后那排动作区：吸顶条下面直接跟按钮，不要卡片原本的大间距 */
.ad-actions--collapsed {
  margin-top: -4px;
}

.ad-head {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  font-size: 13.5px;
  line-height: 1.55;
}

/*
 * 状态图标：**纯线条 + 语义色**，不要实心圆底
 * --------------------------------------------------------------------
 * 原来是 18px 实心靛紫圆（white 图标压在上面）。同一屏里「深度思考」是细线星光
 * svg、「工具结果 / 确认卡」也都是 OsIcon 线条 —— 实心色块混在里面很跳
 * （用户 2026-10-18 指出风格不统一）。统一成透明底 + 描边图标 + 语义色。
 */
.ad-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}

.is-ok .ad-icon {
  color: #22c55e;
}

.is-fail .ad-icon {
  color: var(--os-text-4, #9ca3af);
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

/* ============================================================
   批量删除卡（勾选清单）
   ============================================================ */

.bd-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 0 2px;
}

.bd-selectall {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: #374151;
  cursor: pointer;
  user-select: none;
}

.bd-hint {
  margin-left: auto;
  font-size: 11.5px;
  color: #9ca3af;
}

.bd-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
  padding-right: 2px;
}

.bd-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 11px;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
  cursor: pointer;
  min-width: 0;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.bd-item:hover {
  background: #f1f5f9;
  border-color: #e2e8f0;
}

/* 取消勾选的行：整行变淡 + 标题加删除线，一眼看出「这条不删」 */
.bd-item.is-unchecked {
  opacity: 0.55;
  background: #fff;
}

.bd-item.is-unchecked .bd-item-title {
  text-decoration: line-through;
  color: #9ca3af;
}

.bd-item.is-disabled {
  cursor: not-allowed;
}

.bd-item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1 1 auto;
}

.bd-item-title {
  font-size: 13px;
  color: #1f2937;
  word-break: break-word;
}

.bd-item-sub {
  font-size: 11.5px;
  color: #6b7280;
}

.bd-warn {
  font-size: 11.5px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 7px;
  padding: 6px 10px;
}
</style>
