<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="100px">
      <el-form-item label="笔记标题" prop="title">
        <el-input
          v-model="queryParams.title"
          placeholder="请输入笔记标题"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="所属用户ID" prop="userId">
        <el-input
          v-model="queryParams.userId"
          placeholder="请输入用户ID"
          clearable
          style="width: 120px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="所属分类ID" prop="categoryId">
        <el-input
          v-model="queryParams.categoryId"
          placeholder="请输入分类ID"
          clearable
          style="width: 120px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="是否公开" prop="isPublic">
        <el-select
          v-model="queryParams.isPublic"
          placeholder="公开状态"
          clearable
          style="width: 120px"
        >
          <el-option label="私有" :value="0" />
          <el-option label="公开" :value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="笔记状态" prop="status">
        <el-select
          v-model="queryParams.status"
          placeholder="笔记状态"
          clearable
          style="width: 120px"
        >
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
          <el-option label="已归档" value="archived" />
        </el-select>
      </el-form-item>
      <el-form-item label="标签" prop="tags">
        <el-input
          v-model="queryParams.tags"
          placeholder="请输入标签"
          clearable
          style="width: 150px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Plus"
          @click="handleAdd"
          v-hasPermi="['notes:note:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['notes:note:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['notes:note:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['notes:note:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="noteList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="ID" align="center" prop="id" width="80" />
      <el-table-column label="标题" align="center" prop="title" show-overflow-tooltip />
      <el-table-column label="用户ID" align="center" prop="userId" width="100" />
      <el-table-column label="分类ID" align="center" prop="categoryId" width="100" />
      <el-table-column label="内容预览" align="center" prop="markdownContent" min-width="200">
        <template #default="scope">
          <el-tooltip
            v-if="scope.row.markdownContent"
            :content="scope.row.markdownContent"
            placement="top"
            raw-content
          >
            <span class="content-preview">{{ truncateText(scope.row.markdownContent, 60) }}</span>
          </el-tooltip>
          <span v-else class="text-gray">--</span>
        </template>
      </el-table-column>
      <el-table-column label="字数" align="center" prop="wordCount" width="80" />
      <el-table-column label="标签" align="center" prop="tags" width="150">
        <template #default="scope">
          <div v-if="scope.row.tags && scope.row.tags.length > 0">
            <el-tag
              v-for="(tag, index) in formatTags(scope.row.tags)"
              :key="index"
              size="small"
              style="margin-right: 4px; margin-bottom: 4px;"
            >
              {{ tag }}
            </el-tag>
          </div>
          <span v-else class="text-gray">--</span>
        </template>
      </el-table-column>
      <el-table-column label="公开状态" align="center" prop="isPublic" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.isPublic === 1 ? 'success' : 'info'">
            {{ scope.row.isPublic === 1 ? '公开' : '私有' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="笔记状态" align="center" prop="status" width="100">
        <template #default="scope">
          <el-tag :type="getStatusTagType(scope.row.status)">
            {{ getStatusText(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="排序" align="center" prop="sortOrder" width="80" />
      <el-table-column label="创建时间" align="center" prop="createTime" width="160">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="160">
        <template #default="scope">
          <el-tooltip content="修改" placement="top">
            <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['notes:note:edit']"></el-button>
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['notes:note:remove']"></el-button>
          </el-tooltip>
          <el-tooltip content="发布" placement="top" v-if="scope.row.status === 'draft'">
            <el-button link type="success" icon="CircleCheck" @click="handlePublish(scope.row)" v-hasPermi="['notes:note:edit']"></el-button>
          </el-tooltip>
          <el-tooltip content="归档" placement="top" v-if="scope.row.status === 'published'">
            <el-button link type="warning" icon="Folder" @click="handleArchive(scope.row)" v-hasPermi="['notes:note:edit']"></el-button>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
    
    <pagination
      v-show="total>0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <!-- 添加或修改用户笔记对话框 -->
    <el-dialog :title="title" v-model="open" width="1200px" append-to-body>
      <div class="note-editor-dialog">
        <el-form ref="noteRef" :model="form" :rules="rules" label-width="120px">
          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item label="笔记标题" prop="title" class="title-input">
                <el-input 
                  v-model="form.title" 
                  placeholder="请输入笔记标题" 
                  size="large"
                  @input="updateFilename"
                />
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="所属用户ID" prop="userId">
                <el-input v-model="form.userId" placeholder="请输入所属用户ID" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="所属分类ID" prop="categoryId">
                <el-input v-model="form.categoryId" placeholder="请输入所属分类ID" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="原始文件名" prop="filename">
                <el-input v-model="form.filename" placeholder="请输入原始文件名" />
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="标签">
                <el-select
                  v-model="form.tags"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  placeholder="请输入或选择标签"
                  style="width: 100%"
                >
                  <el-option
                    v-for="tag in availableTags"
                    :key="tag"
                    :label="tag"
                    :value="tag"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="是否公开" prop="isPublic">
                <el-select v-model="form.isPublic" placeholder="请选择" style="width: 100%">
                  <el-option label="私有" :value="0" />
                  <el-option label="公开" :value="1" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="笔记状态" prop="status">
                <el-select v-model="form.status" placeholder="请选择" style="width: 100%">
                  <el-option label="草稿" value="draft" />
                  <el-option label="已发布" value="published" />
                  <el-option label="已归档" value="archived" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="排序权重" prop="sortOrder">
                <el-input-number 
                  v-model="form.sortOrder" 
                  :min="0" 
                  :max="999" 
                  controls-position="right" 
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="字数统计" prop="wordCount">
                <el-input v-model="form.wordCount" placeholder="自动计算" readonly />
              </el-form-item>
            </el-col>
          </el-row>
          
          <!-- 使用 md-editor-v3 组件 -->
          <el-form-item label="笔记内容" prop="markdownContent">
            <div class="md-editor-container">
              <MdEditor
                v-model="form.markdownContent"
                :preview="editorMode"
                :toolbars="editorToolbars"
                :toolbars-exclude="['github', 'save', '=']"
                language="zh-CN"
                :height="500"
                placeholder="开始编写你的笔记..."
                @on-upload-img="handleUploadImg"
                @on-change="updateWordCount"
              />
            </div>
          </el-form-item>
        </el-form>
      </div>
      
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancel">取 消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitting">
            {{ submitting ? '保存中...' : '确 定' }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Notes' })
import { listNote, getNote, delNote, addNote, updateNote } from "@/api/notes/note"
import { uploadImage } from "@/api/common/common"
import { parseTime } from "@/utils/ruoyi"
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { CircleCheck, Folder } from '@element-plus/icons-vue'

const { proxy } = getCurrentInstance()

const noteList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")

// 新增响应式数据
const submitting = ref(false)

// 编辑器配置
const editorMode = ref('edit') // 'edit' | 'preview' | 'both'
const editorToolbars = ref([
  'bold',
  'underline',
  'italic',
  'strikeThrough',
  'title',
  'sub',
  'sup',
  'quote',
  'unorderedList',
  'orderedList',
  'codeRow',
  'code',
  'link',
  'image',
  'table',
  'revoke',
  'next',
  'save',
  '=',
  'preview',
  'htmlPreview',
  'catalog',
  'github'
])

// 可用标签（从现有笔记中提取）
const availableTags = ref(['学习', '工作', 'Java', 'Vue', '笔记', '计划', '总结', '技术'])

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    categoryId: null,
    title: null,
    tags: null,
    isPublic: null,
    status: null,
  },
  rules: {
    userId: [
      { required: true, message: "所属用户ID不能为空", trigger: "blur" }
    ],
    categoryId: [
      { required: true, message: "所属分类ID不能为空", trigger: "blur" }
    ],
    title: [
      { required: true, message: "笔记标题不能为空", trigger: "blur" },
      { max: 255, message: "标题长度不能超过255个字符", trigger: "blur" }
    ],
    filename: [
      { required: true, message: "原始文件名不能为空", trigger: "blur" },
      { max: 255, message: "文件名长度不能超过255个字符", trigger: "blur" }
    ],
    status: [
      { required: true, message: "笔记状态不能为空", trigger: "change" }
    ]
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询用户笔记列表 */
function getList() {
  loading.value = true
  listNote(queryParams.value).then(response => {
    noteList.value = response.rows || []
    total.value = response.total || 0
    
    // 提取标签数据，更新可用标签列表
    extractTagsFromNotes(noteList.value)
    
    loading.value = false
  }).catch(error => {
    console.error('获取笔记列表失败:', error)
    loading.value = false
  })
}

/** 从笔记中提取标签，更新可用标签列表 */
function extractTagsFromNotes(notes) {
  const tagSet = new Set([...availableTags.value])
  
  notes.forEach(note => {
    if (note.tags) {
      const tags = formatTags(note.tags)
      tags.forEach(tag => {
        if (tag && tag.trim()) {
          tagSet.add(tag.trim())
        }
      })
    }
  })
  
  availableTags.value = Array.from(tagSet).sort()
}

/** 格式化标签显示 */
function formatTags(tags) {
  if (!tags) return []
  
  try {
    if (typeof tags === 'string') {
      // 尝试解析JSON格式
      if (tags.startsWith('[') && tags.endsWith(']')) {
        return JSON.parse(tags)
      } else if (tags.includes(',')) {
        // 逗号分隔格式
        return tags.split(',').map(tag => tag.trim()).filter(tag => tag)
      } else {
        return [tags]
      }
    } else if (Array.isArray(tags)) {
      return tags
    }
  } catch (e) {
    console.error('解析标签失败:', e)
  }
  
  return []
}

/** 获取状态标签类型 */
function getStatusTagType(status) {
  const typeMap = {
    'draft': 'info',
    'published': 'success',
    'archived': 'warning'
  }
  return typeMap[status] || 'info'
}

/** 获取状态文本 */
function getStatusText(status) {
  const textMap = {
    'draft': '草稿',
    'published': '已发布',
    'archived': '已归档'
  }
  return textMap[status] || status
}

// 取消按钮
function cancel() {
  open.value = false
  reset()
}

// 表单重置
function reset() {
  form.value = {
    id: null,
    userId: null,
    categoryId: null,
    title: null,
    filename: null,
    markdownContent: null,
    htmlContent: null,
    wordCount: 0,
    tags: [],
    isPublic: 0,
    status: 'draft',
    sortOrder: 0,
    createTime: null,
    updateTime: null
  }
  editorMode.value = 'edit'
  proxy.resetForm("noteRef")
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef")
  queryParams.value = {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    categoryId: null,
    title: null,
    tags: null,
    isPublic: null,
    status: null,
  }
  handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.id)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  // 设置默认内容
  form.value.markdownContent = '# 新笔记\n\n开始记录你的想法...'
  form.value.status = 'draft'
  open.value = true
  title.value = "添加笔记"
  updateWordCount()
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _id = row.id || ids.value
  getNote(_id).then(response => {
    const noteData = response.data
    
    // 处理标签
    const tags = formatTags(noteData.tags)
    
    form.value = {
      ...noteData,
      tags: tags,
      markdownContent: noteData.markdownContent || noteData.htmlContent || '# 新笔记\n\n开始记录你的想法...'
    }
    
    // 自动生成文件名
    if (!form.value.filename && form.value.title) {
      form.value.filename = form.value.title + '.md'
    }
    
    // 确保状态有值
    if (!form.value.status) {
      form.value.status = 'draft'
    }
    
    open.value = true
    title.value = "修改笔记"
    
    // 更新字数统计
    updateWordCount()
  })
}

/** 发布笔记 */
function handlePublish(row) {
  proxy.$modal.confirm('确认发布该笔记？').then(() => {
    const publishData = {
      id: row.id,
      status: 'published'
    }
    
    updateNote(publishData).then(() => {
      proxy.$modal.msgSuccess("发布成功")
      getList()
    })
  }).catch(() => {})
}

/** 归档笔记 */
function handleArchive(row) {
  proxy.$modal.confirm('确认归档该笔记？').then(() => {
    const archiveData = {
      id: row.id,
      status: 'archived'
    }
    
    updateNote(archiveData).then(() => {
      proxy.$modal.msgSuccess("归档成功")
      getList()
    })
  }).catch(() => {})
}

/** 提交按钮 */
async function submitForm() {
  try {
    await proxy.$refs["noteRef"].validate()
    
    submitting.value = true
    
    // 准备提交的数据
    const submitData = { ...form.value }
    
    // 处理标签
    if (Array.isArray(submitData.tags) && submitData.tags.length > 0) {
      submitData.tags = JSON.stringify(submitData.tags)
    } else {
      submitData.tags = null
    }
    
    // 自动生成文件名
    if (!submitData.filename && submitData.title) {
      submitData.filename = submitData.title + '.md'
    }
    
    // 自动计算字数
    if (submitData.markdownContent) {
      const text = submitData.markdownContent.replace(/\s+/g, '')
      submitData.wordCount = text.length
    }
    
    if (submitData.id != null) {
      await updateNote(submitData)
      proxy.$modal.msgSuccess("修改成功")
    } else {
      await addNote(submitData)
      proxy.$modal.msgSuccess("新增成功")
    }
    
    open.value = false
    getList()
    
  } catch (error) {
    if (error instanceof Error) {
      console.error('保存失败:', error)
    }
    // 验证失败不提示
  } finally {
    submitting.value = false
  }
}

/** 删除按钮操作 */
function handleDelete(row) {
  const _ids = row.id || ids.value
  proxy.$modal.confirm('是否确认删除笔记编号为"' + _ids + '"的数据项？').then(function() {
    return delNote(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('notes/note/export', {
    ...queryParams.value
  }, `note_${new Date().getTime()}.xlsx`)
}

// ========== md-editor-v3 相关函数 ==========

/** 处理图片上传 - 参考NoteEditor的handleUploadImg函数 */
async function handleUploadImg(files, callback) {
  const uploadPromises = files.map(file => {
    const formData = new FormData()
    formData.append('file', file)
    return uploadImage(formData)
  })
  
  try {
    const responses = await Promise.all(uploadPromises)
    const urls = responses
      .filter(res => res.code === 200 && res.url)
      .map(res => {
        let url = res.url
        const baseApi = import.meta.env.VITE_APP_BASE_API || ''
        
        // 如果返回的是相对路径，加上基础API地址
        if (!url.startsWith('http')) {
          url = baseApi + url
        }
        
        // URL编码空格
        return url.replace(/ /g, '%20')
      })
    
    callback(urls)
  } catch (error) {
    console.error('上传图片失败:', error)
    proxy.$modal.msgError('上传失败')
    callback([])
  }
}

/** 更新字数统计 */
function updateWordCount() {
  if (form.value.markdownContent) {
    const text = form.value.markdownContent.replace(/\s+/g, '')
    form.value.wordCount = text.length
  } else {
    form.value.wordCount = 0
  }
}

/** 根据标题更新文件名 */
function updateFilename() {
  if (!form.value.filename && form.value.title) {
    form.value.filename = form.value.title + '.md'
  }
}

/** 截断文本显示 */
function truncateText(text, length) {
  if (!text) return ''
  if (text.length <= length) return text
  return text.substring(0, length) + '...'
}

// 初始化
getList()
</script>

<style scoped>
.note-editor-dialog {
  padding: 10px;
}

.title-input :deep(.el-input__wrapper) {
  font-size: 16px;
  font-weight: 500;
}

.md-editor-container {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
}

.content-preview {
  color: #606266;
  font-size: 12px;
  line-height: 1.4;
}

.text-gray {
  color: #909399;
  font-style: italic;
}

/* 自定义md-editor的样式 */
:deep(.md-editor) {
  border: none !important;
  border-radius: 0 !important;
}

:deep(.md-editor-toolbar) {
  background: #f5f7fa !important;
  border-bottom: 1px solid #e4e7ed !important;
}

:deep(.md-editor-content) {
  background: #fff !important;
}

:deep(.md-editor-preview) {
  background: #f8f9fa !important;
}

:deep(.md-editor-preview-wrapper) {
  padding: 16px !important;
}

:deep(.markdown-body) {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
  font-size: 14px !important;
  line-height: 1.6 !important;
}

:deep(.markdown-body img) {
  max-width: 100% !important;
  height: auto !important;
  border-radius: 6px !important;
  margin: 8px 0 !important;
}
</style>  