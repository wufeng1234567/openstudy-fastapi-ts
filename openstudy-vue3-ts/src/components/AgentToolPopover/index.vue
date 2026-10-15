<!-- components/AgentToolPopover/index.vue -->
<!--
  智能体「可用工具」弹层（底部工具栏入口）
  ============================================
  为什么要有它：工具清单原来是一条**常驻横条**（`chat.vue` 里的 `.tool-bar`，
  在标题栏下面占满一整行）。工具名 + tooltip 平时没人看，却一直吃掉一行高度 ——
  把它收进工具栏的一个弹层：默认只显示一个小按钮 + 可用个数，点开才看清单。

  ⚠️ 2026-09-21 起这里的职责变了：**入口按钮与清单都由本组件自己负责**。
  之前清单靠上层（`useAgentChat` 的 `tools`，只有 `meta` 事件会填）传进来，
  于是 `reset()` 把它清成 `[]` 时入口按钮会**整个消失**（用户报的第 ③ 条：
  「切换到新会话窗口后，可用工具按钮就会消失」）；而且那样只能「看」不能「改」
  （用户报的第 ① 条）。现在：挂载期自己拉一次 `GET /ai/agent/tools`（全量清单 +
  每条自己的开关状态），入口按钮**无条件渲染**，清单里每行一个开关。

  数据来源只有**一处**：`rows` —— 本组件自己拉的**当前配置**（全量，含被屏蔽的条目），
  行上的开关绑它。

  ⚠️ 2026-09-21 用户裁决删掉了整个脚注块（模型行 + 工具数行，以及只为它们而存在的两个 prop）。
  所以这里**不存在**第二份数据来源 —— 清单回答的就是「现在配的是什么」这一件事。

  ⚠️ 弹层的三种状态**必须分得开**（这是用户报的第 ③ 条的另一半）：
    ① 正在读清单 → 中性加载态；
    ② 清单没取到（`rows` 为空）→ 明说「没取到」+ 一个「重试」；
    ③ 取到了但每条都被屏蔽 → **整张清单照常列出**，每行带「已屏蔽」。
  ②**绝不能**显示成「一个工具都没有」—— 后端注册表不可能为空（全被禁用时清单仍然在，
  只是每条 `disabled === 1`），所以零条就等于请求失败，说成「没有工具」是一句假话。
-->

