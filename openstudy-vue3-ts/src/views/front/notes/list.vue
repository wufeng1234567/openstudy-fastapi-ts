<!-- ==================== 学习分享页面（公开笔记列表） ==================== -->
<!-- 功能：展示所有用户公开的笔记，支持搜索、筛选、排序 -->
<!-- 访问路径：/front/notes/list -->
<template>
  <div ref="pageRef" class="notes-list-container">
    <!--
      标题行已并入顶栏（用户 2026-10-19）
      ==========================================================================
      原来内容区第一行是「公开笔记 / 来自所有人的学习笔记与经验沉淀」，
      右边是「刷新 / 写笔记」。现在：
        · 顶栏变成 `学习分享 · 公开笔记`（见 layout/front.vue）；
        · 副标题 + 条数并进顶栏那一行（`N 篇笔记`，由 topbar store 推送）；
        · 「刷新 / 写笔记」下移，和搜索框同一行（用户要求「移动到搜索框的右边」）。

      所以这里不再有 header 区块，第一行直接是搜索行。
    -->

    <div class="content-layout">
      <div class="left-column">
        <!--
          ==================== 搜索行 ====================
          一行三件：搜索框（内含「筛选」入口）+ 排序下拉 + 刷新 / 写笔记。
          搜索框复用全站统一组件 `SearchFilterInput`，与「题库管理 / 题目管理 /
          笔记管理」完全一致；排序下拉改为同一行的次级控件。
        -->
        <div ref="searchAreaRef" class="search-bar">
          <SearchFilterInput v-model="searchKeyword" placeholder="搜索笔记..." class="search-input"
            :filter-open="filterOpen" :filter-active="filterActive" @input="handleSearchInput"
            @enter="handleSearchEnter" @clear="handleSearchClear" @toggle-filter="toggleFilterSidebar"
            @focus="handleFocus" @blur="handleBlur">
            <!-- 搜索历史：挂在搜索框正下方（样式沿用原来的下拉面板） -->
            <template #dropdown>
              <div v-show="showSearchHistory && searchHistory.length > 0" class="search-history-dropdown"
                @mousedown.prevent>
                <div class="history-header">
                  <span class="history-title">搜索历史</span>
                  <span class="clear-history" @click="clearHistory">清空</span>
                </div>
                <div class="history-tags">
                  <div v-for="(keyword, index) in searchHistory" :key="index" class="history-tag-item"
                    @click="selectHistory(keyword)">
                    <span class="tag-text">{{ keyword }}</span>
                    <span class="tag-close" @click.stop="removeHistory(keyword)">
                      <el-icon><Close /></el-icon>
                    </span>
                  </div>
                </div>
              </div>
            </template>
          </SearchFilterInput>

          <el-button class="refresh-btn" :icon="Refresh" @click="fetchNotes">刷新</el-button>
          <el-button class="create-btn" type="primary" @click="goEditor()">写笔记</el-button>
        </div>

        <!--
          筛选下拉面板：与「题库管理 / 题目管理 / 笔记管理」同一套组件与交互
          ==========================================================================
          用户 2026-10-19：「搜索框那边的下拉框进行功能重构…改造成一个筛选组件，
          这个组件题库管理和题目管理的输入框里面都有一个复用的筛选组件，把它复用进去」。

          原来这里是一整块常驻的 chips 面板（分区 / 时间 / 标签三行永远占着高度），
          现在收进搜索框内的「筛选」按钮里，点开才出现 —— 内容区少 3 行。
          原来的「展开更多 / 收起」单行折叠逻辑也就不需要了（面板本身是可滚动的）。
        -->
        <CommonFilterSidebar ref="filterSidebarRef" title="笔记筛选" hide-trigger :filter-groups="filterGroups"
          :filter-form="filterForm" :default-filter="defaultFilter" :default-collapsed="true"
          :style="{ '--filter-top': filterTop + 'px', '--filter-left': filterLeft + 'px' }"
          @filter-change="handleFilterChange" @reset-filters="handleResetFilters"
          @collapse-change="handleFilterCollapseChange" @active-change="handleFilterActiveChange" />

        <div v-loading="loading" class="notes-list">
          <div v-for="note in notesList" :key="note.noteId" class="note-item" @click="goDetail(note.noteId)">
            <div class="note-avatar">
              <UserAvatar :size="44" :src="note.avatar" :name="note.authorName" class="user-link"
                @click.stop="goToProfile(note.userId)" />
            </div>
            <div class="note-content">
              <h3 class="note-title">{{ note.title }}</h3>
              <p class="note-summary">{{ getSummary(note.markdownContent) }}</p>
              <div class="note-meta">
                <span class="author user-link" @click.stop="goToProfile(note.userId)">{{ note.authorName || '匿名用户'
                }}</span>
                <span class="separator">·</span>
                <span class="time">{{ formatTime(note.createTime) }}</span>
                <span class="separator">·</span>
                <span class="clicks"><OsIcon name="eye" :size="13" /> {{ note.viewCount || note.clickCount || 0 }}</span>
                <span class="separator">·</span>
                <!-- 评论数含子留言：后端 `note.comment_count` 在建评论时（不分是否回复）就 +1，
                     删评论 / 删笔记时一起扣，所以这里直接用列表接口已经下发的值，不用再查一次 -->
                <span class="comments"><OsIcon name="message-circle" :size="13" /> {{ note.commentCount || 0 }}</span>
                <template v-if="note.tags">
                  <span class="separator">·</span>
                  <span class="tags">
                    <el-tag v-for="tag in getTagList(note.tags).slice(0, 3)" :key="tag" size="small"
                      class="clickable-tag" @click.stop="selectTag(tag)">{{ tag }}</el-tag>
                  </span>
                </template>
              </div>
            </div>
            <div v-if="note.userId === userStore.id" class="note-actions">
              <el-button class="edit-btn" :icon="Edit" text size="small" @click.stop="goEditor(note.noteId)">
                编辑
              </el-button>
            </div>
          </div>

          <el-empty v-if="!loading && notesList.length === 0"
            :description="searchKeyword ? '没有找到相关笔记' : '还没有人分享笔记，快来写一篇吧'" />
        </div>

        <div v-if="total > 0" class="pagination">
          <el-pagination v-model:current-page="pageNum" :page-size="pageSize" :total="total" layout="prev, pager, next"
            @current-change="handlePageChange" />
        </div>
      </div>

      <div class="right-column">
        <div class="ranking-card">
          <div class="ranking-header">
            <span class="ranking-title"><OsIcon name="flame" :size="13" /> 热榜</span>
            <div class="ranking-tabs" role="tablist">
              <button type="button" class="ranking-tab" :class="{ active: rankingPeriod === 'week' }"
                role="tab" :aria-selected="rankingPeriod === 'week'" @click="switchRanking('week')">周榜</button>
              <button type="button" class="ranking-tab" :class="{ active: rankingPeriod === 'month' }"
                role="tab" :aria-selected="rankingPeriod === 'month'" @click="switchRanking('month')">月榜</button>
              <button type="button" class="ranking-tab" :class="{ active: rankingPeriod === 'year' }"
                role="tab" :aria-selected="rankingPeriod === 'year'" @click="switchRanking('year')">年榜</button>
            </div>
          </div>
          <div class="ranking-subtitle">{{ rankingSubtitle }}</div>

          <!-- 切换加载骨架 -->
          <div v-if="rankingLoading" class="ranking-skeleton">
            <div v-for="n in 6" :key="n" class="skeleton-row">
              <span class="skeleton-rank"></span>
              <span class="skeleton-bar"></span>
              <span class="skeleton-num"></span>
            </div>
          </div>

          <!-- 加载失败重试 -->
          <div v-else-if="rankingError" class="ranking-state">
            <span class="state-text">热榜加载失败</span>
            <el-button text type="primary" size="small" @click="fetchRanking">点击重试</el-button>
          </div>

          <transition-group v-else name="rank-fade" tag="div" class="ranking-list">
            <div v-for="(item, index) in rankingList" :key="item.noteId" class="ranking-item"
              :class="{ 'top-three': index < 3 }" :title="item.title" @click="goDetail(item.noteId)">
              <div class="ranking-rank" :class="'rank-' + (index + 1)">
                <OsIcon v-if="index < 3" name="medal" :size="15" class="medal" />
                <span v-else class="rank-num">{{ index + 1 }}</span>
              </div>
              <div class="ranking-title-text">{{ item.title }}</div>
              <div class="ranking-clicks" :title="hotTip(item)">
                <OsIcon name="flame" :size="12" class="hot-flame" />{{ formatHot(itemHot(item)) }}
              </div>
            </div>
          </transition-group>

          <!-- 空态：周榜为空时引导去月榜 -->
          <div v-if="!rankingLoading && !rankingError && rankingList.length === 0" class="ranking-state">
            <div class="state-empty-icon"><OsIcon name="inbox" :size="26" /></div>
            <div class="state-text">{{ rankingPeriodMeta[rankingPeriod].empty }}</div>
            <el-button v-if="rankingPeriod === 'week'" text type="primary" size="small"
              @click="switchRanking('month')">去看看月榜 →</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontNotesList' })
