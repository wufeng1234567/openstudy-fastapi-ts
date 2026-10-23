<!--
  我的词库（英语学习）
  ============================================================================
  2026-10-23 重写。原实现有一整片字段错位，功能从来没真正跑通过：

    · 请求打 `/wordBooks/wordBooks/front/list` —— 后端**没有这个路由**，
      被 catch_all 兜底成「假 200 + 空 rows」，所以永远显示"还没有词库"；
    · 后端返回 `bookId / bookName / bookDescription / wordCount`，
      前端读的却是 `book.id / book.name / book.description`；
    · 点卡片 `router.push(.../${book.id})` → id 是 undefined → 跳到
      `/front/english/vocabulary/undefined`，详情页必然打不开；
    · 新建时把 `{name, description}` 放 JSON body，而后端要的是 Query 参数
      `bookName / bookDescription`。

  这些都不是"样式不好看"，是**功能根本没通**。所以整页按后端真实契约重写。
-->
<template>
  <div class="vocab-page">
    <header class="vp-head">
      <div class="vp-head__main">
        <h1 class="vp-head__title">我的词库</h1>
        <p class="vp-head__desc">
          把要背的单词整理成词库，之后可以听写、也可以让 AI 用它们出题。
        </p>
      </div>
      <button type="button" class="vp-new" @click="openCreate">
        <OsIcon name="plus" :size="15" />
        <span>新建词库</span>
      </button>
    </header>

    <!-- 搜索 -->
    <div class="vp-search">
      <el-input
        v-model="keyword"
        placeholder="搜索词库名称"
        clearable
        :prefix-icon="Search"
      />
    </div>

    <!-- 列表 -->
    <div v-loading="loading" class="vp-body">
      <div v-if="!loading && !filteredBooks.length" class="vp-empty">
        <div class="vp-empty__art">
          <OsIcon :name="keyword ? 'search' : 'book'" :size="28" />
        </div>
        <p class="vp-empty__title">
          {{ keyword ? `没有匹配「${keyword}」的词库` : '还没有词库' }}
        </p>
        <span class="vp-empty__desc">
          {{
            keyword
              ? '换个关键词试试，或清空搜索看全部'
              : '建一个词库，把要背的单词放进去'
          }}
        </span>
        <div class="vp-empty__actions">
          <button v-if="keyword" type="button" class="vp-btn" @click="keyword = ''">
            清空搜索
          </button>
          <button v-else type="button" class="vp-btn is-primary" @click="openCreate">
            新建词库
          </button>
        </div>
      </div>

      <template v-else>
        <!-- 系统预置 -->
        <template v-if="defaultBooks.length">
          <div class="vp-group-title">系统词库</div>
          <div class="vp-grid">
            <div
              v-for="b in defaultBooks"
              :key="b.bookId"
              class="vp-card is-default"
              @click="openBook(b)"
            >
              <div class="vp-card__icon"><OsIcon name="book" :size="18" /></div>
              <div class="vp-card__main">
                <div class="vp-card__name-row">
                  <span class="vp-card__name">{{ b.bookName }}</span>
                  <span class="vp-tag">预置</span>
                </div>
                <div class="vp-card__meta">{{ b.wordCount || 0 }} 个单词</div>
              </div>
            </div>
          </div>
        </template>

        <!-- 我的 -->
        <template v-if="myBooks.length">
          <div class="vp-group-title">我的词库</div>
          <div class="vp-grid">
            <div
              v-for="b in myBooks"
              :key="b.bookId"
              class="vp-card"
              @click="openBook(b)"
            >
              <div class="vp-card__icon"><OsIcon name="book" :size="18" /></div>
              <div class="vp-card__main">
                <div class="vp-card__name-row">
                  <span class="vp-card__name">{{ b.bookName }}</span>
                </div>
                <div class="vp-card__meta">
                  {{ b.wordCount || 0 }} 个单词
                  <span v-if="b.bookDescription" class="vp-card__desc">
                    · {{ b.bookDescription }}
                  </span>
                </div>
              </div>
              <div class="vp-card__ops">
                <span class="vp-card__op" title="重命名" @click.stop="openRename(b)">
                  <OsIcon name="pen-line" :size="13" />
                </span>
                <span class="vp-card__op is-danger" title="删除词库" @click.stop="removeBook(b)">
                  <OsIcon name="trash" :size="13" />
                </span>
              </div>
            </div>
          </div>
        </template>
      </template>
    </div>

    <!-- 新建 / 重命名 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '重命名词库' : '新建词库'"
      width="420px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="词库名称" prop="bookName">
          <el-input v-model="form.bookName" placeholder="例如：四级核心词" maxlength="50" show-word-limit clearable />
        </el-form-item>
        <el-form-item label="一句话说明（选填）" prop="bookDescription">
          <el-input
            v-model="form.bookDescription"
            type="textarea"
            placeholder="这个词库是干什么用的，帮你以后一眼认出来"
            maxlength="200"
            show-word-limit
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          {{ editingId ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishVocabulary' })
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'
import {
  listWordBooks,
  addWordBooks,
  updateWordBooks,
  delWordBooks
} from '@/api/wordBooks/wordBooks'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const loading = ref(false)
const keyword = ref('')
/** 后端返回的是 `bookName / bookDescription / wordCount / isDefault` */
const books = ref<any[]>([])

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<any>(null)
const form = ref({ bookName: '', bookDescription: '' })

const rules = {
  bookName: [
    { required: true, message: '请输入词库名称', trigger: 'blur' },
    { max: 50, message: '最多 50 个字', trigger: 'blur' }
  ],
  bookDescription: [{ max: 200, message: '最多 200 个字', trigger: 'blur' }]
}

const filteredBooks = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return books.value
  return books.value.filter(
    (b) =>
      String(b.bookName || '').toLowerCase().includes(k) ||
      String(b.bookDescription || '').toLowerCase().includes(k)
  )
})

