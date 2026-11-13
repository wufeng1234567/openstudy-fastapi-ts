// api/ai/agentDsFreeResponse.ts
//
// DS 免费 Agent 接口的**响应解析**辅助（从 `agentDsFree.ts` 抽出）。
//
//   · `serverReason` —— 从服务端响应里取出「失败原因」
//
// ⚠ 依赖方向单向：`agentDsFree.ts` → 本模块；本模块**零 import**，
//    不反向依赖它，因此不会形成循环依赖。
//
// ⚠ **API 请求、返回结构、导出面一个字节都没动** —— 这里只把「怎么读错误信息」
//    挪到了可独立读、可独立测的地方。函数体是**从原文件逐字搬过来的**。

/**
 * 从服务端响应里取出「失败原因」
 *
 * ⚠️ `code` 不是 200（或缺失）时才算失败；`msg` 为空就返回空串，
 *    让调用方回落到自己的兜底文案（「保存失败（HTTP xxx）」）。
 */
export function serverReason(data: any): string {
  const code = Number(data?.code)
  if (!Number.isFinite(code) || code === 200) return ''
  const msg = typeof data?.msg === 'string' ? data.msg.trim() : ''
  return msg ? `${msg}（服务端 code=${code}）` : ''
}
