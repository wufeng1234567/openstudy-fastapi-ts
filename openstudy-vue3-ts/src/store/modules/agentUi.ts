import { defineStore } from 'pinia'

/** 抽屉里可切换的两个 tab（设置 / 知识库同属一个抽屉） */
export type AgentPanelTab = 'settings' | 'kb'

/**
 * 智能体界面状态
 * ---------------
 * 侧边栏的「新建对话」「设置」不在对话页内部，却要驱动它。
 * 用一个极轻的 store 传信号（比 query 参数干净，不会污染地址栏 / 位置记忆）。
 *
 * ## 2026-10-18 的两点调整（用户反馈驱动）
 *
 * 1. **设置成了全局抽屉**（挂在外壳 `layout/front.vue` 上），不再住在对话页里。
 *    所以侧栏点设置**不再跳转路由**，信号由 `components/GlobalSettings` 接收，
 *    在**当前页面**就地展开。
 *
 * 2. **设置与知识库不拆开**（用户：「为什么你要把知识库和智能体设置区分开来？不要区分啊」）。
 *    两者是同一个抽屉里的两个 tab。上一版拆成两个独立抽屉，结果侧栏点设置时
 *    「左边知识库 + 右边设置」同时弹出来。现在统一走 `requestPanel(tab)`：
 *    · 抽屉没开 → 打开并停在该 tab；
 *    · 已开在同一个 tab → 收起（开关语义）；
 *    · 已开在另一个 tab → 切过去（不关不重开）。
 *
 * ⚠️ token 用**自增**而不是 `Date.now()`：同一毫秒内连点两次会拿到相同值，
 *    接收方的 token 比较会判定"没变化"从而吞掉第二次点击。
 */
const useAgentUiStore = defineStore('agentUi', {
  state: () => ({
    newChatToken: 0,
    /** 请求开合「设置 / 知识库」抽屉（侧栏 + 对话页工具栏都发这个信号） */
    settingsToken: 0,
    /** 本次信号希望停在哪个 tab */
    settingsTab: 'settings' as AgentPanelTab
  }),
  actions: {
    requestNewChat() {
      this.newChatToken += 1
    },

    /** 打开设置抽屉（默认停在「设置」tab） */
    requestSettings() {
      this.requestPanel('settings')
    },

    /**
     * 请求开合面板
     *
     * @param tab 目标 tab；不传则沿用上次的 tab（侧栏「设置」用默认值即可）
     */
    requestPanel(tab: AgentPanelTab = 'settings') {
      this.settingsTab = tab
      this.settingsToken += 1
    }
  }
})

export default useAgentUiStore
