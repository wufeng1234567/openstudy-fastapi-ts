/** 模拟考试结果页的再考、历史回看和选项乱序动作。 */
export function usePracticeMockHistory(options: {
  activeMockConfig: { value: any }
  currentExamRecord: { value: any }
  historyRecord: { value: any }
  showExamResult: { value: boolean }
  totalScore: { value: number }
  mockPhase: { value: string }
  store: any
  proxy: any
  moduleTypeSafe: { value: string }
  getModuleType: () => string | undefined
  handleMockStart: (config?: any) => void
}) {
  function handleMockAgain(preset?: any) {
    const source = preset || options.activeMockConfig.value || options.store.getMockExamConfig()
    const snapshot = JSON.parse(JSON.stringify(source))
    options.currentExamRecord.value = null
    options.historyRecord.value = null
    options.showExamResult.value = false
    options.totalScore.value = 0
    options.store.saveMockExamConfig(snapshot)
    options.handleMockStart(snapshot)
  }

  function handleOpenHistoryRecord(record: any) {
    options.historyRecord.value = record
    options.currentExamRecord.value = record
    options.mockPhase.value = 'summary'
  }

  function handleMockRetryFromSummary() {
    if (options.historyRecord.value) {
      const snapshot = options.historyRecord.value.config
      if (snapshot) {
        handleMockAgain(snapshot)
        return
      }
      options.proxy.$modal.msgInfo('这条记录没有保存当时的考试配置，将按当前设置重新组卷')
    }
    handleMockAgain()
  }

  function handleMockBackToHistory() {
    options.historyRecord.value = null
    options.currentExamRecord.value = null
    options.mockPhase.value = 'history'
  }

  function handleToggleShuffle(value: boolean) {
    if (options.moduleTypeSafe.value === 'mock') return
    options.store.saveModuleSettings(options.getModuleType(), { shuffleOptions: value })
    options.proxy.$modal.msgSuccess(value ? '已打乱选项顺序' : '已恢复选项原始顺序')
  }

  return { handleMockAgain, handleOpenHistoryRecord, handleMockRetryFromSummary, handleMockBackToHistory, handleToggleShuffle }
}
