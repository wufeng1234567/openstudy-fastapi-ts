<!--
  资产装配台
  ----------------------------------------------------------------------------
  把「一份资料」拆成可拖拽的章节素材，再装配成不同形态的学习产物。

  交互不是只看颜色：
    · 拖拽：左侧章节拖到右侧装配区；装配区内可拖拽排序；
    · 点击：点章节卡片也能加入；点 × 移除；点章节标题展开原文；
    · 搜索：素材区可按标题/正文筛选；
    · 提示：每一步都有空态提示和装配数量提示；
    · 连接：装配区用竖向编号线把章节顺序串起来。

  产物模板全部来自原文，不调用模型：
    · 复习卡：每节压缩到约 300 字；
    · 讲义：保留选中章节全文；
    · 提纲：只保留章节标题 + 首句。
  题单/微课不在这里伪造，分别引导到智能出题与现有微课生成。
-->
<template>
  <el-dialog v-model="visible" width="1120px" top="4vh" append-to-body destroy-on-close class="sp-dialog">
    <template #header>
      <div class="sp-head">
        <div>
          <div class="sp-head__eyebrow">学习资产装配台</div>
          <div class="sp-head__title">把《{{ docName }}》装配成学习产物</div>
        </div>
        <div class="sp-head__meta">拖拽章节 → 调整顺序 → 生成并下载</div>
      </div>
    </template>

    <div v-loading="loading" class="sp-body">
      <div class="sp-mode">
        <button
          v-for="mode in modes"
          :key="mode.key"
          type="button"
          class="sp-mode__item"
          :class="{ 'is-active': packType === mode.key }"
          @click="packType = mode.key"
        >
          <b>{{ mode.label }}</b>
          <span>{{ mode.desc }}</span>
        </button>
      </div>

      <div class="sp-grid">
        <!-- 左：素材区 -->
        <section class="sp-panel sp-panel--source">
          <div class="sp-panel__head">
            <span>素材区 · {{ sections.length }} 个章节</span>
            <el-input v-model="keyword" size="small" clearable placeholder="搜索章节" class="sp-search" />
          </div>
          <div class="sp-source-list">
            <div
              v-for="section in filteredSections"
              :key="section.index"
              class="sp-source"
              :class="{ 'is-picked': isPicked(section), 'is-expanded': expanded.has(section.index) }"
              draggable="true"
              tabindex="0"
              role="button"
              @dragstart="onDragStart($event, section)"
              @dragend="dragSource = null"
              @click="addSection(section)"
              @keydown.enter.prevent="addSection(section)"
              @keydown.space.prevent="addSection(section)"
            >
              <span class="sp-source__dot" :class="`is-${section.coverage}`"></span>
              <span class="sp-source__main">
                <span class="sp-source__title">{{ section.title }}</span>
                <span class="sp-source__meta">{{ section.chars }} 字 · {{ section.questions }} 题 · {{ section.images }} 图</span>
                <span v-if="expanded.has(section.index)" class="sp-source__body">{{ section.fullText }}</span>
              </span>
              <button
                type="button"
                class="sp-source__expand"
                @click.stop="toggleExpand(section)"
              >{{ expanded.has(section.index) ? '收起' : '展开' }}</button>
              <span v-if="isPicked(section)" class="sp-source__picked">已加入</span>
            </div>
            <div v-if="!filteredSections.length" class="sp-empty">没有匹配的章节，换个关键词试试。</div>
          </div>
        </section>

        <!-- 右：装配区 -->
        <section class="sp-panel sp-panel--assembly">
          <div class="sp-panel__head">
            <span>装配区 · {{ picked.length }} 个章节</span>
            <button v-if="picked.length" type="button" class="sp-clear" @click="picked = []">清空</button>
          </div>
          <div
            class="sp-drop"
            :class="{ 'is-over': dragOverAssembly }"
            @dragover.prevent="dragOverAssembly = true"
            @dragleave.prevent="dragOverAssembly = false"
            @drop.prevent="onDropAssembly"
          >
            <div v-if="!picked.length" class="sp-drop__empty">
              <div class="sp-drop__icon">＋</div>
              <b>把左侧章节拖到这里</b>
              <span>也可以直接点击章节卡片加入；装配区里的条目可以拖拽排序。</span>
            </div>
            <div v-else class="sp-picked">
              <div
                v-for="(section, index) in picked"
                :key="section.index"
                class="sp-picked__item"
                draggable="true"
                @dragstart="onDragStart($event, section, index)"
                @dragend="dragSource = null"
                @dragover.prevent
                @drop.stop.prevent="onDropReorder(index)"
              >
                <span class="sp-picked__no">{{ index + 1 }}</span>
                <span class="sp-picked__main">
                  <span class="sp-picked__title">{{ section.title }}</span>
                  <span class="sp-picked__meta">{{ section.chars }} 字</span>
                </span>
                <span class="sp-picked__moves">
                  <button type="button" :disabled="index === 0" title="上移" @click.stop="moveSection(index, -1)">↑</button>
                  <button type="button" :disabled="index === picked.length - 1" title="下移" @click.stop="moveSection(index, 1)">↓</button>
                </span>
                <button type="button" class="sp-picked__remove" title="移出装配区" aria-label="移出装配区" @click.stop="removeSection(index)">×</button>
              </div>
            </div>
          </div>
          <div class="sp-assembly-foot">
            <span>预计 {{ pickedChars }} 字</span>
            <span>·</span>
            <span>{{ packTypeLabel }}模板</span>
          </div>
        </section>
      </div>

      <div class="sp-other">
        <span class="sp-other__label">其他资产</span>
        <button type="button" class="sp-other__item" @click="copyQuestionPrompt">题单 · 智能出题</button>
        <button type="button" class="sp-other__item" @click="emit('micro', currentDoc)">微课 · 现有生成器</button>
        <span class="sp-other__hint">题单与微课不在本地硬拼，分别走智能出题和微课生成。</span>
      </div>
    </div>

    <template #footer>
      <div class="sp-footer">
        <span class="sp-footer__hint">产物全部来自当前资料原文，不会编造内容。</span>
        <div class="sp-footer__actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="!picked.length" :loading="exporting" @click="exportPack('markdown')">
            生成 Markdown
          </el-button>
          <el-button type="primary" plain :disabled="!picked.length" :loading="exporting" @click="exportPack('docx')">
            生成 Word
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { saveAs } from 'file-saver'
import { getDocumentContent, exportDocument } from '@/api/ai/rag'
import { getDocumentHealth } from '@/api/ai/workspace'
import { blobValidate } from '@/utils/ruoyi'

