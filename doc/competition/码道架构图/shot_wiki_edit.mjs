import fs from 'node:fs'

const OUT_DIR = 'D:/OpenStudy/apps/fastapi-v2/doc/screenshots'
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
const capture = async (name) => {
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const out = `${OUT_DIR}/${name}`
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'))
  console.log('saved', out)
}
await send('Network.enable'); await send('Page.enable')
await send('Network.setCookie', { name: 'Admin-Token', value: token, domain: '127.0.0.1', path: '/' })
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1.5, mobile: false })
await send('Page.navigate', { url: 'http://127.0.0.1:3167/#/front/workspace' })
await sleep(1400); await send('Page.reload', { ignoreCache: true }); await sleep(6500)
console.log(await evaljs(`(() => { const kb=[...document.querySelectorAll('.kbp-kb__name')].find(e=>e.textContent.trim()==='人工智能1'); if(kb) kb.click(); return !!kb; })()`))
await sleep(2500)
console.log(await evaljs(`(() => { const t=[...document.querySelectorAll('.kbp-tab')].find(e=>e.textContent.includes('知识百科')); if(t) t.click(); return !!t; })()`))
await sleep(3500)
console.log(await evaljs(`(() => { const cards=[...document.querySelectorAll('.kw-card')]; return JSON.stringify({count:cards.length,titles:cards.map(e=>e.querySelector('h3')?.textContent.trim())}); })()`))
console.log(await evaljs(`(() => { const cards=[...document.querySelectorAll('.kw-card')]; const card=cards[cards.length-1]; if(card) card.dispatchEvent(new MouseEvent('click',{bubbles:true})); return !!card; })()`))
await sleep(2200)
console.log(await evaljs(`(() => ({drawer:!!document.querySelector('.kw-detail'), actions:[...document.querySelectorAll('.kw-detail__head-actions button')].map(e=>e.textContent.trim())}))()`))
console.log(await evaljs(`(() => { const b=[...document.querySelectorAll('.kw-detail__head-actions button')].find(e=>e.textContent.trim()==='编辑'); if(b) b.click(); return !!b; })()`))
await sleep(1200)
console.log(await evaljs(`(() => ({editor:!!document.querySelector('.kw-editor'), title:document.querySelector('.kw-editor input')?.value||''}))()`))
await capture('43-knowledge-wiki-editor-0.6.0.png')
// close editor and open revisions
await evaljs(`document.querySelector('.kw-editor-dialog .el-dialog__headerbtn')?.click()`)
await sleep(500)
console.log(await evaljs(`(() => { const b=[...document.querySelectorAll('.kw-detail__head-actions button')].find(e=>e.textContent.trim()==='历史版本'); if(b) b.click(); return !!b; })()`))
await sleep(900)
console.log(await evaljs(`(() => ({revisions:document.querySelectorAll('.kw-revision').length}))()`))
await capture('44-knowledge-wiki-revisions-0.6.0.png')
// close dialogs, go gallery
await evaljs(`document.querySelectorAll('.el-dialog__headerbtn').forEach(e=>e.click())`)
await evaljs(`document.querySelector('.kw-detail__close')?.click()`)
await sleep(500)
console.log(await evaljs(`(() => { const t=[...document.querySelectorAll('.kbp-tab')].find(e=>e.textContent.includes('画廊')); if(t) t.click(); return !!t; })()`))
await sleep(3500)
console.log(await evaljs(`(() => { const b=[...document.querySelectorAll('.gallery-scope-tabs button')].find(e=>e.textContent.includes('全部资料')); if(b) b.click(); return !!b; })()`))
await sleep(2500)
console.log(await evaljs(`(() => { const c=document.querySelector('.gallery-card'); if(c) c.click(); return !!c; })()`))
await sleep(1800)
console.log(await evaljs(`(() => { const b=[...document.querySelectorAll('.gallery-detail__actions button')].find(e=>e.textContent.includes('插入知识百科')); if(b) b.click(); return !!b; })()`))
await sleep(1200)
console.log(await evaljs(`(() => ({picker:!!document.querySelector('.gallery-wiki-picker'), pages:document.querySelectorAll('.gallery-wiki-pick').length}))()`))
await capture('45-gallery-insert-wiki-0.6.0.png')
ws.close(); process.exit(0)
