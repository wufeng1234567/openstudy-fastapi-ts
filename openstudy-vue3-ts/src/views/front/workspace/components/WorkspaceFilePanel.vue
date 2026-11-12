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

            <div v-if="linkedBanks.length" class="kbp-linked-banks">
              <div class="kbp-linked-banks__head">
                <span class="kbp-linked-banks__label"><OsIcon name="database" :size="14" /> 已关联题库</span>
                <span class="kbp-linked-banks__sub">题库不复制，只做逻辑关联</span>
              </div>
              <div class="kbp-linked-bank-list">
                <div v-for="bank in linkedBanks" :key="bank.bankId || bank.id" class="kbp-linked-bank">
                  <el-tag size="small" type="success" effect="plain">题库</el-tag>
                  <div class="kbp-linked-bank__main">
                    <b>{{ bank.bankName || bank.name }}</b>
                    <span>{{ bank.subject || '未设置科目' }} · {{ bank.questionCount || bank.totalQuestions || 0 }} 道题</span>
                    <em v-if="bank.description">{{ bank.description }}</em>
                  </div>
                  <button type="button" class="kbp-linked-bank__knowledge" @click="emit('open-bank-knowledge', bank)">查看知识点</button>
                  <button type="button" class="kbp-linked-bank__remove" @click="emit('remove-linked-bank', bank)">取消关联</button>
                </div>
              </div>
            </div>

            <div v-if="linkedNotes.length" class="kbp-linked-banks kbp-linked-notes">
              <div class="kbp-linked-banks__head">
                <span class="kbp-linked-banks__label"><OsIcon name="file-text" :size="14" /> 已关联笔记</span>
                <span class="kbp-linked-banks__sub">笔记不复制，只做逻辑关联</span>
              </div>
              <div class="kbp-linked-bank-list">
                <div v-for="note in linkedNotes" :key="note.noteId" class="kbp-linked-bank">
                  <el-tag size="small" type="info" effect="plain">笔记</el-tag>
                  <div class="kbp-linked-bank__main">
                    <b>{{ note.title || '未命名笔记' }}</b>
                    <span>{{ note.summary || '暂无摘要' }}</span>
                  </div>
                  <button type="button" class="kbp-linked-bank__remove" @click="emit('unlink-linked-note', note)">取消关联</button>
                </div>
              </div>
            </div>

            <div class="kbp-docs" v-loading="docsLoading">
              <div v-for="doc in visibleFiles" :key="doc.docId" class="kbp-doc"
                :data-doc-id="doc.docId"
                :class="{ 'is-jump-target': jumpTargetDocId === Number(doc.docId) }"
                @click="emit('show-anatomy', doc)">
                <div class="kbp-doc__check" @click.stop>
                  <el-checkbox :model-value="selectedDocIds.includes(Number(doc.docId))"
                    @change="emit('toggle-doc', Number(doc.docId))" />
                </div>
                <div class="kbp-doc__icon">
                  <OsIcon name="file-text" :size="17" />
                </div>
                <div class="kbp-doc__main">
                  <div class="kbp-doc__name-row">
                    <span class="kbp-doc__name" :title="doc.fileName">{{ doc.fileName }}</span>
                    <el-tag v-if="Number(doc.version || 1) > 1" type="success" size="small" effect="plain">
                      v{{ doc.version }}
                    </el-tag>
                    <el-tag :type="doc.disabled === 1 ? 'warning' : docTagType(doc.status)" size="small" effect="plain">
                      {{ doc.disabled === 1 ? '已屏蔽' : doc.statusText }}
                    </el-tag>
                    <span v-if="doc.sourceType === 'share'" class="kbp-kb__tag is-share">来自分享</span>
                  </div>
                  <div class="kbp-doc__meta">
                    <span>{{ doc.sizeText }}</span>
                    <span v-if="doc.chunkCount">· {{ doc.chunkCount }} 个片段</span>
                    <span v-if="doc.imageCount">· {{ doc.imageCount }} 张图</span>
                    <span v-if="doc.note" class="kbp-doc__note">· {{ doc.note }}</span>
                    <a v-if="doc.sourceUrl" class="kbp-doc__source" :href="doc.sourceUrl" target="_blank"
                      rel="noopener noreferrer" @click.stop>来源网页</a>
                    <span class="kbp-doc__time">{{ doc.createTime }}</span>
                  </div>
                  <div v-if="doc.status === 4 && doc.errorMsg" class="kbp-doc__err">
                    {{ doc.errorMsg }}
                  </div>
                </div>
                <div class="kbp-doc__ops" @click.stop>
                  <span
                    class="kbp-doc__op"
                    :class="{ 'is-blocked': doc.disabled === 1 }"
                    :title="doc.disabled === 1 ? '已屏蔽，点击恢复这份资料的检索' : '可检索，点击屏蔽这份资料'"
                    @click="emit('toggle-searchable', doc)"
                  >
                    <OsIcon :name="doc.disabled === 1 ? 'eye-off' : 'eye'" :size="14" />
                  </span>
                  <button type="button" class="kbp-doc__op kbp-doc__clinic"
                    data-tip="资料诊疗室" aria-label="资料诊疗室"
                    @click="emit('open-clinic', doc)">
                    <OsIcon name="activity" :size="14" />
                  </button>
                  <span class="kbp-doc__op" title="智能整理" @click="emit('start-organize', doc)">
                    <OsIcon name="sparkles" :size="14" />
                  </span>
                  <el-dropdown trigger="click" @command="(command: string) => emit('doc-more', doc, command)">
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
                </div>
              </div>

              <div v-if="!docsLoading && !visibleFiles.length" class="kbp-docs__empty">
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
            </div>
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
  linkedBanks: any[]
  linkedNotes: any[]
  docsLoading: boolean
  visibleFiles: any[]
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
