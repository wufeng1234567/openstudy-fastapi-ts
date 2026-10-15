<template>
    <div class="ocr-page">
        <!-- 顶部导航栏 -->
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title">拍照识词</div>
            <div class="header-right">
                <span v-if="recognizedList.length > 0" class="word-count">
                    已识别 {{ recognizedList.length }} 个
                </span>
            </div>
        </div>

        <!-- 图片上传区域 -->
        <div class="image-section">
            <div class="upload-wrapper">
                <el-upload ref="uploadRef" :action="uploadUrl" :headers="uploadHeaders" :before-upload="beforeUpload"
                    :on-success="handleUploadSuccess" :on-error="handleUploadError" :show-file-list="false" :limit="1"
                    accept="image/png,image/jpeg,image/jpg" class="ocr-upload">
                    <div class="upload-area" v-if="!imageUrl">
                        <el-icon :size="48">
                            <Camera />
                        </el-icon>
                        <span class="upload-text">点击拍照或上传图片</span>
                        <span class="upload-hint">支持 JPG、PNG 格式，不超过 10MB</span>
                    </div>
                </el-upload>

                <!-- 图片预览 -->
                <div class="image-preview" v-if="imageUrl">
                    <div class="preview-container">
                        <div class="preview-toolbar">

                            <span class="zoom-text">{{ Math.round(imageScale * 100) }}%</span>
                        </div>

                        <div class="draggable-container" @mousedown="startDrag" @mousemove="onDrag" @mouseup="stopDrag"
                            @mouseleave="stopDrag" @wheel.prevent="onWheel" @dblclick="openEditor">
                            <!-- 双击提示 -->
                            <div class="dblclick-hint">
                                <el-icon>
                                    <ZoomIn />
                                </el-icon>
                                <span>双击编辑图片</span>
                            </div>
                            <el-image ref="previewImageRef" :src="imageUrl" fit="contain" class="preview-image"
                                :preview-src-list="[imageUrl]" :style="{
                                    transform: `translate(${imagePosition.x}px, ${imagePosition.y}px) scale(${imageScale}) rotate(${rotation}deg)`,
                                    cursor: isDragging ? 'grabbing' : 'grab'
                                }" />
                        </div>
                    </div>

                    <div class="preview-actions">
                        <el-button @click="rotateImage" icon="RefreshRight">
                            旋转
                        </el-button>
                        <el-button @click="exportCurrentImage" icon="Download">
                            导出
                        </el-button>
                        <el-button type="danger" plain @click="removeImage" icon="Delete">
                            删除
                        </el-button>
                        <el-button type="primary" @click="startRecognize" :loading="recognizing">
                            <el-icon v-if="!recognizing">
                                <Search />
                            </el-icon>
                            {{ recognizing ? '识别中...' : '开始识别' }}
                        </el-button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 词库选择 -->
        <div class="book-select-section" v-if="recognizedList.length > 0">
            <div class="select-label">选择词库</div>
            <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" style="width: 100%"
                @change="onBookChange">
                <el-option v-for="book in bookOptions" :key="book.id" :label="book.name" :value="book.id" />
            </el-select>

            <!-- 词库预览面板 -->
            <div class="book-preview" v-if="selectedBookId && bookPreview.total > 0">
                <div class="preview-header" @click="showPreview = !showPreview">
                    <div class="preview-title">
                        <el-icon>
                            <View />
                        </el-icon>
                        <span>词库预览</span>
                    </div>
                    <div class="preview-stats">
                        <span class="stat-word">📝 {{ bookPreview.wordCount }}</span>
                        <span class="stat-phrase">📚 {{ bookPreview.phraseCount }}</span>
                        <span class="stat-sentence">💬 {{ bookPreview.sentenceCount }}</span>
                    </div>
                    <el-icon class="preview-arrow" :class="{ expanded: showPreview }">
                        <ArrowDown />
                    </el-icon>
                </div>

                <div class="preview-content" v-show="showPreview">
                    <div class="preview-list">
                        <div v-for="item in bookPreview.items" :key="item.id" class="preview-item"
                            :class="getTypeClass(item.wordType)">
                            <span class="item-type">{{ getTypeIcon(item.wordType) }}</span>
                            <span class="item-english">{{ item.english }}</span>
                            <span class="item-chinese">{{ item.chinese }}</span>
                        </div>
                    </div>
                    <div class="preview-footer">
                        <el-button text type="primary" @click="goToVocabulary">
                            查看全部 <el-icon>
                                <ArrowRight />
                            </el-icon>
                        </el-button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 流式识别中 -->
        <div class="stream-loading" v-if="recognizing">
            <div class="stream-loading-header">
                <el-icon class="is-loading" :size="20">
                    <Loading />
                </el-icon>
                <span>AI 识别中...</span>
            </div>
            <div class="stream-loading-body">
                <pre>{{ streamContent }}</pre>
            </div>
        </div>

        <!-- 识别结果区域（双视图） -->
        <div class="result-section" v-if="recognizedList.length > 0 && !recognizing">
            <div class="result-header">
                <el-radio-group v-model="resultViewMode" size="small">
                    <el-radio-button label="words">识别结果（可编辑）</el-radio-button>
                    <el-radio-button label="json">AI 原始内容</el-radio-button>
                </el-radio-group>
                <div class="header-actions">
                    <el-button size="small" text @click="copyContent" class="copy-btn">
                        <el-icon :size="16"><DocumentCopy /></el-icon>
                    </el-button>
                    <el-button v-if="resultViewMode === 'words'" type="success" size="small" @click="addAllWords" :loading="batchAdding">
                        一键导入全部 ({{ recognizedList.length }})
                    </el-button>
                </div>
            </div>

            <!-- 视图1：格式化可编辑单词列表 -->
            <div v-if="resultViewMode === 'words'" class="word-list">
                <div v-for="(word, index) in recognizedList" :key="index" class="word-card">
                    <div class="card-header">
                        <span class="word-index">{{ index + 1 }}</span>
                        <div class="header-center">
                            <span class="word-type-badge" :title="getTypeText(word.wordType)">
                                <el-icon v-if="word.wordType === 'word'">
                                    <Document />
                                </el-icon>
                                <el-icon v-else-if="word.wordType === 'phrase'">
                                    <Collection />
                                </el-icon>
                                <el-icon v-else>
                                    <ChatLineSquare />
                                </el-icon>
                            </span>
                        </div>
                        <el-button type="danger" size="small" text @click="removeWord(index)">
                            <el-icon>
                                <Delete />
                            </el-icon>
                        </el-button>
                    </div>

                    <div class="card-body">
                        <el-input v-model="word.english" placeholder="英文/词组/句子" class="word-input" clearable />
                        <el-input v-model="word.chinese" placeholder="中文释义" class="word-input" clearable />
                        <el-input v-model="word.phonetic" placeholder="音标（可选）" class="word-input" clearable />

                        <el-select v-model="word.wordBookId" placeholder="选择词库" size="small" style="width: 100%">
                            <el-option v-for="book in bookOptions" :key="book.id" :label="book.name" :value="book.id" />
                        </el-select>

                        <el-select v-model="word.wordType" placeholder="类型" size="small" style="width: 100%">
                            <el-option label="📝 单词" value="word" />
                            <el-option label="📚 词组" value="phrase" />
                            <el-option label="💬 句子" value="sentence" />
                        </el-select>
                    </div>

                    <div class="card-footer">
                        <el-button type="primary" size="small" @click="addSingleWord(word, index)"
                            :loading="word.adding">
                            <el-icon>
                                <Plus />
                            </el-icon>
                            添加
                        </el-button>
                    </div>
                </div>
            </div>

            <!-- 视图2：AI 原始内容（自动格式化 JSON） -->
            <div v-else class="json-view">
                <pre class="json-content">{{ formattedStreamJson }}</pre>
            </div>
        </div>

        <!-- 空状态 -->
        <div class="empty-state" v-else-if="!imageUrl && !recognizing">
            <el-icon :size="48">
                <Picture />
            </el-icon>
            <span>上传图片后点击「开始识别」</span>
        </div>

        <!-- 图片编辑模态框 -->
        <teleport to="body">
            <div class="image-editor-modal" v-if="editorVisible" @click.self="closeEditor">
                <div class="editor-container">
                    <div class="editor-header">
                        <span class="editor-title">编辑图片</span>
                        <el-icon class="close-btn" @click="closeEditor">
                            <Close />
                        </el-icon>
                    </div>

                    <div class="editor-body">
                        <cropper ref="cropperRef" :src="editorImageUrl" :stencil-props="stencilProps"
                            :default-size="defaultSize" :default-boundaries="'fit'" :image-restriction="'none'"
                            :size-restrictions-algorithm="sizeRestrictionsAlgorithm" @change="onCropChange" />
                    </div>

                    <div class="editor-toolbar">
                        <el-button-group>
                            <el-button @click="rotate(-90)" icon="RefreshLeft">左转</el-button>
                            <el-button @click="rotate(90)" icon="RefreshRight">右转</el-button>
                            <el-button @click="flip('horizontal')">
                                <el-icon>
                                    <Switch />
                                </el-icon>
                                翻转
                            </el-button>
                        </el-button-group>

                        <el-button-group style="margin-left: 12px;">
                            <el-button @click="zoomIn" icon="ZoomIn">放大</el-button>
                            <el-button @click="zoomOut" icon="ZoomOut">缩小</el-button>
                            <el-button @click="resetCropper" icon="Refresh">重置</el-button>
                        </el-button-group>
                    </div>

                    <div class="editor-footer">
                        <el-button @click="exportImage" icon="Download">导出</el-button>
                        <div style="flex: 1"></div>
                        <el-button @click="closeEditor">取消</el-button>
                        <el-button type="primary" @click="applyCrop">应用裁剪</el-button>
                    </div>
                </div>
            </div>
        </teleport>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishOcr' })
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
    ArrowLeft, Camera, Search, Picture, Delete, Plus, Loading,
    RefreshRight, ZoomIn, ZoomOut, Refresh, Close, Switch, Download,
    Document, Collection, ChatLineSquare, View, ArrowDown, ArrowRight,
    DocumentCopy
} from '@element-plus/icons-vue'
import { getToken } from '@/utils/auth'
import { ocrRecognize, ocrRecognizeStream } from '@/api/english/ocr'
import { listWordBooks } from '@/api/wordBooks/wordBooks'
import { addWords, batchAddWords, listWords } from '@/api/words/words'
import useUserStore from '@/store/modules/user'

