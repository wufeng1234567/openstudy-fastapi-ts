import request from '@/utils/request'
import type { ApiResult } from '@/types'

// 新增笔记-题目关联
export function addNoteQuestion(data: {
  noteId: number | string
  questionId: number | string
  questionBankId?: number | string
  userId?: number | string
}): Promise<ApiResult> {
  return request({
    url: '/noteQuestion/noteQuestion',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult>
}

// 删除笔记-题目关联
export function deleteNoteQuestion(noteId: number | string, questionId: number | string): Promise<ApiResult> {
  return request({
    url: `/noteQuestion/noteQuestion/note/${noteId}/question/${questionId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 按笔记查关联题目
export function getNoteQuestionsByNoteId(noteId: number | string): Promise<ApiResult<any[]>> {
  return request({
    url: `/noteQuestion/noteQuestion/byNote/${noteId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<any[]>>
}

// 按题目查关联笔记
export function getNotesByQuestionId(questionId: number | string): Promise<ApiResult<{ noteId: number, noteTitle: string }[]>> {
  return request({
    url: `/noteQuestion/noteQuestion/byQuestion/${questionId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<{ noteId: number, noteTitle: string }[]>>
}

// 批量关联
export function batchLinkNoteQuestions(data: {
  noteId: number | string
  questionIds: (number | string)[]
  questionBankId?: number | string
}): Promise<ApiResult> {
  return request({
    url: '/noteQuestion/noteQuestion/batchLink',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult>
}

// 检查是否已关联
export function checkNoteQuestion(noteId: number | string, questionId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: `/noteQuestion/noteQuestion/check/${noteId}/${questionId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}
