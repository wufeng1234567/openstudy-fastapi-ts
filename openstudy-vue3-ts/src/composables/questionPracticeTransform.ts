// composables/questionPracticeTransform.ts
//
// 练习页**题目转换层**（从 `useQuestionPractice.ts` 抽出的纯逻辑模块）。
//
// 职责：把后端返回的**原始题目对象**转成组件能渲染的 `TransformedQuestion`
//   · `pickSubList` —— 兼容三种字段名取组合题的子题数组
//   · `transformQuestionForDisplay` —— 题型映射 / 选项解析 / 正确答案标准化 / 白名单重建
//   · `toDisplayQuestions` —— 批量转换并**重置答题态**
//
// ⚠️ 这三个函数**只依赖入参**（外加 `@/utils/questionUtils` 的 `parseOptions`），
//    不碰任何响应式状态 —— 抽到这里是为了让「转换规则」可以单独读、单独测。
//
// ⚠️ `transformQuestionForDisplay` 仍是 `useQuestionPractice()` 对外导出的一部分
//    （`myMarked` / `myMistakes` / `myFavoriteQuestion` 三个页面在用），
//    composable 侧原样转出，调用方无需改动。
import { parseOptions } from '@/utils/questionUtils'
import type { TransformedQuestion, QuestionType } from '@/types'

/**
 * 取组合题的子题数组（**字段名兼容**）
 *
 * ⚠️ 这里踩过坑（用户 2026-10-18 bug3「组合题只有题干、看不到子题」）：
 *    前端原来只读 `q.questionSubList`，但后端 `format_question()` 返回的键叫
 *    `subQuestions`（见 `app/api/v1/questions.py`）——**永远取不到**，
 *    于是子题数组恒为空、`ReadingComprehensionDisplay` 的
 *    `v-if="subQuestions.length > 0"` 整块不渲染，界面上就只剩题干。
 *
 *    三个候选键都兼容：`subQuestions`（后端现用）/ `questionSubList`（早期约定，写入时用）/
 *    `question_sub_list`（蛇形接口）。取到第一个非空数组即返回。
 */
