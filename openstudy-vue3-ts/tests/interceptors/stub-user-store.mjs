/** `src/store/modules/user.ts` 的替身：只提供拦截器读的那几个字段。 */
const st = () => (globalThis.__REQ_TEST_STATE__ ??= { userToken: 'dev-token', isGuest: false })

export default function useUserStore() {
  return {
    token: st().userToken || '',
    isGuest: st().isGuest === true,
    name: 'tester',
    logOut: () => Promise.resolve(),
    getInfo: () => Promise.resolve()
  }
}
