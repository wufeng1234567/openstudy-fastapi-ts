<template>
  <el-dialog v-model="visible" :title="doc ? '分享资料' : '分享知识库'" width="520px" append-to-body
    :close-on-click-modal="false">
    <div v-if="!shareResult" class="kb-share-form">
      <p class="kb-share-tip">
        <template v-if="doc">
          分享这份资料给同学。对方领取后，会在自己的「我的资料」里得到一份<b>完整副本</b>，
          直接复用原资料已有的解析结果和向量索引，不会重新解析。
        </template>
        <template v-else>
          分享一个知识库给同学。对方领取后，会在自己的「我的资料」里得到一份<b>完整副本</b>，
          直接复用原知识库已有解析结果与向量索引，不会重新解析；副本可以继续编辑和检索。
        </template>
      </p>
      <el-form label-width="76px">
        <el-form-item v-if="!doc" label="知识库">
          <el-select v-model="form.kbId" placeholder="请选择要分享的知识库" filterable class="kb-share-select"
            :loading="kbLoading">
            <el-option v-for="kb in myKbs" :key="kb.kbId" :value="kb.kbId" :label="kb.name"
              :disabled="!Number(kb.docCount || 0)">
              <span class="opt-name">{{ kb.name }}</span>
              <span class="opt-meta">{{ kb.docCount || 0 }} 份资料</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-else label="资料">
          <span class="kb-share-file">{{ doc.fileName }}</span>
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

      <div class="my-share-block">
        <div class="my-share-head">
          <span>我发出的分享</span>
          <el-button text size="small" @click="loadShares">刷新</el-button>
        </div>
        <div v-if="!myShares.length" class="my-share-empty">还没有分享记录</div>
        <div v-for="item in myShares" :key="item.shareId" class="my-share-item">
          <div class="my-share-main">
            <span class="my-share-name">{{ item.docName || item.kbName || '知识库' }}</span>
            <span class="my-share-meta">
              {{ item.shareCode }} · {{ item.receiveCount || 0 }} 人领取 ·
              <em :class="item.effective ? 'is-valid' : 'is-invalid'">{{ item.effective ? '有效' : '已失效' }}</em>
            </span>
          </div>
          <el-button v-if="item.effective" text type="danger" size="small" @click="revoke(item)">撤销</el-button>
        </div>
      </div>
    </div>

    <div v-else class="kb-share-result">
      <div class="share-row">
        <span class="share-label">{{ doc ? '资料' : '知识库' }}</span>
        <span class="share-kb">{{ shareResult.docName || shareResult.kbName }}</span>
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
      <p class="kb-share-tip">
        有效期：{{ shareResult.expireTime ? formatDateTime(shareResult.expireTime) : '永久有效' }}
      </p>
      <el-alert type="info" :closable="false" show-icon
        title="把链接或分享码发给同学：对方领取后会得到一份复制自有索引的完整副本，不需要重新解析。" />
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button v-if="!shareResult" type="primary" :loading="creating" @click="doCreate">生成分享</el-button>
      <el-button v-else type="primary" @click="resetResult">再生成一个</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listKnowledgeBases } from '@/api/ai/rag'
import { createKbShare, listMyKbShares, revokeKbShare } from '@/api/kbShare/kbShare'
import { buildKnowledgeShareUrl, formatDateTime } from '@/utils/share'

