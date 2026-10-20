import { defineStore } from 'pinia'
import type { ModuleType, ModuleSettings, PracticeSettings, PracticeModuleConfig } from '@/types'

const STORAGE_KEY = 'practice-settings'

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
    examTimeLimit: 60
  }
}

function loadFromStorage(): PracticeSettings | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
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
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
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
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
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
      migrations: (state as any).migrations || {}
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
      migrations: (saved as any)?.migrations || {}
    } as PracticeSettings
  },
  actions: {
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
      localStorage.removeItem(STORAGE_KEY)
    }
  }
})

export default usePracticeSettingsStore
