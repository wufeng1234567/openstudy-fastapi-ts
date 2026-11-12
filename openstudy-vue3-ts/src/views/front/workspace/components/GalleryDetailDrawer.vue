<template>
  <el-drawer :model-value="props.visible" @update:model-value="emit('update:visible', $event)" class="gallery-detail-drawer" size="560px" :with-header="false" append-to-body>
      <div v-if="detail" class="gallery-detail">
        <header class="gallery-detail__head">
          <div>
            <span class="gallery-kicker">IMAGE ASSET</span>
            <h3>{{ detail.displayName || detail.fileName || '图片资产' }}</h3>
          </div>
          <button type="button" class="gallery-detail__close" @click="emit('update:visible', false)">×</button>
        </header>

        <div class="gallery-detail__image">
          <el-image :src="displayUrl(detail.url)" fit="contain" :preview-src-list="[displayUrl(detail.url)]" preview-teleported />
        </div>

        <div class="gallery-detail__badges">
          <span class="gallery-kind">{{ kindLabel(detail.kind) }}</span>
          <span class="gallery-status" :class="`is-${detail.descriptionStatus}`">{{ statusLabel(detail.descriptionStatus) }}</span>
          <span v-if="detail.descriptionModel" class="gallery-detail__model">{{ detail.descriptionModel }}</span>
        </div>

        <section class="gallery-detail__section">
          <div class="gallery-detail__section-title">
            <span>图片描述</span>
            <el-button text size="small" :loading="describingOne" @click="emit('describe')">
              {{ detail.descriptionStatus === 'done' ? '重新描述' : '生成描述' }}
            </el-button>
          </div>
          <p class="gallery-detail__caption" :class="{ 'is-muted': !detail.caption }">
            {{ detail.caption || '这张图还没有生成描述。生成后会同时写入画廊索引和检索。' }}
          </p>
          <div v-if="detail.describeError" class="gallery-detail__error">{{ detail.describeError }}</div>
        </section>

        <section v-if="detail.ocrText" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>OCR 文本</span></div>
          <pre class="gallery-detail__ocr">{{ detail.ocrText }}</pre>
        </section>

        <section class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>来源</span></div>
          <div class="gallery-detail__meta-grid">
            <div><span>来源资料</span><b>{{ detail.sourceName }}</b></div>
            <div><span>所在章节</span><b>{{ detail.sectionTitle || '未识别章节' }}</b></div>
            <div><span>图片类型</span><b>{{ kindLabel(detail.kind) }}</b></div>
            <div><span>被使用</span><b>{{ detail.usedCount || 0 }} 处</b></div>
          </div>
          <p v-if="detail.surroundingText" class="gallery-detail__context">
            {{ detail.surroundingText }}
          </p>
        </section>

        <section v-if="detail.references?.length" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>引用关系</span></div>
          <div class="gallery-detail__usages">
            <div v-for="ref in detail.references" :key="`ref-${ref.id}`" class="gallery-detail__usage">
              <span>{{ ref.targetType === 'question' ? '题目' : ref.targetType === 'note' ? '笔记' : ref.targetType === 'wiki_page' ? '知识百科' : '资料' }}</span>
              <b>{{ ref.targetTitle }}</b>
              <em>{{ ref.createTime }}</em>
            </div>
          </div>
        </section>

        <section v-if="detail.usages?.length" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>使用记录</span></div>
          <div class="gallery-detail__usages">
            <div v-for="usage in detail.usages" :key="`${usage.targetType}-${usage.targetId}`" class="gallery-detail__usage">
              <span>{{ usage.targetType === 'question' ? '题目' : usage.targetType === 'note' ? '笔记' : '资料' }}</span>
              <b>{{ usage.title }}</b>
              <em>{{ usage.createTime }}</em>
            </div>
          </div>
        </section>

        <div class="gallery-detail__actions">
          <el-button v-if="detail.canLocate" plain @click="emit('locate', detail)">定位原文</el-button>
          <el-button plain @click="emit('use-question', detail)">插入题目</el-button>
          <el-button type="primary" plain @click="emit('use-note', detail)">加入笔记</el-button>
          <el-button plain @click="emit('insert-wiki')">插入知识百科</el-button>
        </div>
      </div>
      <div v-else class="gallery-detail__loading" v-loading="true"></div>
    </el-drawer>
</template>

<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  detail: any
  describingOne: boolean
  displayUrl: (url: string) => string
  kindLabel: (kind: string) => string
  statusLabel: (status: string) => string
}>()

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'describe'): void
  (e: 'locate', detail: any): void
  (e: 'use-question', detail: any): void
  (e: 'use-note', detail: any): void
  (e: 'insert-wiki'): void
}>()
</script>

