import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken } from '@/utils/auth'
import { isHttp } from '@/utils/validate'
import { isRelogin } from '@/utils/request'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import { promptLogin, isLoginPromptSuppressed } from '@/utils/loginGuard'
import type { RouteRecordRaw } from 'vue-router'

NProgress.configure({ showSpinner: false });

const whiteList: string[] = ['/', '/login', '/register', '/front/agent/chat', '/front/courses', '/front/resources'];

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
      // 游客允许进入登录页切换为正式账号；普通已登录用户仍跳首页
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
          next({ path: '/' })
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
          if (to.path.startsWith('/index/') && !userStore.roles.includes('admin')) {
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
        if (to.path.startsWith('/index/') && !userStore.roles.includes('admin')) {
          next({ path: '/front/agent/chat' })
          NProgress.done()
          return
        }

        if (permissionStore.addRoutes.length === 0) {
          permissionStore.generateRoutes().then((accessRoutes: RouteRecordRaw[]) => {
            accessRoutes.forEach((route: RouteRecordRaw) => {
              if (!isHttp(route.path)) {
                router.addRoute(route)
              }
            })
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
