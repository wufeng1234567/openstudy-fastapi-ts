<!-- components/AgentToolResult/index.vue -->
<!--
  一条「工具调用」卡片

  信息分三层，从「一眼扫过」到「按需深究」：

    第一层  状态 + 结果摘要   —— 成没成、结果是什么（最重要，独立一行、可换行）
    第二层  工具 · 动作       —— 这是哪个工具的哪个动作（元信息，小字胶囊）
    第三层  错误 / 入参返回   —— 出错原因 + 「请求内容 / 执行结果」（默认收起）

  ⚠️ 为什么不再把三层挤在一行：助手抽屉是可拖拽调宽的，窄的时候
     「结果文案 + 右对齐的工具名」会在同一行里互相挤，工具名还是 `bank_manage.list`
     这种长标识符，结果就是某一行的字全糊在一起、还看不出主次。

  ⚠️ 第三层展开后**不显示 JSON**：这个助手是给学习者用的，不是开发者调试台。
     入参/返回交给 `AgentToolDetail` 渲染成键值行、小卡、胶囊（布尔 → 是/否、
     字段名 → 中文），见那个组件的注释。

  响应式：靠**纯纵向堆叠**本身 —— 结果文案自己占一行、小胶囊 `flex-wrap` 换行、
  长词 `overflow-wrap: anywhere` 断行、详情区靠 `max-width: 100%` 收窄。多窄都不会出现「同一行互相挤」。
  ⚠️ 别再试图用 `container-type` 做「按卡片宽度自适应」（踩过坑，见下方 `.agent-tool` 注释）；
  真要按宽度变样式只能上 ResizeObserver，为这点内边距不值得。
-->
<template>
  <div class="agent-tool" :class="[`is-${status}`]">
    <!-- ① 状态 + 结果摘要 -->
    <div class="at-head">
      <span class="at-icon" aria-hidden="true">
        <span v-if="status === 'running'" class="at-spinner"></span>
        <span v-else-if="status === 'ok'">✓</span>
        <span v-else>!</span>
      </span>
      <span class="at-summary">{{ summary }}</span>
    </div>

    <!-- ② 工具 · 动作（原始标识符只在 title 里，不占视线） -->
    <div v-if="toolLabel || errorCount || (status === 'running' && elapsed >= 1)" class="at-meta">
      <span v-if="toolLabel" class="at-tool" :title="toolPath">{{ toolLabel }}</span>
      <span v-if="errorCount" class="at-badge">{{ errorCount }} 项错误</span>
      <!-- 运行中显示已用时，让用户看到"它在动"而不是傻等 -->
      <span v-if="status === 'running' && elapsed >= 1" class="at-elapsed">已用时 {{ elapsed }}s</span>
    </div>

    <!-- ③ 错误原因 -->
    <div v-if="status === 'fail' && errors.length" class="at-errors">
      <div v-for="(err, i) in errors" :key="i" class="at-error-line">· {{ err }}</div>
    </div>

    <!-- ③ 入参 / 返回（渲染成人能看的形式，不是 JSON） -->
    <div v-if="hasDetails" class="at-details">
      <span class="at-toggle" @click="expanded = !expanded">
        <span class="at-caret" :class="{ 'is-open': expanded }">▸</span>
        {{ expanded ? '收起' : (status === 'running' ? '查看执行过程' : '查看详情') }}
      </span>

      <div v-if="expanded" class="at-body">
        <div v-if="hasParams" class="at-section">
          <div class="at-section-title">请求内容</div>
          <AgentToolDetail :data="params" />
        </div>
        <div v-if="hasData" class="at-section">
          <div class="at-section-title">执行结果</div>
          <AgentToolDetail :data="data" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import AgentToolDetail from '@/components/AgentToolDetail/index.vue'

const props = defineProps({
  tool: { type: String, default: '' },
  action: { type: String, default: '' },
  /** 主文案（进行中/已执行的说明或工具返回的 message） */
  content: { type: String, default: '' },
  /** 工具返回的详细结果（覆盖 content 显示） */
  detail: { type: String, default: '' },
  status: { type: String, default: 'running' },
  errors: { type: Array as () => string[], default: () => [] },
  params: { type: Object as () => Record<string, any> | null, default: null },
  data: { type: Object as () => Record<string, any> | null, default: null }
})

const expanded = ref(false)

