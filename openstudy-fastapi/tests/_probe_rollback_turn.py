# -*- coding: utf-8 -*-
"""一次性探针：「一轮操作的回退」端到端（账本写入 → 逆操作执行 → 越权/幂等闸门）

为什么单独写一个：`tests/e2e_agent_api.py` 是「一次跑全部组」的套件（没有分组参数），
跑一次几分钟、还要打真模型；本探针**只在进程内**跑（直调工具收口 + 服务层，
**不打模型、不碰网络**），几十秒出红绿。

用法（必须用 .venv 的 python）：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_probe_rollback_turn.py

退出码：0 = 全部符合预期；1 = 有红 / 环境不足（**没测到东西**也回 1）。

本探针复刻的是**生产路径**，不是自己另搭一套：
  · 工具执行：`loop._prepare_tool_call`（归一化 + 屏蔽闸门）→ `loop._execute_tool`
    —— 与 `run_agent_stream` 内联分支以及 ds-free 的 `execute_agent_tool` **同一个收口**；
  · 提交：写工具之后显式 `commit()` —— 复刻 `run_agent_stream` 里那句「写操作显式提交」；
  · 回退：`rollback_service.rollback_turn`。

⚠️ 探针**换掉**了 `memory_hook.record_tool_memory`（换成空实现），理由：
   每次写操作都会由它往**真实用户的长期记忆**里落一条 episodic（内容是工具回执拼的、
   我无法在写入时打标记）。那是另一个功能的副作用，与本探针的被测对象（账本 + 逆操作）
   无关，留着只会在真实用户记忆里留垃圾。`_probe_memory_undo.py` 已覆盖记忆本身。
   除此之外**没有改动任何被测代码**。

⚠️ 夹具规则（本仓库出过「测试清理删光真实数据」的事故）：
  · 自造数据一律带 `__probe_rollback_turn__` 标记（账本行用 `turn_id` 前缀当标记）；
  · 记忆夹具**不用 `save_memory`** 造（它带淘汰，会物理删该用户最旧的行 —— 那是真实数据），
    改成裸 SQL INSERT；
  · 收尾只按**本探针登记的精确 id 物理删**（笔记/记忆是逻辑删，走工具的 delete 清不掉），
    再按标记兜底清一次，最后数残留；
  · 同时回比「无标记行一条没少」—— 那是用户自己的数据，一行都不许动。
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

# ⚠️ 必须先 `import app.main`：它会把全量模型注册进 metadata（与另两个探针同一手法），
#    否则第一次查询会在 mapper 配置上炸。
from app.main import app as fastapi_app  # noqa: E402,F401

from app.database import async_session_factory, init_db  # noqa: E402
from app.models.agent_op_log import AiAgentOpLog  # noqa: E402
from app.services.ai.agent import loop, memory_hook, rollback_service  # noqa: E402
from app.services.ai.agent.base import (  # noqa: E402
    OP_RESTORE,
    OP_RESTORE_FIELDS,
    OP_SOFT_DELETE,
    UNDO_BEFORE_KEY,
    ToolContext,
)
from app.services.ai.agent.registry import ensure_tools_loaded, registry  # noqa: E402

MARK = "__probe_rollback_turn__"
SESSION = "__probe_rb__"

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


def ctx_for(db, uid, session_id=SESSION, turn_id=""):
    """构造 `_execute_tool` 用的上下文（形状与 loop 里那两处逐字一致）"""
    return ToolContext(
        db=db,
        user_id=uid,
        session_id=session_id,
        extra={"image_urls": [], "tool_registry": registry, "turn_id": turn_id},
    )


async def run_write_tool(db, tool_name, params, uid, turn_id, commit=True):
    """跑一次写工具并（可选）提交 —— 复刻 `run_agent_stream` 的执行 + 提交两步"""
    tool, normalized, err = await loop._prepare_tool_call(tool_name, params, uid)
    if err:
        return {"success": False, "error": err}
    result = await loop._execute_tool(tool, normalized, ctx_for(db, uid, SESSION, turn_id))
    if commit and tool.write_operation and result.get("success"):
        await db.commit()
    return result


async def op_rows(turn_id):
    """索引：0 tool / 1 action / 2 op / 3 target_table / 4 target_ids / 5 undoable /
    6 reason / 7 undone / 8 before"""
    return await rows(
        "SELECT tool, action, op, target_table, target_ids::text, undoable, reason,"
        " (undone_at IS NOT NULL) AS undone, before::text"
        " FROM ai_agent_op_log WHERE session_id = :s AND turn_id = :t ORDER BY op_index",
        s=SESSION, t=turn_id)


async def note_flag(note_id):
    return await s1("SELECT del_flag FROM note WHERE note_id = :i", i=note_id)


async def mem_flag(mem_id):
    return await s1("SELECT del_flag FROM ai_agent_memory WHERE id = :i", i=mem_id)


async def unmarked_sets():
    """我碰过的表里**不带标记**的行 id 集合（= 用户自己的数据，一条都不许少）"""
    return {
        "note": {r[0] for r in await rows(
            "SELECT note_id FROM note WHERE POSITION(:m IN title) = 0", m=MARK)},
        "memory": {r[0] for r in await rows(
            "SELECT id FROM ai_agent_memory WHERE POSITION(:m IN content) = 0", m=MARK)},
        "question_bank": {r[0] for r in await rows(
            "SELECT id FROM question_bank WHERE POSITION(:m IN bank_name) = 0", m=MARK)},
        "op_log": {r[0] for r in await rows(
            "SELECT id FROM ai_agent_op_log WHERE LEFT(turn_id, LENGTH(:m)) <> :m", m=MARK)},
    }


async def main():
    # ---------------- M0 建表 + 列已就位（证明模型进了 register_all_models）----------------
    await init_db()
    cols = {r[0] for r in await rows(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ai_agent_op_log'")}
    model_cols = {c.name for c in AiAgentOpLog.__table__.columns}
    check("M0", "ai_agent_op_log 已由 create_all 建出，且列与模型逐字一致"
                "（漏了 register_all_models 这一条就是「查无此表」）",
          bool(cols) and cols == model_cols,
          f"模型列={sorted(model_cols)}\n         库里的列={sorted(cols)}")

    ensure_tools_loaded()
    # 探针期间的「写操作记忆」副作用关掉（见模块 docstring；不影响被测的账本/回退）
    memory_hook.record_tool_memory = _noop

    uid_a = int(await s1("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1") or 0)
    uid_b = int(await s1(
        "SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1",
        u=uid_a) or 0)
    if not uid_a or not uid_b:
        print(f"!! 库里只有一个用户（a={uid_a} b={uid_b}）→ 越权用例无法构造 → **没测到东西**，回 1")
        return 1
    # 两道「uid_a 看得见」的题（只读借用，不是我的夹具；用来测题目标记的回退）
    qrow = await rows(
        "SELECT q.id, q.bank_id FROM question_main q JOIN question_bank b ON b.id = q.bank_id "
        "WHERE (b.is_public = 0 OR b.user_id = :u) ORDER BY q.id LIMIT 2", u=uid_a)
    if len(qrow) < 2:
        print("!! 库里找不到两道对 uid_a 可见的题 → 标记类用例无法构造 → **没测到东西**，回 1")
        return 1
    q1, q2 = int(qrow[0][0]), int(qrow[1][0])
    print(f"uid_a={uid_a}  uid_b={uid_b}  借用题目 q1={q1} q2={q2}\n")

    before_unmarked = await unmarked_sets()
    print("跑前无标记行："
          + "  ".join(f"{k}={len(v)}" for k, v in before_unmarked.items()) + "\n")

    ids = {"note": [], "note_category": [], "memory": [], "bank": [], "fav": []}
    try:
        # ---------------- 夹具 ----------------
        await q("INSERT INTO note_category (user_id, name, order_num) VALUES (:u, :n, 0)",
                u=uid_a, n=MARK + "分类")
        cat_id = int(await s1("SELECT id FROM note_category WHERE user_id = :u AND name = :n",
                              u=uid_a, n=MARK + "分类") or 0)
        ids["note_category"].append(cat_id)

        async def add_note(tag):
            await q("INSERT INTO note (user_id, category_id, title, filename, content,"
                    " is_public, view_count, like_count, comment_count, status, del_flag)"
                    " VALUES (:u, :c, :t, '', :body, 0, 0, 0, 0, 'draft', '0')",
                    u=uid_a, c=cat_id, t=MARK + tag, body=MARK + "正文" + tag)
            nid = int(await s1("SELECT note_id FROM note WHERE user_id = :u AND title = :t"
                               " ORDER BY note_id DESC LIMIT 1", u=uid_a, t=MARK + tag) or 0)
            ids["note"].append(nid)
            return nid

        n1 = await add_note("-删除后回退")
        n2 = await add_note("-跳过闸门")          # undoable=False 的靶子（不许被撤）
        n3 = await add_note("-跳过闸门-对照")     # 同一条 op 但 undoable=True 的对照
        n4 = await add_note("-同事务")

        async def add_mem(uid, tag):
            await q("INSERT INTO ai_agent_memory (user_id, memory_type, content, importance)"
                    " VALUES (:u, 'episodic', :c, 7)", u=uid, c=MARK + tag)
            mid = int(await s1("SELECT id FROM ai_agent_memory WHERE user_id = :u AND content = :c"
                               " ORDER BY id DESC LIMIT 1", u=uid, c=MARK + tag) or 0)
            ids["memory"].append(mid)
            return mid

        m1 = await add_mem(uid_a, "-忘记后回退")
        m2 = await add_mem(uid_b, "-别人的记忆")

        await q("INSERT INTO question_bank (bank_name, subject, total_questions, status,"
                " user_id, is_public) VALUES (:n, 'probe', 0, '0', :u, 0)",
                n=MARK + "题库", u=uid_a)
        bank_id = int(await s1("SELECT id FROM question_bank WHERE user_id = :u AND bank_name = :n",
                               u=uid_a, n=MARK + "题库") or 0)
        ids["bank"].append(bank_id)

        check("M1", "夹具登记齐（4 篇笔记 + 1 分类 + 2 条记忆 + 1 个题库，id 都拿到了）",
              all([n1, n2, n3, n4, cat_id, m1, m2, bank_id]) and len(set(ids["note"])) == 4,
              f"notes={ids['note']} cat={cat_id} mem={m1}(a)/{m2}(b) bank={bank_id}")

        # ---------------- P1 正向对照：写工具真的写了，账本也真的记了 ----------------
        t1 = MARK + "-t1"
        async with async_session_factory() as db:
            r1 = await run_write_tool(db, "note_manage",
                                      {"action": "delete", "note_id": n1}, uid_a, t1)
        flag_after_delete = await note_flag(n1)
        led = await op_rows(t1)
        check("P1", "note delete：数据真的被逻辑删（del_flag='2'），且账本记下了「怎么撤」",
              r1.get("success") is True and flag_after_delete == "2" and len(led) == 1
              and led[0][0] == "note_manage" and led[0][1] == "delete"
              and led[0][2] == OP_RESTORE and led[0][3] == "note"
              and led[0][5] is True and led[0][6] == "" and led[0][7] is False
              and json.loads(led[0][4]) == [n1],
              f"回执 success={r1.get('success')} note.del_flag={flag_after_delete!r}\n"
              f"         账本行(tool,action,op,table,ids,undoable,reason,undone)={led}")

        # ---------------- P2 回退：笔记恢复 ----------------
        async with async_session_factory() as db:
            out = await rollback_service.rollback_turn(db, uid_a, SESSION, t1)
            await db.commit()
        check("P2", "rollback_turn 把这一轮删掉的笔记恢复（del_flag 回 '0'）",
              out["reverted"] == 1 and not out["failed"] and await note_flag(n1) == "0",
              f"结果={json.dumps(out, ensure_ascii=False)} note.del_flag={await note_flag(n1)!r}")

        # ---------------- P3 幂等：连点第二次什么都不做 ----------------
        async with async_session_factory() as db:
            out2 = await rollback_service.rollback_turn(db, uid_a, SESSION, t1)
            await db.commit()
        led2 = await op_rows(t1)
        check("P3", "**幂等**：第二次回退 reverted=0、一行数据不动（undone_at 作判据）",
              out2["reverted"] == 0 and not out2["failed"] and await note_flag(n1) == "0"
              and led2[0][7] is True,
              f"第二次结果={json.dumps(out2, ensure_ascii=False)} "
              f"note.del_flag={await note_flag(n1)!r} undone_at 已置={led2[0][7]}")

        # ---------------- P4 记忆：忘记 → 回退 ----------------
        t2 = MARK + "-t2"
        async with async_session_factory() as db:
            r2 = await run_write_tool(db, "memory_manage",
                                      {"action": "forget", "memory_id": m1}, uid_a, t2)
        led_m = await op_rows(t2)
        flag_forgot = await mem_flag(m1)
        async with async_session_factory() as db:
            out_m = await rollback_service.rollback_turn(db, uid_a, SESSION, t2)
            await db.commit()
        check("P4", "memory forget → 逻辑删（'2'）；回退 → 恢复（'0'）（复用 restore_memory）",
              r2.get("success") is True and flag_forgot == "2" and len(led_m) == 1
              and led_m[0][2] == "restore_memory" and out_m["reverted"] == 1
              and await mem_flag(m1) == "0",
              f"forget 后 del_flag={flag_forgot!r} 账本 op={led_m[0][2] if led_m else None} "
              f"回退={json.dumps(out_m, ensure_ascii=False)} 现在 del_flag={await mem_flag(m1)!r}")

        # ---------------- P5 越权：别人的账本行不许被我的回退碰到（**这条必须能红**）----------------
        # 构造：uid_b 在自己名下删掉一条记忆（连账本行）→ 用 uid_a 跑同一个 (session, turn)
        t3 = MARK + "-t3"
        async with async_session_factory() as db:
            await run_write_tool(db, "memory_manage",
                                 {"action": "forget", "memory_id": m2}, uid_b, t3)
        led_b = await rows(
            "SELECT user_id, op, undoable, (undone_at IS NOT NULL) FROM ai_agent_op_log"
            " WHERE session_id = :s AND turn_id = :t", s=SESSION, t=t3)
        flag_b_before = await mem_flag(m2)
        async with async_session_factory() as db:
            steal = await rollback_service.rollback_turn(db, uid_a, SESSION, t3)
            await db.commit()
        check("P5", "**越权闸门**：别人的账本行不在我的回退范围内（用 uid_a 跑 uid_b 的 turn）",
              len(led_b) == 1 and int(led_b[0][0]) == uid_b and flag_b_before == "2"
              and steal["reverted"] == 0 and not steal["skipped"] and not steal["failed"]
              and await mem_flag(m2) == "2",
              f"uid_b 的账本行(user_id,op,undoable,undone)={led_b}；"
              f"uid_a 跑同一 turn 的结果={json.dumps(steal, ensure_ascii=False)}\n"
              f"         uid_b 那条记忆 del_flag={flag_b_before!r} → {await mem_flag(m2)!r}"
              f"（必须仍是 '2'）")

        # ---------------- P6 undoable=False 的条目一个都不许被执行（负/正对照）----------------
        # 两条**手工**账本行，形状完全一样，只差 undoable：
        #   · 负：undoable=False → 必须进 skipped，**不执行**
        #   · 正：undoable=True  → 必须真执行（证明「没执行」不是因为回退整体失灵）
        t4 = MARK + "-t4"
        async with async_session_factory() as db:
            for idx, (flag, nid) in enumerate([(False, n2), (True, n3)], start=1):
                db.add(AiAgentOpLog(
                    user_id=uid_a, session_id=SESSION, turn_id=t4, op_index=idx,
                    tool="note_manage", action="delete", op=OP_SOFT_DELETE,
                    target_table="note", target_ids=[nid],
                    undoable=flag, reason="" if flag else "not_declared",
                ))
            await db.commit()
        async with async_session_factory() as db:
            out4 = await rollback_service.rollback_turn(db, uid_a, SESSION, t4)
            await db.commit()
        check("P6", "undoable=False 的条目**一个都没执行**（负对照跳过 / 正对照照撤）",
              out4["reverted"] == 1 and len(out4["skipped"]) == 1
              and out4["skipped"][0]["tool"] == "note_manage"
              and out4["skipped"][0]["reason"] == "not_declared"
              and bool(out4["skipped"][0]["reasonText"])
              and await note_flag(n2) == "0" and await note_flag(n3) == "2",
              f"结果={json.dumps(out4, ensure_ascii=False)}\n"
              f"         负对照 n2.del_flag={await note_flag(n2)!r}（必须 '0'=没被撤）；"
              f"正对照 n3.del_flag={await note_flag(n3)!r}（必须 '2'=真撤了）")

        # ---------------- P7 真实路径：题库删除 → 账本记「快照整树恢复」→ 回退把数据拿回来 ----------
        # ⚠️ 2026-10-20 口径变更：原先这里断言「题库物理删、本轮不做回退 → 账本记
        #    missing_soft_delete、回退只跳过」。现在题库删除**真的能回退**了
        #    （删除前抓数据快照，回退时按原主键整树重插，见 `bank_tree_snapshot`），
        #    所以断言反过来：账本必须记 `undoable=True` + `op=restore_tree`，
        #    回退必须 `reverted>=1`，且**题库与它的题目都要回来**。
        t5 = MARK + "-t5"
        q_before = int(await s1(
            "SELECT count(*) FROM question_main WHERE bank_id = :i", i=bank_id) or 0)
        async with async_session_factory() as db:
            r5 = await run_write_tool(db, "bank_manage",
                                      {"action": "delete", "bank_id": bank_id}, uid_a, t5)
        led5 = await op_rows(t5)
        bank_gone = int(await s1("SELECT count(*) FROM question_bank WHERE id = :i",
                                 i=bank_id) or 0)
        q_gone = int(await s1(
            "SELECT count(*) FROM question_main WHERE bank_id = :i", i=bank_id) or 0)
        async with async_session_factory() as db:
            out5 = await rollback_service.rollback_turn(db, uid_a, SESSION, t5)
            await db.commit()
        bank_back = int(await s1("SELECT count(*) FROM question_bank WHERE id = :i",
                                 i=bank_id) or 0)
        q_back = int(await s1(
            "SELECT count(*) FROM question_main WHERE bank_id = :i", i=bank_id) or 0)
        check("P7", "题库删除：账本记「快照整树恢复」，回退把题库**和题目**一起拿回来",
              r5.get("success") is True and bank_gone == 0 and len(led5) == 1
              and led5[0][5] is True and led5[0][2] == "restore_tree"
              and out5["reverted"] >= 1 and not out5["failed"]
              and bank_back == 1 and q_back == q_before,
              f"删除后 bank={bank_gone} 题={q_gone}（删前 {q_before}）"
              f"账本(tool,action,op,table,ids,undoable,reason)={led5[0][:7] if led5 else None}\n"
              f"         回退后 bank={bank_back} 题={q_back}；"
              f"回退结果={json.dumps(out5, ensure_ascii=False)}")
        # ⚠️ 题库已被回退恢复，收尾时它**还在**，所以照常留在 `ids` 待删清单里
        #    —— 原来这里写的是「已被物理删掉，从登记表里摘掉」，现在不成立了。

        # ---------------- P7b 快照不可用时**如实拒绝**（负对照）----------------
        # 防「声明了 restore_tree 却没有快照 → 回退时假装成功」。构造一条 before 为空的账本行。
        t5b = MARK + "-t5b"
        async with async_session_factory() as db:
            # ⚠️ 用别名 import：直接 `from ... import AiAgentOpLog` 会在**函数作用域**里
            #    新建一个同名局部变量，把外层（main 开头）那个 AiAgentOpLog 遮蔽掉 ——
            #    于是它上面的 `AiAgentOpLog.__table__` 报 UnboundLocalError。
            from app.models.agent_op_log import AiAgentOpLog as _OpLog
            from datetime import datetime as _dt

            db.add(_OpLog(
                user_id=uid_a, session_id=SESSION, turn_id=t5b, op_index=1,
                tool="bank_manage", action="delete", op="restore_tree",
                target_table="question_bank", target_ids=[999999], before=None,
                undoable=True, reason="", create_time=_dt.now(),
            ))
            await db.commit()
        async with async_session_factory() as db:
            out5b = await rollback_service.rollback_turn(db, uid_a, SESSION, t5b)
            await db.commit()
        check("P7b", "没有快照的 restore_tree 账本行 → **判失败并说明**，绝不假装恢复成功",
              out5b["reverted"] == 0 and len(out5b["failed"]) == 1
              and "快照" in str(out5b["failed"][0].get("error") or ""),
              f"回退结果={json.dumps(out5b, ensure_ascii=False)}")

        # ---------------- P8 账本与数据**同事务**（决定「哪条 commit 路径会落账本」）----------------
        t6 = MARK + "-t6"
        async with async_session_factory() as db:
            await run_write_tool(db, "note_manage",
                                 {"action": "delete", "note_id": n4}, uid_a, t6, commit=False)
            own = int(await db.scalar(text(
                "SELECT count(*) FROM ai_agent_op_log WHERE session_id = :s AND turn_id = :t"),
                {"s": SESSION, "t": t6}) or 0)
            flag_in_tx = await db.scalar(text("SELECT del_flag FROM note WHERE note_id = :i"),
                                         {"i": n4})
            await db.rollback()          # 模拟「请求没提交就结束了」
        other = int(await s1(
            "SELECT count(*) FROM ai_agent_op_log WHERE session_id = :s AND turn_id = :t",
            s=SESSION, t=t6) or 0)
        flag_after_rb = await note_flag(n4)
        left_after_rb = int(await s1(
            "SELECT count(*) FROM ai_agent_op_log WHERE session_id = :s AND turn_id = :t",
            s=SESSION, t=t6) or 0)
        check("P8", "账本行**跟着数据同一个事务**：未提交时别的会话看不到；一起回滚则一起消失"
                    "（所以 api 链路靠 `run_agent_stream` 那句显式 commit 落库）",
              own == 1 and flag_in_tx == "2" and other == 0
              and flag_after_rb == "0" and left_after_rb == 0,
              f"本会话可见={own}（同会话内 del_flag={flag_in_tx!r}）另一会话可见={other}（必须 0）\n"
              f"         回滚后 del_flag={flag_after_rb!r}（必须 '0'）账本残留={left_after_rb}（必须 0）")

        # ---------------- P9 题目标记：add（新造→删掉）与 remove（物理删→插回）----------------
        t7 = MARK + "-t7"
        async with async_session_factory() as db:
            r7 = await run_write_tool(db, "question_flag_manage",
                                      {"action": "add", "flag_type": "favorite",
                                       "question_id": q1, "notes": MARK + "-fav1"}, uid_a, t7)
        rec1 = int(await s1("SELECT favorite_id FROM user_question_favorite WHERE user_id = :u"
                            " AND question_id = :q", u=uid_a, q=q1) or 0)
        ids["fav"].append(rec1)
        led7 = await op_rows(t7)
        async with async_session_factory() as db:
            out7 = await rollback_service.rollback_turn(db, uid_a, SESSION, t7)
            await db.commit()
        left1 = int(await s1("SELECT count(*) FROM user_question_favorite WHERE user_id = :u"
                             " AND question_id = :q", u=uid_a, q=q1) or 0)
        check("P9", "标记 add（新建那条）→ 回退把它删掉（delete_record）",
              r7.get("success") is True and rec1 > 0 and len(led7) == 1
              and led7[0][2] == "delete_record" and out7["reverted"] == 1 and left1 == 0,
              f"回执 created={r7.get('created')} recordId={rec1} 账本 op={led7[0][2] if led7 else None}\n"
              f"         回退={json.dumps(out7, ensure_ascii=False)} 该题收藏剩余={left1}（必须 0）")

        t8 = MARK + "-t8"
        t9 = MARK + "-t9"
        async with async_session_factory() as db:
            await run_write_tool(db, "question_flag_manage",
                                 {"action": "add", "flag_type": "favorite",
                                  "question_id": q2, "notes": MARK + "-fav2"}, uid_a, t8)
        rec2 = int(await s1("SELECT favorite_id FROM user_question_favorite WHERE user_id = :u"
                            " AND question_id = :q", u=uid_a, q=q2) or 0)
        ids["fav"].append(rec2)
        async with async_session_factory() as db:
            r9 = await run_write_tool(db, "question_flag_manage",
                                      {"action": "remove", "flag_type": "favorite",
                                       "record_id": rec2}, uid_a, t9)
        led9 = await op_rows(t9)
        async with async_session_factory() as db:
            out9 = await rollback_service.rollback_turn(db, uid_a, SESSION, t9)
            await db.commit()
        back = await rows("SELECT favorite_id, notes, favorite_status FROM user_question_favorite"
                          " WHERE user_id = :u AND question_id = :q", u=uid_a, q=q2)
        ids["fav"] += [int(r[0]) for r in back]
        check("P9b", "标记 remove（**物理删**）→ 回退按改前值插回一行（备注等字段还在）",
              r9.get("success") is True and len(led9) == 1 and led9[0][2] == "insert_record"
              and out9["reverted"] == 1 and len(back) == 1
              and back[0][1] == MARK + "-fav2" and int(back[0][2] or 0) == 1,
              f"删除回执 success={r9.get('success')} 账本 op={led9[0][2] if led9 else None}\n"
              f"         回退={json.dumps(out9, ensure_ascii=False)} 插回的行={back}"
              f"（notes 必须是 {MARK}-fav2、favorite_status=1）")

        # ---------------- P11 note update：改前值留存 + 写回（restore_fields 执行路径）----------------
        # 这一条同时守两件事：
        #   ① 工具塞进信封的旧值**没有泄漏到回执**（泄漏出去就会随 tool_result 事件进界面、
        #      也进 ToolMessage 回灌给模型 —— 那是「上一轮的旧值」当上下文喂模型）；
        #   ② `restore_fields` 这条逆操作**真的被走通**（P6 用的是 soft_delete，走不到它）。
        t10 = MARK + "-t10"
        old_title = MARK + "-删除后回退"
        old_body = MARK + "正文-删除后回退"
        async with async_session_factory() as db:
            r10 = await run_write_tool(db, "note_manage",
                                       {"action": "update", "note_id": n1,
                                        "title": MARK + "-改过标题",
                                        "content": MARK + "正文-改过"}, uid_a, t10)
        title_now = await s1("SELECT title FROM note WHERE note_id = :i", i=n1)
        led10 = await op_rows(t10)
        before10 = json.loads(led10[0][8]) if led10 and led10[0][8] else {}
        check("P11", "note update：账本留下**改前值**，且信封里的私有键**没有泄漏**到回执/模型",
              r10.get("success") is True and UNDO_BEFORE_KEY not in r10
              and title_now == MARK + "-改过标题" and len(led10) == 1
              and led10[0][2] == OP_RESTORE_FIELDS
              and before10.get("title") == old_title and before10.get("content") == old_body,
              f"回执里有 {UNDO_BEFORE_KEY} 吗={UNDO_BEFORE_KEY in r10}（必须 False）"
              f"改后标题={title_now!r}\n"
              f"         账本 op={led10[0][2] if led10 else None} before={before10}")
        async with async_session_factory() as db:
            out10 = await rollback_service.rollback_turn(db, uid_a, SESSION, t10)
            await db.commit()
        after10 = await rows("SELECT title, content FROM note WHERE note_id = :i", i=n1)
        check("P11b", "回退 update：标题与正文都写回改前值（restore_fields 走到执行）",
              out10["reverted"] == 1 and after10
              and after10[0][0] == old_title and after10[0][1] == old_body,
              f"回退={json.dumps(out10, ensure_ascii=False)} 现在的行(title,content)={after10}")

        # ---------------- P12 memory clear：账本记「将被删的 id 列表」+ 逐条恢复 ----------------
        # ⚠️ 必须挑一个**一条记忆都没有**的用户来跑 `clear`：在 uid_a 上跑会把用户 30 多条
        #    真实记忆整批软删（虽然能恢复，但中途失败就是真实数据的可见性破坏）。
        #    找不到这样的用户 → 报「没测到」，**绝不**拿真实用户冒险。
        t11 = MARK + "-t11"
        uid_c = int(await s1(
            "SELECT u.user_id FROM sys_user u LEFT JOIN ai_agent_memory m ON m.user_id = u.user_id"
            " WHERE m.id IS NULL AND u.user_id <> :a AND u.user_id <> :b"
            " ORDER BY u.user_id LIMIT 1", a=uid_a, b=uid_b) or 0)
        if not uid_c:
            check("P12", "memory clear 的回退（需要一个「零记忆用户」当安全夹具）", False,
                  "库里找不到「一条记忆都没有」的用户 → **没测到**，不拿真实用户冒险")
        else:
            m3 = await add_mem(uid_c, "-clear1")
            m4 = await add_mem(uid_c, "-clear2")
            async with async_session_factory() as db:
                r11 = await run_write_tool(
                    db, "memory_manage", {"action": "clear", "memory_type": "episodic"},
                    uid_c, t11)
            led11 = await op_rows(t11)
            cleared = await rows(
                "SELECT id, del_flag FROM ai_agent_memory WHERE user_id = :u"
                " AND POSITION(:m IN content) > 0 ORDER BY id", u=uid_c, m=MARK)
            mem_ids = (json.loads(led11[0][8]) if led11 and led11[0][8] else {}).get("memoryIds")
            async with async_session_factory() as db:
                out11 = await rollback_service.rollback_turn(db, uid_c, SESSION, t11)
                await db.commit()
            back11 = await rows(
                "SELECT id, del_flag FROM ai_agent_memory WHERE user_id = :u"
                " AND POSITION(:m IN content) > 0 ORDER BY id", u=uid_c, m=MARK)
            check("P12", "memory clear：账本记下**将被删的 id 列表**（before.memoryIds），回退逐条恢复",
                  r11.get("success") is True and len(led11) == 1
                  and led11[0][0] == "memory_manage" and led11[0][2] == "restore_memory"
                  and len(cleared) == 2 and all(f[1] == "2" for f in cleared)
                  # ⚠️ 比的是**集合**不是顺序：这个列表是「将被删的 id」，顺序不在契约里
                  #    （它取自 `list_memories` 的 importance/create_time DESC 排序 = 最新在前，
                  #    而恢复逐条执行、与顺序无关）。第一版写成 `== [m3, m4]` 是**断言过强**
                  #    —— 当场红了一次，实现没问题（两条都恢复了）。
                  and isinstance(mem_ids, list) and len(mem_ids) == 2
                  and sorted(int(i) for i in mem_ids) == sorted([m3, m4])
                  and out11["reverted"] == 1 and len(back11) == 2
                  and all(f[1] == "0" for f in back11),
                  f"清空后(id,del_flag)={cleared} 账本 before={mem_ids}"
                  f"（期望集合 {sorted([m3, m4])}）\n"
                  f"         回退={json.dumps(out11, ensure_ascii=False)} 恢复后={back11}")

        # ---------------- P10 meta 事件回显 turnId（前端要靠它调回退）----------------
        # ⚠️ 只取**第一个**事件（meta）：它在任何 LLM 调用之前发出，取完就 aclose，
        #    所以本探针**不会**打模型。
        req_turn = MARK + "-t10"
        async with async_session_factory() as db:
            gen = loop.run_agent_stream(db, loop.AgentRequest(
                message=MARK + "meta 用", user_id=uid_a, session_id=SESSION,
                turn_id=req_turn, system_prompt="probe"))
            try:
                meta = json.loads(await gen.__anext__())
            except Exception as e:  # noqa: BLE001
                meta = {"error": f"{type(e).__name__}: {e}"}
            finally:
                await gen.aclose()
        check("P10", "meta 事件**原样回显** turnId（前端据此调回退）",
              isinstance(meta, dict) and meta.get("type") == "meta"
              and meta.get("turnId") == req_turn,
              f"meta.turnId={meta.get('turnId')!r}（期望 {req_turn!r}）type={meta.get('type')!r} "
              f"error={meta.get('error')}")

        auto = loop._resolve_turn_id("")
        async with async_session_factory() as db:
            empty_out = await rollback_service.rollback_turn(db, uid_a, SESSION, "")
            zero_out = await rollback_service.rollback_turn(db, 0, SESSION, MARK + "-t1")
            await db.rollback()
        check("P10b", "空 turn_id / uid=0 的回退**返回空结果**（空值绝不许当通配符扫全表）",
              auto.startswith("auto_") and len(auto) > 10
              and empty_out == {"reverted": 0, "skipped": [], "failed": [], "partial": []}
              and zero_out == {"reverted": 0, "skipped": [], "failed": [], "partial": []}
              and await note_flag(n1) == "0",
              f"_resolve_turn_id('')={auto!r}；空turn={json.dumps(empty_out, ensure_ascii=False)} "
              f"uid=0={json.dumps(zero_out, ensure_ascii=False)}")
    finally:
        # ---------------- 收尾：只按登记的精确 id + 标记清理 ----------------
        for nid in ids["fav"]:
            await q("DELETE FROM user_question_favorite WHERE favorite_id = :i", i=nid)
        await q("DELETE FROM user_question_favorite WHERE POSITION(:m IN notes) > 0", m=MARK)
        for mid in ids["memory"]:
            await q("DELETE FROM ai_agent_memory WHERE id = :i", i=mid)
        await q("DELETE FROM ai_agent_memory WHERE POSITION(:m IN content) > 0", m=MARK)
        for nid in ids["note"]:
            await q("DELETE FROM note WHERE note_id = :i", i=nid)
        await q("DELETE FROM note WHERE POSITION(:m IN title) > 0", m=MARK)
        for cid in ids["note_category"]:
            await q("DELETE FROM note_category WHERE id = :i", i=cid)
        await q("DELETE FROM note_category WHERE POSITION(:m IN name) > 0", m=MARK)
        for bid in ids["bank"]:
            await q("DELETE FROM question_bank WHERE id = :i", i=bid)
        await q("DELETE FROM question_bank WHERE POSITION(:m IN bank_name) > 0", m=MARK)
        # 账本行：按标记前缀（**不用 LIKE**，`_` 是通配符）
        await q("DELETE FROM ai_agent_op_log WHERE LEFT(turn_id, LENGTH(:m)) = :m", m=MARK)
        await q("DELETE FROM ai_agent_op_log WHERE session_id = :s", s=SESSION)
        await q("DELETE FROM ai_chat_message WHERE POSITION(:m IN content) > 0", m=MARK)
        await q("DELETE FROM ai_chat_session WHERE session_id = :s", s=SESSION)

        left = {
            "note": int(await s1("SELECT count(*) FROM note WHERE POSITION(:m IN title) > 0",
                                 m=MARK) or 0),
            "memory": int(await s1("SELECT count(*) FROM ai_agent_memory"
                                   " WHERE POSITION(:m IN content) > 0", m=MARK) or 0),
            "bank": int(await s1("SELECT count(*) FROM question_bank"
                                 " WHERE POSITION(:m IN bank_name) > 0", m=MARK) or 0),
            "fav": int(await s1("SELECT count(*) FROM user_question_favorite"
                                " WHERE POSITION(:m IN notes) > 0", m=MARK) or 0),
            "category": int(await s1("SELECT count(*) FROM note_category"
                                     " WHERE POSITION(:m IN name) > 0", m=MARK) or 0),
            "op_log": int(await s1("SELECT count(*) FROM ai_agent_op_log"
                                   " WHERE LEFT(turn_id, LENGTH(:m)) = :m", m=MARK) or 0),
        }
        check("M2", "夹具残留 0（按登记的精确 id + 标记物理删；逻辑删的行只能裸 SQL 清）",
              sum(left.values()) == 0, f"残留={left}")

        after_unmarked = await unmarked_sets()
        lost = {k: sorted(before_unmarked[k] - after_unmarked[k]) for k in before_unmarked}
        check("M3", "**用户自己的数据一条没少**（各表「无标记行」的 id 集合仍包含跑前那批）",
              not any(lost.values()),
              "；".join(f"{k}: {len(before_unmarked[k])}→{len(after_unmarked[k])}"
                        f"{' 丢了 ' + str(v) if v else ''}" for k, v in lost.items()))

    bad = [r for r in RESULTS if not r[2]]
    print(f"\n结果：{len(RESULTS) - len(bad)}/{len(RESULTS)} 通过"
          + ("" if not bad else f"；红：{', '.join(r[0] for r in bad)}"))
    return 0 if not bad else 1


async def _noop(*args, **kwargs):
    """替换 `memory_hook.record_tool_memory`（见模块 docstring）"""
    return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
