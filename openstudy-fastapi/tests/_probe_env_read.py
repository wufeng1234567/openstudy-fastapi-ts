"""只读探针：看看库里有谁、有哪些可用的测试素材（不写任何数据）

用来给 `_probe_agent_tools.py` 挑「受害者用户」（越权自测）与素材，
也用来确认 probe 用户与受害者用户是分开的两个人。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402


async def main() -> None:
    from app.database import async_session_factory, engine, register_all_models

    register_all_models()
    async with async_session_factory() as db:
        print("== 数据库 ==")
        print(await db.scalar(text("SELECT current_database()")))

        print("\n== sys_user（前 12 个）==")
        rows = (
            await db.execute(
                text(
                    "SELECT user_id, user_name, nick_name, "
                    "(SELECT count(*) FROM ai_agent_memory m WHERE m.user_id = u.user_id) mem, "
                    "(SELECT count(*) FROM user_question_error e WHERE e.user_id = u.user_id) err, "
                    "(SELECT count(*) FROM user_question_favorite f WHERE f.user_id = u.user_id) fav, "
                    "(SELECT count(*) FROM user_question_marked k WHERE k.user_id = u.user_id) mk, "
                    "(SELECT count(*) FROM question_bank b WHERE b.user_id = u.user_id) banks, "
                    "(SELECT count(*) FROM rag_knowledge_base k WHERE k.user_id = u.user_id AND k.del_flag='0') kbs "
                    "FROM sys_user u ORDER BY user_id LIMIT 12"
                )
            )
        ).all()
        for r in rows:
            print(
                f"  uid={r[0]:<6} name={r[1]!s:<16} nick={r[2]!s:<12} "
                f"mem={r[3]} err={r[4]} fav={r[5]} mk={r[6]} banks={r[7]} kbs={r[8]}"
            )

        print("\n== 带 __probe / __e2e 标记的残留 ==")
        print(
            "  question_bank:",
            await db.scalar(
                text(
                    "SELECT count(*) FROM question_bank WHERE POSITION('__probe' IN bank_name) > 0 "
                    "OR POSITION('__e2e' IN bank_name) > 0"
                )
            ),
        )
        print(
            "  rag_knowledge_base:",
            await db.scalar(
                text(
                    "SELECT count(*) FROM rag_knowledge_base WHERE POSITION('__probe' IN name) > 0 "
                    "OR POSITION('__e2e' IN name) > 0"
                )
            ),
        )
        print(
            "  ai_agent_memory:",
            await db.scalar(
                text(
                    "SELECT count(*) FROM ai_agent_memory WHERE POSITION('__probe' IN content) > 0 "
                    "OR POSITION('__e2e' IN content) > 0"
                )
            ),
        )

        print("\n== question_bank.allow_fork 分布 ==")
        for r in (
            await db.execute(
                text("SELECT allow_fork, is_public, count(*) FROM question_bank GROUP BY 1,2 ORDER BY 1,2")
            )
        ).all():
            print(f"  allow_fork={r[0]} is_public={r[1]} count={r[2]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
