<template>
  <div class="notes-editor-container">
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" :icon="ArrowLeft" text class="back-btn">
          返回笔记
        </el-button>
      </div>
      <h2 class="header-title">{{ noteTitle ? noteTitle + ' - ' : '' }}{{ editingNoteId ? '编辑笔记' : '写笔记' }}</h2>
      <div class="header-right">
        <el-button class="header-settings-btn" size="small" :icon="Setting" @click="settingsDrawerVisible = true">
          笔记设置
        </el-button>
        <el-button type="primary" class="header-publish-btn" size="small" :loading="saving" @click="handlePublish">
          {{ editingNoteId ? '保存' : '发布' }}
        </el-button>
      </div>
    </div>

    <div class="editor-body">
      <div class="editor-main">
        <!-- 标题 + 高频元信息（始终可见，直接编辑） -->
        <div class="note-meta-card">
          <div class="meta-title-row">
          <el-input ref="titleInputRef" v-model="noteTitle" class="note-title-input"
            :class="{ 'is-missing': missingField === 'title' }" placeholder="请输入笔记标题…" maxlength="100"
            @keydown.enter.prevent="focusEditor" />
            <!-- 复制 / 导出：原来挤在顶栏右侧，移到标题这一行，顶栏只留「笔记设置 + 保存」 -->
            <div class="title-actions">
              <el-tooltip content="复制全文" placement="top" :show-after="300">
                <el-button class="icon-action-btn" :icon="DocumentCopy" circle @click="copyNote" />
              </el-tooltip>
              <el-tooltip content="导出 Markdown" placement="top" :show-after="300">
                <el-button class="icon-action-btn" :icon="Download" circle @click="exportNote" />
              </el-tooltip>
            </div>
          </div>

          <div class="meta-row">
            <div class="meta-field meta-category" :class="{ 'is-missing': missingField === 'category' }">
              <el-select v-model="selectedCategoryId" placeholder="选择 / 新建分类" allow-create filterable
                default-first-option size="small" class="meta-select">
                <el-option v-for="cat in categoryList" :key="cat.id" :label="cat.name" :value="cat.id" />
              </el-select>
            </div>

            <el-radio-group v-model="isPublic" class="visibility-segment" size="small">
              <el-radio-button :value="1">公开</el-radio-button>
              <el-radio-button :value="0">私有</el-radio-button>
            </el-radio-group>

            <div class="meta-field meta-tags-field">
              <el-select v-model="selectedTags" multiple filterable allow-create default-first-option collapse-tags
                collapse-tags-tooltip size="small" placeholder="添加标签，回车确认" class="meta-select">
              </el-select>
            </div>

            <transition name="section-fade">
              <div v-if="isPublic === 1" class="meta-field meta-section"
                :class="{ 'is-missing': missingField === 'section' }">
                <el-select v-model="selectedPublicSectionId" placeholder="选择公开分区" size="small" class="meta-select">
                  <el-option v-for="section in publicSectionList" :key="section.id" :label="section.name"
                    :value="section.id" />
                </el-select>
              </div>
            </transition>
          </div>
        </div>

        <TiptapEditor ref="tiptapEditorRef" v-model="editorHtmlContent" placeholder="开始写下你的笔记..."
          @preview-image="openImageViewer">
        </TiptapEditor>
      </div>

      <!-- 笔记设置抽屉（低频项：关联题库 / 关联题目） -->
      <el-drawer v-model="settingsDrawerVisible" title="笔记设置" direction="rtl" size="340px"
        class="note-settings-drawer" append-to-body>
        <div class="drawer-body">
          <div class="drawer-section">
            <label class="drawer-label">关联题库</label>
            <el-select v-model="selectedBankIds" multiple collapse-tags collapse-tags-tooltip
              placeholder="请选择关联题库（可多选）" class="drawer-select">
              <el-option v-for="bank in bankList" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
            </el-select>
            <div v-if="selectedBankIds.length > 0" class="selected-banks-chips">
              <el-tag v-for="bankId in selectedBankIds" :key="bankId" size="small" closable
                @close="removeBank(bankId)">
                {{ getBankName(bankId) }}
              </el-tag>
            </div>
          </div>

          <div class="drawer-section">
            <label class="drawer-label">关联题目</label>
            <NoteQuestionSelector :note-id="editingNoteId" :bank-list="bankList" :show-label="false" />
          </div>

          <div class="drawer-tip">标题、分类、可见性与标签已移至编辑区顶部，写作过程中可直接修改。</div>
        </div>
      </el-drawer>

      <!-- 滚动按钮 -->
      <ScrollButton :bottom="40" :right="20" />
    </div>
  </div>

  <!-- 图片预览模态框 -->
  <ImageViewer v-model:visible="imageViewerVisible" :src="imageViewerSrc" />
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontNotesEditor' })
import { ref, onMounted, onActivated, onDeactivated, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, DocumentCopy, Download, Setting } from '@element-plus/icons-vue'
import { marked } from 'marked'
import TurndownService from 'turndown'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import NoteQuestionSelector from '@/components/NoteQuestionSelector/NoteQuestionSelector.vue'
import { addNote, updateNote, getNote, getNoteDraft, saveNoteDraft, clearNoteDraft } from '@/api/notes/note'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import useUserStore from '@/store/modules/user'
import { getAllNoteCategory, addNoteCategory } from '@/api/noteCategory/noteCategory'
import { getPublicSections } from '@/api/notes/publicSection'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { listFavoriteBankAll } from '@/api/favoriteBank/favoriteBank'
import { addNoteQuestionBank, getNoteQuestionBanksByNoteId } from '@/api/noteQuestionBank/noteQuestionBank'

