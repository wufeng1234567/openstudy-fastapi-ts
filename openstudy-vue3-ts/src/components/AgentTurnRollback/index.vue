<!-- components/AgentTurnRollback/index.vue -->
<!--
  轮末动作条 —— 挂在**一轮对话的最后一条消息下面**（`useAgentChat` 每轮 push 的那条
  `type:'turn_end'` 标记那一格），每轮两个按钮：

    · **回退**：撤销这一轮的全部写操作（用户点一下就调 `rollbackTurn(turnId)`）；
    · **复制**：一键复制**这一轮 LLM 的回复正文**（该轮 assistant 正文消息拼起来）。

  语义（用户 2026-09-23 裁决）：
    · **每一轮都能点回退**（当天稍晚的裁决反转了更早的「只回退最近一轮」）；
    · 增 / 删 / 改都回退（哪些真能撤由服务端决定，前端不预判）；
    · 组件挂在消息列表里「轮末」那一格（不是悬浮在页面底部，也不是页面头部）。

  ## 这一格是纯 UI，一个判断都不做
  哪些撤了、哪些不给撤、为什么、报了什么错 —— 全是服务端按轮次账本算出来的，
  本组件只把「这一轮」的结果画出来（`reverted` / 整轮被拒的 `reason`）。
  逐条清单（`skipped` / `partial` / `failed`）**不在这里画** —— 见下面那条注释。
  ⚠️ 前端**不替服务端兜底**：不改写原因、不把 `ok=false` 的 `reason` 换成一句「回退失败」
  （那是服务端说的话，原样显示 —— 如「缺少轮次 id（turnId），无法回退」）。
  双链路同口径：回退语义只在服务端一处（见 `src/api/ai/agent.ts` 的 `rollbackAgentTurn`）。

  ## 三态（`state.status`，来自 `useAgentChat` 的 `rollbackStates[turnId]`）
    `idle` 一个可点的「回退」
    `busy` 转圈 + 按钮禁用（连点会打两次账本 —— 后端幂等，但用户会读成「第一次没生效」）
    `done` 「已回退 N 项操作」；有失败项时按钮变「重试」（回退是幂等的）
    `fail` 服务端原话 + 「重试」
  `done` 且 `reverted === 0` 且三份清单都空 ⇒ 「这一轮没有可回退的操作」——
  **不是失败态**（这一轮本来就只有查询，没有写操作可撤）。

  ## 逐条清单为什么不在这一格画
  回退成功时 `useAgentChat` 会把**这一轮的消息整轮摘掉**（`outcome.dropped === true`）——
  那一格连同本组件一起下线，画在这里的清单等于没画。所以
  「哪些没退成、为什么」统一落在**消息列表之外**的 `AgentRollbackNotice`（可关闭、不会被删），
  这一格只负责「这一轮自己的状态 + 两个按钮」。

  ## 为什么根节点一渲染就是 `is-<status>`
  三态要换左边框与底色，靠一个 class 走完，别在模板里堆 `:class` 三元表达式。
