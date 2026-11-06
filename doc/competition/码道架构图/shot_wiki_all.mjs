import fs from 'node:fs'

const OUT_DIR = 'D:/OpenStudy/apps/fastapi-v2/doc/screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const login = await fetch('http://127.0.0.1:9101/quickLogin', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ account: 'user1' })
}).then((r) => r.json())
const token = login?.data?.token
const targets = await fetch('http://127.0.0.1:9222/json').then((r) => r.json())
const page = targets.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let seq = 0
const pending = new Map()
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id)
    pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
}
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq
  pending.set(id, { resolve, reject })
  ws.send(JSON.stringify({ id, method, params }))
})
const evaljs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true })
  return r.result?.value
}
const capture = async (name) => {
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const out = `${OUT_DIR}/${name}`
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'))
  console.log('saved', out)
}

await send('Network.enable')
await send('Page.enable')
await send('Network.setCookie', { name: 'Admin-Token', value: token, domain: '127.0.0.1', path: '/' })
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1.5, mobile: false })
await send('Page.navigate', { url: 'http://127.0.0.1:3167/#/front/workspace' })
await sleep(1400)
await send('Page.reload', { ignoreCache: true })
await sleep(6500)
console.log(await evaljs(`(() => { const kb=[...document.querySelectorAll('.kbp-kb__name')].find(e=>e.textContent.trim()==='人工智能1'); if(kb) kb.click(); return !!kb; })()`))
await sleep(2600)
console.log(await evaljs(`(() => { const t=[...document.querySelectorAll('.kbp-tab')].find(e=>e.textContent.includes('知识百科')); if(t) t.click(); return !!t; })()`))
await sleep(4200)
console.log(await evaljs(`(() => ({cards:[...document.querySelectorAll('.kw-card h3')].map(e=>e.textContent.trim()), stats:document.body.innerText.match(/全部主题[^\\n]*/)?.[0]||''}))()`))
await capture('40-knowledge-wiki-0.5.0.png')

// 打开智能体主题页
console.log(await evaljs(`(() => { const card=[...document.querySelectorAll('.kw-card')].find(e=>e.querySelector('h3')?.textContent.trim()==='智能体'); if(card) card.click(); return !!card; })()`))
await sleep(2600)
console.log(await evaljs(`(() => ({drawer:!!document.querySelector('.kw-detail'), title:document.querySelector('.kw-detail h2')?.textContent||'', sections:[...document.querySelectorAll('.kw-detail__section h3')].map(e=>e.textContent)}))()`))
await capture('41-knowledge-wiki-detail-0.5.0.png')

// 关闭详情，切知识地图
await evaljs(`document.querySelector('.kw-detail__close')?.click()`)
await sleep(700)
console.log(await evaljs(`(() => { const b=[...document.querySelectorAll('.kw-switch button')].find(e=>e.textContent.includes('知识地图')); if(b) b.click(); return !!b; })()`))
await sleep(2200)
console.log(await evaljs(`(() => ({map:!!document.querySelector('.kw-map'), nodes:document.querySelectorAll('.kw-map-node').length, edges:document.querySelectorAll('.kw-map-edge').length}))()`))
await capture('42-knowledge-wiki-map-0.5.0.png')

ws.close()
process.exit(0)
