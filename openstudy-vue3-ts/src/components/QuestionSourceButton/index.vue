<!--
  题目「原文依据」按钮
  ----------------------------------------------------------------------------
  错题溯源的最小闭环：这道题不是凭空出的，它来自资料里的哪一句。

  交互刻意做成「题目 → 原文」的连线卡片，而不是再弹一段纯文字：
    · 上方是当前题目；
    · 中间一条竖向锚点线，标出「来自」；
    · 下方是资料名 + 被引用的原文句子（黄色高亮）。

  没有 source anchor 的历史题/手工题不伪造，点击后明确告知「暂无原文依据」。
-->
<template>
  <span class="qsrc-entry">
    <button type="button" class="qsrc-trigger" :disabled="!questionId" :title="questionId ? '查看这道题的原文依据' : '暂无原文依据'" @click="open">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
        stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M10 13a5 5 0 0 0 7.07 0l1.42-1.42a5 5 0 0 0-7.07-7.07L10 5.93" />
        <path d="M14 11a5 5 0 0 0-7.07 0L5.5 12.42a5 5 0 0 0 7.07 7.07L14 18.07" />
      </svg>
      <span>{{ label }}</span>
    </button>

    <el-dialog v-model="visible" title="原文依据" width="720px" append-to-body class="qsrc-dialog">
      <div v-if="loading" v-loading="true" class="qsrc-loading"></div>
      <div v-else-if="source" class="qsrc">
        <div class="qsrc__question">
          <span class="qsrc__eyebrow">当前题目</span>
          <div class="qsrc__question-text">{{ questionText || '（题目正文）' }}</div>
        </div>

        <div class="qsrc__link">
          <span class="qsrc__line"></span>
          <span class="qsrc__badge">来自</span>
          <span class="qsrc__line"></span>
        </div>

        <div class="qsrc__doc">
          <div class="qsrc__doc-head">
            <span class="qsrc__doc-icon">▤</span>
            <span class="qsrc__doc-name">{{ source.docName }}</span>
            <span v-if="source.chunkId" class="qsrc__chunk">片段 #{{ source.chunkId }}</span>
          </div>
          <blockquote class="qsrc__quote">{{ source.quote || '原文片段已失效' }}</blockquote>
          <div class="qsrc__hint">
            这句话是从资料里逐字摘录的，不是模型改写。题目与原文的对应关系会随资料版本一起保留。
          </div>
        </div>
      </div>
    </el-dialog>
  </span>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getQuestionSource } from '@/api/questionMain/questionMain'

defineOptions({ name: 'QuestionSourceButton' })

const props = withDefaults(
  defineProps<{
    questionId?: number | string | null
    questionText?: string
    label?: string
  }>(),
  { label: '原文依据' }
)

const visible = ref(false)
const loading = ref(false)
const source = ref<any>(null)
let reqSeq = 0

watch(
  () => props.questionId,
  () => {
    visible.value = false
    source.value = null
  }
)

async function open() {
  if (!props.questionId) return
  const seq = ++reqSeq
  loading.value = true
  source.value = null
  try {
    const res: any = await getQuestionSource(props.questionId)
    if (seq !== reqSeq) return
    if (res.code !== 200) throw new Error(res.msg || '读取原文依据失败')
    if (!res.data?.hasSource) {
      ElMessage.info('这道题没有原文依据（手工录入或历史题）')
      return
    }
    source.value = res.data
    visible.value = true
  } catch (e: any) {
    if (seq === reqSeq) ElMessage.error(e?.message || String(e))
  } finally {
    if (seq === reqSeq) loading.value = false
  }
}
</script>

<style scoped>
.qsrc-entry {
  display: inline-flex;
  vertical-align: middle;
}

.qsrc-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border: 1px solid #dbeafe;
  border-radius: 5px;
  background: #f8fbff;
  color: #2563eb;
  font-size: 11px;
  cursor: pointer;
}

.qsrc-trigger:hover:not(:disabled) {
  border-color: #2563eb;
  background: #eff6ff;
}

.qsrc-trigger:disabled {
  color: #b6c2d2;
  background: #f8fafc;
  border-color: #e5e7eb;
  cursor: default;
}

.qsrc-loading {
  height: 180px;
}

.qsrc {
  padding: 2px 2px 4px;
}

.qsrc__eyebrow {
  display: block;
  margin-bottom: 5px;
  color: #9ca3af;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.qsrc__question {
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 9px;
  background: #fbfcff;
}

.qsrc__question-text {
  max-height: 150px;
  overflow: auto;
  color: #1f2937;
  font-size: 13px;
  line-height: 1.7;
}

.qsrc__link {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 34px;
}

.qsrc__line {
  width: 52px;
  height: 1px;
  background: linear-gradient(90deg, transparent, #93c5fd, transparent);
}

.qsrc__badge {
  padding: 1px 7px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 10.5px;
  font-weight: 600;
}

.qsrc__doc {
  padding: 12px 14px;
  border: 1px solid #fde68a;
  border-radius: 9px;
  background: #fffdf5;
}

.qsrc__doc-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
}

.qsrc__doc-icon {
  color: #b45309;
  font-size: 14px;
}

.qsrc__doc-name {
  overflow: hidden;
  color: #78350f;
  font-size: 12.5px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qsrc__chunk {
  flex: none;
  padding: 1px 6px;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
  font-size: 10px;
}

.qsrc__quote {
  margin: 0;
  padding: 9px 11px;
  border-left: 3px solid #f59e0b;
  border-radius: 0 6px 6px 0;
  background: #fff7e0;
  color: #4b3a1d;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.qsrc__hint {
  margin-top: 8px;
  color: #a8a29e;
  font-size: 10.5px;
  line-height: 1.6;
}
</style>
