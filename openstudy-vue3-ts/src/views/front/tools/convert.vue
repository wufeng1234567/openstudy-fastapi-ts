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
        <h2 class="tool-title">文档转换工具</h2>
        <p class="tool-desc">PDF、Word、MD、TXT 格式相互转换</p>
      </div>

      <div class="convert-layout">
        <div class="upload-section">
          <div class="section-title">上传文件</div>
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :show-file-list="false"
            accept=".pdf,.doc,.docx,.md,.txt" :on-change="handleFileChange" :on-exceed="handleExceed"
            drag class="upload-area">
            <el-icon class="upload-icon">
              <UploadFilled />
            </el-icon>
            <div class="upload-text">点击或拖拽上传文件</div>
            <div class="upload-hint">支持 PDF、Word、MD、TXT 格式，不超过 50MB</div>
          </el-upload>

          <div v-if="uploadedFile" class="file-info">
            <el-tag closable @close="removeFile" class="file-tag">
              {{ uploadedFile.name }}
            </el-tag>
          </div>
        </div>

        <div class="format-section">
          <div class="format-row">
            <div class="format-field">
              <div class="section-title">来源格式</div>
              <el-select v-model="sourceFormat" placeholder="选择来源格式" style="width: 100%">
                <el-option v-for="fmt in formats" :key="fmt.value" :label="fmt.label" :value="fmt.value" />
              </el-select>
            </div>
            <div class="swap-icon">
              <el-button class="swap-btn" :icon="Refresh" circle @click="swapFormats" />
            </div>
            <div class="format-field">
              <div class="section-title">目标格式</div>
              <el-select v-model="targetFormat" placeholder="选择目标格式" style="width: 100%">
                <el-option v-for="fmt in filteredTargetFormats" :key="fmt.value" :label="fmt.label"
                  :value="fmt.value" />
              </el-select>
            </div>
          </div>
        </div>

        <div class="convert-section">
          <div class="supported-list">
            <div class="supported-title">支持转换类型</div>
            <div class="format-list">
              <el-tag v-for="item in supportPairs" :key="item" size="small" class="support-tag">{{ item }}</el-tag>
            </div>
          </div>

          <div class="button-row">
            <el-button class="convert-btn" :loading="converting" :disabled="!canConvert" @click="handleConvert">
              开始转换
            </el-button>
          </div>
        </div>

        <div v-if="resultUrl" class="result-section">
          <div class="section-title">转换结果</div>
          <div class="result-meta">
            <span class="result-name">{{ resultFileName }}</span>
          </div>
          <div class="result-actions">
            <el-button class="download-btn" :icon="Download" @click="downloadResult">下载文件</el-button>
            <el-button class="reset-btn" @click="resetAll">重新选择</el-button>
          </div>
          <div v-if="resultPreview" class="result-preview">
            <div class="preview-label">内容预览</div>
            <pre class="preview-content">{{ resultPreview }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, UploadFilled, Download, Refresh } from '@element-plus/icons-vue'
import { convertDocument } from '@/api/document/convert'

const formats = [
  { label: 'PDF', value: 'pdf' },
  { label: 'Word (docx)', value: 'docx' },
  { label: 'Markdown (md)', value: 'md' },
  { label: '纯文本 (txt)', value: 'txt' }
]

const supportPairs = [
  'PDF → TXT', 'PDF → MD',
  'Word → TXT', 'Word → MD',
  'MD → TXT', 'MD → Word',
  'TXT → MD', 'TXT → Word'
]

const sourceFormat = ref('')
const targetFormat = ref('')
const uploadedFile = ref(null)
const converting = ref(false)
const resultUrl = ref('')
const resultFileName = ref('')
const resultPreview = ref('')
const uploadRef = ref(null)

const filteredTargetFormats = computed(() => {
  return formats.filter(f => f.value !== sourceFormat.value)
})

const canConvert = computed(() => {
  return sourceFormat.value && targetFormat.value && uploadedFile.value
})

const handleFileChange = (file) => {
  const isLt50M = file.size / 1024 / 1024 < 50
  if (!isLt50M) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
  uploadedFile.value = file.raw || file
  const ext = getFileExt(uploadedFile.value.name)
  if (ext && formats.some(f => f.value === ext)) {
    sourceFormat.value = ext
  }
}

const handleExceed = () => {
  ElMessage.warning('最多只能上传 1 个文件')
}

const getFileExt = (name) => {
  const ext = name.split('.').pop().toLowerCase()
  const map = { pdf: 'pdf', doc: 'docx', docx: 'docx', md: 'md', txt: 'txt' }
  return map[ext] || null
}

