<!-- 题库卡片组件 -->
<template>
  <div class="bank-card" @click="$emit('click')">
    <div class="card-cover">
      <el-image :src="imageUrl" fit="cover" class="cover-image" @error="handleImageError">
        <template #error>
          <div class="image-error">
            <el-icon><Picture /></el-icon>
          </div>
        </template>
      </el-image>
      <div v-if="bank.isStarred" class="star-icon" @click.stop="$emit('toggle-star')">
        <el-icon color="#f4c542"><StarFilled /></el-icon>
      </div>
    </div>
    <div class="card-content">
      <div class="bank-name">
        <h3>{{ bank.bankName || '未知题库' }}</h3>
        <el-tag v-if="bank.subject" size="small" type="info">{{ bank.subject }}</el-tag>
      </div>
      <div class="bank-stats">
        <div class="stat-item">
          <el-icon><Document /></el-icon>
          <span>{{ bank.totalQuestions || 0 }} 题</span>
        </div>
      </div>
      <div v-if="bank.description" class="bank-description">
        {{ bank.description }}
      </div>
    </div>
    <div class="card-actions">
      <el-button size="small" @click.stop="$emit('view')">
        <el-icon><View /></el-icon>
        查看详情
      </el-button>
      <slot name="actions" />
      <el-button v-if="showDelete" size="small" type="danger" @click.stop="$emit('delete')" :loading="deleteLoading">
        <el-icon><Delete /></el-icon>
        删除
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import { Picture, StarFilled, Document, View, Delete } from '@element-plus/icons-vue'
import type { QuestionBank } from '@/types'

const props = defineProps({
  bank: { type: Object as PropType<Partial<QuestionBank>>, default: () => ({}) },
  showDelete: { type: Boolean, default: true },
  deleteLoading: { type: Boolean, default: false }
})

defineEmits(['click', 'view', 'delete', 'toggle-star'])

const imageUrl = computed(() => {
  const imagePath = props.bank.coverImage
  if (!imagePath) return ''
  const baseApi = import.meta.env.VITE_APP_BASE_API || ''
  return imagePath.startsWith('http') ? imagePath : `${baseApi}${imagePath}`
})

const handleImageError = () => {
  // 图片加载失败
}
</script>

<style scoped>
.bank-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
  margin-bottom: 20px;
  transition: all 0.3s ease;
  cursor: pointer;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    transform: translateY(-2px);
  }
}

.card-cover {
  height: 140px;
  overflow: hidden;
  background: #f3f4f6;
  position: relative;

  .cover-image {
    width: 100%;
    height: 100%;
  }

  .image-error {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #d1d5db;
    font-size: 32px;
  }

  .star-icon {
    position: absolute;
    top: 8px;
    right: 8px;
    cursor: pointer;
    font-size: 24px;
  }
}

.card-content {
  padding: 12px 16px;
}

.bank-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: #1f2937;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.bank-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;

  .stat-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: #6b7280;
  }
}

.bank-description {
  font-size: 12px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-actions {
  display: flex;
  /* 放不下就换行，避免按钮被卡片 overflow:hidden 裁掉 */
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #f3f4f6;

  .el-button {
    flex: 1 1 auto;
    min-width: max-content;
    margin-left: 0;
    border-radius: 6px;
  }
}
</style>
