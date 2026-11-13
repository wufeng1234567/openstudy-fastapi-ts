import { ref, markRaw } from 'vue'
import { CircleCheck, Check, QuestionFilled, EditPen, ChatDotRound, FolderOpened } from '@element-plus/icons-vue'

/**
 * 题型定义、题型名称与题型筛选状态。
 *
 * 从 QuestionBuilder.vue 抽出的内聚逻辑：题型库数据（含 markRaw 图标）、
 * 题型显示名映射、多选筛选状态与增删。仅依赖传入的 currentPage（切筛选时回到第 1 页）。
 */
export function useQuestionBuilderTypes(currentPage: { value: number }) {
  // 题型定义
  // 题型库数据：图标为 Vue 组件，必须用 markRaw 避免被响应式 Proxy 包装导致渲染失败
  const questionTypes = ref([
    { type: 'single', name: '单选题', icon: markRaw(CircleCheck) },
    { type: 'multiple', name: '多选题', icon: markRaw(Check) },
    { type: 'judge', name: '判断题', icon: markRaw(QuestionFilled) },
    { type: 'fill', name: '填空题', icon: markRaw(EditPen) },
    { type: 'essay', name: '简答题', icon: markRaw(ChatDotRound) },
    { type: 'composite', name: '组合题（含子题）', icon: markRaw(FolderOpened) }
  ])

  const getTypeName = (type: any) => {
    if (typeof type === 'number') {
      const map: Record<number, string> = { 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题', 6: '组合题' }
      return map[type] || '未知'
    }
    const found = questionTypes.value.find(t => t.type === type)
    return found?.name || type
  }

  // 题型筛选（支持多选）
  const activeTypeFilters = ref(new Set(['all']))

  // 设置题型筛选（多选模式）
  const setTypeFilter = (type: any) => {
    if (type === 'all') {
      // 点击"全部" = 清除所有筛选
      activeTypeFilters.value = new Set(['all'])
    } else {
      // 移除"全部"
      activeTypeFilters.value.delete('all')
      // 切换选中状态
      if (activeTypeFilters.value.has(type)) {
        activeTypeFilters.value.delete(type)
        // 如果没有选中任何类型，自动选中"全部"
        if (activeTypeFilters.value.size === 0) {
          activeTypeFilters.value.add('all')
        }
      } else {
        activeTypeFilters.value.add(type)
      }
      // 触发响应式更新
      activeTypeFilters.value = new Set(activeTypeFilters.value)
    }
    currentPage.value = 1
  }

  // 判断是否选中
  const isTypeSelected = (type: any) => {
    return activeTypeFilters.value.has(type)
  }

  return { questionTypes, getTypeName, activeTypeFilters, setTypeFilter, isTypeSelected }
}
