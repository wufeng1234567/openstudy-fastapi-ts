import request from '@/utils/request'
import { getToken } from '@/utils/auth'

// 聊天
export function chat(data: any) {
  return request({
    url: '/ai/chat',
    method: 'post',
    data: data
  })
}



// 切换模型
export function switchModel(provider: string) {
  return request({
    url: '/ai/switch-model',
    method: 'get',
    params: { provider: provider }
  })
}

// 获取模型列表
export function getModels() {
  return request({
    url: '/ai/models',
    method: 'get'
  })
}

// 生成题目（非流式，保留备用）
export function generateQuestions(data: any) {
  return request({
    url: '/ai/generate/questions',
    method: 'post',
    data: data,
    timeout: 120000
  })
}

// 生成阅读理解题（非流式，保留备用）
export function generateReadingComprehension(data: any) {
  return request({
    url: '/ai/generate/reading',
    method: 'post',
    data: data,
    timeout: 120000
  })
}

// 解析文件为结构化块（含图片提取）
export function parseFileBlocks(files: File[]) {
  const formData = new FormData()
  files.forEach(file => {
    formData.append('files', file)
  })
  return request({
    url: '/ai/question-bank/parse-files-blocks',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    timeout: 120000
  })
}

// 流式生成普通题目（智能解析版）
export async function generateQuestionsStream(
  knowledgePoint: string,
  questionType: string,
  count: string | number,
  provider: string,
  onMessage?: (content: string) => void,
  onComplete?: (data: any) => void,
  onError?: (error: any) => void
): Promise<void> {
  const params = new URLSearchParams({ knowledgePoint, questionType, count: String(count), provider })
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/generate/questions/stream?${params.toString()}`

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''
    let lastParsedJson: any = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)

      if (chunk && chunk !== '[DONE]') {
        fullContent += chunk
        onMessage?.(fullContent)

        try {
          const parsed = JSON.parse(fullContent)
          lastParsedJson = parsed
        } catch (e) {
          // 解析失败是正常的，继续累积
        }
      }
    }

    if (lastParsedJson) {
      console.log('实时解析成功，题目数量:', Array.isArray(lastParsedJson) ? lastParsedJson.length : 1)
      onComplete?.(lastParsedJson)
    } else {
      const fixed = fixJsonContent(fullContent)
      console.log('修复后的内容:', fixed.substring(0, 500))
      try {
        const parsed = JSON.parse(fixed)
        console.log('修复后解析成功')
        onComplete?.(parsed)
      } catch (e) {
        console.error('最终解析失败，原始内容:', fullContent)
        onComplete?.(fullContent)
      }
    }
  } catch (error) {
    onError?.(error)
    throw error
  }
}

export async function generateQuestionsStreamFull({ knowledgePoint, questionType, count, provider, userId, bankId, thinking, onChunk, onComplete, onError }: {
  knowledgePoint: string
  questionType: string
  count: string | number
  provider: string
  userId?: string | number
  bankId?: string | number
  /** 深度思考：true/false 覆盖 DB 配置；不传则跟随配置 */
  thinking?: boolean
  onChunk?: (content: string) => void
  onComplete?: (content: string) => void
  onError?: (error: any) => void
}): Promise<void> {
  const params = new URLSearchParams({ knowledgePoint, questionType, count: String(count), provider })
  if (userId != null && userId !== '') params.append('userId', String(userId))
  if (bankId) params.append('bankId', String(bankId))
  if (thinking !== undefined && thinking !== null) params.append('thinking', String(thinking))
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/generate/questions/stream?${params.toString()}`
  console.log('【流式出题】请求URL:', url)
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''
    let chunkIndex = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      let chunk = decoder.decode(value)
      chunkIndex++
      console.log(`【流式出题】chunk #${chunkIndex}, 长度: ${chunk.length}, 内容:`, JSON.stringify(chunk).substring(0, 300))
      if (chunk) {
        chunk = chunk.replace(/\[DONE\]/g, '')
        if (chunk) {
          fullContent += chunk
          console.log(`【流式出题】累计内容长度: ${fullContent.length}`)
          onChunk?.(fullContent)
        }
      }
    }
    console.log('【流式出题】流式结束，最终内容长度:', fullContent.length)
    console.log('【流式出题】最终内容前500字符:', fullContent.substring(0, 500))
    console.log('【流式出题】最终内容后500字符:', fullContent.substring(Math.max(0, fullContent.length - 500)))
    onComplete?.(fullContent)
  } catch (error) {
    console.error('【流式出题】请求异常:', error)
    onError?.(error)
  }
}

