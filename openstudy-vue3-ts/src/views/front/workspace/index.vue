<!--
  知识库（整页）
  ============================================================================
  2026-10-22 由「我的空间」升级而来。

  为什么是现在这个样子
  --------------------
  用户原话：「把我的空间改名知识库 就行然后他的具体功能升级为 目前知识库抽屉的那种
             就是统一管理各种知识库 每个知识库包含各种文档」。

  所以这个页面 = 原来的**知识库抽屉**（`components/KnowledgeBasePanel`）的能力，
  从抽屉里搬出来，变成一个有侧栏、有主区、能常驻浏览的完整页面：

      左：知识库列表（新建 / 改名 / 删除 / 屏蔽）
      右：选中库的文档（上传 / 粘贴文本 / 看状态 / 删除 / 重解析 / 看分块）
      顶：全站统计（几个库、几份资料、多少可检索、占多大）

  与对话页那个抽屉的分工
  ---------------------
  · 本页 = **管理**（建库、批量传、整理、删）；
  · 对话页抽屉 = **选范围**（这次提问让 AI 查哪些库）。
  两者读同一套后端数据，所以任何一边的改动另一边立刻能看到。

  ⚠️ 默认库（`isDefault=1`）不能改名、不能删除 —— 它是系统给每个人自动建的落脚点，
     删了下次上传又会重建，不如干脆锁住。
