<!-- front/myQuestion/index.vue -->
<template>
    <div class="my-question-container">
        <LeftMenu />
        <div class="content-area">
            <router-view v-slot="{ Component }">
                <keep-alive>
                    <component :is="Component" />
                </keep-alive>
            </router-view>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyQuestion' })
import { onMounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import LeftMenu from './components/LeftMenu.vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

// 防止重复重定向的标记
let isRedirecting = false

const redirectToLastVisited = () => {
    // 只有路径正好是 /front/myQuestion 时才需要重定向
    if (route.path !== '/front/myQuestion') return false
    if (isRedirecting) return false

    isRedirecting = true
    const lastVisited = cacheStore.getLastVisited('myQuestion', 'myBank')

    router.push(`/front/myQuestion/${lastVisited}`).then(() => {
        isRedirecting = false
    }).catch(() => {
        isRedirecting = false
    })

    return true
}

onMounted(() => {
    redirectToLastVisited()
})

onActivated(() => {
    redirectToLastVisited()
})
</script>

<style scoped lang="scss">
:root {
    --primary-50: #eef2ff;
    --primary-100: #e0e7ff;
    --primary-500: #6366f1;
    --primary-600: #4f46e5;
    --primary-700: #4338ca;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-900: #111827;
}

.my-question-container {
    display: flex;
    gap: 24px;
    min-height: calc(100vh - 200px);
    position: relative;

    .content-area {
        flex: 1;
        background: white;
        border-radius: 16px;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        border: 2px solid var(--gray-200);
        border-left: 3px solid var(--primary-100);
        padding: 28px;
        position: relative;
        overflow-x: hidden;
    }
}

@media (max-width: 768px) {
    .my-question-container {
        flex-direction: column;
        gap: 16px;

        .content-area {
            padding: 16px;
            border-radius: 12px;
        }
    }
}
</style>