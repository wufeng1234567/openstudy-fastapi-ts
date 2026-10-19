import { defineStore } from 'pinia'
import { listSessions, createSession, deleteSession } from '@/api/ai/ai'
import useUserStore from '@/store/modules/user'

/**
 * 智能体会话状态（侧栏与对话页共用）
 * ==================================
 * 为什么放到 store 而不是留在 chat.vue 里：
 *   现在会话历史**显示在左侧导航栏**（对齐 DSH：导航栏第二段就是会话列表 + 搜索），
 *   而消息流仍在对话页里。两个组件都要读写同一份数据，只能提到共享层。
 *
 * 职责边界：
 *   · 本 store 只负责「有哪些会话 / 当前是哪个 / 增删查」；
 *   · 消息内容、流式生成、工具调用仍由 `useAgentChat`（composable）持有；
 *   · 切换会话时由 chat.vue 监听 `currentSessionId` 变化去加载对应历史。
 *
 * ⚠️ 这里的请求都带 userId：后端 `ai_chat_session` 按用户隔离，
 *    不带 userId 会查到别人的会话（历史上踩过）。
 */
/** 会话标题的统一格式（空标题显示「新会话」） */
const formatTitle = (s: any) => s?.title || '新会话'

/**
 * 「上次打开的是哪个会话」的持久化键
 *
 * 为什么不放进别的 store / 不塞进 URL：会话切换是纯前端状态，
 * 且刷新后 URL 不变（保持 #/front/agent/chat），放 localStorage 最省事。
 * 按用户隔离，避免多账号在同一浏览器里互相串会话。
 */
const CURRENT_SESSION_KEY = 'os_agent_current_session'

/**
 * 读：按当前登录用户拼 key
 *
 * ⚠️ 这里**只能**读带当前 uid 的精确键，绝不能"扫前缀兜底"。
 *
 * 历史教训（用户 2026-10-19 报「刷新后跑到最新会话」）：
 *   上一版为了兼容「首屏 userStore.id 还没就绪」，在 uid 为空时扫一遍所有
 *   `os_agent_current_session_*` 键、返回**第一个**命中的值。而 localStorage 的遍历顺序
 *   是「先写入的在前」，同一浏览器里只要留过别的账号（admin/user2…）的键，
 *   就会读到**别人的** session id：
 *
 *     · 该 id 不属于当前用户 → 不在 sessions 列表里 → `canRestore` 判负
 *     · 于是 chat.vue 退回 `sessions[0]`（列表按更新时间倒序 = 最新那个）
 *     · 用户看到的就是「刷新后跳到最新会话」
 *
 *   实测复现：种一个 `os_agent_current_session_1`（admin 的）后刷新，
 *   当前会话从「你好啊」跳到最新的「你好呀 你都会什么」。
 *
 * 正确做法：uid 未知就**返回空**，让上层等真正的 uid。
 *   store 在 `loadSessions()` 里拿到 userId 后还有一次「补读」机会
 *   （见那里的 `if (!this.currentSessionId)`），所以不会丢恢复能力 ——
 *   唯一的要求是那次补读发生在「恢复判断」之前，chat.vue 的 onMounted
 *   正是 `await loadSessions()` 后才判断，顺序有保证。
 */
function readStoredSessionId(): string {
  try {
    const uid = useUserStore().id
    // uid 未知 → 宁可不恢复，也不能拿别人的会话 id
    if (!uid) return ''
    const key = `${CURRENT_SESSION_KEY}_${uid}`
    const own = localStorage.getItem(key)
    if (own) return own
    /*
     * 认领「无主」键：`_0` 是 uid 还没就绪时写入的占位（见 storeSessionId）。
     * 它不是任何真实用户（user_id 从 1 起），所以第一个来认领的登录用户可以安全接管；
     * 认领后立刻搬到自己名下，避免下一个账号又抢一次。
     */
    const anon = localStorage.getItem(`${CURRENT_SESSION_KEY}_0`)
    if (anon) {
      localStorage.setItem(key, anon)
      localStorage.removeItem(`${CURRENT_SESSION_KEY}_0`)
      return anon
    }
    return ''
  } catch {
    return ''
  }
}

/** 写：切会话 / 新建 / 删除时都要同步一次（传空串表示"没有当前会话"） */
function storeSessionId(id: string) {
  try {
    const uid = useUserStore().id
    /*
     * uid 未知 → 写进 `_0` 占位键（否则新会话在刷新后恢复不了）。
     * 这个键由 readStoredSessionId 的「认领」逻辑接管，不会被当成某个真实用户的。
     */
    const key = `${CURRENT_SESSION_KEY}_${uid || 0}`
    if (id) localStorage.setItem(key, id)
    else localStorage.removeItem(key)
  } catch {
    /* localStorage 不可用（隐私模式）时静默降级为纯内存行为 */
  }
}


