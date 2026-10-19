<template>
  <div class="bank-detail-container" ref="containerRef">
    <div>
      <!-- 头部信息 -->
      <div class="bank-header">
        <!-- 左侧：返回 -->
        <div class="header-left">
          <div class="back-link" @click="goBack">
            <el-icon size="20">
              <ArrowLeft />
            </el-icon>
            <span>返回</span>
          </div>
        </div>

        <!-- 中间：标题（绝对居中） -->
        <div class="header-center">
          <div class="bank-info">
            <div class="bank-title-row">
              <h2 class="bank-name">{{ bank.bankName }}</h2>
              <el-tag v-if="bankSource.isShare" size="small" effect="light"
                :type="bankSource.shareStatus === 'invalid' ? 'info' : 'success'">
                {{ bankSource.shareStatus === 'invalid' ? '来自分享 · 已失效' : '来自分享' }}
              </el-tag>
            </div>
            <div class="bank-stats">
              <!-- 「N 个章节」已移除（用户 2026-10-19：每个题库都显示 0 个章节，不需要） -->
              <span class="stat-item">
                <el-icon>
                  <Document />
                </el-icon>
                <span>{{ bank.totalQuestions || 0 }} 道题目</span>
              </span>
              <span v-if="bank.collectedCount" class="stat-item">
                <el-icon>
                  <Star />
                </el-icon>
                <span>{{ bank.collectedCount }} 人收藏</span>
              </span>
            </div>
          </div>
        </div>

        <!-- 右侧：操作按钮 -->
        <div class="header-right">
          <div class="fav-wrapper">
            <FavoriteButton :type="'bank'" :target-id="bank.bankId" :initial-collected="bank.isCollected" size="small"
              :plain="true" :text="true" collected-button-type="warning" uncollected-button-type="default"
              @collect-success="handleCollectSuccess" @uncollect-success="handleUncollectSuccess" />
          </div>

          <el-button v-if="isCreator" type="info" link class="action-link" @click="editBankQuestions">
            <el-icon>
              <Edit />
            </el-icon> 编辑题库
          </el-button>

          <el-button v-if="isCreator" type="info" link class="action-link" @click="openShareDialog">
            <el-icon>
              <Share />
            </el-icon> 分享
          </el-button>

          <!-- 导出：Word / PDF ×（有答案 / 无答案）。
               下拉而不是四个按钮 —— 顶栏已有收藏/编辑/分享，再堆会把这一行挤爆。 -->
          <el-dropdown
            class="export-dropdown"
            trigger="click"
            :disabled="exporting"
            @command="handleExport"
          >
            <el-button type="info" link class="action-link" :loading="exporting">
              <el-icon>
                <Download />
              </el-icon> 导出
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled class="export-group-label">含答案与解析</el-dropdown-item>
                <el-dropdown-item command="docx:answers">
                  <el-icon><Document /></el-icon> Word（.docx）
                </el-dropdown-item>
                <el-dropdown-item command="pdf:answers">
                  <el-icon><Tickets /></el-icon> PDF
                </el-dropdown-item>
                <el-dropdown-item divided disabled class="export-group-label">无答案（学生卷）</el-dropdown-item>
                <el-dropdown-item command="docx:blank">
                  <el-icon><Document /></el-icon> Word（.docx）
                </el-dropdown-item>
                <el-dropdown-item command="pdf:blank">
                  <el-icon><Tickets /></el-icon> PDF
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-button v-if="!isCreator && bankSource.canCopy" type="primary" link class="action-link" :loading="copyLoading" @click="copyBankToMine">
            <el-icon>
              <CopyDocument />
            </el-icon> 复制为我的题库
          </el-button>
        </div>
      </div>

      <!-- 我的学习模块 -->
      <div class="my-learning">
        <div class="section-header">
          <h3 class="section-title">
            <el-icon>
              <User />
            </el-icon>
            <span>我的学习</span>
          </h3>
          <!-- ✅ 这里改成了 刷题设置 按钮 -->
          <el-button size="small" plain class="rounded-btn" @click="openPracticeSettings">
            <el-icon>
              <Setting />
            </el-icon> 刷题设置
          </el-button>
        </div>
        <el-row :gutter="20">
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="learning-card"
              :class="{ 'compact-mode': isCompactMode, 'empty-card': myMistakesCount === 0 }" @click="goToMyMistakes">
              <div class="card-content" :class="{ 'compact': isCompactMode }">
                <div class="card-icon mistake"><el-icon>
                    <Warning />
                  </el-icon></div>
                <div v-if="!isCompactMode" class="card-info">
                  <div class="card-title">我的错题</div>
                  <div class="card-count" :class="{ 'zero': myMistakesCount === 0 }">{{ myMistakesCount }}</div>
                  <div class="card-unit">道题目</div>
                </div>
                <div v-else class="card-info-compact">
                  <div class="card-count-compact" :class="{ 'zero': myMistakesCount === 0 }">{{ myMistakesCount }}</div>
                </div>
              </div>
              <div v-if="!isCompactMode" class="card-footer">
                <span class="go-text">查看错题</span>
                <el-icon>
                  <ArrowRight />
                </el-icon>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="learning-card"
              :class="{ 'compact-mode': isCompactMode, 'empty-card': myFavoriteCount === 0 }"
              @click="goToMyFavoriteQuestion">
              <div class="card-content" :class="{ 'compact': isCompactMode }">
                <div class="card-icon favorite"><el-icon>
                    <Star />
                  </el-icon></div>
                <div v-if="!isCompactMode" class="card-info">
                  <div class="card-title">我的收藏</div>
                  <div class="card-count" :class="{ 'zero': myFavoriteCount === 0 }">{{ myFavoriteCount }}</div>
                  <div class="card-unit">道题目</div>
                </div>
                <div v-else class="card-info-compact">
                  <div class="card-count-compact" :class="{ 'zero': myFavoriteCount === 0 }">{{ myFavoriteCount }}</div>
                </div>
              </div>
              <div v-if="!isCompactMode" class="card-footer">
                <span class="go-text">查看收藏</span>
                <el-icon>
                  <ArrowRight />
                </el-icon>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="learning-card"
              :class="{ 'compact-mode': isCompactMode, 'empty-card': myMarkedCount === 0 }" @click="goToMyMarked">
              <div class="card-content" :class="{ 'compact': isCompactMode }">
                <div class="card-icon marked"><el-icon>
                    <Flag />
                  </el-icon></div>
                <div v-if="!isCompactMode" class="card-info">
                  <div class="card-title">我的斩题</div>
                  <div class="card-count" :class="{ 'zero': myMarkedCount === 0 }">{{ myMarkedCount }}</div>
                  <div class="card-unit">道题目</div>
                </div>
                <div v-else class="card-info-compact">
                  <div class="card-count-compact" :class="{ 'zero': myMarkedCount === 0 }">{{ myMarkedCount }}</div>
                </div>
              </div>
              <div v-if="!isCompactMode" class="card-footer">
                <span class="go-text">查看斩题</span>
                <el-icon>
                  <ArrowRight />
                </el-icon>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="learning-card"
              :class="{ 'compact-mode': isCompactMode, 'empty-card': myNotesCount === 0 }" @click="goToNotesEditor">
              <div class="card-content" :class="{ 'compact': isCompactMode }">
                <div class="card-icon note"><el-icon>
                    <Notebook />
                  </el-icon></div>
                <div v-if="!isCompactMode" class="card-info">
                  <div class="card-title">我的笔记</div>
                  <div class="card-count" :class="{ 'zero': myNotesCount === 0 }">{{ myNotesCount }}</div>
                  <div class="card-unit">篇笔记</div>
                </div>
                <div v-else class="card-info-compact">
                  <div class="card-count-compact" :class="{ 'zero': myNotesCount === 0 }">{{ myNotesCount }}</div>
                </div>
              </div>
              <div v-if="!isCompactMode" class="card-footer">
                <span class="go-text">编辑笔记</span>
                <el-icon>
                  <ArrowRight />
                </el-icon>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>

      <!-- 专项练习模块 -->
      <div class="special-practice">
        <div class="section-header">
          <div class="section-header-left">
            <h3 class="section-title">
              <el-icon>
                <Trophy />
              </el-icon>
              <span>专项练习</span>
            </h3>
            <div class="section-subtitle">选择练习模式，巩固知识点</div>
          </div>
          <!-- ✅ 这里删除了刷题设置按钮 -->
        </div>
        <el-row :gutter="20">
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="practice-card" :class="{ 'compact-mode': isCompactMode }"
              @click="startPractice('sequential')">
              <div class="practice-icon-wrapper">
                <div class="practice-icon sequential"><el-icon>
                    <Sort />
                  </el-icon></div>
              </div>
              <div class="practice-content">
                <h4>顺序练习</h4>
                <p>按章节顺序逐题练习</p>
                <div class="practice-meta"><span>{{ bank.totalQuestions || 0 }} 题</span></div>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="practice-card" :class="{ 'compact-mode': isCompactMode }"
              @click="startPractice('random')">
              <div class="practice-icon-wrapper">
                <div class="practice-icon random"><el-icon>
                    <Refresh />
                  </el-icon></div>
              </div>
              <div class="practice-content">
                <h4>随机练习</h4>
                <p>随机抽取题目进行练习</p>
                <div class="practice-meta"><span>{{ bank.totalQuestions || 0 }} 题</span></div>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="practice-card" :class="{ 'compact-mode': isCompactMode }"
              @click="startPractice('custom')">
              <div class="practice-icon-wrapper">
                <div class="practice-icon custom"><el-icon>
                    <Setting />
                  </el-icon></div>
              </div>
              <div class="practice-content">
                <h4>自定义练习</h4>
                <p>自由配置顺序、乱序、错题等参数</p>
                <div class="practice-meta"><span>灵活配置</span></div>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12" :md="6" :lg="6" :xl="6">
            <el-card shadow="hover" class="practice-card" :class="{ 'compact-mode': isCompactMode }"
              @click="startPractice('mock')">
              <div class="practice-icon-wrapper">
                <div class="practice-icon exam"><el-icon>
                    <Clock />
                  </el-icon></div>
              </div>
              <div class="practice-content">
                <h4>模拟考试</h4>
                <p>仿真考试环境模拟</p>
                <div class="practice-meta"><span>限时完成</span></div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </div>

    <!-- 分享题库弹窗（公共组件：下拉自由选择题库） -->
    <ShareBankDialog v-model="shareDialogVisible" :default-bank-id="bank.bankId" />

    <PracticeSettings v-model="showPracticeSettings" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentInstance } from 'vue'
