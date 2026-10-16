<!-- components/AgentToolDetail/index.vue -->
<!--
  把工具调用的「入参 / 返回」渲染成**人能看的形式**

  为什么不直接丢 JSON：这个助手是给**学习者**用的，不是给开发者看的调试台。
  `{"bankId":3,"totalQuestions":30,"isPublic":true}` 这种既占地方又读不懂 ——
  转成「题库 ID 3 / 题目总数 30」才叫把信息交给了用户。

  渲染规则：
    · 对象          → 键值行（键名走中英映射 `FIELD_LABELS`，认不出来的保留原名）
    · 对象数组      → 一条一张小卡（标题取最有辨识度的字段：题干 / 题库名 / 关键词），
                      每页 8 条、底部「上一页 / 第 x–y 条 / 下一页」，超过一页才出现；
                      后端只回了一页时（`data.total` > 数组长度）额外说明「还剩多少没取回」
    · 简单值数组    → 一排小胶囊
    · 布尔          → 是 / 否（0/1 形式的也由 `YES_NO_KEYS` 翻）
    · 枚举数字      → 人话（`difficulty:2` → 「难度 中等」、`questionType:1` → 「题型 单选题」）
    · 长文本        → 截断并注明总字数
    · 字符串化的 JSON（如选项 `'["A. x","B. y"]'`）→ 先解析回结构再渲染

  不显示的键：
    · 对用户无意义的：`success`（恒为 true）、`action` / `message`（已显示在卡片前两层）、
      `error` / `hint`（显示在错误区）、`_` 开头的内部字段
    · 说两遍的（`REDUNDANT_KEYS`）：`questionTypeText` 在就不显示数字 `questionType`；
      `hasSubQuestions=false` 就不显示必然为 0 的 `subCount`
    · 已经在**小卡标题**上显示过的（`TITLE_GROUPS`）：对象数组的每条只摘掉
      「被选中的那个标题字段 + 它那一组里的同义键」（例如题干当选标题时，不再单列
      只是它截前 80 字的 `preview`）—— **组外字段一律照常显示**，题库名不会被题干挤掉

  ⚠️ 新增字段名时**必须同步补 `FIELD_LABELS`**，否则用户会看到 `sortOrder` 这种原始标识符。

  递归：对象数组里的每条、嵌套对象的每层都会再走一遍本组件。
-->
<template>
  <!--
    落库快照被瘦身过（`useAgentChat.slimTimeline` 在 data 超过 20KB 时整段替换成
    `{message, _truncated, _bytes}`）。必须**专门特判**：这三个键恰好全在隐藏名单里
    （`message` 进了 `HIDDEN_KEYS`、`_` 前缀全隐藏），不特判的话「执行结果」是一片空白，
    用户只会以为功能坏了。
  -->
  <div v-if="truncated" class="td-truncated">
    <span class="td-truncated-icon" aria-hidden="true">!</span>
    <span>结果数据过大{{ bytesText }}，未随会话保存 —— 刷新后这里会变空，需要时再执行一次即可。</span>
  </div>

  <!-- 对象数组：一条一张小卡，多了就翻页 -->
  <div v-else-if="isItemList" class="td-items">
    <div v-for="(item, i) in pagedItems" :key="pageStart + i" class="td-item">
      <div v-if="titleOf(item)" class="td-item-title">{{ titleOf(item) }}</div>
      <AgentToolDetail :data="restOf(item)" :depth="depth + 1" />
    </div>

    <div v-if="showPager" class="td-pager">
      <button type="button" class="td-page-btn" :disabled="safePage <= 1" @click="turn(-1)">
        上一页
      </button>
      <span class="td-page-info">
        第 {{ pageStart + 1 }}–{{ pageStart + pagedItems.length }} 条 · 共 {{ total }} 条
      </span>
      <button type="button" class="td-page-btn" :disabled="safePage >= pageCount" @click="turn(1)">
        下一页
      </button>
    </div>

    <!--
      翻页条只能翻「已经拿到的」这些条。后端可能只回了一页（`question_manage.list`
      默认 limit=20，题库有 30 道），不说明的话用户会以为题库里就只有 20 道题。
    -->
    <div v-if="missingFromServer > 0" class="td-server-more">
      本次只取回 {{ total }} 条（共 {{ serverTotal }} 条），可以让助手继续列出后面的
    </div>
  </div>

  <!-- 简单值数组：一排胶囊 -->
  <div v-else-if="Array.isArray(data)" class="td-chips">
    <span v-for="(item, i) in data" :key="i" class="td-chip">{{ scalarText(item) }}</span>
  </div>

  <!-- 对象：键值行 -->
  <div v-else-if="isPlainObject(data)" class="td-fields">
    <div v-for="row in rows" :key="row.key" class="td-row">
      <span class="td-key">{{ row.label }}</span>
      <div class="td-val">
        <span v-if="row.kind === 'scalar'" class="td-text">{{ row.text }}</span>
        <span v-else-if="row.kind === 'chips'" class="td-chips">
          <span v-for="(c, i) in row.chips" :key="i" class="td-chip">{{ c }}</span>
        </span>
        <AgentToolDetail v-else :data="row.value" :depth="depth + 1" :server-total="rowServerTotal(row.key)" />
      </div>
    </div>
  </div>

  <span v-else class="td-text">{{ scalarText(data) }}</span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

