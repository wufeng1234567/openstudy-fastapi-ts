import request from '@/utils/request'
import type { ApiResult } from '@/types'

/** 生成题库分享（仅题库主） */
export function createBankShare(data: { bankId: number | string; expireDays?: number | null; message?: string }): Promise<ApiResult<any>> {
  return request({
    url: '/bankShare/bankShare/create',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult<any>>
}

/** 我发出的分享列表 */
export function listMyBankShares(): Promise<ApiResult<any[]>> {
  return request({
    url: '/bankShare/bankShare/my',
    method: 'get'
  }) as unknown as Promise<ApiResult<any[]>>
}

/** 撤销分享（仅题库主） */
export function revokeBankShare(shareId: number | string): Promise<ApiResult> {
  return request({
    url: '/bankShare/bankShare/revoke/' + shareId,
    method: 'post'
  }) as unknown as Promise<ApiResult>
}

/** 按分享令牌校验（落地页预展示） */
export function getShareInfoByToken(token: string): Promise<ApiResult<any>> {
  return request({
    url: '/bankShare/bankShare/info/' + token,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

/** 按分享码校验 */
export function getShareInfoByCode(code: string): Promise<ApiResult<any>> {
  return request({
    url: '/bankShare/bankShare/infoByCode/' + code,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

/** 领取分享（写入收藏） */
export function receiveBankShare(data: { token?: string; code?: string }): Promise<ApiResult<any>> {
  return request({
    url: '/bankShare/bankShare/receive',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult<any>>
}

/** 查询我与该题库的关系（是否来自分享 / 能否编辑 / 能否复制） */
export function checkBankSource(bankId: number | string): Promise<ApiResult<any>> {
  return request({
    url: '/bankShare/bankShare/checkSource/' + bankId,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}