import type { PropType } from 'vue'
import useUserStore from '@/store/modules/user'
import { ensureLogin } from '@/utils/loginGuard'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import PracticeSettings from '@/components/PracticeComponent/PracticeSettings.vue'
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
import {
  listFavoriteQuestionAll
} from '@/api/favoriteQuestion/favoriteQuestion'
import {
  listQuestionErrorAll
} from '@/api/questionError/questionError'
import {
  listQuestionMarkedAll
} from '@/api/questionMarked/questionMarked'
import { getNoteQuestionBanksByBankId } from '@/api/noteQuestionBank/noteQuestionBank'
import { checkBankSource } from '@/api/bankShare/bankShare'
import { copyQuestionBank, exportQuestionBank } from '@/api/questionBank/questionBank'
import ShareBankDialog from '@/views/front/myQuestion/components/ShareBankDialog.vue'
import type { QuestionBank } from '@/types'

import {
  Collection, Document, Star, Share, ArrowLeft,
  User, Refresh, Warning, Flag, Notebook, ArrowRight,
  Trophy, Sort, Setting, Aim, Clock, Timer,
  Edit, CopyDocument, Download, Tickets
} from '@element-plus/icons-vue'

const router = useRouter()
const { proxy } = getCurrentInstance() as any
const userStore = useUserStore()
const practiceSettingsStore = usePracticeSettingsStore()
const currentUserId = userStore.id

