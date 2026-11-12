import { computed } from 'vue'
import { normalizePageType } from '../utils/knowledgeGraphMeta'

/** 知识百科页面的来源/页面类型过滤和链接聚合。 */
export function useWikiPanelFilters(options: { props: any; pages: any; activePage: any }) {
  const { props, pages, activePage } = options

const graphSourceTypeFilter = computed(() => {
  const value = props.filters?.sourceType
  return Array.isArray(value) ? value.map(String) : []
})
const graphPageTypeFilter = computed(() => {
  const value = props.filters?.pageType
  return Array.isArray(value) ? value.map(String) : []
})
const graphLearningFilter = computed(() => {
  const value = props.filters?.learning
  return Array.isArray(value) ? value.map(String) : []
})

const filteredPages = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  const pageTypes = graphPageTypeFilter.value
  return pages.value.filter((page: any) => {
    if (query && !`${page.title || ''} ${page.summary || ''}`.toLowerCase().includes(query)) return false
    if (pageTypes.length && !pageTypes.includes(normalizePageType(page.pageType))) return false
    return true
  })
})

const linkTargets = computed(() =>
  pages.value.filter((page: any) => Number(page.pageId) !== Number(activePage.value?.pageId))
)

/** 同一目标页 + 同一锚文本的多次正文出现合并成一行，避免摘要/各小节重复刷屏。 */
function groupLinkItems(items: any[] = []) {
  const grouped = new Map<string, any>()
  for (const item of items) {
    const key = `${item.pageId}:${item.anchorText || ''}`
    let entry = grouped.get(key)
    if (!entry) {
      entry = { ...item, sectionIndexes: [] as number[] }
      grouped.set(key, entry)
    }
    const sectionIndex = Number(item.sectionIndex)
    if (!entry.sectionIndexes.includes(sectionIndex)) entry.sectionIndexes.push(sectionIndex)
  }
  return Array.from(grouped.values())
    .map((item) => ({
      ...item,
      sectionIndexes: [...item.sectionIndexes].sort((a: number, b: number) => a - b)
    }))
    .sort((a, b) => String(a.title || '').localeCompare(String(b.title || '')))
}

const groupedOutLinks = computed(() => groupLinkItems(activePage.value?.outLinks || []))
const groupedInLinks = computed(() => groupLinkItems(activePage.value?.inLinks || []))



  return {
    graphSourceTypeFilter,
    graphPageTypeFilter,
    graphLearningFilter,
    filteredPages,
    linkTargets,
    groupLinkItems,
    groupedOutLinks,
    groupedInLinks
  }
}
