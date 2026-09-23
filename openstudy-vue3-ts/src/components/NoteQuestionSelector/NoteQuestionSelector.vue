<template>
  <div class="note-question-selector">
    <label v-if="showLabel" class="sidebar-label">关联题目</label>

    <!-- 已关联题目列表 -->
    <div v-if="linkedQuestions.length > 0" class="linked-questions">
      <el-tag v-for="q in linkedQuestions" :key="q.id" size="small" closable @close="unlinkQuestion(q.id)">
        {{ truncate(getQuestionText(q), 20) }}
      </el-tag>
    </div>

    <!-- 添加按钮 -->
    <el-button text size="small" class="add-btn" @click="showDialog = true">
      + 添加关联题目
    </el-button>

    <!-- 题目选择弹窗 -->
    <el-dialog v-model="showDialog" title="选择关联题目" width="700px" append-to-body>
      <div class="dialog-content">
        <!-- 题库选择 + 搜索 -->
        <div class="dialog-toolbar">
          <el-select v-model="selectedBankId" placeholder="选择题库" @change="onBankChange" class="bank-select">
            <el-option v-for="bank in bankList" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
          </el-select>

          <el-input v-model="searchKeyword" placeholder="搜索题目" class="search-input" clearable
            @keyup.enter="loadQuestions" />
        </div>

        <!-- 题目列表 -->
        <el-table :data="questionList" v-loading="loading" style="margin-top: 12px" max-height="400" size="small">
          <el-table-column label="题目" min-width="300">
            <template #default="{ row }">
              <span class="q-text">{{ truncate(getQuestionText(row), 50) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="题型" width="90">
            <template #default="{ row }">
              {{ getQuestionTypeText(row.questionType) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" :class="isLinked(row.id) ? 'unlink-btn' : 'link-btn'"
                @click="toggleLink(row)">
                {{ isLinked(row.id) ? '取消' : '关联' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next"
          @current-change="loadQuestions" class="pager" small />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listQuestionMain } from '@/api/questionMain/questionMain'
import {
  getNoteQuestionsByNoteId,
  addNoteQuestion,
  deleteNoteQuestion
} from '@/api/noteQuestion/noteQuestion'
import { getQuestionTypeText, getPlainText } from '@/utils/questionUtils'
import useUserStore from '@/store/modules/user'

const props = defineProps({
  noteId: { type: [Number, String], default: null },
  bankList: { type: Array as () => any[], default: () => [] },
  /* 是否渲染自带标题：宿主已提供同名 label 时置 false，避免出现两个「关联题目」 */
  showLabel: { type: Boolean, default: true }
})

const emit = defineEmits(['change'])

const userStore = useUserStore()

const linkedQuestions = ref<any[]>([])
const showDialog = ref(false)
const selectedBankId = ref<any>(null)
const searchKeyword = ref('')
const questionList = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const total = ref(0)

// 截断文本
const truncate = (text: string, len: number) => {
  if (!text) return ''
  const str = String(text)
  return str.length > len ? str.slice(0, len) + '...' : str
}

// 获取题目展示文本(兼容 questionText / content / questionContent)
const getQuestionText = (q: any) => {
  if (!q) return ''
  const raw = q.questionText || q.content || q.questionContent || ''
  return getPlainText(raw)
}

// 是否已关联
const isLinked = (qid: any) => {
  return linkedQuestions.value.some(q => q.id === qid)
}

// 加载已关联题目
const loadLinkedQuestions = async () => {
  if (!props.noteId) {
    linkedQuestions.value = []
    return
  }
  try {
    const res = await getNoteQuestionsByNoteId(props.noteId)
    if (res.code === 200 && Array.isArray(res.data)) {
      linkedQuestions.value = res.data
    } else {
      linkedQuestions.value = []
    }
  } catch (e) {
    console.error('加载关联题目失败:', e)
    linkedQuestions.value = []
  }
}

// 加载题目列表(从题库中搜索)
const loadQuestions = async () => {
  loading.value = true
  try {
    const params: any = {
      pageNum: page.value,
      pageSize,
      status: 0
    }
    if (selectedBankId.value) params.bankId = selectedBankId.value
    if (searchKeyword.value) params.questionText = searchKeyword.value
    const res = await listQuestionMain(params)
    questionList.value = res.rows || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载题目列表失败:', e)
    questionList.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// 题库切换
const onBankChange = () => {
  page.value = 1
  loadQuestions()
}

// 切换关联状态
const toggleLink = async (row: any) => {
  if (!props.noteId) {
    ElMessage.warning('请先保存笔记')
    return
  }
  if (isLinked(row.id)) {
    await unlinkQuestion(row.id, true)
  } else {
    try {
      const res = await addNoteQuestion({
        noteId: props.noteId,
        questionId: row.id,
        questionBankId: selectedBankId.value || row.bankId,
        userId: userStore.id
      })
      if (res.code === 200) {
        linkedQuestions.value.push(row)
        emit('change', linkedQuestions.value)
        ElMessage.success('关联成功')
      } else {
        ElMessage.error(res.msg || '关联失败')
      }
    } catch (e) {
      console.error('关联失败:', e)
      ElMessage.error('关联失败')
    }
  }
}

// 取消关联
const unlinkQuestion = async (qid: any, silent = false) => {
  if (!props.noteId) return
  try {
    const res = await deleteNoteQuestion(props.noteId, qid)
    if (res.code === 200) {
      linkedQuestions.value = linkedQuestions.value.filter(q => q.id !== qid)
      emit('change', linkedQuestions.value)
      if (!silent) ElMessage.success('已取消关联')
    } else {
      ElMessage.error(res.msg || '取消关联失败')
    }
  } catch (e) {
    console.error('取消关联失败:', e)
    ElMessage.error('取消关联失败')
  }
}

// 弹窗打开时加载题目
watch(showDialog, (v) => {
  if (v) {
    // 默认选中第一个题库
    if (!selectedBankId.value && props.bankList.length > 0) {
      selectedBankId.value = props.bankList[0].bankId ?? props.bankList[0].id
    }
    page.value = 1
    loadQuestions()
  }
})

// noteId 变化时重新加载
watch(() => props.noteId, () => {
  loadLinkedQuestions()
}, { immediate: true })

// 暴露给父组件
defineExpose({
  loadLinkedQuestions,
  getLinkedQuestionIds: () => linkedQuestions.value.map(q => q.id)
})
</script>

<style lang="scss" scoped>
.note-question-selector {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .sidebar-label {
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .linked-questions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed #e5e7eb;

    :deep(.el-tag) {
      background: #e5e7eb;
      border-color: #d1d5db;
      color: #4b5563;
      border-radius: 4px;
    }
  }

  .add-btn {
    align-self: flex-start;
    color: #6b7280;
    padding: 2px 0;

    &:hover {
      color: #4b5563;
    }
  }
}

.dialog-content {
  .dialog-toolbar {
    display: flex;
    gap: 10px;
    align-items: center;

    .bank-select {
      width: 200px;
    }

    .search-input {
      width: 220px;
    }
  }

  .q-text {
    color: #1f2937;
    line-height: 1.5;
  }

  .pager {
    margin-top: 12px;
    justify-content: center;
  }

  .link-btn {
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #4b5563;
    border-radius: 6px;

    &:hover {
      border-color: #d1d5db;
      color: #1f2937;
    }
  }

  .unlink-btn {
    background: #fef2f2;
    border: 1px solid #e5d0d0;
    color: #b45353;
    border-radius: 6px;

    &:hover {
      background: #fee2e2;
    }
  }
}
</style>
