"""
系统管理 API（字典、菜单、角色、部门、参数配置）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.response import success, paginate, error
from app.models.config import SysConfig
from app.models.question import QuestionMain
from app.utils.excel_util import export_to_excel

router = APIRouter()


# ========== 参数配置 ==========

class ConfigUpdateRequest(BaseModel):
    configId: int
    configName: Optional[str] = None
    configValue: Optional[str] = None
    remark: Optional[str] = None


class ConfigCreateRequest(BaseModel):
    configName: str
    configKey: str
    configValue: str
    configType: str = "Y"
    remark: Optional[str] = None

def format_config(cfg):
    return {
        "configId": cfg.config_id,
        "configName": cfg.config_name,
        "configKey": cfg.config_key,
        "configValue": cfg.config_value,
        "configType": cfg.config_type,
        "remark": cfg.remark,
        "createTime": cfg.create_time.isoformat() if cfg.create_time else None,
        "updateTime": cfg.update_time.isoformat() if cfg.update_time else None,
    }


@router.get("/system/config/list")
async def list_configs(
    configName: Optional[str] = Query(None),
    configKey: Optional[str] = Query(None),
    configType: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询参数配置列表"""
    query = select(SysConfig)

    if configName:
        query = query.where(SysConfig.config_name.ilike(f"%{configName}%"))
    if configKey:
        query = query.where(SysConfig.config_key.ilike(f"%{configKey}%"))
    if configType:
        query = query.where(SysConfig.config_type == configType)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(SysConfig.config_id.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    configs = list(result.scalars().all())

    return paginate(total, [format_config(c) for c in configs])


@router.get("/system/config/{config_id}")
async def get_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询参数配置详情"""
    query = select(SysConfig).where(SysConfig.config_id == config_id)
    result = await db.execute(query)
    cfg = result.scalar_one_or_none()

    if not cfg:
        return error("参数配置不存在")

    return success(format_config(cfg))


@router.get("/system/config/key/{config_key}")
async def get_config_by_key(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """根据键名查询参数配置

    ⚠️ 必须管理员：`sys_config` 里有 JWT 有效期、演示模式开关、限流阈值等
    运行参数，暴露给匿名请求等于把系统配置单公开。
    （2026-10-22 审计发现原本连登录都不校验。）
    """
    query = select(SysConfig).where(SysConfig.config_key == config_key)
    result = await db.execute(query)
    cfg = result.scalar_one_or_none()

    if not cfg:
        return error("参数配置不存在")

    return success(format_config(cfg))


@router.post("/system/config")
async def create_config(
    data: ConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """新增参数配置（幂等：若 configKey 已存在则直接返回已有项）"""
    existing = (await db.execute(
        select(SysConfig).where(SysConfig.config_key == data.configKey)
    )).scalar_one_or_none()
    if existing:
        return success(format_config(existing))

    cfg = SysConfig(
        config_name=data.configName,
        config_key=data.configKey,
        config_value=data.configValue,
        config_type=data.configType or "Y",
        create_by=current_user.get("user_name", "admin"),
        create_time=datetime.now(),
        remark=data.remark,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return success(format_config(cfg))


@router.put("/system/config")
async def update_config(
    data: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """修改参数配置"""
    query = select(SysConfig).where(SysConfig.config_id == data.configId)
    result = await db.execute(query)
    cfg = result.scalar_one_or_none()

    if not cfg:
        return error("参数配置不存在")

    if data.configName is not None:
        cfg.config_name = data.configName
    if data.configValue is not None:
        cfg.config_value = data.configValue
    if data.remark is not None:
        cfg.remark = data.remark

    cfg.update_by = current_user.get("user_name")
    cfg.update_time = datetime.now()

    return success()


# ========== 用户管理 ==========

@router.post("/system/user/export")
async def export_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """导出用户列表为 Excel"""
    from app.models.user import SysUser
    query = select(SysUser).where(SysUser.del_flag == "0")
    result = await db.execute(query)
    users = list(result.scalars().all())

    rows = [{
        "userId": u.user_id,
        "userName": u.user_name,
        "nickName": u.nick_name,
        "email": u.email or "",
        "phonenumber": u.phonenumber or "",
        "status": "正常" if u.status == "0" else "停用",
        "createTime": u.create_time.isoformat() if u.create_time else "",
    } for u in users]

    headers = [
        {"key": "userId", "label": "用户ID"},
        {"key": "userName", "label": "用户名"},
        {"key": "nickName", "label": "昵称"},
        {"key": "email", "label": "邮箱"},
        {"key": "phonenumber", "label": "手机号"},
        {"key": "status", "label": "状态"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "user")


# ========== 字典 ==========

_DICT_TYPES = [
    { "dictId": 1, "dictName": "系统状态", "dictType": "common_status", "status": "0" },
    { "dictId": 2, "dictName": "系统正常/停用", "dictType": "sys_normal_disable", "status": "0" },
    { "dictId": 3, "dictName": "通用状态", "dictType": "sys_common_status", "status": "0" },
    { "dictId": 4, "dictName": "是否", "dictType": "sys_yes_no", "status": "0" },
    { "dictId": 5, "dictName": "显示/隐藏", "dictType": "sys_show_hide", "status": "0" },
    { "dictId": 6, "dictName": "题目类型", "dictType": "question_type", "status": "0" },
    { "dictId": 7, "dictName": "难度等级", "dictType": "difficulty_level", "status": "0" },
]

_DICT_DATA = {
    "common_status": [
        { "dictValue": "0", "dictLabel": "正常", "listClass": "success", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "停用", "listClass": "danger", "cssClass": "" },
    ],
    "sys_normal_disable": [
        { "dictValue": "0", "dictLabel": "正常", "listClass": "success", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "停用", "listClass": "danger", "cssClass": "" },
    ],
    "sys_common_status": [
        { "dictValue": "0", "dictLabel": "正常", "listClass": "success", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "停用", "listClass": "danger", "cssClass": "" },
    ],
    "sys_yes_no": [
        { "dictValue": "Y", "dictLabel": "是", "listClass": "primary", "cssClass": "" },
        { "dictValue": "N", "dictLabel": "否", "listClass": "danger", "cssClass": "" },
    ],
    "sys_show_hide": [
        { "dictValue": "0", "dictLabel": "显示", "listClass": "primary", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "隐藏", "listClass": "danger", "cssClass": "" },
    ],
    "question_type": [
        { "dictValue": "1", "dictLabel": "单选题", "listClass": "primary", "cssClass": "1" },
        { "dictValue": "2", "dictLabel": "多选题", "listClass": "success", "cssClass": "2" },
        { "dictValue": "3", "dictLabel": "判断题", "listClass": "warning", "cssClass": "3" },
        { "dictValue": "4", "dictLabel": "填空题", "listClass": "info", "cssClass": "4" },
        { "dictValue": "5", "dictLabel": "简答题", "listClass": "danger", "cssClass": "5" },
        { "dictValue": "6", "dictLabel": "组合题", "listClass": "", "cssClass": "6" },
    ],
    "difficulty_level": [
        { "dictValue": "1", "dictLabel": "简单", "listClass": "success", "cssClass": "" },
        { "dictValue": "2", "dictLabel": "中等", "listClass": "primary", "cssClass": "" },
        { "dictValue": "3", "dictLabel": "困难", "listClass": "warning", "cssClass": "" },
        { "dictValue": "4", "dictLabel": "极难", "listClass": "danger", "cssClass": "" },
    ],
}

@router.get("/system/dict/type/list")
async def list_dict_types(
    dictType: Optional[str] = Query(None),
    dictName: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询字典类型列表"""
    filtered = _DICT_TYPES
    if dictType:
        filtered = [d for d in filtered if dictType in d["dictType"]]
    if dictName:
        filtered = [d for d in filtered if dictName in d["dictName"]]
    if status:
        filtered = [d for d in filtered if d["status"] == status]
    return paginate(len(filtered), filtered)


@router.get("/system/dict/type/optionselect")
async def dict_type_options(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """字典类型选项"""
    return success(_DICT_TYPES)


@router.get("/system/dict/data/list")
async def list_dict_data(
    dictType: Optional[str] = Query(None),
    dictLabel: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询字典数据列表"""
    all_items = []
    dict_type_key = dictType
    if dict_type_key and dict_type_key in _DICT_DATA:
        items = [
            { **item, "dictCode": i + 1, "dictType": dict_type_key }
            for i, item in enumerate(_DICT_DATA[dict_type_key])
        ]
        if dictLabel:
            items = [d for d in items if dictLabel in d["dictLabel"]]
        all_items = items
    return paginate(len(all_items), all_items)


@router.get("/system/dict/data/type/{dict_type}")
async def get_dict_data_by_type(
    dict_type: str,
    db: AsyncSession = Depends(get_db),
):
    """根据字典类型查询字典数据"""
    data = _DICT_DATA.get(dict_type, [])
    return success(data)


class DictDataCreate(BaseModel):
    dictType: str
    dictValue: str
    dictLabel: str
    listClass: Optional[str] = ""
    cssClass: Optional[str] = ""


class DictDataUpdate(BaseModel):
    dictCode: int
    dictType: str
    dictValue: str
    dictLabel: str
    listClass: Optional[str] = ""
    cssClass: Optional[str] = ""


@router.post("/system/dict/data")
async def create_dict_data(
    body: DictDataCreate,
    current_user: dict = Depends(require_admin),
):
    """新增字典数据"""
    if body.dictType not in _DICT_DATA:
        _DICT_DATA[body.dictType] = []
    _DICT_DATA[body.dictType].append({
        "dictValue": body.dictValue,
        "dictLabel": body.dictLabel,
        "listClass": body.listClass or "",
        "cssClass": body.cssClass or "",
    })
    return success()


@router.put("/system/dict/data")
async def update_dict_data(
    body: DictDataUpdate,
    current_user: dict = Depends(require_admin),
):
    """修改字典数据"""
    items = _DICT_DATA.get(body.dictType)
    if not items:
        return error("字典类型不存在")
    if 0 < body.dictCode <= len(items):
        items[body.dictCode - 1] = {
            "dictValue": body.dictValue,
            "dictLabel": body.dictLabel,
            "listClass": body.listClass or "",
            "cssClass": body.cssClass or "",
        }
    return success()


@router.delete("/system/dict/data/{dict_code}")
async def delete_dict_data(
    dict_code: int,
    dictType: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """删除字典数据（级联删除题目）"""
    if not dictType:
        return error("缺少 dictType 参数")
    items = _DICT_DATA.get(dictType)
    if not items:
        return error("字典类型不存在")
    if 0 < dict_code <= len(items):
        removed = items.pop(dict_code - 1)
        # 级联删除：若为题目类型，删除该类型所有题目
        if dictType == "question_type":
            type_num = int(removed["cssClass"])
            stmt = sa_delete(QuestionMain).where(QuestionMain.question_type == type_num)
            await db.execute(stmt)
            await db.commit()
    else:
        return error("字典数据不存在")
    return success()


# ========== 菜单 ==========

def _format_menu(m):
    return {
        "menuId": m.menu_id,
        "menuName": m.menu_name,
        "parentId": m.parent_id,
        "orderNum": m.order_num,
        "path": m.path,
        "component": m.component,
        "query": m.query,
        "isFrame": m.is_frame,
        "isCache": m.is_cache,
        "menuType": m.menu_type,
        "visible": m.visible,
        "status": m.status,
        "perms": m.perms,
        "icon": m.icon,
        "createTime": m.create_time.isoformat() if m.create_time else None,
    }


def _build_menu_treeselect(menus, parent_id=0):
    """构建菜单树选项(仅 id/label/children)"""
    tree = []
    for m in menus:
        if m.parent_id == parent_id:
            node = {"id": m.menu_id, "label": m.menu_name}
            children = _build_menu_treeselect(menus, m.menu_id)
            if children:
                node["children"] = children
            tree.append(node)
    return tree


@router.get("/system/menu/list")
async def list_menus(
    menuName: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询菜单列表（扁平）"""
    from app.models.menu import SysMenu
    query = select(SysMenu).where(SysMenu.status == "0")
    if menuName:
        query = query.where(SysMenu.menu_name.ilike(f"%{menuName}%"))
    query = query.order_by(SysMenu.parent_id, SysMenu.order_num)
    result = await db.execute(query)
    menus = list(result.scalars().all())
    return success([_format_menu(m) for m in menus])


@router.get("/system/menu/treeselect")
async def menu_tree(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """获取菜单树"""
    from app.models.menu import SysMenu
    query = select(SysMenu).where(SysMenu.status == "0").order_by(SysMenu.parent_id, SysMenu.order_num)
    result = await db.execute(query)
    menus = list(result.scalars().all())
    return success(_build_menu_treeselect(menus))


@router.get("/system/menu/roleMenuTreeselect/{role_id}")
async def role_menu_tree(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """获取角色菜单树"""
    from app.models.menu import SysMenu
    from app.models.role import SysRoleMenu
    query = select(SysMenu).where(SysMenu.status == "0").order_by(SysMenu.parent_id, SysMenu.order_num)
    result = await db.execute(query)
    menus = list(result.scalars().all())

    # 查询角色已勾选的菜单 ID
    rm_query = select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id)
    rm_result = await db.execute(rm_query)
    checked_keys = [row[0] for row in rm_result.all()]

    return success({
        "checkedKeys": checked_keys,
        "menus": _build_menu_treeselect(menus),
    })


# ========== 角色 ==========

def _format_role(r):
    return {
        "roleId": r.role_id,
        "roleName": r.role_name,
        "roleKey": r.role_key,
        "roleSort": r.role_sort,
        "dataScope": r.data_scope,
        "status": r.status,
        "delFlag": r.del_flag,
        "createTime": r.create_time.isoformat() if r.create_time else None,
        "remark": r.remark,
    }


@router.get("/system/role/list")
async def list_roles(
    roleName: Optional[str] = Query(None),
    roleKey: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询角色列表"""
    from app.models.role import SysRole
    query = select(SysRole).where(SysRole.del_flag == "0")
    if roleName:
        query = query.where(SysRole.role_name.ilike(f"%{roleName}%"))
    if roleKey:
        query = query.where(SysRole.role_key.ilike(f"%{roleKey}%"))
    if status:
        query = query.where(SysRole.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(SysRole.role_sort.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    roles = list(result.scalars().all())

    return paginate(total, [_format_role(r) for r in roles])


# ========== 部门 ==========

def _format_dept(d):
    return {
        "deptId": d.dept_id,
        "parentId": d.parent_id,
        "ancestors": d.ancestors,
        "deptName": d.dept_name,
        "orderNum": d.order_num,
        "leader": d.leader,
        "phone": d.phone,
        "email": d.email,
        "status": d.status,
        "createTime": d.create_time.isoformat() if d.create_time else None,
    }


@router.get("/system/dept/list")
async def list_depts(
    deptName: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询部门列表"""
    from app.models.user import SysDept
    query = select(SysDept).where(SysDept.del_flag == "0")
    if deptName:
        query = query.where(SysDept.dept_name.ilike(f"%{deptName}%"))
    if status:
        query = query.where(SysDept.status == status)
    query = query.order_by(SysDept.parent_id, SysDept.order_num)

    result = await db.execute(query)
    depts = list(result.scalars().all())
    return success([_format_dept(d) for d in depts])


@router.get("/system/dept/list/exclude/{dept_id}")
async def list_depts_exclude(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """查询部门列表（排除指定部门）"""
    from app.models.user import SysDept
    query = select(SysDept).where(SysDept.del_flag == "0").order_by(SysDept.parent_id, SysDept.order_num)
    result = await db.execute(query)
    all_depts = list(result.scalars().all())

    # 排除指定部门
    depts = [d for d in all_depts if d.dept_id != dept_id]
    return success([_format_dept(d) for d in depts])
