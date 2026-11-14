<template>
  <aside v-if="!collapsed" class="kg-panel" @pointerdown.stop>
    <header class="kg-panel__head">
      <span>图谱工具</span>
      <button type="button" class="kg-panel__close" title="收起操作面板" @click="emit('update:collapsed', true)">×</button>
    </header>
    <div class="kg-panel__actions">
      <button type="button" class="kg-panel__action" :class="{ 'is-active': !showArrows }" @click="emit('toggle-arrows')">
        <OsIcon name="check" :size="14" />
        <span>{{ showArrows ? '隐藏箭头' : '显示箭头' }}</span>
      </button>
      <button type="button" class="kg-panel__action" @click="emit('reset-view')">
        <OsIcon name="refresh" :size="14" />
        <span>适配视图</span>
      </button>
      <button type="button" class="kg-panel__action" @click="emit('show-guide')">
        <OsIcon name="circle-help" :size="14" />
        <span>使用说明</span>
      </button>
      <div class="kg-panel__toggle-row">
        <span>FPS 监控</span>
        <button
          type="button"
          class="kg-panel__switch"
          :class="{ 'is-on': performanceVisible }"
          :aria-pressed="performanceVisible"
          title="显示/隐藏 FPS 监控"
          @click="emit('toggle-performance')"
        >
          <i></i>
        </button>
      </div>
    </div>
  </aside>
  <button v-else type="button" class="kg-panel-open" title="打开图谱操作面板" @click="emit('update:collapsed', false)">
    ☰
  </button>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'

withDefaults(
  defineProps<{
    collapsed?: boolean
    showArrows?: boolean
    performanceVisible?: boolean
  }>(),
  { collapsed: false, showArrows: true, performanceVisible: true }
)

const emit = defineEmits<{
  (e: 'update:collapsed', value: boolean): void
  (e: 'toggle-arrows'): void
  (e: 'reset-view'): void
  (e: 'show-guide'): void
  (e: 'toggle-performance'): void
}>()
</script>

<style scoped>
.kg-panel {
  position: absolute;
  z-index: 8;
  top: 12px;
  right: 12px;
  display: flex;
  width: 172px;
  flex-direction: column;
  padding: 8px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 22px rgba(29, 43, 70, 0.1);
  backdrop-filter: blur(10px);
}
.kg-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 1px 6px;
  border-bottom: 1px solid #edf0f5;
  color: #66758b;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
}
.kg-panel__close {
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  color: #8a94a6;
  background: transparent;
  cursor: pointer;
  font-size: 16px;
  line-height: 16px;
}
.kg-panel__close:hover {
  color: #253247;
  background: #f1f4fa;
}
.kg-panel__actions {
  display: flex;
  flex-direction: column;
  padding-top: 5px;
}
.kg-panel__action {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 1px;
  border: 0;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 10px;
  line-height: 1.35;
  text-align: left;
  transition: color 0.15s ease;
}
.kg-panel__action:hover,
.kg-panel__action.is-active {
  color: #2f5fce;
}
.kg-panel__toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 3px;
  padding: 5px 1px 2px;
  border-top: 1px solid #edf0f5;
  color: #6b7280;
  font-size: 10px;
}
.kg-panel__switch {
  position: relative;
  width: 28px;
  height: 16px;
  flex: none;
  padding: 0;
  border: 0;
  border-radius: 99px;
  background: #dfe5ee;
  cursor: pointer;
  transition: background 0.15s ease;
}
.kg-panel__switch i {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(20, 34, 60, 0.18);
  transition: left 0.15s ease;
}
.kg-panel__switch.is-on { background: #2f5fce; }
.kg-panel__switch.is-on i { left: 14px; }
.kg-panel-open {
  position: absolute;
  z-index: 9;
  top: 12px;
  right: 12px;
  display: grid;
  width: 32px;
  height: 30px;
  place-items: center;
  padding: 0;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  color: #5f6b7d;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 5px 16px rgba(29, 43, 70, 0.1);
  cursor: pointer;
  font-size: 16px;
}
.kg-panel-open:hover {
  color: #2f5fce;
  background: #f8faff;
}
</style>
