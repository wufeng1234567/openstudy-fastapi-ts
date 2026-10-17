import { defineStore } from 'pinia'

/**
 * 智能体界面状态
 * ---------------
 * 侧边栏的「新建对话」「设置」不在 chat.vue 内部，却要驱动它。
 * 用一个极轻的 store 传信号（比 query 参数干净，不会污染地址栏 / 位置记忆）。
 *
 * 约定：
 *   · 侧边栏调用 requestNewChat() / requestSettings() 后立刻跳 /front/agent/chat；
 *   · chat.vue 监听对应的 token 变化 → 执行 newSession() / 打开设置面板；
 *   · chat.vue 挂载时先记下当前 token，避免「跳过来又立刻执行一次」。
 */
const useAgentUiStore = defineStore('agentUi', {
  state: () => ({
    newChatToken: 0,
    /** 请求打开「智能体设置」抽屉（侧栏入口发信号） */
    settingsToken: 0
  }),
  actions: {
    requestNewChat() {
      // ⚠️ 用自增而不是 Date.now()：同一毫秒内连点两次会拿到相同的值，
      //    对话页的 token 比较会判定"没变化"从而吞掉第二次点击。
      this.newChatToken += 1
    },
    requestSettings() {
      this.settingsToken += 1
    }
  }
})

export default useAgentUiStore
