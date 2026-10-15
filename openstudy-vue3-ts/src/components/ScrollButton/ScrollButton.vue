<template>
  <transition name="fade">
    <div v-if="visible" class="scroll-button-container" :style="posStyle">
      <button class="scroll-btn-inner" @click="handleClick">
        <el-icon size="18">
          <ArrowDown v-if="scrollDirection === 'down'" />
          <ArrowUp v-else />
        </el-icon>
      </button>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { ArrowUp, ArrowDown } from '@element-plus/icons-vue'

const props = defineProps({
  bottom: { type: Number, default: 80 },
  right: { type: Number, default: 20 },
  scrollContainer: { type: Object, default: null }
})

const visible = ref(false)
const scrollDirection = ref('down')
const posStyle = ref({})
let hideTimer = null
let lastScrollTop = 0
let currentTarget = null

const getTarget = () => props.scrollContainer || document.documentElement

const updatePosition = () => {
  if (props.scrollContainer) {
    const el = props.scrollContainer
    const elRect = el.getBoundingClientRect()
    posStyle.value = {
      position: 'fixed',
      top: (elRect.bottom - props.bottom - 40) + 'px',
      left: (elRect.right - props.right - 40) + 'px'
    }
  } else {
    posStyle.value = {
      position: 'fixed',
      bottom: props.bottom + 'px',
      right: props.right + 'px'
    }
  }
}

const handleScroll = () => {
  const target = getTarget()
  const scrollTop = props.scrollContainer ? target.scrollTop : document.documentElement.scrollTop || 0

  // 超过 50px 才显示
  visible.value = scrollTop > 50

  // 实时检测滚动方向
  if (scrollTop > lastScrollTop) {
    scrollDirection.value = 'down'
  } else if (scrollTop < lastScrollTop) {
    scrollDirection.value = 'up'
  }
  lastScrollTop = scrollTop <= 0 ? 0 : scrollTop

  updatePosition()

  // 自动隐藏
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    visible.value = false
  }, 2000)
}

const handleClick = () => {
  const target = getTarget()
  if (scrollDirection.value === 'down') {
    target.scrollTo({ top: target.scrollHeight, behavior: 'smooth' })
  } else {
    target.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

const handleResize = () => {
  if (visible.value) updatePosition()
}

const bindScroll = () => {
  // 解绑旧的
  if (currentTarget) {
    currentTarget.removeEventListener('scroll', handleScroll)
  }
  // 绑定新的
  currentTarget = props.scrollContainer || window
  currentTarget.addEventListener('scroll', handleScroll, { passive: true })
}

onMounted(() => {
  bindScroll()
  window.addEventListener('resize', handleResize)
})

// 监听 scrollContainer 变化
watch(() => props.scrollContainer, (newVal) => {
  bindScroll()
})

onBeforeUnmount(() => {
  if (currentTarget) {
    currentTarget.removeEventListener('scroll', handleScroll)
  }
  window.removeEventListener('resize', handleResize)
  if (hideTimer) clearTimeout(hideTimer)
})
</script>

<style scoped>
.scroll-button-container {
  z-index: 1000;
  pointer-events: none;
}

.scroll-btn-inner {
  pointer-events: auto;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #fff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.scroll-btn-inner:hover {
  background: #f9fafb;
  border-color: #d1d5db;
  color: #1f2937;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.scroll-btn-inner:active {
  transform: translateY(0);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
