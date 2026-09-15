<!-- 通用搜索框：最左侧内嵌「筛选」按钮（筛选按钮 + 竖线 + 搜索图标） -->
<template>
  <el-input :model-value="modelValue" :placeholder="placeholder" clearable class="search-filter-input"
    @update:model-value="handleUpdate" @keyup.enter="handleEnter" @clear="handleClear">
    <template #prefix>
      <span v-if="showFilter" class="filter-trigger" :class="{ 'is-open': filterOpen, 'is-active': filterActive }"
        @mousedown.prevent @click.stop="handleToggle" title="筛选">
        <el-icon class="filter-trigger__icon">
          <Operation />
        </el-icon>
        <span class="filter-trigger__text">筛选</span>
        <el-icon class="filter-trigger__caret" :class="{ 'is-open': filterOpen }">
          <ArrowDown />
        </el-icon>
      </span>
      <span v-if="showFilter" class="filter-divider"></span>
      <el-icon class="search-prefix-icon">
        <Search />
      </el-icon>
    </template>
  </el-input>
</template>

<script setup lang="ts">
defineOptions({ name: 'SearchFilterInput' })
import { Operation, ArrowDown, Search } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '搜索...'
  },
  showFilter: {
    type: Boolean,
    default: true
  },
  filterOpen: {
    type: Boolean,
    default: false
  },
  filterActive: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'input', 'enter', 'clear', 'toggle-filter'])

const handleUpdate = (value: string) => {
  emit('update:modelValue', value)
  emit('input', value)
}

const handleEnter = () => {
  emit('enter', props.modelValue)
}

const handleClear = () => {
  emit('update:modelValue', '')
  emit('input', '')
  emit('clear')
}

const handleToggle = () => {
  emit('toggle-filter')
}
</script>

<style scoped lang="scss">
.search-filter-input {
  :deep(.el-input__wrapper) {
    border-radius: 8px;
    box-shadow: 0 0 0 1px #e5e7eb;
    background: #fff;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  :deep(.el-input__wrapper:hover) {
    box-shadow: 0 0 0 1px #d1d5db;
  }

  :deep(.el-input__wrapper.is-focus),
  :deep(.el-input__wrapper:focus-within) {
    box-shadow: 0 0 0 1px #b3b3b3;
  }
}

.filter-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 100%;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
  pointer-events: auto;
  transition: color 0.2s ease;
}

.filter-trigger:hover,
.filter-trigger.is-open {
  color: #1f2937;
}

.filter-trigger.is-active {
  color: #1f2937;
  font-weight: 600;
}

.filter-trigger__icon {
  font-size: 15px;
}

.filter-trigger__text {
  white-space: nowrap;
}

.filter-trigger__caret {
  font-size: 12px;
  color: #9ca3af;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-trigger__caret.is-open {
  transform: rotate(180deg);
}

/* 筛选生效时的小圆点 */
.filter-trigger.is-active::after {
  content: '';
  position: absolute;
  top: -1px;
  right: -6px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6b7280;
}

.filter-divider {
  width: 1px;
  height: 16px;
  margin: 0 10px;
  background: #e5e7eb;
  flex-shrink: 0;
}

.search-prefix-icon {
  font-size: 15px;
  color: #9ca3af;
}
</style>