/* ============================================================
 * 运行中「已用时」计时器
 *
 * 工具执行（尤其批量导入几十道题）可能耗时数秒。卡片只有转圈时，用户分不清
 * 「在跑」还是「卡死了」。这里每秒刷新已用时，给出「确实在动」的可见反馈。
 * 仅在 status==='running' 时计时；转为 ok/fail 即停止并清零。
 * ============================================================ */
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const stopTimer = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
const startTimer = () => {
  stopTimer()
  elapsed.value = 0
  const startedAt = Date.now()
  timer = setInterval(() => {
    elapsed.value = Math.floor((Date.now() - startedAt) / 1000)
  }, 1000)
}

watch(
  () => props.status,
  (s) => {
    if (s === 'running') startTimer()
    else stopTimer()
  },
  { immediate: true }
)

onBeforeUnmount(stopTimer)

/* ============================================================
 * 第一层：结果摘要
 * ============================================================ */

/**
 * 工具 / 动作的「人话」名字；映射表里没有的照原样显示，新工具不会因此变成空白
 * —— 但也因此会**把英文标识符直接打在用户脸上**（`question_flag_manage · master`）。
 *
 * ⚠️ 工具名必须与后端 `app/services/ai/agent/tools/*.py` 里那个 `name = "…"` 一一对应：
 *    清单是 10 个（bank_manage / question_manage / note_manage / question_flag_manage /
 *    memory_manage / learning_stats / knowledge_base_manage / bank_share_manage /
 *    knowledge_search / memory_search）。漏一个，用户看到的就是那个英文标识符。
 *    这条由 `tests/check_frontend_static.mjs` 的 L46 / L47 **读后端注册表自动比对**，别只靠眼睛。
 */
const TOOL_LABELS: Record<string, string> = {
  bank_manage: '题库管理',
  question_manage: '题目管理',
  note_manage: '笔记管理',
  // 2026-09-21：收藏 / 错题 / 斩题三工具合并成一个 question_flag_manage（按 flag_type 分）
  question_flag_manage: '题目标记',
  memory_manage: '记忆管理',
  learning_stats: '学习统计',
  knowledge_base_manage: '知识库管理',
  bank_share_manage: '题库分享',
  // 只读检索类：它们没有 action 参数，卡片上只有工具名这一层
  knowledge_search: '知识库检索',
  memory_search: '记忆检索',
  // 指挥家「派发专家」的元工具：对用户只该说「请专家帮忙」，不该露出 delegate_task
  delegate_task: '请专家帮忙'
}

/**
 * 动作 → 中文。**键必须覆盖每个工具 schema 里 `action` 的那个 enum**
 * （见 `question_mark_manage.py:156` / `memory_manage.py:78` / `learning_stats.py:61` /
 *  `knowledge_base_manage.py:97` / `bank_share_manage.py:100`）——
 * 少一个键，卡片第二层就是「题目标记 · master」这种半截英文。
 */
const ACTION_LABELS: Record<string, string> = {
  list: '查询列表',
  detail: '查看详情',
  search: '搜索',
  create: '创建',
  update: '更新',
  delete: '删除',
  delete_by_name: '按名删除',
  delete_many: '批量删除',
  list_categories: '查询分类',
  clear_questions: '清空题目',
  batch_import: '批量导入',
  // question_flag_manage
  add: '添加',
  master: '标记已掌握',
  remove: '删除/取消',
  // memory_manage
  list_types: '记忆概览',
  forget: '忘记',
  clear: '清空',
  // learning_stats
  overview: '概览',
  by_subject: '按科目',
  trend: '学习趋势',
  error_analysis: '错题分析',
  growth: '成长记录',
  // knowledge_base_manage
  list_documents: '文档列表',
  delete_document: '删除文档',
  // bank_share_manage
  list_shares: '分享列表',
  share: '创建分享',
  revoke: '撤销分享',
  receive: '领取分享',
  copy: '复制题库',
  // delegate_task（指挥家派发专家）
  delegate: '派发'
}

const STATUS_WORDS: Record<string, string> = {
  running: '进行中',
  ok: '完成',
  fail: '失败'
}

const labelOf = (map: Record<string, string>, key: string) => map[key] || key

/**
 * 这些文案等于「没说话」，不能当卡片主行。
 *
 * 后端多数工具只在 `data` 里给结构化结果、**不给 message**，
 * 而前端的兜底是 `result?.message || (success ? 'OK' : '失败')`（agentDsFree），
 * 于是卡片主行就变成一句信息量为零的 "OK" —— 用户看到的就是 `✓ OK bank_manage.list`。
 */
const FILLER_MESSAGES = new Set([
  'ok',
  'ok.',
  'success',
  'success.',
  'done',
  'done.',
  '成功',
  '已完成',
  '完成',
  '失败'
])

