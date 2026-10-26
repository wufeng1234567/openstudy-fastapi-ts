import { ElMessageBox } from 'element-plus'
import router from '@/router'
import useUserStore from '@/store/modules/user'

/**
 * 登录提示（全局单例）
 * ====================
 * ⚠️ 这里必须**只有一个弹窗实例**。
 *
 * 历史 bug（2026-10-17 用户报「点击去登录一直重复弹窗」）：
 *   登录提示原先散落在三处各自弹自己的 `ElMessageBox.confirm`：
 *     ① `utils/loginGuard.ts` 的 `ensureLogin()`（点按钮时）
 *     ② `utils/request.ts` 的请求拦截器（写请求被拦时，**每个请求弹一次**）
 *     ③ `permission.ts` 的 `blockGuestToLogin()`（路由守卫）
 *   于是「点一下按钮」可能同时命中 ①+②（甚至 ③）：弹一个框，用户点「去登录」跳转，
 *   跳转又触发 ③ 再弹一个、还有若干挂起请求各弹一个 —— 看起来就是"一直重复弹窗"。
 *
 * 现在的约定：
 *   · 全站只允许通过本文件的 `promptLogin()` 弹登录提示；
 *   · 弹窗期间（`active` 不为空）后续调用**只复用同一个 Promise**，绝不再弹第二个；
 *   · 用户确认后统一走 `goLogin()`；跳转期间置 `redirecting`，避免路由守卫再弹一次；
 *   · 用户取消后有个很短的冷却期，避免连点/多个失败请求立刻又弹。
 */

/** 正在显示的登录提示（复用同一个 Promise） */
let active: Promise<boolean> | null = null

/** 是否正在跳转登录页（跳转期间的二次提示一律静默） */
let redirecting = false

/** 用户点了「再看看」之后的冷却截止时间（毫秒时间戳） */
let cooldownUntil = 0

const COOLDOWN_MS = 1200

/** 当前是否处于"刚被拒绝 / 正在跳登录"的静默期 */
export function isLoginPromptSuppressed(): boolean {
  return redirecting || Date.now() < cooldownUntil
}

/** 是否已有登录提示正在展示 */
export function isLoginPromptActive(): boolean {
  return active !== null
}

/** 当前是否存在登录态（含游客） */
export function hasLoginToken(): boolean {
  return !!useUserStore().token
}

/** 当前是否为游客只读账号 */
export function isGuestUser(): boolean {
  const userStore = useUserStore()
  return !!userStore.token && userStore.isGuest
}

/** 真正跳登录页（统一入口，带 redirect） */
export function goLogin(redirect?: string) {
  redirecting = true
  const target = redirect || router.currentRoute.value.fullPath || '/front/agent/chat'
  // 已经在登录页就不再重复跳转（避免自己跳自己导致路由抖动）
  if (router.currentRoute.value.path !== '/login') {
    /*
     * ⚠️ 2026-10-26：这里用 `router.push` 是**对的**，因为本项目是 hash 路由
     *    （`createWebHashHistory`），router 会自动把目标拼到 `#` 之后。
     *
     *    对比 `utils/request.ts` 的 401 分支：那里原本用
     *    `window.location.href = '/login?...'` 整页跳转，路径不在 hash 里，
     *    结果是原地刷新、根本没进登录页 —— 已一并修正。
     */
    router.push(`/login?redirect=${encodeURIComponent(target)}`).finally(() => {
      // 给守卫/跳转留出时间窗口，之后再恢复
      window.setTimeout(() => {
        redirecting = false
      }, 800)
    })
  } else {
    redirecting = false
  }
}

/**
 * 弹一次登录提示（全局去重）。
 * @returns true = 已登录可直接继续；false = 未登录/游客（已提示或已跳转）
 */
export function promptLogin(actionName = '进行该操作'): Promise<boolean> {
  const userStore = useUserStore()

  // 已登录（非游客）：直接放行
  if (userStore.token && !userStore.isGuest) return Promise.resolve(true)

  /*
   * ⚠️ 「有 token 但已失效」不走这里 —— 那是 401 通道（`request.ts` 的
   *    「登录状态已过期」框）负责的。两条通道各弹各的框，正是"点去登录一直重复弹窗"
   *    的另一半原因：失效 token 下，页面加载的写请求触发 401 框，用户点按钮又触发本框。
   *    判据：token 存在但用户信息取不到（roles 为空）→ 视为失效会话，静默让 401 处理。
   */
  if (userStore.token && !userStore.name) return Promise.resolve(false)

  // 正在跳转登录页 / 刚被拒绝：不再打扰
  if (isLoginPromptSuppressed()) return Promise.resolve(false)

  // 已有弹窗在展示：复用同一个 Promise（关键：不会叠出第二个框）
  if (active) return active

  const content = userStore.token
    ? `游客仅可浏览，登录后才能${actionName}。`
    : `请先登录后再${actionName}。`

  active = ElMessageBox.confirm(content, '温馨提示', {
    confirmButtonText: '去登录',
    cancelButtonText: '再看看',
    type: 'warning',
    closeOnClickModal: false,
    distinguishCancelAndClose: true
  })
    .then(() => {
      goLogin()
      return false
    })
    .catch(() => {
      // 用户选择「再看看」或直接关闭：进入短暂冷却，避免同一批失败请求立刻再弹
      cooldownUntil = Date.now() + COOLDOWN_MS
      return false
    })
    .finally(() => {
      active = null
    })

  return active
}

/**
 * 需要登录才能继续的操作统一入口。
 *
 * 普通登录用户：直接返回 true，不打断原操作；
 * 未登录 / 游客：弹出「去登录」提示（全局唯一），确认后跳到登录页并带上 redirect。
 *
 * 用法：const canRun = await ensureLogin('刷题')
 */
export async function ensureLogin(actionName = '进行该操作'): Promise<boolean> {
  const userStore = useUserStore()

  // 刷新页面后 Pinia 内存态可能还没拉到用户信息，这里补一次
  if (userStore.token && !userStore.name) {
    try {
      await userStore.getInfo()
    } catch (e) {
      // 拉取失败按未登录处理，用户仍可点击去登录页重新登录
    }
  }

  if (userStore.token && !userStore.isGuest) return true

  return promptLogin(actionName)
}
