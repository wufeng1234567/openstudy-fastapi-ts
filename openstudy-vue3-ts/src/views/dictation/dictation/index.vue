<!-- src/views/dictation/index.vue -->
<template>
  <div class="app-container dictation-container">
    <el-tabs v-model="activeTab" class="dictation-tabs">
      <!-- 单词本管理标签页 -->
      <el-tab-pane label="单词本管理" name="wordBook">
        <div class="tab-content">
          <el-form :model="wordBookQuery" ref="wordBookQueryRef" :inline="true" v-show="showWordBookSearch"
            label-width="85px" class="search-form">
            <el-form-item label="单词本名称" prop="name">
              <el-input v-model="wordBookQuery.name" placeholder="请输入单词本名称" clearable
                @keyup.enter="handleWordBookQuery" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="handleWordBookQuery">搜索</el-button>
              <el-button icon="Refresh" @click="resetWordBookQuery">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="toolbar mb15">
            <el-button type="primary" plain icon="Plus" @click="handleAddWordBook"
              v-hasRole="['common']">新增单词本</el-button>
            <el-button type="success" plain icon="Edit" :disabled="singleWordBook" @click="handleUpdateWordBook"
              v-hasRole="['common']">修改</el-button>
            <el-button type="danger" plain icon="Delete" :disabled="multipleWordBook" @click="handleDeleteWordBook"
              v-hasRole="['common']">删除</el-button>
            <right-toolbar v-model:showSearch="showWordBookSearch" @queryTable="getWordBookList"></right-toolbar>
          </div>

          <el-table v-loading="wordBookLoading" :data="wordBookList" @selection-change="handleWordBookSelectionChange"
            class="data-table">
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="ID" align="center" prop="id" width="80" />
            <el-table-column label="单词本名称" align="center" prop="name" min-width="150" />
            <el-table-column label="描述" align="center" prop="description" min-width="200" show-overflow-tooltip />
            <el-table-column label="创建时间" align="center" prop="createdTime" width="180" />
            <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="150">
              <template #default="scope">
                <el-button link type="primary" icon="Edit" @click="handleUpdateWordBook(scope.row)"
                  v-hasRole="['common']">修改</el-button>
                <el-button link type="primary" icon="Delete" @click="handleDeleteWordBook(scope.row)"
                  v-hasRole="['common']">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination v-show="wordBookTotal > 0" :total="wordBookTotal" v-model:page="wordBookQuery.pageNum"
            v-model:limit="wordBookQuery.pageSize" @pagination="getWordBookList" class="pagination-container" />
        </div>
      </el-tab-pane>

      <!-- 单词录入标签页 -->
      <el-tab-pane label="单词录入" name="word">
        <div class="tab-content">
          <el-form :model="wordQuery" ref="wordQueryRef" :inline="true" v-show="showWordSearch" label-width="80px"
            class="search-form">
            <el-form-item label="所属单词本" prop="wordBookId" label-width="85px">
              <el-select v-model="wordQuery.wordBookId" placeholder="请选择单词本" clearable>
                <el-option v-for="item in wordBookOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="英文单词" prop="english">
              <el-input v-model="wordQuery.english" placeholder="请输入英文单词" clearable
                @keyup.enter="handleWordQuery" />
            </el-form-item>
            <el-form-item label="中文意思" prop="chinese">
              <el-input v-model="wordQuery.chinese" placeholder="请输入中文意思" clearable
                @keyup.enter="handleWordQuery" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="handleWordQuery">搜索</el-button>
              <el-button icon="Refresh" @click="resetWordQuery">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="toolbar mb15">
            <el-button type="primary" plain icon="Plus" @click="handleAddWord"
              v-hasRole="['common']">新增单词</el-button>
            <el-button type="primary" plain icon="Picture" @click="handleScanWord"
              v-hasRole="['common']">单词扫描</el-button>
            <el-button type="success" plain icon="Edit" :disabled="singleWord" @click="handleUpdateWord"
              v-hasRole="['common']">修改</el-button>
            <el-button type="danger" plain icon="Delete" :disabled="multipleWord" @click="handleDeleteWord"
              v-hasRole="['common']">删除</el-button>
            <right-toolbar v-model:showSearch="showWordSearch" @queryTable="getWordList"></right-toolbar>
          </div>

          <el-table v-loading="wordLoading" :data="wordList" @selection-change="handleWordSelectionChange"
            class="data-table" border>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="ID" align="center" prop="id" width="80" />
            <el-table-column label="英文单词" align="center" prop="english" min-width="150" />
            <el-table-column label="中文意思" align="center" prop="chinese" min-width="150" />
            <el-table-column label="音标" align="center" prop="phonetic" min-width="120" />
            <el-table-column label="所属单词本" align="center" prop="wordBookName" min-width="180" />
            <el-table-column label="创建时间" align="center" prop="createdTime" width="180" />
            <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="140">
              <template #default="scope">
                <el-button link type="primary" icon="Edit" @click="handleUpdateWord(scope.row)"
                  v-hasRole="['common']">修改</el-button>
                <el-button link type="primary" icon="Delete" @click="handleDeleteWord(scope.row)"
                  v-hasRole="['common']">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination v-show="wordTotal > 0" :total="wordTotal" v-model:page="wordQuery.pageNum"
            v-model:limit="wordQuery.pageSize" @pagination="getWordList" class="pagination-container" />
        </div>
      </el-tab-pane>

      <!-- 听力练习标签页 -->
      <el-tab-pane label="听力练习" name="dictation">
        <DictationPractice 
          ref="dictationPracticeRef"
          :word-book-options="wordBookOptions"
          @start-dictation="handleStartDictation"
          @stop-dictation="handleStopDictation" />
      </el-tab-pane>
    </el-tabs>

    <!-- 单词本对话框 -->
    <el-dialog :title="wordBookTitle" v-model="wordBookOpen" width="500px" append-to-body>
      <el-form ref="wordBookFormRef" :model="wordBookForm" :rules="wordBookRules" label-width="100px">
        <el-form-item label="单词本名称" prop="name">
          <el-input v-model="wordBookForm.name" placeholder="请输入单词本名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="wordBookForm.description" type="textarea" placeholder="请输入描述" :rows="3" />
        </el-form-item>
        <el-form-item label="设为默认" prop="isDefault">
          <el-switch v-model="wordBookForm.isDefault" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelWordBook">取 消</el-button>
          <el-button type="primary" @click="submitWordBookForm">确 定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 单词对话框 -->
    <el-dialog :title="wordTitle" v-model="wordOpen" width="500px" append-to-body>
      <el-form ref="wordFormRef" :model="wordForm" :rules="wordRules" label-width="100px">
        <el-form-item label="所属单词本" prop="wordBookId">
          <el-select v-model="wordForm.wordBookId" placeholder="请选择单词本">
            <el-option v-for="item in wordBookOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="英文单词" prop="english">
          <el-input v-model="wordForm.english" placeholder="请输入英文单词" />
        </el-form-item>
        <el-form-item label="中文意思" prop="chinese">
          <el-input v-model="wordForm.chinese" placeholder="请输入中文意思" />
        </el-form-item>
        <el-form-item label="音标" prop="phonetic">
          <el-input v-model="wordForm.phonetic" placeholder="请输入音标" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelWord">取 消</el-button>
          <el-button type="primary" @click="submitWordForm">确 定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- OCR扫描对话框 -->
    <!-- OCR扫描对话框 -->