const showPracticeSettings = ref(false)

// ===== 分享 / 复制 =====
const shareDialogVisible = ref(false)
const copyLoading = ref(false)
// 我与该题库的关系：是否题库主 / 是否来自分享 / 分享是否失效
const bankSource = ref<{ isOwner: boolean; isShare: boolean; shareStatus: string | null; ownerName?: string; canEdit: boolean; canCopy: boolean }>({
  isOwner: false,
  isShare: false,
  shareStatus: null,
  canEdit: false,
  canCopy: false
})

const props = defineProps({
  bank: {
    type: Object as PropType<QuestionBank>,
    required: true
  }
})

const emit = defineEmits(['back', 'collect-success', 'uncollect-success'])

const isCreator = computed(() => {
  const bankUserId = props.bank.userId || props.bank.user_id || props.bank.createById
  if (bankUserId) {
    return Number(bankUserId) === Number(currentUserId)
  }
  if (props.bank.createBy) {
    return props.bank.createBy === userStore.name
  }
  return false
})

const loading = ref(false)
const myMistakesCount = ref(0)
const myFavoriteCount = ref(0)
const myMarkedCount = ref(0)
const myNotesCount = ref(0)
const containerRef = ref<HTMLElement | null>(null)
const containerWidth = ref(0)
let resizeObserver: ResizeObserver | null = null