const cacheStore = useFrontPageCacheStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const turndownService = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced'
})

const editingNoteId = ref(null)

const noteTitle = ref('')
const markdownContent = ref('')
const editorHtmlContent = ref('')
const saving = ref(false)
const isPublic = ref(1)
const categoryList = ref([])
const selectedCategoryId = ref(null)
const selectedTags = ref([])
const publicSectionList = ref([])
const selectedPublicSectionId = ref(null)
const bankList = ref([])
const selectedBankIds = ref([])
// 笔记设置抽屉（关联题库 / 关联题目等低频项）
const settingsDrawerVisible = ref(false)
// 发布校验未通过时高亮的字段：title / category / section
const missingField = ref<null | 'title' | 'category' | 'section'>(null)
let missingTimer: ReturnType<typeof setTimeout> | null = null

const tiptapEditorRef = ref(null)
const titleInputRef = ref<any>(null)
const imageViewerVisible = ref(false)
const imageViewerSrc = ref('')

let lastLoadedId = null
let lastLoadedBankId = null

const getBankName = (bankId) => {
  const bank = bankList.value.find(b => (b.bankId ?? b.id) === bankId)
  return bank ? bank.bankName : `题库${bankId}`
}

// 校验失败：高亮对应字段并在一段时间后自动取消
const flagMissing = (field: 'title' | 'category' | 'section') => {
  missingField.value = field
  if (missingTimer) clearTimeout(missingTimer)
  missingTimer = setTimeout(() => {
    missingField.value = null
  }, 2600)
}

// 标题框按回车，光标跳到正文编辑器
const focusEditor = () => {
  nextTick(() => {
    const pm = document.querySelector('.editor-main .ProseMirror') as HTMLElement | null
    pm?.focus()
  })
}

// 图片预览
const openImageViewer = (src: string) => {
  imageViewerSrc.value = src
  imageViewerVisible.value = true
}

const removeBank = (bankId) => {
  selectedBankIds.value = selectedBankIds.value.filter(id => id !== bankId)
}

const saveNoteQuestionBanks = async (noteId) => {
  if (selectedBankIds.value.length === 0) return
  try {
    const existingRes = await getNoteQuestionBanksByNoteId(noteId)
    if (existingRes.code !== 200) return

    const existingBankIds = (existingRes.data || []).map(item => (item.bankId ?? item.questionBankId ?? item.id))
    const newBankIds = selectedBankIds.value.filter(id => !existingBankIds.includes(id))

    for (const bankId of newBankIds) {
      await addNoteQuestionBank({
        noteId: noteId,
        questionBankId: bankId,
        userId: userStore.id
      })
    }
  } catch (error) {
    console.error('保存笔记题库关联失败:', error)
  }
}

const loadNoteQuestionBanks = async (noteId) => {
  try {
    const res = await getNoteQuestionBanksByNoteId(noteId)
    if (res.code === 200 && res.data) {
      selectedBankIds.value = res.data.map(item => (item.bankId ?? item.questionBankId ?? item.id)) || []
    }
  } catch (error) {
    console.error('加载笔记关联题库失败:', error)
  }
}

/** 「写新笔记」态是否已处理过草稿（幂等守卫，防 onMounted+onActivated 双触发重复读，见 syncEditorMode） */
let newNoteDraftSettled = false

/** 当前登录用户 id（草稿 key 的唯一依据）；未就绪返回空串 */
function currentDraftUserId(): string {
  try {
    const id = (useUserStore() as any).id
    return id === undefined || id === null || id === '' ? '' : String(id)
  } catch {
    return ''
  }
}

/**
 * 等 `userStore.id` 就绪（最多约 1.5s）
 *
 * 刷新/首次进站时 Pinia 里的 id 有一段真空期（getInfo 还没回来）。草稿的读写
 * 全靠它拼 key，没有它就没法判断"这是谁的草稿" —— 详见 draftKey()。
 * 与 `agentSession.loadSessions()` 的做法保持一致。
 */
async function waitForUserId(): Promise<string> {
  let uid = currentDraftUserId()
  for (let i = 0; i < 25 && !uid; i++) {
    await new Promise((r) => setTimeout(r, 60))
    uid = currentDraftUserId()
  }
  return uid
}

