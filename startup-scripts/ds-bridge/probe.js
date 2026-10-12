// probe.js — 最小原型验证脚本（免扩展 DS 网页桥）
//
// 用法（在 startup-scripts/ds-bridge 下）：
//   node probe.js                  # 验证：启动无头 Edge + 打开 DS + 判登录态
//   node probe.js --login          # 手动登录：开有头窗口，你自行登录，登录成功即保存
//   node probe.js --chat "你好"     # 已登录后：无头发一条消息并打印回复
//   node probe.js --headed         # 用有头模式跑（便于观察）
//
// 说明：**不做账号密码自动登录** —— 实测手机号/邮箱自动提交密码都会被 DS 的
//       二次验证（短信/邮箱验证）挡住，故只提供手动登录。

import { createDriver, resolveBrowserPath } from './lib/driver.js';
import { createLogin } from './lib/login.js';

function parseArgs(argv) {
  const out = { headed: false, chat: null, login: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--headed') out.headed = true;
    else if (argv[i] === '--login') out.login = true;
    else if (argv[i] === '--chat') out.chat = argv[++i] || '你好';
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const exe = resolveBrowserPath();
  console.log('[probe] 浏览器可执行文件:', exe);
  if (!exe) {
    console.error('[probe] FAIL: 未找到 Edge/Chrome');
    process.exit(2);
  }

  const driver = createDriver({
    headless: !args.headed,
    log: (m) => console.log('[driver]', m),
  });
  const login = createLogin(driver);

  try {
    if (args.login) {
      const res = await login.loginManual({ onNotice: (m) => console.log('[login]', m) });
      console.log('[probe] 手动登录结果:', JSON.stringify(res));
      await driver.close();
      process.exit(res.ok ? 0 : 1);
    }

    console.log('[probe] 启动无头浏览器…');
    await driver.launch({ headless: !args.headed });

    console.log('[probe] 打开 chat.deepseek.com 并判定登录态…');
    const st = await login.isLoggedIn();
    console.log('[probe] 登录态: loggedIn =', st);

    if (!st) {
      console.log('[probe] NEED_LOGIN：当前未登录 → 请运行 `node probe.js --login` 手动登录。');
      await driver.close();
      process.exit(0);
    }

    if (args.chat) {
      console.log(`[probe] 发送消息: ${JSON.stringify(args.chat)}`);
      const res = await driver.chat(args.chat, {
        onDelta: (t) => process.stdout.write(t),
        onThink: () => {},
        timeout: 180000,
      });
      console.log('\n[probe] ---- 结束 ----');
      console.log('[probe] text 长度:', (res.text || '').length, '| thinking 长度:', (res.thinking || '').length);
      console.log('[probe] complete:', res.complete, '| status:', res.status, '| endedBy:', res.endedBy);
      if (res.hint) console.log('[probe] hint:', res.hint);
      if (!res.text) console.log('[probe] WARN: 未拿到正文（可能被限流/风控/页面改版）');
    }
  } catch (e) {
    console.error('[probe] ERROR:', e.code || '', e.message);
    process.exitCode = 1;
  } finally {
    await driver.close();
  }
}

main();