import { Cropper } from 'vue-advanced-cropper'
import 'vue-advanced-cropper/dist/style.css'

import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'




const router = useRouter()
const userStore = useUserStore()

// 当前用户ID
const currentUserId = computed(() => userStore.id)

// 上传配置
const baseUrl = import.meta.env.VITE_APP_BASE_API
const uploadUrl = ref(baseUrl + '/common/upload')
const uploadHeaders = ref({ Authorization: 'Bearer ' + getToken() })

// 响应式数据
const uploadRef = ref(null)
const imageUrl = ref('')
const selectedFile = ref(null)
const recognizing = ref(false)
const batchAdding = ref(false)
const recognizedList = ref([])
const bookOptions = ref([])
const selectedBookId = ref(null)

// 流式输出相关
const streamContent = ref('')
const resultViewMode = ref('words') // 'words' | 'json'

// 格式化后的 JSON
const formattedStreamJson = computed(() => {
    if (!streamContent.value) return ''
    try {
        // 提取 JSON 部分（可能包含 markdown 代码块）
        let jsonStr = streamContent.value
            .replace(/```json\s*/g, '')
            .replace(/```\s*/g, '')
            .trim()
        const parsed = JSON.parse(jsonStr)
        return JSON.stringify(parsed, null, 2)
    } catch (e) {
        // 如果不是完整 JSON，返回原始内容
        return streamContent.value
    }
})

