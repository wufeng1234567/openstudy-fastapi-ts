/**
 * 临时 SSR 取证（用完即删）—— **在 Node 里真的渲染一遍**，给「空气泡」这条缺陷留下红/绿两端。
 *
 * 只编译 SFC 的 `<template>`（`mode:'function'`）+ 用真 vue 的 `computed` 跑组件的
 * `<script setup>`，再交给 `@vue/server-renderer` 输出 HTML。全程离线，不碰浏览器。
 *
 * 用法：node tests/_probe_ssr_turnend.mjs [ROOT]     # ROOT 默认 cwd（可指向镜像做变异对照）
 */
import fs from 'node:fs'
import path from 'node:path'
import { parse, compileTemplate } from '@vue/compiler-sfc'
import { createSSRApp, computed, h, defineComponent } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ts from 'typescript'

const ROOT = process.argv[2] || process.cwd()
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8')

/** SFC 的模板 → 真的渲染函数 */
function renderFnOf(rel) {
  const source = read(rel)
  const { descriptor } = parse(source, { filename: rel })
  const r = compileTemplate({
    source: descriptor.template.content,
    filename: rel,
    id: 'probe',
    compilerOptions: { mode: 'function' }
  })
  if (r.errors.length) throw new Error('模板编译失败：' + r.errors[0].message || r.errors[0])
  // eslint-disable-next-line no-new-func
  return new Function('Vue', r.code)({ computed, h })
}

/** SFC 的 `<script setup>` → 真的跑一遍，拿它声明的那些常量 */
function scriptBindings(rel, props, emitted) {
  const source = read(rel)
  const { descriptor } = parse(source, { filename: rel })
  const raw = descriptor.scriptSetup?.content || ''
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  if (/\bimport\b/.test(noImport)) throw new Error('import 没剥干净')
  const js = ts.transpileModule(noImport, {
    compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2020 },
    fileName: 'probe.ts',
    reportDiagnostics: true
  })
  const errs = (js.diagnostics || []).filter((d) => d.category === ts.DiagnosticCategory.Error)
  if (errs.length) throw new Error('TS 转译报错：' + ts.flattenDiagnosticMessageText(errs[0].messageText, ' '))
  const names = [
    'stateForThisTurn',
    'status',
    'summary',
    'reverted',
    'skipped',
    'partial',
    'failed',
    'nothingToRollback',
    'canRollback',
    'buttonLabel',
    'canClick',
    'onClick',
    'opOf',
    'reasonOf',
    'errorOf'
  ]
  const code = `${js.outputText}\n;return { ${names.join(', ')} };`
  // eslint-disable-next-line no-new-func
  const f = new Function('computed', 'defineProps', 'defineEmits', code)
  const out = f(computed, () => props, () => (ev, payload) => emitted.push([ev, payload]))
  const ctx = { $slots: {}, $emit: () => {} }
  for (const k of names) ctx[k] = out[k] && out[k].value !== undefined ? out[k].value : out[k]
  for (const k of ['active', 'turnId', 'disabled', 'state']) ctx[k] = props[k]
  return ctx
}

const strip = (html) =>
  html
    .replace(/<[^>]*>/g, '|')
    .replace(/\|+/g, ' | ')
    .replace(/\s+/g, ' ')
    .trim()

const countOf = (html, cls) => (html.match(new RegExp(`class="[^"]*\\b${cls}\\b`, 'g')) || []).length

let bad = 0

/* ==========================================================================
 * A) AiChatStream：`turn_end` 那条标记渲染出来的是**回退组件**，还是**空白的 Agent 气泡**
 * ========================================================================== */
const STREAM = 'src/components/AiChatStream/index.vue'
const streamRender = renderFnOf(STREAM)
const stub = (name) => defineComponent({ name, render: () => h('span', { 'data-stub': name }) })

const streamHtml = async (extra) => {
  const ctx = {
    $slots: {},
    $emit: () => {},
    messages: [
      { role: 'user', content: '帮我把这份文档导进去' },
      { role: 'assistant', content: '已经建好题库并导入 3 道题。' },
      { role: 'assistant', type: 'turn_end', turnId: 't_1', content: '' }
    ],
    isGenerating: false,
    isPaused: false,
    disabled: false,
    thinking: false,
    hasAttachment: false,
    placeholder: '',
    mode: 'agent',
    showModeSwitch: false,
    showNewSession: false,
    scrollButtonBottom: 16,
    rollbackState: null,
    inputContent: '',
    messagesRef: null,
    loadingText: 'AI 思考中',
    noteIcon: () => '!',
    isLastAssistantEmpty: () => false,
    copyText: () => {},
    renderAgentMarkdown: (s) => s,
    handleSend: () => {},
    ...extra
  }
  const app = createSSRApp({ render: streamRender, setup: () => ctx })
  app.component('LoadingDots', stub('LoadingDots'))
  app.component('AgentReasoning', stub('AgentReasoning'))
  app.component('ScrollButton', stub('ScrollButton'))
  app.component('ChatAttachmentList', stub('ChatAttachmentList'))
  app.component('ChatInputArea', stub('ChatInputArea'))
  app.component('el-button', stub('el-button'))
  // 回退组件也桩掉：这一段只问「turn_end 落在哪一支」，组件内部由 B 段单独验
  app.component('AgentTurnRollback', stub('AgentTurnRollback'))
  return renderToString(app)
}

const bubbleOf = (html) => {
  // 只数「消息区」里的气泡：`.message-content`（不含输入区的桩）
  return countOf(html, 'message-content')
}

