<template>
  <div class="bank-cover" :style="rootStyle">
    <el-image v-if="hasCover" :src="resolvedCover" fit="cover" class="bank-cover__img"
      @error="imgError = true" />
    <div v-else class="bank-cover__placeholder" :style="placeholderStyle">
      <span v-if="displayName" class="bank-cover__monogram" aria-hidden="true">{{ coverInitial }}</span>
      <el-icon v-else class="bank-cover__icon">
        <Picture />
      </el-icon>
    </div>
    <div v-if="hasCover" class="bank-cover__image-tone" aria-hidden="true"></div>
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

/**
 * 用题库名生成稳定的轻量差异。
 *
 * 不再使用完整的 0–360° 随机色相：所有封面都收敛到蓝灰 / 靛青主色区间，
 * 只通过很小的色相、亮度和渐变角度变化来区分题库，避免卡片列表变成彩色拼盘。
 */
const toneSeed = computed(() => {
  const seed = displayName.value || (props.subject || '').trim() || 'OpenStudy'
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  }
  return hash
})

const placeholderStyle = computed<Record<string, string>>(() => {
  // 218°–230°：只保留很窄的冷蓝 / 靛青区间，整体接近前台中性灰白
  const hue = 218 + (toneSeed.value % 13)
  const angle = 118 + (toneSeed.value % 25)

  return {
    '--cover-angle': `${angle}deg`,
    '--cover-start': `hsl(${hue}, 20%, 98%)`,
    '--cover-end': `hsl(${hue}, 20%, 91%)`,
    '--cover-glow': `hsla(${hue}, 52%, 58%, 0.12)`,
    '--cover-ring': `hsla(${hue}, 32%, 42%, 0.10)`,
    '--cover-pattern': `hsla(${hue}, 20%, 40%, 0.10)`,
    '--cover-muted': `hsl(${hue}, 16%, 40%)`,
    '--cover-accent': `hsl(${hue}, 42%, 56%)`
  }
})

// 封面徽标优先取科目首字，让同一题库分类有稳定的视觉识别；无科目时回退题库名
const coverInitial = computed(() => {
  const source = (props.subject || displayName.value || '题').trim()
  return Array.from(source)[0]?.toUpperCase() || '题'
})

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
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
}

.bank-cover__img {
  width: 100%;
  height: 100%;
  filter: saturate(0.9);
}

/* 真实封面图也压一层极淡的冷色遮罩，避免过亮图片与前台灰白界面脱节 */
.bank-cover__image-tone {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.015) 0%, rgba(15, 23, 42, 0.12) 100%),
    linear-gradient(135deg, rgba(99, 102, 241, 0.035) 0%, transparent 55%);
}

.bank-cover__placeholder {
  position: relative;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  isolation: isolate;
  background:
    radial-gradient(circle at 82% 14%, var(--cover-glow) 0, transparent 44%),
    linear-gradient(var(--cover-angle), var(--cover-start) 0%, var(--cover-end) 100%);
}

/* 轻微点阵纹理：让浅色封面不显得是一块纯色占位 */
.bank-cover__placeholder::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image: radial-gradient(var(--cover-pattern) 1px, transparent 1px);
  background-size: 16px 16px;
  -webkit-mask-image: linear-gradient(135deg, #000 0%, transparent 76%);
  mask-image: linear-gradient(135deg, #000 0%, transparent 76%);
}

/* 右下角装饰圆环，作为唯一的大面积装饰 */
.bank-cover__placeholder::after {
  content: '';
  position: absolute;
  right: -44px;
  bottom: -58px;
  z-index: -1;
  width: 138px;
  height: 138px;
  border: 1px solid var(--cover-ring);
  border-radius: 50%;
  box-shadow: 0 0 0 22px var(--cover-glow);
  pointer-events: none;
}

/* 封面只保留题库首字的磨砂徽标，避免与正文标题、科目重复 */
.bank-cover__monogram {
  position: relative;
  z-index: 1;
  width: 76px;
  height: 76px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.62);
  color: var(--cover-muted);
  box-shadow:
    0 10px 28px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.04em;
  user-select: none;
  backdrop-filter: blur(8px);
}

.bank-cover__monogram::after {
  content: '';
  position: absolute;
  top: 10px;
  right: 10px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cover-accent);
  opacity: 0.5;
}

.bank-cover__icon {
  position: relative;
  z-index: 1;
  color: var(--cover-muted);
  font-size: 40px;
  opacity: 0.7;
}
</style>
