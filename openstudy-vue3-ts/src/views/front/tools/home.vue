<template>
  <div class="tools-home os-page">
    <!-- 顶栏已经显示"实用工具箱"，这里只留一句说明，避免重复标题 -->
    <p class="page-desc">一站式文件处理与转换工具，全部在浏览器本地完成。</p>

    <div class="tool-grid">
      <button type="button" class="tool-card" @click="goTo('watermark')">
        <span class="tool-icon">
          <el-icon :size="20"><Picture /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">图片水印工具</span>
          <span class="tool-desc">为图片添加文字水印，支持旋转、透明度调整</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <button type="button" class="tool-card" @click="goTo('convert')">
        <span class="tool-icon">
          <el-icon :size="20"><Document /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">文档转换工具</span>
          <span class="tool-desc">PDF ↔ Word ↔ MD ↔ TXT ↔ 图片，支持双向互转</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <button type="button" class="tool-card" @click="goTo('image')">
        <span class="tool-icon">
          <el-icon :size="20"><MagicStick /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">图片处理工具</span>
          <span class="tool-desc">图片裁剪、旋转、缩放、翻转</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <button type="button" class="tool-card" @click="goTo('classDiagram')">
        <span class="tool-icon">
          <el-icon :size="20"><DataLine /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">类图生成</span>
          <span class="tool-desc">粘贴 Java 代码，自动生成 UML 类图，支持导出</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontToolsHome' })
import { useRouter } from 'vue-router'
import { Picture, Document, MagicStick, DataLine, ArrowRight } from '@element-plus/icons-vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const goTo = (path) => {
  cacheStore.setLastVisited('tools', path)
  router.push(`/front/tools/${path}`)
}
</script>

<style scoped lang="scss">
.tools-home {
  max-width: 1000px;
}

.page-desc {
  margin: 0 0 18px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--os-text-3);
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.tool-card {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 16px 18px;
  border: 1px solid var(--os-border-soft);
  border-radius: var(--os-radius);
  background: #fff;
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  /* 只动颜色，不做位移/缩放：列表静止时不该有"飘"的感觉 */
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    border-color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--dsw-static-neutral-bluish-50);
    border-color: var(--os-border-strong);
  }

  &:hover .tool-arrow {
    opacity: 1;
  }
}

.tool-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 10px;
  background: var(--dsw-static-neutral-bluish-75);
  color: var(--os-text-2);
}

.tool-content {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}

.tool-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--os-text);
}

.tool-desc {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--os-text-3);
}

.tool-arrow {
  flex: none;
  color: var(--os-text-4);
  opacity: 0;
  transition: opacity var(--ds-duration-fast) var(--ds-ease-in-out);
}

@media (max-width: 720px) {
  .tool-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