/**
 * 从 `data` 里凑一句人话；凑不出返回空串。
 *
 * ⚠️ 顺序有讲究：**数组 / 具名字段排在通用计数之前**。
 *    `bank_manage.list` 的返回是 `{count, banks}`，先命中 `banks` 才能说出
 *    「共 3 个题库」，先命中 `count` 就只能说「共 3 条」，等于白说。
 */
const DATA_SUMMARIES: [string, (n: number) => string][] = [
  ['banks', (n) => `共 ${n} 个题库`],
  ['questions', (n) => `共 ${n} 道题目`],
  ['notes', (n) => `共 ${n} 篇笔记`],
  ['categories', (n) => `共 ${n} 个笔记分类`],
  ['imported', (n) => `已导入 ${n} 道题目`],
  ['deleted', (n) => `已删除 ${n} 项`],
  ['items', (n) => `共 ${n} 条结果`],
  ['count', (n) => `共 ${n} 条`],
  ['total', (n) => `共 ${n} 条`]
]

/** 摘要最长多少字（题干可能很长，卡片主行不该被它撑到三行） */
const MAX_SUMMARY_CHARS = 80

const clip = (text: string) => {
  const s = (text || '').trim()
  return s.length > MAX_SUMMARY_CHARS ? `${s.slice(0, MAX_SUMMARY_CHARS)}…` : s
}

function summarizeData(data: any): string {
  if (!data || typeof data !== 'object') return ''
  for (const [key, render] of DATA_SUMMARIES) {
    const value = data[key]
    const isList = Array.isArray(value)
    const n = isList ? value.length : typeof value === 'number' ? value : null
    if (n === null) continue
    // ⚠️ 数组长度 ≠ 总数：`question_manage.list` 默认只回 20 条，题库可能有 30 道。
    //    这时后端会一并给出 `total`（真总量），按数组长度说「共 20 道题目」就是错的。
    if (isList && typeof data.total === 'number' && data.total > n) {
      return `${render(data.total)}（本次返回 ${n} 条）`
    }
    return render(n)
  }
  // 单个对象（bank_manage.detail 的 bank / question_manage.detail 的 question /
  // note_manage.detail 的 note）→ 报它的名字或题干，比干巴巴一句「查看详情完成」有用得多
  const named =
    data.bankName ||
    data.bank_name ||
    data.name ||
    data.note?.title ||
    data.title ||
    data.bank?.bankName ||
    data.question?.questionText ||
    data.keyword
  return named ? clip(String(named)) : ''
}

const summary = computed(() => {
  // `content` 是「进行中」时的实时说明（「正在查询题库…」）。跑完之后它就**过期了**，
  // 不能再当结论 —— api 链路里工具不给 message 时 detail 为空，
  // `fillTool` 会保留旧的 content，卡片就会定格在「正在查询题库…」上配一个绿勾。
  // 所以：进行中才读 content，已结束只认 detail（工具返回的 message）。
  const raw = (props.status === 'running' ? props.detail || props.content : props.detail).trim()
  if (raw && !FILLER_MESSAGES.has(raw.toLowerCase())) return raw

  const derived = summarizeData(props.data)
  if (derived) return derived

  // 实在推不出来：退回「动作 + 状态」，至少能看出它在干什么、跑完没有
  const actionWord = props.action ? labelOf(ACTION_LABELS, props.action) : ''
  const statusWord = STATUS_WORDS[props.status] || ''
  return `${actionWord}${statusWord}` || statusWord || '执行中'
})

/* ============================================================
 * 第二层：工具 · 动作
 * ============================================================ */

/** 原始标识符（bank_manage.list）—— 只进 title，方便排查问题时看 */
const toolPath = computed(() => [props.tool, props.action].filter(Boolean).join('.'))

const toolLabel = computed(() => {
  if (!props.tool) return ''
  const tool = labelOf(TOOL_LABELS, props.tool)
  return props.action ? `${tool} · ${labelOf(ACTION_LABELS, props.action)}` : tool
})

const errorCount = computed(() => (props.status === 'fail' ? props.errors.length : 0))

/* ============================================================
 * 第三层：详情
 * ============================================================ */

const nonEmpty = (v: Record<string, any> | null) => Boolean(v && Object.keys(v).length > 0)

/** 有入参或有返回值才给「查看详情」 */
const hasDetails = computed(() => nonEmpty(props.params) || nonEmpty(props.data))

const hasParams = computed(() => nonEmpty(props.params))
const hasData = computed(() => nonEmpty(props.data))
</script>

