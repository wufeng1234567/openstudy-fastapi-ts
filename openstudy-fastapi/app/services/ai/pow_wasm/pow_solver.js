#!/usr/bin/env node
/**
 * DeepSeek PoW 求解脚本（DeepSeekHashV1）—— 基于官方 wasm 的真实 ABI
 *
 * 官方 wasm: https://fe-static.deepseek.com/chat/static/sha3_wasm_bg.7b9ca65ddd.wasm
 * 导出表（实测）:
 *   memory, wasm_deepseek_hash_v1, wasm_solve,
 *   __wbindgen_add_to_stack_pointer, __wbindgen_export_0/1/2
 *
 * 调用约定（wasm-bindgen 标准套路）:
 *   retptr = __wbindgen_add_to_stack_pointer(-16)
 *   wasm_solve(retptr, challengePtr, challengeLen, prefixPtr, prefixLen, difficulty)
 *   status = i32 @ retptr, answer = f64 @ retptr+8
 *   __wbindgen_add_to_stack_pointer(16)
 *
 * 输入(stdin) : {"challenge","salt","expireAt","difficulty","wasmPath"}
 * 输出(stdout): {"answer":<number>,"status":<int>,"candidates":[...]}
 * 自检        : node pow_solver.js --inspect <wasm>
 */

const fs = require('fs');

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => (buf += c));
    process.stdin.on('end', () => resolve(buf));
    process.stdin.on('error', reject);
  });
}

async function loadExports(wasmPath) {
  const bytes = fs.readFileSync(wasmPath);
  const { instance } = await WebAssembly.instantiate(bytes, {});
  return instance.exports;
}

function describe(exports) {
  const info = {};
  for (const [k, v] of Object.entries(exports)) {
    if (typeof WebAssembly.Global === 'function' && v instanceof WebAssembly.Global) {
      info[k] = `Global = ${JSON.stringify(v.value)}`;
    } else if (typeof v === 'function') {
      info[k] = `Function(arity=${v.length})`;
    } else if (v instanceof WebAssembly.Memory) {
      info[k] = `Memory(${v.buffer.byteLength} bytes)`;
    } else {
      info[k] = typeof v;
    }
  }
  return info;
}

function pickMalloc(exports) {
  // wasm-bindgen 会把 malloc/realloc/free 导出成 __wbindgen_export_N，
  // malloc 的签名是 (size, align) → arity 2
  const cands = ['__wbindgen_export_0', '__wbindgen_export_1', '__wbindgen_export_2'];
  for (const n of cands) {
    const f = exports[n];
    if (typeof f === 'function' && f.length === 2) return f;
  }
  throw new Error('找不到 malloc（__wbindgen_export_N 里没有 arity=2 的函数）');
}

function solve(exports, { challenge, salt, expireAt, difficulty }) {
  const mem = exports.memory;
  const malloc = pickMalloc(exports);

  const encode = (s) => {
    const bytes = Buffer.from(s, 'utf8');
    const ptr = malloc(bytes.length, 1);
    new Uint8Array(mem.buffer).set(bytes, ptr);
    return [ptr, bytes.length];
  };

  const retptr = exports.__wbindgen_add_to_stack_pointer(-16);
  const [cp, cl] = encode(challenge);
  const prefix = `${salt}_${expireAt}_`;
  const [pp, pl] = encode(prefix);

  exports.wasm_solve(retptr, cp, cl, pp, pl, difficulty);

  const dv = new DataView(mem.buffer);
  const status = dv.getInt32(retptr, true);
  // 8 字节对齐和紧挨着两种读法都试，交给上层判断
  const cands = [dv.getFloat64(retptr + 8, true), dv.getFloat64(retptr + 4, true)];

  exports.__wbindgen_add_to_stack_pointer(16);

  const valid = cands.filter((n) => Number.isFinite(n) && n !== 0);
  const answer = valid.length ? valid[0] : 0;
  return { status, answer, candidates: cands };
}

(async () => {
  const args = process.argv.slice(2);

  try {
    if (args[0] === '--inspect') {
      const exports = await loadExports(args[1]);
      console.log(JSON.stringify(describe(exports), null, 2));
      return;
    }

    const input = JSON.parse(await readStdin());
    const exports = await loadExports(input.wasmPath);
    const res = solve(exports, {
      challenge: input.challenge,
      salt: input.salt,
      expireAt: input.expireAt,
      difficulty: input.difficulty,
    });
    console.log(JSON.stringify(res));
  } catch (e) {
    console.error('pow solve failed:', e && e.message ? e.message : String(e));
    console.log(JSON.stringify({ answer: 0, error: String(e) }));
    process.exit(1);
  }
})();