<template>
  <!-- ⚠️ 这里**没有** `v-if`，是刻意的：用户明确要求「可用工具按钮无论什么时候都要正常出现」。
       清单由本组件自己拉，所以任何「清单为空就把按钮藏起来」的闸门都会把按钮藏到**最需要它的时刻**
       —— 取不到清单时，这个按钮正好是重试入口。别再把它加回来（2026-09-21 已删过一次，L33 守着）。 -->
  <el-popover placement="top-start" :width="380" trigger="click" popper-class="agent-tool-popover">
    <template #reference>
      <button type="button" class="tool-entry" :title="entryTitle">
        <el-icon>
          <Tools />
        </el-icon>
        <!-- 徽标**只在清单加载完成时**出数字：加载中 / 没取到都给 `badgeCount = null`
             → 不渲染。写死 `{{ rows.length }}` 的话，请求失败时按钮上挂着一个 `0`,
             读起来就是「我一个工具都没有」—— 那是假的（后端一定有工具）。 -->
        <span v-if="badgeCount !== null" class="tool-entry-count">{{ badgeCount }}</span>
      </button>
    </template>

    <div class="atp-head">
      <span class="atp-title">可用工具</span>
      <span class="atp-sub">{{ headSub }}</span>
    </div>

    <!-- ① 正在读清单 -->
    <div v-if="loading" class="atp-state atp-loading">正在读取工具清单…</div>

    <!-- ② 没取到：**不是**「没有工具」，要说清楚，并给一个重试出口。
         条件写成独立的 `v-if`（不用 `v-else-if`）—— 与 `.kb-load-failed` 同一套写法：
         各条条件自带 `rows.length`，本来就互斥，不依赖兄弟链的语义。 -->
    <div v-if="!loading && !rows.length" class="atp-state atp-failed">
      <span class="atp-failed-text">
        工具清单这次没取到。后端注册表里一定有工具 —— 取不到是这次请求失败了，
        不是「一个工具都没有」。
      </span>
      <el-button size="small" text type="primary" class="atp-retry" @click="load()">
        重试
      </el-button>
    </div>

    <!-- ③ 拿到了清单：**全量**列出（含被屏蔽的条目）—— 被屏蔽的行必须留在列表里，
           否则用户关掉一个工具之后就再也找不到开关、没法打开它回来。 -->
    <template v-if="!loading && rows.length">
      <!-- 工具条：搜索 + 「全选」。放在清单**上方**，用户先看到「能不能一键改」再逐行看 -->
      <div class="atp-tools-bar">
        <span class="atp-search">
          <input v-model="keyword" class="atp-search-input" type="text"
            placeholder="搜工具（中文名 / 说明 / 英文名）" @keydown.esc="keyword = ''" />
          <button v-if="keyword" type="button" class="atp-search-clear" title="清空（Esc）"
            @click="keyword = ''">清空</button>
        </span>
        <span class="atp-toggle-all" @click.stop
          :title="allEnabled ? '全部屏蔽（智能体将不会调用任何工具）' : '全部启用'">
          <el-switch :model-value="allEnabled" size="small" :loading="bulkBusy" :disabled="busy"
            @update:model-value="toggleAll($event)" />
          <span class="atp-toggle-all-text">全选</span>
        </span>
      </div>
      <!-- 「全选」的**作用范围**要说出来：它作用于全部工具，与搜索框无关。
           不说清楚的话，「只搜出来 3 个、点全选却改了 10 个」就会被读成 bug。 -->
      <div class="atp-tools-hint">
        已启用 {{ enabledCount }}/{{ rows.length }} 个 ·「全选」作用于全部 {{ rows.length }} 个（与搜索无关）
      </div>

      <div v-if="matchedRows.length" class="atp-list">
        <div v-for="t in matchedRows" :key="t.name"
          :class="['atp-item', { blocked: t.disabled === 1 }]">
          <div class="atp-item-main">
            <!-- 主标题是**中文名**（`label`）；它缺失时才回落显示英文 `name`。
                 回落只涉及英文**工具名**，不会把面向模型的英文描述带进界面。 -->
            <span class="atp-name">{{ t.label || t.name }}</span>
            <!-- 英文工具名作为小字副标题：用户报 bug / 我查日志时都要用它定位 -->
            <span class="atp-key">{{ t.name }}</span>
            <!-- 屏蔽状态**常驻**显示（不藏在 hover 里、不只在开关上）：
                 用户要能一眼看出「智能体现在用不了哪些工具」 -->
            <span v-if="t.disabled === 1" class="atp-item-blocked">已屏蔽</span>
            <!-- 说明用**中文层**（`descriptionZh`）。⚠️ 空就留空 —— **绝不回落**
                 英文 `function.description`：那是面向模型的文本，摆给用户看正是本次要修掉的缺陷。 -->
            <span v-if="t.descZh" class="atp-desc">{{ t.descZh }}</span>
          </div>

          <!-- 开关：**受控式**，显示值只来自服务端数据（`toolEnabled`）。
               ⚠️ `:model-value` 绑的是**布尔表达式**，不要绑 `t.disabled` 本身，
                  也**不要**加 `:active-value` / `:inactive-value` —— 见 `toolEnabled` 的注释：
                  绑定值一旦不落在 `[activeValue, inactiveValue]` 里（后端下发的是 0|1 整数），
                  el-switch 会在**挂载期、无任何用户操作**的情况下 emit 一次，
                  每次打开清单都会把所有行写成一遍。 -->
          <span class="atp-toggle" @click.stop
            :title="toolEnabled(t) ? '智能体现在可以用它；关掉就不再下发' : '已屏蔽：智能体不会再下发它'">
            <el-switch :model-value="toolEnabled(t)" size="small" :loading="togglingName === t.name"
              :disabled="busy" @update:model-value="toggleTool(t, $event)" />
          </span>
        </div>
      </div>

      <!-- ③c 搜索没命中：与「没取到」（请求失败）、「全被屏蔽」（用户自己关的）**都不是一回事**，
           所以文案必须能分辨，并且带上用户敲的那个词。 -->
      <div v-else class="atp-state atp-no-hit">
        没搜到「{{ keyword.trim() }}」。换个词，或清空搜索看全部 {{ rows.length }} 个工具。
      </div>
    </template>

    <!-- ③b 清单在、但每条都被屏蔽：这句话与 ② 的「没取到」是两件事，
         文案必须分开（前者是用户自己关的，后者是请求失败）。 -->
    <div v-if="!loading && rows.length && !enabledCount" class="atp-all-off">
      清单里每个工具都被你屏蔽了 —— 智能体这次不会调用任何工具。把开关打开就能恢复。
    </div>

    <!-- ⚠️ 这里原来有一整块脚注（「本次运行模型」+ 工具数两行），已按用户裁决整块删除（2026-09-21）。
         别加回来 —— L41 会在**源码文本层面**断「不许再出现」，并且 L43 断 chat.vue 不许再传
         对应的两个 prop。用户保留的是上面 `.atp-head` 那一行（`headSub`）。 -->
  </el-popover>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Tools } from '@element-plus/icons-vue'
