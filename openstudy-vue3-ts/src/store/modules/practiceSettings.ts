import { defineStore } from 'pinia'
import type {
  ModuleType,
  ModuleSettings,
  PracticeSettings,
  PracticeModuleConfig,
  MockExamConfig,
  MockExamRecord
} from '@/types'

/**
 * localStorage 键前缀
 *
 * ⚠️ **必须按用户分区**（2026-10-22 修的串号 bug）
 *
 * 原来是一个固定的 `practice-settings` 键，所有人共用。后果实测过：
 *   同一浏览器先让 user1 考一场，退出登录换 user2 →
 *   user2 的「考试记录」里**直接出现 user1 的卷子**（bankName 都能看到）；
 *   再让 user2 考一场，两人的记录就混在同一个数组里，
 *   切回 user1 还能看到 user2 的记录。
 *
 * 这不仅是隐私问题，也让"我的考试记录"这个功能失去意义 ——
 * 用户点开一条记录，看到的是别人的成绩单。
 *
 * 现在 key = `practice-settings_{userId}`，与 `os_practice_draft_*`、
 * `os_mock_session_*` 的分区方式保持一致（那两处早就带了 userId）。
 */
const STORAGE_KEY_PREFIX = 'practice-settings'

/** 旧版全局键（迁移用；迁移完成后删除） */
const LEGACY_STORAGE_KEY = 'practice-settings'

/**
 * 当前用户 id（分区依据）
 *
 * ⚠️⚠️ 这里踩过一个坑，务必看清（2026-10-22）
 *
 * 第一版我写的是 `JSON.parse(localStorage.getItem('user')).id` —— 想当然地以为
 * 登录后会像 RuoYi 原版那样把用户信息持久化到 localStorage。
 * **实际这个项目根本不写 `user` 这个键**（`store/modules/user.ts` 里没有任何
 * `localStorage.setItem('user', ...)`），于是它永远是 `null`，
 * 所有用户的数据都被塞进 `practice-settings_0` 匿名区 —— 等于**没做隔离**。
 * 实测才发现：user1 和 user2 的记录还是混在一起。
 *
 * 可靠来源只有一个：`userStore.id`，它在 `getInfo()` 之后被赋值。
 * 但本文件是 store 定义模块，**不能**在 `state()` 里 `useUserStore()`
 * （Pinia 要求 store 创建完成后才能互相取用，且会形成循环依赖）。
 *
 * 所以改成"由外部注入"：外壳 `layout/front.vue` 在用户 id 变化时
 * 调 `setActiveUserId(id)`，这里记在模块级变量里供读写分区使用。
 * 未注入时退回 `null`（匿名区），保证不会串到任何真实用户身上。
 */
let activeUserId: string | number | null = null

/**
 * 设置当前活跃用户（由外壳在登录态变化时调用）
 *
 * @returns 用户是否发生了变化（`true` 时调用方应随即 `reloadForCurrentUser()`）
 */
export function setActiveUserId(id: string | number | null | undefined): boolean {
  const next = id === undefined || id === null || id === '' ? null : id
  const changed = String(next ?? '') !== String(activeUserId ?? '')
  activeUserId = next
  return changed
}

/** 读当前活跃用户 id */
export function getActiveUserId(): string | number | null {
  return activeUserId
}

/** 生成按用户分区的存储键 */
function storageKeyFor(userId: string | number | null): string {
  return `${STORAGE_KEY_PREFIX}_${userId ?? 0}`
}

/** 当前用户对应的存储键（运行时动态取，用户可能中途换账号） */
function currentStorageKey(): string {
  return storageKeyFor(activeUserId)
}


/**
 * 模拟考试的默认配置（2026-10-22）
 *
 * 刻意做成"一份可用的默认考卷"而不是空白：
 *   用户点「模拟考试」应当能直接开始，而不是先被丢进一个空表单。
 *   默认值参考常见考试结构：单选多、判断少、多选居中；总分 100。
 *   若某题型在该题库里没有，组卷时会自动跳过（见 `PracticeComponent` 的组卷逻辑）。
 */