<style scoped>
.gallery-kicker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #4f6bed;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.gallery-kicker__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4f6bed;
  box-shadow: 0 0 0 4px rgba(79, 107, 237, 0.1);
}


.gallery-kind,
.gallery-status {
  position: absolute;
  top: 9px;
  padding: 3px 7px;
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.2;
  backdrop-filter: blur(8px);
}

.gallery-kind {
  left: 9px;
  color: #fff;
  background: rgba(28, 37, 54, 0.58);
}

.gallery-status {
  right: 9px;
}

.gallery-status.is-done {
  color: #1f7a6d;
  background: rgba(226, 248, 244, 0.94);
}

.gallery-status.is-pending {
  color: #946523;
  background: rgba(255, 248, 230, 0.94);
}

.gallery-status.is-processing {
  color: #3f5fc9;
  background: rgba(235, 240, 255, 0.94);
}

.gallery-status.is-failed {
  color: #b34141;
  background: rgba(255, 236, 236, 0.94);
}


.gallery-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 2px 4px 18px;
}

.gallery-detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.gallery-detail__head h3 {
  margin: 6px 0 0;
  color: #1f2937;
  font-size: 18px;
  line-height: 1.35;
}

.gallery-detail__close {
  border: none;
  background: transparent;
  color: #9aa1af;
  cursor: pointer;
  font-size: 24px;
  line-height: 1;
}

.gallery-detail__image {
  overflow: hidden;
  border: 1px solid #eceff4;
  border-radius: 12px;
  background: #f5f7fa;
}

.gallery-detail__image :deep(.el-image) {
  display: block;
  width: 100%;
  max-height: 360px;
}

.gallery-detail__image :deep(img) {
  max-height: 360px;
  object-fit: contain;
}

.gallery-detail__badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gallery-detail__badges .gallery-kind,
.gallery-detail__badges .gallery-status {
  position: static;
  backdrop-filter: none;
}

.gallery-detail__badges .gallery-kind {
  color: #596173;
  background: #f1f3f7;
}

.gallery-detail__model {
  margin-left: auto;
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-detail__section {
  padding: 13px 14px;
  border: 1px solid #eef0f5;
  border-radius: 10px;
  background: #fff;
}

.gallery-detail__section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.gallery-detail__caption {
  margin: 0;
  color: #374151;
  font-size: 13px;
  line-height: 1.75;
}

.gallery-detail__caption.is-muted {
  color: #9aa1af;
}

.gallery-detail__error {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 7px;
  color: #b34141;
  background: #fff4f4;
  font-size: 11px;
  line-height: 1.6;
}

.gallery-detail__ocr {
  overflow: auto;
  max-height: 160px;
  margin: 0;
  padding: 10px;
  border-radius: 7px;
  color: #4b5563;
  background: #f7f8fa;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.gallery-detail__meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}

.gallery-detail__meta-grid div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.gallery-detail__meta-grid span {
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-detail__meta-grid b {
  overflow: hidden;
  color: #4b5563;
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-detail__context {
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px dashed #eceff4;
  color: #8a91a0;
  font-size: 11px;
  line-height: 1.7;
}

.gallery-detail__usages {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.gallery-detail__usage {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 11px;
}

.gallery-detail__usage span {
  flex: none;
  padding: 1px 5px;
  border-radius: 4px;
  color: #4f6bed;
  background: #eef2ff;
  font-size: 10px;
}

.gallery-detail__usage b {
  overflow: hidden;
  color: #374151;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-detail__usage em {
  margin-left: auto;
  color: #b0b6c1;
  font-size: 10px;
  font-style: normal;
}

.gallery-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 4px;
}

.gallery-wiki-picker {
  display: flex;
  min-height: 120px;
  flex-direction: column;
  gap: 8px;
  max-height: 52vh;
  overflow-y: auto;
}

.gallery-wiki-pick {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  background: #fff;
  color: #4b5563;
  cursor: pointer;
  text-align: left;
}

.gallery-wiki-pick:hover {
  border-color: #cbd9f2;
  background: #f7f9ff;
}

.gallery-wiki-pick b {
  font-size: 13px;
}

.gallery-wiki-pick span {
  overflow: hidden;
  color: #9aa1af;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-wiki-empty {
  padding: 30px 0;
  color: #a0a6b2;
  font-size: 12px;
  text-align: center;
}

.gallery-detail__loading {
  height: 500px;
}


</style>
