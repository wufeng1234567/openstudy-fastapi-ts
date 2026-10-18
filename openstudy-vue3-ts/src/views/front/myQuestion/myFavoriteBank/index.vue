<template>
  <div class="bank-collect-page" ref="pageRef">
    <!-- 搜索区域 -->
    <div ref="searchAreaRef" class="search-area-wrapper">
      <div class="title-section">
        <h2 class="page-title">我的收藏题库</h2>
        <span class="total-count">共 {{ filteredList.length }} 个题库</span>
      </div>
      <div class="search-section">
        <SearchFilterInput v-model="searchKeyword" placeholder="搜索题库名称" class="search-input"
          :filter-open="filterOpen" :filter-active="filterActive" @toggle-filter="toggleFilterSidebar" />
        <el-button @click="fetchFavorites" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" plain class="refresh-btn" @click="receiveDialogVisible = true">
          <el-icon><Ticket /></el-icon>
          获取题库分享
        </el-button>
      </div>
    </div>

    <!-- 筛选下拉面板（触发按钮已内嵌到搜索框最左侧） -->
    <CommonFilterSidebar
      ref="filterSidebarRef"
      title="题库筛选"
      hide-trigger
      :filter-groups="filterGroups"
      :filter-form="filterForm"
      :default-filter="{ subjects: [], questionCount: [], isPublic: [], createRange: null }"
      :default-collapsed="true"
      :style="{ '--filter-top': searchAreaHeight + 'px' }"
      @filter-change="handleFilterChange"
      @reset-filters="handleResetFilters"
      @collapse-change="handleFilterCollapseChange"
      @active-change="handleFilterActiveChange"
    />

    <!-- 题库卡片列表 -->
    <!--
      收藏卡片列表
      ==========================================================================
      用户 2026-10-18：「卡片样式不一致，题库卡片、收藏、我的题库样式不一致」。
      与「我的题库」同一处理：复用 `BankCardGrid` 的卡片骨架，
      本页特有的「来源 / 分享者 / 已失效」通过 `#content-extra` 注入，
      按钮通过 `#actions` 注入。三处卡片从此只有**一份**实现。
    -->
    <BankCardGrid
      :banks="favoriteBankList"
      :loading="loading"
      :show-header="false"
      :show-search="false"
      :show-filter="false"
      :show-refresh="false"
      :show-star="false"
      :show-favorite-status="false"
      :show-favorite-button="false"
      :show-uncollect-action="false"
      :col-sm="12"
      :col-md="8"
      :col-lg="6"
      :col-xl="4"
      @card-click="handleCardClick"
    >
      <template #empty>
        <el-empty description="暂无收藏的题库">
          <template #image>
            <el-icon size="80"><Star /></el-icon>
          </template>
          <el-button @click="goToQuestionBank">去发现题库</el-button>
        </el-empty>
      </template>

      <template #content-extra="{ item }">
        <div v-if="item.source === 'share'" class="source-row">
          <el-tag size="small" effect="light" :type="item.shareStatus === 'invalid' ? 'info' : 'success'">
            {{ item.shareStatus === 'invalid' ? '来自分享 · 已失效' : '来自分享' }}
          </el-tag>
          <span v-if="item.shareOwnerName" class="source-owner">来自 {{ item.shareOwnerName }}</span>
        </div>
        <!-- 公开 / 私有（与「我的题库」同一套插槽与文案，保持三处一致） -->
        <div v-if="item.isPublic === 0 || item.isPublic === 1" class="visibility-row"
          :class="isPrivateBank(item) ? 'is-private' : 'is-public'">
          <el-icon>
            <Lock v-if="isPrivateBank(item)" />
            <Unlock v-else />
          </el-icon>
          <span>{{ isPrivateBank(item) ? '私有' : '公开' }}</span>
        </div>
      </template>

      <template #actions="{ item }">
        <el-button size="small" class="action-btn" @click.stop="handleViewDetail(item)">
          查看详情
        </el-button>
        <el-button v-if="item.canCopy !== false" size="small" type="primary" plain class="action-btn"
          @click.stop="handleCopy(item)">
          复制
        </el-button>
        <el-button size="small" type="danger" class="action-btn"
          :loading="!!item.favoriteId && uncollectLoading[item.favoriteId]"
          @click.stop="handleUncollect(item)">
          取消收藏
        </el-button>
      </template>
    </BankCardGrid>

    <!-- 通过分享链接 / 分享码领取 -->
    <ReceiveShareDialog v-model="receiveDialogVisible" @received="fetchFavorites" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontBankCollect' })