// 递归要用自己的名字引用自己
defineOptions({ name: 'AgentToolDetail' })

const props = withDefaults(
  defineProps<{
    data: any
    depth?: number
    /**
     * 这个数组在**服务端的真实总量**（由父级从 `data.total` 传下来）。
     * 后端常常只回一页，比数组长度大时说清楚「还剩多少没取回」。
     */
    serverTotal?: number
  }>(),
  { depth: 0, serverTotal: undefined }
)

/** 递归上限 —— 再深也没人会看，直接省略 */
const MAX_DEPTH = 4
/** 对象数组一页显示几条（其余靠底部分页条翻，别把卡片撑成一面墙） */
const PAGE_SIZE = 8
/** 单个长文本的展示上限 */
const MAX_TEXT = 300
/** 当标题用的字段最多显示多少字 */
const MAX_TITLE = 120

/**
 * 字段名 → 中文标签。认不出来的键**保留原名**（总比藏起来强）。
 *
 * 键名两种写法都要覆盖：**返回体**是 camelCase（后端 `question_brief` /
 * `bank_brief` 为了省前端转换直接用驼峰），**入参**是 snake_case（工具 schema 定的）。
 */
const FIELD_LABELS: Record<string, string> = {
  // 通用
  action: '操作',
  keyword: '关键词',
  subject: '科目',
  description: '简介',
  count: '数量',
  total: '总数',
  items: '结果',
  list: '结果',
  limit: '数量上限',
  offset: '起始位置',
  hasMore: '还有更多',
  has_more: '还有更多',
  bankTotal: '题库题目总数',
  bank_total: '题库题目总数',
  // 笔记
  noteId: '笔记 ID',
  note_id: '笔记 ID',
  noteIds: '笔记 ID',
  note_ids: '笔记 ID',
  notes: '笔记',
  note: '笔记',
  categories: '分类',
  categoryId: '分类 ID',
  category_id: '分类 ID',
  categoryName: '分类',
  category_name: '分类',
  contentLength: '正文字数',
  content_length: '正文字数',
  contentPreview: '正文预览',
  markdownContent: 'Markdown 正文',
  markdown_content: 'Markdown 正文',
  tags: '标签',
  willChange: '将修改',
  will_change: '将修改',
  viewCount: '阅读量',
  likeCount: '点赞数',
  commentCount: '评论数',
  linkedBanks: '关联题库',
  updateTime: '更新时间',
  update_time: '更新时间',
  // ⚠️ 笔记的可见性**故意走 `visibility`（人话）而不是 `isPublic`**：
  //    `is_public` 的语义**按表相反** —— 题库 0=公开/1=私密（`app/api/v1/questions.py:417`），
  //    笔记 1=公开/0=私密（`app/api/v1/notes.py:291`）。
  //    而下面 `ENUM_LABELS.isPublic` 是**单张全局映射**，只按题库语义写过一份。
  //    笔记若回 `isPublic`，可见性会整好显示反。所以后端 `note_brief` 直接给人话字段，
  //    这里只需一个普通标签 —— **别为了「和题库统一」把 visibility 改回 isPublic**。
  visibility: '可见性',
  // 状态：后端同时给 `status`(draft) 和 `statusText`(草稿)，前者由 REDUNDANT_KEYS 隐藏。
  // 没做成 ENUM_LABELS 是因为 `status` 这个键名太通用 —— 题库的 status 是 '0'/'1' 另一套语义，
  // 共用一张枚举表必然互相打架（和 `isPublic` 那个坑同一类问题）。
  statusText: '状态',
  status_text: '状态',
  // 题库
  bankId: '题库 ID',
  bank_id: '题库 ID',
  bankName: '题库名称',
  bank_name: '题库名称',
  bank_ids: '题库 ID',
  bank_names: '题库名称',
  banks: '题库',
  totalQuestions: '题目总数',
  questionCount: '题目数量',
  questionTypes: '题型分布',
  // ⚠️ 不叫「是否公开」：库里 `is_public` 是**反向**的（0=公开 / 1=私密），
  //    见 `app/api/v1/questions.py`「公开题库广场：只认 is_public == 0」。
  //    字面直译会给出与事实相反的结论，所以按「可见性」+ 枚举来展示。
  isPublic: '可见性',
  is_public: '可见性',
  createTime: '创建时间',
  create_time: '创建时间',
  // 题目
  questionId: '题目 ID',
  question_id: '题目 ID',
  questionIds: '题目 ID',
  questionIndex: '题号',
  question_index: '题号',
  questionText: '题干',
  question_text: '题干',
  questionType: '题型',
  question_type: '题型',
  questionTypeText: '题型',
  question_type_text: '题型',
  preview: '题干预览',
  options: '选项',
  answer: '答案',
  analysis: '解析',
  content: '材料正文',
  difficulty: '难度',
  sortOrder: '排序',
  sort_order: '排序',
  hasSubQuestions: '含子题',
  has_sub_questions: '含子题',
  subCount: '子题数量',
  sub_count: '子题数量',
  questions: '题目',
  subQuestions: '子题',
  sub_questions: '子题',
  bank: '题库',
  question: '题目',
  // 批量操作
  imported: '已导入',
  deleted: '已删除',
  missingIds: '未找到的 ID',
  missing_names: '未找到的名称',
  missingNames: '未找到的名称',
  // 通用：这几个键原先认不出来（英文标识符直接打在用户脸上）
  name: '名称',
  title: '标题',
  type: '类型',

  // ============================================================
  // 题目标记 question_flag_manage
  //   （`question_mark_manage.py` 的回执 + `question_record_service.brief_of`）
  // ============================================================
  // `flagType`(error/favorite/marked) 是机器标识符，`flagTypeText`(错题本/收藏/斩题) 是人话；
  // 后者在时前者由 REDUNDANT_KEYS 隐掉。
  flagType: '标记类型',
  flagTypeText: '标记类型',
  recordId: '记录 ID',
  errorId: '错题 ID',
  favoriteId: '收藏 ID',
  markedId: '斩题 ID',
  errors: '错题',
  // ⚠️ 上一条只是**错题本**语境（`question_flag_manage`）；`question_manage.batch_import`
  //    的 `errors` 是导入失败的字符串明细，靠 `labelOf` 按值形状改成「导入错误」。
  favorites: '收藏',
  markedQuestions: '斩题',
  created: '本次新建',
  isMastered: '已掌握',
  errorCount: '错误次数',
  status: '状态',
  lastErrorTime: '最近出错',
  favoriteStatus: '收藏状态',
  correctTimes: '答对次数',
  errorTimes: '答错次数',
  reviewCount: '复习次数',
  isStarred: '星标',
  markedStatus: '斩题状态',
  markedType: '斩题类型',
  markedTypeText: '斩题类型',
  difficultyLevel: '难度等级',

  // ============================================================
  // 记忆管理 memory_manage
  // ============================================================
  memoryId: '记忆 ID',
  memoryType: '记忆类型',
  memoryTypeText: '记忆类型',
  memoryTypes: '各类记忆',

  // ============================================================
  // 学习统计 learning_stats
  //   （`user_stats_service` → `api/v1/user_stats.py`，与「我的学习统计」页面同一批字段）
  // ============================================================
  totalBanks: '收藏题库',
  totalErrors: '错题数',
  totalMarked: '斩题数',
  totalMastered: '已掌握',
  totalFavoriteNotes: '收藏笔记',
  totalPracticeCount: '作答次数',
  correctRate: '正确率',
  bankStudyCount: '学习题库数',
  byQuestionType: '题型分布',
  bankCount: '题库数',
  markedCount: '斩题数',
  date: '日期',
  practiceCount: '作答次数',
  correctCount: '答对次数',
  byDifficulty: '难度分布',
  activeErrors: '待消灭错题',
  mastered: '已掌握',
  masterRate: '掌握率',
  bySubject: '按科目',
  topErrors: '错得最多',
  joinDate: '加入日期',
  studyDays: '学习天数',
  consecutiveDays: '连续天数',
  totalNotes: '笔记数',
  milestones: '里程碑',
  trend: '趋势',
  days: '天数',

  // ============================================================
  // 知识库管理 knowledge_base_manage
  //   （`rag_write_service._kb_brief` / `_doc_brief` + 工具的 preview）
  // ============================================================
  kbId: '知识库 ID',
  docCount: '文档数',
  chunkCount: '分块数',
  disabled: '屏蔽',
  disabledText: '启用状态',
  documents: '文档',
  docId: '文档 ID',
  fileName: '文件名',
  fileType: '文件类型',
  fileSize: '文件大小',
  chunks: '分块',
  knowledgeBases: '知识库',
  // `_kb_brief` 还带这三个（认不出来的话就是英文标识符 + 一堆数字）
  embeddingModel: '向量模型',
  chunkSize: '分块大小',
  chunkOverlap: '分块重叠',
  // `_doc_brief` 的错误列
  errorMsg: '错误信息',

  // ============================================================
  // 题库分享 bank_share_manage
  //   （`bank_share_service.format_share` / `share_info` / `receive_share`）
  // ============================================================
  shareId: '分享 ID',
  shareCode: '分享码',
  shareToken: '分享链接',
  expireTime: '过期时间',
  expireText: '有效期',
  effective: '有效',
  receiveCount: '领取人数',
  shareMessage: '留言',
  ownerName: '分享者',
  ownerNickName: '分享者',
  ownerId: '分享者 ID',
  permission: '权限',
  received: '已领取',
  resultStatus: '领取结果',
  // `bank_share_manage.receive` 的结果里 `resultStatus`(created/exists/restored) 是机器码，
  // 后端**同时**给 `resultStatusText`(已领取 / 之前就已经领取过 / 已重新领取…)——
  // 这一份才是给人看的（值域出处：`bank_share_service.receive_share`）
  resultStatusText: '领取结果',
  alreadyReceived: '之前已领取',
  isOwner: '分享者本人',
  invalidatedReceivers: '受影响人数',
  revoked: '已撤销',
  newBankName: '新题库名',
  allowFork: '允许复制',
  sourceBankId: '源题库 ID',
  sourceBankName: '源题库名',
  shares: '分享',
  coverImage: '封面',

  // ============================================================
  // 指挥家派发专家 delegate_task
  //   （`delegate.py` 的 ok(subAgent, subAgentName, result, steps)）
  //   ⚠️ 这些键名较长（subAgentName 等），不映射的话 68px 标签栏装不下，
  //      会和右侧的值「碰在一起」——故必须补中文短标签。
  // ============================================================
  subAgent: '专家',
  subAgentName: '专家',
  sub_agent: '专家',
  result: '结论',
  steps: '执行步骤',
  task: '任务',

  // ============================================================
  // 题库管理 bank_manage / 题目管理 question_manage / 笔记管理 note_manage
  //   `changed` 是一次更新真正动过的列名（bank/question/note/knowledge_base 共用）
  // ============================================================
  changed: '修改字段',
  // `bank_manage.delete/delete_many` 的 `deleted[]` 元素是 `{id, bankName}`（题库）
  id: '题库 ID',
  failed: '失败数',
  parseStrategy: '解析方式',
  warnings: '提示',
  droppedMarkers: '忽略标记',
  droppedImageMarkers: '忽略标记',
  outOfRange: '越界题号',
  orderNum: '排序',

  // ============================================================
  // 写入知识库 knowledge_ingest
  //   （回执 / 确认预览都会出现的 `kbName`；`kbId` 已在上面那节）
  // ============================================================
  kbName: '知识库名称',
  estimatedChunks: '预计分块数',
  embedCalls: '向量化次数',
  charCount: '字符数',
  source: '来源',

  // ============================================================
  // 智能体管理 agent_manage
  //   （`agent_config_service.to_dict`：agentId/name/greeting/personaPrompt/tools/
  //    model/isEnabled；list 回 `agents`、create/update 回 `agent`）
  // ============================================================
  agent: '智能体',
  agents: '智能体',
  agentId: '智能体 ID',
  greeting: '问候语',
  personaPrompt: '人设提示词',
  tools: '可用工具',
  model: '模型',
  isEnabled: '启用状态'
}