import { fetchAgentToolsForUi, saveAgentToolPref, saveAllToolPrefs } from '@/api/ai/agentDsFree'
import type { AgentToolDefinition, AgentToolsPayload } from '@/api/ai/agent'

const props = defineProps({
  /**
   * 「当前模型」：`chat.vue` 传的是 `model || activeModel`（选择器当前值；未显式选过时回落到
   * 后端 `meta` 回报的那个）—— 语义由 `chat.vue` 那边决定，本组件不参与判断。
   *
   * ⚠️ 它现在**没有消费者**：脚注那行「模型名」已随整块脚注按用户裁决删除（2026-09-21）。
   *    保留这个 prop 是因为 `chat.vue` 的绑定与 L15 都还在（那是另一处决定）；
   *    要删就两边**同一轮**一起动，别只删这边（会留下一个「传了但没人接」的绑定）。
   */
  model: { type: String, default: '' }
})

/** 清单里的一行（界面口径：中文名 / 英文名 / 中文说明 / 开关状态） */
interface ToolRow {
  name: string
  /** 界面主标题：中文名（`label`）。缺失时回落显示 `name`，见模板 */
  label: string
  /** 界面说明：**中文一句说明**（`descriptionZh`）。空则留空，**不回落英文** */
  descZh: string
  disabled?: 0 | 1
}

/**
 * 把后端下发的条目归一成一行。
 *
 * ⚠️ 这里只有**一个来源、一种形状**：`fetchAgentToolsForUi()` / `saveAgentToolPref()` 回传的
 *    `AgentToolsPayload.tools`，条目是 Function Calling schema
 *    （`{ type, function: { name, description }, disabled, label, descriptionZh }`）——
 *    GET 与 PUT 回显是同一份（后端写成功后会重新读库、拼一份全量清单回来）。
 *
 * ⚠️⚠️ **两条道不许混**（本次改动的核心）：
 *    · `function.name` / `function.description` 是**模型侧**的（全英文，进提示词）；
 *    · `label` / `descriptionZh` 是**界面侧**的，在 `function` **外面**。
 *    所以这里只把**界面侧**的两个字段抄进来当文案，`function.description` 一概不进界面：
 *    把面向模型的英文描述直接摆给用户看，正是这次要修掉的缺陷。
 *
 * ⚠️ 因此**不要**在这里加「两种形状都认」的兜底（早先版本有过，是我写错的）：
 *    它当时自称是为 `meta` 事件那种**拍平**的 `AgentToolMeta { name, description }` 兜底，
 *    可那类条目从来没进过这条路径 —— 它只喂过某个 prop 的 `.length`（那个 prop 已随脚注删除），
 *    也就是说那条兜底**连一个调用点都没有**，谁也走不到。留一条谁也走不到的兜底，只会让下一个
 *    读到这里的人以为「清单有可能回拍平形状」；而形状真出问题时，它会把错误**静默抹平**
 *    （画出一行看着正常、其实字段是空的条目）。真要有第二种形状进来，类型标注会先逼出一次
 *    **显式转换** —— 那才是想要的失败方式（L44 守着「只读 `entry.function`」这一格）。
 *    （`?.` 只为「形状意外时别抛」：在 `.map` 里抛出去会把整张列表画成空白。）
 */
