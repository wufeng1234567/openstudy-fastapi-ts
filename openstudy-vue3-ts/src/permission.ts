import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken, removeToken } from '@/utils/auth'
import { isHttp } from '@/utils/validate'
import { isRelogin } from '@/utils/request'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import { promptLogin, isLoginPromptSuppressed } from '@/utils/loginGuard'
import type { RouteRecordRaw } from 'vue-router'

NProgress.configure({ showSpinner: false });

const whiteList: string[] = ['/', '/login', '/register', '/front/agent/chat', '/front/courses', '/front/resources'];

/**
 * 后台管理路径前缀（2026-10-22）
 *
 * 为什么需要这份名单：
 *   这些后台路由在 `router/index.ts` 里是**静态注册**的（`constantRoutes`），
 *   意味着「路由存在」这件事本身就等于「任何人都能访问」。之前只拦了 `/index/`，
 *   于是演示用户 user1 登录后直接敲 `#/system/comment` 就能进后台页面
 *   （页面里能显示，只是接口偶尔返 403 —— 这就是「很奇怪，现在又不会了」的来源）。
 *
 * 现在两层防护：
 *   1. 这里——非 admin 访问任何后台路径，直接重定向回前台；
 *   2. 后端——`/system/**` 接口统一挂 `require_admin`（core/security.py）。
 *   前端这层是体验（不让用户看到空壳页面），后端那层才是安全边界。
 */
const ADMIN_PATH_PREFIXES = [
  '/system',
  '/monitor',
  '/questionBank',
  '/questionMain',
  '/questionError',
  '/questionMarked',
  '/favoriteBank',
  '/favoriteQuestion',
  '/wordBooks',
  '/words',
  '/dictation',
  '/noteCategory',
  '/carousel',
  '/sensitiveWord',
  '/message-mgr',
  '/notice-mgr',
  '/index'
];

/** 当前路径是否是后台管理页面 */
function isAdminPath(path: string): boolean {
  return ADMIN_PATH_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(prefix + '/')
  );
}

/** 当前用户是否是管理员 */
function isAdminUser(): boolean {
  return useUserStore().roles.includes('admin')
}

/**
 * 动态路由是否已经初始化过（2026-10-22）
 *
 * ⚠️ 为什么需要这个标记：
 *   普通用户调用 `/getRouters` 现在返回**空数组**（后台按角色返回，正确行为），
 *   于是 `permissionStore.addRoutes` 一直是 `[]`。而守卫里判断的是
 *   `if (addRoutes.length === 0) { ...generateRoutes().then(() => next({...to, replace:true})) }`
 *   —— 空数组 → 每次都重新生成 → 每次都 `next({...to, replace:true})` →
 *   **无限重定向**（vue-router 直接报 "Infinite redirect in navigation guard"）。
 *
 *   表现为：点了「立即开始刷题」，地址栏 hash 不动、页面也不跳。
 *
 *   加一个「只初始化一次」的标记：第一次跑完就置 true，
 *   之后不管 addRoutes 是不是空，都直接 `next()` 放行。
 */
let routesInitialized = false

/** 当前路由是否标记为必须登录（子路由会继承父级 matched meta） */
function needsLogin(to: any): boolean {
  return (to.matched || []).some((record: any) => record.meta && record.meta.requiresLogin)
}

/**
 * 游客访问登录后功能时，提示去登录；返回 true 表示已拦截。
 *
 * ⚠️ 提示统一走 `promptLogin()`（全局单例）：
 *    这里以前自己也弹一个 ElMessageBox，于是「按钮 ensureLogin 弹一个 → 跳转守卫再弹一个」
 *    变成了连环弹窗（用户 2026-10-17 报的 bug）。现在只复用同一个框；
 *    正在跳登录 / 刚被拒绝的冷却期内直接静默拦截，不再打扰。
 */
function blockGuestToLogin(to: any, next: any): boolean {
  const userStore = useUserStore()
  if (!needsLogin(to) || !userStore.isGuest) return false
  if (isLoginPromptSuppressed()) {
    next(false)
    NProgress.done()
    return true
  }

  promptLogin('使用该功能').finally(() => {
    // promptLogin 里已经负责跳转；这里只需结束这次导航（不要 next() 放行）
    next(false)
    NProgress.done()
  })
  return true
}

