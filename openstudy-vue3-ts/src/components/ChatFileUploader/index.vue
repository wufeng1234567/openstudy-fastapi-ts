<template>
  <div class="chat-file-uploader">
    <!-- 隐藏的原生文件选择器，由回形针按钮触发（模仿 DS 网页） -->
    <input ref="fileInputRef" type="file" :accept="ACCEPT" multiple style="display: none"
      @change="handleChange" />

    <el-tooltip content="上传图片或文件（Word / PDF / md / txt），也可以直接把文件拖进输入框" placement="top" :show-after="150">
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

/**
 * 与后端 `file_parser.parse_file` **真实支持**的格式对齐
 *
 * ⚠️ 2026-10-22 修：这里原来抄的是 DS 网页端的接受列表（ppt/pptx/xls/xlsx/
 * csv/json/py/java/go…），但本系统的解析器只认 Word / PDF / 纯文本。
 * 结果是用户兴冲冲拖进来一个 .xlsx，选文件框里能选中、上传后却「解析失败」——
 * 前端给了个不该给的承诺。现在 accept 只列真支持的，
 * 并在 `addFiles` 里对不支持的格式直接挡掉、说清楚原因。
 */
const ACCEPT = [
  // 图片（走多模态，不经过 file_parser）
  'image/*',
  // 文档（file_parser 支持）
  '.pdf', '.doc', '.docx',
  // 文本（file_parser 按纯文本读）
  '.txt', '.md', '.markdown'
].join(',')

/** 后端 `KB_FILE_EXTENSIONS` 同源口径（不含图片 —— 图片走另一条通道） */
const DOC_EXTS = ['pdf', 'doc', 'docx', 'txt', 'md', 'markdown']

const isSupportedDoc = (file: File): boolean => {
  if (file.type.startsWith('image/')) return true
  const dot = file.name.lastIndexOf('.')
  if (dot < 0) return false
  return DOC_EXTS.includes(file.name.slice(dot + 1).toLowerCase())
}

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

/*
 * 暴露给上层（放在文件末尾 —— `addFiles` 是 const 声明，
 * 在它之前调用会命中 TDZ 报错，不能图省事放上面）：
 *   · `openPicker()` —— 让别处也能唤起文件选择框。
 *     场景：新对话页里那张「上传资料」卡片 —— 点它应该**直接弹文件选择框**，
 *     而不是往对话里发一句"把这资料变成题库"、然后等 AI 反问"哪份资料？"。
 *   · `addFiles()` —— 让上层把**拖进来的文件**塞进来（见 chat.vue 的整页拖拽区）。
 *     把「读文件 / 压缩 / 校验 / 计数」这摊事留在本组件，上层只管把 File[] 递进来，
 *     这样拖拽和点选走的是**同一条**处理路径，不会出现「拖进来能传、点选不能传」这类分叉。
 */

const readAsDataURL = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })

/** 点选文件：把 input 的 FileList 交给 addFiles，并清空 input 以便重选同一个文件 */
const handleChange = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) addFiles(files)
}

/**
 * 把一批文件加进附件区（点选与拖拽的**共用**入口）
 *
 * 这里同时承担校验：数量上限、单文件体积、图片压缩。
 * 上层（chat.vue 的拖拽区）只负责把 File[] 递进来，不要再重复校验一遍。
 */
const addFiles = async (files: File[]) => {
  if (!files.length) return

  const next: ChatAttachments = {
    images: [...props.modelValue.images],
    files: [...props.modelValue.files]
  }

  for (const file of files) {
    // 先挡掉后端解析不了的格式（.xlsx/.pptx/代码文件等），别让它白传一趟
    if (!isSupportedDoc(file)) {
      ElMessage.warning(`${file.name} 这个格式读不了，支持图片 / Word / PDF / Markdown / TXT`)
      continue
    }

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

// 必须在 addFiles 定义之后（见上方注释）
defineExpose({ openPicker: pick, addFiles })
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
