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
        <!--
          导出（2026-10-26）
          ---------------------------------------------------------------
          用户反馈：「能手写、能从图片/文档导入，但导不出去，想打印或换设备就卡住了」。

          三种格式各自解决不同场景：
            · Anki  —— 导入记忆卡软件，带标签/间隔重复
            · Excel —— 打印、二次编辑、给同事
            · Word  —— 打印成纸质单词表

          全部在**纯前端**生成（Blob 下载），不占后端带宽、也不依赖网络 ——
          Anki 是纯文本格式、Excel 用 SpreadsheetML（一个 XML 就能表达）、
          Word 用 HTML 加 `.doc` 扩展名（Word 能直接打开，排版比纯文本好得多）。
          这样连装包都不用，也避免为三种格式各写一个后端接口。
        -->
        <el-dropdown trigger="click" @command="handleExport">
          <button type="button" class="wd-btn" :disabled="exporting || !words.length">
            <OsIcon name="download" :size="14" />
            <span>{{ exporting ? '导出中…' : '导出' }}</span>
            <OsIcon name="chevron-down" :size="12" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="anki">
                Anki 卡片（.txt）
              </el-dropdown-item>
              <el-dropdown-item command="excel">
                Excel 表格（.xls）
              </el-dropdown-item>
              <el-dropdown-item command="word">
                Word 文档（.doc）
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <button type="button" class="wd-btn is-primary" @click="openCreate">
          <OsIcon name="plus" :size="14" />
          <span>添加单词</span>
        </button>
      </div>
    </header>

    <!-- 搜索 -->
    <!--
      进度条 + 开始听写（2026-10-26）
      ============================================================================
      用户提了两件事，它们其实是同一个需求的两面：
        · 「词库这边添加一个一键跳转听力练习的按钮，位置要好，不要太拥挤」
        · 「提供记忆曲线，用户今天刷了，词库那边标记为已学习过，
           下次学习的时候可以换一批」

      所以这一条同时解决"去哪儿练"和"练到哪了"：

        左边  → 记忆曲线进度（已掌握 / 学习中 / 新词），一眼看到还剩多少
        右边  → 「开始听写」主按钮，点了直接带着**今天该复习的词**进练习

      ## 为什么放在搜索栏上方，而不是 header 的按钮组里

        header 现在已经有「拍照识词 / 导出 / 添加单词」三个按钮，
        再加一个必然挤成一行小按钮，且语义也不对：
        那三个是**编辑词库**，这个是**去学习**，是两种不同的意图。

      放在这里的好处：
        · 视觉上有独立一行，不挤压任何已有控件；
        · 和学习进度挨在一起，形成"看进度 → 去练习"的动线；
        · 搜索栏就在下面，用户想找某个词也不受影响。
    -->
    <div class="wd-learn">
      <div class="wd-learn__progress">
        <!--
          进度条：三段色块
          ---------------------------------------------------------------
          mastered（绿）= 已掌握，learning（蓝）= 学习中，new（灰）= 新词。
          宽度按占比算，总数为 0 时不显示色块（避免除零）。
        -->
        <div class="wd-learn__bar" v-if="mastery.total > 0" :title="masteryTitle">
          <i
            class="seg is-mastered"
            :style="{ width: pct(mastery.mastered) }"
          />
          <i
            class="seg is-learning"
            :style="{ width: pct(mastery.learning) }"
          />
          <i class="seg is-new" :style="{ width: pct(mastery.new) }" />
        </div>
        <div class="wd-learn__meta">
          <span class="m is-mastered">
            <b>{{ mastery.mastered }}</b> 已掌握
          </span>
          <span class="m is-learning">
            <b>{{ mastery.learning }}</b> 学习中
          </span>
          <span class="m is-new">
            <b>{{ mastery.new }}</b> 未学
          </span>
          <!--
            今日待复习：只有 >0 才显示。
            这个数字是记忆曲线的"发起信号" —— 它一出现，用户就知道该练了。
          -->
          <span v-if="dueCount > 0" class="wd-learn__due">
            今天该复习 <b>{{ dueCount }}</b> 个
          </span>
        </div>
      </div>

      <div class="wd-learn__ops">
        <button
          type="button"
          class="wd-btn"
          :disabled="!words.length"
          :title="dueCount > 0 ? `先练今天到期的 ${dueCount} 个词` : '按词库顺序练全部单词'"
          @click="startListening()"
        >
          <OsIcon name="book-open" :size="14" />
          <span>开始听写</span>
        </button>
        <!--
          「练新词」入口：只在还有未学的词时出现
          ---------------------------------------------------------------
          这就是用户说的「下次学习的时候可以换一批」——
          点它只练**没学过的**，等于自动换了一批。
        -->
        <button
          v-if="mastery.new > 0"
          type="button"
          class="wd-btn is-primary"
          :title="`练还没学过的 ${mastery.new} 个词`"
          @click="startListening('new')"
        >
          <OsIcon name="sparkles" :size="14" />
          <span>练新词（{{ mastery.new }}）</span>
        </button>
      </div>
    </div>

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

    <!--
      批量操作工具栏（2026-10-26）
      ---------------------------------------------------------------
      改前只能一条一条删，几十上百个词时想清理几乎不可能。
      现在：勾选任意一条就浮出这条工具栏，支持全选当前页 / 反选 / 批量删除。
      没勾选时不占位置（不挤压上面的搜索区）。
    -->
    <div class="wd-bulk" v-if="checkedIds.size > 0">
      <span class="wd-bulk__info">
        已选 <b>{{ checkedIds.size }}</b> 条
      </span>
      <div class="wd-bulk__ops">
        <button type="button" class="wd-btn" @click="selectAllOnPage">全选本页</button>
        <button type="button" class="wd-btn" @click="clearChecked">取消选择</button>
        <button type="button" class="wd-btn is-danger" @click="removeChecked" :disabled="batchDeleting">
          {{ batchDeleting ? '删除中…' : `删除所选（${checkedIds.size}）` }}
        </button>
      </div>
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
        <div v-for="w in pagedWords" :key="w.wordId" class="wd-item" :class="{ 'is-checked': checkedIds.has(w.wordId) }">
          <!--
            批量选择（2026-10-26）
            改前只能一条一条删 —— 词库里有几十上百个词时，
            想清掉一批几乎不可能。这里加复选框，配合顶部工具栏的批量删除。
          -->
          <label class="wd-item__check" :title="'选择 ' + w.word">
            <input
              type="checkbox"
              :checked="checkedIds.has(w.wordId)"
              @change="toggleCheck(w.wordId)"
            />
          </label>
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
import { listAllWords, addWords, updateWords, delWords, getBookMastery, getDueWords } from '@/api/words/words'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { speak as speakText, isSpeechSupported, speakReasonText, warmUpVoices } from '@/utils/speech'
import OcrRecognizer from '@/components/OcrRecognizer/index.vue'
// 词库导出（2026-10-26）：Anki / Excel / Word，纯前端生成
import { exportWordBook, type ExportFormat } from '@/utils/wordbook-export'

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
/** 批量删除进行中（防止重复点击） */
const batchDeleting = ref(false)
/** 导出中（防止重复点击） */
const exporting = ref(false)