function toRow(entry: AgentToolDefinition): ToolRow {
  const fn = entry?.function
  return {
    name: String(fn?.name || ''),
    // 界面侧字段：**不在 `function` 里面**，所以它们进不了提示词（L11 那组断言守着）
    label: entry?.label ? String(entry.label) : '',
    descZh: entry?.descriptionZh ? String(entry.descriptionZh) : '',
    // ⚠️ `disabled` 是 **0|1 整数**（见 `AgentToolDefinition`）。这里归一成 0/1，
    //    判据一律写 `=== 1`；取反着写（`!t.disabled`）会把 `0 = 启用` 读成禁用。
    disabled: entry?.disabled === 1 ? 1 : 0
  }
}

/** 管理清单：**全量**（含被屏蔽的条目），行上的开关绑它 */
const rows = ref<ToolRow[]>([])
/** 正在读清单（含「重试」那一次）。初值 true：挂载请求还没回来时不许先画出「没取到」 */
const loading = ref(true)
/** 正在写的那一行 —— 写的时候所有开关都锁住，别让两次写撞在一起 */
const togglingName = ref('')

/** 用服务端回传的清单刷新界面（显示值永远来自服务端，不做本地翻转） */
const applyPayload = (payload: AgentToolsPayload | null) => {
  if (!payload || !Array.isArray(payload.tools)) return
  rows.value = payload.tools.map(toRow)
}

/**
 * 拉一次清单（挂载期一次；「重试」按钮再拉一次）
 *
 * ⚠️ 「取到了但一条都没有」不作单独的状态位：后端注册表不可能为空，所以
 *    `rows.length === 0` 就等于**这次没取到**。少一个状态位就少一处两处不同步。
 *    （接口本身已经把网络错吃掉了 —— 见 `fetchAgentToolsForUi` 的注释，失败返回空清单。）
 */
