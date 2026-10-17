<!-- ==================== 学习分享页面（公开笔记列表） ==================== -->
<!-- 功能：展示所有用户公开的笔记，支持搜索、筛选、排序 -->
<!-- 访问路径：/front/notes/list -->
<template>
  <div class="notes-list-container">
    <!-- ==================== 页面头部 ==================== -->
    <!-- 顶栏已显示「学习分享」，这里用「公开笔记」做二级标题，避免重复 -->
    <div class="header">
      <div class="header-left">
        <h2 class="header-title">公开笔记</h2>
        <span class="header-sub">来自所有人的学习笔记与经验沉淀</span>
      </div>
      <div class="header-right">
        <el-button class="refresh-btn" :icon="Refresh" @click="fetchNotes">刷新</el-button>
        <el-button class="create-btn" type="primary" @click="goEditor()">写笔记</el-button>
      </div>
    </div>

    <div class="content-layout">
      <div class="left-column">
        <!-- ==================== 搜索区域 ==================== -->
        <!-- 支持关键词搜索，带搜索历史下拉框 -->
        <div class="search-bar">
          <div class="search-wrapper">
            <el-input ref="searchInputRef" v-model="searchKeyword" placeholder="搜索笔记..." clearable @input="handleSearch"
              @focus="handleFocus" @blur="handleBlur" class="search-input">
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <!-- 搜索历史下拉框：显示用户之前的搜索记录 -->
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
          </div>

          <!-- 排序方式：和搜索框同一行，不再混在筛选标签里 -->
          <el-select v-model="sortBy" class="sort-select" size="default" @change="handleSortChange">
            <el-option label="最新发布" value="create_time" />
            <el-option label="最早发布" value="create_time_asc" />
            <el-option label="内容最长" value="content_length" />
            <el-option label="最多浏览" value="click_count" />
          </el-select>
        </div>

        <!-- ==================== 筛选区域 ==================== -->
        <!-- 每个筛选组都带文字标签：分区 / 时间 / 标签 -->
        <div class="filter-panel">
          <!-- 分区：公开笔记所属的分区 -->
          <div class="filter-group">
            <span class="filter-label">分区</span>
            <div class="filter-content" :class="{ 'has-toggle': sectionsHasOverflow }">
              <div ref="sectionChipsRef" class="filter-chips"
                :class="{ 'is-collapsed': sectionsHasOverflow && !sectionsExpanded }">
                <button type="button" class="chip" :class="{ active: selectedPublicSectionIds.length === 0 }"
                  @click="selectSection(null)">全部</button>
                <button type="button" v-for="section in publicSectionList" :key="section.id" class="chip"
                  :class="{ active: selectedPublicSectionIds.includes(section.id) }" @click="selectSection(section.id)">
                  {{ section.name }}
                </button>
                <span v-if="publicSectionList.length === 0" class="filter-empty">暂无分区</span>
              </div>
              <button v-if="sectionsHasOverflow" type="button" class="chip-toggle"
                @click="sectionsExpanded = !sectionsExpanded">
                {{ sectionsExpanded ? '收起' : '展开' }}
                <el-icon :class="{ 'is-open': sectionsExpanded }">
                  <ArrowDown />
                </el-icon>
              </button>
            </div>
          </div>

          <!-- 时间：快捷区间 + 自定义日期 -->
          <div class="filter-group">
            <span class="filter-label">时间</span>
            <div class="filter-chips">
              <button type="button" class="chip" :class="{ active: timeRanges.length === 0 && !dateRange }"
                @click="selectTimeRange('')">全部</button>
              <button type="button" class="chip" :class="{ active: timeRanges.includes('today') }"
                @click="selectTimeRange('today')">今天</button>
              <button type="button" class="chip" :class="{ active: timeRanges.includes('7d') }"
                @click="selectTimeRange('7d')">近 7 天</button>
              <button type="button" class="chip" :class="{ active: timeRanges.includes('30d') }"
                @click="selectTimeRange('30d')">近 30 天</button>
              <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期"
                end-placeholder="结束日期" class="date-picker" size="small" value-format="YYYY-MM-DD"
                @change="handleDateChange" />
            </div>
          </div>

          <!-- 标签：公开笔记的热门标签 -->
          <div v-if="hotTags.length > 0" class="filter-group">
            <span class="filter-label">标签</span>
            <div class="filter-content" :class="{ 'has-toggle': tagsHasOverflow }">
              <div ref="tagChipsRef" class="filter-chips"
                :class="{ 'is-collapsed': tagsHasOverflow && !tagsExpanded }">
                <button type="button" class="chip" :class="{ active: selectedTags.length === 0 }"
                  @click="selectTag('')">全部</button>
                <button type="button" v-for="tag in hotTags" :key="tag" class="chip"
                  :class="{ active: selectedTags.includes(tag) }" @click="selectTag(tag)">{{ tag }}</button>
              </div>
              <button v-if="tagsHasOverflow" type="button" class="chip-toggle"
                @click="tagsExpanded = !tagsExpanded">
                {{ tagsExpanded ? '收起' : '展开' }}
                <el-icon :class="{ 'is-open': tagsExpanded }">
                  <ArrowDown />
                </el-icon>
              </button>
            </div>
          </div>
        </div>

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
import { ref, computed, onMounted, onActivated, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Edit, Refresh, Close, ArrowDown } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
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