export function pickSubList(q: any): any[] {
  if (!q) return []
  const candidates = [q.subQuestions, q.questionSubList, q.question_sub_list]
  for (const c of candidates) {
    if (Array.isArray(c) && c.length > 0) return c
  }
  return []
}
// ✅ 关键：导出的通用转换函数 - 完整版
export function transformQuestionForDisplay(q: any): TransformedQuestion {
  let type: QuestionType = 'unknown'
  switch (q.questionType || q.question_type) {
    case 1:
      type = 'single'
      break
    case 2:
      type = 'multiple'
      break
    case 3:
      type = 'truefalse'
      break
    case 4:
      type = 'fillblank'
      break
    case 5:
      type = 'essay'
      break
    case 6:
      type = 'readingComprehension'
      break
    case 7:
      type = 'cloze'
      break
    default:
      type = 'unknown'
  }

  // 解析选项
  let options: any[] = []
  if (q.options) {
    try {
      // 优先使用 parseOptions 函数
      if (typeof parseOptions === 'function') {
        options = parseOptions(q.options, type)
      } else {
        // 备用方案：手动解析
        if (typeof q.options === 'string') {
          const trimmed = q.options.trim()
          if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
            options = JSON.parse(trimmed)
          } else if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
            const parsed = JSON.parse(trimmed)
            options = Object.values(parsed).filter((val: any) => val !== null && val !== undefined)
          } else {
            options = trimmed.split(',').map((opt: string) => opt.trim())
          }
        } else if (Array.isArray(q.options)) {
          options = q.options
        } else if (typeof q.options === 'object') {
          options = Object.values(q.options).filter((val: any) => val !== null && val !== undefined)
        }
      }
    } catch (e) {
      // 创建有意义的默认选项
      if (type === 'single' || type === 'multiple') {
        // 根据题目内容创建相关选项
        const baseOptions = ['has studied', 'studies', 'is studying', 'study']
        options = baseOptions
      } else if (type === 'truefalse') {
        options = ['正确', '错误']
      }
    }
  } else {
    // 创建有意义的默认选项
    if (type === 'single' || type === 'multiple') {
      // 根据题目内容创建相关选项
      if (q.questionText && q.questionText.includes('English')) {
        options = ['has studied', 'studies', 'is studying', 'study']
      } else if (q.questionText && q.questionText.includes('If I')) {
        options = ['am', 'was', 'were', 'be']
      } else {
        options = ['选项A', '选项B', '选项C', '选项D']
      }
    } else if (type === 'truefalse') {
      options = ['正确', '错误']
    }
  }

  // ✅ 改进：正确答案标准化
  let correctAnswer: any = q.answer

  if (type === 'truefalse') {
    const ans = String(q.answer).trim().toLowerCase()
    correctAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
  } else if (type === 'single') {
    if (typeof q.answer === 'string') {
      const ansStr = q.answer.trim()
      const letter = ansStr.toUpperCase()
      if (letter.length === 1 && letter >= 'A' && letter <= 'Z') {
        correctAnswer = letter.charCodeAt(0) - 65
      } else {
        const num = Number(ansStr)
        if (!isNaN(num)) {
          correctAnswer = num
        } else {
          correctAnswer = 0
        }
      }
    } else {
      correctAnswer = Number(q.answer) || 0
    }
  } else if (type === 'multiple') {
    if (typeof q.answer === 'string') {
      const ansStr = q.answer.trim()

      if (ansStr.startsWith('[') && ansStr.endsWith(']')) {
        try {
          const parsed = JSON.parse(ansStr)
          if (Array.isArray(parsed)) {
            if (parsed.every((item: any) => typeof item === 'number')) {
              correctAnswer = parsed
            }
            else if (parsed.every((item: any) => typeof item === 'string' && item.length === 1)) {
              correctAnswer = parsed
                .map((s: string) => s.trim().toUpperCase())
                .filter((s: string) => s >= 'A' && s <= 'Z')
                .map((s: string) => s.charCodeAt(0) - 65)
            } else {
              correctAnswer = []
            }
          } else {
            correctAnswer = []
          }
        } catch (e) {
          correctAnswer = ansStr
            .split(/[,，]/)
            .map((s: string) => {
              s = s.trim().toUpperCase()
              if (s.length === 1 && s >= 'A' && s <= 'Z') {
                return s.charCodeAt(0) - 65
              }
              const num = Number(s)
              return isNaN(num) ? null : num
            })
            .filter((n: number | null) => n !== null)
        }
      } else {
        correctAnswer = ansStr
          .split(/[,，]/)
          .map((s: string) => {
            s = s.trim().toUpperCase()
            if (s.length === 1 && s >= 'A' && s <= 'Z') {
              return s.charCodeAt(0) - 65
            }
            const num = Number(s)
            return isNaN(num) ? null : num
          })
          .filter((n: number | null) => n !== null)
      }
    } else if (Array.isArray(q.answer)) {
      correctAnswer = q.answer
        .map((item: any) => {
          if (typeof item === 'string') {
            const s = item.trim().toUpperCase()
            if (s.length === 1 && s >= 'A' && s <= 'Z') {
              return s.charCodeAt(0) - 65
            }
            const num = Number(s)
            return isNaN(num) ? null : num
          }
          return typeof item === 'number' ? item : null
        })
        .filter((n: number | null) => n !== null)
    } else {
      correctAnswer = []
    }

    if (!Array.isArray(correctAnswer)) {
      correctAnswer = []
    }
  } else if (type === 'fillblank' || type === 'essay') {
    // 填空题和问答题保持原始答案
    correctAnswer = q.answer
  }

  // 处理阅读理解 & 完形填空
  let subQuestions: any[] = []
  let hasMainContent = false
  let mainContent = ''
  let mainTitle = ''

  if (type === 'cloze') {
    mainContent = q.content || ''
    mainTitle = q.questionText || '完形填空'
    hasMainContent = true

    if (mainContent) {
      mainContent = mainContent.replace(/\[\[(\d+)\]\]/g, '___$1___')
    }

    if (pickSubList(q).length > 0) {
      subQuestions = pickSubList(q).map((sq: any, index: number) => {
        let sqType = 'single'
        switch (sq.questionType || sq.question_type) {
          case 1:
            sqType = 'single'
            break
          case 2:
            sqType = 'multiple'
            break
          case 3:
            sqType = 'truefalse'
            break
          case 4:
            sqType = 'fillblank'
            break
          case 5:
            sqType = 'essay'
            break
          default:
            sqType = 'single'
        }

        // 解析子题选项
        let sqOptions: any[] = []
        if (sq.options) {
          try {
            if (typeof sq.options === 'string') {
              const trimmed = sq.options.trim()
              if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                sqOptions = JSON.parse(trimmed)
              } else {
                sqOptions = trimmed.split(',').map((opt: string) => opt.trim())
              }
            } else if (Array.isArray(sq.options)) {
              sqOptions = sq.options
            }
          } catch (e) {
          }
        }

        // ✅ 改进：子题答案处理
        let sqCorrectAnswer: any = sq.answer
        if (sqType === 'truefalse') {
          const ans = String(sq.answer).trim().toLowerCase()
          sqCorrectAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
        } else if (sqType === 'single') {
          if (typeof sq.answer === 'string' && sq.answer.length === 1) {
            const letter = sq.answer.toUpperCase()
            if (letter >= 'A' && letter <= 'Z') {
              sqCorrectAnswer = letter.charCodeAt(0) - 65
            } else {
              sqCorrectAnswer = Number(sq.answer) || 0
            }
          } else {
            sqCorrectAnswer = Number(sq.answer) || 0
          }
        } else if (sqType === 'multiple') {
          // 使用相同的多选题答案处理逻辑
          if (typeof sq.answer === 'string') {
            sqCorrectAnswer = sq.answer
              .split(/[,，]/)
              .map((s: string) => {
                s = s.trim().toUpperCase()
                if (s.length === 1 && s >= 'A' && s <= 'Z') {
                  return s.charCodeAt(0) - 65
                }
                const num = Number(s)
                return isNaN(num) ? null : num
              })
              .filter((n: number | null) => n !== null)
          } else if (Array.isArray(sq.answer)) {
            sqCorrectAnswer = sq.answer
          } else {
            sqCorrectAnswer = []
          }
        } else if (sqType === 'fillblank' || sqType === 'essay') {
          // ✅ 关键修复：填空题和问答题保持原始答案字符串
          sqCorrectAnswer = sq.answer
        }

        return {
          question: sq.questionText || sq.question_text || `第 ${index + 1} 空应填入：`,
          type: sqType,
          options: sqOptions,
          analysis: sq.analysis,
          correctAnswer: sqCorrectAnswer,
          answered: false,
          correct: false
        }
      })
    }
  }
  else if (type === 'readingComprehension') {
    mainContent = q.content || ''
    mainTitle = q.questionText || '阅读理解'
    hasMainContent = !!mainContent

    if (pickSubList(q).length > 0) {
      subQuestions = pickSubList(q).map((sq: any, index: number) => {
        let sqType = 'single'
        switch (sq.questionType || sq.question_type) {
          case 1:
            sqType = 'single'
            break
          case 2:
            sqType = 'multiple'
            break
          case 3:
            sqType = 'truefalse'
            break
          case 4:
            sqType = 'fillblank'
            break
          case 5:
            sqType = 'essay'
            break
          default:
            sqType = 'single'
        }

        // 解析子题选项
        let sqOptions: any[] = []
        if (sq.options) {
          try {
            if (typeof sq.options === 'string') {
              const trimmed = sq.options.trim()
              if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                sqOptions = JSON.parse(trimmed)
              } else {
                sqOptions = trimmed.split(',').map((opt: string) => opt.trim())
              }
            } else if (Array.isArray(sq.options)) {
              sqOptions = sq.options
            }
          } catch (e) {
          }
        }

        // ✅ 改进：子题答案处理
        let sqCorrectAnswer: any = sq.answer
        if (sqType === 'truefalse') {
          const ans = String(sq.answer).trim().toLowerCase()
          sqCorrectAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
        } else if (sqType === 'single') {
          if (typeof sq.answer === 'string' && sq.answer.length === 1) {
            const letter = sq.answer.toUpperCase()
            if (letter >= 'A' && letter <= 'Z') {
              sqCorrectAnswer = letter.charCodeAt(0) - 65
            } else {
              sqCorrectAnswer = Number(sq.answer) || 0
            }
          } else {
            sqCorrectAnswer = Number(sq.answer) || 0
          }
        } else if (sqType === 'multiple') {
          if (typeof sq.answer === 'string') {
            sqCorrectAnswer = sq.answer
              .split(/[,，]/)
              .map((s: string) => {
                s = s.trim().toUpperCase()
                if (s.length === 1 && s >= 'A' && s <= 'Z') {
                  return s.charCodeAt(0) - 65
                }
                const num = Number(s)
                return isNaN(num) ? null : num
              })
              .filter((n: number | null) => n !== null)
          } else if (Array.isArray(sq.answer)) {
            sqCorrectAnswer = sq.answer
          } else {
            sqCorrectAnswer = []
          }
        } else if (sqType === 'fillblank' || sqType === 'essay') {
          // ✅ 关键修复：填空题和问答题保持原始答案字符串
          sqCorrectAnswer = sq.answer
        }

        return {
          question: sq.questionText || sq.question_text || `问题 ${index + 1}`,
          type: sqType,
          options: sqOptions,
          analysis: sq.analysis,
          correctAnswer: sqCorrectAnswer,
          answered: false,
          correct: false
        }
      })
    }
  }

  if (!hasMainContent) {
    mainContent = ''
    mainTitle = ''
  }

  const questionObj = {
    id: q.id,
    bankId: q.bankId, // ✅ 添加 bankId 字段，用于错题记录
    difficulty: q.difficulty, // ✅ 添加难度字段
    question: (type === 'readingComprehension' || type === 'cloze') ? '' : (q.questionText || q.question_text),
    type,
    options,
    correctAnswer,
    analysis: q.analysis || '',
    /*
     * 模拟考试的分值 / 题型标记必须**透传**过来（2026-10-22）。
     *
     * 本函数是白名单式重建对象 —— 不在这里显式列出的字段会被丢掉。
     * 组卷时挂在原始题目上的 `_mockScore`（每题分值）和 `_mockType`
     * 一旦丢失，判分时 `Number(q._mockScore) || 0` 全是 0，
     * 于是"满分 0 分、0 分及格"。
     * 其它模式没有这两个字段，透传 undefined 无副作用。
     */
    _mockScore: q._mockScore,
    _mockType: q._mockType,
    mainContent,
    mainTitle,
    hasMainContent,
    subQuestions,
    answered: false,
    correct: false,
    showAnalysis: false,
    userAnswer: null,
    // 添加额外的元数据，方便调试
    _rawAnswer: q.answer,
    _rawOptions: q.options
  }

  return questionObj
}

