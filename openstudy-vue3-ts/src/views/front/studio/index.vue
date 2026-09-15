<!-- front/studio/index.vue -->
<template>
  <div class="studio-container">
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>
</template>
<script setup lang="ts">
defineOptions({ name: 'FrontStudio' })
import { useRoute, useRouter } from 'vue-router'
import { onMounted, onActivated } from 'vue'

const route = useRoute()
const router = useRouter()

// 直接进入 /front/studio 时重定向到创建题库页面
const redirectToCreate = () => {
  if (route.path === '/front/studio') {
    router.replace('/front/studio/create?type=public')
  }
}

onMounted(redirectToCreate)
onActivated(redirectToCreate)
</script>
<style scoped>
.studio-container {
  min-height: 100%;
}
</style>