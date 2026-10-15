<template>
  <div class="tool-page">
    <div class="back-bar">
      <el-button class="back-btn" size="small" @click="$router.push('/front/tools')">
        <el-icon>
          <ArrowLeft />
        </el-icon>
        返回工具箱
      </el-button>
    </div>

    <div class="tool-container">
      <div class="tool-header">
        <h2 class="tool-title">图片处理工具</h2>
        <p class="tool-desc">上传图片进行裁剪、旋转、缩放、翻转</p>
      </div>

      <div class="upload-section" v-if="!imageUrl">
        <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :show-file-list="false"
          accept="image/png,image/jpeg,image/jpg" :on-change="handleFileChange" :on-exceed="handleExceed" drag
          class="upload-area">
          <el-icon class="upload-icon">
            <UploadFilled />
          </el-icon>
          <div class="upload-text">点击或拖拽上传图片</div>
          <div class="upload-hint">支持 PNG、JPG 格式，不超过 50MB</div>
        </el-upload>
      </div>

      <div v-else class="preview-section">
        <ImageEditor v-model:visible="showEditor" :src="imageUrl" @save="handleSave" @cancel="handleCancel" />

        <div class="result-section" v-if="resultUrl">
          <div class="result-label">裁剪结果预览</div>
          <img :src="resultUrl" class="result-image" />
          <el-button class="download-btn" :icon="Download" @click="downloadResult">下载图片</el-button>
        </div>

        <div class="action-bar">
          <el-button class="action-btn" @click="showEditor = true">打开图片编辑器</el-button>
          <el-button class="action-btn" @click="removeImage">重新上传</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, UploadFilled, Download } from '@element-plus/icons-vue'
import ImageEditor from '@/components/ImageEditor/index.vue'

const imageUrl = ref('')
const resultUrl = ref('')
const showEditor = ref(false)
let objectUrl = ''

const handleFileChange = (file) => {
  const isValidType = ['image/png', 'image/jpeg', 'image/jpg'].includes(file.raw.type)
  if (!isValidType) {
    ElMessage.error('只支持 PNG、JPG 格式的图片')
    return
  }
  const isLt50M = file.size / 1024 / 1024 < 50
  if (!isLt50M) {
    ElMessage.error('图片大小不能超过 50MB')
    return
  }
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = URL.createObjectURL(file.raw)
  imageUrl.value = objectUrl
  showEditor.value = true
}

const handleExceed = () => {
  ElMessage.warning('最多只能上传 1 张图片')
}

const handleSave = (blob) => {
  if (blob) {
    if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
    resultUrl.value = URL.createObjectURL(blob)
    ElMessage.success('图片处理完成')
  }
}

const handleCancel = () => {
  if (!resultUrl.value) {
    removeImage()
  }
}

const removeImage = () => {
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
  imageUrl.value = ''
  resultUrl.value = ''
}

const downloadResult = () => {
  if (!resultUrl.value) return
  const a = document.createElement('a')
  a.href = resultUrl.value
  a.download = 'edited_image.png'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<style scoped lang="scss">
.tool-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;

  .back-bar {
    margin-bottom: 20px;

    .back-btn {
      border-radius: 8px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-1px);
      }
    }
  }

  .tool-container {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 32px;
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

  .upload-section {
    display: flex;
    justify-content: center;

    .upload-area {
      width: 100%;
      max-width: 500px;

      :deep(.el-upload-dragger) {
        padding: 60px 40px;
        border-radius: 12px;
        border: 2px dashed #d1d5db;
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
  }

  .action-bar {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-top: 24px;

    .action-btn {
      border-radius: 8px;
      font-weight: 500;
      padding: 8px 20px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-2px);
      }
    }
  }

  .result-section {
    text-align: center;
    margin-top: 24px;

    .result-label {
      font-size: 14px;
      font-weight: 500;
      color: #374151;
      margin-bottom: 12px;
    }

    .result-image {
      max-width: 100%;
      max-height: 400px;
      border-radius: 8px;
      border: 1px solid #e5e7eb;
      margin-bottom: 16px;
    }

    .download-btn {
      border-radius: 8px;
      font-weight: 500;
      padding: 8px 20px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-2px);
      }
    }
  }
}
</style>