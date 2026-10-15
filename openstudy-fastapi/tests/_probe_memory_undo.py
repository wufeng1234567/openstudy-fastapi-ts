# -*- coding: utf-8 -*-
"""一次性探针：长期记忆的**逻辑删除** + 「最近删除」/ 恢复 + 越权闸门

为什么单独写一个：`tests/e2e_agent_api.py` 是「一次跑全部组」的套件（没有分组参数），
跑一次几分钟、还要打真模型；本探针**只在进程内**跑（直调 service + 用 ASGITransport
打两个新端点，**不打模型、不碰 HTTP 网络**），几十秒就能给出红绿。

用法（必须用 .venv 的 python）：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_probe_memory_undo.py

退出码：0 = 全部符合预期；1 = 有红 / 环境不足（库里只有一个用户、或找不到「零记忆用户」
= **没测到东西**，也回 1）。

⚠️ 夹具规则（本仓库出过「测试清理删光真实数据」的事故）：
  · 自造数据一律带 `__probe_memory_undo__` 标记；
  · **不用 `save_memory` 造夹具** —— 它内部带淘汰（到上限会**物理删**该用户最旧的行，
    那是真实数据）。改成裸 SQL INSERT：顺带覆盖「只给 4 列也能插进去」，
    即库侧 `del_flag` 必须真有 `DEFAULT '0'`（`tests/e2e_agent_api.py` 的夹具也是这么插的）；
  · 淘汰用例挑一个**当前一条记忆都没有**的真实用户（插进去的行 100% 是本探针的），
    并把这个前提做成断言 —— 不满足就报「没测到」而不是硬跑；
  · 收尾只按**本探针登记的精确 id 物理删**（这些行已被软删，走工具的 delete 清不掉），
    再数一次标记残留 + 按 id 集合回比「无标记行一条没少」。
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

# ⚠️ 必须先 `import app.main`：它会把全量模型注册进 metadata（与 `_probe_idor_scope.py`
#    同一手法），否则第一次查询会在 mapper 配置上炸。
from app.main import app as fastapi_app  # noqa: E402,F401

from app.core.security import get_current_user  # noqa: E402
from app.database import async_session_factory, init_db  # noqa: E402
from app.services.ai import memory_service  # noqa: E402
from app.services.ai.agent.tools.memory_manage import MemoryManageTool  # noqa: E402

MARK = "__probe_memory_undo__"
EPISODIC = memory_service.MEMORY_TYPE_EPISODIC

RESULTS = []


def check(cid, desc, ok, detail):
    RESULTS.append((cid, desc, bool(ok), detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {cid} {desc}")
    print(f"         {detail}")


async def q(sql, **p):
    """跑一条写 SQL 并提交（每条一个独立会话：别让一个会话里的事务把副作用藏起来）"""
    async with async_session_factory() as s:
        r = await s.execute(text(sql), p)
        await s.commit()
        return r


async def s1(sql, **p):
    async with async_session_factory() as s:
        return await s.scalar(text(sql), p)


async def rows(sql, **p):
    async with async_session_factory() as s:
        return (await s.execute(text(sql), p)).all()


async def unmarked_ids():
    """全表里**不带标记**的行 id —— 那是用户自己的记忆，一条都不许少"""
    return {r[0] for r in await rows(
        "SELECT id FROM ai_agent_memory WHERE POSITION(:m IN content) = 0", m=MARK)}


async def del_flag_of(mem_id):
    return await s1("SELECT del_flag FROM ai_agent_memory WHERE id = :i", i=mem_id)


async def main():
    # ---------------- 0. 建表/补列（后端启动时同一条路径）+ 列已就位 ----------------
    await init_db()
    col = (await rows(
        "SELECT data_type, character_maximum_length, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ai_agent_memory' "
        "AND column_name='del_flag'"))
    col = col[0] if col else None
    check("M0", "ai_agent_memory.del_flag 已补齐（varchar(1) NOT NULL DEFAULT '0'，可重复执行）",
          bool(col) and col[0] == "character varying" and col[1] == 1
          and col[2] == "NO" and "0" in (col[3] or ""),
          f"information_schema → {col}")

    # ---------------- 选身份 / 选「零记忆用户」 ----------------
    uid_a = int(await s1("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1") or 0)
    uid_b = int(await s1(
        "SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1",
        u=uid_a) or 0)
    if not uid_a or not uid_b:
        print(f"!! 库里只有一个用户（attacker={uid_a} victim={uid_b}）→ 本探针**没测到东西**，回 1")
        return 1

    # ⚠️ 必须**排除 attacker/victim**：两个角色各自有夹具行，混进淘汰用例里，
    #    「三条活跃行超限 → 淘汰最旧那条」的算式就脏了（第一版就是这么写错的，P9a 当场抓到）。
    uid_ev = int(await s1(
        "SELECT u.user_id FROM sys_user u "
        "LEFT JOIN ai_agent_memory m ON m.user_id = u.user_id "
        "WHERE m.id IS NULL AND u.user_id <> :a AND u.user_id <> :b "
        "ORDER BY u.user_id LIMIT 1", a=uid_a, b=uid_b) or 0)
    if not uid_ev:
        print("!! 找不到「一条记忆都没有」的用户 → 淘汰用例无法安全地跑（会动到真实记忆）"
              "→ **没测到东西**，回 1")
        return 1
    print(f"attacker（登录态）= {uid_a}   victim（别人）= {uid_b}   零记忆用户 = {uid_ev}\n")

    before_unmarked = await unmarked_ids()
    print(f"跑前：全表无标记行 {len(before_unmarked)} 条（跑完必须一条不少）\n")

    ids = []
    mem_a = mem_b = mem_c = 0
    ev = []
    original_caps = dict(memory_service.MAX_PER_TYPE)

    try:
        # ---------------- 造夹具（裸 SQL INSERT，故意只给 4 列 + 不写 del_flag）----------------
        async def insert_mem(uid, content):
            await q("INSERT INTO ai_agent_memory (user_id, memory_type, content, importance) "
                    "VALUES (:u, 'episodic', :c, 7)", u=uid, c=content)
            return int(await s1(
                "SELECT id FROM ai_agent_memory WHERE user_id = :u AND content = :c "
                "ORDER BY id DESC LIMIT 1", u=uid, c=content) or 0)

        mem_a = await insert_mem(uid_a, MARK + "自己的记忆")
        mem_b = await insert_mem(uid_b, MARK + "别人的记忆")
        mem_c = await insert_mem(uid_a, MARK + "端点用的记忆")
        ev = [await insert_mem(uid_ev, MARK + f"淘汰-{i}") for i in (1, 2, 3)]
        ids = [mem_a, mem_b, mem_c, *ev, 0]
        print(f"夹具：自己的 #{mem_a} #{mem_c} / 别人的 #{mem_b} / 淘汰组 {ev}\n")
        check("M1", "夹具是本探针刚插的（4 个 id 都拿到了，且都属于指定用户）",
              all(ids[:6]) and len(set(ids[:6])) == 6,
              f"ids={ids[:6]}")

        # ---------------- P1 正向对照：插入后能搜到（否则后面的「搜不到」恒真）----------------
        async with async_session_factory() as db:
            cnt_before = dict(await memory_service.count_by_type(db, uid_a))
        async with async_session_factory() as db:
            hit = await memory_service.list_memories(db, uid_a, keyword=MARK, limit=50)
        hit_ids = [r.id for r in hit]
        check("P1", "正向对照：刚插的那条**能**被 list_memories 搜到（否则后面的「搜不到」恒真）",
              mem_a in hit_ids and mem_c in hit_ids and mem_b not in hit_ids,
              f"keyword={MARK!r} 命中={hit_ids}（自己的 {mem_a}/{mem_c} 都在、别人的 {mem_b} 不在）")

        # ---------------- P2 逻辑删除：行还在、搜不到、取不到、不计数 ----------------
        async with async_session_factory() as db:
            deleted = await memory_service.delete_memory(db, uid_a, mem_a)
        flag = await del_flag_of(mem_a)
        async with async_session_factory() as db:
            hit2 = [r.id for r in await memory_service.list_memories(db, uid_a, keyword=MARK, limit=50)]
        async with async_session_factory() as db:
            got = await memory_service.get_memory(db, uid_a, mem_a)
        async with async_session_factory() as db:
            cnt_after = dict(await memory_service.count_by_type(db, uid_a))
        check("P2", "delete_memory → 逻辑删（行还在、del_flag='2'）且搜不到、也取不到",
              deleted is True and flag == "2" and mem_a not in hit2 and got is None,
              f"delete 返回={deleted} del_flag={flag!r} 再搜命中={hit2} "
              f"get_memory={getattr(got, 'id', None)}（应为 None —— 确认卡片靠它反查）")
        # 计数：软删的行**不占**口径（这条同时是「删了还占配额」那个坑的判据）
        # 期望值精确到 -1：插入后是 base+2（mem_a/mem_c），软删掉 mem_a 后必须正好 base+1。
        check("P3", "软删的行不占 count_by_type 口径（episodic 正好少 1）",
              int(cnt_after.get(EPISODIC, 0)) == int(cnt_before.get(EPISODIC, 0)) - 1,
              f"软删前 episodic={cnt_before.get(EPISODIC)} → 软删后={cnt_after.get(EPISODIC)}"
              f"（期望 {int(cnt_before.get(EPISODIC, 0)) - 1}；全类型={cnt_after}）")

        # ---------------- P4 同一句不许删两次 ----------------
        async with async_session_factory() as db:
            again = await memory_service.delete_memory(db, uid_a, mem_a)
        check("P4", "同一条记忆删第二次 → False（不假装又删了一次，与物理删时代同行为）",
              again is False,
              f"第二次 delete_memory 返回={again}（del_flag 仍是 {await del_flag_of(mem_a)!r}）")

        # ---------------- P5 「最近删除」列表（含越权读闸门）----------------
        async with async_session_factory() as db:
            deleted_b = await memory_service.delete_memory(db, uid_b, mem_b)
        async with async_session_factory() as db:
            la = [r.id for r in await memory_service.list_deleted_memories(db, uid_a)]
        async with async_session_factory() as db:
            lb = [r.id for r in await memory_service.list_deleted_memories(db, uid_b)]
        check("P5", "list_deleted_memories：自己的删掉的**看得见**，别人的看不见",
              deleted_b is True and mem_a in la and mem_b not in la
              and mem_b in lb and mem_a not in lb,
              f"uid_a 的最近删除={la}（含自己的 {mem_a}={mem_a in la}、含别人的 {mem_b}={mem_b in la}）；"
              f"uid_b 的={lb}（含自己的 {mem_b}={mem_b in lb}）")

        # ---------------- P6 越权恢复：别人的 id / 不存在的 id 都失败，且行不变 ----------------
        async with async_session_factory() as db:
            steal = await memory_service.restore_memory(db, uid_a, mem_b)
        flag_b = await del_flag_of(mem_b)
        async with async_session_factory() as db:
            ghost = await memory_service.restore_memory(db, uid_a, 999999999)
        check("P6", "restore_memory：别人的 id → False 且那行仍是 '2'；不存在的 id → 也 False",
              steal is False and flag_b == "2" and ghost is False,
              f"恢复别人的={steal} 别人的 del_flag={flag_b!r} 恢复不存在的={ghost}")

        # ---------------- P7 恢复：又能搜到、计数回来；且**幂等** ----------------
        async with async_session_factory() as db:
            restored = await memory_service.restore_memory(db, uid_a, mem_a)
        flag_a = await del_flag_of(mem_a)
        async with async_session_factory() as db:
            hit3 = [r.id for r in await memory_service.list_memories(db, uid_a, keyword=MARK, limit=50)]
        async with async_session_factory() as db:
            got3 = await memory_service.get_memory(db, uid_a, mem_a)
        async with async_session_factory() as db:
            cnt_restored = dict(await memory_service.count_by_type(db, uid_a))
        async with async_session_factory() as db:
            restored2 = await memory_service.restore_memory(db, uid_a, mem_a)
        check("P7", "restore_memory → del_flag 回 '0'、又能搜到/取到、计数回到删除前",
              restored is True and flag_a == "0" and mem_a in hit3
              and getattr(got3, "id", None) == mem_a
              and int(cnt_restored.get(EPISODIC, 0)) == int(cnt_before.get(EPISODIC, 0)),
              f"恢复={restored} del_flag={flag_a!r} 再搜命中={hit3} get_memory={getattr(got3, 'id', None)} "
              f"episodic={cnt_restored.get(EPISODIC)}（删除前={cnt_before.get(EPISODIC)}）")
        check("P8", "恢复是**幂等**的（在「最近删除」里连点两次都算成功，不会回「不存在」）",
              restored2 is True and (await del_flag_of(mem_a)) == "0",
              f"第二次 restore 返回={restored2} del_flag={await del_flag_of(mem_a)!r}")

        # ---------------- P9 淘汰只数「未删」的行（uid_ev 一条真实记忆都没有）----------------
        check("P9a", "淘汰用例的前提：零记忆用户确实一条都没有（否则会动到真实数据）",
              int(await s1("SELECT count(*) FROM ai_agent_memory WHERE user_id = :u",
                           u=uid_ev) or 0) == 3,
              f"uid={uid_ev} 当前行数={await s1('SELECT count(*) FROM ai_agent_memory WHERE user_id = :u', u=uid_ev)}"
              f"（应为刚插的 3 条）")
        memory_service.MAX_PER_TYPE = {**original_caps, EPISODIC: 2}
        async with async_session_factory() as db:
            await memory_service.delete_memory(db, uid_ev, ev[0])  # 最旧那条软删掉
        async with async_session_factory() as db:
            evicted_dry = await memory_service._evict(db, uid_ev, EPISODIC)
            await db.commit()
        left_all = int(await s1("SELECT count(*) FROM ai_agent_memory WHERE user_id = :u",
                                u=uid_ev) or 0)
        check("P9b", "软删的行不占淘汰配额：活跃 2 条 ≤ 上限 2 → 一条都不淘汰（物理行数不变）",
              evicted_dry == 0 and left_all == 3,
              f"_evict 返回={evicted_dry} 物理行数={left_all}（若把 del_flag 过滤漏掉，"
              f"就会算成 3 条超限 → 去物理删那条**已软删、本来还能恢复**的行）")

        ev4 = await insert_mem(uid_ev, MARK + "淘汰-4")
        ids[6] = ev4
        async with async_session_factory() as db:
            evicted = await memory_service._evict(db, uid_ev, EPISODIC)
            await db.commit()
        alive = {r[0] for r in await rows(
            "SELECT id FROM ai_agent_memory WHERE user_id = :u", u=uid_ev)}
        check("P9c", "淘汰该淘汰的：活跃 3 条 > 上限 2 → 删掉**最旧的活跃行**，别碰软删那条",
              evicted == 1 and ev[1] not in alive and ev[0] in alive
              and ev[2] in alive and ev4 in alive,
              f"_evict 返回={evicted} 存活={sorted(alive)}（期望：最旧的活跃行 {ev[1]} 被物理删；"
              f"已软删的 {ev[0]} 仍在 —— 漏了 del_flag 过滤就会反过来删 {ev[0]}）")
        memory_service.MAX_PER_TYPE = original_caps

        # ---------------- P10 路由真的注册了（catch_all 会把「路径写错」伪装成 200）----------------
        routes = {(getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", set()) or [])))
                  for r in fastapi_app.routes}
        check("P10", "两个新端点真的挂在路由表上（路径写错时 catch_all 会回假 200）",
              ("/ai/memory/deleted", ("GET",)) in routes
              and ("/ai/memory/restore", ("POST",)) in routes,
              f"GET /ai/memory/deleted={'/ai/memory/deleted' in {p for p, _ in routes}} "
              f"POST /ai/memory/restore={'/ai/memory/restore' in {p for p, _ in routes}}")

        from app.api.v1.ai import RestoreMemoryBody
        body_fields = set(RestoreMemoryBody.model_fields)
        check("P10b", "恢复接口的请求体只有 memoryId（**不收 userId** —— 收一个就是 IDOR 入口）",
              body_fields == {"memoryId"},
              f"RestoreMemoryBody.model_fields={sorted(body_fields)}")

        # ---------------- P11 端点行为（进程内 ASGITransport，不打网络）----------------
        from httpx import ASGITransport, AsyncClient

        fastapi_app.dependency_overrides[get_current_user] = (
            lambda: {"user_id": uid_a, "roles": [], "user_name": "probe"})
        client = AsyncClient(transport=ASGITransport(app=fastapi_app),
                             base_url="http://probe", timeout=30)
        try:
            async with async_session_factory() as db:
                await memory_service.delete_memory(db, uid_a, mem_c)

            r = await client.get("/ai/memory/deleted")
            b = r.json()
            data = b.get("data") or {}
            items = data.get("items") or []
            item_ids = [it.get("id") for it in items]
            keys_ok = all(
                set(it) == {"id", "memoryType", "content", "createTime"} for it in items) and items
            check("P11", "GET /ai/memory/deleted：回 {items,total}（假 200 时 data 是 null → 会红）",
                  r.status_code == 200 and b.get("code") == 200 and "items" in data
                  and item_ids == [mem_c] and data.get("total") == len(items) and keys_ok,
                  f"HTTP={r.status_code} code={b.get('code')} total={data.get('total')} "
                  f"items={item_ids}（期望只剩自己刚删的 #{mem_c}）字段={keys_ok}")

            r = await client.post("/ai/memory/restore", json={"memoryId": mem_c})
            b = r.json()
            check("P12", "POST /ai/memory/restore 自己的 id → restored=true，库里 del_flag 回 '0'",
                  r.status_code == 200 and b.get("code") == 200
                  and (b.get("data") or {}).get("restored") is True
                  and (b.get("data") or {}).get("memoryId") == mem_c
                  and (await del_flag_of(mem_c)) == "0",
                  f"HTTP={r.status_code} body={json.dumps(b, ensure_ascii=False)} "
                  f"del_flag={await del_flag_of(mem_c)!r}")

            r = await client.post("/ai/memory/restore", json={"memoryId": mem_b})
            b_other = r.json()
            r = await client.post("/ai/memory/restore", json={"memoryId": 999999999})
            b_ghost = r.json()
            check("P13", "端点越权：别人的 id 与不存在的 id → 同 code=400、**同一句**话，且行不变",
                  b_other.get("code") == 400 and b_ghost.get("code") == 400
                  and b_other.get("msg") == b_ghost.get("msg")
                  and (await del_flag_of(mem_b)) == "2",
                  f"别人的 → {json.dumps(b_other, ensure_ascii=False)}；"
                  f"不存在的 → {json.dumps(b_ghost, ensure_ascii=False)}；"
                  f"别人的 del_flag={await del_flag_of(mem_b)!r}")
        finally:
            fastapi_app.dependency_overrides.pop(get_current_user, None)
            await client.aclose()

        # ---------------- P14 删记忆仍然要二次确认（可撤销 ≠ 可以不确认）----------------
        tool = MemoryManageTool()
        check("P14", "memory_manage 的 forget/clear 仍是「需要确认 + 破坏性」（撤销不是取消确认）",
              tool.needs_confirmation({"action": "forget"}) is True
              and tool.is_destructive({"action": "forget"}) is True
              and tool.is_destructive({"action": "clear"}) is True
              and tool.is_destructive({"action": "list_types"}) is False,
              f"forget: needs_confirmation={tool.needs_confirmation({'action': 'forget'})} "
              f"is_destructive={tool.is_destructive({'action': 'forget'})}；"
              f"clear.is_destructive={tool.is_destructive({'action': 'clear'})}；"
              f"list_types.is_destructive={tool.is_destructive({'action': 'list_types'})}")
    finally:
        memory_service.MAX_PER_TYPE = original_caps
        # ---------------- 精确物理删（这些行可能是 del_flag='2'，只能裸 SQL）+ 数残留 ----------------
        gone = [i for i in ids if i]
        async with async_session_factory() as cdb:
            for i in gone:
                await cdb.execute(text("DELETE FROM ai_agent_memory WHERE id = :i"), {"i": i})
            await cdb.commit()
        # 兜底：把本探针标记的、上面没登记到的行也物理删掉（只按标记，不碰无标记行）
        await q("DELETE FROM ai_agent_memory WHERE POSITION(:m IN content) > 0", m=MARK)
        left = int(await s1(
            "SELECT count(*) FROM ai_agent_memory WHERE POSITION(:m IN content) > 0",
            m=MARK) or 0)
        check("M2", "夹具残留 0（按登记的精确 id + 标记物理删，不走工具的 delete）",
              left == 0, f"标记残留={left} 登记并删除的 id={gone}")

        after_unmarked = await unmarked_ids()
        lost = sorted(before_unmarked - after_unmarked)
        check("M3", "**用户自己的记忆一条没少**（无标记行 id 集合仍然包含跑前那批）",
              not lost,
              f"跑前 {len(before_unmarked)} 条 → 跑后 {len(after_unmarked)} 条；"
              f"消失的 id={lost or '无'}（新增不判红：库里可能有别的进程在正常写记忆）")

    bad = [r for r in RESULTS if not r[2]]
    print(f"\n结果：{len(RESULTS) - len(bad)}/{len(RESULTS)} 通过"
          + ("" if not bad else f"；红：{', '.join(r[0] for r in bad)}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
