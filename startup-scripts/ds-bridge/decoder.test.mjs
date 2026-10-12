// decoder.test.mjs — 原型解码器自检（离线，无网络）
import { DeepSeekStreamDecoder } from './lib/decoder.js';

let out = '';
let think = '';
const d = new DeepSeekStreamDecoder((t) => { out += t; }, (t) => { think += t; });

const frames = [
  'event: ready\ndata: {"response_message_id":"r1"}\n\n',
  'event: message\ndata: {"v":{"response":{"status":"WIP","fragments":[{"id":2,"type":"RESPONSE","content":""}]}}}\n\n',
  // 带结构帧（含 type/content）
  'event: message\ndata: {"p":"response/fragments/-1/content","o":"APPEND","v":{"type":"RESPONSE","content":"你好"}}\n\n',
  // 裸增量帧（无 p / 无 type）—— 真机常态
  'event: message\ndata: {"v":"，世界"}\n\n',
  // 思考片段
  'event: message\ndata: {"p":"response/fragments/-1/content","o":"APPEND","v":{"type":"THINK","content":"思考"}}\n\n',
  'event: message\ndata: {"v":"中"}\n\n',
  'event: close\ndata: {}\n\n',
];
for (const f of frames) d.push(f);
const r = d.finish();

console.log('text      =', JSON.stringify(r.text));
console.log('thinking  =', JSON.stringify(r.thinking));
console.log('complete  =', r.complete);
console.log('onDelta   =', JSON.stringify(out));
console.log('onThink   =', JSON.stringify(think));

const ok = r.text === '你好，世界' && r.thinking === '思考中' && r.complete === true && out === '你好，世界' && think === '思考中';
console.log(ok ? 'PASS' : 'FAIL');
process.exit(ok ? 0 : 1);
