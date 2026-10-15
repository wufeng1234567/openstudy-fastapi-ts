"""初始化数据脚本"""
import asyncio
from app.database import async_session_factory
from app.core.security import hash_password
from app.models.user import SysUser, SysUserRole
from app.models.role import SysRole
from app.models.menu import SysMenu
from app.models.notice import SysNotice
from app.models.config import SysConfig
from sqlalchemy import select
from datetime import datetime


async def init_data():
    async with async_session_factory() as db:
        # 检查是否已有admin用户
        result = await db.execute(select(SysUser).where(SysUser.user_name == "admin"))
        if result.scalar_one_or_none():
            print("Admin user already exists, skipping user/role/menu initialization")
        else:
            print("Initializing user/role/menu data...")

            # 创建部门
            from app.models.user import SysDept
            dept = SysDept(dept_name="研发部门", order_num=1, status="0", del_flag="0")
            db.add(dept)
            await db.flush()

            # 创建角色
            role = SysRole(
                role_name="管理员",
                role_key="admin",
                role_sort=1,
                data_scope="1",
                menu_check_strictly=True,
                dept_check_strictly=True,
                status="0",
                del_flag="0",
            )
            db.add(role)
            await db.flush()

            # 创建基本菜单
            system_menu = SysMenu(
                menu_name="系统管理",
                parent_id=0,
                order_num=1,
                menu_type="M",
                visible="0",
                status="0",
                perms="",
                icon="system",
            )
            db.add(system_menu)
            await db.flush()

            user_menu = SysMenu(
                menu_name="用户管理",
                parent_id=system_menu.menu_id,
                order_num=1,
                path="user",
                component="system/user/index",
                menu_type="C",
                visible="0",
                status="0",
                perms="system:user:list",
                icon="user",
            )
            db.add(user_menu)
            await db.flush()

            role_menu = SysMenu(
                menu_name="角色管理",
                parent_id=system_menu.menu_id,
                order_num=2,
                path="role",
                component="system/role/index",
                menu_type="C",
                visible="0",
                status="0",
                perms="system:role:list",
                icon="peoples",
            )
            db.add(role_menu)
            await db.flush()

            menu_item = SysMenu(
                menu_name="菜单管理",
                parent_id=system_menu.menu_id,
                order_num=3,
                path="menu",
                component="system/menu/index",
                menu_type="C",
                visible="0",
                status="0",
                perms="system:menu:list",
                icon="tree-table",
            )
            db.add(menu_item)
            await db.flush()

            # 角色菜单关联
            from app.models.role import SysRoleMenu
            for m in [system_menu, user_menu, role_menu, menu_item]:
                db.add(SysRoleMenu(role_id=role.role_id, menu_id=m.menu_id))

            # 创建admin用户
            admin_user = SysUser(
                user_name="admin",
                nick_name="管理员",
                password=hash_password("admin123"),
                sex="0",
                status="0",
                del_flag="0",
                dept_id=dept.dept_id,
            )
            db.add(admin_user)
            await db.flush()

            # 用户角色关联
            db.add(SysUserRole(user_id=admin_user.user_id, role_id=role.role_id))

            # 创建默认公告
            notice = SysNotice(
                notice_title="欢迎使用OpenStudy",
                notice_type="1",
                notice_content="OpenStudy 是一个在线学习平台，支持题库管理、AI出题等功能。",
                status="0",
            )
            db.add(notice)
            print("User/role/menu data initialized!")

        # 系统配置 - 每次都检查并补充（幂等操作）
        config_result = await db.execute(
            select(SysConfig).where(SysConfig.config_key == "sys.account.captchaEnabled")
        )
        if not config_result.scalar_one_or_none():
            print("Initializing system config data...")
            configs = [
                SysConfig(
                    config_name="主框架页-默认皮肤样式名称",
                    config_key="sys.index.skinName",
                    config_value="skin-blue",
                    config_type="Y",
                    create_by="admin",
                    create_time=datetime.utcnow(),
                    remark="蓝色 skin-blue、绿色 skin-green、紫色 skin-purple、红色 skin-red、黄色 skin-yellow",
                ),
                SysConfig(
                    config_name="用户管理-账号初始密码",
                    config_key="sys.user.initPassword",
                    config_value="123456",
                    config_type="Y",
                    create_by="admin",
                    create_time=datetime.utcnow(),
                    remark="初始化密码 123456",
                ),
                SysConfig(
                    config_name="主框架页-侧边栏主题",
                    config_key="sys.index.sideTheme",
                    config_value="theme-dark",
                    config_type="Y",
                    create_by="admin",
                    create_time=datetime.utcnow(),
                    remark="深色主题theme-dark，浅色主题theme-light",
                ),
                SysConfig(
                    config_name="账号自助-验证码开关",
                    config_key="sys.account.captchaEnabled",
                    config_value="true",
                    config_type="Y",
                    create_by="admin",
                    create_time=datetime.utcnow(),
                    remark="是否开启验证码功能（true开启，false关闭）",
                ),
                SysConfig(
                    config_name="账号自助-是否开启用户注册功能",
                    config_key="sys.account.registerUser",
                    config_value="true",
                    config_type="Y",
                    create_by="admin",
                    create_time=datetime.utcnow(),
                    remark="是否开启注册用户功能（true开启，false关闭）",
                ),
            ]
            for cfg in configs:
                db.add(cfg)
            print("System config data initialized!")
        else:
            print("System config data already exists, skipping")

        await db.commit()
        print("Data initialization complete!")


if __name__ == "__main__":
    asyncio.run(init_data())
