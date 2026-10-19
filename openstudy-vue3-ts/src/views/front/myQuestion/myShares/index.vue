<!--
  我的分享（分享列表）
  ============================================================================
  用户 2026-10-19：「我的分享也没的重构，给他作为一个子路由，转移到题库管理内部去，
  并且配套对应的搜索组件，尽量让他们样式统一」。

  所以它现在是「题库管理」的**第三个分组**（我的题库 / 题库收藏 / 我的分享），
  与另外两个分组共用同一个搜索框与同一个筛选面板。

  ## 两种用法

  · `embedded = true`（在「题库管理」里）：不渲染自己的操作条，
    搜索框 / 刷新 / 分享按钮都由外层提供，这里只渲染列表；
    外部通过 props 传 `keyword` / `statuses` / `createRange`，本组件内部过滤。

  · 独立访问（`embedded = false`）：保留原来的操作条，行为与改造前一致。
    旧路由 `/front/myQuestion/myShares` 现在会重定向到
    `/front/myQuestion/myBank?tab=share`，所以这条路径基本只剩兜底作用。

  ## 为什么过滤放在组件内部

  与 `MyQuestion` / `MyNotes` 的内嵌模式一致：外层只给"条件"，
  列表与总数由数据拥有方自己算 —— 这样 `total-change` 报出去的数字
  永远和用户看到的行数一致，不会出现"顶栏说 5 条、列表里有 3 条"。
-->
<template>
  <div class="my-shares-page" :class="{ 'is-embedded': embedded }">
    <!--
      操作条（仅独立访问时出现）
      内嵌模式下「分享我的题库」「刷新」由外层的搜索行提供，这里不再重复。
    -->
    <div v-if="!embedded" class="title-section is-actions-only">
      <div class="title-right">
        <el-button type="primary" plain @click="shareDialogVisible = true">
          <el-icon><Share /></el-icon>
          分享我的题库
        </el-button>
        <el-button @click="fetchShares">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <div class="share-list" v-loading="loading">
      <el-empty v-if="!loading && filteredList.length === 0" :description="emptyText">
        <el-button v-if="!hasFilter" type="primary" @click="shareDialogVisible = true">
          分享我的题库
        </el-button>
        <span v-else class="empty-hint">当前筛选条件下没有匹配的分享</span>
      </el-empty>

      <div v-for="item in filteredList" :key="item.shareId" class="share-item"
        :class="{ 'is-invalid': !item.effective }">
        <div class="item-main">
          <div class="item-head">
            <h3 class="bank-name">{{ item.bankName || '题库已删除' }}</h3>
            <el-tag v-if="statusOf(item) === 'revoked'" size="small" type="info">已撤销</el-tag>
            <el-tag v-else-if="statusOf(item) === 'expired'" size="small" type="info">已过期</el-tag>
            <el-tag v-else size="small" type="success">有效</el-tag>
          </div>
          <div class="item-meta">
            <span class="meta-item">
              <el-icon><Document /></el-icon>
              {{ item.totalQuestions || 0 }} 题
            </span>
            <span class="meta-item">
              <el-icon><User /></el-icon>
              已领取 {{ item.receiveCount || 0 }} 人
            </span>
            <span class="meta-item">
              <el-icon><Clock /></el-icon>
              {{ item.expireTime ? '有效期至 ' + formatDateTime(item.expireTime) : '永久有效' }}
            </span>
            <span class="meta-item">
              <el-icon><Calendar /></el-icon>
              创建于 {{ formatDateTime(item.createTime) }}
            </span>
          </div>
          <div v-if="item.message" class="item-message">「{{ item.message }}」</div>
        </div>

        <div class="item-actions">
          <div class="code-box">
            <span class="code-label">分享码</span>
            <span class="code-value">{{ item.shareCode }}</span>
          </div>
          <el-button size="small" :disabled="!item.effective" @click="copyCode(item)">复制分享码</el-button>
          <el-button size="small" :disabled="!item.effective" @click="copyLink(item)">复制链接</el-button>
          <el-button size="small" type="danger" plain :disabled="item.status !== '0'" @click="revoke(item)">
            撤销
          </el-button>
        </div>
      </div>
    </div>

    <!-- 分享题库弹窗（下拉自由选择题库） -->
    <ShareBankDialog v-model="shareDialogVisible" @created="fetchShares" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyShares' })
import { computed, ref, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Document, User, Clock, Calendar, Share } from '@element-plus/icons-vue'
import { listMyBankShares, revokeBankShare } from '@/api/bankShare/bankShare'
import { buildBankShareUrl, copyToClipboard, formatDateTime } from '@/utils/share'
import ShareBankDialog from '@/views/front/myQuestion/components/ShareBankDialog.vue'

/* ==================== props / emits ====================
 *
 * 内嵌到「题库管理」时，搜索条件由外层传进来（共用那一个搜索框与筛选面板）。
 * `embedded` 只是控制操作条是否渲染；过滤逻辑两边都用同一份。
 */
const props = withDefaults(
  defineProps<{
    /** 被「题库管理」内嵌：不渲染自己的操作条 */
    embedded?: boolean
    /** 搜索关键词（按题库名匹配） */
    keyword?: string
    /** 状态多选：effective / expired / revoked */
    statuses?: string[]
    /** 创建时间范围 [start, end]（YYYY-MM-DD） */
    createRange?: string[] | null
  }>(),
  {
    embedded: false,
    keyword: '',
    statuses: () => [],
    createRange: null
  }
)

const emit = defineEmits<{
  (e: 'total-change', payload: { total: number; loading: boolean }): void
}>()

const loading = ref(false)
const shareList = ref<any[]>([])
const shareDialogVisible = ref(false)

/* ==================== 状态归类 ==================== */

