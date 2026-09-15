<template>
    <div class="resources-page">
        <div class="back-bar">
            <el-button class="back-btn" size="small" @click="$router.push('/front/tools')">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                返回工具箱
            </el-button>
        </div>

        <div class="watermark-card">
            <div class="tool-header">
                <h2 class="tool-title">图片水印工具</h2>
                <p class="tool-desc">为图片添加文字水印，支持旋转、透明度调整</p>
            </div>

            <div class="card-body">
                <div class="control-panel">
                    <div class="panel-section">
                        <div class="section-title">水印文本</div>
                        <el-input v-model="watermarkText" type="textarea" :rows="2" placeholder="请输入水印文本"
                            resize="none" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">
                            字体大小 <span class="value-label">{{ fontSize }}px</span>
                        </div>
                        <el-slider v-model="fontSize" :min="12" :max="120" :step="1" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">文字颜色</div>
                        <el-color-picker v-model="textColor" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">
                            透明度 <span class="value-label">{{ opacity }}%</span>
                        </div>
                        <el-slider v-model="opacity" :min="0" :max="100" :step="1" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">
                            旋转角度 <span class="value-label">{{ rotation }}°</span>
                        </div>
                        <el-slider v-model="rotation" :min="-90" :max="90" :step="1" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">
                            水平间距 <span class="value-label">{{ horizontalSpacing }}px</span>
                        </div>
                        <el-slider v-model="horizontalSpacing" :min="100" :max="800" :step="10" />
                    </div>

                    <div class="panel-section">
                        <div class="section-title">
                            垂直间距 <span class="value-label">{{ verticalSpacing }}px</span>
                        </div>
                        <el-slider v-model="verticalSpacing" :min="100" :max="800" :step="10" />
                    </div>

                    <div class="panel-actions">
                        <el-button type="primary" :icon="Download" @click="exportImage" :disabled="!imageUrl">
                            下载水印图片
                        </el-button>
                    </div>
                </div>

                <div class="preview-panel">
                    <div class="preview-toolbar" v-if="imageUrl">
                        <span class="zoom-info">{{ Math.round(scale * 100) }}%</span>
                        <el-button size="small" :icon="Refresh" @click="resetTransform">重置</el-button>
                        <el-button size="small" type="danger" :icon="Delete" @click="removeImage">删除图片</el-button>
                    </div>

                    <div class="preview-container" ref="previewContainerRef" @mousedown="startDrag" @mousemove="onDrag"
                        @mouseup="stopDrag" @mouseleave="stopDrag" @wheel.prevent="onWheel">
                        <el-upload v-if="!imageUrl" ref="uploadRef" :auto-upload="false" :limit="1"
                            :show-file-list="false" accept="image/png,image/jpeg,image/jpg,image/gif"
                            :on-change="handleFileChange" :on-exceed="handleExceed" drag class="upload-area">
                            <el-icon class="upload-icon">
                                <Upload />
                            </el-icon>
                            <div class="upload-text">点击或拖拽上传图片</div>
                            <div class="upload-hint">支持 PNG、JPG、GIF 格式，不超过 20MB</div>
                        </el-upload>

                        <div v-if="imageUrl" class="image-wrapper">
                            <div class="transform-container" :style="transformContainerStyle">
                                <img ref="imageRef" :src="imageUrl" class="preview-image" @load="onImageLoad" />
                                <canvas ref="watermarkCanvasRef" class="watermark-canvas" :width="naturalWidth"
                                    :height="naturalHeight" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontResources' })
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload, Delete, Download, Refresh, ArrowLeft } from '@element-plus/icons-vue'

const uploadRef = ref(null)
const previewContainerRef = ref(null)
const imageRef = ref(null)
const watermarkCanvasRef = ref(null)

const imageUrl = ref('')
const imageFile = ref(null)
const naturalWidth = ref(0)
const naturalHeight = ref(0)
let objectUrl = ''

const watermarkText = ref('刘诗塬 2550308182 2025级软专5班')
const fontSize = ref(40)
const textColor = ref('#000000')
const opacity = ref(30)
const rotation = ref(-30)
const horizontalSpacing = ref(300)
const verticalSpacing = ref(300)

const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const isDragging = ref(false)
const dragStart = reactive({ x: 0, y: 0 })

const transformContainerStyle = computed(() => ({
    transform: `scale(${scale.value}) translate(${translateX.value}px, ${translateY.value}px)`,
    transformOrigin: 'top left'
}))

