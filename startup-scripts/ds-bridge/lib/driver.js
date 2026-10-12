// driver.js — 免扩展 DS 网页桥核心驱动（原型）
//
// 借鉴 dsh-web-bridge/lib/browser-driver.js 的机制，精简为原型所需：
//   1. playwright-core 启动系统 Edge 的**持久化上下文**（登录态存磁盘 profile）
//      — 首登 headed（用户手登），之后 headless。
//   2. addInitScript 注入「劫持页面自身 fetch/XHR」的捕获脚本：
//      命中的 POST 响应 `body.tee()`，分片经 window.__wcChunk 回吐。
//   3. exposeBinding('__wcChunk') 把分片送回 Node。
//   4. DOM 自动化：填 textarea.ds-scroll-area → 点发送按钮 → 等 SSE → 解码。
//
// 站点契约（来自 dsh providers.js 的实测结论）：
//   输入框   textarea.ds-scroll-area
//   发送按钮  div[role='button']:has(path[d^='M8.3125'])
//   停止按钮  div[role='button']:has(path[d^='M2 4.88'])
//   完成端点  /api/v0/chat/completion
//   登录判定  有 textarea.ds-scroll-area = 已登录；游客页停在 /sign_in

import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { DeepSeekStreamDecoder } from './decoder.js';

export const DS_ORIGIN = 'https://chat.deepseek.com';
/** 默认 profile 目录（登录态持久化处） */
export const DEFAULT_PROFILE_DIR = path.join(os.homedir(), '.openstudy', 'ds-edge-profile');

const SEL = {
  input: 'textarea.ds-scroll-area',
  sendButton: "div[role='button']:has(path[d^='M8.3125'])",
  stopButton: "div[role='button']:has(path[d^='M2 4.88'])",
  completionPath: '/api/v0/chat/completion',
  // 文件上传入口（隐藏的 input[type=file]），来自 dsh providers.js 的 DS 契约
  attach: "input[type='file']",
  // 「深度思考」开关：DS 底部的 ds-toggle-button，文本「深度思考」。
  //   开 = aria-pressed="true" 且 class 带 `--selected`；关 = aria-pressed="false"。
  deepThink: "div.ds-toggle-button:has-text('深度思考')",
};

