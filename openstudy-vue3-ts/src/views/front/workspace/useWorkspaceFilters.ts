import { computed } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { documentStatusKey, documentTypeKey } from './helpers'

export type WorkspaceViewMode = 'list' | 'shelf' | 'gallery' | 'wiki'

interface WorkspaceFilterOptions {
  viewMode: Ref<WorkspaceViewMode>
  activeKb: ComputedRef<any>
  workspaceSearch: Ref<string>
  workspaceFilters: Record<string, any>
  stats: Record<string, any>
  galleryStats: { total: number }
  mapStats: { total: number }
}

/**
 * 资料空间顶部的搜索提示、计数和筛选条件。
 *
 * 之前这些都堆在 `index.vue` 的 script 里；抽出来后页面只负责绑定视图和动作。
 */
export function useWorkspaceFilters(options: WorkspaceFilterOptions) {
  const workspaceSearchPlaceholder = computed(() => {
    if (options.viewMode.value === 'gallery') return '搜索图片描述或文字…'
    if (options.viewMode.value === 'wiki') return '搜索主题、资料、题库或笔记…'
    if (options.viewMode.value === 'shelf') return '搜索资料…'
    return '搜索资料夹或资料…'
  })

  const workspaceCountLabel = computed(() => {
    if (options.viewMode.value === 'list') return `全部资料夹：共 ${options.stats.kbCount} 个资料夹`
    if (options.viewMode.value === 'shelf') return `全部资料：共 ${options.stats.docCount} 份资料`
    if (options.viewMode.value === 'gallery') return `全部图片：共 ${options.galleryStats.total} 张`
    return `全部主题：共 ${options.mapStats.total} 个`
  })

  const workspaceFilterTitle = computed(() => {
    if (options.viewMode.value === 'gallery') return '图片筛选'
    if (options.viewMode.value === 'wiki') return '知识筛选'
    return '资料筛选'
  })

  const workspaceFilterDefault = computed(() => {
    if (options.viewMode.value === 'list' || options.viewMode.value === 'shelf') {
      return { fileType: [], status: [] }
    }
    if (options.viewMode.value === 'gallery') {
      return { kind: [], descriptionStatus: [] }
    }
    if (options.viewMode.value === 'wiki') {
      return { sourceType: [], pageType: [], learning: [] }
    }
    return {}
  })

  const workspaceFilterGroups = computed(() => {
    if (options.viewMode.value === 'gallery') {
      return [
        {
          key: 'kind',
          label: '图片类型',
          type: 'checkbox',
          options: [
            { value: 'photo', label: '照片' },
            { value: 'diagram', label: '示意图' },
            { value: 'table', label: '表格' },
            { value: 'formula', label: '公式' },
            { value: 'screenshot', label: '截图' }
          ]
        },
        {
          key: 'descriptionStatus',
          label: '描述状态',
          type: 'checkbox',
          options: [
            { value: 'done', label: '已描述' },
            { value: 'pending', label: '待描述' },
            { value: 'failed', label: '失败' }
          ]
        }
      ]
    }
    if (options.viewMode.value === 'wiki') {
      return [
        {
          key: 'sourceType',
          label: '实体集类型',
          type: 'checkbox',
          options: [
            { value: 'topic', label: '知识主题' },
            { value: 'bank', label: '题库' },
            { value: 'document', label: '资料' },
            { value: 'web', label: '网页' },
            { value: 'note', label: '笔记' },
            { value: 'image', label: '图片' }
          ]
        },
        {
          key: 'pageType',
          label: '主题页类型',
          type: 'checkbox',
          options: [
            { value: 'summary', label: '摘要' },
            { value: 'entity', label: '实体' },
            { value: 'concept', label: '概念' },
            { value: 'synthesis', label: '综合' },
            { value: 'comparison', label: '对比' },
            { value: 'overview', label: '总览' }
          ]
        },
        {
          key: 'learning',
          label: '学习状态',
          type: 'checkbox',
          options: [
            { value: 'unread', label: '未学' },
            { value: 'reading', label: '已读' },
            { value: 'practicing', label: '练习中' },
            { value: 'mastered', label: '已掌握' }
          ]
        }
      ]
    }
    return [
      {
        key: 'fileType',
        label: '资料类型',
        type: 'checkbox',
        options: [
          { value: 'word', label: 'Word' },
          { value: 'pdf', label: 'PDF' },
          { value: 'ppt', label: 'PPT' },
          { value: 'text', label: 'Markdown / TXT' },
          { value: 'image', label: '图片' }
        ]
      },
      {
        key: 'status',
        label: '处理状态',
        type: 'checkbox',
        options: [
          { value: 'ready', label: '可检索' },
          { value: 'processing', label: '处理中' },
          { value: 'failed', label: '失败' },
          { value: 'blocked', label: '已屏蔽' }
        ]
      }
    ]
  })

  const visibleFiles = computed(() => {
    const files = options.activeKb.value?.files || []
    const query = options.workspaceSearch.value.trim().toLowerCase()
    const types = Array.isArray(options.workspaceFilters.fileType) ? options.workspaceFilters.fileType : []
    const statuses = Array.isArray(options.workspaceFilters.status) ? options.workspaceFilters.status : []
    return files.filter((doc: any) => {
      if (query && !`${doc.fileName || ''} ${doc.note || ''}`.toLowerCase().includes(query)) return false
      if (types.length && !types.includes(documentTypeKey(doc))) return false
      if (statuses.length && !statuses.includes(documentStatusKey(doc))) return false
      return true
    })
  })

  return {
    workspaceSearchPlaceholder,
    workspaceCountLabel,
    workspaceFilterTitle,
    workspaceFilterDefault,
    workspaceFilterGroups,
    visibleFiles
  }
}