function handleFileChange(file) {
    const isValidType = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif'].includes(file.raw.type)
    if (!isValidType) {
        ElMessage.error('只支持 PNG、JPG、GIF 格式的图片')
        return
    }
    const isLt20M = file.size / 1024 / 1024 < 20
    if (!isLt20M) {
        ElMessage.error('图片大小不能超过 20MB')
        return
    }
    if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
    }
    objectUrl = URL.createObjectURL(file.raw)
    imageUrl.value = objectUrl
    imageFile.value = file.raw
    resetTransform()
}

function handleExceed() {
    ElMessage.warning('最多只能上传 1 张图片')
}

function onImageLoad() {
    if (imageRef.value) {
        naturalWidth.value = imageRef.value.naturalWidth
        naturalHeight.value = imageRef.value.naturalHeight
        autoFitImage()
        drawWatermark()
    }
}

function autoFitImage() {
    if (!imageRef.value || !previewContainerRef.value) return
    const containerWidth = previewContainerRef.value.clientWidth
    const containerHeight = previewContainerRef.value.clientHeight
    const imgWidth = naturalWidth.value
    const imgHeight = naturalHeight.value

    const scaleX = containerWidth / imgWidth
    const scaleY = containerHeight / imgHeight
    scale.value = Math.min(scaleX, scaleY, 1)

    const scaledWidth = imgWidth * scale.value
    const scaledHeight = imgHeight * scale.value
    translateX.value = (containerWidth - scaledWidth) / 2 / scale.value
    translateY.value = (containerHeight - scaledHeight) / 2 / scale.value
}

function resetTransform() {
    autoFitImage()
}

function startDrag(e) {
    if (!imageUrl.value) return
    isDragging.value = true
    dragStart.x = e.clientX - translateX.value * scale.value
    dragStart.y = e.clientY - translateY.value * scale.value
    e.preventDefault()
}

function onDrag(e) {
    if (!isDragging.value) return
    translateX.value = (e.clientX - dragStart.x) / scale.value
    translateY.value = (e.clientY - dragStart.y) / scale.value
}

function stopDrag() {
    isDragging.value = false
}

function onWheel(e) {
    if (!imageUrl.value) return
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = Math.max(0.1, Math.min(5, scale.value + delta))
    scale.value = newScale
}

function removeImage() {
    if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
        objectUrl = ''
    }
    imageUrl.value = ''
    imageFile.value = null
    naturalWidth.value = 0
    naturalHeight.value = 0
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
}

function drawWatermark() {
    const canvas = watermarkCanvasRef.value
    if (!canvas || !imageUrl.value) return

    const ctx = canvas.getContext('2d')
    const width = canvas.width
    const height = canvas.height

    ctx.clearRect(0, 0, width, height)
    ctx.save()

    const alpha = opacity.value / 100
    ctx.fillStyle = textColor.value
    ctx.globalAlpha = alpha
    ctx.font = `${fontSize.value}px sans-serif`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'

    const textMetrics = ctx.measureText(watermarkText.value)
    const textWidth = textMetrics.width
    const textHeight = fontSize.value

    const cosR = Math.cos(rotation.value * Math.PI / 180)
    const sinR = Math.sin(rotation.value * Math.PI / 180)

    ctx.translate(width / 2, height / 2)
    ctx.rotate(rotation.value * Math.PI / 180)
    ctx.translate(-width / 2, -height / 2)

    const diagonal = Math.sqrt(width * width + height * height)
    const startX = -diagonal / 2
    const startY = -diagonal / 2
    const endX = width + diagonal / 2
    const endY = height + diagonal / 2

    for (let y = startY; y < endY; y += textHeight + verticalSpacing.value) {
        for (let x = startX; x < endX; x += textWidth + horizontalSpacing.value) {
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(rotation.value * Math.PI / 180)
            ctx.fillText(watermarkText.value, 0, 0)
            ctx.restore()
        }
    }

    ctx.restore()
}

function exportImage() {
    if (!imageUrl.value || !imageFile.value) {
        ElMessage.error('请先上传图片')
        return
    }

    const img = new Image()
    img.onload = () => {
        const exportCanvas = document.createElement('canvas')
        exportCanvas.width = img.naturalWidth
        exportCanvas.height = img.naturalHeight
        const ctx = exportCanvas.getContext('2d')

        ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight)

        const alpha = opacity.value / 100
        ctx.fillStyle = textColor.value
        ctx.globalAlpha = alpha
        ctx.font = `${fontSize.value}px sans-serif`
        ctx.textAlign = 'left'
        ctx.textBaseline = 'top'

        const textMetrics = ctx.measureText(watermarkText.value)
        const textWidth = textMetrics.width
        const textHeight = fontSize.value

        const width = img.naturalWidth
        const height = img.naturalHeight

        const diagonal = Math.sqrt(width * width + height * height)
        const startX = -diagonal / 2
        const startY = -diagonal / 2
        const endX = width + diagonal / 2
        const endY = height + diagonal / 2

        for (let y = startY; y < endY; y += textHeight + verticalSpacing.value) {
            for (let x = startX; x < endX; x += textWidth + horizontalSpacing.value) {
                ctx.save()
                ctx.translate(x, y)
                ctx.rotate(rotation.value * Math.PI / 180)
                ctx.fillText(watermarkText.value, 0, 0)
                ctx.restore()
            }
        }

        exportCanvas.toBlob((blob) => {
            if (!blob) {
                ElMessage.error('导出失败')
                return
            }
            const downloadUrl = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = downloadUrl
            link.download = 'watermarked_image.png'
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(downloadUrl)
            ElMessage.success('图片已下载')
        }, 'image/png')
    }
    img.src = imageUrl.value
}

