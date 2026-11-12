import { reactive, ref } from 'vue'

/** 练习设置弹窗的打开快照和保存后的重拉策略。 */
export function usePracticeSettings(options: {
  moduleSettings: { value: any }
  resetAndFetchQuestions: () => void
  updateQuestionCountAndSlice: (count: number) => void
}) {
  const showSettings = ref(false)
  const settingsSnapshot = reactive({
    onlyWrong: false,
    questionCount: 10 as number | string,
    isOverviewMode: false
  })

  const handleSettingsSave = (data: { moduleType: string; settings: any }) => {
    const { settings } = data
    const prevOnlyWrong = !!settingsSnapshot.onlyWrong
    const prevCount = settingsSnapshot.questionCount
    const onlyWrongChanged = !!settings.onlyWrong !== prevOnlyWrong
    const countChanged = settings.questionCount !== prevCount
    if (onlyWrongChanged) {
      options.resetAndFetchQuestions()
      return
    }
    if (countChanged) options.updateQuestionCountAndSlice(settings.questionCount)
  }

  const openSettings = () => {
    const settings = options.moduleSettings.value
    settingsSnapshot.onlyWrong = !!settings.onlyWrong
    settingsSnapshot.questionCount = settings.questionCount
    settingsSnapshot.isOverviewMode = !!settings.isOverviewMode
    showSettings.value = true
  }

  return { showSettings, settingsSnapshot, handleSettingsSave, openSettings }
}
