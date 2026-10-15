"""一次性探针：写工具的 SAVEPOINT 里调用「自己会 commit() 的服务」会发生什么？

背景：`loop._execute_tool` 对 `write_operation=True` 的工具会包一层
`async with ctx.db.begin_nested()`（SAVEPOINT），而我要复用的
`memory_service` / `rag_write_service` 内部的写函数**自己会 `commit()`**。
`loop.py` 的注释已经点出这个组合危险，但没给实测结论 —— 本探针量化两件事：

  1) 在 `begin_nested()` 里调用 `memory_service.save_memory`：
     抛不抛异常？记忆有没有真的落库？有没有 WARNING？
  2) 同一个调用放在**自己开的独立会话**里：是否干净？

判据（跑完即知该选哪种写法）：
  · 若 (1) 抛异常 → 工具会返回 `fail("工具执行异常…")`，**用户看到失败但数据已改**（最坏）；
  · 若 (1) 只刷 warning 但成功 → 仍然不该用（SAVEPOINT 是假的 + 日志噪声）。

清理：只删自己写的、带 `__probe_nested_commit__` 标记的那几条记忆（POSITION 子串，不用 LIKE）。

跑完删除本文件。
"""

import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

WARNINGS: list[str] = []
_sink_id = logger.add(lambda m: WARNINGS.append(m), level="WARNING")

MARK = "__probe_nested_commit__"


async def main() -> None:
    from sqlalchemy import text

    from app.database import async_session_factory, engine, register_all_models
    from app.services.ai import memory_service

    register_all_models()

    # 用「零记忆用户」，绝不动真实用户已有数据（同 _probe_nested_tx.py 的取法）
    async with async_session_factory() as db:
        uid = int(
            await db.scalar(
                text(
                    "SELECT u.user_id FROM sys_user u "
                    "LEFT JOIN (SELECT user_id, count(*) c FROM ai_agent_memory GROUP BY user_id) m "
                    "  ON u.user_id = m.user_id "
                    "WHERE COALESCE(m.c, 0) = 0 ORDER BY u.user_id LIMIT 1"
                )
            )
            or 0
        )
    print(f"测试用户 uid={uid}（零记忆用户）")
    if not uid:
        print("没有零记忆用户，放弃")
        return

    async def count() -> int:
        async with async_session_factory() as db:
            return int(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM ai_agent_memory WHERE user_id = :u "
                        "AND POSITION(:p IN content) > 0"
                    ),
                    {"u": uid, "p": MARK},
                )
                or 0
            )

    async def cleanup() -> None:
        async with async_session_factory() as db:
            await db.execute(
                text(
                    "DELETE FROM ai_agent_memory WHERE user_id = :u "
                    "AND POSITION(:p IN content) > 0"
                ),
                {"u": uid, "p": MARK},
            )
            await db.commit()

    await cleanup()
    print(f"跑之前带标记的记忆 = {await count()} 条\n")

    # ---------- 1) SAVEPOINT 里调 commit() 服务 ----------
    WARNINGS.clear()
    raised: str = ""
    async with async_session_factory() as db:
        try:
            async with db.begin_nested():
                await memory_service.save_memory(
                    db, uid, f"{MARK} 在 SAVEPOINT 里写的", importance=7
                )
        except Exception as e:  # noqa: BLE001
            raised = f"{type(e).__name__}: {e}"
    print("=== 1) begin_nested() 内调用 save_memory ===")
    print(f"  抛异常      : {raised or '（无）'}")
    print(f"  落库条数    : {await count()}")
    print(f"  期间 WARNING: {len(WARNINGS)} 条")
    for w in WARNINGS[:4]:
        print("    " + str(w).strip().splitlines()[0][:170])
    if raised:
        print("  --- traceback ---")
        print("  " + "\n  ".join(traceback.format_exc().splitlines()[-6:]))

    # ---------- 2) 自己开的独立会话 ----------
    WARNINGS.clear()
    await cleanup()
    raised2 = ""
    try:
        async with async_session_factory() as own:
            await memory_service.save_memory(
                own, uid, f"{MARK} 在独立会话里写的", importance=7
            )
    except Exception as e:  # noqa: BLE001
        raised2 = f"{type(e).__name__}: {e}"
    print("\n=== 2) 独立会话（不套 SAVEPOINT）===")
    print(f"  抛异常      : {raised2 or '（无）'}")
    print(f"  落库条数    : {await count()}")
    print(f"  期间 WARNING: {len(WARNINGS)} 条")
    for w in WARNINGS[:4]:
        print("    " + str(w).strip().splitlines()[0][:170])

    # ---------- 3) 空 SAVEPOINT（写工具用独立会话时，外层仍会包一层） ----------
    WARNINGS.clear()
    raised3 = ""
    try:
        async with async_session_factory() as db:
            async with db.begin_nested():
                pass  # 工具本体不在这个会话里做任何事
    except Exception as e:  # noqa: BLE001
        raised3 = f"{type(e).__name__}: {e}"
    print("\n=== 3) 空 SAVEPOINT（工具改用独立会话后，外层那层仍在）===")
    print(f"  抛异常      : {raised3 or '（无）'}")
    print(f"  期间 WARNING: {len(WARNINGS)} 条")

    await cleanup()
    print(f"\n清理后带标记的记忆 = {await count()} 条（应为 0）")
    logger.remove(_sink_id)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