export async function generateCompositeStreamFull({ requirement, questionCount, wordCount, provider, userId, thinking, onChunk, onComplete, onError }: {
  requirement: string
  questionCount: string | number
  wordCount?: string | number
  provider: string
  userId?: string | number
  /** 深度思考：true/false 覆盖 DB 配置；不传则跟随配置 */
  thinking?: boolean
  onChunk?: (content: string) => void
  onComplete?: (content: string) => void
  onError?: (error: any) => void
}): Promise<void> {
  const params = new URLSearchParams({ requirement, questionCount: String(questionCount), wordCount: String(wordCount || 300), provider })
  if (userId != null && userId !== '') params.append('userId', String(userId))
  if (thinking !== undefined && thinking !== null) params.append('thinking', String(thinking))
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/generate/composite/stream?${params.toString()}`
  console.log('【流式组合题】请求URL:', url)
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''
    let chunkIndex = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      let chunk = decoder.decode(value)
      chunkIndex++
      if (chunk) {
        chunk = chunk.replace(/\[DONE\]/g, '')
        if (chunk) {
          fullContent += chunk
          onChunk?.(fullContent)
        }
      }
    }
    onComplete?.(fullContent)
  } catch (error) {
    console.error('【流式组合题】请求异常:', error)
    onError?.(error)
  }
}

// 流式生成组合题（智能解析版）
export async function generateReadingComprehensionStream(
  requirement: string,
  questionCount: string | number,
  provider: string,
  onMessage?: (content: string) => void,
  onComplete?: (data: any) => void,
  onError?: (error: any) => void
): Promise<void> {
  const params = new URLSearchParams({ requirement, questionCount: String(questionCount), provider })
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/generate/reading/stream?${params.toString()}`

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''
    let lastParsedJson: any = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)

      if (chunk && chunk !== '[DONE]') {
        fullContent += chunk
        onMessage?.(fullContent)

        try {
          const parsed = JSON.parse(fullContent)
          lastParsedJson = parsed
        } catch (e) { }
      }
    }

    if (lastParsedJson) {
      onComplete?.(lastParsedJson)
    } else {
      const fixed = fixJsonContent(fullContent)
      try {
        onComplete?.(JSON.parse(fixed))
      } catch (e) {
        onError?.(new Error('JSON 解析失败'))
      }
    }
  } catch (error) {
    onError?.(error)
    throw error
  }
}

// 修复 JSON 格式
function fixJsonContent(content: string): string {
  if (!content) return ''

  let fixed = content
    .replace(/data:\s*/g, '')
    .replace(/\[DONE\]/g, '')
    .trim()

  fixed = fixed.replace(/"([^"]*?)"([^"]*?)"([^"]*?)"/g, function (match, before, middle, after) {
    return '"' + before + '\\"' + middle + '\\"' + after + '"'
  })

  fixed = fixed.replace(/:\s*"([^"]*)"/g, function (match, value) {
    const escaped = value.replace(/(?<!\\)"/g, '\\"')
    return ': "' + escaped + '"'
  })

  const lastCompleteIndex = Math.max(
    fixed.lastIndexOf('}]'),
    fixed.lastIndexOf('"}'),
    fixed.lastIndexOf(']'),
    fixed.lastIndexOf('}')
  )
  if (lastCompleteIndex > 0 && lastCompleteIndex < fixed.length - 1) {
    fixed = fixed.substring(0, lastCompleteIndex + 1)
  }

  const openBrackets = (fixed.match(/\[/g) || []).length
  const closeBrackets = (fixed.match(/\]/g) || []).length
  if (openBrackets > closeBrackets) {
    fixed += ']'.repeat(openBrackets - closeBrackets)
  }

  const openBraces = (fixed.match(/\{/g) || []).length
  const closeBraces = (fixed.match(/\}/g) || []).length
  if (openBraces > closeBraces) {
    fixed += '}'.repeat(openBraces - closeBraces)
  }

  return fixed
}

// 生成普通题目（非流式，一次性返回）
export function generateQuestionsSync(data: any) {
  return request({
    url: '/ai/generate/questions/sync',
    method: 'post',
    data: data,
    timeout: 120000
  })
}

// 生成组合题/阅读理解题（非流式，一次性返回）
export function generateReadingComprehensionSync(data: any) {
  return request({
    url: '/ai/generate/composite/sync',
    method: 'post',
    data: data,
    timeout: 120000
  })
}

// 获取题库AI上下文信息
export function getBankContextInfo(bankId: number | string) {
  return request({
    url: `/ai/bank/context/${bankId}`,
    method: 'get'
  })
}

// 清空题库对话上下文
export function clearBankConversation(bankId: number | string) {
  return request({
    url: `/ai/conversation/bank/${bankId}`,
    method: 'delete'
  })
}

