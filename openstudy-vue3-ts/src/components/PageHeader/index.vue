<!-- 通用页面头部组件（标题 + 搜索） -->
<template>
  <div class="page-header">
    <!-- 标题和搜索区域 -->
    <div class="search-area">
      <!--
        `hideTitle`：内嵌到「笔记管理」这类分组壳里时，
        标题行由外层分组切换 + 顶栏承担，这里不再重复渲染。
        搜索框与操作按钮保留（那是页面级功能，不是标题）。
      -->
      <div v-if="!hideTitle" class="title-section">
        <h2 class="page-title">{{ title }}</h2>
        <span class="total-count">{{ countText }}</span>
      </div>

      <div class="search-section">
        <SearchFilterInput v-model="keyword" :placeholder="placeholder" class="search-input" :show-filter="showFilter"
          :filter-open="filterOpen" :filter-active="filterActive" @input="handleInput" @enter="handleEnter"
          @clear="handleClear" @toggle-filter="emit('toggle-filter')" />

        <el-button @click="handleRefresh" class="refresh-btn">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>

        <slot name="extra"></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  /**
   * 隐藏标题行（只保留搜索框与操作按钮）
   * 用于内嵌到「题库管理 / 题目管理 / 笔记管理」这类带分组切换的壳里 ——
   * 标题由分组切换 + 顶栏承担，不再重复。
   */
  hideTitle: {
    type: Boolean,
    default: false
  },
  total: {
    type: Number,
    default: 0
  },
  unit: {
    type: String,
    default: '个'
  },
  itemName: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '搜索...'
  },
  modelValue: {
    type: String,
    default: ''
  },
  // 是否在搜索框内展示「筛选」入口
  showFilter: {
    type: Boolean,
    default: false
  },
  // 筛选面板是否展开（用于按钮态）
  filterOpen: {
    type: Boolean,
    default: false
  },
  // 是否已有生效的筛选条件（用于小圆点提示）
  filterActive: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['search', 'refresh', 'update:modelValue', 'toggle-filter'])

const keyword = ref(props.modelValue || '')
let searchTimer = null

watch(() => props.modelValue, (val) => {
  keyword.value = val || ''
})

const countText = computed(() => {
  if (!props.itemName) return `共 ${props.total} ${props.unit}`
  return `共 ${props.total} ${props.unit}${props.itemName}`
})

const handleInput = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    emit('update:modelValue', keyword.value)
    emit('search', keyword.value)
  }, 300)
}

const handleEnter = () => {
  if (searchTimer) clearTimeout(searchTimer)
  emit('update:modelValue', keyword.value)
  emit('search', keyword.value)
}

const handleClear = () => {
  if (searchTimer) clearTimeout(searchTimer)
  emit('update:modelValue', '')
  emit('search', '')
}

const handleRefresh = () => emit('refresh')
</script>

<style scoped lang="scss">
.page-header {
  .search-area {
    margin-bottom: 24px;
  }

  .title-section {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
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

    :deep(.el-input__wrapper) {
      border-radius: 8px;
      box-shadow: 0 0 0 1px #e5e7eb;
      background: #fff;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    :deep(.el-input__wrapper):hover {
      box-shadow: 0 0 0 1px #d1d5db;
    }

    :deep(.el-input__wrapper.is-focus) {
      box-shadow: 0 0 0 1px #b3b3b3;
    }
  }

  .refresh-btn {
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    padding: 8px 14px;
    height: auto;
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .refresh-btn:hover {
    transform: translateY(-2px);
    border-color: #d1d5db;
    color: #4b5563;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
  }

  .refresh-btn:active {
    transform: translateY(0);
  }
}
</style>
