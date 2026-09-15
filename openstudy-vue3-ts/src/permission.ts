import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken } from '@/utils/auth'
import { isHttp } from '@/utils/validate'
import { isRelogin } from '@/utils/request'
import { ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import type { RouteRecordRaw } from 'vue-router'

NProgress.configure({ showSpinner: false });

const whiteList: string[] = ['/', '/login', '/register', '/front/index', '/front/courses', '/front/resources'];

/** 当前路由是否标记为必须登录（子路由会继承父级 matched meta） */
function needsLogin(to: any): boolean {
  return (to.matched || []).some((record: any) => record.meta && record.meta.requiresLogin)
}

/** 游客访问登录后功能时，提示去登录；返回 true 表示已拦截 */
function blockGuestToLogin(to: any, next: any): boolean {
  const userStore = useUserStore()
  if (!needsLogin(to) || !userStore.isGuest) return false

  ElMessageBox.confirm('游客仅可浏览，登录后即可使用该功能。', '温馨提示', {
    confirmButtonText: '去登录',
    cancelButtonText: '再看看',
    type: 'warning',
    closeOnClickModal: false
  }).then(() => {
    // 不退出游客态；/login 已允许游客进入，登录成功后 token 会被新账号覆盖
    next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
  }).catch(() => {
    next(false)
  })
  NProgress.done()
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
      if (userStore.roles.length === 0) {
        userStore.getInfo().then(() => {
          if (userStore.roles.includes('admin')) {
            next({ path: '/index/home' })
          } else {
            next({ path: '/front/index' })
          }
          NProgress.done()
        }).catch(() => {
          next({ path: '/front/index' })
          NProgress.done()
        })
      } else {
        if (userStore.roles.includes('admin')) {
          next({ path: '/index/home' })
        } else {
          next({ path: '/front/index' })
        }
        NProgress.done()
      }
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
            next({ path: '/front/index' })
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
            next('/front/index')
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
          next({ path: '/front/index' })
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