/** 相对时间：与 chat.vue 里会话列表的文案保持一致 */
export function formatSessionTime(time: any): string {
  if (!time) return ''
  const d = new Date(time)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const useAgentSessionStore = defineStore('agentSession', {
  state: () => ({
    /** 全部会话（后端已按 updatedAt 倒序） */
    sessions: [] as any[],
    loading: false,
    /**
     * 当前打开的会话 id
     *
     * ⚠️ 初值从 localStorage 恢复（用户 2026-10-18 报「在某个会话里刷新页面，
     *    自动跑到新会话窗口去了」）：
     *      Pinia 是纯内存的，刷新即丢；`chat.vue` 的 onMounted 又只做
     *      `sessionId = sessions[0]`（列表按更新时间倒序，第一条就是最新的那个），
     *      于是"刷新"永远等于"跳到最新会话"，而不是"回到你看的那条"。
     *      这里把上一次打开的会话记下来，页面初始化时优先恢复它。
     */
    currentSessionId: readStoredSessionId(),
    /** 侧栏搜索关键词 */
    keyword: '',
    /**
     * 切换计数：每次「用户主动切会话 / 新建会话」自增。
     * chat.vue 监听它来加载历史 —— 用计数而不是直接盯 currentSessionId，
     * 是为了支持「点同一个会话也要重新加载」这种场景（例如删掉后重建同名）。
     */
    switchToken: 0
  }),

  getters: {
    title: () => formatTitle,

    /** 按关键词过滤后的会话（侧栏直接渲染这份） */
    filtered(state): any[] {
      const kw = state.keyword.trim().toLowerCase()
      if (!kw) return state.sessions
      return state.sessions.filter((s: any) => formatTitle(s).toLowerCase().includes(kw))
    },

    current(state): any {
      return state.sessions.find((s: any) => s.sessionId === state.currentSessionId) || null
    }
  },

  actions: {
    /**
     * 拉取会话列表
     *
     * ⚠️ `userId` 未就绪时**不能直接 return**（用户 2026-10-18 报的
     *    「在某个会话刷新页面，自动跑到新会话」的真正成因就在这里）：
     *      刷新时 `chat.vue` 的 onMounted 会 `await loadSessions()` 后立刻判断
     *      「列表为空就新建会话」；而早期 `userStore.id` 还是空，
     *      旧实现 `if (!userId) return` 让这个 await **秒回且什么都没加载**，
     *      于是 sessions 恒为 0 → 直接 newSession() → 用户看到的就是"新会话"。
     *      而侧栏稍后才加载出 16 个会话，两边就不一致了。
     *
     * 现在：等一小会儿（每 60ms 轮询，最多 15 次 ≈ 0.9s）拿 userId，
     *      仍拿不到才跳过 —— 让"先加载再判断"的调用方拿到真实列表。
     */
    async loadSessions() {
      let userId = useUserStore().id
      if (!userId) {
        for (let i = 0; i < 15 && !userId; i++) {
          await new Promise((r) => setTimeout(r, 60))
          userId = useUserStore().id
        }
      }
      if (!userId) return
      /*
       * 补读持久化的会话 id。
       * 为什么不能只在 `state()` 里读一次：Pinia store 可能在**登录信息到位之前**
       * 就被创建（首屏渲染时 userStore.id 还是空），那时 `readStoredSessionId()`
       * 拿不到 uid、返回空串，于是"上次的会话"永远恢复不出来。
       * 这里在拿到 userId 后补一次；只在内存里还是空的时候补，不覆盖用户当前的切换。
       */
      if (!this.currentSessionId) {
        const stored = readStoredSessionId()
        if (stored) this.currentSessionId = stored
      }
      this.loading = true
      try {
        const res: any = await listSessions(userId)
        if (res?.code === 200 && Array.isArray(res.data)) this.sessions = res.data
        else if (Array.isArray(res?.rows)) this.sessions = res.rows
      } catch (e) {
        console.warn('[agent] 加载会话列表失败', e)
      } finally {
        this.loading = false
      }
    },

    /** 新建会话：后端落一条空会话，首条消息后标题自动替换 */
    async createSession(): Promise<string> {
      const userId = useUserStore().id
      try {
        const res: any = await createSession(userId)
        const id = res?.data?.sessionId || `asst_${Date.now()}`
        this.currentSessionId = id
        storeSessionId(id)
        await this.loadSessions()
        return id
      } catch {
        const id = `asst_${Date.now()}`
        this.currentSessionId = id
        storeSessionId(id)
        return id
      }
    },

    /** 用户点了某个会话（由 chat.vue 的 watcher 负责真正加载消息） */
    selectSession(id: string) {
      if (!id) return
      this.currentSessionId = id
      storeSessionId(id)
      this.switchToken += 1
    },

    /** 新建并切换（侧栏的「新建对话」走这里） */
    async startNewSession(): Promise<string> {
      const id = await this.createSession()
      this.switchToken += 1
      return id
    },

    async removeSession(id: string) {
      const userId = useUserStore().id
      try {
        await deleteSession(id, userId)
        this.sessions = this.sessions.filter((s: any) => s.sessionId !== id)
        // 删掉的正好是当前会话 → 通知对话页重置（由 chat.vue 监听 switchToken）
        if (this.currentSessionId === id) {
          this.currentSessionId = ''
          storeSessionId('')
          this.switchToken += 1
        }
      } catch (e) {
        console.warn('[agent] 删除会话失败', e)
        throw e
      }
    },

    /** 本地改标题（会话里发出第一条消息后，后端会回填标题） */
    touchTitle(id: string, title: string) {
      const s = this.sessions.find((x: any) => x.sessionId === id)
      if (s && title) s.title = title
    }
  }
})

export default useAgentSessionStore
