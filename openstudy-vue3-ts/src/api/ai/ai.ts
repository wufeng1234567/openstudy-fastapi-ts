import request from '@/utils/request'
import { getToken } from '@/utils/auth'
import {
  buildDocPreview,
  collectDocImages,
  dataUrlToFile,
  isDocFile,
  parseDocFile,
  resolveFileName
} from '@/utils/doc-parse'

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

/**
 * 解析文件为结构化块（含图片提取）
 *
 * 实现已搬到 `@/utils/doc-parse`（聊天助手的附件在线预览走同一套，必须单一事实来源），
 * 这里 re-export 是为了保持旧调用方（`AiQuestionBuilder.vue`）的 import 不变。
 */
export { parseFileBlocks } from '@/utils/doc-parse'

/** {@link postAiStream} 的入参：一次「AI 流式轮次」的全部信息 */
export interface AiStreamOptions {
  /**
   * 场景，对应后端 `app/services/ai/prompts.py` 里的 `SCENE_*`：
   * `assistant`（OS 助手）/ `question-bank`（AI 搭建题库）/
   * `question-generate`（批量出题）/ `reading` / `composite` / `analysis`。
   * 决定后端用哪套系统提示词与用户模板。
   */
  scene: string
  /** 正文。聊天 = 用户输入；出题 = 知识点 / 要求；题库搭建 = 前端拼好的长指令 */
  prompt: string
  /** 场景模板变量：count / knowledge_point / question_type / requirement / question … */
  variables?: Record<string, any>
  /** 图片附件，base64 data URL 数组 */
  images?: string[]
  /** 文档附件 `{ name, type, base64 }`，base64 为完整 data URL，服务端抽正文 */
  files?: { name: string; type: string; base64: string }[]
  /**
   * 仅用于**历史落库**的附件元信息（原图 / 原件都不入库）：
   *   · 图片 `{name,type,thumb,preview}` —— thumb 列表小图、preview 点开查看图；
   *   · 文档 `{name,type,blocks:[…]}` —— 有序图文块，供聊天记录里的在线预览。
   * 由 `buildAttachmentMetas()` 生成，非聊天场景（不落库）留空。
   */
  attachments?: any[]
  model?: string
  provider?: string
  /** 会话 id。**只有聊天助手传**（形如 `asst_xxx`）；留空 = 不写聊天历史 */
  sessionId?: string
  userId?: string | number
  /** 深度思考：true / false 覆盖 DB 配置；不传则跟随配置 */
  thinking?: boolean
  /** 采样温度。不传 = 后端默认 0.7；出题类沿用历史口径 0.8 */
  temperature?: number
  signal?: AbortSignal
}

/**
 * **全平台唯一的 AI 流式请求函数**
 *
 * 所有 AI 流式能力（OS 助手 / AI 搭建题库 / 批量出题 / 阅读理解 / 组合题 / 题目解析）
 * 最终都调它 → `POST {VITE_APP_BASE_API}/ai/assistant/stream`，
 * 后端再统一交给 `services/ai/chat_engine.py` 的 `stream_turn()`。
 *
 * 为什么必须收敛到一处：改造前每个能力各自 `fetch` + 各自写一遍读流解析，
 * 结果就是「同一个能力，助手能用、搭建题库用不了」（附件就是这么坏的），
 * 而且「Error: xxx」的错误契约只有助手那条链路处理了，别的链路会把报错
 * 当成 AI 回复显示出来。现在改提示词 / 加模型能力 / 修事件流解析都只改一处。
 *
 * @returns 累积的完整回复文本；失败（含主动中止）时返回 `''` 并通过 `onError` 告知。
 */