-->
<template>
  <div class="agent-rollback" :class="[`is-${status}`]">
    <!-- ① 主行：状态文案 + 两个动作按钮（回退 / 复制这一轮的回复正文） -->
    <div class="atr-head">
      <span v-if="status === 'busy'" class="atr-spinner" aria-hidden="true"></span>

      <!-- 摘要：文案全部由服务端字段拼出，前端一个词都不编 -->
      <span v-if="status === 'busy'" class="atr-title">正在回退…</span>
      <span v-else-if="nothingToRollback" class="atr-title">这一轮没有可回退的操作</span>
      <span v-else-if="status === 'done'" class="atr-title">已回退 {{ reverted }} 项操作</span>

      <!--
        ⚠️ 两个按钮**永远都在**（不适用的那一个置灰，而不是消失）：
           它们是同一行里的并列动作，谁消失都等于让另一个跳位 ——
           用户上一轮点的是左边那个，下一轮它却跑到了右边。
           图标一律走 Element Plus 图标组件（`RefreshLeft` = 撤销/回退语义、
           `CopyDocument` = 复制语义），**不许用 emoji 或 ↻ / ⚠ 这类字符当图标**。
      -->
      <div class="atr-actions">
        <button type="button" class="atr-btn" :disabled="!canClick" @click="onRollback">
          <el-icon class="atr-icon">
            <RefreshLeft />
          </el-icon>
          <span>{{ buttonLabel }}</span>
        </button>

        <button type="button" class="atr-btn is-copy" :disabled="!canCopy" @click="onCopy">
          <el-icon class="atr-icon">
            <CopyDocument />
          </el-icon>
          <span>复制</span>
        </button>
      </div>

      <!--
        本轮耗时记录（2026-10-27 新增）

        用户要求：「做一个记录，记录了本次对话共耗时多少时间，
                   每轮聊天的底部都可以看到」

        ⚠️ 放在按钮**右侧**、同一行：它是这一轮的元信息，不是操作，
           单独占一行会凭空多出一段垂直空白（每轮都多一次）。
        ⚠️ 只在有值时渲染：老数据（本次改动之前落库的轮次）没有这个字段，
           显示 "，用时 0 秒" 是错的信息，不如不显示。
      -->
      <span v-if="durationMs > 0" class="atr-duration" :title="durationTitle">
        {{ durationText }}
      </span>
    </div>

    <!--
      ② 整轮被拒时服务端的**原话**（`ok === false` 的 `reason`）
      ⚠️ 插值里就是 `outcome.reason` 本身 —— 一字不改、不加前缀也不换成「回退失败」：
         它是唯一说得清「为什么没退成」的东西（轮次不存在 / 不属于你 / 缺 turnId…）。
         这种情况下消息**不会**被摘掉，所以就地显示是对的（清单那一侧见 `AgentRollbackNotice`）。
         L75 断的就是「这一格渲染的是服务端那个字段本身」。
    -->
    <div v-if="status === 'fail' && outcome && outcome.reason" class="atr-reason">{{ outcome.reason }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CopyDocument, RefreshLeft } from '@element-plus/icons-vue'
import type { AgentRollbackItem, AgentRollbackResult } from '@/api/ai/agent'

/**
 * 某一轮的回退状态 —— `useAgentChat` 的 `rollbackStates[turnId]`
 *
 * ⚠️ 这里**只读类型/对象**，不 `import { useAgentChat }`：`AiChatStream` 有两个消费方
 *    （大屏智能体页 + 右侧助手抽屉），谁都不该在展示层再起一份业务状态。
 */
type RollbackState = {
  status?: 'idle' | 'busy' | 'done' | 'fail'
  /** 服务端结果（`busy` 时为 null） */
  outcome?: (AgentRollbackResult & { userText?: string; dropped?: boolean }) | null
}

const props = defineProps({
  /** 这一格属于哪一轮（`turn_end` 标记里的 `turnId`）—— 回退请求要靠它定位账本 */
  turnId: { type: String, default: '' },
  /**
   * **这一轮**的回退状态（`rollbackStates[turnId]`；没点过 / 找不到时给 `null`）。
   * 页面按轮传进来，本组件不自己去 composable 里取（见上方 `RollbackState` 的注释）。
   */
  state: { type: Object as () => RollbackState | null, default: null },
  /**
   * 这一轮 LLM 的回复正文（「复制」按钮复制的内容）。
   * 由消息流按轮拼好传进来（它手上才有整份 `messages`），本组件只负责交给剪贴板前的搬运。
   */
  answerText: { type: String, default: '' },
  /**
   * 本轮耗时（毫秒）—— 2026-10-27 新增
   *
   * 用户要求：「做一个记录，记录了本次对话共耗时多少时间，每轮聊天的底部都可以看到」
   */
  durationMs: { type: Number, default: 0 },
  /**
   * 到此为止整段对话的累计耗时（毫秒）—— 2026-10-27 新增
   *
   * 单轮耗时回答"这次等了多久"；累计值回答"这段对话一共花了多久"，
   * 后者是用户说的"记录本次对话共耗时"。
   */
  totalDurationMs: { type: Number, default: 0 },
  /**
   * 外部禁用（目前只用于「正在生成」：这一轮还在跑，撤账本会跟它交叉）。
   * 与 `state.status === 'busy'` 是「或」的关系。
   */
  disabled: { type: Boolean, default: false }
})

