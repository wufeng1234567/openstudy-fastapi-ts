<template>
  <div class="my-bank-page" ref="pageRef">
    <!-- 搜索区域 -->
    <div ref="searchAreaRef" class="search-area-wrapper">
    <!--
      内容区不再有「题库管理  5 个题库」这一行
      ==========================================================================
      用户 2026-10-18：「题库管理 5 个题库 …这个部分内容多余了，把他提取出来，
      一起给到第一行去：我的学习 · 题库管理 xx 个题库」。

      现在顶栏是 `我的学习 · 题库管理   5 个题库`（计数由 `topbar` store 推送），
      内容区紧接着就是分组切换 —— 少一行、垂直方向更紧凑。
    -->

      <!--
        分组切换（我的题库 / 题库收藏）
        ----------------------------------------------------------------
        用户 2026-10-18：「题库收藏和我的题库功能高度重合，合并成我的题库包含收藏功能」。
        这里不再跳另一个页面，两套数据共用下面的搜索框与筛选面板。
      -->
      <div class="tab-switch">
        <button type="button" :class="['tab-btn', { active: activeTab === 'own' }]" @click="activeTab = 'own'">
          我的题库
          <span class="tab-count">{{ allBankList.length }}</span>
        </button>
        <button type="button" :class="['tab-btn', { active: activeTab === 'favorite' }]"
          @click="activeTab = 'favorite'">
          题库收藏
          <span class="tab-count">{{ allFavoriteList.length }}</span>
        </button>
      </div>

      <div class="search-section">
        <SearchFilterInput v-model="searchKeyword" placeholder="搜索题库名称" class="search-input"
          :filter-open="filterOpen" :filter-active="filterActive" @toggle-filter="toggleFilterSidebar" />
        <el-button @click="activeTab === 'own' ? fetchBanks() : fetchFavorites()" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <!--
          「获取题库分享」按钮已移除（用户 2026-10-18：「我的题库那边的获取题库分享
          按钮取消掉 不用了」）。
          领取走的是侧栏「学习分享」页面，这里再放一个入口是重复的。
        -->
      </div>
    </div>

    <!--
      批量操作栏（有选中项时才出现）
      ----------------------------------------------------------------
      三个动作的语义严格区分（用户明确要求）：
        · 批量取消收藏 —— 只移出收藏夹，题库不删
        · 批量删除     —— 真正删除题库（仅「我的题库」分组提供）
    -->
    <div v-if="selectedCount > 0" class="batch-bar">
      <span class="batch-info">已选 {{ selectedCount }} 项</span>
      <el-button size="small" :disabled="batchBusy" @click="clearSelection">取消选择</el-button>
      <el-button v-if="activeTab === 'favorite'" size="small" type="warning" plain :loading="batchBusy"
        @click="handleBatchUncollect">
        批量取消收藏
      </el-button>
      <el-button v-if="activeTab === 'own'" size="small" type="danger" :loading="batchBusy" @click="handleBatchDelete">
        批量删除
      </el-button>
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

    <!--
      题库卡片列表
      ==========================================================================
      用户 2026-10-18：「卡片样式不一致，题库卡片、收藏、我的题库样式不一致」。
      根因不是配色，是**同一张卡片被实现了三次** —— 本页原先手写了一套，
      与共用的 `BankCardGrid`（题库练习页在用）在封面高度(140/144)、
      内边距(12/16)、按钮布局(flex:0 0 auto / flex:1)、圆角字号上都各自漂移。

      现在改为复用 `BankCardGrid`，本页特有的按钮通过 `#actions` 插槽注入，
      卡片骨架/间距/悬停效果全站只有一份。
    -->
    <!-- ==================== 我的题库 ==================== -->
    <BankCardGrid
      v-show="activeTab === 'own'"
      :banks="filteredBankList"
      :loading="loading"
      :show-header="false"
      :show-search="false"
      :show-filter="false"
      :show-refresh="false"
      :show-star="false"
      :show-favorite-status="false"
      :show-favorite-button="false"
      :show-description="true"
      :col-sm="12"
      :col-md="12"
      :col-lg="8"
      :col-xl="6"
      empty-text="还没有创建任何题库"
      @card-click="handleCardClick"
    >
      <template #empty>
        <el-empty description="还没有创建任何题库">
          <template #image>
            <el-icon size="80"><FolderOpened /></el-icon>
          </template>
          <el-button @click="goCreateBank">去创建题库</el-button>
        </el-empty>
      </template>

      <template #content-extra="{ item }">
        <div class="extra-row">
          <!-- 公开 / 私有 标识（共用卡片没有这个语义，用插槽补） -->
          <span v-if="item.isPublic === 0 || item.isPublic === 1" class="visibility-row"
            :class="isPrivateBank(item) ? 'is-private' : 'is-public'">
            <el-icon>
              <Lock v-if="isPrivateBank(item)" />
              <Unlock v-else />
            </el-icon>
            {{ isPrivateBank(item) ? '私有' : '公开' }}
          </span>
          <!-- 多选：批量删除用 -->
          <el-checkbox :model-value="isSelected(item)" class="pick-box" @click.stop
            @change="toggleSelect(item)">
            选择
          </el-checkbox>
        </div>
      </template>

      <template #actions="{ item }">
        <el-button size="small" class="action-btn" @click.stop="handleViewDetail(item)">
          查看详情
        </el-button>
        <el-button size="small" text class="action-btn" @click.stop="handleShare(item)">
          <el-icon><Share /></el-icon>
          分享
        </el-button>
        <el-button size="small" text type="danger" class="action-btn"
          :loading="deleteLoading[item.bankId]" @click.stop="handleDelete(item)">
          删除
        </el-button>
      </template>
    </BankCardGrid>

    <!-- ==================== 题库收藏 ==================== -->
    <BankCardGrid
      v-show="activeTab === 'favorite'"
      :banks="filteredFavoriteList"
      :loading="favoriteLoading"
      :show-header="false"
      :show-search="false"
      :show-filter="false"
      :show-refresh="false"
      :show-star="false"
      :show-favorite-status="false"
      :show-favorite-button="false"
      :show-uncollect-action="false"
      :col-sm="12"
      :col-md="12"
      :col-lg="8"
      :col-xl="6"
      empty-text="还没有收藏任何题库"
      @card-click="handleViewDetail"
    >
      <template #empty>
        <el-empty description="还没有收藏任何题库">
          <template #image>
            <el-icon size="80"><Star /></el-icon>
          </template>
          <el-button @click="goToQuestionBank">去发现题库</el-button>
        </el-empty>
      </template>

      <template #content-extra="{ item }">
        <div class="extra-row">
          <span v-if="item.source === 'share'" class="source-row">
            <el-tag size="small" effect="light" :type="item.shareStatus === 'invalid' ? 'info' : 'success'">
              {{ item.shareStatus === 'invalid' ? '来自分享 · 已失效' : '来自分享' }}
            </el-tag>
            <span v-if="item.shareOwnerName" class="source-owner">{{ item.shareOwnerName }}</span>
          </span>
          <span v-if="item.isPublic === 0 || item.isPublic === 1" class="visibility-row"
            :class="isPrivateBank(item) ? 'is-private' : 'is-public'">
            <el-icon>
              <Lock v-if="isPrivateBank(item)" />
              <Unlock v-else />
            </el-icon>
            {{ isPrivateBank(item) ? '私有' : '公开' }}
          </span>
          <!-- 多选：批量取消收藏用 -->
          <el-checkbox :model-value="isSelected(item)" class="pick-box" @click.stop
            @change="toggleSelect(item)">
            选择
          </el-checkbox>
        </div>
      </template>

      <template #actions="{ item }">
        <el-button size="small" class="action-btn" @click.stop="handleViewDetail(item)">
          查看详情
        </el-button>
        <el-button v-if="item.canCopy !== false" size="small" type="primary" plain class="action-btn"
          @click.stop="handleCopy(item)">
          <el-icon><CopyDocument /></el-icon>
          复制
        </el-button>
        <el-button size="small" type="danger" class="action-btn"
          :loading="uncollectLoading[item.favoriteId]" @click.stop="handleUncollect(item)">
          取消收藏
        </el-button>
      </template>
    </BankCardGrid>

    <!-- 通过分享链接 / 分享码领取题库 -->
    <ReceiveShareDialog v-model="receiveDialogVisible" @received="fetchBanks" />

    <!-- 分享题库弹窗（下拉自由选择题库，默认当前点击的那个） -->
    <ShareBankDialog v-model="shareDialogVisible" :default-bank-id="shareBankId" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyBank' })
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, FolderOpened, Document, View, Delete, Share, Lock, Unlock, CopyDocument, Star } from '@element-plus/icons-vue'
import BankCardGrid from '@/components/BankCardGrid/BankCardGrid.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import ReceiveShareDialog from '@/views/front/myQuestion/components/ReceiveShareDialog.vue'
import ShareBankDialog from '@/views/front/myQuestion/components/ShareBankDialog.vue'
import { listMyQuestionBank, delQuestionBank, copyQuestionBank } from '@/api/questionBank/questionBank'
import { listFavoriteBank, delFavoriteBank } from '@/api/favoriteBank/favoriteBank'
import useTopbarStore from '@/store/modules/topbar'
import type { UserBankFavorite } from '@/types'