/**
 * 字段名 → 标签。多数键查 `FIELD_LABELS` 即可，但 **同一个键在两个工具里语义相反** 时
 * 只能看值的形状：`errors` ——
 *   · `question_manage.batch_import`：**导入失败的字符串明细**（数组元素是字符串）；
 *   · `question_flag_manage.list`：**错题本记录**（数组元素是对象，`_ITEMS_KEY`）。
 * 前者套「错题」是错的，所以这里按「是不是对象数组」分开取名。
 */
const labelOf = (key: string, value?: any): string => {
  if (key === 'errors') {
    const arr = Array.isArray(value) ? value.map(expand) : []
    return arr.length > 0 && arr.every(isPlainObject) ? '错题' : '导入错误'
  }
  return FIELD_LABELS[key] || key
}

/** 题型 id → 文案（与后端 `app/services/question_write_service.py` 的 QUESTION_TYPE_TEXT 一致） */
const QUESTION_TYPE_TEXT: Record<string, string> = {
  '1': '单选题',
  '2': '多选题',
  '3': '判断题',
  '4': '填空题',
  '5': '简答题',
  '6': '阅读理解（组合题）',
  '7': '完形填空（组合题）'
}

/**
 * 值是「枚举数字」的字段：数字对人没意义，换成人话；映射不中时照原样显示
 *
 * ⚠️ 这张表是**按字段名**全局生效的，所以只往里放**语义唯一**的键。
 *    `status` 就**故意不在这里**（见下面 REDUNDANT_KEYS 的注释）：
 *    错题记录的 `status` 是 1=活跃、分享的 `status` 是 '0'=有效，
 *    塞进同一张表必然给其中一个显示反 —— 与 `isPublic` 那个坑同一类问题。
 */
