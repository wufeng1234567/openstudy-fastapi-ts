<template>
    <div class="english-container">
        <router-view v-slot="{ Component }">
            <keep-alive>
                <component :is="Component" />
            </keep-alive>
        </router-view>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglish' })
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { onMounted, onActivated, watch } from 'vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

// 更新缓存为当前路径
const updateCache = () => {
    const path = route.path
    if (path.startsWith('/front/english/')) {
        // 提取相对于 /front/english/ 的路径部分，包括可能的多级路径，如 'vocabulary/123'
        const subPath = path.replace('/front/english/', '')
        if (subPath) {
            cacheStore.setLastVisited('english', subPath)
        }
    }
}

// 组件挂载时（首次进入或刷新）
onMounted(() => {
    // 如果当前在英语根路径，跳转到上次访问的子页面
    if (route.path === '/front/english') {
        const lastVisited = cacheStore.getLastVisited('english', 'home')
        router.replace(`/front/english/${lastVisited}`)
        return
    }
    // 否则更新缓存以记录当前路径
    updateCache()
})

// 从其他模块切换回英语模块时（缓存激活）
onActivated(() => {
    // 如果处于根路径（可能由于某种原因），重定向
    if (route.path === '/front/english') {
        const lastVisited = cacheStore.getLastVisited('english', 'home')
        router.push(`/front/english/${lastVisited}`)
        return
    }
    // 更新缓存
    updateCache()
})

// 监听路由改变（如手动输入URL或内部跳转），及时更新缓存
watch(() => route.path, () => {
    if (route.path === '/front/english') {
        // 如果跳到了根路径，不做处理，让 onActivated 处理
        return
    }
    updateCache()
})
</script>