const syncEditorMode = async () => {
  const id = route.query.id
  const numId = id ? Number(id) : null

  if (numId) {
    if (numId === lastLoadedId) return
    lastLoadedId = numId
    editingNoteId.value = numId
    // 进入「编辑已有笔记」→ 复位草稿处理标记，以便之后切回「写新笔记」时能重新读草稿
    newNoteDraftSettled = false
    loadNoteData(id)
  } else {
    // ⚠️ 无 id = 「写新笔记」。**不要**在这里写 `if (!editingNoteId.value) return`——
    //    首次进入 / 刷新后编辑页时 `editingNoteId` 初值就是 null，那个 return 会让
    //    `loadDraft()` **永不执行**（用户 2026-10-11 报「离开/刷新后草稿丢了」的根因）。
    //    正确做法：重置为新笔记态（仅当从编辑态切回时），然后**无条件**读草稿。
    //
    // ⚠️ 幂等守卫：本组件在 keep-alive 内，首次挂载时 **onMounted 与 onActivated 都会触发**
    //    `syncEditorMode()` → 若不加守卫，else 分支会跑两次 → 第二次读草稿还可能覆盖
    //    用户已输入内容。已处理过就返回。
    if (newNoteDraftSettled) return
    /*
     * ⚠️ 必须等 uid 就绪再读草稿（用户 2026-10-19 报「两个演示用户共用一篇草稿」）：
     *    刷新/首次进站时 `userStore.id` 有一段真空期，此刻 draftKey() 是空，
     *    读不到"自己的"那份草稿。上一版会在 uid 空时退回共享槽位 —— 那正是串号的来源。
     *    现在改为**等一下**（与 agentSession.loadSessions 同款轮询），拿不到才放弃。
     */
    const uid = await waitForUserId()
    if (!uid) return
    if (lastLoadedId !== null || editingNoteId.value !== null) {
      lastLoadedId = null
      editingNoteId.value = null
      noteTitle.value = ''
      markdownContent.value = ''
      editorHtmlContent.value = ''
      isPublic.value = 1
      selectedCategoryId.value = null
      selectedTags.value = []
      selectedPublicSectionId.value = null
    }
    // 幂等标记必须在 await 之前置位：否则 await 期间 onActivated 重入会再跑一遍。
    newNoteDraftSettled = true
    /*
     * 分类列表要先就绪：applyDraft 用它校验草稿里的 categoryId 是否属于当前用户
     * （见那里的说明）。
     * ⚠️ 这里**不能**直接 `await loadCategories()` —— 它在下方才用 `const` 声明，
     *    虽然本函数是在 await 之后才执行到那行（此时模块已求值完），但依赖这种
     *    时序太脆弱（TDZ 一旦命中就是白屏，且 build 查不出来）。改为内联同一个请求。
     */
    if (!Array.isArray(categoryList.value) || !categoryList.value.length) {
      try {
        const res: any = await getAllNoteCategory({ userId: userStore.id })
        if (res.code === 200) categoryList.value = res.data || []
      } catch {
        /* 拿不到分类列表 → applyDraft 会认为所有 categoryId 都非法，置空让用户重选 */
      }
    }
    // 恢复草稿**静默**进行：内容会直接出现在编辑器里，不再弹任何提示
    // （用户 2026-10-19：「直接把整个草稿提示删除掉，不需要了」）。
    await loadDraft()
  }
}

/**
 * 草稿的 localStorage key（**按用户隔离**）
 * ============================================================================
 * 用户 2026-10-18：「草稿功能没做用户区分！演示用户1 和 演示用户2 共用了一个草稿」。
 *
 * 根因：key 是写死的 `'note_draft'`，同一浏览器里所有账号共用一个槽位 ——
 *      演示用户1 写的草稿，切到演示用户2 会被读出来并覆盖对方的内容。
 *
 * 现在 key 带用户 id：`openstudy_note_draft_<userId>`。
 * 拿不到 userId 时退回旧 key（保证未登录/异常时不至于存不进去），
 * 但正常登录态一律走隔离 key。
 *
 * ⚠️ 同时做**旧 key 的一次性迁移**：把历史上存在 `note_draft` 里的内容
 *    搬给当前用户，避免升级后老用户以为草稿丢了。
 */
const LEGACY_DRAFT_KEY = 'note_draft'
const DRAFT_KEY_PREFIX = 'openstudy_note_draft'

/**
 * 草稿 key：**必须**带用户 id（`currentDraftUserId()` 已上移到 waitForUserId 旁边）
 *
 * ⚠️ 用户 2026-10-19 再报「演示用户1 的草稿，演示用户2 也是同一篇」。
 *
 * 上一版虽然把 key 改成了 `openstudy_note_draft_<uid>`，但**取不到 uid 时会退回
 * 共享的 `note_draft`**。而 refresh / 首次进站时 `userStore.id` 有一段真空期
 * （Pinia 刚建、getInfo 还没回来），此时 `onMounted → syncEditorMode → loadDraft`
 * 拿到的 key 就是那个共享槽位 —— 谁先登录谁的内容落进去，下一个账号原样读出来。
 *
 * 现在取不到 uid 时返回空串，调用方一律**跳过**本地草稿（只认后端草稿，
 * 后端那份天然按 token 隔离）。等 uid 就绪后 onActivated / 切路由会重新走一遍。
 */
