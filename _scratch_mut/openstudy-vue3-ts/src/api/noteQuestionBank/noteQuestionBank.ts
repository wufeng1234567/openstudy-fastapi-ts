import request from '@/utils/request'

export function listNoteQuestionBank(query: any) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/list',
    method: 'get',
    params: query
  })
}

export function getNoteQuestionBank(id: number | string) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/' + id,
    method: 'get'
  })
}

export function addNoteQuestionBank(data: any) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank',
    method: 'post',
    data: data
  })
}

export function updateNoteQuestionBank(data: any) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank',
    method: 'put',
    data: data
  })
}

export function delNoteQuestionBank(id: number | string) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/' + id,
    method: 'delete'
  })
}

export function getNoteQuestionBanksByNoteId(noteId: number | string) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/byNote/' + noteId,
    method: 'get'
  })
}

export function getNoteQuestionBanksByBankId(bankId: number | string) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/byBank/' + bankId,
    method: 'get'
  })
}

export function removeNoteQuestionBank(noteId: number | string, bankId: number | string) {
  return request({
    url: '/noteQuestionBank/noteQuestionBank/note/' + noteId + '/bank/' + bankId,
    method: 'delete'
  })
}
