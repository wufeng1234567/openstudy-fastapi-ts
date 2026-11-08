<template>
  <el-drawer :model-value="modelValue" title="我的规划" size="420px" append-to-body @update:model-value="emit('update:modelValue', $event)">
    <div class="sph">
      <div class="sph__bar">
        <el-input v-model="keyword" size="small" clearable placeholder="搜索规划标题" @keyup.enter="refresh" />
        <el-button size="small" plain @click="refresh">刷新</el-button>
      </div>

      <div v-if="!filtered.length" class="sph__empty">
        <b>还没有保存的规划</b>
        <span>生成建议后会自动留一份快照；也可以在工作台点「保存」。</span>
      </div>

      <div v-else class="sph__list">
        <article v-for="item in filtered" :key="item.id" class="sph__item" :class="{ 'is-pinned': item.pinned }">
          <div class="sph__item-head">
            <button type="button" class="sph__title" @click="emit('load', item)">{{ item.title || '未命名规划' }}</button>
            <button type="button" class="sph__pin" :class="{ 'is-on': item.pinned }" :title="item.pinned ? '取消置顶' : '置顶'" @click="emit('pin', item)">
              ●
            </button>
          </div>
          <p class="sph__summary">{{ item.summary || '建议快照' }}</p>
          <div class="sph__meta">
            <span>{{ item.createTime || '' }}</span>
            <span v-if="item.phaseCount">{{ item.phaseCount }} 个阶段</span>
          </div>
          <div class="sph__ops">
            <button type="button" @click="emit('load', item)">查看 / 继续</button>
            <button type="button" @click="rename(item)">重命名</button>
            <button type="button" class="is-danger" @click="remove(item)">删除</button>
          </div>
        </article>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{
  modelValue: boolean
  items?: any[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'load', item: any): void
  (e: 'refresh'): void
  (e: 'rename', item: any, title: string): void
  (e: 'pin', item: any): void
  (e: 'delete', item: any): void
}>()

const keyword = ref('')

const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  const list = props.items || []
  if (!q) return list
  return list.filter((item: any) => String(item.title || '').toLowerCase().includes(q))
})

function refresh() {
  emit('refresh')
}

async function rename(item: any) {
  try {
    const result = await ElMessageBox.prompt('给这条规划起一个容易找到的名字', '重命名规划', {
      inputValue: String(item.title || ''),
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (value: string) => (String(value || '').trim() ? true : '名字不能为空')
    })
    const title = String((result as any).value || '').trim()
    if (title) emit('rename', item, title)
  } catch {
    // 用户取消
  }
}

async function remove(item: any) {
  try {
    await ElMessageBox.confirm(`删除「${item.title || '未命名规划'}」？删除后不会影响当前建议。`, '删除规划', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    emit('delete', item)
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
.sph { display: flex; flex-direction: column; gap: 10px; }
.sph__bar { display: flex; gap: 6px; }
.sph__bar :deep(.el-input) { flex: 1; }
.sph__list { display: flex; flex-direction: column; gap: 8px; }
.sph__item {
  padding: 10px;
  border: 1px solid #e8edf5;
  border-radius: 9px;
  background: #fff;
}
.sph__item.is-pinned { border-color: #cfdcf5; background: #fbfcff; }
.sph__item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.sph__title {
  min-width: 0;
  padding: 0;
  border: 0;
  color: #253247;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  text-align: left;
}
.sph__title:hover { color: #2f5fce; }
.sph__pin { border: 0; color: #c4ccd8; background: transparent; cursor: pointer; font-size: 12px; }
.sph__pin.is-on { color: #2f5fce; }
.sph__summary { margin: 5px 0; color: #7d8596; font-size: 11px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sph__meta { display: flex; flex-wrap: wrap; gap: 8px; color: #a0a8b6; font-size: 10px; }
.sph__ops { display: flex; gap: 8px; margin-top: 7px; padding-top: 6px; border-top: 1px solid #f0f3f8; }
.sph__ops button { padding: 0; border: 0; color: #5d6b82; background: transparent; cursor: pointer; font: inherit; font-size: 10px; }
.sph__ops button:hover { color: #2f5fce; }
.sph__ops button.is-danger:hover { color: #d9534f; }
.sph__empty { display: flex; min-height: 220px; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: #9aa3b2; text-align: center; }
.sph__empty b { color: #5f6b7d; font-size: 13px; }
.sph__empty span { max-width: 260px; font-size: 11px; line-height: 1.55; }
</style>