type ShareStatus = 'effective' | 'expired' | 'revoked'

/**
 * 分享状态
 * `status !== '0'` 表示已撤销（后端字段），否则看 `effective` 判断是否过期。
 * 三个状态互斥，筛选按它来。
 */
const statusOf = (item: any): ShareStatus => {
  if (String(item.status) !== '0') return 'revoked'
  if (!item.effective) return 'expired'
  return 'effective'
}

/* ==================== 过滤 ==================== */

/** 是否设置了任何搜索/筛选条件（空态文案要区分"没有分享"和"筛不出来"） */
const hasFilter = computed(
  () =>
    !!props.keyword?.trim() ||
    (props.statuses?.length || 0) > 0 ||
    (props.createRange?.length === 2)
)

const filteredList = computed(() => {
  let list = shareList.value

  // 关键词：按题库名
  const kw = props.keyword?.trim().toLowerCase()
  if (kw) {
    list = list.filter((it) => String(it.bankName || '').toLowerCase().includes(kw))
  }

  // 状态（多选，命中任一）
  if (props.statuses?.length) {
    list = list.filter((it) => props.statuses.includes(statusOf(it)))
  }

  // 创建时间范围
  if (props.createRange?.length === 2) {
    const [start, end] = props.createRange
    const startTs = new Date(`${start} 00:00:00`).getTime()
    const endTs = new Date(`${end} 23:59:59`).getTime()
    list = list.filter((it) => {
      if (!it.createTime) return false
      const ts = new Date(it.createTime).getTime()
      return ts >= startTs && ts <= endTs
    })
  }

  return list
})

const emptyText = computed(() =>
  hasFilter.value ? '没有匹配的分享' : '还没有分享过题库'
)

/* ==================== 条数上报 ====================
 *
 * 顶层（「题库管理」）据此把「N 条分享」推到顶栏、并显示分组角标。
 * 带上 loading 是为了让外层区分「还不知道」和「确实是 0 条」——
 * 裸数字会让顶栏在加载过程中闪出中间的 0（用户 2026-10-19 反馈过）。
 */
watch(
  [() => filteredList.value.length, loading],
  () => {
    emit('total-change', {
      total: filteredList.value.length,
      loading: loading.value
    })
  },
  { immediate: true }
)

/* ==================== 数据 ==================== */

const fetchShares = async () => {
  loading.value = true
  try {
    const res: any = await listMyBankShares()
    if (res.code === 200) {
      shareList.value = res.data || []
    } else {
      ElMessage.error(res.msg || '获取分享失败')
    }
  } catch (e) {
    ElMessage.error('获取分享失败')
  } finally {
    loading.value = false
  }
}

/* ==================== 动作 ==================== */

const copyCode = (item: any) => {
  copyToClipboard(item.shareCode)
    .then(() => ElMessage.success('分享码已复制'))
    .catch(() => ElMessage.error('复制失败，请手动复制'))
}

const copyLink = (item: any) => {
  copyToClipboard(buildBankShareUrl(item.shareToken))
    .then(() => ElMessage.success('分享链接已复制'))
    .catch(() => ElMessage.error('复制失败，请手动复制'))
}

const revoke = async (item: any) => {
  try {
    await ElMessageBox.confirm(
      `撤销后，已领取该分享的用户将看到「已失效」标识且无法再领取。确定撤销《${item.bankName}》的分享吗？`,
      '撤销分享',
      { confirmButtonText: '撤销', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return
  }
  try {
    const res: any = await revokeBankShare(item.shareId)
    if (res.code === 200) {
      ElMessage.success('已撤销')
      fetchShares()
    } else {
      ElMessage.error(res.msg || '撤销失败')
    }
  } catch (e) {
    ElMessage.error('撤销失败')
  }
}

/* ==================== 对外暴露 ====================
 *
 * 内嵌时「分享我的题库」按钮在外层（与刷新按钮同一行），
 * 点它只是要把这里的弹窗打开，所以暴露一个方法，不复制一份弹窗到外层。
 */
function openShareDialog() {
  shareDialogVisible.value = true
}

defineExpose({ refresh: fetchShares, openShareDialog })

onMounted(fetchShares)
</script>

<style scoped>
.my-shares-page {
  padding: 0;
}

/* 内嵌模式：外层已有搜索行，这里直接从列表开始 */
.my-shares-page.is-embedded {
  padding: 0;
}

.title-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  /* 只剩操作按钮时右对齐并收紧下边距 —— 否则左侧会留一块空白，像"标题没渲染出来" */
  &.is-actions-only {
    justify-content: flex-end;
    margin-bottom: 12px;
  }
}

.title-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.share-list {
  min-height: 240px;
}

.empty-hint {
  font-size: 13px;
  color: var(--os-text-4, #9ca3af);
}

.share-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  background: #fff;
  border: 1px solid var(--os-border-soft, #e5e7eb);
  border-radius: var(--os-radius, 12px);
  padding: 16px 20px;
  margin-bottom: 12px;
  transition: box-shadow var(--ds-duration-base) var(--ds-ease-in-out),
    border-color var(--ds-duration-base) var(--ds-ease-in-out);
}

.share-item:hover {
  border-color: var(--os-border-strong, #d1d5db);
  box-shadow: var(--os-shadow-2, 0 4px 16px rgba(0, 0, 0, 0.08));
}

.share-item.is-invalid {
  opacity: 0.72;
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.bank-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--os-text-3, #6b7280);
}

.item-message {
  margin-top: 8px;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.code-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-right: 6px;
}

.code-label {
  font-size: 11px;
  color: var(--os-text-4, #9ca3af);
}

.code-value {
  font-family: 'Courier New', monospace;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--os-primary, #409eff);
}
</style>
