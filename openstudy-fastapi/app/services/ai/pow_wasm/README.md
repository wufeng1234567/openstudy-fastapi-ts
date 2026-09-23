# pow_wasm —— DeepSeek PoW 求解所需资源

`provider = deepseek-free` 这条链路要过官方的 **PoW（Proof of Work）** 校验，
而官方算法 `DeepSeekHashV1` 不是普通的 SHA3，它是编译成 WebAssembly 的：

```
prefix = f"{salt}_{expire_at}_"
wasm_solve(retptr, challengePtr, challengeLen, prefixPtr, prefixLen, difficulty)
→ 得到 answer（整数）
X-Ds-Pow-Response = base64(json({
    algorithm, challenge, salt, answer, signature, target_path
}))
```

## 你需要放什么进来

需要**官方前端实际加载的那个 wasm 文件**，形如：

```
app/services/ai/pow_wasm/sha3_wasm_bg.<hash>.wasm
```

获取方式（自行完成，属于本次作业的调研部分）：

1. 打开 `https://chat.deepseek.com/`，F12 → Network → 过滤 `wasm`；
2. 刷新页面，找到 `sha3_wasm_bg.*.wasm`，右键 Save as，放进本目录；
3. 也可以在 Elements/Sources 里搜 `sha3_wasm` 找到构建产物引用。

放好之后：

```bash
# 1) 打印 wasm 导出表，核对导出名（不同构建版本可能不同）
node app/services/ai/pow_wasm/pow_solver.js --inspect app/services/ai/pow_wasm/sha3_wasm_bg.xxx.wasm

# 2) 用真实 challenge 试算（challenge/salt/expire_at 从
#    POST /api/v0/chat/create_pow_challenge 的响应里取）
echo '{"challenge":"...","salt":"...","expireAt":1234567890,"difficulty":3,"wasmPath":"app/services/ai/pow_wasm/sha3_wasm_bg.xxx.wasm"}' \
  | node app/services/ai/pow_wasm/pow_solver.js
```

`pow_solver.js` 里的 ABI 调用（`__wbindgen_malloc` / `__wbindgen_export_0` /
`wasm_solve`）是按公开资料还原的，**未经真实 wasm 验证**。如果 `--inspect`
打印出来的导出名不一样，按实际名字改 `pow_solver.js` 里的对应调用即可。

## 没有 wasm 时会怎样

客户端会自动回退到 `NaiveSha3PowSolver`（纯 Python 近似实现）。
它几乎必然过不了官方的校验，到时候日志里会看到 400/403/429，
并且在 `self_test()` 的 `stages` 里能看到失败发生在 `pow` 阶段 ——
这就是「PoW 没做对」的信号，而不是手机号密码错。
