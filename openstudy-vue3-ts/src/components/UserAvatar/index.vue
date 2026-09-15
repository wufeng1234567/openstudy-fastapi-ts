<template>
  <div class="user-avatar" :style="containerStyle" :class="{ 'has-image': showImage }">
    <img v-if="resolvedSrc && !imgError" :src="resolvedSrc" :style="imgStyle" @error="imgError = true"
      @load="imgLoaded = true" />
    <span v-if="!showImage" class="avatar-initials" :style="initialsStyle">{{ initials }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps({
  src: { type: String, default: '' },
  name: { type: String, default: '' },
  size: { type: [Number, String], default: 40 }
})

const baseUrl = import.meta.env.VITE_APP_BASE_API || ''

const imgError = ref(false)
const imgLoaded = ref(false)

const sizeNum = computed(() => typeof props.size === 'number' ? props.size : parseInt(props.size) || 40)

// 自动拼接 BASE_API 前缀
const resolvedSrc = computed(() => {
  const raw = (props.src || '').trim()
  if (!raw) return ''
  if (raw.startsWith('http') || raw.startsWith('data:')) return raw
  return baseUrl + raw
})

watch(() => props.src, () => {
  imgError.value = false
  imgLoaded.value = false
})

const showImage = computed(() => resolvedSrc.value && !imgError.value && imgLoaded.value)

// 取名字第一个字符
const initials = computed(() => {
  const name = (props.name || '').trim()
  if (!name) return '?'
  return [...name][0]
})

const containerStyle = computed(() => ({
  width: sizeNum.value + 'px',
  height: sizeNum.value + 'px',
  minWidth: sizeNum.value + 'px',
  fontSize: Math.max(sizeNum.value * 0.38, 12) + 'px',
}))

const imgStyle = computed(() => ({
  width: sizeNum.value + 'px',
  height: sizeNum.value + 'px',
}))

const initialsStyle = computed(() => ({
  fontSize: Math.max(sizeNum.value * 0.38, 12) + 'px',
}))
</script>

<style scoped>
.user-avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: #f3f4f6;
  border: 2px solid #e5e7eb;
  box-sizing: border-box;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.user-avatar.has-image {
  border-color: #f3f4f6;
}

.user-avatar img {
  display: block;
  border-radius: 50%;
  object-fit: cover;
}

.avatar-initials {
  color: #1f2937;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.02em;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
</style>
