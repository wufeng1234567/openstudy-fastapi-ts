import { defineStore } from 'pinia'
import auth from '@/plugins/auth'
import router, { constantRoutes, dynamicRoutes } from '@/router'
import { getRouters } from '@/api/menu'
import Layout from '@/layout/index'
import ParentView from '@/components/ParentView'
import InnerLink from '@/layout/components/InnerLink'
import type { RouteRecordRaw } from 'vue-router'

const modules = import.meta.glob('./../../views/**/*.vue')

const usePermissionStore = defineStore(
  'permission',
  {
    state: () => ({
      routes: [] as RouteRecordRaw[],
      addRoutes: [] as RouteRecordRaw[],
      defaultRoutes: [] as RouteRecordRaw[],
      topbarRouters: [] as RouteRecordRaw[],
      sidebarRouters: [] as any[]
    }),
    actions: {
      setRoutes(routes: RouteRecordRaw[]) {
        this.addRoutes = routes
        this.routes = constantRoutes.concat(routes)
      },
      setDefaultRoutes(routes: RouteRecordRaw[]) {
        this.defaultRoutes = constantRoutes.concat(routes)
      },
      setTopbarRoutes(routes: RouteRecordRaw[]) {
        this.topbarRouters = routes
      },
      setSidebarRouters(routes: any[]) {
        this.sidebarRouters = routes
      },
      generateRoutes(): Promise<RouteRecordRaw[]> {
        return new Promise((resolve, reject) => {
          getRouters().then((res: any) => {
            try {
              const data = res.data || []
              // 只做一次深拷贝，其余用引用
              const sdata = JSON.parse(JSON.stringify(data))
              const rdata = JSON.parse(JSON.stringify(data))

              const sidebarRoutes = filterAsyncRouter(sdata)
              const rewriteRoutes = filterAsyncRouter(rdata, false, true)

              const asyncRoutes = filterDynamicRoutes(dynamicRoutes)
              asyncRoutes.forEach(route => { router.addRoute(route) })

              this.setRoutes(rewriteRoutes)
              this.setSidebarRouters(constantRoutes.concat(sidebarRoutes))
              this.setDefaultRoutes(sidebarRoutes)
              this.setTopbarRoutes(rewriteRoutes)
              resolve(rewriteRoutes)
            } catch (e) {
              console.error('路由处理失败:', e)
              reject(e)
            }
          }).catch((error: any) => {
            console.error('获取路由失败:', error)
            reject(error)
          })
        })
      }
    }
  })

function filterAsyncRouter(asyncRouterMap: any[], lastRouter: any = false, type: boolean = false): any[] {
  return asyncRouterMap.filter(route => {
    if (type && route.children) {
      route.children = filterChildren(route.children)
    }
    if (route.component) {
      if (route.component === 'Layout') {
        route.component = Layout
      } else if (route.component === 'ParentView') {
        route.component = ParentView
      } else if (route.component === 'InnerLink') {
        route.component = InnerLink
      } else {
        route.component = loadView(route.component)
      }
    }
    if (route.children != null && route.children && route.children.length) {
      route.children = filterAsyncRouter(route.children, route, type)
    } else {
      delete route['children']
      delete route['redirect']
    }
    return true
  })
}

function filterChildren(childrenMap: any[], lastRouter: any = false): any[] {
  var children: any[] = []
  childrenMap.forEach((el, index) => {
    if (el.children && el.children.length) {
      if (el.component === 'ParentView' && !lastRouter) {
        el.children.forEach((c: any) => {
          c.path = el.path + '/' + c.path
          if (c.children && c.children.length) {
            children = children.concat(filterChildren(c.children, c))
            return
          }
          children.push(c)
        })
        return
      }
    }
    if (lastRouter) {
      el.path = lastRouter.path + '/' + el.path
      if (el.children && el.children.length) {
        children = children.concat(filterChildren(el.children, el))
        return
      }
    }
    children = children.concat(el)
  })
  return children
}

export function filterDynamicRoutes(routes: any[]): any[] {
  const res: any[] = []
  routes.forEach(route => {
    if (route.permissions) {
      if (auth.hasPermiOr(route.permissions)) {
        res.push(route)
      }
    } else if (route.roles) {
      if (auth.hasRoleOr(route.roles)) {
        res.push(route)
      }
    }
  })
  return res
}

// 缓存已解析的组件
const viewCache = new Map<string, () => Promise<any>>()
export const loadView = (view: string): (() => Promise<any>) | undefined => {
  if (viewCache.has(view)) return viewCache.get(view)
  for (const path in modules) {
    const dir = path.split('views/')[1].split('.vue')[0]
    if (dir === view) {
      const loader = () => (modules[path] as () => Promise<any>)()
      viewCache.set(view, loader)
      return loader
    }
  }
  return undefined
}

export default usePermissionStore