interface MyBankItem {
  id: number | string
  bankName: string
  subject?: string
  coverImage?: string
  totalQuestions?: number
  description?: string
  isPublic?: number
  [key: string]: any
}

const router = useRouter()

const loading = ref(false)
// 领取分享题库弹窗
const receiveDialogVisible = ref(false)
// 分享题库弹窗
const shareDialogVisible = ref(false)
const shareBankId = ref<number | string | null>(null)
const allBankList = ref<MyBankItem[]>([])
const deleteLoading = ref<Record<string | number, boolean>>({})

/* ==================== 收藏题库（合并自「题库收藏」页） ====================
 *
 * 用户 2026-10-18：「题库收藏和我的题库功能高度重合了，能否进行合理的合并，
 * 直接变成我的题库包含题库收藏相关功能，包括搜索、筛选面板也要做相应的优化；
 * 还有取消收藏、批量取消、批量删除的功能区分」。
 *
 * 做法：不再跳去另一个页面，而是在**本页顶部加一个分段切换**（我的题库 / 题库收藏），
 * 两套数据共用一个搜索框与一个筛选面板 —— 筛选组按当前分组动态生成
 * （题库分组按「公开/私有」，收藏分组按「来源/失效」），避免出现点了没反应的筛选项。
 */
type BankTab = 'own' | 'favorite'
const route = useRoute()
/**
 * 初始分组：支持 `?tab=favorite`
 *
 * 「题库收藏」的旧路由现在重定向到这里（`/front/myQuestion/myBank?tab=favorite`），
 * 所以进入时要认这个参数，否则用户点旧链接会落在「我的题库」分组，像是走错了。
 */
