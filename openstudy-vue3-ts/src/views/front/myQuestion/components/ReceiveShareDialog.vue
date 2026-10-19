<!-- ==================== 领取分享题库弹窗（公共组件） ==================== -->
<!--
  支持粘贴「分享链接」或输入「分享码」两种方式。

  ## 为什么要先校验再领取

  用户 2026-10-19：「关于获取分享，要检查当前这个分享题库是否是用户自己的题库，
  不可以获取自己的分享，要给用户对应的提示」。

  后端 `receive` 接口本身已经拦了（`share.owner_id == user_id` → 500「这是你自己分享的题库，
  无需领取」），但那个错误是以全局 toast 的形式弹出来的 —— 用户看到的是
  一个红条一闪而过，弹窗还开着、输入框还在，不知道下一步该做什么。

  所以这里改成**先走 `info` 接口预校验**（它本来就会返回 `isOwner` / `received`）：
    · 是自己的分享 → 弹窗内直接给出说明，并把「获取题库」按钮禁用；
    · 已经领过     → 提示"已在你的题库收藏中"，按钮改成「去看看」；
    · 分享失效     → 提示已撤销 / 已过期。
  预校验期间按钮处于 loading，避免用户连点两次。

  预校验失败（网络抖动等）时不阻断流程 —— 直接放行到 `receive`，
  由后端做最终判定，绝不因为一个辅助请求把用户挡在门外。
-->
<template>
  <el-dialog v-model="visible" title="获取题库分享" width="480px" :close-on-click-modal="false">
    <p class="code-tip">
      粘贴好友给你的<b>分享链接</b>，或直接输入 <b>分享码</b>：题库会加入你的「<b>题库收藏</b>」（只读，不能编辑）。
      想改题目内容，可在题库详情里点「<b>复制为我的题库</b>」自己留一份。
    </p>

    <el-input v-model="input" size="large" clearable class="code-input" :disabled="receiving"
      placeholder="粘贴分享链接，或输入分享码（如 3XKD7N）" @keyup.enter="handleReceive" @input="onInput" />

    <p class="code-example">示例：http://localhost:3167/front/share/xxxxxx　或　3XKD7N</p>

    <!--
      预校验结果：三种状态各自有明确文案 + 对应动作。
      `blocked` 时「获取题库」按钮禁用，用户不会点了才被后端拒绝。
    -->
    <div v-if="checkState" class="check-box" :class="'is-' + checkState.kind">
      <el-icon class="check-ico">
        <CircleCheck v-if="checkState.kind === 'ok'" />
        <WarningFilled v-else />
      </el-icon>
      <div class="check-body">
        <div class="check-title">{{ checkState.title }}</div>
        <div v-if="checkState.desc" class="check-desc">{{ checkState.desc }}</div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ checkState?.kind === 'received' ? '关闭' : '取消' }}</el-button>
      <el-button v-if="checkState?.kind === 'received'" type="primary" @click="goCollect">
        去看看
      </el-button>
      <el-button v-else type="primary" :loading="receiving" :disabled="checkState?.kind === 'blocked'"
        @click="handleReceive">
        {{ checkState?.kind === 'blocked' ? '无法获取' : '获取题库' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheck, WarningFilled } from '@element-plus/icons-vue'
import { receiveBankShare, getShareInfoByToken, getShareInfoByCode } from '@/api/bankShare/bankShare'
import { parseShareInput } from '@/utils/share'
import { ensureLogin } from '@/utils/loginGuard'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success', data: any): void
  (e: 'received'): void
}>()

const router = useRouter()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

const input = ref('')
const receiving = ref(false)

/**
 * 预校验结果
 * `kind`:
 *   ok       —— 可以领（显示题库名 + 题数，让用户确认再点）
 *   blocked  —— 不能领（自己的分享 / 已撤销 / 已过期 / 不存在）
 *   received —— 之前领过（按钮换成「去看看」）
 */
interface CheckState {
  kind: 'ok' | 'blocked' | 'received'
  title: string
  desc?: string
  bankId?: number | string
}
const checkState = ref<CheckState | null>(null)
/** 预校验请求序号：输入变化后旧请求的结果要丢弃 */
let checkSeq = 0
/** 输入防抖计时器 */
let inputTimer: ReturnType<typeof setTimeout> | null = null

function resetCheck() {
  checkState.value = null
  checkSeq++
}

/**
 * 输入即预校验（600ms 防抖）
 * ----------------------------------------------------------------------------
 * 用户要么粘一整个链接、要么敲 6 位分享码，两者都是"一次给完"的动作，
 * 所以短防抖足够；真正要避免的是**每敲一个字符打一次接口**。
 *
 * 好处：用户敲完分享码、还没点按钮，就已经能看到
 * 「这是你自己分享的题库」/「可以获取《xxx》」—— 不用点了才被拒。
 */
function onInput() {
  resetCheck()
  const raw = input.value.trim()
  if (!raw) return
  if (inputTimer) clearTimeout(inputTimer)
  inputTimer = setTimeout(async () => {
    const state = await runCheck(raw)
    // 期间用户又改了输入 → 丢弃这次结果
    if (input.value.trim() !== raw) return
    checkState.value = state
  }, 600)
}

// 关弹窗时清空，避免下次打开还挂着上一次的提示
watch(visible, (v) => {
  if (!v) {
    input.value = ''
    if (inputTimer) clearTimeout(inputTimer)
    resetCheck()
  }
})