function draftKey(): string {
  const uid = currentDraftUserId()
  return uid ? `${DRAFT_KEY_PREFIX}_${uid}` : ''
}

/**
 * 把旧版共享 key 的内容迁到当前用户的隔离 key
 *
 * 只在「当前用户的隔离 key 还是空的」且「旧 key 有内容」时搬一次，
 * 搬完删掉旧 key（否则下一个账号登录还会再搬一次）。
 * 迁移只在拿到 uid 后执行，避免把共享槽位的内容写给错误的用户。
 */
function migrateLegacyDraftOnce() {
  const uid = currentDraftUserId()
  if (!uid) return
  const scoped = `${DRAFT_KEY_PREFIX}_${uid}`
  try {
    const legacy = localStorage.getItem(LEGACY_DRAFT_KEY)
    if (!legacy) return
    if (!localStorage.getItem(scoped)) localStorage.setItem(scoped, legacy)
    localStorage.removeItem(LEGACY_DRAFT_KEY)
  } catch {
    /* 隐私模式下忽略 */
  }
}

/** 把一份草稿对象套用到表单（本地草稿与后端草稿共用同一套字段名） */
const applyDraft = (d: any) => {
  const md = d.content || d.markdownContent || ''
  noteTitle.value = d.title || ''
  markdownContent.value = md
  editorHtmlContent.value = marked.parse(md)
  // ⚠️ 用 ?? 不用 ||：isPublic=0（私密）是合法值，`0 || 1` 会被错误改成 1（公开）。
  isPublic.value = d.isPublic ?? 1
  /*
   * 分类要校验归属：草稿里的 categoryId 可能是**别人**的分类 id。
   *
   * 历史上草稿串号时（用户 2026-10-19 报的 bug2），user1 的分类 id 被写进了
   * user2 的草稿里；直接套用会让下拉框显示一个孤零零的数字（el-select 找不到
   * 对应 option 就回退显示原始 value），既看不懂、发布时还会带上不属于自己的分类。
   *
   * 这里只接受「当前用户的分类列表里确实存在」的 id，否则置空让用户重选。
   * ⚠️ 注意 categoryList 是异步加载的：调用方（loadDraft）已确保它先就绪。
   */
  const catId = d.categoryId ?? null
  const catOk = catId === null || (Array.isArray(categoryList.value) &&
    categoryList.value.some((c: any) => String(c.id) === String(catId)))
  selectedCategoryId.value = catOk ? catId : null
  selectedTags.value = d.tags || []
  selectedPublicSectionId.value = d.publicSectionId ?? null
  nextTick(() => {
    if (tiptapEditorRef.value) {
      tiptapEditorRef.value.setContent(editorHtmlContent.value)
    }
  })
}

/**
 * 读草稿并套用到表单（仅「写新笔记」用；草稿不属于任何笔记、没有 noteId）。
 *
 * 用户 2026-10-11：**两个来源合并** —— 浏览器 localStorage 草稿 + 后端「用户草稿」
 * （智能体 `note_manage.save_draft` 写的也是后端那份）。**谁 updateTime 新用谁**，
 * 这样"换设备后智能体帮存的草稿"也能带出来；本地那份作为离线兜底。
 *
 * @returns 实际恢复的那份草稿；没有可用草稿时返回 `null`。
 *
 * ⚠️ 空草稿（标题与正文都空）忽略、**不覆盖**当前表单。
 * ⚠️ 恢复过程**不弹提示**：内容直接出现在编辑器里即可（用户 2026-10-19 要求删掉「已恢复上次未发布的草稿」）。
 */
const loadDraft = async (): Promise<any | null> => {
  // 本地草稿（按用户隔离的 key，见 draftKey()）
  // ⚠️ key 为空 = 还没拿到 uid → 跳过本地那份（绝不能退回共享槽位，否则读到的
  //    可能是上一个登录账号的草稿，用户 2026-10-19 报的"两个演示用户同一篇"就是它）。
  let local: any = null
  const key = draftKey()
  if (key) {
    try {
      const raw = localStorage.getItem(key)
      if (raw) local = JSON.parse(raw)
    } catch (e) {
      console.error('读取本地草稿失败:', e)
    }
  }
  // 后端草稿（失败当作没有，不影响本地兜底）
  let remote: any = null
  try {
    const res: any = await getNoteDraft()
    if (res?.code === 200 && res.data) remote = res.data
  } catch (e) {
    console.error('读取后端草稿失败:', e)
  }

  const localHas = !!(local && ((local.content || '').trim() || (local.title || '').trim()))
  const remoteHas = !!(remote && ((remote.content || remote.markdownContent || '').trim() || (remote.title || '').trim()))
  if (!localHas && !remoteHas) return null

  // 谁新用谁：无法比较时间时优先本地（用户本机最新编辑的确定性更高）
  let picked = local
  if (remoteHas && localHas) {
    const lt = Date.parse(local.updatedAt || '') || 0
    const rt = Date.parse(remote.updateTime || '') || 0
    picked = rt > lt ? remote : local
  } else if (remoteHas) {
    picked = remote
  }
  applyDraft(picked)
  return picked
}

