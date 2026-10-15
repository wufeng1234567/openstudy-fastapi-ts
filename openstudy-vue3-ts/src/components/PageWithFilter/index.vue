<!-- 通用页面容器（带筛选栏） -->
<template>
  <div class="page-with-filter" ref="pageRef">
    <!-- 搜索区域 -->
    <div ref="searchAreaRef" class="search-area">
      <div class="title-section">
        <h2 class="page-title">{{ title }}</h2>
        <span class="total-count">共 {{ total }} {{ unit }}</span>
      </div>
      <div class="search-section">
        <el-input
          v-model="searchKeyword"
          :placeholder="searchPlaceholder"
          clearable
          class="search-input"
          @input="$emit('search', searchKeyword)"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button @click="$emit('refresh')" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <slot name="header-extra" />
      </div>
    </div>

    <!-- 筛选侧边栏 -->
    <div class="filter-sidebar-wrapper" :style="{ top: searchAreaHeight + 'px' }">
      <slot name="filter" />
    </div>

    <!-- 内容区域 -->
    <div class="content-area" v-loading="loading">
      <!-- 空状态 -->
      <el-empty v-if="!loading && isEmpty" :description="emptyText">
        <template #image>
          <el-icon size="80"><component :is="emptyIcon" /></el-icon>
        </template>
        <slot name="empty-action" />
      </el-empty>

      <!-- 内容插槽 -->
      <slot v-else name="content" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  title: { type: String, default: '' },
  total: { type: Number, default: 0 },
  unit: { type: String, default: '个' },
  searchPlaceholder: { type: String, default: '搜索...' },
  loading: { type: Boolean, default: false },
  isEmpty: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  emptyIcon: { type: [String, Object], default: 'FolderOpened' },
  modelValue: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue', 'search', 'refresh', 'filter-change', 'reset-filters'])

const pageRef = ref(null)
const searchAreaRef = ref(null)
const searchAreaHeight = ref(0)
const searchKeyword = ref(props.modelValue)

// 测量搜索区域高度
const updateSearchAreaHeight = () => {
  nextTick(() => {
    if (searchAreaRef.value) {
      searchAreaHeight.value = searchAreaRef.value.offsetHeight
    }
  })
}

onMounted(() => {
  updateSearchAreaHeight()
  window.addEventListener('resize', updateSearchAreaHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateSearchAreaHeight)
})
</script>

<style scoped>
.page-with-filter {
  position: relative;
  min-height: 100%;
  padding: 0 16px;
}

.search-area {
  margin-bottom: 20px;
}

.title-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2937;
  margin: 0;
}

.total-count {
  font-size: 14px;
  color: #6b7280;
}

.search-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-input {
  flex: 1;
  max-width: 400px;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
}

.refresh-btn {
  border-radius: 8px;
}

.filter-sidebar-wrapper {
  position: absolute;
  left: 16px;
  z-index: 100;
}

.content-area {
  min-height: 400px;
}
</style>