<el-dialog :title="ocrTitle" v-model="ocrOpen" width="800px" append-to-body>
  <div class="ocr-dialog-content">
    <!-- 图片上传区域 -->
    <div class="ocr-upload-area">
      <el-upload
        ref="ocrUploadRef"
        class="upload-demo"
        drag
        :action="uploadFileUrl"
        :headers="headers"
        :on-success="handleOcrImageSuccess"
        :on-error="handleOcrImageError"
        :before-upload="beforeOcrImageUpload"
        :limit="1"
        :show-file-list="false"
      >
        <el-icon class="el-icon--upload">
          <UploadFilled />
        </el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 JPG/PNG/GIF 格式，大小不超过10MB
          </div>
        </template>
      </el-upload>
      
      <!-- 图片预览 -->
      <div class="image-preview" v-if="ocrImageUrl">
        <div class="image-preview-container">
          <div class="preview-header">
            <span class="preview-title">图片预览（支持拖动缩放）</span>
            <div class="preview-actions">
              <el-button-group size="small">
                <el-button @click="zoomImage(0.1)" icon="ZoomIn">放大</el-button>
                <el-button @click="zoomImage(-0.1)" icon="ZoomOut">缩小</el-button>
                <el-button @click="resetImageZoom" icon="Refresh">重置</el-button>
              </el-button-group>
            </div>
          </div>
          
          <div 
            class="draggable-image-preview"
            ref="draggableContainerRef"
            @mousedown="startDrag"
            @mousemove="handleDrag"
            @mouseup="stopDrag"
            @mouseleave="stopDrag"
            @wheel="handleWheel"
            @touchstart="startTouch"
            @touchmove="handleTouch"
            @touchend="stopTouch"
          >
            <div 
              class="image-wrapper"
              :style="{
                transform: `translate(${imagePosition.x}px, ${imagePosition.y}px) scale(${imageScale})`,
                cursor: isDragging ? 'grabbing' : 'grab'
              }"
            >
              <el-image 
                :src="ocrImageUrl" 
                fit="contain" 
                class="ocr-image-preview"
                :preview-src-list="[ocrImageUrl]"
                :initial-index="0"
              >
                <template #placeholder>
                  <div class="image-slot">
                    加载中<span class="dot">...</span>
                  </div>
                </template>
              </el-image>
            </div>
            
            <!-- 缩放控制 -->
            <div class="zoom-controls">
              <el-slider
                v-model="imageScale"
                :min="0.1"
                :max="3"
                :step="0.1"
                style="width: 150px;"
                @change="onScaleChange"
              />
              <span class="zoom-text">{{ Math.round(imageScale * 100) }}%</span>
            </div>
            
            <!-- 拖动提示 -->
            <div class="drag-hint" v-show="!isDragging">
              <el-icon><Promotion /></el-icon>
              <span>拖动查看</span>
            </div>
          </div>
          
          <div class="image-actions mt15">
            <el-button type="danger" size="small" @click="removeOcrImage" icon="Delete">删除图片</el-button>
            <el-button 
              type="primary" 
              size="small" 
              @click="startOcrRecognize" 
              :loading="ocrLoading"
              :disabled="!ocrImageUrl"
            >
              {{ ocrLoading ? '识别中...' : '开始识别' }}
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- OCR识别结果编辑区域 -->
    <div class="ocr-result-area" v-if="ocrWordList.length > 0">
      <div class="result-header">
        <span class="header-title">识别结果（请检查并编辑）</span>
        <div class="header-actions">
          <el-button type="success" size="small" @click="addAllWords" :loading="batchLoading">
            批量添加所有单词
          </el-button>
        </div>
      </div>
      
      <div class="word-list-container">
        <div class="word-item" v-for="(word, index) in ocrWordList" :key="word.id">
          <div class="word-index">{{ index + 1 }}</div>
          <el-input 
            v-model="word.english" 
            placeholder="英文单词" 
            class="english-input"
            clearable
          />
          <el-input 
            v-model="word.chinese" 
            placeholder="中文意思" 
            class="chinese-input"
            clearable
          />
          <el-input 
            v-model="word.phonetic" 
            placeholder="音标（可选）" 
            class="phonetic-input"
            clearable
          />
          <div class="word-actions">
            <el-button 
              type="primary" 
              size="small" 
              @click="addSingleWord(word, index)"
              :loading="word.loading"
            >
              添加
            </el-button>
            <el-button 
              type="danger" 
              size="small" 
              @click="removeWordItem(index)"
            >
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- OCR原始结果 -->
    <div class="ocr-raw-result" v-if="ocrRawText">
      <el-divider>原始识别结果</el-divider>
      <el-input 
        type="textarea" 
        :rows="4" 
        v-model="ocrRawText" 
        readonly
        placeholder="OCR识别结果将显示在这里"
      />
    </div>
  </div>
  
  <template #footer>
    <div class="dialog-footer">
      <el-button @click="cancelOcr">关闭</el-button>
    </div>
  </template>
