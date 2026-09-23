<!-- components/AgentRollbackNotice/index.vue -->
<!--
  回退结果栏 —— **长在消息列表之外**（`AiChatStream` 里 `.chat-messages` 与输入区之间的兄弟节点）。

  ## 为什么必须另起一栏（而不是继续画在轮末那一格）
  回退成功时**那一轮的消息会被整轮摘掉**（`outcome.dropped === true`），挂在轮末的
  `AgentTurnRollback` 跟着一起下线 —— 结果画在那一格上等于没画：用户只看到「消息突然少了一段」，
  「哪一条没退成、为什么」全丢了。所以它必须落在一个**不会跟着消息消失**的地方。

  ## 一条记录 = 一轮
  `entries` 的每一项是 `{ turnId, outcome }`。按轮分组而不是合并成一张大表：
  用户连点两轮回退时，「第一条是第 1 轮的问题、第二条是第 2 轮的问题」是用户唯一能对上号的信息。

  ## 只画不判
  条目文案取服务端给的 `reasonText`（中文人话），没有才回落原因码 `reason`；
  `failed` 取服务端报的 `error`。前端不合并清单、不改写原因、不总结成一句「部分失败」。

  ## 可关闭
  用户看完点掉即可；**下一条新的结果进来时会自动重新出现**（由 `AiChatStream` 的
  `noticeSignature` 复位），不用用户再去找。

  ## 「旧数据」也要如实说一句（`historyMatched === 0`）
  回退要撤的东西有两样，分在两个接口上：**写操作**（账本）与**这一轮的对话**（会话历史 + 快照）。
  老会话里那一轮可能**从来没有过轮次标记**（`turn_id` 是后加的列）—— 服务端按
  `(user_id, session_id, turn_id)` 一条都命不中，于是「从历史里删掉这一轮」这件事**做不成**，
  但**界面上这一轮确实已经移除了**（本地消息流 + 快照两步都成了）。
  这种情况必须说一句：不说的话用户看到「消息没了、历史里还在」只会以为回退没生效、一遍遍重点。
  ⚠️ 判据落在 `historyMatched === 0`（**不看 `del_flag`** 的命中行数）上：幂等重试时那一轮的行
  **还在**、只是 `del_flag` 已置位，所以 `matched > 0` —— 两个场景靠这一个数分得开，
  说成「旧数据」才是假话。行数与布尔两种形状的处理见 `historyUnmarked` 的注释。