const ENUM_LABELS: Record<string, Record<string, string>> = {
  difficulty: { '1': '简单', '2': '中等', '3': '较难', '4': '很难' },
  questionType: QUESTION_TYPE_TEXT,
  question_type: QUESTION_TYPE_TEXT,
  isPublic: { '0': '公开', '1': '私密' },
  is_public: { '0': '公开', '1': '私密' },
  // ---- 0/1 状态位（原先显示的是裸 0/1，用户看不出是什么）
  // 错题：`status=1` 活跃在错题本里；`is_mastered=1` 已掌握（见 question_record_service 模块 docstring）
  isMastered: { '0': '未掌握', '1': '已掌握' },
  // 收藏 / 斩题：「取消」是**物理删行**，所以这两列只会有 1（见同一个 docstring）
  favoriteStatus: { '0': '未收藏', '1': '已收藏' },
  markedStatus: { '0': '未斩题', '1': '已斩题' },
  // 斩题类型：与 `question_record_service.MARKED_TYPE_TEXT` 逐个相同（questions.py 的同一张表）
  markedType: { '1': '错题', '2': '难题', '3': '重点', '4': '易错', '5': '技巧' },
  // 知识库屏蔽位：与 `knowledge_base_manage._disabled_text` 同口径（0=参与检索，1=不参与）
  disabled: { '0': '启用', '1': '已屏蔽' },
  // 智能体启用位：`agent_config_service.to_dict` 回的 `isEnabled` 是 int（1=启用 / 0=已停用）
  isEnabled: { '0': '已停用', '1': '启用' }
}

