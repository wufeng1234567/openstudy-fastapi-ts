import { defineStore } from 'pinia'

// store/modules/frontPageCache.ts
export const useFrontPageCacheStore = defineStore('frontPageCache', {
    state: () => ({
        lastVisitedMap: {} as Record<string, string>,
        cachedForms: {} as Record<string, any>  // 新增
    }),
    actions: {
        setLastVisited(pageKey: string, path: string) { this.lastVisitedMap[pageKey] = path },
        getLastVisited(pageKey: string, defaultPath: string = 'home'): string { return this.lastVisitedMap[pageKey] || defaultPath },
        // 新增方法
        setCachedForm(formKey: string, data: any) { this.cachedForms[formKey] = data },
        getCachedForm(formKey: string): any { return this.cachedForms[formKey] || null },
        clearCachedForm(formKey: string) { delete this.cachedForms[formKey] }
    },
    persist: {
        enabled: true,
        strategies: [{ storage: localStorage, paths: ['lastVisitedMap', 'cachedForms'] }]
    }
})
