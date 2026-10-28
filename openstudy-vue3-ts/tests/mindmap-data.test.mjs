/**
 * mindmapData 纯函数测试（无浏览器 / 无网络）
 *
 * 覆盖：
 *   1) Markdown → 树的层级判定（标题 / 列表缩进 / 同根标题去重）
 *   2) 树 → mind-elixir 数据（id 稳定唯一、topic 原样）
 *   3) 节点计数
 *
 * 运行：node tests/mindmap-data.test.mjs
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')

const results = []
function check(name, cond, detail = '') {
  results.push({ name, ok: !!cond, detail })
  console.log(`  ${cond ? 'PASS' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`)
}

const server = await createServer({
  root: ROOT,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
})
const mod = await server.ssrLoadModule('/src/utils/mindmapData.ts')

try {
  const { parseMarkdownToTree, toMindElixirData, countMindNodes } = mod

  // 1) 标题 + 列表缩进 + 同根标题去重
  const md = `# Vue3 深度实战笔记

## 技术栈

- 核心框架：Vue 3.4
- 状态管理：Pinia

## 核心概念

- 响应式系统
  - Proxy 拦截
- 组合式函数`
  const tree = parseMarkdownToTree(md, 'Vue3 深度实战笔记')
  check('解析出根节点', tree?.name === 'Vue3 深度实战笔记', tree?.name || 'null')
  check('根下有两个一级分支', tree?.children?.length === 2, String(tree?.children?.length))
  check('一级分支名称正确', tree?.children?.[0]?.name === '技术栈' && tree?.children?.[1]?.name === '核心概念')
  const stack = tree?.children?.[0]
  check('列表缩进产生第二层', stack?.children?.length === 2 && stack?.children?.[0]?.name === '核心框架：Vue 3.4')
  const deep = tree?.children?.[1]?.children?.[0]
  check('两空格缩进产生第三层', deep?.children?.[0]?.name === 'Proxy 拦截', deep?.children?.[0]?.name || '')
  check('节点总数正确（根+2+2+2+1 = 8）', countMindNodes(tree) === 8, String(countMindNodes(tree)))

  // 2) 无层级内容 → null（空态由组件负责）
  check('纯连续文字返回 null', parseMarkdownToTree('这是一段没有任何标题和列表的连续文字。', '标题') === null)

  // 3) 树 → mind-elixir：id 唯一、topic 原样
  const data = toMindElixirData(tree)
  check('转换结果有 nodeData', !!data?.nodeData)
  check('根 topic 正确', data?.nodeData?.topic === 'Vue3 深度实战笔记')
  const ids = []
  const walk = (n) => { ids.push(n.id); (n.children || []).forEach(walk) }
  walk(data.nodeData)
  check('mind-elixir 节点数正确', ids.length === 8, String(ids.length))
  check('所有 id 均非空且唯一', ids.every(Boolean) && new Set(ids).size === ids.length)
  check('叶子 topic 保持完整文本', walk && data.nodeData.children[1].children[0].children[0].topic === 'Proxy 拦截')

  // 4) 同树重复转换 id 稳定
  const data2 = toMindElixirData(tree)
  const ids2 = []
  const walk2 = (n) => { ids2.push(n.id); (n.children || []).forEach(walk2) }
  walk2(data2.nodeData)
  check('同树两次转换 id 完全一致', JSON.stringify(ids) === JSON.stringify(ids2))

  // 5) 空树
  check('null 树转换返回 null', toMindElixirData(null) === null)
  check('null 树计数为 0', countMindNodes(null) === 0)
} finally {
  await server.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n结果：${results.length - failed.length} / ${results.length} 项通过`)
if (failed.length) process.exit(1)
