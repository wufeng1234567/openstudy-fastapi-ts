<template>
    <el-dialog v-model="visible" title="拍照识词" :width="dialogWidth" :close-on-click-modal="false" destroy-on-close
        @closed="handleClosed">
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
                        <el-button @click="rotateImage" :icon="RefreshRight">旋转</el-button>
                        <el-button @click="exportCurrentImage" :icon="Download">导出</el-button>
                        <el-button type="danger" plain @click="removeImage" :icon="Delete">删除</el-button>
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

        <!-- 流式识别中 -->
        <div class="stream-loading" v-if="recognizing">
            <div class="stream-loading-header">
                <el-icon class="is-loading" :size="18">
                    <Loading />
                </el-icon>
                <span>AI 识别中...</span>
            </div>
            <div class="stream-loading-body">
                <pre>{{ streamContent }}</pre>
            </div>
        </div>

        <!-- 识别结果（双视图） -->
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

        <template #footer>
            <el-button @click="handleClose">关闭</el-button>
        </template>
    </el-dialog>

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
                        <el-button @click="rotate(-90)" :icon="RefreshLeft">左转</el-button>
                        <el-button @click="rotate(90)" :icon="RefreshRight">右转</el-button>
                        <el-button @click="flip('horizontal')">
                            <el-icon>
                                <Switch />
                            </el-icon>
                            翻转
                        </el-button>
                    </el-button-group>

                    <el-button-group style="margin-left: 12px;">
                        <el-button @click="zoomIn" :icon="ZoomIn">放大</el-button>
                        <el-button @click="zoomOut" :icon="ZoomOut">缩小</el-button>
                        <el-button @click="resetCropper" :icon="Refresh">重置</el-button>
                    </el-button-group>
                </div>

                <div class="editor-footer">
                    <el-button @click="exportImage" :icon="Download">导出</el-button>
                    <div style="flex: 1"></div>
                    <el-button @click="closeEditor">取消</el-button>
                    <el-button type="primary" @click="applyCrop">应用裁剪</el-button>
                </div>
            </div>
        </div>
    </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
    Camera, Search, Picture, Delete, Plus, Loading,
    RefreshRight, ZoomIn, ZoomOut, Refresh, Close, Switch, Download,
    Document, Collection, ChatLineSquare, RefreshLeft, DocumentCopy
} from '@element-plus/icons-vue'
import { getToken } from '@/utils/auth'
import { ocrRecognize, ocrRecognizeStream } from '@/api/english/ocr'
import { addWords, batchAddWords } from '@/api/words/words'
import { Cropper } from 'vue-advanced-cropper'
import 'vue-advanced-cropper/dist/style.css'

const props = defineProps({
    modelValue: {
        type: Boolean,
        default: false
    },
    wordBookId: {
        type: [String, Number],
        default: null
    },
    width: {
        type: String,
        default: '800px'
    }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
})

const dialogWidth = computed(() => props.width)

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

// 流式输出相关
const streamContent = ref('')
const resultViewMode = ref('words') // 'words' | 'json'

// 格式化后的 JSON
const formattedStreamJson = computed(() => {
    if (!streamContent.value) return ''
    try {
        let jsonStr = streamContent.value
            .replace(/```json\s*/g, '')
            .replace(/```\s*/g, '')
            .trim()
        const parsed = JSON.parse(jsonStr)
        return JSON.stringify(parsed, null, 2)
    } catch (e) {
        return streamContent.value
    }
})

// 图片编辑相关
const editorVisible = ref(false)
const editorImageUrl = ref('')
const cropperRef = ref(null)
const rotation = ref(0)
const editedImageFile = ref(null)
const imageScale = ref(1)
const imagePosition = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const startDragPosition = ref({ x: 0, y: 0 })
const defaultSize = ref({ width: 400, height: 400 })

// 裁剪框配置
const stencilProps = ref({
    aspectRatio: null,
    movable: true,
    resizable: true,
    handlers: {
        north: true, south: true, west: true, east: true,
        northWest: true, northEast: true, southWest: true, southEast: true
    }
})

