// server.js — DS 网页桥的 OpenAI 兼容 HTTP 端点
//
// 把本机无头 Edge 驱动的 DS 网页会话，包装成 OpenAI 兼容接口，挂在本机回环：
//   GET  /v1/models              → 模型列表（model id: ds-free-nb）
//   POST /v1/chat/completions    → 聊天（stream:false → JSON；stream:true → SSE + [DONE]）
//   GET  /bridge/status          → 桥状态（登录态 / 忙碌）
//   POST /bridge/login           → 触发手动登录（打开有头窗口）—— 由上层 UI 调用
//
// 这样上层（本项目后端）只要把 `ds-free-nb` 配成一个 base_url=本机地址的模型，
// 就能像普通 OpenAI 模型一样用它，**无需改任何 AI 层代码**。
//
// 安全：默认只绑 127.0.0.1（回环），绝不 0.0.0.0 —— 这个端口背后是用户已登录的网页会话。

import http from 'node:http';
import { createDriver, resolveBrowserPath } from './lib/driver.js';
import { createLogin } from './lib/login.js';

/** 模型 id（上层据此在模型列表里显示） */
const MODEL_ID = 'ds-free-nb';
const MODEL_NAME = 'DS Free (无浏览器)';

const PORT = Number(process.env.DS_BRIDGE_PORT || 9200);
const HOST = '127.0.0.1';

const driver = createDriver({
  // 默认无头；设 DS_BRIDGE_HEADED=1 启动带界面浏览器，便于排查卡在哪一步
  headless: process.env.DS_BRIDGE_HEADED !== '1',
  log: (m) => console.log('[driver]', m),
});
const login = createLogin(driver);

function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch { resolve({}); }
    });
  });
}

/** OpenAI 消息数组 → 单条文本（DS 网页无 system role，system 拼前面） */
function messagesToText(messages) {
  const sys = [];
  const rest = [];
  for (const m of messages || []) {
    const content = typeof m.content === 'string'
      ? m.content
      : Array.isArray(m.content)
        ? m.content.map((p) => (typeof p === 'string' ? p : p?.text || '')).join('')
        : '';
    if (m.role === 'system') sys.push(content);
    else rest.push(`${m.role === 'assistant' ? '## 助手' : '## 用户'}\n${content}`);
  }
  return (sys.length ? sys.join('\n\n') + '\n\n' : '') + rest.join('\n\n');
}

/**
 * 从 OpenAI 消息里提取图片附件（`content` 的 image_url 块，data URL 形式）→
 * 本桥 `uploadAttachments` 需要的 `{name,mimeType,base64}` 载荷。
 *
 * 本项目后端 langchain 走 OpenAI 兼容协议时，图片会以
 * `{"type":"image_url","image_url":{"url":"data:image/png;base64,...."}}` 下发。
 * 这里把 data URL 拆成 (mimeType, base64)，交给驱动 `setInputFiles` 直接上传。
 * 非 data URL（http(s)）暂不支持（网页上传需要字节），跳过。
 */
function extractImageAttachments(messages) {
  const out = [];
  let idx = 0;
  for (const m of messages || []) {
    if (!Array.isArray(m.content)) continue;
    for (const part of m.content) {
      const url = part && part.type === 'image_url' ? (part.image_url?.url || part.image_url) : null;
      if (typeof url !== 'string' || !url.startsWith('data:')) continue;
      const m2 = /^data:([^;,]+)?(;base64)?,(.*)$/s.exec(url);
      if (!m2) continue;
      const mime = m2[1] || 'image/png';
      const isB64 = Boolean(m2[2]);
      const data = m2[3] || '';
      idx += 1;
      const ext = (mime.split('/')[1] || 'png').replace('jpeg', 'jpg');
      out.push({
        name: `image-${idx}.${ext}`,
        mimeType: mime,
        base64: isB64 ? data : Buffer.from(decodeURIComponent(data), 'utf8').toString('base64'),
      });
    }
  }
  return out;
}

/**
 * 提取**显式声明的文件附件**：本项目可把长文本/文档以 base64 附在会话里。
 * 约定：请求体可带顶层 `files: [{name, type, base64}]`（OpenAI 扩展字段），
 * 也会把消息 content 里 `type:'file'` 的块算进来。base64 可为 data URL 或裸串。
 */