-->
<template>
  <div class="arn-panel" role="status">
    <div class="arn-head">
      <span class="arn-title">回退结果</span>
      <button type="button" class="arn-close" title="关闭" aria-label="关闭" @click="$emit('close')">
        <el-icon>
          <Close />
        </el-icon>
      </button>
    </div>

    <div class="arn-list">
      <div v-for="entry in entries" :key="entry.turnId" class="arn-entry">
        <!-- 这一轮退成了几条（0 也是实话：这一轮可能只有查询 / 全都没退成，下面两张表会说为什么） -->
        <div class="arn-count">已回退 {{ entry.outcome.reverted }} 项操作</div>

        <!--
          旧数据：服务端历史里这一轮**没有轮次标记**（`historyMatched === 0`），
          所以「把它从历史/快照里删掉」这一半做不成，但**界面这一侧已经移除了**。
          这一句必须说 —— 不说的话用户看到「消息没了、历史里还在」，只会以为回退没生效、一遍遍重点。
          ⚠️ 只在「本来就没有标记」时说：幂等重试（上次已经删过了）时行还在、只是 `del_flag` 已置位，
             `historyMatched` 因此 **> 0**，那是正常成功，说什么「旧数据」就是假话。
          ⚠️ 判据（`historyUnmarked`）**只决定说不说这句话**，不参与回退本身的任何判断 ——
             旧数据照样要能从界面上移除，不许因为匹配不到就拦下后续步骤。
        -->
        <div v-if="historyUnmarked(entry.outcome)" class="arn-old">
          已从界面移除；但服务端历史里这一轮没有轮次标记（旧数据），删不掉历史里那几行。
        </div>

        <!-- 没有回退的条目（工具不支持、影响到了别人、已被物理删除…） -->
        <div v-if="entry.outcome.skipped.length" class="arn-block">
          <div class="arn-block-title">没有回退</div>
          <div v-for="(item, i) in entry.outcome.skipped" :key="'skipped-' + i" class="arn-item">
            <span v-if="opOf(item)" class="arn-op">{{ opOf(item) }}</span>
            <span class="arn-text">{{ reasonOf(item) }}</span>
          </div>
        </div>

        <!-- 只退回一部分（撤了，但没撤干净：如知识库回来了、里面的文档已物理删除） -->
        <div v-if="entry.outcome.partial.length" class="arn-block">
          <div class="arn-block-title">只退回一部分</div>
          <div v-for="(item, i) in entry.outcome.partial" :key="'partial-' + i" class="arn-item">
            <span v-if="opOf(item)" class="arn-op">{{ opOf(item) }}</span>
            <span class="arn-text">{{ reasonOf(item) }}</span>
          </div>
        </div>

        <!-- 回退报错的条目：原文取服务端的 `error`（这一栏只展示，重试在轮末那个组件上） -->
        <div v-if="entry.outcome.failed.length" class="arn-block">
          <div class="arn-block-title">回退失败</div>
          <div v-for="(item, i) in entry.outcome.failed" :key="'failed-' + i" class="arn-item">
            <span v-if="opOf(item)" class="arn-op">{{ opOf(item) }}</span>
            <span class="arn-text">{{ errorOf(item) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import type { AgentRollbackItem, AgentRollbackResult } from '@/api/ai/agent'

/**
 * 一轮的回退结果
 *
 * ⚠️ 这里**只声明本组件真正读到的字段**，不从 `@/composables/useAgentChat` import
 *    `TurnRollbackOutcome`：展示层不依赖业务 composable（两个消费方共用本组件，
 *    谁都不该在展示层再起一份业务状态）。字段名与服务端契约逐字一致。
 */
type RollbackOutcome = AgentRollbackResult & {
  /** 这一轮提问的正文（本轮消息已被摘掉；本组件不读它，列出来是为了形状完整） */
  userText?: string
  /** 这一轮的对话是否真的被移除了（同上，本组件不判） */
  dropped?: boolean | number
  /**
   * 服务端历史里按 `(user_id, session_id, turn_id)` 命中的行数（**不看 `del_flag`**）
   *
   * `0` = 这一轮在服务端历史里**没有轮次标记**（老数据，`turn_id` 是后加的列）——
   * 「从历史里删掉它」做不成，本组件要如实说一句（见 `historyUnmarked`）。
   * ⚠️ 名字与服务端契约逐字一致（`drop-turn` 响应里的 `matched`）。
   */
  historyMatched?: number
}

defineProps({
  /** 要展示的记录，一条 = 一轮：`{ turnId, outcome }`（`outcome` 必有值） */
  entries: {
    type: Array as () => Array<{ turnId: string; outcome: RollbackOutcome }>,
    default: () => []
  }
})

defineEmits(['close'])

/* ============================================================
 * 条目的三个取值（只挑字段，不编内容）
 * ⚠️ 与 `AgentTurnRollback` 里那三个同名函数是**同一套口径**（`opOf` / `reasonOf` / `errorOf`）：
 *    改一处必须改另一处，否则同一份服务端结果在两处会显示成两种样子。
 * ============================================================ */

/** 条目的定位：`工具.动作`（服务端给的原样标识符，界面上是次要信息） */
const opOf = (item: AgentRollbackItem) => [item?.tool, item?.action].filter(Boolean).join('.')

/** 没回退 / 只退回一部分的原因：优先服务端的中文 `reasonText`，缺了才退到原因码 `reason` */
const reasonOf = (item: AgentRollbackItem) => String(item?.reasonText || item?.reason || '')

/** 回退报错原文（服务端 `failed` 条目的 `error`） */
const errorOf = (item: AgentRollbackItem) => String(item?.error || '')

/**
 * 「服务端历史里本来就没有这一轮的轮次标记」—— 老数据，界面要如实说一句
 *
 * 判据分两步，缺一步就会说假话：
 *   ① `ok === true` —— `ok === false` 是**失败**，它的原因在轮末那一格显示
 *      （`AgentTurnRollback` 的 `atr-reason`），不在这一栏里冒充「旧数据」；
 *   ② `historyMatched === 0` —— 服务端按 `(user_id, session_id, turn_id)`、**不看 `del_flag`**
 *      命中 0 行。「不看 `del_flag`」正是这个字段存在的意义：幂等重试（上次已删过）时行**还在**，
 *      只是 `del_flag` 已置位，所以那时 `matched > 0` —— 两个场景靠它一个数就分得开。
 *   ③ 再核一遍「一行都没删」：`matched === 0` 本身就蕴含它（没命中就不可能删到行）。
 *      服务端把**行数**也交出来时（`dropped` 是 number）就照它核；`dropped` 是 boolean 时
 *      **不拿它当行数**——那是 composable 里的「这一轮有没有从界面移除」的开关，
 *      两种形状在本组件里都出现过，混淆会直接把这句话判反。
 *
 * ⚠️ `historyMatched` 读不到（undefined → `Number(...)` 是 NaN）时判 **false**（不说这句话）：
 *    宁可少说一句，也不要凭「没拿到」编一句「旧数据」。
 * ⚠️ 这个函数**只决定说不说这句话**，不参与回退本身的任何判断 ——
 *    老数据照样要能从界面上移除，不许因为匹配不到就拦下后续步骤。
 */
const historyUnmarked = (o: RollbackOutcome | null | undefined) => {
  if (!o || o.ok !== true) return false
  if (Number(o.historyMatched) !== 0) return false
  const rows = typeof o.dropped === 'number' ? o.dropped : 0
  return Number(rows) === 0
}
</script>

<style scoped>
/*
 * ⚠️ 这一栏是消息列表（`flex: 1`）与输入区（`flex-shrink: 0`）之间的**第三个** flex item。
 *    两条硬约束，缺一条就会把输入框挤出视线（本仓「输入框吸底」那条链的规矩）：
 *      · `flex-shrink: 0` —— 不许被压缩（压它没意义，里面的文字会重叠）；
 *      · `max-height` + `overflow-y: auto` —— 条目多时**自己滚**，别长到把消息区挤成 0。
 */
.arn-panel {
  flex-shrink: 0;
  margin: 0 12px 6px;
  max-height: min(32vh, 220px);
  overflow-y: auto;
  box-sizing: border-box;
  border: 1px solid #e5e7eb;
  border-left: 3px solid #fbbf24;
  border-radius: 10px;
  background: #fffdf7;
  font-size: 12.5px;
  line-height: 1.6;
  color: #4a5a72;
}

.arn-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px 5px;
  border-bottom: 1px solid #f3ecd9;
}

.arn-title {
  font-weight: 600;
  color: #92400e;
}

/* 关闭按钮：只动颜色/底色，别把 border 之类也卷进逐帧重排（`transition: all` 是本仓的禁例） */
.arn-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9aa5b5;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.arn-close:hover {
  background: #f3f4f6;
  color: #4b5563;
}

.arn-list {
  padding: 6px 10px 8px;
}

.arn-entry + .arn-entry {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #efe7d5;
}

.arn-count {
  color: #4b5563;
}

/*
 * 「旧数据」那一句（判据见 `historyUnmarked`）：这是**说明**，不是错误也不是警告 ——
 * 不铺底色、不用红色，只在条数那行下面加一行小字 + 左侧一条浅色竖线（与清单块区分开）。
 */
.arn-old {
  margin-top: 2px;
  padding-left: 7px;
  border-left: 2px solid #e5e7eb;
  color: #8a94a6;
  font-size: 12px;
}

.arn-block {
  margin-top: 5px;
}

.arn-block-title {
  margin-bottom: 2px;
  font-size: 11px;
  font-weight: 600;
  color: #8a94a6;
  letter-spacing: 0.4px;
}

.arn-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  overflow-wrap: anywhere;
}

.arn-op {
  flex: none;
  padding: 0 7px;
  border: 1px solid #eceff3;
  border-radius: 9px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 11px;
  line-height: 1.65;
}

.arn-text {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
