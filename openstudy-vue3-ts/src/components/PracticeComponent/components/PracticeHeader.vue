<template>
  <div class="practice-header">
    <el-button size="small" @click="$emit('close')">
      <el-icon>
        <ArrowLeft />
      </el-icon> 返回题库
    </el-button>

    <!-- 核心修改：将标题包裹在 title-container 中 -->
    <div class="header-right">
      <div class="title-container">
        <span class="mode-title">{{ getModeText(mode) }} · {{ bankName }}</span>
      </div>

      <!-- 模拟考试计时器 -->
      <div v-if="mode === 'mock' && formattedTime" class="exam-timer"
        :class="{ 'time-warning': isWarning, 'time-danger': isDanger }">
        <el-icon>
          <Timer />
        </el-icon>
        <span class="timer-text">{{ formattedTime }}</span>
      </div>

      <el-button size="small" @click="$emit('open-settings')" class="settings-btn">
        <el-icon>
          <Setting />
        </el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Setting, Timer } from '@element-plus/icons-vue'

defineProps({
  mode: {
    type: String,
    required: true,
    validator: (val: any) => ['sequential', 'random', 'custom', 'mock'].includes(val)
  },
  bankName: {
    type: String,
    default: '题库'
  },
  formattedTime: {
    type: String,
    default: ''
  },
  isWarning: {
    type: Boolean,
    default: false
  },
  isDanger: {
    type: Boolean,
    default: false
  }
})

defineEmits(['close', 'open-settings'])

function getModeText(mode: string) {
  const modeMap: Record<string, string> = {
    sequential: '顺序练习',
    random: '随机练习',
    // `custom` 这个 key 现在是「错题练习」（2026-10-20 由「自定义练习」改造，见 store）
    custom: '错题练习',
    mock: '模拟考试'
  }
  return modeMap[mode] || '练习模式'
}
</script>

<style scoped>
.practice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* 确保左侧按钮和右侧区域分布在两端 */
  padding: 10px 0;
}

.header-right {
  display: flex;
  align-items: center;
  flex: 1;
  /* 让右侧区域占据剩余的所有空间 */
  /* 移除默认的 justify-content，因为子元素会自行控制位置 */
}

/* 新增：标题容器 */
.title-container {
  flex: 1;
  /* 占据 header-right 中的剩余空间 */
  display: flex;
  justify-content: center;
  /* 水平居中 */
}

.mode-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
}

.exam-timer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: #f3f4f6;
  border-radius: 20px;
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  border: 1px solid #e5e7eb;
}

.exam-timer.time-warning {
  background: #fef3c7;
  border-color: #fcd34d;
  color: #92400e;
}

.exam-timer.time-danger {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
  animation: pulse 1s infinite;
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.7;
  }
}

.settings-btn {
  margin-left: 12px;
  display: inline-flex;
  align-items: center;
}
</style>