// test-attach.js — 附件测试：① 超长文本(md 附件) ② 图片 ③ 文档(txt 附件)
//
// 前置：ds 桥已登录（首次先跑 `node probe.js --login`）。
// 用法：node test-attach.js [text|image|both]  （默认 both）
//   直接连驱动（不经 HTTP），便于观察每一步。
import { createDriver } from './lib/driver.js';
import { createLogin } from './lib/login.js';
import zlib from 'node:zlib';

/** 生成一张带明显特征的 PNG（无第三方依赖）：左红右蓝 + 斜纹 */
function makePng(width, height) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    const rowStart = y * (width * 4 + 1);
    raw[rowStart] = 0;
    for (let x = 0; x < width; x++) {
      const o = rowStart + 1 + x * 4;
      const left = x < width / 2;
      raw[o] = left ? 220 : 30;
      raw[o + 1] = ((x + y) % 40 < 20) ? 200 : 60;
      raw[o + 2] = left ? 30 : 220;
      raw[o + 3] = 255;
    }
  }
  const idat = zlib.deflateSync(raw);
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const t = Buffer.from(type, 'ascii');
    const crcBuf = Buffer.concat([t, data]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(crcBuf) >>> 0);
    return Buffer.concat([len, t, data, crc]);
  };
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]);
}
function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xEDB88320 & -(c & 1));
  }
  return ~c;
}

const mode = process.argv[2] || 'both';
const driver = createDriver({ headless: true, log: (m) => console.log('[driver]', m) });
const login = createLogin(driver);

await driver.launch({ headless: true });
if (!(await login.isLoggedIn())) {
  console.error('未登录，请先：node probe.js --login');
  await driver.close();
  process.exit(1);
}

async function runCase(label, message, attachments) {
  console.log(`\n========== ${label} ==========`);
  console.log('附件:', attachments.map((a) => `${a.name}(${a.mimeType})`).join(', ') || '(无)');
  try {
    const res = await driver.chat(message, {
      onDelta: (t) => process.stdout.write(t),
      onThink: () => {},
      attachments,
      timeout: 180000,
    });
    console.log('\n--- 结果 ---');
    console.log('attachInfo =', JSON.stringify(res.attachInfo));
    console.log('text 长度 =', (res.text || '').length, '| complete =', res.complete, '| endedBy =', res.endedBy);
    if (res.hint) console.log('hint =', res.hint);
  } catch (e) {
    console.log(`\n[${label}] ERROR:`, e.code || '', e.message);
  }
}

try {
  if (mode === 'text' || mode === 'both') {
    const lines = [];
    for (let i = 1; i <= 2000; i++) lines.push(`第 ${i} 行：超长文本附件测试占位，编号 ${i}，关键词 ALPHA-${i}。`);
    const md = `# 超长文本附件测试\n\n读完后请回答：一共多少行？最后一行编号是多少？\n\n` + lines.join('\n');
    console.log('\n[test] md 字符数 =', md.length);
    await runCase('① 超长文本 (.md)', '', [
      { name: `long-context-${md.length}.md`, mimeType: 'text/markdown', base64: Buffer.from(md, 'utf8').toString('base64') },
    ]);
  }

  if (mode === 'image' || mode === 'both') {
    const png = makePng(240, 160);
    console.log('\n[test] 生成 PNG，字节 =', png.length);
    await runCase('② 图片 (.png)', '请描述这张图片：左半边和右半边分别是什么颜色？有无斜纹？', [
      { name: 'openstudy-test-image.png', mimeType: 'image/png', base64: png.toString('base64') },
    ]);
  }
} finally {
  await driver.close();
}