import { ref, computed, onMounted, onUnmounted, onActivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentInstance } from 'vue'
import { ElMessage } from 'element-plus'
import { Star, Refresh, Document, View, Ticket, CopyDocument, Lock, Unlock } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import BankCardGrid from '@/components/BankCardGrid/BankCardGrid.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import ReceiveShareDialog from '@/views/front/myQuestion/components/ReceiveShareDialog.vue'
import { listFavoriteBank, delFavoriteBank } from '@/api/favoriteBank/favoriteBank'
import { getQuestionBank, copyQuestionBank } from '@/api/questionBank/questionBank'
import type { UserBankFavorite } from '@/types'

const { proxy } = getCurrentInstance() as any
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const allFavoriteList = ref<UserBankFavorite[]>([])
const uncollectLoading = ref<Record<string | number, boolean>>({})
const bankCache = ref<Record<string | number, any>>({})
const searchKeyword = ref('')
const searchAreaRef = ref<HTMLElement | null>(null)
const searchAreaHeight = ref(0)
// 内嵌筛选按钮状态
const filterSidebarRef = ref<any>(null)
const filterOpen = ref(false)
const filterActive = ref(false)

// 领取分享题库弹窗
const receiveDialogVisible = ref(false)

// 筛选相关
const filterForm = ref<{
  subjects: string[]
  questionCount: string[]
  isPublic: number[]
  createRange: string[] | null
}>({
  subjects: [],
  questionCount: [],
  isPublic: [],
  createRange: null
})

// 筛选配置（多选 + 时间范围，组内 OR、组间 AND）
const filterGroups = computed(() => {
  const subjects = new Set<string>()
  allFavoriteList.value.forEach((item: UserBankFavorite) => {
    if (item.bank?.subject) subjects.add(item.bank.subject)
  })

  return [
    {
      key: 'subjects',
      label: '科目分类',
      type: 'checkbox',
      options: Array.from(subjects).sort().map((s: string) => ({ value: s, label: s }))
    },
    {
      key: 'questionCount',
      label: '题目数量',
      type: 'checkbox',
      options: [
        { value: '0-10', label: '10题以下' },
        { value: '10-50', label: '10-50题' },
        { value: '50-100', label: '50-100题' },
        { value: '100+', label: '100题以上' }
      ]
    },
    {
      key: 'isPublic',
      label: '可见性',
      type: 'checkbox',
      options: [
        { value: 0, label: '公开' },
        { value: 1, label: '私有' }
      ]
    },
    {
      key: 'createRange',
      label: '创建时间',
      type: 'dateRange'
    }
  ]
})

// 过滤后的列表
const filteredList = computed(() => {
  let list: UserBankFavorite[] = allFavoriteList.value

  // 关键词搜索
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    list = list.filter((item: UserBankFavorite) => (item.bank?.bankName || '').toLowerCase().includes(keyword))
  }

  // 科目筛选
  if (filterForm.value.subjects.length > 0) {
    list = list.filter((item: UserBankFavorite) => filterForm.value.subjects.includes(item.bank?.subject || ''))
  }

  // 题目数量（多选：命中任一档即可）
  if (filterForm.value.questionCount?.length > 0) {
    const ranges = filterForm.value.questionCount
    list = list.filter((item: UserBankFavorite) => {
      const total = item.bank?.totalQuestions || 0
      return ranges.some((count: string) => {
        if (count === '0-10') return total < 10
        if (count === '10-50') return total >= 10 && total < 50
        if (count === '50-100') return total >= 50 && total < 100
        if (count === '100+') return total >= 100
        return false
      })
    })
  }

  // 可见性（多选：公开/私有可同时选）
  if (filterForm.value.isPublic?.length > 0) {
    list = list.filter((item: UserBankFavorite) => filterForm.value.isPublic.includes(item.bank?.isPublic as number))
  }

  // 创建时间范围
  if (filterForm.value.createRange?.length === 2) {
    const [start, end] = filterForm.value.createRange
    const startTs = new Date(`${start} 00:00:00`).getTime()
    const endTs = new Date(`${end} 23:59:59`).getTime()
    list = list.filter((item: UserBankFavorite) => {
      const time = item.bank?.createTime
      if (!time) return false
      const ts = new Date(time).getTime()
      return ts >= startTs && ts <= endTs
    })
  }

  return list
})

