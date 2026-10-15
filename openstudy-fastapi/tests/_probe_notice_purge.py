# -*- coding: utf-8 -*-
"""探针：前台「清空全部 / 删除」通知 —— 两类通知两种处理（用户 2026-10-12）

背景：用户担心「乱删」——通知有两类，删除语义必须不同：
  A) **用户通知**（评论/回复/@，remark.toUserId 指向唯一接收者）→ 可**真删 sys_notice 行**；
  B) **系统公告**（管理员群发，无 toUserId，全体共用一行）→ **绝不能删行**（会连同所有人
     的列表、管理员后台一起抹掉），只能**按用户隐藏**（sys_notice_delete）。

本探针用内存 SQLite（aiosqlite）建真表、插真数据，直接调用 `_delete_notices_for_user`，断言：
  1. 用户通知被真正删除（行没了）；其 sys_notice_read 一并清理；
  2. 系统公告 **行仍在**（未被删），但当前用户被记入 sys_notice_delete（=对其隐藏）；
  3. 发给**别人**的通知不被动（越权保护）；
  4. `get_deleted_notice_ids` 能读回隐藏集合，供 listAll 过滤。

用法：.venv/Scripts/python.exe tests/_probe_notice_purge.py   # 全部退出 0
"""
import os
import sys
import asyncio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "ok": bool(cond), "actual": actual})


def _seed_sqlite(sync_conn):
    """建真表（本探针用到的三张）并插夹具数据"""
    from app.models.notice import SysNotice, SysNoticeRead, SysNoticeDelete

    SysNotice.__table__.create(sync_conn, checkfirst=True)
    SysNoticeRead.__table__.create(sync_conn, checkfirst=True)
    SysNoticeDelete.__table__.create(sync_conn, checkfirst=True)
    # ⚠️ SQLite 不把 BigInteger 主键当自增（PG 会）。本探针在 SQLite 上跑，
    #    需把三张表的 id/notice_id 列改成 INTEGER 才能自动赋值（仅探针环境，不影响 PG 生产库）。
    from sqlalchemy import text
    sync_conn.execute(text("DROP TABLE sys_notice_delete"))
    sync_conn.execute(text(
        "CREATE TABLE sys_notice_delete ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id BIGINT NOT NULL, notice_id BIGINT NOT NULL, "
        "delete_time DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "CONSTRAINT uk_user_notice_delete UNIQUE (user_id, notice_id))"
    ))
    import json
    from datetime import datetime

    def remark(**kw):
        return json.dumps(kw, ensure_ascii=False)

    rows = [
        # id, remark
        (1, remark(type="comment", fromUserId=200, toUserId=100, noteId=9, commentId=1)),  # 发给我的评论
        (2, remark(type="reply", fromUserId=201, toUserId=100, noteId=9, commentId=2)),    # 发给我的回复
        (3, remark(type="mention", fromUserId=202, toUserId=100, noteId=9)),               # @我
        (4, remark(type="comment", fromUserId=200, toUserId=999, noteId=9)),               # 发给别人
        (5, None),                                                                          # 系统公告（无 remark）
        (6, remark(type="notice")),                                                         # 系统公告（非用户类型）
    ]
    for nid, rk in rows:
        sync_conn.execute(
            SysNotice.__table__.insert().values(
                notice_id=nid, notice_title=f"n{nid}", notice_type="1",
                notice_content="c", status="0", create_by="system",
                create_time=datetime.now(), remark=rk,
            )
        )
    sync_conn.execute(SysNoticeRead.__table__.insert().values(id=1, user_id=100, notice_id=2))
    sync_conn.execute(SysNoticeRead.__table__.insert().values(id=2, user_id=999, notice_id=4))


async def run_probe() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.database import register_all_models
    from app.models.notice import SysNotice, SysNoticeRead, SysNoticeDelete
    from app.api.v1.notices import _delete_notices_for_user, get_deleted_notice_ids

    # SysUser 有到 SysRole 的 relationship，需先注册全部模型，否则 mapper 初始化会报
    register_all_models()

    try:
        import aiosqlite  # noqa: F401
        has_aiosqlite = True
    except ImportError:
        has_aiosqlite = False

    if not has_aiosqlite:
        check("B0", "aiosqlite 未安装（无法端到端；请 pip install aiosqlite）", False)
    else:
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "_probe_notice_purge.sqlite")
        if os.path.exists(db_file):
            os.remove(db_file)
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        async with engine.begin() as conn:
            await conn.run_sync(_seed_sqlite)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        # 用户 100「清空全部」：传 1..6 全部 id
        async with Session() as db:
            counts = await _delete_notices_for_user(db, 100, [1, 2, 3, 4, 5, 6])
            await db.commit()

        async with Session() as db:
            left = [r[0] for r in (await db.execute(
                select(SysNotice.notice_id).order_by(SysNotice.notice_id))).all()]
            reads = [r[0] for r in (await db.execute(
                select(SysNoticeRead.notice_id).order_by(SysNoticeRead.notice_id))).all()]
            hides = sorted(await get_deleted_notice_ids(db, 100))
        # 另一个用户 999 不受影响：系统公告仍可见（不在其删除集合里）
        async with Session() as db:
            other_hides = await get_deleted_notice_ids(db, 999)

        await engine.dispose()
        try:
            os.remove(db_file)
        except OSError:
            pass

        # 1) 用户通知(1,2,3) 真删；2) 系统公告(5,6) 行仍在；别人(4) 不动
        check("B1", "用户通知真删 3 条", counts["purged"] == 3, f"purged={counts['purged']}")
        check("B2", "系统公告隐藏 2 条", counts["hidden"] == 2, f"hidden={counts['hidden']}")
        check("B3", "sys_notice 残留=系统公告(5,6)+别人的(4)", left == [4, 5, 6], str(left))
        check("B4", "系统公告行**未被删**（5,6 仍在）", 5 in left and 6 in left, str(left))
        check("B5", "已读记录清理(仅剩别人的4)", reads == [4], str(reads))
        check("B6", "隐藏集合=我这边的系统公告(5,6)", hides == [5, 6], str(hides))
        check("B7", "其它用户不受影响（999 无隐藏记录）", other_hides == set(), str(other_hides))

    # C) 静态核对：批量删端点调用了 _delete_notices_for_user（而非旧 mark_notices_read）
    src = open(os.path.join(ROOT, "app", "api", "v1", "notices.py"), encoding="utf-8").read()
    seg = src.split('@router.delete("/front/batch/{notice_ids}")', 1)[-1]
    check("C1", "/front/batch 使用 _delete_notices_for_user", "_delete_notices_for_user" in seg)
    check("C2", "/front/batch 不再调 mark_notices_read", "mark_notices_read" not in seg)

    ok = all(r["ok"] for r in ROWS)
    for r in ROWS:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['cid']} {r['title']}   {r['actual']}")
    print("结论:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main():
    sys.exit(asyncio.run(run_probe()))


if __name__ == "__main__":
    main()
