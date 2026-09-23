<!-- 通用筛选侧边栏 -->
<template>
  <div class="filter-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- 收缩/展开按钮 -->
    <div class="toggle-btn" @click="toggleCollapse">
      <el-icon>
        <DArrowLeft v-if="!isCollapsed" />
        <DArrowRight v-else />
      </el-icon>
    </div>

    <!-- 筛选内容 -->
    <div class="filter-content" v-show="!isCollapsed">
      <div class="filter-section">
        <h3 class="filter-title">{{ title }}</h3>

        <!-- 动态渲染筛选组 -->
        <div v-for="group in filterGroups" :key="group.key" class="filter-group">
          <div class="filter-label">{{ group.label }}</div>
          <div class="filter-options">
            <!-- 多选 -->
            <el-checkbox-group v-if="group.type === 'checkbox'" v-model="localFilter[group.key]" @change="handleChange">
              <el-checkbox v-for="opt in group.options" :key="opt.value" :label="opt.value" class="filter-checkbox">
                {{ opt.label }}
                <span v-if="opt.count !== undefined" class="option-count">{{ opt.count }}</span>
              </el-checkbox>
            </el-checkbox-group>

            <!-- 单选 -->
            <el-radio-group v-else-if="group.type === 'radio'" v-model="localFilter[group.key]" @change="handleChange">
              <el-radio v-for="opt in group.options" :key="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-radio>
            </el-radio-group>

            <!-- 下拉选择 -->
            <el-select v-else-if="group.type === 'select'" v-model="localFilter[group.key]" placeholder="选择" clearable @change="handleChange" class="filter-select">
              <el-option v-for="opt in group.options" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
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
import { ref, watch } from 'vue'
import { DArrowLeft, DArrowRight } from '@element-plus/icons-vue'

const props = defineProps({
  title: { type: String, default: '筛选' },
  filterGroups: { type: Array, default: () => [] },
  filterForm: { type: Object, default: () => ({}) },
  defaultFilter: { type: Object, default: () => ({}) },
  defaultCollapsed: { type: Boolean, default: true }
})

const emit = defineEmits(['filter-change', 'reset-filters'])

const isCollapsed = ref(props.defaultCollapsed)
const localFilter = ref({ ...props.defaultFilter, ...props.filterForm })

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const handleChange = () => {
  emit('filter-change', { ...localFilter.value })
}

const handleReset = () => {
  localFilter.value = { ...props.defaultFilter }
  emit('reset-filters')
  emit('filter-change', { ...localFilter.value })
}

// 监听父组件 filterForm 的变化
watch(() => props.filterForm, (newVal) => {
  if (!newVal) return
  localFilter.value = { ...localFilter.value, ...newVal }
}, { deep: true, immediate: true })
</script>

<style scoped>
.filter-sidebar {
  width: 260px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  border: 1px solid #e4e7ed;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: visible;
  position: relative;
}

.filter-sidebar.collapsed {
  width: 0;
  min-width: 0;
  border: none;
  box-shadow: none;
  overflow: hidden;
}

.toggle-btn {
  position: absolute;
  right: -36px;
  top: 16px;
  width: 36px;
  height: 40px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-left: none;
  border-radius: 0 8px 8px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 101;
  box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.06);
  transition: all 0.2s ease;
}

.filter-sidebar.collapsed .toggle-btn {
  right: -36px;
}

.toggle-btn:hover {
  background: #ecf5ff;
  border-color: #409eff;
}

.toggle-btn:hover .el-icon {
  color: #409eff;
}

.toggle-btn .el-icon {
  font-size: 18px;
  color: #606266;
  transition: color 0.2s;
}

.filter-content {
  padding: 16px;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.filter-content::-webkit-scrollbar {
  width: 4px;
}

.filter-content::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 2px;
}

.filter-section .filter-title {
  margin: 0 0 16px 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #e4e7ed;
  padding-bottom: 10px;
}

.filter-group {
  margin-bottom: 16px;
}

.filter-group .filter-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
  font-weight: 500;
}

.filter-options :deep(.el-checkbox-group),
.filter-options :deep(.el-radio-group) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-options :deep(.el-checkbox),
.filter-options :deep(.el-radio) {
  margin-right: 0;
  font-size: 13px;
  display: flex;
  align-items: center;
}

.option-count {
  margin-left: auto;
  background: #f0f0f0;
  color: #666;
  padding: 0 6px;
  border-radius: 8px;
  font-size: 11px;
}

.filter-select {
  width: 100%;
}

.filter-actions {
  margin-top: 20px;
}

.filter-actions :deep(.el-button) {
  width: 100%;
  border-radius: 8px;
}
</style>