/** 解析输入后跑一次预校验；解析不出来就当没有结果，交给 handleReceive 提示 */
async function runCheck(raw: string): Promise<CheckState | null> {
  const { token, code } = parseShareInput(raw)
  if (!token && !code) return null

  const seq = ++checkSeq
  try {
    const res: any = token
      ? await getShareInfoByToken(token)
      : await getShareInfoByCode(code as string)
    if (seq !== checkSeq) return null
    if (res.code !== 200 || !res.data) {
      return { kind: 'blocked', title: res.msg || '分享不存在或已失效' }
    }

    const d = res.data
    const name = d.bankName ? `《${d.bankName}》` : '这个题库'
    const meta = d.totalQuestions ? `　${d.totalQuestions} 道题` : ''

    // 自己的分享：后端本来就会拒，这里提前讲清楚
    if (d.isOwner) {
      return {
        kind: 'blocked',
        title: '这是你自己分享的题库',
        desc: '不需要领取 —— 它已经在你的「我的题库」里了。想发给别人，把分享码或链接发过去就行。'
      }
    }
    // 已经领过
    if (d.received) {
      return {
        kind: 'received',
        title: `${name}已在你的「题库收藏」中`,
        desc: '不用重复领取，直接去收藏里刷题即可。',
        bankId: d.bankId
      }
    }
    return {
      kind: 'ok',
      title: `可以获取${name}`,
      desc: `分享者：${d.ownerName || d.ownerNickName || '匿名用户'}${meta}　获取后进入「题库收藏」`,
      bankId: d.bankId
    }
  } catch {
    // 辅助请求失败不阻断主流程
    return null
  }
}

const handleReceive = async () => {
  const raw = input.value.trim()
  if (!raw) {
    ElMessage.warning('请粘贴分享链接或输入分享码')
    return
  }
  if (receiving.value) return
  if (!(await ensureLogin('获取题库分享'))) return

  const { token, code } = parseShareInput(raw)
  if (!token && !code) {
    ElMessage.warning('链接格式不正确，请检查后重试，或直接输入 6 位分享码')
    return
  }

  receiving.value = true
  try {
    // 先预校验：自己的分享 / 已失效 在这里就被拦住，不去打扰后端
    if (!checkState.value) {
      const checked = await runCheck(raw)
      checkState.value = checked
      if (checked?.kind === 'blocked') {
        receiving.value = false
        return
      }
      if (checked?.kind === 'received') {
        receiving.value = false
        return
      }
    } else if (checkState.value.kind === 'blocked') {
      receiving.value = false
      return
    }

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
      resetCheck()
      emit('received')
      emit('success', res.data)
    } else {
      // 后端业务拒绝（例如自己的分享）：留在弹窗里显示，而不是只闪一个 toast
      const msg = res.msg || '领取失败，请稍后重试'
      checkState.value = { kind: 'blocked', title: msg }
      ElMessage.error(msg)
    }
  } catch (e: any) {
    /*
     * 业务错误（自己的分享 / 已撤销 / 已过期）由 request 拦截器 reject，
     * 这里把它留在弹窗内展示 —— 用户关掉 toast 之后仍然能看到原因。
     */
    const msg = e?.message || String(e || '')
    if (msg && !msg.includes('未登录')) {
      checkState.value = { kind: 'blocked', title: msg }
    }
    console.warn('[share] 领取失败:', e)
  } finally {
    receiving.value = false
  }
}

/** 「去看看」：关弹窗并跳到题库收藏分组 */
function goCollect() {
  visible.value = false
  emit('received')
  router.push('/front/myQuestion/myBank?tab=favorite')
}
</script>

<style scoped>
.code-tip {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--os-text-3, #6b7280);
  line-height: 1.6;
}

.code-tip b {
  color: var(--os-text, #1f2937);
}

.code-example {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
  line-height: 1.6;
  word-break: break-all;
}

/* 输入框既可能填链接（长文本）也可能填分享码，用常规左对齐 */
.code-input :deep(.el-input__inner) {
  font-size: 13px;
}

/* ==================== 预校验结果 ==================== */
.check-box {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--os-radius-sm, 8px);
  border: 1px solid var(--os-border-soft, #e5e7eb);
  background: var(--dsw-static-neutral-bluish-50, #f9fafb);
  font-size: 13px;
  line-height: 1.55;
}

.check-ico {
  flex: none;
  margin-top: 1px;
  font-size: 15px;
}

.check-body {
  min-width: 0;
}

.check-title {
  font-weight: 500;
  color: var(--os-text, #1f2937);
}

.check-desc {
  margin-top: 2px;
  font-size: 12.5px;
  color: var(--os-text-3, #6b7280);
}

/* 可以获取：绿色调 */
.check-box.is-ok {
  border-color: rgba(16, 185, 129, 0.28);
  background: rgba(16, 185, 129, 0.06);

  .check-ico {
    color: #059669;
  }
}

/* 不能获取：暖色调提醒（不用刺眼的纯红，这里不是报错，是「不需要这么做」） */
.check-box.is-blocked {
  border-color: rgba(217, 119, 6, 0.28);
  background: rgba(217, 119, 6, 0.07);

  .check-ico {
    color: #d97706;
  }
}

/* 已领过：中性 */
.check-box.is-received {
  border-color: var(--os-border, #d1d5db);

  .check-ico {
    color: var(--os-text-3, #6b7280);
  }
}
</style>
