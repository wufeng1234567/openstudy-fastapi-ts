<!--
  通用搜索框：最左侧内嵌「筛选」按钮（筛选按钮 + 竖线 + 搜索图标）
  ============================================================================
  全站所有主搜索框都用这一个组件（题库练习 / 题库管理 / 题目管理 / 笔记管理 /
  学习分享），所以「筛选」入口的形态只有一份定义。

  `#dropdown` 插槽：搜索框下方可以挂一块下拉内容（「学习分享」用它显示搜索历史）。
  内容绝对定位在输入框正下方，样式由使用方自己给。
-->
<template>
  <div class="sfi-root" :class="{ 'has-dropdown': !!$slots.dropdown }">
    <el-input :model-value="modelValue" :placeholder="placeholder" clearable class="search-filter-input"
      @update:model-value="handleUpdate" @keyup.enter="handleEnter" @clear="handleClear" @focus="emit('focus')"
      @blur="emit('blur')">
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

    <!-- 可选：搜索框下方的下拉内容（如搜索历史） -->
    <slot name="dropdown" />
  </div>
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

const emit = defineEmits(['update:modelValue', 'input', 'enter', 'clear', 'toggle-filter', 'focus', 'blur'])

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
/*
 * 根节点就是"输入框 + 可选下拉"的定位容器。
 * 使用方传进来的 class（如 `.search-input`）落在这一层，所以
 * `flex: 1 / max-width: 400px` 这类布局约束照旧生效。
 */
.sfi-root {
  position: relative;
  min-width: 0;
}

.sfi-root :deep(.el-input) {
  width: 100%;
}

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
