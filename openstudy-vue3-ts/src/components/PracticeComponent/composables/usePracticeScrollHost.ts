import { computed, ref } from 'vue'
import { readScrollPosition, resolveScrollHost, scrollHostTo, type ScrollHost } from '@/utils/scrollHost'

/**
 * 练习页的滚动宿主生命周期：探测外壳滚动容器、监听尺寸/结构变化、
 * 处理「回到顶部 / 跳到底部」。
 *
 * 从 `PracticeComponent.vue` 抽出；题目和答题状态仍由页面持有。
 */
export function usePracticeScrollHost() {
  const containerRef = ref<HTMLElement | null>(null)
  const scrollMax = ref(0)
  const scrollable = computed(() => scrollMax.value > 80)

  let scrollHost: ScrollHost | null = null
  let lastScrollSyncAt = 0
  let scrollHostResizeObserver: ResizeObserver | null = null
  let scrollHostMutationObserver: MutationObserver | null = null
  const scrollHostRetryTimers: Array<ReturnType<typeof setTimeout>> = []

  function syncScrollState() {
    scrollMax.value = readScrollPosition(scrollHost).max
  }

  const SCROLL_SYNC_INTERVAL = 60
  function onPracticeScroll() {
    const now = performance.now()
    if (now - lastScrollSyncAt < SCROLL_SYNC_INTERVAL) return
    lastScrollSyncAt = now
    syncScrollState()
  }

  function ensureScrollHost() {
    const current = scrollHost
    const alive = current === window || (current instanceof HTMLElement && current.isConnected)
    if (alive) {
      const { max } = readScrollPosition(current)
      if (max > 4) return
    }

    detachScrollHost()
    scrollHost = resolveScrollHost(containerRef.value)
    lastScrollSyncAt = 0
    syncScrollState()

    if (scrollHost && scrollHost !== window) {
      const el = scrollHost as HTMLElement
      el.addEventListener('scroll', onPracticeScroll, { passive: true })
      if (typeof ResizeObserver !== 'undefined') {
        scrollHostResizeObserver = new ResizeObserver(onPracticeScroll)
        scrollHostResizeObserver.observe(el)
        if (el.firstElementChild) scrollHostResizeObserver.observe(el.firstElementChild as HTMLElement)
      }
      if (typeof MutationObserver !== 'undefined') {
        scrollHostMutationObserver = new MutationObserver(onPracticeScroll)
        scrollHostMutationObserver.observe(el, { childList: true, subtree: true })
      }
    } else {
      window.addEventListener('scroll', onPracticeScroll, { passive: true })
    }
    window.addEventListener('resize', onPracticeScroll)
  }

  function detachScrollHost() {
    if (scrollHost) {
      if (scrollHost === window) window.removeEventListener('scroll', onPracticeScroll)
      else (scrollHost as HTMLElement).removeEventListener('scroll', onPracticeScroll)
    }
    window.removeEventListener('resize', onPracticeScroll)
    scrollHostResizeObserver?.disconnect()
    scrollHostResizeObserver = null
    scrollHostMutationObserver?.disconnect()
    scrollHostMutationObserver = null
    scrollHost = null
  }

  function bindPracticeScrollHost() {
    detachScrollHost()
    ensureScrollHost()
    syncScrollState()
  }

  function unbindPracticeScrollHost(clearRetry = true) {
    detachScrollHost()
    if (clearRetry) {
      scrollHostRetryTimers.forEach((timer) => clearTimeout(timer))
      scrollHostRetryTimers.length = 0
    }
  }

  function scheduleScrollHostBinding() {
    requestAnimationFrame(bindPracticeScrollHost)
    scrollHostRetryTimers.push(
      setTimeout(bindPracticeScrollHost, 300),
      setTimeout(bindPracticeScrollHost, 1200)
    )
  }

  function handleScrollTop() {
    scrollHostTo(scrollHost, 0)
  }

  function handleScrollBottom() {
    scrollHostTo(scrollHost, readScrollPosition(scrollHost).max)
  }

  return {
    containerRef,
    scrollable,
    ensureScrollHost,
    syncScrollState,
    bindPracticeScrollHost,
    unbindPracticeScrollHost,
    scheduleScrollHostBinding,
    handleScrollTop,
    handleScrollBottom
  }
}
