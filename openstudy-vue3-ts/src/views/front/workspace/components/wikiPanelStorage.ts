/** 知识百科视图的本地持久化 key 与安全读取。 */
export const WIKI_VIEW_KEY = 'openstudy.workspace.wikiView'
export const WIKI_LEARN_KEY = 'openstudy.workspace.wikiLearnMode'
export const WIKI_GUIDE_KEY = 'openstudy.workspace.routeGuideSeen'
export const WIKI_ROUTE_KEY = 'openstudy.workspace.routeQuery'
export function readWikiView(): 'pages' | 'map' {
  try {
    return localStorage.getItem(WIKI_VIEW_KEY) === 'map' ? 'map' : 'pages'
  } catch {
    return 'pages'
  }
}
export function readWikiLearnMode(): boolean {
  try {
    return localStorage.getItem(WIKI_LEARN_KEY) !== '0'
  } catch {
    return true
  }
}
export function readRouteQuery(): { strategy: 'weakness' | 'foundation' | 'explore'; targetPageId: number | null } | null {
  try {
    const raw = sessionStorage.getItem(WIKI_ROUTE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw)
    const strategy = ['weakness', 'foundation', 'explore'].includes(value?.strategy)
      ? value.strategy
      : 'weakness'
    return {
      strategy,
      targetPageId: Number(value?.targetPageId) || null
    }
  } catch {
    return null
  }
}
