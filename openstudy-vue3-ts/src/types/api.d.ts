/**
 * API 响应类型定义
 */

/** 统一响应格式 */
export interface ApiResponse<T = any> {
  code: number
  msg: string
  data: T
}

/**
 * 通用 API 结果（ApiResponse 的简写别名）
 * @example function addX(data: Partial<X>): Promise<ApiResult>
 */
export interface ApiResult<T = any> {
  code: number
  msg: string
  data: T
}

/** 分页响应格式 */
export interface PageResponse<T = any> {
  code: number
  msg: string
  total: number
  rows: T[]
}

/**
 * 分页结果（PageResponse 的简写别名，rows + total）
 * @example function listX(query: any): Promise<PageResult<X>>
 */
export interface PageResult<T = any> {
  rows: T[]
  total: number
  code: number
  msg: string
}

/** 分页查询参数 */
export interface PageQuery {
  pageNum: number
  pageSize: number
  [key: string]: any
}

/** CRUD 通用响应 */
export interface CrudResponse {
  code: number
  msg: string
  data?: any
}

/** 增删改操作响应（返回影响行数） */
export interface ModifyResponse {
  code: number
  msg: string
  data?: number
}

/** 登录请求 */
export interface LoginRequest {
  username: string
  password: string
  code?: string
  uuid?: string
}

/** 登录响应 */
export interface LoginResponse {
  token: string
}

/** 注册请求 */
export interface RegisterRequest {
  username: string
  password: string
  nick_name?: string
}

/** 用户信息 */
export interface UserInfo {
  user: {
    userId: number
    userName: string
    nickName: string
    email: string
    phonenumber: string
    sex: string
    avatar: string
    status: string
    [key: string]: any
  }
  roles: string[]
  permissions: string[]
}

/** 验证码响应 */
export interface CaptchaResponse {
  code: number
  uuid: string
  img: string
  captchaEnabled?: boolean
}

/** 通用 ID 参数 */
export interface IdParam {
  id: number | string
}

/** 树形结构 */
export interface TreeNode<T = any> {
  id: number
  label?: string
  children?: TreeNode<T>[]
  [key: string]: any
}

/** 导入响应 */
export interface ImportResponse {
  code: number
  msg: string
  successCount?: number
  failureCount?: number
  errorMsg?: string
}
