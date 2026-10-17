<template>
  <el-dialog
    v-model="visible"
    title="导入题目到题库"
    width="520px"
    append-to-body
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 已有题库时，显示快捷导入选项 -->
    <div v-if="hasExistingBank" class="existing-bank-section">
      <div class="section-label">快捷导入</div>
      <div class="existing-bank-card" @click="handleImportToExisting">
        <div class="bank-info">
          <el-icon class="bank-icon"><FolderOpened /></el-icon>
          <div class="bank-details">
            <div class="bank-name">{{ props.bankName }}</div>
            <div class="bank-subject" v-if="props.bankSubject">{{ props.bankSubject }}</div>
          </div>
        </div>
        <el-button type="primary" size="small">
          导入到此题库
        </el-button>
      </div>

      <div class="divider">
        <span>或者创建新题库</span>
      </div>
    </div>

    <!-- 新建题库表单 -->
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="题库名称" prop="bankName">
        <el-input
          v-model="form.bankName"
          placeholder="请输入题库名称"
          maxlength="50"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="科目分类" prop="subject">
        <el-select
          v-model="form.subject"
          placeholder="选择或输入科目"
          filterable
          allow-create
          style="width: 100%"
        >
          <el-option label="Java" value="Java" />
          <el-option label="Python" value="Python" />
          <el-option label="前端开发" value="前端开发" />
          <el-option label="数据库" value="数据库" />
          <el-option label="算法" value="算法" />
          <el-option label="数学" value="数学" />
          <el-option label="英语" value="英语" />
          <el-option label="软件工程" value="软件工程" />
        </el-select>
      </el-form-item>
      <el-form-item label="题库描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="简单介绍一下这个题库（选填）"
          maxlength="200"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="是否公开">
        <el-radio-group v-model="form.isPublic">
          <el-radio :value="0">公开</el-radio>
          <el-radio :value="1">私有</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="primary" @click="handleCreateAndImport" :loading="loading">
          创建新题库并导入
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import { createQuestionBankWithReturn } from '@/api/questionBank/questionBank'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  bankId: {
    type: [Number, String],
    default: null
  },
  bankName: {
    type: String,
    default: ''
  },
  bankSubject: {
    type: String,
    default: ''
  },
  questionCount: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const visible = ref(false)
const loading = ref(false)
const formRef = ref(null)

// 是否已有题库
const hasExistingBank = computed(() => !!props.bankId && !!props.bankName)

const form = reactive({
  bankName: '',
  subject: '',
  description: '',
  isPublic: 0
})

const rules = {
  bankName: [
    { required: true, message: '请输入题库名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  subject: [
    { required: true, message: '请选择或输入科目', trigger: 'change' }
  ]
}

// 监听显示状态
watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    // 初始化表单数据（用于创建新题库）
    form.bankName = ''
    form.subject = props.bankSubject || ''
    form.description = ''
    form.isPublic = 0
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const handleClose = () => {
  formRef.value?.resetFields()
}

const handleCancel = () => {
  visible.value = false
}

// 导入到已有题库
const handleImportToExisting = () => {
  console.log('[BankInfoDialog] Import to existing bank:', props.bankId)
  emit('confirm', {
    bankId: props.bankId,
    bankName: props.bankName,
    subject: props.bankSubject,
    description: '',
    isPublic: 0,
    isNew: false
  })
  visible.value = false
}

// 创建新题库并导入
const handleCreateAndImport = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const createData = {
      bankName: form.bankName,
      subject: form.subject,
      description: form.description,
      isPublic: form.isPublic,
      status: '0'
    }
    const res = await createQuestionBankWithReturn(createData)
    if (res.code === 200 && res.data) {
      ElMessage.success('题库创建成功')
      emit('confirm', {
        bankId: res.data.id,
        bankName: form.bankName,
        subject: form.subject,
        description: form.description,
        isPublic: form.isPublic,
        isNew: true
      })
      visible.value = false
    } else {
      throw new Error(res.msg || '创建题库失败')
    }
  } catch (error) {
    ElMessage.error(error.message || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.existing-bank-section {
  margin-bottom: 20px;
}

.section-label {
  font-size: 14px;
  color: var(--os-text-2);
  margin-bottom: 12px;
}

.existing-bank-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
}

.existing-bank-card:hover {
  background: #e1f3d8;
  border-color: #b3e19d;
}

.bank-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bank-icon {
  font-size: 24px;
  color: #67c23a;
}

.bank-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bank-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.bank-subject {
  font-size: 12px;
  color: var(--os-text-3);
}

.divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
  color: var(--os-text-3);
  font-size: 13px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e4e7ed;
}

.divider span {
  padding: 0 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
