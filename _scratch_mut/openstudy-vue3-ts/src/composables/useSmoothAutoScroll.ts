import { ref, watch, onBeforeUnmount, type Ref } from 'vue'

/**
 * 流式输出时的「丝滑跟随滚动」。
 *
 * 要解决的问题：流式内容持续变长，如果每次都无条件
 * `el.scrollTop = el.scrollHeight`，会和用户的滚动操作**抢控制权** ——
 * 用户想往上翻看前面的内容，却被不断拽回底部。
 *
 * 策略（业界通用的 "stick to bottom" 做法）：
 *   1. 只在**用户本来就在底部附近**（距离 ≤ threshold）时才自动跟随；
 *   2. 用户一旦往上滚，立即**停止跟随**，内容继续增长也不动视口；
 *   3. 用户滚回底部附近，**自动恢复**跟随；
 *   4. 用 `requestAnimationFrame` 合并同一帧内的多次滚动请求。
 *
 * ⚠️ 两个踩过的坑（不要再犯）：
 *   · **不要**用「时间窗」来忽略自己造成的 scroll 事件。流式输出时内容
 *     每 50ms 更新一次，时间窗会被连续刷新，把用户真实的滚动全部吞掉，
 *     表现为「怎么滚都被拽回底部」。程序化滚动必然停在底部（距离≈0），
 *     本来就会被正确判定为「跟随中」，不需要额外忽略。
 *   · 用户意图用 `wheel` 事件捕获更可靠：wheel 会从真正的滚动容器
 *     **冒泡**上来，即使 ref 绑的是外层容器也能捕获；且它绝不会由
 *     程序触发，天然区分「用户行为」与「代码行为」。
 *
 * 用法：
 * ```ts
 * const contentRef = ref<HTMLElement | null>(null)
 * const { isFollowing, keepAtBottom, scrollToBottom } = useSmoothAutoScroll(contentRef)
 * keepAtBottom()   // 每收到一段流式内容后调用
 * // 可选：模板里放「回到底部」按钮，仅在 !isFollowing 时显示
 * ```
 *
 * @param elRef 滚动容器的 ref
 * @param threshold 距底部多少像素内仍视为「跟随中」，默认 48
 */
export function useSmoothAutoScroll(
  elRef: Ref<HTMLElement | null>,
  threshold = 48
) {
  const isFollowing = ref(true)
  let rafId: number | null = null

  const distanceFromBottom = (el: HTMLElement) =>
    el.scrollHeight - el.scrollTop - el.clientHeight

  /** 根据当前位置判断是否还在跟随（程序化滚动会停到底部 → 判定为跟随，符合预期） */
  const onScroll = () => {
    const el = elRef.value
    if (!el) return
    isFollowing.value = distanceFromBottom(el) <= threshold
  }

  /** 用户滚轮意图：向上滚就立刻停止跟随 */
  const onWheel = (e: WheelEvent) => {
    const el = elRef.value
    if (!el) return
    if (e.deltaY < 0 && distanceFromBottom(el) > 0) {
      isFollowing.value = false
    }
  }

  /** 触摸设备：手指下滑浏览前先解除跟随 */
  const onTouchMove = () => {
    const el = elRef.value
    if (!el) return
    if (distanceFromBottom(el) > threshold) {
      isFollowing.value = false
    }
  }

  // ⚠️ 绑定时机：必须用 watch(elRef)，**不能**只在 onMounted 绑一次。
  // 目标元素很可能晚于组件挂载才出现 —— 典型场景是内容在 el-dialog 里，
  // Element Plus 首次打开对话框才渲染 DOM。若在 onMounted 时 elRef 还是
  // null，监听器就永远装不上，wheel/scroll 全部收不到，
  // 表现为「跟随逻辑完全失效、一直抢滚动条」。
  let boundEl: HTMLElement | null = null

  const unbind = () => {
    if (!boundEl) return
    boundEl.removeEventListener('scroll', onScroll)
    boundEl.removeEventListener('wheel', onWheel)
    boundEl.removeEventListener('touchmove', onTouchMove)
    boundEl = null
  }

  watch(
    elRef,
    (el) => {
      if (el === boundEl) return
      unbind()
      if (!el) return
      el.addEventListener('scroll', onScroll, { passive: true })
      el.addEventListener('wheel', onWheel, { passive: true })
      el.addEventListener('touchmove', onTouchMove, { passive: true })
      boundEl = el
    },
    { immediate: true }
  )

  onBeforeUnmount(() => {
    unbind()
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  })

  /** 内容增长后调用：仅在跟随中才滚到底，且同一帧内只滚一次 */
  const keepAtBottom = () => {
    if (!isFollowing.value) return
    if (rafId !== null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      const el = elRef.value
      if (!el || !isFollowing.value) return
      el.scrollTop = el.scrollHeight
    })
  }

  /** 手动回到底部（供「回到底部」按钮使用） */
  const scrollToBottom = () => {
    const el = elRef.value
    if (!el) return
    isFollowing.value = true
    el.scrollTop = el.scrollHeight
  }

  /** 用户主动操作时立即停止跟随（可挂到任意交互事件上） */
  const pauseFollowing = () => {
    isFollowing.value = false
  }

  return { isFollowing, keepAtBottom, scrollToBottom, pauseFollowing }
}