const isCompactMode = computed(() => {
  return containerWidth.value > 0 && containerWidth.value < 600
})

const updateContainerWidth = () => {
  if (containerRef.value) {
    containerWidth.value = containerRef.value.offsetWidth
  }
}

onMounted(() => {
  updateContainerWidth()
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateContainerWidth()
    })
    resizeObserver.observe(containerRef.value)
  }
  loadStatistics()
  loadBankSource()
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})

const getUserId = () => currentUserId

const editBankQuestions = () => {
  const type = props.bank.isPublic === 0 ? 'public' : 'private'
  router.push({
    path: '/front/studio/create',
    query: { bankId: props.bank.bankId, type }
  })
}

async function loadStatistics() {
  loading.value = true
  try {
    const userId = getUserId()
    const bankId = props.bank.bankId

    const mistakeRes = await listQuestionErrorAll({ userId, bankId })
    myMistakesCount.value = mistakeRes.data?.length || 0

    const favoriteRes = await listFavoriteQuestionAll({ userId, bankId })
    myFavoriteCount.value = favoriteRes.data?.length || 0

    const markedRes = await listQuestionMarkedAll({ userId, bankId })
    myMarkedCount.value = markedRes.data?.length || 0

    const notesRes = await getNoteQuestionBanksByBankId(bankId)
    myNotesCount.value = notesRes.data?.length || 0
  } catch (error) {
    console.error('加载统计数据失败:', error)
    proxy.$modal.msgError('数据加载失败')
  } finally {
    loading.value = false
  }
}

function goToMyMistakes() {
  router.push({ path: '/front/myQuestion/wrongQuestion', query: { bankId: props.bank.bankId } })
}

function goToMyFavoriteQuestion() {
  router.push({ path: '/front/myQuestion/questionCollect', query: { bankId: props.bank.bankId } })
}

function goToMyMarked() {
  router.push({ path: '/front/myQuestion/masteredQuestion', query: { bankId: props.bank.bankId } })
}

function goToNotesEditor() {
  router.push({ path: '/front/myQuestion/myNotes', query: { bankId: props.bank.bankId } })
}

async function startPractice(type: string) {
  if (!props.bank.totalQuestions || props.bank.totalQuestions === 0) {
    return
  }
  if (!(await ensureLogin('刷题'))) return
  router.push(`/front/questionPractice/${props.bank.bankId}/practice/${type}?bankName=${encodeURIComponent(props.bank.bankName || '')}`)
}

function openPracticeSettings() {
  practiceSettingsStore.setCurrentBank(props.bank.bankId, props.bank.bankName)
  showPracticeSettings.value = true
}

/** 查询我与该题库的关系：决定「分享 / 复制」等按钮显示与来源标识 */
async function loadBankSource() {
  try {
    const res: any = await checkBankSource(props.bank.bankId)
    if (res.code === 200 && res.data) {
      bankSource.value = { ...bankSource.value, ...res.data }
    }
  } catch (e) {
    // 关系查询失败不阻塞页面，回退到 isCreator 判定
    bankSource.value.isOwner = isCreator.value
    bankSource.value.canEdit = isCreator.value
    bankSource.value.canCopy = !isCreator.value
  }
}

