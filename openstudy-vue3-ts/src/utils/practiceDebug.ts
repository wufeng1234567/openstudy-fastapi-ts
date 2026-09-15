/**
 * 刷题模块调试日志工具
 *
 * 使用方法：
 * 1. 在浏览器控制台执行：window.__PRACTICE_DEBUG__ = true 开启日志
 * 2. 执行：window.__PRACTICE_DEBUG__ = false 关闭日志
 * 3. 默认关闭状态
 */

// 全局调试开关（默认关闭）
if (typeof window.__PRACTICE_DEBUG__ === 'undefined') {
  window.__PRACTICE_DEBUG__ = false
}

// 记录启动时间
const startTime = Date.now()

// 模块颜色配置
const MODULE_COLORS: Record<string, string> = {
  sequential: '#4CAF50',  // 绿色 - 顺序
  random: '#FF9800',      // 橙色 - 乱序
  custom: '#2196F3',      // 蓝色 - 自定义
  mock: '#9C27B0'         // 紫色 - 模拟考试
}

const MODULE_NAMES: Record<string, string> = {
  sequential: '顺序练习',
  random: '乱序练习',
  custom: '自定义练习',
  mock: '模拟考试'
}

/**
 * 获取相对时间戳
 */
function getTimestamp(): string {
  const elapsed = Date.now() - startTime
  return `${(elapsed / 1000).toFixed(2)}s`
}

/** 题目项（用于调试打印） */
interface DebugQuestionItem {
  id?: any
  question?: string
  [key: string]: any
}

/**
 * 基础日志函数
 */
function log(moduleType: string, tag: string, message: string, data: any = null): void {
  if (!window.__PRACTICE_DEBUG__) return

  const moduleName = MODULE_NAMES[moduleType] || moduleType
  const color = MODULE_COLORS[moduleType] || '#666'
  const timestamp = getTimestamp()

  const prefix = `%c[DEBUG][${timestamp}][${moduleName}]`
  const style = `color: ${color}; font-weight: bold;`

  if (data) {
    console.log(prefix, style, message, data)
  } else {
    console.log(prefix, style, message)
  }
}

/**
 * 打印数组前N项作为样例
 */
function sampleArray(arr: any[] | null, n: number = 3): string {
  if (!arr || !Array.isArray(arr)) return 'null/undefined'
  if (arr.length === 0) return '[]'
  const sample = arr.slice(0, n).map(q => q?.id || q?.question?.substring(0, 20) || 'unknown')
  return `[${sample.join(', ')}...] (共${arr.length}项)`
}

/**
 * 打印题目ID序列
 */
function printIdSequence(arr: DebugQuestionItem[] | null, n: number = 5): string {
  if (!arr || !Array.isArray(arr)) return 'null/undefined'
  if (arr.length === 0) return '[]'
  const ids = arr.slice(0, n).map(q => q?.id || '?')
  return `[${ids.join(' → ')}...]`
}

// ==================== 调试日志函数 ====================

/**
 * 进入模块时调用
 */
export function debugEnterModule(moduleType: string, bankId: any): void {
  log(moduleType, 'ENTER', `========== 进入模块 ==========`, {
    bankId,
    moduleType,
    currentTime: new Date().toLocaleTimeString()
  })
}

/**
 * 离开模块时调用
 */
export function debugLeaveModule(moduleType: string, bankId: any): void {
  log(moduleType, 'LEAVE', `========== 离开模块 ==========`, {
    bankId,
    moduleType
  })
}

/**
 * 开始加载题目时调用
 */
export function debugFetchStart(moduleType: string, bankId: any): void {
  log(moduleType, 'FETCH', `开始加载题目`, { bankId })
}

/**
 * 从API获取到原始数据时调用
 */
export function debugFetchComplete(moduleType: string, data: DebugQuestionItem[] | null): void {
  log(moduleType, 'FETCH', `API返回数据`, {
    totalQuestions: data?.length || 0,
    sampleIds: printIdSequence(data)
  })
}

/**
 * 进入 processQuestions 时调用
 */
export function debugProcessStart(moduleType: string, data: DebugQuestionItem[] | null, options: any = {}): void {
  log(moduleType, 'PROCESS', `processQuestions 开始处理`, {
    inputCount: data?.length || 0,
    inputSample: printIdSequence(data),
    shouldShuffle: options.shouldShuffle,
    questionCount: options.questionCount,
    offset: options.offset
  })
}

/**
 * 检查缓存时调用
 */
export function debugCacheCheck(moduleType: string, cacheKey: string, hasCache: boolean, cachedData: DebugQuestionItem[] | null = null): void {
  if (hasCache) {
    log(moduleType, 'CACHE', `✓ 命中缓存: ${cacheKey}`, {
      cachedSample: printIdSequence(cachedData)
    })
  } else {
    log(moduleType, 'CACHE', `✗ 未命中缓存: ${cacheKey}，将生成新数据`)
  }
}

