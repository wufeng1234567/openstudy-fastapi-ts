import request from '@/utils/request'

/** 资料夹 ↔ 笔记逻辑关联（不复制笔记正文） */

export function listKbNotes(kbId: number | string) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/notes`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

export function linkKbNote(kbId: number | string, noteId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/notes`,
    method: 'post',
    data: { noteId }
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

export function getKbNoteKnowledge(kbId: number | string, noteId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/notes/${noteId}/knowledge`,
    method: 'get',
    timeout: 120000
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

export function unlinkKbNote(kbId: number | string, noteId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/notes/${noteId}`,
    method: 'delete'
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}
