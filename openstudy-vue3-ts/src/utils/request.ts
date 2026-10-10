/**
 * HTTP 请求工具 (TypeScript 版本)
 */

import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElNotification, ElMessageBox, ElMessage, ElLoading } from 'element-plus'
import { getToken } from '@/utils/auth'
import errorCode from '@/utils/errorCode'
import { tansParams, blobValidate } from '@/utils/ruoyi'
import cache from '@/plugins/cache'
import { saveAs } from 'file-saver'
import useUserStore from '@/store/modules/user'

let downloadLoadingInstance: ReturnType<typeof ElLoading.service>;
// 是否显示重新登录
export const isRelogin = { show: false };

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'

// 创建 axios 实例
const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API,
  timeout: 30000
})

// 登录/注册/退出本身不能被“游客只读”拦截
const AUTH_APIS = ['/login', '/register', '/quickLogin', '/logout']

function isAuthApi(url: string): boolean {
  return AUTH_APIS.some(api => url === api || url.startsWith(api + '?') || url.includes(api + '/'))
}

function redirectToLoginPage() {
  // 不退出游客态；/login 已允许游客进入，登录成功后 token 会被新账号覆盖
  const redirect = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/login?redirect=${redirect}`
}

// request 拦截器
service.interceptors.request.use(
  (config: AxiosRequestConfig) => {
    // 是否需要设置 token
    const isToken = (config.headers || {}).isToken === false
    // 是否需要防止数据重复提交
    const isRepeatSubmit = (config.headers || {}).repeatSubmit === false
    if (getToken() && !isToken) {
      config.headers['Authorization'] = 'Bearer ' + getToken()
    }

    // 游客 / 未登录用户只能浏览 GET；所有写操作先统一提示登录，避免绕开页面按钮直接调接口
    const method = (config.method || '').toLowerCase()
    const url = config.url || ''
    const isWrite = ['post', 'put', 'delete'].includes(method)
    if (isWrite && !isAuthApi(url)) {
      const userStore = useUserStore()
      if (!userStore.token || userStore.isGuest) {
        ElMessageBox.confirm(
          userStore.token ? '游客仅可浏览，登录后才能进行该操作。' : '请先登录后再进行该操作。',
          '温馨提示',
          {
            confirmButtonText: '去登录',
            cancelButtonText: '再看看',
            type: 'warning',
            closeOnClickModal: false
          }
        ).then(() => redirectToLoginPage()).catch(() => {})
        return Promise.reject({ __needLogin: true, message: '需要登录' })
      }
    }
    // get 请求映射 params 参数
    if (config.method === 'get' && config.params) {
      let url = config.url + '?' + tansParams(config.params)
      url = url.slice(0, -1)
      config.params = {}
      config.url = url
    }
    if (!isRepeatSubmit && (config.method === 'post' || config.method === 'put')) {
      const chatApis = ['/system/chat/', '/ai/sessions']
      const isChatApi = chatApis.some(url => config.url && config.url.includes(url))
      // FormData（文件上传）无法 JSON.stringify，跳过防重复检查
      const isFormData = config.data instanceof FormData

      if (isChatApi || isFormData) {
        return config
      }

      const requestObj = {
        url: config.url,
        data: typeof config.data === 'object' ? JSON.stringify(config.data) : config.data,
        time: new Date().getTime()
      }
      const requestSize = Object.keys(JSON.stringify(requestObj)).length // 请求数据大小
      const limitSize = 5 * 1024 * 1024 // 限制存放数据5M
      if (requestSize >= limitSize) {
        console.warn(`[${config.url}]: ` + '请求数据大小超出允许的5M限制，无法进行防重复提交验证。')
        return config
      }
      if (isChatApi) {
        return config
      }
      const sessionObj = cache.session.getJSON('sessionObj')
      if (sessionObj === undefined || sessionObj === null || sessionObj === '') {
        cache.session.setJSON('sessionObj', requestObj)
      } else {
        const s_url = sessionObj.url // 请求地址
        const s_data = sessionObj.data // 请求数据
        const s_time = sessionObj.time // 请求时间
        /*
         * 高频重复提交 —— **静默拦下**（用户 2026-10-11：「不提示就行，改成静默拦截高频点击，
         * 防抖节流那种」）。
         *
         * 判定：同 url + 同 data + 距上次 < `interval`（500ms）视为「同一瞬间的连点」，
         * 直接拦下**不再放行**（"静默节流"：连点只发第一发，后续同请求在窗口内丢弃）。
         *
         * ⚠️ **不再弹任何提示**（旧版会弹「操作太快了，请稍候再试」/「数据正在处理，请勿重复提交」）。
         *    那条提示误伤面太大（草稿自动保存 `PUT /notes/note/draft`、路由切换后的连续同名请求
         *    都会命中），弹出来像"系统坏了"。现在改为：拦下 + 仅一条 `console.warn` 便于排查，
         *    用户侧无感。调用方 `.catch()` 的静默处理能接住这个 `reject`（带 `__repeatSubmit` 标记）。
         *    真正需要幂等的场景（答题上报失败重试）已由 clientToken 在前面豁免（见上）。
         */
        const interval = 500 // 间隔时间(ms)，小于此时间视为重复提交（节流窗口）
        if (s_data === requestObj.data && requestObj.time - s_time < interval && s_url === requestObj.url) {
          console.warn(`[${s_url}]: 高频重复提交，已静默拦截（距上次同请求 ${requestObj.time - s_time}ms）`)
          return Promise.reject({ __repeatSubmit: true, message: '重复提交已拦截' })
        }
        cache.session.setJSON('sessionObj', requestObj)
      }
    }
    return config
  },
  (error) => {
    console.log(error)
    Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (res: AxiosResponse) => {
    // 未设置状态码则默认成功状态
    const code: number = res.data.code || 200
    // 获取错误信息
    const msg: string = errorCode[code] || res.data.msg || errorCode['default']

    // 二进制数据则直接返回
    if (res.request.responseType === 'blob' || res.request.responseType === 'arraybuffer') {
      return res.data
    }
    if (code === 401) {
      if (!isRelogin.show) {
        isRelogin.show = true
        ElMessageBox.confirm('登录状态已过期，您可以继续留在该页面，或者重新登录', '系统提示', {
          confirmButtonText: '重新登录',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          isRelogin.show = false
          useUserStore().logOut().then(() => {
            location.href = '/index'
          })
        }).catch(() => {
          isRelogin.show = false
        })
      }
      return Promise.reject('无效的会话，或者会话已过期，请重新登录。')
    } else if (code === 500) {
      ElMessage({ message: msg, type: 'error' })
      return Promise.reject(new Error(msg))
    } else if (code === 601) {
      ElMessage({ message: msg, type: 'warning' })
      return Promise.reject(new Error(msg))
    } else if (code !== 200) {
      ElNotification.error({ title: msg })
      return Promise.reject('error')
    } else {
      return Promise.resolve(res.data)
    }
  },
  (error) => {
    // 游客/未登录写操作被前置拦截：登录弹窗已处理，不再重复报错
    if (error && error.__needLogin) {
      return Promise.reject(error)
    }
    // 本地「静默节流」拦下的高频重复提交：不弹任何提示（拦截处已 console.warn），直接静默 reject
    if (error && error.__repeatSubmit) {
      return Promise.reject(error)
    }
    console.log('err' + error)
    let { message } = error
    if (message == 'Network Error') {
      message = '后端接口连接异常'
    } else if (message.includes('timeout')) {
      message = '系统接口请求超时'
    } else if (message.includes('Request failed with status code')) {
      message = '系统接口' + message.substr(message.length - 3) + '异常'
    }
    ElMessage({ message: message, type: 'error', duration: 5 * 1000 })
    return Promise.reject(error)
  }
)

// 通用下载方法
export function download(url: string, params: any, filename: string, config?: any) {
  downloadLoadingInstance = ElLoading.service({ text: '正在下载数据，请稍候', background: 'rgba(0, 0, 0, 0.7)' })
  // 后端导出接口的筛选参数统一声明为 Query(...)，必须拼到 URL 上；
  // 早期实现把参数塞进 form-urlencoded 请求体，FastAPI 读不到 →「导出」永远不带筛选条件。
  const query = params ? tansParams(params).replace(/&$/, '') : ''
  const fullUrl = query ? url + (url.includes('?') ? '&' : '?') + query : url
  return service.post(fullUrl, null, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    responseType: 'blob',
    ...config
  }).then(async (data) => {
    const isBlob = blobValidate(data)
    if (isBlob) {
      const blob = new Blob([data])
      saveAs(blob, filename)
    } else {
      const resText = await data.text()
      const rspObj = JSON.parse(resText)
      const errMsg = errorCode[rspObj.code] || rspObj.msg || errorCode['default']
      ElMessage.error(errMsg)
    }
    downloadLoadingInstance.close()
  }).catch((r) => {
    console.error(r)
    ElMessage.error('下载文件出现错误，请联系管理员！')
    downloadLoadingInstance.close()
  })
}

export default service