/**
 * 执行打乱时调用
 */
export function debugShuffle(moduleType: string, before: DebugQuestionItem[] | null, after: DebugQuestionItem[] | null): void {
  log(moduleType, 'SHUFFLE', `执行打乱操作`, {
    beforeShuffle: printIdSequence(before),
    afterShuffle: printIdSequence(after),
    isSameOrder: JSON.stringify(before?.map(q => q?.id)) === JSON.stringify(after?.map(q => q?.id))
  })
}

/**
 * 写入缓存时调用
 */
export function debugCacheWrite(moduleType: string, cacheKey: string, data: DebugQuestionItem[] | null): void {
  log(moduleType, 'CACHE', `写入缓存: ${cacheKey}`, {
    dataSample: printIdSequence(data)
  })
}

/**
 * 设置 allQuestionsData 时调用
 */
export function debugSetAllQuestionsData(moduleType: string, data: DebugQuestionItem[] | null, caller: string = 'unknown'): void {
  log(moduleType, 'DATA', `设置 allQuestionsData (调用者: ${caller})`, {
    count: data?.length || 0,
    sample: printIdSequence(data)
  })
}

/**
 * 设置 questions 时调用
 */
export function debugSetQuestions(moduleType: string, data: DebugQuestionItem[] | null, caller: string = 'unknown'): void {
  log(moduleType, 'DATA', `设置 questions (调用者: ${caller})`, {
    count: data?.length || 0,
    sample: printIdSequence(data)
  })
}

/**
 * processQuestions 完成时调用
 */
export function debugProcessComplete(moduleType: string, questions: DebugQuestionItem[] | null, allQuestionsData: DebugQuestionItem[] | null): void {
  log(moduleType, 'PROCESS', `processQuestions 处理完成`, {
    questionsCount: questions?.length || 0,
    questionsSample: printIdSequence(questions),
    allDataCount: allQuestionsData?.length || 0,
    allDataSample: printIdSequence(allQuestionsData)
  })
}

/**
 * resetAndFetchQuestions 调用时
 */
export function debugResetAndFetch(moduleType: string, bankId: any): void {
  log(moduleType, 'RESET', `resetAndFetchQuestions 被调用`, {
    bankId,
    reason: '模式切换'
  })
}

/**
 * fetchQuestions 调用时
 */
export function debugFetchQuestions(moduleType: string, bankId: any, hasExistingData: boolean): void {
  log(moduleType, 'FETCH', `fetchQuestions 被调用`, {
    bankId,
    hasExistingData,
    willSkip: hasExistingData
  })
}

/**
 * watch 触发时调用
 */
export function debugWatchTrigger(watchName: string, moduleType: string, newVal: any, oldVal: any): void {
  log(moduleType, 'WATCH', `watch "${watchName}" 触发`, {
    newVal: typeof newVal === 'object' ? JSON.stringify(newVal)?.substring(0, 50) : newVal,
    oldVal: typeof oldVal === 'object' ? JSON.stringify(oldVal)?.substring(0, 50) : oldVal
  })
}

/**
 * 打印当前完整状态快照
 */
export function debugStateSnapshot(moduleType: string, state: any): void {
  log(moduleType, 'STATE', `当前状态快照`, {
    questionsCount: state.questions?.length || 0,
    questionsSample: printIdSequence(state.questions),
    allDataCount: state.allQuestionsData?.length || 0,
    allDataSample: printIdSequence(state.allQuestionsData),
    currentQuestionIndex: state.currentQuestionIndex,
    questionCount: state.questionCount,
    questionOffset: state.questionOffset,
    isResetting: state.isResetting
  })
}

/**
 * 打印缓存状态
 */
export function debugCacheStatus(shuffledCache: Map<string, any>): void {
  if (!window.__PRACTICE_DEBUG__) return

  console.log('%c[DEBUG] 缓存状态:', 'color: #9C27B0; font-weight: bold;', {
    cacheSize: shuffledCache.size,
    keys: Array.from(shuffledCache.keys())
  })
}

// 导出调试开关控制
export function enableDebug(): void {
  window.__PRACTICE_DEBUG__ = true
  console.log('%c[DEBUG] 调试日志已开启', 'color: #4CAF50; font-weight: bold; font-size: 14px;')
}

export function disableDebug(): void {
  window.__PRACTICE_DEBUG__ = false
  console.log('%c[DEBUG] 调试日志已关闭', 'color: #F44336; font-weight: bold; font-size: 14px;')
}

// 在控制台打印使用说明（仅调试模式开启时显示）
if (typeof window !== 'undefined' && window.__PRACTICE_DEBUG__) {
  console.log(`%c[刷题调试工具] 已加载
使用方法：
  开启日志: __PRACTICE_DEBUG__ = true
  关闭日志: __PRACTICE_DEBUG__ = false`, 'color: #2196F3; font-size: 12px;')
}
