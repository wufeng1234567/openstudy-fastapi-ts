<template>
  <el-tooltip :content="tooltip" placement="top" :show-after="150">
    <button type="button" class="ai-thinking-toggle" :class="{ 'is-on': modelValue, 'is-small': size === 'small' }"
      :disabled="disabled" @click="onClick">
      <!-- 原子轨道图标（三椭圆交叉 + 中心点） -->
      <svg class="atom-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="12" cy="12" rx="9.6" ry="4.1" stroke="currentColor" stroke-width="1.5" />
        <ellipse cx="12" cy="12" rx="9.6" ry="4.1" stroke="currentColor" stroke-width="1.5"
          transform="rotate(60 12 12)" />
        <ellipse cx="12" cy="12" rx="9.6" ry="4.1" stroke="currentColor" stroke-width="1.5"
          transform="rotate(120 12 12)" />
        <circle cx="12" cy="12" r="1.6" fill="currentColor" />
      </svg>
    </button>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 通用「深度思考」开关（纯图标，靠颜色区分状态）
 * 全站共用：助手对话 / 题目解析 / AI 出题 等所有用到 AI 的地方
 */
const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  /** small = 28×28，用于与 size="small" 的下拉框并排；默认 36×36 */
  size: {
    type: String,
    default: 'default',
    validator: (v: string) => ['default', 'small'].includes(v)
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const tooltip = computed(() => {
  if (props.disabled) return '当前不可切换'
  return props.modelValue
    ? '深度思考已开启：回答更严谨，但会先思考一段时间再输出'
    : '深度思考已关闭：响应更快。开启后模型会先推理再作答'
})

const onClick = () => {
  if (props.disabled) return
  const next = !props.modelValue
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<style scoped lang="scss">
.ai-thinking-toggle {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #9ca3af;
  /* 关闭态：灰色图标，无背景 */
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;

  .atom-icon {
    width: 20px;
    height: 20px;
    display: block;
  }

  &:hover:not(:disabled) {
    background: #eef1f5;
    color: #6b7280;
  }

  &:active:not(:disabled) {
    transform: scale(0.94);
  }

  /* 开启态：实心蓝底 + 白色图标 —— 只用颜色区分，不放文字 */
  &.is-on {
    background: #409eff;
    color: #fff;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.35);

    &:hover:not(:disabled) {
      background: #66b1ff;
      color: #fff;
    }

    .atom-icon {
      animation: atom-spin 8s linear infinite;
    }
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  /* 小尺寸：与 size="small" 的下拉框（28px）等高并排 */
  &.is-small {
    width: 28px;
    height: 28px;
    border-radius: 7px;

    .atom-icon {
      width: 16px;
      height: 16px;
    }
  }
}

/* 开启后原子轨道缓慢旋转，暗示“推理模式” */
@keyframes atom-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