defineOptions({ name: 'StudyPackDialog' })

interface PackDoc {
  docId: number
  fileName?: string
}

const emit = defineEmits<{
  (e: 'micro', doc: PackDoc | null): void
}>()

const visible = ref(false)
const loading = ref(false)
const exporting = ref(false)
const currentDoc = ref<PackDoc | null>(null)
const content = ref('')
const sections = ref<any[]>([])
const picked = ref<any[]>([])
const keyword = ref('')
const expanded = ref(new Set<number>())
const packType = ref<'review' | 'lecture' | 'outline'>('review')
const dragSource = ref<{ section: any; index: number | null } | null>(null)
const dragOverAssembly = ref(false)
let openSeq = 0

const modes = [
  { key: 'review' as const, label: '复习卡', desc: '每节压到 300 字，适合考前速览' },
  { key: 'lecture' as const, label: '讲义', desc: '保留选中章节全文，适合打印' },
  { key: 'outline' as const, label: '提纲', desc: '只留标题与首句，适合搭框架' }
]

const docName = computed(() => currentDoc.value?.fileName || '未命名资料')

const filteredSections = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return sections.value
  return sections.value.filter((s: any) =>
    `${s.title || ''} ${s.fullText || ''}`.toLowerCase().includes(key)
  )
})

const pickedChars = computed(() =>
  picked.value.reduce((sum: number, s: any) => sum + Number(s.chars || 0), 0)
)

