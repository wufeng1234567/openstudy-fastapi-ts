"""
用户仓库
"""

from typing import Optional, Tuple, List
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.user import SysUser, SysUserRole, SysDept
from app.models.role import SysRole
from app.models.menu import SysMenu


class UserRepository:
    """用户仓库"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> Optional[SysUser]:
        """根据用户名查询用户"""
        query = select(SysUser).where(
            SysUser.user_name == username,
            SysUser.del_flag == "0",
        ).options(selectinload(SysUser.roles))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[SysUser]:
        """根据ID查询用户"""
        query = select(SysUser).where(
            SysUser.user_id == user_id,
            SysUser.del_flag == "0",
        ).options(selectinload(SysUser.roles), selectinload(SysUser.dept))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        user_name: Optional[str] = None,
        phonenumber: Optional[str] = None,
        status: Optional[str] = None,
        dept_id: Optional[int] = None,
        page_num: int = 1,
        page_size: int = 10,
    ) -> Tuple[int, List[SysUser]]:
        """查询用户列表"""
        query = select(SysUser).where(SysUser.del_flag == "0")

        if user_name:
            query = query.where(SysUser.user_name.ilike(f"%{user_name}%"))
        if phonenumber:
            query = query.where(SysUser.phonenumber.ilike(f"%{phonenumber}%"))
        if status:
            query = query.where(SysUser.status == status)
        if dept_id:
            query = query.where(SysUser.dept_id == dept_id)

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # 分页
        query = query.options(
            selectinload(SysUser.roles),
            selectinload(SysUser.dept),
        ).order_by(SysUser.user_id.desc())
        query = query.offset((page_num - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return total, list(result.scalars().all())

    async def create(self, user: SysUser) -> SysUser:
        """创建用户"""
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: SysUser) -> None:
        """更新用户"""
        await self.db.merge(user)

    async def delete_by_ids(self, ids: List[int]) -> None:
        """删除用户（逻辑删除）"""
        stmt = (
            update(SysUser)
            .where(SysUser.user_id.in_(ids))
            .values(del_flag="2")
        )
        await self.db.execute(stmt)

    async def get_user_roles(self, user_id: int) -> List[SysRole]:
        """获取用户角色"""
        user = await self.get_by_id(user_id)
        return user.roles if user else []

    async def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户权限"""
        user = await self.get_by_id(user_id)
        if not user:
            return []

        # 管理员拥有所有权限
        if any(role.role_key == "admin" for role in user.roles):
            return ["*:*:*"]

        # 查询角色对应的菜单权限
        perms = set()
        for role in user.roles:
            for menu in role.menus:
                if menu.perms:
                    perms.add(menu.perms)

        return list(perms)

    async def update_user_roles(self, user_id: int, role_ids: List[int]) -> None:
        """更新用户角色"""
        # 删除原有角色关联
        delete_stmt = SysUserRole.__table__.delete().where(SysUserRole.user_id == user_id)
        await self.db.execute(delete_stmt)

        # 添加新角色关联
        for role_id in role_ids:
            user_role = SysUserRole(user_id=user_id, role_id=role_id)
            self.db.add(user_role)

    async def check_user_name_unique(self, user_name: str, exclude_id: int = None) -> bool:
        """检查用户名是否唯一"""
        query = select(SysUser).where(
            SysUser.user_name == user_name,
            SysUser.del_flag == "0",
        )
        if exclude_id:
            query = query.where(SysUser.user_id != exclude_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is None