const removeFile = () => {
  if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
  uploadedFile.value = null
  resultUrl.value = ''
  resultPreview.value = ''
}

const swapFormats = () => {
  if (sourceFormat.value && targetFormat.value) {
    const temp = sourceFormat.value
    sourceFormat.value = targetFormat.value
    targetFormat.value = temp
  }
}

const handleConvert = async () => {
  if (!canConvert.value) return
  converting.value = true
  try {
    const result = await convertFile(uploadedFile.value, sourceFormat.value, targetFormat.value)
    if (result) {
      resultUrl.value = result.url
      resultFileName.value = result.fileName || `converted.${targetFormat.value}`
      resultPreview.value = result.preview || ''
      ElMessage.success('转换完成')
    } else {
      ElMessage.error('转换失败')
    }
  } catch (e) {
    ElMessage.error('转换失败: ' + (e.message || '未知错误'))
  } finally {
    converting.value = false
  }
}

const convertFile = async (file, source, target) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('sourceFormat', source)
  formData.append('targetFormat', target)

  try {
    const response = await convertDocument(formData)
    const blob = new Blob([response], { type: response.type || 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const ext = target === 'docx' ? 'docx' : target
    const fileName = file.name.replace(/\.[^.]+$/, '') + '_converted.' + ext
    return {
      url,
      fileName: fileName,
      preview: ''
    }
  } catch (e) {
    console.error('转换失败:', e)
    throw e
  }
}

const downloadResult = () => {
  if (!resultUrl.value) return
  const a = document.createElement('a')
  a.href = resultUrl.value
  a.download = resultFileName.value
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

const resetAll = () => {
  if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
  uploadedFile.value = null
  sourceFormat.value = ''
  targetFormat.value = ''
  resultUrl.value = ''
  resultFileName.value = ''
  resultPreview.value = ''
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

  .section-title {
    font-size: 14px;
    font-weight: 500;
    color: #374151;
    margin-bottom: 10px;
  }

  .upload-section {
    margin-bottom: 24px;

    .upload-area {
      width: 100%;

      :deep(.el-upload-dragger) {
        padding: 40px 30px;
        border-radius: 12px;
        border: 2px dashed #d1d5db;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          border-color: #9ca3af;
        }
      }

      .upload-icon {
        font-size: 40px;
        color: #9ca3af;
        margin-bottom: 12px;
      }

      .upload-text {
        font-size: 15px;
        color: #374151;
        margin-bottom: 6px;
      }

      .upload-hint {
        font-size: 12px;
        color: #9ca3af;
      }
    }

    .file-info {
      margin-top: 12px;

      .file-tag {
        font-size: 13px;
      }
    }
  }

  .format-section {
    margin-bottom: 24px;

    .format-row {
      display: flex;
      align-items: flex-end;
      gap: 12px;

      .format-field {
        flex: 1;
      }

      .swap-icon {
        flex-shrink: 0;
        padding-bottom: 4px;

        .swap-btn {
          border-radius: 50%;
          color: #6b7280;
          background: #fff;
          border: 1px solid #e5e7eb;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

          &:hover {
            border-color: #d1d5db;
            color: #4b5563;
          }
        }
      }
    }
  }

  .convert-section {
    margin-bottom: 24px;

    .supported-list {
      margin-bottom: 20px;

      .supported-title {
        font-size: 13px;
        color: #9ca3af;
        margin-bottom: 8px;
      }

      .format-list {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;

        .support-tag {
          background: #f3f4f6;
          border-color: #e5e7eb;
          color: #6b7280;
          font-size: 12px;
        }
      }
    }

    .button-row {
      display: flex;
      gap: 12px;

      .convert-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 8px 28px;
        color: #1f2937;
        background: #fff;
        border: 1px solid #d1d5db;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          border-color: #9ca3af;
          color: #1f2937;
          transform: translateY(-2px);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }
      }
    }
  }

  .result-section {
    border-top: 1px solid #f3f4f6;
    padding-top: 24px;

    .result-meta {
      margin-bottom: 16px;

      .result-name {
        font-size: 14px;
        font-weight: 500;
        color: #1f2937;
      }
    }

    .result-actions {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;

      .download-btn,
      .reset-btn {
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

    .result-preview {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 16px;

      .preview-label {
        font-size: 13px;
        font-weight: 500;
        color: #6b7280;
        margin-bottom: 8px;
      }

      .preview-content {
        font-size: 13px;
        color: #374151;
        white-space: pre-wrap;
        word-break: break-word;
        margin: 0;
        line-height: 1.6;
      }
    }
  }
}
</style>