async function postAiStream(
  opts: AiStreamOptions,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void
): Promise<string> {
  let full = ''
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/assistant/stream`, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: opts.prompt ?? '',
        scene: opts.scene,
        variables: opts.variables || {},
        images: opts.images || [],
        files: opts.files || [],
        attachments: opts.attachments || [],
        provider: opts.provider,
        model: opts.model,
        // 空串 = 后端不写聊天历史（出题类一次性生成都不该进历史表）
        sessionId: opts.sessionId || '',
        userId: normalizeUserId(opts.userId),
        thinking: opts.thinking,
        temperature: opts.temperature
      }),
      signal: opts.signal
    })

    await consumeAssistantStream(
      response,
      (text: string) => {
        full = text
        onChunk?.(text)
      },
      (text: string) => {
        full = text
        onComplete?.(text)
      },
      onError
    )
    return full
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      // 用户点了「停止生成」：不算错误，交给调用方自行收尾
      console.log('请求已取消')
      return ''
    }
    onError?.(error)
    return ''
  }
}

export async function generateQuestionsStreamFull({ knowledgePoint, questionType, count, model, userId, bankId, thinking, onChunk, onComplete, onError }: {
  knowledgePoint: string
  questionType: string
  count: string | number
  model: string
  userId?: string | number
  bankId?: string | number
  /** 深度思考：true/false 覆盖 DB 配置；不传则跟随配置 */
  thinking?: boolean
  onChunk?: (content: string) => void
  onComplete?: (content: string) => void
  onError?: (error: any) => void
}): Promise<void> {
  // 统一走后端 chat_engine（scene=question-generate）：系统提示词与用户模板
  // 都由后端 `prompts.py` 提供，温度固定 0.8，与改造前的出题口径一致。
  // bankId 仅为兼容旧调用方签名保留：流式生成本身不落库，保存题目由调用方负责。
  void bankId
  await postAiStream(
    {
      scene: 'question-generate',
      prompt: knowledgePoint,
      variables: {
        knowledge_point: knowledgePoint,
        question_type: questionType,
        count: Number(count) || 5
      },
      model,
      userId,
      thinking,
      // 出题沿用历史口径：温度 0.8
      temperature: 0.8
    },
    onChunk,
    onComplete,
    onError
  )
}

export async function generateCompositeStreamFull({ requirement, questionCount, wordCount, model, userId, thinking, onChunk, onComplete, onError }: {
  requirement: string
  questionCount: string | number
  wordCount?: string | number
  model: string
  userId?: string | number
  /** 深度思考：true/false 覆盖 DB 配置；不传则跟随配置 */
  thinking?: boolean
  onChunk?: (content: string) => void
  onComplete?: (content: string) => void
  onError?: (error: any) => void
}): Promise<void> {
  // 统一走后端 chat_engine（scene=composite），温度 0.8，与改造前口径一致。
  await postAiStream(
    {
      scene: 'composite',
      prompt: requirement,
      variables: {
        requirement,
        question_count: Number(questionCount) || 5,
        word_count: Number(wordCount) || 300
      },
      model,
      userId,
      thinking,
      // 出题沿用历史口径：温度 0.8
      temperature: 0.8
    },
    onChunk,
    onComplete,
    onError
  )
}

/**
 * 批量出题（兼容包装）
 *
 * ⚠️ 当前代码库里**没有调用方**（历史遗留的「智能解析版」入口），保留是为了不破坏
 * 公共 API。内部已改为走 {@link postAiStream}（scene=question-generate），
 * 不再自己 fetch / 解析流。
 */
export async function generateQuestionsStream(
  knowledgePoint: string,
  questionType: string,
  count: string | number,
  model: string,
  onMessage?: (content: string) => void,
  onComplete?: (data: any) => void,
  onError?: (error: any) => void
): Promise<void> {
  let lastParsedJson: any = null
  const full = await postAiStream(
    {
      scene: 'question-generate',
      prompt: knowledgePoint,
      variables: {
        knowledge_point: knowledgePoint,
        question_type: questionType,
        count: Number(count) || 5
      },
      model,
      // 出题沿用历史口径：温度 0.8（发散更强，题目更丰富）
      temperature: 0.8
    },
    (text) => {
      onMessage?.(text)
      // 流式过程中若已能解析出完整 JSON，就地记下来，结束时不必再猜
      try {
        lastParsedJson = JSON.parse(text)
      } catch {
        /* 解析失败是正常的，继续累积 */
      }
    },
    undefined,
    onError
  )
  // 失败 / 中止：postAiStream 已经交给 onError，这里不再重复回调
  if (!full) return
  if (lastParsedJson) {
    onComplete?.(lastParsedJson)
    return
  }
  try {
    onComplete?.(JSON.parse(fixJsonContent(full)))
  } catch {
    onComplete?.(full)
  }
}

/**
 * 阅读理解题生成（兼容包装）
 *
 * ⚠️ 当前代码库里**没有调用方**。同上，内部已收敛到 {@link postAiStream}
 * （scene=reading），不再自己 fetch / 解析流。
 */
export async function generateReadingComprehensionStream(
  requirement: string,
  questionCount: string | number,
  model: string,
  onMessage?: (content: string) => void,
  onComplete?: (data: any) => void,
  onError?: (error: any) => void
): Promise<void> {
  let lastParsedJson: any = null
  const full = await postAiStream(
    {
      scene: 'reading',
      prompt: requirement,
      variables: { requirement, question_count: Number(questionCount) || 5 },
      model,
      // 出题沿用历史口径：温度 0.8
      temperature: 0.8
    },
    (text) => {
      onMessage?.(text)
      try {
        lastParsedJson = JSON.parse(text)
      } catch {
        /* 继续累积 */
      }
    },
    undefined,
    onError
  )
  if (!full) return
  if (lastParsedJson) {
    onComplete?.(lastParsedJson)
    return
  }
  try {
    onComplete?.(JSON.parse(fixJsonContent(full)))
  } catch {
    onError?.(new Error('JSON 解析失败'))
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
 * 助手系统提示词缓存（来自后端 /ai/prompts/assistant）
 *
 * ds-free 走前端直连、不经后端 assistant/stream，所以系统提示词要从后端取；
 * 缓存一次，避免每条消息都请求。
 */
let _assistantPromptCache: string | null = null

export async function fetchAssistantPrompt(): Promise<string> {
  if (_assistantPromptCache !== null) return _assistantPromptCache
  try {
    const resp = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/prompts/assistant`, {
      headers: { 'Authorization': 'Bearer ' + getToken() }
    })
    if (!resp.ok) return ''
    const json = await resp.json()
    // 后端统一响应体：{ code, msg, data: { assistant } }
    _assistantPromptCache = json?.data?.assistant || json?.assistant || ''
    return _assistantPromptCache
  } catch (e) {
    console.warn('[ds-free] 获取后端助手提示词失败，将不带系统提示词:', e)
    return ''
  }
}

