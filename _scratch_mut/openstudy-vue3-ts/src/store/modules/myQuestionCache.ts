import { defineStore } from 'pinia'

const useMyQuestionCacheStore = defineStore('myQuestionCache', {
    state: () => ({
        lastVisited: 'myBank'  // 默认我的题库
    }),
    actions: {
        setLastVisited(path: string) {
            this.lastVisited = path
        }
    }
})

export default useMyQuestionCacheStore
