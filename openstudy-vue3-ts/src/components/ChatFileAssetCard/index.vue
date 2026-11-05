<!--
  对话文件 / 图片资产卡
  ----------------------------------------------------------------------------
  背景：`chat_file_manage` 的返回原本被当成通用 JSON 塞进「查看详情」，用户看到的是
  imageId / fileId / mimeType / url 这种调试字段。这个组件的职责是把**输出契约**
  翻译成用户能用的东西：

    · 文件：文件名 + 类型 + 大小 + 上传时间；点击打开文档预览
    · 图片：缩略图 + 图片名 + 大小 + 上传时间；点击打开大图
    · 不展示内部 id / mimeType / url（这些只留在「查看详情」里）

  判据认数据形状（files / images），不认工具名，后续任何工具吐出同形状都能复用。
-->
<template>
  <div v-if="hasItems" class="cf-card" :class="{ 'is-expanded': expanded, 'has-sticky': hasMore }">
    <!--
      长清单的标题栏就是吸顶条（与 AgentDraftCard / AgentConfirmCard 同一套交互）：
        · 不额外再画一行标题，避免「标题 + 吸顶条」重复出现；
        · 展开时 sticky 在消息流顶部，滚到列表中部也能一键收起；
        · 收起后退回普通文档流，卡片只剩很短一截，不需要再吸顶。
      展开态由 useCollapseBar 的 COLLAPSE_BAR_STYLE 提供 top，抵消聊天列表的 padding-top。
    -->
    <div v-if="hasMore" class="cf-sticky" :class="{ 'is-collapsed': !expanded }"
      :style="expanded ? COLLAPSE_BAR_STYLE : undefined">
      <span class="cf-sticky__label">{{ title }}</span>
      <span class="cf-count">{{ total }} 项</span>
      <button type="button" class="cf-sticky__btn" @click="expanded = !expanded">
        {{ expanded ? '收起' : `展开全部（${total}）` }}
      </button>
    </div>

    <div v-else class="cf-head">
      <span class="cf-title">{{ title }}</span>
      <span class="cf-count">{{ total }} 项</span>
    </div>

    <div v-if="visibleFiles.length" class="cf-files">
      <button v-for="file in visibleFiles" :key="`f-${file.fileId || file.fileName}`" type="button" class="cf-file"
        @click="openFile(file)">
        <span class="cf-file__icon">
          <OsIcon name="file-text" :size="17" />
        </span>
        <span class="cf-file__main">
          <span class="cf-file__name">{{ file.fileName }}</span>
          <span class="cf-file__meta">
            {{ file.ext || '文件' }}
            <template v-if="file.size"> · {{ formatSize(file.size) }}</template>
            <template v-if="file.imageCount"> · {{ file.imageCount }} 张图</template>
            <template v-if="file.createTime"> · {{ file.createTime }}</template>
          </span>
        </span>
        <span class="cf-file__open">打开</span>
      </button>
    </div>

    <div v-if="visibleImages.length" class="cf-images">
      <button v-for="image in visibleImages" :key="`i-${image.imageId || image.imageName}`" type="button" class="cf-image"
        @click="openImage(image)">
        <img class="cf-image__thumb" :src="assetUrl(image.url)" :alt="image.imageName" loading="lazy" />
        <span class="cf-image__main">
          <span class="cf-image__name">{{ image.imageName }}</span>
          <span class="cf-image__meta">
            <template v-if="image.size">{{ formatSize(image.size) }}</template>
            <template v-if="image.createTime"> · {{ image.createTime }}</template>
          </span>
        </span>
      </button>
    </div>

    <div v-if="!expanded && hasMore" class="cf-more">
      还有 {{ total - visibleImages.length - visibleFiles.length }} 项
      <button type="button" @click="expanded = true">展开查看</button>
    </div>

    <el-dialog v-model="previewVisible" :title="previewTitle" width="860px" top="4vh" append-to-body
      destroy-on-close class="cf-preview-dialog">
      <div v-if="previewItem" class="cf-preview">
        <DocxPreview v-if="previewKind === 'docx'" :url="assetUrl(previewItem.url)"
          :title="previewTitle" :height="620" />
        <iframe v-else-if="previewKind === 'pdf'" class="cf-preview__pdf" :src="assetUrl(previewItem.url)"
          title="PDF 预览" />
        <div v-else class="cf-preview__fallback">
          <OsIcon name="file-text" :size="30" />
          <p>这个文件暂不支持在线预览</p>
          <a :href="assetUrl(previewItem.url)" target="_blank" rel="noopener">下载文件</a>
        </div>
      </div>
    </el-dialog>

    <!-- 与站内题目/练习共用同一个缩放预览组件 -->
    <ImageViewer v-model:visible="imageViewerVisible" :src="imageViewerSrc" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'
