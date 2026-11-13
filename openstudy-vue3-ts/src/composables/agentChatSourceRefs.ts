// composables/agentChatSourceRefs.ts
//
// 工具成功后带回的**来源引用**（从 `useAgentChat.ts` 抽出）。
//
//   · `mergeSourceRefs` —— 按工具类型分派，把该工具产出的来源引用并进已有的引用表
//
// ⚠ 依赖方向单向：`useAgentChat.ts` → 本模块 → `agentChatReferences`；
//    这两个模块**都不反向依赖** composable，因此不会形成循环依赖。
//
// ⚠ **SSE 事件顺序与公开导出一个字节都没动** —— 这里只把「哪些工具会带回引用、
//    各自怎么并」挪到了可独立读、可独立测的地方；`pendingReferences` 的读写时机
//    与先后完全保留在 `useAgentChat.ts` 里。
//
// ⚠️ **四类工具的合并顺序逐字照搬**（知识库检索 → 文档读取 → 图库 → 网页搜索），
//    每一类都是**各自单独**并一次 —— 不是「先攒齐再并一次」。两种写法在去重与
//    24 条上限上等价，但这里刻意保持原样，避免以后有人「顺手优化」时改变行为。
import type { AgentEvent } from '@/api/ai/agent'
import {
  collectDocumentReferences,
  collectGalleryReferences,
  collectKnowledgeReferences,
  collectWebReferences,
  mergeKnowledgeReferences
} from './agentChatReferences'

/**
 * 把本次工具结果带回的来源引用并进 `base`，返回合并后的引用表。
 *
 * 四类工具各自产出的引用形状不同（知识库片段 / 文档小节 / 图库图片 / 网页），
 * 所以按工具类型分派、**分别**并入。
 */
export function mergeSourceRefs(base: any[], event: AgentEvent): any[] {
  let out = base
  if (
    event.success &&
    ['knowledge_search', 'search_knowledge', 'workspace_search'].includes(event.tool || '')
  ) {
    const refs = collectKnowledgeReferences(event.data)
    if (refs.length) out = mergeKnowledgeReferences(out, refs)
  }
  if (
    event.success &&
    event.tool === 'knowledge_base_manage' &&
    ['read_document', 'get_document', 'read'].includes(String(event.action || event.data?.action || ''))
  ) {
    const refs = collectDocumentReferences(event.data)
    if (refs.length) out = mergeKnowledgeReferences(out, refs)
  }
  if (event.success && event.tool === 'gallery_manage') {
    const refs = collectGalleryReferences(event.data)
    if (refs.length) out = mergeKnowledgeReferences(out, refs)
  }
  if (event.success && event.tool === 'web_search') {
    const refs = collectWebReferences(event.data)
    if (refs.length) out = mergeKnowledgeReferences(out, refs)
  }
  return out
}
