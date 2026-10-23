<!--
  词库详情（英语学习）
  ============================================================================
  2026-10-23 重写。原实现有整片字段错位，功能从来没通：

    · 后端返回 `wordId / word / translation / phonetic / example`，
      前端读的是 `word.id / word.english / word.chinese`；
    · 前端还用了 `wordType`、`isMastered` —— **后端表里根本没有这两列**
      （`words` 只有 word_id / book_id / word / phonetic / translation /
        example / audio_url / sort_order / create_time）；
      于是"掌握状态"开关永远发不出去、「类型」筛选永远筛不到东西。
    · 编辑保存把 `{id, english, chinese, wordType}` 放 JSON body，
      后端要的是 Query 参数 `wordId / word / translation`。

  这次按后端真实契约重写：
    · 字段全部对齐（wordId / word / translation / phonetic / example）；
    · 去掉不存在的「掌握状态 / 类型」——不假装有；
    · 增删改都走 Query 参数；
    · 保留能用的能力：朗读、OCR 识词、搜索、分页。
-->
<template>
  <div class="wd-page">
    <header class="wd-head">
      <button type="button" class="wd-back" @click="goBack">
        <OsIcon name="arrow-left" :size="16" />
        <span>词库</span>
      </button>
      <div class="wd-head__main">
        <h1 class="wd-head__title">{{ bookInfo.bookName || '词库' }}</h1>
        <p class="wd-head__desc">
          {{ bookInfo.bookDescription || '还没有说明' }}
        </p>
      </div>
      <div class="wd-head__ops">
        <button type="button" class="wd-btn" @click="ocrVisible = true">
          <OsIcon name="sparkles" :size="14" />
          <span>拍照识词</span>
        </button>
        <button type="button" class="wd-btn is-primary" @click="openCreate">
          <OsIcon name="plus" :size="14" />
          <span>添加单词</span>
        </button>
      </div>
    </header>

    <!-- 搜索 -->
    <div class="wd-toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索单词或释义"
        clearable
        :prefix-icon="Search"
        class="wd-search"
      />
      <span class="wd-count">
        共 <b>{{ words.length }}</b> 个单词
        <template v-if="keyword.trim()">，匹配 {{ filtered.length }} 个</template>
      </span>
    </div>

    <!-- 列表 -->
    <div v-loading="loading" class="wd-body">
      <div v-if="!loading && !filtered.length" class="wd-empty">
        <div class="wd-empty__art">
          <OsIcon :name="keyword.trim() ? 'search' : 'book'" :size="26" />
        </div>
        <p class="wd-empty__title">
          {{ keyword.trim() ? `没有匹配「${keyword}」的单词` : '这个词库还是空的' }}
        </p>
        <span class="wd-empty__desc">
          {{
            keyword.trim()
              ? '换个词试试，或清空搜索'
              : '手动加几个单词，或者用「拍照识词」从图片里抓'
          }}
        </span>
        <div class="wd-empty__actions">
          <button v-if="keyword.trim()" type="button" class="wd-btn" @click="keyword = ''">
            清空搜索
          </button>
          <button v-else type="button" class="wd-btn is-primary" @click="openCreate">
            添加单词
          </button>
        </div>
      </div>

      <div v-else class="wd-list">
        <div v-for="w in pagedWords" :key="w.wordId" class="wd-item">
          <div class="wd-item__main">
            <div class="wd-item__word-row">
              <span class="wd-item__word">{{ w.word }}</span>
              <button
                type="button"
                class="wd-item__say"
                title="朗读"
                @click="speak(w.word)"
              >
                <OsIcon name="megaphone" :size="13" />
              </button>
              <span v-if="w.phonetic" class="wd-item__phonetic">/{{ w.phonetic }}/</span>
            </div>
            <div class="wd-item__trans">{{ w.translation || '（还没有释义）' }}</div>
            <div v-if="w.example" class="wd-item__example">{{ w.example }}</div>
          </div>
          <div class="wd-item__ops">
            <span class="wd-item__op" title="编辑" @click="openEdit(w)">
              <OsIcon name="pen-line" :size="14" />
            </span>
            <span class="wd-item__op is-danger" title="删除" @click="removeWord(w)">
              <OsIcon name="trash" :size="14" />
            </span>
          </div>
        </div>
      </div>

      <div v-if="filtered.length > pageSize" class="wd-pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="filtered.length"
          layout="prev, pager, next"
          small
          background
        />
      </div>
    </div>

    <!-- OCR 识词 -->
    <OcrRecognizer v-model="ocrVisible" :word-book-id="bookId" @success="load" />

    <!-- 新增 / 编辑单词 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑单词' : '添加单词'"
      width="460px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="单词 / 词组" prop="word">
          <el-input v-model="form.word" placeholder="例如：abandon" maxlength="100" clearable />
        </el-form-item>
        <el-form-item label="中文释义" prop="translation">
          <el-input v-model="form.translation" placeholder="例如：v. 放弃；抛弃" maxlength="200" clearable />
        </el-form-item>
        <el-form-item label="音标（选填）" prop="phonetic">
          <el-input v-model="form.phonetic" placeholder="例如：əˈbændən" maxlength="100" clearable />
        </el-form-item>
        <el-form-item label="例句（选填）" prop="example">
          <el-input
            v-model="form.example"
            type="textarea"
            :rows="2"
            placeholder="放一句带这个词的句子，复习时更有语境"
            maxlength="300"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          {{ editingId ? '保存' : '添加' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishVocabularyDetail' })
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { getWordBooks } from '@/api/wordBooks/wordBooks'
import { listAllWords, addWords, updateWords, delWords } from '@/api/words/words'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { speak as speakText, isSpeechSupported, speakReasonText } from '@/utils/speech'
import OcrRecognizer from '@/components/OcrRecognizer/index.vue'

const router = useRouter()
const route = useRoute()
const cacheStore = useFrontPageCacheStore()

const bookId = ref<number | null>(null)

/**
 * 词书信息 —— 字段名与后端 `format_word_book` 一致：
 * `bookId / bookName / bookDescription / wordCount / isDefault`
 * （原实现读的是 `bookInfo.name`，永远拿不到，标题一直是「词库详情」）
 */
const bookInfo = ref<any>({})

const words = ref<any[]>([])
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = 20

const ocrVisible = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<any>(null)
const form = ref({ word: '', translation: '', phonetic: '', example: '' })

const rules = {
  word: [
    { required: true, message: '请输入单词', trigger: 'blur' },
    { max: 100, message: '最多 100 个字符', trigger: 'blur' }
  ],
  translation: [{ max: 200, message: '最多 200 个字符', trigger: 'blur' }],
  phonetic: [{ max: 100, message: '最多 100 个字符', trigger: 'blur' }]
}

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return words.value
  return words.value.filter(
    (w) =>
      String(w.word || '').toLowerCase().includes(k) ||
      String(w.translation || '').toLowerCase().includes(k)
  )
})

