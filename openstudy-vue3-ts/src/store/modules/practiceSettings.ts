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
    onlyWrong: false,
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
      modules: state.modules
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
      modules: saved?.modules ? saved.modules : JSON.parse(JSON.stringify(defaultModules))
    }
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
