import request from '@/utils/request'
import axios from 'axios'
import { getToken } from '@/utils/auth'
import type { QuestionBank, PageResult, ApiResult } from '@/types'

// 查询题库主列表
export function listQuestionBank(query: any): Promise<PageResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<QuestionBank>>
}

// 查询题库主列表不分页
export function listQuestionBankAll(query?: any): Promise<ApiResult<QuestionBank[]>> {
  return request({
    url: '/questionBank/questionBank/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<QuestionBank[]>>
}

// 获取当前用户的题库列表
export function listMyQuestionBank(): Promise<ApiResult<QuestionBank[]>> {
  return request({
    url: '/questionBank/questionBank/my',
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank[]>>
}

// 查询题库主详细
export function getQuestionBank(id: number | string): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/' + id,
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

// 新增题库主（原接口，返回影响行数）
export function addQuestionBank(data: Partial<QuestionBank>): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 创建题库并返回完整对象（供前台使用）
export function createQuestionBankWithReturn(data: Partial<QuestionBank>): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/createWithReturn',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

// 修改题库主
export function updateQuestionBank(data: Partial<QuestionBank>): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除题库主
export function delQuestionBank(id: number | string): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank/' + id,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 复制题库为我的新题库（深拷贝题目与子题）
export function copyQuestionBank(id: number | string, data?: { bankName?: string }): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/copy/' + id,
    method: 'post',
    data: data || {}
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

/**
 * 导出题库为 Word / PDF
 *
 * 为什么不用 `request`（全局 axios 实例）：
 *   它的响应拦截器对 `responseType: 'blob'` 只 `return res.data`，
 *   **响应头被丢掉了** —— 而文件名恰好在 `Content-Disposition` 里。
 *   这里用独立实例拿到完整 response，顺便避开全局拦截器对二进制的误判。
 *
 * 失败时后端返回的是 **JSON**（`{code:403,msg:"..."}`），但 responseType 已是 blob，
 * 所以要按 `Content-Type` 分流：是 JSON 就转成业务错误，不能把一坨 JSON
 * 存成 .docx 让用户打开时发现文件损坏。
 *
 * ── 关于 PDF 的两种格式（2026-10-26 v3）──────────────────────────────
 *   `pdf`        reportlab 直出。快（~1s），但**没有 TeX 引擎**，复杂公式
 *                只能 Unicode 近似：`\dfrac{a}{b}` 印成 `a⁄b`，积分限挤在
 *                积分号右边、上下标压平。
 *   `pdf_docx`   先出 DOCX（OMML 真公式 + 原生表格），再用 LibreOffice 转 PDF。
 *                慢一些（~3-20s），但**与 Word 逐像素一致**。
 *
 * 用户诉求是"复杂公式正确渲染、打印不走样"，所以默认走 `pdf_docx`；
 * 后端在 kit 不可用时会自动回落 reportlab，前端无需关心。
 */
export async function exportQuestionBank(
  id: number | string,
  format: 'docx' | 'pdf' | 'pdf_docx',
  withAnswers: boolean = true
): Promise<{ blob?: Blob; filename?: string; error?: string }> {
  const resp = await axios.get(`${import.meta.env.VITE_APP_BASE_API}/questionBank/questionBank/${id}/export`, {
    params: { format, with_answers: withAnswers },
    responseType: 'blob',
    // 含大量图片时可能超过默认 30s，单独放宽；
    // `pdf_docx` 还要跑一遍 LibreOffice（实测 670 题约 20s），所以给到 5 分钟
    timeout: 300000,
    headers: getToken() ? { Authorization: 'Bearer ' + getToken() } : {}
  })

  const blob: Blob = resp.data
  if (!blob || typeof blob.slice !== 'function') {
    return { error: '导出失败：服务端未返回文件' }
  }

  // 后端把错误塞进了 blob（Content-Type: application/json）
  if (blob.type && blob.type.includes('application/json')) {
    try {
      const json = JSON.parse(await blob.text())
      return { error: json?.msg || '导出失败' }
    } catch {
      return { error: '导出失败' }
    }
  }

  const disposition = resp.headers?.['content-disposition'] as string | undefined
  return { blob, filename: parseFilename(disposition, `题库-${id}.${format}`) }
}

/**
 * 从 `Content-Disposition` 解析文件名
 *
 * 后端同时给了 `filename="ascii"` 和 `filename*=UTF-8''<pct>`，
 * 优先用后者 —— 那才是中文原名。缺失时退回前端自己拼的名字。
 */
export function parseFilename(disposition: string | undefined | null, fallback: string): string {
  if (!disposition) return fallback
  const star = /filename\*=(?:UTF-8|utf-8)?''([^;]+)/.exec(disposition)
  if (star && star[1]) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      /* 解码失败就用兜底名 */
    }
  }
  const plain = /filename="?([^";]+)"?/.exec(disposition)
  if (plain && plain[1]) return plain[1]
  return fallback
}
