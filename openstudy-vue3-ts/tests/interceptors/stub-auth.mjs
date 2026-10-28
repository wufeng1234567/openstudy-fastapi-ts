/** `src/utils/auth.ts` 的替身：Node 里没有 `document.cookie`（js-cookie 依赖它）。 */
const st = () => (globalThis.__REQ_TEST_STATE__ ??= { token: 'dev-token' })

export function getToken() {
  return st().token || undefined
}
export function setToken(t) {
  st().token = t
}
export function removeToken() {
  st().token = ''
}