const load = async () => {
  loading.value = true
  try {
    applyPayload(await fetchAgentToolsForUi())
  } catch (e) {
    // 第二道防线：上面那个接口按约定不抛，真抛上来也不能让弹层崩掉（否则整个工具栏都点不开）
    console.warn('[agent-tools] 读取工具清单失败', e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 这个工具现在**可用吗**（开关的「开」状态，`true` = 智能体会下发它）
 *
 * ⚠️⚠️ 返回值**必须是布尔**（`true`/`false`），这不是顺手写的：`el-switch` 在 setup 期
 *    会检查绑定值是否落在 `[activeValue, inactiveValue]` 里，不在就**在没有用户操作的情况下**
 *    emit 一次 `update:modelValue`（已安装的 `element-plus@2.14.5`，
 *    `es/components/switch/src/switch.vue_vue_type_script_setup_true_lang.mjs:71-76`，
 *    默认 `activeValue = true` / `inactiveValue = false`）。
 *    后端下发的 `disabled` 是 **0|1 整数**，原样绑上去必然命中那一格
 *    ⇒ **打开一次清单就对每一行各发一次 PUT**（用户根本没拨开关）。
 *    绑恒为布尔的表达式则永远落在默认取值域里，不可能触发。
 *    （模板里同时**不要**写 `:active-value` / `:inactive-value`。）
 *
 * ⚠️ 判据是 `disabled !== 1`，不能写成「`=== 0` 才算可用」：
 *    `undefined`（后端还没下发这个字段）时 `!== 1` 判「可用」—— 与「默认全部工具开启」
 *    这个用户决定一致；`=== 0` 会把每一个工具都画成「已屏蔽」。
 */
const toolEnabled = (t: ToolRow) => t.disabled !== 1

/** 可用（没被屏蔽）的工具个数 */
const enabledCount = computed(() => rows.value.filter((t) => t.disabled !== 1).length)

/** 搜索关键词（按**中文名 / 中文说明 / 英文名**三处匹配，见 `matchedRows`） */
const keyword = ref('')

/**
 * 搜索命中的行
 *
 * 匹配三处：中文名（`label`）、中文说明（`descZh`）、英文名（`name`）——
 * 用户既可能记得「题库管理」，也可能记得 `bank_manage`，还可能是说明里的某个词。
 * trim 后不区分大小写（英文名是小写，用户可能大写着敲）。
 *
 * ⚠️ 它**只影响列表的显示**，不影响「全选」的作用范围（理由见 `toggleAll`）。
 * ⚠️ 不过滤原数组：`rows` 是服务端回传的权威值，过滤结果只用于渲染。
 */
const matchedRows = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((t) =>
    `${t.label}\n${t.descZh}\n${t.name}`.toLowerCase().includes(q)
  )
})

/**
 * 「全选」现在的状态：**只有每一个工具都可用**才是 `true`
 *
 * 用户明确要求：「当检测到有一个工具没选上，全选按钮也要自动显示关闭」——
 * 所以判据是 `every`，不是「有没有一个可用」。
 *
 * ⚠️ 返回值必须是**布尔**，理由与 `toolEnabled` 完全一样（`el-switch` 在 setup 期会检查
 *    绑定值是否落在 `[activeValue, inactiveValue]` 里，不在就**在没有用户操作的情况下**
 *    emit 一次）。这里 `every()` 天然给布尔，别改成返回 0|1。
 * ⚠️ 空清单给 `false`；而且模板里那个控件只在 `!loading && rows.length` 时才渲染 ——
 *    拿不准的时候**不显示**，不许画成「已全选」。
 */
const allEnabled = computed(
  () => rows.value.length > 0 && rows.value.every((t) => t.disabled !== 1)
)

/** 正在批量写（「全选」那一次） */
const bulkBusy = ref(false)

/** 有写在飞：逐行开关与「全选」一起锁住，别让两次写撞在一起 */
const busy = computed(() => bulkBusy.value || !!togglingName.value)

/** 入口徽标上的数字：**只在清单加载完成时**给值，其它时候 `null`（模板据此不渲染） */
const badgeCount = computed(() => (loading.value || !rows.value.length ? null : enabledCount.value))

const entryTitle = computed(() => {
  if (loading.value) return '可用工具 —— 正在读取清单…'
  if (!rows.value.length) return '可用工具 —— 清单没取到，点开可以重试'
  return `可用工具 ${enabledCount.value}/${rows.value.length} 个可用（点击管理）`
})

const headSub = computed(() => {
  if (loading.value) return '正在读取…'
  if (!rows.value.length) return '这次没取到'
  return `${enabledCount.value}/${rows.value.length} 个可用 · 由后端按当前配置下发`
})

/**
 * 拨开关：把**这一行**的可用状态写回服务端
 *
 * **受控式**：本地**不**先翻过去，显示值永远来自服务端回值（写成功用回传清单刷新，失败就保持原位）。
 *
 * ⚠️ 为什么不用乐观式（先翻过去、失败再翻回来）：后端 catch-all 会把「路由被挪走 / 字段名写错」
 *    表现成 `200 + {code:200,…,data:null}` 这种**假成功** —— 于是服务端什么都没存，
 *    而 UI 把开关留在「已屏蔽」上：用户以为这个工具关了，下一次提问照样把工具下发给模型。
 *    受控式最坏只让开关**弹回原位**，不可能伪造状态（`saveAgentToolPref` 的 `ok` 字段
 *    就是为这件事存在的：它要求服务端回显的 `disabled` 与我们发的一致）。
 *
 * ⚠️ `on` 是**开关要去的状态**（`true` = 可用），写回服务端的 `disabled` 正好相反：
 *    可用 → `0`，屏蔽 → `1`。取值来自 el-switch 的 `update:model-value` 事件（带的就是新值），
 *    所以这里不依赖「有没有先写回 v-model」这种发射顺序。
 */
const toggleTool = async (t: ToolRow, on: boolean) => {
  const want: 0 | 1 = on ? 0 : 1
  // ① 要去的状态就是它现在的状态 → 这不是用户操作，一个字都不写。
  //    挡住两种东西：重复点击，以及「上一次 PUT 还在飞、用户又点一下」。
  //    ⚠️ 它**挡不住**挂载期那次程序化 emit（那种 emit 报的是**相反**的状态，
  //       语义上和「用户真的要改」一模一样）—— 那次只能靠 `toolEnabled` 返回布尔从源头消除。
  if ((toolEnabled(t) ? 0 : 1) === want) return
  togglingName.value = t.name
  try {
    const res = await saveAgentToolPref(t.name, want)
    if (res.ok) {
      // ② 用服务端回传的清单刷新（它就是权威值；接口内部已经把缓存换成它了）
      applyPayload(res.payload)
      ElMessage.success(
        want === 1
          ? `已屏蔽「${t.name}」—— 智能体提问时不会再下发这个工具`
          : `已恢复「${t.name}」—— 智能体提问时正常使用这个工具`
      )
    } else {
      // ③ 服务端**没确认**：**不翻开关**，如实把原因说出来。
      //    这一格就是「假 200 不许让 UI 断言服务端没存的状态」。
      ElMessage.error(res.reason || `「${t.name}」没保存成功`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || `「${t.name}」没保存成功`)
  } finally {
    togglingName.value = ''
  }
}

/**
 * 「全选」：**一个控件、两个方向**
 *
 * 当前**不是**全开 → 全部启用（`disabled=0`）；当前**已经**全开 → 全部屏蔽（`disabled=1`）。
 *
 * ⚠️ 为什么是双向，而不是「只做启用」：
 *    用户要的是「**只做一个**全选控件」，并且要求它自动反映状态。如果它只会「启用」，
 *    那么全部启用之后这个控件就**再也按不动了** —— 它显示着「开」，点下去却什么都不发生。
 *    做成双向，它才是一个可撤销的操作（点错了再点一下就能回去）。
 *    「全部启用」在后端是**删行**（稀疏语义：没有行 = 启用），不是写一堆 0。
 *
 * ⚠️ 作用范围是**全部工具**，不随搜索框过滤而缩小。若它只作用于当前搜出来的几个，
 *    「全选」这个词在用户心里就是「全部」，两者对不上；而且「有一个工具没选上就显示关」
 *    这条也会随之失真（被搜索藏起来的那个没选上，控件却显示「开」）。
 *
 * ⚠️ 受控式，与逐行开关同一套：`ok === false` **不翻**，把服务端原话**原样**说出来。
 *    假 200（catch_all 把路由挪走）在这里最危险 —— 界面显示「全部屏蔽了」，
 *    下一次提问却照样把 10 个工具全下发给模型。
 */
const toggleAll = async (on: boolean) => {
  const want: 0 | 1 = on ? 0 : 1
  // 要去的状态就是它现在的状态 → 不是用户操作，一个字都不写（挡重复点击 / 飞行中再点）
  if ((allEnabled.value ? 0 : 1) === want) return
  bulkBusy.value = true
  try {
    const res = await saveAllToolPrefs(want)
    if (res.ok) {
      applyPayload(res.payload)
      ElMessage.success(
        want === 1
          ? `已屏蔽全部 ${rows.value.length} 个工具 —— 智能体这次不会调用任何工具`
          : `已启用全部 ${rows.value.length} 个工具`
      )
    } else {
      ElMessage.error(res.reason || '全选没保存成功')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '全选没保存成功')
  } finally {
    bulkBusy.value = false
  }
}

/**
 * 进去就把清单拉回来 —— **不要在第一次点开时才拉**（用户点开弹层要立刻看到清单，
 * 而不是先看一个转圈），也**不要每次点击都拉**（一次点击一个 GET 是白烧请求）。
 * 切 / 新建会话不需要重拉：清单是「当前配置」，与会话无关；接口内部有模块级缓存。
 */
onMounted(load)
</script>

<!-- 弹层被 teleport 到 body，所以要**非 scoped** 样式；选择器全部挂在
     `popper-class="agent-tool-popover"` 之下，不会漏到别处 -->
<style lang="scss">
.agent-tool-popover.el-popover.el-popper {
  padding: 10px 12px 8px;
}

.agent-tool-popover {
  .atp-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #eef2f7;
  }

  .atp-title {
    font-size: 13px;
    font-weight: 600;
    color: #1f2d3d;
  }

  .atp-sub {
    font-size: 11.5px;
    color: #9aa5b5;
  }

  /* ===== 工具条：搜索 + 「全选」 ===== */
  .atp-tools-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 0 5px;
  }

  .atp-search {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
  }

  .atp-search-input {
    width: 100%;
    min-width: 0;
    height: 26px;
    padding: 0 42px 0 8px;
    border: 1px solid #e5e7eb;
    border-radius: 7px;
    background: #fff;
    font-size: 12px;
    color: #1f2d3d;
    outline: none;

    &::placeholder {
      color: #b6bfcc;
    }

    &:focus {
      border-color: #a9bcf5;
    }
  }

  .atp-search-clear {
    position: absolute;
    right: 6px;
    border: 0;
    background: transparent;
    padding: 0 2px;
    font-size: 11px;
    color: #9aa5b5;
    cursor: pointer;

    &:hover {
      color: #4f6ef7;
    }
  }

  .atp-toggle-all {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
  }

  .atp-toggle-all-text {
    font-size: 12px;
    color: #6b7280;
    cursor: default;
  }

  /* 「全选」作用范围那句：小字，但**不能省** —— 不然「搜出 3 个却改了 10 个」像 bug */
  .atp-tools-hint {
    padding: 0 0 4px;
    font-size: 11px;
    color: #9aa5b5;
  }

  /* 搜不到：中性提示，与「没取到」那条橙色错误态**在视觉上也要分得开** */
  .atp-no-hit {
    padding: 10px 2px;
    font-size: 11.5px;
    color: #9aa5b5;
  }

  /* ===== 三种状态：加载中 / 没取到 / 清单 ===== */
  .atp-state {
    padding: 12px 2px;
    font-size: 12px;
    line-height: 1.7;
    color: #9aa5b5;
  }

  /* 「没取到」那条：要显眼到能分辨——它不是空态，是错误态 */
  .atp-failed {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 10px;
    border: 1px solid #f0d9a8;
    border-radius: 7px;
    background: #fffaf0;
    color: #8a6d3b;
  }

  .atp-failed-text {
    flex: 1;
    min-width: 0;
  }

  .atp-retry {
    flex-shrink: 0;
  }

  /* 清单在、但每条都被屏蔽：这句话与上面那条错误提示**不是一回事** */
  .atp-all-off {
    margin-top: 6px;
    padding: 6px 10px;
    border: 1px solid #eef2f7;
    border-radius: 7px;
    background: #f8fafc;
    font-size: 11.5px;
    line-height: 1.7;
    color: #6b7280;
  }

  .atp-list {
    max-height: 260px;
    overflow-y: auto;
    padding: 4px 0;
  }

  .atp-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 2px;

    & + .atp-item {
      border-top: 1px dashed #f1f5f9;
    }
  }

  /* 被屏蔽的行：名字压暗，但**不隐藏、不禁用整行** —— 开关还要能拨回来。
     ⚠️ 与知识库抽屉 `.kb-item.blocked` 同一套口径。 */
  /* 被屏蔽的行：主标题压暗（**不隐藏**、不禁用整行 —— 开关还要能拨回来） */
  .atp-item.blocked .atp-name {
    color: #9aa5b5;
  }

  .atp-item-main {
    flex: 1;
    min-width: 0;
  }

  /* 主标题 = **中文名**（`label`）—— 用户看的是这个，不是工具标识 */
  .atp-name {
    font-size: 12.5px;
    font-weight: 500;
    color: #1f2d3d;
  }

  /* 副标题 = 英文工具标识（小字、等宽）—— 用户报 bug / 我查日志时都要用它定位 */
  .atp-key {
    display: inline-block;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 9px;
    background: #eef2f8;
    color: #7b8799;
    font-family: Consolas, Monaco, monospace;
    font-size: 10.5px;
    line-height: 16px;
    vertical-align: 1px;
  }

  /* 「已屏蔽」状态：**常驻**可见（不是 hover 才显形），与知识库抽屉同观感 */
  .atp-item-blocked {
    display: inline-block;
    margin-left: 6px;
    padding: 0 5px;
    border-radius: 4px;
    background: #f1f3f5;
    color: #8a94a6;
    font-size: 11px;
    line-height: 16px;
    vertical-align: 1px;
  }

  .atp-desc {
    display: block;
    margin-top: 3px;
    font-size: 12px;
    line-height: 1.5;
    color: #6b7280;
    word-break: break-word;
  }

  /* 开关容器：常驻可见、不参与任何 hover 机制（它承载的正是「一眼看出被屏蔽了」） */
  .atp-toggle {
    display: inline-flex;
    align-items: center;
    flex-shrink: 0;
  }
}
</style>

<style scoped lang="scss">
/* 与 .toolbar-btn / .kb-entry 同观感（28×28 / 圆角 8 / 透明底） */
.tool-entry {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #6b7280;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;

  &:hover {
    background: #fff;
    border-color: #e5e7eb;
    color: #1f2937;
  }
}

.tool-entry-count {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  border-radius: 7px;
  background: #4f6ef7;
  color: #fff;
  font-size: 10px;
  line-height: 14px;
  text-align: center;
  box-sizing: border-box;
}
</style>
