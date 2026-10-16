<template>
  <div class="my-bank-page" ref="pageRef">
    <!-- 搜索区域 -->
    <div ref="searchAreaRef" class="search-area-wrapper">
      <div class="title-section">
        <h2 class="page-title">我的题库</h2>
        <span class="total-count">共 {{ filteredBankList.length }} 个题库</span>
      </div>
      <div class="search-section">
        <SearchFilterInput v-model="searchKeyword" placeholder="搜索题库名称" class="search-input"
          :filter-open="filterOpen" :filter-active="filterActive" @toggle-filter="toggleFilterSidebar" />
        <el-button @click="fetchBanks" class="refresh-btn">
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
    <div class="bank-grid" v-loading="loading">
      <el-empty v-if="!loading && filteredBankList.length === 0" description="还没有创建任何题库">
        <template #image>
          <el-icon size="80"><FolderOpened /></el-icon>
        </template>
        <el-button @click="goCreateBank">去创建题库</el-button>
      </el-empty>

      <el-row v-else :gutter="20">
        <el-col v-for="item in filteredBankList" :key="item.bankId" :xs="24" :sm="12" :md="8" :lg="6" :xl="4">
          <div class="bank-card" @click="handleCardClick(item)">
            <div class="card-cover">
              <BankCover :cover-image="item.coverImage" :bank-name="item.bankName" :subject="item.subject"
                class="cover-image" />
              <!-- 公开 / 私有 标识 -->
              <div v-if="item.isPublic === 0 || item.isPublic === 1" class="visibility-badge"
                :class="isPrivateBank(item) ? 'is-private' : 'is-public'">
                <el-icon>
                  <Lock v-if="isPrivateBank(item)" />
                  <Unlock v-else />
                </el-icon>
                <span>{{ isPrivateBank(item) ? '私有' : '公开' }}</span>
              </div>
            </div>
            <div class="card-content">
              <div class="bank-name">
                <h3>{{ item.bankName }}</h3>
                <el-tag v-if="item.subject" size="small" type="info">{{ item.subject }}</el-tag>
              </div>
              <div class="bank-stats">
                <div class="stat-item">
                  <el-icon><Document /></el-icon>
                  <span>{{ item.totalQuestions || 0 }} 题</span>
                </div>
              </div>
              <div v-if="item.description" class="bank-description">
                {{ item.description }}
              </div>
            </div>
            <div class="card-actions">
              <el-button size="small" @click.stop="handleViewDetail(item)">
                <el-icon><View /></el-icon>
                查看详情
              </el-button>
              <el-button size="small" type="primary" plain @click.stop="handleShare(item)">
                <el-icon><Share /></el-icon>
                分享
              </el-button>
              <el-button size="small" type="danger" @click.stop="handleDelete(item)" :loading="deleteLoading[item.bankId]">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 通过分享链接 / 分享码领取题库 -->
    <ReceiveShareDialog v-model="receiveDialogVisible" @received="fetchBanks" />

    <!-- 分享题库弹窗（下拉自由选择题库，默认当前点击的那个） -->
    <ShareBankDialog v-model="shareDialogVisible" :default-bank-id="shareBankId" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyBank' })
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, FolderOpened, Document, View, Delete, Ticket, Share, Lock, Unlock } from '@element-plus/icons-vue'
import BankCover from '@/components/BankCover/index.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import ReceiveShareDialog from '@/views/front/myQuestion/components/ReceiveShareDialog.vue'
import ShareBankDialog from '@/views/front/myQuestion/components/ShareBankDialog.vue'
import { listMyQuestionBank, delQuestionBank } from '@/api/questionBank/questionBank'

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

const goCreateBank = () => {
  router.push('/front/studio')
}

onMounted(() => {
  fetchBanks()
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

.bank-grid {
  min-height: 400px;
}

.bank-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
  margin-bottom: 20px;
  transition: all 0.3s ease;
  cursor: pointer;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    transform: translateY(-2px);
  }
}

.card-cover {
  position: relative;
  height: 140px;
  overflow: hidden;
  background: #f3f4f6;

  .cover-image {
    width: 100%;
    height: 100%;
  }

  /* 公开 / 私有 标识 */
  .visibility-badge {
    position: absolute;
    top: 8px;
    right: 8px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    line-height: 1.7;
    border-radius: 999px;
    border: 1px solid #e5e7eb;
    background: rgba(255, 255, 255, 0.92);
    color: #6b7280;
    pointer-events: none;

    &.is-public {
      background: #f0f9eb;
      border-color: #e1f3d8;
      color: #67c23a;
    }

    &.is-private {
      background: #fefce8;
      border-color: #e5e0c0;
      color: #947a4a;
    }

    .el-icon {
      font-size: 12px;
    }
  }
}

.card-content {
  padding: 12px 16px;
}

.bank-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: #1f2937;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.bank-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;

  .stat-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: #6b7280;
  }
}

.bank-description {
  font-size: 12px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-actions {
  display: flex;
  /* 放不下就换行，避免按钮被卡片 overflow:hidden 裁掉 */
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #f3f4f6;

  .el-button {
    flex: 1 1 auto;
    min-width: max-content;
    margin-left: 0;
    border-radius: 6px;
  }
}
</style>