/** 解析系统 Edge / Chrome 可执行文件 */
export function resolveBrowserPath() {
  const candidates =
    process.platform === 'win32'
      ? [
          'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
          'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
          'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
          'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ]
      : [
          '/usr/bin/microsoft-edge',
          '/usr/bin/google-chrome',
          '/usr/bin/chromium',
        ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

/**
 * 捕获脚本：包装 fetch / XHR，对命中 completionPath 的 POST 响应 tee 出分片，
 * 经 window.__wcChunk(id, phase, text) 回吐给 Node（exposeBinding）。
 * 带自愈：站点埋点 SDK 可能把 fetch 还原成原生引用，每 500ms 重装一次。
 */
function captureInit(completionPath) {
  return `
(function () {
  const TARGET = ${JSON.stringify(completionPath)};
  if (window.__wcCaptureInstalled) { try { install(); } catch {} return; }
  window.__wcCaptureInstalled = true;
  const hit = (u) => String(u || '').includes(TARGET);
  const emit = (id, phase, text) => { try { window.__wcChunk(id, phase, text || ''); } catch {} };
  const newId = () => 'cap-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  function install() {
    if (!(window.fetch && window.fetch.__wcCap)) {
      const origFetch = window.fetch ? window.fetch.bind(window) : null;
      if (origFetch) {
        const wrapped = async function (input, init) {
          const resp = await origFetch(input, init);
          try {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            const method = String((init && init.method) || 'GET').toUpperCase();
            if (method === 'POST' && hit(url) && resp.ok && resp.body) {
              const id = newId();
              emit(id, 'start', '');
              const [forPage, forCapture] = resp.body.tee();
              const reader = forCapture.getReader();
              const dec = new TextDecoder();
              (async () => {
                try {
                  for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    emit(id, 'chunk', dec.decode(value, { stream: true }));
                  }
                } catch {}
                emit(id, 'end', '');
              })();
              return new Response(forPage, { status: resp.status, statusText: resp.statusText, headers: resp.headers });
            }
          } catch {}
          return resp;
        };
        wrapped.__wcCap = true;
        window.fetch = wrapped;
      }
    }
    if (!(XMLHttpRequest.prototype.send && XMLHttpRequest.prototype.send.__wcCap)) {
      const origOpen = XMLHttpRequest.prototype.open;
      const origSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (method, url) {
        try { this.__wcInfo = { method: String(method || '').toUpperCase(), url: String(url || '') }; } catch {}
        return origOpen.apply(this, arguments);
      };
      const wrappedSend = function () {
        const info = this.__wcInfo;
        if (info && info.method === 'POST' && hit(info.url)) {
          const id = newId();
          let lastLen = 0;
          const drain = () => {
            try {
              const t = typeof this.responseText === 'string' ? this.responseText : '';
              if (t.length > lastLen) { emit(id, 'chunk', t.slice(lastLen)); lastLen = t.length; }
            } catch {}
          };
          const timer = setInterval(drain, 30);
          emit(id, 'start', '');
          this.addEventListener('loadend', () => { clearInterval(timer); drain(); emit(id, 'end', ''); });
        }
        return origSend.apply(this, arguments);
      };
      wrappedSend.__wcCap = true;
      XMLHttpRequest.prototype.send = wrappedSend;
    }
  }
  install();
  setInterval(() => { try { install(); } catch {} }, 500);
})();
`;
}

export function createDriver(options = {}) {
  const profileDir = options.profileDir || DEFAULT_PROFILE_DIR;
  const executablePath = options.executablePath || resolveBrowserPath();
  // 启动时的**默认**模式（关窗后复位到它）。调试时 showWindow 会临时改成有头，
  // 但那只是「临时」——关上窗口即回到这个默认值。
  const defaultHeadless = options.headless !== false;
  // 当前模式（可变）
  let headless = defaultHeadless;
  const log = options.log || (() => {});
  const completionPath = options.completionPath || SEL.completionPath;

  let ctx = null;
  let page = null;
  let busy = false;
  // 正在进行的这一轮：解码器 + 完成 Promise
  let active = null;

  function onCapture({ captureId, phase, text }) {
    if (process.env.DS_SSE_DEBUG) {
      try {
        if (phase === 'chunk') fs.appendFileSync(process.env.DS_SSE_DEBUG, text);
        else if (phase === 'start') fs.appendFileSync(process.env.DS_SSE_DEBUG, `\n#### CAPTURE START ${captureId} ####\n`);
        else if (phase === 'end') fs.appendFileSync(process.env.DS_SSE_DEBUG, `\n#### CAPTURE END ${captureId} ####\n`);
      } catch {}
    }
    // ⚠️ 同一个 completion 请求会被**捕获两次**（fetch + XHR 两套包装都命中，真机实测
    //    2026-10-12：一轮里出现两个 cap-xxxx，其中一股可能**完全没有数据**）。
    //    若两股都喂进解码器 → 每个增量处理两遍 → 正文重复、片段错乱。
    //    处理：锁到**第一条真正带数据的 chunk** 所属的那一股；其余整股忽略。
    if (phase === 'chunk') {
      if (!active) return;
      if (!active.captureId) active.captureId = captureId; // 首个有数据的股
      if (captureId !== active.captureId) return;          // 别的股 → 丢弃
      active.decoder.push(text);
    }
    if (phase === 'end') {
      // 只认「本轮锁定股」的结束；若还没锁定（两股都没数据）→ 也结束，避免干等超时。
      if (!active) return;
      if (active.captureId) {
        if (captureId === active.captureId) active.settle('end');
      } else {
        active.settle('end');
      }
    }
  }

  async function launch({ headless: hl } = {}) {
    if (!executablePath) throw new Error('未找到受支持的浏览器（Edge / Chrome）。');
    if (hl !== undefined) headless = hl;
    fs.mkdirSync(profileDir, { recursive: true });
    ctx = await chromium.launchPersistentContext(profileDir, {
      executablePath,
      headless: hl !== undefined ? hl : headless,
      args: ['--no-first-run', '--no-default-browser-check', '--disable-blink-features=AutomationControlled'],
      viewport: { width: 640, height: 900 },
    });
    // 开干净新页（不复用恢复页，避免捕获绑定缺失）
    const stale = ctx.pages();
    page = await ctx.newPage();
    for (const s of stale) { try { await s.close(); } catch {} }
    // 上下文被关掉（用户手动关窗 / Edge 退出）：
    //   · 清空 ctx/page，让下次 ensure() 重新拉起；
    //   · **把模式复位成「启动时的默认」**——调试时临时切到有头，关掉后不应一直有头，
    //     否则以后每一轮都会再弹一个可见窗口（用户 2026-10-12 报）。
    ctx.on('close', () => {
      ctx = null;
      page = null;
      headless = defaultHeadless;
    });
    await installPage();
    log(`launched (${headless ? 'headless' : 'headed'}) profile=${profileDir}`);
  }

  async function installPage() {
    const p = page;
    p.on('close', () => { if (page === p) page = null; });
    await p.exposeBinding('__wcChunk', (source, captureId, phase, text) => {
      onCapture({ captureId, phase, text });
    }).catch(() => {});
    const init = captureInit(completionPath);
    await p.addInitScript(init);
    try { await p.evaluate(init); } catch {}
  }

  async function ensure() {
    if (ctx && page && !page.isClosed()) return;
    // 用户可能刚关掉有头窗口：Edge 退出后 profile 的 SingletonLock 未必立刻释放，
    // 立刻重开偶尔会失败。给足重试（最多 10 次 / 每次 1s = 10s），覆盖浏览器优雅退出耗时。
    let lastErr = null;
    for (let i = 0; i < 10; i++) {
      try {
        await launch();
        // 启动成功但页面可能还没就绪：等输入框或超时（不计失败）
        return;
      } catch (e) {
        lastErr = e;
        log(`ensure 启动失败(第 ${i + 1}/10 次): ${e.message}`);
        // 上一次可能残留半开的上下文，清掉再试，避免 profile 被自身锁住
        try { await ctx?.close(); } catch {}
        ctx = null; page = null;
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    throw lastErr || new Error('浏览器启动失败');
  }

  /** 打开 DS 首页并判定登录态 */
  async function checkLogin() {
    await ensure();
    if (!page || page.isClosed()) {
      return { loggedIn: false, url: '', hasInput: 0, onSignIn: false, closed: true };
    }
    // ⚠️ 冷启动 / 浏览器刚被关后重开时，DS 是 SPA：导航完 domcontentloaded 后
    //    输入框要等 JS 水合才出现（可能 2~8s）。只等 1.5s 会把「其实已登录」误判成未登录
    //    （用户 2026-10-12：关窗后再发 → 报 NEED_LOGIN）。这里**轮询等待**输入框，最多 ~20s。
    if (!page.url().startsWith(DS_ORIGIN)) {
      await page.goto(DS_ORIGIN, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
    }
    let hasInput = 0;
    const deadline = Date.now() + 20000;
    for (;;) {
      if (!page || page.isClosed()) {
        return { loggedIn: false, url: '', hasInput: 0, onSignIn: false, closed: true };
      }
      const url = page.url();
      // 明确停在登录页 → 真未登录，立即返回
      if (url.includes('/sign_in')) {
        return { loggedIn: false, url, hasInput: 0, onSignIn: true };
      }
      hasInput = await page.locator(SEL.input).count().catch(() => 0);
      if (hasInput > 0) break;
      if (Date.now() > deadline) break;
      await page.waitForTimeout(500);
    }
    if (!page || page.isClosed()) {
      return { loggedIn: false, url: '', hasInput: 0, onSignIn: false, closed: true };
    }
    const url = page.url();
    const onSignIn = url.includes('/sign_in');
    return { loggedIn: hasInput > 0 && !onSignIn, url, hasInput, onSignIn };
  }

  // ============================================================
  // 附件上传（**照抄 dsh-web-bridge/lib/browser-driver.js 的契约**）
  // ------------------------------------------------------------
  // dsh 的核心纪律（逐条照搬，别自己发挥）：
  //   1. 图片证据 = **类名清单**（`img[src^='blob:']` 等），不等文件名；
  //   2. 文件证据 = **刚上传的文件名出现在页面上**（`filenameEvidence`，
  //      不猜类名，因为 DS 用构建期哈希类名，猜不着）；
  //   3. 两者都是**轮询等待**（图片 15s / 文件 20s），命中才放行；
  //   4. 失败必须带**现场**（候选选择器命中数 + DOM 片段），不许只丢一个错误码；
  //   5. 图片有数量上限（DS 的 maxImagesPerMessage，拿不到退回 6）。
  // ============================================================

  //: 附件预览候选选择器（dsh 原文，不新增任何类名字面量）
  const ATTACH_PREVIEW_FALLBACK = [
    "img[src^='blob:']",
    "[class*='attachment']",
    "[class*='Attachment']",
    "[class*='file-card']",
    "[class*='fileCard']",
    "[class*='upload-item']",
    "[class*='uploadItem']",
    "[data-testid*='attachment']",
    "[data-testid*='file']",
  ];

  /** 「刚上传的文件名出现在页面上」——不猜类名的确认判据（dsh filenameEvidence 原文） */
  async function filenameEvidence(name) {
    const target = String(name || '');
    if (!target) return null;
    return page.evaluate(({ NAME, MAX }) => {
      const hit = [...document.querySelectorAll('body *')].filter((el) => {
        const tag = el.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'INPUT' || tag === 'TEXTAREA') return false;
        const t = (el.textContent || '').trim();
        return t.includes(NAME) && t.length <= MAX;
      });
      if (!hit.length) return null;
      const deep = hit.filter((el) => !hit.some((o) => o !== el && el.contains(o)));
      const node = deep[0] || hit[0];
      return { tag: node.tagName.toLowerCase(), cls: String(node.getAttribute('class') || '').slice(0, 120), snippet: node.outerHTML.replace(/\s+/g, ' ').trim().slice(0, 200) };
    }, { NAME: target, MAX: target.length + 80 }).catch(() => null);
  }

  /** 轮询等待附件出现（dsh waitForAttachment 原文）。`name` 传了才启用文件名证据（文件轮）。 */
  async function waitForAttachment(timeoutMs, { name = null } = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      for (const sel of ATTACH_PREVIEW_FALLBACK) {
        try {
          const loc = page.locator(sel).first();
          if ((await loc.count()) && (await loc.isVisible().catch(() => false))) return sel;
        } catch { /* 选择器语法/页面转场：试下一个 */ }
      }
      if (name) {
        const hit = await filenameEvidence(name);
        if (hit) return 'text:' + name;
      }
      if (Date.now() >= deadline) return null;
      await page.waitForTimeout(250);
    }
  }

  /** 失败现场（dsh attachEvidenceDiag 原文）：候选选择器命中数 + 文件名命中 + DOM 片段 */
  async function attachEvidenceDiag(name) {
    return page.evaluate(({ NAME, sels, inputSel, MAX }) => {
      const pick = (sel) => { try { return [...document.querySelectorAll(sel)]; } catch { return []; } };
      const visible = (el) => Boolean(el.offsetWidth || el.offsetHeight || el.getClientRects?.().length);
      const candidates = (sels || []).map((sel) => {
        const els = pick(sel);
        return { sel, count: els.length, visible: els.filter(visible).length };
      });
      const hits = [...document.querySelectorAll('body *')].filter((el) => {
        const tag = el.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'INPUT' || tag === 'TEXTAREA') return false;
        const t = (el.textContent || '').trim();
        return NAME && t.includes(NAME) && t.length <= MAX;
      });
      const deep = hits.filter((el) => !hits.some((o) => o !== el && el.contains(o)));
      const node = deep[0] || hits[0] || null;
      let near = null;
      const input = pick(inputSel)[0] || null;
      let box = input;
      for (let i = 0; i < 2 && box?.parentElement; i += 1) box = box.parentElement;
      if (box) near = box.outerHTML.replace(/\s+/g, ' ').trim().slice(0, MAX);
      return {
        candidates,
        nameHit: node ? { tag: node.tagName.toLowerCase(), cls: String(node.getAttribute('class') || '').slice(0, 120) } : null,
        domSnippet: node ? node.outerHTML.replace(/\s+/g, ' ').trim().slice(0, MAX) : near,
      };
    }, { NAME: String(name || ''), sels: ATTACH_PREVIEW_FALLBACK, inputSel: SEL.attach, MAX: 200 })
      .catch((e) => ({ error: String(e?.message || e).slice(0, 120), candidates: [], nameHit: null, domSnippet: null }));
  }

  /** 上传图片附件（dsh uploadImages 逻辑）：证据 = 类名清单；超时 15s。 */
  async function uploadImages(files, { timeoutMs = 15000, maxImages = 6 } = {}) {
    log(`[attach] 图片轮：${files.length} 张（上限 ${maxImages}）`);
    const fi = page.locator(SEL.attach).first();
    if (!(await fi.count())) {
      const err = new Error('ATTACH_UNAVAILABLE: 页面没有可用的文件上传入口');
      err.code = 'ATTACH_UNAVAILABLE';
      throw err;
    }
    const payloads = files.slice(0, maxImages).map((f) => ({
      name: String(f.name || 'image.png').replace(/[\\/:*?"<>|]/g, '_').slice(0, 120) || 'image.png',
      mimeType: String(f.mimeType || f.contentType || 'image/png'),
      buffer: Buffer.from(String(f.base64 || f.data || ''), 'base64'),
    }));
    await fi.setInputFiles(payloads, { timeout: 15000 });
    const hit = await waitForAttachment(timeoutMs); // 图片轮：不传 name（只认类名）
    if (!hit) {
      const diag = await attachEvidenceDiag(null);
      const err = new Error(
        `ATTACH_NOT_CONFIRMED: 已选择 ${payloads.length} 张图片，但 ${Math.round(timeoutMs / 1000)}s 内页面上没有出现附件 — 现场：${JSON.stringify(diag.candidates)}`
      );
      err.code = 'ATTACH_NOT_CONFIRMED';
      err.attachDiag = diag;
      throw err;
    }
    log(`[attach] 图片证据命中：${hit}`);
    return { attached: payloads.length, evidence: hit };
  }

  /** 上传一个文件附件（dsh uploadTextAttachment 逻辑）：证据 = 文件名出现在页面上；超时 20s。 */
  async function uploadFile(f, { timeoutMs = 20000 } = {}) {
    const name = String(f.name || 'file').replace(/[\\/:*?"<>|]/g, '_').slice(0, 120) || 'file';
    log(`[attach] 文件轮：${name}（${Math.round((f.base64 || '').length / 1024)}KB b64）`);
    const fi = page.locator(SEL.attach).first();
    if (!(await fi.count())) {
      const err = new Error('ATTACH_UNAVAILABLE: 页面没有可用的文件上传入口');
      err.code = 'ATTACH_UNAVAILABLE';
      throw err;
    }
    await fi.setInputFiles([{
      name,
      mimeType: String(f.mimeType || f.type || 'application/octet-stream'),
      buffer: Buffer.from(String(f.base64 || ''), 'base64'),
    }], { timeout: 15000 });
    const hit = await waitForAttachment(timeoutMs, { name });
    if (!hit) {
      const diag = await attachEvidenceDiag(name);
      const err = new Error(
        `ATTACH_NOT_CONFIRMED: 已选择附件 ${name}，但 ${Math.round(timeoutMs / 1000)}s 内页面上没有出现附件${diag?.domSnippet ? ' — 现场 DOM：' + diag.domSnippet : ''}`
      );
      err.code = 'ATTACH_NOT_CONFIRMED';
      err.attachDiag = diag;
      throw err;
    }
    log(`[attach] 文件证据命中：${hit}`);
    return { attached: 1, evidence: hit };
  }

  /**
   * 上传本轮全部附件：**图片走 uploadImages（一坨）**，**文件逐个走 uploadFile**。
   * 与 dsh 一致：图片和文件是两种证据，绝不混为一谈。
   */
  async function uploadAttachments(attachments, { maxImages = 6 } = {}) {
    const t0 = Date.now();
    const step = (m) => log(`[attach] +${((Date.now() - t0) / 1000).toFixed(1)}s ${m}`);
    const images = attachments.filter((a) => String(a.mimeType || a.type || '').toLowerCase().startsWith('image/'));
    const files = attachments.filter((a) => !String(a.mimeType || a.type || '').toLowerCase().startsWith('image/'));
    step(`拆分：图片 ${images.length} 张，文件 ${files.length} 个`);
    let attached = 0;
    if (images.length) { const r = await uploadImages(images, { maxImages }); attached += r.attached; }
    for (const f of files) { const r = await uploadFile(f); attached += r.attached; }
    step(`全部完成：共 ${attached} 个附件`);
    return { attached };
  }

  /**
   * 确保 DS 网页的「深度思考」开关处于**开启**状态（发送前调用）。
   * 契约（实测自 DS 页面）：
   *   div.ds-toggle-button（文本「深度思考」）开 = aria-pressed="true" + class 带 `--selected`；
   *   关 = aria-pressed="false"。
   * 找不到开关时**不报错**（老页面/改版），直接放行，避免拖垮整轮。
   * @returns {{found:boolean, on:boolean, toggled:boolean}}
   */
  async function ensureDeepThink() {
    const node = page.locator(SEL.deepThink).first();
    const cnt = await node.count().catch(() => 0);
    if (!cnt) return { found: false, on: false, toggled: false };
    const readOn = async () => {
      const pressed = await node.getAttribute('aria-pressed').catch(() => null);
      if (pressed !== null) return pressed === 'true';
      const cls = (await node.getAttribute('class').catch(() => '')) || '';
      return /--selected/.test(cls);
    };
    let on = await readOn();
    if (on) return { found: true, on: true, toggled: false };
    // 未开 → 点一下
    try {
      await node.click({ timeout: 3000 });
      await page.waitForTimeout(300);
      on = await readOn();
    } catch {}
    return { found: true, on, toggled: on };
  }

  /**
   * 发送一条消息并等待回复。
   * @param {string} message 正文（可为空：只发附件）
   * @param {{timeout?:number, onDelta?:Function, onThink?:Function,
   *          attachments?: Array<{name,mimeType,base64}>}} opts
   * @returns {{text, thinking, status, complete}}
   */
  async function chat(message, { timeout = 180000, onDelta, onThink, attachments = [], asAttachment = false } = {}) {
    if (busy) throw new Error('驱动忙：上一轮尚未结束');
    busy = true;
    const t0 = Date.now();
    const step = (label) => log(`[turn] +${((Date.now() - t0) / 1000).toFixed(1)}s ${label}`);
    try {
      step('ensure 浏览器就绪…');
      await ensure();
      step(`ensure 完成，url=${page ? page.url() : '(null)'}`);
      if (!page.url().startsWith(DS_ORIGIN)) {
        step('导航到 chat.deepseek.com…');
        await page.goto(DS_ORIGIN, { waitUntil: 'domcontentloaded', timeout: 45000 });
      }
      step('检查登录态…');
      const login = await checkLogin();
      step(`登录态=${login.loggedIn}`);
      if (!login.loggedIn) {
        const err = new Error('NEED_LOGIN: DeepSeek 未登录');
        err.code = 'NEED_LOGIN';
        throw err;
      }
      const input = page.locator(SEL.input).first();
      step('等待输入框…');
      await input.waitFor({ timeout: 20000 });
      step('输入框就绪');

      // 发送前先确保「深度思考」开关是**开启**的（用户 2026-10-12 要求默认开启）。
      step('检查深度思考开关…');
      const dt = await ensureDeepThink().catch((e) => ({ found: false, on: false, toggled: false, error: e.message }));
      step(`深度思考: found=${dt.found} on=${dt.on} toggled=${dt.toggled}${dt.error ? ' err=' + dt.error : ''}`);

      // 先传附件（等证据），再填正文
      let attachInfo = null;
      const hasAttachments = Array.isArray(attachments) && attachments.length > 0;
      if (hasAttachments) {
        step(`开始上传 ${attachments.length} 个附件…`);
        attachInfo = await uploadAttachments(attachments);
        step(`附件上传完成: ${JSON.stringify(attachInfo)}`);
      }

      // ⚠️ 正文投递形态由**调用方显式决定**（用户 2026-10-12 定案）：
      //   · asAttachment=true  → 正文写成 context.md **附件**上传，输入框只留短指令。
      //     用途：把"当前会话历史"灌给 DS 网页（量大），避免输入框卡死。
      //   · asAttachment=false → 正文**直接填输入框**（新会话无历史 / 工具往返 / 普通对话）。
      //   绝不再"无脑全部走附件"——那会让每轮工具往返都传一个 context.md（慢且乱）。
      const body = String(message || '').trim();
      let textToSend = body;
      if (asAttachment && body) {
        step(`调用方要求正文走附件（${body.length} 字）→ context.md …`);
        await uploadFile(
          { name: `context-${body.length}.md`, mimeType: 'text/markdown', base64: Buffer.from(body, 'utf8').toString('base64') },
          { timeoutMs: 30000 },
        );
        textToSend = '请阅读附件中的完整上下文与要求，并据此回答。';
        step(`正文已转附件，输入框只填指令（${textToSend.length} 字）`);
      }
      // 附件轮但正文为空：给一句最小提示，否则 DS 的发送按钮可能保持禁用、
      // 或发出一条「只有附件、没有指令」的消息（模型不知道要对附件做什么）。
      if (!textToSend) textToSend = hasAttachments ? '请阅读我上传的附件并据此回答。' : '';
      step(`填正文（${textToSend.length} 字，asAttachment=${asAttachment}）…`);
      await input.fill(textToSend, { timeout: 15000 });
      step('正文已填');
      // 回读校验（防静默截断）——只对**直接填框**的正文校验（走附件的已不填框）
      if (!asAttachment && body) {
        const echoed = await input.inputValue().catch(() => null);
        if (typeof echoed === 'string' && echoed.length + 8 < body.length) {
          const err = new Error(`PROMPT_TRUNCATED: 输入框只接收了 ${echoed.length}/${body.length} 字符`);
          err.code = 'PROMPT_TRUNCATED';
          throw err;
        }
      }

      const decoder = new DeepSeekStreamDecoder(onDelta, onThink);
      let settle;
      const done = new Promise((resolve) => { settle = resolve; });
      active = { decoder, settle };

      // 用户在本轮进行中关掉浏览器窗口 → 立刻结束本轮（别干等到 180s 超时，
      // 上层会看到"模型调用失败"，但至少是**快速失败**而不是长时间挂起）。
      const pAtSend = page;
      const onClosed = () => { try { settle('closed'); } catch {} };
      try { pAtSend && pAtSend.once('close', onClosed); } catch {}
      try { ctx && ctx.once('close', onClosed); } catch {}

      // 发送：优先点按钮（等其可用），退化回车。
      // ⚠️ 点一次**不代表真发出去了**（DS 的按钮有时在附件处理完前是"看似可点但无效"，
      //    或选择器命中不到）。所以每轮尝试后必须**校验发送是否真的开始**：
      //      · 输入框被清空，或  · 停止按钮出现（正在生成）
      //    没校验到就重试（再点 / 回车），避免"点了没发出去 → 干等 180s 超时"。
      step('准备发送…');
      let sent = false;
      const sendSelectors = [
        SEL.sendButton,                                   // 稳定 SVG path
        "div[role='button']:has-text('发送')",             // 文本兜底
        "button:has-text('发送')",
        "[class*='send']",
      ];
      const detectSent = async () => {
        // 1) 输入框被清空
        const val = await input.inputValue().catch(() => null);
        if (typeof val === 'string' && val.trim() === '') return true;
        // 2) 停止按钮出现
        const stopCount = await page.locator(SEL.stopButton).count().catch(() => 0);
        return stopCount > 0;
      };
      for (let round = 0; round < 12 && !sent; round++) {
        // 每次尝试：遍历选择器，点第一个 enabled 的
        for (const sel of sendSelectors) {
          if (sent) break;
          const btn = page.locator(sel).first();
          const cnt = await btn.count().catch(() => 0);
          if (!cnt) continue;
          const enabled = await btn.isEnabled().catch(() => true);
          if (!enabled) continue;
          step(`尝试点发送按钮 sel=${sel}（enabled=${enabled}）…`);
          try {
            await btn.click({ timeout: 3000 });
            // 校验
            await page.waitForTimeout(400);
            if (await detectSent()) sent = true;
          } catch (e) {
            step(`点击异常: ${e.message}`);
          }
        }
        // 仍没发出去：回车兜底
        if (!sent) {
          step('退化：按 Enter 发送');
          try {
            await input.click({ timeout: 2000 }).catch(() => {});
            await input.press('Enter', { timeout: 8000 });
            await page.waitForTimeout(400);
            if (await detectSent()) sent = true;
          } catch (e) {
            step(`Enter 异常: ${e.message}`);
          }
        }
        if (!sent) await page.waitForTimeout(600);
      }
      step(`已发送(sent=${sent})，等待网页流式回复…`);
      if (!sent) {
        const err = new Error('SEND_FAILED: 未能触发 DS 网页发送（发送按钮点不到且回车无效）');
        err.code = 'SEND_FAILED';
        throw err;
      }

      // 等收流（end）或兜底超时
      const timer = setTimeout(() => { step(`等待超时(${timeout}ms)，放弃`); settle('timeout'); }, timeout);
      const why = await done;
      clearTimeout(timer);
      active = null;
      step(`本轮结束（${why}）`);

      const result = decoder.finish();
      // 浏览器被关掉（用户手动关窗）且没收到任何内容 → 明确报错，
      // 别把空回复当正常返回（上层会显示"模型调用失败"，原因一目了然）。
      if (why === 'closed' && !result?.text) {
        const err = new Error('DS 浏览器窗口已被关闭（本轮中断）。请重试，桥会自动重开窗口。');
        err.code = 'BROWSER_CLOSED';
        throw err;
      }
      return { ...result, endedBy: why, attachInfo };
    } finally {
      active = null;
      busy = false;
    }
  }

  /**
   * 调试：打开/显示当前登录态的 DS 浏览器窗口。
   *  - 若当前是 headless：关掉无头上下文，用**同一个持久化 profile**有头重启
   *    （登录态在磁盘 profile 里，不会丢），并把 DS 页带到前台。
   *  - 若已是 headed：把已有窗口/页面带到前台即可。
   *  - 若正有一轮在进行（busy）：拒绝，避免把正在跑的上下文掐掉。
   */
  async function showWindow() {
    if (busy) return { ok: false, reason: 'busy', message: '当前有一轮对话正在进行，稍后再试' };
    const wasHeadless = headless;
    try {
      // 已在有头：直接把页面带到前台
      if (ctx && page && !page.isClosed() && !wasHeadless) {
        await page.bringToFront().catch(() => {});
        return { ok: true, alreadyHeaded: true, url: page.url() };
      }
      // 无头（或未启动）：用同一 profile 有头重启
      if (ctx) { try { await ctx.close(); } catch {} ctx = null; page = null; }
      await launch({ headless: false });
      if (!page.url().startsWith(DS_ORIGIN)) {
        await page.goto(DS_ORIGIN, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
      }
      await page.bringToFront().catch(() => {});
      const loginInfo = await checkLogin().catch(() => ({ loggedIn: false }));
      return { ok: true, alreadyHeaded: false, url: page.url(), loggedIn: !!loginInfo.loggedIn };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e?.message || e) };
    }
  }

  async function close() {
    try { await ctx?.close(); } catch {}
    ctx = null;
    page = null;
  }

  return { launch, ensure, checkLogin, chat, uploadAttachments, showWindow, ensureDeepThink, close, get page() { return page; }, get context() { return ctx; }, state: () => ({ running: !!ctx, busy }) };
}
