<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted, nextTick } from 'vue'
import useSettingsStore from '@/store/modules/settings'
import { handleThemeStyle } from '@/utils/theme'

onMounted(() => {
  nextTick(() => {
    handleThemeStyle(useSettingsStore().theme)
  })
})
</script>

<style>
/* 全局样式 */
html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
}
</style>