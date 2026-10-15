<template>
  <div class="chat-file-uploader">
    <!-- 隐藏的原生文件选择器，由回形针按钮触发（模仿 DS 网页） -->
    <input ref="fileInputRef" type="file" :accept="ACCEPT" multiple style="display: none"
      @change="handleFiles" />

    <el-tooltip content="上传图片或文件（Word / PDF / md / txt 等）" placement="top" :show-after="150">
      <button type="button" class="upload-btn" :disabled="disabled" @click="pick">
        <!-- 回形针图标，与 DS 网页端的附件按钮一致 -->
        <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" class="upload-icon">
          <path
            d="M5.5498 9.75V5H6.9502V9.75C6.9502 10.3299 7.4201 10.7998 8 10.7998C8.5799 10.7998 9.0498 10.3299 9.0498 9.75V4.5C9.0498 2.9536 7.7964 1.7002 6.25 1.7002C4.7036 1.7002 3.4502 2.9536 3.4502 4.5V9.75C3.4502 12.2629 5.4871 14.2998 8 14.2998C10.5129 14.2998 12.5498 12.2629 12.5498 9.75V4H13.9502V9.75C13.9502 13.0361 11.2861 15.7002 8 15.7002C4.71391 15.7002 2.0498 13.0361 2.0498 9.75V4.5C2.04981 2.1804 3.9304 0.299806 6.25 0.299805C8.5696 0.299805 10.4502 2.1804 10.4502 4.5V9.75C10.4502 11.1031 9.3531 12.2002 8 12.2002C6.6469 12.2002 5.5498 11.1031 5.5498 9.75Z"
            fill="currentColor" />
        </svg>
        <span v-if="total" class="count">{{ total }}</span>
      </button>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { compressImageDataUrl, dataUrlByteSize, humanSize } from '@/utils/image-compress'

/**
 * 聊天附件上传按钮（模仿 DS 网页端的单一「上传文件」按钮）
 *
 * 只负责「选文件 → 读成 data URL → 更新 v-model」；
 * **预览条的渲染在 ChatAttachmentList**（放在输入框上方，见 AiChatStream 的
 * #input-header 插槽），这样才和 DS 网页端一致：附件显示在输入框上方。
 *
 * 支持图片 + 文档（Word / PDF / md / txt 等），不走后端上传；由扩展代交给 DS 网页端：
 *   · 图片 → images 通道，扩展塞进 DS 的 <input type="file">
 *   · 其它文件 → files 通道（fileDataList），扩展按文件附件处理
 *
 * 图片会先本地压缩（长边 1600 / JPEG 逐档降质），原因见 utils/image-compress.ts：
 * 原图 base64 会撑爆扩展的 IPC 通道，表现为「无法连接到 DeepSeek 页面」。
 */

export interface ChatAttachment {
  name: string
  type: string
  /** 完整 data URL */
  base64: string
}

export type ChatAttachments = { images: ChatAttachment[]; files: ChatAttachment[] }

/** 与 DS 网页端接受的类型对齐（取其常用子集，避免 accept 串过长） */
const ACCEPT = [
  // 图片
  'image/*',
  // 文档
  '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
  // 文本 / 数据
  '.txt', '.md', '.csv', '.tsv', '.json', '.xml', '.yaml', '.yml', '.log',
  '.html', '.htm', '.css', '.js', '.ts', '.jsx', '.tsx', '.vue',
  // 代码
  '.py', '.java', '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.sql', '.sh', '.bat'
].join(',')

const MAX_IMAGE_COUNT = 6
const MAX_FILE_COUNT = 6
/** 选图时的原始体积上限（压缩后会小很多） */
const MAX_IMAGE_MB = 20
const MAX_FILE_MB = 10
/** 压缩后仍然超过这个体积就提醒用户（避免撑爆扩展通道） */
const WARN_AFTER_COMPRESS_MB = 3

const props = defineProps({
  modelValue: {
    type: Object as () => ChatAttachments,
    default: () => ({ images: [], files: [] })
  },
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue'])

const fileInputRef = ref<HTMLInputElement | null>(null)

const total = computed(() => (props.modelValue.images?.length || 0) + (props.modelValue.files?.length || 0))

const pick = () => {
  if (props.disabled) return
  fileInputRef.value?.click()
}

const readAsDataURL = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })

const handleFiles = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  // 立刻清空，保证同一个文件连续选择两次也能触发 change
  input.value = ''
  if (!files.length) return

  const next: ChatAttachments = {
    images: [...props.modelValue.images],
    files: [...props.modelValue.files]
  }

  for (const file of files) {
    const isImage = file.type.startsWith('image/')
    const list = isImage ? next.images : next.files
    const maxCount = isImage ? MAX_IMAGE_COUNT : MAX_FILE_COUNT
    const maxMb = isImage ? MAX_IMAGE_MB : MAX_FILE_MB

    if (list.length >= maxCount) {
      ElMessage.warning(`${isImage ? '图片' : '文件'}最多 ${maxCount} 个`)
      continue
    }
    if (file.size > maxMb * 1024 * 1024) {
      ElMessage.warning(`${file.name} 超过 ${maxMb}MB，已跳过`)
      continue
    }
    try {
      let base64 = await readAsDataURL(file)
      if (isImage) {
        const before = dataUrlByteSize(base64)
        base64 = await compressImageDataUrl(base64)
        const after = dataUrlByteSize(base64)
        if (after > WARN_AFTER_COMPRESS_MB * 1024 * 1024) {
          ElMessage.warning(`${file.name} 压缩后仍有 ${humanSize(after)}，可能上传失败，建议换小一点的图`)
        } else if (before - after > 200 * 1024) {
          console.debug(`[file-upload] 压缩 ${file.name}: ${humanSize(before)} → ${humanSize(after)}`)
        }
      }
      list.push({ name: file.name, type: file.type || 'application/octet-stream', base64 })
    } catch (err) {
      console.warn('[file-upload] 读取失败:', file.name, err)
      ElMessage.error(`${file.name} 读取失败`)
    }
  }

  emit('update:modelValue', next)
}
</script>

<style scoped>
.chat-file-uploader {
  display: inline-flex;
  align-items: center;
}

.upload-btn {
  position: relative;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.upload-btn:hover:not(:disabled) {
  background: #eef1f5;
  color: #6b7280;
}

.upload-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.upload-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.count {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 8px;
  background: #409eff;
  color: #fff;
  font-size: 10px;
  line-height: 15px;
  text-align: center;
}
</style>
