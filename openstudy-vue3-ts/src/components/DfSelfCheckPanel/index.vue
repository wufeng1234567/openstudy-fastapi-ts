<template>
  <div class="selfcheck-panel">
    <!-- 工具条 -->
    <div class="sc-toolbar">
      <el-button size="small" type="primary" :disabled="running" @click="startLoop">
        协议/循环
      </el-button>
      <el-button size="small" type="primary" :disabled="running" @click="startLive">
        真链路端到端
      </el-button>
      <el-button size="small" type="danger" plain :disabled="!running" @click="onAbort">
        中止
      </el-button>
      <el-button size="small" plain :disabled="running" @click="doClean">清理测试数据</el-button>
    </div>

    <!-- 说明：说清两组各需要什么、代价是什么 -->
    <div class="sc-hint">
      <div><b>协议/循环</b>：把模型回复脚本化，跑真循环代码，<b>完全不碰 DS</b>，秒级、安全，随便反复跑。</div>
      <div>
        <b>真链路</b>：真扩展 + 真 DS 页面 + 真后端。一条几十秒、整体要几分钟 ——
        用例之间刻意留了 5 秒间隔，因为 DS 网页端对连续消息有限流，连着打会被它挡下来。
      </div>
    </div>

    <div class="sc-sub">
      <el-input
        v-model="only"
        size="small"
        placeholder="只跑指定前缀，如 DF-LOOP-"
        clearable
        class="sc-only"
      />
      <span class="sc-count">{{ matchedCount }} 条</span>
    </div>

    <!-- 前置条件（只有真链路组会填） -->
    <div v-if="chips.length" class="sc-chips">
      <span
        v-for="c in chips"
        :key="c.label"
        :class="['sc-chip', c.ok ? 'ok' : 'bad']"
        :title="c.hint || c.label"
      >
        <OsIcon :name="c.ok ? 'check' : 'close'" :size="12" /> {{ c.label }}
      </span>
    </div>

    <!-- 进度 -->
    <div v-if="running || progress.total" class="sc-progress">
      <el-progress :percentage="pct" :stroke-width="6" :show-text="false" />
      <div class="sc-progress-text">
        {{ progress.group }} · {{ progress.done }}/{{ progress.total }} ·
        通过 {{ progress.passed }} · 失败 {{ progress.failed }}
        <template v-if="progress.aborted">· 中止 {{ progress.aborted }}</template>
        <template v-if="progress.current"> · {{ progress.current }}</template>
      </div>
    </div>

    <!-- 日志窗口 -->
    <div ref="logEl" class="sc-log" @scroll="onScroll">
      <div v-for="e in visibleEntries" :key="e.id" :class="['sc-line', e.level]">
        <span class="sc-time">{{ hms(e.ts) }}</span>
        <span class="sc-level">{{ e.level.toUpperCase() }}</span>
        <span class="sc-msg">
          <span v-if="e.caseId" class="sc-case">{{ e.caseId }}</span>
          <span>{{ e.message }}</span>
        </span>
        <pre v-if="e.detail" class="sc-detail">{{ e.detail }}</pre>
      </div>
      <div v-if="!visibleEntries.length" class="sc-empty">
        还没有日志。点上面的按钮开始。
      </div>
    </div>

    <!-- 底部：级别筛选 + 导出 -->
    <div class="sc-foot">
      <div class="sc-levels">
        <el-checkbox
          v-for="l in LEVELS"
          :key="l"
          size="small"
          :model-value="levelOn.has(l)"
          @change="() => toggleLevel(l)"
        >
          {{ l }}
        </el-checkbox>
      </div>
      <div class="sc-actions">
        <el-button size="small" text :type="onlyFail ? 'primary' : ''" @click="onlyFail = !onlyFail">
          只看失败
        </el-button>
        <el-button v-if="!stick" size="small" text @click="jumpBottom">回到底部</el-button>
        <el-button size="small" text :disabled="running" @click="clear">清空</el-button>
        <el-button size="small" text :disabled="!rows.length" @click="exportLog">导出 .log</el-button>
        <el-button size="small" text :disabled="!rows.length" @click="exportJson">导出 .json</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ds-free 自检面板（**仅开发环境**，由 AiAssistant 动态 import）
 *
 * 为什么要有它：原来那套 Node 脚本（`tests/check_agent_dsfree.mjs`）跑真链路要
 * 另起一个干净 Chrome、再手动给那个实例登录 DS 和 OpenStudy —— 成本全转嫁给了使用者。
 * 这个面板复用**你当前已经登录好的浏览器**（扩展已加载、DS 已登、OpenStudy 已登），
 * 点一下就跑。
 *
 * 两组测试的差别见模板里的说明；日志、结果、运行状态都放在模块级 store 里
 * （`src/devtools/dfSelfCheck/store.ts`），所以**关掉抽屉不会中止运行也不丢日志**。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import {
  entries,
  rows,
  running,
  progress,
  append,
  clear,
  beginRun,
  endRun,
  abortGroup,
  downloadText,
  toText,
  toJson,
  fileStamp,
  runContext
} from '@/devtools/dfSelfCheck/store'
import type { Row } from '@/devtools/dfSelfCheck/evaluate'
import type { DfCase } from '../../../tests/df_cases.mjs'
import { LOOP_CASES, LIVE_CASES, SELF_LIVE_CASES, PREFIX } from '../../../tests/df_cases.mjs'
import { runLoopGroup } from '@/devtools/dfSelfCheck/runLoopGroup'
import {
  runLiveGroup,
  preflight,
  seedTestData,
  cleanTestData,
  type PreflightItem
} from '@/devtools/dfSelfCheck/runLiveGroup'
// 这几个模块只在开发环境被打进包（本组件本身就是 dev-only 动态 import）
import { hasDSProxy } from '@/utils/ds-proxy'
import { getToken } from '@/utils/auth'

