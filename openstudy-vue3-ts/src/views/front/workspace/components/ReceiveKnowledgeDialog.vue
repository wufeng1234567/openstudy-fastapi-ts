<template>
  <el-dialog v-model="visible" title="获取知识库分享" width="480px" :close-on-click-modal="false">
    <p class="kb-code-tip">
      粘贴好友给你的<b>分享链接</b>，或直接输入 <b>分享码</b>。领取后会得到一份完整副本，系统会为副本重新解析和向量化。
    </p>
    <el-input v-model="input" size="large" clearable class="kb-code-input" :disabled="receiving"
      placeholder="粘贴分享链接，或输入分享码（如 3XKD7N）" @keyup.enter="handleReceive" @input="onInput" />

    <p class="kb-code-example">示例：http://localhost:3167/front/knowledgeShare/xxxxxx　或　3XKD7N</p>

    <div v-if="checkState" class="kb-check-box" :class="'is-' + checkState.kind">
      <el-icon class="kb-check-ico">
        <CircleCheck v-if="checkState.kind === 'ok'" />
        <WarningFilled v-else />
      </el-icon>
      <div>
        <div class="kb-check-title">{{ checkState.title }}</div>
        <div v-if="checkState.desc" class="kb-check-desc">{{ checkState.desc }}</div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ checkState?.kind === 'received' ? '关闭' : '取消' }}</el-button>
      <el-button v-if="checkState?.kind === 'received'" type="primary" @click="goReceived">去看看</el-button>
      <el-button v-else type="primary" :loading="receiving" :disabled="checkState?.kind === 'blocked'"
        @click="handleReceive">
        {{ checkState?.kind === 'blocked' ? '无法获取' : (checkState?.isDoc ? '复制到我的资料' : '领取资料夹副本') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheck, WarningFilled } from '@element-plus/icons-vue'
import {
  getKbShareInfoByCode,
  getKbShareInfoByToken,
  receiveKbShare
} from '@/api/kbShare/kbShare'
import { parseShareInput } from '@/utils/share'
import { ensureLogin } from '@/utils/loginGuard'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'received', data: any): void
}>()

const router = useRouter()
const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

interface CheckState {
  kind: 'ok' | 'blocked' | 'received'
  title: string
  desc?: string
  kbId?: number
  docId?: number
  isDoc?: boolean
}

const input = ref('')
const receiving = ref(false)
const checkState = ref<CheckState | null>(null)
let checkSeq = 0
let inputTimer: ReturnType<typeof setTimeout> | null = null

function resetCheck() {
  checkState.value = null
  checkSeq++
}

function onInput() {
  resetCheck()
  const raw = input.value.trim()
  if (!raw) return
  if (inputTimer) clearTimeout(inputTimer)
  inputTimer = setTimeout(async () => {
    const state = await runCheck(raw)
    if (input.value.trim() === raw) checkState.value = state
  }, 600)
}

watch(visible, (v) => {
  if (!v) {
    input.value = ''
    if (inputTimer) clearTimeout(inputTimer)
    resetCheck()
  }
})

async function runCheck(raw: string): Promise<CheckState | null> {
  const { token, code } = parseShareInput(raw)
  if (!token && !code) return null
  const seq = ++checkSeq
  try {
    const res: any = token
      ? await getKbShareInfoByToken(token)
      : await getKbShareInfoByCode(code as string)
    if (seq !== checkSeq) return null
    if (res.code !== 200 || !res.data) {
      return { kind: 'blocked', title: res.msg || '分享不存在或已失效' }
    }
    const d = res.data
    const name = d.docName ? `《${d.docName}》` : d.kbName ? `《${d.kbName}》` : '这个资料'
    if (d.isOwner) {
      return {
        kind: 'blocked',
        title: '这是你自己分享的资料',
        desc: '不需要领取 —— 它已经在你的「我的资料」里了。'
      }
    }
    if (d.received && (d.newKbId || d.newDocId)) {
      return {
        kind: 'received',
        title: `${name}已领取过`,
        desc: '不用重复领取，直接去你的资料夹查看即可。',
        kbId: d.newKbId,
        docId: d.newDocId,
        isDoc: !!d.docName
      }
    }
    return {
      kind: 'ok',
      title: `可以获取${name}`,
      desc: `分享者：${d.ownerName || '匿名用户'}　${d.docName ? '1 份资料' : `${d.docCount || 0} 份资料`}　领取后生成完整副本并重新建立索引`,
      kbId: d.kbId,
      isDoc: !!d.docName
    }
  } catch {
    return null
  }
}

async function handleReceive() {
  const raw = input.value.trim()
  if (!raw) {
    ElMessage.warning('请粘贴分享链接或输入分享码')
    return
  }
  if (receiving.value) return
  if (!(await ensureLogin('获取知识库分享'))) return
  const { token, code } = parseShareInput(raw)
  if (!token && !code) {
    ElMessage.warning('链接格式不正确，请检查后重试，或直接输入 6 位分享码')
    return
  }
  receiving.value = true
  try {
    const checked = checkState.value || (await runCheck(raw))
    if (!checkState.value) checkState.value = checked
    if (checked?.kind === 'blocked') {
      receiving.value = false
      return
    }
    if (checked?.kind === 'received' && checked.kbId) {
      receiving.value = false
      goKb(checked.kbId, checked.docId)
      return
    }
    const res: any = await receiveKbShare({ token, code })
    if (res.code === 200 && res.data?.kbId) {
      ElMessage.success('已复制到你的「我的资料」')
      emit('received', res.data)
      goKb(res.data.kbId, res.data.docId)
    } else {
      ElMessage.error(res.msg || '领取失败，请稍后重试')
    }
  } catch {
    // request 拦截器已提示
  } finally {
    receiving.value = false
  }
}

function goKb(kbId: number, docId?: number) {
  visible.value = false
  const query = docId ? `?kbId=${kbId}&docId=${docId}&open=1` : `?kbId=${kbId}`
  router.push(`/front/workspace${query}`)
}

function goReceived() {
  if (checkState.value?.kbId) goKb(checkState.value.kbId, checkState.value.docId)
}
</script>

<style scoped>
.kb-code-tip {
  margin: 0 0 12px;
  color: #909399;
  font-size: 12px;
  line-height: 1.7;
}

.kb-code-tip b {
  color: #1f2937;
}

.kb-code-input {
  width: 100%;
}

.kb-code-example {
  margin: 7px 0 12px;
  color: #b1b3b8;
  font-size: 10px;
}

.kb-check-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.5;
}

.kb-check-box.is-ok {
  background: #f0f9eb;
  color: #529b2e;
}

.kb-check-box.is-blocked {
  background: #fef0f0;
  color: #c45656;
}

.kb-check-box.is-received {
  background: #f4f4f5;
  color: #73767a;
}

.kb-check-ico {
  margin-top: 1px;
  flex: none;
}

.kb-check-title {
  font-weight: 600;
}

.kb-check-desc {
  margin-top: 2px;
  opacity: 0.9;
}
</style>
