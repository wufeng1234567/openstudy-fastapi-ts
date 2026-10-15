/**
 * 后台管理「斩题管理」页面 —— 真实浏览器（Chrome Headless + CDP）功能验证
 *
 * 目的：验证 前端页面 → 后端接口 的整链路，而不是只看后端接口。
 *   1) 页面能否加载/渲染（有无编译错误、JS 异常）
 *   2) 列表、查询表单、操作按钮是否齐全可用
 *   3) 点「搜索」时前端是否真的把筛选条件发了出去、后端有没有按条件过滤
 *   4) 表格展示列（错误次数/复习次数/最后复习）是否有数据
 *   5) 点「新增」对话框是否正常弹出、表单字段是否齐全
 *
 * 用法（Windows 侧 Node 运行；Vite dev server 需已在 3167 运行）：
 *   node tests/e2e_marked_admin_ui.mjs
 * 产出：同目录 e2e_marked_admin_ui_result.json + _ui_evidence/*.png
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// el-table 有「多级表头」，最后一行 thead 不含 rowspan 的叶子列 →
// 这里按 rowspan/colspan 展开成网格，取最后一行作为列名（与 tbody 的 td 一一对应）
const GRID_FN = `
  const trs = [...document.querySelectorAll('.el-table__header-wrapper thead tr')];
  const grid = [];
  trs.forEach((tr, ri) => {
    grid[ri] = grid[ri] || [];
    let ci = 0;
    [...tr.children].forEach(th => {
      while (grid[ri][ci] !== undefined) ci++;
      const cs = th.colSpan || 1, rs = th.rowSpan || 1;
      const text = (th.innerText || '').trim();
      for (let r = 0; r < rs; r++) for (let c = 0; c < cs; c++) {
        grid[ri + r] = grid[ri + r] || [];
        grid[ri + r][ci + c] = text;
      }
      ci += cs;
    });
  });
  const head = grid[grid.length - 1].map(t => (t === undefined ? '' : t));
  const body = [...document.querySelectorAll('.el-table__body-wrapper tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => (td.innerText || '').trim()));
`

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(__dirname, 'e2e_marked_admin_ui_result.json')
const SHOTS = path.join(__dirname, '_ui_evidence')
const FRONT = process.env.UI_FRONT || 'http://localhost:3167'
const BACK = process.env.UI_BACK || 'http://127.0.0.1:9101'
const CHROME = process.env.UI_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const DBG = Number(process.env.UI_CDP_PORT || 9333)

const ROWS = []
function T(cid, title, pre, steps, expected, ok, actual) {
  ROWS.push({ cid, module: '斩题管理(后台·前端)', title, pre, steps, expected, actual, status: ok ? '通过' : '失败' })
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${cid} ${title} -> ${actual}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function httpJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = ''
      res.on('data', (c) => (body += c))
      res.on('end', () => {
        try { resolve(JSON.parse(body)) } catch (e) { reject(e) }
      })
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

class CDP {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.listeners = []
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
      } else if (msg.method) {
        this.listeners.forEach((fn) => fn(msg))
      }
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
      try { if (await this.evalJs(`return (${expression})`)) return true } catch { /* 页面切换中 */ }
      await sleep(interval)
    }
    return false
  }
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true })

  // ---- 1. 取管理员 token（后端 /quickLogin）----
  const lr = await fetch(BACK + '/quickLogin', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account: 'admin' }),
  }).then((r) => r.json())
  const token = lr?.data?.token
  if (!token) throw new Error('quickLogin 失败: ' + JSON.stringify(lr))
  console.log('admin token 获取成功')

  // ---- 2. 启动 headless Chrome ----
  const userDataDir = path.join(os.tmpdir(), 'os-ui-marked-' + Date.now())
  const child = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox',
    '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
    `--remote-debugging-port=${DBG}`, `--user-data-dir=${userDataDir}`,
    '--window-size=1680,1050', 'about:blank',
  ], { stdio: 'ignore', detached: false })

  let cdp
  try {
    await waitPort(`http://127.0.0.1:${DBG}/json/version`)
    const list = await httpJson(`http://127.0.0.1:${DBG}/json/list`)
    const page = list.find((t) => t.type === 'page')
    const ws = new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej) })
    cdp = new CDP(ws)

    const net = []          // 后端 API 请求记录
    const consoleErrs = []
    cdp.on((msg) => {
      if (msg.method === 'Network.requestWillBeSent') {
        const u = msg.params.request.url
        if (u.includes('/questionMarked/') || u.includes('/dev-api/')) {
          net.push({ url: u, method: msg.params.request.method,
                     body: (msg.params.request.postData || '').slice(0, 300) })
        }
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
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false,
    })
    await cdp.send('Network.setCookie', { name: 'Admin-Token', value: token, url: FRONT, path: '/' })

    // ---- 3. 打开后台斩题管理页 ----
    await cdp.send('Page.navigate', { url: FRONT + '/questionMarked/questionMarked' })
    const rendered = await cdp.waitFor(
      `document.querySelector('.app-container') && document.querySelector('.el-table')`, 30000)
    await sleep(1500)

    const info = await cdp.evalJs(`
      const t = document.body.innerText || '';
      return {
        url: location.href,
        hasTitle: t.includes('斩题管理'),
        hasTable: !!document.querySelector('.el-table'),
        rows: document.querySelectorAll('.el-table__body-wrapper tbody tr').length,
        hasQueryForm: !!document.querySelector('.app-container form.el-form--inline'),
        buttons: [...document.querySelectorAll('.app-container button')].map(b => (b.innerText || '').trim()).filter(Boolean),
      }
    `)
    T('F01', '页面可加载并渲染（无白屏/编译错误）',
      'Vite dev server(3167) 运行中，admin 已登录', 'headless Chrome 打开 /questionMarked/questionMarked',
      'URL 停在斩题管理路由、页面含标题、出现 el-table',
      rendered && info.hasTitle && info.hasTable && info.url.includes('/questionMarked/questionMarked'),
      `url=${info.url} 标题=${info.hasTitle} 表格=${info.hasTable}`)

    T('F02', '列表数据渲染出表格行',
      'admin 名下有斩题记录（演示数据 3 条）', '读取 .el-table__body-wrapper tbody tr 数量',
      '行数 > 0', info.rows > 0, `行数=${info.rows}`)

    const qf = await cdp.evalJs(`
      const labels = [...document.querySelectorAll('.app-container form.el-form--inline .el-form-item__label')]
        .map(l => (l.innerText || '').trim());
      return { labels, hasSearch: !![...document.querySelectorAll('.app-container button')]
        .find(b => (b.innerText || '').includes('搜索')) };
    `)
    const wantLabels = ['用户ID', '题目ID', '所属题库', '斩题类型', '难度等级', '掌握状态', '斩题时间']
    const missLabels = wantLabels.filter((l) => !qf.labels.some((x) => x.startsWith(l)))
    T('F03', '查询表单 7 个筛选条件 + 搜索按钮齐全',
      '打开列表页', '读取 .el-form--inline 的 label 文本',
      '包含 用户ID/题目ID/所属题库/斩题类型/难度等级/掌握状态/斩题时间',
      missLabels.length === 0 && qf.hasSearch, `缺失=${missLabels.join(',') || '无'}`)

    const wantBtns = ['新增', '修改', '删除', '导出']
    const missBtns = wantBtns.filter((b) => !info.buttons.includes(b))
    T('F04', '操作按钮齐全（admin 权限 *:*:* 下 v-hasPermi 放行）',
      'admin 角色 = admin（拥有 *:*:*）', '读取工具栏按钮文本',
      '出现 新增/修改/删除/导出 四个按钮',
      missBtns.length === 0, `缺失=${missBtns.join(',') || '无'}；实际=${info.buttons.join(' ')}`)

    // ---- 4. 表格列读数（错误次数/复习次数/最后复习）----
    // 前置：库中 admin 记录被 _ui_seed_marked.py 塞入非零值（错误次数=5 复习次数=7 最后复习=2026-09-01）
    const cols = await cdp.evalJs(`
      ${GRID_FN}
      return { head, body };
    `)
    const idx = (name) => cols.head.findIndex((h) => h === name)
    const iUser = idx('用户ID')
    const iErr = idx('错误次数')
    const iRev = idx('复习次数')
    const iLast = idx('最后复习')
    const users = cols.body.map((r) => r[iUser]).filter(Boolean)
    T('F05', '表格「用户ID」列显示记录归属',
      '列表 loaded', '按表头网格定位「用户ID」列并逐行取值',
      '每行都有用户ID（admin 视角当前应全为 1）',
      iUser >= 0 && users.length > 0, `表头索引=${iUser} 值=${[...new Set(users)].join(',')}`)

    const errVals = iErr >= 0 ? cols.body.map((r) => r[iErr]) : []
    const revVals = iRev >= 0 ? cols.body.map((r) => r[iRev]) : []
    const lastVals = iLast >= 0 ? cols.body.map((r) => r[iLast]) : []
    const emptyish = (v) => !v || v === '0' || v === '-'
    T('F06', '表格「错误次数/复习次数/最后复习」列展示库中真实值',
      '库中 admin 记录已置为 错误次数=5/复习次数=7/最后复习=2026-09-01',
      '读取这 3 列每行文本',
      '出现 5、7、2026-09-01（接口若丢字段，页面只能显示 0 / -）',
      errVals.some((v) => !emptyish(v)) && revVals.some((v) => !emptyish(v)) && lastVals.some((v) => !emptyish(v)),
      `错误次数=${errVals.join('|')} 复习次数=${revVals.join('|')} 最后复习=${lastVals.join('|')}`)

    // ---- 5. 搜索：前端是否真的发出了 userId 条件，后端是否过滤 ----
    const netBefore = net.length
    await cdp.evalJs(`
      const inp = document.querySelector('.app-container form.el-form--inline input');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(inp, '105');
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    `)
    await sleep(200)
    await cdp.evalJs(`
      const btn = [...document.querySelectorAll('.app-container button')].find(b => (b.innerText||'').includes('搜索'));
      btn.click(); return true;
    `)
    await sleep(2000)
    const searchReqs = net.slice(netBefore).filter((r) => r.url.includes('/questionMarked/questionMarked/list'))
    const sentUserId = searchReqs.some((r) => /[?&]userId=105(&|$)/.test(r.url))
    T('F07', '点击「搜索」后前端确实把 userId=105 发给了后端',
      '在「用户ID」输入框填 105 后点搜索', '抓取 Network 请求 URL',
      '请求 URL 含 userId=105',
      sentUserId, `请求=${searchReqs.map((r) => r.url.split('/dev-api')[1] || r.url).join(' ; ') || '未抓到'}`)

    const after = await cdp.evalJs(`
      ${GRID_FN}
      const iUser = head.findIndex(h => h === '用户ID');
      return { iUser, users: body.map(r => r[iUser]), count: body.length };
    `)
    const usersAfter = [...new Set(after.users.filter(Boolean))]
    T('F08', '搜索「用户ID=105」后列表只剩该用户的记录（筛选真正生效）',
      'user1(105) 有 7 条斩题，admin(1) 有 3 条',
      '点搜索 → 读表格「用户ID」列',
      '表格中出现的用户ID 全部为 105',
      after.count > 0 && usersAfter.length === 1 && usersAfter[0] === '105',
      `行数=${after.count} 出现的用户ID=${usersAfter.join(',') || '无'}`)

    // ---- 6. 新增对话框 ----
    await cdp.evalJs(`
      const btn = [...document.querySelectorAll('.app-container button')].find(b => (b.innerText||'').trim() === '新增');
      btn.click(); return true;
    `)
    const dlgOk = await cdp.waitFor(`document.querySelector('.el-dialog .el-form')`, 8000)
    await sleep(600)
    const dlg = await cdp.evalJs(`
      const d = document.querySelector('.el-dialog');
      if (!d) return { labels: [], visible: false };
      return {
        visible: d.offsetParent !== null,
        title: (d.querySelector('.el-dialog__title')?.innerText || '').trim(),
        labels: [...d.querySelectorAll('.el-form-item__label')].map(l => (l.innerText||'').trim()).filter(Boolean),
        footer: [...d.querySelectorAll('.dialog-footer button')].map(b => (b.innerText||'').trim()),
      };
    `)
    const wantDlg = ['用户ID', '题目ID', '所属题库', '斩题类型', '难度等级', '掌握状态', '错误次数', '复习次数',
      '最后复习时间', '下次复习时间', '斩题备注', '标签']
    const missDlg = wantDlg.filter((l) => !dlg.labels.some((x) => x.startsWith(l)))
    T('F09', '点「新增」弹出对话框且表单字段齐全',
      '列表页点新增', '读取 el-dialog 内 .el-form-item__label',
      '包含 用户ID/题目ID/所属题库/斩题类型/难度等级/掌握状态/错误次数/复习次数/最后复习时间/下次复习时间/斩题备注/标签',
      dlgOk && dlg.visible && missDlg.length === 0,
      `标题=${dlg.title} 缺失=${missDlg.join(',') || '无'} 按钮=${dlg.footer.join('/')}`)

    const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    fs.writeFileSync(path.join(SHOTS, 'marked-admin-dialog.png'), Buffer.from(shot.data, 'base64'))
    await cdp.evalJs(`
      const b = [...document.querySelectorAll('.el-dialog .dialog-footer button')].find(x => (x.innerText||'').includes('取'));
      if (b) b.click(); return true;
    `)
    await sleep(500)
    const shot2 = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    fs.writeFileSync(path.join(SHOTS, 'marked-admin-list.png'), Buffer.from(shot2.data, 'base64'))

    // ---- 7. 导出按钮：筛选条件必须拼在 URL 上（修复 utils/request.download 后）----
    const netBeforeExport = net.length
    await cdp.evalJs(`
      const b = [...document.querySelectorAll('.app-container button')].find(x => (x.innerText||'').trim() === '导出');
      if (b) b.click(); return true;
    `)
    await sleep(2500)
    const expReq = net.slice(netBeforeExport).find((r) => r.url.includes('/questionMarked/questionMarked/export'))
    T('F11', '点「导出」时筛选条件拼在 URL 查询串上（导出按条件过滤）',
      '搜索框里已填 用户ID=105', '点击「导出」并抓取 Network 请求 URL',
      '导出请求 URL 含 userId=105（修复前参数在请求体里，后端 Query 读不到）',
      !!expReq && /[?&]userId=105(&|$)/.test(expReq.url),
      `请求=${expReq ? expReq.url.split('/dev-api')[1] : '未抓到'}`)

    // ---- 8. 无 JS 异常 ----
    const realErrs = consoleErrs.filter((e) => !/favicon|ResizeObserver|Download the Vue Devtools/i.test(e))
    T('F10', '页面运行期间无 JS 异常 / 接口 5xx',
      '整个交互过程', '监听 Runtime.exceptionThrown 与 console.error',
      '无未捕获异常',
      realErrs.length === 0, realErrs.length ? realErrs.slice(0, 2).join(' | ') : '无')

    console.log('\n网络请求（斩题相关）:')
    net.filter((r) => r.url.includes('/questionMarked/')).forEach((r) => console.log('  ' + r.method + ' ' + r.url))
  } finally {
    try { child.kill() } catch { /* ignore */ }
    await sleep(500)
    try { fs.rmSync(userDataDir, { recursive: true, force: true }) } catch { /* ignore */ }
  }

  const passed = ROWS.filter((r) => r.status === '通过').length
  console.log('='.repeat(78))
  console.log(`前端用例总数 ${ROWS.length}，通过 ${passed}，失败 ${ROWS.length - passed}`)
  console.log('='.repeat(78))
  fs.writeFileSync(OUT, JSON.stringify({ module: '斩题管理(后台·前端)', rows: ROWS }, null, 2), 'utf-8')
  console.log('结果已写入', OUT)
}

main().catch((e) => { console.error('UI 测试失败:', e); process.exit(1) })