/**
 * 两个动作都抛给外面，本组件自己不调接口、不碰剪贴板：
 *   · `rollback` 的载荷 = **这一轮**的 `turnId`（页面用同一个 composable 的 `rollbackTurn` 调接口）；
 *   · `copy` 的载荷 = 这一轮的回复正文（剪贴板与提示统一由消息流做，全站只有一份实现）。
 */
const emit = defineEmits(['rollback', 'copy'])

/* ============================================================
 * 服务端结果 → 展示字段（全部原样搬运）
 * ============================================================ */

/** 服务端结果；没点过给 `null` */
const outcome = computed<RollbackState['outcome']>(() => props.state?.outcome || null)
const status = computed(() => props.state?.status || 'idle')

const reverted = computed(() => outcome.value?.reverted ?? 0)
const skipped = computed<AgentRollbackItem[]>(() => outcome.value?.skipped ?? [])
const partial = computed<AgentRollbackItem[]>(() => outcome.value?.partial ?? [])
const failed = computed<AgentRollbackItem[]>(() => outcome.value?.failed ?? [])

/**
 * 「这一轮没有可回退的操作」—— **不是失败态**。
 *
 * 判据必须四个一起看（`ok` + `reverted === 0` + 三份清单都空）：
 * 只判 `reverted === 0` 会把「0 条退成、3 条不给退」也说成「没有可回退的操作」，
 * 那等于把服务端列出来的清单吞掉、替它下了个它没下的结论。
 */
const nothingToRollback = computed(() => {
  const s = outcome.value
  if (!s || s.ok !== true) return false
  return s.reverted === 0 && !s.skipped.length && !s.failed.length && !s.partial.length
})

/* ============================================================
 * 按钮：什么时候能点
 * ============================================================ */

/** 还有可点的动作：没点过 / 整轮被拒 / 有失败项（回退幂等，重试是安全的） */
const canRollback = computed(
  () => status.value === 'idle' || status.value === 'fail' || failed.value.length > 0
)

/**
 * 按钮文案。
 * `busy` 时按钮**留在原位**（变成「回退中…」并禁用）：连点会打两次账本，但按钮消失会让
 * 右边的「复制」跳位 —— 同一行的两个按钮，只有一个会动就是观感 bug。
 */
const buttonLabel = computed(() => {
  if (status.value === 'busy') return '回退中…'
  return status.value !== 'idle' && canRollback.value ? '重试' : '回退'
})

const canClick = computed(() => !props.disabled && canRollback.value)
const canCopy = computed(() => !!props.answerText.trim())

/**
 * 耗时文案（2026-10-27 三次修）
 *
 * ⚠️ 这里**只显示本轮耗时**，绝不显示累计。
 *
 * 演进过程（每次都是用户实测打回）：
 *    v1「用时 31 秒 · 共 54 秒」→ 用户：「没看懂…怎么又说用时31秒 然后又来个共54秒的？」
 *    v2「本次对话共 54秒」      → 用户：「他把上一次的对话时间也统计进来了
 *                                        每轮对话时间单独计算」
 *
 * 结论：轮末这一行是**本轮**的元信息，就该只放本轮的数字。
 *       "本次对话共耗时"挪到整个对话的最末尾单独一行（见 `AiChatStream` 的
 *       `conversationTotal`）—— 那里才是"会话级"的位置，不会和"轮级"混在一起。
 */
const fmtSec = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return rest === 0 ? `${m}分` : `${m}分${rest}秒`
}