/**
 * 语义是「是/否」的字段：后端有时给 bool、有时给 0/1。
 * `scalarText` 只在值**本来就是** boolean 时才翻，0/1 会原样显示成「0」，
 * 所以这些**确认是整数 0/1** 的列必须列在这里，否则用户看到的是裸数字。
 */
const YES_NO_KEYS = new Set([
  'hasSubQuestions',
  'has_sub_questions',
  // 收藏记录：`is_starred` 是 int 0/1
  'isStarred',
  // 加入/取消标记的回执：`created`（本次新建）是 bool、`allowFork`/`revoked` 是 int 0/1
  'created',
  'allowFork',
  'revoked'
])

const hasText = (...vals: any[]) =>
  vals.some((v) => (typeof v === 'string' ? v.trim() !== '' : v !== undefined && v !== null))

/**
 * 后端把「同一件事」用两个字段给了两遍，展示时只留信息量大的那个：
 *   · `questionType`(1) 与 `questionTypeText`(单选题) —— 数字对人没意义
 *   · `subCount` 与 `hasSubQuestions` —— 没有子题时 subCount 必然是 0，纯噪声
 *   · `offset` 与它自己的 0 / `hasMore` 与它自己的 false —— 默认值不是信息
 *
 * （`preview` 与 `questionText` 的关系也是重复，但它靠 `TITLE_GROUPS` 解决：
 *  两者在**同一组**里，标题选了组里任意一个，组里其余的一起从键值区去掉。
 *  **不能**在这里判断 —— 「有 `questionText` 就不显示 `preview`」这条在
 *  `question_flag_manage.list` 的元素上**永远不成立**：那种元素只有 `preview`、没有 `questionText`，
 *  而 `preview` 正是要拿它当标题的题干。）
 */
const REDUNDANT_KEYS: Array<[string, (obj: any) => boolean]> = [
  ['questionType', (o) => hasText(o.questionTypeText, o.question_type_text)],
  ['question_type', (o) => hasText(o.questionTypeText, o.question_type_text)],
  // 笔记：有 `statusText`(草稿) 就不显示原始 `status`(draft)，同 questionTypeText 的道理
  //
  // ⚠️ 第二个条件（`effective` 是布尔）守的是**分享记录**：`format_share` 每条都带
  //    `status`('0'=有效) 和 `effective`(bool)，后者就是前者的结论。
  //    单看 `status` 没人知道 '0' 是什么意思，旁边那个 是/否 才是给人看的。
  //    ⚠️ 错题记录**不再是「缺人话」**：后端已把那一列整个删掉（`brief_of` 的错题分支，
  //       `question_record_service.py`）—— 理由是 `list_records(active_only=True)` 已把
  //       `status == 1` 写进 WHERE，该列恒为 1、只会渲染成一行「状态：1」，对谁都是零信息；
  //       「已掌握」那件事由 `isMastered` 表达。所以**本规则行为不变**（错题项里没有 `status`
  //       可显示了），它现在只为 `note_brief`(`status`/`statusText`) 与
  //       `format_share`(`status`/`effective`) 生效 —— **别**因为「错题项已没有 status」就删掉它。
  ['status', (o) => hasText(o.statusText, o.status_text) || typeof o.effective === 'boolean'],
  ['subCount', (o) => !o.hasSubQuestions && !o.has_sub_questions],
  ['sub_count', (o) => !o.hasSubQuestions && !o.has_sub_questions],
  ['offset', (o) => !o.offset],
  ['hasMore', (o) => !o.hasMore],
  ['has_more', (o) => !o.has_more],
  // 机器标识符 + 它的人话，后端两个都给时只显示人话：
  //   `flagType`(error) / `flagTypeText`(错题本) —— question_flag_manage
  //   `memoryType`(episodic) / `memoryTypeText`(操作记录) —— memory_manage
  //   `markedType`(2) / `markedTypeText`(难题) —— 斩题记录
  // ⚠️ 只在**有**人话那份时才隐：`memory_manage.clear` 的回执只给了 `memoryType`，
  //    那时把它藏掉等于什么都不显示（后端补 `memoryTypeText` 才是正解，已报给 team-lead）。
  ['flagType', (o) => hasText(o.flagTypeText)],
  ['memoryType', (o) => hasText(o.memoryTypeText)],
  ['markedType', (o) => hasText(o.markedTypeText)]
]