/* ============================================================================
 * 记忆曲线（2026-10-26）
 *
 * 这块数据来自 `/words/practice/mastery?bookId=`，反映这本书里
 * 每个词学到什么程度了：
 *
 *   mastered  已掌握（SM-2 stage 8，不再进日常复习）
 *   learning  学习中（stage 1~7，按 due_date 排期）
 *   new       没学过
 *
 * 「今天该复习几个」单独查一次 `/words/practice/due?bookId=&limit=1`，
 * 只为拿 count —— 那个接口真正返回的是词列表，这里不需要列表。
 * ========================================================================== */
const mastery = ref({
  mastered: 0,
  learning: 0,
  new: 0,
  total: 0,
  masteryRate: 0
})

/** 今天到期的复习词数 */
const dueCount = ref(0)

/** 进度条的悬浮提示：把三段数字说清楚 */
const masteryTitle = computed(
  () =>
    `共 ${mastery.value.total} 个词：` +
    `已掌握 ${mastery.value.mastered}，` +
    `学习中 ${mastery.value.learning}，` +
    `未学 ${mastery.value.new}`
)

/** 某一段占的百分比（给进度条用） */
function pct(n: number): string {
  const total = mastery.value.total || 0
  if (!total) return '0%'
  return ((n / total) * 100).toFixed(2) + '%'
}