console.log(`\n### A) AiChatStream —— ROOT=${ROOT}`)
{
  const html = await streamHtml({ lastTurnId: 't_1' })
  const turnCells = countOf(html, 'msg-turn_end')
  const slots = countOf(html, 'turn-end-slot')
  const bubbles = bubbleOf(html)
  const hasStub = html.includes('AgentTurnRollback')
  console.log(`  最近一轮：.message-content=${bubbles}  .msg-turn_end=${turnCells}  .turn-end-slot=${slots}  组件挂上了=${hasStub}`)
  console.log(`  可见文案：${strip(html).slice(0, 200)}`)
  if (bubbles !== 1) {
    bad++
    console.log(`  ✗ 期望只有 1 个 .message-content（一条 assistant 正文）；实际 ${bubbles} —— 多出来的就是空气泡`)
  } else console.log('  ✓ turn_end 没有掉进正文分支（没有多出来的空气泡）')
  if (!hasStub) {
    bad++
    console.log('  ✗ turn_end 那一格没有挂回退组件')
  }
}
{
  const html = await streamHtml({ lastTurnId: '' })
  const hasStub = html.includes('AgentTurnRollback')
  console.log(`  非最近一轮（lastTurnId=''）：.message-content=${bubbleOf(html)}  组件挂上了=${hasStub}`)
  console.log('  （组件挂不挂是 L74 的静态判据管的；这里只记录渲染产物）')
}

/* ==========================================================================
 * B) AgentTurnRollback：跑真的 script setup（真 vue 的 computed）+ 渲染真模板
 * ========================================================================== */
const RB = 'src/components/AgentTurnRollback/index.vue'
const rbRender = renderFnOf(RB)

const rollbackHtml = async (props) => {
  const emitted = []
  const ctx = scriptBindings(RB, props, emitted)
  const app = createSSRApp({ render: rbRender, setup: () => ctx })
  return { html: await renderToString(app), emitted }
}

const baseProps = { turnId: 't_1', active: false, state: null, disabled: false }

console.log(`\n### B) AgentTurnRollback —— 真 script + 真模板`)
const cases = [
  ['非最近一轮（active=false）', { ...baseProps }, (html) => !html.includes('agent-rollback') && html.includes('<!--')],
  ['最近一轮 · 没点过（idle）', { ...baseProps, active: true }, (html) => html.includes('回退这次操作')],
  [
    '最近一轮 · 生成中（disabled）',
    { ...baseProps, active: true, disabled: true },
    (html) => html.includes('disabled') && /button[^>]*disabled/.test(html)
  ],
  [
    '结果：退了 2 条 + 1 条没退 + 1 条partial + 1 条失败',
    {
      ...baseProps,
      active: true,
      state: {
        turnId: 't_1',
        status: 'done',
        summary: {
          ok: true,
          reason: '',
          reverted: 2,
          skipped: [{ tool: 'bank_manage', action: 'delete', reason: 'missing_soft_delete', reasonText: '题库与题目目前是物理删除，暂时无法回退' }],
          partial: [{ tool: 'knowledge_base_manage', action: 'delete_document', reason: 'documents_destroyed', reasonText: '知识库已恢复，但其中的文档与分块已被物理删除' }],
          failed: [{ tool: 'note_manage', action: 'update', error: "RuntimeError: 没有命中任何行（id=[7]）" }]
        }
      }
    },
    (html) =>
      html.includes('已回退 2 项操作') &&
      html.includes('题库与题目目前是物理删除') &&
      html.includes('文档与分块已被物理删除') &&
      html.includes('RuntimeError: 没有命中任何行') &&
      html.includes('重试')
  ],
  [
    '结果：一条都没退，但三份清单都空（只有查询）',
    { ...baseProps, active: true, state: { turnId: 't_1', status: 'done', summary: { ok: true, reason: '', reverted: 0, skipped: [], failed: [], partial: [] } } },
    (html) => html.includes('这一轮没有可回退的操作') && !html.includes('回退失败')
  ],
  [
    '整轮被拒：reason 原样显示',
    { ...baseProps, active: true, state: { turnId: 't_1', status: 'fail', summary: { ok: false, reason: '该轮次不存在或不属于你（服务端 code=403）', reverted: 0, skipped: [], failed: [], partial: [] } } },
    (html) => html.includes('该轮次不存在或不属于你（服务端 code=403）')
  ],
  [
    '状态属于**别的轮次**（不该画到这一轮上）',
    { ...baseProps, active: true, state: { turnId: 't_别的', status: 'done', summary: { ok: true, reason: '', reverted: 9, skipped: [], failed: [], partial: [] } } },
    (html) => !html.includes('9 项操作') && html.includes('回退这次操作')
  ]
]

for (const [label, props, ok] of cases) {
  try {
    const { html } = await rollbackHtml(props)
    const pass = ok(html)
    if (!pass) bad++
    console.log(`  ${pass ? '✓' : '✗'} ${label}`)
    console.log(`      文案：${strip(html).slice(0, 220)}`)
  } catch (e) {
    bad++
    console.log(`  ✗ ${label} —— 渲染抛错：${e.message}`)
  }
}

/* 点击 → emit */
{
  const props = { ...baseProps, active: true }
  const emitted = []
  const ctx = scriptBindings(RB, props, emitted)
  ctx.onClick()
  const pass = emitted.length === 1 && emitted[0][0] === 'rollback' && emitted[0][1] === 't_1'
  if (!pass) bad++
  console.log(`  ${pass ? '✓' : '✗'} 点按钮 → emit('rollback', turnId)：${JSON.stringify(emitted)}`)
}

console.log(bad ? `\n${bad} 条不符合预期` : '\n全部符合预期')
process.exit(bad ? 1 : 0)
