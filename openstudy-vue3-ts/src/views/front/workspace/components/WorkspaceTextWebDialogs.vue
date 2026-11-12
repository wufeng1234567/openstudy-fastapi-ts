<template>
  <el-dialog
    :model-value="textImportVisible"
    title="粘贴文本"
    width="640px"
    append-to-body
    @update:model-value="emit('update:textImportVisible', $event)"
    @closed="emit('reset-text')"
  >
    <div class="kbp-import">
      <p class="kbp-import__hint">把正文直接粘进来就行，不用先存成文件。导入后智能体一样能检索到。</p>
      <el-input
        :model-value="textImportContent"
        type="textarea"
        :rows="10"
        placeholder="把课件文字、笔记、错题解析粘在这里…"
        @update:model-value="emit('update:textImportContent', $event)"
      />
      <div class="kbp-import__row">
        <span class="kbp-import__label">起个名字</span>
        <el-input
          :model-value="textImportFileName"
          placeholder="例如：概率论第四章笔记"
          maxlength="80"
          @update:model-value="emit('update:textImportFileName', $event)"
        />
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:textImportVisible', false)">取消</el-button>
      <el-button type="primary" :loading="importing" @click="emit('submit-text')">导入</el-button>
    </template>
  </el-dialog>

  <el-dialog
    :model-value="webImportVisible"
    title="从网页导入"
    width="680px"
    append-to-body
    @update:model-value="emit('update:webImportVisible', $event)"
    @closed="emit('reset-web')"
  >
    <div class="kbp-web">
      <p class="kbp-web__hint">粘贴一个公开网页链接直接导入；或输入关键词，让系统搜索后由你挑选。</p>
      <div class="kbp-web__search">
        <el-input
          :model-value="webImportQuery"
          clearable
          placeholder="粘贴网址，或输入关键词搜索网页"
          @update:model-value="emit('update:webImportQuery', $event)"
          @keyup.enter="emit('submit-web')"
        />
        <el-button type="primary" :loading="webSearching || webImporting" @click="emit('submit-web')">
          {{ webImportIsUrl ? '导入网址' : '搜索网页' }}
        </el-button>
      </div>
      <div v-if="webImportQuery.trim() && !webImportIsUrl && !webResults.length && !webSearching" class="kbp-web__empty">
        还没有搜索结果。输入关键词后点「搜索网页」。
      </div>
      <div v-if="webResults.length" class="kbp-web__results">
        <div v-for="item in webResults" :key="item.url" class="kbp-web__item">
          <div class="kbp-web__main">
            <a class="kbp-web__title" :href="item.url" target="_blank" rel="noopener noreferrer">
              [{{ item.index }}] {{ item.title }}
            </a>
            <div class="kbp-web__meta">
              <span>{{ item.siteName }}</span>
              <span v-if="item.date">· {{ item.date }}</span>
            </div>
            <p>{{ item.snippet || item.summary }}</p>
          </div>
          <el-button size="small" plain :loading="webImporting" @click="emit('import-web', item)">导入</el-button>
        </div>
      </div>
      <div class="kbp-web__note">
        <span class="kbp-import__label">备注（可选）</span>
        <el-input
          :model-value="webImportNote"
          maxlength="200"
          placeholder="例如：这节课要用的参考资料"
          @update:model-value="emit('update:webImportNote', $event)"
        />
      </div>
      <p class="kbp-web__foot">导入后会走和上传文件相同的分块、向量化、知识百科与知识图谱流程，智能体可以直接检索。</p>
    </div>
    <template #footer>
      <el-button @click="emit('update:webImportVisible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineProps<{
  textImportVisible: boolean
  textImportContent: string
  textImportFileName: string
  importing: boolean
  webImportVisible: boolean
  webImportQuery: string
  webImportNote: string
  webSearching: boolean
  webImporting: boolean
  webResults: Array<Record<string, any>>
  webImportIsUrl: boolean
}>()

const emit = defineEmits<{
  (e: 'update:textImportVisible', value: boolean): void
  (e: 'update:textImportContent', value: string): void
  (e: 'update:textImportFileName', value: string): void
  (e: 'update:webImportVisible', value: boolean): void
  (e: 'update:webImportQuery', value: string): void
  (e: 'update:webImportNote', value: string): void
  (e: 'reset-text'): void
  (e: 'reset-web'): void
  (e: 'submit-text'): void
  (e: 'submit-web'): void
  (e: 'import-web', item: Record<string, any>): void
}>()
</script>
