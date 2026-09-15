# -*- coding: utf-8 -*-
"""一次性清理历次 E2E 测试残留（先备份后删除，只动测试数据）"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text  # noqa: E402
from app.database import async_session_factory  # noqa: E402

BK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cleanup_backup_20260912.json")

NAME_LIKE = "(title LIKE 'E2EL%' OR title LIKE 'E2E%' OR title LIKE 'DBG%')"


async def m():
    async with async_session_factory() as db:
        q = lambda s, p=None: db.execute(text(s), p or {})  # noqa: E731

        note_ids = [r[0] for r in (await q(f"SELECT note_id FROM note WHERE {NAME_LIKE}")).all()]
        cat_ids = [r[0] for r in (await q(
            "SELECT id FROM note_category WHERE name LIKE 'E2EL%' OR name LIKE 'E2E%' OR name LIKE 'DBG%'")).all()]
        bank_ids = [r[0] for r in (await q(
            "SELECT id FROM question_bank WHERE bank_name LIKE 'E2EL%' OR bank_name LIKE 'E2E%' OR bank_name LIKE 'DBG%'")).all()]
        q_ids = []
        if bank_ids:
            q_ids = [r[0] for r in (await q(
                "SELECT id FROM question_main WHERE bank_id IN :b", {"b": tuple(bank_ids)})).all()]

        # ---------- 1) 备份 ----------
        backup = {}
        jobs = [
            ("notes", "SELECT * FROM note WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)}),
            ("note_category", "SELECT * FROM note_category WHERE id IN :i", {"i": tuple(cat_ids) or (0,)}),
            ("note_comment", "SELECT * FROM note_comment WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)}),
            ("user_note_favorite",
             "SELECT * FROM user_note_favorite WHERE note_id IN :i OR note_id NOT IN (SELECT note_id FROM note)",
             {"i": tuple(note_ids) or (0,)}),
            ("note_question", "SELECT * FROM note_question WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)}),
            ("note_question_bank", "SELECT * FROM note_question_bank WHERE note_id IN :i",
             {"i": tuple(note_ids) or (0,)}),
            ("sys_notice", "SELECT * FROM sys_notice WHERE remark LIKE '%noteId%'", {}),
            ("question_bank", "SELECT * FROM question_bank WHERE id IN :i", {"i": tuple(bank_ids) or (0,)}),
            ("question_main", "SELECT * FROM question_main WHERE bank_id IN :b", {"b": tuple(bank_ids) or (0,)}),
            ("user_practice_log",
             "SELECT * FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)", {}),
        ]
        for name, sql, params in jobs:
            rows = (await q(sql, params)).all()
            backup[name] = [dict(r._mapping) for r in rows]
            print("备份", name, len(rows), "行")
        with open(BK, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=1, default=str)
        print("备份已写:", BK)

        # ---------- 2) 删除（顺序：从被依赖方到依赖方） ----------
        n1 = (await q("""DELETE FROM sys_notice WHERE remark LIKE '%noteId%'
                AND (remark LIKE '%\"noteId\": 82,%' OR remark LIKE '%\"noteId\": 83,%'
                     OR remark LIKE '%\"noteId\": 84,%' OR remark LIKE '%\"noteId\": 85,%'
                     OR remark LIKE '%\"noteId\": 86,%')""")).rowcount
        n2 = (await q("DELETE FROM note_comment WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)})).rowcount
        n3 = (await q("""DELETE FROM user_note_favorite WHERE note_id IN :i
                OR note_id NOT IN (SELECT note_id FROM note)""", {"i": tuple(note_ids) or (0,)})).rowcount
        n4 = (await q("DELETE FROM note_question WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)})).rowcount
        n5 = (await q("DELETE FROM note_question_bank WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)})).rowcount
        n6 = (await q("DELETE FROM note WHERE note_id IN :i", {"i": tuple(note_ids) or (0,)})).rowcount
        print("删除 通知/评论/收藏/题关联/库关联/笔记:", n1, n2, n3, n4, n5, n6)

        if q_ids:
            await q("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM user_question_error WHERE question_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM note_question WHERE question_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM question_sub WHERE main_id IN :i", {"i": tuple(q_ids)})
            await q("DELETE FROM question_main WHERE id IN :i", {"i": tuple(q_ids)})
        if bank_ids:
            await q("DELETE FROM question_bank WHERE id IN :i", {"i": tuple(bank_ids)})
        if cat_ids:
            await q("DELETE FROM note_category WHERE id IN :i", {"i": tuple(cat_ids)})
        print("删除测试题库/题目/分类: bank", bank_ids, "question", q_ids, "cat", cat_ids)

        n8 = (await q(
            "DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")).rowcount
        print("删除孤儿答题流水:", n8)

        await db.commit()
        print("--- 已提交 ---")

        # ---------- 3) 复核 ----------
        checks = [
            ("E2E/DBG 命名笔记", f"SELECT COUNT(*) FROM note WHERE {NAME_LIKE}"),
            ("E2E/DBG 命名题库", "SELECT COUNT(*) FROM question_bank WHERE bank_name LIKE 'E2EL%' OR bank_name LIKE 'E2E%' OR bank_name LIKE 'DBG%'"),
            ("指向已删笔记的评论", "SELECT COUNT(*) FROM note_comment c LEFT JOIN note n ON n.note_id=c.note_id WHERE n.note_id IS NULL OR n.del_flag<>'0'"),
            ("孤儿笔记收藏", "SELECT COUNT(*) FROM user_note_favorite f LEFT JOIN note n ON n.note_id=f.note_id WHERE n.note_id IS NULL"),
            ("孤儿答题流水", "SELECT COUNT(*) FROM user_practice_log l LEFT JOIN question_main q ON q.id=l.question_id WHERE q.id IS NULL"),
            ("消息中心 noteId 通知", "SELECT COUNT(*) FROM sys_notice WHERE remark LIKE '%noteId%'"),
        ]
        for label, sql in checks:
            print("复核", label, "=", (await q(sql)).scalar())


asyncio.run(m())
