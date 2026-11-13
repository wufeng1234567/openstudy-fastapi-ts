/** AiChatStream 的纯展示/状态派生函数。 */

export function progressHeadline(msg: any): string {
  const steps: any[] = Array.isArray(msg?.steps) ? msg.steps : []
  if (steps.length) {
    const running = steps.find((s) => s.state === 'running')
    if (running?.message) return String(running.message)
    const last = steps[steps.length - 1]
    if (last?.message) return String(last.message)
  }
  return msg?.content || '正在处理…'
}

export function expertHeadline(ex: any): string {
  const s = String(ex?.summary || '').replace(/\s+/g, ' ').trim()
  if (ex?.status === 'fail') return s ? `执行失败：${s}` : '执行失败'
  if (s) return s
  return ex?.status === 'ok' ? '已完成（没有返回结论）' : '已完成'
}

export function visibleSteps(ex: any): any[] {
  const all = Array.isArray(ex?.steps) ? ex.steps : []
  const kept = all.filter((st: any) => ['tool_call', 'tool_result', 'error'].includes(String(st?.phase || '')))
  const src = kept.length ? kept : all
  return src.slice(-4)
}

export function stepState(st: any): 'fail' | 'ok' | 'running' {
  if (st?.phase === 'error' || st?.success === false) return 'fail'
  if (st?.success === true) return 'ok'
  return 'running'
}

export function expertGroupTitle(experts: any): string {
  const list = Array.isArray(experts) ? experts : []
  const n = list.length
  const running = list.some((e: any) => e?.status === 'running')
  return running ? `专家协同中（${n} 位）` : `专家协同完成（${n} 位）`
}

export function isLastAssistantEmpty(messages: any[], idx: number): boolean {
  for (let i = messages.length - 1; i > idx; i--) {
    const t = messages[i].type
    if (
      messages[i].role === 'assistant' &&
      t !== 'tool_confirm' &&
      t !== 'tool_result' &&
      t !== 'agent_note' &&
      t !== 'experts'
    ) {
      return false
    }
  }
  return true
}

export function noteIcon(kind: string): string {
  if (kind === 'correct') return '↻'
  if (kind === 'error') return '✕'
  return '!'
}

/** 取某一轮 `turn_end` 之前的 assistant 正文。 */
export function getTurnAnswerText(list: any[], turnId: string | number | undefined): string {
  let end = -1
  for (let i = list.length - 1; i >= 0; i--) {
    const m = list[i]
    if (m && m.type === 'turn_end' && String(m.turnId) === String(turnId)) {
      end = i
      break
    }
  }
  if (end < 0) return ''
  const parts: string[] = []
  for (let i = end - 1; i >= 0; i--) {
    const m = list[i]
    if (m && m.type === 'turn_end') break
    if (m && m.role === 'assistant' && !m.type && String(m.content || '').trim()) {
      parts.unshift(String(m.content))
    }
  }
  return parts.join('\n\n')
}
