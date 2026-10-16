<!-- ==================== 题库分享落地页 ==================== -->
<!-- 用户 B 通过分享链接打开本页：展示题库摘要 -> 领取（写入收藏，只读） -> 前往题库 -->
<template>
  <div class="share-page">
    <div class="share-card" v-loading="loading">
      <!-- 校验失败 / 失效 -->
      <el-result v-if="errorMsg" icon="warning" title="分享不可用" :sub-title="errorMsg">
        <template #extra>
          <el-button @click="goHome">返回首页</el-button>
          <el-button type="primary" @click="goMyCollect">我的题库收藏</el-button>
        </template>
      </el-result>

      <!-- 分享详情 -->
      <template v-else-if="info">
        <div class="share-header">
          <div class="cover">
            <BankCover :cover-image="info.coverImage" :bank-name="info.bankName" :subject="info.subject" />
          </div>
          <div class="meta">
            <h2 class="bank-name">{{ info.bankName }}</h2>
            <div class="tag-row">
              <el-tag v-if="info.subject" size="small" type="info">{{ info.subject }}</el-tag>
              <el-tag size="small" type="warning" effect="light">只读分享</el-tag>
            </div>
            <div class="stats">
              <span class="stat"><el-icon><Document /></el-icon>{{ info.totalQuestions || 0 }} 道题目</span>
            </div>
            <div class="owner-line">
              来自 <b>{{ info.ownerName || '匿名用户' }}</b> 的分享
            </div>
            <div class="expire-line">
              有效期：{{ info.expireTime ? formatTime(info.expireTime) : '永久有效' }}
            </div>
            <div v-if="info.message" class="share-message">「{{ info.message }}」</div>
          </div>
        </div>

        <el-alert class="perm-alert" type="info" :closable="false" show-icon
          title="获取后题库会加入你的「题库收藏」（只读，可随时刷题）；想改题目内容，可在题库详情里点「复制为我的题库」自己留一份。" />

        <div class="share-actions">
          <template v-if="info.isOwner">
            <el-button type="primary" @click="goBank">这是你自己分享的题库，去查看</el-button>
          </template>
          <template v-else-if="info.received">
            <el-button type="success" :icon="Select" disabled>已加入收藏</el-button>
            <el-button type="primary" @click="goBank">去刷题</el-button>
          </template>
          <template v-else>
            <el-button type="primary" size="large" :loading="receiving" @click="doReceive">
              <el-icon><Download /></el-icon>
              获取并加入收藏
            </el-button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontBankShare' })
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, Download, Select } from '@element-plus/icons-vue'
import BankCover from '@/components/BankCover/index.vue'
import { getShareInfoByToken, receiveBankShare } from '@/api/bankShare/bankShare'
import { getToken } from '@/utils/auth'
import { ensureLogin } from '@/utils/loginGuard'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const receiving = ref(false)
const info = ref<any>(null)
const errorMsg = ref('')

const formatTime = (timeStr: string) => {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  if (Number.isNaN(d.getTime())) return timeStr
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const fetchInfo = async () => {
  const token = route.params.token as string
  if (!token) {
    errorMsg.value = '分享链接无效'
    return
  }
  // 未登录先去登录，登录后回跳本页
  if (!getToken()) {
    router.replace({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  loading.value = true
  try {
    const res: any = await getShareInfoByToken(token)
    if (res.code === 200 && res.data) {
      info.value = res.data
    } else {
      errorMsg.value = res.msg || '分享不存在或已失效'
    }
  } catch (e) {
    errorMsg.value = '分享加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

const doReceive = async () => {
  if (receiving.value) return
  if (!(await ensureLogin('领取分享题库'))) return
  receiving.value = true
  try {
    const res: any = await receiveBankShare({ token: route.params.token as string })
    if (res.code === 200 && res.data) {
      const msgMap: Record<string, string> = {
        created: '已加入你的「题库收藏」',
        restored: '已重新加入你的「题库收藏」',
        exists: '该题库已在你的「题库收藏」中'
      }
      ElMessage.success(msgMap[res.data.resultStatus] ||
        (res.data.alreadyReceived ? '该题库已在你的收藏中' : '已加入你的题库收藏'))
      goBank()
    } else {
      ElMessage.error(res.msg || '领取失败，请稍后重试')
    }
  } catch (e) {
    console.warn('[share] 领取失败（业务提示已由 request 拦截器给出，不再重复弹窗）:', e)
  } finally {
    receiving.value = false
  }
}

const goBank = () => {
  const bankId = info.value?.bankId
  if (!bankId) {
    goMyCollect()
    return
  }
  router.push(`/front/questionPractice/${bankId}?from=myLearning`)
}

const goMyCollect = () => router.push('/front/myQuestion/bankCollect')
const goHome = () => router.push('/front/index')

onMounted(fetchInfo)
</script>

<style scoped>
.share-page {
  display: flex;
  justify-content: center;
  padding: 40px 16px;
}

.share-card {
  width: 100%;
  max-width: 620px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 28px;
  min-height: 260px;
}

.share-header {
  display: flex;
  gap: 20px;
}

.cover {
  width: 120px;
  height: 120px;
  flex: 0 0 120px;
  border-radius: 12px;
  overflow: hidden;
  background: #f3f4f6;
}

.meta {
  flex: 1;
  min-width: 0;
}

.bank-name {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.stats .stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #6b7280;
}

.owner-line,
.expire-line {
  font-size: 13px;
  color: #6b7280;
  margin-top: 8px;
}

.owner-line b {
  color: #374151;
}

.share-message {
  margin-top: 10px;
  font-size: 13px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 8px;
  padding: 8px 12px;
}

.perm-alert {
  margin: 20px 0;
}

.share-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
