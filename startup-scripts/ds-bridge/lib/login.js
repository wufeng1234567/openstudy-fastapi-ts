// login.js — DS 登录能力（手动登录，唯一入口）
//
// 结论（真机实测 2026-10-12）：**自动填密码登录不可行**。
//   · 手机号 + 密码 → DS 弹「手机短信认证」
//   · 邮箱 + 密码   → DS 弹「邮箱验证」
//   无论哪种，脚本提交密码后都会被 DS 的二次验证（风控）挡住。
//   dsh-web-bridge 亦正因如此**只做手动登录**（browser-driver.js 首登 headed）。
// 因此本模块**只保留手动登录**：打开有头窗口 → 用户自行完成登录/验证 → 轮询到已登录即返回。
//
// ⚠️ 本模块不接触、不存储任何密码/账号凭据。

const DS_ORIGIN = 'https://chat.deepseek.com';
/** 登录成功的判定标志：已登录的会话页有正文输入框 textarea.ds-scroll-area */
const COMPOSER = 'textarea.ds-scroll-area';

export function createLogin(driver, { log = () => {} } = {}) {
  async function gotoSignIn() {
    const page = driver.page;
    if (!page) return null;
    if (!page.url().startsWith(DS_ORIGIN)) {
      await page.goto(DS_ORIGIN, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
    }
    await page.waitForTimeout(1200);
    return page;
  }

  /** 是否已登录（有正文输入框且不在 /sign_in） */
  async function isLoggedIn() {
    // 上下文可能已被用户关窗销毁 → 先确保有一份可用的浏览器（无头重开，登录态在 profile）。
    try { await driver.ensure?.(); } catch {}
    const page = driver.page;
    if (!page || page.isClosed()) return false;
    // ⚠️ 必须先确保已在 DS 页面：冷启动时页面是 about:blank，
    //    composer 必然为 0 → 会误判「未登录」。这里按需导航一次。
    if (!page.url().startsWith(DS_ORIGIN)) {
      await page.goto(DS_ORIGIN, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
      await page.waitForTimeout(2000);
    }
    // SPA 水合需要时间：轮询等输入框，最多 ~15s
    const deadline = Date.now() + 15000;
    for (;;) {
      const p = driver.page;
      if (!p || p.isClosed()) return false;
      if (p.url().includes('/sign_in')) return false;
      const hasInput = await p.locator(COMPOSER).count().catch(() => 0);
      if (hasInput > 0) return true;
      if (Date.now() > deadline) return false;
      await p.waitForTimeout(500);
    }
  }

  /**
   * 手动登录：打开有头窗口，用户自行完成 DeepSeek 登录 / 二次验证；轮询到已登录即返回。
   *
   * @param {(msg:string)=>void} onNotice 进度回调（给 UI 显示）
   * @param {number} timeout 最长等待（默认 5 分钟）
   * @returns {Promise<{ok:boolean, reason?:string, message?:string}>}
   */
  async function loginManual({ onNotice = () => {}, timeout = 5 * 60 * 1000 } = {}) {
    // 关掉无头实例，用有头重开（登录态存 profile，二者共用）
    await driver.close();
    await driver.launch({ headless: false });
    await gotoSignIn();
    onNotice('已打开 Edge 登录窗口。请在其中完成 DeepSeek 登录（扫码 / 手机号 / 邮箱均可，含后续验证）。');

    const deadline = Date.now() + timeout;
    for (;;) {
      if (await isLoggedIn()) {
        onNotice('已检测到登录成功 ✅（登录态已保存，后续将切回无头模式）。');
        return { ok: true };
      }
      const page = driver.page;
      if (!page || page.isClosed()) {
        return { ok: false, reason: 'window-closed', message: '登录窗口被关闭；若已完成登录，请重新点击「检测登录」。' };
      }
      if (Date.now() > deadline) {
        return { ok: false, reason: 'timeout', message: '手动登录等待超时，可再次点击「手动登录」重试。' };
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  return { isLoggedIn, loginManual };
}

export { COMPOSER as LOGIN_COMPOSER };