const loading = ref(false)
const notesList = ref([])
const searchKeyword = ref('')
const pageNum = ref(1)
const pageSize = ref(10)
const total = ref(0)

const publicSectionList = ref([])
// 多选筛选：分区 / 时间 / 标签都支持多选，组内 OR、组间 AND
const selectedPublicSectionIds = ref([])
const sortBy = ref('create_time')
const sortOrder = ref('desc')
const dateRange = ref(null)
// 时间快捷区间多选：today / 7d / 30d
const timeRanges = ref([])
// 分区 / 标签：内容超过一行时，自动显示「展开更多」按钮
const sectionChipsRef = ref(null)
const tagChipsRef = ref(null)
const sectionsExpanded = ref(false)
const tagsExpanded = ref(false)
const sectionsHasOverflow = ref(false)
const tagsHasOverflow = ref(false)
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
const selectedTags = ref([])
const showSearchHistory = ref(false)
const searchHistory = ref([])
const searchInputRef = ref(null)

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
  fetchNotes()
}

let searchTimer = null

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

const getSortParams = () => {
  if (sortBy.value === 'create_time_asc') {
    return { sortBy: 'create_time', sortOrder: 'asc' }
  }
  if (sortBy.value === 'create_time') {
    return { sortBy: 'create_time', sortOrder: 'desc' }
  }
  return { sortBy: sortBy.value, sortOrder: sortOrder.value }
}

// 判断 chips 是否换行（超出第一行）——折叠时 max-height 不影响布局，仍能测出真实行数
const chipsHasMultipleRows = (el) => {
  if (!el) return false
  const chips = Array.from(el.querySelectorAll('.chip'))
  if (chips.length <= 1) return false
  const firstTop = chips[0].offsetTop
  return chips.some(chip => chip.offsetTop - firstTop > 4)
}

const measureFilterOverflow = () => {
  sectionsHasOverflow.value = chipsHasMultipleRows(sectionChipsRef.value)
  tagsHasOverflow.value = chipsHasMultipleRows(tagChipsRef.value)
}

// 自定义日期范围（快捷区间由后端按 timeRanges 计算，二者可叠加）
const getFilterTime = () => {
  if (dateRange.value && dateRange.value.length === 2) {
    return {
      startTime: dateRange.value[0] + ' 00:00:00',
      endTime: dateRange.value[1] + ' 23:59:59'
    }
  }
  return {}
}