const defaultBooks = computed(() => filteredBooks.value.filter((b) => b.isDefault === 1))
const myBooks = computed(() => filteredBooks.value.filter((b) => b.isDefault !== 1))

async function load() {
  loading.value = true
  try {
    const res: any = await listWordBooks({ pageNum: 1, pageSize: 200 })
    // 注意：分页接口返回的是 `rows`（不是 data）
    if (res.code === 200) {
      books.value = res.rows || []
    } else {
      ElMessage.error(res.msg || '读取词库失败')
    }
  } catch (e: any) {
    ElMessage.error('读取词库失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = { bookName: '', bookDescription: '' }
  dialogVisible.value = true
  setTimeout(() => formRef.value?.clearValidate?.(), 0)
}

function openRename(b: any) {
  editingId.value = b.bookId
  form.value = { bookName: b.bookName, bookDescription: b.bookDescription || '' }
  dialogVisible.value = true
  setTimeout(() => formRef.value?.clearValidate?.(), 0)
}

function resetForm() {
  editingId.value = null
  form.value = { bookName: '', bookDescription: '' }
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      bookName: form.value.bookName.trim(),
      bookDescription: form.value.bookDescription.trim() || undefined
    }
    const res: any = editingId.value
      ? await updateWordBooks({ bookId: editingId.value, ...payload })
      : await addWordBooks(payload)

    if (res.code === 200) {
      ElMessage.success(editingId.value ? '已重命名' : '词库已创建')
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

async function removeBook(b: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${b.bookName}」吗？里面的 ${b.wordCount || 0} 个单词会一起删掉。`,
      '删除词库',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res: any = await delWordBooks(b.bookId)
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

/** 打开词书详情：`bookId` 一定有值（后端字段名就是 bookId） */
function openBook(b: any) {
  if (!b?.bookId) {
    ElMessage.error('这个词库缺少 ID，打不开')
    return
  }
  cacheStore.setLastVisited('english', `vocabulary/${b.bookId}`)
  router.push(`/front/english/vocabulary/${b.bookId}`)
}

onMounted(load)
</script>

<style scoped lang="scss">
.vocab-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px 20px 60px;
}

/* ---------- 头部 ---------- */
.vp-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.vp-head__title {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.vp-head__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
  max-width: 520px;
}

.vp-new {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 15px;
  flex: none;
  font-size: 13.5px;
  font-weight: 500;
  font-family: inherit;
  border: none;
  border-radius: 8px;
  background: var(--os-text, #111827);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: #000;
  }
}

/* ---------- 搜索 ---------- */
.vp-search {
  max-width: 320px;
  margin-bottom: 20px;
}

/* ---------- 列表 ---------- */
.vp-body {
  min-height: 260px;
}

.vp-group-title {
  margin: 4px 0 10px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--os-text-3, #9ca3af);
}

.vp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}

.vp-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 15px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 11px;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-border-strong, #d1d5db);
    background: var(--os-bg-subtle, #fafafa);
  }

  &:hover .vp-card__ops {
    opacity: 1;
  }
}

.vp-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 10px;
  background: var(--os-bg-subtle, #f3f4f6);
  color: var(--os-text-2, #4b5563);
}

.vp-card__main {
  flex: 1;
  min-width: 0;
}

.vp-card__name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.vp-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vp-tag {
  flex: none;
  padding: 0 5px;
  font-size: 10px;
  line-height: 15px;
  border-radius: 4px;
  background: var(--os-accent-50, #eff6ff);
  color: var(--os-accent, #2563eb);
}

.vp-card__meta {
  margin-top: 3px;
  font-size: 12px;
  color: var(--os-text-3, #9ca3af);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vp-card__desc {
  color: var(--os-text-3, #9ca3af);
}

.vp-card__ops {
  display: flex;
  gap: 2px;
  flex: none;
  opacity: 0;
  transition: opacity 0.15s;
}

.vp-card__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
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

/* ---------- 空态 ---------- */
.vp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 64px 20px;
  text-align: center;
  border: 1px dashed var(--os-border, #e5e7eb);
  border-radius: 14px;
  background: var(--os-bg-subtle, #fafafa);
}

.vp-empty__art {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  margin-bottom: 2px;
  border-radius: 15px;
  background: #fff;
  border: 1px solid var(--os-border-light, #f1f3f5);
  color: var(--os-text-3, #9ca3af);
}

.vp-empty__title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.vp-empty__desc {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

.vp-empty__actions {
  margin-top: 6px;
}

.vp-btn {
  height: 32px;
  padding: 0 16px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 8px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;

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

@media (max-width: 720px) {
  .vp-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .vp-grid {
    grid-template-columns: 1fr;
  }
}
</style>
