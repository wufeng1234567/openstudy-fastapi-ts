/**
 * Agent 工具清单 API（界面用）
 *
 * 这里只保留与「工具开关 / 工具清单」相关的通用请求，不放任何模型特有的循环逻辑。
 */

import { getToken } from '@/utils/auth'
import type { AgentToolDefinition, AgentToolsPayload } from './agent'

const BASE = import.meta.env.VITE_APP_BASE_API

let _toolsCache: AgentToolsPayload | null = null
let _actionsCache: Record<string, { write?: string[]; destructive?: string[] }> = {}

/** 清掉工具清单缓存（页面刷新 / 工具设置保存后使用） */
export function resetAgentToolsCache(): void {
  _toolsCache = null
  _actionsCache = {}
}

async function loadAgentToolsPayload(): Promise<AgentToolsPayload | null> {
  if (_toolsCache) return _toolsCache
  try {
    const res = await fetch(`${BASE}/ai/agent/tools`, {
      headers: { Authorization: 'Bearer ' + getToken() }
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (!Array.isArray(data?.tools)) throw new Error('响应里没有 tools 数组')
    _toolsCache = {
      tools: data.tools,
      actions: data && typeof data.actions === 'object' && data.actions ? data.actions : {}
    }
    _actionsCache = _toolsCache.actions || {}
  } catch (e) {
    // 失败不写缓存：避免一次网络抖动把工具清单永久锁成空数组。
    console.warn('[agent] 拉取工具清单失败（不缓存，下次重试）', e)
  }
  return _toolsCache
}

/** 生效工具清单（过滤 disabled=1），供后端循环或界面展示使用 */
export async function fetchAgentTools(): Promise<AgentToolDefinition[]> {
  const payload = await loadAgentToolsPayload()
  if (!payload) return []
  return payload.tools.filter((t) => t?.disabled !== 1)
}

/** 全量工具清单（含 disabled），供设置页开关渲染 */
export async function fetchAgentToolsForUi(): Promise<AgentToolsPayload> {
  const payload = await loadAgentToolsPayload()
  if (!payload) return { tools: [], actions: {} }
  return payload
}

export interface SaveAgentToolPrefResult {
  ok: boolean
  payload: AgentToolsPayload | null
  reason: string
}

function serverReason(data: any): string {
  const code = Number(data?.code)
  if (!Number.isFinite(code) || code === 200) return ''
  const msg = typeof data?.msg === 'string' ? data.msg.trim() : ''
  return msg ? `${msg}（服务端 code=${code}）` : ''
}

/** 保存单个工具开关；以服务端回显为准，避免把假成功渲染成已保存 */
export async function saveAgentToolPref(
  tool: string,
  disabled: 0 | 1
): Promise<SaveAgentToolPrefResult> {
  const fail = (reason: string): SaveAgentToolPrefResult => ({ ok: false, payload: null, reason })
  try {
    const res = await fetch(`${BASE}/ai/agent/tools`, {
      method: 'PUT',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ tool, disabled })
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) return fail(serverReason(data) || `保存失败（HTTP ${res.status}）`)
    if (!Array.isArray(data?.tools)) {
      return fail(serverReason(data) || '响应里没有工具列表（改动可能没落库）')
    }
    const entry = data.tools.find((t: any) => (t?.function || t)?.name === tool)
    if (!entry) return fail(`响应里没有 ${tool}（改动可能没落库）`)
    const echoed = entry.disabled === undefined ? 0 : Number(entry.disabled)
    if (echoed !== disabled) {
      return fail(`${tool} 的开关没变（服务端仍是 ${echoed}）`)
    }
    const prevActions = _toolsCache?.actions || {}
    const payload: AgentToolsPayload = {
      tools: data.tools,
      actions:
        data && typeof data.actions === 'object' && data.actions ? data.actions : prevActions
    }
    _toolsCache = payload
    return { ok: true, payload, reason: '' }
  } catch (e: any) {
    return fail(String(e?.message || e))
  }
}
