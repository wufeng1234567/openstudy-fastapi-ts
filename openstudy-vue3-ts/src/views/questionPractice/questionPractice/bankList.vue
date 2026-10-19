<!--
  题库练习 · 公开题库
  ============================================================================
  用户 2026-10-19：「题库练习页面的第二行标题『公开题库 共 35 个题库』要移动到
  第一行去，变成『题库练习 · 公开题库  共 35 个题库』」。

  做法与「我的学习」下几个子页完全一致：
    · 顶栏由外壳拼成 `模块 · 子页`（见 `layout/front.vue` 的 `SECOND_LEVEL_BY_ROUTE`）；
    · 计数由本页推到顶栏（`topbar` store），内容区不再占一行；
    · 给 `BankCardGrid` 传 `hide-title`，它就只渲染搜索行。
-->
<template>
  <div class="app-container">
    <BankCardGrid :banks="questionBankList" :loading="loading" title="公开题库" :hide-title="true"
      :show-total-count="true" :show-search="true" :show-refresh="true" :show-pagination="true"
      :show-favorite-status="false" :show-star="false" :show-stats="true" :show-collect-count="true"
      :show-create-time="true" :show-notes="false" :show-study-info="false" :show-description="true"
      :show-favorite-button="true" :show-uncollect-action="false" :use-full-data-search="true"
      :enable-card-click-modal="true" @refresh="getList" @total-change="syncTopbarCount"
      @card-click="handleCardClick" @card-click-confirm="handleCardClickConfirm" @view-detail="viewBankDetail"
      @collect-success="handleCollectSuccess" @uncollect-success="handleUncollectSuccess"
      @empty-action="handleEmptyAction" @page-change="handlePageChange" @size-change="handleSizeChange">
      <template #empty>
        <el-empty description="暂无题库数据">
          <template #image>
            <el-icon size="80">
              <Collection />
            </el-icon>
          </template>
          <el-button type="primary" @click="handleRefresh">
            刷新列表
          </el-button>
        </el-empty>
      </template>
    </BankCardGrid>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontQuestionBankList' })
import { ref, onMounted, onActivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentInstance } from 'vue'
import useUserStore from '@/store/modules/user'
import useTopbarStore from '@/store/modules/topbar'
import { listQuestionBankAll } from '@/api/questionBank/questionBank'
import { listFavoriteBankAll } from '@/api/favoriteBank/favoriteBank'
import BankCardGrid from '@/components/BankCardGrid/BankCardGrid.vue'
import { Collection } from '@element-plus/icons-vue'
import type { UserBankFavorite } from '@/types'

const router = useRouter()
const { proxy } = getCurrentInstance() as any
const userStore = useUserStore()
const topbarStore = useTopbarStore()

const loading = ref(false)
const questionBankList = ref<any[]>([])
const allFavoriteData = ref<UserBankFavorite[]>([])

const getList = () => {
  loading.value = true
  Promise.all([
    // 题库练习 = 公开题库广场：只拉公开题库（私有题库不进这里）
    listQuestionBankAll({ onlyPublic: true }),
    listFavoriteBankAll({ favoriteStatus: 1 })
  ]).then(([bankRes, favRes]: [any, any]) => {
    if (bankRes.code === 200) {
      const banks: any[] = bankRes.data || []
      allFavoriteData.value = favRes.data || []

      const countMap: Record<string | number, number> = {}
      allFavoriteData.value.forEach((favorite: any) => {
        const bankId = favorite.bankId
        countMap[bankId] = (countMap[bankId] || 0) + 1
      })

      const userId = userStore.id
      let userFavoriteBankIds = new Set<string | number>()

      if (userId) {
        const userFavorites = allFavoriteData.value.filter((item: any) => item.userId === userId)
        userFavoriteBankIds = new Set(userFavorites.map((item: any) => item.bankId))
      }

      questionBankList.value = banks.map((bank: any) => ({
        ...bank,
        collectCount: countMap[bank.bankId] || 0,
        isCollected: userId ? userFavoriteBankIds.has(bank.bankId) : false,
        bankName: bank.bankName || `题库ID: ${bank.bankId}`,
        totalQuestions: bank.totalQuestions || 0,
        chapterCount: bank.chapterCount || 0,
        subject: bank.subject || '',
        coverImage: bank.coverImage || '',
        description: bank.description || '',
        createTime: bank.createTime || ''
      }))
    }
    loading.value = false
  }).catch((err: any) => {
    console.error('获取题库失败:', err)
    proxy.$modal.msgError('获取题库失败')
    loading.value = false
  })
}

/* ==================== 顶栏计数 ====================
 *
 * 「共 N 个题库」原来在内容区标题行，现在并进顶栏那一行：
 *   `题库练习 · 公开题库   35 个题库`
 * 搜索 / 筛选之后条数会变，所以计数由 `BankCardGrid` 的 `total-change` 驱动。
 */
function syncTopbarCount(n: number) {
  topbarStore.setCount(Number(n) ? `${n} 个题库` : '')
}

// 本页是 keep-alive 的：离开时清掉，避免把计数带到题库详情 / 刷题页
onBeforeUnmount(() => topbarStore.clear())

/*
 * 刷新时机
 * ----------------------------------------------------------------------------
 * `onMounted` 负责首次加载；`onActivated` 负责「从详情 / 刷题页回来」的刷新。
 * 但 keep-alive 里首次挂载时 onActivated 也会触发一次 —— 用一个标记避免打两次接口。
 */
let loadedOnce = false
onMounted(() => {
  loadedOnce = true
  getList()
})
onActivated(() => {
  if (!loadedOnce) return
  getList()
})

const handleCardClick = (bank: any) => {
}

const handleCardClickConfirm = (bank: any) => {
  viewBankDetail(bank)
}

const viewBankDetail = (bank: any) => {
  // 空题库不允许进入
  if (!bank || !bank.totalQuestions || Number(bank.totalQuestions) === 0) {
    return
  }
  router.push(`/front/questionPractice/${bank.bankId}?from=questionPractice`)
}

const handleCollectSuccess = (targetId: any, type: any) => {
  const userId = userStore.id
  if (userId) {
    allFavoriteData.value.push({
      userId: userId,
      bankId: targetId,
      favoriteStatus: 1
    } as any)
  }
  const listItem = questionBankList.value.find((item: any) => item.id === targetId)
  if (listItem) {
    listItem.isCollected = true
    listItem.collectCount = (listItem.collectCount || 0) + 1
  }
}

const handleUncollectSuccess = (targetId: any, type: any) => {
  const userId = userStore.id
  if (userId) {
    allFavoriteData.value = allFavoriteData.value.filter((item: any) =>
      !(item.userId === userId && item.bankId === targetId)
    )
  }
  const listItem = questionBankList.value.find((item: any) => item.id === targetId)
  if (listItem) {
    listItem.isCollected = false
    listItem.collectCount = Math.max(0, (listItem.collectCount || 0) - 1)
  }
}

const handleEmptyAction = () => {
  proxy.$modal.msgInfo('暂无题库，请等待管理员添加')
}

const handleRefresh = () => {
  getList()
}

const handlePageChange = (page: any) => {
}

const handleSizeChange = (size: any) => {
}
</script>

<style scoped lang="scss">
.app-container {
  width: 100%;
  max-width: 1320px;
  margin: 0 auto;
  padding: 22px 28px 48px;
  box-sizing: border-box;
  min-height: calc(100vh - 100px);
}

@media (max-width: 1024px) {
  .app-container {
    padding: 16px 18px 40px;
  }
}
</style>
