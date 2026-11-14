<template>
  <div class="kbp-docs" v-loading="docsLoading">
    <div
      v-for="entity in entities"
      :key="entity.key"
      class="kbp-doc kbp-entity"
      :class="{ 'is-jump-target': entity.doc && jumpTargetDocId === Number(entity.doc.docId) }"
      :data-doc-id="entity.doc?.docId"
      @click="activate(entity)"
    >
      <div v-if="entity.doc" class="kbp-doc__check" @click.stop>
        <el-checkbox
          :model-value="selectedDocIds.includes(Number(entity.doc.docId))"
          @change="emit('toggle-doc', Number(entity.doc.docId))"
        />
      </div>
      <div class="kbp-doc__icon" :class="`is-${entity.type}`">
        <OsIcon :name="entity.icon" :size="17" />
      </div>
      <div class="kbp-doc__main">
        <div class="kbp-doc__name-row">
          <span class="kbp-doc__name" :title="entity.title">{{ entity.title }}</span>
          <el-tag :type="entity.tagType" size="small" effect="plain">{{ entity.typeLabel }}</el-tag>
          <el-tag v-if="entity.doc && Number(entity.doc.version || 1) > 1" type="success" size="small" effect="plain">
            v{{ entity.doc.version }}
          </el-tag>
          <el-tag v-if="entity.doc" :type="entity.doc.disabled === 1 ? 'warning' : docTagType(entity.doc.status)" size="small" effect="plain">
            {{ entity.doc.disabled === 1 ? '已屏蔽' : entity.doc.statusText }}
          </el-tag>
        </div>
        <div class="kbp-doc__meta">
          <span v-if="entity.metaText">{{ entity.metaText }}</span>
          <span v-if="entity.subtitle" class="kbp-doc__note">{{ entity.subtitle }}</span>
          <a v-if="entity.doc?.sourceUrl" class="kbp-doc__source-url" :href="entity.doc.sourceUrl" target="_blank"
            rel="noopener noreferrer" @click.stop>来源网页</a>
          <span v-if="entity.createTime" class="kbp-doc__time">{{ entity.createTime }}</span>
        </div>
        <div v-if="entity.doc?.status === 4 && entity.doc.errorMsg" class="kbp-doc__err">{{ entity.doc.errorMsg }}</div>
      </div>
      <div class="kbp-doc__ops" @click.stop>
        <template v-if="entity.type === 'bank'">
          <button type="button" class="kbp-entity__action" @click="emit('open-bank-knowledge', entity.bank)">查看知识点</button>
          <button type="button" class="kbp-entity__action is-muted" @click="emit('remove-linked-bank', entity.bank)">取消关联</button>
        </template>
        <template v-else-if="entity.type === 'note'">
          <button type="button" class="kbp-entity__action" @click="emit('open-note', entity.note)">打开笔记</button>
          <button type="button" class="kbp-entity__action is-muted" @click="emit('unlink-linked-note', entity.note)">取消关联</button>
        </template>
        <template v-else-if="entity.image">
          <button type="button" class="kbp-entity__action" @click="emit('open-image', entity.image)">查看图片</button>
        </template>
        <template v-else>
          <span
            class="kbp-doc__op"
            :class="{ 'is-blocked': entity.doc.disabled === 1 }"
            :title="entity.doc.disabled === 1 ? '已屏蔽，点击恢复这份资料的检索' : '可检索，点击屏蔽这份资料'"
            @click="emit('toggle-searchable', entity.doc)"
          >
            <OsIcon :name="entity.doc.disabled === 1 ? 'eye-off' : 'eye'" :size="14" />
          </span>
          <button type="button" class="kbp-doc__op kbp-doc__clinic" data-tip="资料诊疗室" aria-label="资料诊疗室"
            @click="emit('open-clinic', entity.doc)">
            <OsIcon name="activity" :size="14" />
          </button>
          <span class="kbp-doc__op" title="智能整理" @click="emit('start-organize', entity.doc)">
            <OsIcon name="sparkles" :size="14" />
          </span>
          <el-dropdown trigger="click" @command="(command: string) => emit('doc-more', entity.doc, command)">
            <span class="kbp-doc__op" title="更多操作">
              <OsIcon name="more" :size="14" />
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="micro">生成微课</el-dropdown-item>
                <el-dropdown-item command="share">分享资料</el-dropdown-item>
                <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
                <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
                <el-dropdown-item command="reprocess">重新解析并向量化</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除资料</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </div>
    </div>
    <slot name="empty" />
  </div>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'

defineProps<{
  entities: any[]
  selectedDocIds: number[]
  jumpTargetDocId: number | null
  docTagType: (status: any) => string
  docsLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'open-bank-knowledge', bank: any): void
  (e: 'remove-linked-bank', bank: any): void
  (e: 'unlink-linked-note', note: any): void
  (e: 'open-note', note: any): void
  (e: 'open-image', image: any): void
  (e: 'toggle-doc', docId: number): void
  (e: 'show-anatomy', doc: any): void
  (e: 'toggle-searchable', doc: any): void
  (e: 'open-clinic', doc: any): void
  (e: 'start-organize', doc: any): void
  (e: 'doc-more', doc: any, command: string): void
}>()

function activate(entity: any) {
  if (entity.doc) {
    emit('show-anatomy', entity.doc)
    return
  }
  if (entity.type === 'bank') {
    emit('open-bank-knowledge', entity.bank)
    return
  }
  if (entity.type === 'note') {
    emit('open-note', entity.note)
    return
  }
  if (entity.type === 'image') emit('open-image', entity.image)
}
</script>

<style scoped>
.kbp-entity__action {
  padding: 0 4px;
  border: 0;
  color: #2f5fce;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 10.5px;
  white-space: nowrap;
}
.kbp-entity__action:hover { color: #1f4fae; }
.kbp-entity__action.is-muted { color: #9aa1af; }
.kbp-entity__action.is-muted:hover { color: #6b7280; }
.kbp-doc__icon.is-image { color: #d18a4b; }
.kbp-doc__icon.is-bank { color: #2f9e8f; }
.kbp-doc__icon.is-note { color: #5b8def; }
.kbp-doc__icon.is-web { color: #2f5fce; }
.kbp-doc__source-url { color: #2f5fce; }
</style>
