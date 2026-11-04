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
    { "dictId": 8, "dictName": "操作类型", "dictType": "sys_oper_type", "status": "0" },
    { "dictId": 9, "dictName": "任务分组", "dictType": "sys_job_group", "status": "0" },
    { "dictId": 10, "dictName": "任务状态", "dictType": "sys_job_status", "status": "0" },
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
        { "dictValue": "1", "dictLabel": "失败", "listClass": "danger", "cssClass": "" },
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
    "sys_oper_type": [
        { "dictValue": "0", "dictLabel": "其他", "listClass": "info", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "新增", "listClass": "primary", "cssClass": "" },
        { "dictValue": "2", "dictLabel": "修改", "listClass": "success", "cssClass": "" },
        { "dictValue": "3", "dictLabel": "删除", "listClass": "danger", "cssClass": "" },
        { "dictValue": "4", "dictLabel": "授权", "listClass": "primary", "cssClass": "" },
        { "dictValue": "5", "dictLabel": "导出", "listClass": "warning", "cssClass": "" },
        { "dictValue": "6", "dictLabel": "导入", "listClass": "warning", "cssClass": "" },
        { "dictValue": "7", "dictLabel": "强退", "listClass": "danger", "cssClass": "" },
        { "dictValue": "8", "dictLabel": "清空", "listClass": "danger", "cssClass": "" },
    ],
    "sys_job_group": [
        { "dictValue": "DEFAULT", "dictLabel": "默认", "listClass": "primary", "cssClass": "" },
        { "dictValue": "SYSTEM", "dictLabel": "系统", "listClass": "info", "cssClass": "" },
    ],
    "sys_job_status": [
        { "dictValue": "0", "dictLabel": "正常", "listClass": "success", "cssClass": "" },
        { "dictValue": "1", "dictLabel": "暂停", "listClass": "danger", "cssClass": "" },
    ],
}

_DICT_LOADED = False


async def _ensure_dict_loaded(db: AsyncSession) -> None:
    """首次访问时把 DB 字典加载到进程缓存；空库则用内置默认值种子化。

    进程内 list/dict 继续作为读缓存（保持现有前端接口），但任何写操作都会同步
    写 `sys_dict_type` / `sys_dict_data`，重启后不会丢新增的字典。
    """
    global _DICT_LOADED
    if _DICT_LOADED:
        return
    from app.models.dict import SysDictData, SysDictType

    type_count = await db.scalar(select(func.count()).select_from(SysDictType))
    if not type_count:
        for item in _DICT_TYPES:
            db.add(SysDictType(
                dict_id=item["dictId"],
                dict_name=item["dictName"],
                dict_type=item["dictType"],
                status=item.get("status", "0"),
                create_time=datetime.now(),
            ))
        for dict_type, items in _DICT_DATA.items():
            for idx, item in enumerate(items):
                db.add(SysDictData(
                    dict_sort=idx,
                    dict_label=item["dictLabel"],
                    dict_value=item["dictValue"],
                    dict_type=dict_type,
                    css_class=item.get("cssClass", ""),
                    list_class=item.get("listClass", ""),
                    create_time=datetime.now(),
                ))
        await db.flush()
    else:
        types = list((await db.execute(select(SysDictType).order_by(SysDictType.dict_id))).scalars().all())
        rows = list((await db.execute(select(SysDictData).order_by(SysDictData.dict_type, SysDictData.dict_sort, SysDictData.dict_code))).scalars().all())
        _DICT_TYPES.clear()
        _DICT_TYPES.extend([
            {"dictId": int(t.dict_id), "dictName": t.dict_name, "dictType": t.dict_type, "status": t.status, "remark": t.remark}
            for t in types
        ])
        _DICT_DATA.clear()
        for row in rows:
            _DICT_DATA.setdefault(row.dict_type, []).append({
                "_dictCode": int(row.dict_code),
                "dictValue": row.dict_value,
                "dictLabel": row.dict_label,
                "listClass": row.list_class or "",
                "cssClass": row.css_class or "",
            })
    _DICT_LOADED = True


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
    await _ensure_dict_loaded(db)
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
    await _ensure_dict_loaded(db)
    return success(_DICT_TYPES)