export const DEFAULT_MOCK_EXAM: MockExamConfig = {
  typeRows: [
    { type: 'single', count: 20, score: 2 },
    { type: 'multiple', count: 10, score: 4 },
    { type: 'truefalse', count: 10, score: 2 }
  ],
  timeLimit: 60,
  passScore: 60,
  shuffleOptions: true,
  multipleMode: 'strict',
  partialRatio: 0.5
}

const defaultModules: PracticeModuleConfig = {
  sequential: {
    questionCount: 10,
    shuffleOptions: false,
    autoNextOnCorrect: false,
    onlyWrong: false,
    practiceMode: 'practice',
    isOverviewMode: false,
    overviewScrollIndex: 0,
    markedQuestions: []
  },
  random: {
    questionCount: 10,
    shuffleOptions: true,
    autoNextOnCorrect: false,
    onlyWrong: false,
    practiceMode: 'practice',
    isOverviewMode: false,
    overviewScrollIndex: 0,
    markedQuestions: []
  },
  custom: {
    questionCount: 10,
    shuffleOptions: false,
    autoNextOnCorrect: false,
    /*
     * ⚠️ `custom` = 「错题练习」（2026-10-20 由「自定义练习」改造）。
     *
     * 为什么保留 `custom` 这个 key 而不新造 `wrong`：
     *   路由 `:moduleType` 的值、`PracticeSettings` 的模块 tabs、localStorage 存量
     *   都按 `custom` 存；改名要同时动路由校验、存量迁移、以及一堆
     *   `moduleType === 'custom'` 判断 —— 而用户看到的只是标题文案。
     *   key 是内部标识，文案才是产品语义。（历史上还有过一次 `wrong → custom`
     *   的迁移，见 `loadFromStorage`，可见这个 key 反复改名的代价。）
     *
     * `onlyWrong: true` 是**默认值**不是硬编码：用户仍可在设置里关掉
     * （他可能想「这个题库全刷一遍，但优先错题」）。这个默认值就是
     * 「错题练习」与「顺序练习」唯一的语义差别 —— 也是它值得单独占一个入口的原因。
     */
    onlyWrong: true,
    practiceMode: 'practice',
    isOverviewMode: false,
    overviewScrollIndex: 0,
    markedQuestions: []
  },
  mock: {
    questionCount: 10,
    shuffleOptions: true,
    autoNextOnCorrect: false,
    onlyWrong: false,
    practiceMode: 'exam',
    isOverviewMode: false,
    overviewScrollIndex: 0,
    markedQuestions: [],
    examTimeLimit: 60,
    // 模拟考试的按题型组卷配置（2026-10-22）
    mockExam: JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM))
  }
}

