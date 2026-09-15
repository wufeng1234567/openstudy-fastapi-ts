<template>
  <div class="app-container">
    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span>OCR图片上传测试</span>
        </div>
      </template>
      
      <!-- 图片预览区域 -->
      <div class="image-preview" v-if="imageUrl">
        <div class="image-item">
          <el-image 
            :src="imageUrl" 
            fit="cover" 
            class="image-preview-img" 
          />
          <el-button 
            type="danger" 
            size="small" 
            @click="removeImage"
            icon="Delete"
          >删除</el-button>
        </div>
      </div>
      
      <!-- 上传按钮区域 -->
      <div class="upload-actions">
        <el-button 
          type="primary" 
          @click="insertImage"
          icon="Plus"
          :disabled="uploading"
        >选择图片</el-button>
        <el-button 
          type="success" 
          @click="submitForOCR"
          :disabled="!imageUrl || uploading"
          icon="Upload"
        >进行OCR识别</el-button>
      </div>
      
      <!-- 隐藏的上传组件 -->
      <el-upload 
        ref="imageUpload" 
        :action="uploadFileUrl" 
        :headers="headers" 
        :on-success="handleImageSuccess"
        :on-error="handleImageError" 
        :before-upload="beforeImageUpload" 
        :limit="1" 
        list-type="text"
        style="display: none;"
      >
      </el-upload>
      
      <!-- OCR识别结果 -->
      <div class="ocr-result" v-if="ocrResult">
        <el-divider>OCR识别结果</el-divider>
        <el-input 
          type="textarea" 
          :rows="6" 
          v-model="ocrResult" 
          readonly
        ></el-input>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'OCRUplodTest' })
import { ref } from 'vue'
import { ocrRecognize } from '@/api/ocr/ocr'
import { getToken } from "@/utils/auth"
import { ElMessage } from 'element-plus'

const imageUpload = ref(null)
const uploadFileUrl = ref(import.meta.env.VITE_APP_BASE_API + "/common/upload")
const baseUrl = import.meta.env.VITE_APP_BASE_API
const headers = ref({ Authorization: "Bearer " + getToken() })

// 图片URL
const imageUrl = ref('')
// OCR识别结果
const ocrResult = ref('')
// 上传状态
const uploading = ref(false)
// 存储实际的文件对象
const selectedFile = ref(null)

// 插入图片 - 打开文件选择器
const insertImage = () => {
  imageUpload.value.$el.querySelector('input').click()
}

// 图片上传成功处理
const handleImageSuccess = (response, file) => {
  if (response.code === 200) {
    const imageUrlPath = response.fileName
    imageUrl.value = `${baseUrl}${imageUrlPath}`
    ElMessage.success('图片上传成功')
  } else {
    ElMessage.error(response.msg)
  }
  uploading.value = false
  // 清除上传组件的文件列表
  imageUpload.value.clearFiles()
}
// 图片上传失败处理
const handleImageError = (err, file) => {
  ElMessage.error('图片上传失败')
  uploading.value = false
  // 清除上传组件的文件列表
  imageUpload.value.clearFiles()
}


// 上传前检查
const beforeImageUpload = (file) => {
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    ElMessage.error('只能上传图片文件!')
    return false
  }
  
  const isLt10M = file.size / 1024 / 1024 < 10
  if (!isLt10M) {
    ElMessage.error('图片大小不能超过 10MB!')
    return false
  }
  
  // 保存实际的文件对象
  selectedFile.value = file
  uploading.value = true
  return true
}

// 删除图片
const removeImage = () => {
  imageUrl.value = ''
  ocrResult.value = ''
  selectedFile.value = null
  ElMessage.info('图片已删除')
  // 清除上传组件的文件列表
  imageUpload.value.clearFiles()
}

// 提交图片进行OCR识别
const submitForOCR = () => {
  if (!imageUrl.value || !selectedFile.value) {
    ElMessage.warning('请先选择图片')
    return
  }
  
  uploading.value = true
  ocrResult.value = ''
  
  // 构造正确的FormData对象
  const formData = new FormData()
  // 添加真实的文件对象
  formData.append('file', selectedFile.value)
  
  // 调用OCR接口
  ocrRecognize(formData).then(response => {
    if (response.code === 200) {
      // 根据实际返回结果调整
      ocrResult.value = response.data ? JSON.stringify(response.data, null, 2) : '识别成功但无结果'
      ElMessage.success('OCR识别成功')
    } else {
      ElMessage.error(response.msg || 'OCR识别失败')
    }
    uploading.value = false
  }).catch(error => {
    ElMessage.error('OCR识别请求失败: ' + error.message)
    uploading.value = false
  })
}
</script>

<style scoped>
.upload-card {
  margin-bottom: 20px;
}

.card-header {
  font-weight: bold;
  font-size: 16px;
}

.image-preview {
  margin: 20px 0;
  min-height: 120px;
}

.image-item {
  display: inline-block;
  position: relative;
}

.image-preview-img {
  max-width: 300px;
  max-height: 300px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.image-item .el-button {
  position: absolute;
  top: 5px;
  right: 5px;
}

.upload-actions {
  margin: 20px 0;
}

.upload-actions .el-button {
  margin-right: 10px;
}

.ocr-result {
  margin-top: 20px;
}
</style>