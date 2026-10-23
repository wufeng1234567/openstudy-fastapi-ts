<!--
  英语学习 · 首页
  ============================================================================
  2026-10-23 重做。原来的首页把「听力」「阅读」标成「开发中」并禁用，
  但那两个页面实际上是有实现的（听力 963 行 / OCR 1443 行）——
  只是被隐藏了。既然现在要把英语功能放出来，就必须先让入口是真的能点的。

  本页只做一件事：**把四个能力讲清楚、点得动**。
  不自造统计数字（词库当前可能还是空的），也不写"开发中"。
-->
<template>
  <div class="en-home">
    <header class="en-head">
      <h1 class="en-head__title">英语学习</h1>
      <p class="en-head__desc">
        背单词、听写、阅读，工具都在这儿。查词可以用拍照识词，生词直接存进词库。
      </p>
    </header>

    <div class="en-grid">
      <button
        v-for="t in tools"
        :key="t.key"
        type="button"
        class="en-card"
        @click="go(t)"
      >
        <span class="en-card__icon">
          <OsIcon :name="t.icon" :size="20" />
        </span>
        <span class="en-card__main">
          <span class="en-card__title">{{ t.title }}</span>
          <span class="en-card__desc">{{ t.desc }}</span>
        </span>
        <span class="en-card__arrow">
          <OsIcon name="arrow-right" :size="15" />
        </span>
      </button>
    </div>

    <div class="en-tip">
      <OsIcon name="lightbulb" :size="14" />
      <span>
        生词攒够一批后，可以让 AI 用它们出一套题 —— 在「智能对话」里说
        「用我的 xx 词库出几道词汇题」就行。
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishHome' })
import { useRouter } from 'vue-router'
import OsIcon from '@/components/OsIcon/index.vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

/**
 * 四个入口 —— 全部**真实可用**，不再有「开发中」。
 *
 * 「阅读练习」此前页面是空壳（只有一句"开发中"）。这次没有把它做成假的入口，
 * 而是用它真正该做的事：**用 AI 生成一篇阅读理解** —— 后端
 * `/ai/generate/reading/stream` 早就存在（scene=reading），
 * 只是一直没有前端页面接它。见 `views/front/english/reading/index.vue`。
 */
const tools = [
  {
    key: 'ocr',
    title: '拍照识词',
    desc: '拍张照片，把上面的生词抓下来存进词库',
    icon: 'sparkles',
    to: '/front/english/ocr'
  },
  {
    key: 'vocabulary',
    title: '我的词库',
    desc: '整理要背的单词，支持朗读和例句',
    icon: 'book',
    to: '/front/english/vocabulary'
  },
  {
    key: 'listening',
    title: '单词听写',
    desc: '听发音写单词，错了会重来',
    icon: 'megaphone',
    to: '/front/english/listening'
  },
  {
    key: 'reading',
    title: '阅读练习',
    desc: '让 AI 按你的水平生成短文 + 题目',
    icon: 'file-text',
    to: '/front/english/reading'
  }
]

function go(t: { key: string; to: string }) {
  cacheStore.setLastVisited('english', t.key)
  router.push(t.to)
}
</script>

<style scoped lang="scss">
.en-home {
  max-width: 940px;
  margin: 0 auto;
  padding: 28px 20px 60px;
}

.en-head {
  margin-bottom: 22px;
}

.en-head__title {
  margin: 0 0 7px;
  font-size: 25px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.en-head__desc {
  margin: 0;
  max-width: 560px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--os-text-3, #6b7280);
}

.en-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.en-card {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 16px 17px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-border-strong, #d1d5db);
    background: var(--os-bg-subtle, #fafafa);
  }

  &:hover .en-card__arrow {
    opacity: 1;
  }
}

.en-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex: none;
  border-radius: 11px;
  background: var(--os-bg-subtle, #f3f4f6);
  color: var(--os-text-2, #4b5563);
}

.en-card__main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}

.en-card__title {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.en-card__desc {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--os-text-3, #6b7280);
}

.en-card__arrow {
  flex: none;
  color: var(--os-text-4, #9ca3af);
  opacity: 0;
  transition: opacity 0.15s;
}

.en-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 22px;
  padding: 12px 15px;
  border-radius: 10px;
  background: var(--os-bg-subtle, #fafafa);
  font-size: 12px;
  line-height: 1.65;
  color: var(--os-text-3, #6b7280);

  :deep(svg) {
    flex: none;
    margin-top: 1px;
  }
}

@media (max-width: 720px) {
  .en-grid {
    grid-template-columns: 1fr;
  }
}
</style>