const cacheStore = useFrontPageCacheStore()


// 词库预览相关
const showPreview = ref(true)
const bookPreview = ref({
    total: 0,
    wordCount: 0,
    phraseCount: 0,
    sentenceCount: 0,
    items: []
})

// 获取类型显示文本
const getTypeText = (type) => {
    const map = {
        'word': '单词',
        'phrase': '词组',
        'sentence': '句子'
    }
    return map[type] || '单词'
}

// 编辑器相关
const editorVisible = ref(false)
const editorImageUrl = ref('')
const cropperRef = ref(null)
const defaultSize = ref({ width: 400, height: 400 })

// 裁剪框配置 - 显示所有 8 个控制点
const stencilProps = ref({
    aspectRatio: null,
    movable: true,
    resizable: true,
    handlers: {
        // 四边中点
        north: true,
        south: true,
        west: true,
        east: true,


    }
})

// 图片编辑相关
const rotation = ref(0)  // 旋转角度：0, 90, 180, 270
const editedImageFile = ref(null)  // 编辑后的图片文件

// 自定义尺寸限制算法（允许图片完全自由）
const sizeRestrictionsAlgorithm = (minWidth, minHeight, maxWidth, maxHeight) => {
    return {
        minWidth: 10,      // 最小宽度 10px
        minHeight: 10,     // 最小高度 10px
        maxWidth: 5000,    // 最大宽度 5000px
        maxHeight: 5000    // 最大高度 5000px
    }
}

// 旋转图片
const rotateImage = () => {
    rotation.value = (rotation.value + 90) % 360
    applyRotation()
}


// 打开编辑器时，根据图片尺寸调整默认裁剪框
// 打开编辑器
const openEditor = () => {
    if (!imageUrl.value) return

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
        // 限制最大尺寸，避免图片过大
        const maxSize = 1200
        let width = img.width
        let height = img.height

        // 如果图片太大，等比缩小
        if (width > maxSize || height > maxSize) {
            const scale = maxSize / Math.max(width, height)
            width = Math.round(width * scale)
            height = Math.round(height * scale)
        }

        // 确保尺寸是偶数
        if (width % 2 !== 0) width++
        if (height % 2 !== 0) height++

        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')
        canvas.width = width
        canvas.height = height

        ctx.drawImage(img, 0, 0, width, height)
        editorImageUrl.value = canvas.toDataURL('image/jpeg', 0.9)
        editorVisible.value = true
    }
    img.onerror = () => {
        editorImageUrl.value = imageUrl.value
        editorVisible.value = true
    }
    img.src = imageUrl.value
}

// 导出当前预览图片
const exportCurrentImage = () => {
    if (!imageUrl.value) {
        ElMessage.warning('没有可导出的图片')
        return
    }

    // 如果有编辑后的文件，导出编辑后的
    if (editedImageFile.value) {
        const url = URL.createObjectURL(editedImageFile.value)
        const link = document.createElement('a')
        link.download = editedImageFile.value.name || `image_${Date.now()}.jpg`
        link.href = url
        link.click()
        URL.revokeObjectURL(url)
        ElMessage.success('图片已导出')
        return
    }

    // 否则导出原始图片
    const link = document.createElement('a')
    link.download = `image_${Date.now()}.jpg`
    link.href = imageUrl.value
    link.click()
    ElMessage.success('图片已导出')
}