/** 把 userId 规整成后端要的整数（非数字 / 空值 → undefined，JSON 序列化时会被忽略） */
function normalizeUserId(userId?: string | number): number | undefined {
  if (userId === null || userId === undefined || userId === '') return undefined
  const n = Number(userId)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

/**
 * 消费助手的后端事件流（GET / POST 两个入口共用）
 *
 * 后端契约（见 `app/api/v1/ai.py` 的 `_assistant_event_stream`）：
 *   · 正文 → 直接下发增量分片，这里累积成全文后回调 onChunk
 *   · 失败 → 下发 `Error: <原因>`（**只在还没有任何正文时**才算真失败）
 *   · 结束 → 下发 `[DONE]`
 * 抽成公共函数是为了让「带附件的 POST」和「纯文字 GET」保持完全一致的解析口径。
 */
async function consumeAssistantStream(
  response: Response,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void
): Promise<void> {
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

  // 后端在「请求本身不合法」时（例如附件全部解析失败、且没写文字）返回的是
  // JSON 错误信封而不是事件流。若直接当正文解析，用户会看到一串原始 JSON，
  // 所以先按 Content-Type 分流，取出 msg 交给 onError。
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    let msg = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      msg = body?.msg || body?.message || msg
    } catch {
      /* 拿不到 msg 就用默认文案 */
    }
    onError?.(new Error(msg))
    return
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let fullContent = ''
  let streamError = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    let chunk = decoder.decode(value)
    if (!chunk) continue
    // 本项目后端返回纯文本流，仅在结束时附带 [DONE] 标记
    chunk = chunk.replace(/\[DONE\]/g, '')
    if (!chunk) continue

    // 后端流式出错时下发 `Error: xxx`。模型一调用就失败时（例如配置缺 API Key），
    // 这是拿到的**第一个**分片，交给 onError 走「发送失败 + 原因」的分支，
    // 避免把英文报错当成 AI 回复。
    // 只有「整段分片以 Error: 开头」且此前无正文才认定是错误，正文里恰好含这几个字不会误判。
    if (chunk.indexOf('Error: ') === 0 && !fullContent) {
      streamError = chunk.slice(7).trim()
      break
    }
    fullContent += chunk
    onChunk?.(fullContent)
  }

  if (streamError) {
    onError?.(new Error(streamError))
    return
  }
  onComplete?.(fullContent)
}

/**
 * 助手 / 场景化 AI 流式对话
 *
 * 后端侧统一落到 `POST /ai/assistant/stream`（见 {@link postAiStream}），
 * 再交给 `services/ai/chat_engine.py` 的 `stream_turn()`。场景由 `extras.scene`
 * 指定，所以「OS 助手」和「AI 搭建题库」走的是**同一个接口**，不再是两个。
 */
