/**
 * 系统管理类型定义
 */

/** 用户 */
export interface SysUser {
  userId: number
  userName: string
  nickName: string
  email: string
  phonenumber: string
  sex: string
  avatar: string
  status: string
  deptId?: number
  dept?: DeptInfo
  roles?: SysRole[]
  createTime?: string
}

/** 角色 */
export interface SysRole {
  roleId: number
  roleName: string
  roleKey: string
  roleSort: number
  status: string
  menuIds?: number[]
  createTime?: string
}

/** 菜单 */
export interface SysMenu {
  menuId: number
  menuName: string
  parentId: number
  orderNum: number
  path: string
  component?: string
  menuType: string
  visible: string
  status: string
  perms?: string
  icon: string
  children?: SysMenu[]
}

/** 部门 */
export interface DeptInfo {
  deptId: number
  deptName: string
  parentId: number
  leader?: string
  phone?: string
  email?: string
  status: string
  children?: DeptInfo[]
}

/** 字典 */
export interface SysDict {
  dictId: number
  dictName: string
  dictType: string
  status: string
}

/** 字典数据 */
export interface SysDictData {
  dictCode: number
  dictLabel: string
  dictValue: string
  dictType: string
  cssClass?: string
  listClass?: string
  isDefault: string
  status: string
}

/** 通知公告 */
export interface SysNotice {
  noticeId: number
  noticeTitle: string
  noticeType: string
  noticeContent?: string
  status: string
  createBy?: string
  createTime?: string
}