const activeTab = ref<BankTab>(route.query.tab === 'favorite' ? 'favorite' : 'own')

const favoriteLoading = ref(false)
const allFavoriteList = ref<UserBankFavorite[]>([])
/** 收藏项的取消收藏 loading（key = favoriteId） */
const uncollectLoading = ref<Record<string | number, boolean>>({})
/** 批量操作进行中（禁用按钮 + 防重复点击） */
const batchBusy = ref(false)
/** 当前选中的卡片（批量操作对象）：own 用 bankId 作 key，favorite 用 favoriteId */
const selectedKeys = ref<Set<string>>(new Set())

const favKeyOf = (item: any) => (activeTab.value === 'own' ? `own:${item.bankId}` : `fav:${item.favoriteId}`)
const isSelected = (item: any) => selectedKeys.value.has(favKeyOf(item))

function toggleSelect(item: any) {
  const k = favKeyOf(item)
  const s = new Set(selectedKeys.value)
  if (s.has(k)) s.delete(k)
  else s.add(k)
  selectedKeys.value = s
}

function clearSelection() {
  selectedKeys.value = new Set()
}

// 切换分组时清空选择（两边的 key 语义不同，留着会误操作）
watch(activeTab, () => clearSelection())
const searchKeyword = ref('')
const searchAreaRef = ref<HTMLElement | null>(null)
const searchAreaHeight = ref(0)
// 内嵌筛选按钮状态
const filterSidebarRef = ref<any>(null)
const filterOpen = ref(false)
const filterActive = ref(false)

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
  allBankList.value.forEach((bank: MyBankItem) => {
    if (bank.subject) subjects.add(bank.subject)
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

// 过滤后的题库列表
const filteredBankList = computed(() => {
  let list: MyBankItem[] = allBankList.value

  // 关键词搜索
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    list = list.filter((bank: MyBankItem) => bank.bankName?.toLowerCase().includes(keyword))
  }

  // 科目筛选
  if (filterForm.value.subjects?.length > 0) {
    list = list.filter((bank: MyBankItem) => filterForm.value.subjects.includes(bank.subject || ''))
  }

  // 题目数量（多选：命中任一档即可）
  if (filterForm.value.questionCount?.length > 0) {
    const ranges = filterForm.value.questionCount
    list = list.filter((bank: MyBankItem) => {
      const total = bank.totalQuestions || 0
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
    list = list.filter((bank: MyBankItem) => filterForm.value.isPublic.includes(bank.isPublic as number))
  }

  // 创建时间范围
  if (filterForm.value.createRange?.length === 2) {
    const [start, end] = filterForm.value.createRange
    const startTs = new Date(`${start} 00:00:00`).getTime()
    const endTs = new Date(`${end} 23:59:59`).getTime()
    list = list.filter((bank: MyBankItem) => {
      if (!bank.createTime) return false
      const ts = new Date(bank.createTime).getTime()
      return ts >= startTs && ts <= endTs
    })
  }

  return list
})

/**
 * 过滤后的收藏列表
 *
 * 与 `filteredBankList` 共用同一个搜索框与筛选面板。
 * ⚠️ 取值统一写成 `f.bankName ?? f.bank?.bankName` 这种形式：
 *    后端实际返回**扁平**结构（见 `favoriteCardList` 的注释），
 *    但处理器里保留了 `bank` 自引用，两种形态都兼容，避免以后再踩一次。
 */
const filteredFavoriteList = computed(() => {
  let list: any[] = favoriteCardList.value as unknown as any[]

  // 关键词搜索（按题库名）
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter((f: any) => String(f.bankName ?? f.bank?.bankName ?? '').toLowerCase().includes(kw))
  }

  // 科目（多选）
  if (filterForm.value.subjects?.length > 0) {
    list = list.filter((f: any) => filterForm.value.subjects.includes(f.subject ?? f.bank?.subject ?? ''))
  }

  // 题目数量（多选，命中任一档）
  if (filterForm.value.questionCount?.length > 0) {
    const ranges = filterForm.value.questionCount
    list = list.filter((f: any) => {
      const total = Number(f.totalQuestions ?? f.bank?.totalQuestions ?? 0)
      return ranges.some((c: string) => {
        if (c === '0-10') return total < 10
        if (c === '10-50') return total >= 10 && total < 50
        if (c === '50-100') return total >= 50 && total < 100
        if (c === '100+') return total >= 100
        return false
      })
    })
  }

  // 可见性（多选）
  if (filterForm.value.isPublic?.length > 0) {
    list = list.filter((f: any) => {
      const v = f.isPublic ?? f.bank?.isPublic
      return filterForm.value.isPublic.includes(v as number)
    })
  }

  return list
})

/** 去题库广场（收藏为空时的引导） */
const goToQuestionBank = () => {
  router.push('/front/questionPractice')
}

/* ==================== 顶栏计数 ====================
 *
 * 把「N 个题库」推到顶栏（与标题同一行），内容区不再单独占一行。
 * 见 `store/modules/topbar.ts` 与 `layout/front.vue` 的 `os-topbar__count`。
 */
const topbarStore = useTopbarStore()
watch(
  [activeTab, () => filteredBankList.value.length, () => filteredFavoriteList.value.length],
  () => {
    const n = activeTab.value === 'own' ? filteredBankList.value.length : filteredFavoriteList.value.length
    topbarStore.setCount(`${n} 个题库`)
  },
  { immediate: true }
)
// keep-alive 页面：离开时必须清，否则会把本页计数带到下一个页面
onBeforeUnmount(() => topbarStore.clear())

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
const isPrivateBank = (bank: MyBankItem | null | undefined) => Number(bank?.isPublic) === 1

const fetchBanks = () => {
  loading.value = true
  listMyQuestionBank().then((res: any) => {
    if (res.code === 200) {
      allBankList.value = res.data || []
    } else {
      ElMessage.error(res.msg || '获取题库失败')
    }
    loading.value = false
  }).catch(() => {
    ElMessage.error('获取题库失败')
    loading.value = false
  })
}

const handleCardClick = (item: MyBankItem) => {
  handleViewDetail(item)
}

const handleViewDetail = (item: MyBankItem) => {
  // 空题库不允许进入
  if (!item.totalQuestions || Number(item.totalQuestions) === 0) {
    return
  }
  router.push(`/front/questionPractice/${item.bankId}?from=myLearning`)
}

/** 分享：原地弹出分享弹窗，默认选中该题库（弹窗内可切换成其它题库） */
const handleShare = (item: MyBankItem) => {
  if (!item.totalQuestions || Number(item.totalQuestions) === 0) {
    ElMessage.warning('空题库无法分享，请先添加题目')
    return
  }
  shareBankId.value = item.bankId
  shareDialogVisible.value = true
}

const handleDelete = (item: MyBankItem) => {
  ElMessageBox.confirm(`确定删除题库"${item.bankName}"吗？删除后无法恢复。`, '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    deleteLoading.value[item.bankId] = true
    return delQuestionBank(item.bankId)
  }).then(() => {
    ElMessage.success('删除成功')
    fetchBanks()
  }).catch(() => { }).finally(() => {
    deleteLoading.value[item.bankId] = false
  })
}

/* ==================== 收藏相关（合并进来的功能） ==================== */

/** 拉取收藏列表 */
const fetchFavorites = () => {
  favoriteLoading.value = true
  listFavoriteBank().then((res: any) => {
    if (res.code === 200) {
      allFavoriteList.value = res.rows || res.data || []
    }
    favoriteLoading.value = false
  }).catch(() => {
    ElMessage.error('获取收藏题库失败')
    favoriteLoading.value = false
  })
}

/**
 * 收藏列表 → 卡片数据
 *
 * ⚠️⚠️ 后端 `/favoriteBank/favoriteBank/all` 返回的是**已经摊平**的结构：
 *    `_format_favorite_bank()` 里是 `row = format_bank(bank)`，题库字段
 *    （`bankName` / `id` / `totalQuestions` / `coverImage` …）全在**顶层**，
 *    `favoriteId` / `bankId` / `createTime` 这些收藏字段也与它同级。
 *    **没有** `item.bank` 这个嵌套对象。
 *
 *    我上一版按 `item.bank?.bankName` 去取（那是「后端返回嵌套」的假设），
 *    结果摊平出空对象 → 卡片显示「题库ID: undefined」（用户 2026-10-18 截图）。
 *
 * 所以这里**直接用原始条目**，只补一个 `bank` 自引用，
 * 让下面的 `handleViewDetail` / `handleCopy` / `handleUncollect`
 * （它们按 `item.bank?.xxx` 写的）也能正常工作 —— 两种取值都指向同一份数据。
 */
const favoriteCardList = computed(() =>
  allFavoriteList.value.map((item: UserBankFavorite) => ({
    ...item,
    // 自引用：兼容按 `item.bank?.xxx` 取值的既有处理器
    bank: item.bank || item,
    isCollected: true
  }))
)

/** 取消收藏（单个） */
const handleUncollect = async (item: any) => {
  try {
    await ElMessageBox.confirm(`确定取消收藏"${item.bank?.bankName || item.bankName || '该题库'}"吗？`, '取消收藏', {
      confirmButtonText: '取消收藏',
      cancelButtonText: '再想想',
      type: 'warning'
    })
  } catch {
    return
  }
  const fid = item.favoriteId
  if (fid == null) return
  uncollectLoading.value[fid] = true
  try {
    const res: any = await delFavoriteBank(fid)
    if (res.code === 200) {
      ElMessage.success('已取消收藏')
      fetchFavorites()
    } else {
      ElMessage.error(res.msg || '取消收藏失败')
    }
  } finally {
    uncollectLoading.value[fid] = false
  }
}

/** 复制收藏的题库到「我的题库」 */
const handleCopy = async (item: any) => {
  const bankId = item.bankId
  if (!bankId) return
  try {
    await ElMessageBox.confirm(
      `确定把「${item.bank?.bankName || '该题库'}」复制一份到「我的题库」吗？复制后可自由编辑。`,
      '复制题库',
      { confirmButtonText: '复制', cancelButtonText: '取消', type: 'info' }
    )
  } catch {
    return
  }
  try {
    const res: any = await copyQuestionBank(bankId)
    if (res.code === 200 && res.data) {
      ElMessage.success('复制成功，已放入「我的题库」')
      fetchBanks()
    } else {
      ElMessage.error(res.msg || '复制失败')
    }
  } catch {
    ElMessage.error('复制失败')
  }
}

/* ==================== 批量操作 ====================
 *
 * 用户要求「取消收藏、批量取消、批量删除的功能区分」。三者语义不同，不能混：
 *   · 取消收藏（单个）→ 只从收藏夹移除，**不删题库本身**，随时可重新收藏；
 *   · 批量取消     → 同上，只是多选后一次处理；
 *   · 批量删除     → **真正删除题库**（连题目一起），不可恢复。
 * 所以批量删除的确认文案要明确写"题库及其题目将一并删除、无法恢复"，
 * 并且只在「我的题库」分组出现（收藏里没有删除权限，只有取消收藏）。
 */

/** 当前分组选中的条目 */
const selectedItems = computed(() => {
  if (activeTab.value === 'own') {
    return allBankList.value.filter((b) => selectedKeys.value.has(`own:${b.bankId}`))
  }
  return allFavoriteList.value.filter((f) => selectedKeys.value.has(`fav:${f.favoriteId}`))
})

const selectedCount = computed(() => selectedItems.value.length)

/** 批量取消收藏 */
const handleBatchUncollect = async () => {
  const items = selectedItems.value as UserBankFavorite[]
  if (!items.length) return
  try {
    await ElMessageBox.confirm(
      `确定取消收藏选中的 ${items.length} 个题库吗？题库本身不会被删除，之后仍可重新收藏。`,
      '批量取消收藏',
      { confirmButtonText: '取消收藏', cancelButtonText: '再想想', type: 'warning' }
    )
  } catch {
    return
  }
  batchBusy.value = true
  let ok = 0
  let fail = 0
  for (const it of items) {
    const fid = it.favoriteId
    if (fid == null) continue
    try {
      const res: any = await delFavoriteBank(fid)
      if (res.code === 200) ok += 1
      else fail += 1
    } catch {
      fail += 1
    }
  }
  batchBusy.value = false
  clearSelection()
  fetchFavorites()
  if (ok && !fail) ElMessage.success(`已取消收藏 ${ok} 个题库`)
  else if (ok && fail) ElMessage.warning(`成功 ${ok} 个，失败 ${fail} 个`)
  else ElMessage.error('批量取消失败，请重试')
}

/** 批量删除（真正删库，不可恢复） */
const handleBatchDelete = async () => {
  const items = selectedItems.value as MyBankItem[]
  if (!items.length) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${items.length} 个题库吗？\n题库及其全部题目将被一并删除，**无法恢复**。`,
      '批量删除题库',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'error' }
    )
  } catch {
    return
  }
  batchBusy.value = true
  let ok = 0
  let fail = 0
  for (const it of items) {
    try {
      const res: any = await delQuestionBank(it.bankId)
      if (res?.code === 200) ok += 1
      else fail += 1
    } catch {
      fail += 1
    }
  }
  batchBusy.value = false
  clearSelection()
  fetchBanks()
  if (ok && !fail) ElMessage.success(`已删除 ${ok} 个题库`)
  else if (ok && fail) ElMessage.warning(`成功 ${ok} 个，失败 ${fail} 个`)
  else ElMessage.error('批量删除失败，请重试')
}

const goCreateBank = () => {
  router.push('/front/studio')
}

onMounted(() => {
  fetchBanks()
  // 收藏数据一起预取：切 tab 时就不用等一次网络往返，计数也能立刻显示
  fetchFavorites()
  updateSearchAreaHeight()
  window.addEventListener('resize', updateSearchAreaHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateSearchAreaHeight)
})
</script>

<style scoped>
.my-bank-page {
  position: relative;
  min-height: 100%;
  /* 外层聚合页已经给了统一留白，这里不再重复加左右 padding */
  padding: 0;
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
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--os-text);
  margin: 0;
}

/* 「我的学习 · xxx」里的分隔点：做弱处理，让模块名仍是视觉重心 */
.title-sep {
  margin: 0 6px;
  color: var(--os-text-4, #9ca3af);
  font-weight: 400;
}

.total-count {
  font-size: 13px;
  color: var(--os-text-3);
}

.search-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

/*
 * 分组切换（我的题库 / 题库收藏）
 * ----------------------------------------------------------------
 * 用下划线式分段控件，而不是 el-tabs：这里的两个分组是"同一份数据的两个视图"，
 * 视觉上比 tab 更轻，也不会在外壳里再多一层描边。
 */
.tab-switch {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px 10px;
  border: 0;
  background: transparent;
  font-size: 13.5px;
  line-height: 1;
  color: var(--os-text-3, #6b7280);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s ease, border-color 0.15s ease;

  &:hover {
    color: var(--os-text, #1f2937);
  }

  &.active {
    color: var(--os-text, #1f2937);
    font-weight: 600;
    border-bottom-color: var(--os-primary, #4f6ef7);
  }

  .tab-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 500;
    background: var(--os-bg-hover, rgba(0, 0, 0, 0.05));
    color: var(--os-text-3, #6b7280);
  }
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  border-radius: var(--os-radius-sm, 8px);
  background: var(--os-bg-hover, rgba(0, 0, 0, 0.02));

  .batch-info {
    font-size: 13px;
    color: var(--os-text-2, #4b5563);
  }
}

/* 卡片信息区最后一行的容器（公开/私有 + 选择框） */
.extra-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.pick-box {
  flex: none;
  height: auto;

  :deep(.el-checkbox__label) {
    font-size: 12px;
    padding-left: 4px;
  }
}

.search-input {
  flex: 1;
  max-width: 400px;
}

.refresh-btn {
  border-radius: 8px;
}

/*
 * 公开 / 私有 标识（卡片信息区最后一行）
 * 图标走 OsIcon 同款语义色，不用色块 —— 与全站状态标识保持一致。
 */
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

</style>

