import type { Plugin } from 'vite'
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'

/**
 * Vite 插件：把「DS 网页桥」（无头 Edge，无需浏览器插件）作为**前端 dev server 的子进程**拉起。
 *
 * 效果（用户 2026-10-12 要求）：
 *   · `npm run dev` 启动前端 = 自动启动桥，**不再需要单独窗口**；
 *   · 桥的 stdout/stderr 直接转发到**前端终端**（前缀 `[ds-bridge]`），日志混在一起可读；
 *   · Vite dev server 关闭时，桥进程一并结束（`closeBundle` / 进程退出钩子）。
 *
 * 只对 dev server 生效（`apply: 'serve'`）：`vite build` 不会起桥。
 *
 * 可关：设环境变量 `OPENSTUDY_DS_BRIDGE=0` 即跳过（桥另行手动启动）。
 * 端口：`DS_BRIDGE_PORT`（默认 9200），须与后端 sys_ai_config 里 ds-free-nb 的 base_url 一致。
 *
 * ⚠️ 端口复用：若 9200 已在监听（用户已单独启动过桥 / 上次没退干净），**不重复 fork**
 *    （否则 EADDRINUSE，且会和正在跑的桥抢同一个 Edge profile 单实例锁）。此时直接复用。
 */

const BRIDGE_DIR = path.resolve(__dirname, '../../../startup-scripts/ds-bridge')
const BRIDGE_PORT = Number(process.env.DS_BRIDGE_PORT || 9200)

function log(msg: string) {
  console.log(`\x1b[36m[ds-bridge]\x1b[0m ${msg}`)
}

/** 探测端口是否已被监听（TCP connect 通 = 有服务在听） */
function isPortInUse(port: number, host = '127.0.0.1'): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host })
    const done = (inUse: boolean) => {
      sock.removeAllListeners()
      try { sock.destroy() } catch { /* ignore */ }
      resolve(inUse)
    }
    sock.setTimeout(800)
    sock.once('connect', () => done(true))
    sock.once('timeout', () => done(false))
    sock.once('error', () => done(false))
  })
}

export default function createDsBridge(): Plugin {
  let child: ChildProcess | null = null

  const stop = (why: string) => {
    if (!child) return
    log(`停止桥进程（${why}） pid=${child.pid}`)
    try { child.kill() } catch { /* ignore */ }
    child = null
  }

  return {
    name: 'openstudy-ds-bridge',
    apply: 'serve',
    async configureServer(server) {
      if (process.env.OPENSTUDY_DS_BRIDGE === '0') {
        log('OPENSTUDY_DS_BRIDGE=0，跳过自动启动（请自行启动桥）')
        return
      }

      // 端口已在监听 → 复用，不重复 fork（避免 EADDRINUSE + profile 锁冲突）
      if (await isPortInUse(BRIDGE_PORT)) {
        log(`端口 ${BRIDGE_PORT} 已有服务在监听，复用现有桥（不重复启动）`)
        return
      }

      const entry = path.join(BRIDGE_DIR, 'server.js')
      if (!existsSync(entry)) {
        log(`未找到桥入口 ${entry}，跳过（不影响前端运行）`)
        return
      }
      // playwright-core 依赖：缺失时给出可行动的提示，不阻断前端
      if (!existsSync(path.join(BRIDGE_DIR, 'node_modules', 'playwright-core'))) {
        log('桥依赖未安装：请在 startup-scripts/ds-bridge 下执行 `npm install`（本次跳过桥）')
        return
      }

      log(`启动 DS 桥：node server.js  (端口 ${BRIDGE_PORT}, 目录 ${BRIDGE_DIR})`)
      child = spawn(process.execPath, ['server.js'], {
        cwd: BRIDGE_DIR,
        env: { ...process.env, DS_BRIDGE_PORT: String(BRIDGE_PORT) },
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      child.stdout?.on('data', (d) => process.stdout.write(`\x1b[36m[ds-bridge]\x1b[0m ${d}`))
      child.stderr?.on('data', (d) => process.stderr.write(`\x1b[36m[ds-bridge]\x1b[0m ${d}`))
      child.on('exit', (code, sig) => {
        log(`桥进程退出 code=${code} signal=${sig}`)
        child = null
      })
      child.on('error', (e) => log(`桥进程启动失败：${e.message}`))

      // Vite dev server 关闭 / 进程退出时，确保桥一起收掉
      server.httpServer?.on('close', () => stop('dev server closed'))
      process.once('SIGINT', () => stop('SIGINT'))
      process.once('SIGTERM', () => stop('SIGTERM'))
      process.once('exit', () => stop('process exit'))
    },
  }
}
