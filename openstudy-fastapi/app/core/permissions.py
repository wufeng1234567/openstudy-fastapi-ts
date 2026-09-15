"""
权限检查
"""

from enum import Enum
from typing import Optional


class DataScope(Enum):
    """数据权限范围"""
    ALL = "1"           # 全部数据权限
    CUSTOM = "2"        # 自定义数据权限
    DEPT = "3"          # 本部门数据权限
    DEPT_AND_CHILD = "4"  # 本部门及以下数据权限
    SELF = "5"          # 仅本人数据权限


def check_permission(required_perm: str, user_perms: list) -> bool:
    """检查用户是否有指定权限"""
    if "*:*:*" in user_perms:
        return True
    return required_perm in user_perms


def check_role(required_role: str, user_roles: list) -> bool:
    """检查用户是否有指定角色"""
    if "admin" in user_roles:
        return True
    return required_role in user_roles


def build_data_scope_filter(
    current_user: dict,
    dept_column: str = "dept_id",
    user_column: str = "user_id",
) -> Optional[str]:
    """构建数据权限过滤条件"""
    data_scope = current_user.get("data_scope", "1")
    user_id = current_user.get("user_id")
    dept_id = current_user.get("dept_id")

    if data_scope == DataScope.ALL.value:
        return None  # 不过滤
    elif data_scope == DataScope.DEPT.value:
        return f"{dept_column} = {dept_id}"
    elif data_scope == DataScope.DEPT_AND_CHILD.value:
        # 需要查询部门子级
        return f"{dept_column} IN (SELECT dept_id FROM sys_dept WHERE dept_id = {dept_id} OR ancestors LIKE '%,{dept_id},%')"
    elif data_scope == DataScope.SELF.value:
        return f"{user_column} = {user_id}"
    return None