const durationText = computed(() => {
  if (!props.durationMs) return ''
  return `本轮 ${fmtSec(props.durationMs)}`
})

/** 悬停：说明这是"本轮"耗时（并给出对话累计，需要时才看） */
const durationTitle = computed(() => {
  const parts = [`本轮耗时 ${fmtSec(props.durationMs)}`]
  if (props.totalDurationMs > 0) {
    parts.push(`本对话累计 ${fmtSec(props.totalDurationMs)}（在对话末尾单独显示）`)
  }
  return parts.join('，')
})

const onRollback = () => {
  if (!canClick.value) return
  emit('rollback', props.turnId)
}

const onCopy = () => {
  if (!canCopy.value) return
  emit('copy', props.answerText)
}
</script>

<style scoped>
/*
 * ⚠️ 高度与间距都长在这里，不在消息流那边：这一格**每一轮都有**，
 *    而 `AgentTurnRollback` 的上下留白就是消息间距的一部分
 *    （消息流给的是 `.message.msg-turn_end { margin-bottom: 0 }`）。
 *
 * 观感：平时是一条**很轻的动作行**（透明底、无描边，只有两个 ghost 按钮），
 * 有状态（busy / done / fail）时才变成左侧带色条的卡片 ——
 * 每一轮末尾都挂一张白卡片，长对话里会在消息流上刷出一排盒子。
 */
.agent-rollback {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 12px;
  padding: 2px 2px 0;
  max-width: min(100%, 560px);
  box-sizing: border-box;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  border-radius: 10px;
  background: transparent;
  font-size: 12.5px;
  line-height: 1.6;
  color: #4a5a72;
}

/* 有结果 / 出错时才铺底色与描边（`is-idle` 保持透明，不给消息流加盒子） */
.agent-rollback.is-busy,
.agent-rollback.is-done,
.agent-rollback.is-fail {
  padding: 7px 10px;
  border-color: #e5e7eb;
  border-left-color: #cbd5e1;
  background: #fff;
}

.agent-rollback.is-done {
  border-left-color: #34d399;
}

.agent-rollback.is-fail {
  border-left-color: #f87171;
  background: #fffafa;
}

.atr-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.atr-title {
  min-width: 0;
  overflow-wrap: anywhere;
}

/* 「正在回退」的转圈：只有它自己在动，别把整格做进动画里 */
.atr-spinner {
  flex: none;
  width: 12px;
  height: 12px;
  border: 2px solid #dbe3ee;
  border-top-color: #60a5fa;
  border-radius: 50%;
  box-sizing: border-box;
  animation: atr-spin 0.7s linear infinite;
}

@keyframes atr-spin {
  to {
    transform: rotate(360deg);
  }
}

.atr-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/*
 * 耗时记录（2026-10-27）
 *
 * 定位：这一行的**元信息**，不是操作按钮。
 * 所以用纯文字、不加边框/底色/悬停态 —— 一眼能区分"能点的"和"只是显示的"。
 * 字号比按钮文字小一档，颜色更淡，安静地待在右侧。
 */
.atr-duration {
  margin-left: auto;
  padding-left: 10px;
  font-size: 11.5px;
  color: var(--os-text-3, #8a94a6);
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  white-space: nowrap;
  flex: none;
  cursor: default;
}

.atr-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  padding: 2px 11px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
  cursor: pointer;
  /* ⚠️ 只列属性名，不写 `all`：`all` 会把布局属性也卷进逐帧重排（L28 守的就是这个机制） */
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.atr-btn:hover:not(:disabled) {
  border-color: #93b4f5;
  background: #f7faff;
  color: #2563eb;
}

.atr-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

/* 图标跟着文字一起变色（`el-icon` 默认是继承色，这里只统一尺寸/基线） */
.atr-icon {
  font-size: 13px;
}

/* 服务端原话（整轮被拒的原因）——自己一行，长句自由换行 */
.atr-reason {
  color: #b91c1c;
  overflow-wrap: anywhere;
}
</style>