/** 对用户没有意义的键：要么恒为真，要么已经在卡片别处显示过了 */
const HIDDEN_KEYS = new Set(['success', 'action', 'message', 'error', 'hint'])
const isHidden = (key: string) => HIDDEN_KEYS.has(key) || key.startsWith('_')

/**
 * 「能当『这条是什么』的字段」——**按组**写，组内是**同一份内容的不同长度 / 两种拼法**。
 *
 * 组与组之间的顺序 = 「选谁当标题」的偏好顺序（`titleOf` 顺序遍历拍平后的 `TITLE_KEYS`）。
 *
 * ⚠️ **题干那一组必须排在题库名前面。**
 *    `question_flag_manage.list` 的元素是 `question_record_service.brief_of` 的产物：
 *    **有 `bankName`、有 `preview`（80 字题干）、没有 `questionText`**。
 *    若 `bankName` 排在 `preview` 前面，标题会被选成**题库名** ——
 *    用户点开详情看到一排 ID 和状态，**唯独不知道是哪道题**。
 *    （`questionText` 与 `preview` 是同一份内容的两种长度：`question_write_service.question_brief`
 *      两种模式都回全文，`include_preview` 时才追加 80 字 `preview`。）
 *
 * ⚠️ 组的范围**就是** `restOf` 的去重范围：标题选了组里任意一个，**组里其余的一起从键值区去掉**
 *    （否则题干会以「题干 + 题干预览」两种长度各显示一遍）。**组外的字段一律照常以键值行出现** ——
 *    所以只有 `bankName` + `preview` 的元素，题库名不会被题干挤掉，两者都看得见。
 */
const TITLE_GROUPS = [
  // ① 题干：全文 / 截断版，同一份内容只该出现一次
  ['questionText', 'question_text', 'preview'],
  // ② 题库名 —— 题干缺失（没反查到题）时才退到这里
  ['bankName', 'bank_name'],
  // ③ 通用名 / 标题 / 关键词：笔记走 `title`（`note_brief`）、知识库走 `name`（`_kb_brief`）
  ['name'],
  ['title'],
  ['keyword']
]

/** 拍平后的偏好顺序 —— `titleOf` 按它逐个试 */
const TITLE_KEYS = TITLE_GROUPS.flat()

/** 这条 `data` 是「落库时被瘦身」的产物，不是真实结果 —— 见模板顶部注释 */
const truncated = computed(() => (props.data as any)?._truncated === true)

const bytesText = computed(() => {
  const b = Number((props.data as any)?._bytes)
  return Number.isFinite(b) && b > 0 ? `（约 ${Math.round(b / 1024)} KB）` : ''
})

const isPlainObject = (v: any) => !!v && typeof v === 'object' && !Array.isArray(v)
const isScalar = (v: any) => v === null || ['string', 'number', 'boolean'].includes(typeof v)

const clip = (s: string, max: number) =>
  s.length > max ? `${s.slice(0, max)}…（共 ${s.length} 字）` : s

const yesNo = (v: any) => (v === true || v === 1 || v === '1' || v === 'true' ? '是' : '否')

function scalarText(v: any): string {
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (v === null || v === undefined) return '—'
  return clip(String(v), MAX_TEXT)
}

/** 先查枚举表，查不到再按标量渲染 */
const renderValue = (key: string, v: any): string => {
  const hit = ENUM_LABELS[key]?.[String(v)]
  if (hit) return hit
  if (YES_NO_KEYS.has(key)) return yesNo(v)
  return scalarText(v)
}

