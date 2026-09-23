<!-- ==================== 分享题库弹窗（公共组件） ==================== -->
<!-- 题库主使用：下拉自由选择要分享的题库（默认当前题库）→ 生成分享码 / 分享链接 -->
<!-- 用于：① 题库详情页「分享」按钮  ② 我的分享页「分享我的题库」按钮 -->
<template>
  <el-dialog v-model="visible" title="分享题库" width="480px" append-to-body :close-on-click-modal="false">
    <div v-if="!shareResult" class="share-form">
      <p class="share-tip">
        一次只分享<b>一个</b>题库，可在下方下拉框里自由选择你名下的题库。
        对方领取后，该题库会加入他的「题库收藏」（只读，不能编辑），想改内容需自己「复制为我的题库」。
      </p>
      <el-form label-width="76px">
        <el-form-item label="分享题库">
          <el-select v-model="form.bankId" placeholder="请选择要分享的题库" class="bank-select"
            :loading="banksLoading" filterable popper-class="bank-share-select-popper">
            <el-option v-for="b in myBanks" :key="b.bankId" :value="b.bankId"
              :label="optionLabel(b)" :disabled="!b.totalQuestions">
              <span class="opt-name">{{ b.bankName }}</span>
              <span class="opt-count">{{ b.totalQuestions || 0 }} 题</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="有效期">
          <el-radio-group v-model="form.expireDays">
            <el-radio :value="0">永久</el-radio>
            <el-radio :value="7">7 天</el-radio>
            <el-radio :value="30">30 天</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="留言">
          <el-input v-model="form.message" type="textarea" :rows="2" maxlength="100" show-word-limit
            placeholder="选填，一句想对同学说的话" />
        </el-form-item>
      </el-form>
    </div>

    <div v-else class="share-result">
      <div class="share-row">
        <span class="share-label">题库</span>
        <span class="share-bank">{{ shareResult.bankName }}</span>
      </div>
      <div class="share-row">
        <span class="share-label">分享码</span>
        <span class="share-code">{{ shareResult.shareCode }}</span>
        <el-button size="small" @click="copyText(shareResult.shareCode, '分享码')">复制</el-button>
      </div>
      <div class="share-row">
        <span class="share-label">分享链接</span>
        <el-input v-model="shareResult.shareUrl" readonly size="small" />
        <el-button size="small" type="primary" @click="copyText(shareResult.shareUrl, '分享链接')">复制</el-button>
      </div>
      <p class="share-tip">
        有效期：{{ shareResult.expireTime ? formatDateTime(shareResult.expireTime) : '永久有效' }}
      </p>
      <el-alert class="share-usage" type="info" :closable="false" show-icon>
        <template #title>
          <span class="usage-text">
            把<b>链接</b>或<b>分享码</b>发给同学：对方登录后打开链接即可领取；
            也可在「我的收藏题库 → 获取题库分享」处填写分享码。
            领取后题库进入对方的「题库收藏」（只读），对方可「复制为我的题库」再自行编辑。
          </span>
        </template>
      </el-alert>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button v-if="!shareResult" type="primary" :loading="creating" @click="doCreateShare">
        生成分享
      </el-button>
      <el-button v-else type="primary" @click="resetResult">再生成一个</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createBankShare } from '@/api/bankShare/bankShare'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { buildBankShareUrl, formatDateTime } from '@/utils/share'

