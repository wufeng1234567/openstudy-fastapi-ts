import request from '@/utils/request'
import { getToken } from '@/utils/auth'

/**
 * 拍照识词 / OCR API
 * ============================================================================
 * ⚠️ 2026-10-26 重大修正：这条链路之前**完全用不了**。
 *
 * 原实现（本文件旧版）主路径请求 `POST /ocr/recognize/stream`，
 * 但后端 `app/api/v1/ocr.py` **只注册了 `/ocr/recognize`**，
 * 根本没有 `/stream`。请求于是落到 `catch_all` 兜底，
 * 返回一个假的 `{code:200, msg:"操作成功", data:null}` ——
 * 前端拿不到任何文字，页面就显示"识别失败"。
 *
 * 更根本的问题是：**本地 Tesseract OCR 这条路本身就不该用**。
 *   · 服务器上根本没装 tesseract 引擎（只装了 pytesseract 这个 Python 包），
 *     所以 `/ocr/recognize` 真调用也会抛 `tesseract is not installed`；
 *   · Tesseract 对"拍照识词"这种场景效果很差（倾斜、光照、艺术字基本读不出）。
 *
 * 项目里其实早就有更好的方案：**多模态大模型直接读图**
 * （`app/services/ai/prompts.py::OCR_SYSTEM_PROMPT`，scene=`ocr`）。
 * 实测同一张截图，Tesseract 路线不可用，而这条路线能正确吐出词条 JSON：
 *
 *     [{"english":"OpenStudy","chinese":"开放学习（平台名称）", ...}, ...]
 *
 * 所以本文件改为统一走 `POST /ai/assistant/stream`（scene=ocr），
 * 把图片以 data URI 放进 `images` 字段。`/ocr/*` 两个旧函数保留但标注废弃，
 * 避免其它调用方 import 报错。
 */

/** 把 File 读成 data URI（多模态接口要求 base64 内联） */
function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })
}

/** OCR 使用的提示词：要求模型只吐 JSON 数组，与后端 OCR_SYSTEM_PROMPT 呼应 */
const OCR_USER_PROMPT = `请识别这张图片里的英文单词 / 词组，输出 JSON 数组。
每个元素包含 english（英文）、chinese（中文释义）、phonetic（音标，可空）。
只输出 JSON 数组，不要任何解释文字。`

/**
 * 拍照识词（流式）
 *
 * @param file     要识别的图片
 * @param onChunk  每次收到增量全文时回调（用于流式展示）
 * @param onComplete 结束时回调完整文本
 * @param onError  出错时回调
 */
export function ocrRecognizeStream(
  file: File,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void
): void {
  const baseUrl = import.meta.env.VITE_APP_BASE_API

  fileToDataUri(file)
    .then((dataUri) =>
      fetch(`${baseUrl}/ai/assistant/stream`, {
        method: 'POST',
        headers: {
          Authorization: 'Bearer ' + getToken(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: OCR_USER_PROMPT,
          scene: 'ocr',
          images: [dataUri],
          // 空 sessionId = 一次性生成，不写聊天历史
          sessionId: ''
        })
      })
    )
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      if (!response.body) {
        throw new Error('响应没有可读内容')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let fullContent = ''

      const read = (): void => {
        reader
          .read()
          .then(({ done, value }) => {
            if (done) {
              onComplete?.(fullContent)
              return
            }

            const chunk = decoder.decode(value, { stream: true })
            const lines = chunk.split('\n')

            for (const line of lines) {
              if (!line.trim()) continue

              const data = line.replace(/^data:\s*/, '')

              if (data === '[DONE]') {
                onComplete?.(fullContent)
                return
              }

              if (data) {
                fullContent += data
                onChunk?.(fullContent)
              }
            }

            read()
          })
          .catch((error) => {
            onError?.(error)
          })
      }

      read()
    })
    .catch((error) => {
      onError?.(error)
    })
}

/**
 * OCR 识别（非流式）
 *
 * @deprecated 2026-10-26：后端 `/ocr/recognize` 依赖本机 Tesseract，
 *   而服务器上没装引擎、识别质量也差。请改用 {@link ocrRecognizeStream}。
 *   这里保留只是为了不让历史调用方 import 直接崩。
 */
export function ocrRecognize(data: FormData) {
  return request({
    url: '/ocr/recognize',
    method: 'post',
    data: data,
    timeout: 600000,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}
