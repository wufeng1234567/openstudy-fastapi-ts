<!-- 通用筛选侧边栏组件 -->
<template>
  <div ref="filterRef" class="filter-sidebar" :class="{ collapsed: isCollapsed, embedded: hideTrigger }">
    <!-- 收缩/展开按钮（内嵌模式下改由搜索框内的按钮触发） -->
    <div v-if="!hideTrigger" class="toggle-btn" @click.stop="toggleCollapse">
      <el-icon>
        <DArrowLeft v-if="!isCollapsed" />
        <DArrowRight v-else />
      </el-icon>
    </div>

    <!-- 筛选内容 -->
    <div class="filter-content" v-show="!isCollapsed">
      <div class="filter-section">
        <h3 class="filter-title">
          <span>{{ title }}</span>
          <span v-if="hideTrigger" class="panel-close" @click.stop="toggleCollapse">
            <el-icon>
              <Close />
            </el-icon>
          </span>
        </h3>

        <!-- 动态渲染筛选组 -->
        <div v-for="group in filterGroups" :key="group.key" class="filter-group">
          <div class="filter-label">{{ group.label }}</div>
          <div class="filter-options">
            <!-- 复选框组 -->
            <el-checkbox-group v-if="group.type === 'checkbox'" v-model="localFilter[group.key]" @change="handleChange">
              <el-checkbox v-for="opt in group.options" :key="opt.value" :label="opt.value" class="filter-checkbox">
                <span :class="opt.class">{{ opt.label }}</span>
              </el-checkbox>
            </el-checkbox-group>

            <!-- 单选框组 -->
            <el-radio-group v-else-if="group.type === 'radio'" v-model="localFilter[group.key]" @change="handleChange">
              <el-radio v-for="opt in group.options" :key="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-radio>
            </el-radio-group>

            <!-- 下拉选择 -->
            <el-select v-else-if="group.type === 'select'" v-model="localFilter[group.key]" placeholder="选择" clearable
              @change="handleChange" class="filter-select">
              <el-option v-for="opt in group.options" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>

            <!-- 日期范围（时间筛选） -->
            <el-date-picker v-else-if="group.type === 'dateRange'" v-model="localFilter[group.key]" type="daterange"
              range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
              size="small" class="filter-date-range" @change="handleChange" />
          </div>
        </div>

        <!-- 清空筛选按钮 -->
        <div class="filter-actions">
          <el-button type="default" size="small" @click="handleReset" plain>
            清空筛选
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { DArrowLeft, DArrowRight, Close } from '@element-plus/icons-vue'

const emit = defineEmits(['filter-change', 'reset-filters', 'collapse-change', 'active-change'])

const props = defineProps({
  title: {
    type: String,
    default: '筛选'
  },
  filterGroups: {
    type: Array,
    default: () => []
    // 格式: [{ key: 'type', label: '题型', type: 'checkbox', options: [{ value: 1, label: '单选题' }] }]
  },
  filterForm: {
    type: Object,
    default: () => ({})
  },
  defaultFilter: {
    type: Object,
    default: () => ({})
  },
  defaultCollapsed: {
    type: Boolean,
    default: true
  },
  // 内嵌模式：不渲染悬浮触发按钮，由外部的搜索框按钮控制
  hideTrigger: {
    type: Boolean,
    default: false
  }
})

const filterRef = ref(null)
const isCollapsed = ref(props.defaultCollapsed)
const localFilter = ref({ ...props.defaultFilter, ...props.filterForm })

// 切换展开/收起
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
  emit('collapse-change', isCollapsed.value)
}

// 点击外部关闭
const handleClickOutside = (event: MouseEvent) => {
  if (isCollapsed.value) return
  const target = event.target as HTMLElement | null
  // 点击搜索框内的筛选触发按钮时交给按钮自己切换，避免又关又开
  if (target?.closest?.('.filter-trigger')) return
  // 点击 el-date-picker / el-select 的弹出浮层（默认 teleport 到 body，
  // 不在 filterRef 内）时不关闭面板，否则点一下日期面板筛选栏就消失
  if (target?.closest?.('.el-picker__popper, .el-select__popper')) return
  if (filterRef.value && !filterRef.value.contains(event.target)) {
    isCollapsed.value = true
    emit('collapse-change', true)
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside, true)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside, true)
})

