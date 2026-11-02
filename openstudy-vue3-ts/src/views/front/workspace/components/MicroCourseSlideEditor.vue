<template>
  <el-drawer v-model="visible" title="编辑微课页面" size="980px" append-to-body :close-on-click-modal="false">
    <div v-if="!slides.length" class="slide-editor-empty">当前版本没有可编辑的页面</div>
    <div v-else class="slide-editor">
      <aside class="slide-editor__side">
        <div class="slide-editor__side-head">
          <span>页面</span>
          <el-button text size="small" @click="addSlide">+ 新增</el-button>
        </div>
        <div class="slide-editor__list">
          <div
            v-for="(slide, index) in slides"
            :key="index"
            class="slide-editor__item"
            :class="{ 'is-active': currentIndex === index }"
            draggable="true"
            @dragstart="onDragStart(index)"
            @dragover.prevent
            @drop="onDrop(index)"
            @click="selectSlide(index)"
          >
            <span class="slide-editor__handle">⋮⋮</span>
            <span class="slide-editor__index">{{ index + 1 }}</span>
            <span class="slide-editor__label">{{ slide.title || '未命名页面' }}</span>
          </div>
        </div>
      </aside>

      <main class="slide-editor__main">
        <div class="slide-editor__form-head">
          <div>
            <div class="slide-editor__eyebrow">正在编辑第 {{ currentIndex + 1 }} 页</div>
            <h3>{{ form.title || '未命名页面' }}</h3>
          </div>
          <span class="slide-editor__record">v{{ result?.version || '—' }}</span>
        </div>

        <el-form label-position="top" class="slide-editor__form">
          <div class="slide-editor__grid">
            <el-form-item label="页面类型">
              <el-select v-model="form.layout" style="width: 100%">
                <el-option label="内容" value="content" />
                <el-option label="图片" value="image" />
                <el-option label="图表" value="chart" />
                <el-option label="表格" value="table" />
                <el-option label="引用" value="quote" />
                <el-option label="封面" value="cover" />
                <el-option label="小结" value="summary" />
              </el-select>
            </el-form-item>
            <el-form-item label="环节标签">
              <el-input v-model="form.eyebrow" placeholder="例如：核心概念" />
            </el-form-item>
          </div>
          <el-form-item label="页面标题">
            <el-input v-model="form.title" maxlength="100" />
          </el-form-item>
          <el-form-item label="正文要点（每行一条）">
            <el-input v-model="form.bulletsText" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="课堂提示（可选）">
            <el-input v-model="form.note" type="textarea" :rows="2" />
          </el-form-item>

          <template v-if="form.layout === 'image'">
            <el-form-item label="图片">
              <MicroCourseImagePicker
                v-model="form.imageUrl"
                v-model:caption="form.imageCaption"
                :doc-id="result?.docId"
              />
            </el-form-item>
          </template>

          <template v-if="form.layout === 'chart'">
            <div class="slide-editor__grid">
              <el-form-item label="图表标题">
                <el-input v-model="form.chartTitle" />
              </el-form-item>
              <el-form-item label="单位">
                <el-input v-model="form.chartUnit" placeholder="例如：%" />
              </el-form-item>
            </div>
            <el-form-item label="标签（逗号分隔）">
              <el-input v-model="form.chartLabels" placeholder="感知, 规划, 行动" />
            </el-form-item>
            <el-form-item label="数值（逗号分隔）">
              <el-input v-model="form.chartValues" placeholder="80, 95, 90" />
            </el-form-item>
          </template>

          <template v-if="form.layout === 'table'">
            <el-form-item label="表头（逗号分隔）">
              <el-input v-model="form.tableHeaders" placeholder="维度, 普通程序, 智能体" />
            </el-form-item>
            <el-form-item label="表格行（每行一条，单元格用 | 分隔）">
              <el-input v-model="form.tableRows" type="textarea" :rows="4" placeholder="执行方式 | 固定规则 | 动态规划" />
            </el-form-item>
          </template>

          <el-form-item v-if="form.layout === 'quote'" label="引用内容">
            <el-input v-model="form.quote" type="textarea" :rows="3" />
          </el-form-item>

          <el-form-item label="本页重生成提示词（可选）">
            <el-input v-model="slidePrompt" placeholder="例如：减少文字，换成更具体的例子" />
          </el-form-item>
        </el-form>

        <div class="slide-editor__actions">
          <el-button @click="regenerate" :loading="regenerating">重新生成这一页</el-button>
          <el-button type="primary" @click="save" :loading="saving">保存本页</el-button>
        </div>
      </main>
    </div>

    <el-dialog v-model="compareVisible" title="修改前后对比" width="760px" append-to-body>
      <div class="slide-compare">
        <div class="slide-compare__col">
          <div class="slide-compare__label">修改前</div>
          <h4>{{ compareBefore?.title || '—' }}</h4>
          <ul>
            <li v-for="(b, i) in compareBefore?.bullets || []" :key="i">{{ b }}</li>
          </ul>
        </div>
        <div class="slide-compare__col is-after">
          <div class="slide-compare__label">修改后</div>
          <h4>{{ compareAfter?.title || '—' }}</h4>
          <ul>
            <li v-for="(b, i) in compareAfter?.bullets || []" :key="i">{{ b }}</li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import MicroCourseImagePicker from './MicroCourseImagePicker.vue'
