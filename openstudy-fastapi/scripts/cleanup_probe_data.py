#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理探针/测试产生的数据

为什么需要这个脚本
==================
每次跑 UI 探针 / Agent 端到端验证，都会在**真实数据库**里留下痕迹：
自动创建的题库（"回退按钮验证-xxxx"）、点选项产生的错题、练习记录……

对我（agent）来说那是测试垃圾，对用户来说那是"我的题库怎么多了一堆没见过的"。
用户在 2026-10-20 明确要求：「每次修完bug 这种测试数据记得删除掉 不然我不好清理」。

用法
====
    # 1) 先看有什么（默认行为，不删任何东西）
    python cleanup_probe_data.py

    # 2) 预览将被删除的内容
    python cleanup_probe_data.py --dry-run

    # 3) 真删（需要显式给 --yes）
    python cleanup_probe_data.py --yes

    # 4) 指定日期（默认今天）
    python cleanup_probe_data.py --since 2026-10-20 --yes

识别规则（**保守优先**）
========================
题库：名字命中 PATTERN 才处理 —— 这些是探针常用的命名习惯
      ``验证`` / ``回退`` / ``probe`` / ``API回退`` / ``UI验证``
      ⚠️ **不会**动「测试2」「java期末测试」这类用户自己建的题库
      （用户确实在用它们做功能测试，删掉是灾难）。

练习记录/错题：只清理**上面识别出的题库**里的行，或 `--bank-ids` 显式指定。
      不按时间盲删 —— 用户白天自己也可能在做题。

安全边界
========
· 默认 dry-run（只打印）；真删必须 `--yes`
· 题库若有**非探针命名**的，一律跳过并列出来，让用户自己判断
· 删除前打印每一行，删完再复核一次计数
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from datetime import date

try:
    import asyncpg
except ImportError:
    print("需要 asyncpg：openstudy-fastapi/.venv/Scripts/python.exe 里已安装")
    raise

# Windows 控制台默认 GBK，打印中文/符号会 UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DB = dict(host="127.0.0.1", port=5432, user="root", password="123456",
          database="openstudy_v2_pgsql")

# 探针题库的命名特征。**只匹配这些**，避免误伤用户自建的「测试2」等。
PATTERN = r"验证|回退|probe|Probe|交互测试|删库测试"


async def fetch_probe_banks(conn, since: date):
    """
    ⚠️ `since` 必须是 `datetime.date` 对象，不能传字符串：
    asyncpg 把参数交给 `$2::date` 时会走 date 编码器，
    传 `'2026-10-20'` 会抛
        DataError: invalid input for query argument $2: ... ('str' object has no attribute 'toordinal')
    """
    return await conn.fetch(
        """
        SELECT id, bank_name, user_id, create_time,
               (SELECT count(*) FROM question_main q WHERE q.bank_id = b.id) AS qn
        FROM question_bank b
        WHERE bank_name ~ $1 AND create_time >= $2
        ORDER BY id
        """,
        PATTERN, since,
    )