/**
 * 把「后端原始题目数组」转成组件能渲染的 `TransformedQuestion[]`
 *
 * ⚠️⚠️ **任何给 `questions.value` 赋值的地方都必须经过它**（2026-10-20 修的 bug）。
 *
 * 现象（用户口径）：「只刷错题 会变成题型无法识别 全部都一样」，截图里每一道题
 * 都显示「未知题型 / 暂不支持该题型」。
 *
 * 根因：`transformQuestionForDisplay()` 负责把 `questionType`(数字 1~7) 映射成
 * 组件认识的 `type`('single'/'multiple'/…) 并整理 options 等字段。
 * `processQuestions` 的分支是 `slicedData.map(transformQuestionForDisplay)`，
 * 但我在修 bug1 时让错题分支改走 `applyQuestionLimits()` —— 而那个函数里是
 * **裸赋值** `questions.value = shuffled / slice(...)`，
 * 于是 `questions` 里躺的是后端原始对象：没有 `type`、没有整理过的 options，
 * 组件拿不到题型 → 每道题都渲染成「未知题型」。
 *
 * 修法：把转换收进这一个函数，`applyQuestionLimits` 的四个赋值点全部改用它。
 * 这样「哪里赋值」不再重要 —— 只要都走这里，就不会再漏一次。
 */
export function toDisplayQuestions(raw: any[]): TransformedQuestion[] {
  return (raw || []).map((q) => {
    const processed = transformQuestionForDisplay(q)
    return {
      ...processed,
      // 每次都重置答题态：换波/换筛选之后，上一波的作答不能带过来
      answered: false,
      correct: false,
      showAnalysis: false,
      userAnswer: null
    } as TransformedQuestion
  })
}
