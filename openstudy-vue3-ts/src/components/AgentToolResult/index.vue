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
      <!--
        状态图标统一走 `OsIcon`（2026-10-18）：
        原来是字形 ✓ / — / !，与全站线性图标不是一套语言。
        运行中仍用细转圈（它不是"图标"，是"正在动"的指示）。
      -->
      <span class="at-icon" aria-hidden="true">
        <span v-if="status === 'running'" class="at-spinner"></span>
        <OsIcon v-else-if="status === 'ok'" name="check" :size="13" />
        <OsIcon v-else-if="status === 'cancelled'" name="minus" :size="13" />
        <OsIcon v-else name="alert" :size="13" />
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

    <!--
      ③ 产物卡片（`bank_export` 等「产出文件」的工具）
      ==================================================================
      为什么单独一层而不是塞进详情里：
        详情是「点开才看」的调试信息，而**文件本身就是这次操作的成果**。
        用户说「导出这个题库」，他要的不是一行「导出完成」，是那个能下载的文件。
        把它折叠进「查看详情」等于把成品藏起来，只给看流水账。

      为什么不显示原始 `downloadUrl`：
        那是一条 `/profile/export/2026/10/20/<uuid>_题库名.docx`。让人复制粘贴这种
        路径是给开发者用的，不是给学习者用的。点按钮下载才是正常的交互。
    -->
    <div v-if="artifact" class="at-artifact">
      <span class="at-artifact-icon" aria-hidden="true">
        <OsIcon name="file-text" :size="15" />
      </span>
      <span class="at-artifact-main">
        <span class="at-artifact-name">{{ artifact.fileName }}</span>
        <span class="at-artifact-meta">{{ artifact.meta }}</span>
      </span>
      <button type="button" class="at-artifact-btn" :disabled="downloading" @click="downloadArtifact">
        <span v-if="downloading" class="at-artifact-spinner" aria-hidden="true"></span>
        <OsIcon v-else name="download" :size="13" />
        <span>{{ downloading ? '下载中…' : '下载' }}</span>
      </button>
    </div>

    <!-- ③ 跳转卡片：建库/导题完成后，一步直达题库 -->
    <div v-if="bankJump" class="at-jump">
      <div class="at-jump__main">
        <span class="at-jump__badge">
          <OsIcon name="check-circle" :size="13" />
          {{ bankJump.isNew ? '题库已建好' : '题目已导入' }}
        </span>
        <span class="at-jump__name">{{ bankJump.bankName }}</span>
        <span v-if="bankJump.meta" class="at-jump__meta">{{ bankJump.meta }}</span>
      </div>
      <button type="button" class="at-jump__btn at-jump__btn--primary" @click="goToBank">
        <OsIcon name="book-open" :size="13" />
        <span>立即开始刷题</span>
      </button>
    </div>

    <!-- ④ 跳转卡片：笔记写完/改完，一步直达那篇笔记 -->
    <div v-if="noteJump" class="at-jump">
      <div class="at-jump__main">
        <span class="at-jump__badge">
          <OsIcon name="check-circle" :size="13" />
          {{ noteJump.isNew ? '笔记已发布' : '笔记已更新' }}
        </span>
        <span class="at-jump__name">{{ noteJump.title }}</span>
        <span v-if="noteJump.meta" class="at-jump__meta">{{ noteJump.meta }}</span>
      </div>
      <button type="button" class="at-jump__btn at-jump__btn--primary" @click="goToNote">
        <OsIcon name="file-text" :size="13" />
        <span>查看笔记</span>
      </button>
    </div>

    <!--
      ④b 通用跳转卡片（2026-10-26）
      ------------------------------
      任何工具只要在回执里带上 `jumpUrl`，就自动获得一张「去看看」卡片。

      为什么要有这条通用通道：原来只有 `bank_manage` / `note_manage` /
      `question_manage` 三处**硬编码**的跳转（各自判 bankId / noteId）。
      新加的 `english_wordbook` 回执里带的是 `jumpUrl`（词库页地址），
      前端不认 —— 用户看到的是「已创建词书『雅思核心词』」加一个折叠的
      `▸ 查看详情`，**下一步又断了**，闭环差最后一环。

      有了它，以后任何工具（英语词库、知识库、学习统计…）只要返回
      `jumpUrl` + 一句 message，就自动接上"去哪儿看"的入口，
      不用每加一个工具就改一次这个组件。
    -->
    <div v-if="linkJump" class="at-jump">
      <div class="at-jump__main">
        <span class="at-jump__badge">
          <OsIcon name="check-circle" :size="13" />
          {{ linkJump.badge }}
        </span>
        <span class="at-jump__name">{{ linkJump.name }}</span>
        <span v-if="linkJump.meta" class="at-jump__meta">{{ linkJump.meta }}</span>
      </div>
      <button type="button" class="at-jump__btn at-jump__btn--primary" @click="goToLink">
        <OsIcon :name="linkJump.icon" :size="13" />
        <span>{{ linkJump.buttonText }}</span>
      </button>
    </div>

    <!-- ⑤ 「AI 翻文件」可视化：它在空间里找到了什么 -->
    <div v-if="spaceScan" class="at-scan">
      <div class="at-scan__head">
        <span class="at-scan__icon" :class="{ 'is-done': spaceScan.done }">
          <OsIcon :name="spaceScan.done ? 'check-circle' : 'search'" :size="13" />
        </span>
        <span class="at-scan__title">
          {{ spaceScan.done ? '在空间里找到了' : '正在翻你的空间…' }}
        </span>
        <span v-if="spaceScan.query" class="at-scan__query">「{{ spaceScan.query }}」</span>
      </div>

      <ul class="at-scan__list">
        <li
          v-for="(f, i) in spaceScan.files"
          :key="f.docId || i"
          class="at-scan__file"
          :class="{ 'is-best': i === 0 && spaceScan.done }"
        >
          <span class="at-scan__dot" />
          <span class="at-scan__name">{{ f.fileName }}</span>
          <span v-if="f.note" class="at-scan__note">{{ f.note }}</span>
          <span v-if="i === 0 && spaceScan.done" class="at-scan__tag">最匹配</span>
        </li>
      </ul>

      <div v-if="spaceScan.done && spaceScan.count === 0" class="at-scan__empty">
        空间里没有对得上的文件
      </div>
      <div v-else-if="spaceScan.done && spaceScan.summary" class="at-scan__summary">
        {{ spaceScan.summary }}
      </div>
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
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import AgentToolDetail from '@/components/AgentToolDetail/index.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { getToken } from '@/utils/auth'

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
 *    清单是 13 个（bank_manage / question_manage / note_manage / question_flag_manage /
 *    memory_manage / learning_stats / knowledge_base_manage / knowledge_ingest /
 *    bank_share_manage / knowledge_search / memory_search / agent_manage / delegate_task）。
 *    漏一个，用户看到的就是那个英文标识符。
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
  // 内容入库（knowledge_ingest.py）：与管理知识库的 knowledge_base_manage 分工
  knowledge_ingest: '写入知识库',
  bank_share_manage: '题库分享',
  // 题库导出（bank_export.py）：产出文件，卡片上有独立的「产物行 + 下载按钮」
  bank_export: '题库导出',
  // 只读检索类：它们没有 action 参数，卡片上只有工具名这一层
  knowledge_search: '知识库检索',
  memory_search: '记忆检索',
  // 工作空间找文件（workspace_search.py）——2026-10-22
  workspace_search: '找资料',
  // 用户自定义智能体的管理工具（agent_manage.py）
  agent_manage: '智能体管理',
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
  create_category: '新建分类',
  clear_questions: '清空题目',
  batch_import: '批量导入',
  // note_manage（写草稿；正式笔记的创建走 create/update）
  save_draft: '保存草稿',
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
  // 2026-10-20 新增：逐题学情诊断（不是聚合数字，见 study_diagnosis_service）
  diagnose: '学情诊断',
  plan_review: '排复习计划',
  diagnose_report: '学情报告',
  // knowledge_base_manage
  list_documents: '文档列表',
  delete_document: '删除文档',
  // knowledge_ingest
  from_text: '文本入库',
  from_attachment: '附件入库',
  // bank_share_manage
  list_shares: '分享列表',
  share: '创建分享',
  revoke: '撤销分享',
  receive: '领取分享',
  copy: '复制题库',
  // bank_export（导出成文件；两个版本的文案不同，让用户在卡片上一眼分清）
  export: '导出文件',
  // delegate_task（指挥家派发专家）
  delegate: '派发'
}