defineOptions({ name: 'DfSelfCheckPanel' })

const LEVELS = ['debug', 'info', 'pass', 'fail', 'warn', 'error'] as const
type Level = (typeof LEVELS)[number]

const only = ref('')
const onlyFail = ref(false)
// debug 默认关掉：事件流很吵，要看协议怎么跑偏的时候再勾
const levelOn = ref<Set<Level>>(new Set(['info', 'pass', 'fail', 'warn', 'error'] as Level[]))
const chips = ref<PreflightItem[]>([])
const stick = ref(true)
const logEl = ref<HTMLElement | null>(null)

const pct = computed(() =>
  progress.total ? Math.round((progress.done / progress.total) * 100) : 0
)

/** 当前会跑哪些用例（受前缀筛选影响） */
function pick(all: DfCase[]): DfCase[] {
  const p = only.value.trim()
  return p ? all.filter((c) => c.id.startsWith(p)) : all
}

const matchedCount = computed(() => pick([...LOOP_CASES, ...LIVE_CASES, ...SELF_LIVE_CASES]).length)

const visibleEntries = computed(() => {
  let list = entries.value.filter((e) => levelOn.value.has(e.level as Level))
  if (onlyFail.value) list = list.filter((e) => e.level === 'fail' || e.level === 'error')
  return list
})

function toggleLevel(l: Level) {
  const s = new Set(levelOn.value)
  s.has(l) ? s.delete(l) : s.add(l)
  levelOn.value = s
}

