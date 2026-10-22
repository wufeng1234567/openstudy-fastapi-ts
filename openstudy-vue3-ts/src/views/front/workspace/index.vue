<template>
  <div class="workspace-page">
    <!-- ============ 顶部：空间概况 ============ -->
    <header class="ws-head">
      <div class="ws-head__main">
        <h1 class="ws-head__title">我的空间</h1>
        <p class="ws-head__desc">
          把常用的资料放进来。之后直接跟 AI 说「用我空间里那份资料出题」，它会自己找。
        </p>
      </div>
      <div class="ws-head__stats">
        <div class="ws-stat">
          <span class="ws-stat__num">{{ stats.docCount }}</span>
          <span class="ws-stat__label">份资料</span>
        </div>
        <div class="ws-stat__divider" />
        <div class="ws-stat">
          <span class="ws-stat__num">{{ stats.readyCount }}</span>
          <span class="ws-stat__label">份可检索</span>
        </div>
        <div class="ws-stat__divider" />
        <div class="ws-stat">
          <span class="ws-stat__num">{{ stats.totalSizeText || '0 B' }}</span>
          <span class="ws-stat__label">占用空间</span>
        </div>
      </div>
    </header>

    <!-- ============ 上传区 ============ -->
    <section class="ws-upload">
      <div
        class="ws-drop"
        :class="{ 'is-over': dragOver, 'is-busy': uploading }"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="onDrop"
        @click="pickFile"
      >
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.md,.txt"
          style="display: none"
          @change="onPick"
        />

        <template v-if="!uploading">
          <div class="ws-drop__icon">
            <OsIcon name="folder" :size="26" />
          </div>
          <div class="ws-drop__title">把资料拖到这里，或点击选择文件</div>
          <div class="ws-drop__hint">
            支持 Word / PDF / Markdown / TXT，带公式和图片也能读
          </div>
        </template>

        <template v-else>
          <div class="ws-drop__spinner" />
          <div class="ws-drop__title">正在上传并解析…</div>
          <div class="ws-drop__hint">{{ uploadingName }}</div>
        </template>
      </div>

      <!-- 备注输入：帮 AI 以后认出这份资料 -->
      <div class="ws-note">
        <label class="ws-note__label">给这批文件加一句说明（可选）</label>
        <el-input
          v-model="uploadNote"
          placeholder="例如：高二数学期末卷 / 概率论第四章课件"
          maxlength="60"
          show-word-limit
          clearable
        />
        <div class="ws-note__tip">
          文件名叫「新建文档(2)」时，这句说明能帮 AI 找到它
        </div>
      </div>
    </section>

    <!-- ============ 试试 AI 怎么找 ============ -->
    <section v-if="files.length" class="ws-try">
      <div class="ws-try__head">
        <span class="ws-try__title">试试 AI 会怎么找</span>
        <span class="ws-try__hint">在下面输入一句描述，看看 AI 会挑中哪份文件</span>
      </div>
      <div class="ws-try__row">
        <el-input
          v-model="tryQuery"
          placeholder="例如：那份概率论的资料"
          clearable
          @keyup.enter="doTry"
        />
        <el-button type="primary" :loading="trying" @click="doTry">找找看</el-button>
      </div>

      <transition-group name="ws-fade" tag="div" class="ws-try__result" v-if="tryResult.length">
        <div
          v-for="(f, i) in tryResult"
          :key="f.docId"
          class="ws-try__file"
          :class="{ 'is-best': i === 0 }"
        >
          <span class="ws-try__rank">{{ i + 1 }}</span>
          <span class="ws-try__file-name">{{ f.fileName }}</span>
          <span v-if="f.note" class="ws-try__file-note">{{ f.note }}</span>
          <span v-if="i === 0" class="ws-try__badge">最匹配</span>
        </div>
      </transition-group>
      <div v-else-if="tried" class="ws-try__empty">
        没找到对得上的文件。可以换个说法，或者在备注里加个关键词。
      </div>
    </section>

    <!-- ============ 文件列表 ============ -->
    <section class="ws-files">
      <div class="ws-files__head">
        <span class="ws-files__title">空间里的资料</span>
        <el-button text :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>

      <div v-if="loading && !files.length" class="ws-files__loading">
        <div class="ws-drop__spinner" />
      </div>

      <div v-else-if="!files.length" class="ws-files__empty">
        <OsIcon name="inbox" :size="32" />
        <p>空间还是空的</p>
        <span>把课件、真题、教材上传到这里，AI 就能拿它们给你出题</span>
      </div>

      <ul v-else class="ws-list">
        <li v-for="f in files" :key="f.docId" class="ws-item">
          <div class="ws-item__icon">
            <OsIcon name="file-text" :size="18" />
          </div>
          <div class="ws-item__main">
            <div class="ws-item__name-row">
              <span class="ws-item__name">{{ f.fileName }}</span>
              <el-tag
                :type="f.status === 5 ? 'success' : f.status === 4 ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                {{ f.statusText }}
              </el-tag>
            </div>
            <div class="ws-item__meta">
              <span>{{ f.sizeText }}</span>
              <span v-if="f.chunkCount">· {{ f.chunkCount }} 个片段</span>
              <span v-if="f.note" class="ws-item__note">· {{ f.note }}</span>
              <span class="ws-item__time">{{ f.createTime }}</span>
            </div>
          </div>
          <button class="ws-item__del" title="移出空间" @click.stop="remove(f)">
            <OsIcon name="trash" :size="14" />
          </button>
        </li>
      </ul>
    </section>

    <!-- 底部提示 -->
    <div class="ws-foot">
      <OsIcon name="lightbulb" :size="14" />
      <span>
        在对话里直接说「用我空间里的资料出个题库」，AI 会先找到文件、再读内容、最后建题库。
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import {
  getWorkspace,
  uploadToWorkspace,
  deleteWorkspaceFile,
  searchWorkspace
} from '@/api/ai/workspace'