function loadFromStorage(): PracticeSettings | null {
  try {
    /*
     * 读取顺序：先读**当前用户**的分区键，读不到再看旧全局键（迁移）。
     *
     * 迁移策略（只做一次）：
     *   旧版是单一 `practice-settings`，无法知道它属于谁 ——
     *   按"谁先登录就归谁"处理：第一次读到旧键的用户接管它，
     *   随后把旧键删掉，避免后登录的另一个用户又把同一份数据搬走。
     *   这是牺牲一点历史数据的确定性，换取"之后永不再串号"。
     */
    const key = currentStorageKey()
    let saved = localStorage.getItem(key)

    if (!saved) {
      const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
      if (legacy) {
        // 旧数据整体过户给当前用户
        saved = legacy
        try {
          localStorage.setItem(key, legacy)
          localStorage.removeItem(LEGACY_STORAGE_KEY)
        } catch {
          /* 写不进去也不影响本次读取 */
        }
      }
    }

    if (saved) {
      const data: any = JSON.parse(saved)
      // 兼容旧数据：wrong → custom
      if (data.modules) {
        if (data.modules.wrong && !data.modules.custom) {
          data.modules.custom = { ...defaultModules.custom, ...data.modules.wrong }
          delete data.modules.wrong
        }
        // 为旧模块补上 onlyWrong 字段
        Object.keys(data.modules).forEach((key: string) => {
          if (data.modules[key].onlyWrong === undefined) {
            data.modules[key].onlyWrong = false
          }
          if (data.modules[key].examTimeLimit === undefined) {
            data.modules[key].examTimeLimit = 60
          }
          if (data.modules[key].isOverviewMode === undefined) {
            data.modules[key].isOverviewMode = false
          }
        })

        /*
         * 存量迁移：给 mock 模块补上 `mockExam`（2026-10-22）
         *
         * 老用户的 localStorage 里只有 `examTimeLimit`，没有按题型组卷的配置。
         * 不补的话，进「模拟考试」会读到 `undefined.mockExam.typeRows` 直接报错
         * （考场页第一件事就是读 typeRows 来组卷）。
         *
         * 这里用**深拷贝**补默认值：不能直接引用 `DEFAULT_MOCK_EXAM`，
         * 否则用户 A 改了自己的考题数，会顺着同一个对象改到默认值上。
         */
        if (data.modules.mock && !data.modules.mock.mockExam) {
          data.modules.mock.mockExam = JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM))
          // 把老的「考试时间」迁移进新配置，用户之前的设置不该被丢掉
          if (typeof data.modules.mock.examTimeLimit === 'number') {
            data.modules.mock.mockExam.timeLimit = data.modules.mock.examTimeLimit
          }
        }
        // 新配置里缺字段时补齐（可能来自更早的中间版本）
        if (data.modules.mock && data.modules.mock.mockExam) {
          data.modules.mock.mockExam = {
            ...JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM)),
            ...data.modules.mock.mockExam
          }
          if (!Array.isArray(data.modules.mock.mockExam.typeRows) ||
              data.modules.mock.mockExam.typeRows.length === 0) {
            data.modules.mock.mockExam.typeRows =
              JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM.typeRows))
          }
        }

        /*
         * ⚠️⚠️ 存量迁移：`custom` 从「自定义练习」变成「错题练习」（2026-10-20）
         *
         * 新默认值是 `onlyWrong: true`，但**老用户 localStorage 里存的是 false**
         * （上一行 `onlyWrong === undefined → false` 那段是给更老的库补的，
         *  而「自定义练习」时期默认也是 false）。只在 `defaultModules` 里改默认值
         * 对**已打开过设置面板的用户完全无效** —— 他们进「错题练习」看到的仍是全库题目，
         * 会以为这个改造没生效。
         *
         * 这里用一次性迁移标记 `migrations.wrongModeV1`：
         * 迁移**只跑一次**，之后用户自己关掉 `onlyWrong` 是明确的选择，不再覆盖。
         * （不能每次启动都强制置 true —— 那等于不让用户关。）
         *
         * ⚠️ 迁移结果**必须立刻写回 localStorage**（见下面的 `_migrated` 分支）：
         *    第一版只改了内存里的 `data` 就 return，结果
         *    ① 用户首屏看到的是 true，但下次刷新又回到 false（因为盘上还是 false）；
         *    ② `migrations` 标记也没落盘，于是每次启动都重跑迁移 ——
         *    用户手动关掉「只刷错题」后，下次进来又被强制打开，完全无法理解。
         *    由 `_verify-wrong-mode.mjs` 的 B3/B4 抓到。
         */
        let _migrated = false
        if (!data.migrations || data.migrations.wrongModeV1 !== true) {
          if (data.modules.custom) {
            data.modules.custom.onlyWrong = true
          }
          data.migrations = { ...(data.migrations || {}), wrongModeV1: true }
          _migrated = true
        }
        if (_migrated) {
          try {
            localStorage.setItem(currentStorageKey(), JSON.stringify(data))
          } catch (e) {
            console.warn('刷题设置迁移落盘失败（不影响使用）:', e)
          }
        }
      }
      return data as PracticeSettings
    }
  } catch (e) {
    console.warn('读取刷题设置失败:', e)
  }
  return null
}

