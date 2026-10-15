import request from '@/utils/request'
import { getToken } from '@/utils/auth'

// OCR 识别（非流式，保留兼容）
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

// OCR 识别（流式输出）
export function ocrRecognizeStream(
  file: File,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void
): void {
  const formData = new FormData()
  formData.append('file', file)

  const baseUrl = import.meta.env.VITE_APP_BASE_API
  const url = `${baseUrl}/ocr/recognize/stream`

  fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + getToken()
    },
    body: formData
  }).then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''

    function read(): void {
      reader.read().then(({ done, value }) => {
        if (done) {
          onComplete?.(fullContent)
          return
        }

        let chunk = decoder.decode(value, { stream: true })

        // 清洗数据：处理 SSE 格式
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (!line.trim()) continue

          // 移除 data: 前缀
          let data = line.replace(/^data:\s*/, '')

          // 检查结束标记
          if (data === '[DONE]') {
            onComplete?.(fullContent)
            return
          }

          if (data && data !== '[DONE]') {
            fullContent += data
            onChunk?.(fullContent)
          }
        }

        read()
      }).catch(error => {
        onError?.(error)
      })
    }

    read()
  }).catch(error => {
    onError?.(error)
  })
}