// 关闭编辑器
const closeEditor = () => {
    editorVisible.value = false
}

// 导出图片
const exportImage = () => {
    if (!cropperRef.value) {
        ElMessage.warning('没有可导出的图片')
        return
    }

    const result = cropperRef.value.getResult()
    const canvas = result.canvas

    if (canvas) {
        // 创建下载链接
        const link = document.createElement('a')
        link.download = `edited_image_${Date.now()}.jpg`
        link.href = canvas.toDataURL('image/jpeg', 0.9)
        link.click()

        ElMessage.success('图片已导出')
    } else {
        ElMessage.error('导出失败')
    }
}


// 旋转
const rotate = (angle) => {
    if (cropperRef.value) {
        cropperRef.value.rotate(angle)
    }
}

// 翻转
const flip = (direction) => {
    if (cropperRef.value) {
        cropperRef.value.flip(true, direction === 'horizontal')
    }
}

// 重置裁剪器
const resetCropper = () => {
    if (cropperRef.value) {
        cropperRef.value.reset()
    }
}

// 裁剪变化
const onCropChange = (data) => {
    // 可以在这里实时获取裁剪区域
}

// 应用裁剪（同时应用旋转和翻转）
const applyCrop = () => {
    if (!cropperRef.value) return

    // 获取当前裁剪结果（已经包含旋转和翻转）
    const result = cropperRef.value.getResult()
    const canvas = result.canvas

    if (canvas) {
        // 将编辑后的图片转为 Data URL
        const editedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = editedUrl

        // 生成新文件用于上传
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'edited_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)

        // 重置预览状态
        rotation.value = 0
        imageScale.value = 1
        imagePosition.value = { x: 0, y: 0 }

        ElMessage.success('图片已保存')
        closeEditor()
    }
}



// 图片缩放和拖拽相关
const imageScale = ref(1)
const imagePosition = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const startDragPosition = ref({ x: 0, y: 0 })
const previewImageRef = ref(null)

// 缩放图片
// 放大
const zoomIn = () => {
    if (cropperRef.value) {
        cropperRef.value.zoom(1.2)
    }
}

// 缩小
const zoomOut = () => {
    if (cropperRef.value) {
        cropperRef.value.zoom(0.8)
    }
}

const resetZoom = () => {
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
}

// 开始拖拽
const startDrag = (e) => {
    isDragging.value = true
    startDragPosition.value = {
        x: e.clientX - imagePosition.value.x,
        y: e.clientY - imagePosition.value.y
    }
    e.preventDefault()
}

// 拖拽中
const onDrag = (e) => {
    if (!isDragging.value) return
    imagePosition.value = {
        x: e.clientX - startDragPosition.value.x,
        y: e.clientY - startDragPosition.value.y
    }
}

// 结束拖拽
const stopDrag = () => {
    isDragging.value = false
}

// 滚轮缩放
const onWheel = (e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = imageScale.value + delta
    if (newScale >= 0.5 && newScale <= 3) {
        imageScale.value = newScale
    }
}


// 应用旋转并生成新文件
const applyRotation = () => {
    if (!imageUrl.value) return

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl.value

    img.onload = () => {
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')

        // 根据旋转角度设置画布尺寸
        if (rotation.value === 90 || rotation.value === 270) {
            canvas.width = img.height
            canvas.height = img.width
        } else {
            canvas.width = img.width
            canvas.height = img.height
        }

        // 平移并旋转
        ctx.translate(canvas.width / 2, canvas.height / 2)
        ctx.rotate(rotation.value * Math.PI / 180)
        ctx.drawImage(img, -img.width / 2, -img.height / 2)

        // 更新预览
        const rotatedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = rotatedUrl

        // 生成新文件用于上传
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'rotated_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)
    }
}

// 重置旋转
const resetRotation = () => {
    rotation.value = 0
}

// 返回上一页
const goBack = () => {
    cacheStore.setLastVisited('english', 'home')
    router.push('/front/english/home')

}

// 上传前校验
const beforeUpload = (file) => {
    const isImage = file.type.startsWith('image/')
    if (!isImage) {
        ElMessage.error('只能上传图片文件')
        return false
    }

    const isLt10M = file.size / 1024 / 1024 < 10
    if (!isLt10M) {
        ElMessage.error('图片大小不能超过 10MB')
        return false
    }

    selectedFile.value = file
    return true
}



// 上传失败
const handleUploadError = () => {
    ElMessage.error('图片上传失败')
}

// 删除图片
const removeImage = () => {
    imageUrl.value = ''
    selectedFile.value = null
    recognizedList.value = []
    rotation.value = 0
    editedImageFile.value = null
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
    uploadRef.value?.clearFiles()
}

