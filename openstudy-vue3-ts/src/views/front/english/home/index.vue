<template>
  <div class="english-home os-page">
    <p class="page-desc">轻量级英语学习工具箱：识词、词库、听写与阅读，边学边攒。</p>

    <div class="tool-grid">
      <!-- 拍照识词 -->
      <button type="button" class="tool-card" @click="goToOcr">
        <span class="tool-icon">
          <el-icon :size="20"><Camera /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">拍照识词</span>
          <span class="tool-desc">拍照或上传图片，快速识别单词</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <!-- 我的词库 -->
      <button type="button" class="tool-card" @click="goToVocabulary">
        <span class="tool-icon">
          <el-icon :size="20"><Notebook /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">我的词库</span>
          <span class="tool-desc">管理你的单词本和词组库</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <!-- 听力练习 -->
      <button type="button" class="tool-card" @click="goToListListening">
        <span class="tool-icon">
          <el-icon :size="20"><Headset /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">
            听力练习
            <el-tag size="small" type="info">开发中</el-tag>
          </span>
          <span class="tool-desc">单词听写，提升听力水平</span>
        </span>
        <span class="tool-arrow">
          <el-icon><ArrowRight /></el-icon>
        </span>
      </button>

      <!-- 阅读练习（暂未开放） -->
      <div class="tool-card is-disabled">
        <span class="tool-icon">
          <el-icon :size="20"><Reading /></el-icon>
        </span>
        <span class="tool-content">
          <span class="tool-title">
            阅读练习
            <el-tag size="small" type="info">开发中</el-tag>
          </span>
          <span class="tool-desc">短文阅读，积累生词</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishHome' })
import { useRouter } from 'vue-router'
import { Camera, Notebook, Headset, Reading, ArrowRight } from '@element-plus/icons-vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const goToOcr = () => {
  cacheStore.setLastVisited('english', 'ocr')
  router.push('/front/english/ocr')
}

const goToVocabulary = () => {
  cacheStore.setLastVisited('english', 'vocabulary')
  router.push('/front/english/vocabulary')
}

const goToListListening = () => {
  cacheStore.setLastVisited('english', 'listening')
  router.push('/front/english/listening')
}
</script>

<style scoped lang="scss">
.english-home {
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

.tool-card.is-disabled {
  cursor: not-allowed;
  opacity: 0.62;

  &:hover {
    background: #fff;
    border-color: var(--os-border-soft);
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