async function loadMastery() {
  if (!bookId.value) return
  try {
    const [m, d] = await Promise.all([
      getBookMastery(bookId.value),
      getDueWords({ bookId: bookId.value, limit: 1 })
    ])
    const md: any = (m as any)?.data ?? m
    if (md && typeof md === 'object') {
      mastery.value = {
        mastered: Number(md.mastered || 0),
        learning: Number(md.learning || 0),
        new: Number(md.new || 0),
        total: Number(md.total || 0),
        masteryRate: Number(md.masteryRate || 0)
      }
    }
    const dd: any = (d as any)?.data ?? d
    dueCount.value = Number(dd?.count || 0)
  } catch (e) {
    // 进度拿不到不影响主流程（词列表已经出来了），静默处理
    console.warn('加载记忆曲线进度失败:', e)
  }
}

/**
 * 带着参数跳到听写页
 *
 * @param scope 'due' = 今天该复习的（默认）；'new' = 还没学过的；'all' = 整本
 *
 * 为什么用 URL 而不是 sessionStorage：
 *   · 可分享 —— 用户能把这链接发给同学；
 *   · 可刷新 —— 刷一下还在同一组题；
 *   · 可回退 —— 浏览器后退能回词库页。
 *   听写页读 `auto=1` 会自动开练，见 listening/index.vue 的 consumeSeedWords。
 */
function startListening(scope: 'due' | 'new' | 'all' = 'due') {
  const query: Record<string, string> = {
    auto: '1',
    bookId: String(bookId.value || ''),
    scope
  }
  router.push({ path: '/front/english/listening', query })
}

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

/* ============================================================================
 * 批量操作（2026-10-26）
 *
 * 改前只能一条一条删 —— 词库有几十上百个词时想清理一批几乎不可能。
 * 现在勾选后浮出工具栏，支持全选本页 / 取消 / 批量删除。
 *
 * ⚠️ 为什么用 `Set` 而不是数组：勾选/取消是高频操作，
 *    `Array.includes` 是 O(n)，词库几百条时每帧都要扫一遍；
 *    `Set.has` 是 O(1)。模板里 `checkedIds.has(w.wordId)` 直接查。
 * ========================================================================== */

const checkedIds = ref<Set<number>>(new Set())

/** 勾选/取消一条 */
function toggleCheck(wordId: number) {
  const next = new Set(checkedIds.value)
  if (next.has(wordId)) next.delete(wordId)
  else next.add(wordId)
  checkedIds.value = next
}

/** 全选当前页（不是整个词库 —— 用户看到的才是他想要的） */
function selectAllOnPage() {
  const next = new Set(checkedIds.value)
  pagedWords.value.forEach((w: any) => next.add(w.wordId))
  checkedIds.value = next
}

/** 取消全部选择 */
function clearChecked() {
  checkedIds.value = new Set()
}

/**
 * 批量删除所选单词
 *
 * ⚠️ 逐条调用 `delWords`：后端 `/words/words/{id}` 是单删接口，没有批量端点。
 *    串行发（不是 `Promise.all`）是有意的 —— 词库可能有几百条，
 *    并发几百个 DELETE 会把连接池打满、也容易被限流中间件拦。
 *    串行慢一点，但结果可预期；进度条会告诉用户还剩多少。
 */