const props = defineProps<{
  modelValue: boolean
  /** 默认选中的题库（从某个题库详情进来时传，一般为当前题库 id） */
  defaultBankId?: number | string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 分享生成成功（父页面可刷新列表） */
  (e: 'created', data: any): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const myBanks = ref<any[]>([])
const banksLoading = ref(false)
const creating = ref(false)
const shareResult = ref<any>(null)
const form = reactive<{ bankId: number | string; expireDays: number; message: string }>({
  bankId: '',
  expireDays: 0,
  message: ''
})

/** 下拉项 / 已选项文案：题库名 + 题目数，中间留出间隔 */
const optionLabel = (b: any) => {
  const n = Number(b.totalQuestions || 0)
  return n ? `${b.bankName}（${n} 题）` : `${b.bankName}（空题库）`
}

const selectedBank = computed(() =>
  myBanks.value.find((b: any) => String(b.bankId) === String(form.bankId))
)

async function loadMyBanks() {
  banksLoading.value = true
  try {
    const res: any = await listMyQuestionBank()
    if (res.code === 200) {
      myBanks.value = res.data || []
    } else {
      myBanks.value = []
    }
  } catch (e) {
    myBanks.value = []
  } finally {
    banksLoading.value = false
    // 默认选中：传入的题库 → 否则第一个可分享的题库
    const wanted = props.defaultBankId
    const hit = wanted && myBanks.value.some((b: any) => String(b.bankId) === String(wanted))
    if (hit) {
      form.bankId = wanted as any
    } else if (myBanks.value.length) {
      const first = myBanks.value.find((b: any) => Number(b.totalQuestions || 0) > 0) || myBanks.value[0]
      form.bankId = first.bankId
    }
  }
}

// 每次打开都重新拉一遍（题库随时可能新增/删除），并重置结果面板
watch(visible, (v) => {
  if (v) {
    shareResult.value = null
    form.expireDays = 0
    form.message = ''
    form.bankId = props.defaultBankId || ''
    loadMyBanks()
  }
})

function resetResult() {
  shareResult.value = null
  form.expireDays = 0
  form.message = ''
}

async function doCreateShare() {
  if (creating.value) return
  if (!form.bankId) {
    ElMessage.warning('请选择要分享的题库')
    return
  }
  const total = Number(selectedBank.value?.totalQuestions || 0)
  if (!total) {
    ElMessage.warning('空题库无法分享，请先添加题目')
    return
  }
  creating.value = true
  try {
    const res: any = await createBankShare({
      bankId: form.bankId,
      expireDays: form.expireDays || null,
      message: form.message || undefined
    })
    if (res.code === 200 && res.data) {
      shareResult.value = {
        ...res.data,
        bankName: res.data.bankName || selectedBank.value?.bankName || '题库',
        shareUrl: buildBankShareUrl(res.data.shareToken)
      }
      emit('created', shareResult.value)
    } else {
      ElMessage.error(res.msg || '生成分享失败')
    }
  } catch (e) {
    // 业务提示由 request 拦截器统一弹出
  } finally {
    creating.value = false
  }
}

function copyText(text: string, label: string) {
  if (!text) return
  navigator.clipboard.writeText(text)
    .then(() => ElMessage.success(`${label}已复制`))
    .catch(() => ElMessage.error('复制失败，请手动复制'))
}
</script>

<style scoped>
.share-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin: 0 0 12px;
}

.share-tip b {
  color: #1f2937;
}

.share-form .bank-select {
  width: 100%;
}

.share-result .share-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.share-result .share-label {
  flex: 0 0 60px;
  font-size: 13px;
  color: #606266;
}

.share-result .share-bank {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-result .share-code {
  flex: 1;
  font-family: 'Courier New', monospace;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 3px;
  color: #409EFF;
  user-select: all;
}

.share-usage {
  margin-top: 4px;
}

.share-usage .usage-text {
  font-size: 12px;
  line-height: 1.7;
  font-weight: 400;
}
</style>

<!-- 下拉面板被 teleport 到 body，scoped 样式命中不了，必须用非 scoped + popper-class -->
<style>
/* 下拉项：题库名靠左、题目数靠右，两者之间自动撑开间隔 */
.bank-share-select-popper .el-select-dropdown__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.bank-share-select-popper .el-select-dropdown__item .opt-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bank-share-select-popper .el-select-dropdown__item .opt-count {
  flex: 0 0 auto;
  font-size: 12px;
  color: #909399;
}

/* 禁用项（空题库）整体变浅，计数颜色跟随 */
.bank-share-select-popper .el-select-dropdown__item.is-disabled .opt-count {
  color: #c0c4cc;
}
</style>