/**
 * 存草稿（仅「写新笔记」模式）：**本地 + 后端双写**。
 *
 * ⚠️ **编辑已有笔记时不写草稿**：否则用户编辑某篇笔记的过程中，watch 会把它的内容盖进
 *    `note_draft`，等 ta 回「写笔记」时被错误带出别人的内容（用户 2026-10-11 要求排查的
 *    「从其他地方点编辑笔记会不会覆盖草稿」正是这个坑）。
 * ⚠️ 内容全空（标题与正文都空）时**不写**、并清掉两处草稿，避免留下一条脏草稿。
 */
const saveDraft = () => {
  try {
    // 编辑已有笔记 → 不写草稿（草稿只属于「尚未发布的新笔记」）
    if (editingNoteId.value) return

    const key = draftKey()
    /*
     * ⚠️ 拿不到 uid 时**连后端也不写**（用户 2026-10-19 报的跨用户共享）：
     *    localStorage 没有隔离槽位可用，而此刻发出去的 PUT 也未必带对用户
     *    （uid 真空期通常意味着登录态刚建立）；一旦写错，后端那份就是**共享**的，
     *    下一个账号读出来就是别人的内容。等 uid 就绪后 watch 会再次触发保存。
     */
    if (!key) return

    const md = editorHtmlContent.value ? turndownService.turndown(editorHtmlContent.value) : ''
    // 全空 → 清掉两处草稿，不留脏数据
    if (!md.trim() && !noteTitle.value.trim()) {
      localStorage.removeItem(key)
      clearNoteDraft().catch(() => {})
      return
    }
    const payload = {
      title: noteTitle.value,
      content: md,
      markdownContent: md,
      isPublic: isPublic.value,
      categoryId: selectedCategoryId.value,
      tags: selectedTags.value,
      publicSectionId: selectedPublicSectionId.value
    }
    localStorage.setItem(key, JSON.stringify({ ...payload, updatedAt: new Date().toISOString() }))
    // 同步后端草稿（失败不影响本地草稿，静默即可——本地已是兜底）
    saveNoteDraft(payload).catch(() => {})
  } catch (error) {
    console.error('保存草稿失败:', error)
  }
}

const clearDraft = () => {
  const key = draftKey()
  try {
    if (key) localStorage.removeItem(key)
  } catch (error) {
    console.error('清除草稿失败:', error)
  }
  // 后端草稿也一并清（发布成功时两处都要清）
  clearNoteDraft().catch(() => {})
}

const goBack = () => {
  saveDraft()
  if (editingNoteId.value) {
    router.push(`/front/notes/detail/${editingNoteId.value}`)
  } else {
    router.push('/front/notes/list')
  }
}

const exportNote = () => {
  const title = noteTitle.value || '笔记'
  let mdContent = markdownContent.value
  if (!mdContent && editorHtmlContent.value) {
    mdContent = turndownService.turndown(editorHtmlContent.value)
  }
  const content = `# ${title}\n\n${mdContent || ''}`
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('笔记已导出为 Markdown 文件')
}

const loadCategories = async () => {
  const res = await getAllNoteCategory({ userId: userStore.id })
  if (res.code === 200) {
    categoryList.value = res.data || []
  }
}

const loadPublicSections = async () => {
  try {
    const res = await getPublicSections()
    if (res.code === 200) {
      publicSectionList.value = res.data || []
    }
  } catch (error) {
    console.error('获取公开分区失败:', error)
  }
}

const loadQuestionBanks = async () => {
  try {
    // 自己的题库 + 收藏的题库：两者都能被笔记关联。
    // 只列 listMyQuestionBank（自己创建的）会让「收藏了别人的题库」根本选不到。
    const [mine, favs] = await Promise.all([
      listMyQuestionBank(),
      listFavoriteBankAll({})
    ])
    const own = mine?.code === 200 ? (mine.data || []) : []
    const fav = favs?.code === 200 ? (favs.data || []) : []
    // 按 bankId 去重：自己创建的库也可能被自己收藏，会出现两次
    const seen = new Set()
    bankList.value = [...own, ...fav].filter((b: any) => {
      const id = b.bankId ?? b.id
      if (id == null || seen.has(id)) return false
      seen.add(id)
      return true
    })
  } catch (error) {
    console.error('获取题库列表失败:', error)
  }
}

const loadNoteData = async (id) => {
  try {
    const res = await getNote(id)
    if (res.code === 200 && res.data) {
      const note = res.data
      noteTitle.value = note.title || ''
      markdownContent.value = note.markdownContent || ''
      editorHtmlContent.value = marked.parse(note.markdownContent || '')
      isPublic.value = note.isPublic ?? 1
      selectedCategoryId.value = note.categoryId || null
      selectedTags.value = typeof note.tags === 'string'
        ? note.tags.split(',').filter(t => t.trim())
        : (note.tags || [])
      selectedPublicSectionId.value = note.publicSectionId || null
      await loadNoteQuestionBanks(id)
      await nextTick()
      if (tiptapEditorRef.value) {
        tiptapEditorRef.value.setContent(editorHtmlContent.value)
      }
    }
  } catch (error) {
    ElMessage.error('加载笔记数据失败')
    console.error(error)
  }
}

