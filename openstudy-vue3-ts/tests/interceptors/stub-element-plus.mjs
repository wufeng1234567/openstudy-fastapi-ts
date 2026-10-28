/**
 * 测试替身：**只替浏览器/UI 边界**，不替被测逻辑。
 *
 * 被测的是 `src/utils/request.ts` 里的 axios 拦截器链本身；而 axios 实例、它的
 * adapter（`axios/lib/adapters/http`，走真实 TCP）都是真的。
 * 这里替掉的只有：
 *   · element-plus 的提示（ElMessage / ElNotification / ElMessageBox / ElLoading）
 *   · js-cookie（`getToken`，Node 里没有 document.cookie）
 *   · sessionStorage 缓存（防重复提交用的 `plugins/cache`）
 *   · pinia 用户 store、登录守卫（只需要一处可断言的副作用记录）
 * 替换件把副作用写到 `globalThis.__REQ_TEST_STATE__`，由测试脚本读取断言。
 */
const st = () => (globalThis.__REQ_TEST_STATE__ ??= {
  token: 'dev-token',
  userToken: 'dev-token',
  isGuest: false,
  prompts: [],
  messages: [],
  notifications: [],
  box: [],
})
export const ElMessage = (o) => {
  st().messages.push(o)
}
ElMessage.error = (o) => ElMessage({ message: o, type: 'error' })
ElMessage.success = (o) => ElMessage({ message: o, type: 'success' })
ElMessage.warning = (o) => ElMessage({ message: o, type: 'warning' })
ElMessage.info = (o) => ElMessage({ message: o, type: 'info' })

export const ElNotification = {
  error: (o) => st().notifications.push({ kind: 'error', ...o }),
  success: (o) => st().notifications.push({ kind: 'success', ...o }),
  warning: (o) => st().notifications.push({ kind: 'warning', ...o }),
  info: (o) => st().notifications.push({ kind: 'info', ...o }),
}

export const ElMessageBox = {
  // 返回**永不 settle** 的 promise：既不确认也不取消，让被测代码继续往下走，
  // 同时避免命中「确认后 window.location 跳转」那条分支（Node 里没有 location）。
  confirm: (message, title, opts) => {
    st().box.push({ message, title, opts })
    return new Promise(() => {})
  },
  prompt: () => new Promise(() => {}),
  alert: () => new Promise(() => {}),
}

export const ElLoading = {
  service: () => ({ close: () => {} }),
}

export default {}
