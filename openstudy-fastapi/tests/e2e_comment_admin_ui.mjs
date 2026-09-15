/**
 * 后台管理「评论管理」页面 —— 真实浏览器（Chrome Headless + CDP）功能验证
 *
 * 重点验证「修复前是假功能」的部分：
 *   1) 列表以前恒为空（后端 /system/comment/list 缺失 → catch_all 返回 paginate(0,[])）
 *   2) 状态列依赖 status === '0'（后端必须回字符串）
 *   3) 隐藏/显示、删除以前只弹「成功」但数据没动 —— 这里会真的比对页面与库
 *
 * 脚本自己造评论，跑完走接口删除。
 * 用法（Windows 侧 Node 运行；Vite dev server 需已在 3167 运行）：
 *   node tests/e2e_comment_admin_ui.mjs
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(__dirname, 'e2e_comment_admin_ui_result.json')
const SHOTS = path.join(__dirname, '_ui_evidence')
const FRONT = process.env.UI_FRONT || 'http://localhost:3167'
const BACK = process.env.UI_BACK || 'http://127.0.0.1:9101'
const CHROME = process.env.UI_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const DBG = Number(process.env.UI_CDP_PORT || 9336)

const STAMP = String(Date.now()).slice(-6)
const CONTENT_A = `UI校验-评论A-${STAMP}`
const CONTENT_B = `UI校验-评论B-${STAMP}`

const ROWS = []
function T(cid, title, pre, steps, expected, ok, actual) {
  ROWS.push({ cid, module: '评论管理(后台·前端)', title, pre, steps, expected, actual, status: ok ? '通过' : '失败' })
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${cid} ${title} -> ${actual}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function api(path, { method = 'GET', token, body, params } = {}) {
  let url = BACK + path
  if (params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== ''))
    if (qs.toString()) url += '?' + qs.toString()
  }
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  const txt = await res.text()
  try { return JSON.parse(txt) } catch { return { code: res.status, raw: txt.slice(0, 200) } }
}

function httpJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = ''
      res.on('data', (c) => (body += c))
      res.on('end', () => { try { resolve(JSON.parse(body)) } catch (e) { reject(e) } })
    }).on('error', reject)
  })
}
async function waitPort(url, timeout = 15000) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    try { return await httpJson(url) } catch { await sleep(300) }
  }
  throw new Error('CDP 端口未就绪: ' + url)
}

const TABLE_FN = `
  const head = [...document.querySelectorAll('.el-table__header-wrapper thead tr th')]
    .map(th => (th.innerText || '').trim());
  const body = [...document.querySelectorAll('.el-table__body-wrapper tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => (td.innerText || '').trim()));
  return { head, body };
`

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.listeners = []
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
      } else if (msg.method) { this.listeners.forEach((fn) => fn(msg)) }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('CDP 超时: ' + method)) }
      }, 30000)
    })
  }
  on(fn) { this.listeners.push(fn) }
  async evalJs(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(() => { ${expression} })()`, returnByValue: true, awaitPromise: true,
    })
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400))
    return r.result.value
  }
  async waitFor(expression, timeout = 25000, interval = 300) {
    const t0 = Date.now()
    while (Date.now() - t0 < timeout) {
      try { if (await this.evalJs(`return (${expression})`)) return true } catch { /* ignore */ }
      await sleep(interval)
    }
    return false
  }
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true })

  const ad = await api('/quickLogin', { method: 'POST', body: { account: 'admin' } })
  const token = ad?.data?.token
  const u1 = await api('/quickLogin', { method: 'POST', body: { account: 'user1' } })
  const t1 = u1?.data?.token
  if (!token || !t1) throw new Error('登录失败')

  const notes = await api('/system/comment/list', { token, params: { pageNum: 1, pageSize: 50 } })
  const noteId = (notes?.rows || []).length ? notes.rows[notes.rows.length - 1].noteId : null
  if (!noteId) throw new Error('需要至少一条已有评论以取到 noteId')

  const createdIds = []
  const cleanup = async () => {
    if (createdIds.length) {
      await api('/system/comment/' + createdIds.join(','), { method: 'DELETE', token })
    }
  }

  try {
    for (const c of [CONTENT_A, CONTENT_B]) {
      const r = await api('/notes/comment/create', { method: 'POST', token: t1, params: { noteId, content: c } })
      const id = r?.data?.commentId
      if (id) createdIds.push(id)
    }
    console.log(`已造数据：noteId=${noteId} 评论=${createdIds.join(',')}`)

    const userDataDir = path.join(os.tmpdir(), 'os-ui-comment-' + Date.now())
    const child = spawn(CHROME, [
      '--headless=new', '--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox',
      '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
      `--remote-debugging-port=${DBG}`, `--user-data-dir=${userDataDir}`,
      '--window-size=1680,1050', 'about:blank',
    ], { stdio: 'ignore' })

    try {
      await waitPort(`http://127.0.0.1:${DBG}/json/version`)
      const list = await httpJson(`http://127.0.0.1:${DBG}/json/list`)
      const page = list.find((t) => t.type === 'page')
      const ws = new WebSocket(page.webSocketDebuggerUrl)
      await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej) })
      const cdp = new CDP(ws)

      const net = []
      const consoleErrs = []
      cdp.on((msg) => {
        if (msg.method === 'Network.requestWillBeSent') {
          const u = msg.params.request.url
          if (u.includes('/system/comment')) net.push({ url: u, method: msg.params.request.method })
        }
        if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
          consoleErrs.push(msg.params.args.map((a) => a.value || a.description || '').join(' ').slice(0, 300))
        }
        if (msg.method === 'Runtime.exceptionThrown') {
          consoleErrs.push('[exception] ' + JSON.stringify(msg.params.exceptionDetails).slice(0, 300))
        }
      })

      await cdp.send('Page.enable')
      await cdp.send('Runtime.enable')
      await cdp.send('Network.enable')
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false })
      await cdp.send('Network.setCookie', { name: 'Admin-Token', value: token, url: FRONT, path: '/' })

      await cdp.send('Page.navigate', { url: FRONT + '/system/comment' })
      const rendered = await cdp.waitFor(`document.querySelector('.app-container') && document.querySelector('.el-table')`, 30000)
      await sleep(1800)

      const info = await cdp.evalJs(`
        const t = document.body.innerText || '';
        return {
          url: location.href,
          hasTitle: t.includes('评论管理'),
          hasTable: !!document.querySelector('.el-table'),
          rows: document.querySelectorAll('.el-table__body-wrapper tbody tr').length,
        }
      `)
      T('V01', '页面可加载并渲染（无白屏/编译错误）',
        'Vite dev server(3167) 运行中，admin 已登录', 'headless Chrome 打开 /system/comment',
        'URL 停在评论管理路由、页面出现 el-table',
        rendered && info.hasTitle && info.hasTable && info.url.includes('/system/comment'),
        `url=${info.url} 标题=${info.hasTitle} 表格=${info.hasTable}`)

      T('V02', '列表渲染出评论（修复前后端缺接口 → 列表恒为空）',
        '库中存在评论（含本次造的 2 条）', '读取 tbody tr 数量',
        '行数 > 0', info.rows > 0, `行数=${info.rows}`)

      const qf = await cdp.evalJs(`
        return [...document.querySelectorAll('.app-container form.el-form--inline .el-form-item__label')]
          .map(l => (l.innerText || '').trim());
      `)
      const wantLabels = ['笔记ID', '用户名称', '评论内容', '状态', '评论时间']
      const missLabels = wantLabels.filter((l) => !qf.some((x) => x.startsWith(l)))
      T('V03', '查询表单筛选条件齐全',
        '打开列表页', '读取 .el-form--inline 的 label 文本',
        '包含 笔记ID/用户名称/评论内容/状态/评论时间',
        missLabels.length === 0, `缺失=${missLabels.join(',') || '无'}`)

      const t0 = await cdp.evalJs(`${TABLE_FN}`)
      const iStatus = t0.head.findIndex((h) => h === '状态')
      const iContent = t0.head.findIndex((h) => h === '评论内容')
      const statusVals = [...new Set(t0.body.map((r) => r[iStatus]).filter(Boolean))]
      T('V04', '状态列正常渲染（后端 status 必须回字符串 "0"/"1"）',
        '评论默认 status=0', '读取表头定位「状态」列并取值',
        '状态值出现在 {正常, 隐藏} 中（若后端回数字，页面会恒显示「隐藏」）',
        statusVals.length > 0 && statusVals.every((v) => v === '正常' || v === '隐藏'),
        `状态集合=${statusVals.join(',')}`)

      T('V05', '列表包含本次造的测试评论',
        `内容 ${CONTENT_A} / ${CONTENT_B}`, '读取「评论内容」列',
        '两条都在列表中',
        t0.body.some((r) => (r[iContent] || '').includes(CONTENT_A))
        && t0.body.some((r) => (r[iContent] || '').includes(CONTENT_B)),
        `命中A=${t0.body.some((r) => (r[iContent] || '').includes(CONTENT_A))} 命中B=${t0.body.some((r) => (r[iContent] || '').includes(CONTENT_B))}`)

      // ---- 按笔记ID筛选 ----
      await cdp.evalJs(`
        const inp = document.querySelector('.app-container form.el-form--inline input');
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, '${noteId}');
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
      `)
      await sleep(200)
      const netBeforeQ = net.length
      await cdp.evalJs(`
        const btn = [...document.querySelectorAll('.app-container button')].find(b => (b.innerText||'').includes('搜索'));
        btn.click(); return true;
      `)
      await sleep(1800)
      const q = await cdp.evalJs(`${TABLE_FN}`)
      const qReq = net.slice(netBeforeQ).find((r) => r.url.includes('/system/comment/list'))
      T('V06', '按「笔记ID」搜索真正生效',
        `填 笔记ID=${noteId} 后点搜索`, '抓请求 URL + 读表格内容列',
        '请求 URL 含 noteId；列表仍包含本次造的评论',
        !!qReq && /[?&]noteId=/.test(qReq.url)
        && q.body.some((r) => (r[iContent] || '').includes(CONTENT_A)),
        `请求=${qReq ? qReq.url.split('/dev-api')[1] : '未抓到'}`)

      // ---- 查看对话框（.el-dialog__wrapper 是 position:fixed，offsetParent 恒为 null，不能用它判断可见性）----
      const viewClick = await cdp.evalJs(`
        const rows = [...document.querySelectorAll('.el-table__body-wrapper tbody tr')];
        const row = rows.find(tr => (tr.innerText || '').includes('${CONTENT_A}'));
        if (!row) return { ok: false, reason: 'row-not-found' };
        const btn = [...row.querySelectorAll('button')].find(b => (b.innerText || '').trim() === '查看');
        if (!btn) return { ok: false, reason: 'btn-not-found' };
        btn.click();
        return { ok: true };
      `)
      let dlgText = ''
      let dlgVisible = false
      for (let i = 0; i < 20; i++) {
        await sleep(400)
        const st = await cdp.evalJs(`
          const d = document.querySelector('.el-dialog');
          // Element Plus 2.x 没有 .el-dialog__wrapper，且弹层是 position:fixed（offsetParent 恒为 null）
          const vis = !!d && d.getClientRects().length > 0;
          const ta = d ? d.querySelector('textarea') : null;
          return { vis, val: ta ? ta.value : (d ? d.innerText : '') };
        `)
        dlgVisible = st.vis
        dlgText = st.val || ''
        if (dlgVisible && dlgText.includes(CONTENT_A)) break
      }
      T('V07', '点「查看」弹出对话框并回显评论内容',
        `${CONTENT_A} 所在行点「查看」`, '等待 el-dialog__wrapper 显示并读取 textarea 的值',
        '对话框可见且包含该评论内容（修复前后端无接口 → 弹出空白）',
        viewClick.ok && dlgVisible && dlgText.includes(CONTENT_A),
        `点击=${viewClick.ok ? '成功' : viewClick.reason} 可见=${dlgVisible} 内容="${dlgText.slice(0, 40)}"`)
      await cdp.evalJs(`
        const b = [...document.querySelectorAll('.el-dialog .dialog-footer button')].find(x => (x.innerText||'').includes('取'));
        if (b) b.click(); return true;
      `)
      await sleep(600)

      // ---- 通用：点行内按钮 + 确认 + 轮询状态 ----
      const clickRowBtn = (content, label) => cdp.evalJs(`
        const rows = [...document.querySelectorAll('.el-table__body-wrapper tbody tr')];
        const row = rows.find(tr => (tr.innerText || '').includes('${content}'));
        if (!row) return { ok: false, reason: 'row-not-found' };
        const btn = [...row.querySelectorAll('button')].find(b => (b.innerText || '').trim() === '${label}');
        if (!btn) return { ok: false, reason: 'btn-not-found' };
        btn.click();
        return { ok: true };
      `)
      const confirmBox = () => cdp.evalJs(`
        const btns = [...document.querySelectorAll('.el-message-box__btns button')];
        const ok = btns.find(b => (b.innerText || '').trim().includes('确定'));
        if (!ok) return { ok: false, reason: 'confirm-not-found' };
        ok.click();
        return { ok: true };
      `)
      const waitRowStatus = async (content, expected, timeout = 12000) => {
        const begin = Date.now()
        let last = ''
        while (Date.now() - begin < timeout) {
          const t = await cdp.evalJs(`${TABLE_FN}`)
          const ic = t.head.findIndex((h) => h === '评论内容')
          const is = t.head.findIndex((h) => h === '状态')
          const row = t.body.find((r) => (r[ic] || '').includes(content))
          last = row ? (row[is] || '') : '(未找到行)'
          if (last === expected) return { ok: true, status: last }
          await sleep(500)
        }
        return { ok: false, status: last }
      }

      // ---- 隐藏 → 轮询等到状态变为「隐藏」 ----
      const hideClick = await clickRowBtn(CONTENT_A, '隐藏')
      await sleep(600)
      const hideConfirm = await confirmBox()
      const hideRes = await waitRowStatus(CONTENT_A, '隐藏')
      T('V08', '点「隐藏」后该行状态变为「隐藏」（真的改了库）',
        `${CONTENT_A} 所在行点隐藏并确认`, '轮询列表直到状态变为「隐藏」（最多 12s）',
        '点击/确认均成功，且该行状态最终=隐藏（修复前只弹「隐藏成功」，刷新后仍是正常）',
        hideClick.ok && hideConfirm.ok && hideRes.ok,
        `点击=${hideClick.ok ? '成功' : hideClick.reason} 确认=${hideConfirm.ok ? '成功' : hideConfirm.reason} 最终状态=${hideRes.status}`)

      // ---- 显示 → 轮询等到状态恢复「正常」 ----
      const showClick = await clickRowBtn(CONTENT_A, '显示')
      await sleep(600)
      const showConfirm = await confirmBox()
      const showRes = await waitRowStatus(CONTENT_A, '正常')
      T('V09', '点「显示」后该行状态恢复「正常」',
        `${CONTENT_A} 所在行点显示并确认`, '轮询列表直到状态变为「正常」（最多 12s）',
        '点击/确认均成功，且该行状态最终=正常',
        showClick.ok && showConfirm.ok && showRes.ok,
        `点击=${showClick.ok ? '成功' : showClick.reason} 确认=${showConfirm.ok ? '成功' : showConfirm.reason} 最终状态=${showRes.status}`)

      const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
      fs.writeFileSync(path.join(SHOTS, 'comment-admin-list.png'), Buffer.from(shot.data, 'base64'))

      // ---- 删除：走后端，然后刷新确认（页面删除走的是同一个接口）----
      await cdp.evalJs(`
        const rows = [...document.querySelectorAll('.el-table__body-wrapper tbody tr')];
        const row = rows.find(tr => (tr.innerText || '').includes('${CONTENT_B}'));
        const btn = [...row.querySelectorAll('button')].find(b => (b.innerText || '').trim() === '删除');
        if (btn) btn.click();
        return !!btn;
      `)
      await sleep(700)
      await cdp.evalJs(`
        const btns = [...document.querySelectorAll('.el-message-box__btns button')];
        const ok = btns.find(b => (b.innerText || '').trim().includes('确定'));
        if (ok) ok.click();
        return !!ok;
      `)
      await sleep(2000)
      const afterDel = await cdp.evalJs(`${TABLE_FN}`)
      const delGone = !afterDel.body.some((r) => (r[iContent] || '').includes(CONTENT_B))
      const apiAfter = await api('/system/comment/list', { token, params: { content: CONTENT_B, pageNum: 1, pageSize: 10 } })
      T('V10', '点「删除」后评论真的被删除（修复前只弹「删除成功」）',
        `${CONTENT_B} 所在行点删除并确认`, '刷新列表 + 调接口按内容查询',
        '页面不再出现该评论，且接口查询结果为空',
        delGone && (apiAfter?.total === 0),
        `页面已消失=${delGone} 接口total=${apiAfter?.total}`)

      const realErrs = consoleErrs.filter((e) => !/favicon|ResizeObserver|Download the Vue Devtools/i.test(e))
      T('V11', '页面运行期间无 JS 异常',
        '整个交互过程', '监听 Runtime.exceptionThrown 与 console.error',
        '无未捕获异常',
        realErrs.length === 0, realErrs.length ? realErrs.slice(0, 2).join(' | ') : '无')

      console.log('\n网络请求（评论管理）:')
      net.slice(0, 12).forEach((r) => console.log('  ' + r.method + ' ' + r.url.split('/dev-api')[1]))
    } finally {
      try { child.kill() } catch { /* ignore */ }
      await sleep(500)
      try { fs.rmSync(userDataDir, { recursive: true, force: true }) } catch { /* ignore */ }
    }
  } finally {
    await cleanup()
  }

  const passed = ROWS.filter((r) => r.status === '通过').length
  console.log('='.repeat(78))
  console.log(`前端用例总数 ${ROWS.length}，通过 ${passed}，失败 ${ROWS.length - passed}`)
  console.log('='.repeat(78))
  fs.writeFileSync(OUT, JSON.stringify({ module: '评论管理(后台·前端)', createdIds, rows: ROWS }, null, 2), 'utf-8')
  console.log('结果已写入', OUT)
}

main().catch((e) => { console.error('UI 测试失败:', e); process.exit(1) })
