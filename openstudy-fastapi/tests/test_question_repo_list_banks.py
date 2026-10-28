"""聚焦只读测试：QuestionBankRepository.list_banks 的 status 过滤条件

背景（2026-10-28 审核发现 #1）：原实现先硬编码 `status == '0'`，再叠加显式
`status`，两个 where 为 AND → 显式传非 '0' 时恒空。

本测试**只读**，不写库、不提交、不服务。分两层证明：
  A. 条件层（不依赖数据）：用一个只捕获传入 statement、不真正执行的会话，
     把真实 `list_banks` 生成的 SQL 编译成字符串，断言 WHERE 条件——
       · 默认（未传 status）→ 含 `status = '0'`，且只有这一个 status 条件；
       · 显式 '0'          → 只含 `status = '0'` 一次（不与硬编码再叠一次）；
       · 显式 '2'          → 含 `status = '2'`，且**不含** `status = '0'`（不再互斥）。
  B. 真实库层（只读）：对真实数据库跑这三种调用，断言不抛异常。
     库中若无「非 '0' 状态」的数据，**不编造非空断言**，只验证 SQL 可执行、不报错。

运行：
    ./.venv/Scripts/python.exe tests/test_question_repo_list_banks.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects import postgresql

from app.repositories.question_repo import QuestionBankRepository


class _CapturingSession:
    """只记录传进来的 SQLAlchemy statement，不真正执行（用于编译出 SQL 断言条件）。"""

    def __init__(self) -> None:
        self.scalar_stmts = []   # list_banks 里 count 走 scalar(subquery)
        self.execute_stmts = []  # 列表查询走 execute(query)

    async def scalar(self, stmt):
        self.scalar_stmts.append(stmt)
        return 0  # 不关心总数，只拿 SQL

    async def execute(self, stmt):
        self.execute_stmts.append(stmt)
        # 返回空结果集（标量列表为空），不访问真实库
        class _Res:
            def scalars(self):
                return self

            def all(self):
                return []

        return _Res()


def _compile_where(captured_session: _CapturingSession) -> str:
    """把捕获到的列表查询（execute 的 stmt）编译成 SQL 字符串（PG 方言）。"""
    assert captured_session.execute_stmts, "list_banks 未对 execute 传入查询"
    stmt = captured_session.execute_stmts[-1]
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    # 去掉 SELECT/FROM/ORDER/LIMIT 等噪声，只围绕 WHERE 做断言
    return str(compiled)


async def _collect_sql(**kwargs) -> str:
    cap = _CapturingSession()
    repo = QuestionBankRepository(cap)  # type: ignore[arg-type]
    await repo.list_banks(**kwargs)
    return _compile_where(cap)


async def test_default_filters_status_zero() -> None:
    sql = await _collect_sql()  # status 未传
    assert "question_bank.status = '0'" in sql, sql
    # 默认情形不应出现第二个 status 条件（即只有一次 status 比较）
    assert sql.count("question_bank.status =") == 1, f"默认应只有一个 status 条件：\n{sql}"


async def test_explicit_zero_single_condition() -> None:
    sql = await _collect_sql(status="0")
    assert "question_bank.status = '0'" in sql, sql
    # 不与硬编码再叠一次（否则会变成 status='0' AND status='0' 以外的双条件）
    assert sql.count("question_bank.status =") == 1, f"显式 '0' 不应叠加两次：\n{sql}"


async def test_explicit_nonzero_no_and_with_zero() -> None:
    sql = await _collect_sql(status="2")
    assert "question_bank.status = '2'" in sql, sql
    # 核心回归：显式非 '0' 绝不能再夹带 status='0'（否则 AND 互斥恒空）
    assert "question_bank.status = '0'" not in sql, f"显式 '2' 仍夹带 status='0'：\n{sql}"
    assert sql.count("question_bank.status =") == 1, f"显式 '2' 应只有一个 status 条件：\n{sql}"


async def test_real_db_calls_do_not_error() -> None:
    """真实库只读：三种调用都能执行、不抛异常。

    ⚠️ 不编造非空断言：库中当前可能只有 status='0' 的数据。
       显式 '2' 允许返回 0 行，仅要求「不报错」。
    """
    from app.database import async_session_factory

    async with async_session_factory() as db:
        repo = QuestionBankRepository(db)
        # 只读：不 commit（session 上下文退出即回滚/关闭，不会写库）
        total_default, rows_default = await repo.list_banks(page_size=1)
        total_zero, rows_zero = await repo.list_banks(status="0", page_size=1)
        total_two, rows_two = await repo.list_banks(status="2", page_size=1)
        assert total_default >= 0 and total_zero >= 0 and total_two >= 0
        # 默认与显式 '0' 语义一致：条件相同 → 计数应一致（真实库只读，不假设具体值）
        assert total_default == total_zero, (
            f"默认({total_default}) 与显式 '0'({total_zero}) 条件应等价"
        )
        # 显式非 '0' 允许为空，只要求不报错
        assert isinstance(rows_two, list)
        print(
            f"      [real-db] total_default={total_default}, total_zero={total_zero}, "
            f"total_status2={total_two}"
        )


async def _main() -> int:
    cases = [
        ("A1 默认只查 '0'", test_default_filters_status_zero),
        ("A2 显式 '0' 单条件", test_explicit_zero_single_condition),
        ("A3 显式 '2' 不再互斥", test_explicit_nonzero_no_and_with_zero),
        ("B1 真实库只读不报错", test_real_db_calls_do_not_error),
    ]
    passed = 0
    failed = 0
    for name, case in cases:
        try:
            await case()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}\n        {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}\n        {type(e).__name__}: {e}")
            failed += 1
    print(f"\n合计：{passed} passed, {failed} failed, {passed + failed} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