/** 打开分享弹窗（仅题库主）—— 弹窗内可下拉自由选择题库，默认当前题库 */
function openShareDialog() {
  if (!isCreator.value) return
  shareDialogVisible.value = true
}

/* ===== 导出 Word / PDF =====
 * 后端起见 `app/api/v1/bank_export.py`：图文按 HTML 原始顺序输出，
 * 图片等比缩放后嵌在原位置（不堆到文末）。
 * 导出可能耗时几秒（题库含几十张图），期间用 loading 锁住按钮，避免重复点。
 */
const exporting = ref(false)

/**
 * 导出 Word / PDF
 *
 * command 形如 `docx:answers` / `pdf:blank` —— 前半是格式，后半是版本。
 * 用户 2026-10-19 要求「无论 word 还是 pdf 都要支持有答案和无答案两种」。
 */
async function handleExport(command: string) {
  if (exporting.value) return
  const [format, variant] = String(command || '').split(':')
  if (format !== 'docx' && format !== 'pdf') return
  const withAnswers = variant !== 'blank'

  if (!(await ensureLogin('导出题库'))) return

  exporting.value = true
  try {
    const { blob, filename, error } = await exportQuestionBank(
      props.bank.bankId,
      format as 'docx' | 'pdf',
      withAnswers
    )
    if (error || !blob) {
      proxy.$modal.msgError(error || '导出失败')
      return
    }
    // 触发浏览器下载
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || `题库-${props.bank.bankId}${withAnswers ? '' : '-无答案'}.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // 立刻 revoke 在部分浏览器（Safari）会打断下载，延后一点
    setTimeout(() => URL.revokeObjectURL(url), 5000)
    const label = `${format === 'docx' ? 'Word' : 'PDF'}${withAnswers ? '' : '（无答案）'}`
    proxy.$modal.msgSuccess(`已导出为 ${label} 文件`)
  } catch (e: any) {
    // 后端业务错误（403 无权 / 500 生成失败）走 axios 的 reject
    const msg = e?.response?.data?.msg || e?.message || '导出失败'
    proxy.$modal.msgError(msg)
  } finally {
    exporting.value = false
  }
}

/** 复制题库为我的新题库（生成独立副本，可自由编辑） */
async function copyBankToMine() {
  if (copyLoading.value) return
  if (!(await ensureLogin('复制题库'))) return
  try {
    await proxy.$modal.confirm(
      `将「${props.bank.bankName}」复制一份到「我的题库」？复制后可自由编辑，不影响原题库。`,
      '复制题库',
      { confirmButtonText: '复制', cancelButtonText: '取消', type: 'info' }
    )
  } catch (e) {
    return
  }

  copyLoading.value = true
  try {
    const res: any = await copyQuestionBank(props.bank.bankId)
    if (res.code === 200 && res.data) {
      proxy.$modal.msgSuccess(`已复制为《${res.data.bankName}》，可在「我的题库」中编辑`)
    } else {
      proxy.$modal.msgError(res.msg || '复制失败')
    }
  } catch (e) {
    proxy.$modal.msgError('复制失败')
  } finally {
    copyLoading.value = false
  }
}

const handleCollectSuccess = (targetId: number | string, type: string) => emit('collect-success', targetId, type)
const handleUncollectSuccess = (targetId: number | string, type: string) => emit('uncollect-success', targetId, type)
function goBack() {
  emit('back')
}
</script>

<style scoped>
.bank-detail-container {
  padding: 20px;
}

/* --- 头部 --- */
.bank-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 20px;
  margin-bottom: 30px;
  border-bottom: 1px solid #f0f0f0;
  position: relative;
  min-height: 80px;
}

/* 左侧：返回 */
.header-left {
  display: flex;
  align-items: center;
  flex: 1;
}

.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
}

.back-link:hover {
  color: #333;
}

/* 中间：标题 - 绝对居中 */
.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.bank-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.bank-name {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
  white-space: nowrap;
}

.bank-stats {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 右侧：操作按钮 */
.header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  flex: 1;
}

/* 导出下拉的分组标题（「含答案与解析」/「无答案（学生卷）」）：
   ⚠️ 不能写在这个 scoped 块里 —— `el-dropdown-menu` 会 teleport 到 body，
   scoped 的 `[data-v-xxx]` 属性加不到那些节点上。实际样式见文件末尾的非 scoped 块。 */

.action-link {
  color: #6b7280;
  font-weight: 400;
}

.action-link:hover {
  color: #409EFF;
}

.fav-wrapper {
  display: flex;
  align-items: center;
}

.fav-wrapper :deep(.el-button) {
  border: none;
  background: transparent !important;
  padding: 0;
}

/* 响应式适配 */
@media (max-width: 768px) {
  .bank-header {
    flex-direction: column;
    align-items: flex-start;
    min-height: auto;
    gap: 12px;
  }

  .header-center {
    position: static;
    transform: none;
    width: 100%;
    align-items: flex-start;
    padding: 8px 0;
  }

  .bank-info {
    align-items: flex-start;
  }

  .bank-name {
    font-size: 20px;
  }

  .bank-stats {
    flex-wrap: wrap;
    gap: 10px;
  }

  .header-left {
    width: 100%;
  }

  .header-right {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

/* 左侧：返回 */
.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
  flex-shrink: 0;
}

.back-link:hover {
  color: #333;
}

/* 中间：标题居中 */
.bank-title {
  display: flex;
  justify-content: center;
  flex: 1;
  padding: 0 20px;
}

.bank-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.bank-name {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
}

.bank-stats {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 右侧：操作按钮 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.action-link {
  color: #6b7280;
  font-weight: 400;
}

.action-link:hover {
  color: #409EFF;
}

.fav-wrapper {
  display: flex;
  align-items: center;
}

.fav-wrapper :deep(.el-button) {
  border: none;
  background: transparent !important;
  padding: 0;
}

.header-left-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
}

/* 返回按钮独立一行，靠左上角 */
.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
  margin-bottom: 8px;
}

.back-link:hover {
  color: #333;
}

.bank-title {
  display: flex;
  align-items: flex-start;
  width: 100%;
}

.bank-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bank-name {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
}

.bank-stats {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  align-self: flex-end;
}

.action-link {
  color: #6b7280;
  font-weight: 400;
}

.action-link:hover {
  color: #409EFF;
}

.fav-wrapper {
  display: flex;
  align-items: center;
}

.fav-wrapper :deep(.el-button) {
  border: none;
  background: transparent !important;
  padding: 0;
}

.header-left-wrapper {
  display: flex;
  align-items: center;
  gap: 20px;
}

.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
}

.back-link:hover {
  color: #333;
}

.bank-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.bank-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  color: #6b7280;
  font-size: 14px;
}

.bank-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bank-name {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1f2937;
}

.bank-stats {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.action-link {
  color: #6b7280;
  font-weight: 400;
}

.action-link:hover {
  color: #409EFF;
}

.fav-wrapper {
  display: flex;
  align-items: center;
}

.fav-wrapper :deep(.el-button) {
  border: none;
  background: transparent !important;
  padding: 0;
}

/* --- 我的学习 --- */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.section-header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 18px;
  color: #1f2937;
}

.section-title .el-icon {
  color: #6b7280;
}

.section-subtitle {
  color: #9ca3af;
  font-size: 13px;
  margin-left: 28px;
}

.rounded-btn {
  border-radius: 8px !important;
}

.learning-card {
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  margin-bottom: 20px;
}

.learning-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #d1d5db;
}

.learning-card.empty-card {
  opacity: 0.8;
}

.learning-card.empty-card:hover {
  transform: none;
  box-shadow: none;
}

.card-content {
  display: flex;
  align-items: center;
  padding: 20px;
}

.card-icon {
  width: 50px;
  height: 50px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 24px;
  color: white;
  flex-shrink: 0;
}

.card-icon.mistake {
  background-color: #f56c6c;
}

.card-icon.favorite {
  background-color: #e6a23c;
}

.card-icon.marked {
  background-color: #f59e0b;
}

.card-icon.note {
  background-color: #67c23a;
}

.card-info {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 4px;
}

.card-count {
  font-size: 32px;
  font-weight: 600;
  color: #303133;
  line-height: 1;
}

.card-count.zero {
  color: #c0c4cc;
}

.card-unit {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

/* 卡片底部 - 去掉背景，左对齐，灰色文字 */
.card-footer {
  background: transparent;
  border-top: none;
  padding: 12px 20px 8px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  /* ✅ 改为 center 实现水平居中 */
  gap: 4px;
  color: #6b7280;
  font-size: 13px;
  transition: color 0.2s;
}

.card-footer:hover {
  color: #409EFF;
}

/* 紧凑模式适配 */
.learning-card.compact-mode .card-content {
  flex-direction: column;
  padding: 16px;
  justify-content: center;
  align-items: center;
}

.learning-card.compact-mode .card-icon {
  margin-right: 0;
  margin-bottom: 12px;
  width: 48px;
  height: 48px;
}

.learning-card.compact-mode .card-info-compact {
  text-align: center;
}

.learning-card.compact-mode .card-count-compact {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}

.learning-card.compact-mode .card-count-compact.zero {
  color: #c0c4cc;
}

/* --- 专项练习 --- */
.practice-card {
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid #e4e7ed;
  border-radius: 16px;
  margin-bottom: 20px;
  min-height: 200px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.practice-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #d1d5db;
}

.practice-icon-wrapper {
  margin-bottom: 12px;
}

.practice-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: white;
  margin: 0 auto;
  flex-shrink: 0;
}

.practice-icon.sequential {
  background-color: rgba(64, 158, 255, 0.9);
}

.practice-icon.random {
  background-color: rgba(245, 108, 108, 0.9);
}

.practice-icon.custom {
  background-color: rgba(103, 194, 58, 0.9);
}

.practice-icon.exam {
  background-color: rgba(230, 162, 60, 0.9);
}

.practice-content {
  text-align: center;
  width: 100%;
}

.practice-content h4 {
  margin: 0 0 4px 0;
  font-size: 16px;
  color: #303133;
}

.practice-content p {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #909399;
  word-break: break-word;
  line-height: 1.4;
}

.practice-meta {
  font-size: 12px;
  color: #c0c4cc;
}

.practice-card.compact-mode {
  min-height: auto;
  padding: 16px;
}

.practice-card.compact-mode .practice-icon {
  width: 40px;
  height: 40px;
  font-size: 20px;
}

.practice-card.compact-mode .practice-content p {
  display: none;
}

/* --- 响应式 --- */
@media (max-width: 768px) {
  .bank-header {
    flex-direction: column;
    gap: 16px;
  }

  .header-left-wrapper {
    flex-direction: row;
    align-items: flex-start;
    width: 100%;
  }

  .bank-title {
    flex-direction: column;
    align-items: flex-start;
  }

  .bank-stats {
    flex-wrap: wrap;
    gap: 10px;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .learning-card,
  .practice-card {
    margin-bottom: 16px;
  }
}

/* 动画 */
.learning-card,
.practice-card {
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

:deep(.el-progress-bar__inner) {
  background-color: #409EFF;
}

/* ===== 分享 / 复制 ===== */
.bank-title-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.bank-title-row .bank-name {
  margin: 0;
}

</style>

<!--
  导出下拉的分组标题样式：
  ⚠️ 必须用**非 scoped** 样式 —— `el-dropdown-menu` 由 Element Plus teleport 到 body，
  scoped 的 `[data-v-xxx]` 属性不会加到那些节点上，规则对它们无效
  （与 LatexRenderer 的表格样式同一个道理）。
-->
<style>
.export-dropdown-popper .el-dropdown-menu__item.export-group-label,
.el-dropdown-menu__item.export-group-label {
  font-size: 12px;
  color: #9ca3af;
  cursor: default;
  padding-top: 6px;
  padding-bottom: 2px;
  min-height: auto;
  line-height: 1.4;
}

/* disabled 的 el-dropdown-item 默认会变半透明，分组标题不该"看起来坏了" */
.el-dropdown-menu__item.export-group-label.is-disabled {
  color: #9ca3af;
  opacity: 1;
}
</style>