import { ref, computed, watch, onMounted, onActivated, onBeforeUnmount, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Edit, Refresh, Close } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import useTopbarStore from '@/store/modules/topbar'
import { listPublicNotes, getRanking, getPublicNoteTags } from '@/api/notes/public'
import { getPublicSections } from '@/api/notes/publicSection'
import UserAvatar from '@/components/UserAvatar/index.vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import useUserStore from '@/store/modules/user'
import { ensureLogin } from '@/utils/loginGuard'

import defAva from '@/assets/images/profile.jpg'
const cacheStore = useFrontPageCacheStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const topbarStore = useTopbarStore()

const loading = ref(false)
const notesList = ref([])
const searchKeyword = ref('')
const pageNum = ref(1)
const pageSize = ref(10)
const total = ref(0)

const publicSectionList = ref([])

/*
 * ==================== 筛选状态 ====================
 * 用户 2026-10-19：「搜索框那边的下拉框进行功能重构，改造成一个筛选组件，
 * 这个组件题库管理和题目管理的输入框里面都有一个复用的筛选组件，把它复用进去」。
 *
 * 所以原来三行常驻的 chips（分区 / 时间 / 标签）+ 搜索框右侧的排序下拉，
 * 全部收进 `CommonFilterSidebar` 这一个面板：
 *   · 排序   —— radio（最新发布 / 最早发布 / 内容最长 / 最多浏览）
 *   · 分区   —— checkbox（来自后端公开分区）
 *   · 时间   —— checkbox 快捷区间（今天 / 近 7 天 / 近 30 天）
 *   · 自定义日期 —— dateRange（与快捷区间互斥）
 *   · 标签   —— checkbox（来自后端热门标签）
 *
 * 状态全在 `filterForm` 一个对象里，请求参数从它派生 —— 不再散成五个 ref。
 */