// 生成题目（带题库上下文）
export function generateQuestionsWithContext(data: any) {
  return request({
    url: '/ai/generate/questions/sync',
    method: 'post',
    data: data,
    timeout: 120000
  })
}

/**
 * 助手流式聊天
 */
export async function assistantStream(
  message: string,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void,
  signal?: AbortSignal,
  provider?: string,
  userId?: string | number,
  sessionId: string = 'assistant',
  thinking?: boolean
): Promise<void> {
  const params = new URLSearchParams({ message, sessionId })
  if (provider) params.append('provider', provider)
  if (userId != null && userId !== '') params.append('userId', String(userId))
  // 深度思考开关：true/false 覆盖数据库里的 thinking_mode，不传则跟随配置
  if (thinking !== undefined && thinking !== null) params.append('thinking', String(thinking))
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/assistant/stream?${params.toString()}`

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() },
      signal
    })

    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      let chunk = decoder.decode(value)

      // 本项目后端返回纯文本流，仅在结束时附带 [DONE] 标记
      if (chunk) {
        chunk = chunk.replace(/\[DONE\]/g, '')
        if (chunk) {
          fullContent += chunk
          onChunk?.(fullContent)
        }
      }
    }
    onComplete?.(fullContent)
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.log('请求已取消')
      return
    }
    onError?.(error)
  }
}

/**
 * AI 搭建题库：支持图片的流式生成（POST，对接 /ai/assistant/generate-with-images）
 * images 为 base64 data URL 数组
 */
export async function generateWithImagesStream(
  message: string,
  images: string[],
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void,
  signal?: AbortSignal,
  provider?: string,
  thinking?: boolean
): Promise<void> {
  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/assistant/generate-with-images`

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message, images, provider, thinking }),
      signal
    })

    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      let chunk = decoder.decode(value)
      if (chunk) {
        chunk = chunk.replace(/\[DONE\]/g, '')
        if (chunk) {
          fullContent += chunk
          onChunk?.(fullContent)
        }
      }
    }
    onComplete?.(fullContent)
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.log('请求已取消')
      return
    }
    onError?.(error)
  }
}

// 获取对话历史
export function getConversationHistory(sessionId: string | number, userId?: string | number) {
  return request({
    url: `/ai/conversation/${sessionId}`,
    method: 'get',
    params: { userId }
  })
}

// 清空对话
export function clearConversation(sessionId: string | number, userId?: string | number) {
  return request({
    url: `/ai/conversation/${sessionId}`,
    method: 'delete',
    params: { userId }
  })
}

// 会话列表
export function listSessions(userId?: string | number) {
  return request({
    url: '/ai/sessions',
    method: 'get',
    params: { userId }
  })
}

// 新建会话（sessionId 由后端生成，并立即写入会话列表）
export function createSession(userId?: string | number) {
  return request({
    url: '/ai/sessions',
    method: 'post',
    params: { userId }
  })
}

// 删除会话
export function deleteSession(sessionId: string | number, userId?: string | number) {
  return request({
    url: `/ai/sessions/${sessionId}`,
    method: 'delete',
    params: { userId }
  })
}


/**
 * 题目智能解析（流式）
 * deepThink=true 时后端开启深度思考，但**只下发正式回答**（思考过程不下发），
 * 前端用「思考中」动画占位即可。
 * 注：onReasoningChunk 参数仅为兼容旧调用而保留，已不再回传思考内容。
 */
export async function analyzeQuestionStream(
  question: string,
  questionType?: string,
  options?: string,
  correctAnswer?: string,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void,
  provider?: string,
  userId?: string | number,
  deepThink?: boolean,
  onReasoningChunk?: (reasoning: string) => void
): Promise<void> {
  const params = new URLSearchParams({ question })
  if (questionType) params.append('questionType', questionType)
  if (options) params.append('options', options)
  if (correctAnswer) params.append('correctAnswer', correctAnswer)
  if (provider) params.append('provider', provider)
  if (userId != null && userId !== '') params.append('userId', String(userId))
  if (deepThink) params.append('deepThink', 'true')

  const url = `${import.meta.env.VITE_APP_BASE_API}/ai/analyze/question/stream?${params.toString()}`

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      let chunk = decoder.decode(value)
      if (!chunk) continue
      // 后端返回纯文本流，仅在结束时附带 [DONE]；思考内容不会下发
      chunk = chunk.replace(/\[DONE\]/g, '')
      if (!chunk) continue
      fullContent += chunk
      onChunk?.(fullContent)
    }
    onComplete?.(fullContent)
  } catch (error) {
    onError?.(error)
  }
}