import DocxPreview from '@/components/DocxPreview/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'
import { COLLAPSE_BAR_STYLE } from '@/composables/useCollapseBar'

defineOptions({ name: 'ChatFileAssetCard' })

const props = defineProps<{
  data: Record<string, any>
}>()

const previewVisible = ref(false)
const previewItem = ref<any>(null)
const previewKind = ref<'docx' | 'pdf' | 'other'>('other')
const imageViewerVisible = ref(false)
const imageViewerSrc = ref('')
const expanded = ref(false)

// 默认只露前几项，避免一次把 20 张图铺满整个对话
const COLLAPSED_IMAGES = 3
const COLLAPSED_FILES = 2

const files = computed<any[]>(() => {
  if (Array.isArray(props.data?.files)) return props.data.files
  if (props.data?.fileId && props.data?.fileName) return [props.data]
  return []
})

const images = computed<any[]>(() => {
  if (Array.isArray(props.data?.images)) return props.data.images
  if (props.data?.imageId && props.data?.imageName) return [props.data]
  return []
})

const total = computed(() => files.value.length + images.value.length)
const hasItems = computed(() => total.value > 0)
const title = computed(() => {
  if (files.value.length && images.value.length) return '对话文件与图片'
  return images.value.length ? '对话图片' : '对话文件'
})
const visibleFiles = computed(() => expanded.value ? files.value : files.value.slice(0, COLLAPSED_FILES))
const visibleImages = computed(() => expanded.value ? images.value : images.value.slice(0, COLLAPSED_IMAGES))
const hasMore = computed(() => total.value > COLLAPSED_IMAGES + COLLAPSED_FILES
  || (files.value.length > COLLAPSED_FILES || images.value.length > COLLAPSED_IMAGES))

watch(
  () => props.data,
  () => { expanded.value = false },
  { deep: true }
)

const previewTitle = computed(() => {
  const item = previewItem.value
  return String(item?.fileName || item?.imageName || '文件预览')
})

function assetUrl(url: string): string {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : `/${value}`)
}

