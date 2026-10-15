/** 题型文本/数字类型 */
export type QuestionTypeValue = number | string

export function textToHtml(text: string): string {
  if (!text) return ''
  if (/<[a-z][\s\S]*>/i.test(text)) return text
  return '<p>' + text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '</p><p>') + '</p>'
}

export function getPlainText(html: any): string {
  if (!html) return ''
  if (typeof html !== 'string') return String(html)
  if (!/<[a-z][\s\S]*>/i.test(html)) return html
  if (typeof document !== 'undefined') {
    const div = document.createElement('div')
    div.innerHTML = html
    return (div.textContent || div.innerText || '').trim()
  }
  return html.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').trim()
}

/**
 * 从 HTML 文本里按出现顺序抽取所有 `<img src="...">` 的 src。
 *
 * 用途：AI 题目解析时把题干 / 材料 / 小题正文里内嵌的图片一并喂给多模态模型。
 * 旧实现用 getPlainText 提取正文，会把 `<img>` 整个丢掉 → 模型根本看不到图。
 * 去重保序；无图返回空数组。
 */
export function extractImageUrls(html: any): string[] {
  if (!html || typeof html !== 'string') return []
  if (!/<img/i.test(html)) return []
  const re = /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/gi
  const seen = new Set<string>()
  const urls: string[] = []
  let m: RegExpExecArray | null
  while ((m = re.exec(html)) !== null) {
    const src = (m[1] || '').trim()
    if (!src || seen.has(src)) continue
    seen.add(src)
    urls.push(src)
  }
  return urls
}

// 通用选项解析函数，安全处理各种格式
export function parseOptions(rawOptions: any, type: string = '1'): string[] {
  // 判断题固定选项
  if (type === '3' || type === 'truefalse') {
    return ['正确', '错误']
  }

  // 如果是 null / undefined / 空字符串
  if (!rawOptions) {
    return []
  }

  // 如果已经是数组，直接返回
  if (Array.isArray(rawOptions)) {
    return rawOptions.filter(opt => opt !== null && opt !== undefined).map(String)
  }

  // 如果是字符串
  if (typeof rawOptions === 'string') {
    let str = rawOptions.trim()
    if (!str) return []

    // 尝试 JSON 解析
    try {
      const parsed = JSON.parse(str)
      if (Array.isArray(parsed)) {
        return parsed.filter(opt => opt !== null && opt !== undefined).map(String)
      }
    } catch (e) {
      // JSON 失败，按换行符分割
    }

    // 按换行、逗号、分号等常见分隔符分割
    return str
      .split(/[\n,;，；]+/)
      .map(s => s.trim())
      .filter(s => s !== '')
  }

  // 其他类型（如数字、对象）一律转为空数组
  console.warn('无法解析的 options 格式:', rawOptions)
  return []
}

// 格式化答案显示
export function formatAnswer(answer: any, type: string): string {
  if (answer === undefined || answer === null) return ''

  if (type === '2' || type === 'multiple') {
    if (Array.isArray(answer)) {
      return answer.map(a => {
        if (typeof a === 'number') {
          return String.fromCharCode(65 + a)
        }
        return a
      }).join(', ')
    }
    return String(answer)
  } else if (type === '1' || type === 'single') {
    if (typeof answer === 'number') {
      return String.fromCharCode(65 + answer)
    }
    return String(answer)
  } else if (type === '3' || type === 'truefalse') {
    return answer === 0 ? '正确' : '错误'
  }

  return String(answer)
}

// 格式化主干内容
export function formatMainContent(content: string): string {
  if (!content) return ''
  return content.replace(/___(\d+)___/g, '<strong style="color: #409eff; text-decoration: underline;">[$1]</strong>')
}

/**
 * 将题型值转换为中文文本
 * @param type 题型（1-7的整数或字符串）
 * @returns 题型中文文本
 */
export const getQuestionTypeText = (type: QuestionTypeValue): string => {
  if (type == null) return '未知题型'
  const typeNum = Number(type) || 0
  const typeMap: Record<number, string> = {
    1: '单选题',
    2: '多选题',
    3: '判断题',
    4: '填空题',
    5: '简答题',
    6: '组合题',
    7: '组合题'
  }
  return typeMap[typeNum] || '未知题型'
}

/**
 * 获取题型CSS类
 * @param type 题型（1-7的整数或字符串）
 * @returns CSS类名
 */
export const getQuestionTypeClass = (type: QuestionTypeValue): string => {
  const typeNum = Number(type) || 0
  const classMap: Record<number, string> = {
    1: 'type-single',
    2: 'type-multiple',
    3: 'type-truefalse',
    4: 'type-fillblank',
    5: 'type-essay',
    6: 'type-composite',
    7: 'type-composite'
  }
  return classMap[typeNum] || ''
}

/**
 * 格式化正确答案（特别是多选题）
 * @param answer 原始答案
 * @param questionType 题型
 * @returns 格式化后的答案
 */
export const formatCorrectAnswer = (answer: any, questionType: number): any => {
  if (!answer) return questionType === 2 ? [] : ''

  // 如果是多选题（类型2）
  if (questionType === 2) {
    try {
      if (typeof answer === 'string') {
        // 尝试解析JSON
        const parsed = JSON.parse(answer)
        if (Array.isArray(parsed)) {
          return parsed
        }
        // 如果是逗号分隔的字符串
        return answer.split(',').map((item: string) => item.trim()).filter(Boolean)
      } else if (Array.isArray(answer)) {
        return answer
      }
    } catch (e) {
      // 如果不是JSON，可能是逗号分隔
      if (typeof answer === 'string') {
        return answer.split(',').map((item: string) => item.trim()).filter(Boolean)
      }
    }
  }

  return answer
}
