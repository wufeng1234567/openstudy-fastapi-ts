<template>
  <section v-if="hasChart" class="learning-chart">
    <header class="learning-chart__head">
      <div class="learning-chart__titles">
        <span class="learning-chart__title">{{ chart.title || '学习数据' }}</span>
        <span v-if="chart.subtitle" class="learning-chart__subtitle">{{ chart.subtitle }}</span>
      </div>
      <div class="learning-chart__types" role="group" aria-label="图表类型">
        <button
          type="button"
          class="learning-chart__type"
          :class="{ 'is-active': chartType === 'line' }"
          @click="setType('line')"
        >
          折线
        </button>
        <button
          type="button"
          class="learning-chart__type"
          :class="{ 'is-active': chartType === 'bar' }"
          @click="setType('bar')"
        >
          柱状
        </button>
      </div>
    </header>
    <div ref="chartRef" class="learning-chart__canvas" role="img" :aria-label="chart.title || '学习数据图表'"></div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  chart: Record<string, any> | null
}>()

const chartRef = ref<HTMLElement | null>(null)
const chartType = ref<'line' | 'bar'>(props.chart?.kind === 'bar' ? 'bar' : 'line')
let instance: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const series = computed<any[]>(() => (Array.isArray(props.chart?.series) ? props.chart!.series : []))
const hasChart = computed(() => Boolean(props.chart && series.value.length && Array.isArray(props.chart.xAxis)))

function setType(type: 'line' | 'bar') {
  chartType.value = type
  render()
}

function render() {
  if (!chartRef.value || !props.chart || !series.value.length) return
  if (!instance) instance = echarts.init(chartRef.value)
  const isBar = chartType.value === 'bar'
  const labels = Array.isArray(props.chart.xAxis) ? props.chart.xAxis : []
  const colors = series.value.map((item) => String(item.color || '#409eff'))
  instance.setOption(
    {
      animationDuration: 320,
      color: colors,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: isBar ? 'shadow' : 'line' }
      },
      legend: {
        top: 0,
        right: 8,
        type: 'scroll',
        itemWidth: 10,
        itemHeight: 8,
        textStyle: { color: '#606266', fontSize: 11 }
      },
      grid: { top: 36, left: 8, right: 18, bottom: 26, containLabel: true },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: isBar,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#dcdfe6' } },
        axisLabel: { color: '#909399', fontSize: 11, hideOverlap: true }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        name: props.chart.yAxisName || '',
        nameTextStyle: { color: '#909399', fontSize: 11, padding: [0, 0, 4, 0] },
        axisLabel: { color: '#909399', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0f2f5' } }
      },
      series: series.value.map((item) => ({
        name: String(item.name || ''),
        type: isBar ? 'bar' : 'line',
        data: Array.isArray(item.data) ? item.data : [],
        smooth: !isBar,
        symbol: 'circle',
        symbolSize: isBar ? 0 : 5,
        showSymbol: !isBar,
        barMaxWidth: 28,
        itemStyle: { color: item.color || '#409eff', borderRadius: isBar ? [3, 3, 0, 0] : 0 },
        lineStyle: { width: 2 }
      }))
    },
    true
  )
}

watch(
  () => props.chart,
  (value) => {
    if (value?.kind === 'bar') chartType.value = 'bar'
    else if (value?.kind === 'line') chartType.value = 'line'
    nextTick(render)
  },
  { deep: true }
)

onMounted(() => {
  nextTick(() => {
    render()
    if (typeof ResizeObserver !== 'undefined' && chartRef.value) {
      resizeObserver = new ResizeObserver(() => instance?.resize())
      resizeObserver.observe(chartRef.value)
    }
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  instance?.dispose()
  instance = null
})
</script>

<style scoped>
.learning-chart {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid var(--os-border-soft, #e4e7ed);
  border-radius: 10px;
  background: #fff;
}

.learning-chart__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px 0;
}

.learning-chart__titles {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.learning-chart__title {
  overflow: hidden;
  color: var(--os-text, #303133);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.learning-chart__subtitle {
  color: var(--os-text-4, #909399);
  font-size: 11px;
}

.learning-chart__types {
  display: inline-flex;
  flex: none;
  padding: 2px;
  border-radius: 6px;
  background: #f5f7fa;
}

.learning-chart__type {
  padding: 2px 9px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  font-size: 11px;
}

.learning-chart__type:hover {
  color: #409eff;
}

.learning-chart__type.is-active {
  background: #fff;
  color: #303133;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.learning-chart__canvas {
  width: 100%;
  height: 270px;
}
</style>