const loading = ref(false)
const uploading = ref(false)
const uploadingName = ref('')
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const uploadNote = ref('')

const files = ref<any[]>([])
const stats = reactive<any>({ docCount: 0, readyCount: 0, totalSizeText: '0 B' })

const tryQuery = ref('')
const trying = ref(false)
const tried = ref(false)
const tryResult = ref<any[]>([])

async function load() {
  loading.value = true
  try {
    const res: any = await getWorkspace()
    if (res.code === 200) {
      files.value = res.data.files || []
      Object.assign(stats, res.data.stats || {})
    }
  } catch (e: any) {
    ElMessage.error('读取工作空间失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function pickFile() {
  if (uploading.value) return
  fileInput.value?.click()
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) uploadFiles(Array.from(input.files))
  input.value = ''
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (uploading.value) return
  const list = e.dataTransfer?.files
  if (list?.length) uploadFiles(Array.from(list))
}

async function uploadFiles(list: File[]) {
  uploading.value = true
  let ok = 0
  let fail = 0
  try {
    for (const f of list) {
      uploadingName.value = f.name
      try {
        const res: any = await uploadToWorkspace(f, uploadNote.value || undefined)
        if (res.code === 200) ok++
        else {
          fail++
          ElMessage.error(`${f.name}：${res.msg || '上传失败'}`)
        }
      } catch (e: any) {
        fail++
        ElMessage.error(`${f.name}：${e?.message || '上传失败'}`)
      }
    }
    if (ok) {
      ElMessage.success(`已上传 ${ok} 份${fail ? `，${fail} 份失败` : ''}，正在后台解析`)
      uploadNote.value = ''
      await load()
      // 解析是后台任务，3 秒后再刷一次让状态跟上
      setTimeout(load, 3000)
    }
  } finally {
    uploading.value = false
    uploadingName.value = ''
  }
}

async function remove(f: any) {
  try {
    await ElMessageBox.confirm(`确定从空间移除「${f.fileName}」吗？`, '移除资料', {
      confirmButtonText: '移除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await deleteWorkspaceFile(f.docId)
    if (res.code === 200) {
      ElMessage.success('已移除')
      await load()
    } else {
      ElMessage.error(res.msg || '移除失败')
    }
  } catch (e: any) {
    ElMessage.error('移除失败：' + (e?.message || e))
  }
}

async function doTry() {
  const q = tryQuery.value.trim()
  if (!q) {
    ElMessage.warning('先输入一句描述')
    return
  }
  trying.value = true
  tried.value = false
  try {
    const res: any = await searchWorkspace(q, 5)
    if (res.code === 200) {
      tryResult.value = res.data.files || []
      tried.value = true
    }
  } catch (e: any) {
    ElMessage.error('查找失败：' + (e?.message || e))
  } finally {
    trying.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.workspace-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 28px 24px 60px;
}

/* ---------- 头部 ---------- */
.ws-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 26px;
}

.ws-head__title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.ws-head__desc {
  margin: 0;
  font-size: 13px;
  color: var(--os-text-3, #6b7280);
  line-height: 1.6;
  max-width: 520px;
}

.ws-head__stats {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: none;
}

.ws-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.ws-stat__num {
  font-size: 20px;
  font-weight: 700;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.ws-stat__label {
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

.ws-stat__divider {
  width: 1px;
  height: 26px;
  background: var(--os-border, #e5e7eb);
}

/* ---------- 上传 ---------- */
.ws-upload {
  margin-bottom: 26px;
}

.ws-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 34px 20px;
  border: 1.5px dashed var(--os-border, #d1d5db);
  border-radius: 14px;
  background: var(--os-bg-subtle, #fafafa);
  cursor: pointer;
  transition: all 0.18s;
}

.ws-drop:hover,
.ws-drop.is-over {
  border-color: var(--os-accent, #2563eb);
  background: var(--os-accent-50, #eff6ff);
}

.ws-drop.is-busy {
  cursor: default;
  border-style: solid;
  border-color: var(--os-accent, #2563eb);
}

.ws-drop__icon {
  color: var(--os-text-3, #9ca3af);
}

.ws-drop__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.ws-drop__hint {
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);
}

.ws-drop__spinner {
  width: 26px;
  height: 26px;
  border: 2.5px solid var(--os-border, #e5e7eb);
  border-top-color: var(--os-accent, #2563eb);
  border-radius: 50%;
  animation: ws-spin 0.8s linear infinite;
}

@keyframes ws-spin {
  to {
    transform: rotate(360deg);
  }
}

.ws-note {
  margin-top: 14px;
}

.ws-note__label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
  margin-bottom: 6px;
}

.ws-note__tip {
  margin-top: 5px;
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

/* ---------- 试试 AI 怎么找 ---------- */
.ws-try {
  margin-bottom: 26px;
  padding: 18px 20px;
  border-radius: 14px;
  background: var(--os-accent-50, #eff6ff);
  border: 1px solid var(--os-accent-100, #dbeafe);
}

.ws-try__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}

.ws-try__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.ws-try__hint {
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.ws-try__row {
  display: flex;
  gap: 10px;
}

.ws-try__result {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ws-try__file {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: #fff;
  border-radius: 9px;
  border: 1px solid transparent;
  font-size: 13px;
}

.ws-try__file.is-best {
  border-color: var(--os-accent, #2563eb);
  box-shadow: 0 1px 3px rgba(37, 99, 235, 0.12);
}

.ws-try__rank {
  width: 18px;
  height: 18px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--os-bg-subtle, #f3f4f6);
  font-size: 11px;
  font-weight: 600;
  color: var(--os-text-3, #6b7280);
}

.ws-try__file.is-best .ws-try__rank {
  background: var(--os-accent, #2563eb);
  color: #fff;
}

.ws-try__file-name {
  font-weight: 500;
  color: var(--os-text, #111827);
}

.ws-try__file-note {
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.ws-try__badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--os-accent, #2563eb);
}

.ws-try__empty {
  margin-top: 12px;
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

/* ---------- 文件列表 ---------- */
.ws-files__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.ws-files__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.ws-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ws-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--os-border-light, #f1f3f5);
  transition: border-color 0.15s, background 0.15s;
}

.ws-item:hover {
  border-color: var(--os-border, #e5e7eb);
  background: var(--os-bg-subtle, #fafafa);
}

.ws-item__icon {
  color: var(--os-text-3, #9ca3af);
  flex: none;
}

.ws-item__main {
  flex: 1;
  min-width: 0;
}

.ws-item__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ws-item__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-item__meta {
  margin-top: 3px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.ws-item__note {
  color: var(--os-text-2, #6b7280);
}

.ws-item__time {
  margin-left: auto;
}

.ws-item__del {
  flex: none;
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--os-text-3, #9ca3af);
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
}

.ws-item:hover .ws-item__del {
  opacity: 1;
}

.ws-item__del:hover {
  background: #fee2e2;
  color: #ef4444;
}

.ws-files__empty {
  padding: 48px 20px;
  text-align: center;
  color: var(--os-text-3, #9ca3af);
  border: 1px dashed var(--os-border, #e5e7eb);
  border-radius: 12px;
}

.ws-files__empty p {
  margin: 10px 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--os-text-2, #6b7280);
}

.ws-files__empty span {
  font-size: 12px;
}

.ws-files__loading {
  display: flex;
  justify-content: center;
  padding: 40px;
}

/* ---------- 底部 ---------- */
.ws-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 26px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--os-bg-subtle, #fafafa);
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
  line-height: 1.6;
}

/* ---------- 过渡 ---------- */
.ws-fade-enter-active,
.ws-fade-leave-active {
  transition: all 0.2s;
}

.ws-fade-enter-from,
.ws-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
