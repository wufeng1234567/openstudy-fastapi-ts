/**
 * `src/plugins/cache.ts` 的替身：原实现直接读写 `sessionStorage` / `localStorage`，
 * Node 里这两个全局不存在（`!sessionStorage` 会直接 ReferenceError）。
 * 行为等价：内存里的 key-value + JSON 编解码，防重复提交的判断逻辑仍是真的。
 */
function mkCache(store) {
  return {
    set(key, value) {
      if (key == null || value == null) return
      store.set(key, value)
    },
    get(key) {
      if (key == null) return null
      return store.has(key) ? store.get(key) : null
    },
    setJSON(key, jsonValue) {
      if (jsonValue != null) this.set(key, JSON.stringify(jsonValue))
    },
    getJSON(key) {
      const v = this.get(key)
      return v != null ? JSON.parse(v) : undefined
    },
    remove(key) {
      store.delete(key)
    }
  }
}

const st = () => (globalThis.__REQ_TEST_STATE__ ??= {})

// 每个 Vite 实例一份；同一次进程内跨 ssrLoadModule 保持一致
st().sessionStore ??= new Map()
st().localStore ??= new Map()

export default {
  session: mkCache(st().sessionStore),
  local: mkCache(st().localStore)
}