// 上传成功
const handleUploadSuccess = (response) => {
    if (response.code === 200) {
        imageUrl.value = baseUrl + response.fileName
        rotation.value = 0
        editedImageFile.value = null
        imageScale.value = 1
        imagePosition.value = { x: 0, y: 0 }
        ElMessage.success('图片上传成功')
    } else {
        ElMessage.error(response.msg || '上传失败')
    }
}

// ==================== 开始 OCR 识别（流式输出） ====================
// 流式输出：AI 边识别边返回结果，用户可以实时看到识别进度
// 对比非流式：需要等待全部识别完成才能看到结果
const startRecognize = async () => {
    if (!selectedFile.value) {
        ElMessage.warning('请先上传图片')
        return
    }

    // 重置状态
    recognizing.value = true
    recognizedList.value = []
    streamContent.value = ''
    resultViewMode.value = 'words'

    // 调用流式 OCR API
    ocrRecognizeStream(
        selectedFile.value,
        // onChunk 回调：每收到一个数据块就更新显示
        (fullContent) => {
            streamContent.value = fullContent
        },
        // onComplete 回调：流式完成，解析最终结果
        (fullContent) => {
            streamContent.value = fullContent
            recognizing.value = false
            // 尝试解析最终结果
            parseStreamResult(fullContent)
        },
        // onError
        (error) => {
            console.error('OCR流式识别失败:', error)
            ElMessage.error('识别请求失败')
            recognizing.value = false
        }
    )
}

// ==================== 解析流式结果 ====================
// AI 返回的内容可能包含 markdown 代码块标记，需要清理后解析 JSON
const parseStreamResult = (content) => {
    if (!content) return

    try {
        // 清理 markdown 代码块标记（```json ... ```）
        let jsonStr = content
            .replace(/```json\s*/g, '')
            .replace(/```\s*/g, '')
            .trim()
        const parsed = JSON.parse(jsonStr)
        if (Array.isArray(parsed)) {
            parseOcrResultFromWords(parsed)
            ElMessage.success(`识别完成，共 ${parsed.length} 个词条`)
        }
    } catch (e) {
        // JSON 解析失败，尝试按文本格式解析（兼容旧格式）
        console.log('流式结果不是标准 JSON，尝试文本解析')
        parseOcrResult(content)
    }
}

// ==================== 从 words 数组解析词条 ====================
// 将 AI 返回的 JSON 数组转换为前端可编辑的词条格式
const parseOcrResultFromWords = (words) => {
    if (!words || words.length === 0) {
        recognizedList.value = []
        return
    }

    // 映射为统一的词条格式
    recognizedList.value = words.map((item, index) => ({
        id: index,
        english: item.english || '',
        chinese: item.chinese || '',
        phonetic: item.phonetic || '',
        wordType: item.type || 'word',
        wordBookId: selectedBookId.value,  // 默认使用全局选择的词库
        adding: false
    }))

    console.log('词条解析完成，数量:', recognizedList.value.length)
}