function saveToStorage(state: PracticeSettings) {
  try {
    localStorage.setItem(currentStorageKey(), JSON.stringify({
      currentBankId: state.currentBankId,
      currentBankName: state.currentBankName,
      modules: state.modules,
      /*
       * ⚠️ `migrations` 必须一起存（2026-10-20）。
       *
       * 不存的话会出现一个很难查的 bug：`loadFromStorage` 判定
       * 「没有 wrongModeV1 标记 → 把 custom.onlyWrong 强制置 true」，
       * 而用户在设置里关掉它之后，`saveToStorage` 把标记丢了 →
       * 下次启动又跑一次迁移 → **用户关不掉「只刷错题」**，
       * 而且他每次关完重进都会发现又开了，完全无法理解。
       */
      migrations: (state as any).migrations || {},
      /*
       * 模拟考试历史（2026-10-22）
       *
       * 与 `modules` 分开持久化：历史是**用户数据**，不是模块偏好。
       * `resetModuleSettings('mock')` / `resetAllSettings()` 都不该把它一起清掉
       * （后者的语义见该 action 的注释 —— 它只重置"设置"，不删用户考卷）。
       */
      mockExamHistory: Array.isArray((state as any).mockExamHistory)
        ? (state as any).mockExamHistory
        : []
    }))
  } catch (e) {
    console.warn('保存刷题设置失败:', e)
  }
}

