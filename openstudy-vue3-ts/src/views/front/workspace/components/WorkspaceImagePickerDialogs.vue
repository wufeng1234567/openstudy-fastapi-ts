<template>
  <el-dialog v-model="questionPickerVisible" title="插入题目解析" width="820px" append-to-body>
    <div class="kbp-question-picker">
      <div class="kbp-question-picker__toolbar">
        <el-input v-model="questionKeyword" clearable placeholder="搜索题目题干" @keyup.enter="api.loadQuestionPicker(1)" />
        <el-select v-model="questionBankFilter" clearable filterable placeholder="全部题库"
          class="kbp-question-picker__bank" @change="api.loadQuestionPicker(1)">
          <el-option v-for="bank in questionBanks" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
        </el-select>
        <el-button type="primary" @click="api.loadQuestionPicker(1)">搜索</el-button>
        <span class="kbp-question-picker__image">
          当前图片：{{ questionPickerImage?.docName }} · 图 {{ questionPickerImage?.seq }}
        </span>
      </div>
      <p class="kbp-question-picker__hint">只显示你创建的题库中的题目，可按题库筛选，确保有编辑权限。</p>
      <el-table :data="questionRows" v-loading="questionPickerLoading" max-height="420" size="small">
        <el-table-column label="题目" min-width="360">
          <template #default="{ row }">
            <span class="kbp-question-picker__text">{{ String(row.questionText || row.content || '未命名题目').slice(0, 100) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所属题库" width="160">
          <template #default="{ row }"><span class="kbp-question-picker__bank-name">{{ row.bankName || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="题型" width="90">
          <template #default="{ row }">{{ row.questionTypeText || row.questionType || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" :loading="questionInsertingId === row.id"
              @click="api.insertImageIntoQuestion(row)">插入解析</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="questionPage" :page-size="questionPageSize"
        :total="questionTotal" layout="prev, pager, next" small @current-change="api.loadQuestionPicker" />
    </div>
  </el-dialog>

  <el-dialog v-model="notePickerVisible" title="加入笔记" width="820px" append-to-body>
    <div class="kbp-question-picker">
      <div class="kbp-question-picker__toolbar">
        <el-input v-model="noteKeyword" clearable placeholder="搜索笔记标题" @keyup.enter="api.loadNotePicker(1)" />
        <el-button type="primary" @click="api.loadNotePicker(1)">搜索</el-button>
        <span class="kbp-question-picker__image">
          当前图片：{{ notePickerImage?.docName }} · 图 {{ notePickerImage?.seq }}
        </span>
      </div>
      <el-table :data="noteRows" v-loading="notePickerLoading" max-height="420" size="small">
        <el-table-column label="笔记" min-width="420">
          <template #default="{ row }">
            <span class="kbp-question-picker__text">{{ String(row.title || row.noteTitle || '未命名笔记').slice(0, 100) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" :loading="noteInsertingId === row.id"
              @click="api.insertImageIntoNote(row)">加入笔记</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="notePage" :page-size="notePageSize"
        :total="noteTotal" layout="prev, pager, next" small @current-change="api.loadNotePicker" />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
const questionPickerVisible = defineModel<boolean>('questionPickerVisible', { required: true })
const questionKeyword = defineModel<string>('questionKeyword', { required: true })
const questionBankFilter = defineModel<any>('questionBankFilter', { required: true })
const questionPage = defineModel<number>('questionPage', { required: true })
const notePickerVisible = defineModel<boolean>('notePickerVisible', { required: true })
const noteKeyword = defineModel<string>('noteKeyword', { required: true })
const notePage = defineModel<number>('notePage', { required: true })

defineProps<{
  questionBanks: any[]
  questionPickerImage: any
  questionRows: any[]
  questionPickerLoading: boolean
  questionInsertingId: number
  questionTotal: number
  notePickerImage: any
  noteRows: any[]
  notePickerLoading: boolean
  noteInsertingId: number
  noteTotal: number
  questionPageSize: number
  notePageSize: number
  api: {
    loadQuestionPicker: (page?: number) => void
    insertImageIntoQuestion: (row: any) => void
    loadNotePicker: (page?: number) => void
    insertImageIntoNote: (row: any) => void
  }
}>()
</script>
