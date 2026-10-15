"""
Agent 工具开关的读写服务（`ai_agent_tool_pref`）

产品口径（用户已拍板）
----------------------
**默认全部工具开启，用户自由选择屏蔽**；全部被屏蔽时**不报错**，退化成纯聊天
（在提示词里如实说明「本轮没有任何工具」，见 `loop.run_agent_stream`）。

存储是**稀疏**的：没有行 = 启用，有行且 `disabled` 非零 = 屏蔽。
所以「新增一个工具」不需要任何回填，新工具对所有人天生可用。

谁在用这个模块（四处「面向模型」的出口 + 两处执行闸门）
------------------------------------------------------
    · `loop.run_agent_stream` → `registry.definitions(exclude=…)`（Function Calling）
    · `loop.run_agent_stream` → `registry.describe(exclude=…)`（系统提示词的工具清单）
    · `loop.run_agent_stream` → `meta` 事件的「可用工具」列表
    · `api/v1/ai.py: _agent_tools_payload` → `GET /ai/agent/tools`（ds-free 的唯一来源）
    · `loop._prepare_tool_call` → ds-free 的 `/agent/execute` 与 `/agent/preview`
    · `loop.run_agent_stream` 内联执行分支

⚠️ 只做「不广播」是不够的：模型完全可能凭上一轮上下文发起一个没被广播的工具名，
所以**执行侧必须自己再拦一次**。这个模块只负责回答「这个用户屏蔽了哪些」，
两处闸门都在 `loop.py` 里（口径收敛在 `loop._disabled_fail`）。

本模块**自己开数据库会话**（调用方不持有 db）：
`run_agent_stream` 是流式响应，借请求会话去查会漏连接（见 `runtime_context` 的说明），
而这里读偏好同样发生在流式响应里。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Set

from loguru import logger
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.models.agent_tool_pref import AiAgentToolPref


async def disabled_tool_names(user_id: int) -> Set[str]:
    """该用户**生效的**屏蔽集合：`{tool_name | 该行 disabled 非零}`。

    没有行 / `disabled = 0` / 库里根本没这张表 → 都不在集合里（= 启用）。

    ⚠️ **本函数永不抛异常**（读失败只记 warning 并返回空集）。这是**刻意的
    fail-open**，理由要说清楚，免得下次被当成 bug「修」掉：

      · 它读的是**用户的偏好**，不是权限、不是数据。读不到的最坏后果是
        「这一轮少屏蔽了一个工具」；
      · 反过来 fail-closed（读失败就当成全部屏蔽）会让「这张表一时连不上」
        直接表现成「Agent 一个工具都没有」，而 `run_agent_stream` 会据此走纯聊天
        —— 用户看到的是一句「本轮没有可用工具」，他连自己哪里做错了都看不出来；
      · 与 RAG 那道闸门（`rag_write_service.resolve_kbs`）方向一致：那里的默认分支
        也是在 SQL 里过滤，而不是让检索整个失败。

    只针对**读**。写侧 `set_tool_disabled` 失败必须抛出去让路由如实回错 ——
    「用户以为关掉了、其实没关」是最糟的结果，比回一个 500 严重得多。
    """
    try:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(AiAgentToolPref.tool_name, AiAgentToolPref.disabled).where(
                        AiAgentToolPref.user_id == int(user_id or 0)
                    )
                )
            ).all()
        # 判据是「**非零**即屏蔽」，与读侧 `disabled == 0` 的 SQL 过滤同向；
        # 库里真存进过 2 这种值也不会出现「UI 说开着、模型说关着」的分叉。
        return {str(name) for name, flag in rows if int(flag or 0) != 0}
    except Exception as e:  # noqa: BLE001 - 见 docstring：读偏好失败必须 fail-open
        logger.warning("[tool_pref] 读取工具开关失败（按「全部启用」继续）user={}: {}", user_id, e)
        return set()


async def set_tool_disabled(user_id: int, tool_name: str, disabled: int) -> None:
    """upsert 一条 `(user_id, tool_name)` 开关记录。

    - `disabled` 归一成 **0/1**（非零 → 1）。与 `rag_write_service.update_knowledge_base`
      里那条教训同一个：闸门判「非零即屏蔽」，而前端开关判 `disabled === 1`，
      库里若存进 2 两边就会分叉 ——「界面显示已启用、模型却用不到」比写反还难查。
    - 工具名**不在本函数里校验**：合法名单只有注册表知道，校验放在路由层
      （`ai.py` 的 PUT 处理器），这样服务层不依赖注册表、也不会因为导入顺序踩循环依赖。
    - 归属由调用方保证（路由层只用 `current_user["user_id"]`，见 IDOR 红线）。
    """
    uid = int(user_id or 0)
    name = str(tool_name or "").strip()
    if not name:
        raise ValueError("tool_name 不能为空")
    flag = 1 if int(disabled or 0) else 0

    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(AiAgentToolPref).where(
                    AiAgentToolPref.user_id == uid,
                    AiAgentToolPref.tool_name == name,
                )
            )
        ).scalars().first()

        now = datetime.now()
        if row is None:
            db.add(
                AiAgentToolPref(
                    user_id=uid,
                    tool_name=name,
                    disabled=flag,
                    create_time=now,
                    update_time=now,
                )
            )
        else:
            row.disabled = flag
            row.update_time = now
        await db.commit()

    logger.info("[tool_pref] 已保存工具开关 user={} tool={} disabled={}", uid, name, flag)


async def set_all_tools_disabled(
    user_id: int, tool_names: List[str], disabled: int
) -> None:
    """一次改**全部**工具的开关（面板上的「全选」）。

    与 `set_tool_disabled` 同一套语义，区别只在「一批名字、一个事务」：

    - `disabled=1` → 把 `tool_names` 里每个名字 upsert 成 1。
    - `disabled=0` → **删除**该用户在这些名字上的行。存储是稀疏的（没有行 = 启用，
      见模块开头），所以「全部启用」的正解就是把它还原成稀疏，而不是写一堆 0 留着。
      ⚠️ **只删 `user_id` 本人的、且名字在 `tool_names` 里的行**：不在注册表里的
      遗留行不是这次请求的对象，顺手删它们等于改了用户没要求改的数据。

    ⚠️ **一个事务**：要么全生效要么全不生效。半开半关（写进去 6 个、报错 4 个）
    比整个失败难查得多 —— 用户看到的是「面板一半开着」，却没有任何报错。

    与读侧不同：**写失败必须抛出去**让路由如实回错，不许静默。
    归属由调用方保证（路由层只用 `current_user["user_id"]`，见 IDOR 红线）。
    """
    uid = int(user_id or 0)
    names = [str(n or "").strip() for n in (tool_names or [])]
    names = [n for n in names if n]
    if not names:
        return
    flag = 1 if int(disabled or 0) else 0

    async with async_session_factory() as db:
        if flag == 0:
            await db.execute(
                delete(AiAgentToolPref).where(
                    AiAgentToolPref.user_id == uid,
                    AiAgentToolPref.tool_name.in_(names),
                )
            )
        else:
            rows = (
                await db.execute(
                    select(AiAgentToolPref).where(
                        AiAgentToolPref.user_id == uid,
                        AiAgentToolPref.tool_name.in_(names),
                    )
                )
            ).scalars().all()
            existing = {r.tool_name: r for r in rows}
            now = datetime.now()
            for name in names:
                row = existing.get(name)
                if row is None:
                    db.add(
                        AiAgentToolPref(
                            user_id=uid,
                            tool_name=name,
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
        "[tool_pref] 已批量保存工具开关 user={} count={} disabled={}",
        uid,
        len(names),
        flag,
    )


__all__ = ["disabled_tool_names", "set_tool_disabled", "set_all_tools_disabled"]