// 自定义尺寸限制
const sizeRestrictionsAlgorithm = () => ({
    minWidth: 10, minHeight: 10, maxWidth: 5000, maxHeight: 5000
})

// 获取类型文本
const getTypeText = (type) => {
    const map = { 'word': '单词', 'phrase': '词组', 'sentence': '句子' }
    return map[type] || '单词'
}

// 重置数据
const resetData = () => {
    imageUrl.value = ''
    selectedFile.value = null
    recognizedList.value = []
    recognizing.value = false
    rotation.value = 0
    editedImageFile.value = null
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
    uploadRef.value?.clearFiles()
}

// 关闭对话框
const handleClose = () => {
    visible.value = false
}

const handleClosed = () => {
    resetData()
}

// 上传前校验并压缩图片
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
    compressImage(file).then(compressedFile => {
        selectedFile.value = compressedFile
    })
    return true
}

// 图片压缩函数
const compressImage = (file) => {
    return new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = (e) => {
            const img = new Image()
            img.onload = () => {
                const canvas = document.createElement('canvas')
                const ctx = canvas.getContext('2d')

                // 最大宽度/高度限制
                const maxWidth = 1920
                const maxHeight = 1920
                let width = img.width
                let height = img.height

                if (width > maxWidth || height > maxHeight) {
                    const ratio = Math.min(maxWidth / width, maxHeight / height)
                    width = Math.round(width * ratio)
                    height = Math.round(height * ratio)
                }

                canvas.width = width
                canvas.height = height
                ctx.drawImage(img, 0, 0, width, height)

                canvas.toBlob(
                    (blob) => {
                        const compressedFile = new File([blob], file.name, {
                            type: 'image/jpeg',
                            lastModified: Date.now()
                        })
                        console.log(`图片压缩: ${file.size / 1024}KB -> ${compressedFile.size / 1024}KB (${Math.round(compressedFile.size / file.size * 100)}%)`)
                        resolve(compressedFile)
                    },
                    'image/jpeg',
                    0.85
                )
            }
            img.src = e.target.result
        }
        reader.readAsDataURL(file)
    })
}

const handleUploadError = () => ElMessage.error('图片上传失败')

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

// 开始识别（流式）
const startRecognize = async () => {
    if (!selectedFile.value) {
        ElMessage.warning('请先上传图片')
        return
    }

    recognizing.value = true
    recognizedList.value = []
    streamContent.value = ''
    resultViewMode.value = 'words'

    ocrRecognizeStream(
        selectedFile.value,
        (fullContent) => {
            streamContent.value = fullContent
        },
        (fullContent) => {
            streamContent.value = fullContent
            recognizing.value = false
            parseStreamResult(fullContent)
        },
        (error) => {
            console.error('OCR流式识别失败:', error)
            ElMessage.error('识别请求失败')
            recognizing.value = false
        }
    )
}

