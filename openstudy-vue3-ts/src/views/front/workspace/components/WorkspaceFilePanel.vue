<template>
  <section class="kbp-main">
        <template v-if="activeKb">
          <div class="kbp-main__head">
            <div class="kbp-main__title-row">
              <span class="kbp-main__title">{{ activeKb.name }}</span>
              <el-tag v-if="activeKb.isDefault" size="small" type="info" effect="plain">默认</el-tag>
              <el-tag v-if="activeKb.disabled === 1" size="small" type="warning" effect="plain">
                已屏蔽，不参与检索
              </el-tag>
            </div>
            <div class="kbp-main__actions">
              <el-button size="small" text @click="emit('open-share', activeKb)">
                <el-icon><Share /></el-icon>
                分享资料夹
              </el-button>
              <el-button v-if="selectedDocCount" size="small" plain type="danger" :disabled="busy"
                @click="emit('remove-selected')">
                <OsIcon name="trash" :size="14" />
                删除（{{ selectedDocCount }}）
              </el-button>
              <el-button size="small" text @click="emit('open-organize-report')">
                <OsIcon name="alert" :size="14" />
                整理记录
                <span v-if="organizeReport.pending || organizeReport.failed" class="kbp-report-dot">
                  {{ organizeReport.pending + organizeReport.failed }}
                </span>
              </el-button>
              <el-dropdown class="kbp-upload-dropdown" trigger="click" :disabled="busy"
                @command="emit('upload-command', $event)">
                <button type="button" class="kbp-upload" :class="{ 'is-disabled': busy }" :disabled="busy"
                  title="上传文档：可在文件选择窗口按住 Ctrl 多选 Markdown、图片等文件">
                  <OsIcon name="arrow-up" :size="14" />
                  <span>{{ uploading ? '上传中…' : '上传文档' }}</span>
                  <OsIcon name="chevron-down" :size="12" />
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="file">
                      <OsIcon name="arrow-up" :size="14" />
                      选择文件（Ctrl 可多选）
                    </el-dropdown-item>
                    <el-dropdown-item command="text" :disabled="importing">
                      <OsIcon name="file-text" :size="14" />
                      {{ importing ? '导入中…' : '粘贴文本' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="url" :disabled="importing">
                      <OsIcon name="globe" :size="14" />
                      从网页导入
                    </el-dropdown-item>
                    <el-dropdown-item command="bank" :disabled="bankImporting">
                      <OsIcon name="database" :size="14" />
                      从题库导入
                    </el-dropdown-item>
                    <el-dropdown-item command="note" :disabled="noteImporting">
                      <OsIcon name="file-text" :size="14" />
                      {{ noteImporting ? '导入中…' : '导入笔记' }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>

          <!-- 拖拽上传：整块文档区都是投放目标 -->
          <div
            class="kbp-drop"
            :class="{ 'is-over': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div v-if="dragOver" class="kbp-drop__mask">
              <OsIcon name="arrow-up" :size="26" />
              <span>松手就传到「{{ activeKb.name }}」</span>
            </div>

            <div v-if="uploadTip" class="kbp-tip">{{ uploadTip }}</div>

            <WorkspaceEntityList
              :entities="entities"
              :selected-doc-ids="selectedDocIds"
              :jump-target-doc-id="jumpTargetDocId"
              :doc-tag-type="docTagType"
              :docs-loading="docsLoading"
              @open-bank-knowledge="emit('open-bank-knowledge', $event)"
              @remove-linked-bank="emit('remove-linked-bank', $event)"
              @unlink-linked-note="emit('unlink-linked-note', $event)"
              @open-note="emit('open-note', $event)"
              @open-image="emit('open-image', $event)"
              @toggle-doc="emit('toggle-doc', $event)"
              @show-anatomy="emit('show-anatomy', $event)"
              @toggle-searchable="emit('toggle-searchable', $event)"
              @open-clinic="emit('open-clinic', $event)"
              @start-organize="emit('start-organize', $event)"
              @doc-more="(doc, command) => emit('doc-more', doc, command)"
            >
              <template #empty>
                <div v-if="!docsLoading && !entities.length" class="kbp-docs__empty">
                  <div class="kbp-empty__art">
                    <OsIcon name="inbox" :size="30" />
                  </div>
                  <p class="kbp-empty__title">{{ workspaceSearch ? '没有匹配的资料' : '这个资料夹还是空的' }}</p>
                  <span class="kbp-empty__desc">
                    {{ workspaceSearch ? '换个关键词，或清空搜索再看全部资料。' : '把课件、真题、笔记传进来，智能体出题时就能翻到它们' }}
                  </span>
                  <div class="kbp-empty__actions">
                    <el-dropdown trigger="click" :disabled="busy" @command="emit('upload-command', $event)">
                      <button type="button" class="kbp-empty__btn is-primary" :disabled="busy">
                        <OsIcon name="arrow-up" :size="14" />
                        <span>上传文档</span>
                        <OsIcon name="chevron-down" :size="12" />
                      </button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="file">
                            <OsIcon name="arrow-up" :size="14" /> 选择文件（Ctrl 可多选）
                          </el-dropdown-item>
                          <el-dropdown-item command="text">
                            <OsIcon name="file-text" :size="14" /> 粘贴文本
                          </el-dropdown-item>
                          <el-dropdown-item command="url">
                            <OsIcon name="globe" :size="14" /> 从网页导入
                          </el-dropdown-item>
                          <el-dropdown-item command="bank">
                            <OsIcon name="database" :size="14" /> 从题库导入
                          </el-dropdown-item>
                          <el-dropdown-item command="note">
                            <OsIcon name="file-text" :size="14" /> 导入笔记
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                  <span class="kbp-empty__formats">
                    支持 Word / PDF / Markdown / TXT，带公式和图片也能读；也可以直接粘贴文本
                  </span>
                </div>
              </template>
            </WorkspaceEntityList>
          </div>

        </template>

        <div v-else-if="!loading" class="kbp-main__empty">
          <div class="kbp-empty__art">
            <OsIcon name="folder" :size="30" />
          </div>
          <p class="kbp-empty__title">左边选一个资料夹</p>
          <span class="kbp-empty__desc">选中后这里会显示它里面的资料</span>
        </div>
      </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Share } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import WorkspaceEntityList from './WorkspaceEntityList.vue'

const props = defineProps<{
  activeKb: any
  loading: boolean
  busy: boolean
  uploading: boolean
  importing: boolean
  bankImporting: boolean
  noteImporting: boolean
  uploadTip: string
  selectedDocCount: number
  selectedDocIds: number[]
  organizeReport: any
  entities: any[]
  docsLoading: boolean
  jumpTargetDocId: number | null
  docTagType: (status: any) => string
  workspaceSearch: string
}>()
const emit = defineEmits<{
  (e: 'open-share', kb: any): void
  (e: 'remove-selected'): void
  (e: 'open-organize-report'): void
  (e: 'upload-command', command: string): void
  (e: 'drop', event: DragEvent): void
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
  (e: 'pick'): void
}>()

const dragOver = ref(false)
function onDrop(event: DragEvent) {
  dragOver.value = false
  emit('drop', event)
}
</script>
