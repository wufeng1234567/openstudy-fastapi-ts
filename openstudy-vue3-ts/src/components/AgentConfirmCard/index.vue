<!-- components/AgentConfirmCard/index.vue -->
<!--
  写操作「二次确认」卡片

  两条链路的共用 UI：
    · api 付费：后端 `run_agent_stream` 下发 `tool_confirm` 事件后**挂起**，等本卡片回调；
    · ds-free ：前端循环在 `executeTool` 之前本地等一个 Promise。

  为什么必须有：删除类操作**不可撤销**（题库/题目是一次性物理删除），
  让用户多点一次，远比误删一个题库 + 几十道题划算。

  ⚠️ 「确认」要有意义，前提是**用户看得见将影响什么**。所以：
    · 头部显示人话的「题库管理 · 批量删除」，原始标识符只进 `title`；
    · `preview` 渲染成键值行 + 逐条样例，**不是**把 JSON 拼成一行
      （旧实现会把 `batch_import` 的 `count` / `sample` 整段丢掉，见下方注释）。
-->
<template>
  <div class="agent-confirm" :class="[`is-${status}`, { 'is-destructive': destructive, 'is-draft': isDraft, 'has-sticky': shouldOfferCollapse && !isDraft }]">
    <!--
      建库导入草稿（需求二）：交给 AgentDraftCard —— 用户在导入前可改题库信息与每道题，
      确认时把改动随 `edited` 回传。非草稿卡片走下面原来的只读预览。
    -->
    <AgentDraftCard
      v-if="isDraft"
      :draft="preview && preview.draft"
      :status="status"
      @resolve="onDraftResolve"
    />
    <template v-else>
    <!--
      吸顶折叠条（2026-10-22）
      ==================================================================
      与 `AgentDraftCard` 同一套机制（见 `composables/useCollapseBar.ts`）。
      确认卡的 preview 可能是「逐条列出 50 条将删除的对象」，
      一样会把卡片撑到几屏高 —— 用户滚到中间就找不到按钮了。

      ⚠️ 这条必须放在卡片最外层、且是第一个子元素。
      ⚠️ 折叠时只藏内容、不藏这一条，否则收起后无法展开。
      ⚠️ **动作区（取消 / 确认）在折叠时仍然保留**：用户收起是为了不被挡住，
         不是为了放弃这次操作；把确认按钮一起藏起来是反人类的。
    -->
    <div v-if="shouldOfferCollapse" class="ac-sticky" :style="COLLAPSE_BAR_STYLE">
      <span class="ac-sticky-icon" :class="`is-${status}`">
        <OsIcon v-if="status === 'running'" :name="destructive ? 'alert' : 'circle-help'" :size="13" />
        <OsIcon v-else-if="status === 'ok'" name="check" :size="13" />
        <OsIcon v-else name="close" :size="13" />
      </span>
      <span class="ac-sticky-title">{{ title }}</span>
      <span v-if="previewSummary" class="ac-sticky-meta">{{ previewSummary }}</span>
      <button
        type="button"
        class="ac-sticky-toggle"
        :aria-expanded="!collapsed"
        :title="collapsed ? '展开这张卡片' : '收起这张卡片'"
        @click="toggleCollapse"
      >
        {{ collapsed ? '展开' : '收起' }}
        <span class="ac-sticky-caret" :class="{ 'is-collapsed': collapsed }">▾</span>
      </button>
    </div>

    <template v-if="!collapsed">
    <!--
      ⚠️ 有吸顶条时头部**只保留工具名**（2026-10-22 修重复标题）
      吸顶条已经写了「需要确认：写操作」+ 图标，`.ac-head` 再写一遍就是两行重复。
      但 `toolLabel`（题库管理 · 批量删除）不能丢 —— 它是最有信息量的那一句，
      而吸顶条里放不下（会挤掉收起按钮）。所以这里只渲染工具名这一行。
    -->
    <div v-if="shouldOfferCollapse" class="ac-head ac-head--compact">
      <span
        v-if="toolLabel"
        class="ac-name ac-name--solo"
        :title="toolPath"
      >{{ toolLabel }}</span>
    </div>
    <div v-else class="ac-head">
      <span class="ac-icon">
          <OsIcon v-if="status === 'running'" :name="destructive ? 'alert' : 'circle-help'" :size="14" />
          <OsIcon v-else-if="status === 'ok'" name="check" :size="14" />
          <OsIcon v-else name="close" :size="14" />
        </span>
      <span class="ac-title">{{ title }}</span>
      <!-- 原始标识符（bank_manage.delete）只进 title，别摆在用户脸上 -->
      <span v-if="toolLabel" class="ac-name" :title="toolPath">{{ toolLabel }}</span>
    </div>

    <div class="ac-desc">{{ content }}</div>
    <div v-if="destructive" class="ac-warn">此操作不可撤销，请确认后再执行</div>

    <!-- 将影响什么：键值行 + 列表逐条，不是把 JSON 拼成一行 -->
    <div v-if="previewRows.length || previewLists.length" class="ac-preview">
      <!--
        长值（`content` 记忆正文 / 任何超长字符串）**单独成块**：标签一行、值另起一块。
        短值仍是原来的「标签 + 同行值」，不因为这条规则把卡片撑松。
      -->
      <div
        v-for="row in previewRows"
        :key="row.key"
        class="ac-preview-row"
        :class="{ 'ac-preview-row--block': row.block }"
      >
        <span class="ac-preview-key">{{ row.label }}</span>
        <span class="ac-preview-val" :class="{ 'ac-preview-val--block': row.block }">{{ row.text }}</span>
      </div>
      <template v-for="list in previewLists" :key="list.key">
        <div class="ac-preview-key ac-preview-key--list">{{ list.heading }}</div>
        <div v-for="(item, i) in list.items" :key="i" class="ac-preview-item">· {{ item }}</div>
      </template>
    </div>

    <div v-if="status === 'running'" class="ac-actions">
      <button class="ac-btn ac-cancel" @click="$emit('resolve', false)">取消</button>
      <button class="ac-btn ac-ok" @click="$emit('resolve', true)">
        {{ destructive ? '确认删除' : '确认执行' }}
      </button>
    </div>
    <div v-else class="ac-result">{{ status === 'ok' ? '已确认' : '已取消' }}</div>
    </template>

    <!--
      收起后仍显示状态结果（已确认 / 已取消）
      不显示的话，收起一张已确认的卡会看起来"什么都没发生"。
      注意动作区已经在上面那段里，这段只负责终态。
    -->
    <div v-if="collapsed && status !== 'running'" class="ac-result">
      {{ status === 'ok' ? '已确认' : '已取消' }}
    </div>
    <!-- 收起但仍在待确认：动作按钮必须保留，否则用户没法确认 -->
    <div v-if="collapsed && status === 'running'" class="ac-actions">
      <button class="ac-btn ac-cancel" @click="$emit('resolve', false)">取消</button>
      <button class="ac-btn ac-ok" @click="$emit('resolve', true)">
        {{ destructive ? '确认删除' : '确认执行' }}
      </button>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import AgentDraftCard from '@/components/AgentDraftCard/index.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { useCollapseBar, COLLAPSE_BAR_STYLE } from '@/composables/useCollapseBar'

