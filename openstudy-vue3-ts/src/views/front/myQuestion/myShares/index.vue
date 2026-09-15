<!-- ==================== 我的分享 ==================== -->
<!-- 题库主查看自己发出的分享：有效期 / 领取人数 / 撤销 -->
<template>
  <div class="my-shares-page">
    <div class="title-section">
      <h2 class="page-title">我的分享</h2>
      <div class="title-right">
        <span class="total-count">共 {{ shareList.length }} 条分享</span>
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
      <el-empty v-if="!loading && shareList.length === 0" description="还没有分享过题库">
        <el-button type="primary" @click="shareDialogVisible = true">分享我的题库</el-button>
      </el-empty>

      <div v-for="item in shareList" :key="item.shareId" class="share-item"
        :class="{ 'is-invalid': !item.effective }">
        <div class="item-main">
          <div class="item-head">
            <h3 class="bank-name">{{ item.bankName || '题库已删除' }}</h3>
            <el-tag v-if="item.status !== '0'" size="small" type="info">已撤销</el-tag>
            <el-tag v-else-if="!item.effective" size="small" type="info">已过期</el-tag>
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Document, User, Clock, Calendar, Share } from '@element-plus/icons-vue'
import { listMyBankShares, revokeBankShare } from '@/api/bankShare/bankShare'
import { buildBankShareUrl, copyToClipboard, formatDateTime } from '@/utils/share'
import ShareBankDialog from '@/views/front/myQuestion/components/ShareBankDialog.vue'

const loading = ref(false)
const shareList = ref<any[]>([])
const shareDialogVisible = ref(false)

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

onMounted(fetchShares)</script>

<style scoped>
.my-shares-page {
  padding: 0 16px;
}

.title-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.title-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1f2937;
}

.total-count {
  font-size: 14px;
  color: #6b7280;
}

.share-list {
  min-height: 300px;
}

.share-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 14px;
  transition: all 0.25s ease;
}

.share-item:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
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
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
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
  color: #6b7280;
}

.item-message {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
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
  color: #9ca3af;
}

.code-value {
  font-family: 'Courier New', monospace;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #409EFF;
}
</style>