const STATUS_WORDS: Record<string, string> = {
  running: '进行中',
  ok: '完成',
  fail: '失败',
  cancelled: '已取消'
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
  // `diagnose` / `diagnose_report` 的结论句：它们不是数组、也没有 named 字段，
  // 但后端专门给了 `headline`（算法算出的那句话）。不特判的话卡片主行会退化成
  // 「学情诊断完成」，等于把最有信息量的那句话扔掉。
  if (typeof data.headline === 'string' && data.headline.trim()) {
    return clip(data.headline)
  }
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

/* ============================================================
 * 产物卡片（工具产出了**文件**，如 bank_export 的 Word / PDF）
 * ============================================================ */

/**
 * 这个工具的返回里是否有「一份可下载的文件」
 *
 * 判据落在 `downloadUrl` 上，而不是「tool === 'bank_export'」：
 * 将来任何工具（学情报告 PDF、笔记导出、错题本导出）只要回执里给 `downloadUrl`，
 * 就自动获得这张卡片，不必回来改这里。工具的**输出契约**比工具名稳定。
 */
const artifact = computed(() => {
  if (props.status !== 'ok') return null
  const d = props.data
  if (!d || typeof d !== 'object') return null
  const url = typeof d.downloadUrl === 'string' ? d.downloadUrl.trim() : ''
  if (!url) return null

  const format = String(d.format || '').toLowerCase()
  const parts: string[] = []
  if (d.version) parts.push(String(d.version))
  if (d.questionCount) parts.push(`${d.questionCount} 道题`)
  if (d.fileSizeText) parts.push(String(d.fileSizeText))

  return {
    url,
    format,
    fileName: String(d.fileName || (format === 'pdf' ? '导出文件.pdf' : '导出文件.docx')),
    meta: parts.join(' · ')
  }
})

/* ============================================================
 * 跳转卡片（工具刚建好/填好一个题库，用户下一步就是「去刷题」）
 * ============================================================ */

/**
 * 为什么需要这张卡片
 * ----------------
 * 建库成功后，AI 会回一句「题库已建好，共 20 题」。然后呢？
 * 用户得自己去点「题库练习」→ 找一个可能重名的库 → 再点「查看详情」→
 * 再选练习模式。**从"建好了"到"开始刷"要 4 次点击**。
 *
 * 这里把「建好了」和「去刷题」缝在一起：回执里只要有 `bankId`，
 * 就在这条工具结果下面直接给一个按钮，一点直达题库详情页。
 *
 * 判据同样落在**输出契约**（bankId + 有意义的动作）上，而不是工具名：
 *   · bank_manage(action=create)        → 建库完成
 *   · question_manage(action=batch_import) → 题目导完了
 *   · 后续任何工具只要回执带 bankId，自动获得这张卡
 */
const BANK_ACTIONS = new Set(['create', 'batch_import', 'import', 'update'])

/**
 * 从工具回执里找出「题库」对象。
 *
 * ⚠️ 2026-10-22 修 bug：不同工具的回执结构**不一样**，这里原先只读顶层字段，
 * 于是 `bank_manage(action=create)` 完全不出卡片 —— 因为它把题库信息放在
 * **嵌套的 `bank` 对象**里：
 *
 *   bank_manage(create)           → { action:'create', bank:{bankId,bankName,totalQuestions,...}, message }
 *   question_manage(batch_import) → { action:'batch_import', bankId, bankName, imported, bankTotal }
 *   bank_manage(update)           → { action:'update', bank:{...} }
 *
 * 所以先看 `d.bank` 是否有 bankId，没有再看顶层。两条路都覆盖，
 * 以后哪个工具换成另一种写法也不会再丢卡片。
 */
function pickBankPayload(d: any): any | null {
  if (!d || typeof d !== 'object') return null
  const nested = d.bank
  if (nested && typeof nested === 'object') {
    const nid = nested.bankId ?? nested.bank_id ?? nested.id
    if (nid) return nested
  }
  const did = d.bankId ?? d.bank_id ?? d.id
  if (did) return d
  return null
}

/** 只有题库类工具才出「去刷题」卡片 */
const BANK_TOOLS = new Set(['bank_manage', 'question_manage'])

const bankJump = computed(() => {
  if (props.status !== 'ok') return null
  // 加工具白名单：下面的 `pickBankPayload` 会兜底读顶层 `id`，
  // 若不限定工具，别的工具回执里恰好有个 `id` 也会被误当成题库。
  if (props.tool && !BANK_TOOLS.has(props.tool)) return null
  const d = props.data
  if (!d || typeof d !== 'object') return null

  const payload = pickBankPayload(d)
  if (!payload) return null

  const bankId = Number(payload.bankId ?? payload.bank_id ?? payload.id ?? 0)
  if (!bankId) return null

  // 只对「刚建好 / 刚填好」的动作出卡片；
  // list / detail 这类只读查询回执里也有 bankId，但那时用户并不需要跳转
  const action = String(d.action || props.action || '').toLowerCase()
  if (action && !BANK_ACTIONS.has(action)) return null

  const bankName = String(payload.bankName || payload.bank_name || payload.name || '题库')
  const total = Number(payload.bankTotal ?? payload.totalQuestions ?? payload.total_questions ?? d.imported ?? 0)

  // 副标题：优先说「共几题」，其次是「本次导入了几题」
  const metaParts: string[] = []
  if (total > 0) metaParts.push(`共 ${total} 题`)
  if (d.imported) metaParts.push(`本次导入 ${d.imported} 题`)
  const subject = payload.subject || d.subject
  if (subject) metaParts.push(String(subject))

  return {
    bankId,
    bankName,
    meta: metaParts.join(' · '),
    isNew: action === 'create',
    total
  }
})

const router = useRouter()

/**
 * 跳到题库详情页
 *
 * ⚠️ 2026-10-22 修 bug：原来用 `window.location.hash = '#/front/...'` 直接改地址栏，
 *    结果**只有 hash 变了、页面没切换**（vue-router 没收到这次导航）。
 *    必须走 `router.push()`，让路由守卫、组件挂载、keep-alive 都正常触发。
 */
function goToBank() {
  const b = bankJump.value
  if (!b) return
  router.push(`/front/questionPractice/${b.bankId}`)
}

/* ============================================================
 * 笔记跳转卡片（note_manage）
 * ============================================================ */

/** 只有「刚写完 / 刚改完」才给入口；list / detail 这类只读回执不需要 */
const NOTE_ACTIONS = new Set(['create', 'update'])

/**
 * 为什么笔记也要这张卡
 * ------------------
 * 用户对 AI 说「帮我建一篇笔记」，AI 回一句「已保存到分类 Vue（ID=467）」——
 * 信息是全的，但**下一步没了**：想看看它写成什么样，得自己离开对话、
 * 点进「学习管理 → 笔记管理」、再在一堆笔记里找那篇。
 *
 * 建题库早就有「立即开始刷题」这种一步直达，笔记不该是二等公民。
 *
 * 回执结构（`note_manage._create` / `_update`）：
 *   { action:'create', note:{ noteId, title, categoryId, visibility, statusText, tags, ... }, message }
 * 与题库一样，笔记信息在**嵌套的 `note` 对象**里，不是顶层字段 —— 照抄顶层字段会拿不到。
 */
const noteJump = computed(() => {
  if (props.tool !== 'note_manage') return null
  if (props.status !== 'ok') return null
  const d = props.data
  if (!d || typeof d !== 'object') return null

  const action = String(d.action || '').toLowerCase()
  if (action && !NOTE_ACTIONS.has(action)) return null

  const note = d.note && typeof d.note === 'object' ? d.note : d
  const noteId = Number(note.noteId ?? note.note_id ?? 0)
  if (!noteId) return null

  const title = String(note.title || '笔记')

  // 副标题挑用户最关心的两件事：可见性（发给谁看）+ 标签
  const metaParts: string[] = []
  if (note.visibility) metaParts.push(String(note.visibility))
  const tags = String(note.tags || '').trim()
  if (tags) metaParts.push(tags.replace(/,/g, ' · '))

  return {
    noteId,
    title,
    meta: metaParts.join(' · '),
    isNew: action === 'create'
  }
})

function goToNote() {
  const n = noteJump.value
  if (!n) return
  router.push(`/front/notes/detail/${n.noteId}`)
}

/* ============================================================
 * 通用跳转卡片（2026-10-26）
 * ============================================================ */

/**
 * 判据落在**输出契约**上：回执里有非空的 `jumpUrl` 字符串 → 出一张卡。
 * 不按工具名白名单 —— 那正是原来每加一个工具就要改一次组件的根因。
 *
 * 为什么需要它：`english_wordbook` 的回执带 `jumpUrl`（词库页地址），
 * 但前端只认 `bankId` / `noteId`，于是用户看到「已创建词书『雅思核心词』」
 * 后面跟一个折叠的 `▸ 查看详情`，**下一步又断了**，闭环差最后一环。
 *
 * 有了它，以后任何工具只要返回 `jumpUrl` + 一句 message，
 * 就自动接上"去哪儿看"的入口。
 *
 * 只对「写操作」出卡：`list_books` / `stats` 这类只读回执也带 jumpUrl
 * （方便用户去看），但用户当时只是问问，弹一张卡反而打断阅读。
 */
const LINK_WRITE_ACTIONS = new Set([
  'create_book',
  'rename_book',
  'add_word',
  'batch_add_words'
])

/** 不同工具落地页的文案/图标（没配的走默认） */
const LINK_UI: Record<string, { badge: string; buttonText: string; icon: string }> = {
  english_wordbook: { badge: '词库已更新', buttonText: '去看看', icon: 'book' }
}

const linkJump = computed(() => {
  if (props.status !== 'ok') return null

  const d = props.data
  if (!d || typeof d !== 'object') return null

  const raw = d.jumpUrl
  if (typeof raw !== 'string' || !raw.trim()) return null

  // 只读 action 不出卡（见上方注释）
  const action = String(d.action || props.action || '').toLowerCase()
  if (action && !LINK_WRITE_ACTIONS.has(action)) return null

  // 已经被 bankJump / noteJump 覆盖的，不重复出卡
  if (bankJump.value || noteJump.value) return null

  const ui = LINK_UI[String(props.tool || '')] || {
    badge: '已保存',
    buttonText: '去看看',
    icon: 'arrow-right'
  }

  /*
   * 卡片标题：从回执里挑一个像"名字"的字段。
   * ⚠️ 注意 `create_book` 的回执把词书放在**嵌套的 `book` 对象**里
   *    （`{action, book: {bookId, bookName...}, message}`），而 `batch_add_words`
   *    是顶层 `bookName`。原来只读顶层，导致「已创建词书」那张卡片标题是空的。
   */
  const nested = d.book && typeof d.book === 'object' ? d.book : null
  const name = String(
    d.bookName || nested?.bookName || d.noteTitle || d.title || ''
  )
  const meta =
    typeof d.message === 'string'
      ? d.message
      : d.addedCount
        ? `本次加入 ${d.addedCount} 个`
        : ''

  return {
    url: raw.trim(),
    badge: ui.badge,
    buttonText: ui.buttonText,
    icon: ui.icon,
    name,
    meta
  }
})

/**
 * 跳转到通用 jumpUrl
 *
 * ⚠️ 必须走 `router.push()`，不能改 `location.hash` ——
 *    后者只改地址栏、vue-router 收不到导航（见 `goToBank` 的注释）。
 */
function goToLink() {
  const j = linkJump.value
  if (!j) return
  router.push(j.url)
}

/* ============================================================
 * 「AI 翻文件」可视化（workspace_search）
 * ============================================================ */

/**
 * 为什么单独做这张卡
 * ----------------
 * `workspace_search` 发生时，界面上原本只有一行「找资料 · search」，
 * 用户（和评委）完全看不到 AI **去了哪里、翻到了什么**。
 *
 * 而这件事恰恰是这个功能最值得展示的部分：
 * 用户说「用那份概率论的资料出题」，AI 不是凭空变出题，
 * 是真的在他的资料抽屉里翻了一遍、挑中了《概率论与数理统计.pdf》。
 *
 * 所以这里把回执渲染成「翻文件」的过程：
 *   · 运行中：正在翻你的空间…
 *   · 完成后：在空间里找到了 + 文件清单（第一个标「最匹配」）
 */
const spaceScan = computed(() => {
  if (props.tool !== 'workspace_search') return null
  const d = props.data
  const running = props.status === 'running'

  // 运行中还没有 data（工具没跑完），只显示「正在翻」
  if (running) {
    const q = props.params?.query || ''
    return { done: false, query: q, files: [], count: 0, summary: '' }
  }
  if (props.status !== 'ok' || !d || typeof d !== 'object') return null

  const files = Array.isArray(d.files) ? d.files : []
  return {
    done: true,
    query: d.query || '',
    files,
    count: Number(d.count ?? files.length),
    summary: typeof d.message === 'string' ? d.message : ''
  }
})


const downloading = ref(false)

/**
 * 下载产物
 *
 * ⚠️ 必须走 axios **带 Authorization 头**再转 Blob，不能直接
 *     `window.open(url)` / `<a download>`：`/profile/**` 是静态挂载，
 *     但整站接口都要登录态；直接开新窗口会拿到 401 的 JSON 而不是文件
 *     （而且跨域场景下那个错误会被浏览器静默吞掉，用户只会觉得「点了没反应」）。
 */
const downloadArtifact = async () => {
  const a = artifact.value
  if (!a || downloading.value) return
  downloading.value = true
  try {
    const resp = await axios.get(`${import.meta.env.VITE_APP_BASE_API}${a.url}`, {
      responseType: 'blob',
      timeout: 180000,
      headers: getToken() ? { Authorization: 'Bearer ' + getToken() } : {}
    })
    const blob: Blob = resp.data
    if (!blob || typeof blob.slice !== 'function') {
      ElMessage.error('下载失败：服务端未返回文件')
      return
    }
    // 服务端出错时回来的是 JSON（不是文件），不能存成 .docx 让用户打开时发现损坏
    if (blob.type && blob.type.includes('application/json')) {
      try {
        const json = JSON.parse(await blob.text())
        ElMessage.error(json?.msg || '下载失败')
      } catch {
        ElMessage.error('下载失败')
      }
      return
    }
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = a.fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    // 延迟回收：立刻 revoke 在部分浏览器里会让下载中断
    setTimeout(() => URL.revokeObjectURL(href), 4000)
  } catch (e: any) {
    ElMessage.error(e?.message ? `下载失败：${e.message}` : '下载失败')
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
/*
 * 工具调用 = **对话流里的一行**，不是一张卡（用户 2026-10-17：
 * "Agent 的输出不需要那些白色边框容器包裹，想要 DSH 那种简洁效果"）。
 *
 * 去掉：白底、1px 描边、左侧彩色竖条、圆角、内边距。
 * 保留：状态图标（✓ / 转圈 / !）+ 一句结果摘要 + 可展开的详情。
 * 状态不再靠"彩色边框"表达，而是靠图标自身的颜色与形状。
 */
.agent-tool {
  border: none;
  border-radius: 0;
  padding: 0;
  background: transparent;
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

/* 状态差异只体现在图标颜色上（不再用整块底色 / 左侧竖条） */
.agent-tool.is-running .at-icon {
  color: var(--os-accent);
}

.agent-tool.is-ok .at-icon {
  color: var(--dsw-static-green-500);
}

.agent-tool.is-fail .at-icon {
  color: var(--os-danger);
}

/* 用户取消：中性灰，不是红（取消不是错误） */
.agent-tool.is-cancelled .at-icon {
  color: var(--os-text-4);
}

/* ===================== 第一层：状态 + 结果 ===================== */
.at-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13.5px;
  line-height: 1.5;
}

/*
 * 状态图标：**纯线条 + 语义色**，不要实心圆底
 * --------------------------------------------------------------------
 * 原来这里是 18px 实心彩圆（white 图标压在上面）：running 蓝 / ok 绿 / fail 红。
 * 而同一屏里「深度思考」用的是细线星光 svg、「确认卡」也是 OsIcon 线条 ——
 * 实心色块与细线条混排，观感明显不统一（用户 2026-10-18 标箭头指出）。
 *
 * 现在统一成和 AgentReasoning 同一套语言：透明底 + 1.75 描边线性图标 + 语义色。
 * 颜色只表达状态，不再用色块压视觉。
 */
.at-icon {
  flex: none;
  width: 16px;
  height: 16px;
  /* 跟第一行文字对齐（图标压在 1.5 行高的文字上会略高，往下压 2px） */
  margin-top: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--os-text-3, #6b7280);
}

.is-running .at-icon {
  color: #3b82f6;
}

.is-ok .at-icon {
  color: #22c55e;
}

.is-fail .at-icon {
  color: #ef4444;
}

.is-cancelled .at-icon {
  color: var(--os-text-4, #9ca3af);
}

/*
 * 进行中的转圈：原来用白色 2px 边框（因为底色是深色圆）。
 * 现在没有底色了，改成当前语义色，否则白圈在白底上完全看不见。
 */
.at-spinner {
  width: 10px;
  height: 10px;
  border: 1.75px solid currentColor;
  border-top-color: transparent;
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

/* ===================== 第三层：错误 / 产物 / 详情 ===================== */
.at-errors {
  margin-top: 7px;
  font-size: 12px;
  color: #b91c1c;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

/*
 * 产物行（工具产出了文件）—— 一行：图标 + 文件名/元信息 + 下载按钮
 *
 * 刻意**不加**底色与描边（与工具卡片本身同一条原则：Agent 输出不套白框）。
 * 分隔靠「与上一行的间距 + 文件名加粗」，不靠画一个盒子。
 */
.at-artifact {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  max-width: 100%;
}

.at-artifact-icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: var(--os-text-3, #6b7280);
}

/* ============================================================
 * 跳转卡片：建库/导题完成 → 一键去刷题
 *
 * 与「产物卡片」的区别：产物卡片是**极简一行**（工具流水账里的一份文件），
 * 这里是**一张有边界的小卡**——因为它是这一轮对话的「成果落地」，
 * 值得占一点视觉重量。但仍不套大白框，用浅底 + 发丝描边，与整站一致。
 * ============================================================ */
.at-jump {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 10px;
  padding: 12px 14px;
  max-width: 460px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: var(--os-bg-subtle, #fafafa);
}

/* 左侧信息：徽标 / 题库名 / 副标题，纵向三行紧密排布 */
.at-jump__main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0; /* 让长题库名可以正常收缩换行，不把按钮挤出去 */
}

.at-jump__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--os-success, #16a34a);
}

.at-jump__name {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--os-text, #111827);
  word-break: break-all;
}

.at-jump__meta {
  font-size: 12px;
  line-height: 1.35;
  color: var(--os-text-3, #6b7280);
}

/* 按钮固定不掉行，避免长题库名把它压换行 */
.at-jump__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  padding: 7px 14px;
  font-size: 13px;
  white-space: nowrap;
  border-radius: 8px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  transition: all 0.15s;
}

.at-jump__btn:hover {
  border-color: var(--os-accent, #2563eb);
  color: var(--os-accent, #2563eb);
}

.at-jump__btn--primary {
  background: var(--os-text, #111827);
  border-color: var(--os-text, #111827);
  color: #fff;
  font-weight: 500;
}

.at-jump__btn--primary:hover {
  background: #000;
  border-color: #000;
  color: #fff;
}

/* 窄屏：横向排不下时回落成上下两段，按钮靠左 */
@media (max-width: 560px) {
  .at-jump {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}

/* ============================================================
 * 「AI 翻文件」可视化
 *
 * 与跳转卡片同一视觉语言（浅底 + 发丝描边 + 12px 圆角），
 * 但更「过程感」：左侧一条竖线模拟"扫描"，文件一行一行浮出来。
 * ============================================================ */
.at-scan {
  margin-top: 10px;
  padding: 12px 14px;
  max-width: 480px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: var(--os-bg-subtle, #fafafa);
}

.at-scan__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
  margin-bottom: 9px;
}

.at-scan__icon {
  display: inline-flex;
  color: var(--os-text-3, #9ca3af);
}

.at-scan__icon.is-done {
  color: var(--os-success, #16a34a);
}

.at-scan__query {
  font-weight: 400;
  color: var(--os-text-3, #6b7280);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.at-scan__list {
  list-style: none;
  margin: 0;
  padding: 0 0 0 10px;
  border-left: 1.5px solid var(--os-border, #e5e7eb);
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.at-scan__file {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--os-text, #111827);
  padding: 2px 0;
  animation: at-scan-in 0.25s ease-out;
}

@keyframes at-scan-in {
  from {
    opacity: 0;
    transform: translateX(-4px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.at-scan__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--os-border, #d1d5db);
  flex: none;
}

.at-scan__file.is-best .at-scan__dot {
  background: var(--os-success, #16a34a);
}

.at-scan__file.is-best .at-scan__name {
  font-weight: 600;
}

.at-scan__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.at-scan__note {
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.at-scan__tag {
  margin-left: auto;
  flex: none;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--os-success, #16a34a);
  background: var(--os-success-bg, #ecfdf5);
  padding: 1px 6px;
  border-radius: 4px;
}

.at-scan__empty {
  margin-top: 8px;
  padding-left: 12px;
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);
}

.at-scan__summary {
  margin-top: 9px;
  padding-left: 12px;
  font-size: 11.5px;
  color: var(--os-text-3, #6b7280);
  line-height: 1.6;
}

.at-artifact-main {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.at-artifact-name {
  font-size: 12.5px;
  color: var(--os-text, #111827);
  font-weight: 500;
  /* 题库名可能很长 —— 省略而不是撑破卡片 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.at-artifact-meta {
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
  white-space: nowrap;
}

.at-artifact-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 9px;
  font-size: 12px;
  color: var(--os-text-2, #4b5563);
  background: transparent;
  border: 1px solid var(--os-border, #0000001a);
  border-radius: var(--os-radius-sm, 6px);
  cursor: pointer;
  transition: background var(--ds-duration-base, 0.15s) ease,
    border-color var(--ds-duration-base, 0.15s) ease;
}

.at-artifact-btn:hover:not(:disabled) {
  background: var(--os-fill, #f3f4f6);
  border-color: var(--os-border-strong, #00000033);
}

.at-artifact-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.at-artifact-spinner {
  width: 10px;
  height: 10px;
  border: 1.75px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: at-spin 0.7s linear infinite;
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
