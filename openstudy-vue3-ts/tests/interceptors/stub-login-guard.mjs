/** `src/utils/loginGuard.ts` 的替身：只记录「被提示过一次」，不弹窗、不跳转。 */
const st = () => (globalThis.__REQ_TEST_STATE__ ??= { prompts: [] })

export function promptLogin(action) {
  st().prompts.push(action)
  return Promise.resolve(false)
}

export function ensureLogin(action) {
  const s = st()
  if (s.userToken && !s.isGuest) return Promise.resolve(true)
  return promptLogin(action)
}