onMounted(async () => {
  // 先把旧版共享 key 的草稿迁到当前用户的隔离 key（否则升级后用户会觉得草稿丢了）
  migrateLegacyDraftOnce()
  await Promise.all([
    loadCategories(),
    loadPublicSections(),
    loadQuestionBanks()
  ])
  await syncEditorMode()

  document.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
  if (missingTimer) clearTimeout(missingTimer)
  // 离开编辑页时兜底存一次草稿：`watch` 是 500ms 防抖，用户若在防抖窗口内直接关标签页 /
  // 切路由（不走 `goBack`），最后一次改动会丢。这里补一次同步保存（内部已保证编辑已有
  // 笔记时不写、空内容不留）。
  if (draftTimer) clearTimeout(draftTimer)
  saveDraft()
})

onActivated(() => {
  nextTick(() => {
    void syncEditorMode()
  })
})

onDeactivated(() => {
})

watch(selectedCategoryId, async (newVal) => {
  if (typeof newVal === 'string' && newVal.trim()) {
    try {
      const res = await addNoteCategory({ name: newVal.trim(), userId: userStore.id })
      if (res.code === 200 && res.data) {
        selectedCategoryId.value = res.data.id || res.data
        await loadCategories()
      }
    } catch (error) {
      ElMessage.error('创建分类失败')
      selectedCategoryId.value = null
    }
  }
})

watch(() => route.query.id, () => {
  void syncEditorMode()
})

let draftTimer = null
watch([noteTitle, editorHtmlContent, isPublic, selectedCategoryId, selectedTags], () => {
  if (draftTimer) clearTimeout(draftTimer)
  draftTimer = setTimeout(() => {
    saveDraft()
  }, 500)
}, { deep: true })

const handleGlobalKeydown = (event) => {
  if (event.ctrlKey && event.key === 's') {
    event.preventDefault()
    handleSave()
  }
}

