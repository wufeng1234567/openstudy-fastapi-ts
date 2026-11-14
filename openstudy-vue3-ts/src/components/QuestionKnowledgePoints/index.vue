<template>
  <div v-if="!examMode && points.length" class="qkp" :class="{ 'is-compact': compact }">
    <div class="qkp__head">
      <span class="qkp__label">知识点</span>
      <span class="qkp__count">{{ points.length }}</span>
      <button type="button" class="qkp__toggle" @click="expanded = !expanded">
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>
    <div class="qkp__list" :class="{ 'is-expanded': expanded }">
      <span v-for="point in visiblePoints" :key="point.pageId" class="qkp__chip" :title="point.title">
        {{ point.title }}
      </span>
      <span v-if="!expanded && hiddenCount" class="qkp__more">+{{ hiddenCount }}</span>
    </div>
    <div v-if="source?.quote" class="qkp__source" :title="source.quote">
      来源：资料 #{{ source.docId }}<template v-if="source.chunkId"> · 第 {{ source.chunkId }} 段</template>
      · {{ source.quote }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getQuestionKnowledgePoints } from '@/api/questionMain/questionMain'

const props = withDefaults(defineProps<{
  questionId?: number | string | null
  examMode?: boolean
  compact?: boolean
}>(), {
  questionId: null,
  examMode: false,
  compact: false
})

const points = ref<any[]>([])
const source = ref<any>(null)
const expanded = ref(false)
let reqSeq = 0

const visiblePoints = computed(() => expanded.value ? points.value : points.value.slice(0, 2))
const hiddenCount = computed(() => Math.max(0, points.value.length - 2))

async function load() {
  const id = Number(props.questionId || 0)
  if (!id) {
    points.value = []
    return
  }
  const seq = ++reqSeq
  try {
    const res: any = await getQuestionKnowledgePoints([id])
    if (seq !== reqSeq) return
    const item = Array.isArray(res.data) ? res.data.find((entry: any) => Number(entry.questionId) === id) : null
    points.value = item?.points || []
    source.value = item?.source || null
  } catch {
    if (seq === reqSeq) {
      points.value = []
      source.value = null
    }
  }
}

watch(
  () => props.questionId,
  () => {
    expanded.value = false
    void load()
  },
  { immediate: true }
)
</script>

<style scoped>
.qkp { display: flex; min-width: 0; flex-direction: column; gap: 5px; margin-bottom: 10px; }
.qkp__head { display: flex; align-items: center; gap: 6px; color: #6b7280; font-size: 11px; }
.qkp__label { font-weight: 600; color: #4b5563; }
.qkp__count { padding: 0 5px; border-radius: 99px; background: #eef4ff; color: #2f5fce; font-size: 9.5px; }
.qkp__toggle { margin-left: auto; padding: 0; border: 0; color: #2f5fce; background: transparent; cursor: pointer; font: inherit; font-size: 10px; }
.qkp__list { display: flex; flex-wrap: wrap; gap: 5px; max-height: 44px; overflow: hidden; }
.qkp__list.is-expanded { max-height: 58px; overflow-y: auto; }
.qkp__chip { max-width: 210px; overflow: hidden; padding: 3px 7px; border: 1px solid #e3eaf5; border-radius: 5px; color: #5f6b7d; background: #f8faff; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.qkp__more { padding: 3px 5px; color: #9aa1af; font-size: 10px; }
.qkp__source { overflow: hidden; max-width: 100%; padding-top: 4px; border-top: 1px dashed #edf1f7; color: #9aa1af; font-size: 9.5px; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.qkp.is-compact .qkp__list { max-height: 25px; }
</style>
