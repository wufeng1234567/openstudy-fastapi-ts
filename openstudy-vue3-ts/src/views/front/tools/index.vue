<template>
    <div class="tools-container">
        <router-view v-slot="{ Component }">
            <keep-alive>
                <component :is="Component" />
            </keep-alive>
        </router-view>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontTools' })
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { onMounted, onActivated, watch } from 'vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const updateCache = () => {
    const path = route.path
    if (path.startsWith('/front/tools/')) {
        const subPath = path.replace('/front/tools/', '')
        if (subPath) {
            cacheStore.setLastVisited('tools', subPath)
        }
    }
}

onMounted(() => {
    if (route.path === '/front/tools') {
        const lastVisited = cacheStore.getLastVisited('tools', 'home')
        router.replace(`/front/tools/${lastVisited}`)
        return
    }
    updateCache()
})

onActivated(() => {
    if (route.path === '/front/tools') {
        const lastVisited = cacheStore.getLastVisited('tools', 'home')
        router.push(`/front/tools/${lastVisited}`)
        return
    }
    updateCache()
})

watch(() => route.path, () => {
    if (route.path === '/front/tools') return
    updateCache()
})
</script>