function hms(ts: number): string {
  const d = new Date(ts)
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

// ---- 日志窗口：只在用户本来就贴底时才自动跟到底 ----
function onScroll() {
  const el = logEl.value
  if (!el) return
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 50
}

function jumpBottom() {
  const el = logEl.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  stick.value = true
}

watch(
  () => entries.value.length,
  async () => {
    if (!stick.value) return
    await nextTick()
    jumpBottom()
  }
)

onMounted(() => nextTick(jumpBottom))

// ---- 环境信息（写进导出文件的头部，排查时很值钱） ----
function envInfo(): Record<string, string> {
  return {
    页面: location.href,
    扩展: hasDSProxy() ? '已注入' : '未检测到',
    登录: getToken() ? '已登录' : '未登录',
    UA: navigator.userAgent
  }
}

/** 前置不满足 / seed 失败时，把原因**写进结果行** —— 只在横幅上写一句，用前缀筛过之后就看不见了 */
function blockedRows(cases: DfCase[], reason: string): Row[] {
  return cases.map((c) => ({
    id: c.id,
    suite: c.suite,
    title: c.title,
    status: '中止' as const,
    secs: null,
    asserts: [{ label: '前置条件未满足', pass: false, actual: reason }]
  }))
}

function notify(title: string) {
  const bad = progress.failed + progress.aborted
  ElNotification({
    title,
    message: `${progress.passed} 通过 / ${progress.failed} 失败${
      progress.aborted ? ` / ${progress.aborted} 中止` : ''
    }`,
    type: bad ? 'warning' : 'success',
    duration: bad ? 8000 : 3000
  })
}

// =====================================================================
// 协议/循环（桩模型，不碰 DS）
// =====================================================================
async function startLoop() {
  if (running.value) return
  const cases = pick(LOOP_CASES)
  if (!cases.length) return void ElMessage.warning('没有匹配的用例，检查一下前缀')

  clear()
  chips.value = []
  beginRun('协议/循环', cases.length, envInfo())
  try {
    rows.value = await runLoopGroup(cases)
  } catch (e: any) {
    append('error', `驱动自身出错：${String(e?.message || e)}`, { scope: 'runLoop' })
  } finally {
    endRun()
    notify('协议/循环 结束')
  }
}

// =====================================================================
// 真链路端到端（真扩展 + 真 DS + 真后端）
// =====================================================================
async function startLive() {
  if (running.value) return
  const cases = pick([...LIVE_CASES, ...SELF_LIVE_CASES])
  if (!cases.length) return void ElMessage.warning('没有匹配的用例，检查一下前缀')

  // ⚠️ DS 会话隔离不了（见 runLiveGroup 头部注释），开跑前必须说清楚代价。
  //    消息保持**单段纯文本**：ElMessageBox 的 message 渲染在 <p> 里，`\n` 会被折叠成空格，
  //    想换行就得开 dangerouslyUseHTMLString —— 为一个提示引 HTML 不划算。
  const n = cases.length
  try {
    await ElMessageBox.confirm(
      `这 ${n} 条会依次发到「你当前那个 DeepSeek 会话」里（扩展的发送目标锁在最早打开的那个 DS 标签页上，切不走），` +
        `每条都带 [自检] 前缀，事后好认。整体要几分钟（用例之间有 5 秒间隔，规避 DS 的发送频率限制）。` +
        `想让 DS 历史干净的话，先去 DS 页面点一下「新对话」再回来点开始。`,
      '真链路端到端',
      {
        confirmButtonText: '开始',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  clear()
  beginRun('真链路端到端', cases.length, envInfo())

  // 前置检查
  chips.value = await preflight()
  const bad = chips.value.filter((c) => !c.ok)
  if (bad.length) {
    const reason = bad.map((c) => `${c.label}：${c.hint}`).join('；')
    append('fail', `前置条件不满足，未执行：${reason}`, { scope: 'runLive' })
    rows.value = blockedRows(cases, reason)
    progress.done = cases.length
    progress.aborted = cases.length
    endRun()
    notify('真链路 未执行')
    return
  }

  // seed 测试数据
  append('info', '准备测试数据…', { scope: 'seed' })
  const seed = await seedTestData()
  if (!seed.ok) {
    append('fail', `测试数据准备失败：${seed.detail}`, { scope: 'seed' })
    // ⚠️ 必须清一次：seed 可能「题库建好了、导题失败了」，不清就留个 __df_test__ 残骸在用户库里
    const cleaned = await cleanTestData()
    append(cleaned.ok ? 'pass' : 'warn', cleaned.detail, { scope: 'seed' })
    rows.value = blockedRows(cases, `测试数据准备失败：${seed.detail}`)
    progress.done = cases.length
    progress.aborted = cases.length
    endRun()
    notify('真链路 未执行')
    return
  }
  append('pass', seed.detail, { scope: 'seed' })

  try {
    rows.value = await runLiveGroup(cases, {
      bankName: seed.bankName,
      userId: readUserId()
    })
  } catch (e: any) {
    append('error', `驱动自身出错：${String(e?.message || e)}`, { scope: 'runLive' })
  } finally {
    // 无论成功失败都清干净 —— 崩在中途留下的 __df_test__ 题库会污染用户数据
    append('info', '清理测试数据…', { scope: 'seed' })
    const cleaned = await cleanTestData()
    append(cleaned.ok ? 'pass' : 'warn', cleaned.detail, { scope: 'seed' })
    endRun()
    notify('真链路 结束')
  }
}

/** 从 localStorage 里读当前用户 id（后端工具执行要它） */
function readUserId(): number | string {
  try {
    return Number(JSON.parse(localStorage.getItem('user') || '{}').id) || 0
  } catch {
    return 0
  }
}

function onAbort() {
  abortGroup()
  append('warn', '已请求中止…', { scope: 'panel' })
}

async function doClean() {
  if (running.value) return
  clear()
  append('info', `清理 ${PREFIX} 前缀的测试数据…`, { scope: 'seed' })
  const r = await cleanTestData()
  append(r.ok ? 'pass' : 'fail', r.detail, { scope: 'seed' })
  ElMessage[r.ok ? 'success' : 'warning'](r.detail)
}

// =====================================================================
// 导出
// =====================================================================
function groupSlug(): string {
  return runContext.group.includes('真链路') ? 'live' : 'loop'
}

function exportLog() {
  downloadText(`selfcheck-${groupSlug()}-${fileStamp()}.log`, toText(), 'text/plain')
}

function exportJson() {
  downloadText(
    `selfcheck-${groupSlug()}-${fileStamp()}.json`,
    toJson(rows.value as unknown as Array<Record<string, any>>),
    'application/json'
  )
}
</script>

<style scoped lang="scss">
.selfcheck-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 14px 8px;
  font-size: 12px;
}

.sc-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sc-hint {
  padding: 6px 8px;
  background: #f7f9fc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  color: #6b7280;
  line-height: 1.6;

  b {
    color: #374151;
  }

  code {
    padding: 0 3px;
    background: #eef2f7;
    border-radius: 3px;
    color: #409eff;
  }
}

.sc-sub {
  display: flex;
  align-items: center;
  gap: 8px;

  .sc-only {
    width: 170px;
  }

  .sc-count {
    color: #9ca3af;
  }
}

.sc-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;

  .sc-chip {
    padding: 2px 8px;
    border-radius: 10px;
    border: 1px solid transparent;

    &.ok {
      color: #16a34a;
      background: #f0fdf4;
      border-color: #bbf7d0;
    }

    &.bad {
      color: #dc2626;
      background: #fef2f2;
      border-color: #fecaca;
    }
  }
}

.sc-progress {
  .sc-progress-text {
    margin-top: 3px;
    color: #6b7280;
  }
}

.sc-log {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  padding: 6px 8px;
  background: #1e1e1e;
  border-radius: 6px;
  color: #d4d4d4;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.55;
}

.sc-line {
  display: flex;
  flex-wrap: wrap;
  column-gap: 6px;

  .sc-time {
    color: #6a9955;
    flex-shrink: 0;
  }

  .sc-level {
    flex-shrink: 0;
    width: 40px;
  }

  .sc-msg {
    flex: 1;
    min-width: 0;
    word-break: break-word;
  }

  .sc-case {
    margin-right: 5px;
    color: #569cd6;
  }

  .sc-detail {
    flex: 0 0 100%;
    margin: 0 0 2px 52px;
    padding: 0;
    color: #9cdcfe;
    font: inherit;
    white-space: pre-wrap;
    word-break: break-word;
  }

  &.debug .sc-level {
    color: #6b7280;
  }
  &.debug .sc-msg {
    color: #9ca3af;
  }
  &.info .sc-level {
    color: #569cd6;
  }
  &.pass .sc-level {
    color: #4ec9b0;
  }
  &.pass .sc-msg {
    color: #b5cea8;
  }
  &.fail .sc-level {
    color: #f48771;
  }
  &.fail .sc-msg {
    color: #f48771;
  }
  &.warn .sc-level {
    color: #dcdcaa;
  }
  &.warn .sc-msg {
    color: #dcdcaa;
  }
  &.error .sc-level,
  &.error .sc-msg {
    color: #ff6b6b;
  }
}

.sc-empty {
  padding: 12px 0;
  color: #6b7280;
  text-align: center;
}

.sc-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;

  .sc-levels {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
  }

  .sc-actions {
    display: flex;
    gap: 2px;
  }
}
</style>
