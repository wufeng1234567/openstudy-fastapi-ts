<template>
  <div class="card-option" @click="emit('select')">
    <div class="card-icon" :style="{ background: iconBg }">
      <el-icon :size="32">
        <component :is="icon" />
      </el-icon>
    </div>
    <div class="card-content">
      <h3 class="card-title">{{ title }}</h3>
      <p class="card-desc">{{ description }}</p>
    </div>
    <div class="card-arrow">
      <el-icon>
        <ArrowRight />
      </el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'

defineProps({
  title: String,
  description: String,
  icon: Object,
  iconBg: {
    type: String,
    default: '#f0f7ff'
  }
})

const emit = defineEmits(['select'])
</script>

<style scoped lang="scss">
:root {
  --primary-50: #eef2ff;
  --primary-100: #e0e7ff;
  --primary-500: #6366f1;
  --primary-600: #4f46e5;
  --primary-700: #4338ca;
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-400: #9ca3af;
  --gray-500: #6b7280;
  --gray-600: #4b5563;
  --gray-700: #374151;
  --gray-900: #111827;
}

.card-option {
  display: flex;
  align-items: center;
  padding: 28px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--gray-200);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    border-color: #d1d5db;

    .card-icon {
      transform: scale(1.05);
    }

    .card-arrow {
      transform: translateX(4px);
      color: #6b7280;
    }
  }

  .card-icon {
    width: 64px;
    height: 64px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    margin-right: 20px;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .card-content {
    flex: 1;

    .card-title {
      font-size: 18px;
      font-weight: 600;
      color: #1f2937;
      margin: 0 0 8px 0;
    }

    .card-desc {
      font-size: 14px;
      color: #6b7280;
      margin: 0;
    }
  }

  .card-arrow {
    color: #9ca3af;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
}
</style>