-->
<template>
  <div class="kb-page">
    <!-- ============ 顶部：标题 + 统计 ============ -->
    <header class="kbp-head">
      <div class="kbp-head__main">
        <h1 class="kbp-head__title">知识库</h1>
        <p class="kbp-head__desc">
          把课件、真题、笔记传进来，智能体出题时会自己翻这些资料。
        </p>
      </div>
      <div class="kbp-stats">
        <div class="kbp-stat">
          <span class="kbp-stat__num">{{ stats.kbCount }}</span>
          <span class="kbp-stat__label">个知识库</span>
        </div>
        <div class="kbp-stat__divider" />
        <div class="kbp-stat">
          <span class="kbp-stat__num">{{ stats.docCount }}</span>
          <span class="kbp-stat__label">份资料</span>
        </div>
        <div class="kbp-stat__divider" />
        <div class="kbp-stat">
          <span class="kbp-stat__num">{{ stats.readyCount }}</span>
          <span class="kbp-stat__label">份可检索</span>
        </div>
        <div class="kbp-stat__divider" />
        <div class="kbp-stat">
          <span class="kbp-stat__num">{{ stats.totalSizeText || '0 B' }}</span>
          <span class="kbp-stat__label">占用空间</span>
        </div>
      </div>
    </header>

    <div class="kbp-body">
      <!-- ============ 左：知识库列表 ============ -->
      <aside class="kbp-side">
        <div class="kbp-side__head">
          <span class="kbp-side__title">全部知识库</span>
          <el-button size="small" :icon="Plus" :disabled="creating" @click="promptCreate">
            新建
          </el-button>
        </div>

        <div class="kbp-side__list" v-loading="loading">
          <button
            v-for="kb in kbs"
            :key="kb.kbId"
            type="button"
            class="kbp-kb"
            :class="{ 'is-active': kb.kbId === activeKbId, 'is-blocked': kb.disabled === 1 }"
            @click="selectKb(kb.kbId)"
          >
            <span class="kbp-kb__icon">
              <OsIcon :name="kb.isDefault ? 'folder' : 'database'" :size="16" />
            </span>
            <span class="kbp-kb__main">
              <span class="kbp-kb__name-row">
                <span class="kbp-kb__name">{{ kb.name }}</span>
                <span v-if="kb.isDefault" class="kbp-kb__tag">默认</span>
                <span v-if="kb.disabled === 1" class="kbp-kb__tag is-blocked">已屏蔽</span>
              </span>
              <span class="kbp-kb__meta">{{ kb.docCount }} 份资料</span>
            </span>
            <!-- 操作只在 hover / 当前项出现，避免每个库都挂一排图标 -->
            <span v-if="!kb.isDefault" class="kbp-kb__ops">
              <span class="kbp-kb__op" title="重命名" @click.stop="promptRename(kb)">
                <OsIcon name="pen-line" :size="13" />
              </span>
              <span class="kbp-kb__op is-danger" title="删除知识库" @click.stop="removeKb(kb)">
                <OsIcon name="trash" :size="13" />
              </span>
            </span>
          </button>

          <div v-if="!loading && !kbs.length" class="kbp-side__empty">
            还没有知识库
          </div>
        </div>
      </aside>

      <!-- ============ 右：当前库的文档 ============ -->
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
              <el-tooltip
                :content="activeKb.disabled === 1 ? '取消屏蔽，让智能体能检索这个库' : '屏蔽后智能体不会检索这个库，随时可以打开'"
                placement="top"
              >
                <el-switch
                  :model-value="activeKb.disabled === 0"
                  size="small"
                  inline-prompt
                  active-text="可检索"
                  inactive-text="已屏蔽"
                  @change="toggleDisabled(activeKb)"
                />
              </el-tooltip>
              <label class="kbp-upload" :class="{ 'is-disabled': busy }">
                <input
                  ref="fileInputRef"
                  type="file"
                  :accept="KB_FILE_ACCEPT"
                  multiple
                  :disabled="busy"
                  @change="onFilesPicked"
                />
                <OsIcon name="arrow-up" :size="14" />
                <span>{{ uploading ? '上传中…' : '上传文档' }}</span>
              </label>
              <button type="button" class="kbp-btn" :disabled="busy" @click="openTextImport">
                <OsIcon name="file-text" :size="14" />
                <span>粘贴文本</span>
              </button>
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

            <div class="kbp-docs" v-loading="docsLoading">
              <div v-for="doc in activeKb.files" :key="doc.docId" class="kbp-doc">
                <div class="kbp-doc__icon">
                  <OsIcon name="file-text" :size="17" />
                </div>
                <div class="kbp-doc__main">
                  <div class="kbp-doc__name-row">
                    <span class="kbp-doc__name" :title="doc.fileName">{{ doc.fileName }}</span>
                    <el-tag :type="docTagType(doc.status)" size="small" effect="plain">
                      {{ doc.statusText }}
                    </el-tag>
                  </div>
                  <div class="kbp-doc__meta">
                    <span>{{ doc.sizeText }}</span>
                    <span v-if="doc.chunkCount">· {{ doc.chunkCount }} 个片段</span>
                    <span v-if="doc.note" class="kbp-doc__note">· {{ doc.note }}</span>
                    <span class="kbp-doc__time">{{ doc.createTime }}</span>
                  </div>
                  <div v-if="doc.status === 4 && doc.errorMsg" class="kbp-doc__err">
                    {{ doc.errorMsg }}
                  </div>
                </div>
                <div class="kbp-doc__ops">
                  <span
                    v-if="doc.status === 5"
                    class="kbp-doc__op"
                    title="看看分块切得对不对"
                    @click="showChunks(doc)"
                  >
                    <OsIcon name="eye" :size="14" />
                  </span>
                  <span
                    v-if="doc.status !== 2"
                    class="kbp-doc__op"
                    title="重新解析并向量化"
                    @click="reprocess(doc)"
                  >
                    <OsIcon name="zap" :size="14" />
                  </span>
                  <span class="kbp-doc__op is-danger" title="删除" @click="removeDoc(doc)">
                    <OsIcon name="trash" :size="14" />
                  </span>
                </div>
              </div>

              <div v-if="!docsLoading && !activeKb.files.length" class="kbp-docs__empty">
                <OsIcon name="inbox" :size="30" />
                <p>这个知识库还是空的</p>
                <span>把文件拖进来，或点右上角「上传文档」</span>
              </div>
            </div>
          </div>

          <!-- 试试 AI 会怎么找：只在默认库显示，因为它才是 AI 自动翻的地方 -->
          <section v-if="activeKb.files.length" class="kbp-try">
            <div class="kbp-try__head">
              <span class="kbp-try__title">试试 AI 会怎么找</span>
              <span class="kbp-try__hint">
                在对话里说「用我那份概率论的资料出题」时，AI 就是这么找的
              </span>
            </div>
            <div class="kbp-try__row">
              <el-input
                v-model="tryQuery"
                placeholder="例如：那份概率论的资料"
                clearable
                @keyup.enter="doTry"
              />
              <el-button type="primary" :loading="trying" @click="doTry">找找看</el-button>
            </div>
            <transition-group v-if="tryResult.length" name="kbp-fade" tag="div" class="kbp-try__result">
              <div
                v-for="(f, i) in tryResult"
                :key="f.docId"
                class="kbp-try__file"
                :class="{ 'is-best': i === 0 }"
              >
                <span class="kbp-try__rank">{{ i + 1 }}</span>
                <span class="kbp-try__file-name">{{ f.fileName }}</span>
                <span v-if="f.note" class="kbp-try__file-note">{{ f.note }}</span>
                <span v-if="i === 0" class="kbp-try__badge">最匹配</span>
              </div>
            </transition-group>
            <div v-else-if="tried" class="kbp-try__empty">
              没找到对得上的文件。可以换个说法，或者在备注里加个关键词。
            </div>
          </section>
        </template>

        <div v-else-if="!loading" class="kbp-main__empty">
          <OsIcon name="folder" :size="34" />
          <p>左边选一个知识库</p>
          <span>或者点「新建」建一个</span>
        </div>
      </section>
    </div>

    <!-- 分块预览 -->
    <el-dialog v-model="chunksVisible" :title="`分块预览 · ${chunkDocName}`" width="680px" append-to-body>
      <div class="kbp-chunks" v-loading="chunksLoading">
        <div v-for="c in chunks" :key="c.chunkId" class="kbp-chunk">
          <div class="kbp-chunk__head">
            <span class="kbp-chunk__idx">第 {{ c.chunkIndex + 1 }} 段</span>
            <span class="kbp-chunk__len">{{ c.contentLength || c.content.length }} 字</span>
            <el-tag v-if="c.images && c.images.length" type="warning" size="small" effect="light">
              {{ c.images.length }} 张图
            </el-tag>
          </div>
          <div class="kbp-chunk__text">{{ c.content }}</div>
        </div>
        <div v-if="!chunksLoading && !chunks.length" class="kbp-docs__empty">没有分块</div>
      </div>
    </el-dialog>

    <!-- 粘贴文本 -->
    <el-dialog v-model="textImportVisible" title="粘贴文本" width="640px" append-to-body @closed="resetTextImport">
      <div class="kbp-import">
        <p class="kbp-import__hint">
          把正文直接粘进来就行，不用先存成文件。导入后智能体一样能检索到。
        </p>
        <el-input
          v-model="textImportContent"
          type="textarea"
          :rows="10"
          placeholder="把课件文字、笔记、错题解析粘在这里…"
        />
        <div class="kbp-import__row">
          <span class="kbp-import__label">起个名字</span>
          <el-input v-model="textImportFileName" placeholder="例如：概率论第四章笔记" maxlength="80" />
        </div>
      </div>
      <template #footer>
        <el-button @click="textImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitTextImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import { getWorkspaceOverview, uploadToWorkspace, searchWorkspace } from '@/api/ai/workspace'