const props = defineProps<{
  modelValue: boolean
  defaultKbId?: number | string | null
  doc?: { docId: number; fileName: string } | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created', data: any): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const myKbs = ref<any[]>([])
const myShares = ref<any[]>([])
const kbLoading = ref(false)
const creating = ref(false)
const shareResult = ref<any>(null)
const form = reactive<{ kbId: number | string; expireDays: number; message: string }>({
  kbId: '',
  expireDays: 0,
  message: ''
})

const selectedKb = computed(() =>
  myKbs.value.find((kb) => String(kb.kbId) === String(form.kbId))
)

async function loadKbs() {
  kbLoading.value = true
  try {
    const res: any = await listKnowledgeBases()
    myKbs.value = res.code === 200 && Array.isArray(res.data) ? res.data : []
  } catch {
    myKbs.value = []
  } finally {
    kbLoading.value = false
    const wanted = props.defaultKbId
    const hit = wanted && myKbs.value.some((kb) => String(kb.kbId) === String(wanted))
    if (hit) {
      form.kbId = wanted as any
    } else if (myKbs.value.length) {
      const first = myKbs.value.find((kb) => Number(kb.docCount || 0) > 0) || myKbs.value[0]
      form.kbId = first.kbId
    }
  }
}

async function loadShares() {
  try {
    const res: any = await listMyKbShares()
    myShares.value = res.code === 200 && Array.isArray(res.data) ? res.data : []
  } catch {
    myShares.value = []
  }
}

watch(visible, (v) => {
  if (v) {
    shareResult.value = null
    form.expireDays = 0
    form.message = ''
    form.kbId = props.defaultKbId || ''
    void loadKbs()
    void loadShares()
  }
})

function resetResult() {
  shareResult.value = null
  form.expireDays = 0
  form.message = ''
}

async function doCreate() {
  if (creating.value) return
  if (!props.doc && !form.kbId) {
    ElMessage.warning('请选择要分享的知识库')
    return
  }
  if (!props.doc && !Number(selectedKb.value?.docCount || 0)) {
    ElMessage.warning('空知识库无法分享，请先添加资料')
    return
  }
  creating.value = true
  try {
    const payload: any = {
      expireDays: form.expireDays || null,
      message: form.message || undefined
    }
    if (props.doc) payload.docId = props.doc.docId
    else payload.kbId = form.kbId
    const res: any = await createKbShare(payload)
    if (res.code === 200 && res.data) {
      shareResult.value = {
        ...res.data,
        kbName: res.data.kbName || selectedKb.value?.name || '知识库',
        docName: res.data.docName || props.doc?.fileName || '',
        shareUrl: buildKnowledgeShareUrl(res.data.shareToken)
      }
      emit('created', shareResult.value)
      await loadShares()
    } else {
      ElMessage.error(res.msg || '生成分享失败')
    }
  } catch {
    // request 拦截器已提示
  } finally {
    creating.value = false
  }
}

async function revoke(item: any) {
  try {
    await ElMessageBox.confirm(`撤销「${item.kbName || '知识库'}」的分享？已领取的副本仍然保留。`, '撤销分享', {
      type: 'warning'
    })
    const res: any = await revokeKbShare(item.shareId)
    if (res.code === 200) {
      ElMessage.success('已撤销分享')
      await loadShares()
    } else {
      ElMessage.error(res.msg || '撤销失败')
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('撤销失败')
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
.kb-share-tip {
  margin: 0 0 12px;
  color: #909399;
  font-size: 12px;
  line-height: 1.65;
}

.kb-share-tip b {
  color: #1f2937;
}

.kb-share-select {
  width: 100%;
}

.kb-share-file {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.opt-name {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.opt-meta {
  float: right;
  color: #a8abb2;
  font-size: 11px;
}

.my-share-block {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid #f0f1f3;
}

.my-share-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #606266;
  font-size: 12px;
}

.my-share-empty {
  padding: 8px 0;
  color: #a8abb2;
  font-size: 11px;
}

.my-share-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 0;
  border-top: 1px dashed #f2f3f5;
}

.my-share-main {
  flex: 1;
  min-width: 0;
}

.my-share-name {
  display: block;
  overflow: hidden;
  color: #303133;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.my-share-meta {
  display: block;
  margin-top: 2px;
  color: #a8abb2;
  font-size: 10px;
}

.my-share-meta em {
  font-style: normal;
}

.my-share-meta .is-valid {
  color: #67c23a;
}

.my-share-meta .is-invalid {
  color: #f56c6c;
}

.share-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.share-label {
  flex: 0 0 60px;
  color: #606266;
  font-size: 13px;
}

.share-kb {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-code {
  flex: 1;
  color: #409eff;
  font-family: 'Courier New', monospace;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 3px;
  user-select: all;
}
</style>