<style scoped>
.agent-tool {
  border: 1px solid #e5e7eb;
  border-left: 3px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 14px;
  background: #fff;
  max-width: 100%;
  box-sizing: border-box;
  /*
   * ⚠️ 这里**不能**用 `container-type: inline-size` 做「按卡片宽度自适应」。
   *   卡片挂在 `.message-content` 下面，而它是 flex 里的 **fit-content** 项
   *   （`.message` 是 `display:flex`，`.message-content` 只有 max-width、没有 width）。
   *   一旦卡片自己开启 inline-size 容器，它的宽度就「不再由内容决定」，
   *   于是父级的 fit-content 算出来是 0 → 整张卡片塌成一条、文字被逐字换行。
   *   （已用无头 Chrome 实测：加容器时宽度 2px，去掉后 320px。）
   *   要按宽度自适应只能上 ResizeObserver —— 为这点内边距不值得。
   */
}

.agent-tool.is-running {
  border-left-color: #60a5fa;
  background: #f8fbff;
}

.agent-tool.is-ok {
  border-left-color: #34d399;
}

.agent-tool.is-fail {
  border-left-color: #f87171;
  background: #fffafa;
}

/* ===================== 第一层：状态 + 结果 ===================== */
.at-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13.5px;
  line-height: 1.5;
}

.at-icon {
  flex: none;
  width: 18px;
  height: 18px;
  /* 跟第一行文字对齐（18px 的圆压在 1.5 行高的文字上会略高，往下压 1px） */
  margin-top: 1px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: #cbd5e1;
}

.is-running .at-icon {
  background: #60a5fa;
}

.is-ok .at-icon {
  background: #34d399;
}

.is-fail .at-icon {
  background: #f87171;
}

.at-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #fff;
  border-radius: 50%;
  animation: at-spin 0.7s linear infinite;
  box-sizing: border-box;
}

@keyframes at-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 结果文案自己占满剩余宽度并自由换行 —— 这是「不再挤一行」的关键 */
.at-summary {
  flex: 1;
  min-width: 0;
  color: #1f2d3d;
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* ===================== 第二层：工具 · 动作 ===================== */
.at-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.at-tool,
.at-badge {
  font-size: 11px;
  line-height: 1.65;
  padding: 0 8px;
  border-radius: 9px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.at-tool {
  color: #6b7280;
  background: #f3f4f6;
  border: 1px solid #eceff3;
  font-family: inherit;
}

.at-badge {
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

/* 运行中「已用时」标签：低饱和蓝，暗示"进行中" */
.at-elapsed {
  font-size: 11px;
  line-height: 1.65;
  padding: 0 8px;
  border-radius: 9px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #dbeafe;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* ===================== 第三层：错误 / 详情 ===================== */
.at-errors {
  margin-top: 7px;
  font-size: 12px;
  color: #b91c1c;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.at-details {
  margin-top: 7px;
}

.at-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
}

.at-toggle:hover {
  color: #2563eb;
}

.at-caret {
  display: inline-block;
  transition: transform 0.15s ease;
}

.at-caret.is-open {
  transform: rotate(90deg);
}

/*
 * 展开后的详情区（请求内容 / 执行结果）
 *
 * 卡片本身是 fit-content（见 `AiChatStream` 里 `.msg-tool_result .message-content` 的注释），
 * 收起时只有 ~240px；展开后需要更宽才好读键值行 —— 这里用 `width` 给一个「倾向宽度」
 * 把它自然撑开。
 *
 * ⚠️ 必须用 `width` + `max-width: 100%`，**不能**用 `min-width`：
 *   `min-width` 的优先级高于 `max-width`，窄屏下会顶穿气泡横向溢出；
 *   而 `width` 会被 `max-width: 100%` 正常夹住。
 */
.at-body {
  width: 420px;
  max-width: 100%;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.at-section {
  padding: 9px 11px;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #fbfcfe;
}

.at-section-title {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #8a94a6;
  letter-spacing: 0.4px;
}

/* ===================== 窄卡片 =====================
 * 不再用容器查询（见 `.agent-tool` 的注释）：卡片本身就**纯纵向堆叠** ——
 * 结果文案自己占一行、小胶囊 `flex-wrap` 换行、长词 `overflow-wrap: anywhere`
 * 断行、`AgentToolDetail` 的键值行自己换行。所以窄到多窄都不会出现「同一行互相挤」。
 * 唯一的宽度自适应是收紧内边距，那点收益换来整张卡片塌掉，不划算。
 */
</style>
