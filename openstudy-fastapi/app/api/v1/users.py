"""
用户管理 API
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.core.security import get_current_user, hash_password, verify_password
from app.core.response import success, paginate, error
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate, ResetPasswordRequest, UserStatusUpdate
from app.models.user import SysUser, SysDept
from app.models.role import SysRole

router = APIRouter(prefix="/system/user")


def _format_role_option(role: SysRole) -> dict:
    """角色下拉/授权表格通用字段。"""
    return {
        "roleId": role.role_id,
        "roleName": role.role_name,
        "roleKey": role.role_key,
        "roleSort": role.role_sort,
        "status": role.status,
        "createTime": role.create_time.isoformat() if role.create_time else None,
        "remark": role.remark,
    }


async def _list_role_options(db: AsyncSession) -> list[dict]:
    """查询全部未删除角色。"""
    query = (
        select(SysRole)
        .where(SysRole.del_flag == "0")
        .order_by(SysRole.role_sort.asc())
    )
    result = await db.execute(query)
    return [_format_role_option(r) for r in result.scalars().all()]


def _format_user_row(user: SysUser) -> dict:
    dept = None
    if user.dept:
        dept = {
            "deptId": user.dept.dept_id,
            "deptName": user.dept.dept_name,
        }
    return {
        "userId": user.user_id,
        "userName": user.user_name,
        "nickName": user.nick_name,
        "email": user.email,
        "phonenumber": user.phonenumber,
        "sex": user.sex,
        "avatar": user.avatar,
        "status": user.status,
        "deptId": user.dept_id,
        "dept": dept,
        "createTime": user.create_time.isoformat() if user.create_time else None,
    }


def _user_form_payload(user: Optional[SysUser], role_options: list[dict]) -> dict:
    """用户表单所需的用户信息 + 角色下拉。"""
    payload = {
        "roles": role_options,
        "posts": [],
        "postIds": [],
    }
    if user is not None:
        payload.update({
            "userId": user.user_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "email": user.email,
            "phonenumber": user.phonenumber,
            "sex": user.sex,
            "avatar": user.avatar,
            "status": user.status,
            "deptId": user.dept_id,
            "roleIds": [r.role_id for r in user.roles],
            "createTime": user.create_time.isoformat() if user.create_time else None,
        })
    else:
        payload["roleIds"] = []
    return payload


def _with_top_level_options(data: dict, role_options: list[dict]) -> dict:
    """兼容旧若依前端：roles/posts/roleIds 同时放在顶层。"""
    resp = success(data)
    resp["roles"] = role_options
    resp["posts"] = []
    resp["roleIds"] = data.get("roleIds", [])
    resp["postIds"] = []
    return resp


def _filtered_role_options(role_options: list[dict], target_user: Optional[SysUser]) -> list[dict]:
    """非超级管理员目标用户不允许分配 admin 角色。"""
    is_admin_user = bool(target_user and any(r.role_key == "admin" for r in target_user.roles))
    if is_admin_user:
        return role_options
    return [r for r in role_options if r.get("roleKey") != "admin"]


@router.get("/list")
async def list_users(
    user_name: Optional[str] = Query(None, alias="userName"),
    phonenumber: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    dept_id: Optional[int] = Query(None, alias="deptId"),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询用户列表"""
    user_repo = UserRepository(db)
    total, users = await user_repo.list_users(
        user_name=user_name,
        phonenumber=phonenumber,
        status=status,
        dept_id=dept_id,
        page_num=pageNum,
        page_size=pageSize,
    )

    return paginate(total, [_format_user_row(user) for user in users])