/**
 * 扁平化后的收藏列表（喂给共用的 `BankCardGrid`）
 * ------------------------------------------------------------------
 * 本接口返回的是 `UserBankFavorite`：题库字段嵌套在 `item.bank` 里
 * （`item.bank.bankName` / `item.bank.totalQuestions` …），
 * 而共享卡片是**按题库条目**的扁平结构读的（`item.bankName`）。
 *
 * 与其去改共用组件、给它加一套「嵌套/扁平双形态」的兼容分支
 * （那会让卡片逻辑越来越难维护），不如在这里做一次映射：
 * 把 `bank` 的字段摊到顶层，同时保留 `favoriteId` / `source` / `canCopy`
 * 这些收藏自身的信息 —— 卡片、插槽、事件里都能直接用。
 */
const favoriteBankList = computed(() =>
  filteredList.value.map((item: UserBankFavorite) => ({
    ...(item.bank || {}),
    /*
     * ⚠️ 保留 `bank` 原引用。
     * 本页的事件处理器（handleViewDetail / handleCopy / handleUncollect）
     * 都是按 `item.bank?.bankName`、`item.bank?.totalQuestions` 取值写的 ——
     * 只做扁平化会让这些地方全部读到 undefined。
     * 两个形态都留着，卡片读顶层、处理器读 `bank`，互不影响。
     */
    bank: item.bank,
    favoriteId: item.favoriteId,
    source: item.source,
    shareStatus: item.shareStatus,
    shareOwnerName: item.shareOwnerName,
    canCopy: item.canCopy,
    isCollected: true
  }))
)

const handleFilterChange = (newFilter: any) => {
  filterForm.value = { ...newFilter }
}

const handleResetFilters = () => {
  filterForm.value = { subjects: [], questionCount: [], isPublic: [], createRange: null }
}

// 内嵌在搜索框里的筛选按钮：切换下方筛选面板
const toggleFilterSidebar = () => {
  filterSidebarRef.value?.toggleCollapse?.()
}

// 面板展开/收起同步到按钮态（事件值为「是否已收起」）
const handleFilterCollapseChange = (collapsed: boolean) => {
  filterOpen.value = !collapsed
}

// 是否有生效的筛选条件（按钮小圆点）
const handleFilterActiveChange = (active: boolean) => {
  filterActive.value = !!active
}

// 测量搜索区域高度
const updateSearchAreaHeight = () => {
  nextTick(() => {
    if (searchAreaRef.value) {
      searchAreaHeight.value = searchAreaRef.value.offsetHeight
    }
  })
}

// 0=公开 / 1=私有
const isPrivateBank = (bank: any) => Number(bank?.isPublic) === 1

onActivated(() => {})

