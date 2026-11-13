import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

/**
 * 题型库悬浮层：显隐状态、点击外部关闭与生命周期监听。
 *
 * 从 QuestionBuilder.vue 抽出。模板仍使用同名的
 * typePopoverVisible / typePopoverTriggerRef / typePopoverRef / toggleTypePopover。
 */
export function useQuestionBuilderTypePopover() {
  // 题型库悬浮层状态
  const typePopoverVisible = ref(false)
  const typePopoverTriggerRef = ref<HTMLElement | null>(null)
  const typePopoverRef = ref<HTMLElement | null>(null)

  const toggleTypePopover = (e?: Event) => {
    const before = typePopoverVisible.value
    typePopoverVisible.value = !typePopoverVisible.value
  }

  // 点击外部关闭悬浮层
  const handleOutsideClick = (e: MouseEvent) => {
    const target = e.target as Node
    if (!typePopoverVisible.value) {
      return
    }
    const triggerEl = typePopoverTriggerRef.value
    const popoverEl = typePopoverRef.value
    // 判断点击是否在悬浮层和触发按钮之外
    const inTrigger = triggerEl ? triggerEl.contains(target) : false
    const inPopover = popoverEl ? popoverEl.contains(target) : false
    if (!inTrigger && !inPopover) {
      typePopoverVisible.value = false
    }
  }

  // 监听悬浮层 visible 变化（无论何时改变都打印）
  watch(typePopoverVisible, (newVal, oldVal) => {
    if (newVal) {
      // 打开后下一帧检查 DOM 是否真的渲染
      nextTick(() => {
        const el = typePopoverRef.value
        if (!el) {
          return
        }
        const rect = el.getBoundingClientRect()
        const style = window.getComputedStyle(el)
      })
    }
  })

  onMounted(() => {
    document.addEventListener('mousedown', handleOutsideClick)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('mousedown', handleOutsideClick)
  })

  return { typePopoverVisible, typePopoverTriggerRef, typePopoverRef, toggleTypePopover }
}