/*
 * 吸顶折叠条（2026-10-22）
 * ----------------------------------------------------------------------------
 * 阈值 8：确认卡的 preview 行数（键值行 + 列表条目）超过 8 条，
 * 卡片就够高了、值得给折叠条。实测「批量删除 50 条」这种卡远超阈值，
 * 而「删除 1 个题库」只有两三行，不需要。
 */
const { collapsed, setContentLines, shouldOfferCollapse, toggle } = useCollapseBar({
  threshold: 8
})

const toggleCollapse = toggle

const props = defineProps({
  tool: { type: String, default: '' },
  action: { type: String, default: '' },
  /** 卡片主文案（"即将执行 bank_manage.delete"） */
  content: { type: String, default: '' },
  /** running=待确认；ok=已确认；fail=已取消 */
  status: { type: String, default: 'running' },
  /** 破坏性操作（删除类）→ 文案与配色更醒目 */
  destructive: { type: Boolean, default: false },
  /** 确认前展示的信息（题库名 / 题量…） */
  preview: { type: Object as () => Record<string, any> | null, default: null }
})

const emit = defineEmits(['resolve'])

const title = computed(() => (props.destructive ? '需要确认：删除操作' : '需要确认：写操作'))

/**
 * 是不是「建库导入」的可编辑草稿 —— 是就换 `AgentDraftCard`，不是就还是只读预览。
 *
 * 判据落在 `preview.draft.kind` 上（后端 `_build_import_draft` 给的形状），
 * 不落在 `action === 'batch_import'` 上：老的 `batch_import` 预览（只有 count/sample）
 * 也该走只读那条路，只有带 `draft` 的才可编辑。
 */