const fetchFavorites = () => {
  loading.value = true
  const userId = userStore.id
  if (!userId) {
    proxy.$modal.msgWarning('请先登录')
    loading.value = false
    return
  }

  listFavoriteBank({ userId, favoriteStatus: 1, pageNum: 1, pageSize: 100 })
    .then((res: any) => {
      if (res.code === 200) {
        const favorites: any[] = res.rows || []
        const promises = favorites.map((item: any) => {
          if (bankCache.value[item.bankId]) {
            item.bank = bankCache.value[item.bankId]
            return Promise.resolve(item)
          }
          return getQuestionBank(item.bankId).then((bankRes: any) => {
            if (bankRes.code === 200) {
              item.bank = bankRes.data || {}
              bankCache.value[item.bankId] = item.bank
            } else {
              item.bank = { bankName: '未知题库' } as any
            }
            return item
          }).catch(() => {
            item.bank = { bankName: '未知题库' } as any
            return item
          })
        })
        Promise.all(promises).then(() => {
          allFavoriteList.value = favorites
          loading.value = false
        })
      } else {
        ElMessage.error(res.msg || '获取收藏失败')
        loading.value = false
      }
    })
    .catch(() => {
      ElMessage.error('获取收藏失败')
      loading.value = false
    })
}

const handleCardClick = (item: UserBankFavorite) => {
  proxy.$modal.confirm(
    `是否查看题库 "${item.bank?.bankName || '未知题库'}" 的详细信息？`,
    '提示',
    { confirmButtonText: '查看详情', cancelButtonText: '取消', type: 'info' }
  ).then(() => {
    handleViewDetail(item)
  }).catch(() => { })
}

const handleViewDetail = (item: UserBankFavorite) => {
  // 空题库不允许进入
  const total = item.bank?.totalQuestions
  if (!total || Number(total) === 0) {
    return
  }
  router.push(`/front/questionPractice/${item.bankId}?from=myLearning`)
}

const handleUncollect = async (item: UserBankFavorite) => {
  try {
    uncollectLoading.value[item.favoriteId!] = true
    await proxy.$modal.confirm(
      `确定取消收藏"${item.bank?.bankName || '该题库'}"吗？`,
      '取消收藏',
      { type: 'warning' }
    )
    const res: any = await delFavoriteBank(item.favoriteId!)
    if (res.code === 200) {
      ElMessage.success('已取消收藏')
      fetchFavorites()
    } else {
      ElMessage.error(res.msg || '操作失败')
    }
  } catch (e) {
  } finally {
    uncollectLoading.value[item.favoriteId!] = false
  }
}

/** 复制题库为我的新题库（可自由编辑，不影响原题库） */
const handleCopy = async (item: UserBankFavorite) => {
  try {
    await proxy.$modal.confirm(
      `确定把「${item.bank?.bankName || '该题库'}」复制一份到「我的题库」吗？复制后可自由编辑。`,
      '复制题库',
      { confirmButtonText: '复制', cancelButtonText: '取消', type: 'info' }
    )
  } catch (e) {
    return
  }
  try {
    const res: any = await copyQuestionBank(item.bankId)
    if (res.code === 200 && res.data) {
      ElMessage.success(`已复制为《${res.data.bankName}》，可在「我的题库」中查看`)
    } else {
      ElMessage.error(res.msg || '复制失败')
    }
  } catch (e) {
    ElMessage.error('复制失败')
  }
}

/** 领取分享题库的弹窗逻辑已抽到公共组件 ReceiveShareDialog */

const goToQuestionBank = () => {
  router.push('/front/questionPractice')
}

onMounted(() => {
  fetchFavorites()
  updateSearchAreaHeight()
  window.addEventListener('resize', updateSearchAreaHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateSearchAreaHeight)
})
</script>

<style scoped>
.bank-collect-page {
  position: relative;
  min-height: 100%;
  padding: 0 16px;
}

.search-area-wrapper {
  margin-bottom: 20px;
}

.title-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2937;
  margin: 0;
}

.total-count {
  font-size: 14px;
  color: #6b7280;
}

.search-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-input {
  flex: 1;
  max-width: 400px;
}

.refresh-btn {
  border-radius: 8px;
}


.source-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  min-height: 20px;
}

.source-owner {
  font-size: 12px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 公开 / 私有 标识（与「我的题库」完全一致的写法） */
.visibility-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;

  &.is-private {
    color: var(--el-color-warning, #e6a23c);
  }

  &.is-public {
    color: var(--os-text-4, #9ca3af);
  }
}

/* 领取弹窗的样式在公共组件 ReceiveShareDialog.vue 内 */
</style>
