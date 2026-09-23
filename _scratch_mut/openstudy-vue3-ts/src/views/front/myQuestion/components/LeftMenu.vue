<template>
    <div class="left-menu">
        <div class="menu-header">
            <el-icon>
                <User />
            </el-icon>
            <span>我的学习</span>
        </div>
        <el-menu :default-active="activeMenu" class="menu-list" @select="handleMenuSelect">
            <el-menu-item index="/front/myQuestion/myBank">
                <el-icon>
                    <FolderOpened />
                </el-icon>
                <span>我的题库</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/myShares">
                <el-icon>
                    <Share />
                </el-icon>
                <span>我的分享</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/bankCollect">
                <el-icon>
                    <Star />
                </el-icon>
                <span>题库收藏</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/questionCollect">
                <el-icon>
                    <Collection />
                </el-icon>
                <span>题目收藏</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/wrongQuestion">
                <el-icon>
                    <Warning />
                </el-icon>
                <span>我的错题</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/masteredQuestion">
                <el-icon>
                    <CircleCheck />
                </el-icon>
                <span>我的斩题</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/myNotes">
                <el-icon>
                    <Notebook />
                </el-icon>
                <span>我的笔记</span>
            </el-menu-item>
            <el-menu-item index="/front/myQuestion/myStats">
                <el-icon>
                    <TrendCharts />
                </el-icon>
                <span>学习统计</span>
            </el-menu-item>
        </el-menu>
    </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { User, Star, Collection, Warning, CircleCheck, FolderOpened, Notebook, TrendCharts, Share } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const activeMenu = computed(() => route.path)

const handleMenuSelect = (index: string) => {
    // 记录最后访问的路径
    const path = index.split('/').pop() || ''  // 获取 myBank, bankCollect 等
    cacheStore.setLastVisited('myQuestion', path)
    router.push(index)
}

// 每次激活时，跳转到上次访问的子页面
onActivated(() => {
    if (route.path === '/front/myQuestion') {
        const lastVisited = cacheStore.getLastVisited('myQuestion', 'myBank')
        // console.log('🔄 回到上次访问的页面:', lastVisited)
        router.push(`/front/myQuestion/${lastVisited}`)
    }
})


onMounted(() => {
    // 如果当前路径是 /front/myQuestion/xxx，就将 xxx 存入缓存
    if (route.path.startsWith('/front/myQuestion/')) {
        const subPath = route.path.split('/').pop()
        if (subPath) {
            cacheStore.setLastVisited('myQuestion', subPath)
        }
    }
})
</script>

<style scoped lang="scss">
:root {
    --primary-50: #eef2ff;
    --primary-100: #e0e7ff;
    --primary-200: #c7d2fe;
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

.left-menu {
    width: 220px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    overflow: hidden;
    border: 2px solid var(--gray-200);
    border-right: 3px solid var(--primary-100);

    .menu-header {
        padding: 24px 20px 16px;
        display: flex;
        align-items: center;
        gap: 10px;
        border-bottom: 1px solid var(--gray-200);

        .el-icon {
            font-size: 22px;
            color: var(--primary-600);
        }

        span {
            font-size: 16px;
            font-weight: 600;
            color: var(--gray-900);
        }
    }

    .menu-list {
        border: none;
        padding: 8px 0;

        :deep(.el-menu-item) {
            height: 48px;
            line-height: 48px;
            margin: 4px 12px;
            border-radius: 8px;
            color: var(--gray-600);
            font-size: 14px;
            transition: all 0.2s ease;
            position: relative;
            border-left: 3px solid transparent;

            &:hover {
                background: var(--gray-50);
                color: var(--gray-900);
                border-left-color: var(--primary-200);
            }

            &.is-active {
                background: var(--primary-50);
                color: var(--primary-600);
                font-weight: 600;
                border-left: 3px solid var(--primary-600);
                box-shadow: 0 2px 8px rgba(79, 70, 229, 0.1);

                .el-icon {
                    color: var(--primary-600);
                }
            }

            .el-icon {
                margin-right: 12px;
                font-size: 18px;
                transition: color 0.2s ease;
            }
        }
    }
}
</style>