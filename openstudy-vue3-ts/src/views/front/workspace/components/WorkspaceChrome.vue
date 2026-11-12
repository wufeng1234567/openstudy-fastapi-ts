<template>
  <Teleport v-if="canTeleport" to="#os-workspace-nav">
    <div class="kbp-workspace-nav">
      <div class="kbp-nav-row">
        <nav class="kbp-crumbs" aria-label="当前位置">
          <button type="button" class="kbp-crumbs__root" @click="emit('update:viewMode', 'list')">我的资料</button>
          <span class="kbp-crumbs__sep">/</span>
          <span class="kbp-crumbs__current">{{ activeKbName || '全部资料' }}</span>
        </nav>

        <nav class="kbp-tabs" role="tablist" aria-label="资料视图">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            class="kbp-tab"
            :class="{ 'is-active': viewMode === tab.key }"
            role="tab"
            :aria-selected="viewMode === tab.key"
            @click="emit('update:viewMode', tab.key)"
          >
            <OsIcon :name="tab.icon" :size="15" />
            <span>{{ tab.label }}</span>
          </button>
        </nav>
      </div>
    </div>
  </Teleport>

  <div class="kbp-context-bar">
    <div class="kbp-context-count">{{ countLabel }}</div>
    <div class="kbp-context-tools">
      <div class="kbp-search-wrap">
        <SearchFilterInput
          :model-value="search"
          class="kbp-global-search"
          :placeholder="searchPlaceholder"
          :show-filter="true"
          :filter-open="filterOpen"
          :filter-active="filterActive"
          @update:model-value="emit('update:search', $event)"
          @toggle-filter="emit('toggle-filter')"
          @enter="emit('enter')"
        >
          <template #dropdown>
            <div v-if="viewMode === 'wiki'" id="workspace-wiki-search-dropdown"></div>
          </template>
        </SearchFilterInput>
        <CommonFilterSidebar
          ref="filterSidebarRef"
          :key="viewMode"
          :title="filterTitle"
          hide-trigger
          :filter-groups="filterGroups"
          :filter-form="filterForm"
          :default-filter="filterDefault"
          :default-collapsed="true"
          :style="{ '--filter-top': '38px', '--filter-left': '0px' }"
          @filter-change="emit('filter-change', $event)"
          @reset-filters="emit('reset-filters')"
          @collapse-change="emit('update:filterOpen', $event)"
          @active-change="emit('update:filterActive', $event)"
        />
      </div>
      <div v-if="viewMode === 'gallery'" id="workspace-gallery-describe" class="kbp-gallery-describe-slot"></div>
      <div v-if="viewMode === 'wiki'" id="workspace-wiki-toolbar" class="kbp-wiki-toolbar"></div>
      <el-button v-if="viewMode !== 'wiki'" size="small" text class="kbp-receive-share" @click="emit('receive')">
        <el-icon><Download /></el-icon>
        获取资料分享
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'

const props = defineProps<{
  canTeleport: boolean
  viewMode: 'list' | 'shelf' | 'gallery' | 'wiki'
  activeKbName?: string
  tabs: Array<{ key: string; label: string; icon: string }>
  countLabel: string
  search: string
  searchPlaceholder: string
  filterOpen: boolean
  filterActive: boolean
  filterTitle: string
  filterGroups: any[]
  filterForm: Record<string, any>
  filterDefault: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'update:viewMode', value: 'list' | 'shelf' | 'gallery' | 'wiki'): void
  (e: 'update:search', value: string): void
  (e: 'update:filterOpen', value: boolean): void
  (e: 'update:filterActive', value: boolean): void
  (e: 'toggle-filter'): void
  (e: 'enter'): void
  (e: 'filter-change', value: Record<string, any>): void
  (e: 'reset-filters'): void
  (e: 'receive'): void
}>()

const filterSidebarRef = ref<any>(null)
defineExpose({
  toggleCollapse: () => filterSidebarRef.value?.toggleCollapse?.()
})
</script>