const DRAFT_KINDS = ['question_bank_import', 'batch_delete']

/**
 * 是否交给 `AgentDraftCard` 渲染（而不是下面的只读预览）。
 *
 * 两种草稿：
 *   · `question_bank_import` —— 建库导入，可改题库信息与每道题；
 *   · `batch_delete`         —— 批量删除，可逐条勾选 / 全选 / 反悔（用户 2026-10-17 需求）。
 * 判据落在 `preview.draft.kind` 上：老的 `batch_import` 预览（只有 count/sample）
 * 没有 `draft`，仍走只读那条路。
 */
const isDraft = computed(() => DRAFT_KINDS.includes(String((props.preview as any)?.draft?.kind || '')))

/** 草稿卡片回传的载荷（`{approved, edited?}` / `{approved:false, regenerate, opinion}`）原样上抛 */
const onDraftResolve = (payload: any) => emit('resolve', payload)

/* ============================================================
 * 头部：工具 · 动作（人话）
 * ============================================================ */

/**
 * ⚠️ 与 `AgentToolResult` 的 `TOOL_LABELS` 必须**同一份清单**（13 个工具名，见那边的注释）：
 *    这张卡片也要写「需要确认：写操作 / 题库管理 · 批量删除」的头，漏一个就是英文标识符。
 */
const TOOL_LABELS: Record<string, string> = {
  bank_manage: '题库管理',
  question_manage: '题目管理',
  note_manage: '笔记管理',
  question_flag_manage: '题目标记',
  memory_manage: '记忆管理',
  learning_stats: '学习统计',
  knowledge_base_manage: '知识库管理',
  knowledge_ingest: '写入知识库',
  bank_share_manage: '题库分享',
  knowledge_search: '知识库检索',
  memory_search: '记忆检索',
  agent_manage: '智能体管理',
  delegate_task: '请专家帮忙'
}

/** 与 `AgentToolResult` 的 `ACTION_LABELS` 同一口径（覆盖每个工具 schema 的 action enum） */
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
  // delegate_task（指挥家派发专家）
  delegate: '派发'
}

/** 原始标识符（bank_manage.delete）—— 只进 title，方便排查问题时看 */
const toolPath = computed(() => [props.tool, props.action].filter(Boolean).join('.'))

const toolLabel = computed(() => {
  if (!props.tool) return ''
  const tool = TOOL_LABELS[props.tool] || props.tool
  return props.action ? `${tool} · ${ACTION_LABELS[props.action] || props.action}` : tool
})

/* ============================================================
 * 预览：把 preview 里的字段摊成「人能读」的键值行 / 列表
 * ============================================================
 *
 * ⚠️ 旧实现有两个坑，都是「给用户看 JSON」的变体：
 *   1. `if (p.action) parts.push(...)` 会**提前把兜底分支堵死** ——
 *      `batch_import` 的 preview 是 `{action, count, sample}`，
 *      `parts` 一旦有「动作：batch_import」就 return 了，
 *      `count` 和 `sample` 全被丢掉 → 确认导入 5 道题时一道都看不见。
 *   2. 兜底分支是 `${k}: ${value}` 拼逗号串 → 英文键名 + `sample` 数组
 *      被逗号黏成一行。
 */

/**
 * 字段名 → 中文标签；认不出来的**保留原键名**（和 `AgentToolDetail` 一个口径）
 *
 * 值怎么显示见下面「值的展示」那一节（有人话就隐机器码 / 布尔→是/否 / 核实过的枚举→人话）。
 */
