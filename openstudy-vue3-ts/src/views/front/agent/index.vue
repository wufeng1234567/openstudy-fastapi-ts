<!-- ==================== 智能体模块（聚合页） ==================== -->
<!--
  仿照 sp3 的 `views/front/agent/index.vue`：只做「记住上次访问的子页面」这一件事。

  为什么要有这一层而不是直接挂 chat.vue：
    · 与「我的学习 / 题库搭建 / 学习分享」保持一致的路由形态（/front/agent/<子页>）；
    · `goToModule('agent', 'chat')` 能复用 `frontPageCache` 的「回到上次子页」记忆。

  ⚠️ 这里原先写着「以后加『智能体 > 知识库』时不用改导航」—— **那个计划已作废**。
     知识库**不做独立子页/独立入口**，而是作为「输入栏按钮 + 右侧抽屉」嵌在 chat.vue 里：
     资料是给「这次提问」用的，入口就该在发消息的地方，跳页面反而绕远了。
     详见 `.codebuddy/rules/frontend-agent.md`。所以现在 `agent` 模块下只有 `chat` 一个子页。
-->
<template>
  <router-view v-slot="{ Component, route }">
    <keep-alive>
      <component :is="Component" :key="route.path" />
    </keep-alive>
  </router-view>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontAgent' })

import { onMounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

/** 只带模块路径（/front/agent）时补全到上次访问的子页 */
const ensureSubPath = () => {
  const path = route.path
  if (path === '/front/agent' || path === '/front/agent/') {
    const last = cacheStore.getLastVisited('agent', 'chat')
    router.replace(`/front/agent/${last}`)
  }
}

onMounted(ensureSubPath)
onActivated(ensureSubPath)
</script>
