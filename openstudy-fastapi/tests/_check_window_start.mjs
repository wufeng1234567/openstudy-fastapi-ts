// 验证「渲染窗口起点对齐到用户消息」的算法。
//
// 对应 bug（用户 2026-10-18 截图）：
//   历史很长时只渲染最近 RENDER_CHUNK(40) 条，按条数切会把起点切在一轮**中间**，
//   于是窗口最上方是一条助手回复（还带「已深度思考」），却看不到它回答的提问。
//   期望：窗口顶部**永远是一轮的提问**（role === 'user'）。
//
// 这里把 AiChatStream 里的 windowStart 算法原样复刻一遍，用几种典型消息形态验证。

const RENDER_CHUNK = 40

/** 复刻组件里的算法 */
function windowStart(all, renderLimit) {
  if (all.length <= renderLimit) return 0
  const rough = all.length - renderLimit
  for (let i = rough; i < all.length; i++) {
    if (all[i]?.role === 'user') return i
  }
  return rough
}

/** 不复刻旧算法，用同样的"按条数粗切"作为对照组 */
function oldStart(all, renderLimit) {
  if (all.length <= renderLimit) return 0
  return all.length - renderLimit
}

/**
 * 造一段对话：每轮 = 1 条 user + n 条 assistant（含 reasoning / tool_result / 正文）
 * @param {number} turns 轮数
 */
function makeConversation(turns) {
  const out = []
  for (let t = 0; t < turns; t++) {
    out.push({ role: 'user', content: `问题 ${t + 1}` })
    out.push({ role: 'assistant', type: 'reasoning', content: `思考 ${t + 1}` })
    out.push({ role: 'assistant', content: `回答 ${t + 1}` })
    out.push({ role: 'assistant', type: 'tool_result', content: `工具 ${t + 1}` })
  }
  return out
}

let failures = 0
function check(name, cond, detail) {
  if (cond) {
    console.log(`  ✓ ${name}`)
  } else {
    failures++
    console.log(`  ✗ ${name}  ${detail || ''}`)
  }
}

/** 检查某个窗口的顶部是不是用户消息 */
function assertTopsWithUser(name, conv, limit) {
  const start = windowStart(conv, limit)
  const vis = conv.slice(start)
  const first = vis[0]
  check(
    `${name}（共 ${conv.length} 条，窗口 ${vis.length} 条）顶部是用户消息`,
    first && first.role === 'user',
    `实际顶部 role=${first ? first.role : 'none'} type=${first ? first.type || '-' : '-'}`
  )
  return { start, first }
}

console.log('=== 1. 4 条/轮 × 40 轮 = 160 条（窗口 40） ===')
{
  const conv = makeConversation(40)
  assertTopsWithUser('默认窗口', conv, RENDER_CHUNK)
  // 旧算法作对照
  const oldIdx = oldStart(conv, RENDER_CHUNK)
  const oldFirst = conv[oldIdx]
  console.log(
    `  · 旧算法起点 ${oldIdx} → role=${oldFirst.role} type=${oldFirst.type || '（正文）'}` +
      (oldFirst.role === 'user' ? '  （碰巧对）' : '  ← 这就是 bug：顶部是回复没有提问')
  )
}

console.log('\n=== 2. 不规则轮次（2~6 条/轮） ===')
{
  const conv = []
  let i = 0
  for (let t = 0; t < 30; t++) {
    conv.push({ role: 'user', content: `q${t}` })
    const n = 1 + (t % 5) // 1~5 条回复
    for (let k = 0; k < n; k++) {
      conv.push({ role: 'assistant', type: k === 0 ? 'reasoning' : undefined, content: `a${t}-${k}` })
    }
  }
  assertTopsWithUser('不规则窗口', conv, RENDER_CHUNK)
}

console.log('\n=== 3. 加载更早后（窗口 80 / 120） ===')
{
  const conv = makeConversation(60) // 240 条
  assertTopsWithUser('窗口 80', conv, 80)
  assertTopsWithUser('窗口 120', conv, 120)
}

console.log('\n=== 4. 消息数不足一屏（不应有"加载更早"） ===')
{
  const conv = makeConversation(5) // 20 条
  const start = windowStart(conv, RENDER_CHUNK)
  check('20 条时窗口起点为 0', start === 0, `实际 ${start}`)
  check('20 条时无"更早"', conv.length - start === conv.length)
}

console.log('\n=== 5. 首条就是 user（正常会话） ===')
{
  const conv = makeConversation(20)
  const start = windowStart(conv, RENDER_CHUNK)
  check(
    '窗口末尾始终覆盖到最后一条',
    conv.slice(start).length + start === conv.length,
    `start=${start}`
  )
}

console.log('\n=== 6. 极端：窗口内没有任何 user（异常数据兜底） ===')
{
  const conv = []
  conv.push({ role: 'user', content: 'q0' })
  for (let k = 0; k < 100; k++) conv.push({ role: 'assistant', content: `a${k}` })
  const start = windowStart(conv, RENDER_CHUNK)
  check('兜底不越界', start >= 0 && start < conv.length, `start=${start}`)
  console.log(`  · 该情况无 user 可用，退回粗切起点 ${start}（role=${conv[start].role}）`)
}

console.log(`\n${failures === 0 ? '全部通过' : `失败 ${failures} 项`}`)
process.exit(failures === 0 ? 0 : 1)
