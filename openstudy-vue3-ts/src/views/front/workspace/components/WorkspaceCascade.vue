<template>
  <section v-if="isCascadeMode" class="kbp-cascade" v-loading="loading">
    <header class="kbp-cascade__head">
      <div>
        <div class="kbp-cascade__kicker">级联搜索 · 资料夹 + 内部文档</div>
        <h2>“{{ search }}”的搜索结果</h2>
      </div>
      <div class="kbp-cascade__summary">
        {{ result.totalFolders }} 个资料夹 · {{ result.totalDocs }} 份资料命中
      </div>
    </header>

    <div v-if="result.folders?.length" class="kbp-cascade__folders">
      <article v-for="folder in result.folders" :key="folder.kbId" class="kbp-cascade-folder">
        <button type="button" class="kbp-cascade-folder__head" @click="emit('open-folder', folder)">
          <span class="kbp-cascade-folder__icon"><OsIcon name="folder" :size="17" /></span>
          <span class="kbp-cascade-folder__main">
            <span class="kbp-cascade-folder__name" v-html="highlightQuery(folder.name, result.query)"></span>
            <span v-if="folder.matchedByName" class="kbp-cascade-folder__tag">资料夹名称命中</span>
          </span>
          <span class="kbp-cascade-folder__meta">
            {{ folder.docCount }} 份资料
            <template v-if="folder.matchedDocCount">· {{ folder.matchedDocCount }} 份文档命中</template>
          </span>
          <OsIcon name="chevron-right" :size="15" />
        </button>

        <div v-if="folder.documents?.length" class="kbp-cascade-docs">
          <button
            v-for="doc in folder.documents"
            :key="doc.docId"
            type="button"
            class="kbp-cascade-doc"
            @click="emit('open-document', doc)"
          >
            <span class="kbp-cascade-doc__icon"><OsIcon name="file-text" :size="15" /></span>
            <span class="kbp-cascade-doc__main">
              <span class="kbp-cascade-doc__top">
                <b v-html="highlightQuery(doc.fileName, result.query)"></b>
                <span v-for="field in doc.matchedBy" :key="field" class="kbp-cascade-doc__hit">{{ field }}命中</span>
              </span>
              <span v-if="doc.snippet" class="kbp-cascade-doc__snippet" v-html="highlightQuery(doc.snippet, result.query)"></span>
              <span v-else-if="doc.note" class="kbp-cascade-doc__snippet">{{ doc.note }}</span>
            </span>
            <span class="kbp-cascade-doc__meta">{{ doc.sizeText }} · {{ doc.createTime }}</span>
          </button>
        </div>
        <div v-else class="kbp-cascade-folder__hint">资料夹名称命中，内部暂无文档正文命中。</div>
      </article>
    </div>

    <div v-else-if="!loading" class="kbp-cascade__empty">
      <div class="kbp-empty__art"><OsIcon name="search" :size="28" /></div>
      <h3>没有找到“{{ search }}”</h3>
      <p>可以换个关键词，资料夹名称和文档正文会一起搜索。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'

const props = defineProps<{
  isCascadeMode: boolean
  loading: boolean
  search: string
  result: any
  highlightQuery: (content: string, query: string) => string
}>()

const emit = defineEmits<{
  (e: 'open-folder', folder: any): void
  (e: 'open-document', doc: any): void
}>()
</script>
