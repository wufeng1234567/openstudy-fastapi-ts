<template>
  <el-dialog
    :model-value="modelValue"
    title="版本对照"
    width="1080px"
    top="6vh"
    append-to-body
    class="version-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="version-shell" v-loading="loading">
      <aside class="version-timeline">
        <div class="version-timeline__head">
          <div>
            <span class="version-eyebrow">VERSION HISTORY</span>
            <h3>{{ doc?.fileName || '资料版本' }}</h3>
          </div>
          <span class="version-timeline__count">{{ versions.length }} 个快照</span>
        </div>
        <p class="version-timeline__hint">
          每次保存、整理或恢复前都会留一份快照。点一个版本，和当前正文做左右对照。
        </p>
        <div v-if="!versions.length" class="version-timeline__empty">暂无历史版本</div>
        <button
          v-for="version in versions"
          :key="version.versionId"
          type="button"
          class="version-item"
          :class="{ 'is-active': selectedFrom === version.versionId }"
          @click="selectVersion(version)"
        >
          <span class="version-item__dot"></span>
          <span class="version-item__body">
            <b>{{ version.createTime }}</b>
            <em>{{ version.reason }}</em>
            <span>{{ version.contentLength }} 字</span>
          </span>
        </button>
        <button type="button" class="version-item is-current" :class="{ 'is-active': selectedFrom === 0 }" @click="selectCurrent">
          <span class="version-item__dot"></span>
          <span class="version-item__body">
            <b>当前正文</b>
            <em>编辑器里正在展示的内容</em>
            <span>与历史版本对照</span>
          </span>
        </button>
      </aside>

      <section class="version-main">
        <div class="version-compare-head">
          <div class="version-compare-title">
            <span class="version-eyebrow">COMPARE</span>
            <h3>{{ diff?.from?.createTime || '选择版本' }} <i>→</i> {{ diff?.to?.createTime || '当前正文' }}</h3>
          </div>
          <div class="version-compare-selects">
            <el-select v-model="selectedFrom" size="small" placeholder="历史版本" @change="loadDiff">
              <el-option v-for="version in versions" :key="version.versionId" :label="`${version.createTime} · ${version.reason}`" :value="version.versionId" />
              <el-option label="当前正文" :value="0" />
            </el-select>
            <span>→</span>
            <el-select v-model="selectedTo" size="small" placeholder="对比目标" @change="loadDiff">
              <el-option label="当前正文" :value="0" />
              <el-option v-for="version in versions" :key="version.versionId" :label="`${version.createTime} · ${version.reason}`" :value="version.versionId" />
            </el-select>
          </div>
        </div>

        <div v-if="diff" class="version-stats">
          <div class="version-stat">
            <span>新增行</span>
            <b class="is-add">+{{ diff.stats.addedLines }}</b>
          </div>
          <div class="version-stat">
            <span>删除行</span>
            <b :class="diff.stats.removedLines ? 'is-remove' : ''">{{ diff.stats.removedLines ? `-${diff.stats.removedLines}` : '0' }}</b>
          </div>
          <div class="version-stat">
            <span>字数变化</span>
            <b :class="diff.stats.charDelta >= 0 ? 'is-add' : 'is-remove'">
              {{ diff.stats.charDelta >= 0 ? '+' : '' }}{{ diff.stats.charDelta }}
            </b>
          </div>
          <div class="version-stat">
            <span>体检分变化</span>
            <b :class="diff.health.scoreDelta >= 0 ? 'is-add' : 'is-remove'">
              {{ diff.health.scoreDelta >= 0 ? '+' : '' }}{{ diff.health.scoreDelta }}
            </b>
            <em>{{ diff.health.before.score }} → {{ diff.health.after.score }}</em>
          </div>
          <div class="version-stat">
            <span>问题数变化</span>
            <b :class="diff.health.issueDelta <= 0 ? 'is-add' : 'is-remove'">
              {{ diff.health.issueDelta >= 0 ? '+' : '' }}{{ diff.health.issueDelta }}
            </b>
            <em>{{ diff.health.before.issueCount }} → {{ diff.health.after.issueCount }}</em>
          </div>
        </div>

        <div v-if="diff?.identical" class="version-identical">
          <div class="version-identical__icon">＝</div>
          <div>
            <b>两个版本正文一致</b>
            <span>没有文本差异，可以放心关闭。</span>
          </div>
        </div>

        <div v-else-if="diff" class="version-diff">
          <div class="version-diff__head">
            <span>{{ diff.from.fileName }} · {{ diff.from.reason }}</span>
            <span>{{ diff.to.fileName }} · {{ diff.to.reason }}</span>
          </div>
          <div class="version-diff__body">
            <div class="version-diff__column version-diff__column--old">
              <div v-for="(row, index) in diff.rows" :key="`old-${index}`" class="version-line" :class="`is-${row.type}`">
                <span class="version-line__no">{{ row.leftNo ?? '' }}</span>
                <code>{{ row.left || ' ' }}</code>
              </div>
            </div>
            <div class="version-diff__column version-diff__column--new">
              <div v-for="(row, index) in diff.rows" :key="`new-${index}`" class="version-line" :class="`is-${row.type}`">
                <span class="version-line__no">{{ row.rightNo ?? '' }}</span>
                <code>{{ row.right || ' ' }}</code>
              </div>
            </div>
          </div>
          <div v-if="diff.rows.length >= 600" class="version-diff__limit">差异较长，只展示前 600 行；统计口径仍按全文计算。</div>
        </div>

        <div class="version-main__foot">
          <span>恢复历史版本不会覆盖当前内容：系统会先保存当前快照，再生成新版本。</span>
          <el-button
            v-if="selectedFrom"
            type="primary"
            plain
            :loading="restoring"
            @click="askRestore"
          >
            恢复这个版本
          </el-button>
        </div>
      </section>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { diffDocumentVersions, listDocumentVersions, restoreDocumentVersion } from '@/api/ai/workspace'

