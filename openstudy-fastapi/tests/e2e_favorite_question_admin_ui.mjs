/**
 * 后台管理「题目收藏」页面 —— 真实浏览器（Chrome Headless + CDP）功能验证
 *
 * 覆盖：
 *   1) 页面能否加载/渲染（无编译错误、JS 异常）
 *   2) 查询表单 12 个筛选条件、4 个操作按钮
 *   3) 表格「所属题库」列是否显示真实题库名（旧代码会被题库下拉冲成「未知题库」）
 *   4) 表格「难度评级/错误次数/正确次数/复习次数」列是否有真实数据
 *   5) 新增对话框字段完整性 + 题目ID校验自动填充 + 未校验禁用「确定」
 *   6) 导出请求是否带筛选条件
 *
 * 脚本自己造「user1 的私密题库 + 题目 + 收藏」，跑完自动删库。
 * 用法（Windows 侧 Node 运行；Vite dev server 需已在 3167 运行）：
 *   node tests/e2e_favorite_question_admin_ui.mjs
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(__dirname, 'e2e_favorite_question_admin_ui_result.json')
const SHOTS = path.join(__dirname, '_ui_evidence')
const FRONT = process.env.UI_FRONT || 'http://localhost:3167'
const BACK = process.env.UI_BACK || 'http://127.0.0.1:9101'
const CHROME = process.env.UI_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const DBG = Number(process.env.UI_CDP_PORT || 9335)

const BANK_NAME = '题目收藏UI校验题库-私有'
const NOTES = 'UI校验-收藏备注'
const DIFF = 5, ERR = 7, CORR = 8, REV = 9

const ROWS = []
function T(cid, title, pre, steps, expected, ok, actual) {
  ROWS.push({ cid, module: '题目收藏(后台·前端)', title, pre, steps, expected, actual, status: ok ? '通过' : '失败' })
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

  // ---- 造数据：user1 私密题库 + 题目 + 收藏（带难度/错误/正确/复习次数）----
  const u1 = await api('/quickLogin', { method: 'POST', body: { account: 'user1' } })
  const t1 = u1?.data?.token
  if (!t1) throw new Error('user1 登录失败')
  const bankRes = await api('/questionBank/questionBank', {
    method: 'POST', token: t1, body: { bankName: BANK_NAME, isPublic: 1 },
  })
  const bankId = bankRes?.data?.id
  if (!bankId) throw new Error('建题库失败: ' + JSON.stringify(bankRes).slice(0, 200))

  let cleanupDone = false
  const cleanup = async () => {
    if (cleanupDone) return
    cleanupDone = true
    await api('/questionBank/questionBank/' + bankId, { method: 'DELETE', token: t1 })
  }

  try {
    const qRes = await api('/questionMain/questionMain', {
      method: 'POST', token: t1,
      body: { bankId, questionType: 1, questionText: 'UI校验题目-收藏用',
              options: [{ key: 'A', value: '1' }, { key: 'B', value: '2' }], answer: 'A' },
    })
    const questionId = qRes?.data?.questionId
    if (!questionId) throw new Error('建题目失败: ' + JSON.stringify(qRes).slice(0, 200))

    await api('/favoriteQuestion/favoriteQuestion', { method: 'POST', token: t1, body: { questionId, bankId } })
    const lst = await api('/favoriteQuestion/favoriteQuestion/list', {
      token: t1, params: { questionId, pageNum: 1, pageSize: 10 },
    })
    const favoriteId = lst?.rows?.[0]?.favoriteId
    if (!favoriteId) throw new Error('收藏失败: ' + JSON.stringify(lst).slice(0, 200))
    await api('/favoriteQuestion/favoriteQuestion', {
      method: 'PUT', token: t1,
      body: { favoriteId, notes: NOTES, tags: '重点', difficultyRating: DIFF, errorTimes: ERR,
              correctTimes: CORR, reviewCount: REV, isStarred: 1, favoriteStatus: 1,
              lastReviewTime: '2026-09-07 09:00:00', nextReviewTime: '2026-09-22 09:00:00' },
    })
    console.log(`已造数据：bank=${bankId} question=${questionId} favorite=${favoriteId}（user1 私密题库）`)

    const ad = await api('/quickLogin', { method: 'POST', body: { account: 'admin' } })
    const token = ad?.data?.token
    if (!token) throw new Error('admin 登录失败')

    const userDataDir = path.join(os.tmpdir(), 'os-ui-favq-' + Date.now())
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
          if (u.includes('/favoriteQuestion/') || u.includes('/questionMain/')) {
            net.push({ url: u, method: msg.params.request.method })
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
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1050, deviceScaleFactor: 1, mobile: false })
      await cdp.send('Network.setCookie', { name: 'Admin-Token', value: token, url: FRONT, path: '/' })

      await cdp.send('Page.navigate', { url: FRONT + '/favoriteQuestion/favoriteQuestion' })
      const rendered = await cdp.waitFor(`document.querySelector('.app-container') && document.querySelector('.el-table')`, 30000)
      await sleep(1800)

      const info = await cdp.evalJs(`
        const t = document.body.innerText || '';
        return {
          url: location.href,
          hasTitle: t.includes('题目收藏'),
          hasTable: !!document.querySelector('.el-table'),
          rows: document.querySelectorAll('.el-table__body-wrapper tbody tr').length,
          buttons: [...document.querySelectorAll('.app-container button')].map(b => (b.innerText || '').trim()).filter(Boolean),
        }
      `)
      T('U01', '页面可加载并渲染（无白屏/编译错误）',
        'Vite dev server(3167) 运行中，admin 已登录', 'headless Chrome 打开 /favoriteQuestion/favoriteQuestion',
        'URL 停在题目收藏路由、页面出现 el-table',
        rendered && info.hasTitle && info.hasTable && info.url.includes('/favoriteQuestion/favoriteQuestion'),
        `url=${info.url} 标题=${info.hasTitle} 表格=${info.hasTable}`)

      T('U02', '列表数据渲染出表格行', '库中存在收藏记录', '读取 tbody tr 数量',
        '行数 > 0', info.rows > 0, `行数=${info.rows}`)

      const qf = await cdp.evalJs(`
        const labels = [...document.querySelectorAll('.app-container form.el-form--inline .el-form-item__label')]
          .map(l => (l.innerText || '').trim());
        return { labels };
      `)
      const wantLabels = ['用户ID', '题目ID', '收藏备注', '标签', '难度评级', '错误次数', '正确次数',
        '最后复习时间', '下次复习时间', '复习次数', '是否标星', '收藏状态']
      const missLabels = wantLabels.filter((l) => !qf.labels.some((x) => x.startsWith(l)))
      T('U03', '查询表单 12 个筛选条件齐全',
        '打开列表页', '读取 .el-form--inline 的 label 文本',
        '包含用户ID/题目ID/收藏备注/标签/难度评级/错误次数/正确次数/最后复习时间/下次复习时间/复习次数/是否标星/收藏状态',
        missLabels.length === 0, `缺失=${missLabels.join(',') || '无'}`)

      const wantBtns = ['新增', '修改', '删除', '导出']
      const missBtns = wantBtns.filter((b) => !info.buttons.includes(b))
      T('U04', '操作按钮齐全（admin 权限 *:*:* 下 v-hasPermi 放行）',
        'admin 角色 = admin', '读取工具栏按钮文本',
        '出现 新增/修改/删除/导出',
        missBtns.length === 0, `缺失=${missBtns.join(',') || '无'}`)

      // 搜索 userId=105 后读表格
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

      const cols = await cdp.evalJs(`${GRID_FN} return { head, body };`)
      const idx = (name) => cols.head.findIndex((h) => h === name)
      const pick = (name) => { const i = idx(name); return i < 0 ? [] : cols.body.map((r) => r[i]) }
      const users = pick('用户ID')
      const banks = pick('所属题库')
      const diffs = pick('难度评级')
      const errs = pick('错误次数')
      const corrs = pick('正确次数')
      const revs = pick('复习次数')

      T('U05', '搜索「用户ID=105」后列表只剩该用户的记录',
        'user1 有收藏记录（含本次造的私密题库题目）', '填 用户ID=105 → 点搜索 → 读表格',
        '每行用户ID 均为 105，且行数 > 0',
        users.length > 0 && users.every((u) => u === '105'),
        `行数=${users.length} 用户ID=${[...new Set(users)].join(',')}`)

      T('U06', '表格「所属题库」列显示真实题库名（不被题库下拉冲成"未知题库"）',
        `user1 的私密题库《${BANK_NAME}》不在 admin 的题库下拉里`, '读取表格 所属题库 列',
        `出现《${BANK_NAME}》，且不出现「未知题库」`,
        banks.includes(BANK_NAME) && !banks.includes('未知题库'),
        `名称=${[...new Set(banks)].slice(0, 5).join(' | ')}`)

      T('U07', '表格「难度评级 / 错误次数 / 正确次数 / 复习次数」列显示库中真实值',
        `该收藏 difficultyRating=${DIFF} errorTimes=${ERR} correctTimes=${CORR} reviewCount=${REV}`,
        '读取这 4 列文本',
        `出现 ${DIFF}星、${ERR}、${CORR}、${REV}（接口漏字段时这些列恒为 0/空）`,
        diffs.some((v) => v.includes(String(DIFF))) && errs.includes(String(ERR))
        && corrs.includes(String(CORR)) && revs.includes(String(REV)),
        `评级=${diffs.join('|').slice(0, 40)} 错=${errs.join('|')} 对=${corrs.join('|')} 复习=${revs.join('|')}`)

      await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
        .then((s) => fs.writeFileSync(path.join(SHOTS, 'favquestion-admin-list.png'), Buffer.from(s.data, 'base64')))

      // ---- 新增对话框 ----
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
        };
      `)
      const wantDlg = ['用户ID', '题目ID', '所属题库', '收藏备注', '标签', '难度评级', '错误次数',
        '正确次数', '最后复习时间', '下次复习时间', '复习次数', '是否标星', '收藏状态']
      const missDlg = wantDlg.filter((l) => !dlg.labels.some((x) => x.startsWith(l)))
      T('U08', '点「新增」弹出对话框且表单字段齐全',
        '列表页点新增', '读取 el-dialog 内 .el-form-item__label',
        '包含 13 个表单字段（与 index.vue 一致）',
        dlgOk && dlg.visible && missDlg.length === 0,
        `标题=${dlg.title} 缺失=${missDlg.join(',') || '无'}`)

      // ---- 填题目ID → 校验 → 自动填充题库名；并检查「确定」禁用逻辑 ----
      const readConfirm = `
        const btns = [...document.querySelectorAll('.el-dialog .dialog-footer button')];
        const ok = btns.find(b => (b.innerText || '').replace(/\\s/g, '') === '确定');
        return ok ? ok.disabled : null;
      `
      const confirmDisabledBefore = await cdp.evalJs(readConfirm)
      const focusRes = await cdp.evalJs(`
        const items = [...document.querySelectorAll('.el-dialog .el-form-item')];
        const item = items.find(i => ((i.querySelector('.el-form-item__label') || {}).innerText || '').trim().startsWith('题目ID'));
        if (!item) return { ok: false };
        const inp = item.querySelector('input');
        if (!inp) return { ok: false };
        inp.focus();
        return { ok: document.activeElement === inp };
      `)
      const netBefore = net.length
      await cdp.send('Input.insertText', { text: String(questionId) })
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
      await sleep(2200)
      const checked = await cdp.evalJs(`
        const items = [...document.querySelectorAll('.el-dialog .el-form-item')];
        const item = items.find(i => ((i.querySelector('.el-form-item__label') || {}).innerText || '').trim().startsWith('题目ID'));
        const bankItem = items.find(i => ((i.querySelector('.el-form-item__label') || {}).innerText || '').trim().startsWith('所属题库'));
        return {
          typed: item ? item.querySelector('input').value : '',
          hint: item ? (item.innerText || '').replace(/题目ID/g, '').trim() : '',
          bankText: bankItem ? (bankItem.innerText || '') : '',
        };
      `)
      const checkReqs = net.slice(netBefore).filter((r) => r.url.includes('/favoriteQuestion/favoriteQuestion/check/'))
      T('U09', '对话框填题目ID后校验通过并自动填充所属题库（不再误报"题目ID不存在"）',
        `输入存在的题目ID=${questionId}（《${BANK_NAME}》）后按 Tab 失焦`,
        '读取校验提示 / 所属题库区域 / check 请求',
        '发出 check 请求；提示不含「不存在」；所属题库显示真实题库名',
        focusRes.ok && checked.typed === String(questionId) && checkReqs.length > 0
        && checked.bankText.includes(BANK_NAME) && !checked.hint.includes('不存在'),
        `聚焦=${focusRes.ok} check请求=${checkReqs.length} 所属题库="${checked.bankText.replace(/\\s+/g, ' ').slice(0, 50)}"`)

      const confirmDisabledAfter = await cdp.evalJs(readConfirm)
      T('U10', '未通过题目ID校验时禁用「确定」（不再"报错也照样入库"）',
        '新增对话框：校验前 / 校验通过后 分别读取「确定」按钮 disabled',
        '读取 .dialog-footer 中「确定」按钮的 disabled 属性',
        '校验前 disabled=true；校验通过后 disabled=false',
        confirmDisabledBefore === true && confirmDisabledAfter === false,
        `校验前=${confirmDisabledBefore} 校验后=${confirmDisabledAfter}`)

      const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
      fs.writeFileSync(path.join(SHOTS, 'favquestion-admin-dialog.png'), Buffer.from(shot.data, 'base64'))
      await cdp.evalJs(`
        const b = [...document.querySelectorAll('.el-dialog .dialog-footer button')].find(x => (x.innerText||'').includes('取'));
        if (b) b.click(); return true;
      `)
      await sleep(500)

      // ---- 导出 ----
      const before = net.length
      await cdp.evalJs(`
        const b = [...document.querySelectorAll('.app-container button')].find(x => (x.innerText||'').trim() === '导出');
        if (b) b.click(); return true;
      `)
      await sleep(2500)
      const expReq = net.slice(before).find((r) => r.url.includes('/favoriteQuestion/favoriteQuestion/export'))
      T('U11', '点「导出」调用后端导出接口且筛选条件拼在 URL 上',
        '搜索框已填 用户ID=105', '点「导出」并抓取 Network 请求 URL',
        'POST /favoriteQuestion/favoriteQuestion/export 且 URL 含 userId=105',
        !!expReq && /[?&]userId=105(&|$)/.test(expReq.url),
        `请求=${expReq ? expReq.url.split('/dev-api')[1] : '未抓到'}`)

      const realErrs = consoleErrs.filter((e) => !/favicon|ResizeObserver|Download the Vue Devtools|处理后的列表数据/i.test(e))
      T('U12', '页面运行期间无 JS 异常',
        '整个交互过程', '监听 Runtime.exceptionThrown 与 console.error',
        '无未捕获异常',
        realErrs.length === 0, realErrs.length ? realErrs.slice(0, 2).join(' | ') : '无')

      console.log('\n网络请求（题目收藏相关）:')
      net.forEach((r) => console.log('  ' + r.method + ' ' + r.url.split('/dev-api')[1]))
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
  fs.writeFileSync(OUT, JSON.stringify({ module: '题目收藏(后台·前端)', rows: ROWS }, null, 2), 'utf-8')
  console.log('结果已写入', OUT)
}

main().catch((e) => { console.error('UI 测试失败:', e); process.exit(1) })