const PREVIEW_LABELS: Record<string, string> = {
  bankName: '题库',
  bank_name: '题库',
  subject: '科目',
  totalQuestions: '现有题目',
  total_questions: '现有题目',
  count: '影响数量',
  total: '总数',
  imported: '已导入',
  deleted: '已删除',
  questionText: '题目',
  question_text: '题目',
  keyword: '关键词',
  bankNames: '题库名称',
  bank_names: '题库名称',
  questionIds: '题目 ID',
  question_ids: '题目 ID',
  questionIndexes: '题号',
  question_indexes: '题号',
  bankIds: '题库 ID',
  bank_ids: '题库 ID',
  missingIds: '未找到的 ID',
  missingNames: '未找到的名称',
  // 笔记（note_manage 的 preview 产物）
  title: '标题',
  noteId: '笔记 ID',
  note_id: '笔记 ID',
  categoryName: '分类',
  category_name: '分类',
  contentLength: '正文字数',
  content_length: '正文字数',
  tags: '标签',
  // `save_draft` 预览：是否会覆盖已有草稿 + 那份草稿的标题
  overwrite: '是否覆盖',
  existingTitle: '已有草稿',
  // 笔记可见性走人话字段，不用 `isPublic` —— 库里的 is_public 语义按表相反（题库 0=公开，
  // 笔记 1=公开），共用一张枚举必然显示反，详见 AgentToolDetail 的 FIELD_LABELS 注释
  visibility: '可见性',
  willChange: '将修改',
  will_change: '将修改',
  sample: '样例',
  // ---- 题目标记 question_flag_manage（`_preview_record` / `_preview_question`）
  // ⚠️ `flagType` 是英文标识符（error / favorite / marked），`flagTypeText` 才是人话
  //    （后端 `_type_fields` 两个都给）—— 两个都留标签，好让「模型把 flag_type 传错」
  //    这件事在确认卡片上**看得见**（见 `question_mark_manage.py` 模块 docstring）。
  flagType: '标记类型',
  flagTypeText: '标记类型',
  recordId: '记录 ID',
  questionId: '题目 ID',
  // 反查出来的题干（`_preview_record` / `_preview_question`，`_load_doc` 的「没找到」也用它）
  preview: '题干预览',
  // ---- 记忆管理 memory_manage
  memoryId: '记忆 ID',
  memoryType: '记忆类型',
  memoryTypeText: '记忆类型',
  // 记忆正文：只有 memory_manage.forget 的 preview 会带 `content`
  content: '记忆内容',
  // ---- 知识库管理 knowledge_base_manage
  kbId: '知识库 ID',
  name: '名称',
  description: '简介',
  disabledText: '启用状态',
  documents: '文档数',
  chunks: '分块数',
  docId: '文档 ID',
  fileName: '文件名',
  // ---- 写入知识库 knowledge_ingest（preview：反查的库名 + 切块/向量化估算）
  kbName: '知识库名称',
  embedCalls: '向量化次数',
  charCount: '字符数',
  source: '来源',
  // ---- 题库分享 bank_share_manage
  shareId: '分享 ID',
  expireText: '有效期',
  expireTime: '过期时间',
  receiveCount: '领取人数',
  invalidatedReceivers: '受影响人数',
  ownerName: '分享者',
  permission: '权限',
  received: '是否已领取',
  newBankName: '新题库名',
  allowFork: '允许复制',
  shareMessage: '留言',
  // ---- 智能体管理 agent_manage（create 预览摊开人设/工具/模型，delete/update 给 id）
  agentId: '智能体 ID',
  personaPrompt: '人设提示词',
  tools: '可用工具',
  model: '模型'
}

/**
 * 单独处理的键：`action` 已在卡片头部写成人话（题库管理 · 批量删除），
 * `success` / `error` / `hint` 属于结果与错误区，都不该在这里重复一遍。
 * `draft` 是建库导入的可编辑草稿（交给 `AgentDraftCard`），在这里当对象行渲染成
 * `draft: [object Object]` 只会是噪音 —— 也一并跳过。
 */
const PREVIEW_SKIP = new Set(['action', 'success', 'error', 'hint', 'draft'])

/* ============================================================
 * 值的展示：把「机器码」换成人话（**只有这三条规则，不做通用框架**）
 * ============================================================
 * 键名有 `PREVIEW_LABELS` 兜着，但**值**此前是 `String(v)` 原样打出来的：
 * 用户在这一屏要按「确认删除」，看到的却是 `允许复制: 1`、`屏蔽: 0`、
 * `是否已领取: false`、`权限: read` —— 和「不给用户看 JSON」是同一个问题。
 *
 * 三条规则（与 `AgentToolDetail` 的 `REDUNDANT_KEYS` / `YES_NO_KEYS` / `ENUM_LABELS`
 * 同一套语义，但**只实现这个组件真的会用到的部分**，不搬整套框架过来）：
 */

/**
 * ① 有人话就隐掉机器码：`X` 与 `XText` 同时在 preview 里时只显示后者。
 *
 * 后端本来就是**成对**给这两个字段的（`flagType`/`flagTypeText`、
 * `memoryType`/`memoryTypeText`、`disabled`/`disabledText`），所以这条能盖住大半。
 * ⚠️ 只在**人话确实有值**时才隐：光有一条 `flagTypeText: ''` 就把 `flagType` 也藏了，
 *    等于什么都不显示。
 */