watch([watermarkText, fontSize, textColor, opacity, rotation, horizontalSpacing, verticalSpacing], () => {
    if (imageUrl.value) {
        drawWatermark()
    }
})

watch(imageUrl, (newVal) => {
    if (newVal) {
        setTimeout(drawWatermark, 50)
    }
})

onMounted(() => {
    window.addEventListener('resize', autoFitImage)
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', autoFitImage)
    if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
    }
})
</script>

<style scoped lang="scss">
:root {
    --primary-50: #eef2ff;
    --primary-100: #e0e7ff;
    --primary-500: #6366f1;
    --primary-600: #4f46e5;
    --primary-700: #4338ca;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-900: #111827;
}

.resources-page {
    min-height: calc(100vh - 200px);
    padding: 24px;
    // margin-bottom: 240px;

    .back-bar {
        margin-bottom: 16px;

        .back-btn {
            border-radius: 8px;
            color: #6b7280;
            background: #fff;
            border: 1px solid #e5e7eb;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin-left: 20px;
            margin-bottom: 5px;

            &:hover {
                border-color: #d1d5db;
                color: #4b5563;
                transform: translateY(-1px);
            }
        }
    }
}

.watermark-card {
    background: white;
    border-radius: 16px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    padding: 32px;
    max-width: 900px;
    margin: 0 auto;
}

.tool-header {
    text-align: center;
    margin-bottom: 32px;

    .tool-title {
        font-size: 20px;
        font-weight: 700;
        color: #1f2937;
        margin: 0 0 8px 0;
    }

    .tool-desc {
        font-size: 14px;
        color: #6b7280;
        margin: 0;
    }
}

.card-body {
    display: flex;
    min-height: 400px;

    @media (max-width: 1024px) {
        flex-direction: column;
    }
}

.control-panel {
    width: 320px;
    padding: 20px 24px;
    border-right: 1px solid #e5e7eb;
    overflow-y: auto;
    max-height: calc(100vh - 320px);

    @media (max-width: 1024px) {
        width: 100%;
        max-height: none;
        border-right: none;
        border-bottom: 1px solid #e5e7eb;
    }
}

.panel-section {
    margin-bottom: 20px;

    .section-title {
        font-size: 14px;
        font-weight: 500;
        color: #374151;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;

        .value-label {
            font-weight: 400;
            color: #6b7280;
        }
    }
}

.panel-actions {
    margin-top: 32px;

    .el-button {
        width: 100%;
    }
}

.preview-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;

    @media (max-width: 1024px) {
        min-height: 400px;
    }
}

.preview-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;

    .zoom-info {
        font-size: 13px;
        color: #6b7280;
        font-weight: 500;
        background: #f3f4f6;
        padding: 4px 10px;
        border-radius: 6px;
    }
}

.preview-container {
    flex: 1;
    background: #f3f4f6;
    overflow: hidden;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;

    &:active {
        cursor: grabbing;
    }
}

.upload-area {
    width: 100%;
    height: 100%;
    min-height: 400px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
    border: 2px dashed #d1d5db;
    border-radius: 12px;
    margin: 24px;
    transition: all 0.3s ease;

    &:hover {
        border-color: #b3d8ff;
        background: #f0f7ff;
    }

    :deep(.el-upload-dragger) {
        padding: 60px 40px;
        background: transparent;
        border: none;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    .upload-icon {
        font-size: 48px;
        color: #9ca3af;
        margin-bottom: 16px;
    }

    .upload-text {
        font-size: 16px;
        color: #374151;
        margin-bottom: 8px;
    }

    .upload-hint {
        font-size: 13px;
        color: #9ca3af;
    }
}

.image-wrapper {
    position: relative;
    display: inline-block;
}

.transform-container {
    position: relative;
    transition: transform 0.05s linear;
}

.preview-image {
    display: block;
    max-width: none;
    user-select: none;
}

.watermark-canvas {
    position: absolute;
    top: 0;
    left: 0;
    pointer-events: none;
    max-width: none;
}
</style>