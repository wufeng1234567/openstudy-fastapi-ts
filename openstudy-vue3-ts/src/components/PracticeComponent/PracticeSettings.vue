<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="刷题设置"
    width="560px" :close-on-click-modal="false" class="practice-settings-dialog">
    <div class="settings-body">
      <!-- 顶部信息栏 -->
      <div class="bank-info-bar" v-if="store.currentBankName">
        <div class="info-item">
          <el-icon>
            <Collection />
          </el-icon>
          <span>当前题库：{{ store.currentBankName }}</span>
        </div>
        <div class="info-divider"></div>
        <div class="info-item" v-if="selectedModule">
          <span class="info-label">当前选中：</span>
          <span class="info-value">{{ getModuleLabel(selectedModule) }}</span>
        </div>
      </div>

      <!-- 模块切换区 -->
      <div class="settings-section">
        <div class="section-label">选择模块</div>
        <div class="module-tabs">
          <div v-for="mod in moduleList" :key="mod.type" class="module-tab"
            :class="{ active: selectedModule === mod.type }" @click="switchModule(mod.type)">
            <div class="tab-icon" :class="mod.type">
              <el-icon>
                <component :is="mod.icon" />
              </el-icon>
            </div>
            <span class="tab-label">{{ mod.label }}</span>
          </div>
        </div>
      </div>

      <!-- 设置配置区 -->
      <div class="settings-section">
        <div class="section-label">
          模块设置
          <span class="module-hint">{{ getModuleHint(selectedModule) }}</span>
        </div>

        <!-- 每次练习数量 -->
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">每次练习数量</div>
            <div class="setting-desc">本次练习的题目数量</div>
          </div>
          <el-select v-model="localSettings.questionCount" style="width: 120px">
            <el-option :value="5" label="5 题" />
            <el-option :value="10" label="10 题" />
            <el-option :value="20" label="20 题" />
            <el-option :value="50" label="50 题" />
            <el-option value="all" label="全部题库" />
          </el-select>
        </div>

        <!-- 选项乱序 -->
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">选项乱序</div>
            <div class="setting-desc">{{ getShuffleHint(selectedModule) }}</div>
          </div>
          <template v-if="isShuffleFixed(selectedModule)">
            <el-switch :model-value="localSettings.shuffleOptions" disabled />
          </template>
          <template v-else>
            <el-switch v-model="localSettings.shuffleOptions" />
          </template>
        </div>

        <!-- 自动下一题 -- 考试模式固定关闭 -->
        <div class="setting-row"
          :class="{ 'setting-disabled': selectedModule === 'mock' || localSettings.practiceMode === 'exam' }">
          <div class="setting-info">
            <div class="setting-label">自动下一题</div>
            <div class="setting-desc">{{ localSettings.practiceMode === 'exam' ? '考试模式下不支持自动下一题' : '答对后自动跳转到下一题' }}
            </div>
          </div>
          <el-switch v-model="localSettings.autoNextOnCorrect"
            :disabled="selectedModule === 'mock' || localSettings.practiceMode === 'exam'" />
        </div>

        <!-- 只刷错题 -->
        <div class="setting-row" :class="{ 'setting-disabled': selectedModule === 'mock' }"
          v-if="selectedModule !== 'mock'">
          <div class="setting-info">
            <div class="setting-label">只刷错题</div>
            <div class="setting-desc">仅练习已记录的错题，针对性强化</div>
          </div>
          <el-switch v-model="localSettings.onlyWrong" />
        </div>

        <!-- 整体浏览模式 -->
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">整体浏览模式</div>
            <div class="setting-desc">一次性查看所有题目，右侧显示答题卡，支持快速跳转</div>
          </div>
          <el-switch v-model="localSettings.isOverviewMode" />
        </div>

        <!-- 模拟考试时间限制 -->
        <div class="setting-row" v-if="selectedModule === 'mock'">
          <div class="setting-info">
            <div class="setting-label">考试时间限制</div>
            <div class="setting-desc">设置本次模拟考试的答题时间（分钟）</div>
          </div>
          <div class="time-limit-input">
            <el-input-number v-model="localSettings.examTimeLimit" :min="1" :max="43200" controls-position="right" />
            <span class="time-unit">分钟</span>
          </div>
        </div>

        <!-- 练习模式切换 -->
        <div class="setting-row" v-if="selectedModule !== 'mock'">
          <div class="setting-info">
            <div class="setting-label">练习模式</div>
            <div class="setting-desc">刷题模式答完即显示解析，考试模式提交后统一判题</div>
          </div>
          <el-switch :model-value="localSettings.practiceMode === 'exam'" @update:model-value="togglePracticeMode"
            active-text="考试" inactive-text="刷题" inline-prompt />
        </div>

        <!-- 模拟考试模式（只读固定） -->
        <div class="setting-row mode-readonly" v-else>
          <div class="setting-info">
            <div class="setting-label">练习模式</div>
            <div class="setting-desc">模拟考试固定为考试模式</div>
          </div>
          <span class="mode-tag exam">考试模式</span>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button plain @click="handleSave">保存设置</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { Collection, Sort, Refresh, Setting, Clock } from '@element-plus/icons-vue'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  defaultModule: {
    type: String,
    default: 'sequential',
    validator: (val: any) => ['sequential', 'random', 'custom', 'mock'].includes(val)
  }
})

const emit = defineEmits(['update:modelValue', 'save'])

const store = usePracticeSettingsStore()

