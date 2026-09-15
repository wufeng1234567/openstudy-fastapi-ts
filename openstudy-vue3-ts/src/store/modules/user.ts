import { defineStore } from 'pinia'
import { login, logout, getInfo, quickLogin as quickLoginApi } from '@/api/login'
import { getToken, setToken, removeToken } from '@/utils/auth'
import defAva from '@/assets/images/profile.jpg'
import usePermissionStore from '@/store/modules/permission'
import router from '@/router'
import { isHttp } from '@/utils/validate'

interface LoginUserInfo {
  username: string
  password: string
  code: string
  uuid: string
}

const useUserStore = defineStore(
  'user',
  {
    state: () => ({
      token: getToken(),
      id: '' as string | number,
      name: '',
      nickName: '',
      avatar: '',
      roles: [] as string[],
      permissions: [] as string[]
    }),
    getters: {
      /** 游客账号（只读）：用户名 guest 或绑定 visitor 角色 */
      isGuest: (state) => state.name === 'guest' || state.roles.includes('visitor')
    },
    actions: {
      // 拿到 token 后的公共流程：写入 token → 拉取用户信息 → 生成并注册动态路由
      async _afterLogin(token: string) {
        setToken(token)
        this.token = token

        // 获取用户信息
        await this.getInfo()

        // 生成路由并注册
        const permissionStore = usePermissionStore()
        const accessRoutes = await permissionStore.generateRoutes()
        accessRoutes.forEach(route => {
          if (!isHttp(route.path)) {
            router.addRoute(route)
          }
        })
      },

      async login(userInfo: LoginUserInfo) {
        const username = userInfo.username.trim()
        const password = userInfo.password
        const code = userInfo.code
        const uuid = userInfo.uuid

        // 1. 登录获取 token
        const res = await login(username, password, code, uuid)

        // 2. 公共流程
        await this._afterLogin(res.data.token)
      },

      // 演示账号一键登录（无需密码 / 验证码）
      // account: user1 / user2 / admin
      async quickLogin(account: string) {
        const res = await quickLoginApi(account)
        await this._afterLogin(res.data.token)
      },

      async getInfo() {
        const res = await getInfo()
        const user = res.data.user
        const avatar = (user.avatar == "" || user.avatar == null) ? defAva : import.meta.env.VITE_APP_BASE_API + user.avatar

        if (res.data.roles && res.data.roles.length > 0) {
          this.roles = res.data.roles
          this.permissions = res.data.permissions
        } else {
          this.roles = ['ROLE_DEFAULT']
        }
        this.id = user.userId
        this.name = user.userName
        this.nickName = user.nickName || user.userName
        this.avatar = avatar
        return res.data
      },

      clearState() {
        this.token = ''
        this.roles = []
        this.permissions = []
        this.name = ''
        this.nickName = ''
        this.avatar = ''
        removeToken()
        const permissionStore = usePermissionStore()
        permissionStore.$reset()
      },

      async logOut() {
        const savedToken = this.token
        this.clearState()
        try {
          sessionStorage.clear()
        } catch (e) {
          console.warn('sessionStorage 清除失败:', e)
        }
        const projectKeys = ['user', 'permission', 'tagsView', 'settings']
        projectKeys.forEach(key => {
          try {
            if (localStorage.getItem(key)) {
              localStorage.removeItem(key)
            }
          } catch (e) {
            console.warn(`localStorage.${key} 清除失败:`, e)
          }
        })
        logout(savedToken).catch(() => {})
      }
    }
  })

export default useUserStore