const fetchNotes = async () => {
  loading.value = true
  try {
    const sortParams = getSortParams()
    const timeParams = getFilterTime()
    const res = await listPublicNotes({
      pageNum: pageNum.value,
      pageSize: pageSize.value,
      keyword: searchKeyword.value || undefined,
      // 多选：逗号分隔传给后端（组内 OR）
      tags: selectedTags.value.length ? selectedTags.value.join(',') : undefined,
      publicSectionIds: selectedPublicSectionIds.value.length ? selectedPublicSectionIds.value.join(',') : undefined,
      timeRanges: timeRanges.value.length ? timeRanges.value.join(',') : undefined,
      ...sortParams,
      ...timeParams
    })
    notesList.value = res.rows || []
    total.value = res.total || 0
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
const handleSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (searchKeyword.value && searchKeyword.value.trim()) {
      addHistory(searchKeyword.value)
    }
    showSearchHistory.value = false
    pageNum.value = 1
    fetchNotes()
  }, 300)
}

const handlePageChange = (page) => {
  pageNum.value = page
  fetchNotes()
}

// 分区多选：id === null 表示「全部」；再次点击已选中的 = 取消
const selectSection = (id) => {
  if (id === null) {
    selectedPublicSectionIds.value = []
  } else {
    const arr = selectedPublicSectionIds.value
    const idx = arr.indexOf(id)
    if (idx >= 0) arr.splice(idx, 1)
    else arr.push(id)
  }
  pageNum.value = 1
  fetchNotes()
}

const handleSortChange = () => {
  pageNum.value = 1
  fetchNotes()
}

// 时间区间多选：'' 表示「全部」；与自定义日期互斥
const selectTimeRange = (range) => {
  if (range === '') {
    timeRanges.value = []
    dateRange.value = null
  } else {
    const arr = timeRanges.value
    const idx = arr.indexOf(range)
    if (idx >= 0) arr.splice(idx, 1)
    else arr.push(range)
    dateRange.value = null
  }
  pageNum.value = 1
  fetchNotes()
}

// 自定义日期范围（选定后清掉快捷区间）
const handleDateChange = (val) => {
  dateRange.value = val && val.length === 2 ? val : null
  if (dateRange.value) {
    timeRanges.value = []
  }
  pageNum.value = 1
  fetchNotes()
}