const props = defineProps<{
  modelValue: boolean
  doc?: { docId: number; fileName: string } | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'restored', version: any): void
}>()

const loading = ref(false)
const restoring = ref(false)
const versions = ref<any[]>([])
const selectedFrom = ref<number | null>(null)
const selectedTo = ref(0)
const diff = ref<any>(null)

async function load() {
  if (!props.doc?.docId) return
  loading.value = true
  versions.value = []
  selectedFrom.value = null
  selectedTo.value = 0
  diff.value = null
  try {
    const res: any = await listDocumentVersions(props.doc.docId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '读取历史版本失败')
      return
    }
    versions.value = res.data || []
    if (versions.value.length) {
      selectedFrom.value = versions.value[0].versionId
      await loadDiff()
    }
  } catch (error: any) {
    ElMessage.error('读取历史版本失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

async function loadDiff() {
  if (!props.doc?.docId || selectedFrom.value == null) return
  loading.value = true
  try {
    const res: any = await diffDocumentVersions(props.doc.docId, selectedFrom.value, selectedTo.value)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '读取版本对照失败')
      return
    }
    diff.value = res.data
  } catch (error: any) {
    ElMessage.error('读取版本对照失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

function selectVersion(version: any) {
  selectedFrom.value = version.versionId
  selectedTo.value = 0
  loadDiff()
}

function selectCurrent() {
  selectedFrom.value = 0
  selectedTo.value = versions.value[0]?.versionId || 0
  loadDiff()
}

async function askRestore() {
  if (!props.doc?.docId || !selectedFrom.value) return
  try {
    await ElMessageBox.confirm(
      '恢复这个历史版本？恢复前会先把当前内容自动保存一份，之后仍可再次恢复。',
      '恢复历史版本',
      { type: 'warning', confirmButtonText: '恢复这个版本', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  restoring.value = true
  try {
    const res: any = await restoreDocumentVersion(props.doc.docId, selectedFrom.value)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '恢复失败')
      return
    }
    ElMessage.success('历史版本已恢复，正在重新解析')
    emit('restored', { versionId: selectedFrom.value })
    emit('update:modelValue', false)
  } catch (error: any) {
    ElMessage.error('恢复失败：' + (error?.message || error))
  } finally {
    restoring.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) load()
  }
)
</script>

<style scoped>
.version-shell {
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr);
  min-height: 540px;
  overflow: hidden;
  border: 1px solid #e9ecf2;
  border-radius: 12px;
}

.version-timeline {
  display: flex;
  flex-direction: column;
  padding: 16px 13px;
  border-right: 1px solid #eef0f5;
  background: #fbfcfe;
}

.version-eyebrow {
  color: #4f6bed;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.version-timeline__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.version-timeline__head h3 {
  margin: 5px 0 0;
  color: #1f2937;
  font-size: 14px;
  line-height: 1.4;
}

.version-timeline__count {
  flex: none;
  color: #9aa1af;
  font-size: 9px;
}

.version-timeline__hint {
  margin: 10px 0 12px;
  color: #8a91a0;
  font-size: 10px;
  line-height: 1.65;
}

.version-timeline__empty {
  padding: 30px 0;
  color: #a0a6b2;
  font-size: 11px;
  text-align: center;
}

.version-item {
  display: flex;
  width: 100%;
  gap: 8px;
  padding: 9px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
}

.version-item:hover {
  background: #f5f7fb;
}

.version-item.is-active {
  border-color: rgba(79, 107, 237, 0.16);
  background: #eef2ff;
}

.version-item.is-current {
  margin-top: auto;
  border-style: dashed;
}

.version-item__dot {
  flex: none;
  width: 7px;
  height: 7px;
  margin-top: 4px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #b5bfd4;
  box-shadow: 0 0 0 1px #c3ccdd;
}

.version-item.is-active .version-item__dot {
  background: #4f6bed;
  box-shadow: 0 0 0 2px rgba(79, 107, 237, 0.2);
}

.version-item__body {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.version-item__body b {
  color: #4b5563;
  font-size: 10.5px;
  font-weight: 600;
}

.version-item__body em {
  overflow: hidden;
  color: #8a91a0;
  font-size: 9.5px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-item__body span {
  color: #b0b6c1;
  font-size: 9px;
}

.version-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 16px;
}

.version-compare-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.version-compare-title h3 {
  margin: 5px 0 0;
  color: #1f2937;
  font-size: 14px;
  font-weight: 600;
}

.version-compare-title h3 i {
  padding: 0 5px;
  color: #a0a6b2;
  font-style: normal;
}

.version-compare-selects {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.version-compare-selects span {
  color: #a0a6b2;
  font-size: 11px;
}

.version-compare-selects :deep(.el-select) {
  width: 175px;
}

.version-stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 7px;
  margin: 14px 0 11px;
}

.version-stat {
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid #eef0f5;
  border-radius: 8px;
  background: #fbfcfe;
}

.version-stat span {
  display: block;
  color: #9aa1af;
  font-size: 9px;
}

.version-stat b {
  display: inline-block;
  margin-top: 4px;
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

.version-stat b.is-add { color: #2f9e8f; }
.version-stat b.is-remove { color: #c45656; }

.version-stat em {
  display: block;
  margin-top: 3px;
  color: #b0b6c1;
  font-size: 8.5px;
  font-style: normal;
}

.version-diff {
  overflow: hidden;
  border: 1px solid #e9ecf2;
  border-radius: 9px;
}

.version-diff__head {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid #eef0f5;
  background: #fbfcfe;
}

.version-diff__head span {
  overflow: hidden;
  padding: 7px 10px;
  color: #8a91a0;
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-diff__head span + span {
  border-left: 1px solid #eef0f5;
}

.version-diff__body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  max-height: 360px;
  overflow: auto;
  background: #fff;
}

.version-diff__column {
  min-width: 0;
}

.version-diff__column + .version-diff__column {
  border-left: 1px solid #eef0f5;
}

.version-line {
  display: flex;
  min-height: 22px;
  align-items: flex-start;
  gap: 7px;
  padding: 2px 7px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 10px;
  line-height: 1.6;
}

.version-line__no {
  flex: none;
  width: 24px;
  color: #b7bdc8;
  text-align: right;
  user-select: none;
}

.version-line code {
  min-width: 0;
  overflow-wrap: anywhere;
  color: #596173;
  font-family: inherit;
  white-space: pre-wrap;
}

.version-line.is-add { background: #f0faf7; }
.version-line.is-add code { color: #1f7a6d; }
.version-line.is-remove { background: #fff5f5; }
.version-line.is-remove code { color: #b34141; }
.version-line.is-change { background: #fffaf0; }
.version-line.is-change code { color: #946523; }

.version-diff__limit {
  padding: 6px 10px;
  border-top: 1px solid #eef0f5;
  color: #a0a6b2;
  background: #fbfcfe;
  font-size: 9px;
}

.version-identical {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 18px;
  padding: 18px;
  border: 1px solid #e6f4f1;
  border-radius: 9px;
  background: #f6fcfa;
}

.version-identical__icon {
  display: flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #2f9e8f;
  background: #e2f5f0;
  font-size: 20px;
}

.version-identical b {
  display: block;
  color: #2f6d63;
  font-size: 12px;
}

.version-identical span {
  display: block;
  margin-top: 3px;
  color: #82a9a1;
  font-size: 10px;
}

.version-main__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding-top: 14px;
  color: #a0a6b2;
  font-size: 9.5px;
  line-height: 1.6;
}

@media (max-width: 1000px) {
  .version-shell {
    grid-template-columns: 1fr;
  }

  .version-timeline {
    border-right: none;
    border-bottom: 1px solid #eef0f5;
  }

  .version-item.is-current {
    margin-top: 0;
  }

  .version-stats {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