import {
  KB_FILE_ACCEPT,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  getDocumentChunks,
  importDocumentText,
  reprocessDocument,
  updateKnowledgeBase,
  uploadDocument
} from '@/api/ai/rag'

/* ===================== 状态 ===================== */

const loading = ref(false)
const creating = ref(false)
const uploading = ref(false)
const uploadTip = ref('')
const dragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const docsLoading = ref(false)

const kbs = ref<any[]>([])
const activeKbId = ref<number | null>(null)
const stats = reactive<any>({ kbCount: 0, docCount: 0, readyCount: 0, totalSizeText: '0 B' })

const activeKb = computed(() => kbs.value.find((k) => k.kbId === activeKbId.value) || null)

const busy = computed(() => uploading.value || importing.value)

/* 试试 AI 怎么找 */
const tryQuery = ref('')
const trying = ref(false)
const tried = ref(false)
const tryResult = ref<any[]>([])

/* 分块 */
const chunksVisible = ref(false)
const chunksLoading = ref(false)
const chunks = ref<any[]>([])
const chunkDocName = ref('')

/* 粘贴文本 */
const importing = ref(false)
const textImportVisible = ref(false)
const textImportContent = ref('')
const textImportFileName = ref('')

/* ===================== 加载 ===================== */

async function load(keepActive = true) {
  loading.value = true
  try {
    const res: any = await getWorkspaceOverview()
    if (res.code === 200) {
      kbs.value = res.data.knowledgeBases || []
      Object.assign(stats, res.data.stats || {})

      // 保持当前选中的库；它被删了就退回默认库
      if (!keepActive || !kbs.value.some((k) => k.kbId === activeKbId.value)) {
        activeKbId.value = res.data.defaultKbId || kbs.value[0]?.kbId || null
      }
    }
  } catch (e: any) {
    ElMessage.error('读取知识库失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function selectKb(kbId: number) {
  if (activeKbId.value === kbId) return
  activeKbId.value = kbId
  // 换库时清掉上一个库的检索结果，否则会张冠李戴
  tryResult.value = []
  tried.value = false
  tryQuery.value = ''
}

/* ===================== 知识库增删改 ===================== */

async function promptCreate() {
  try {
    const r: any = await ElMessageBox.prompt('给知识库起个名字', '新建知识库', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：概率论、数据结构期末',
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    creating.value = true
    const res: any = await createKnowledgeBase({ name: r.value.trim() })
    if (res.code === 200) {
      ElMessage.success('知识库已创建')
      await load()
      if (res.data?.kbId) activeKbId.value = res.data.kbId
    } else {
      ElMessage.error(res.msg || '创建失败')
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('创建失败：' + (e?.message || e))
  } finally {
    creating.value = false
  }
}

async function promptRename(kb: any) {
  try {
    const r: any = await ElMessageBox.prompt('改成什么名字？', '重命名知识库', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: kb.name,
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    const res: any = await updateKnowledgeBase(kb.kbId, { name: r.value.trim() })
    if (res.code === 200) {
      ElMessage.success('已重命名')
      await load()
    } else {
      ElMessage.error(res.msg || '重命名失败')
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('重命名失败：' + (e?.message || e))
  }
}

async function removeKb(kb: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${kb.name}」吗？里面的 ${kb.docCount} 份资料会一起删掉，不能恢复。`,
      '删除知识库',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res: any = await deleteKnowledgeBase(kb.kbId)
    if (res.code === 200) {
      ElMessage.success('已删除')
      if (activeKbId.value === kb.kbId) activeKbId.value = null
      await load(false)
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message || e))
  }
}

async function toggleDisabled(kb: any) {
  const next = kb.disabled === 1 ? 0 : 1
  try {
    const res: any = await updateKnowledgeBase(kb.kbId, { disabled: next })
    if (res.code === 200) {
      ElMessage.success(next === 1 ? '已屏蔽，智能体不会再检索它' : '已恢复检索')
      await load()
    } else {
      ElMessage.error(res.msg || '操作失败')
    }
  } catch (e: any) {
    ElMessage.error('操作失败：' + (e?.message || e))
  }
}

/* ===================== 文档上传 ===================== */

function onPick() {
  fileInputRef.value?.click()
}

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) await uploadFiles(files)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (busy.value || !activeKb.value) return
  const list = e.dataTransfer?.files
  if (list?.length) uploadFiles(Array.from(list))
}

async function uploadFiles(list: File[]) {
  const kb = activeKb.value
  if (!kb) return
  uploading.value = true
  let ok = 0
  let fail = 0
  try {
    for (const f of list) {
      uploadTip.value = `正在上传 ${f.name}…`
      try {
        // 默认库走 workspace 接口（能带备注语义、不需要 kbId）；其它库走通用文档上传
        const res: any = kb.isDefault
          ? await uploadToWorkspace(f)
          : await uploadDocument(kb.kbId, f)
        if (res.code === 200) ok++
        else {
          fail++
          ElMessage.error(`${f.name}：${res.msg || '上传失败'}`)
        }
      } catch (err: any) {
        fail++
        ElMessage.error(`${f.name}：${err?.message || '上传失败'}`)
      }
    }
    if (ok) {
      ElMessage.success(`已上传 ${ok} 份${fail ? `，${fail} 份失败` : ''}，正在后台解析`)
      uploadTip.value = '解析和向量化在后台跑，稍等一下状态就会变成「可检索」'
      await load()
      // 后台流水线不是瞬时的，几秒后自动再刷一次
      setTimeout(() => load(), 4000)
    } else {
      uploadTip.value = ''
    }
  } finally {
    uploading.value = false
  }
}

async function removeDoc(doc: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${doc.fileName}」吗？`, '删除资料', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await deleteDocument(doc.docId)
    if (res.code === 200) {
      ElMessage.success('已删除')
      await load()
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message || e))
  }
}

async function reprocess(doc: any) {
  try {
    const res: any = await reprocessDocument(doc.docId)
    if (res.code === 200) {
      ElMessage.success('已重新提交，稍后状态会更新')
      await load()
      setTimeout(() => load(), 4000)
    } else {
      ElMessage.error(res.msg || '重新处理失败')
    }
  } catch (e: any) {
    ElMessage.error('重新处理失败：' + (e?.message || e))
  }
}

async function showChunks(doc: any) {
  chunksVisible.value = true
  chunkDocName.value = doc.fileName
  chunksLoading.value = true
  chunks.value = []
  try {
    const res: any = await getDocumentChunks(doc.docId)
    if (res.code === 200) chunks.value = res.data || []
  } catch (e: any) {
    ElMessage.error('读取分块失败：' + (e?.message || e))
  } finally {
    chunksLoading.value = false
  }
}

/* ===================== 粘贴文本 ===================== */

function openTextImport() {
  if (busy.value) {
    ElMessage.warning('有导入正在进行，等它跑完')
    return
  }
  textImportContent.value = ''
  textImportFileName.value = ''
  textImportVisible.value = true
}

function resetTextImport() {
  textImportContent.value = ''
  textImportFileName.value = ''
}

async function submitTextImport() {
  const kb = activeKb.value
  if (!kb) return
  const content = textImportContent.value.trim()
  if (!content) {
    ElMessage.warning('先粘点内容进来')
    return
  }
  importing.value = true
  try {
    const res: any = await importDocumentText(
      kb.kbId,
      content,
      textImportFileName.value.trim() || '粘贴的文本'
    )
    if (res.code === 200) {
      ElMessage.success('已导入，后台正在分块')
      textImportVisible.value = false
      await load()
      setTimeout(() => load(), 4000)
    } else {
      ElMessage.error(res.msg || '导入失败')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || e))
  } finally {
    importing.value = false
  }
}

/* ===================== 试试 AI 怎么找 ===================== */

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

/* ===================== 工具 ===================== */

function docTagType(status: number) {
  if (status === 5) return 'success'
  if (status === 4) return 'danger'
  if (status === 2) return 'warning'
  return 'info'
}

onMounted(() => load(false))
</script>

<style scoped lang="scss">
.kb-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 24px 60px;
}

/* ---------- 头部 ---------- */
.kbp-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.kbp-head__title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.kbp-head__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
  max-width: 520px;
}

.kbp-stats {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: none;
}

.kbp-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.kbp-stat__num {
  font-size: 20px;
  font-weight: 700;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.kbp-stat__label {
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-stat__divider {
  width: 1px;
  height: 26px;
  background: var(--os-border, #e5e7eb);
}

/* ---------- 两栏 ---------- */
.kbp-body {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

/* ---------- 左：库列表 ---------- */
.kbp-side {
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.kbp-side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--os-border-light, #f1f3f5);
}

.kbp-side__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.kbp-side__list {
  padding: 6px;
  max-height: calc(100vh - 260px);
  overflow-y: auto;
}

.kbp-side__empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-kb {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: var(--os-bg-subtle, #fafafa);
  }

  &.is-active {
    background: var(--os-bg-active, #eef2ff);
  }

  &.is-blocked .kbp-kb__name {
    color: var(--os-text-3, #9ca3af);
  }

  &:hover .kbp-kb__ops {
    opacity: 1;
  }
}

.kbp-kb__icon {
  flex: none;
  color: var(--os-text-3, #9ca3af);

  .is-active & {
    color: var(--os-accent, #2563eb);
  }
}

.kbp-kb__main {
  flex: 1;
  min-width: 0;
}

.kbp-kb__name-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.kbp-kb__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-kb__tag {
  flex: none;
  padding: 0 5px;
  font-size: 10px;
  line-height: 15px;
  border-radius: 4px;
  background: var(--os-accent-50, #eff6ff);
  color: var(--os-accent, #2563eb);

  &.is-blocked {
    background: #fef3c7;
    color: #b45309;
  }
}

.kbp-kb__meta {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-kb__ops {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}

.kbp-kb__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  color: var(--os-text-3, #9ca3af);

  &:hover {
    background: var(--os-bg-hover, #f3f4f6);
    color: var(--os-text, #111827);
  }

  &.is-danger:hover {
    background: #fee2e2;
    color: #ef4444;
  }
}

/* ---------- 右：文档区 ---------- */
.kbp-main {
  min-width: 0;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
  padding: 16px 18px 18px;
}

.kbp-main__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.kbp-main__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.kbp-main__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-main__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.kbp-upload,
.kbp-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 7px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }

  &.is-disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  input {
    display: none;
  }
}

/* ---------- 拖拽投放区 ---------- */
.kbp-drop {
  position: relative;
  border-radius: 10px;
  transition: background 0.15s;

  &.is-over {
    background: var(--os-accent-50, #eff6ff);
    outline: 2px dashed var(--os-accent, #2563eb);
    outline-offset: 3px;
  }
}

.kbp-drop__mask {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  font-size: 13px;
  font-weight: 600;
  color: var(--os-accent, #2563eb);
}

.kbp-tip {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--os-accent-50, #eff6ff);
  font-size: 12px;
  color: var(--os-accent, #2563eb);
}

.kbp-docs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 120px;
}

.kbp-doc {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 9px;
  border: 1px solid transparent;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-border, #e5e7eb);
    background: var(--os-bg-subtle, #fafafa);
  }

  &:hover .kbp-doc__ops {
    opacity: 1;
  }
}

.kbp-doc__icon {
  flex: none;
  margin-top: 2px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-doc__main {
  flex: 1;
  min-width: 0;
}

.kbp-doc__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kbp-doc__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-doc__meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-doc__note {
  color: var(--os-text-2, #6b7280);
}

.kbp-doc__time {
  margin-left: auto;
}

.kbp-doc__err {
  margin-top: 4px;
  font-size: 11.5px;
  color: #ef4444;
  line-height: 1.5;
}

.kbp-doc__ops {
  display: flex;
  gap: 2px;
  flex: none;
  opacity: 0;
  transition: opacity 0.15s;
}

.kbp-doc__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 5px;
  color: var(--os-text-3, #9ca3af);
  cursor: pointer;

  &:hover {
    background: var(--os-bg-hover, #f3f4f6);
    color: var(--os-text, #111827);
  }

  &.is-danger:hover {
    background: #fee2e2;
    color: #ef4444;
  }
}

.kbp-docs__empty,
.kbp-main__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 56px 20px;
  color: var(--os-text-3, #9ca3af);
  text-align: center;

  p {
    margin: 6px 0 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--os-text-2, #6b7280);
  }

  span {
    font-size: 12px;
  }
}

/* ---------- 试试 AI 怎么找 ---------- */
.kbp-try {
  margin-top: 20px;
  padding: 16px 18px;
  border-radius: 12px;
  background: var(--os-accent-50, #eff6ff);
  border: 1px solid var(--os-accent-100, #dbeafe);
}

.kbp-try__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.kbp-try__title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.kbp-try__hint {
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.kbp-try__row {
  display: flex;
  gap: 10px;
}

.kbp-try__result {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kbp-try__file {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;

  &.is-best {
    border-color: var(--os-accent, #2563eb);
  }
}

.kbp-try__rank {
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

  .is-best & {
    background: var(--os-accent, #2563eb);
    color: #fff;
  }
}

.kbp-try__file-name {
  font-weight: 500;
  color: var(--os-text, #111827);
}

.kbp-try__file-note {
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.kbp-try__badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--os-accent, #2563eb);
}

.kbp-try__empty {
  margin-top: 10px;
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

/* ---------- 弹窗内容 ---------- */
.kbp-chunks {
  max-height: 56vh;
  overflow-y: auto;
}

.kbp-chunk {
  padding: 10px 0;
  border-bottom: 1px solid var(--os-border-light, #f1f3f5);

  &:last-child {
    border-bottom: none;
  }
}

.kbp-chunk__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-chunk__idx {
  font-weight: 600;
}

.kbp-chunk__text {
  font-size: 13px;
  line-height: 1.75;
  color: var(--os-text-2, #4b5563);
  white-space: pre-wrap;
  word-break: break-word;
}

.kbp-import__hint {
  margin: 0 0 10px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
}

.kbp-import__row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.kbp-import__label {
  flex: none;
  font-size: 13px;
  color: var(--os-text-2, #4b5563);
}

/* ---------- 过渡 ---------- */
.kbp-fade-enter-active,
.kbp-fade-leave-active {
  transition: all 0.2s;
}

.kbp-fade-enter-from,
.kbp-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ---------- 窄屏 ---------- */
@media (max-width: 900px) {
  .kbp-body {
    grid-template-columns: 1fr;
  }

  .kbp-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .kbp-side__list {
    max-height: 240px;
  }
}
</style>