function hasTextTwin(p: Record<string, any>, key: string): boolean {
  const twin = p[key + 'Text']
  return twin !== null && twin !== undefined && twin !== ''
}

/**
 * ② 值是「是/否」的键：后端给 bool 或 int 0/1 都可能，`String(v)` 会打出 `false`/`0`。
 *
 * 与 `AgentToolDetail.YES_NO_KEYS` 同口径。**核实过的取值**：
 * `received`=`bool(...)`（`bank_share_service.py:400`）、
 * `allowFork`=`int(... or 0)`（`bank_share_manage.py:274 / 467`）、
 * `revoked`=字面量 1（`bank_share_manage.py:380`）、
 * `created`=Python bool（`question_mark_manage.py:475`）、
 * `isStarred`/`effective`=int 0/1 / bool（`question_record_service.py:340`、`bank_share_service.py:107`）。
 * 其中只有 `received` / `allowFork` 目前会出现在 preview 里，其余是同一套语义的同类列。
 * `overwrite` 是 `note_manage._preview_save_draft` 回的 Python bool（line 330）——
 * 不放进来的话确认卡片会打出裸 `true` / `false`。
 */
const YES_NO_KEYS = new Set(['received', 'allowFork', 'revoked', 'created', 'isStarred', 'effective', 'overwrite'])

/**
 * ③ 枚举值 → 人话。**只放取值域能从后端源码核实的键**。
 *
 * · `disabled`：0=启用 / 1=已屏蔽（`knowledge_base_manage._disabled_text` 逐字同口径）
 * · `permission`：全仓**只写过 `"read"` 一个值**（`bank_share_service.py:293`、
 *   `bankShare.py:177` 都写死 `permission="read"`，模型默认值也是 `"read"`）→ 只读
 *
 * ⚠️ 核实不到取值域的键**一律不在这里**（宁可显示原值，也不编一份可能显示反的映射）：
 *    · `resultStatus`（`created`/`restored`/`exists`）与 `markedType`（1..5）虽然取值域清楚，
 *      但**任何 `preview()` 都不会回它们**（前者只出现在 `receive` 的执行结果、后者只出现在
 *      错题记录的 brief），所以放到这里也是死代码 —— `markedType` 已在
 *      `AgentToolDetail.ENUM_LABELS` 里翻（它真的会到那里）。
 */
const VALUE_ENUMS: Record<string, Record<string, string>> = {
  disabled: { '0': '启用', '1': '已屏蔽' },
  permission: { read: '只读' }
}

/** 键 + 值 → 给人看的文本（三条规则都不命中就原样） */
function displayText(key: string, value: any): string {
  const hit = VALUE_ENUMS[key]?.[String(value)]
  if (hit) return hit
  if (YES_NO_KEYS.has(key)) {
    return value === true || value === 1 || value === '1' || value === 'true' ? '是' : '否'
  }
  return String(value)
}

/* ============================================================
 * 长值单独成块：标签一行、值另起一块（**只加这一条，不改其它渲染路径**）
 * ============================================================
 *
 * 为什么：`memory_manage.forget` 的预演会回 `content`（记忆正文，可达数百字），
 * 而上面的 `previewRows` 把它当普通短值和 60px 宽的标签挤在同一行（`.ac-preview-val`
 * 只是 `overflow-wrap: anywhere`）—— 正文被挤成一条极窄的竖排，读不成句。
 *
 * 判据（**双条件，命中任一即可**，两者都是「这行不该按短值排版」的信号）：
 *   ① 键名是 `content` —— 全仓只有 `memory_manage.forget` / `_preview_memory` 会回它，
 *      语义就是「一整篇正文」，哪怕模型只存了很短一句，它也不是一个「字段值」；
 *   ② 值本身超长（> `LONG_TEXT_MIN`）—— 覆盖 `shareMessage`（留言）/ `description`（简介）/
 *      `preview`（题干预览）这类**长度不定**的字段：短的时候和别的键值一样同行显示就好，
 *      长的时候必须让出来。**不要**无条件拆块：那会把整张卡片撑成一屏，短值也各占两行。
 */
const LONG_TEXT_MIN = 60

