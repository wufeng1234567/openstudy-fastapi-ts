import { defineStore } from 'pinia'

export const useEnglishCacheStore = defineStore('englishCache', {
    state: () => ({
        lastVisited: 'home'  // 默认首页
    }),
    actions: {
        setLastVisited(path: string) {
            this.lastVisited = path
        }
    },
    persist: {
        enabled: true,
        strategies: [
            {
                storage: localStorage,
                paths: ['lastVisited']
            }
        ]
    }
})