</el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Dictation' })
import { ref, reactive, computed, toRefs, getCurrentInstance, onMounted, watch, nextTick } from 'vue'
import useUserStore from '@/store/modules/user'
import { listWordBooks, getWordBooks, delWordBooks, addWordBooks, updateWordBooks } from "@/api/wordBooks/wordBooks"
import { listWords, getWords, delWords, addWords, updateWords, batchAddWords } from "@/api/words/words"
import { ocrRecognize } from "@/api/ocr/ocr"
import DictationPractice from "@/components/Dictation/DictationPractice.vue"
import { getToken } from "@/utils/auth"
import { UploadFilled, Promotion, ZoomIn, ZoomOut, Refresh } from '@element-plus/icons-vue'

const { proxy } = getCurrentInstance()
const dictationPracticeRef = ref(null)
const ocrUploadRef = ref(null)
const draggableContainerRef = ref(null)
const userStore = useUserStore()

// 获取当前用户信息
const currentUserId = computed(() => userStore.id)
const currentUserName = computed(() => userStore.name)

// 标签页控制
const activeTab = ref('wordBook')

// 单词本相关数据
const wordBookList = ref([])
const wordBookOpen = ref(false)
const wordBookLoading = ref(true)
const showWordBookSearch = ref(true)
const wordBookIds = ref([])
const singleWordBook = ref(true)
const multipleWordBook = ref(true)
const wordBookTotal = ref(0)
const wordBookTitle = ref("")
const wordBookOptions = ref([])

// 单词相关数据
const wordList = ref([])
const wordOpen = ref(false)
const wordLoading = ref(true)
const showWordSearch = ref(true)
const wordIds = ref([])
const singleWord = ref(true)
const multipleWord = ref(true)
const wordTotal = ref(0)
const wordTitle = ref("")

// OCR扫描相关数据
const ocrOpen = ref(false)
const ocrTitle = ref("单词扫描")
const ocrImageUrl = ref('')
const ocrRawText = ref('')
const ocrWordList = ref([])
const ocrLoading = ref(false)
const batchLoading = ref(false)
const uploadFileUrl = ref(import.meta.env.VITE_APP_BASE_API + "/common/upload")
const headers = ref({ Authorization: "Bearer " + getToken() })
const ocrSelectedFile = ref(null)

// OCR图片拖动和缩放相关数据
const isDragging = ref(false)
const startPosition = ref({ x: 0, y: 0 })
const imagePosition = ref({ x: 0, y: 0 })
const imageScale = ref(1)
const lastScale = ref(1)
const touchDistance = ref(0)

// 表单引用
const wordBookQueryRef = ref(null)
const wordQueryRef = ref(null)
const wordBookFormRef = ref(null)
const wordFormRef = ref(null)

// 响应式数据
const wordBookData = reactive({
  wordBookForm: {
    id: null,
    name: null,
    description: null,
    isDefault: 0,
    userId: null
  },
  wordBookQuery: {
    pageNum: 1,
    pageSize: 10,
    name: null,
    userId: null
  },
  wordBookRules: {
    name: [
      { required: true, message: "单词本名称不能为空", trigger: "blur" },
      { min: 1, max: 50, message: "长度在 1 到 50 个字符", trigger: "blur" }
    ]
  }
})

const wordData = reactive({
  wordForm: {
    id: null,
    wordBookId: null,
    english: null,
    chinese: null,
    phonetic: null
  },
  wordQuery: {
    pageNum: 1,
    pageSize: 10,
    wordBookId: null,
    english: null,
    chinese: null,
    userId: null
  },
  wordRules: {
    wordBookId: [
      { required: true, message: "所属单词本不能为空", trigger: "blur" }
    ],
    english: [
      { required: true, message: "英文单词不能为空", trigger: "blur" },
      { min: 1, max: 100, message: "长度在 1 到 100 个字符", trigger: "blur" }
    ],
    chinese: [
      { required: true, message: "中文意思不能为空", trigger: "blur" },
      { min: 1, max: 200, message: "长度在 1 到 200 个字符", trigger: "blur" }
    ]
  }
})

const {
  wordBookForm, wordBookQuery, wordBookRules
} = toRefs(wordBookData)

const {
  wordForm, wordQuery, wordRules
} = toRefs(wordData)

// ========== 单词本相关方法 ==========
function getWordBookList() {
  wordBookLoading.value = true
  wordBookQuery.value.userId = currentUserId.value
  
  listWordBooks(wordBookQuery.value).then(response => {
    wordBookList.value = response.rows
    wordBookTotal.value = response.total
    wordBookLoading.value = false
  }).catch(error => {
    console.error('获取单词本列表失败:', error)
    wordBookLoading.value = false
    proxy.$modal.msgError("获取单词本列表失败")
  })
}

function handleWordBookQuery() {
  wordBookQuery.value.pageNum = 1
  getWordBookList()
}

function resetWordBookQuery() {
  if (wordBookQueryRef.value) {
    wordBookQueryRef.value.resetFields()
  }
  wordBookQuery.value.userId = currentUserId.value
  handleWordBookQuery()
}

