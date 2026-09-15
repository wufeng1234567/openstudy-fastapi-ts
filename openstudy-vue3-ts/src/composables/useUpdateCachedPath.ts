import { onMounted, onActivated, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

export function useUpdateCachedPath(moduleKey: string, prefix: string) {
    const route = useRoute()
    const cacheStore = useFrontPageCacheStore()

    const update = () => {
        const path = route.path
        if (path.startsWith(prefix + '/')) {
            const subPath = path.replace(prefix + '/', '')
            if (subPath) {
                cacheStore.setLastVisited(moduleKey, subPath)
            }
        }
    }

    onMounted(update)
    onActivated(update)

    // 监听路由变化，确保手动输入 URL 也能更新
    watch(() => route.path, update)
}