router.beforeEach((to, from, next) => {
  NProgress.start()

  const token = getToken()
  const userStore = useUserStore()
  const permissionStore = usePermissionStore()

  if (token) {
    to.meta.title && useSettingsStore().setTitle(to.meta.title)

    if (to.path === '/login') {
      /*
       * ⚠️ 2026-10-26 修「点重新登录后不跳转，仍留在智能体页面」。
       *
       *    用户报的现象：token 过期 → 点「重新登录」→ **没有**进登录页，
       *    而是停在智能体页面又弹一次登录框。
       *
       *    根因就在这一段：只要本地**还有 token**（哪怕已经彻底失效），
       *    `/login` 就会被重定向走。其中：
       *
       *      · `getInfo()` 成功（token 仍有效）→ 跳首页，这是对的；
       *      · `getInfo()` **失败**（token 已过期）→ 原来也跳首页 `next({path:'/'})`，
       *        于是页面弹回智能体，`isRelogin` 又因为随后接口 401 再次置位，
       *        用户看到的就是「点了重新登录，结果还在原地弹窗」——
       *        一个死循环，永远进不去登录页。
       *
       *    正确行为：`getInfo()` 失败 = 会话确实失效，此时**应该放行到登录页**
       *    （并顺手清掉失效 token，免得后面每个请求都再撞一次 401）。
       */
      if (userStore.isGuest) {
        next()
        NProgress.done()
      } else if (!userStore.name && userStore.roles.length === 0) {
        userStore.getInfo().then(() => {
          if (userStore.isGuest) {
            next()
          } else {
            next({ path: '/' })
          }
          NProgress.done()
        }).catch(() => {
          // 取不到用户信息 = token 已失效。放行到登录页，并清掉脏 token。
          removeToken()
          userStore.token = ''
          userStore.name = ''
          userStore.roles = []
          next()
          NProgress.done()
        })
      } else {
        next({ path: '/' })
        NProgress.done()
      }
    } else if (to.path === '/') {
      // 进站即智能体：不再区分 admin / 普通用户，前台统一落在对话页
      next({ path: '/front/agent/chat' })
      NProgress.done()
    } else if (whiteList.indexOf(to.path) !== -1) {
      next()
    } else {
      if (userStore.roles.length === 0) {
        isRelogin.show = true

        userStore.getInfo().then(() => {
          isRelogin.show = false

          // 游客访问「必须登录」的页面 → 先提示登录
          if (blockGuestToLogin(to, next)) return

          // 获取用户信息后，检查是否有权限访问后台页面
          if (isAdminPath(to.path) && !isAdminUser()) {
            next({ path: '/front/agent/chat' })
            NProgress.done()
            return
          }

          permissionStore.generateRoutes().then((accessRoutes: RouteRecordRaw[]) => {
            accessRoutes.forEach((route: RouteRecordRaw) => {
              if (!isHttp(route.path)) {
                router.addRoute(route)
              }
            })
            next({ ...to, replace: true })
          }).catch(() => {
            isRelogin.show = false
            next('/front/agent/chat')
            NProgress.done()
          })
        }).catch(() => {
          isRelogin.show = false
          userStore.clearState()
          next(`/login?redirect=${to.fullPath}`)
          NProgress.done()
        })
      } else {
        // 游客访问「必须登录」的页面 → 先提示登录
        if (blockGuestToLogin(to, next)) return

        // 已有用户信息，检查是否有权限访问后台页面
        if (isAdminPath(to.path) && !isAdminUser()) {
          next({ path: '/front/agent/chat' })
          NProgress.done()
          return
        }

        if (permissionStore.addRoutes.length === 0 && !routesInitialized) {
          routesInitialized = true
          permissionStore.generateRoutes().then((accessRoutes: RouteRecordRaw[]) => {
            accessRoutes.forEach((route: RouteRecordRaw) => {
              if (!isHttp(route.path)) {
                router.addRoute(route)
              }
            })
            next({ ...to, replace: true })
          }).catch(() => {
            next({ ...to, replace: true })
          })
        } else {
          next()
        }
      }
    }
  } else {
    if (whiteList.indexOf(to.path) !== -1) {
      next()
    } else {
      if (to.path === '/') {
        next('/login')
      } else {
        next(`/login?redirect=${to.fullPath}`)
      }
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  NProgress.done()
})
