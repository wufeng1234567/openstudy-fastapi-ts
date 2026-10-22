/**
 * 长卡片「吸顶折叠条」组合式函数（2026-10-22）
 * ============================================================================
 * ## 解决什么问题
 *
 * 智能体页的工具卡片有三类会长得很高：
 *   · `AgentDraftCard`    —— 导入预览，一张卡里可能有 15 道题的编辑表单；
 *   · `AgentConfirmCard`  —— 写操作确认，带 preview 键值行 / 逐条列表；
 *   · `AgentToolResult`   —— 工具执行结果，展开详情后也很长。
 *
 * 用户原话：
 *   「这些卡片 有的特别长 用户需要滚动很久才能看到底部 或者看到卡片之前的消息」
 *   「要实现用户往下滚动的时候 可以直接看到那个卡片的按钮 然后可以直接点击收起来
 *     那张卡片 也可以一键展开」
 *
 * 核心痛点**不是"没有折叠"** —— `AgentToolResult` 本来就有「收起 / 查看详情」，
 * 但那个按钮在**卡片底部**：卡一长，用户滚到卡片中间时按钮早已滑出视野，
 * 想收起还得先往下滚到按钮那儿。**越长的卡越收不动，正好反了。**
 *
 * ## 做法
 *
 * 在卡片内部放一个 `position: sticky; top: 0` 的细条，它包含：
 *   · 左：卡片标题 + 一句状态摘要（收起后仍知道这是什么卡）；
 *   · 右：折叠 / 展开按钮。
 *
 * `sticky` 让这条**始终贴在消息流可视区顶部**，滚到卡片任意位置都能点。
 * 收起后卡片只占这一条的高度，后面的消息立刻回到视线里。
 *
 * ## 为什么不用 IntersectionObserver
 *
 * 纯 CSS `sticky` + 一个布尔 ref 就够了。监听滚动位置去"动态显示按钮"会带来
 * 一堆边界情况（窗口缩放、消息流重排、keep-alive 切换），而 sticky 由浏览器计算，
 * 永远正确、零成本。
 *
 * ## 为什么用"内容量级"而不是"DOM 高度"判断要不要显示折叠条
 *
 * 因为折叠会改变 DOM 高度 → 用真实高度判断会自相矛盾：
 *   收起 → 变矮 → 认为不需要折叠条 → 折叠条消失 → **用户再也展不开**。
 * 所以阈值必须由"内容本身的量级"（题目条数 / 预览行数）决定，与折叠状态无关。
 */
import { computed, ref } from 'vue'

export interface CollapseBarOptions {
  /**
   * 内容达到多少"行"才值得显示折叠条
   *
   * 默认 12：约 12 行文本的高度。低于这个量级给折叠条是噪音 ——
   * 用户一眼看完，多一个可点区域反而干扰。
   * 实测一张 15 题的导入卡约 400+ 行，远超阈值；
   * 而「已确认」这类短卡片只有几行，就不该出现折叠条。
   */
  threshold?: number
  /** 初始是否折叠（默认展开：用户刚生成的卡片应该能直接看到内容） */
  defaultCollapsed?: boolean
}

/**
 * 吸顶条的公共样式
 *
 * `z-index` 取 2：只需压住卡片内部内容。
 * 设太大会盖住消息流右上角的复制按钮与外层的轮次导航。
 */
export const COLLAPSE_BAR_STYLE: Record<string, string> = {
  position: 'sticky',
  top: '0',
  zIndex: '2'
}

export function useCollapseBar(options: CollapseBarOptions = {}) {
  const { threshold = 12, defaultCollapsed = false } = options

  const collapsed = ref(defaultCollapsed)

  /** 内容量级（行数），由组件上报 */
  const contentLines = ref(0)

  /** 组件上报内容量级后调用 */
  function setContentLines(n: number) {
    contentLines.value = Number.isFinite(n) && n > 0 ? n : 0
  }

  /** 是否值得显示折叠条 */
  const shouldOfferCollapse = computed(() => contentLines.value >= threshold)

  function toggle() {
    collapsed.value = !collapsed.value
  }
  function expand() {
    collapsed.value = false
  }
  function collapse() {
    collapsed.value = true
  }

  return {
    collapsed,
    contentLines,
    setContentLines,
    shouldOfferCollapse,
    toggle,
    expand,
    collapse
  }
}