function extractFileAttachments(body) {
  const out = [];
  const push = (f) => {
    if (!f) return;
    let b64 = String(f.base64 || f.data || '');
    let mime = String(f.mimeType || f.type || '');
    const dm = /^data:([^;,]+)?(;base64)?,(.*)$/s.exec(b64);
    if (dm) { mime = mime || dm[1] || ''; b64 = dm[3] || ''; }
    if (!b64) return;
    out.push({ name: f.name || 'file.txt', mimeType: mime || 'text/markdown', base64: b64 });
  };
  for (const f of body.files || []) push(f);
  for (const m of body.messages || []) {
    if (!Array.isArray(m.content)) continue;
    for (const part of m.content) {
      if (part && part.type === 'file') push(part.file || part);
    }
  }
  return out;
}

async function handleChat(req, res, body) {
  const text = messagesToText(body.messages);
  const stream = body.stream === true;

  if (!(await login.isLoggedIn())) {
    return sendJson(res, 200, { error: { message: 'NEED_LOGIN: DeepSeek 未登录，请先在本机完成手动登录', type: 'bridge_error', code: 'NEED_LOGIN' } });
  }

  // 附件：图片（消息 content 的 image_url data URL）+ 显式文件（body.files / content type:file）
  let attachments = [];
  let asAttachment = false;
  try {
    const imgs = extractImageAttachments(body.messages);
    const fls = extractFileAttachments(body);
    asAttachment = body.asAttachment === true;
    // 诊断：把桥收到的顶层字段与附件构成打出来，便于排查"文件本体为什么没到"
    const topKeys = Object.keys(body || {});
    console.log(`[bridge] 收到请求: 顶层字段=[${topKeys.join(', ')}] | body.files=${Array.isArray(body.files) ? body.files.length : (body.files === undefined ? 'undefined' : typeof body.files)} | asAttachment=${asAttachment} | 图片=${imgs.length} 文件=${fls.length}`);
    if (Array.isArray(body.files)) {
      console.log('[bridge] body.files 明细:', JSON.stringify(body.files.map((f) => ({ name: f?.name, mimeType: f?.mimeType || f?.type, b64len: String(f?.base64 || '').length }))));
    }
    for (const f of fls) console.log(`[bridge] 文件附件: ${f.name} (${f.mimeType}, b64 ${Math.round((f.base64 || '').length / 1024)}KB)`);
    for (const im of imgs) console.log(`[bridge] 图片附件: ${im.name} (${im.mimeType}, b64 ${Math.round((im.base64 || '').length / 1024)}KB)`);
    attachments = [...imgs, ...fls];
  } catch (e) {
    console.error('[bridge] 附件解析失败:', e && e.stack || e);
    attachments = [];
  }

  if (!stream) {
    try {
      const r = await driver.chat(text, { timeout: 180000, attachments, asAttachment });
      return sendJson(res, 200, {
        id: 'chatcmpl-ds-' + Date.now(),
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: body.model || MODEL_ID,
        choices: [{ index: 0, message: { role: 'assistant', content: r.text || '' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
      });
    } catch (e) {
      return sendJson(res, 200, { error: { message: String(e.message || e), type: 'bridge_error', code: e.code || 'ERR' } });
    }
  }

  // 流式：SSE
  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });
  const chatId = 'chatcmpl-ds-' + Date.now();
  const frame = (delta, finish = null) => {
    res.write('data: ' + JSON.stringify({
      id: chatId, object: 'chat.completion.chunk', created: Math.floor(Date.now() / 1000),
      model: body.model || MODEL_ID,
      choices: [{ index: 0, delta, finish_reason: finish }],
    }) + '\n\n');
  };
  try {
    await driver.chat(text, {
      timeout: 180000,
      attachments,
      asAttachment,
      onDelta: (t) => frame({ content: t }),
      onThink: (t) => frame({ reasoning_content: t }),
    });
    frame({}, 'stop');
    res.write('data: [DONE]\n\n');
  } catch (e) {
    frame({ content: `\n[错误] ${String(e.message || e)}` }, 'stop');
    res.write('data: [DONE]\n\n');
  }
  res.end();
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);
  try {
    if (req.method === 'GET' && url.pathname === '/v1/models') {
      return sendJson(res, 200, {
        object: 'list',
        data: [{ id: MODEL_ID, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: 'openstudy-bridge', name: MODEL_NAME }],
      });
    }
    if (req.method === 'GET' && url.pathname === '/bridge/status') {
      const loggedIn = await login.isLoggedIn().catch(() => false);
      return sendJson(res, 200, { model: MODEL_ID, loggedIn, busy: driver.state().busy, running: driver.state().running });
    }
    if (req.method === 'POST' && url.pathname === '/bridge/login') {
      const r = await login.loginManual({ onNotice: (m) => console.log('[login]', m) });
      return sendJson(res, 200, r);
    }
    if (req.method === 'POST' && url.pathname === '/bridge/show') {
      // 调试：打开/显示当前登录态的 DS 浏览器（headless→headed 重启，复用磁盘 profile）
      const r = await driver.showWindow();
      return sendJson(res, 200, r);
    }
    if (req.method === 'POST' && url.pathname === '/bridge/ensure-deepthink') {
      // 调试：确保「深度思考」开关开启（与每轮发送前的检查同一逻辑）
      const r = await driver.ensureDeepThink();
      return sendJson(res, 200, r);
    }
    if (req.method === 'POST' && (url.pathname === '/v1/chat/completions' || url.pathname === '/chat/completions')) {
      const body = await readBody(req);
      // ⚠️ handleChat 是 async：必须显式 catch，否则它抛出的（未捕获）rejection
      //    会让 Node 默认**直接退出进程** → 上层看到的就是 APIConnectionError。
      return handleChat(req, res, body).catch((e) => {
        console.error('[bridge] handleChat 异常:', e && e.stack || e);
        try {
          if (!res.headersSent) sendJson(res, 200, { error: { message: String(e?.message || e), type: 'bridge_error', code: e?.code || 'ERR' } });
          else res.end();
        } catch {}
      });
    }
    return sendJson(res, 404, { error: { message: 'not found' } });
  } catch (e) {
    return sendJson(res, 500, { error: { message: String(e.message || e) } });
  }
});

