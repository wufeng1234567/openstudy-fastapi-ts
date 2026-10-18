import { defineStore } from 'pinia'

/**
 * 顶栏副标题信号
 * ============================================================================
 * 用户 2026-10-18：「题库管理 5 个题库 …这个部分内容多余了，把他提取出来，
 * 一起给到第一行去：我的学习 · 题库管理 xx个题库」。
 *
 * 原来每个子页在内容区顶部都有一行「页面名 + N 个 X」：
 *
 *   我的学习 · 题库管理            ← 顶栏（第 1 行）
 *   题库管理              5 个题库  ← 内容区（第 2 行，用户划掉的那行）
 *
 * 这两行说的是同一件事。现在把「名称」留在顶栏、「计数」也并进顶栏，
 * 内容区那一行整块去掉，下面直接是分组切换。
 *
 * ## 为什么用 store 而不是 props/事件
 *
 * 页面的标题在**外壳**（`layout/front.vue`）里渲染，而计数只有**页面自己**知道
 * （数据是页面拉的）。两者是**跨层级**的兄弟关系，没有父子 props 通道。
 * 外壳已经是顶栏渲染方，这里只需要一个极轻的桥：
 * 页面挂载/数据变化时 `set()`，卸载时 `clear()`。
 *
 * ⚠️ 必须在页面 `onBeforeUnmount` 里 clear ——
 *    这个页面是 keep-alive 的，不 clear 会把上一个页面的计数带到下一个页面。
 */
const useTopbarStore = defineStore('topbar', {
  state: () => ({
    /** 副标题里的计数文本，如「5 个题库」；空串表示不显示 */
    countText: ''
  }),
  actions: {
    setCount(text: string) {
      this.countText = text || ''
    },
    clear() {
      this.countText = ''
    }
  }
})

export default useTopbarStore
