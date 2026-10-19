<!--
  分组切换（下划线式分段控件）
  ============================================================================
  用户 2026-10-18 起，「题库管理 / 题目管理 / 笔记管理」三个页面都是
  「一个页面 + 顶部分组切换」的形态，而这三处的切换条原本是各自复制的一份 CSS
  （`.tab-switch` + `.tab-btn` + `.tab-count`，约 40 行），改一处要改三处。

  抽成组件后：
    · 视觉只有一份定义，三个页面天然一致；
    · 计数（`我的题库 26`）作为可选 `count` 字段，没有就不渲染；
    · 样式变量全部走 `--os-*` 令牌，跟着主题走。

  ⚠️ 不用 `el-tabs`：这里的分组是「同一份数据的两个视图」，下划线式更轻，
     也不会在外壳里再套一层描边。
-->
<template>
  <div class="seg-tabs" role="tablist">
    <button v-for="t in tabs" :key="t.key" type="button" role="tab" :aria-selected="modelValue === t.key"
      :class="['seg-tab', { 'is-active': modelValue === t.key }]" @click="select(t.key)">
      <span class="seg-tab__label">{{ t.label }}</span>
      <span v-if="t.count !== undefined && t.count !== null" class="seg-tab__count">{{ t.count }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'SegmentedTabs' })

export interface SegmentedTab {
  key: string
  label: string
  /** 可选的角标计数（如「我的题库 26」）；不传则不渲染 */
  count?: number | string
}

defineProps<{
  tabs: SegmentedTab[]
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', key: string): void
  (e: 'change', key: string): void
}>()

function select(key: string) {
  emit('update:modelValue', key)
  emit('change', key)
}
</script>

<style scoped lang="scss">
.seg-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.seg-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px 10px;
  border: 0;
  background: transparent;
  font-family: inherit;
  font-size: 13.5px;
  line-height: 1;
  color: var(--os-text-3, #6b7280);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s ease, border-color 0.15s ease;

  &:hover {
    color: var(--os-text, #1f2937);
  }

  &:focus-visible {
    outline: 2px solid var(--os-primary, #4f6ef7);
    outline-offset: -2px;
    border-radius: 4px;
  }

  &.is-active {
    color: var(--os-text, #1f2937);
    font-weight: 600;
    border-bottom-color: var(--os-primary, #4f6ef7);
  }
}

/*
 * 计数角标：小一号、次级色。
 * 选中态稍深一点，但不要变成"第二个标题"，保证 tab 名仍是视觉重心。
 */
.seg-tab__count {
  font-size: 12px;
  font-weight: 500;
  color: var(--os-text-4, #9ca3af);
  font-variant-numeric: tabular-nums;
}

.seg-tab.is-active .seg-tab__count {
  color: var(--os-text-3, #6b7280);
}
</style>