// 解析流式结果
const parseStreamResult = (content) => {
    if (!content) return
    try {
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
        console.log('流式结果不是标准 JSON，尝试文本解析')
        parseOcrResult(content)
    }
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

const parseOcrResultFromWords = (words) => {
    recognizedList.value = words.map((item, index) => ({
        id: index,
        english: item.english || '',
        chinese: item.chinese || '',
        phonetic: item.phonetic || '',
        wordType: item.type || 'word',
        adding: false
    }))
}

// 文本解析兜底
const parseOcrResult = (text) => {
    if (!text) return
    const lines = text.split('\n').filter(line => line.trim())
    const entries = []
    lines.forEach((line, index) => {
        let english = '', chinese = '', phonetic = ''
        const phoneticMatch = line.match(/\/[^/]+\//)
        if (phoneticMatch) { phonetic = phoneticMatch[0]; line = line.replace(phonetic, '').trim() }
        if (line.includes(':')) { const parts = line.split(':'); english = parts[0].trim(); chinese = parts.slice(1).join(':').trim() }
        else if (line.includes('  ')) { const parts = line.split(/\s{2,}/); english = parts[0].trim(); chinese = parts.slice(1).join(' ').trim() }
        else { english = line.trim() }
        if (english && english.length >= 2) entries.push({ id: index, english, chinese, phonetic, wordType: 'word', adding: false })
    })
    recognizedList.value = entries
}

const removeWord = (index) => recognizedList.value.splice(index, 1)

// 添加单个单词
const addSingleWord = async (word, index) => {
    if (!props.wordBookId) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (!word.english || !word.chinese) {
        ElMessage.warning('请填写英文和中文')
        return
    }

    word.adding = true

    const typeMap = { 'word': 1, 'phrase': 2, 'sentence': 3 }
    const wordData = {
        wordBookId: props.wordBookId,
        english: word.english,
        chinese: word.chinese,
        phonetic: word.phonetic || '',
        wordType: typeMap[word.wordType] || 1
    }

    try {
        const response = await addWords(wordData)
        if (response.code === 200) {
            ElMessage.success(`"${word.english}" 添加成功`)
            recognizedList.value.splice(index, 1)
            emit('success')
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

// 批量添加
const addAllWords = async () => {
    if (!props.wordBookId) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (recognizedList.value.length === 0) {
        ElMessage.warning('没有可添加的单词')
        return
    }

    const invalidWords = recognizedList.value.filter(w => !w.english || !w.chinese)
    if (invalidWords.length > 0) {
        ElMessage.warning(`有 ${invalidWords.length} 个词条缺少英文或中文`)
        return
    }

    batchAdding.value = true

    const typeMap = { 'word': 1, 'phrase': 2, 'sentence': 3 }
    const batchData = recognizedList.value.map(word => ({
        wordBookId: props.wordBookId,
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
            emit('success')
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

// ========== 图片编辑方法 ==========
const openEditor = () => {
    if (!imageUrl.value) return
    editorImageUrl.value = imageUrl.value
    editorVisible.value = true
}

const closeEditor = () => { editorVisible.value = false }

const rotate = (angle) => cropperRef.value?.rotate(angle)
const flip = (direction) => cropperRef.value?.flip(true, direction === 'horizontal')
const zoomIn = () => cropperRef.value?.zoom(1.2)
const zoomOut = () => cropperRef.value?.zoom(0.8)
const resetCropper = () => cropperRef.value?.reset()
const onCropChange = () => { }

const applyCrop = () => {
    if (!cropperRef.value) return
    const result = cropperRef.value.getResult()
    const canvas = result.canvas
    if (canvas) {
        const editedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = editedUrl
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'edited_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)
        rotation.value = 0
        imageScale.value = 1
        imagePosition.value = { x: 0, y: 0 }
        ElMessage.success('图片已保存')
        closeEditor()
    }
}

const exportImage = () => {
    if (!cropperRef.value) return
    const result = cropperRef.value.getResult()
    const canvas = result.canvas
    if (canvas) {
        const link = document.createElement('a')
        link.download = `edited_image_${Date.now()}.jpg`
        link.href = canvas.toDataURL('image/jpeg', 0.9)
        link.click()
        ElMessage.success('图片已导出')
    }
}

const exportCurrentImage = () => {
    if (!imageUrl.value) return
    if (editedImageFile.value) {
        const url = URL.createObjectURL(editedImageFile.value)
        const link = document.createElement('a')
        link.download = editedImageFile.value.name || `image_${Date.now()}.jpg`
        link.href = url
        link.click()
        URL.revokeObjectURL(url)
    } else {
        const link = document.createElement('a')
        link.download = `image_${Date.now()}.jpg`
        link.href = imageUrl.value
        link.click()
    }
    ElMessage.success('图片已导出')
}

const rotateImage = () => {
    rotation.value = (rotation.value + 90) % 360
    if (!imageUrl.value) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl.value
    img.onload = () => {
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')
        if (rotation.value === 90 || rotation.value === 270) {
            canvas.width = img.height
            canvas.height = img.width
        } else {
            canvas.width = img.width
            canvas.height = img.height
        }
        ctx.translate(canvas.width / 2, canvas.height / 2)
        ctx.rotate(rotation.value * Math.PI / 180)
        ctx.drawImage(img, -img.width / 2, -img.height / 2)
        const rotatedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = rotatedUrl
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'rotated_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)
    }
}

// 拖拽缩放
const startDrag = (e) => {
    isDragging.value = true
    startDragPosition.value = { x: e.clientX - imagePosition.value.x, y: e.clientY - imagePosition.value.y }
    e.preventDefault()
}
const onDrag = (e) => {
    if (!isDragging.value) return
    imagePosition.value = { x: e.clientX - startDragPosition.value.x, y: e.clientY - startDragPosition.value.y }
}
const stopDrag = () => { isDragging.value = false }
const onWheel = (e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = imageScale.value + delta
    if (newScale >= 0.5 && newScale <= 3) imageScale.value = newScale
}
</script>

<style scoped lang="scss">
.image-section {
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
                    justify-content: flex-end;
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

                    .dblclick-hint {
                        position: absolute;
                        top: 12px;
                        right: 12px;
                        display: flex;
                        align-items: center;
                        gap: 6px;
                        padding: 6px 12px;
                        background: rgba(64, 158, 255, 0.15);
                        border-radius: 8px;
                        font-size: 12px;
                        color: #409eff;
                        z-index: 5;
                        pointer-events: none;
                    }

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

// 流式识别中
.stream-loading {
    margin-top: 16px;
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e4e7ed;
    overflow: hidden;

    .stream-loading-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 14px;
        background: #f0f7ff;
        border-bottom: 1px solid #e4e7ed;
        font-size: 13px;
        font-weight: 500;
        color: #409eff;

        .is-loading { animation: rotating 1s linear infinite; }
    }

    .stream-loading-body {
        max-height: 200px;
        overflow-y: auto;
        padding: 12px;

        pre {
            margin: 0;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-all;
            color: #333;
        }
    }
}

.result-section {
    margin-top: 16px;

    .result-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;

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

    // JSON 视图
    .json-view {
        .json-content {
            background: #f8fafc;
            color: #1e293b;
            padding: 16px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            font-family: 'JetBrains Mono', 'Fira Code', 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 13px;
            line-height: 1.7;
            white-space: pre-wrap;
            word-break: break-all;
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }
    }

    .word-list {
        display: flex;
        flex-direction: column;
        gap: 16px;
        max-height: 350px;
        overflow-y: auto;
        padding: 4px;

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
                    }
                }
            }

            .card-body {
                display: flex;
                flex-direction: column;
                gap: 12px;

                .word-input :deep(.el-input__wrapper) {
                    border-radius: 8px;
                    background: #fff;
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
}

.empty-state,
.loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 0;
    color: #bbb;
    gap: 12px;
}

.loading-state {
    color: #409eff;
}

@keyframes rotating {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
</style>

<style lang="scss">
.image-editor-modal {
    position: fixed !important;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.8) !important;
    backdrop-filter: blur(12px);
    z-index: 99999 !important;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    box-sizing: border-box;

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

        .editor-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);

            .editor-title {
                font-size: 16px;
                font-weight: 500;
                color: #fff;
            }

            .close-btn {
                font-size: 20px;
                color: rgba(255, 255, 255, 0.7);
                cursor: pointer;

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

                :deep(.vue-advanced-cropper__handler) {
                    width: 12px !important;
                    height: 12px !important;
                    background: #409eff !important;
                    border: 2px solid #fff !important;
                    border-radius: 50% !important;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
                    opacity: 1 !important;
                }
            }
        }

        .editor-toolbar {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);

            .el-button-group .el-button {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: #fff;

                &:hover {
                    background: rgba(255, 255, 255, 0.2);
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

            .el-button {
                padding: 10px 24px;
                border-radius: 24px;
            }
        }
    }
}
</style>