export async function assistantStream(
  message: string,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void,
  signal?: AbortSignal,
  model?: string,
  userId?: string | number,
  /**
   * 会话 id（形如 `asst_xxx`）。**只有聊天助手需要传**；
   * 出题类一次性生成留空 → 后端不写聊天历史，避免污染会话表。
   */
  sessionId: string = '',
  thinking?: boolean,
  /**
   * 附加参数
   * - scene / variables：场景与模板变量（见 {@link AiStreamOptions}）。
   *     不传 scene 时按 `assistant` 处理 —— 也只有该场景才会用 sessionId 落历史。
   * - images / files：附件数组 [{ name, type, base64 }]，base64 为**完整 data URL**。
   *     · 选到 `deepseek-free` → 交给浏览器扩展，由 DS 网页端上传；
   *     · 其它模型 → 走后端多模态通道，附件不再被忽略。
   * - systemPrompt：系统提示词（仅 ds-free 需要，DS 网页版没有 system role）。
   * - provider：显式指定供应商（一般用 model 就够了）。
   * - turnId：**本轮的轮次 id**。只有 ds-free 分支用它（补写历史要带上，
   *   见 `saveConversationMessages` 的 `turnId`）；不传时**自己生成一个**，
   *   两次补写共用同一个 —— 少了它，落库的行 `turn_id` 是空串，
   *   用户点「回退」时服务端一行都匹配不到（`dropped: 0`，还带成功样式）。
   */
  extras?: {
    images?: any[]
    files?: any[]
    systemPrompt?: string
    scene?: string
    variables?: Record<string, any>
    provider?: string
    turnId?: string
  }
): Promise<void> {
  // ---- deepseek-free：走浏览器扩展（DeepSeek 官网 Web 版），完全不经过后端 ----
  // 这个分支是**在用**的（从模型下拉框选到 model='deepseek-free' 就会走这里），
  // 不是兜底死代码：聊天助手的「只发图片/文件、不写文字」能力依赖它。
  if (model === 'deepseek-free') {
    if (signal?.aborted) return

    // 只给「真正的聊天会话」补写历史：会话 id 一律由后端生成（asst_ 前缀）。
    // 出题类一次性生成（AI 搭建题库 / 批量出题…）不带 sessionId（默认为空串），
    // 持久化整体跳过，不会往历史表里塞数据。
    const persistSessionId =
      typeof sessionId === 'string' && sessionId.startsWith('asst_') ? sessionId : ''

    /**
     * 本轮的轮次 id —— **一次提问一个**，下面两次补写（先写提问、后补回复）共用它。
     *
     * 为什么在这里算：两次补写都在本函数里发起，只有这里能保证「跨调用一致」
     * （两次拿到的必须是同一个 id，否则回退只能删掉其中一行）。
     * 调用方有 id（例如智能体链路那种「一次提问一个 id」的页面）就从 `extras.turnId`
     * 传进来；没有（普通聊天链路，本来就没有轮次概念）就现生成一个 ——
     * 落库的行至少要带上「属于哪一轮」这个信息，回退才有凭据。
     */
    const persistTurnId = String(extras?.turnId || '') || newPersistTurnId()

    // 本轮的累积全文（扩展 SDK 的 onChunk 给的是增量，这里统一成「累积」）
    let acc = ''

    // 文档解析：DS 网页端只会读 Word / PDF 里的**文字**，文档内的插图会被直接丢掉。
    // 这里先在前端把插图解析出来，当作图片附件一起上传，AI 才能真正「看到」图。
    // （官方 API 链路不需要这么做：后端 chat_engine.extract_attachments() 已经抽了，
    //   前端再传一遍会变成重复图片。）
    // 同一份解析结果还会被压成预览块落库，供聊天记录里的「在线预览」使用。
    const { map: docPreviews, docs: parsedDocs } = await parseDocsForPreview(extras?.files)
    const dsImages = [...(extras?.images || []), ...(await collectDocImages(parsedDocs))]

    // ① 提问先落库：ds-free 完全绕过后端，历史只能前端补写。若等回复结束再写，
    //    一旦回复为空 / 超时 / 用户刷新页面，整轮都不见了 —— 用户看到的就是
    //    「刷新后历史会话是空的」。这里发送即写，附件在写入时才生成缩略图。
    const userSaved = persistSessionId
      ? persistDsFreeUserTurn({
          userId,
          sessionId: persistSessionId,
          userMessage: message,
          images: extras?.images,
          files: extras?.files,
          docPreviews,
          // 本轮 id：与下面补写回复那一次**必须逐字相同**（回退按它删整轮）
          turnId: persistTurnId
        })
      : Promise.resolve()

    try {
      const { chatWithDSAccumulated, setDeepThink } = await import('@/utils/ds-proxy')
      // 深度思考是 DS 页面上的开关，需要先同步过去再发消息
      if (thinking !== undefined && thinking !== null) {
        await setDeepThink(thinking)
      }
      const full = await chatWithDSAccumulated({
        userMessage: message,
        // 提示词注入：DS 网页版没有 system role，由封装层拼接在用户消息前。
        // 提示词从后端取（单一事实来源），调用方也可用 extras.systemPrompt 覆盖。
        systemPrompt: extras?.systemPrompt || (await fetchAssistantPrompt()),
        // 图片附件：DS 官网现已默认支持，直传 data URL；
        // 末尾追加「文档里的插图」，否则带图 Word 的图 AI 看不到。
        images: dsImages,
        // 文档附件（Word / PDF / md / txt 等）：走扩展的 fileDataList 通道
        files: extras?.files || [],
        onChunk: (text: string) => {
          acc = text
          onChunk?.(text)
        }
      })
      if (!acc && full) {
        acc = full
        onChunk?.(full)
      }
      onComplete?.(acc)
    } catch (error: any) {
      onError?.(error)
    } finally {
      // ② 回复等「稳定」后再补写（成功 / 报错 / 中断都会走到这里）。
      //    必须串在提问落库之后，否则回复行可能拿到比提问更小的 id，
      //    历史里的顺序就会变成「先回复后提问」。
      if (persistSessionId) {
        void (async () => {
          try {
            await userSaved
          } catch {
            /* 提问落库失败已在内部告警，这里不阻断回复落库 */
          }
          await persistDsFreeAssistant({
            userId,
            sessionId: persistSessionId,
            getText: () => acc,
            // 用户点了「停止生成」时用「已停止生成」而不是「检查扩展」的说明
            aborted: signal?.aborted === true,
            // 与先写提问那一次同一个 id（这一行漏了，回退就只能删掉提问行）
            turnId: persistTurnId
          })
        })()
      }
    }
    return
  }

  // ---- 官方 API（后端）分支：统一走 postAiStream ----
  // 不再区分「有附件走 POST / 纯文字走 GET」：附件位置、长文本（GET 会撞 URL 长度
  // 上限）、scene / variables 只有 POST 能完整表达。纯文字以前走 GET 只是为了
  // 「能贴进浏览器调试」，现在那件事由后端保留的 GET 兼容路由承担，应用内只留一条链路。
  // 图片：兼容两种写法 —— `string`（本身就是 base64 data URL）或 `{ base64 }` 对象。
  // AI 搭建题库用的是字符串数组，聊天助手用的是对象数组（带缩略图元信息）。
  const images = (extras?.images || [])
    .map((a: any) => (typeof a === 'string' ? a : a?.base64 || ''))
    .filter(Boolean)
  const files = (extras?.files || [])
    .map((f: any) => ({
      name: f?.name || 'file',
      type: f?.type || '',
      base64: f?.base64 || ''
    }))
    .filter((f: { base64: string }) => !!f.base64)

  // 只有聊天助手场景才带 sessionId —— 出题类一次性生成不能写进聊天历史
  const scene = extras?.scene || 'assistant'

  // attachments 只服务于**历史落库**：
  //   · 图片 → 列表小图（thumb）+ 点开查看图（preview），原图不入库；
  //   · 文档 → 解析出来的图文块（blocks），供聊天记录里的「在线预览」。
  // 这样刷新后既看得清图，也能点开文档看内容，又不会把 ai_chat_message 撑爆
  // （该列已是 MEDIUMTEXT）。
  // 非聊天场景不落库，所以这些都不必生成。
  const attachments =
    scene === 'assistant' && (images.length || files.length)
      ? await buildAttachmentMetas(
          extras?.images,
          extras?.files,
          (await parseDocsForPreview(files)).map
        )
      : []

  await postAiStream(
    {
      scene,
      prompt: message,
      variables: extras?.variables,
      images,
      files,
      attachments,
      model,
      provider: extras?.provider,
      sessionId: scene === 'assistant' ? sessionId : '',
      userId,
      thinking,
      signal
    },
    onChunk,
    onComplete,
    onError
  )
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
 * 补写一轮对话到会话历史（SQL，服务端原子写入）
 *
 * ds-free 的请求由浏览器扩展代发给 chat.deepseek.com，**完全不经过后端**，
 * 所以后端没有机会保存历史 —— 刷新页面后会话就是空的。
 * 前端会调用两次：发送后先写提问（+附件缩略图），回复稳定后再写回复；
 * 后端把「提问 + 回复」放在一个事务里，不会出现半截会话。
 */
export function saveConversationMessages(
  sessionId: string | number,
  body: {
    userMessage: string
    assistantMessage: string
    /** [{name, type, thumb}]，thumb 是小缩略图（不传原图） */
    attachments?: any[]
    /**
     * **这一轮的轮次 id**（一次用户提问一个）—— 落进 `ai_chat_message.turn_id`
     *
     * 它是「回退这一轮对话」的唯一凭据：`POST /ai/conversation/drop-turn` 按
     * `(user_id, sessionId, turnId)` 命中行，**行上没有它 = 一行都匹配不到**，
     * 用户点回退时服务端只能回 `dropped: 0`（还带 `code:200` 的成功样式）。
     *
     * ⚠️ **先写提问、后补回复是两次调用，两次必须带同一个 id**（见 `persistDsFreeUserTurn`
     *    的注释）；带成两个 id，回退时就只能撤掉其中一行。
     * ⚠️ 后端 `SaveConversationBody` 收这个字段并透传给 `save_turn` —— 但**它是显式声明的
     *    字段**（pydantic 默认忽略未知字段，字段名对不上会被静默丢掉，落库全是空串）。
     * ⚠️ 可选是为了不改老调用方；**凡是有轮次概念的那条链路都必须传**。
     */
    turnId?: string
  },
  userId?: string | number
) {
  return request({
    url: `/ai/conversation/${sessionId}/messages`,
    method: 'post',
    params: { userId },
    data: body
  })
}

/**
 * 保存智能体「完整时间线快照」（含工具调用卡片）
 *
 * `saveConversationMessages` 只存「提问 + 最终回复」两行，**不含工具卡片** —— 刷新后
 * 卡片全丢、只剩纯文本（用户说的「变成死数据」）。这里把前端 `useAgentChat` 的整条
 * 消息流按会话存一份 JSON，加载时优先用它复原，卡片样式与状态就都还在。
 */
export function saveAgentTimeline(
  sessionId: string | number,
  messages: any[],
  userId?: string | number
) {
  return request({
    url: `/ai/conversation/${sessionId}/agent-timeline`,
    method: 'put',
    params: { userId },
    data: { messages }
  })
}

/** 读取智能体「完整时间线快照」（空数组 = 没有快照，调用方退回普通消息行） */
export function getAgentTimeline(sessionId: string | number, userId?: string | number) {
  return request({
    url: `/ai/conversation/${sessionId}/agent-timeline`,
    method: 'get',
    params: { userId }
  })
}

/**
 * `dropAgentTurn()` 的返回 —— 调用方靠它区分「真删掉了」与「服务端 200 却什么都没删」
 *
 * ⚠️ 字段名是**界面契约**（`useAgentChat.rollbackTurn` 的 `TurnRollbackOutcome.dropped`
 * 就是它，UI 拿它决定「这一轮的对话到底删没删」），改名等于让回退结果说不清。
 */
export interface AgentDropTurnResult {
  /** 服务端确认删掉了（判据见下：`code === 200` **且** `data` 里有 `dropped`） */
  ok: boolean
  /** `ok = false` 的原因（服务端原话，直接给用户看；`ok = true` 时是空串） */
  reason: string
  /**
   * 被逻辑删掉的消息行数（`0` 也是**成功** —— 这个接口是幂等的：
   * 同一轮再点一次就是「已经删过了」，服务端回 `dropped: 0` 而不是报错）。
   */
  dropped: number
  /**
   * 服务端「按 `(user_id, session_id, turn_id)` **不考虑 `del_flag`** 命中的行数」
   *
   * 它回答 `dropped` 回答不了的那个问题：**这一轮在服务端历史里有没有轮次标记**。
   *   · `0` + `dropped: 0` → 那一轮的行 `turn_id` 是空串（ds-free 补写历史时前端还没带
   *     `turnId` 的旧数据）→ 服务端**一行都匹配不到**；
   *   · `> 0` + `dropped: 0` → **已经删过了**（幂等重试的正常回执）。
   * 界面据此把这两件事分开说；但它**不是** `ok` 的判据，也**不改变任何一步**。
   * 老后端没这个字段时归 0（形状恒定，UI 不用写判空分支）。
   */
  matched: number
}

/**
 * 把**某一轮**的对话从会话历史里逻辑删掉（`POST /ai/conversation/drop-turn`）
 *
 * 「回退」这个功能要撤掉的东西有两样，**分属两个接口**：
 *   · 这一轮产生的**写操作**（建了哪个题库 / 删了哪道题…）→ `rollbackAgentTurn()`（`api/ai/agent.ts`）；
 *   · 这一轮的**对话**本身（提问 + 回答 + 工具过程）→ 本函数。
 * 用户点一次「回退」是两件事一起做；顺序与失败语义由 `useAgentChat.rollbackTurn` 负责，
 * 这里只负责把这一半如实做掉、把结果如实端回来。
 *
 * ## 为什么走原生 `fetch`、而不是本文件里到处在用的 `request()`
 * 因为 `request` 的响应拦截器**会把服务端那句原话丢掉**：`utils/request.ts` 里
 * `code !== 200` 的分支是 `ElNotification.error(...)` 之后 `Promise.reject('error')` ——
 * 上抛的只是一个字符串 `'error'`，`msg` 和 `code` 都拿不到了。
 * 而本接口的失败几乎全是**业务信封**（缺 `turnId` → `HTTP 200 + code=400`），
 * 「缺哪个参数」这句话恰恰是用户和排查者唯一需要的信息。
 * 所以与 `api/ai/agent.ts` 的 `rollbackAgentTurn()` **同一口径**：原生 fetch + 自己判信封。
 *
 * ## 为什么 `ok` 不是 `res.ok`（`catch_all` 会伪造成功）
 * 本仓 `catch_all`（`app/main.py` 最后注册）把任何未匹配路径变成
 * `HTTP 200 + {code:200, msg:'操作成功', data:null}`：路由写错时看到的是一句「操作成功」。
 * 所以判据只能是「`code === 200` **且** `data` 里有一个数字 `dropped`」——
 * 少了后半句，一次根本没发生的删除会被判成成功，用户看到「已删除」而库里还在。
 *
 * ## 失败原因一律取服务端原话
 * `code !== 200` 时把 `msg` 连同 code 一起带出来；`code === 200` 时**不许**用 `msg`
 * —— 那是 `catch_all` 那句假成功。
 *
 * ## 没有 `turnId` 时**不**在本地短路
 * `rollbackAgentTurn()` 对空 `turnId` 是「一个请求都不发、本地如实报缺参数」；
 * 这里**刻意不同**：本接口的契约明文规定了「缺 `turnId` → `HTTP 200 + code=400`」，
 * 也就是**服务端有话可说**，那就照「只搬运、不兜底」来（前端自己编一句等于两处口径）。
 */
export async function dropAgentTurn(params: {
  sessionId: string
  turnId: string
}): Promise<AgentDropTurnResult> {
  /** 失败时的退化值：形状恒定（`dropped: 0` / `matched: 0`），UI 不用写判空分支 */
  const fail = (reason: string): AgentDropTurnResult => ({
    ok: false,
    reason,
    dropped: 0,
    matched: 0
  })
  /** 只有 `code` 明确不是 200 才用 `msg`（200 那句「操作成功」是假成功的话，不能当理由） */
  const serverReason = (data: any): string => {
    const code = Number(data?.code)
    if (!Number.isFinite(code) || code === 200) return ''
    const msg = typeof data?.msg === 'string' ? data.msg.trim() : ''
    return msg ? `${msg}（服务端 code=${code}）` : ''
  }

  try {
    const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/conversation/drop-turn`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      // 请求体**只有这两个键**（契约冻结）：不带 userId —— 归属由服务端从令牌里取
      body: JSON.stringify({
        sessionId: String(params?.sessionId || ''),
        turnId: String(params?.turnId || '')
      })
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) return fail(serverReason(data) || `删除本轮对话失败（HTTP ${res.status}）`)

    const code = Number((data as any)?.code)
    if (code !== 200) return fail(serverReason(data) || '删除本轮对话被服务端拒绝')

    const d = (data as any)?.data
    // 判据落在「data 里有一个数字 dropped」上：`dropped: 0` 是**合法成功**（幂等），
    // 所以不能写成 `d.dropped > 0` —— 那样「再点一次」会被报成失败。
    if (!d || typeof d !== 'object' || typeof d.dropped !== 'number') {
      return fail('响应里没有删除结果（路由没匹配上？被 catch_all 兜成 200 假成功？）')
    }
    // `matched` 是**加法字段**：老后端（还没有它）不许因此判成失败 —— 归 0 即可。
    // ⚠️ 判据仍然是 `dropped` 的形状，**不是** `matched`：`matched: 0` 是合法结果
    //    （旧数据没有轮次标记），拿它当失败判据会让「从界面移除这一轮」永远做不到。
    const matched = typeof d.matched === 'number' && Number.isFinite(d.matched) ? Number(d.matched) : 0
    return { ok: true, reason: '', dropped: Number(d.dropped), matched }
  } catch (e: any) {
    return fail(String(e?.message || e))
  }
}

/** 单张缩略图生成的硬超时：解码卡住时不能把「落库」一起拖死 */
const THUMB_TIMEOUT_MS = 5000

/** 单个文档解析的硬超时（解析失败只是没预览，绝不能拖住发送） */
const DOC_PARSE_TIMEOUT_MS = 20000

/** 带超时的 Promise（超时 / 报错都返回兜底值，绝不抛出） */
function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise<T>((resolve) => {
    let settled = false
    const finish = (v: T) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(v)
    }
    const timer = setTimeout(() => finish(fallback), ms)
    p.then(finish).catch(() => finish(fallback))
  })
}

/** 文档附件解析出的预览块（图文交错），按文件名索引 */
export type DocPreviewMap = Map<string, { blocks: any[]; text: string; error?: string }>

/**
 * 把文档附件（Word / PDF / txt / md）解析成「可落库的预览块」
 *
 * 用途有两个，一次解析同时满足：
 *   ① 落进历史记录的附件元信息 → 聊天记录里点开文档就能在线预览（图文交错）；
 *   ② 返回的原始解析结果可用于抽取文档内嵌插图（见 collectDocImages）。
 *
 * 解析失败 / 超时都只是「没有预览」，附件照常发送，绝不阻断对话。
 */
async function parseDocsForPreview(
  files?: any[]
): Promise<{ map: DocPreviewMap; docs: any[] }> {
  const map: DocPreviewMap = new Map()
  const docs: any[] = []
  const targets = (files || []).filter((f) => isDocFile(f?.name || '', f?.type || ''))
  for (const f of targets) {
    const file = dataUrlToFile(f?.base64 || '', f?.name || 'file', f?.type || '')
    if (!file) continue
    const parsed = await withTimeout(parseDocFile(file), DOC_PARSE_TIMEOUT_MS, null)
    if (!parsed) continue
    docs.push(parsed)
    const preview = await buildDocPreview(parsed)
    if (preview) map.set(f.name || 'file', preview)
  }
  return { map, docs }
}

/**
 * 把附件转成**历史落库用**的元信息（原图 / 原件都不入库，避免撑大数据库）
 *
 *   · 图片：`thumb`（列表小图，长边 240）+ `preview`（点开查看图，长边 ≤1600）。
 *     只存 thumb 的话，刷新后点开就是「把 240px 拉满全屏」，糊到看不清。
 *   · 文档：`blocks`（图文交错的有序块，已把内嵌插图压到长边 1000 / ≤180KB）。
 *
 * 每一步都套一层超时：预览只是锦上添花，绝不能因为它而丢掉整轮历史。
 */
async function buildAttachmentMetas(
  images?: any[],
  files?: any[],
  docPreviews?: DocPreviewMap
): Promise<any[]> {
  const attachments: any[] = []
  if (images && images.length) {
    try {
      const { makeImageVariants } = await import('@/utils/image-compress')
      for (let i = 0; i < images.length; i++) {
        const img = images[i]
        const v = await withTimeout(makeImageVariants(img?.base64 || ''), THUMB_TIMEOUT_MS, {
          thumb: '',
          preview: ''
        })
        attachments.push({
          // 用文件自带的命名；只有剪贴板那种通用名（image.png）才兜底生成
          name: resolveFileName(img?.name, { mime: img?.type, label: '图片', index: i }),
          type: img?.type || 'image/png',
          thumb: v.thumb,
          preview: v.preview
        })
      }
    } catch (e) {
      console.warn('[附件] 生成图片缩略图失败，历史里只记录文件名:', e)
      for (let i = 0; i < images.length; i++) {
        const img = images[i]
        attachments.push({
          name: resolveFileName(img?.name, { mime: img?.type, label: '图片', index: i }),
          type: img?.type || 'image/png',
          thumb: '',
          preview: ''
        })
      }
    }
  }
  for (let i = 0; i < (files || []).length; i++) {
    const f = files![i]
    const name = resolveFileName(f?.name, { mime: f?.type, label: '附件', index: i })
    const preview = docPreviews?.get(f?.name || '')
    attachments.push({
      name,
      type: f?.type || '',
      thumb: '',
      // 文档的在线预览块（点开就能看内容）；老记录没有这个字段，前端会退回「暂不支持预览」
      ...(preview?.blocks?.length ? { blocks: preview.blocks } : {}),
      ...(preview?.error ? { error: preview.error } : {})
    })
  }
  return attachments
}

/** 附件元信息的「占位」形态：只有名字和类型 —— 发送瞬间就能把文件名渲染出来 */
export function attachmentPlaceholder(att: any): any {
  const isImage = (att?.type || '').startsWith('image/')
  return {
    name: resolveFileName(att?.name, { mime: att?.type, label: isImage ? '图片' : '附件' }),
    type: att?.type || '',
    thumb: '',
    preview: ''
  }
}

/**
 * 异步补齐附件元信息（图片缩略图 / 文档预览块），**就地写回传入的数组**。
 *
 * 用途：Agent 模式（抽屉里的助手、大屏智能体页）在**发送那一刻**就把附件推给
 * `useAgentChat` 渲染用户气泡，不能让「文档解析」把它拖住 ——
 * 单个文档的解析硬超时是 20s（见 `DOC_PARSE_TIMEOUT_MS`），而预览只是锦上添花。
 *
 * ⚠️ `target` 必须是 `reactive([])` 得到的**代理**：这里是通过下标改属性来触发刷新的，
 *    传普通数组的话界面不会跟着更新。
 */
export async function fillAttachmentMetas(
  target: any[],
  images?: any[],
  files?: any[]
): Promise<void> {
  try {
    const { map } = await parseDocsForPreview(files)
    const metas = await buildAttachmentMetas(images, files, map)
    metas.forEach((meta, i) => {
      if (target[i]) Object.assign(target[i], meta)
    })
  } catch (e) {
    console.warn('[附件] 补齐缩略图 / 文档预览块失败（附件照常发送）:', e)
  }
}

/**
 * 生成一个**轮次 id**（补写历史用）
 *
 * 形状 `t_<毫秒>_<随机 6 位>` —— 与 `composables/useAgentChat.ts` 的 `newTurnId()`
 * **逐字同形**（那边是「标准件」，这里是补写历史那条链路自己的那份）：
 *   · 毫秒时间戳 —— 日志 / 库里一眼看出先后；
 *   · 随机后缀 —— 同一毫秒内连发两次也不会撞车（撞了会把两轮的账本混成一炉）。
 *
 * 为什么 `api/ai/ai.ts` 不直接 import 那个函数：方向反了 —— `useAgentChat` import 本模块，
 * 反过来 import 会成环。两行纯函数各留一份，改形状时**两边一起改**。
 */
function newPersistTurnId(): string {
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 8).padEnd(6, '0')}`
}

/**
 * ds-free 专用：把「这一轮的提问」先写进历史（含附件缩略图）
 *
 * 返回 Promise 以便调用方串行化（保证回复行的 id 一定大于提问行）。
 *
 * ⚠️ `turnId` 必须与「稍后补写回复」那一次（`persistDsFreeAssistant`）**逐字相同**：
 *    后端按 `(user_id, sessionId, turnId)` 删除「这一轮对话」，两个 id 不带成一样，
 *    用户点一次回退就只能撤掉提问行或回复行之一。
 */
async function persistDsFreeUserTurn(params: {
  userId?: string | number
  sessionId: string
  userMessage: string
  images?: any[]
  files?: any[]
  /** 已解析好的文档预览块（避免重复解析一遍） */
  docPreviews?: DocPreviewMap
  /** 本轮的轮次 id（落进 `ai_chat_message.turn_id`，回退按它命中） */
  turnId?: string
}): Promise<void> {
  try {
    const attachments = await buildAttachmentMetas(
      params.images,
      params.files,
      params.docPreviews
    )
    await saveConversationMessages(
      params.sessionId,
      {
        userMessage: params.userMessage || '',
        assistantMessage: '',
        attachments,
        turnId: params.turnId || ''
      },
      params.userId
    )
  } catch (e) {
    console.warn('[ds-free] 提问落库失败（不影响本次对话）:', e)
  }
}

/** 回复文本为空时的占位说明（与前端气泡提示口径保持一致） */
const DS_FREE_NO_REPLY_NOTE =
  '（本次没有收到回复内容）请确认扩展侧的 chat.deepseek.com 已打开并登录，或在输入框里能正常发送，然后重试。'

/**
 * ds-free 专用：等回复文本「稳定」后补写 AI 回复
 *
 * 为什么要等稳定：扩展侧的 DONE 有两个来源 —— SSE 的 [DONE]，以及
 * 「静默 30s」的兜底定时器（见扩展 bridge.js 的 _doneTimer）。后者有时会在
 * 流式还没真正结束时先 resolve，此时前端拿到的文本只有半截甚至为空；
 * 直接落库就会写出空回复 / 半截回复，用户刷新后看到的是「AI 回复没了」。
 *
 * 于是这里轮询 getText()，当文本连续 settleMs 不再变化（且非空）才写库。
 * settleMs 取 1200ms：扩展每 ~50ms 推一次分片，只要流还在跑就不可能稳定
 * 1.2s，所以「稳定」≈「流已结束」；比原来的 2500ms 更快落库，
 * 缩短用户「看到回复后立刻刷新页面」导致这轮丢失的窗口。
 *
 * 兜底：跑满 maxWaitMs 仍然一个字都没有时，**不再直接 return** ——
 * 之前那样会让历史里只剩用户提问（用户看到的就是「AI 回复存不上」）。
 * 现在补一条说明行，"提问 + 回复"成对出现，刷新后不会只剩半截会话。
 * 全程 fire-and-forget，失败只告警。
 */
async function persistDsFreeAssistant(params: {
  userId?: string | number
  sessionId: string
  getText: () => string
  settleMs?: number
  maxWaitMs?: number
  /** 用户是否点了「停止生成」——决定一个字都没收到时写入哪种说明 */
  aborted?: boolean
  /**
   * 本轮的轮次 id —— **与先写提问那次（`persistDsFreeUserTurn`）逐字相同**。
   * 两次写的是同一轮的两行，回退按 `turnId` 把这一轮一起删掉（见那边的注释）。
   */
  turnId?: string
}): Promise<void> {
  const settleMs = params.settleMs ?? 1200
  const maxWaitMs = params.maxWaitMs ?? 60000
  const pollMs = 300
  const startedAt = Date.now()

  let last = ''
  let lastChangeAt = Date.now()
  while (Date.now() - startedAt < maxWaitMs) {
    await new Promise((r) => setTimeout(r, pollMs))
    const now = params.getText() || ''
    if (now !== last) {
      last = now
      lastChangeAt = Date.now()
      continue
    }
    // 文本已稳定且非空 → 认为回复结束
    if (now && Date.now() - lastChangeAt >= settleMs) break
  }

  const text = (params.getText() || '').trim()
  // 一个字都没拿到时也要留下助手这一行，否则历史里只剩提问（= 用户说的「回复没保存」）
  const payload = text || (params.aborted ? '（已停止生成）' : DS_FREE_NO_REPLY_NOTE)
  if (!text) {
    console.warn('[ds-free] 本轮没有拿到回复文本，改为写入说明行（避免历史只剩提问）')
  }

  try {
    await saveConversationMessages(
      params.sessionId,
      { userMessage: '', assistantMessage: payload, attachments: [], turnId: params.turnId || '' },
      params.userId
    )
  } catch (e) {
    console.warn('[ds-free] AI 回复落库失败（不影响本次对话）:', e)
  }
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
  model?: string,
  userId?: string | number,
  deepThink?: boolean,
  onReasoningChunk?: (reasoning: string) => void
): Promise<void> {
  // ---- deepseek-free：走浏览器扩展（DeepSeek 官网 Web 版），完全不经过后端 ----
  if (model === 'deepseek-free') {
    const parts: string[] = [
      '你是 OpenStudy 学习平台的题目解析助手。请对下面这道题给出详细、准确的中文解析。',
      '',
      '## 题目',
      question
    ]
    if (questionType) parts.push('', `题型：${questionType}`)
    if (options) parts.push('', '## 选项', options)
    if (correctAnswer) parts.push('', '## 正确答案', correctAnswer)
    parts.push(
      '',
      '## 输出要求',
      '1. 先给出正确答案并说明判断依据；',
      '2. 逐项分析每个选项为什么对 / 为什么错；',
      '3. 指出本题涉及的知识点与常见易错点；',
      '4. 用 Markdown 排版，不要复述题目原文。'
    )

    try {
      const { chatWithDSAccumulated, setDeepThink } = await import('@/utils/ds-proxy')
      // 深度思考是 DS 页面上的按钮，先同步再发
      if (deepThink !== undefined && deepThink !== null) {
        await setDeepThink(deepThink)
      }
      const full = await chatWithDSAccumulated({
        userMessage: parts.join('\n'),
        onChunk,
        // 深度思考过程透传给「思考中」区域
        onThinking: onReasoningChunk
      })
      onComplete?.(full)
    } catch (error: any) {
      onError?.(error)
    }
    return
  }

  // 统一走后端 chat_engine（scene=analysis）：5 段式输出结构由后端
  // `prompts.py` 的 ANALYSIS_OUTPUT_SPEC 提供，这里只负责搬运参数。
  // deepThink → thinking：思考过程不下发，前端用「思考中」动画占位。
  await postAiStream(
    {
      scene: 'analysis',
      prompt: question,
      variables: {
        question,
        question_type: questionType,
        options,
        correct_answer: correctAnswer
      },
      model,
      userId,
      thinking: deepThink
    },
    onChunk,
    onComplete,
    onError
  )
}
