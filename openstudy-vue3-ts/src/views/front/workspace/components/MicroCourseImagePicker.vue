<template>
  <div class="image-picker">
    <div v-if="modelValue" class="image-picker__selected">
      <img :src="modelValue" alt="已选图片" class="image-picker__thumb" />
      <div class="image-picker__selected-main">
        <span class="image-picker__selected-label">已插入图片</span>
        <span class="image-picker__url" :title="modelValue">{{ modelValue }}</span>
      </div>
      <el-button text size="small" @click="open">更换</el-button>
    </div>
    <el-button v-else plain class="image-picker__empty" @click="open">
      <el-icon><Picture /></el-icon>
      插入图片
    </el-button>

    <el-input
      :model-value="caption"
      placeholder="图片说明（可选）"
      maxlength="100"
      class="image-picker__caption"
      @update:model-value="$emit('update:caption', $event)"
    />

    <el-dialog v-model="dialogVisible" title="插入图片" width="720px" append-to-body>
      <div class="image-picker__toolbar">
        <el-button plain :loading="uploading" @click="fileInput?.click()">
          <el-icon><Upload /></el-icon>
          上传本地图片
        </el-button>
        <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileChange" />
        <span class="image-picker__hint">也可以直接选资料里的图片</span>
      </div>

      <div v-if="images.length" class="image-picker__grid">
        <button
          v-for="(image, index) in images"
          :key="image.url"
          type="button"
          class="image-picker__item"
          :class="{ 'is-selected': modelValue === image.url }"
          @click="select(image)"
        >
          <img :src="image.url" :alt="image.label" />
          <span>{{ image.label }}</span>
        </button>
      </div>
      <el-empty v-else description="这份资料里还没有图片，可以直接上传一张" :image-size="60" />

      <div class="image-picker__url-row">
        <el-input v-model="urlDraft" placeholder="或粘贴图片 URL，例如 /profile/upload/..." clearable />
        <el-button type="primary" plain :disabled="!urlDraft.trim()" @click="useUrl">使用链接</el-button>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload } from '@element-plus/icons-vue'
import { getDocumentContent } from '@/api/ai/rag'
import { uploadImage } from '@/api/common/common'

const props = defineProps<{
  modelValue: string
  caption: string
  docId?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'update:caption', value: string): void
}>()

const dialogVisible = ref(false)
const uploading = ref(false)
const images = ref<Array<{ url: string; label: string }>>([])
const urlDraft = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

watch(
  () => props.docId,
  async (docId) => {
    if (!docId) return
    try {
      const res: any = await getDocumentContent(docId)
      const map = res.data?.imageMap || {}
      images.value = Object.entries(map).map(([key, url], index) => ({
        url: String(url),
        label: `资料图片 ${index + 1}`,
      }))
    } catch {
      images.value = []
    }
  },
  { immediate: true }
)

function open() {
  urlDraft.value = ''
  dialogVisible.value = true
}

function select(image: { url: string; label: string }) {
  emit('update:modelValue', image.url)
  if (!props.caption) emit('update:caption', image.label)
  dialogVisible.value = false
}

function useUrl() {
  const value = urlDraft.value.trim()
  if (!value) return
  emit('update:modelValue', value)
  dialogVisible.value = false
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const res: any = await uploadImage(form)
    const url = res?.url || res?.data?.url || ''
    if (!url) throw new Error('上传结果没有图片地址')
    emit('update:modelValue', url)
    if (!props.caption) emit('update:caption', file.name.replace(/\.[^.]+$/, ''))
    ElMessage.success('图片已上传并插入')
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '图片上传失败')
  } finally {
    uploading.value = false
    input.value = ''
  }
}
</script>

<style scoped>
.image-picker {
  width: 100%;
}

.image-picker__selected {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border: 1px solid var(--os-border-soft, #e5e7eb);
  border-radius: 9px;
  background: var(--os-bg-subtle, #f8fafc);
}

.image-picker__thumb {
  width: 76px;
  height: 48px;
  flex: none;
  border-radius: 6px;
  object-fit: cover;
  background: #fff;
}

.image-picker__selected-main {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.image-picker__selected-label {
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
  font-weight: 500;
}

.image-picker__url {
  overflow: hidden;
  color: var(--os-text-4, #9ca3af);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-picker__empty {
  width: 100%;
  height: 58px;
  border-style: dashed;
  color: var(--os-text-3, #6b7280);
}

.image-picker__caption {
  margin-top: 7px;
}

.image-picker__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.image-picker__hint {
  color: var(--os-text-4, #9ca3af);
  font-size: 11px;
}

.image-picker__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  max-height: 340px;
  overflow: auto;
}

.image-picker__item {
  padding: 5px;
  overflow: hidden;
  border: 1px solid var(--os-border-soft, #e5e7eb);
  border-radius: 8px;
  background: #fff;
  color: var(--os-text-3, #6b7280);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.image-picker__item:hover,
.image-picker__item.is-selected {
  border-color: var(--os-accent, #4176e6);
  box-shadow: 0 0 0 2px var(--os-accent-soft, #edf3fe);
}

.image-picker__item img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 10;
  margin-bottom: 5px;
  border-radius: 5px;
  object-fit: cover;
  background: #f3f4f6;
}

.image-picker__url-row {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--os-border-soft, #e5e7eb);
}
</style>
