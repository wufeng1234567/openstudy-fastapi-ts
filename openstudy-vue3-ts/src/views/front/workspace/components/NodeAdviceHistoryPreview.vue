<template>
  <aside class="nah">
    <header class="nah__head">
      <span class="nah__eyebrow">历史规划建议</span>
      <h3>{{ nodeTitle || '当前节点' }}</h3>
      <p>这里只展示以当前节点为起点的历史规划，可查看、重命名、置顶或删除。</p>
    </header>

    <div class="nah__bar">
      <el-input v-model="keyword" size="small" clearable placeholder="搜索当前节点的规划标题" @keyup.enter="loadHistory" />
      <el-button size="small" plain :loading="loading" @click="loadHistory">刷新</el-button>
    </div>

    <div v-loading="loading" class="nah__scroll">
      <div v-if="!items.length && !loading" class="nah__empty">
        当前节点还没有历史规划建议。点击下方按钮生成第一条。
      </div>
      <article v-for="item in items" :key="item.id" class="nah__item" :class="{ 'is-pinned': item.pinned }">
        <div class="nah__item-head">
          <button type="button" class="nah__title" @click="emit('load', item)">{{ item.title || '未命名规划' }}</button>
          <button type="button" class="nah__pin" :class="{ 'is-on': item.pinned }" :title="item.pinned ? '取消置顶' : '置顶'" @click="pinItem(item)">●</button>
        </div>
        <p class="nah__summary">{{ item.summary || '规划建议快照' }}</p>
        <div class="nah__meta">
          <span>{{ item.createTime || '' }}</span>
          <span v-if="item.phaseCount">{{ item.phaseCount }} 个阶段</span>
        </div>
        <div class="nah__ops">
          <button type="button" @click="emit('load', item)">查看 / 继续</button>
          <button type="button" @click="renameItem(item)">重命名</button>
          <button type="button" class="is-danger" @click="deleteItem(item)">删除</button>
        </div>
      </article>
    </div>

    <footer class="nah__foot">
      <el-button type="primary" @click="emit('generate')">以此生成建议</el-button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteStudyPlanHistory, listStudyPlanHistory, updateStudyPlanHistory } from '@/api/ai/studyPlan'

const props = defineProps<{
  seedNodeId?: string
  nodeTitle?: string
}>()

const emit = defineEmits<{
  (e: 'load', item: any): void
  (e: 'generate'): void
}>()

const items = ref<any[]>([])
const loading = ref(false)
const keyword = ref('')

async function loadHistory() {
  if (!props.seedNodeId) return
  loading.value = true
  try {
    const res: any = await listStudyPlanHistory(50, keyword.value.trim(), props.seedNodeId)
    items.value = res.code === 200 ? res.data?.items || [] : []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function renameItem(item: any) {
  try {
    const result = await ElMessageBox.prompt('修改规划标题', '重命名规划', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: item.title || '',
      inputValidator: (value: string) => (value?.trim() ? true : '标题不能为空')
    })
    await updateStudyPlanHistory(Number(item.id), { title: result.value.trim() })
    ElMessage.success('已重命名')
    await loadHistory()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('重命名失败')
  }
}

async function pinItem(item: any) {
  await updateStudyPlanHistory(Number(item.id), { pinned: !item.pinned })
  await loadHistory()
}

async function deleteItem(item: any) {
  try {
    await ElMessageBox.confirm('删除后无法恢复，确定删除这条规划建议吗？', '删除规划', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteStudyPlanHistory(Number(item.id))
    ElMessage.success('已删除')
    await loadHistory()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}

watch(() => props.seedNodeId, () => {
  keyword.value = ''
  void loadHistory()
})
onMounted(loadHistory)
</script>

<style scoped>
.nah { display: flex; height: calc(100vh - 110px); min-height: 420px; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid #e8edf5; border-radius: 12px; background: #fff; }
.nah__head { flex: none; }
.nah__eyebrow { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.nah__head h3 { margin: 5px 0 0; color: #253247; font-size: 16px; line-height: 1.35; }
.nah__head p { margin: 5px 0 0; color: #7d8596; font-size: 11px; line-height: 1.55; }
.nah__bar { display: flex; flex: none; gap: 6px; }
.nah__bar .el-input { flex: 1; }
.nah__scroll { min-height: 0; flex: 1; overflow-y: auto; padding-right: 3px; scrollbar-width: thin; scrollbar-color: #cfd8e6 transparent; }
.nah__scroll::-webkit-scrollbar { width: 6px; }
.nah__scroll::-webkit-scrollbar-thumb { border-radius: 99px; background: #cfd8e6; }
.nah__item { padding: 10px; border: 1px solid #e8edf5; border-radius: 8px; background: #fbfcff; }
.nah__item + .nah__item { margin-top: 8px; }
.nah__item.is-pinned { border-color: #c9d9f8; background: #f8faff; }
.nah__item-head { display: flex; align-items: center; gap: 7px; }
.nah__title { min-width: 0; flex: 1; overflow: hidden; border: 0; background: transparent; color: #253247; cursor: pointer; font-size: 12.5px; font-weight: 600; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.nah__title:hover { color: #2f5fce; }
.nah__pin { flex: none; border: 0; background: transparent; color: #d3dae6; cursor: pointer; font-size: 10px; }
.nah__pin.is-on { color: #2f5fce; }
.nah__summary { display: -webkit-box; overflow: hidden; margin: 5px 0 0; color: #5f6b7d; font-size: 11px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.nah__meta { display: flex; gap: 10px; margin-top: 6px; color: #9aa3b2; font-size: 10px; }
.nah__ops { display: flex; gap: 12px; margin-top: 7px; padding-top: 7px; border-top: 1px solid #edf0f5; }
.nah__ops button { border: 0; background: transparent; color: #5f6b7d; cursor: pointer; font-size: 10.5px; padding: 0; }
.nah__ops button:hover { color: #2f5fce; }
.nah__ops button.is-danger { color: #c45b5b; }
.nah__empty { padding: 30px 10px; color: #9aa3b2; font-size: 11.5px; line-height: 1.6; text-align: center; }
.nah__foot { flex: none; padding-top: 7px; border-top: 1px solid #eef1f6; }
.nah__foot .el-button { width: 100%; }
</style>
