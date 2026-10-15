<template>
  <div class="loading-dots" :class="size">
    <span class="dots">
      <span class="dot dot-1"></span>
      <span class="dot dot-2"></span>
      <span class="dot dot-3"></span>
    </span>
    <span v-if="label" class="loading-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * 通用「三点来回抖动」等待组件
 * 全站共用：AI 思考中 / 深度思考中 / 加载中等
 */
defineProps({
  size: {
    type: String,
    default: 'medium',
    validator: (v: string) => ['small', 'medium', 'large'].includes(v)
  },
  /** 右侧可选文案，如「深度思考中」 */
  label: {
    type: String,
    default: ''
  }
})
</script>

<style scoped lang="scss">
.loading-dots {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  vertical-align: middle;

  .dots {
    display: inline-flex;
    align-items: flex-end;
    gap: 4px;
  }

  .dot {
    display: inline-block;
    background-color: #909399;
    border-radius: 50%;
    /* 三个点依次上下抖动 */
    animation: dots-bounce 1.1s infinite ease-in-out both;
  }

  .dot-1 {
    animation-delay: 0s;
  }

  .dot-2 {
    animation-delay: 0.15s;
  }

  .dot-3 {
    animation-delay: 0.3s;
  }

  .loading-label {
    font-size: 12px;
    color: #6b7280;
    white-space: nowrap;
    animation: label-fade 1.6s ease-in-out infinite;
  }

  &.small {
    .dot {
      width: 4px;
      height: 4px;
    }
  }

  &.medium {
    .dot {
      width: 6px;
      height: 6px;
    }
  }

  &.large {
    .dot {
      width: 8px;
      height: 8px;
    }

    .loading-label {
      font-size: 13px;
    }
  }
}

@keyframes dots-bounce {
  0%,
  70%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }

  35% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

@keyframes label-fade {
  0%,
  100% {
    opacity: 0.65;
  }

  50% {
    opacity: 1;
  }
}
</style>