@router.get("/frontList")
async def front_list_users(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台用户列表"""
    user_repo = UserRepository(db)
    total, users = await user_repo.list_users(page_num=pageNum, page_size=pageSize)

    rows = []
    for user in users:
        rows.append({
            "userId": user.user_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "avatar": user.avatar,
        })

    return paginate(total, rows)


@router.get("/profile")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户信息"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user.get("user_id"))

    if not user:
        return error("用户不存在")

    return success({
        "user": {
            "userId": user.user_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "email": user.email,
            "phonenumber": user.phonenumber,
            "sex": user.sex,
            "avatar": user.avatar,
            "status": user.status,
        },
        "roles": current_user.get("roles", []),
        "permissions": current_user.get("perms", []),
    })


@router.get("/deptTree")
async def dept_tree(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取部门树（表单归属部门下拉用）"""
    query = (
        select(SysDept)
        .where(SysDept.del_flag == "0")
        .order_by(SysDept.parent_id.asc(), SysDept.order_num.asc())
    )
    result = await db.execute(query)
    depts = list(result.scalars().all())

    def build(parent_id: int = 0) -> list[dict]:
        nodes = []
        for dept in depts:
            if dept.parent_id != parent_id:
                continue
            node = {"id": dept.dept_id, "label": dept.dept_name}
            children = build(dept.dept_id)
            if children:
                node["children"] = children
            nodes.append(node)
        return nodes

    return success(build())


@router.get("")
@router.get("/")
async def get_user_form_options(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增用户时获取角色下拉等表单选项（兼容若依 GET /system/user/ 约定）"""
    role_options = await _list_role_options(db)
    data = _user_form_payload(None, role_options)
    return _with_top_level_options(data, role_options)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询用户详情"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        return error("用户不存在")

    role_options = _filtered_role_options(await _list_role_options(db), user)
    data = _user_form_payload(user, role_options)
    return _with_top_level_options(data, role_options)


@router.post("")
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建用户"""
    user_repo = UserRepository(db)

    # 检查用户名唯一
    if not await user_repo.check_user_name_unique(data.user_name):
        return error("用户名已存在")

    user = SysUser(
        user_name=data.user_name,
        nick_name=data.nick_name,
        password=hash_password(data.password),
        email=data.email,
        phonenumber=data.phonenumber,
        sex=data.sex,
        dept_id=data.dept_id,
        status=data.status,
        remark=data.remark,
        create_by=current_user.get("user_name"),
        create_time=datetime.now(),
    )
    await user_repo.create(user)

    # 设置角色
    if data.role_ids:
        await user_repo.update_user_roles(user.user_id, data.role_ids)

    return success({"user_id": user.user_id})


@router.put("")
async def update_user(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新用户"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(data.user_id)

    if not user:
        return error("用户不存在")

    if data.nick_name is not None:
        user.nick_name = data.nick_name
    if data.email is not None:
        user.email = data.email
    if data.phonenumber is not None:
        user.phonenumber = data.phonenumber
    if data.sex is not None:
        user.sex = data.sex
    if data.dept_id is not None:
        user.dept_id = data.dept_id
    if data.status is not None:
        user.status = data.status
    if data.remark is not None:
        user.remark = data.remark

    user.update_by = current_user.get("user_name")
    user.update_time = datetime.now()
    await user_repo.update(user)

    # 更新角色
    if data.role_ids is not None:
        await user_repo.update_user_roles(user.user_id, data.role_ids)

    return success()


@router.delete("/{user_ids}")
async def delete_users(
    user_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除用户（逻辑删除）"""
    ids = [int(id) for id in user_ids.split(",")]
    if current_user.get("user_id") in ids:
        return error("当前用户不能删除", code=400)

    user_repo = UserRepository(db)
    await user_repo.delete_by_ids(ids)
    return success()


@router.put("/resetPwd")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重置密码"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(data.user_id)

    if not user:
        return error("用户不存在")

    user.password = hash_password(data.password)
    user.update_by = current_user.get("user_name")
    user.update_time = datetime.now()
    await user_repo.update(user)

    return success()


@router.put("/profile/updatePwd")
async def update_password(
    oldPassword: str = Query(...),
    newPassword: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改密码"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user.get("user_id"))

    if not user:
        return error("用户不存在")

    if not verify_password(oldPassword, user.password):
        return error("旧密码错误")

    user.password = hash_password(newPassword)
    await user_repo.update(user)

    return success()


@router.put("/profile")
async def update_profile(
    nickName: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    phonenumber: Optional[str] = Query(None),
    sex: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改个人信息"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user.get("user_id"))

    if not user:
        return error("用户不存在")

    if nickName is not None:
        user.nick_name = nickName
    if email is not None:
        user.email = email
    if phonenumber is not None:
        user.phonenumber = phonenumber
    if sex is not None:
        user.sex = sex

    await user_repo.update(user)

    return success()


@router.post("/profile/avatar")
async def update_avatar(
    avatarfile: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改头像"""
    from app.utils.file_util import save_upload_file

    result = await save_upload_file(avatarfile, sub_dir="avatar")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user.get("user_id"))

    if user:
        user.avatar = result["fileUrl"]
        await user_repo.update(user)

    return success({"imgUrl": result["fileUrl"]})


@router.put("/changeStatus")
async def change_status(
    data: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改用户状态（若依前端为 PUT + JSON body）"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(data.user_id)

    if not user:
        return error("用户不存在")

    if user.user_id == current_user.get("user_id"):
        return error("当前用户不能停用自己", code=400)

    user.status = data.status
    user.update_by = current_user.get("user_name")
    user.update_time = datetime.now()
    await user_repo.update(user)

    return success()


@router.put("/authRole")
@router.post("/authRole")
async def auth_role(
    userId: int = Query(...),
    roleIds: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """授权角色（同时兼容 PUT/POST，前端以 query 传 userId/roleIds）"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(userId)
    if not user:
        return error("用户不存在")

    ids = [int(role_id) for role_id in roleIds.split(",") if role_id.strip()]
    await user_repo.update_user_roles(userId, ids)

    return success()


@router.get("/authRole/{user_id}")
async def get_auth_role(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取用户角色授权信息（返回全部角色，已授权角色 flag=true）"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        return error("用户不存在")

    assigned_ids = {r.role_id for r in user.roles}
    role_options = _filtered_role_options(await _list_role_options(db), user)
    roles = []
    for role in role_options:
        item = dict(role)
        item["flag"] = item["roleId"] in assigned_ids
        roles.append(item)

    return {
        "code": 200,
        "msg": "操作成功",
        "data": {
            "user": {
                "userId": user.user_id,
                "userName": user.user_name,
                "nickName": user.nick_name,
            },
            "roles": roles,
        },
        "user": {
            "userId": user.user_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
        },
        "roles": roles,
    }