const copyNote = () => {
  const content = markdownContent.value || ''
  navigator.clipboard.writeText(content).then(() => {
    ElMessage.success('复制成功')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

const handleSave = async () => {
  if (!noteTitle.value.trim()) {
    ElMessage.warning('请输入笔记标题')
    titleInputRef.value?.focus?.()
    flagMissing('title')
    return
  }

  const md = editorHtmlContent.value ? turndownService.turndown(editorHtmlContent.value) : ''
  if (!md.trim()) {
    ElMessage.warning('请输入笔记内容')
    return
  }

  const userId = userStore.id
  if (!userId) {
    ElMessage.error('请重新登录')
    return
  }

  saving.value = true
  try {
    const noteData = {
      title: noteTitle.value.trim(),
      markdownContent: md,
      isPublic: isPublic.value,
      userId: userId,
      categoryId: selectedCategoryId.value || null,
      tags: selectedTags.value.join(','),
      publicSectionId: selectedPublicSectionId.value || null
    }

    if (editingNoteId.value) {
      await updateNote({ id: editingNoteId.value, ...noteData })
      ElMessage.success('保存成功')
      if (editingNoteId.value && selectedBankIds.value.length > 0) {
        await saveNoteQuestionBanks(editingNoteId.value)
      }
    } else {
      ElMessage.warning('请先发布笔记')
    }
    // ⚠️ 这里**不再** clearDraft()：本函数是「编辑已有笔记」专用保存路径（else 只提示
    //    "请先发布笔记"）。编辑已有笔记与「写笔记」的草稿是两回事，不该顺手清掉用户
    //    在「写笔记」攒的草稿（用户 2026-10-11 要求排查的"编辑会不会覆盖/清掉草稿"）。
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  } finally {
    saving.value = false
  }
}

const handlePublish = async () => {
  if (!noteTitle.value.trim()) {
    ElMessage.warning('请输入笔记标题')
    titleInputRef.value?.focus?.()
    flagMissing('title')
    return
  }

  const md = editorHtmlContent.value ? turndownService.turndown(editorHtmlContent.value) : ''
  if (!md.trim()) {
    ElMessage.warning('请输入笔记内容')
    return
  }
  if (!selectedCategoryId.value) {
    ElMessage.warning('请选择一个笔记分类')
    flagMissing('category')
    return
  }
  if (isPublic.value === 1 && !selectedPublicSectionId.value) {
    ElMessage.warning('公开笔记请选择一个公开分区')
    flagMissing('section')
    return
  }

  const userId = userStore.id
  if (!userId) {
    ElMessage.error('请重新登录')
    return
  }

  saving.value = true
  try {
    const noteData = {
      title: noteTitle.value.trim(),
      markdownContent: md,
      isPublic: isPublic.value,
      userId: userId,
      categoryId: selectedCategoryId.value || null,
      tags: selectedTags.value.join(','),
      publicSectionId: selectedPublicSectionId.value || null
    }

    let savedNoteId = editingNoteId.value
    const isNewNote = !editingNoteId.value

    if (editingNoteId.value) {
      await updateNote({ id: editingNoteId.value, ...noteData })
      ElMessage.success('保存成功')
    } else {
      const addRes = await addNote(noteData)
      if (addRes.code === 200 && addRes.data) {
        savedNoteId = typeof addRes.data === 'object' ? addRes.data.id : addRes.data
      }
      ElMessage.success('发布成功')
    }

    if (savedNoteId && selectedBankIds.value.length > 0) {
      await saveNoteQuestionBanks(savedNoteId)
    }

    // ⚠️ 只有「发布新笔记」成功才清草稿：草稿只属于「尚未发布的新笔记」。若用户是在
    //    「编辑已有笔记」，ta 之前攒的「写笔记」草稿不该被这次编辑保存顺手清掉。
    if (isNewNote) clearDraft()
    editingNoteId.value = null

    /*
     * 发布后去哪儿（2026-10-22 修）
     * ----------------------------
     * 原来无论新建还是编辑，一律 `router.push('/front/notes/list')` ——
     * 用户刚写完一篇笔记，被丢回列表，还得自己在一堆笔记里找刚才那篇。
     * 而这时 `savedNoteId` 其实**已经拿到了**，只是没用。
     *
     * 现在：新发布的先进**这篇笔记的详情页**（能看到成品长什么样、确认发布效果），
     * 编辑已有笔记则回它自己的详情页。只有拿不到 id 时才退回列表兜底。
     */
    if (savedNoteId) {
      // lastVisited 只记「回来时落在哪个子路由」，详情页要 id、不能当持久落点，
      // 所以缓存仍记 list；本次直接跳详情即可。
      cacheStore.setLastVisited('notes', 'list')
      /*
       * `published=1`：告诉详情页「这是刚发布成功的」，由它显示一条成功提示条。
       * 为什么不用 ElMessage 就够了：发布成功时人已经被跳到新页面，
       * 一条 3 秒就消失的 toast 很容易被忽略；而"我到底发出去没有"是用户此刻
       * 最想知道的事，值得在页面上留一个明确的落脚点。
       * 只在**新发布**时带这个参数，编辑已有笔记走 else 分支不带。
       */
      router.push(
        isNewNote
          ? `/front/notes/detail/${savedNoteId}?published=1`
          : `/front/notes/detail/${savedNoteId}`
      )
    } else {
      cacheStore.setLastVisited('notes', 'list')
      router.push('/front/notes/list')
    }
  } catch (error) {
    ElMessage.error(editingNoteId.value ? '保存失败' : '发布失败')
    console.error(error)
  } finally {
    saving.value = false
  }
}
</script>

<style lang="scss">
.notes-editor-container {
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;

  .header {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 12px;
    padding: 12px 24px;
    flex-shrink: 0;

    // 允许两侧 1fr 列收缩，避免被按钮最小内容宽度撑破、挤偏居中标题
    > * {
      min-width: 0;
    }
  }

  .header-left {
    justify-self: start;
  }

  .back-btn {
    width: fit-content;
    border-radius: 8px;
    font-weight: 500;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover {
      color: #4b5563;
      background: #f3f4f6;
    }
  }

  .header-title {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: #1f2937;
    text-align: center;
    max-width: min(280px, 34vw);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    justify-self: center;
  }

  .header-right {
    justify-self: end;
    display: flex;
    gap: 8px;
    align-items: center;

    .header-settings-btn {
      border-radius: 8px;
      font-weight: 500;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      cursor: pointer;
      font-size: 14px;
      line-height: 1;

      &:hover {
        background: #fff;
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-2px);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      }

      &:active {
        transform: translateY(0);
      }
    }

    .header-publish-btn {
      border-radius: 8px;
      font-weight: 600;
      padding-left: 18px;
      padding-right: 18px;
    }
  }

  .editor-body {
    flex: 1;
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 0 24px 16px;
  }

  .editor-main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
    /*
     * ⚠️ 必须自己滚（用户 2026-10-18：「写笔记页面无法滚动，页面好像被限制死了，
     *    我目前在草稿那边无法进行任何操作，滚动条没有出现」）。
     *
     * 原因：顶层 `.notes-editor-container` 是 `height:100%` + flex 列，
     * 而这一层只有 `flex:1 / min-height:0`，**没有任何 overflow 约束** ——
     * 内容超过视口就被上层裁掉，外层又不会滚 → 整页卡死、连滚动条都不出现。
     *
     * 修法：让这一层成为滚动容器，高度仍由 flex 分配，不撑破外壳。
     */
    overflow-y: auto;
    overscroll-behavior: contain;

    /*
     * ⚠️ Tiptap 组件自带 `height:100% + min-height:500px + overflow:hidden`，
     *    内部 `.editor-content` 又是 `overflow-y:auto` —— 它是一个**自带滚动的盒子**。
     *    放在编辑页里会和外层 `.editor-main` 形成两层滚动：外层因为内层不撑高
     *    而永远算不出溢出（可滚量 0），内层又只给出 500px 的窗口，
     *    用户看到的就是「页面滚不动、内容还被切掉」（用户 2026-10-19 报的 bug3）。
     *
     *    修法：编辑页里让 Tiptap **自然增高**（height:auto / min-height:0 /
     *    overflow:visible），滚动统一交给 `.editor-main` 一层。
     *    `.editor-content` 同理，否则内容仍被它裁在内部。
     */
    .tiptap-editor {
      flex: none;
      height: auto;
      min-height: 0;
      overflow: visible;

      .editor-content {
        flex: none;
        overflow: visible;
      }
    }
  }

  /* —— 标题 + 高频元信息卡片 —— */
  .note-meta-card {
    flex-shrink: 0;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 20px 12px;
  }
  /* 标题行：标题 + 右侧图标动作（复制全文 / 导出 MD） */
  .meta-title-row {
    display: flex;
    align-items: center;
    gap: 10px;

    .note-title-input {
      flex: 1;
      min-width: 0;
    }
  }

  .title-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  /* 图标按钮：圆形、无边框，弱化存在感但悬停可辨 ——
     这两个是低频动作，不该和「笔记设置 / 保存」抢注意力 */
  .icon-action-btn {
    width: 30px;
    height: 30px;
    border: 1px solid #e5e7eb;
    background: #fff;
    color: #9ca3af;
    transition: all 0.2s ease;

    &:hover {
      color: #4b5563;
      border-color: #d1d5db;
      background: #f9fafb;
    }

    &:active {
      transform: scale(0.96);
    }
  }


  .note-title-input {
    .el-input__wrapper {
      padding: 2px 0;
      background: transparent;
      box-shadow: none !important;

      &:hover {
        box-shadow: none !important;
      }

      .el-input__inner {
        font-size: 22px;
        font-weight: 700;
        color: #111827;
        height: 36px;
        line-height: 36px;
      }
    }

    &.is-missing .el-input__wrapper {
      box-shadow: 0 0 0 1px #f56c6c !important;
      border-radius: 8px;
      padding-left: 10px;
      padding-right: 10px;
      animation: field-shake 0.32s ease;
    }
  }

  .meta-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
    padding-top: 12px;
    border-top: 1px solid #f3f4f6;
  }

  .meta-field {
    min-width: 0;

    .meta-select {
      width: 172px;
    }
  }

  .meta-tags-field {
    flex: 1 1 200px;
    min-width: 180px;

    .meta-select {
      width: 100%;
    }
  }

  /* 公开 / 私有 分段开关 */
  .visibility-segment {
    flex-shrink: 0;

    .el-radio-button__inner {
      border-radius: 0;
      font-weight: 500;
      padding: 7px 16px;
    }

    .el-radio-button:first-child .el-radio-button__inner {
      border-top-left-radius: 8px;
      border-bottom-left-radius: 8px;
    }

    .el-radio-button:last-child .el-radio-button__inner {
      border-top-right-radius: 8px;
      border-bottom-right-radius: 8px;
    }
  }

  /* 校验缺失：红框 + 轻微抖动 */
  .meta-field.is-missing {
    .el-select__wrapper {
      box-shadow: 0 0 0 1px #f56c6c !important;
      animation: field-shake 0.32s ease;
    }
  }

  /* 公开分区展开/收起过渡 */
  .section-fade-enter-active,
  .section-fade-leave-active {
    transition: all 0.2s ease;
  }

  .section-fade-enter-from,
  .section-fade-leave-to {
    opacity: 0;
    transform: translateX(-6px);
  }
}

