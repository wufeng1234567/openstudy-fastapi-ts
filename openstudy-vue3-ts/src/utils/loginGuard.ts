import { ElMessageBox } from 'element-plus'
import router from '@/router'
import useUserStore from '@/store/modules/user'

/** 当前是否存在登录态（含游客） */
export function hasLoginToken(): boolean {
  return !!useUserStore().token
}

/** 当前是否为游客只读账号 */
export function isGuestUser(): boolean {
  const userStore = useUserStore()
  return !!userStore.token && userStore.isGuest
}

/**
 * 需要登录才能继续的操作统一入口。
 *
 * 普通登录用户：直接返回 true，不打断原操作；
 * 未登录 / 游客：弹出「去登录」提示，确认后跳到登录页并带上 redirect。
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

  if (userStore.token && !userStore.isGuest) {
    return true
  }

  const content = userStore.token
    ? `游客仅可浏览，登录后才能${actionName}。`
    : `请先登录后再${actionName}。`

  try {
    await ElMessageBox.confirm(content, '温馨提示', {
      confirmButtonText: '去登录',
      cancelButtonText: '再看看',
      type: 'warning',
      closeOnClickModal: false
    })
  } catch (e) {
    return false
  }

  // 注意：不退出游客态。路由守卫会允许游客进入登录页，登录成功后 token 自然被新账号覆盖。
  const redirect = router.currentRoute.value.fullPath || '/front/index'
  router.push(`/login?redirect=${encodeURIComponent(redirect)}`)
  return false
}
