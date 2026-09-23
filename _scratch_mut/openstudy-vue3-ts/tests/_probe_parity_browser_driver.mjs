/**
 * 临时探针（audit 用，跑完即删）：在 Node 里用 vite SSR 把**浏览器驱动**
 * `src/devtools/dfSelfCheck/runLoopGroup.ts` 真跑一遍，与 Node 驱动
 * `tests/check_agent_dsfree.mjs` 的同一批 LOOP 用例逐条比对。
 */
import { createServer } from 'vite'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { LOOP_CASES } from './df_cases.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const VUE_ROOT = path.resolve(__dirname, '..')
const STUB_PREFIX = String.fromCharCode(0) + 'dfstub:'
const BS = String.fromCharCode(92)

const stubs = {
  '@/utils/auth': 'export function getToken(){ return "df-test-token" }',
  '@/utils/doc-parse': [
    'export const DOC_UPLOAD_MAX_IMAGES = 8',
    'export function parseDocFile(){ return { text: "", images: [] } }',
    'export function dataUrlToFile(){ return null }',
    'export function extFromMime(){ return "txt" }',
    'export async function parseFileToBlocks(){ return { blocks: [], images: [] } }'
  ].join('\n'),
  '@/utils/image-compress': [
    'export function compressImageDataUrl(_n, d){ return Promise.resolve(d) }',
    'export function mimeOfDataUrl(){ return "image/png" }',
    'export function dataUrlByteSize(){ return 0 }'
  ].join('\n')
}

const keyOf = (id) => {
  const norm = String(id).split(BS).join('/')
  for (const key of Object.keys(stubs)) {
    const rel = key.slice(2) // 去掉 "@/"
    if (norm === key || norm.endsWith('/src/' + rel + '.ts')) return key
  }
  return ''
}

const server = await createServer({
  root: VUE_ROOT,
  logLevel: 'error',
  cacheDir: 'node_modules/.vite-dftest',
  server: { middlewareMode: true },
  appType: 'custom',
  plugins: [
    {
      name: 'df-stub',
      enforce: 'pre',
      resolveId(id) {
        const k = keyOf(id)
        if (k) return STUB_PREFIX + k
      },
      load(id) {
        if (id.startsWith(STUB_PREFIX)) return stubs[id.slice(STUB_PREFIX.length)]
      }
    }
  ]
})

let rows = []
try {
  const mod = await server.ssrLoadModule('@/devtools/dfSelfCheck/runLoopGroup')
  rows = await mod.runLoopGroup(LOOP_CASES)
} finally {
  await server.close()
}

const nodeRes = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'check_agent_dsfree_result.json'), 'utf8')
)
const nodeLoop = new Map(nodeRes.rows.filter((r) => r.suite === 'LOOP').map((r) => [r.id, r]))

console.log('browser-driver rows=' + rows.length + '  node-driver LOOP rows=' + nodeLoop.size)
console.log('只有浏览器驱动有：' + JSON.stringify(rows.filter((r) => !nodeLoop.has(r.id)).map((r) => r.id)))
console.log('只有 Node 驱动有：' + JSON.stringify([...nodeLoop.keys()].filter((id) => !rows.some((r) => r.id === id))))

const diff = []
for (const r of rows) {
  const n = nodeLoop.get(r.id)
  if (n && n.status !== r.status) diff.push({ id: r.id, node: n.status, browser: r.status })
}
console.log('状态不一致 ' + diff.length + ' 条')
for (const d of diff) console.log('   ' + JSON.stringify(d))
const failed = rows.filter((r) => r.status !== '通过')
console.log('浏览器驱动非通过 ' + failed.length + ' 条：' + JSON.stringify(failed.map((r) => [r.id, r.status])))

const out = rows.map((r) => ({
  id: r.id,
  status: r.status,
  asserts: (r.asserts || []).map((a) => [a.label, !!a.pass, a.actual == null ? '' : String(a.actual)])
}))
fs.writeFileSync(path.join(__dirname, '_probe_browser_rows.json'), JSON.stringify(out, null, 2))
console.log('细分断言 -> tests/_probe_browser_rows.json')
