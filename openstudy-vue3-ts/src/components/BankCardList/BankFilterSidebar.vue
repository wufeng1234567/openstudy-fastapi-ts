<!-- src/components/BankCardList/BankFilterSidebar.vue -->
<template>
  <div ref="filterRef" class="filter-sidebar" :class="{ collapsed: isCollapsed }">
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
        <h3 class="filter-title">筛选</h3>

        <!-- 科目筛选 -->
        <div class="filter-group">
          <div class="filter-label">科目分类</div>
          <div class="filter-options">
            <el-checkbox-group v-model="localFilter.subjects" @change="handleChange">
              <el-checkbox v-for="subject in subjectOptions" :key="subject" :value="subject" class="filter-checkbox">
                {{ subject }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </div>

        <!-- 题目数量筛选 -->
        <div class="filter-group">
          <div class="filter-label">题目数量</div>
          <div class="filter-options">
            <el-radio-group v-model="localFilter.questionCount" @change="handleChange">
              <el-radio :value="null">全部</el-radio>
              <el-radio :value="'0-10'">10题以下</el-radio>
              <el-radio :value="'10-50'">10-50题</el-radio>
              <el-radio :value="'50-100'">50-100题</el-radio>
              <el-radio :value="'100+'">100题以上</el-radio>
            </el-radio-group>
          </div>
        </div>

        <!-- 公开状态筛选 -->
        <div class="filter-group">
          <div class="filter-label">可见性</div>
          <div class="filter-options">
            <el-radio-group v-model="localFilter.isPublic" @change="handleChange">
              <el-radio :value="null">全部</el-radio>
              <el-radio :value="0">公开</el-radio>
              <el-radio :value="1">私有</el-radio>
            </el-radio-group>
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
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { DArrowLeft, DArrowRight } from '@element-plus/icons-vue'

const emit = defineEmits(['filter-change', 'reset-filters', 'collapse-change'])

const props = defineProps({
  filterForm: {
    type: Object,
    default: () => ({})
  },
  bankList: {
    type: Array,
    default: () => []
  },
  defaultCollapsed: {
    type: Boolean,
    default: true
  }
})

const filterRef = ref(null)
const isCollapsed = ref(props.defaultCollapsed)
const localFilter = ref({
  subjects: [],
  questionCount: null,
  isPublic: null,
  ...props.filterForm
})

// 从题库列表中提取所有科目选项
const subjectOptions = computed(() => {
  const subjects = new Set()
  props.bankList.forEach(bank => {
    if (bank.subject) subjects.add(bank.subject)
  })
  return Array.from(subjects).sort()
})

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
  emit('collapse-change', isCollapsed.value)
}

// 点击外部关闭
const handleClickOutside = (event) => {
  if (isCollapsed.value) return
  if (filterRef.value && !filterRef.value.contains(event.target)) {
    // 排除 toggle-btn 的点击
    const toggleBtn = filterRef.value.querySelector('.toggle-btn')
    if (toggleBtn && toggleBtn.contains(event.target)) return
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

const handleChange = () => {
  emit('filter-change', { ...localFilter.value })
}

const handleReset = () => {
  localFilter.value = {
    subjects: [],
    questionCount: null,
    isPublic: null
  }
  emit('reset-filters')
}

// 监听父组件 filterForm 的变化
watch(() => props.filterForm, (newVal) => {
  if (!newVal) return
  localFilter.value = {
    ...localFilter.value,
    ...newVal
  }
  if (newVal.subjects && Array.isArray(newVal.subjects)) {
    localFilter.value.subjects = [...newVal.subjects]
  }
}, { deep: true, immediate: true })
</script>

<style scoped>
.filter-sidebar {
  position: absolute;
  left: 0;
  top: var(--filter-top, 0);
  width: 260px;
  height: auto;
  max-height: calc(100% - var(--filter-top, 0px));
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  border: 1px solid #e4e7ed;
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
  padding: 16px 18px;
  height: auto;
  max-height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
  background: #fff;
}

.filter-content::-webkit-scrollbar {
  width: 4px;
}

.filter-content::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 2px;
}

.filter-section .filter-title {
  margin: 0 0 14px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #e4e7ed;
  padding-bottom: 10px;
}

.filter-group {
  margin-bottom: 18px;
  text-align: left;
}

.filter-group .filter-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.filter-options {
  display: flex;
  flex-direction: column;
}

.filter-options :deep(.el-checkbox-group),
.filter-options :deep(.el-radio-group) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.filter-options :deep(.el-checkbox),
.filter-options :deep(.el-radio) {
  margin-right: 0;
  margin-left: 0;
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background 0.2s;
  width: 100%;
  box-sizing: border-box;
}

.filter-options :deep(.el-checkbox:hover),
.filter-options :deep(.el-radio:hover) {
  background: #f5f7fa;
}

.filter-options :deep(.el-checkbox.is-checked),
.filter-options :deep(.el-radio.is-checked) {
  background: #ecf5ff;
}

.filter-options :deep(.el-radio__label),
.filter-options :deep(.el-checkbox__label) {
  padding-left: 8px;
}

.filter-select {
  width: 100%;
}

.filter-select :deep(.el-select__wrapper) {
  border-radius: 6px;
  text-align: left;
}

.filter-options :deep(.el-checkbox__input),
.filter-options :deep(.el-radio__input) {
  margin-left: 0;
}

.filter-actions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e4e7ed;
}

.filter-actions :deep(.el-button) {
  width: 100%;
  border-radius: 6px;
}

@media (max-width: 768px) {
  .filter-sidebar {
    width: 240px;
  }
}
</style>