const packTypeLabel = computed(
  () => modes.find((m) => m.key === packType.value)?.label || '复习卡'
)

function sectionFullText(section: any): string {
  const start = Number(section.start || 0)
  const end = Number(section.end || 0)
  return String(content.value || '').slice(start, end).replace(/【图\d+】/g, '').trim()
}

function isPicked(section: any): boolean {
  return picked.value.some((s: any) => s.index === section.index)
}

function addSection(section: any) {
  if (isPicked(section)) return
  picked.value.push(section)
}

function removeSection(index: number) {
  picked.value.splice(index, 1)
}

function moveSection(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= picked.value.length) return
  const item = picked.value[index]
  picked.value.splice(index, 1)
  picked.value.splice(target, 0, item)
}

function toggleExpand(section: any) {
  const next = new Set(expanded.value)
  if (next.has(section.index)) next.delete(section.index)
  else next.add(section.index)
  expanded.value = next
}

function onDragStart(event: DragEvent, section: any, index: number | null = null) {
  dragSource.value = { section, index }
  event.dataTransfer?.setData('text/openstudy-section', String(section.index))
  event.dataTransfer?.setDragImage?.(event.target as Element, 12, 12)
}

function onDropAssembly() {
  dragOverAssembly.value = false
  const source = dragSource.value
  if (!source) return
  if (source.index == null && source.section) {
    addSection(source.section)
  } else if (source.index != null) {
    // 从装配区内部拖到空白处 = 移到末尾。
    const item = picked.value[source.index]
    if (item) {
      picked.value.splice(source.index, 1)
      picked.value.push(item)
    }
  }
  dragSource.value = null
}

function onDropReorder(targetIndex: number) {
  const source = dragSource.value
  if (!source) return
  // 从左侧素材区拖到装配区已有条目上时，index 为 null：这是「新增」，不是「排序」。
  if (source.index == null) {
    addSection(source.section)
    dragSource.value = null
    return
  }
  const from = source.index
  const item = picked.value[from]
  if (!item) {
    dragSource.value = null
    return
  }
  if (from === targetIndex) {
    dragSource.value = null
    return
  }
  // 统一语义：都插到「目标条目之前」。删除后目标索引会前移一位，需要校正。
  const to = from < targetIndex ? targetIndex - 1 : targetIndex
  picked.value.splice(from, 1)
  picked.value.splice(to, 0, item)
  dragSource.value = null
}

function buildPack(): string {
  const lines: string[] = []
  const title = docName.value.replace(/\.[^.]+$/, '')
  if (packType.value === 'outline') {
    lines.push(`# ${title} · 学习提纲`, '', `> 从《${docName.value}》装配 · ${picked.value.length} 个章节`, '')
    for (const section of picked.value) {
      const first = String(section.excerpt || '').split(/[。！？]/)[0]
      lines.push(`## ${section.title}`, first ? `${first}。` : '', '')
    }
    return lines.join('\n')
  }
  lines.push(
    packType.value === 'review' ? `# ${title} · 复习卡` : `# ${title} · 学习讲义`,
    '',
    `> 从《${docName.value}》装配 · ${picked.value.length} 个章节`,
    ''
  )
  for (const section of picked.value) {
    lines.push(`## ${section.title}`, '')
    const full = sectionFullText(section)
    if (packType.value === 'review') {
      lines.push(full.slice(0, 300).trim() + (full.length > 300 ? '…' : ''), '')
    } else {
      lines.push(full, '')
    }
  }
  return lines.join('\n')
}