// 筛选变化
const handleChange = () => {
  emit('filter-change', { ...localFilter.value })
}

// 重置筛选
const handleReset = () => {
  localFilter.value = { ...props.defaultFilter }
  emit('reset-filters')
  emit('filter-change', { ...localFilter.value })
}

// 是否已有生效的筛选条件（与默认筛选不一致）
const isFilterActive = computed(() => {
  const def = props.defaultFilter || {}
  const keys = Object.keys(props.filterForm || def)
  return keys.some((key) => {
    const current = localFilter.value?.[key]
    const base = def?.[key]
    if (Array.isArray(current) || Array.isArray(base)) {
      return JSON.stringify(current || []) !== JSON.stringify(base || [])
    }
    return current !== base
  })
})

watch(isFilterActive, (val) => {
  emit('active-change', val)
}, { immediate: true })

// 监听父组件 filterForm 的变化
watch(() => props.filterForm, (newVal) => {
  if (!newVal) return
  localFilter.value = { ...localFilter.value, ...newVal }
}, { deep: true, immediate: true })

// 供父组件（内嵌触发按钮）调用
defineExpose({
  toggleCollapse,
  close: () => {
    if (!isCollapsed.value) {
      isCollapsed.value = true
      emit('collapse-change', true)
    }
  },
  isCollapsed
})
</script>

<style scoped>
.filter-sidebar {
  position: absolute;
  left: 0;
  top: calc(var(--filter-top, 0px) + 8px);
  display: flex;
  flex-direction: column;
  width: 260px;
  height: auto;
  /* 限高：最多 560px，且不超出视口（给 header 和底部留出空间） */
  max-height: min(560px, calc(100vh - var(--filter-top, 0px) - 40px));
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid #e5e7eb;
  z-index: 50;
  transition: width 0.3s ease;
  overflow: hidden;
}

.filter-sidebar.collapsed {
  width: 32px;
  height: 32px;
  min-height: 32px;
  border-radius: 8px;
  cursor: pointer;
}

/* 内嵌模式：面板对齐页面内容左边缘（默认 16px，可用 --filter-left 覆盖） */
.filter-sidebar.embedded {
  left: var(--filter-left, 16px);
  transform-origin: top left;
  /*
   * 关键：不要宽度过渡。
   * 否则展开时宽度 0 → 260px，期间容器极窄，胶囊选项会被挤成竖排，
   * 等宽度涨到位才重新横向排列，看起来就是「一瞬间竖→横」的跳动。
   * 展开动画改用下面的 filter-panel-in（只做透明度 + 位移，不改宽度）。
   */
  transition: none;
}

/* 内嵌模式：收起时完全隐藏，避免留下空白小方块 */
.filter-sidebar.embedded.collapsed {
  width: 0;
  height: 0;
  min-height: 0;
  border: 0;
  box-shadow: none;
  overflow: hidden;
  pointer-events: none;
}

/* 内嵌模式下拉出现动画 */
.filter-sidebar.embedded:not(.collapsed) {
  animation: filter-panel-in 0.18s ease;
}

@keyframes filter-panel-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.toggle-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s ease;
}

.filter-sidebar:not(.collapsed) .toggle-btn {
  position: absolute;
  right: 4px;
  top: 6px;
  z-index: 51;
}

.filter-sidebar.collapsed .toggle-btn {
  border-radius: 8px;
}

.toggle-btn:hover {
  background: #f5f5f5;
}

.toggle-btn .el-icon {
  font-size: 16px;
  color: #606266;
}

