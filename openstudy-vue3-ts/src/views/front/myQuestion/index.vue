<!-- front/myQuestion/index.vue -->
<!--
  「我的学习」聚合页
  =================
  ⚠️ 2026-10 重构：**删掉了页面内的左侧菜单**。
  导航早已统一收进全局竖向侧栏（侧栏「我的学习」可展开 8 个子项），
  这里再放一份左手菜单＝同一个功能出现三次（侧栏 → 二级列表 → 页内菜单），
  既占宽度又显得旧。现在这一层只做「记住上次子页」和路由出口。
-->
<template>
  <div class="my-question-page">
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyQuestion' })
import { onMounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

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

  router
    .push(`/front/myQuestion/${lastVisited}`)
    .then(() => {
      isRedirecting = false
    })
    .catch(() => {
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
.my-question-page {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 22px 28px 56px;
  box-sizing: border-box;
}

@media (max-width: 1024px) {
  .my-question-page {
    padding: 16px 18px 40px;
  }
}
</style>
