<!-- ==================== 领取分享题库弹窗（公共组件） ==================== -->
<!-- 支持粘贴「分享链接」或输入「分享码」两种方式 -->
<template>
  <el-dialog v-model="visible" title="领取分享题库" width="460px" :close-on-click-modal="false">
    <p class="code-tip">
      粘贴好友给你的<b>分享链接</b>，或直接输入 <b>6 位分享码</b>：题库会加入你的「<b>题库收藏</b>」（只读，不能编辑）。
      想改题目内容，可在题库详情里点「<b>复制为我的题库</b>」自己留一份。
    </p>
    <el-input v-model="input" size="large" clearable class="code-input"
      placeholder="粘贴分享链接，或输入分享码（如 3XKD7N）" @keyup.enter="handleReceive" />
    <p class="code-example">示例：http://localhost:3167/front/share/xxxxxx　或　3XKD7N</p>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="receiving" @click="handleReceive">获取题库</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { receiveBankShare } from '@/api/bankShare/bankShare'
import { parseShareInput } from '@/utils/share'
import { ensureLogin } from '@/utils/loginGuard'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success', data: any): void
  (e: 'received'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const input = ref('')
const receiving = ref(false)

const handleReceive = async () => {
  const raw = input.value.trim()
  if (!raw) {
    ElMessage.warning('请粘贴分享链接或输入分享码')
    return
  }
  if (receiving.value) return
  if (!(await ensureLogin('领取分享题库'))) return

  const { token, code } = parseShareInput(raw)
  if (!token && !code) {
    ElMessage.warning('链接格式不正确，请检查后重试，或直接输入 6 位分享码')
    return
  }

  receiving.value = true
  try {
    const res: any = await receiveBankShare(token ? { token } : { code })
    if (res.code === 200 && res.data) {
      const status = res.data.resultStatus
      const msgMap: Record<string, string> = {
        created: '已加入你的「题库收藏」',
        restored: '已重新加入你的「题库收藏」',
        exists: '该题库已在你的「题库收藏」中'
      }
      ElMessage.success(msgMap[status] || (res.data.alreadyReceived ? '该题库已在你的收藏中' : '已加入你的题库收藏'))
      visible.value = false
      input.value = ''
      emit('received')
      emit('success', res.data)
    } else {
      ElMessage.error(res.msg || '领取失败，请稍后重试')
    }
  } catch (e) {
    console.warn('[share] 领取失败（业务提示已由 request 拦截器给出，不再重复弹窗）:', e)
  } finally {
    receiving.value = false
  }
}
</script>

<style scoped>
.code-tip {
  margin: 0 0 14px;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
}

.code-tip b {
  color: #1f2937;
}

.code-example {
  margin: 8px 0 0;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.6;
  word-break: break-all;
}

/* 输入框既可能填链接（长文本）也可能填分享码，用常规左对齐 */
.code-input :deep(.el-input__inner) {
  font-size: 13px;
}
</style>