async function removeChecked() {
  const ids = Array.from(checkedIds.value)
  if (!ids.length) return

  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 个单词吗？删除后不可恢复。`,
      '批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  batchDeleting.value = true
  let ok = 0
  let failed = 0
  try {
    for (const id of ids) {
      try {
        const res: any = await delWords(id)
        if (res.code === 200) ok++
        else failed++
      } catch {
        failed++
      }
    }

    if (failed === 0) {
      ElMessage.success(`已删除 ${ok} 个单词`)
    } else {
      ElMessage.warning(`删除完成：成功 ${ok} 个，失败 ${failed} 个`)
    }

    clearChecked()
    await load()
  } finally {
    batchDeleting.value = false
  }
}

/* ============================================================================
 * 导出（2026-10-26）
 *
 * 导出的是**这本书的全部单词**（`words`），不是当前搜索过滤后的结果 ——
 * 用户点「导出」时想的是"把这本词库导出去"，而不是"导出我现在筛出来的这几条"。
 * 如果确实想导筛选结果，先清空搜索框再看会更符合直觉。
 * ========================================================================== */
const EXPORT_LABEL: Record<ExportFormat, string> = {
  anki: 'Anki 卡片',
  excel: 'Excel 表格',
  word: 'Word 文档'
}

async function handleExport(format: ExportFormat) {
  if (!words.value.length) {
    ElMessage.warning('这个词库还没有单词')
    return
  }
  exporting.value = true
  try {
    exportWordBook(format, words.value, {
      bookName: bookInfo.value.bookName || '词库',
      description: bookInfo.value.bookDescription || ''
    })
    ElMessage.success(`已导出 ${words.value.length} 个单词为 ${EXPORT_LABEL[format]}`)
  } catch (e: any) {
    console.error('导出失败:', e)
    ElMessage.error('导出失败：' + (e?.message || e))
  } finally {
    // 下载是同步触发的，给一点缓冲让用户看到"导出中"再复位
    setTimeout(() => {
      exporting.value = false
    }, 600)
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
 */async function speak(text: string) {
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
  // 记忆曲线进度跟着词库一起刷（2026-10-26）
  loadMastery()
}

onMounted(() => {
  // 预热语音列表：让「朗读」按钮点击时不必 await，保住用户手势上下文
  warmUpVoices()
  syncFromRoute()
})

// keep-alive 回到本页（换了 id 才重新拉，避免每次切回来都请求）
onActivated(() => {
  const id = Number(route.params.id)
  if (id && id !== bookId.value) {
    syncFromRoute()
  } else {
    /*
     * 同一本词库返回时也要刷进度（2026-10-26）
     *
     * 用户从听写页练完点「去我的词库」回来，最想看的就是
     * 「已掌握」那个数字变了没有。不刷的话他看到的是进练习前的旧值，
     * 会以为"练了没用"。
     */
    loadMastery()
  }
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

/* ---------- 学习进度 + 开始听写（2026-10-26） ---------- */
/*
 * 一条独立的横条，夹在头部和搜索栏之间。
 * 左半边是记忆曲线进度（三段进度条 + 数字），右半边是练习入口。
 *
 * 用 `flex-wrap: wrap`：窄屏时右侧按钮组会掉到下一行，
 * 而不是把进度条压成一条线 —— 这是"不要拥挤"的兜底。
 */
.wd-learn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--os-border, #eef0f3);
  border-radius: 12px;
  background: var(--os-bg-soft, #fafbfc);
}

.wd-learn__progress {
  flex: 1;
  min-width: 220px;
}

/* 三段进度条：绿=已掌握 蓝=学习中 灰=未学 */
.wd-learn__bar {
  display: flex;
  width: 100%;
  height: 7px;
  border-radius: 4px;
  overflow: hidden;
  background: #e5e7eb;

  .seg {
    display: block;
    height: 100%;
    transition: width 0.3s ease;

    &.is-mastered {
      background: #10b981;
    }
    &.is-learning {
      background: #3b82f6;
    }
    &.is-new {
      background: #d1d5db;
    }
  }
}

.wd-learn__meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);

  .m {
    b {
      font-weight: 600;
      color: var(--os-text, #111827);
    }

    /* 用小圆点传达颜色，比整段上色克制 */
    &:before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 6px;
      margin-right: 5px;
      border-radius: 50%;
      vertical-align: 1px;
    }

    &.is-mastered:before {
      background: #10b981;
    }
    &.is-learning:before {
      background: #3b82f6;
    }
    &.is-new:before {
      background: #d1d5db;
    }
  }
}

/* 今日待复习：整条里唯一的高亮 —— 它是"该行动了"的信号 */
.wd-learn__due {
  padding: 2px 8px;
  border-radius: 6px;
  background: #fef3c7;
  color: #b45309;
  font-size: 11.5px;

  b {
    font-weight: 700;
  }
}

.wd-learn__ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  flex-wrap: wrap;
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

/* ---------- 批量操作工具栏（2026-10-26） ---------- */
.wd-bulk {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #eff6ff;
  border: 1px solid #dbeafe;

  .wd-bulk__info {
    font-size: 13px;
    color: #1e40af;

    b {
      font-weight: 600;
    }
  }

  .wd-bulk__ops {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
}

/* 勾选行的视觉反馈：一眼看出哪几条被选中 */
.wd-item.is-checked {
  background: #f0f7ff;
  border-color: #bfdbfe;
}

.wd-item__check {
  display: flex;
  align-items: center;
  padding-top: 2px;
  flex: none;
  cursor: pointer;

  input {
    width: 15px;
    height: 15px;
    cursor: pointer;
    accent-color: #3b82f6;
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