const usePracticeSettingsStore = defineStore('practiceSettings', {
  state: (): PracticeSettings => {
    const saved = loadFromStorage()
    return {
      currentBankId: saved?.currentBankId ?? null,
      currentBankName: saved?.currentBankName ?? '',
      modules: saved?.modules ? saved.modules : JSON.parse(JSON.stringify(defaultModules)),
      // 与 `saveToStorage` 里的 `migrations` 成对出现（见那里的注释）
      migrations: (saved as any)?.migrations || {},
      mockExamHistory: Array.isArray((saved as any)?.mockExamHistory)
        ? (saved as any).mockExamHistory
        : [],
      /*
       * 本份数据属于哪个用户（`null` = 匿名区）
       *
       * ⚠️ 不能省（2026-10-22 串号 bug 的第二层）
       *
       * `state()` 只在 store **首次创建**时执行一次，之后整个 SPA 生命周期
       * 都是同一个实例。用户在同一个浏览器里退出登录、换个账号登录，
       * store 不会重建 —— 内存里还是上一个人的 `mockExamHistory` 与模块偏好。
       *
       * 所以要把"这份数据是谁的"记在 state 里，由外壳在用户变化时比对；
       * 不一致就调 `reloadForCurrentUser()` 从新用户的分区键重读。
       */
      ownerUserId: activeUserId as any
    } as PracticeSettings
  },
  actions: {
    /**
     * 换账号后重新加载本用户的数据
     *
     * ⚠️ 为什么必须有这个（2026-10-22 串号 bug）
     *
     * `state()` 只在 store 创建时跑一次，整个 SPA 生命周期同一个实例。
     * 同一浏览器里 user1 退出、user2 登录，store 不会重建 ——
     * 于是 user2 看到的是 user1 的考试记录与模块偏好（实测复现过）。
     *
     * 调用时机：外壳 `layout/front.vue` 监听当前用户 id 变化时调用。
     * 内部做三件事：读新分区 → 覆盖 state → 记下 ownerUserId。
     *
     * @returns 是否真的发生了切换（`false` 表示用户没变，什么都没做）
     */
    reloadForCurrentUser(): boolean {
      const uid = activeUserId
      if (String(uid ?? '') === String((this as any).ownerUserId ?? '')) return false

      const saved = loadFromStorage()
      this.currentBankId = saved?.currentBankId ?? null
      this.currentBankName = saved?.currentBankName ?? ''
      this.modules = saved?.modules ? saved.modules : JSON.parse(JSON.stringify(defaultModules))
      ;(this as any).migrations = (saved as any)?.migrations || {}
      this.mockExamHistory = Array.isArray((saved as any)?.mockExamHistory)
        ? (saved as any).mockExamHistory
        : []
      ;(this as any).ownerUserId = uid
      return true
    },

    setCurrentBank(bankId: number | string | null, bankName: string) {
      this.currentBankId = bankId
      this.currentBankName = bankName
      saveToStorage(this.$state)
    },
    getModuleSettings(moduleType: ModuleType | string): ModuleSettings {
      const key = moduleType as ModuleType
      return this.modules[key] || { ...defaultModules[key] }
    },
    saveModuleSettings(moduleType: ModuleType | string, settings: Partial<ModuleSettings>) {
      const key = moduleType as ModuleType
      if (this.modules[key]) {
        Object.assign(this.modules[key], settings)
        saveToStorage(this.$state)
      }
    },
    saveAllModules(allModules: Record<ModuleType, Partial<ModuleSettings>>) {
      (Object.keys(allModules) as ModuleType[]).forEach((key) => {
        if (this.modules[key]) {
          Object.assign(this.modules[key], allModules[key])
        }
      })
      saveToStorage(this.$state)
    },
    resetModuleSettings(moduleType: ModuleType | string) {
      const key = moduleType as ModuleType
      if (this.modules[key]) {
        this.modules[key] = { ...defaultModules[key] }
        saveToStorage(this.$state)
      }
    },
    resetAllSettings() {
      this.modules = JSON.parse(JSON.stringify(defaultModules))
      this.currentBankId = null
      this.currentBankName = ''
      // ⚠️ 刻意**不清** mockExamHistory：这是"重置设置"，不是"删除我的考试记录"。
      //    用户点重置是想把偏好恢复默认，他考过的卷子不属于偏好。
      saveToStorage(this.$state)
    },

    /* ==================== 模拟考试（2026-10-22） ==================== */

    /** 读取模拟考试配置（保证返回一份完整可用的对象，绝不返回 undefined） */
    getMockExamConfig(): MockExamConfig {
      const mock = this.modules.mock as any
      const cfg = mock?.mockExam
      if (!cfg) return JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM))
      return {
        ...JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM)),
        ...cfg,
        typeRows: Array.isArray(cfg.typeRows) && cfg.typeRows.length
          ? cfg.typeRows
          : JSON.parse(JSON.stringify(DEFAULT_MOCK_EXAM.typeRows))
      }
    },

    /** 保存模拟考试配置 */
    saveMockExamConfig(cfg: MockExamConfig) {
      const mock = this.modules.mock as any
      if (!mock) return
      mock.mockExam = JSON.parse(JSON.stringify(cfg))
      // 兼容仍在使用 `examTimeLimit` 的老代码路径（计时器读的是它）
      mock.examTimeLimit = cfg.timeLimit
      saveToStorage(this.$state)
    },

    /**
     * 追加一条考试历史
     *
     * 上限 50 条：localStorage 有 5MB 左右配额，而一条记录含逐题明细
     * （30 题约 20~40KB），不设上限迟早把配额写爆 —— 那时**整份设置都存不进去**，
     * 用户会发现"改了设置刷新就丢"，比丢历史严重得多。
     */
    addMockExamRecord(record: MockExamRecord) {
      const list = Array.isArray(this.mockExamHistory) ? this.mockExamHistory : []
      list.unshift(record)
      this.mockExamHistory = list.slice(0, 50)
      saveToStorage(this.$state)
    },

    /** 删除一条考试历史 */
    removeMockExamRecord(id: string) {
      if (!Array.isArray(this.mockExamHistory)) return
      this.mockExamHistory = this.mockExamHistory.filter((r: MockExamRecord) => r.id !== id)
      saveToStorage(this.$state)
    },

    /** 清空全部考试历史 */
    clearMockExamHistory() {
      this.mockExamHistory = []
      saveToStorage(this.$state)
    },

    /** 按 id 取一条历史 */
    getMockExamRecord(id: string): MockExamRecord | undefined {
      if (!Array.isArray(this.mockExamHistory)) return undefined
      return this.mockExamHistory.find((r: MockExamRecord) => r.id === id)
    },

    /**
     * 就地替换一条历史记录（2026-10-22）
     *
     * 用途：早期版本保存的记录里没有 `options` 字段（只存了题干和答案），
     * 回看时选项区是空的。`ExamSummary` 会按题号从题库补全选项，
     * 补完用这个方法写回，下次再打开就不必再拉一次接口。
     *
     * ⚠️ 只用于**补充展示字段**，不允许改判分结果（得分/对错）。
     *    那些是历史事实，改了就是篡改成绩。
     */
    updateMockExamRecord(id: string, record: MockExamRecord) {
      if (!Array.isArray(this.mockExamHistory)) return
      const i = this.mockExamHistory.findIndex((r: MockExamRecord) => r.id === id)
      if (i < 0) return
      this.mockExamHistory[i] = record
      saveToStorage(this.$state)
    }
  }
})

export default usePracticeSettingsStore
