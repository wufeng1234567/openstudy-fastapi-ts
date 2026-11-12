import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getPlainText } from '@/utils/questionUtils'

/** 题目列表筛选、分页和标题自适应。 */
export function useQuestionBuilderList(options: {
  questions: { value: any[] }
  searchKeyword: { value: string }
  activeTypeFilters: { value: Set<string> }
  currentPage: { value: number }
  pageSize: { value: number }
  getTypeName: (type: string) => string
}) {
  const allFilteredQuestions = computed(() => {
    const keyword = options.searchKeyword.value.toLowerCase()
    const filters = options.activeTypeFilters.value
    return options.questions.value.filter((q: any) => {
      if (!filters.has('all') && !filters.has(q.type)) return false
      if (keyword) {
        const title = getPlainText(q?.title).toLowerCase()
        const typeName = options.getTypeName(q?.type)
        return title.includes(keyword) || typeName.includes(keyword)
      }
      return true
    })
  })

  const filteredQuestions = computed(() => {
    const start = (options.currentPage.value - 1) * options.pageSize.value
    return allFilteredQuestions.value.slice(start, start + options.pageSize.value)
  })

  watch(options.searchKeyword, () => {
    options.currentPage.value = 1
  })
  watch(allFilteredQuestions, (list) => {
    const maxPage = Math.ceil(list.length / options.pageSize.value) || 1
    if (options.currentPage.value > maxPage) options.currentPage.value = maxPage
  })

  const handlePageChange = (page: number) => {
    options.currentPage.value = page
  }
  const handleSizeChange = (size: number) => {
    options.pageSize.value = size
    options.currentPage.value = 1
  }

  const panelHeaderRef = ref<HTMLElement | null>(null)
  const panelTitleRef = ref<HTMLElement | null>(null)
  const titleMeasureRef = ref<HTMLElement | null>(null)
  const showTitleCount = ref(true)
  let titleFitObserver: ResizeObserver | null = null

  const updateTitleFit = () => {
    const titleEl = panelTitleRef.value
    const measureEl = titleMeasureRef.value
    if (!titleEl || !measureEl) return
    showTitleCount.value = measureEl.getBoundingClientRect().width <= titleEl.getBoundingClientRect().width
  }
  const stopTitleFitObserver = () => {
    titleFitObserver?.disconnect()
    titleFitObserver = null
  }
  const startTitleFitObserver = () => {
    stopTitleFitObserver()
    if (typeof ResizeObserver === 'undefined') return
    titleFitObserver = new ResizeObserver(() => updateTitleFit())
    if (panelHeaderRef.value) titleFitObserver.observe(panelHeaderRef.value)
    if (panelTitleRef.value) titleFitObserver.observe(panelTitleRef.value)
    updateTitleFit()
  }

  watch(
    () => `${allFilteredQuestions.value.length}/${options.questions.value.length}`,
    () => nextTick(() => updateTitleFit())
  )
  onMounted(() => nextTick(() => startTitleFitObserver()))
  onBeforeUnmount(() => stopTitleFitObserver())

  return {
    allFilteredQuestions,
    filteredQuestions,
    handlePageChange,
    handleSizeChange,
    panelHeaderRef,
    panelTitleRef,
    titleMeasureRef,
    showTitleCount
  }
}
