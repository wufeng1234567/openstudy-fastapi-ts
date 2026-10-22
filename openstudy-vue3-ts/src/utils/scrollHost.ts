/**
 * 滚动宿主探测（公共）
 * ============================================================================
 * 为什么要有这个文件（2026-10-22）
 *
 * 「页面到底是谁在滚」这件事在本项目里踩过坑：练习页真正滚动的是**外壳内容区
 * `.os-content`**（实测 scrollHeight 4938 / clientHeight 948），
 * 而 `document.documentElement` 恒为 0（整页高度 = 视口），
 * `.overview-question-stream` 自己 `scrollHeight === clientHeight`（不滚）。
 * 任何一处写死容器都会踩空。
 *
 * 这段探测逻辑原先只存在于 `ScrollButton.vue` 内部。现在答题卡里的
 * 「回到顶部 / 跳到底部」也要用同一套探测 —— 与其复制一份，不如抽出来，
 * 两边共用，将来换外壳（或改 `is-flush` 页面）只改一处。
 *
 * ⚠️ 约定：这里全部是**纯函数**，不持有任何状态。
 *    状态（绑了谁、监听怎么解）留给调用方，避免两个使用者互相抢监听。
 */

/** 真正在滚的东西：某个元素，或者整个 window */
export type ScrollHost = HTMLElement | Window

/**
 * 「算溢出」的下限
 *
 * 取 4 而不是 0：浏览器亚像素布局会让 `scrollHeight - clientHeight` 出现 1~3px
 * 的假溢出（尤其是有 transform / 小数行高时）。拿它当判据会导致
 * "内容根本没超出，却认为可以滚"。
 */
const OVERFLOW_MIN = 4

/**
 * 向上找一个「内容确实超出」的可滚动祖先
 *
 * 找不到就退回 `window`（而不是 null）：
 * 调用方拿到 window 仍然可以工作（读 `window.scrollY` / `scrollTo`），
 * 拿 null 就只能干等，反而更容易出"按钮永不出现"的 bug。
 */
export function findScrollParent(el: HTMLElement | null): ScrollHost {
  let node: HTMLElement | null = el
  while (node && node !== document.body && node !== document.documentElement) {
    const style = getComputedStyle(node)
    const scrollable = /(auto|scroll|overlay)/.test(style.overflowY)
    if (scrollable && node.scrollHeight > node.clientHeight + OVERFLOW_MIN) return node
    node = node.parentElement
  }
  return window
}

/**
 * 兜底：全文档里找「最像主滚动区」的那个元素
 *
 * 为什么要它：浮层/卡片可能在 `<transition>` / keep-alive 下、于外壳内容区
 * 尚未撑开时挂载 —— 那一刻向上找每一层都"不溢出"，只能退回 window；
 * 但整页高度 = 视口时 window 根本不动（top / max 恒为 0）。
 *
 * 判据：overflowY 可滚 且 内容溢出，取**溢出量最大**的。
 */
export function findMainScroller(): HTMLElement | null {
  let best: HTMLElement | null = null
  let bestOverflow = 0
  const nodes = document.querySelectorAll<HTMLElement>(
    '.os-content, .os-main, .main-content, .overview-question-stream, [class*="content"]'
  )
  for (const node of nodes) {
    const style = getComputedStyle(node)
    if (!/(auto|scroll|overlay)/.test(style.overflowY)) continue
    const overflow = node.scrollHeight - node.clientHeight
    if (overflow > bestOverflow) {
      best = node
      bestOverflow = overflow
    }
  }
  return bestOverflow > OVERFLOW_MIN ? best : null
}

/**
 * 完整探测：先向上找 → 再全文档找 → 最后 window
 *
 * @param startEl 探测起点（通常是页面根节点）
 */
export function resolveScrollHost(startEl: HTMLElement | null): ScrollHost {
  const fromParent = findScrollParent(startEl)
  if (fromParent !== window) return fromParent
  const main = findMainScroller()
  return main ?? window
}

/**
 * 读滚动位置（window 与元素两种口径）
 *
 * @returns `top` 当前位置；`max` 还能滚多远（0 表示内容不溢出）
 */
export function readScrollPosition(host: ScrollHost | null): { top: number; max: number } {
  if (!host) return { top: 0, max: 0 }
  if (host === window) {
    const doc = document.documentElement
    return {
      top: window.scrollY || doc.scrollTop || 0,
      max: Math.max(0, doc.scrollHeight - window.innerHeight)
    }
  }
  const el = host as HTMLElement
  return {
    top: el.scrollTop || 0,
    max: Math.max(0, (el.scrollHeight || 0) - (el.clientHeight || 0))
  }
}

/**
 * 平滑滚到指定位置
 *
 * `scrollTo({ behavior: 'smooth' })` 在系统开了「减少动态效果」时
 * 浏览器会自己降级成瞬时跳转，所以这里不用再判 `prefers-reduced-motion`。
 *
 * ⚠️ **页面在后台时必须降级为瞬时跳转**（2026-10-22 实测踩到）：
 *    Chrome 在 `document.hidden === true`（标签页在后台 / 窗口被完全遮挡）时
 *    **不推进 smooth 滚动动画** —— 调用不报错，`scrollTop` 却一直是 0。
 *    用户切到别的窗口再回来点「跳到底部」就会看到"点了没反应"。
 *
 *    这里主动判 `document.hidden`：后台直接瞬时定位（位置正确、用户回来看得到结果），
 *    前台才走平滑动画。既保住观感，又不会出现"点了没动"。
 *
 * @param smooth 是否允许平滑动画（默认允许）
 */
export function scrollHostTo(host: ScrollHost | null, top: number, smooth = true): void {
  if (!host) return
  const scroller: any = host === window ? window : host
  const target = Math.max(0, top)
  const useSmooth = smooth && !document.hidden
  if (typeof scroller.scrollTo === 'function') {
    scroller.scrollTo({ top: target, behavior: useSmooth ? 'smooth' : 'auto' })
    /*
     * 双保险：某些浏览器对"同一次任务里连续两次 scrollTo"会合并/忽略第一次。
     * 瞬时模式下直接同步写一次 scrollTop，确保位置一定生效。
     */
    if (!useSmooth) {
      try {
        scroller.scrollTop = target
      } catch {
        /* window 上 scrollTop 只读，忽略即可 */
      }
    }
  } else {
    scroller.scrollTop = target
  }
}