function handleWordBookSelectionChange(selection) {
  wordBookIds.value = selection.map(item => item.id)
  singleWordBook.value = selection.length !== 1
  multipleWordBook.value = !selection.length
}

function handleAddWordBook() {
  resetWordBookForm()
  wordBookOpen.value = true
  wordBookTitle.value = "添加单词本"
}

function handleUpdateWordBook(row) {
  resetWordBookForm()
  const id = row.id || wordBookIds.value
  getWordBooks(id).then(response => {
    wordBookForm.value = response.data
    wordBookOpen.value = true
    wordBookTitle.value = "修改单词本"
  }).catch(error => {
    console.error('获取单词本详情失败:', error)
    proxy.$modal.msgError("获取单词本详情失败")
  })
}

function submitWordBookForm() {
  if (!wordBookFormRef.value) return
  
  wordBookFormRef.value.validate(valid => {
    if (valid) {
      if (!wordBookForm.value.userId) {
        wordBookForm.value.userId = currentUserId.value
      }
      
      const submitPromise = wordBookForm.value.id 
        ? updateWordBooks(wordBookForm.value)
        : addWordBooks(wordBookForm.value)
      
      submitPromise.then(response => {
        proxy.$modal.msgSuccess(wordBookForm.value.id ? "修改成功" : "新增成功")
        wordBookOpen.value = false
        getWordBookList()
        if (!wordBookForm.value.id) {
          initWordBookOptions()
        }
      }).catch(error => {
        console.error('保存单词本失败:', error)
        proxy.$modal.msgError(error.msg || "保存失败")
      })
    }
  })
}

function cancelWordBook() {
  wordBookOpen.value = false
  resetWordBookForm()
}

function resetWordBookForm() {
  wordBookForm.value = {
    id: null,
    name: null,
    description: null,
    isDefault: 0,
    userId: currentUserId.value
  }
  if (wordBookFormRef.value) {
    wordBookFormRef.value.resetFields()
  }
}

