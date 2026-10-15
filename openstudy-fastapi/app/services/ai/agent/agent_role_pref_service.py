"""
Agent 专家开关的读写服务（`ai_agent_role_pref`）

产品口径（用户 2026-10-10 拍板）
-------------------------------
**默认全部专家开启，用户自由关闭**；关闭某专家的效果 = 指挥家的子代理通讯录里不再出现它、
显式路由也不会落到它 —— LLM 因此**实时**知道「这个专家叫不到」。

为什么是「专家粒度」而不是「工具粒度」
------------------------------------
普通用户不懂 `bank_manage` 这种技术工具名。用户要管理的是「我要不要用题库专家 / 笔记专家」
这种**能理解的角色**。故界面开关的对象是**官方专家（角色）**，本表存的是「用户关闭了哪些专家」。

存储是**稀疏**的：没有行 = 启用，有行且 `disabled` 非零 = 关闭。
所以「新增一个官方专家」不需要任何回填，新专家对所有人天生可用。

谁在用
------
    · `orchestrator` / `loop`：指挥家模式组装「子代理通讯录」时，跳过被关闭的专家；
      显式路由（用户选了某专家）也据此拦截。读侧只回答「这个用户关了哪些专家」。

本模块**自己开数据库会话**（调用方不持有 db）：读偏好发生在流式响应里，借请求会话会漏连接
（同 `tool_pref_service` 的说明）。

读侧 fail-open、写侧 fail-loud
------------------------------
读失败 → 返回空集（= 全部启用）。理由与 `tool_pref_service.disabled_tool_names` 一致：
它读的是**偏好**不是权限，读不到的最坏后果是「这一轮少关了一个专家」；反过来 fail-closed
会让「表一时连不上」直接表现成「专家全没了」。
写失败必须抛出去让路由如实回错 —— 「用户以为关掉了、其实没关」是最糟的结果。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Set

from loguru import logger
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.models.agent_role_pref import AiAgentRolePref


async def disabled_role_keys(user_id: int) -> Set[str]:
    """该用户**已关闭**的专家 key 集合（没有行 / disabled=0 / 表连不上 → 都不在集合里 = 启用）

    ⚠️ **永不抛**（读失败只记 warning 并返回空集）—— 见模块 docstring 的 fail-open 说明。
    """
    try:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(AiAgentRolePref.role_key, AiAgentRolePref.disabled).where(
                        AiAgentRolePref.user_id == int(user_id or 0)
                    )
                )
            ).all()
        # 判据是「**非零**即关闭」，与写侧归一 0/1 同向。
        return {str(key) for key, flag in rows if int(flag or 0) != 0}
    except Exception as e:  # noqa: BLE001 - 见 docstring：读偏好失败必须 fail-open
        logger.warning("[role_pref] 读取专家开关失败（按「全部启用」继续）user={}: {}", user_id, e)
        return set()


async def set_role_disabled(user_id: int, role_key: str, disabled: int) -> None:
    """upsert 一条 `(user_id, role_key)` 专家开关记录。

    - `disabled` 归一成 **0/1**（非零 → 1），避免「界面显示已启用、模型却用不到」的分叉。
    - **关闭（disabled=1）**：upsert 成 1；**启用（disabled=0）**：**删除**该行（还原稀疏，
      而不是写一堆 0 留着）。
    - 专家 key 合法性**不在本函数里校验**：合法名单只有 `roles.OFFICIAL_ROLES` 知道，
      校验放路由层，服务层不依赖 roles 模块、避免导入顺序踩循环依赖。
    - 归属由调用方保证（路由层只用 `current_user["user_id"]`，见 IDOR 红线）。
    """
    uid = int(user_id or 0)
    key = str(role_key or "").strip()
    if not key:
        raise ValueError("role_key 不能为空")
    flag = 1 if int(disabled or 0) else 0

    async with async_session_factory() as db:
        if flag == 0:
            await db.execute(
                delete(AiAgentRolePref).where(
                    AiAgentRolePref.user_id == uid,
                    AiAgentRolePref.role_key == key,
                )
            )
        else:
            row = (
                await db.execute(
                    select(AiAgentRolePref).where(
                        AiAgentRolePref.user_id == uid,
                        AiAgentRolePref.role_key == key,
                    )
                )
            ).scalars().first()
            now = datetime.now()
            if row is None:
                db.add(
                    AiAgentRolePref(
                        user_id=uid,
                        role_key=key,
                        disabled=flag,
                        create_time=now,
                        update_time=now,
                    )
                )
            else:
                row.disabled = flag
                row.update_time = now
        await db.commit()

    logger.info("[role_pref] 已保存专家开关 user={} role={} disabled={}", uid, key, flag)


async def set_all_roles_disabled(user_id: int, role_keys: List[str], disabled: int) -> None:
    """一次改**全部**专家的开关（面板上的「全选」）。

    与 `set_role_disabled` 同一套语义，区别只在「一批 key、一个事务」：
      · `disabled=1` → 把每个 key upsert 成 1；
      · `disabled=0` → **删除**该用户在这些 key 上的行（稀疏还原）。
    ⚠️ 只删 `user_id` 本人、且 key 在传入列表里的行。一个事务，要么全生效要么全不生效。
    写失败必须抛出去。
    """
    uid = int(user_id or 0)
    keys = [str(k or "").strip() for k in (role_keys or [])]
    keys = [k for k in keys if k]
    if not keys:
        return
    flag = 1 if int(disabled or 0) else 0

    async with async_session_factory() as db:
        if flag == 0:
            await db.execute(
                delete(AiAgentRolePref).where(
                    AiAgentRolePref.user_id == uid,
                    AiAgentRolePref.role_key.in_(keys),
                )
            )
        else:
            rows = (
                await db.execute(
                    select(AiAgentRolePref).where(
                        AiAgentRolePref.user_id == uid,
                        AiAgentRolePref.role_key.in_(keys),
                    )
                )
            ).scalars().all()
            existing = {r.role_key: r for r in rows}
            now = datetime.now()
            for key in keys:
                row = existing.get(key)
                if row is None:
                    db.add(
                        AiAgentRolePref(
                            user_id=uid,
                            role_key=key,
                            disabled=flag,
                            create_time=now,
                            update_time=now,
                        )
                    )
                else:
                    row.disabled = flag
                    row.update_time = now
        await db.commit()

    logger.info(
        "[role_pref] 已批量保存专家开关 user={} count={} disabled={}",
        uid,
        len(keys),
        flag,
    )


__all__ = ["disabled_role_keys", "set_role_disabled", "set_all_roles_disabled"]