function formatSize(bytes: any): string {
  const n = Number(bytes || 0)
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function detectKind(item: any): 'image' | 'docx' | 'pdf' | 'other' {
  const mime = String(item?.mimeType || '').toLowerCase()
  const ext = String(item?.ext || item?.fileName || item?.imageName || '').toLowerCase()
  if (mime.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/.test(ext)) return 'image'
  if (mime.includes('pdf') || ext.endsWith('.pdf')) return 'pdf'
  if (mime.includes('word') || ext.endsWith('.docx') || ext.endsWith('.doc')) return 'docx'
  return 'other'
}

function openImage(image: any) {
  imageViewerSrc.value = assetUrl(image.url)
  imageViewerVisible.value = true
}

function openFile(file: any) {
  if (detectKind(file) === 'image') {
    openImage({ ...file, url: file.url })
    return
  }
  previewItem.value = file
  previewKind.value = detectKind(file) as 'docx' | 'pdf' | 'other'
  previewVisible.value = true
}
</script>

<style scoped>
.cf-card {
  margin-top: 10px;
  padding: 10px 12px 11px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #fbfdff;
}

/* 有吸顶条时顶部不再留 padding：让吸顶条天然贴住卡片上边框，避免圆角处露缝 */
.cf-card.has-sticky {
  padding-top: 0;
}

.cf-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.cf-title {
  color: #1e3a5f;
  font-size: 12px;
  font-weight: 700;
}

.cf-count {
  color: #9ca3af;
  font-size: 10px;
}

.cf-toggle {
  margin-left: auto;
  padding: 2px 7px;
  border: 1px solid #dbeafe;
  border-radius: 5px;
  background: #fff;
  color: #2563eb;
  font-size: 10px;
  cursor: pointer;
}

.cf-toggle:hover {
  border-color: #2563eb;
  background: #eff6ff;
}

.cf-sticky {
  display: flex;
  align-items: center;
  gap: 8px;
  /* 通栏到卡片左右边缘，滚动时底下内容不会从两侧透出来 */
  margin: 0 -12px 0;
  padding: 9px 12px;
  border-bottom: 1px solid #e6eefb;
  border-radius: 9px 9px 0 0;
  background: rgba(251, 253, 255, 0.97);
  box-shadow: 0 3px 12px rgba(30, 58, 95, 0.08);
  backdrop-filter: blur(6px);
}

/* 展开时吸顶条与下方列表保持间距；收起后它就等同于卡片标题，不再额外留白 */
.cf-sticky:not(.is-collapsed) {
  margin-bottom: 8px;
}

.cf-sticky.is-collapsed {
  position: static;
  border-bottom: none;
  border-radius: 9px;
  box-shadow: none;
}

.cf-sticky__label {
  color: #1e3a5f;
  font-size: 12px;
  font-weight: 700;
}

.cf-sticky__btn {
  margin-left: auto;
  padding: 3px 9px;
  border: 0;
  border-radius: 5px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 10.5px;
  cursor: pointer;
}

.cf-sticky__btn:hover {
  background: #dbeafe;
}

.cf-more {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
  color: #9ca3af;
  font-size: 10px;
}

.cf-more button {
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 10px;
  cursor: pointer;
}

.cf-files {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.cf-file {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.cf-file:hover {
  border-color: #93c5fd;
  background: #f8fbff;
}

.cf-file__icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex: none;
  place-items: center;
  border-radius: 6px;
  background: #eff6ff;
  color: #2563eb;
}

.cf-file__main {
  min-width: 0;
}

.cf-file__name {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cf-file__meta {
  display: block;
  margin-top: 2px;
  color: #9ca3af;
  font-size: 10px;
}

.cf-file__open {
  flex: none;
  margin-left: auto;
  color: #2563eb;
  font-size: 10.5px;
}

.cf-images {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
  gap: 7px;
  margin-top: 7px;
}

.cf-image {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 5px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #fff;
  text-align: left;
  cursor: zoom-in;
}

.cf-image:hover {
  border-color: #93c5fd;
  background: #f8fbff;
}

.cf-image__thumb {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 5px;
  object-fit: cover;
  background: #f3f4f6;
}

.cf-image__main {
  min-width: 0;
}

.cf-image__name {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 11px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cf-image__meta {
  display: block;
  margin-top: 2px;
  color: #9ca3af;
  font-size: 9.5px;
}

.cf-preview {
  min-height: 180px;
}

.cf-preview__image {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  margin: 0 auto;
  border-radius: 6px;
}

.cf-preview__pdf {
  width: 100%;
  height: 68vh;
  border: 0;
}

.cf-preview__fallback {
  padding: 50px 20px;
  color: #9ca3af;
  text-align: center;
}

.cf-preview__fallback p {
  margin: 8px 0 10px;
  font-size: 12px;
}

.cf-preview__fallback a {
  color: #2563eb;
  font-size: 12px;
}
</style>
