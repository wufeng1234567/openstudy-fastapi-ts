import { watch, onScopeDispose, type Ref } from 'vue'

/**
 * 让「深度思考」开关与 DeepSeek 网页端的按钮**双向**同步。
 *
 * 为什么需要单独一层：
 *   ds-free 走浏览器扩展（前端直连 DS 网页版），DS 网页版的「深度思考」
 *   是页面上的一个**按钮**，不是请求参数。所以有三件事必须做：
 *     ① 点开关 → **立即**同步到页面（不能攒到发消息，否则点完没反应）
 *     ② 切到 ds-free → 读页面真实状态回填 UI（消除切换时的不一致）
 *     ③ 在页面那边手动改（或在 DS 页面直接关掉）→ UI **要跟着变**
 *
 * ③ 就是「双向通讯」：扩展当前没有主动推送变更的能力，所以这里用**轮询**
 * 拉取页面状态。轮询仅在 provider === 'deepseek-free' 时运行，
 * 且页面处于后台标签时跳过，避免无谓开销。组件卸载时自动停止。
 *
 * 其它 provider（deepseek / zhipu / siliconflow）的深度思考是**后端传参**
 * （`thinking` / `thinking_mode` / `reasoning_effort`），不走这里。
 *
 * 用法：
 * ```ts
 * const selectedProvider = ref('')
 * const deepThink = ref(false)
 * const { syncBeforeSend } = useDsDeepThinkSync(selectedProvider, deepThink)
 * await syncBeforeSend()   // 发请求前兜底（幂等，可省略）
 * ```
 *
 * @param provider 当前选中的 provider。可以是 Ref，也可以直接传 getter
 *                 （如 `() => aiForm.model`，省掉一个 computed 导入）。
 *                 ⚠️ **用 getter 形式时，本函数必须写在被引用变量声明之后** ——
 *                 `watch(source, cb)` 在创建时会同步求值一次 source 来收集依赖，
 *                 写反了就会撞 TDZ（`Cannot access 'aiForm' before initialization`）
 *                 → 组件白屏，而且 SFC 编译查不出来。正确写法：
 *                 ```ts
 *                 const aiForm = ref({ model: '' })            // 先声明
 *                 useDsDeepThinkSync(() => aiForm.model, deepThink)  // 再调用
 *                 ```
 * @param thinking 深度思考开关
 * @param persistKey 传了就顺带把开关持久化到 localStorage
 * @param pollInterval 轮询间隔毫秒，默认 1200
 */
export function useDsDeepThinkSync(
  provider: Ref<string> | (() => string | undefined),
  thinking: Ref<boolean>,
  persistKey?: string,
  pollInterval = 1200
) {
  const getProvider = (): string | undefined =>
    typeof provider === 'function' ? provider() : provider?.value

  const isDsFree = () => getProvider() === 'deepseek-free'

  // 标记「这次变化来自远端回填」——避免再推回页面，形成来回抖动
  let applyingRemote = false
  let timer: ReturnType<typeof setInterval> | null = null
  // watch 的停止函数：正常路径由组件作用域自动回收，兜底路径（见下）靠这个手动回收
  let stopThinkingWatch: (() => void) | null = null
  let stopProviderWatch: (() => void) | null = null

  async function readRemote(): Promise<boolean | null> {
    if (!isDsFree()) return null
    try {
      const { getDeepThink } = await import('@/utils/ds-proxy')
      return await getDeepThink()
    } catch {
      // 扩展未就绪 / DS 页面未打开：静默，等下一轮
      return null
    }
  }

  /** ③ 拉取页面状态；有变化就回填 UI */
  async function pullRemote() {
    if (typeof document !== 'undefined' && document.hidden) return
    const on = await readRemote()
    if (typeof on === 'boolean' && on !== thinking.value) {
      applyingRemote = true
      thinking.value = on
      // 等 watch 的同步回调跑完后复位
      setTimeout(() => {
        applyingRemote = false
      }, 0)
    }
  }

  function startPolling() {
    if (timer !== null) return
    timer = setInterval(pullRemote, pollInterval)
  }

  function stopPolling() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  /** ① 正向：点开关 → 立即同步到页面 */
  async function onThinkingChange(val: boolean) {
    if (persistKey) localStorage.setItem(persistKey, val ? '1' : '0')
    if (applyingRemote) return // 远端回填触发的，不要再推回去
    if (!isDsFree()) return
    try {
      const { setDeepThink } = await import('@/utils/ds-proxy')
      await setDeepThink(val)
    } catch (e) {
      console.warn('[ds-free] 同步深度思考开关失败:', e)
    }
  }

  /** ② 切到 ds-free：读一次真实状态 + 启动轮询；切走则停止 */
  async function onProviderChange(val: string | undefined) {
    if (val !== 'deepseek-free') {
      stopPolling()
      return
    }
    await pullRemote()
    startPolling()
  }

  /**
   * 建立两个 watch。
   *
   * ⚠️ 必须写在调用方所传变量**声明之后**：`watch(source, cb)`（无论有没有
   * `immediate`）在创建时会**同步求值一次** source 以收集依赖。调用方常写成
   * `useDsDeepThinkSync(() => aiForm.model, deepThink)`，若这个调用写在
   * `const aiForm = ref(...)` 之前，同步求值就会撞 TDZ 让组件白屏。
   */
  function createWatchers() {
    if (stopProviderWatch) return
    stopThinkingWatch = watch(thinking, onThinkingChange)
    stopProviderWatch = watch(getProvider, onProviderChange)
    // `{ immediate: true }` 的等价物：自己先读一次并处理
    void onProviderChange(getProvider())
  }

  // 正常路径（顺序写对）：setup 期间同步建立，watcher 随组件作用域自动回收。
  //
  // 兜底路径（顺序写反）：同步建立会撞 TDZ。退一步延迟到微任务再建立 —— setup 是
  // 同步跑完的，微任务执行时调用方的 ref 一定已初始化，于是只是「晚一拍生效」，
  // 不会白屏。延迟建立的 watcher 不在组件作用域里，统一由下面的 onScopeDispose
  // 销毁（那条是在 setup 期间同步注册的，作用域是准的，所以回收是可靠的）。
  try {
    createWatchers()
  } catch (e) {
    if (!(e instanceof ReferenceError)) throw e
    console.warn(
      '[useDsDeepThinkSync] 首次读取 provider 失败 —— 多半是把本函数写在了它引用的 ' +
        'ref 之前（TDZ）。已延迟到下一个 tick 重试；建议把它移到相关 ref 声明之后。',
      e
    )
    void Promise.resolve().then(() => {
      try {
        createWatchers()
      } catch (err) {
        console.error('[useDsDeepThinkSync] 延迟建立 watch 仍然失败：', err)
      }
    })
  }

  onScopeDispose(() => {
    stopProviderWatch?.()
    stopThinkingWatch?.()
    stopPolling()
  })

  /**
   * 发送前兜底同步：防止用户在轮询间隔内刚改了页面状态。
   * 幂等 —— 状态一致时扩展直接回 changed:false，无副作用。
   */
  async function syncBeforeSend(): Promise<void> {
    if (!isDsFree()) return
    try {
      const { setDeepThink } = await import('@/utils/ds-proxy')
      await setDeepThink(thinking.value)
    } catch (e) {
      console.warn('[ds-free] 发送前同步深度思考失败:', e)
    }
  }

  return { syncBeforeSend, isDsFree, pullRemote }
}