const defaultFilter = {
  sortBy: 'create_time',
  sections: [] as any[],
  timeRanges: [] as string[],
  createRange: null as string[] | null,
  tags: [] as string[]
}
const filterForm = ref({
  sortBy: 'create_time',
  sections: [] as any[],
  timeRanges: [] as string[],
  createRange: null as string[] | null,
  tags: [] as string[]
})

// 筛选入口的按钮态（展开中 / 有生效条件）
const filterOpen = ref(false)
const filterActive = ref(false)
const filterSidebarRef = ref<any>(null)
// 筛选面板定位：靠它贴到搜索框正下方 + 对齐搜索框左缘
const searchAreaRef = ref(null)
const pageRef = ref(null)
const filterTop = ref(0)
const filterLeft = ref(0)

const rankingList = ref([])
const rankingPeriod = ref('week')
// 热榜加载态 / 请求竞态序号（快速切换时只认最后一次结果）
const rankingLoading = ref(false)
const rankingError = ref(false)
let rankingReqSeq = 0
  // 各周期的中文说明，用于副标题与空态引导
  const rankingPeriodMeta = {
    week: { label: '周榜', subtitle: '近 7 天发布 · 综合热度', empty: '近 7 天还没有新笔记' },
    month: { label: '月榜', subtitle: '近 30 天发布 · 综合热度', empty: '近 30 天还没有新笔记' },
    year: { label: '年榜', subtitle: '近 365 天发布 · 综合热度', empty: '近一年还没有新笔记' }
  }
const rankingSubtitle = computed(() => rankingPeriodMeta[rankingPeriod.value]?.subtitle || '')
const showSearchHistory = ref(false)
const searchHistory = ref([])

let blurTimer = null

const handleFocus = () => {
  clearTimeout(blurTimer)
  if (searchHistory.value.length > 0) {
    showSearchHistory.value = true
  }
}

const handleBlur = () => {
  blurTimer = setTimeout(() => {
    showSearchHistory.value = false
  }, 200)
}

const HISTORY_KEY = 'search_history_notes'
const MAX_HISTORY = 10

const loadHistory = () => {
  const history = localStorage.getItem(HISTORY_KEY)
  if (history) {
    searchHistory.value = JSON.parse(history)
  }
}

const saveHistory = () => {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(searchHistory.value))
}