import {
  editMicroCourseSlide,
  insertMicroCourseSlide,
  regenerateMicroCourseSlide,
  reorderMicroCourseSlides,
  type MicroCourseHtmlResult,
} from '@/api/ai/workspace'

const props = defineProps<{
  modelValue: boolean
  result: MicroCourseHtmlResult | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'updated', data: MicroCourseHtmlResult): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const slides = computed<any[]>(() => ((props.result?.deck as any)?.slides || []) as any[])
const currentIndex = ref(0)
const saving = ref(false)
const regenerating = ref(false)
const slidePrompt = ref('')
const compareVisible = ref(false)
const compareBefore = ref<any>(null)
const compareAfter = ref<any>(null)
let dragFrom = -1

const form = reactive({
  layout: 'content',
  eyebrow: '',
  title: '',
  bulletsText: '',
  note: '',
  imageUrl: '',
  imageCaption: '',
  chartTitle: '',
  chartLabels: '',
  chartValues: '',
  chartUnit: '',
  tableHeaders: '',
  tableRows: '',
  quote: '',
})

function syncForm() {
  const slide = slides.value[currentIndex.value] || {}
  form.layout = slide.layout || 'content'
  form.eyebrow = slide.eyebrow || ''
  form.title = slide.title || ''
  form.bulletsText = (slide.bullets || []).join('\n')
  form.note = slide.note || ''
  form.imageUrl = slide.image?.url || ''
  form.imageCaption = slide.image?.caption || ''
  form.chartTitle = slide.chart?.title || ''
  form.chartLabels = (slide.chart?.labels || []).join(', ')
  form.chartValues = (slide.chart?.values || []).join(', ')
  form.chartUnit = slide.chart?.unit || ''
  form.tableHeaders = (slide.table?.headers || []).join(', ')
  form.tableRows = (slide.table?.rows || []).map((r: any[]) => r.join(' | ')).join('\n')
  form.quote = typeof slide.quote === 'string' ? slide.quote : ''
}

function selectSlide(index: number) {
  currentIndex.value = Math.max(0, Math.min(index, slides.value.length - 1))
  syncForm()
}

watch(
  () => [props.modelValue, props.result?.recordId],
  () => {
    if (props.modelValue) {
      currentIndex.value = 0
      syncForm()
    }
  }
)

function parseList(text: string) {
  return text.split(/[,，]/).map((x) => x.trim()).filter(Boolean)
}

function buildPatch() {
  const patch: any = {
    layout: form.layout,
    eyebrow: form.eyebrow,
    title: form.title,
    bullets: form.bulletsText.split('\n').map((x) => x.trim()).filter(Boolean),
    note: form.note,
  }
  if (form.layout === 'image') {
    patch.image = { url: form.imageUrl.trim(), caption: form.imageCaption.trim() }
  }
  if (form.layout === 'chart') {
    patch.chart = {
      type: 'bar',
      title: form.chartTitle,
      labels: parseList(form.chartLabels),
      values: parseList(form.chartValues).map((x) => Number(x) || 0),
      unit: form.chartUnit,
    }
  }
  if (form.layout === 'table') {
    patch.table = {
      headers: parseList(form.tableHeaders),
      rows: form.tableRows.split('\n').map((line) => line.split('|').map((x) => x.trim())).filter((r) => r.some(Boolean)),
    }
  }
  if (form.layout === 'quote') patch.quote = form.quote
  return patch
}