/**
 * 有些字段是「被转成字符串的 JSON」（最典型的是 `options: '["A. x","B. y"]'`）。
 * 先解析回结构，否则选项会以一整串带转义符的字符串糊在界面上。
 */
function expand(v: any): any {
  if (typeof v !== 'string') return v
  const s = v.trim()
  if (s.length > 1 && (s[0] === '[' || s[0] === '{')) {
    try {
      const parsed = JSON.parse(s)
      if (parsed && typeof parsed === 'object') return parsed
    } catch {
      /* 就是普通字符串，按原样展示 */
    }
  }
  return v
}

/** 过滤空值 / 无意义键 / 重复键 */
function visibleEntries(obj: any): [string, any][] {
  if (!isPlainObject(obj)) return []
  return Object.entries(obj)
    .filter(([key, value]) => {
      if (isHidden(key)) return false
      if (REDUNDANT_KEYS.some(([k, when]) => k === key && when(obj))) return false
      const v = expand(value)
      if (v === undefined || v === null || v === '') return false
      if (Array.isArray(v) && v.length === 0) return false
      if (isPlainObject(v) && Object.keys(v).length === 0) return false
      return true
    })
    .map(([key, value]) => [key, expand(value)])
}

const isItemList = computed(() => {
  const d = props.data
  return Array.isArray(d) && d.length > 0 && d.every((x) => isPlainObject(expand(x)))
})

/* ---------- 分页 ----------
 * 一个题库 30 道题、一次 list 就 30 张卡 —— 全铺出来会把消息流撑成一面墙，
 * 但只截前 8 条、剩下的吞掉更糟：用户点不动、也看不到（就是之前那句
 * 「还有 22 条未展开」的问题）。所以分页：默认只看第一页，剩下的能翻。
 */
const page = ref(1)

const total = computed(() => (Array.isArray(props.data) ? props.data.length : 0))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

/**
 * 取「实际生效」的页码而不是 `page.value`：
 * 翻到第 4 页后工具结果若被替换成更短的列表，`page` 会越界，
 * 那时应该回到最后一页而不是显示空白。
 */
const safePage = computed(() => Math.min(page.value, pageCount.value))
const pageStart = computed(() => (safePage.value - 1) * PAGE_SIZE)

const pagedItems = computed(() => {
  const d = props.data
  return Array.isArray(d) ? d.slice(pageStart.value, pageStart.value + PAGE_SIZE) : []
})

/** 只有超过一页才给翻页条，否则底部不出现任何多余的东西 */
const showPager = computed(() => total.value > PAGE_SIZE)

/** 服务端还有多少条没取回来（后端只回了一页时 > 0） */
const missingFromServer = computed(() => {
  const st = props.serverTotal
  return typeof st === 'number' && st > total.value ? st - total.value : 0
})

/**
 * 递归到某个数组字段时，把父级 `total` 传下去当「服务端总量」。
 *
 * ⚠️ 只认这几个**会被拿去当总数展示**的字段名 ——
 *    否则随便一个数组（比如 `subQuestions`）都会把父级的 `total` 认成自己的总量，
 *    平白多出一句「本次只取回 3 条（共 30 条）」。
 *
 * 名单里每一项都对应一个「父级会同时给 `total` + 只回一页」的结果：
 *   · `questions` / `banks` —— question_manage / bank_manage
 *   · `errors` / `favorites` / `markedQuestions` —— question_flag_manage.list（limit/offset）
 *   · `documents` —— knowledge_base_manage.list_documents（limit/offset）
 *   · `shares` —— bank_share_manage.list_shares（limit/offset）
 */
const COUNTED_LIST_KEYS = new Set([
  'questions',
  'banks',
  'items',
  'errors',
  'favorites',
  'markedQuestions',
  'documents',
  'shares'
])
function rowServerTotal(key: string): number | undefined {
  const parentTotal = (props.data as any)?.total
  return COUNTED_LIST_KEYS.has(key) && typeof parentTotal === 'number' ? parentTotal : undefined
}

function turn(delta: number) {
  page.value = Math.min(Math.max(safePage.value + delta, 1), pageCount.value)
}

// ⚠️ 监听**条数**而不是 `props.data` 本身：父级模板里传下来的是 `restOf(item)`，
//    每次父组件重渲染都会造一个新对象，按对象身份监听会把刚翻到的页码冲掉。
watch(total, () => {
  page.value = 1
})

const rows = computed(() => {
  const out: { key: string; label: string; kind: string; text?: string; chips?: string[]; value?: any }[] = []
  for (const [key, value] of visibleEntries(props.data)) {
    if (isScalar(value)) {
      out.push({ key, label: labelOf(key, value), kind: 'scalar', text: renderValue(key, value) })
    } else if (Array.isArray(value) && value.every(isScalar)) {
      out.push({ key, label: labelOf(key, value), kind: 'chips', chips: value.map((v) => renderValue(key, v)) })
    } else if (props.depth + 1 > MAX_DEPTH) {
      out.push({ key, label: labelOf(key, value), kind: 'scalar', text: '（内容较深，已省略）' })
    } else {
      out.push({ key, label: labelOf(key, value), kind: 'nested', value })
    }
  }
  return out
})