class DictTypeCreate(BaseModel):
    dictName: str
    dictType: str
    status: Optional[str] = "0"
    remark: Optional[str] = None


class DictTypeUpdate(BaseModel):
    dictId: int
    dictName: str
    dictType: str
    status: Optional[str] = "0"
    remark: Optional[str] = None


@router.get("/system/dict/type/{dict_id}")
async def get_dict_type(
    dict_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    await _ensure_dict_loaded(db)
    row = next((d for d in _DICT_TYPES if int(d["dictId"]) == dict_id), None)
    if not row:
        return error("字典类型不存在", code=404)
    return success(row)


@router.post("/system/dict/type")
async def create_dict_type(
    body: DictTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    await _ensure_dict_loaded(db)
    if any(d["dictType"] == body.dictType for d in _DICT_TYPES):
        return error("字典类型已存在", code=400)
    from app.models.dict import SysDictType
    next_id = max((int(d["dictId"]) for d in _DICT_TYPES), default=0) + 1
    row = {
        "dictId": next_id,
        "dictName": body.dictName.strip(),
        "dictType": body.dictType.strip(),
        "status": body.status or "0",
        "remark": body.remark,
    }
    db.add(SysDictType(
        dict_id=next_id,
        dict_name=row["dictName"],
        dict_type=row["dictType"],
        status=row["status"],
        remark=row["remark"],
        create_time=datetime.now(),
    ))
    _DICT_TYPES.append(row)
    _DICT_DATA.setdefault(row["dictType"], [])
    await db.flush()
    return success(row)


@router.put("/system/dict/type")
async def update_dict_type(
    body: DictTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    await _ensure_dict_loaded(db)
    row = next((d for d in _DICT_TYPES if int(d["dictId"]) == body.dictId), None)
    if not row:
        return error("字典类型不存在", code=404)
    old_type = row["dictType"]
    if body.dictType != old_type and any(d["dictType"] == body.dictType for d in _DICT_TYPES):
        return error("字典类型已存在", code=400)
    row.update({
        "dictName": body.dictName.strip(),
        "dictType": body.dictType.strip(),
        "status": body.status or "0",
        "remark": body.remark,
    })
    from app.models.dict import SysDictData, SysDictType
    db_row = await db.get(SysDictType, body.dictId)
    if db_row:
        db_row.dict_name = row["dictName"]
        db_row.dict_type = row["dictType"]
        db_row.status = row["status"]
        db_row.remark = row["remark"]
        db_row.update_time = datetime.now()
    if old_type != body.dictType:
        for data_row in (await db.execute(select(SysDictData).where(SysDictData.dict_type == old_type))).scalars().all():
            data_row.dict_type = body.dictType
        _DICT_DATA[body.dictType] = _DICT_DATA.pop(old_type, [])
    await db.flush()
    return success(row)


@router.delete("/system/dict/type/refreshCache")
async def refresh_dict_cache(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    global _DICT_LOADED
    _DICT_LOADED = False
    await _ensure_dict_loaded(db)
    return success({"refreshed": len(_DICT_TYPES)})


@router.delete("/system/dict/type/{dict_id}")
async def delete_dict_type(
    dict_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    await _ensure_dict_loaded(db)
    idx = next((i for i, d in enumerate(_DICT_TYPES) if int(d["dictId"]) == dict_id), None)
    if idx is None:
        return error("字典类型不存在", code=404)
    row = _DICT_TYPES.pop(idx)
    _DICT_DATA.pop(row["dictType"], None)
    from app.models.dict import SysDictData, SysDictType
    await db.execute(sa_delete(SysDictData).where(SysDictData.dict_type == row["dictType"]))
    await db.execute(sa_delete(SysDictType).where(SysDictType.dict_id == dict_id))
    await db.flush()
    return success()


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
    await _ensure_dict_loaded(db)
    all_items = []
    dict_type_key = dictType
    if dict_type_key and dict_type_key in _DICT_DATA:
        items = [
            { **{k: v for k, v in item.items() if k != "_dictCode"}, "dictCode": int(item.get("_dictCode", i + 1)), "dictType": dict_type_key}
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
    await _ensure_dict_loaded(db)
    data = [
        {k: v for k, v in item.items() if k != "_dictCode"}
        for item in _DICT_DATA.get(dict_type, [])
    ]
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """新增字典数据"""
    await _ensure_dict_loaded(db)
    from app.models.dict import SysDictData
    row = SysDictData(
        dict_type=body.dictType,
        dict_value=body.dictValue,
        dict_label=body.dictLabel,
        list_class=body.listClass or "",
        css_class=body.cssClass or "",
        create_time=datetime.now(),
    )
    db.add(row)
    await db.flush()
    if body.dictType not in _DICT_DATA:
        _DICT_DATA[body.dictType] = []
    _DICT_DATA[body.dictType].append({
        "_dictCode": int(row.dict_code),
        "dictValue": body.dictValue,
        "dictLabel": body.dictLabel,
        "listClass": body.listClass or "",
        "cssClass": body.cssClass or "",
    })
    return success({"dictCode": int(row.dict_code)})


@router.put("/system/dict/data")
async def update_dict_data(
    body: DictDataUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """修改字典数据"""
    await _ensure_dict_loaded(db)
    items = _DICT_DATA.get(body.dictType)
    if not items:
        return error("字典类型不存在")
    target = next((item for item in items if int(item.get("_dictCode", 0)) == body.dictCode), None)
    if target is None and 0 < body.dictCode <= len(items):
        target = items[body.dictCode - 1]
    if target is None:
        return error("字典数据不存在", code=404)
    target.update({
        "dictValue": body.dictValue,
        "dictLabel": body.dictLabel,
        "listClass": body.listClass or "",
        "cssClass": body.cssClass or "",
    })
    from app.models.dict import SysDictData
    db_row = next((r for r in (await db.execute(
        select(SysDictData).where(SysDictData.dict_type == body.dictType)
    )).scalars().all() if int(r.dict_code) == int(target.get("_dictCode", body.dictCode))), None)
    if db_row:
        db_row.dict_value = body.dictValue
        db_row.dict_label = body.dictLabel
        db_row.list_class = body.listClass or ""
        db_row.css_class = body.cssClass or ""
        db_row.update_time = datetime.now()
        await db.flush()
    return success()


@router.delete("/system/dict/data/{dict_code}")
async def delete_dict_data(
    dict_code: int,
    dictType: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """删除字典数据（只删字典配置，不触碰业务题目）"""
    await _ensure_dict_loaded(db)
    if not dictType:
        return error("缺少 dictType 参数")
    items = _DICT_DATA.get(dictType)
    if not items:
        return error("字典类型不存在")
    target_idx = next((i for i, item in enumerate(items) if int(item.get("_dictCode", i + 1)) == dict_code), None)
    if target_idx is None and 0 < dict_code <= len(items):
        target_idx = dict_code - 1
    if target_idx is None:
        return error("字典数据不存在")
    item = items.pop(target_idx)
    from app.models.dict import SysDictData
    await db.execute(sa_delete(SysDictData).where(
        SysDictData.dict_type == dictType,
        SysDictData.dict_code == int(item.get("_dictCode", dict_code)),
    ))
    await db.flush()
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


@router.get("/system/role/{role_id}")
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole
    role = (await db.execute(select(SysRole).where(SysRole.role_id == role_id))).scalar_one_or_none()
    if not role or role.del_flag != "0":
        return error("角色不存在", code=404)
    return success(_format_role(role))


@router.post("/system/role")
async def create_role(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole, SysRoleMenu
    name = str(payload.get("roleName") or "").strip()
    key = str(payload.get("roleKey") or "").strip()
    if not name or not key:
        return error("角色名称和权限字符不能为空", code=400)
    dup = await db.scalar(select(func.count()).select_from(SysRole).where(SysRole.role_key == key, SysRole.del_flag == "0"))
    if dup:
        return error("权限字符已存在", code=400)
    role = SysRole(
        role_name=name,
        role_key=key,
        role_sort=int(payload.get("roleSort") or 0),
        data_scope=str(payload.get("dataScope") or "1"),
        status=str(payload.get("status") or "0"),
        remark=payload.get("remark"),
        create_by=current_user.get("user_name", ""),
        create_time=datetime.now(),
    )
    db.add(role)
    await db.flush()
    for menu_id in payload.get("menuIds") or []:
        try:
            db.add(SysRoleMenu(role_id=role.role_id, menu_id=int(menu_id)))
        except (TypeError, ValueError):
            continue
    await db.flush()
    return success({"roleId": role.role_id})


@router.put("/system/role")
async def update_role(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole, SysRoleMenu
    role_id = int(payload.get("roleId") or 0)
    role = (await db.execute(select(SysRole).where(SysRole.role_id == role_id))).scalar_one_or_none()
    if not role or role.del_flag != "0":
        return error("角色不存在", code=404)
    if role.role_key == "admin" and "roleKey" in payload and payload.get("roleKey") != "admin":
        return error("内置管理员角色不能修改权限字符", code=400)
    if payload.get("roleName") is not None:
        role.role_name = str(payload["roleName"]).strip()
    if payload.get("roleKey") is not None:
        role.role_key = str(payload["roleKey"]).strip()
    if payload.get("roleSort") is not None:
        role.role_sort = int(payload["roleSort"])
    if payload.get("status") is not None:
        role.status = str(payload["status"])
    if payload.get("dataScope") is not None:
        role.data_scope = str(payload["dataScope"])
    if payload.get("remark") is not None:
        role.remark = payload["remark"]
    if "menuIds" in payload:
        await db.execute(sa_delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id))
        for menu_id in payload.get("menuIds") or []:
            try:
                db.add(SysRoleMenu(role_id=role_id, menu_id=int(menu_id)))
            except (TypeError, ValueError):
                continue
    role.update_by = current_user.get("user_name", "")
    role.update_time = datetime.now()
    await db.flush()
    return success()


@router.put("/system/role/changeStatus")
async def change_role_status(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole
    role = (await db.execute(select(SysRole).where(SysRole.role_id == int(payload.get("roleId") or 0)))).scalar_one_or_none()
    if not role:
        return error("角色不存在", code=404)
    if role.role_key == "admin" and str(payload.get("status")) != "0":
        return error("内置管理员角色不能停用", code=400)
    role.status = str(payload.get("status") or "0")
    role.update_time = datetime.now()
    await db.flush()
    return success()


@router.put("/system/role/dataScope")
async def update_role_data_scope(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole
    role = (await db.execute(select(SysRole).where(SysRole.role_id == int(payload.get("roleId") or 0)))).scalar_one_or_none()
    if not role:
        return error("角色不存在", code=404)
    role.data_scope = str(payload.get("dataScope") or "1")
    role.update_time = datetime.now()
    await db.flush()
    return success()


@router.delete("/system/role/{role_ids}")
async def delete_roles(
    role_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.role import SysRole, SysRoleMenu
    from app.models.user import SysUserRole
    ids = []
    for raw in role_ids.split(","):
        if raw.strip().isdigit():
            ids.append(int(raw.strip()))
    if not ids:
        return error("角色ID不能为空", code=400)
    roles = list((await db.execute(select(SysRole).where(SysRole.role_id.in_(ids)))).scalars().all())
    if any(r.role_key == "admin" for r in roles):
        return error("内置管理员角色不能删除", code=400)
    await db.execute(sa_delete(SysRoleMenu).where(SysRoleMenu.role_id.in_(ids)))
    await db.execute(sa_delete(SysUserRole).where(SysUserRole.role_id.in_(ids)))
    await db.execute(update(SysRole).where(SysRole.role_id.in_(ids)).values(del_flag="2", update_time=datetime.now()))
    await db.flush()
    return success()


@router.get("/system/role/authUser/allocatedList")
async def allocated_role_users(
    roleId: int = Query(...),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysUser, SysUserRole
    base = select(SysUser).join(SysUserRole, SysUserRole.user_id == SysUser.user_id).where(SysUserRole.role_id == roleId)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = list((await db.execute(base.offset((pageNum - 1) * pageSize).limit(pageSize))).scalars().all())
    return paginate(total or 0, [
        {"userId": u.user_id, "userName": u.user_name, "nickName": u.nick_name, "email": u.email, "phonenumber": u.phonenumber, "status": u.status}
        for u in rows
    ])


@router.get("/system/role/authUser/unallocatedList")
async def unallocated_role_users(
    roleId: int = Query(...),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysUser, SysUserRole
    allocated = select(SysUserRole.user_id).where(SysUserRole.role_id == roleId)
    base = select(SysUser).where(SysUser.user_id.not_in(allocated))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = list((await db.execute(base.offset((pageNum - 1) * pageSize).limit(pageSize))).scalars().all())
    return paginate(total or 0, [
        {"userId": u.user_id, "userName": u.user_name, "nickName": u.nick_name, "email": u.email, "phonenumber": u.phonenumber, "status": u.status}
        for u in rows
    ])


@router.put("/system/role/authUser/cancel")
async def cancel_role_user(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysUserRole
    await db.execute(sa_delete(SysUserRole).where(
        SysUserRole.role_id == int(payload.get("roleId") or 0),
        SysUserRole.user_id == int(payload.get("userId") or 0),
    ))
    await db.flush()
    return success()


@router.put("/system/role/authUser/cancelAll")
async def cancel_all_role_users(
    roleId: int = Query(...),
    userIds: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysUserRole
    ids = [int(x) for x in str(userIds).split(",") if x.strip().isdigit()]
    if ids:
        await db.execute(sa_delete(SysUserRole).where(SysUserRole.role_id == roleId, SysUserRole.user_id.in_(ids)))
        await db.flush()
    return success()


@router.put("/system/role/authUser/selectAll")
async def select_all_role_users(
    roleId: int = Query(...),
    userIds: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysUserRole
    ids = [int(x) for x in str(userIds).split(",") if x.strip().isdigit()]
    existing = set((await db.execute(select(SysUserRole.user_id).where(SysUserRole.role_id == roleId))).scalars().all())
    for uid in ids:
        if uid not in existing:
            db.add(SysUserRole(role_id=roleId, user_id=uid))
    await db.flush()
    return success()


@router.get("/system/role/deptTree/{role_id}")
async def role_dept_tree(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysDept
    depts = list((await db.execute(select(SysDept).where(SysDept.del_flag == "0").order_by(SysDept.parent_id, SysDept.order_num))).scalars().all())
    return success({"checkedKeys": [], "depts": [_format_dept(d) for d in depts]})


@router.get("/system/dept/{dept_id}")
async def get_dept(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysDept
    dept = (await db.execute(select(SysDept).where(SysDept.dept_id == dept_id))).scalar_one_or_none()
    if not dept or dept.del_flag != "0":
        return error("部门不存在", code=404)
    return success(_format_dept(dept))


@router.post("/system/dept")
async def create_dept(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysDept
    name = str(payload.get("deptName") or "").strip()
    if not name:
        return error("部门名称不能为空", code=400)
    parent_id = int(payload.get("parentId") or 0)
    parent = await db.get(SysDept, parent_id) if parent_id else None
    ancestors = f"{parent.ancestors},{parent_id}" if parent and parent.ancestors else (str(parent_id) if parent_id else "0")
    dept = SysDept(
        parent_id=parent_id,
        ancestors=ancestors,
        dept_name=name,
        order_num=int(payload.get("orderNum") or 0),
        leader=payload.get("leader"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        status=str(payload.get("status") or "0"),
        create_time=datetime.now(),
    )
    db.add(dept)
    await db.flush()
    return success({"deptId": dept.dept_id})


@router.put("/system/dept")
async def update_dept(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysDept
    dept = await db.get(SysDept, int(payload.get("deptId") or 0))
    if not dept or dept.del_flag != "0":
        return error("部门不存在", code=404)
    if payload.get("deptName") is not None:
        dept.dept_name = str(payload["deptName"]).strip()
    if payload.get("orderNum") is not None:
        dept.order_num = int(payload["orderNum"])
    if payload.get("leader") is not None:
        dept.leader = payload["leader"]
    if payload.get("phone") is not None:
        dept.phone = payload["phone"]
    if payload.get("email") is not None:
        dept.email = payload["email"]
    if payload.get("status") is not None:
        dept.status = str(payload["status"])
    dept.update_time = datetime.now()
    await db.flush()
    return success()


@router.delete("/system/dept/{dept_id}")
async def delete_dept(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.user import SysDept, SysUser
    dept = await db.get(SysDept, dept_id)
    if not dept or dept.del_flag != "0":
        return error("部门不存在", code=404)
    children = await db.scalar(select(func.count()).select_from(SysDept).where(SysDept.parent_id == dept_id, SysDept.del_flag == "0"))
    if children:
        return error("存在下级部门，不能删除", code=400)
    users = await db.scalar(select(func.count()).select_from(SysUser).where(SysUser.dept_id == dept_id))
    if users:
        return error("部门下存在用户，不能删除", code=400)
    dept.del_flag = "2"
    dept.update_time = datetime.now()
    await db.flush()
    return success()


@router.get("/system/menu/{menu_id}")
async def get_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.menu import SysMenu
    menu = await db.get(SysMenu, menu_id)
    if not menu:
        return error("菜单不存在", code=404)
    return success(_format_menu(menu))


@router.post("/system/menu")
async def create_menu(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.menu import SysMenu
    name = str(payload.get("menuName") or "").strip()
    if not name:
        return error("菜单名称不能为空", code=400)
    menu = SysMenu(
        menu_name=name,
        parent_id=int(payload.get("parentId") or 0),
        order_num=int(payload.get("orderNum") or 0),
        path=payload.get("path") or "",
        component=payload.get("component"),
        query=payload.get("query"),
        is_frame=int(payload.get("isFrame") if payload.get("isFrame") is not None else 1),
        is_cache=int(payload.get("isCache") or 0),
        menu_type=str(payload.get("menuType") or "C"),
        visible=str(payload.get("visible") or "0"),
        status=str(payload.get("status") or "0"),
        perms=payload.get("perms"),
        icon=payload.get("icon") or "#",
        remark=payload.get("remark"),
        create_by=current_user.get("user_name", ""),
        create_time=datetime.now(),
    )
    db.add(menu)
    await db.flush()
    return success({"menuId": menu.menu_id})


@router.put("/system/menu")
async def update_menu(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.menu import SysMenu
    menu = await db.get(SysMenu, int(payload.get("menuId") or 0))
    if not menu:
        return error("菜单不存在", code=404)
    for field, key in (
        ("menu_name", "menuName"), ("parent_id", "parentId"), ("order_num", "orderNum"),
        ("path", "path"), ("component", "component"), ("menu_type", "menuType"),
        ("visible", "visible"), ("status", "status"), ("perms", "perms"), ("icon", "icon"),
    ):
        if payload.get(key) is not None:
            value = payload[key]
            if field in ("parent_id", "order_num"):
                value = int(value or 0)
            setattr(menu, field, str(value) if field in ("menu_type", "visible", "status") else value)
    menu.update_by = current_user.get("user_name", "")
    menu.update_time = datetime.now()
    await db.flush()
    return success()


@router.delete("/system/menu/{menu_id}")
async def delete_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    from app.models.menu import SysMenu
    from app.models.role import SysRoleMenu
    menu = await db.get(SysMenu, menu_id)
    if not menu:
        return error("菜单不存在", code=404)
    children = await db.scalar(select(func.count()).select_from(SysMenu).where(SysMenu.parent_id == menu_id))
    if children:
        return error("存在子菜单，不能删除", code=400)
    await db.execute(sa_delete(SysRoleMenu).where(SysRoleMenu.menu_id == menu_id))
    await db.delete(menu)
    await db.flush()
    return success()


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
