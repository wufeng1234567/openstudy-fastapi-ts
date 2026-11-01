import request from '@/utils/request'
import type { ApiResult } from '@/types'

/** 生成知识库分享（仅知识库主） */
export function createKbShare(data: {
  kbId?: number | string
  docId?: number | string
  expireDays?: number | null
  message?: string
}): Promise<ApiResult<any>> {
  return request({
    url: '/kbShare/kbShare/create',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult<any>>
}

/** 我发出的知识库分享 */
export function listMyKbShares(): Promise<ApiResult<any[]>> {
  return request({
    url: '/kbShare/kbShare/my',
    method: 'get'
  }) as unknown as Promise<ApiResult<any[]>>
}

/** 撤销知识库分享 */
export function revokeKbShare(shareId: number | string): Promise<ApiResult> {
  return request({
    url: '/kbShare/kbShare/revoke/' + shareId,
    method: 'post'
  }) as unknown as Promise<ApiResult>
}

/** 按分享链接 token 校验知识库分享 */
export function getKbShareInfoByToken(token: string): Promise<ApiResult<any>> {
  return request({
    url: '/kbShare/kbShare/info/' + token,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

/** 按分享码校验知识库分享 */
export function getKbShareInfoByCode(code: string): Promise<ApiResult<any>> {
  return request({
    url: '/kbShare/kbShare/infoByCode/' + code,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

/** 领取知识库分享：在领取者名下生成一份副本 */
export function receiveKbShare(data: { token?: string; code?: string }): Promise<ApiResult<any>> {
  return request({
    url: '/kbShare/kbShare/receive',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult<any>>
}