const pagedWords = computed(() => {
  const start = (page.value - 1) * pageSize
  return filtered.value.slice(start, start + pageSize)
})

watch(keyword, () => {
  page.value = 1
})

async function loadBook() {
  if (!bookId.value) return
  try {
    const res: any = await getWordBooks(bookId.value)
    if (res.code === 200) bookInfo.value = res.data || {}
  } catch {
    // 词书信息取不到不阻塞单词列表，标题退回默认文案
  }
}

async function load() {
  if (!bookId.value) {
    ElMessage.error('没有拿到词库 ID，请从「我的词库」重新进入')
    return
  }
  loading.value = true
  try {
    // ⚠️ 后端参数名是 `bookId`（不是 wordBookId）
    //
    // ⚠️ 2026-10-23 修「系统接口 422 异常」：
    //    这里原来是 `listWords({ bookId, pageNum: 1, pageSize: 1000 })`，
    //    而后端是 `pageSize: int = Query(50, ge=1, le=200)` —— 1000 超上限，
    //    FastAPI 直接返 HTTP 422，整页读不出单词。
    //    详情页需要「这本书的全部单词」，所以改用 listAllWords（内部按 200 翻页取完）。
    const res: any = await listAllWords({ bookId: bookId.value })
    if (res.code === 200) {
      words.value = res.rows || []
    } else {
      ElMessage.error(res.msg || '读取单词失败')
    }
  } catch (e: any) {
    ElMessage.error('读取单词失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = { word: '', translation: '', phonetic: '', example: '' }
  dialogVisible.value = true
}

function openEdit(w: any) {
  editingId.value = w.wordId
  form.value = {
    word: w.word || '',
    translation: w.translation || '',
    phonetic: w.phonetic || '',
    example: w.example || ''
  }
  dialogVisible.value = true
}

function resetForm() {
  editingId.value = null
  form.value = { word: '', translation: '', phonetic: '', example: '' }
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (!bookId.value) return

  saving.value = true
  try {
    const payload = {
      word: form.value.word.trim(),
      translation: form.value.translation.trim() || undefined,
      phonetic: form.value.phonetic.trim() || undefined,
      example: form.value.example.trim() || undefined
    }
    const res: any = editingId.value
      ? await updateWords({ wordId: editingId.value, ...payload })
      : await addWords({ bookId: bookId.value, ...payload })

    if (res.code === 200) {
      ElMessage.success(editingId.value ? '已保存' : '已添加')
      dialogVisible.value = false
      await load()
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}

async function removeWord(w: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${w.word}」吗？`, '删除单词', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await delWords(w.wordId)
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

/**
 * 朗读单词
 *
 * 2026-10-23 改：原来直接 `window.speechSynthesis.speak()`，有两个问题：
 *  · 不指定 `voice`，只用 `lang='en-US'` 靠引擎自己挑。系统里没有英文语音包时
 *    会**静默不响**（onerror 没人接）；
 *  · `cancel()` 之后立刻 `speak()`，Chrome 下这一发有概率被直接丢弃。
 * 现在统一走 @/utils/speech，失败会明确告诉用户原因，而不是点了没反应。
 */
async function speak(text: string) {
  if (!text) return
  if (!isSpeechSupported()) {
    ElMessage.warning(speakReasonText('unsupported', 'en-US'))
    return
  }
  const res = await speakText(text, { lang: 'en-US', rate: 0.85 })
  if (!res.ok) {
    if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
      ElMessage.warning(speakReasonText(res.reason, 'en-US'))
    }
  }
}

function goBack() {
  cacheStore.setLastVisited('english', 'vocabulary')
  router.push('/front/english/vocabulary')
}

function syncFromRoute() {
  const raw = route.params.id
  const id = Number(raw)
  if (!id || Number.isNaN(id)) {
    ElMessage.error('词库 ID 不合法')
    return
  }
  if (bookId.value === id) return
  bookId.value = id
  page.value = 1
  keyword.value = ''
  loadBook()
  load()
}

onMounted(syncFromRoute)

// keep-alive 回到本页（换了 id 才重新拉，避免每次切回来都请求）
onActivated(() => {
  const id = Number(route.params.id)
  if (id && id !== bookId.value) syncFromRoute()
})

watch(() => route.params.id, (nv, ov) => {
  if (nv && nv !== ov) syncFromRoute()
})
</script>

<style scoped lang="scss">
.wd-page {
  max-width: 920px;
  margin: 0 auto;
  padding: 20px 20px 60px;
}

/* ---------- 头部 ---------- */
.wd-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 18px;
}

.wd-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 10px;
  flex: none;
  font-size: 13px;
  font-family: inherit;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 7px;
  background: #fff;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }
}

.wd-head__main {
  flex: 1;
  min-width: 0;
}

.wd-head__title {
  margin: 0 0 4px;
  font-size: 21px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.wd-head__desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

.wd-head__ops {
  display: flex;
  gap: 8px;
  flex: none;
}

.wd-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 13px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 8px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }

  &.is-primary {
    background: var(--os-text, #111827);
    border-color: var(--os-text, #111827);
    color: #fff;

    &:hover {
      background: #000;
      border-color: #000;
      color: #fff;
    }
  }
}

/* ---------- 工具条 ---------- */
.wd-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.wd-search {
  max-width: 300px;
}

.wd-count {
  font-size: 12.5px;
  color: var(--os-text-3, #9ca3af);

  b {
    color: var(--os-text, #111827);
    font-weight: 600;
  }
}

/* ---------- 列表 ---------- */
.wd-body {
  min-height: 220px;
}

.wd-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wd-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-border, #e5e7eb);
    background: var(--os-bg-subtle, #fafafa);
  }

  &:hover .wd-item__ops {
    opacity: 1;
  }
}

.wd-item__main {
  flex: 1;
  min-width: 0;
}

.wd-item__word-row {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
}

.wd-item__word {
  font-size: 15px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.wd-item__say {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--os-text-3, #9ca3af);
  cursor: pointer;

  &:hover {
    background: var(--os-bg-hover, #f3f4f6);
    color: var(--os-accent, #2563eb);
  }
}

.wd-item__phonetic {
  font-size: 12.5px;
  color: var(--os-text-3, #9ca3af);
}

.wd-item__trans {
  margin-top: 3px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--os-text-2, #4b5563);
}

.wd-item__example {
  margin-top: 5px;
  padding-left: 9px;
  border-left: 2px solid var(--os-border, #e5e7eb);
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

.wd-item__ops {
  display: flex;
  gap: 2px;
  flex: none;
  opacity: 0;
  transition: opacity 0.15s;
}

.wd-item__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
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

.wd-pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

/* ---------- 空态 ---------- */
.wd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 60px 20px;
  text-align: center;
  border: 1px dashed var(--os-border, #e5e7eb);
  border-radius: 14px;
  background: var(--os-bg-subtle, #fafafa);
}

.wd-empty__art {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  margin-bottom: 2px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid var(--os-border-light, #f1f3f5);
  color: var(--os-text-3, #9ca3af);
}

.wd-empty__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.wd-empty__desc {
  max-width: 340px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

.wd-empty__actions {
  margin-top: 6px;
}

@media (max-width: 720px) {
  .wd-head {
    flex-wrap: wrap;
  }

  .wd-head__ops {
    width: 100%;
    justify-content: flex-end;
  }

  .wd-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .wd-search {
    max-width: none;
  }
}
</style>
