<template>
  <section class="app-main">
    <router-view v-slot="{ Component, route }">
      <transition name="fade-transform" mode="out-in">
        <keep-alive :include="tagsViewStore.cachedViews">
          <component v-if="!route.meta.link" :is="Component" :key="route.path"/>
        </keep-alive>
      </transition>
    </router-view>
    <iframe-toggle />
  </section>
</template>

<script setup lang="ts">
import iframeToggle from "./IframeToggle/index"
import useTagsViewStore from '@/store/modules/tagsView'

const tagsViewStore = useTagsViewStore()
</script>

<style lang="scss" scoped>
.app-main {
  /* 60= navbar  60  */
  min-height: calc(100vh - 60px);
  width: 100%;
  position: relative;
  overflow: hidden;
  background-color: #f9fafb;
}

.fixed-header + .app-main {
  padding-top: 60px;
}

.hasTagsView {
  .app-main {
    /* 100 = navbar + tags-view = 60 + 40 */
    min-height: calc(100vh - 100px);
  }

  .fixed-header + .app-main {
    padding-top: 100px;
  }
}
</style>

<style lang="scss">
// fix css style bug in open el-dialog
.el-popup-parent--hidden {
  .fixed-header {
    padding-right: 6px;
  }
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background-color: #f9fafb;
}

::-webkit-scrollbar-thumb {
  background-color: #d1d5db;
  border-radius: 3px;

  &:hover {
    background-color: #9ca3af;
  }
}
</style>

