import fs from 'node:fs'

const OUT = 'D:/OpenStudy/apps/fastapi-v2/doc/screenshots/40-knowledge-wiki-0.5.0.png'
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
await send('Network.enable')
await send('Page.enable')
await send('Network.setCookie', { name: 'Admin-Token', value: token, domain: '127.0.0.1', path: '/' })
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1.5, mobile: false })
await send('Page.navigate', { url: 'http://127.0.0.1:3167/#/front/workspace' })
await sleep(1400)
await send('Page.reload', { ignoreCache: true })
await sleep(6500)
const folder = await send('Runtime.evaluate', {
  expression: `(() => { const names=[...document.querySelectorAll('.kbp-kb__name')].map(e=>e.textContent.trim()); const kb=[...document.querySelectorAll('.kbp-kb__name')].find(e=>e.textContent.trim()==='人工智能1'); if(kb) kb.click(); return JSON.stringify({names:names.slice(0,8), clicked:!!kb}); })()`,
  returnByValue: true
})
console.log('folder', folder.result.value)
await sleep(3000)
const tab = await send('Runtime.evaluate', {
  expression: `(() => { const tabs=[...document.querySelectorAll('.kbp-tab')].map(e=>e.textContent.trim()); const t=[...document.querySelectorAll('.kbp-tab')].find(e=>e.textContent.includes('知识百科')); if(t) t.click(); return JSON.stringify({tabs, clicked:!!t}); })()`,
  returnByValue: true
})
console.log('tab', tab.result.value)
await sleep(4500)
const info = await send('Runtime.evaluate', {
  expression: `(() => ({ title: document.title, cards: [...document.querySelectorAll('.kw-card h3')].map(e=>e.textContent.trim()).slice(0,20), count: document.querySelectorAll('.kw-card').length, empty: document.querySelector('.kw-empty')?.innerText || '', body: document.body.innerText.slice(0,500) }))()`,
  returnByValue: true
})
console.log('info', JSON.stringify(info.result.value, null, 2))
const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
fs.writeFileSync(OUT, Buffer.from(shot.data, 'base64'))
console.log('saved', OUT)
ws.close()
process.exit(0)
