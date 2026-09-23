"""一次性复现：`begin_nested()` 里再 `commit()` 会怎样。

背景：`_execute_tool` 用 `async with ctx.db.begin_nested()` 包写工具，
`memory_hook.record_tool_memory` 又用 `async with db.begin_nested()` 包 `save_memory`；
而各写服务（`create_knowledge_base` / `create_document` / `save_memory`…）内部**自己会 `commit()`**。

问题：在 SAVEPOINT 里 `commit()` 会把**整个事务**提交掉，退出 `async with` 时
那个嵌套事务已经失效 → `Can't operate on closed transaction inside context manager`。

本脚本量化两件事：
  1) `_execute_tool` 走写工具时到底有没有报错、返回的 success 是什么
  2) `record_tool_memory` 有没有报错、记忆最后有没有真的落库

跑完删掉。
"""

import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

# 把 warning 抓出来，别被日志刷掉
WARNINGS: list[str] = []
_sink_id = logger.add(lambda m: WARNINGS.append(m), level="WARNING")


async def main() -> None:
    from sqlalchemy import text

    from app.database import async_session_factory, engine, register_all_models
    from app.services.ai.agent import memory_hook
    from app.services.ai.agent.base import ToolContext
    from app.services.ai.agent.loop import _execute_tool
    from app.services.ai.agent.registry import ensure_tools_loaded, registry

    register_all_models()
    ensure_tools_loaded()

    # 用零记忆用户，跑完清干净（绝不动真实用户）
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
    print(f"测试用户 uid={uid}")
    if not uid:
        print("没有零记忆用户，放弃")
        return

    name = "__p6_hook_probe__"

    async def memory_count() -> int:
        async with async_session_factory() as db:
            return int(
                await db.scalar(
                    text("SELECT count(*) FROM ai_agent_memory WHERE user_id = :u"), {"u": uid}
                )
                or 0
            )

    async def cleanup() -> None:
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM ai_agent_memory WHERE user_id = :u AND POSITION(:p IN content) > 0"),
                {"u": uid, "p": name},
            )
            await db.commit()
        # 题库是物理删；按名字前缀精确匹配（不用 LIKE，`_` 是通配符）
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM question_bank WHERE user_id = :u AND LEFT(bank_name, :n) = :p"),
                {"u": uid, "n": len(name), "p": name},
            )
            await db.commit()

    await cleanup()
    before = await memory_count()
    print(f"跑之前：该用户记忆 {before} 条\n")

    tool = registry.get("bank_manage")
    ctx = ToolContext(db=None, user_id=uid)

    # ---------- 1) 走真实的 _execute_tool（含它那层 begin_nested）----------
    WARNINGS.clear()
    async with async_session_factory() as db:
        ctx.db = db
        result = await _execute_tool(
            tool, {"action": "create", "bank_name": f"{name}甲"}, ctx
        )
        print("=== 1) _execute_tool 返回 ===")
        print(f"  success = {result.get('success')!r}")
        print(f"  message = {result.get('message')!r}")
        print(f"  error   = {result.get('error')!r}")
    after_exec = await memory_count()
    print(f"  记忆条数：{before} → {after_exec}")
    print(f"  期间 WARNING {len(WARNINGS)} 条：")
    for w in WARNINGS:
        print("    " + str(w).strip().splitlines()[0][:160])

    # ---------- 2) 直接调 record_tool_memory（含它那层 begin_nested）----------
    WARNINGS.clear()
    fake_result = {"success": True, "message": f"题库「{name}乙」创建成功（ID=999）"}
    fake_params = {"action": "create", "bank_name": f"{name}乙"}
    before_mem = await memory_count()
    try:
        await memory_hook.record_tool_memory(uid, tool, fake_params, fake_result)
        print("\n=== 2) record_tool_memory 未抛异常 ===")
    except Exception:
        print("\n=== 2) record_tool_memory 抛了异常 ===")
        traceback.print_exc()
    after_mem = await memory_count()
    print(f"  记忆条数：{before_mem} → {after_mem}")
    print(f"  期间 WARNING {len(WARNINGS)} 条：")
    for w in WARNINGS:
        print("    " + str(w).strip().splitlines()[0][:200])

    await cleanup()
    final = await memory_count()
    print(f"\n清理后记忆条数 = {final}（应为 {before}）")
    logger.remove(_sink_id)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
