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
const formatTitle = (s: any) => s?.title || '新会话'

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
    /** 当前打开的会话 id */
    currentSessionId: '',
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
    async loadSessions() {
      const userId = useUserStore().id
      // 用户信息还没回来：直接跳过（页面挂载早期很常见），免得发出无 userId 的请求
      if (!userId) return
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
        await this.loadSessions()
        return id
      } catch {
        const id = `asst_${Date.now()}`
        this.currentSessionId = id
        return id
      }
    },

    /** 用户点了某个会话（由 chat.vue 的 watcher 负责真正加载消息） */
    selectSession(id: string) {
      if (!id) return
      this.currentSessionId = id
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