/** `titleOf` 实际选中的那个键（一个都没命中给 null）—— `restOf` 靠它决定摘哪一组 */
function titleKeyOf(item: any): string | null {
  for (const key of TITLE_KEYS) {
    const v = item?.[key]
    if (typeof v === 'string' && v.trim()) return key
  }
  return null
}

function titleOf(item: any): string {
  const key = titleKeyOf(item)
  if (!key) return ''
  return clip(String(item[key]).trim(), MAX_TITLE)
}

/**
 * 标题里显示过的字段，就不在下面的键值行里重复一遍。
 *
 * ⚠️ 摘的是「`titleOf` **真正选中的那个键** + **它所在组**里的同义键」，
 *    **不是整张 `TITLE_KEYS`**（旧写法是 `if (TITLE_KEYS.includes(key)) continue`）。
 *    按整张表跳过会连没被选中的字段一起吞掉：`question_flag_manage.list` 的元素
 *    （有 `bankName`、有 `preview`、无 `questionText`）标题选成题库名之后，
 *    **题干 `preview` 也被摘掉了** —— 卡片上任何位置都看不到是哪道题。
 *    现在只有被选中的那一组被摘，**其余字段（题库名、科目、时间…）照常以键值行出现**。
 */
function restOf(item: any): any {
  const key = titleKeyOf(item)
  if (!key) return item
  const drop = new Set(TITLE_GROUPS.find((g) => g.includes(key)) || [key])
  const out: Record<string, any> = {}
  for (const [k, value] of Object.entries(item || {})) {
    if (drop.has(k)) continue
    out[k] = value
  }
  return out
}
</script>

<style scoped>
/* 「结果太大没存下来」的提示条 —— 见模板顶部注释，这必须有，否则就是一片空白 */
.td-truncated {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 7px 9px;
  border: 1px solid #fde68a;
  border-radius: 7px;
  background: #fffbeb;
  font-size: 12px;
  line-height: 1.65;
  color: #b45309;
  overflow-wrap: anywhere;
}

.td-truncated-icon {
  flex: none;
  width: 15px;
  height: 15px;
  margin-top: 1px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: #f59e0b;
}

.td-fields {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.td-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

/* 标签定宽、值自适应并自由换行 —— 窄卡片下也不会互相挤 */
.td-key {
  flex: none;
  width: 68px;
  font-size: 12px;
  line-height: 1.6;
  color: #8a94a6;
}

.td-val {
  flex: 1;
  min-width: 0;
}

.td-text {
  display: block;
  font-size: 12.5px;
  line-height: 1.6;
  color: #33415c;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.td-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 5px;
}

.td-chip {
  font-size: 11.5px;
  line-height: 1.7;
  padding: 0 7px;
  border-radius: 6px;
  color: #526581;
  background: #f1f5f9;
  border: 1px solid #e6ecf3;
  overflow-wrap: anywhere;
}

/* 对象数组：一条一张小卡，靠卡片本身做视觉分组 */
.td-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.td-item {
  padding: 7px 9px;
  border: 1px solid #eef2f7;
  border-radius: 7px;
  background: #fbfcfe;
}

.td-item-title {
  margin-bottom: 4px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #1f2d3d;
  overflow-wrap: anywhere;
}

/* 分页条：只有超过一页才渲染。窄卡片下按钮会被挤到第二行，所以允许 wrap */
.td-pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 2px;
  padding-top: 8px;
  border-top: 1px dashed #eef2f7;
}

.td-page-btn {
  font-family: inherit;
  font-size: 11.5px;
  line-height: 1.9;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #526581;
  cursor: pointer;
}

.td-page-btn:hover:not(:disabled) {
  color: #2563eb;
  border-color: #bfdbfe;
  background: #f8fbff;
}

.td-page-btn:disabled {
  color: #c3cbd8;
  background: #f8fafc;
  cursor: not-allowed;
}

.td-page-info {
  font-size: 11.5px;
  color: #8a94a6;
}

/* 「后端只回了一页」的补充说明，跟在翻页条下面 */
/* 紧跟在翻页条下面时不用再来一条分隔线（上面那条已经是了），免得出现双线 */
.td-pager + .td-server-more {
  padding-top: 2px;
  border-top: none;
}

.td-server-more {
  padding-top: 6px;
  border-top: 1px dashed #eef2f7;
  font-size: 11.5px;
  line-height: 1.6;
  color: #9aa5b5;
  text-align: center;
  overflow-wrap: anywhere;
}
</style>
