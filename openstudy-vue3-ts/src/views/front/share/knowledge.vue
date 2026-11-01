<template>
  <div class="kb-share-page">
    <div class="kb-share-card" v-loading="loading">
      <el-result v-if="errorMsg" icon="warning" title="分享不可用" :sub-title="errorMsg">
        <template #extra>
          <el-button @click="goHome">返回首页</el-button>
          <el-button type="primary" @click="goWorkspace">我的资料</el-button>
        </template>
      </el-result>

      <template v-else-if="info">
        <div class="kb-share-head">
          <div class="kb-share-icon">AI</div>
          <div class="kb-share-meta">
            <h2>{{ info.kbName }}</h2>
            <div class="kb-share-tags">
              <el-tag size="small" type="info">{{ info.docCount || 0 }} 份资料</el-tag>
              <el-tag size="small" type="warning" effect="light">完整副本</el-tag>
            </div>
            <p>来自 <b>{{ info.ownerName || '匿名用户' }}</b> 的知识库分享</p>
            <p class="kb-share-expire">有效期：{{ info.expireTime ? formatTime(info.expireTime) : '永久有效' }}</p>
            <p v-if="info.message" class="kb-share-message">「{{ info.message }}」</p>
          </div>
        </div>

        <el-alert class="kb-share-alert" type="info" :closable="false" show-icon
          title="领取后会在你的「我的资料」里生成一份完整副本，可以继续编辑、检索和添加资料。" />

        <div class="kb-share-actions">
          <template v-if="info.isOwner">
            <el-button type="primary" @click="goOrigin">这是你自己分享的知识库，去查看</el-button>
          </template>
          <template v-else-if="info.received">
            <el-button type="success" :icon="Select" disabled>已领取</el-button>
            <el-button type="primary" @click="goReceived">去我的资料</el-button>
          </template>
          <template v-else>
            <el-button type="primary" size="large" :loading="receiving" @click="doReceive">
              <el-icon><Download /></el-icon>
              领取并保存副本
            </el-button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontKnowledgeShare' })
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Select } from '@element-plus/icons-vue'
import { getKbShareInfoByToken, receiveKbShare } from '@/api/kbShare/kbShare'
import { getToken } from '@/utils/auth'
import { ensureLogin } from '@/utils/loginGuard'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const receiving = ref(false)
const info = ref<any>(null)
const errorMsg = ref('')

function formatTime(value: string) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function fetchInfo() {
  const token = String(route.params.token || '')
  if (!token) {
    errorMsg.value = '分享链接无效'
    return
  }
  if (!getToken()) {
    router.replace({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  loading.value = true
  try {
    const res: any = await getKbShareInfoByToken(token)
    if (res.code === 200 && res.data) info.value = res.data
    else errorMsg.value = res.msg || '分享不存在或已失效'
  } catch {
    errorMsg.value = '分享加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function doReceive() {
  if (receiving.value) return
  if (!(await ensureLogin('领取知识库分享'))) return
  receiving.value = true
  try {
    const res: any = await receiveKbShare({ token: String(route.params.token || '') })
    if (res.code === 200 && res.data?.kbId) {
      ElMessage.success('已复制到你的「我的资料」')
      goKb(res.data.kbId)
    } else {
      ElMessage.error(res.msg || '领取失败，请稍后重试')
    }
  } catch {
    // request 拦截器已提示
  } finally {
    receiving.value = false
  }
}

function goKb(kbId: number) {
  router.push(`/front/workspace?kbId=${kbId}`)
}
function goReceived() {
  if (info.value?.newKbId) goKb(info.value.newKbId)
  else goWorkspace()
}
function goOrigin() {
  if (info.value?.kbId) goKb(info.value.kbId)
  else goWorkspace()
}
function goWorkspace() {
  router.push('/front/workspace')
}
function goHome() {
  router.push('/front/index')
}

onMounted(fetchInfo)
</script>

<style scoped>
.kb-share-page {
  display: flex;
  justify-content: center;
  padding: 40px 16px;
}

.kb-share-card {
  width: 100%;
  max-width: 620px;
  min-height: 260px;
  padding: 28px;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: #fff;
}

.kb-share-head {
  display: flex;
  gap: 18px;
}

.kb-share-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 104px;
  height: 104px;
  flex: 0 0 104px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eef4ff, #dce8ff);
  color: #2f5fd0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 1px;
}

.kb-share-meta {
  min-width: 0;
  flex: 1;
}

.kb-share-meta h2 {
  margin: 0 0 9px;
  overflow: hidden;
  color: #1f2937;
  font-size: 20px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-share-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.kb-share-meta p {
  margin: 7px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.kb-share-meta b {
  color: #374151;
}

.kb-share-expire {
  font-size: 12px !important;
}

.kb-share-message {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  color: #4b5563 !important;
  font-size: 12px !important;
}

.kb-share-alert {
  margin-top: 20px;
}

.kb-share-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 22px;
}
</style>