/** 该键值是否该单独成块：键名是记忆正文，或值文本本身超长 */
function isBlockValue(key: string, text: string): boolean {
  return key === 'content' || text.length > LONG_TEXT_MIN
}

/** `sample` 只放前几条，真值条数在后端的 `count` 里 */
const hasSample = computed(() => {
  const s = (props.preview as any)?.sample
  return Array.isArray(s) && s.length > 0
})

const previewRows = computed(() => {
  const p = props.preview
  if (!p || typeof p !== 'object') return []
  return Object.entries(p)
    .filter(([k, v]) => {
      if (PREVIEW_SKIP.has(k)) return false
      if (Array.isArray(v)) return false // 数组走 previewLists
      // 有样例列表时不再单列「影响数量」—— 样例标题里已经写了「共 N 条」
      if (k === 'count' && hasSample.value) return false
      if (hasTextTwin(p, k)) return false // ① 有人话就别再摆一行机器码
      return v !== null && v !== undefined && v !== ''
    })
    .map(([k, v]) => {
      const text = displayText(k, v)
      // `block` 只决定这一行的排版（长值 → 标签一行、值一块），**不参与过滤**：
      // 上面的 filter 一个字节没动，所以「哪些键会出现」的行为完全不变。
      return { key: k, label: PREVIEW_LABELS[k] || k, text, block: isBlockValue(k, text) }
    })
})

/**
 * 数组类字段：**逐条成行**，不是 `String(v)` 逗号黏成一行
 *（`delete_many` 的 `bank_names`、`batch_import` 的 `sample` 都会走到这里）
 */
const previewLists = computed(() => {
  const p = props.preview as any
  if (!p || typeof p !== 'object') return []
  return Object.entries(p)
    .filter(([k, v]) => !PREVIEW_SKIP.has(k) && Array.isArray(v) && (v as any[]).length > 0)
    .map(([k, v]) => {
      const items = (v as any[]).map((x) => String(x)).filter(Boolean)
      // `sample` 是「前 N 条样例」，总条数看后端的 count；别的数组本身就是全集
      const total = k === 'sample' && typeof p.count === 'number' ? p.count : items.length
      const label = PREVIEW_LABELS[k] || k
      return {
        key: k,
        heading:
          total > items.length
            ? `${label}（共 ${total} 条，显示前 ${items.length} 条）`
            : `${label}（${items.length} 条）`,
        items
      }
    })
})

/* ============================================================
 * 吸顶折叠条：内容量级 + 收起后的一行摘要
 * ============================================================ */

/**
 * 把"这张卡有多长"告诉折叠条
 *
 * ⚠️ 用**行数/条数**而不是 DOM 高度：折叠会改变高度，
 *    用高度判断"要不要折叠条"会自相矛盾（收起 → 变矮 → 判定不需要 →
 *    折叠条消失 → 用户再也展不开）。详见 `useCollapseBar` 顶部注释。
 *
 * `immediate` 必须开：卡片一出现就要决定是否显示折叠条。
 */
watch(
  () => [previewRows.value.length, previewLists.value.length, previewLists.value.reduce((s, l) => s + l.items.length, 0)] as const,
  ([rows, lists, items]) => {
    setContentLines(rows + lists + items)
  },
  { immediate: true }
)

/**
 * 收起后显示的一行摘要
 *
 * 收起时卡片只剩吸顶条，用户需要一眼知道"这是什么、影响多大"。
 * 优先用样例总数（最能表达规模），没有就退回行数。
 */
const previewSummary = computed(() => {
  const p = props.preview as any
  if (p && typeof p.count === 'number' && p.count > 0) return `${p.count} 项`
  const total = previewLists.value.reduce((s, l) => s + l.items.length, 0)
  if (total > 0) return `${total} 项`
  return ''
})
</script>

<style scoped>
.agent-confirm {
  border: 1px solid #fde68a;
  border-left: 3px solid #f59e0b;
  border-radius: 10px;
  padding: 10px 14px;
  background: #fffbeb;
  max-width: 100%;
  box-sizing: border-box;
}

.agent-confirm.is-destructive {
  border-color: #fecaca;
  border-left-color: #ef4444;
  background: #fef2f2;
}

.agent-confirm.is-ok {
  border-color: #bbf7d0;
  border-left-color: #22c55e;
  background: #f0fdf4;
}

.agent-confirm.is-fail {
  border-color: #e5e7eb;
  border-left-color: #9ca3af;
  background: #f9fafb;
}

