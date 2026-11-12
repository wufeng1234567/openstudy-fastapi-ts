import { nextTick, ref } from 'vue'
import * as echarts from 'echarts'

/** myStats 的 ECharts 生命周期与配置，页面只负责传数据。 */
export function useStatsCharts() {
  const trendChartRef = ref<HTMLElement | null>(null)
  const subjectChartRef = ref<HTMLElement | null>(null)
  const difficultyChartRef = ref<HTMLElement | null>(null)

  let trendChart: echarts.ECharts | null = null
  let subjectChart: echarts.ECharts | null = null
  let difficultyChart: echarts.ECharts | null = null

  const difficultyMap: Record<number, string> = { 1: '简单', 2: '中等', 3: '困难' }
  const SUBJECT_PALETTE = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b8afb']
  const subjectLegend = ref<{ name: string; value: number; color: string }[]>([])

  function disposeCharts() {
    trendChart?.dispose(); trendChart = null
    subjectChart?.dispose(); subjectChart = null
    difficultyChart?.dispose(); difficultyChart = null
  }

  function hexToRgba(hex: string, alpha: number) {
    const h = hex.replace('#', '')
    const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
  }

  function initTrendChart(data: any[], onDayClick?: (date: string) => void) {
    if (!trendChartRef.value) return
    trendChart?.dispose()
    trendChart = echarts.init(trendChartRef.value)
    const line = (name: string, color: string, values: number[], withArea = false) => ({
      name,
      type: 'line' as const,
      smooth: true,
      symbolSize: 6,
      data: values,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
      areaStyle: withArea
        ? {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: hexToRgba(color, 0.22) },
              { offset: 1, color: hexToRgba(color, 0.02) }
            ])
          }
        : undefined
    })
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['练习总量', '答对次数', '答错次数', '斩题'], bottom: 0, itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12 } },
      grid: { left: 4, right: 12, bottom: 34, top: 12, containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.map((d) => (d.date || '').slice(5)),
        axisLine: { lineStyle: { color: '#e5e7eb' } },
        axisLabel: { color: '#9ca3af', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#f3f4f6' } },
        axisLabel: { color: '#9ca3af', fontSize: 11 }
      },
      series: [
        line('练习总量', '#409eff', data.map((d) => d.practiceCount), true),
        line('答对次数', '#67c23a', data.map((d) => d.correctCount)),
        line('答错次数', '#f56c6c', data.map((d) => d.errorCount)),
        line('斩题', '#e6a23c', data.map((d) => d.markedCount))
      ]
    })
    trendChart.on('click', (params: any) => {
      const index = Number(params?.dataIndex ?? -1)
      const day = data[index]
      if (day?.date) onDayClick?.(day.date)
    })
  }

  async function initSubjectChart(data: any[]) {
    const list = (data || []).filter((s) => (s.bankCount || 0) > 0)
    subjectLegend.value = list.map((s, i) => ({
      name: s.subject || '未分类',
      value: s.bankCount || 0,
      color: SUBJECT_PALETTE[i % SUBJECT_PALETTE.length]
    }))

    subjectChart?.dispose()
    subjectChart = null
    if (!list.length) return
    await nextTick()
    if (!subjectChartRef.value) return

    subjectChart = echarts.init(subjectChartRef.value)
    subjectChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} 个题库 ({d}%)' },
      legend: { show: false },
      color: SUBJECT_PALETTE,
      series: [{
        type: 'pie',
        radius: ['58%', '80%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 4, label: { show: false } },
        data: list.map((s) => ({ value: s.bankCount, name: s.subject || '未分类' }))
      }]
    })
  }

  function initDifficultyChart(data: any[]) {
    if (!difficultyChartRef.value) return
    difficultyChart?.dispose()
    difficultyChart = echarts.init(difficultyChartRef.value)

    const sorted = [...(data || [])].sort((a, b) => a.difficulty - b.difficulty)
    const categories = sorted.map((d) => difficultyMap[d.difficulty] || `难度${d.difficulty}`)
    const counts = sorted.map((d) => d.count)
    const colorMap: Record<number, string> = { 1: '#67c23a', 2: '#e6a23c', 3: '#f56c6c' }

    difficultyChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 4, right: 8, bottom: 4, top: 16, containLabel: true },
      xAxis: {
        type: 'category',
        data: categories.length ? categories : ['暂无数据'],
        axisLine: { lineStyle: { color: '#e5e7eb' } },
        axisTick: { show: false },
        axisLabel: { color: '#9ca3af', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#f3f4f6' } },
        axisLabel: { color: '#9ca3af', fontSize: 11 }
      },
      series: [{
        type: 'bar',
        barWidth: '42%',
        data: counts.length
          ? sorted.map((d) => ({ value: d.count, itemStyle: { color: colorMap[d.difficulty] || '#909399' } }))
          : [{ value: 0, itemStyle: { color: '#e5e7eb' } }],
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      }]
    })
  }

  function handleResize() {
    trendChart?.resize()
    subjectChart?.resize()
    difficultyChart?.resize()
  }

  return {
    trendChartRef,
    subjectChartRef,
    difficultyChartRef,
    subjectLegend,
    disposeCharts,
    initTrendChart,
    initSubjectChart,
    initDifficultyChart,
    handleResize
  }
}
