# -*- coding: utf-8 -*-
"""笔记分类创建探针 —— 连 DB（probe 专属分类/笔记前缀），零 LLM 成本

验证「把笔记放进一个不存在的分类」这条路径（用户 2026-10-17 报的 笔记专家 失败）：
  1. `note_manage.create_category` 建出分类，落库能按名读回
  2. 同名再调用是**幂等**的（返回同一 categoryId，不产生重复行）
  3. `create` 带 `create_category_if_missing=true` → 缺失分类自动建 + 笔记落库
  4. `create` **不带**该标记、分类名不存在 → 仍是失败信封，且**不**建分类
  5. 空名 / 预览字段等边界

自清理：全程一个事务，结束 `rollback`；再按 `probe-note-cat-` 前缀兜底清一次
（覆盖上一次探测中途崩溃留下的残行）。

用法
----
    .venv/Scripts/python.exe tests/_probe_note_category.py     # 全绿退出码 0
"""
import asyncio
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_PREFIX = "probe-note-cat-"
TAG = PROBE_PREFIX + uuid.uuid4().hex[:8]

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": str(actual)})


async def _pick_user_id(db):
    from sqlalchemy import select
    from app.models.user import SysUser

    uid = await db.scalar(select(SysUser.user_id).order_by(SysUser.user_id.asc()).limit(1))
    return int(uid or 0)


async def _cleanup(user_id):
    from sqlalchemy import delete, select
    from app.database import async_session_factory, engine
    from app.models.note import Note, NoteCategory

    try:
        async with async_session_factory() as db:
            note_ids = (
                await db.execute(
                    select(Note.note_id).where(
                        Note.user_id == user_id, Note.title.like(PROBE_PREFIX + "%")
                    )
                )
            ).scalars().all()
            if note_ids:
                # 先删笔记（note.category_id 外键指向 note_category）
                await db.execute(delete(Note).where(Note.note_id.in_(note_ids)))
            await db.execute(
                delete(NoteCategory).where(
                    NoteCategory.user_id == user_id,
                    NoteCategory.name.like(PROBE_PREFIX + "%"),
                )
            )
            await db.commit()
    finally:
        await engine.dispose()


def _print_and_exit() -> int:
    print("\n---- 笔记分类创建探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


async def run_probe() -> int:
    from sqlalchemy import func, select

    from app.database import async_session_factory, register_all_models

    register_all_models()
    from app.services import note_write_service as nws
    from app.services.ai.agent.base import ToolContext
    from app.services.ai.agent.tools.note_manage import NoteManageTool
    from app.models.note import NoteCategory

    async with async_session_factory() as db:
        user_id = await _pick_user_id(db)
    if not user_id:
        check("NC-00", "取到一个可用的 user_id", False, "sys_user 为空")
        return _print_and_exit()

    await _cleanup(user_id)

    async with async_session_factory() as db:
        tool = NoteManageTool()
        ctx = ToolContext(db=db, user_id=user_id)
        name = f"{TAG}-JS"

        # ---- 1. create_category 建出分类 ----
        res = await tool.execute(
            {"action": "create_category", "name": name, "order_num": 7}, ctx
        )
        cat = (res or {}).get("category") or {}
        cid = cat.get("categoryId")
        check(
            "NC-01",
            "create_category 成功且回 categoryId/name/orderNum",
            res.get("success") is True
            and cid is not None
            and cat.get("name") == name
            and cat.get("orderNum") == 7,
            res,
        )
        found = await nws.find_category_by_name(db, user_id, name)
        check("NC-02", "新建分类能按名读回", found is not None and found.id == cid, found and found.id)

        # ---- 2. 幂等：同名再建返回同一 id ----
        res2 = await tool.execute({"action": "create_category", "name": name}, ctx)
        cid2 = ((res2 or {}).get("category") or {}).get("categoryId")
        check("NC-03", "同名再建返回同一 categoryId", cid2 == cid, f"first={cid} second={cid2}")
        dup = await db.scalar(
            select(func.count())
            .select_from(NoteCategory)
            .where(NoteCategory.user_id == user_id, NoteCategory.name == name)
        )
        check("NC-04", "同名分类没有产生重复行", int(dup or 0) == 1, dup)

        # ---- 3. create + create_category_if_missing=true → 自动建分类 ----
        fresh = f"{TAG}-fresh"
        res3 = await tool.execute(
            {
                "action": "create",
                "title": f"{TAG}-note1",
                "content": "探针正文",
                "category_name": fresh,
                "create_category_if_missing": True,
            },
            ctx,
        )
        note = (res3 or {}).get("note") or {}
        new_cat = await nws.find_category_by_name(db, user_id, fresh)
        check("NC-05", "create+if_missing=true 成功建笔记", res3.get("success") is True and note.get("noteId") is not None, res3)
        check(
            "NC-06",
            "缺失分类被自动创建且笔记落在其中",
            new_cat is not None and note.get("categoryId") == new_cat.id,
            f"cat={new_cat and new_cat.id} note.cat={note.get('categoryId')}",
        )

        # ---- 4. create 不带标记、分类名不存在 → 仍失败，且不建分类 ----
        missing = f"{TAG}-missing"
        res4 = await tool.execute(
            {"action": "create", "title": f"{TAG}-note2", "content": "x", "category_name": missing},
            ctx,
        )
        check("NC-07", "不带标记时缺失分类仍失败", res4.get("success") is False, res4)
        check("NC-08", "失败时没有建出分类", await nws.find_category_by_name(db, user_id, missing) is None)

        # ---- 5. name 为空 → fail（且不进 _WRITE_ACTIONS 之外）----
        res5 = await tool.execute({"action": "create_category", "name": "   "}, ctx)
        check("NC-09", "create_category 空名 fail", res5.get("success") is False, res5)

        # ---- 6. 确认卡预览 ----
        pv = await tool.preview({"action": "create_category", "name": name}, ctx)
        check("NC-10", "create_category 预览含 name", pv.get("name") == name, pv)
        preview_name = f"{TAG}-preview"
        pv2 = await tool.preview(
            {
                "action": "create",
                "title": "x",
                "category_name": preview_name,
                "create_category_if_missing": True,
            },
            ctx,
        )
        check("NC-11", "create 预览标记 willCreateCategory", pv2.get("willCreateCategory") == preview_name, pv2)

        # ---- 7. 改动面：create_category 是需确认的写操作，但**非**破坏性 ----
        check("NC-12", "create_category 进 _WRITE_ACTIONS", tool.needs_confirmation({"action": "create_category"}))
        check("NC-13", "create_category 不是破坏性操作", not tool.is_destructive({"action": "create_category"}))

        await db.rollback()

    await _cleanup(user_id)
    return _print_and_exit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