async function exportPack(format: 'markdown' | 'docx') {
  if (!currentDoc.value?.docId || !picked.value.length) return
  exporting.value = true
  try {
    const text = buildPack()
    const blob: any = await exportDocument(currentDoc.value.docId, format, text)
    // axios 对 blob 响应不做 code 校验：后端业务失败会以 JSON Blob 返回。
    // 不校验就 saveAs，会把错误信息存成 .md/.docx 并提示成功。
    if (!(blob instanceof Blob) || blob.size === 0 || !blobValidate(blob)) {
      let msg = '导出失败'
      try {
        const parsed = JSON.parse(await blob.text())
        msg = parsed?.msg || parsed?.message || msg
      } catch { /* 非 JSON 错误体，保留通用提示 */ }
      ElMessage.error(msg)
      return
    }
    const stem = docName.value.replace(/\.[^.]+$/, '')
    const suffix = packType.value === 'review' ? '复习卡' : packType.value === 'lecture' ? '讲义' : '提纲'
    saveAs(new Blob([blob]), `${stem}-${suffix}.${format === 'docx' ? 'docx' : 'md'}`)
    ElMessage.success(`${packTypeLabel.value}已生成`)
  } catch (e: any) {
    ElMessage.error('生成失败：' + (e?.message || e))
  } finally {
    exporting.value = false
  }
}

async function copyQuestionPrompt() {
  const name = docName.value.replace(/\.[^.]+$/, '')
  const prompt = `用《${name}》按章节生成一套分层题单：每个章节 3 道基础题 + 2 道变式题，给出答案与解析，并为每题标注原文依据。`
  try {
    await navigator.clipboard.writeText(prompt)
    ElMessage.success('已复制出题指令，粘贴到对话里即可')
  } catch {
    ElMessage.info(prompt)
  }
}

async function open(doc: PackDoc) {
  const seq = ++openSeq
  currentDoc.value = doc
  visible.value = true
  loading.value = true
  // 先清空旧状态，避免请求失败时出现「新文档标题 + 旧文档章节」。
  content.value = ''
  sections.value = []
  picked.value = []
  keyword.value = ''
  expanded.value = new Set()
  dragSource.value = null
  dragOverAssembly.value = false
  try {
    const [contentRes, healthRes] = await Promise.all([
      getDocumentContent(doc.docId),
      getDocumentHealth(doc.docId)
    ])
    if (seq !== openSeq) return
    if (contentRes.code === 200) content.value = contentRes.data?.content || ''
    if (healthRes.code !== 200) throw new Error(healthRes.msg || '读取体检信息失败')
    sections.value = (healthRes.data?.sections || []).map((section: any) => ({
      ...section,
      fullText: sectionFullText(section)
    }))
    // 默认把得分最高的前 3 个章节放进装配区，用户一打开就能看到「可生成」。
    picked.value = [...sections.value]
      .filter((s: any) => s.coverage !== 'thin')
      .slice(0, 3)
  } catch (e: any) {
    if (seq === openSeq) ElMessage.error('读取资料失败：' + (e?.message || e))
  } finally {
    if (seq === openSeq) loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.sp-dialog :deep(.el-dialog__body) {
  padding-top: 4px;
}

.sp-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-right: 28px;
}

.sp-head__eyebrow {
  margin-bottom: 3px;
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.sp-head__title {
  color: #111827;
  font-size: 18px;
  font-weight: 700;
}

.sp-head__meta {
  color: #9ca3af;
  font-size: 11.5px;
}

.sp-body {
  min-height: 480px;
}

.sp-mode {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  margin-bottom: 12px;
}

.sp-mode__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 11px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.sp-mode__item b {
  color: #374151;
  font-size: 12.5px;
}

.sp-mode__item span {
  color: #9ca3af;
  font-size: 10.5px;
}

.sp-mode__item.is-active {
  border-color: #93c5fd;
  background: #eff6ff;
}

.sp-mode__item.is-active b {
  color: #1d4ed8;
}

.sp-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.92fr);
  gap: 12px;
}

.sp-panel {
  min-width: 0;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}

.sp-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 11px;
  border-bottom: 1px solid #f0f2f5;
  color: #111827;
  font-size: 12.5px;
  font-weight: 700;
}

.sp-search {
  width: 160px;
}

.sp-source-list {
  height: 348px;
  overflow: auto;
}

.sp-source {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 11px;
  border-top: 1px solid #f6f7f9;
  cursor: grab;
  user-select: none;
}