const addHistory = (keyword) => {
  if (!keyword || !keyword.trim()) return
  const trimmed = keyword.trim()
  const index = searchHistory.value.indexOf(trimmed)
  if (index > -1) {
    searchHistory.value.splice(index, 1)
  }
  searchHistory.value.unshift(trimmed)
  if (searchHistory.value.length > MAX_HISTORY) {
    searchHistory.value = searchHistory.value.slice(0, MAX_HISTORY)
  }
  saveHistory()
}

const removeHistory = (keyword) => {
  const index = searchHistory.value.indexOf(keyword)
  if (index > -1) {
    searchHistory.value.splice(index, 1)
    saveHistory()
  }
}

const clearHistory = () => {
  searchHistory.value = []
  localStorage.removeItem(HISTORY_KEY)
  showSearchHistory.value = false
}

const selectHistory = (keyword) => {
  searchKeyword.value = keyword
  showSearchHistory.value = false
  pageNum.value = 1
  fetchNotes()
}

const baseUrl = import.meta.env.VITE_APP_BASE_API || ''

const getAvatarUrl = (avatar) => {
  if (!avatar) return defAva
  if (avatar.startsWith('http')) return avatar
  return baseUrl + avatar
}

const getSummary = (content) => {
  if (!content) return ''
  let plainText = content

  plainText = plainText.replace(/!\[([^\]]*)\]\([^)]+\)/g, '')

  const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g
  plainText = plainText.replace(codeBlockRegex, (match, lang, code) => {
    return code.trim()
  })

  plainText = plainText.replace(/`{1,3}[^`\n]*?`{1,3}/g, '')

  plainText = plainText
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/>/g, '')
    .replace(/-/g, '')
    .replace(/\n/g, ' ')
    .trim()
  if (plainText.length > 200) {
    return plainText.substring(0, 200) + '...'
  }
  return plainText
}

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatTags = (tags) => {
  if (!tags) return ''
  if (typeof tags === 'string') {
    return tags.split(',').slice(0, 3).join('、')
  }
  return tags.slice(0, 3).join('、')
}

const getTagList = (tags) => {
  if (!tags) return []
  if (typeof tags === 'string') {
    return tags.split(',').filter(t => t.trim())
  }
  return tags
}

// 热门标签：来自后端聚合（不是当前页数据，避免筛选后标签乱跳）
const hotTags = ref([])
const fetchHotTags = async () => {
  try {
    const res = await getPublicNoteTags(20)
    hotTags.value = (res.data || []).map(item => item.tag).filter(Boolean)
  } catch (error) {
    console.error('获取热门标签失败:', error)
    hotTags.value = []
  }
}

/*
 * ==================== 筛选面板配置 ====================
 * 分区 / 标签的候选项是后端下发的，所以这里是 computed —— 数据回来会自己更新。
 * 组内多选 OR、组间 AND（与「题库管理 / 题目管理」完全一致的语义）。
 */
const filterGroups = computed(() => {
  const groups: any[] = [
    {
      key: 'sortBy',
      label: '排序',
      type: 'radio',
      options: [
        { value: 'create_time', label: '最新发布' },
        { value: 'create_time_asc', label: '最早发布' },
        { value: 'content_length', label: '内容最长' },
        { value: 'click_count', label: '最多浏览' }
      ]
    }
  ]

  // 分区：后端公开分区（没有分区时不渲染这一组，避免空面板）
  if (publicSectionList.value.length > 0) {
    groups.push({
      key: 'sections',
      label: '分区',
      type: 'checkbox',
      options: publicSectionList.value.map((s: any) => ({ value: s.id, label: s.name }))
    })
  }

  groups.push({
    key: 'timeRanges',
    label: '时间',
    type: 'checkbox',
    options: [
      { value: 'today', label: '今天' },
      { value: '7d', label: '近 7 天' },
      { value: '30d', label: '近 30 天' }
    ]
  })

  // 自定义日期：精确区间（选了就覆盖快捷区间，由 handleFilterChange 处理互斥）
  groups.push({ key: 'createRange', label: '自定义日期', type: 'dateRange' })

  // 标签：后端热门标签
  if (hotTags.value.length > 0) {
    groups.push({
      key: 'tags',
      label: '标签',
      type: 'checkbox',
      options: hotTags.value.map((t: string) => ({ value: t, label: t }))
    })
  }

  return groups
})

/*
 * 排序 → 后端参数
 * `create_time_asc` 是前端的一个选项值，后端只认 (sortBy, sortOrder) 两段。
 */
const getSortParams = () => {
  const v = filterForm.value.sortBy
  if (v === 'create_time_asc') return { sortBy: 'create_time', sortOrder: 'asc' }
  if (v === 'create_time') return { sortBy: 'create_time', sortOrder: 'desc' }
  return { sortBy: v, sortOrder: 'desc' }
}

// 自定义日期范围 → startTime / endTime
const getFilterTime = () => {
  const r = filterForm.value.createRange
  if (r && r.length === 2) {
    return { startTime: r[0] + ' 00:00:00', endTime: r[1] + ' 23:59:59' }
  }
  return {}
}

const fetchNotes = async () => {
  loading.value = true
  try {
    const sortParams = getSortParams()
    const timeParams = getFilterTime()
    const f = filterForm.value
    const res = await listPublicNotes({
      pageNum: pageNum.value,
      pageSize: pageSize.value,
      keyword: searchKeyword.value || undefined,
      // 多选：逗号分隔传给后端（组内 OR）
      tags: f.tags.length ? f.tags.join(',') : undefined,
      publicSectionIds: f.sections.length ? f.sections.join(',') : undefined,
      timeRanges: f.timeRanges.length ? f.timeRanges.join(',') : undefined,
      ...sortParams,
      ...timeParams
    })
    notesList.value = res.rows || []
    total.value = res.total || 0
    loaded.value = true
  } catch (error) {
    ElMessage.error('获取笔记列表失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const fetchRanking = async () => {
  // 竞态保护：记录本次请求序号，返回时若已被更新的请求取代则丢弃
  const seq = ++rankingReqSeq
  rankingLoading.value = true
  rankingError.value = false
  try {
    const res = await getRanking(rankingPeriod.value)
    if (seq !== rankingReqSeq) return
    rankingList.value = res.data || []
  } catch (error) {
    if (seq !== rankingReqSeq) return
    console.error('获取热榜失败:', error)
    rankingError.value = true
    rankingList.value = []
  } finally {
    if (seq === rankingReqSeq) rankingLoading.value = false
  }
}

// 切换今日 / 周榜：点已选中的不重复请求
const switchRanking = (period) => {
  if (period === rankingPeriod.value && !rankingError.value) return
  rankingPeriod.value = period
  fetchRanking()
}

// 热度数字格式化：过万显示 x.xw
const formatHot = (n) => {
  const v = Number(n) || 0
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  return String(v)
}

// 单条热榜的展示热度：优先用后端综合热度，回退浏览量
const itemHot = (item) => Number(item.hotScore ?? item.viewCount ?? item.clickCount ?? 0) || 0

// 悬浮提示：展示热度构成
const hotTip = (item) =>
  `浏览 ${item.viewCount || 0} · 点赞 ${item.likeCount || 0} · 评论 ${item.commentCount || 0}`

/* ---------- 搜索框（复用 SearchFilterInput 后，输入 / 回车 / 清空是三个事件） ---------- */
let searchTimer = null

const runSearch = () => {
  clearTimeout(searchTimer)
  if (searchKeyword.value && searchKeyword.value.trim()) {
    addHistory(searchKeyword.value)
  }
  showSearchHistory.value = false
  pageNum.value = 1
  fetchNotes()
}

/** 边打字边搜（300ms 防抖） */
const handleSearchInput = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(runSearch, 300)
}

/** 回车立即搜，不等防抖 */
const handleSearchEnter = () => {
  clearTimeout(searchTimer)
  runSearch()
}

/** 清空：立即回到全量 */
const handleSearchClear = () => {
  clearTimeout(searchTimer)
  searchKeyword.value = ''
  pageNum.value = 1
  fetchNotes()
}

const handlePageChange = (page) => {
  pageNum.value = page
  fetchNotes()
}

/* ---------- 筛选面板 → 请求 ---------- */
const handleFilterChange = (newFilter: any) => {
  /*
   * 时间互斥：选了自定义日期就清掉快捷区间，反之亦然。
   * 只在前端归一化，避免用户同时开了两组条件却以为只有一组生效。
   */
  const next = { ...newFilter }
  if (next.createRange && next.createRange.length === 2) {
    next.timeRanges = []
  } else {
    next.createRange = null
  }
  filterForm.value = next
  pageNum.value = 1
  fetchNotes()
}

/*「清空筛选」：组件紧接着会再 emit 一次 filter-change，这里只重置本地状态，
  请求交给 handleFilterChange 统一发，避免一次点击打两次接口 */
const handleResetFilters = () => {
  filterForm.value = {
    sortBy: 'create_time',
    sections: [],
    timeRanges: [],
    createRange: null,
    tags: []
  }
}

/** 点搜索框里的「筛选」：切换面板展开/收起 */
const toggleFilterSidebar = () => {
  filterSidebarRef.value?.toggleCollapse?.()
}

/** 面板展开态同步到按钮（事件值 = 是否已收起） */
const handleFilterCollapseChange = (collapsed: boolean) => {
  filterOpen.value = !collapsed
}

/** 是否已有生效条件（按钮小圆点） */
const handleFilterActiveChange = (active: boolean) => {
  filterActive.value = !!active
}

/** 点标签直接参与筛选（笔记卡片上的标签仍可点，等同在面板里勾选它） */
const selectTag = (tag) => {
  if (tag === '') {
    filterForm.value.tags = []
  } else {
    const arr = filterForm.value.tags
    const idx = arr.indexOf(tag)
    if (idx >= 0) arr.splice(idx, 1)
    else arr.push(tag)
  }
  pageNum.value = 1
  fetchNotes()
}

const fetchPublicSections = async () => {
  try {
    const res = await getPublicSections()
    if (res.code === 200) {
      publicSectionList.value = res.data || []
    }
  } catch (error) {
    console.error('获取公开分区失败:', error)
  }
}

const goDetail = (id) => {
  cacheStore.setLastVisited('notes', `detail/${id}`)
  router.push(`/front/notes/detail/${id}`)
}

const goToProfile = (userId) => {
  if (!userId) return
  router.push(`/front/profile/${userId}`)
}

const goEditor = async (id) => {
  if (!(await ensureLogin('写笔记'))) return
  cacheStore.setLastVisited('notes', 'editor')
  if (id) {
    router.push(`/front/notes/editor?id=${id}`)
  } else {
    router.push('/front/notes/editor')
  }
}

/* ---------- 顶栏计数 ----------
 * 「公开笔记 来自所有人的学习笔记与经验沉淀 + N 篇笔记」原来在内容区，
 * 现在标题并进顶栏（`学习分享 · 公开笔记`），计数也一并推过去。
 * 搜索 / 筛选后 total 会变，所以 watch 这个值而不是只推一次。
 *
 * `loaded` 用来区分「还没请求」和「请求回来是 0 条」：
 * 前者不显示（否则首屏会闪一下 0），后者要显示「0 篇笔记」——
 * 筛出 0 条时顶栏空白会让人以为计数丢了。
 */
const loaded = ref(false)
watch(
  () => total.value,
  (n) => {
    if (!route.path.startsWith('/front/notes/list')) return
    if (!loaded.value && !n) return
    topbarStore.setCount(`${n} 篇笔记`)
  },
  { immediate: true }
)

/* 搜索区高度变化 → 筛选面板跟着挪（窗口缩放也要重算） */
const updateSearchAreaHeight = () => {
  nextTick(() => {
    const page = pageRef.value
    const area = searchAreaRef.value
    if (!page || !area) return
    /*
     * 面板是 `position:absolute`，定位基准是最近的定位祖先（这里是 `.notes-list-container`）。
     * 所以要用**相对容器的偏移**，不能用 offsetHeight ——
     * 搜索行上面还有一行留白（容器 padding-top 22px），
     * 直接用 offsetHeight 会让面板盖住搜索框下半截（首版就是这样，实测错位 18px）。
     */
    const pageRect = page.getBoundingClientRect()
    const areaRect = area.getBoundingClientRect()
    filterTop.value = areaRect.bottom - pageRect.top + 8
    filterLeft.value = areaRect.left - pageRect.left
  })
}

onMounted(async () => {
  loadHistory()
  await Promise.all([fetchPublicSections(), fetchHotTags()])
  await nextTick()
  updateSearchAreaHeight()
  window.addEventListener('resize', updateSearchAreaHeight)
  fetchNotes()
  fetchRanking()
})

onActivated(() => {
  fetchRanking()
  nextTick(updateSearchAreaHeight)
  // 回到本页时重推计数（设置抽屉等场景会把顶栏清掉再回来）
  if (loaded.value) topbarStore.setCount(`${total.value} 篇笔记`)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateSearchAreaHeight)
})

// keep-alive 页面：离开时必须清，否则会把计数带到笔记详情 / 编辑器
onUnmounted(() => topbarStore.clear())
</script>

<style lang="scss">
.notes-list-container {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 22px 28px 48px;
  box-sizing: border-box;
  /* 筛选面板（position:absolute）的定位参考 */
  position: relative;

  /*
   * ==================== 搜索行 ====================
   * 一行：搜索框（内含「筛选」入口）+ 刷新 + 写笔记。
   * 搜索框 flex:1 吃掉剩余宽度，两个按钮定宽靠右。
   */
  .search-bar {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;

    .search-input {
      flex: 1;
      min-width: 0;
    }

    .refresh-btn {
      flex: none;
      border-radius: var(--os-radius-sm);
      font-weight: 500;
      padding: 8px 14px;
      height: auto;
      min-height: 32px;
      background: #fff;
      border: 1px solid var(--os-border);
      color: var(--os-text-2);
      transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;

      &:hover {
        background: var(--dsw-static-neutral-bluish-50);
        border-color: var(--os-border-strong);
        color: var(--os-text);
        transform: none;
      }

      &:active {
        transform: none;
      }
    }

    .create-btn {
      flex: none;
      border-radius: var(--os-radius-sm);
      font-weight: 500;
      padding: 8px 16px;
      height: auto;
      min-height: 32px;
      letter-spacing: 0.01em;

      &:hover,
      &:active {
        transform: none;
      }
    }

    /* 搜索历史：挂在搜索框正下方（SearchFilterInput 的 #dropdown 插槽） */
    .search-history-dropdown {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      width: 400px;
      max-width: 100%;
      padding: 14px 16px;
      background: #fff;
      border: 1px solid var(--os-border-soft);
      border-radius: var(--os-radius);
      box-shadow: var(--os-shadow-2, 0 8px 24px rgba(0, 0, 0, 0.08));
      z-index: 100;

      .history-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;

        .history-title {
          font-size: 13px;
          font-weight: 600;
          color: var(--os-text);
        }

        .clear-history {
          font-size: 12px;
          color: var(--os-text-4);
          cursor: pointer;
          transition: color 0.2s;

          &:hover {
            color: var(--os-text-2);
          }
        }
      }

      .history-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;

        .history-tag-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 10px;
          background: var(--os-bg-hover, #f3f4f6);
          border: 1px solid var(--os-border-soft);
          border-radius: var(--os-radius-sm);
          font-size: 13px;
          color: var(--os-text-3);
          cursor: pointer;
          transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;

          &:hover {
            background: var(--dsw-static-neutral-bluish-75);
            border-color: var(--os-border);
            color: var(--os-text-2);
          }

          .tag-text {
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .tag-close {
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--os-text-4);

            &:hover {
              color: var(--os-text-2);
            }

            .el-icon {
              font-size: 12px;
            }
          }
        }
      }
    }
  }

  .notes-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .pagination {
    display: flex;
    justify-content: center;
    margin-top: 24px;

    .el-pager li {
      border-radius: 6px;

      &.is-active {
        background: #f3f4f6;
        color: #1f2937;
      }
    }
  }
}

/* ==================== 双栏布局 ====================
 * 左：搜索行 + 笔记列表 + 分页；右：热榜卡片。
 * 这两条规则原先被误删过（页面会变成上下堆叠），所以放在根容器里显式声明。
 */
.notes-list-container .content-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.notes-list-container .left-column {
  flex: 1;
  min-width: 0;
}

.notes-list-container .right-column {
  width: 280px;
  flex-shrink: 0;
}

.right-column {
  width: 280px;
  flex-shrink: 0;
}

.note-item {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    border-color: #d1d5db;
  }

  .note-avatar {
    flex-shrink: 0;
  }

  .note-content {
    flex: 1;
    min-width: 0;

    .note-title {
      margin: 0 0 6px 0;
      font-size: 16px;
      font-weight: 600;
      color: #1f2937;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .note-summary {
      margin: 0 0 10px 0;
      font-size: 13px;
      color: #6b7280;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .note-meta {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #9ca3af;

      .separator {
        color: #d1d5db;
      }

      .tags {
        color: #947a4a;

        .clickable-tag {
          cursor: pointer;
          border-radius: 4px;
          padding: 0 6px;
          height: 20px;
          line-height: 20px;
          font-size: 11px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          background: #fefce8;
          border-color: #e5e0c0;
          color: #947a4a;
          margin: 0 2px;

          &:hover {
            background: #fef3c7;
            border-color: #d4c89a;
            color: #7a6239;
          }
        }
      }
    }
  }

  .note-actions {
    display: flex;
    align-items: center;
    flex-shrink: 0;
    margin-left: 12px;

    .edit-btn {
      border-radius: 8px;
      font-weight: 500;
      padding: 6px 14px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        background: #fff;
        border-color: #409eff;
        color: #409eff;
        transform: translateY(-2px);
      }

      &:active {
        transform: translateY(0);
      }
    }
  }
}

.ranking-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 18px 18px 14px;
  position: sticky;
  top: 24px;

  .ranking-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .ranking-title {
    font-size: 16px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: 0.3px;
  }

  /* —— 今日 / 周榜 分段胶囊 —— */
  .ranking-tabs {
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    background: #f3f4f6;
    border-radius: 9px;

    .ranking-tab {
      appearance: none;
      border: none;
      outline: none;
      cursor: pointer;
      padding: 4px 14px;
      border-radius: 7px;
      font-size: 12px;
      line-height: 1.4;
      color: #6b7280;
      background: transparent;
      font-weight: 500;
      transition: color 0.22s ease, background 0.22s ease, box-shadow 0.22s ease;

      &:hover {
        color: #374151;
      }

      &:focus-visible {
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.35);
      }

      &.active {
        background: #fff;
        color: #2563eb;
        font-weight: 600;
        box-shadow: 0 1px 3px rgba(17, 24, 39, 0.12);
      }
    }
  }

  .ranking-subtitle {
    margin-top: 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid #f3f4f6;
    font-size: 11px;
    color: #9ca3af;
    letter-spacing: 0.2px;
  }

  .ranking-list {
    margin-top: 4px;
    max-height: 460px;
    overflow-y: auto;

    .ranking-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 8px;
      margin: 2px 0;
      border-radius: 10px;
      cursor: pointer;
      transition: background 0.2s ease, transform 0.2s ease;

      &:hover {
        background: #f8fafc;
        transform: translateX(2px);

        .ranking-title-text {
          color: #2563eb;
        }
      }

      .ranking-rank {
        width: 24px;
        height: 24px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 7px;

        .medal {
          font-size: 17px;
          line-height: 1;
        }

        .rank-num {
          font-size: 12px;
          font-weight: 700;
          color: #9ca3af;
        }

        // 4 名之后的数字排名给一个浅灰底块，对齐奖牌尺寸
        &.rank-4,
        &.rank-5,
        &.rank-6,
        &.rank-7,
        &.rank-8,
        &.rank-9,
        &.rank-10 {
          background: #f3f4f6;

          .rank-num {
            color: #6b7280;
          }
        }
      }

      // 前三甲行轻微底色强调
      &.top-three {
        .ranking-title-text {
          font-weight: 600;
        }
      }

      .ranking-title-text {
        flex: 1;
        min-width: 0;
        font-size: 13px;
        font-weight: 500;
        color: #1f2937;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        transition: color 0.2s ease;
      }

      .ranking-clicks {
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        gap: 2px;
        font-size: 12px;
        font-weight: 600;
        color: #f97316;

        .hot-flame {
          font-size: 11px;
        }
      }
    }
  }

  /* —— 加载骨架 —— */
  .ranking-skeleton {
    margin-top: 8px;

    .skeleton-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 8px;
    }

    .skeleton-rank {
      width: 24px;
      height: 24px;
      border-radius: 7px;
      flex-shrink: 0;
    }

    .skeleton-bar {
      flex: 1;
      height: 12px;
      border-radius: 6px;
    }

    .skeleton-num {
      width: 34px;
      height: 12px;
      border-radius: 6px;
      flex-shrink: 0;
    }

    .skeleton-rank,
    .skeleton-bar,
    .skeleton-num {
      background: linear-gradient(90deg, #f3f4f6 25%, #e9edf2 37%, #f3f4f6 63%);
      background-size: 400% 100%;
      animation: ranking-shimmer 1.3s ease-in-out infinite;
    }
  }

  /* —— 空态 / 错误态 —— */
  .ranking-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 28px 12px;

    .state-empty-icon {
      font-size: 26px;
    }

    .state-text {
      font-size: 12px;
      color: #9ca3af;
    }
  }
}

/* 榜单切换：列表淡入 + 轻微上移 */
.rank-fade-enter-active {
  transition: all 0.3s ease;
}

.rank-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.rank-fade-leave-active {
  transition: all 0.15s ease;
}

.rank-fade-leave-to {
  opacity: 0;
}

@keyframes ranking-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.el-empty__description {
  color: #9ca3af;
}

.user-link {
  cursor: pointer;
  transition: all 0.2s ease;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid transparent;

  &:hover {
    color: #409eff;
    border-bottom: 1px dashed #409eff;
  }
}

.user-link.user-avatar {
  border-bottom: none;

  &:hover {
    transform: scale(1.08);
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
  }
}
</style>
