<template>
  <div class="bank-cover" :style="rootStyle">
    <el-image v-if="hasCover" :src="resolvedCover" fit="cover" class="bank-cover__img"
      @error="imgError = true" />
    <div v-else class="bank-cover__placeholder" :style="placeholderStyle">
      <template v-if="displayName">
        <span class="bank-cover__name">{{ displayName }}</span>
        <span v-if="subject" class="bank-cover__subject">{{ subject }}</span>
      </template>
      <el-icon v-else class="bank-cover__icon">
        <Picture />
      </el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'

const props = defineProps({
  coverImage: { type: String, default: '' },
  bankName: { type: String, default: '' },
  subject: { type: String, default: '' },
  size: { type: [Number, String], default: 0 },
  rounded: { type: [Number, String], default: '' }
})

const baseUrl = import.meta.env.VITE_APP_BASE_API || ''

const imgError = ref(false)

const resolvedCover = computed(() => {
  const raw = (props.coverImage || '').trim()
  if (!raw) return ''
  if (raw.startsWith('http') || raw.startsWith('data:')) return raw
  return baseUrl + raw
})

const hasCover = computed(() => !!resolvedCover.value && !imgError.value)

watch(() => props.coverImage, () => {
  imgError.value = false
})

const displayName = computed(() => (props.bankName || '').trim())

const hue = computed(() => {
  const seed = displayName.value || (props.subject || '').trim() || 'OpenStudy'
  let h = 0
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) % 360
  }
  return h
})

const placeholderStyle = computed(() => ({
  background: `linear-gradient(135deg, hsl(${hue.value}, 58%, 60%), hsl(${(hue.value + 32) % 360}, 54%, 46%))`
}))

const rootStyle = computed(() => {
  const style: Record<string, string> = {}
  const size = Number(props.size)
  if (size > 0) {
    style.width = `${size}px`
    style.height = `${size}px`
    style.flex = `0 0 ${size}px`
  }
  if (props.rounded !== '' && props.rounded != null) {
    style.borderRadius = /^\d+(\.\d+)?$/.test(String(props.rounded))
      ? `${props.rounded}px`
      : String(props.rounded)
  }
  return style
})
</script>

<style scoped>
.bank-cover {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.bank-cover__img {
  width: 100%;
  height: 100%;
}

.bank-cover__placeholder {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
  color: #fff;
}

.bank-cover__name {
  max-width: 100%;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  word-break: break-word;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}

.bank-cover__subject {
  max-width: 100%;
  font-size: 12px;
  line-height: 1.2;
  opacity: 0.9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bank-cover__icon {
  font-size: 40px;
  opacity: 0.9;
}
</style>