// ==================== 解析 OCR 结果（兼容多种格式） ====================
// 支持 JSON 格式和纯文本格式，优先使用 JSON
const parseOcrResult = (text) => {
    if (!text) return

    recognizedList.value = []

    // 1. 优先尝试 JSON 格式解析
    try {
        const parsed = JSON.parse(text)
        if (Array.isArray(parsed) && parsed.length > 0) {
            recognizedList.value = parsed.map((item, index) => ({
                id: index,
                english: item.english || '',
                chinese: item.chinese || '',
                phonetic: item.phonetic || '',
                adding: false,
                wordBookId: selectedBookId.value
            }))
            console.log('JSON 解析成功，词条数:', recognizedList.value.length)
            return
        }
    } catch (e) {
        console.log('非 JSON 格式，使用文本解析')
    }

    // 2. 兜底：纯文本格式解析（兼容旧版 OCR 结果）
    // 按行分割，每行尝试提取英文和中文
    const lines = text.split('\n').filter(line => line.trim() !== '')

    lines.forEach((line, index) => {
        let english = ''
        let chinese = ''
        let phonetic = ''

        // 提取音标（/.../ 格式）
        const phoneticMatch = line.match(/\/[^/]+\//)
        if (phoneticMatch) {
            phonetic = phoneticMatch[0]
            line = line.replace(phonetic, '').trim()
        }

        // 按不同分隔符分割英文和中文
        if (line.includes(':')) {
            // 冒号分隔：english: 中文释义
            const parts = line.split(':')
            english = parts[0].trim()
            chinese = parts.slice(1).join(':').trim()
        }
        else if (line.includes('  ')) {
            // 多空格分隔：english  中文释义
            const parts = line.split(/\s{2,}/)
            english = parts[0].trim()
            chinese = parts.slice(1).join(' ').trim()
        }
        else if (line.includes(' ')) {
            // 单空格分隔：取第一个空格前后
            const firstSpaceIndex = line.indexOf(' ')
            english = line.substring(0, firstSpaceIndex).trim()
            chinese = line.substring(firstSpaceIndex + 1).trim()
        }
        else {
            // 无分隔符：整行当作英文
            english = line.trim()
        }

        // 清理英文：移除音标和词性标注残留
        english = english.replace(/\/[^/]+\//g, '').trim()  // 移除音标
        english = english.replace(/\s+[nvadjp]+\.?$/i, '').trim()  // 移除词性

        // 修复粘连词组
        if (english === 'stealtheshow') english = 'steal the show'

        if (english) {
            recognizedList.value.push({
                id: index,
                english,
                chinese,
                phonetic,
                adding: false,
                wordBookId: selectedBookId.value
            })
        }
    })

    // 3. 过滤无效词条（标题、太短的文本等）
    recognizedList.value = recognizedList.value.filter(word => {
        const lowerEnglish = word.english.toLowerCase()
        // 过滤常见标题词
        if (['word tips', 'vocabulary', 'words', '单词', '词汇'].includes(lowerEnglish)) {
            return false
        }
        // 英文长度至少 2 个字符
        return word.english && word.english.length >= 2
    })

    console.log('文本解析完成，词条数:', recognizedList.value.length)
}

// ==================== 词条操作 ====================
// 移除单个词条（从识别结果列表中删除）
const removeWord = (index) => {
    recognizedList.value.splice(index, 1)
}

// 添加单个单词到词库
const addSingleWord = async (word, index) => {
    if (!word.wordBookId) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (!word.english || !word.chinese) {
        ElMessage.warning('请填写英文和中文')
        return
    }

    word.adding = true

    const typeMap = { 'word': 1, 'phrase': 2, 'sentence': 3 }
    const wordType = typeMap[word.wordType] || 1

    const wordData = {
        wordBookId: word.wordBookId,
        english: word.english,
        chinese: word.chinese,
        phonetic: word.phonetic || '',
        wordType: wordType
    }

    try {
        const response = await addWords(wordData)
        if (response.code === 200) {
            ElMessage.success(`"${word.english}" 添加成功`)
            recognizedList.value.splice(index, 1)
        } else {
            ElMessage.error(response.msg || '添加失败')
        }
    } catch (error) {
        console.error('添加失败:', error)
        ElMessage.error('添加失败')
    } finally {
        word.adding = false
    }
}

// ==================== 批量添加所有词条 ====================
// 将识别结果中的所有词条批量导入到选定的词库中
const addAllWords = async () => {
    if (!selectedBookId.value) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (recognizedList.value.length === 0) {
        ElMessage.warning('没有可添加的单词')
        return
    }

    const invalidWords = recognizedList.value.filter(w => !w.english || !w.chinese)
    if (invalidWords.length > 0) {
        ElMessage.warning(`有 ${invalidWords.length} 个词条缺少英文或中文，请补充完整`)
        return
    }

    batchAdding.value = true

    // 类型映射：前端字符串 → 后端数字
    const typeMap = { 'word': 1, 'phrase': 2, 'sentence': 3 }
    const batchData = recognizedList.value.map(word => ({
        wordBookId: selectedBookId.value,
        english: word.english,
        chinese: word.chinese,
        phonetic: word.phonetic || '',
        wordType: typeMap[word.wordType] || 1
    }))

    try {
        const response = await batchAddWords(batchData)
        if (response.code === 200) {
            ElMessage.success(`成功添加 ${batchData.length} 个词条`)
            recognizedList.value = []
        } else {
            ElMessage.error(response.msg || '批量添加失败')
        }
    } catch (error) {
        console.error('批量添加失败:', error)
        ElMessage.error('批量添加失败')
    } finally {
        batchAdding.value = false
    }
}

// ==================== 加载词库选项 ====================
// 获取当前用户的所有词库，用于下拉选择
const loadBookOptions = async () => {
    try {
        const response = await listWordBooks({
            pageNum: 1,
            pageSize: 100,
            userId: currentUserId.value
        })
        if (response.code === 200) {
            bookOptions.value = response.rows || []
            if (bookOptions.value.length > 0) {
                selectedBookId.value = bookOptions.value[0].id
                // 加载第一个词库的预览
                loadBookPreview(selectedBookId.value)
            }
        }
    } catch (error) {
        console.error('加载词库失败:', error)
    }
}


// 词库切换时加载预览
const onBookChange = (bookId) => {
    if (bookId) {
        loadBookPreview(bookId)
    }
}

// 加载词库预览数据
const loadBookPreview = async (bookId) => {
    try {
        const response = await listWords({
            wordBookId: bookId,
            pageNum: 1,
            pageSize: 10
        })
        if (response.code === 200) {
            const items = response.rows || []

            // 统计各类型数量（需要获取全部数据统计，这里简化处理）
            let wordCount = 0, phraseCount = 0, sentenceCount = 0
            items.forEach(item => {
                if (item.wordType === 1) wordCount++
                else if (item.wordType === 2) phraseCount++
                else if (item.wordType === 3) sentenceCount++
            })

            bookPreview.value = {
                total: response.total || 0,
                wordCount,
                phraseCount,
                sentenceCount,
                items: items.slice(0, 5) // 只显示前5条
            }
        }
    } catch (error) {
        console.error('加载词库预览失败:', error)
    }
}

// 获取类型图标
const getTypeIcon = (type) => {
    if (type === 1) return '📝'
    if (type === 2) return '📚'
    return '💬'
}

// 获取类型样式类
const getTypeClass = (type) => {
    if (type === 1) return 'type-word'
    if (type === 2) return 'type-phrase'
    return 'type-sentence'
}

// 跳转到词库管理
const goToVocabulary = () => {
    router.push('/front/english/vocabulary')
}

// 一键复制
const copyContent = async () => {
    const text = resultViewMode.value === 'json' ? formattedStreamJson.value : JSON.stringify(recognizedList.value, null, 2)
    try {
        await navigator.clipboard.writeText(text)
        ElMessage.success('已复制到剪贴板')
    } catch {
        ElMessage.error('复制失败')
    }
}



onMounted(() => {
    loadBookOptions()
})
</script>

<style scoped lang="scss">
.ocr-page {
    min-height: 100vh;
    background: #f5f7fa;
    display: flex;
    flex-direction: column;

    .page-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e4e7ed;

        .header-left {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #666;
            cursor: pointer;
            font-size: 15px;

            &:hover {
                color: #409eff;
            }
        }

        .header-title {
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
        }

        .header-right {
            .word-count {
                font-size: 14px;
                color: #409eff;
                font-weight: 500;
            }
        }
    }

    .image-section {
        padding: 20px;
        background: #fff;
        margin-bottom: 12px;

        .upload-wrapper {
            .ocr-upload {
                width: 100%;
            }

            .upload-area {
                width: 100%;
                min-height: 200px;
                background: #fafafa;
                border-radius: 16px;
                border: 2px dashed #e4e7ed;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

                &:hover {
                    border-color: #b3d8ff;
                    background: #f0f7ff;
                }

                .upload-text {
                    font-size: 15px;
                    color: #666;
                    margin-top: 8px;
                }

                .upload-hint {
                    font-size: 12px;
                    color: #bbb;
                    margin-top: 4px;
                }
            }

            .image-preview {
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid #e4e7ed;
                background: #fafafa;

                .preview-container {
                    padding: 12px;

                    .preview-toolbar {
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        margin-bottom: 12px;

                        .zoom-text {
                            font-size: 13px;
                            color: #666;
                            font-weight: 500;
                            background: #f0f0f0;
                            padding: 4px 10px;
                            border-radius: 8px;
                        }
                    }

                    .draggable-container {
                        width: 100%;
                        height: 280px;
                        overflow: hidden;
                        border-radius: 12px;
                        background: #f5f5f5;
                        position: relative;

                        .preview-image {
                            width: 100%;
                            height: 100%;
                            transition: transform 0.05s ease;
                            transform-origin: center center;

                            :deep(img) {
                                object-fit: contain;
                                pointer-events: none;
                            }
                        }
                    }
                }

                .preview-actions {
                    display: flex;
                    gap: 12px;
                    justify-content: center;
                    padding: 16px;
                    background: #fff;
                    border-top: 1px solid #e4e7ed;

                    .el-button {
                        flex: 1;
                        max-width: 120px;
                        border-radius: 8px;
                    }
                }
            }
        }
    }

    .book-select-section {
        padding: 0 20px 20px;
        background: #fff;
        margin-bottom: 12px;

        .select-label {
            font-size: 14px;
            font-weight: 500;
            color: #333;
            margin-bottom: 8px;
        }

        .book-preview {
            margin-top: 16px;
            border: 1px solid #e4e7ed;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

            .preview-header {
                display: flex;
                align-items: center;
                padding: 12px 16px;
                background: #f8fafc;
                cursor: pointer;

                .preview-title {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    font-weight: 500;
                    color: #333;
                }

                .preview-stats {
                    display: flex;
                    gap: 16px;
                    margin-left: 16px;
                    font-size: 13px;

                    .stat-word {
                        color: #409eff;
                    }

                    .stat-phrase {
                        color: #67c23a;
                    }

                    .stat-sentence {
                        color: #e6a23c;
                    }
                }

                .preview-arrow {
                    margin-left: auto;
                    color: #999;
                    transition: transform 0.3s;

                    &.expanded {
                        transform: rotate(180deg);
                    }
                }
            }

            .preview-content {
                border-top: 1px solid #e4e7ed;
                background: #fff;

                .preview-list {
                    max-height: 250px;
                    overflow-y: auto;

                    .preview-item {
                        display: flex;
                        align-items: center;
                        padding: 10px 16px;
                        border-bottom: 1px solid #f5f5f5;

                        .item-type {
                            margin-right: 10px;
                        }

                        .item-english {
                            flex: 1;
                            font-weight: 500;
                            color: #333;
                        }

                        .item-chinese {
                            color: #666;
                            margin-left: 12px;
                        }
                    }
                }

                .preview-footer {
                    padding: 10px 16px;
                    text-align: center;
                    border-top: 1px solid #e4e7ed;
                }
            }
        }
    }

    .result-section {
        flex: 1;
        background: #fff;
        border-radius: 16px 16px 0 0;
        padding: 20px;
        border: 1px solid #e4e7ed;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

        .result-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;

            .header-actions {
                display: flex;
                align-items: center;
                gap: 8px;

                .copy-btn {
                    color: #909399;
                    padding: 6px;
                    border-radius: 6px;
                    transition: all 0.2s;

                    &:hover {
                        color: #409eff;
                        background: #ecf5ff;
                    }
                }
            }
        }

        .word-list {
            display: flex;
            flex-direction: column;
            gap: 16px;

            .word-card {
                background: #fff;
                border-radius: 16px;
                padding: 16px;
                border: 1px solid #e4e7ed;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

                .card-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 12px;

                    .word-index {
                        width: 28px;
                        height: 28px;
                        background: linear-gradient(135deg, #409eff, #66b1ff);
                        color: #fff;
                        border-radius: 8px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 14px;
                        font-weight: 600;
                    }

                    .header-center {
                        flex: 1;
                        display: flex;
                        justify-content: center;

                        .word-type-badge {
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            width: 28px;
                            height: 28px;
                            background: #f0f0f0;
                            border-radius: 8px;
                            color: #666;
                            cursor: default;
                        }
                    }
                }

                .card-body {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;

                    .word-input {
                        :deep(.el-input__wrapper) {
                            border-radius: 8px;
                            background: #fff;
                        }
                    }
                }

                .card-footer {
                    margin-top: 16px;
                    display: flex;
                    justify-content: flex-end;

                    .el-button {
                        border-radius: 8px;
                    }
                }
            }
        }

        // JSON 视图
        .json-view {
            .json-content {
                background: #f8fafc;
                color: #1e293b;
                padding: 20px;
                border-radius: 12px;
                border: 1px solid #e2e8f0;
                font-family: 'JetBrains Mono', 'Fira Code', 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 13px;
                line-height: 1.7;
                white-space: pre-wrap;
                word-break: break-all;
                overflow-x: auto;
                max-height: 500px;
                overflow-y: auto;
            }
        }
    }

    .empty-state,
    .loading-state {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 12px;
        color: #bbb;
        font-size: 14px;
    }

    .loading-state {
        color: #409eff;
    }

    // 流式识别中
    .stream-loading {
        margin: 12px 0;
        background: #fff;
        border-radius: 16px;
        border: 1px solid #e4e7ed;
        overflow: hidden;

        .stream-loading-header {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 16px;
            background: #f0f7ff;
            border-bottom: 1px solid #e4e7ed;
            font-size: 14px;
            font-weight: 500;
            color: #409eff;

            .is-loading {
                animation: rotating 1s linear infinite;
            }
        }

        .stream-loading-body {
            max-height: 300px;
            overflow-y: auto;
            padding: 16px;

            pre {
                margin: 0;
                font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 13px;
                line-height: 1.6;
                white-space: pre-wrap;
                word-break: break-all;
                color: #333;
            }
        }
    }

    @keyframes rotating {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
}
</style>

<!-- 新增：全局样式，用于模态框 -->
<style lang="scss">
.image-editor-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    background: rgba(0, 0, 0, 0.8) !important;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    z-index: 99999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 20px !important;
    box-sizing: border-box !important;

    .editor-container {
        width: 90vw;
        max-width: 900px;
        max-height: 85vh;
        background: #1a1a1a;
        border-radius: 20px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        margin: 0 auto;

        .editor-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            flex-shrink: 0;

            .editor-title {
                font-size: 16px;
                font-weight: 500;
                color: #fff;
            }

            .close-btn {
                font-size: 20px;
                color: rgba(255, 255, 255, 0.7);
                cursor: pointer;
                transition: color 0.2s;

                &:hover {
                    color: #fff;
                }
            }
        }

        .editor-body {
            flex: 1;
            min-height: 300px;
            max-height: 60vh;
            background: #2a2a2a;
            overflow: hidden;

            .vue-advanced-cropper {
                background: #2a2a2a;
                width: 100%;
                height: 100%;

                // 控制点样式 - 确保所有点都可见
                :deep(.vue-advanced-cropper__handler) {
                    width: 12px !important;
                    height: 12px !important;
                    background: #409eff !important;
                    border: 2px solid #fff !important;
                    border-radius: 50% !important;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                }
            }
        }

        .editor-toolbar {
            display: flex;
            align-items: center;
            justify-content: center;
            flex-wrap: wrap;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            flex-shrink: 0;

            .el-button-group {
                .el-button {
                    background: rgba(255, 255, 255, 0.1);
                    border: none;
                    color: #fff;

                    &:hover {
                        background: rgba(255, 255, 255, 0.2);
                    }
                }
            }
        }

        .editor-footer {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            flex-shrink: 0;

            .el-button {
                padding: 10px 24px;
                border-radius: 24px;
            }
        }
    }
}
</style>