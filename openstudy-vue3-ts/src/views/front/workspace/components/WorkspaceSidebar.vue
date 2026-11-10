<template>
  <aside class="kbp-side">
    <div class="kbp-side__head">
      <span class="kbp-side__title">全部资料</span>
      <el-button size="small" :icon="Plus" :disabled="creating" @click="emit('create')">新建</el-button>
    </div>

    <div class="kbp-side__search">
      <el-input
        :model-value="folderKeyword"
        size="small"
        clearable
        placeholder="搜索资料夹"
        :prefix-icon="Search"
        @update:model-value="emit('update:folderKeyword', $event)"
      />
    </div>

    <div class="kbp-side__list" v-loading="loading">
      <button
        v-for="kb in filteredKbs"
        :key="kb.kbId"
        type="button"
        class="kbp-kb"
        :class="{ 'is-active': kb.kbId === activeKbId, 'is-blocked': kb.disabled === 1 }"
        @click="emit('select', kb.kbId)"
        @contextmenu.prevent.stop="emit('open-menu', $event, kb)"
      >
        <span class="kbp-kb__icon">
          <OsIcon :name="kb.isDefault ? 'folder' : 'database'" :size="16" />
        </span>
        <span class="kbp-kb__main">
          <span class="kbp-kb__name-row">
            <span class="kbp-kb__name">{{ kb.name }}</span>
            <span v-if="kb.isDefault" class="kbp-kb__tag">默认</span>
            <span v-if="kb.disabled === 1" class="kbp-kb__tag is-blocked">已屏蔽</span>
            <span v-if="kb.sourceType === 'share'" class="kbp-kb__tag is-share">来自分享</span>
          </span>
          <span class="kbp-kb__meta">
            {{ kb.docCount }} 份资料<template v-if="kb.disabled !== 1"> · 可检索</template>
          </span>
        </span>
        <span class="kbp-kb__ops">
          <span class="kbp-kb__op" title="更多操作" @click.stop="emit('open-menu', $event, kb)">
            <OsIcon name="more" :size="14" />
          </span>
        </span>
      </button>

      <div v-if="!loading && !filteredKbs.length" class="kbp-side__empty">
        <p>{{ folderKeyword ? '没有匹配的资料夹' : '还没有资料' }}</p>
        <span>{{ folderKeyword ? '换个关键词试试' : '建一个资料夹来放课件和真题' }}</span>
        <el-button v-if="!folderKeyword" size="small" type="primary" :icon="Plus" @click="emit('create')">
          新建资料夹
        </el-button>
      </div>
    </div>

    <div
      v-if="kbMenu.visible"
      class="kbp-context-menu"
      :style="{ left: `${kbMenu.x}px`, top: `${kbMenu.y}px` }"
      @click.stop
    >
      <button type="button" class="kbp-context-item" @click="emit('command', 'rename', kbMenu.kb)">
        <OsIcon name="pen-line" :size="14" />
        重命名
      </button>
      <button type="button" class="kbp-context-item" @click="emit('command', 'share', kbMenu.kb)">
        <el-icon><Share /></el-icon>
        分享资料夹
      </button>
      <button type="button" class="kbp-context-item" @click="emit('command', 'toggle-disabled', kbMenu.kb)">
        <OsIcon :name="kbMenu.kb?.disabled === 1 ? 'eye' : 'eye-off'" :size="14" />
        {{ kbMenu.kb?.disabled === 1 ? '恢复检索' : '屏蔽检索' }}
      </button>
      <button
        v-if="Number(kbMenu.kb?.isDefault || 0) !== 1"
        type="button"
        class="kbp-context-item is-danger"
        @click="emit('command', 'delete', kbMenu.kb)"
      >
        <OsIcon name="trash" :size="14" />
        删除资料夹
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Plus, Search, Share } from '@element-plus/icons-vue'
import OsIcon from '@/components/OsIcon/index.vue'

defineProps<{
  loading: boolean
  creating: boolean
  filteredKbs: any[]
  activeKbId: number | null
  folderKeyword: string
  kbMenu: { visible: boolean; x: number; y: number; kb: any }
}>()

const emit = defineEmits<{
  (e: 'create'): void
  (e: 'select', kbId: number): void
  (e: 'open-menu', event: MouseEvent, kb: any): void
  (e: 'command', command: string, kb: any): void
  (e: 'update:folderKeyword', value: string): void
}>()
</script>
