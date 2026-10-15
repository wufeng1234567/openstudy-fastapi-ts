<!-- src/components/MyQuestion/QuestionList.vue -->
<template>
  <div class="question-list-container">
    <el-row :gutter="20">
      <el-col 
        v-for="item in questions" 
        :key="getItemKey(item)" 
        :xs="24" 
        :sm="12" 
        :md="12" 
        :lg="8" 
        class="question-card-col"
      >
        <QuestionCard
          :question="item"
          :question-type="questionType"
          :show-star="showStar"
          :show-favorite-status="showFavoriteStatus"
          :show-collect-actions="showCollectActions"
          :show-study-stats="showStudyStats"
          :uncollect-loading="uncollectLoading[getItemKey(item)]"
          @view-detail="$emit('view-detail', item)"
          @toggle-star="$emit('toggle-star', item)"
          @uncollect="$emit('uncollect', item)"
        />
      </el-col>
    </el-row>
    
    <!-- 分页 -->
    <div v-if="showPagination" class="pagination-section">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 96]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="pagination.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import QuestionCard from './QuestionCard.vue'

const props = defineProps({
  questions: Array,
  questionType: String,
  showStar: Boolean,
  showFavoriteStatus: Boolean,
  showCollectActions: Boolean,
  showStudyStats: Boolean,
  uncollectLoading: Object,
  pagination: {
    type: Object,
    default: () => ({
      currentPage: 1,
      pageSize: 12,
      total: 0
    })
  }
})

const emit = defineEmits(['view-detail', 'toggle-star', 'uncollect', 'page-change'])

const currentPage = ref(props.pagination.currentPage || 1)
const pageSize = ref(props.pagination.pageSize || 12)

const showPagination = computed(() => {
  return props.pagination.total > props.pagination.pageSize
})

const getItemKey = (item) => {
  return item.favoriteId || item.wrongId || item.markedId || item.bankId
}

const handleSizeChange = (size) => {
  pageSize.value = size
  emit('page-change', {
    currentPage: currentPage.value,
    pageSize: size
  })
}

const handleCurrentChange = (page) => {
  currentPage.value = page
  emit('page-change', {
    currentPage: page,
    pageSize: pageSize.value
  })
}
</script>

<style scoped>
.question-list-container {
  .pagination-section {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #e4e7ed;
    display: flex;
    justify-content: center;
  }
}
</style>