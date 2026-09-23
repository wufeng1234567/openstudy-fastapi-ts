// TEMP probe — delete after use. Cross-checks fe-1's 14-value table and asks:
// in the NON-sample scenario, which guard is load-bearing for STRING counts?
// (does not touch the repo file: variants are built from the extracted script text)
import fs from 'node:fs'
import ts from 'typescript'
import { parse } from '@vue/compiler-sfc'

const T = "const total = k === 'sample' && typeof p.count === 'number' ? p.count : items.length"
const raw = parse(fs.readFileSync('src/components/AgentConfirmCard/index.vue', 'utf8'), {
  filename: 'AgentConfirmCard/index.vue'
}).descriptor.scriptSetup.content
const strip = (s) => s.replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')

const VARIANTS = {
  real: strip(raw),
  keydrop: strip(raw).replace(T, "const total = typeof p.count === 'number' ? p.count : items.length"),
  bare: strip(raw).replace(T, 'const total = p.count')
}

const compile = (code) => {
  const out = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: 'x.ts',
    reportDiagnostics: true // fe-1's tip: don't silently run broken JS
  })
  const errs = (out.diagnostics || []).filter((d) => d.category === ts.DiagnosticCategory.Error)
  if (errs.length) throw new Error('TS: ' + errs.map((d) => ts.flattenDiagnosticMessageText(d.messageText, ' ')).join(' / '))
  return out.outputText
}

const run = (code, preview) => {
  const f = new Function(
    'computed', 'defineProps', 'defineEmits',
    compile(code) + '\n;return { previewLists: previewLists }'
  )
  const o = f(
    (fn) => ({ get value() { return fn() } }),
    () => ({ preview }),
    () => () => {}
  )
  return o.previewLists.value[0].heading
}

const S5 = ['第1题', '第2题', '第3题', '第4题', '第5题']
const VALUES = [
  ['10', 10], ["'10'", '10'], ["'5'", '5'], ["'0'", '0'], ['0', 0],
  ["'abc'", 'abc'], ['NaN', NaN], ['Infinity', Infinity], ['true', true],
  ['{}', {}], ['[]', []], ['null', null], ['undefined', undefined], ['不传', Symbol('absent')]
]

const preview = (scenario, v) => {
  const p = scenario === 'sample' ? { action: 'batch_import', sample: S5 } : { bank_names: ['甲库', '乙库'] }
  if (v !== undefined && typeof v !== 'symbol') p.count = v
  return p
}

for (const scenario of ['sample', 'bank_names']) {
  console.log(`\n===== 场景 ${scenario} =====`)
  console.log('  count       |  real                        |  keydrop                     |  bare')
  for (const [label, v] of VALUES) {
    const cell = (variant) => run(VARIANTS[variant], preview(scenario, v)).padEnd(28)
    const r = cell('real'), k = cell('keydrop'), b = cell('bare')
    const marks = []
    if (k !== r) marks.push('keydrop≠real')
    if (b !== r) marks.push('bare≠real')
    console.log(`  ${label.padEnd(11)} | ${r} | ${k} | ${b}   ${marks.length ? '<< ' + marks.join(', ') : ''}`)
  }
}