function handleDeleteWordBook(row) {
  const ids = row.id || wordBookIds.value
  
  if (!ids || ids.length === 0) {
    proxy.$modal.msgWarning("请选择要删除的单词本")
    return
  }
  
  proxy.$modal.confirm(`是否确认删除选中的 ${ids.length} 个单词本？`).then(() => {
    return delWordBooks(ids)
  }).then(() => {
    getWordBookList()
    initWordBookOptions()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

// ========== 单词相关方法 ==========
async function getWordList() {
  wordLoading.value = true
  
  if (wordBookOptions.value.length === 0) {
    await initWordBookOptions()
  }
  
  if (!wordQuery.value.wordBookId && wordBookOptions.value.length > 0) {
    wordQuery.value.wordBookId = wordBookOptions.value[0].id
  } else if (!wordQuery.value.wordBookId) {
    wordList.value = []
    wordTotal.value = 0
    wordLoading.value = false
    return
  }
  
  // 验证单词本是否有效
  const isValidWordBook = wordBookOptions.value.some(
    book => book.id === wordQuery.value.wordBookId
  )
  
  if (!isValidWordBook) {
    proxy.$modal.msgWarning("请选择您自己的单词本")
    wordList.value = []
    wordTotal.value = 0
    wordLoading.value = false
    return
  }
  
  listWords(wordQuery.value).then(response => {
    wordList.value = response.rows
    wordTotal.value = response.total
    wordLoading.value = false
  }).catch(error => {
    console.error('获取单词列表失败:', error)
    wordLoading.value = false
    proxy.$modal.msgError("获取单词列表失败")
  })
}

function handleWordQuery() {
  wordQuery.value.pageNum = 1
  getWordList()
}

function resetWordQuery() {
  if (wordQueryRef.value) {
    wordQueryRef.value.resetFields()
  }
  
  if (wordBookOptions.value.length > 0) {
    wordQuery.value.wordBookId = wordBookOptions.value[0].id
  } else {
    wordQuery.value.wordBookId = null
  }
  
  handleWordQuery()
}

function handleWordSelectionChange(selection) {
  wordIds.value = selection.map(item => item.id)
  singleWord.value = selection.length !== 1
  multipleWord.value = !selection.length
}

function handleAddWord() {
  if (wordBookOptions.value.length === 0) {
    proxy.$modal.msgWarning("请先创建单词本")
    activeTab.value = 'wordBook'
    return
  }
  
  resetWordForm()
  wordOpen.value = true
  wordTitle.value = "添加单词"
}

function handleUpdateWord(row) {
  resetWordForm()
  const id = row.id || wordIds.value
  
  getWords(id).then(response => {
    wordForm.value = response.data
    wordOpen.value = true
    wordTitle.value = "修改单词"
  }).catch(error => {
    console.error('获取单词详情失败:', error)
    proxy.$modal.msgError("获取单词详情失败")
  })
}

function submitWordForm() {
  if (!wordFormRef.value) return
  
  wordFormRef.value.validate(valid => {
    if (valid) {
      // 验证单词本是否有效
      const selectedBook = wordBookOptions.value.find(
        book => book.id === wordForm.value.wordBookId
      )
      
      if (!selectedBook) {
        proxy.$modal.msgError("请选择有效的单词本")
        return
      }
      
      const submitPromise = wordForm.value.id 
        ? updateWords(wordForm.value)
        : addWords(wordForm.value)
      
      submitPromise.then(response => {
        proxy.$modal.msgSuccess(wordForm.value.id ? "修改成功" : "新增成功")
        wordOpen.value = false
        getWordList()
      }).catch(error => {
        console.error('保存单词失败:', error)
        proxy.$modal.msgError(error.msg || "保存失败")
      })
    }
  })
}

function cancelWord() {
  wordOpen.value = false
  resetWordForm()
}

function resetWordForm() {
  wordForm.value = {
    id: null,
    wordBookId: wordBookOptions.value.length > 0 ? wordBookOptions.value[0].id : null,
    english: null,
    chinese: null,
    phonetic: null
  }
  if (wordFormRef.value) {
    wordFormRef.value.resetFields()
  }
}

function handleDeleteWord(row) {
  const ids = row.id || wordIds.value
  
  if (!ids || ids.length === 0) {
    proxy.$modal.msgWarning("请选择要删除的单词")
    return
  }
  
  proxy.$modal.confirm(`是否确认删除选中的 ${ids.length} 个单词？`).then(() => {
    return delWords(ids)
  }).then(() => {
    getWordList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

// ========== OCR扫描相关方法 ==========
function handleScanWord() {
  if (wordBookOptions.value.length === 0) {
    proxy.$modal.msgWarning("请先创建单词本")
    activeTab.value = 'wordBook'
    return
  }
  
  resetOcrData()
  ocrOpen.value = true
  ocrTitle.value = "单词扫描"
}

function handleOcrImageSuccess(response) {
  if (response.code === 200) {
    const baseUrl = import.meta.env.VITE_APP_BASE_API
    ocrImageUrl.value = `${baseUrl}${response.fileName}`
    proxy.$modal.msgSuccess('图片上传成功')
    resetImageZoom()
  } else {
    proxy.$modal.msgError(response.msg || '图片上传失败')
  }
}

function handleOcrImageError(error) {
  console.error('图片上传失败:', error)
  proxy.$modal.msgError('图片上传失败')
}

function beforeOcrImageUpload(file) {
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    proxy.$modal.msgError('只能上传图片文件!')
    return false
  }
  
  const isLt10M = file.size / 1024 / 1024 < 10
  if (!isLt10M) {
    proxy.$modal.msgError('图片大小不能超过 10MB!')
    return false
  }
  
  ocrSelectedFile.value = file
  return true
}

function removeOcrImage() {
  ocrImageUrl.value = ''
  ocrRawText.value = ''
  ocrWordList.value = []
  ocrSelectedFile.value = null
  if (ocrUploadRef.value) {
    ocrUploadRef.value.clearFiles()
  }
}

function startOcrRecognize() {
  if (!ocrSelectedFile.value) {
    proxy.$modal.msgWarning('请先上传图片')
    return
  }
  
  ocrLoading.value = true
  ocrRawText.value = ''
  ocrWordList.value = []
  
  const formData = new FormData()
  formData.append('file', ocrSelectedFile.value)
  
  ocrRecognize(formData).then(response => {
    if (response.code === 200) {
      ocrRawText.value = response.data.text || ''
      parseOcrResult(ocrRawText.value)
      proxy.$modal.msgSuccess('OCR识别成功')
    } else {
      proxy.$modal.msgError(response.msg || 'OCR识别失败')
    }
    ocrLoading.value = false
  }).catch(error => {
    console.error('OCR识别失败:', error)
    proxy.$modal.msgError('OCR识别请求失败')
    ocrLoading.value = false
  })
}

function parseOcrResult(text) {
  if (!text) return
  
  const lines = text.split('\n').filter(line => line.trim() !== '')
  ocrWordList.value = []
  
  lines.forEach((line, index) => {
    const parts = line.split(':')
    if (parts.length >= 2) {
      const english = parts[0].trim()
      const chinese = parts.slice(1).join(':').trim()
      
      ocrWordList.value.push({
        id: index,
        english: english,
        chinese: chinese,
        phonetic: '',
        loading: false,
        wordBookId: wordQuery.value.wordBookId
      })
    } else {
      ocrWordList.value.push({
        id: index,
        english: line.trim(),
        chinese: '',
        phonetic: '',
        loading: false,
        wordBookId: wordQuery.value.wordBookId
      })
    }
  })
}

function addSingleWord(word, index) {
  if (!word.wordBookId) {
    proxy.$modal.msgWarning('请先选择单词本')
    return
  }
  
  if (!word.english || !word.chinese) {
    proxy.$modal.msgWarning('请填写英文和中文')
    return
  }
  
  word.loading = true
  
  const wordData = {
    wordBookId: word.wordBookId,
    english: word.english,
    chinese: word.chinese,
    phonetic: word.phonetic || ''
  }
  
  addWords(wordData).then(response => {
    proxy.$modal.msgSuccess(`"${word.english}" 添加成功`)
    ocrWordList.value.splice(index, 1)
    word.loading = false
    getWordList()
  }).catch(error => {
    console.error('添加单词失败:', error)
    word.loading = false
    proxy.$modal.msgError("添加失败")
  })
}

function addAllWords() {
  if (!wordQuery.value.wordBookId) {
    proxy.$modal.msgWarning('请先选择单词本')
    return
  }
  
  if (ocrWordList.value.length === 0) {
    proxy.$modal.msgWarning('没有可添加的单词')
    return
  }
  
  const invalidWords = ocrWordList.value.filter(word => !word.english || !word.chinese)
  if (invalidWords.length > 0) {
    proxy.$modal.msgWarning(`有 ${invalidWords.length} 个单词缺少英文或中文，请补充完整`)
    return
  }
  
  batchLoading.value = true
  
  const batchData = ocrWordList.value.map(word => ({
    wordBookId: word.wordBookId,
    english: word.english,
    chinese: word.chinese,
    phonetic: word.phonetic || ''
  }))
  
  batchAddWords(batchData).then(response => {
    proxy.$modal.msgSuccess(response.msg || `成功批量添加 ${batchData.length} 个单词`)
    ocrWordList.value = []
    batchLoading.value = false
    getWordList()
  }).catch(error => {
    console.error('批量添加失败:', error)
    proxy.$modal.msgError(error.msg || '批量添加失败')
    batchLoading.value = false
  })
}

function removeWordItem(index) {
  ocrWordList.value.splice(index, 1)
}

function resetOcrData() {
  ocrImageUrl.value = ''
  ocrRawText.value = ''
  ocrWordList.value = []
  ocrSelectedFile.value = null
  resetImageZoom()
  if (ocrUploadRef.value) {
    ocrUploadRef.value.clearFiles()
  }
}

function cancelOcr() {
  ocrOpen.value = false
  resetOcrData()
}

// ========== 图片拖动缩放方法 ==========
function startDrag(event) {
  if (!ocrImageUrl.value) return
  
  isDragging.value = true
  startPosition.value = {
    x: event.clientX - imagePosition.value.x,
    y: event.clientY - imagePosition.value.y
  }
  event.preventDefault()
}

function handleDrag(event) {
  if (!isDragging.value || !ocrImageUrl.value) return
  
  imagePosition.value = {
    x: event.clientX - startPosition.value.x,
    y: event.clientY - startPosition.value.y
  }
}

function stopDrag() {
  isDragging.value = false
}

function handleWheel(event) {
  if (!ocrImageUrl.value) return
  
  event.preventDefault()
  const delta = event.deltaY > 0 ? -0.1 : 0.1
  zoomImage(delta)
}

function zoomImage(delta) {
  if (!ocrImageUrl.value) return
  
  const newScale = imageScale.value + delta
  if (newScale >= 0.1 && newScale <= 3) {
    imageScale.value = parseFloat(newScale.toFixed(1))
    lastScale.value = imageScale.value
  }
}

function onScaleChange(value) {
  if (!ocrImageUrl.value) return
  
  imageScale.value = value
  lastScale.value = value
}

function resetImageZoom() {
  imageScale.value = 1
  imagePosition.value = { x: 0, y: 0 }
  lastScale.value = 1
}

function startTouch(event) {
  if (!ocrImageUrl.value) return
  
  event.preventDefault()
  if (event.touches.length === 1) {
    isDragging.value = true
    const touch = event.touches[0]
    startPosition.value = {
      x: touch.clientX - imagePosition.value.x,
      y: touch.clientY - imagePosition.value.y
    }
  } else if (event.touches.length === 2) {
    isDragging.value = false
    const touch1 = event.touches[0]
    const touch2 = event.touches[1]
    touchDistance.value = Math.sqrt(
      Math.pow(touch2.clientX - touch1.clientX, 2) +
      Math.pow(touch2.clientY - touch1.clientY, 2)
    )
    lastScale.value = imageScale.value
  }
}

function handleTouch(event) {
  if (!ocrImageUrl.value) return
  
  event.preventDefault()
  
  if (event.touches.length === 1 && isDragging.value) {
    const touch = event.touches[0]
    imagePosition.value = {
      x: touch.clientX - startPosition.value.x,
      y: touch.clientY - startPosition.value.y
    }
  } else if (event.touches.length === 2) {
    isDragging.value = false
    const touch1 = event.touches[0]
    const touch2 = event.touches[1]
    const currentDistance = Math.sqrt(
      Math.pow(touch2.clientX - touch1.clientX, 2) +
      Math.pow(touch2.clientY - touch1.clientY, 2)
    )
    
    if (touchDistance.value > 0) {
      const scaleChange = (currentDistance - touchDistance.value) / 100
      const newScale = lastScale.value + scaleChange
      if (newScale >= 0.1 && newScale <= 3) {
        imageScale.value = parseFloat(newScale.toFixed(2))
      }
    }
  }
}

function stopTouch() {
  isDragging.value = false
  touchDistance.value = 0
}

// ========== 辅助方法 ==========
async function initWordBookOptions() {
  const query = {
    pageNum: 1,
    pageSize: 1000,
    userId: currentUserId.value
  }
  
  try {
    const response = await listWordBooks(query)
    wordBookOptions.value = response.rows
    
    if (wordBookOptions.value.length > 0 && !wordQuery.value.wordBookId) {
      wordQuery.value.wordBookId = wordBookOptions.value[0].id
    }
    
    return response.rows
  } catch (error) {
    console.error('获取单词本选项失败:', error)
    wordBookOptions.value = []
    return []
  }
}

function handleStartDictation(dictationConfig) {
  proxy.$modal.msgSuccess("开始听力练习")
}

function handleStopDictation() {
  proxy.$modal.msgSuccess("停止听力练习")
}

// ========== 生命周期钩子 ==========
onMounted(async () => {
  if (currentUserId.value) {
    await initWordBookOptions()
    getWordBookList()
    getWordList()
  } else {
    proxy.$modal.msgWarning("请先登录")
  }
})

// 监听用户ID变化
watch(currentUserId, (newVal) => {
  if (newVal) {
    initWordBookOptions().then(() => {
      getWordBookList()
      getWordList()
    })
  }
})
</script>

<style scoped lang="scss">
.dictation-container {
  background-color: #f5f7fa;
  padding: 20px;
  border-radius: 8px;
  min-height: calc(100vh - 84px);
}

.dictation-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 20px;
    background: white;
    padding: 0 20px;
    border-radius: 6px 6px 0 0;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    .el-tabs__nav-wrap::after {
      height: 1px;
      background-color: #e4e7ed;
    }

    .el-tabs__item {
      font-weight: 500;
      color: #606266;
      padding: 0 24px;
      height: 48px;
      line-height: 48px;
      transition: all 0.3s ease;

      &.is-active {
        color: #409eff;
        font-weight: 600;
      }

      &:hover {
        color: #409eff;
      }
    }

    .el-tabs__active-bar {
      background-color: #409eff;
      height: 3px;
    }
  }
}

.tab-content {
  background: white;
  padding: 20px;
  border-radius: 0 0 6px 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  min-height: 500px;
}

.search-form {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
  margin-bottom: 20px;
  border: 1px solid #ebeef5;

  :deep(.el-form-item) {
    margin-bottom: 0;
    margin-right: 20px;

    &:last-child {
      margin-right: 0;
    }

    .el-form-item__label {
      font-weight: 500;
      color: #606266;
    }
  }
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 0;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 20px;

  .el-button {
    border-radius: 4px;
    font-weight: 500;
    
    &[type="primary"]:not(.is-plain) {
      background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
      border-color: #409eff;
      
      &:hover {
        background: linear-gradient(135deg, #66b1ff 0%, #409eff 100%);
        border-color: #66b1ff;
      }
    }
    
    &.is-plain {
      border-width: 1px;
    }
  }
}

.mb15 {
  margin-bottom: 15px;
}

.mt15 {
  margin-top: 15px;
}

.mt20 {
  margin-top: 20px;
}

.mb8 {
  margin-bottom: 8px;
}

.data-table {
  margin-top: 15px;
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;

  :deep(.el-table__header) {
    th {
      background-color: #f5f7fa;
      color: #606266;
      font-weight: 600;
      height: 48px;
      padding: 12px 0;
    }
  }

  :deep(.el-table__body) {
    tr {
      &:hover {
        background-color: #f5f7fa;
      }
      
      td {
        padding: 12px 0;
        transition: background-color 0.3s ease;
      }
    }
  }

  :deep(.el-table__row) {
    &:nth-child(2n) {
      background-color: #fafafa;
    }
  }
}

.pagination-container {
  padding: 20px 0;
  display: flex;
  justify-content: center;
  align-items: center;
  border-top: 1px solid #ebeef5;
  margin-top: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #ebeef5;
  
  .el-button {
    min-width: 80px;
    border-radius: 4px;
    font-weight: 500;
    
    &--primary {
      background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
      border-color: #409eff;
      
      &:hover {
        background: linear-gradient(135deg, #66b1ff 0%, #409eff 100%);
        border-color: #66b1ff;
      }
    }
  }
}

/* OCR对话框样式 */
:deep(.el-dialog) {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  
  .el-dialog__header {
    padding: 20px;
    border-bottom: 1px solid #ebeef5;
    background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
    margin: 0;
    
    .el-dialog__title {
      font-weight: 600;
      color: #303133;
      font-size: 18px;
    }
  }
  
  .el-dialog__body {
    padding: 20px;
    max-height: 70vh;
    overflow-y: auto;
  }
}

/* OCR上传区域 */
.ocr-upload-area {
  margin-bottom: 24px;
  
  .upload-demo {
    width: 100%;
    margin-bottom: 20px;
    
    :deep(.el-upload) {
      width: 100%;
    }
    
    :deep(.el-upload-dragger) {
      width: 100%;
      height: 200px;
      border: 2px dashed #dcdfe6;
      border-radius: 8px;
      background-color: #fafafa;
      transition: all 0.3s ease;
      
      &:hover {
        border-color: #409eff;
        background-color: #f0f7ff;
      }
      
      .el-icon--upload {
        font-size: 48px;
        color: #c0c4cc;
        margin-bottom: 16px;
      }
      
      .el-upload__text {
        color: #606266;
        font-size: 14px;
        margin-bottom: 8px;
        
        em {
          color: #409eff;
          font-style: normal;
          font-weight: 500;
        }
      }
      
      .el-upload__tip {
        color: #909399;
        font-size: 12px;
      }
    }
  }
  
  .image-preview-container {
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    padding: 16px;
    background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    
    .preview-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid #e4e7ed;
      
      .preview-title {
        font-weight: 600;
        color: #409eff;
        font-size: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
        
        &::before {
          content: "📷";
          font-size: 18px;
        }
      }
      
      .preview-actions {
        .el-button-group {
          .el-button {
            border-radius: 4px;
            
            .el-icon {
              margin-right: 4px;
            }
          }
        }
      }
    }
    
    .draggable-image-preview {
      position: relative;
      height: 320px;
      overflow: hidden;
      border: 1px solid #dcdfe6;
      border-radius: 6px;
      background: white;
      cursor: grab;
      user-select: none;
      touch-action: none;
      
      &:active {
        cursor: grabbing;
      }
      
      .image-wrapper {
        position: absolute;
        top: 0;
        left: 0;
        transform-origin: center center;
        transition: transform 0.15s ease-out;
        
        .ocr-image-preview {
          width: 100%;
          height: 100%;
          object-fit: contain;
          pointer-events: none;
          
          &:deep(.el-image__inner) {
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          }
        }
      }
      
      .zoom-controls {
        position: absolute;
        bottom: 16px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 16px;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(64, 158, 255, 0.2);
        z-index: 10;
        min-width: 220px;
        
        :deep(.el-slider) {
          flex: 1;
          
          .el-slider__runway {
            background-color: #e4e7ed;
            height: 4px;
            
            .el-slider__bar {
              background: linear-gradient(90deg, #409eff 0%, #66b1ff 100%);
              height: 4px;
            }
            
            .el-slider__button {
              width: 16px;
              height: 16px;
              border: 2px solid #409eff;
              background-color: white;
              box-shadow: 0 2px 4px rgba(64, 158, 255, 0.3);
              
              &:hover {
                transform: scale(1.2);
              }
            }
          }
        }
        
        .zoom-text {
          font-size: 12px;
          color: #409eff;
          font-weight: 600;
          min-width: 50px;
          text-align: center;
          background: rgba(64, 158, 255, 0.1);
          padding: 2px 8px;
          border-radius: 12px;
        }
      }
      
      .drag-hint {
        position: absolute;
        top: 12px;
        right: 12px;
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        background: rgba(64, 158, 255, 0.15);
        border-radius: 16px;
        font-size: 12px;
        color: #409eff;
        animation: fadeInOut 2s infinite ease-in-out;
        backdrop-filter: blur(4px);
        border: 1px solid rgba(64, 158, 255, 0.3);
        z-index: 5;
        
        .el-icon {
          font-size: 14px;
          animation: float 3s infinite ease-in-out;
        }
        
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
      }
      
      @keyframes fadeInOut {
        0%, 100% { 
          opacity: 0.6;
          transform: translateY(0);
        }
        50% { 
          opacity: 1;
          transform: translateY(-2px);
        }
      }
    }
    
    .image-actions {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid #e4e7ed;
      
      .el-button {
        min-width: 120px;
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.3s ease;
        
        &--primary {
          background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
          border-color: #409eff;
          
          &:hover:not(.is-disabled) {
            background: linear-gradient(135deg, #66b1ff 0%, #409eff 100%);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
          }
          
          &.is-disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }
        }
        
        &--danger {
          background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%);
          border-color: #f56c6c;
          
          &:hover {
            background: linear-gradient(135deg, #f78989 0%, #f56c6c 100%);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(245, 108, 108, 0.3);
          }
        }
        
        .el-icon {
          margin-right: 6px;
        }
      }
    }
  }
}

/* OCR结果区域 */
.ocr-result-area {
  margin: 24px 0;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  background: white;
  
  .result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    border-bottom: 1px solid #e4e7ed;
    
    .header-title {
      font-weight: 600;
      color: #303133;
      font-size: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      
      &::before {
        content: "📝";
        font-size: 18px;
      }
    }
    
    .header-actions {
      .el-button {
        border-radius: 6px;
        font-weight: 500;
        
        &--success {
          background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
          border-color: #67c23a;
          
          &:hover:not(.is-loading) {
            background: linear-gradient(135deg, #85ce61 0%, #67c23a 100%);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(103, 194, 58, 0.3);
          }
        }
      }
    }
  }
  
  .word-list-container {
    max-height: 320px;
    overflow-y: auto;
    padding: 16px;
    background: #fafafa;
    
    .word-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      background: white;
      border: 1px solid #e4e7ed;
      border-radius: 6px;
      margin-bottom: 12px;
      transition: all 0.3s ease;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      &:hover {
        border-color: #409eff;
        box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
        transform: translateY(-1px);
      }
      
      .word-index {
        min-width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
        color: white;
        font-weight: 600;
        font-size: 14px;
        border-radius: 50%;
        flex-shrink: 0;
      }
      
      .english-input,
      .chinese-input,
      .phonetic-input {
        :deep(.el-input__wrapper) {
          border-radius: 6px;
          transition: all 0.3s ease;
          
          &:hover {
            border-color: #c0c4cc;
          }
          
          &.is-focus {
            border-color: #409eff;
            box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
          }
        }
      }
      
      .english-input {
        flex: 2;
      }
      
      .chinese-input {
        flex: 3;
      }
      
      .phonetic-input {
        flex: 2;
      }
      
      .word-actions {
        min-width: 140px;
        display: flex;
        gap: 8px;
        flex-shrink: 0;
        
        .el-button {
          flex: 1;
          border-radius: 6px;
          font-weight: 500;
          transition: all 0.3s ease;
          
          &--primary {
            background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
            border-color: #409eff;
            
            &:hover:not(.is-loading) {
              background: linear-gradient(135deg, #66b1ff 0%, #409eff 100%);
              transform: translateY(-2px);
            }
          }
          
          &--danger {
            background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%);
            border-color: #f56c6c;
            
            &:hover {
              background: linear-gradient(135deg, #f78989 0%, #f56c6c 100%);
              transform: translateY(-2px);
            }
          }
        }
      }
    }
  }
}

/* OCR原始结果 */
.ocr-raw-result {
  margin-top: 24px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  
  :deep(.el-divider) {
    margin: 0;
    
    .el-divider__text {
      background: white;
      color: #909399;
      font-size: 12px;
      padding: 0 16px;
    }
  }
  
  :deep(.el-textarea) {
    .el-textarea__inner {
      padding: 16px;
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 13px;
      line-height: 1.6;
      border: none;
      border-radius: 0;
      background: #f8f9fa;
      color: #333;
      resize: none;
      
      &:focus {
        box-shadow: none;
      }
    }
  }
}

/* 图片加载状态样式 */
.image-slot {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  color: #909399;
  font-size: 14px;
  
  .dot {
    display: inline-block;
    margin-left: 2px;
    
    &:nth-child(1) {
      animation: dotFlashing 1.4s infinite linear 0s;
    }
    
    &:nth-child(2) {
      animation: dotFlashing 1.4s infinite linear 0.2s;
    }
    
    &:nth-child(3) {
      animation: dotFlashing 1.4s infinite linear 0.4s;
    }
  }
  
  @keyframes dotFlashing {
    0%, 100% { 
      opacity: 0;
      transform: translateY(0);
    }
    50% { 
      opacity: 1;
      transform: translateY(-2px);
    }
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .dictation-container {
    padding: 12px;
  }
  
  .tab-content {
    padding: 16px;
  }
  
  .search-form {
    padding: 16px;
    
    :deep(.el-form-item) {
      margin-right: 12px;
      margin-bottom: 12px;
      
      &:last-child {
        margin-bottom: 0;
      }
    }
  }
  
  .toolbar {
    gap: 8px;
    
    .el-button {
      flex: 1;
      min-width: auto;
    }
  }
  
  .data-table {
    :deep(.el-table) {
      font-size: 12px;
    }
  }
  
  .ocr-upload-area {
    .draggable-image-preview {
      height: 240px;
    }
    
    .word-item {
      flex-wrap: wrap;
      
      .word-actions {
        min-width: 100%;
        margin-top: 8px;
      }
    }
  }
}
</style>