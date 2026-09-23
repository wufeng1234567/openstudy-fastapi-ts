<!-- src/views/questionPractice/index.vue -->
<template>
  <router-view v-slot="{ Component }">
    <keep-alive>
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontQuestionPractice' })
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { onMounted, onActivated, watch } from 'vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const getSubPath = (path: string) => {
  if (!path || !path.startsWith('/front/questionPractice/')) return ''
  return path.replace('/front/questionPractice/', '')
}

const updateCache = () => {
  const subPath = getSubPath(route.path)
  if (subPath) {
    cacheStore.setLastVisited('questionPractice', subPath)
  }
}

const redirectToLastVisited = () => {
  const lastVisited = cacheStore.getLastVisited('questionPractice', '')
  if (lastVisited && lastVisited !== 'undefined') {
    router.replace(`/front/questionPractice/${lastVisited}`)
    return true
  }
  return false
}

watch(() => route.path, () => {
  updateCache()
})

onMounted(() => {
  if (route.path === '/front/questionPractice') {
    if (redirectToLastVisited()) return
  }
  updateCache()
})

onActivated(() => {
  if (route.path === '/front/questionPractice') {
    if (redirectToLastVisited()) return
  }
  updateCache()
})
</script>
