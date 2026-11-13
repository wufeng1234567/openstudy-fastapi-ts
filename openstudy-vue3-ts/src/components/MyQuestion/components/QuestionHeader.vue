<!-- src/components/MyQuestion/QuestionHeader.vue -->
<template>
  <!--
    `hide-title`：被「题目管理」内嵌时上层传进来的 `title` 是空串，
    此时整行标题（标题 + 「共 N 个收藏题目」）都不该渲染 ——
    模块名与计数已经由顶栏承担（`我的学习 · 题目管理  6 道题`），
    留一个空 h2 + 计数会变成一行孤零零的「共 6 个收藏题目」。
  -->
  <PageHeader :title="title" :total="total" :item-name="itemName" placeholder="搜索题目内容" :model-value="searchKeyword"
    :hide-title="!title" :show-filter="showFilter" :filter-open="filterOpen" :filter-active="filterActive"
    @search="handleSearch" @refresh="handleRefresh" @toggle-filter="emit('toggle-filter')"
    @update:model-value="handleUpdate" />
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