// 标签多选：'' 表示「全部」；再次点击已选中的 = 取消
const selectTag = (tag) => {
  if (tag === '') {
    selectedTags.value = []
  } else {
    const arr = selectedTags.value
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

onMounted(async () => {
  loadHistory()
  await Promise.all([fetchPublicSections(), fetchHotTags()])
  await nextTick()
  measureFilterOverflow()
  window.addEventListener('resize', measureFilterOverflow)
  fetchNotes()
  fetchRanking()
})

onActivated(() => {
  fetchRanking()
  nextTick(measureFilterOverflow)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', measureFilterOverflow)
})
</script>

<style lang="scss">
.notes-list-container {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 22px 28px 48px;
  box-sizing: border-box;

  .header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 18px;
  }

  .header-left {
    min-width: 0;
  }

  .header-title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--os-text);
  }

  .header-sub {
    display: block;
    margin-top: 4px;
    font-size: 13px;
    color: var(--os-text-3);
  }

  .header-right {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    flex: none;

    .refresh-btn {
      border-radius: var(--os-radius-sm);
      font-weight: 500;
      padding: 8px 14px;
      height: auto;
      min-height: 34px;
      transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
      background: #fff;
      border: 1px solid var(--os-border);
      color: var(--os-text-2);

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
      border-radius: var(--os-radius-sm);
      font-weight: 500;
      padding: 8px 16px;
      height: auto;
      min-height: 34px;
      letter-spacing: 0.01em;
      transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;

      &:hover {
        transform: none;
      }

      &:active {
        transform: none;
      }
    }
  }

  .content-layout {
    display: flex;
    gap: 24px;
    align-items: flex-start;
  }

  .left-column {
    flex: 1;
    min-width: 0;
  }

  .right-column {
    width: 280px;
    flex-shrink: 0;
  }

  .search-bar {
    margin-bottom: 20px;
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;

    .search-wrapper {
      position: relative;
      flex: 1;
      min-width: 0;
    }

    /* 排序：放在搜索框右侧，独立且直观 */
    .sort-select {
      width: 140px;
      flex-shrink: 0;

      .el-input__wrapper {
        border-radius: 8px;
        box-shadow: 0 0 0 1px #e5e7eb;

        &:hover {
          box-shadow: 0 0 0 1px #d1d5db;
        }

        &.is-focus {
          box-shadow: 0 0 0 1px #b3b3b3;
        }
      }
    }

    .search-input {
      .el-input__wrapper {
        border-radius: 8px;
        box-shadow: 0 0 0 1px #e5e7eb;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          box-shadow: 0 0 0 1px #d1d5db;
        }

        &.is-focus {
          box-shadow: 0 0 0 1px #b3b3b3;
        }
      }
    }

    .search-history-dropdown {
      position: absolute;
      top: 100%;
      left: 0;
      width: 400px;
      margin-top: 8px;
      padding: 16px;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
      z-index: 100;

      .history-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;

        .history-title {
          font-size: 13px;
          font-weight: 600;
          color: #1f2937;
        }

        .clear-history {
          font-size: 12px;
          color: #9ca3af;
          cursor: pointer;
          transition: color 0.2s;

          &:hover {
            color: #6b7280;
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
          padding: 6px 12px;
          background: #f3f4f6;
          border: 1px solid #e5e7eb;
          border-radius: 6px;
          font-size: 13px;
          color: #6b7280;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

          &:hover {
            background: #e5e7eb;
            border-color: #d1d5db;
            color: #4b5563;
          }

          .tag-text {
            color: #6b7280;
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .tag-close {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #9ca3af;
            transition: color 0.2s;

            &:hover {
              color: #4b5563;
            }

            .el-icon {
              font-size: 12px;
            }
          }
        }
      }
    }
  }

  /* 筛选面板：每个分组都有文字标签，让用户一眼看懂「这是筛什么」 */
  .filter-panel {
    margin-bottom: 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px 16px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
  }

  .filter-group {
    display: flex;
    align-items: flex-start;
    gap: 12px;

    .filter-label {
      flex-shrink: 0;
      width: 32px;
      padding-top: 5px;
      font-size: 13px;
      font-weight: 600;
      color: #6b7280;
      line-height: 1.5;
    }

    /* 分区 / 标签：一行放不下时，右侧出现「展开 / 收起」 */
    .filter-content {
      position: relative;
      flex: 1;
      min-width: 0;

      &.has-toggle .filter-chips {
        padding-right: 56px;
      }
    }

    .filter-chips {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;

      /* 折叠成一行的最大高度（chip 高 28 + 间隙余量） */
      &.is-collapsed {
        max-height: 30px;
        overflow: hidden;
      }

      .chip {
        display: inline-flex;
        align-items: center;
        height: 28px;
        padding: 0 12px;
        font-size: 13px;
        line-height: 1;
        color: #6b7280;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 999px;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          background: #e5e7eb;
          border-color: #d1d5db;
        }

        &.active {
          background: #e5e7eb;
          border-color: #9ca3af;
          color: #1f2937;
          font-weight: 600;
        }
      }

      .filter-empty {
        font-size: 12px;
        color: #9ca3af;
      }

      .date-picker {
        width: 260px;
        flex-shrink: 0;

        .el-input__wrapper {
          border-radius: 8px;
          box-shadow: 0 0 0 1px #e5e7eb;

          &:hover {
            box-shadow: 0 0 0 1px #d1d5db;
          }

          &.is-focus {
            box-shadow: 0 0 0 1px #b3b3b3;
          }
        }
      }
    }

    /* 「展开更多 / 收起」按钮 */
    .chip-toggle {
      position: absolute;
      top: 0;
      right: 0;
      display: inline-flex;
      align-items: center;
      gap: 2px;
      height: 28px;
      padding: 0 4px;
      font-size: 13px;
      color: #6b7280;
      background: transparent;
      border: none;
      cursor: pointer;
      white-space: nowrap;

      &:hover {
        color: #1f2937;
      }

      .el-icon {
        font-size: 12px;
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &.is-open {
          transform: rotate(180deg);
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