async function save() {
  if (!props.result?.recordId) return
  if (!form.title.trim()) {
    ElMessage.warning('页面标题不能为空')
    return
  }
  saving.value = true
  try {
    const res: any = await editMicroCourseSlide(props.result.recordId, currentIndex.value, buildPatch())
    if (res.code === 200 && res.data) {
      compareBefore.value = res.data.before || null
      compareAfter.value = res.data.after || null
      compareVisible.value = true
      emit('updated', res.data)
      ElMessage.success('已保存为新版本')
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function regenerate() {
  if (!props.result?.recordId) return
  regenerating.value = true
  try {
    const res: any = await regenerateMicroCourseSlide(
      props.result.recordId,
      currentIndex.value,
      slidePrompt.value.trim()
    )
    if (res.code === 200 && res.data) {
      compareBefore.value = res.data.before || null
      compareAfter.value = res.data.after || null
      compareVisible.value = true
      emit('updated', res.data)
      ElMessage.success('本页已重新生成')
    } else {
      ElMessage.error(res.msg || '生成失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    regenerating.value = false
  }
}

async function addSlide() {
  if (!props.result?.recordId) return
  try {
    const res: any = await insertMicroCourseSlide(props.result.recordId, currentIndex.value + 1, {
      layout: 'content',
      eyebrow: '补充',
      title: '新页面',
      bullets: ['在这里补充内容'],
    })
    if (res.code === 200 && res.data) {
      emit('updated', res.data)
      ElMessage.success('已新增页面')
      currentIndex.value = Math.min(currentIndex.value + 1, slides.value.length - 1)
      syncForm()
    } else {
      ElMessage.error(res.msg || '新增失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '新增失败')
  }
}

function onDragStart(index: number) {
  dragFrom = index
}

async function onDrop(index: number) {
  if (dragFrom < 0 || dragFrom === index || !props.result?.recordId) return
  const from = dragFrom
  dragFrom = -1
  try {
    const res: any = await reorderMicroCourseSlides(props.result.recordId, from, index)
    if (res.code === 200 && res.data) {
      emit('updated', res.data)
      currentIndex.value = index
      syncForm()
      ElMessage.success('页面顺序已更新')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '调整顺序失败')
  }
}
</script>

<style scoped>
.slide-editor-empty {
  padding: 40px;
  color: var(--os-text-3, #81858c);
  text-align: center;
}

.slide-editor {
  display: flex;
  gap: 20px;
  min-height: 540px;
}

.slide-editor__side {
  width: 250px;
  flex: none;
  padding-right: 16px;
  border-right: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.slide-editor__side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
  font-weight: 600;
}

.slide-editor__list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.slide-editor__item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
}

.slide-editor__item:hover,
.slide-editor__item.is-active {
  border-color: var(--os-accent-soft, #dbe7ff);
  background: var(--os-accent-soft, #edf3fe);
  color: var(--os-text, #0f1115);
}

.slide-editor__handle {
  color: var(--os-text-4, #adb2b8);
  cursor: grab;
}

.slide-editor__index {
  flex: none;
  width: 18px;
  color: var(--os-text-4, #adb2b8);
  font-size: 10px;
}

.slide-editor__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slide-editor__main {
  flex: 1;
  min-width: 0;
}

.slide-editor__form-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.slide-editor__eyebrow {
  color: var(--os-accent, #4176e6);
  font-size: 11px;
  font-weight: 600;
}

.slide-editor__form-head h3 {
  margin: 5px 0 0;
  color: var(--os-text, #0f1115);
  font-size: 20px;
}

.slide-editor__record {
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.slide-editor__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.slide-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.slide-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.slide-compare__col {
  min-height: 160px;
  padding: 16px;
  border-radius: 10px;
  background: #f8fafc;
}

.slide-compare__col.is-after {
  background: #edf3fe;
}

.slide-compare__label {
  margin-bottom: 8px;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.slide-compare__col h4 {
  margin: 0 0 10px;
  color: var(--os-text, #0f1115);
  font-size: 16px;
}

.slide-compare__col ul {
  margin: 0;
  padding-left: 18px;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
  line-height: 1.7;
}
</style>
