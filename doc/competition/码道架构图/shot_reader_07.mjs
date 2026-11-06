import fs from 'node:fs'

const OUT = 'D:/OpenStudy/apps/fastapi-v2/doc/screenshots/46-reader-0.7.0.png'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const login = await fetch('http://127.0.0.1:9101/quickLogin', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account: 'user1' })
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
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  }
}
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq; pending.set(id, { resolve, reject })
  ws.send(JSON.stringify({ id, method, params }))
})
const evaljs = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true })
  return r.result?.value
}
await send('Network.enable'); await send('Page.enable')
await send('Network.setCookie', { name: 'Admin-Token', value: token, domain: '127.0.0.1', path: '/' })
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1.5, mobile: false })
await send('Page.navigate', { url: 'http://127.0.0.1:3167/#/front/workspace' })
await sleep(1400); await send('Page.reload', { ignoreCache: true }); await sleep(6500)
console.log(await evaljs(`(() => { const kb=[...document.querySelectorAll('.kbp-kb__name')].find(e=>e.textContent.trim()==='人工智能1'); if(kb) kb.click(); return !!kb; })()`))
await sleep(2600)
console.log(await evaljs(`(() => { const row=document.querySelector('[data-doc-id="670"]'); if(row) row.scrollIntoView({block:'center'}); const btn=row?.querySelector('.kbp-doc__clinic'); if(btn) btn.click(); return JSON.stringify({row:!!row,btn:!!btn}); })()`))
await sleep(2200)
console.log(await evaljs(`(() => { const tabs=[...document.querySelectorAll('.clinic-tab')].map(e=>e.textContent.trim()); const t=[...document.querySelectorAll('.clinic-tab')].find(e=>e.textContent.includes('原文阅读')); if(t) t.click(); return JSON.stringify({tabs, clicked:!!t}); })()`))
await sleep(3500)
console.log(await evaljs(`(() => ({ title: document.querySelector('.reader-toolbar__title b')?.textContent || '', toc:[...document.querySelectorAll('.reader-toc__item')].map(e=>e.textContent.trim()).slice(0,8), sections:document.querySelectorAll('.reader-section').length }))()`))
const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
fs.writeFileSync(OUT, Buffer.from(shot.data, 'base64'))
console.log('saved', OUT)
console.log(await evaljs(`(() => { const items=[...document.querySelectorAll('.reader-toc__item')]; if(items[2]) items[2].click(); return items.length; })()`))
await sleep(1000)
console.log(await evaljs(`(() => ({ scrollTop: document.querySelector('.reader-main')?.scrollTop || 0, active: document.querySelector('.reader-toc__item.is-active')?.textContent.trim() || '' }))()`))
const shot2 = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
const OUT2 = 'D:/OpenStudy/apps/fastapi-v2/doc/screenshots/47-reader-navigation-0.7.0.png'
fs.writeFileSync(OUT2, Buffer.from(shot2.data, 'base64'))
console.log('saved', OUT2)
ws.close(); process.exit(0)