const moduleList = [
  { type: 'sequential', label: '顺序练习', icon: 'Sort' },
  { type: 'random', label: '随机练习', icon: 'Refresh' },
  { type: 'custom', label: '自定义练习', icon: 'Setting' },
  { type: 'mock', label: '模拟考试', icon: 'Clock' }
]

const selectedModule = ref('sequential')

const localSettings = reactive({
  questionCount: 10 as number | string,
  shuffleOptions: false,
  autoNextOnCorrect: false,
  onlyWrong: false,
  practiceMode: 'practice',
  examTimeLimit: 60,
  isOverviewMode: false
})

function getModuleLabel(type: string) {
  const item = moduleList.find(m => m.type === type)
  return item ? item.label : ''
}

function loadModuleSettings(moduleType: string) {
  const settings = store.getModuleSettings(moduleType)
  localSettings.questionCount = settings.questionCount
  localSettings.shuffleOptions = settings.shuffleOptions
  localSettings.autoNextOnCorrect = settings.autoNextOnCorrect
  localSettings.onlyWrong = settings.onlyWrong ?? false
  localSettings.practiceMode = settings.practiceMode
  localSettings.examTimeLimit = settings.examTimeLimit ?? 60
  localSettings.isOverviewMode = settings.isOverviewMode ?? false
}

function switchModule(type: string) {
  selectedModule.value = type
  loadModuleSettings(type)
}

function isShuffleFixed(moduleType: string) {
  return moduleType === 'sequential' || moduleType === 'random' || moduleType === 'mock'
}

function getShuffleHint(moduleType: string) {
  if (moduleType === 'sequential') return '顺序练习固定顺序，无法更改'
  if (moduleType === 'random') return '随机练习固定乱序，无法更改'
  if (moduleType === 'mock') return '模拟考试固定乱序，无法更改'
  return '打乱每道题的选项顺序'
}

function getModuleHint(moduleType: string) {
  if (moduleType === 'sequential') return '（题数可调，顺序固定）'
  if (moduleType === 'random') return '（题数可调，乱序固定）'
  if (moduleType === 'mock') return '（题数可调，乱序固定，考试模式）'
  return '（全部可调）'
}

function togglePracticeMode(isExam: boolean) {
  localSettings.practiceMode = isExam ? 'exam' : 'practice'
  if (isExam) {
    localSettings.autoNextOnCorrect = false
  }
}

watch(() => props.modelValue, (val) => {
  if (val) {
    selectedModule.value = props.defaultModule
    loadModuleSettings(props.defaultModule)
  }
})

function handleSave() {
  store.saveModuleSettings(selectedModule.value, { ...localSettings } as any)
  emit('save', { moduleType: selectedModule.value, settings: { ...localSettings } })
  emit('update:modelValue', false)
}

function handleCancel() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
.practice-settings-dialog :deep(.el-dialog) {
  border-radius: 16px;
}

.practice-settings-dialog :deep(.el-dialog__header) {
  padding: 20px 24px 0;
}

.practice-settings-dialog :deep(.el-dialog__title) {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.practice-settings-dialog :deep(.el-dialog__body) {
  padding: 16px 24px 24px;
}

.settings-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.bank-info-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #f3f4f6;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  font-size: 13px;
  color: #6b7280;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-divider {
  width: 1px;
  height: 16px;
  background: #d1d5db;
}

.info-label {
  color: #9ca3af;
}

.info-value {
  color: #1f2937;
  font-weight: 600;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}

.module-hint {
  font-size: 12px;
  font-weight: 400;
  color: #9ca3af;
}

.module-tabs {
  display: flex;
  gap: 8px;
}

.module-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 6px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: #fff;
  font-size: 13px;
  color: #6b7280;
}

.module-tab:hover {
  border-color: #d1d5db;
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.module-tab.active {
  border-color: #9ca3af;
  background: #f3f4f6;
  color: #1f2937;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.tab-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.tab-icon.sequential {
  background: #e8f4fd;
  color: #3b82f6;
}

.tab-icon.random {
  background: #fef6e4;
  color: #d97706;
}

.tab-icon.custom {
  background: #f0f0f5;
  color: #6b7280;
}

.tab-icon.mock {
  background: #fde8e8;
  color: #b91c1c;
}

.module-tab.active .tab-icon.sequential {
  background: #dbeafe;
  color: #2563eb;
}

.module-tab.active .tab-icon.random {
  background: #fef3c7;
  color: #b45309;
}

.module-tab.active .tab-icon.custom {
  background: #e5e7eb;
  color: #374151;
}

.module-tab.active .tab-icon.mock {
  background: #fecaca;
  color: #991b1b;
}

.tab-label {
  font-size: 12px;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.setting-row.setting-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
}

.setting-desc {
  font-size: 12px;
  color: #9ca3af;
}

.mode-readonly {
  background: #f8fafc;
  border-style: dashed;
}

.mode-tag {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.mode-tag.practice {
  background: #f3f4f6;
  color: #6b7280;
  border: 1px solid #e5e7eb;
}

.mode-tag.exam {
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/*<!-- 练习模式切换开关颜色与圆角 */
.practice-settings-dialog :deep(.el-switch.is-checked) {
  --el-switch-on-color: #6b9ac9;
}

.practice-settings-dialog :deep(.el-switch__core) {
  border-radius: 12px;
}

.practice-settings-dialog :deep(.el-switch__core .el-switch__action) {
  border-radius: 50%;
}

.time-limit-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time-unit {
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
}
</style>