async def report(conn, since: date, bank_ids: list[int]):
    print(f"\n{'=' * 66}")
    print(f"探针数据检查（create_time >= {since}）")
    print("=" * 66)

    banks = await fetch_probe_banks(conn, since)
    print(f"\n[题库] 命中探针命名规则的有 {len(banks)} 个：")
    for r in banks:
        print(f"  id={r['id']:5d} owner={r['user_id']:4d} qn={r['qn']:3d} "
              f"{r['create_time']:%m-%d %H:%M}  {r['bank_name']}")
    if not banks:
        print("  （无）")

    ids = bank_ids or [r["id"] for r in banks]

    # 说明哪些题库被跳过，避免用户以为"都清了"
    all_today = await conn.fetch(
        "SELECT id, bank_name FROM question_bank WHERE create_time >= $1 "
        "AND NOT (bank_name ~ $2) ORDER BY id",
        since, PATTERN,
    )
    if all_today:
        print(f"\n[跳过] 当天创建但**不属于探针命名**的题库（不动）：")
        for r in all_today:
            print(f"  id={r['id']:5d}  {r['bank_name']}")

    if not ids:
        print("\n没有可清理的题库，也没有指定 --bank-ids。")
        return

    print(f"\n[待清理] 目标 bank_ids = {ids}")
    for label, sql in [
        ("question_sub", "DELETE FROM question_sub WHERE main_id IN "
                         "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
        ("question_main", "DELETE FROM question_main WHERE bank_id = ANY($1)"),
        ("user_question_error", "DELETE FROM user_question_error WHERE bank_id = ANY($1)"),
        ("user_question_favorite", "DELETE FROM user_question_favorite WHERE question_id IN "
                                   "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
        ("user_question_marked", "DELETE FROM user_question_marked WHERE question_id IN "
                                 "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
        ("user_bank_favorite", "DELETE FROM user_bank_favorite WHERE bank_id = ANY($1)"),
        ("user_practice_log", "DELETE FROM user_practice_log WHERE bank_id = ANY($1)"),
        ("question_bank", "DELETE FROM question_bank WHERE id = ANY($1)"),
    ]:
        try:
            n = await conn.fetchval(
                sql.replace("DELETE FROM", "SELECT count(*) FROM").split(" WHERE")[0]
                + " WHERE" + sql.split(" WHERE", 1)[1],
                ids,
            )
            print(f"  {label:24s} {n} 行")
        except Exception as e:  # 表可能不存在
            print(f"  {label:24s} skip ({str(e)[:40]})")


async def do_cleanup(conn, ids: list[int]):
    async with conn.transaction():
        # 顺序很重要：先子表后主表
        statements = [
            ("question_sub", "DELETE FROM question_sub WHERE main_id IN "
                             "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
            ("user_question_error", "DELETE FROM user_question_error WHERE bank_id = ANY($1)"),
            ("user_question_favorite", "DELETE FROM user_question_favorite WHERE question_id IN "
                                       "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
            ("user_question_marked", "DELETE FROM user_question_marked WHERE question_id IN "
                                     "(SELECT id FROM question_main WHERE bank_id = ANY($1))"),
            ("user_bank_favorite", "DELETE FROM user_bank_favorite WHERE bank_id = ANY($1)"),
            ("user_practice_log", "DELETE FROM user_practice_log WHERE bank_id = ANY($1)"),
            ("question_main", "DELETE FROM question_main WHERE bank_id = ANY($1)"),
            ("question_bank", "DELETE FROM question_bank WHERE id = ANY($1)"),
        ]
        for label, sql in statements:
            try:
                r = await conn.execute(sql, ids)
                print(f"  {label:24s} {r}")
            except Exception as e:
                print(f"  {label:24s} skip ({str(e)[:50]})")


async def main():
    ap = argparse.ArgumentParser(description="清理探针/测试产生的数据")
    ap.add_argument("--since", default=date.today(), type=date.fromisoformat,
                    help="只处理该日期之后创建的数据（默认今天），格式 YYYY-MM-DD")
    ap.add_argument("--bank-ids", default="", help="显式指定题库 id，逗号分隔")
    ap.add_argument("--dry-run", action="store_true", help="只看不删（默认行为）")
    ap.add_argument("--yes", action="store_true", help="真的删除（必须显式给）")
    args = ap.parse_args()

    bank_ids = [int(x) for x in args.bank_ids.split(",") if x.strip().isdigit()]
    conn = await asyncpg.connect(**DB)
    try:
        await report(conn, args.since, bank_ids)

        if not args.yes:
            print("\n（当前是预览模式，没有删除任何数据。加 --yes 才会真删。）")
            return

        ids = bank_ids or [r["id"] for r in await fetch_probe_banks(conn, args.since)]
        if not ids:
            print("\n没有要删的。")
            return
        print(f"\n开始删除 bank_ids={ids} ...")
        await do_cleanup(conn, ids)

        print("\n=== 复核 ===")
        print("  目标题库剩余:",
              await conn.fetchval("SELECT count(*) FROM question_bank WHERE id = ANY($1)", ids))
        print("  目标题目剩余:",
              await conn.fetchval("SELECT count(*) FROM question_main WHERE bank_id = ANY($1)", ids))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