// ---- 进程级兜底：桥绝不能因为一次**请求**异常而整个退出 ----
// （Node 22 默认把未处理的 rejection 当致命错误 → 进程退出 → 上层 Connection error）
process.on('unhandledRejection', (e) => {
  console.error('[bridge] unhandledRejection（已兜住，不退出）:', (e && e.stack) || e);
});
process.on('uncaughtException', (e) => {
  // ⚠️ 端口占用是**致命**的（桥根本无法服务），必须如实报错并退出——
  //    若也兜住不退出，进程会「假装活着但什么都不干」，上层只看到莫名的 Connection error。
  if (e && e.code === 'EADDRINUSE') {
    console.error(`[bridge] 致命错误：端口 ${PORT} 已被占用（可能已有一个桥在运行）。`);
    console.error('[bridge] 处理：关掉另一个桥，或设 DS_BRIDGE_PORT 换端口后重启。本进程退出。');
    process.exit(1);
  }
  console.error('[bridge] uncaughtException（已兜住，不退出）:', (e && e.stack) || e);
});

const exe = resolveBrowserPath();
console.log('[bridge] 浏览器:', exe || '(未找到)');
console.log(`[bridge] 监听 http://${HOST}:${PORT}  模型 id = ${MODEL_ID}`);

// 端口占用的正确处理：监听 `error` 事件（比 uncaughtException 更早、更准）
server.on('error', (e) => {
  if (e && e.code === 'EADDRINUSE') {
    console.error(`[bridge] 致命错误：端口 ${PORT} 已被占用（可能已有一个桥在运行）。`);
    console.error('[bridge] 处理：关掉另一个桥，或设 DS_BRIDGE_PORT 换端口后重启。本进程退出。');
    process.exit(1);
  }
  console.error('[bridge] HTTP server error:', (e && e.stack) || e);
});

// 预热：启动浏览器并检查登录态（不阻塞 HTTP）。继承 DS_BRIDGE_HEADED 决定 headed/headless。
const HEADED = process.env.DS_BRIDGE_HEADED === '1';
server.listen(PORT, HOST, async () => {
  try {
    await driver.launch({ headless: !HEADED });
    const ok = await login.isLoggedIn();
    console.log('[bridge] 登录态:', ok);
  } catch (e) {
    console.log('[bridge] 预热失败（可后续经 /bridge/login 登录）:', e.message);
  }
});

process.on('SIGINT', async () => { await driver.close(); process.exit(0); });