@keyframes field-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-3px); }
  75% { transform: translateX(3px); }
}

/* —— 笔记设置抽屉（el-drawer teleport 到 body，样式写在容器外） —— */
.note-settings-drawer {
  .el-drawer__header {
    margin-bottom: 0;
    padding: 16px 20px;
    border-bottom: 1px solid #f3f4f6;
    color: #1f2937;
    font-weight: 600;
  }

  .el-drawer__body {
    padding: 0;
  }

  .drawer-body {
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 20px;
  }

  .drawer-section {
    display: flex;
    flex-direction: column;
  }

  .drawer-label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }

  .drawer-select {
    width: 100%;
  }

  .selected-banks-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;

    .el-tag {
      border-radius: 6px;
      background: #f3f4f6;
      border-color: #e5e7eb;
      color: #4b5563;
    }
  }

  .drawer-tip {
    font-size: 12px;
    line-height: 1.7;
    color: #9ca3af;
    background: #f9fafb;
    border-radius: 8px;
    padding: 10px 12px;
  }
}

@media (max-width: 768px) {
  .notes-editor-container {
    .header {
      padding: 10px 12px;
    }

    .header-right {
      gap: 6px;
    }

    .editor-body {
      padding: 0 12px 12px;
    }

    .meta-field .meta-select {
      width: 100%;
    }

    .meta-field {
      flex: 1 1 100%;
    }

    .visibility-segment {
      flex: 1 1 auto;
    }
  }
}
</style>