/* 草稿卡片自带唯一一层外框，外层在这里收干净 —— 否则就是「琥珀套琥珀」的双层边框 */
.agent-confirm.is-draft {
  border: none;
  background: transparent;
  padding: 0;
  border-radius: 0;
}

/* ============================================================
 * 吸顶折叠条（2026-10-22）
 * ============================================================ */

/*
 * 背景色必须**跟随卡片状态色**（琥珀 / 绿 / 灰）
 * ----------------------------------------------------------------------------
 * 卡片本身有底色（`#fffbeb` / `#f0fdf4` / `#f9fafb`）。折叠条若固定用白色，
 * 吸附时会在卡片里"贴一块白",看起来像另一张卡片浮在上面。
 * 这里用与卡片同色的底 + 发丝分隔线，视觉上仍是这张卡的一部分。
 *
 * 负边距抵消卡片 padding（`10px 14px`），让这条通栏到卡片边缘，
 * 避免滚动时两侧透出下面的内容（详见 AgentDraftCard 里同类注释）。
 */
.ac-sticky {
  display: flex;
  align-items: center;
  gap: 8px;
  /*
   * 顶部**不用负边距**（2026-10-22 修间隙）
   * ------------------------------------------------------------------
   * 上一版是 `margin: -10px -14px 10px` 去抵消卡片 padding，
   * 结果上沿在圆角处露出一条 1~2px 的缝（与 AgentDraftCard 同一问题）。
   * 现在卡片在有吸顶条时顶部 padding 归零（`.agent-confirm.has-sticky`），
   * 这条天然贴到边框内侧。
   */
  margin: 0 -14px 0;
  padding: 9px 14px;
  background: var(--ac-sticky-bg, #fffbeb);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 9px 9px 0 0;
  font-size: 12.5px;
  line-height: 1.4;
}

/* 有吸顶条时：卡片顶部不留 padding，避免圆角处露缝 */
.agent-confirm.has-sticky {
  padding-top: 0;
}

/*
 * 吸顶条与下方内容的间隔
 * ----------------------------------------------------------------------------
 * 卡片不是 flex 布局（普通 block），所以不能靠 `gap` 控制。
 * 这里给吸顶条自己一个 `margin-bottom`，让它与第一个内容块之间保持
 * 与卡片原来 `padding` 视觉相当的间距 —— 不能贴太紧，否则像被裁掉了。
 */
.agent-confirm.has-sticky > .ac-sticky {
  margin-bottom: 10px;
}

.ac-sticky-icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: #f59e0b;
}

.ac-sticky-icon.is-ok {
  color: #22c55e;
}

.ac-sticky-icon.is-fail {
  color: #9ca3af;
}

/* 三种状态各自的吸顶条底色，与卡片底色一致 */
.agent-confirm.is-destructive .ac-sticky {
  --ac-sticky-bg: #fffbeb;
}

.agent-confirm.is-ok .ac-sticky {
  --ac-sticky-bg: #f0fdf4;
}

.agent-confirm.is-fail .ac-sticky {
  --ac-sticky-bg: #f9fafb;
}

/* 草稿模式外层无 padding，吸顶条也被 AgentDraftCard 自己接管，不需要偏移 */
.agent-confirm.is-draft .ac-sticky {
  margin: 0;
}