.filter-content {
  /* flex 撑满剩余高度，内部出现竖向滚动条 */
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  padding: 16px 18px;
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  background: #fff;
  border-radius: 12px;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #dcdfe6 transparent;
}

/* 竖向滚动条常驻可见（细样式） */
.filter-content::-webkit-scrollbar {
  width: 6px;
}

.filter-content::-webkit-scrollbar-track {
  background: transparent;
}

.filter-content::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 3px;
}

.filter-content::-webkit-scrollbar-thumb:hover {
  background: #c8ccd4;
}

.filter-section .filter-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 0 14px 0;
  padding-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  border-bottom: 1px solid #f3f4f6;
}

.panel-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.2s ease;
}

.panel-close:hover {
  background: #f3f4f6;
  color: #4b5563;
}

.filter-group {
  margin-bottom: 14px;
  text-align: left;
}

.filter-group:last-of-type {
  margin-bottom: 0;
}

.filter-group .filter-label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
  font-weight: 500;
  letter-spacing: 0.5px;
}

.filter-options {
  display: flex;
  flex-direction: column;
}

/* 选项改为横向换行的「胶囊」标签，避免纵向堆叠占空间 */
.filter-options :deep(.el-checkbox-group),
.filter-options :deep(.el-radio-group) {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.filter-options :deep(.el-checkbox),
.filter-options :deep(.el-radio) {
  display: inline-flex;
  align-items: center;
  width: auto;
  height: auto;
  margin: 0;
  padding: 4px 12px;
  font-size: 12px;
  line-height: 1.5;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  box-sizing: border-box;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 隐藏原生勾选框/圆点，只保留文字，整体作为可点击胶囊 */
.filter-options :deep(.el-checkbox__input),
.filter-options :deep(.el-radio__input) {
  display: none;
}

.filter-options :deep(.el-radio__label),
.filter-options :deep(.el-checkbox__label) {
  padding-left: 0;
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
  transition: color 0.2s ease;
}

.filter-options :deep(.el-checkbox:hover),
.filter-options :deep(.el-radio:hover) {
  background: #f9fafb;
  border-color: #d1d5db;
}

.filter-options :deep(.el-checkbox.is-checked),
.filter-options :deep(.el-radio.is-checked) {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.filter-options :deep(.el-checkbox.is-checked .el-checkbox__label),
.filter-options :deep(.el-radio.is-checked .el-radio__label) {
  color: #1f2937;
  font-weight: 600;
}

.filter-select {
  width: 100%;
}

/* 时间筛选：日期范围占满整行
   注意：el-date-picker 是多根组件，父作用域 data-v 不会落到其根元素，
   所以必须从 .filter-sidebar（组件根，带 data-v）用 :deep 后代选择器命中，
   不能直接写 .filter-date-range（会编译成带 [data-v] 的属性选择器而失配）。
   覆盖 Element Plus daterange 默认 350px 宽度，否则右侧会被
   .filter-content 的 overflow-x:hidden 裁掉，只显示左边一部分 */
.filter-sidebar :deep(.filter-date-range) {
  --el-date-editor-width: 100%;
  width: 100%;
  box-sizing: border-box;
}

.filter-date-range :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-date-range :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #d1d5db;
}

.filter-select :deep(.el-select__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
  text-align: left;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-select :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px #d1d5db;
}

.filter-actions {
  /* 吸底：内容滚动时「清空筛选」始终可见 */
  position: sticky;
  bottom: 0;
  z-index: 1;
  margin: 14px -18px 0;
  padding: 12px 18px 16px;
  border-top: 1px solid #f3f4f6;
  background: #fff;
}

.filter-actions :deep(.el-button) {
  width: 100%;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-actions :deep(.el-button:hover) {
  border-color: #d1d5db;
  color: #4b5563;
  background: #fff;
}

/* 难度颜色 */
.difficulty-1 { color: #67c23a; }
.difficulty-2 { color: #409eff; }
.difficulty-3 { color: #e6a23c; }
.difficulty-4 { color: #f56c6c; }
</style>
