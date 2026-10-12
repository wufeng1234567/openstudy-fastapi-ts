# -*- coding: utf-8 -*-
"""探针：前台「清空全部 / 删除」用户通知 —— 必须真正删行，而非只标已读（用户 2026-10-12）

复现用户报的 bug：在「回复与@」页点「清空全部」，界面瞬时清空，但**刷新后评论又都回来了**。
根因：notices.py 的 `/front/batch/{ids}` 与 `/front/{id}` 此前调 `mark_notices_read`（只往
`sys_notice_read` 插已读记录），**从不删 `sys_notice` 行** → 刷新 `/listAll` 又拉回来。

本探针用内存 SQLite 建真表、插真数据，直接调用 `_purge_user_notices`，断言：
  1. 发给「我」的用户通知（comment/reply/mention）被**真正删除**（行没了，不只是标已读）；
  2. 发给**别人**的用户通知**不被动**（越权保护）；
  3. 系统公告（非用户通知类型）**不被动**（不能被单个用户清掉全局公告）；
  4. 被删通知对应的 `sys_notice_read` 记录一并清理（不留悬挂）。

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
    """建真表（只建本探针用到的两张）并插夹具数据"""
    from app.models.notice import SysNotice, SysNoticeRead

    SysNotice.__table__.create(sync_conn, checkfirst=True)
    SysNoticeRead.__table__.create(sync_conn, checkfirst=True)
    import json
    from datetime import datetime

    def remark(**kw):
        return json.dumps(kw, ensure_ascii=False)

    rows = [
        # id, type, remark
        (1, "1", remark(type="comment", fromUserId=200, toUserId=100, noteId=9, commentId=1)),  # 发给我的评论
        (2, "1", remark(type="reply", fromUserId=201, toUserId=100, noteId=9, commentId=2)),    # 发给我的回复
        (3, "1", remark(type="mention", fromUserId=202, toUserId=100, noteId=9)),               # @我
        (4, "1", remark(type="comment", fromUserId=200, toUserId=999, noteId=9)),               # 发给别人
        (5, "1", None),                                                                          # 系统公告（无 remark）
        (6, "1", remark(type="notice")),                                                         # 系统公告（非用户类型）
    ]
    for nid, ntype, rk in rows:
        sync_conn.execute(
            SysNotice.__table__.insert().values(
                notice_id=nid, notice_title=f"n{nid}", notice_type=ntype,
                notice_content="c", status="0", create_by="system",
                create_time=datetime.now(), remark=rk,
            )
        )
    # 已读记录：id 2 我已读、id 4 是别人的记录（显式给 id，sqlite 不自动填 BigInteger 自增）
    sync_conn.execute(SysNoticeRead.__table__.insert().values(id=1, user_id=100, notice_id=2))
    sync_conn.execute(SysNoticeRead.__table__.insert().values(id=2, user_id=999, notice_id=4))


async def run_probe() -> int:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.database import register_all_models
    from app.models.notice import SysNotice, SysNoticeRead
    from app.api.v1.notices import _purge_user_notices

    # SysUser 有到 SysRole 的 relationship，需先注册全部模型，否则 mapper 初始化会报
    # InvalidRequestError（找不到 'SysRole'）。
    register_all_models()

    # --- A) 选择集合用真 helpers 计算（这是正确性的核心） ---
    from app.api.v1.notices import is_system_notice, is_notice_visible

    class Row:
        def __init__(self, nid, remark):
            self.notice_id = nid
            self.remark = remark

    candidates = [
        Row(1, '{"type":"comment","toUserId":100}'),
        Row(2, '{"type":"reply","toUserId":100}'),
        Row(3, '{"type":"mention","toUserId":100}'),
        Row(4, '{"type":"comment","toUserId":999}'),
        Row(5, None),
        Row(6, '{"type":"notice"}'),
    ]
    targets = [r.notice_id for r in candidates
               if not is_system_notice(r) and is_notice_visible(r, 100)]
    check("S1", "选择集合=只含发给我的用户通知(1,2,3)", targets == [1, 2, 3], str(targets))

    # --- B) 端到端：真 async 会话跑 _purge_user_notices（用 sqlite 异步引擎） ---
    # 优先尝试 aiosqlite；装不了就跳过 B 段（A 段已覆盖选择逻辑）
    try:
        import aiosqlite  # noqa: F401
        has_aiosqlite = True
    except ImportError:
        has_aiosqlite = False

    if has_aiosqlite:
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "_probe_notice_purge.sqlite")
        if os.path.exists(db_file):
            os.remove(db_file)
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
        async with engine.begin() as conn:
            await conn.run_sync(_seed_sqlite)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            removed = await _purge_user_notices(db, 100, [1, 2, 3, 4, 5, 6])
            await db.commit()
        async with Session() as db:
            left = [r[0] for r in (await db.execute(select(SysNotice.notice_id).order_by(SysNotice.notice_id))).all()]
            reads = [r[0] for r in (await db.execute(select(SysNoticeRead.notice_id).order_by(SysNoticeRead.notice_id))).all()]
        await engine.dispose()
        try:
            os.remove(db_file)
        except OSError:
            pass
        check("B1", "删除了 3 条(1,2,3)", removed == 3, f"removed={removed}")
        check("B2", "残留=系统公告+别人的通知(4,5,6)", left == [4, 5, 6], str(left))
        check("B3", "已读记录被清理(仅剩别人的4)", reads == [4], str(reads))
    else:
        check("B0", "aiosqlite 未安装（跳过端到端段，A 段已覆盖核心选择逻辑）", True, "skipped")

    # --- C) 静态核对：源码里 /front 删除段确实调用了 _purge_user_notices（而非 mark_notices_read） ---
    src = open(os.path.join(ROOT, "app", "api", "v1", "notices.py"), encoding="utf-8").read()
    # 取 /front/batch 段到文件尾
    seg = src.split('@router.delete("/front/batch/{notice_ids}")', 1)[-1]
    check("C1", "/front/batch 调用了 _purge_user_notices", "_purge_user_notices" in seg)
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
