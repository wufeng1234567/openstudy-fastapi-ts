<!-- src/components/MyQuestion/QuestionHeader.vue -->
<template>
  <PageHeader :title="title" :total="total" :item-name="itemName" placeholder="搜索题目内容" :model-value="searchKeyword"
    :show-filter="showFilter" :filter-open="filterOpen" :filter-active="filterActive" @search="handleSearch"
    @refresh="handleRefresh" @toggle-filter="emit('toggle-filter')" @update:model-value="handleUpdate" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PageHeader from '@/components/PageHeader/index.vue'

const props = defineProps({
  title: String,
  total: Number,
  searchKeyword: String,
  questionType: {
    type: String,
    default: 'favorite'
  },
  showFilter: {
    type: Boolean,
    default: false
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

const emit = defineEmits(['search', 'refresh', 'update:searchKeyword', 'toggle-filter'])

const itemName = computed(() => {
  const map = { favorite: '收藏题目', wrong: '错题', marked: '斩题' }
  return map[props.questionType] || '题目'
})

const handleSearch = (keyword) => {
  emit('search', keyword)
}

const handleUpdate = (keyword) => {
  emit('update:searchKeyword', keyword)
}

const handleRefresh = () => emit('refresh')
</script>
<style scoped>
:deep(.search-area) {
  margin-bottom: 20px !important;
}
</style>