.sp-source:first-child {
  border-top: 0;
}

.sp-source:hover {
  background: #f8fafc;
}

.sp-source.is-picked {
  background: #f0f7ff;
}

.sp-source__dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
}

.sp-source__dot.is-good { background: #16a34a; }
.sp-source__dot.is-partial { background: #f59e0b; }
.sp-source__dot.is-thin { background: #ef4444; }

.sp-source__main {
  min-width: 0;
}

.sp-source__title {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sp-source__meta {
  display: block;
  margin-top: 2px;
  color: #9ca3af;
  font-size: 10.5px;
}

.sp-source__body {
  display: block;
  max-height: 100px;
  margin-top: 5px;
  overflow: auto;
  color: #6b7280;
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.sp-source__expand {
  flex: none;
  margin-left: auto;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 10.5px;
  cursor: pointer;
}

.sp-source__picked {
  flex: none;
  color: #2563eb;
  font-size: 10px;
}

.sp-drop {
  min-height: 348px;
  margin: 10px;
  border: 1.5px dashed #dbe3ee;
  border-radius: 9px;
  background: #fbfcfe;
  transition: border-color 0.15s, background 0.15s;
}

.sp-drop.is-over {
  border-color: #2563eb;
  background: #eff6ff;
}

.sp-drop__empty {
  display: flex;
  height: 330px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #9ca3af;
  text-align: center;
}

.sp-drop__icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid #dbe3ee;
  border-radius: 50%;
  color: #94a3b8;
  font-size: 19px;
}

.sp-drop__empty b {
  color: #6b7280;
  font-size: 12.5px;
}

.sp-drop__empty span {
  max-width: 250px;
  font-size: 10.5px;
  line-height: 1.6;
}

.sp-picked {
  padding: 8px;
}

.sp-picked__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #fff;
  cursor: grab;
}

.sp-picked__item + .sp-picked__item {
  margin-top: 6px;
}

.sp-picked__no {
  display: grid;
  width: 20px;
  height: 20px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  font-size: 10.5px;
  font-weight: 700;
}

.sp-picked__main {
  min-width: 0;
}

.sp-picked__title {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 11.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sp-picked__meta {
  color: #9ca3af;
  font-size: 10px;
}

.sp-picked__moves {
  display: flex;
  gap: 2px;
  margin-left: auto;
}

.sp-picked__moves button {
  width: 22px;
  height: 22px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  color: #6b7280;
  font-size: 11px;
  cursor: pointer;
}

.sp-picked__moves button:disabled {
  color: #d1d5db;
  cursor: default;
}

.sp-picked__remove {
  margin-left: 4px;
  border: 0;
  background: transparent;
  color: #cbd5e1;
  font-size: 16px;
  cursor: pointer;
}

.sp-picked__remove:hover {
  color: #ef4444;
}

.sp-assembly-foot {
  display: flex;
  gap: 6px;
  padding: 0 12px 10px;
  color: #9ca3af;
  font-size: 10.5px;
}

.sp-other {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 11px;
  padding: 9px 12px;
  border: 1px solid #f0e6c8;
  border-radius: 8px;
  background: #fffdf5;
}

.sp-other__label {
  color: #92400e;
  font-size: 11px;
  font-weight: 700;
}

.sp-other__item {
  padding: 2px 8px;
  border: 1px solid #fde68a;
  border-radius: 999px;
  background: #fff;
  color: #92400e;
  font-size: 10.5px;
  cursor: pointer;
}

.sp-other__item:hover {
  border-color: #f59e0b;
}

.sp-other__hint {
  color: #b8a98a;
  font-size: 10px;
}

.sp-empty {
  padding: 30px 16px;
  color: #9ca3af;
  font-size: 12px;
  text-align: center;
}

.sp-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sp-footer__hint {
  color: #9ca3af;
  font-size: 11px;
}

.sp-footer__actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 900px) {
  .sp-grid,
  .sp-mode {
    grid-template-columns: 1fr;
  }
}
</style>