.ac-sticky-title {
  font-weight: 600;
  color: var(--os-text, #1f2937);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ac-sticky-meta {
  flex: none;
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
}

/* 折叠按钮：贴右，文字 + 小箭头（与 AgentDraftCard 保持同一形态） */
.ac-sticky-toggle {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  line-height: 1.3;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.ac-sticky-toggle:hover {
  color: var(--os-text, #1f2937);
  border-color: rgba(0, 0, 0, 0.24);
  background: #fff;
}

.ac-sticky-toggle:focus-visible {
  outline: 2px solid var(--os-primary, #0f1115);
  outline-offset: 2px;
}

.ac-sticky-caret {
  display: inline-block;
  font-size: 10px;
  line-height: 1;
  transition: transform 0.18s ease;
}

.ac-sticky-caret.is-collapsed {
  transform: rotate(180deg);
}

.ac-head {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 13.5px;
  line-height: 1.55;
}

/*
 * 状态图标：**纯线条 + 语义色**，不要实心圆底
 * --------------------------------------------------------------------
 * 原来这里是 18px 的实心彩色圆（背景 #f59e0b / #22c55e），图标白色压在上面，
 * 看起来像"绿色实心圆圈勾"；而同一屏里的「深度思考」用的是细线星光 svg、
 * 「工具结果」用的是 OsIcon 纯线条 —— 三种形态混在一起非常突兀
 * （用户 2026-10-18 专门标箭头指出）。
 *
 * 现在统一成和 AgentToolResult / AgentReasoning 一致的做法：
 * 透明底 + 1.75 描边的线性图标 + 语义色。颜色只用来区分状态，不再用色块。
 */
.ac-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--os-text-3, #6b7280);
}

.is-destructive .ac-icon {
  color: #ef4444;
}

.is-ok .ac-icon {
  color: #22c55e;
}

.is-fail .ac-icon {
  color: var(--os-text-4, #9ca3af);
}

.ac-title {
  font-weight: 600;
  color: #92400e;
}

.is-destructive .ac-title {
  color: #b91c1c;
}

.is-ok .ac-title,
.is-fail .ac-title {
  color: #4b5563;
}

.ac-name {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 11px;
  color: #9aa5b5;
  font-family: Consolas, Monaco, monospace;
  background: #fff;
  border: 1px solid #e5e7eb;
  padding: 1px 7px;
  border-radius: 9px;
}

/*
 * 有吸顶条时的头部：只有「工具 · 动作」这一行
 *
 * `.ac-name` 本身是给**机器码**用的等宽小胶囊（`bank_manage.delete`），
 * 而这里的 `toolLabel` 是「题库管理 · 批量删除」这种人话 ——
 * 用等宽字体 + 灰胶囊会显得是内部标识符。所以 solo 变体改成正常字体、
 * 常规字色，只做一个轻量的"上下文行"。
 */
.ac-head--compact {
  margin-top: 0;
  min-height: 18px;
}

.ac-name--solo {
  margin-left: 0;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  color: var(--os-text-3, #6b7280);
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
}

.ac-desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #1f2d3d;
  word-break: break-word;
}

.ac-warn {
  margin-top: 5px;
  font-size: 12px;
  color: #b91c1c;
}

/* 预览块：告诉用户「这一下会动到什么」—— 用键值行和列表，不是一坨 JSON */
.ac-preview {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.66);
  font-size: 12px;
  line-height: 1.7;
  color: #4b5563;
}

.ac-preview-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

/* 标签定宽、值自适应换行 —— 窄卡片下也不会互相挤 */
.ac-preview-key {
  flex: none;
  width: 60px;
  color: #9aa5b5;
}

.ac-preview-val {
  flex: 1;
  min-width: 0;
  color: #374151;
  overflow-wrap: anywhere;
}

/* 长值行：`column` 让「标签」与「值」自然上下排（标签不再占那 60px 定宽） */
.ac-preview-row--block {
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
}

.ac-preview-row--block .ac-preview-key {
  width: auto;
}

/*
 * 长值块：**保留换行**（记忆正文本来就是多行的）、可选中、不截断。
 *
 * ⚠️ 不要往这里加 `text-overflow` / `overflow: hidden` / `-webkit-line-clamp` ——
 *    「长正文被挤掉、读不成句」正是这条规则要解决的问题，加回去等于把问题还给了用户。
 *    `pre-wrap` 保留原文换行与连续空格，同时仍然自动折行（长英文串也不会撑破卡片）。
 */
.ac-preview-val--block {
  width: 100%;
  white-space: pre-wrap;
  user-select: text;
  -webkit-user-select: text;
}

/* 列表标题（「样例（共 10 条，显示前 5 条）」）单独占一行，不参与键值对齐 */
.ac-preview-key--list {
  width: auto;
  margin-top: 6px;
}

.ac-preview-item {
  padding-left: 10px;
  color: #374151;
  overflow-wrap: anywhere;
}

.ac-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 10px;
}

.ac-btn {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 5px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ac-cancel {
  background: #fff;
  border-color: #d1d5db;
  color: #4b5563;
}

.ac-cancel:hover {
  border-color: #9ca3af;
  color: #1f2937;
}

.ac-ok {
  background: #2563eb;
  color: #fff;
}

.ac-ok:hover {
  background: #1d4ed8;
}

.is-destructive .ac-ok {
  background: #dc2626;
}

.is-destructive .ac-ok:hover {
  background: #b91c1c;
}

.ac-result {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
  text-align: right;
}
</style>
