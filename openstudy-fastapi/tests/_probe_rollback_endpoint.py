# -*- coding: utf-8 -*-
"""一次性探针：回退的 **HTTP 层**（turnId 透传 + `POST /ai/agent/rollback`）

为什么单独写一个：`tests/_probe_rollback_turn.py` 验的是**服务层**（直调 `_prepare_tool_call`
→ `_execute_tool` → `rollback_service.rollback_turn`），它**不经过 HTTP**。而 2026-09-23 补齐的
两处恰好都在 HTTP 层：

  ① `AgentStreamRequest` / `AgentExecuteRequest` 原来**没有 `turnId` 字段** —— pydantic 默认
     忽略未知字段，前端发上来的轮次 id 被**静默丢掉**，后端只能兜一个 `auto_<hex>`；
     而轮末标记带的是前端的 `t_...` → 回退按 `t_...` 查不到账本行（表现为「点了没反应」）。
  ② `POST /ai/agent/rollback` 原来**不存在** —— 前端调它只会落进 `catch_all`，拿到
     HTTP 200 + `{code:200, data:null}` 的**假成功**（`code===200` 为真、`data` 却什么都没有）。

本探针**只打这两处**：进程内 ASGITransport（不打网络、不打模型），几十秒出红绿。

用法（必须用 .venv 的 python）：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_probe_rollback_endpoint.py

退出码：0 = 全部符合预期；1 = 有红 / 环境不足（**没测到东西**也回 1）。

⚠️ 夹具规则（本仓库出过「测试清理删光真实数据」的事故）：
  · 夹具全部挂在**合成 uid**（990001/990002）下，正文/轮次 id 带 `__probe_rb_ep__` 标记；
  · 收尾只按**本探针登记的精确 id**物理删（记忆是逻辑删，走工具的 delete 清不掉）；
  · 同时回比「无标记行一条没少」—— 那是用户自己的数据，一行都不许动。

⚠️ 别和 `tests/e2e_agent_api.py` 并发跑：它 Z1 按 `id > baseline` 数记忆行，
   本探针的夹具会短暂落进那个窗口。

⚠️ 探针换掉了 `memory_hook.record_tool_memory`（换成空实现）：每次写操作都会由它往
   **长期记忆**里落一条 episodic（内容是工具回执拼的，探针无法在写入时打标记）——
   那是另一个功能的副作用，与本探针的被测对象无关。除此外没有改动任何被测代码。
"""
import asyncio
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

# ⚠️ 必须先 `import app.main`：它把全量模型注册进 metadata（与另两个探针同一手法）
from app.main import app as fastapi_app  # noqa: E402,F401

from app.core.security import get_current_user  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.agent_op_log import AiAgentOpLog  # noqa: E402
from app.services.ai.agent import loop, memory_hook  # noqa: E402

MARK = "__probe_rb_ep__"
SESSION = "__probe_rb_ep_sess__"
TURN_A = MARK + "turn_a"
TURN_B = MARK + "turn_b"

# ⚠️ `ai_agent_memory.user_id` 有 FK → `sys_user`（PG 真约束，MySQL 上没有），
#    所以夹具用户**只能取库里已存在的 uid**（与另两个探针同一手法：取最小两个）。
#    写进去的每一行都带 `MARK` 标记，收尾按精确 id 物理删，并回比无标记行没少。
UID_A = 0
UID_B = 0

RESULTS = []


def check(cid, desc, ok, detail):
    RESULTS.append((cid, desc, bool(ok), detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {cid} {desc}")
    print(f"         {detail}")


async def one(sql, **p):
    """只读一条标量。⚠️ **不要拿它插数据** —— 这个会话关闭时会回滚（`INSERT … RETURNING`
    也会被回滚，看着拿到了 id、行其实没落库）。写用 `ins()`。"""
    async with async_session_factory() as s:
        return await s.scalar(text(sql), p)


async def ins(sql, **p):
    """插入并**提交**，返回 RETURNING 的标量（夹具专用）"""
    async with async_session_factory() as s:
        v = await s.scalar(text(sql), p)
        await s.commit()
        return v


async def allrows(sql, **p):
    async with async_session_factory() as s:
        return (await s.execute(text(sql), p)).all()


async def write(sql, **p):
    async with async_session_factory() as s:
        r = await s.execute(text(sql), p)
        await s.commit()
        return r


async def _noop(*args, **kwargs):
    """替换 `memory_hook.record_tool_memory`（见模块 docstring）"""


async def mem_flag(mem_id):
    return await one("SELECT del_flag FROM ai_agent_memory WHERE id = :i", i=mem_id)


async def ledger_rows(user_id, turn_id):
    return await allrows(
        "SELECT id, turn_id, tool, action, op, undoable, reason, undone_at "
        "FROM ai_agent_op_log WHERE user_id = :u AND turn_id = :t ORDER BY op_index, id",
        u=user_id,
        t=turn_id,
    )


async def main():
    global UID_A, UID_B
    memory_hook.record_tool_memory = _noop

    print("=" * 78)
    print("回退 HTTP 层探针：turnId 透传 + POST /ai/agent/rollback")
    print("=" * 78)

    # ---------- 环境前提 ----------
    has_log = await one(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name = 'ai_agent_op_log'"
    )
    if not has_log:
        check("E0", "账本表 ai_agent_op_log 存在（不存在则说明建表没生效）", False,
              "information_schema 里查不到这张表")
        return 1

    UID_A = int(await one("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1") or 0)
    UID_B = int(await one(
        "SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1",
        u=UID_A) or 0)
    if not UID_A or not UID_B:
        print(f"!! 库里只有一个用户（a={UID_A} b={UID_B}）→ 越权用例无法构造 → **没测到东西**，回 1")
        return 1

    # ---------- 夹具 ----------
    # ⚠️ 开跑前先扫掉**本探针自己**的历史残留：上一次跑崩在半路时夹具会留在库里，
    #    不扫的话末尾的 M1（残留=0）会把上一轮的账算到这一轮头上（红得莫名其妙 —— 实测过）。
    #    判据只用「本探针的标记」+「本探针的会话 id」，用户数据一个字节都不碰。
    await write("DELETE FROM ai_agent_memory WHERE POSITION(:m IN content) > 0", m=MARK)
    await write(
        "DELETE FROM ai_agent_op_log WHERE session_id = :s "
        "AND (POSITION(:m IN turn_id) > 0 OR LEFT(turn_id, 5) = 'auto_')",
        s=SESSION, m=MARK)

    mem_a1 = await ins(
        "INSERT INTO ai_agent_memory (user_id, memory_type, content, importance, del_flag, create_time) "
        "VALUES (:u, 'episodic', :c, 5, '0', now()) RETURNING id",
        u=UID_A, c=MARK + "记忆A1（将被 forget 后回退）")
    mem_a2 = await ins(
        "INSERT INTO ai_agent_memory (user_id, memory_type, content, importance, del_flag, create_time) "
        "VALUES (:u, 'episodic', :c, 5, '0', now()) RETURNING id",
        u=UID_A, c=MARK + "记忆A2（不带 turnId，验证 auto_ 兜底）")
    mem_b1 = await ins(
        "INSERT INTO ai_agent_memory (user_id, memory_type, content, importance, del_flag, create_time) "
        "VALUES (:u, 'episodic', :c, 5, '0', now()) RETURNING id",
        u=UID_B, c=MARK + "记忆B1（越权靶子）")
    print(f"\n夹具：uid_a={UID_A} mem_a1={mem_a1} mem_a2={mem_a2}；uid_b={UID_B} mem_b1={mem_b1}")

    # 跑前快照：无标记行（= 用户自己的数据）。**按标记筛，不按 uid 筛** ——
    # 夹具用的就是真实 uid，按 uid 排除会把那个用户的行漏出视野。
    before_mem = {r[0] for r in await allrows(
        "SELECT id FROM ai_agent_memory WHERE POSITION(:m IN content) = 0", m=MARK)}
    before_log = {r[0] for r in await allrows("SELECT id FROM ai_agent_op_log")}

    from httpx import ASGITransport, AsyncClient

    extra_log_ids = []  # 兜底（auto_）账本行的精确 id，收尾按 id 删
    fastapi_app.dependency_overrides[get_current_user] = (
        lambda: {"user_id": UID_A, "roles": [], "user_name": "probe"})
    client = AsyncClient(transport=ASGITransport(app=fastapi_app),
                         base_url="http://probe", timeout=30)
    try:
        # ================= R1 请求体模型真的收下 turnId =================
        from app.api.v1.ai import (
            AgentExecuteRequest,
            AgentStreamRequest,
            RollbackTurnBody,
        )

        s_ok = (
            "turnId" in AgentStreamRequest.model_fields
            and AgentStreamRequest(message="x", turnId=TURN_A).turnId == TURN_A
        )
        e_ok = (
            "turnId" in AgentExecuteRequest.model_fields
            and AgentExecuteRequest(tool="t", turnId=TURN_A).turnId == TURN_A
        )
        check("R1", "两条链路的请求体都**声明**了 turnId（不声明就是静默丢掉 → 回退空转）",
              s_ok and e_ok,
              f"AgentStreamRequest={ '有' if 'turnId' in AgentStreamRequest.model_fields else '缺' }；"
              f"AgentExecuteRequest={ '有' if 'turnId' in AgentExecuteRequest.model_fields else '缺' }")

        rbody = set(RollbackTurnBody.model_fields)
        check("R2", "回退请求体只有 {sessionId, turnId}（**不收 userId** —— 收一个就是 IDOR 入口）",
              rbody == {"sessionId", "turnId"}, f"RollbackTurnBody.model_fields={sorted(rbody)}")

        # ================= R3 预览发票据（顺带证明 preview 仍可用）=================
        params_forget = {"action": "forget", "memory_id": mem_a1}
        r = await client.post("/ai/agent/preview", json={
            "tool": "memory_manage", "params": params_forget,
            "sessionId": SESSION, "autoConfirm": True, "turnId": TURN_A,
        })
        pb = r.json()
        ticket = str(pb.get("confirmTicket") or "")
        check("R3", "PREVIEW 下发非空 confirmTicket（破坏性动作必须先拿票）",
              r.status_code == 200 and bool(ticket),
              f"HTTP={r.status_code} 票据长度={len(ticket)} preview={json.dumps(pb.get('preview'), ensure_ascii=False)[:120]}")

        # ================= R4 execute 的 turnId 逐字进账本（核心修复）=================
        r = await client.post("/ai/agent/execute", json={
            "tool": "memory_manage", "params": params_forget,
            "sessionId": SESSION, "turnId": TURN_A,
            "autoConfirm": True, "confirmed": True, "confirmTicket": ticket,
        })
        eb = r.json()
        rows = await ledger_rows(UID_A, TURN_A)
        row = rows[0] if rows else None
        # ⚠️ 明细串**不能**假设 row 一定存在：这一条恰恰要在「一行都没记上」时变红，
        #    而 `row[1]` 会先抛 TypeError —— 探针自己崩掉就变成「没测到」，不是红。
        rowdesc = (f"turn_id={row[1]!r} tool={row[2]} action={row[3]} op={row[4]} undoable={row[5]}"
                   if row else "（这一轮**一条账本行都没有**）")
        check("R4", "EXECUTE 下发的 turnId **逐字**进账本（不是 auto_ 兜底）",
              r.status_code == 200 and eb.get("success") is not False and len(rows) == 1
              and row is not None and row[1] == TURN_A
              and row[2] == "memory_manage" and row[3] == "forget" and row[4] == "restore_memory"
              and row[5] is True,
              f"HTTP={r.status_code} success={eb.get('success')} 账本行={len(rows)} {rowdesc}")

        # 工具真的删了（del_flag='2'）—— 否则「回退成功」可能是假的
        flag_after_exec = await mem_flag(mem_a1)
        check("R5", "正向对照：execute 之后那条记忆**确实**被逻辑删了（del_flag='2'）",
              flag_after_exec == "2", f"del_flag={flag_after_exec!r}")

        # ================= R6 端点：回退这一轮 =================
        r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION, "turnId": TURN_A})
        rb = r.json()
        data = rb.get("data") or {}
        flag_after_rb = await mem_flag(mem_a1)
        check("R6", "POST /ai/agent/rollback → {reverted:1}，记忆 del_flag 回 '0'，skipped 为空",
              r.status_code == 200 and rb.get("code") == 200
              and data.get("reverted") == 1 and (data.get("skipped") or []) == []
              and flag_after_rb == "0",
              f"HTTP={r.status_code} data={json.dumps(data, ensure_ascii=False)} "
              f"del_flag={flag_after_rb!r}")

        # ================= R7 假 200 负对照（证明 R6 的判据不是恒真）=================
        r = await client.post("/ai/agent/rollbac", json={"sessionId": SESSION, "turnId": TURN_A})
        nb = r.json()
        check("R7", "负对照：路径打错一个字母 → catch_all 假 200，且 **data 里没有 reverted**"
                    "（R6 判的就是这个形状，所以 R6 不是恒真）",
              r.status_code == 200 and nb.get("code") == 200
              and nb.get("data") is None and "reverted" not in json.dumps(nb),
              f"打错路径 → HTTP={r.status_code} body={json.dumps(nb, ensure_ascii=False)[:110]}")

        # ================= R8 幂等 =================
        r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION, "turnId": TURN_A})
        rb2 = r.json()
        d2 = rb2.get("data") or {}
        check("R8", "再点一次 → reverted=0（幂等），data 形状仍在（调用方能区分「撤过了」与「接口没了」）",
              rb2.get("code") == 200 and d2.get("reverted") == 0 and (await mem_flag(mem_a1)) == "0",
              f"第二次 data={json.dumps(d2, ensure_ascii=False)} del_flag={await mem_flag(mem_a1)!r}")

        # ================= R9 缺 turnId → 400（不许拿空值当通配符）=================
        r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION, "turnId": ""})
        b9 = r.json()
        r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION})
        b9b = r.json()
        check("R9", "turnId 为空 / 根本没给 → code=400（空值绝不当通配符）",
              b9.get("code") == 400 and b9b.get("code") == 400,
              f"空串 → {json.dumps(b9, ensure_ascii=False)}；缺字段 → {json.dumps(b9b, ensure_ascii=False)}")

        # ================= R10 越权：别人的轮次撤不动 =================
        # 给 uid_b 造一条「可撤销」的账本行 + 一行已软删的记忆（模拟 B 自己删过）
        await write("UPDATE ai_agent_memory SET del_flag='2' WHERE id = :i", i=mem_b1)
        async with async_session_factory() as s:
            s.add(AiAgentOpLog(
                user_id=UID_B, session_id=SESSION, turn_id=TURN_B, op_index=1,
                tool="memory_manage", action="forget", op="restore_memory",
                target_table="ai_agent_memory", target_ids=[mem_b1],
                undoable=True, reason="", create_time=datetime.now(),
            ))
            await s.commit()
        r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION, "turnId": TURN_B})
        b10 = r.json()
        d10 = b10.get("data") or {}
        b_rows = await ledger_rows(UID_B, TURN_B)
        check("R10", "越权：以 uid_a 身份回退 **uid_b 的轮次** → reverted=0、B 的行仍是 '2'、B 的账本行仍未撤",
              b10.get("code") == 200 and d10.get("reverted") == 0
              and (await mem_flag(mem_b1)) == "2"
              and b_rows and b_rows[0][7] is None,
              f"data={json.dumps(d10, ensure_ascii=False)} B.del_flag={await mem_flag(mem_b1)!r} "
              f"B.undone_at={b_rows[0][7] if b_rows else 'n/a'}")

        # ================= R11 不带 turnId 时兜底 auto_（R4 不是恒真的反向对照）=================
        params2 = {"action": "forget", "memory_id": mem_a2}
        r = await client.post("/ai/agent/preview", json={
            "tool": "memory_manage", "params": params2,
            "sessionId": SESSION, "autoConfirm": True})
        ticket2 = str((r.json().get("confirmTicket") or ""))
        r = await client.post("/ai/agent/execute", json={
            "tool": "memory_manage", "params": params2,
            "sessionId": SESSION, "autoConfirm": True, "confirmed": True,
            "confirmTicket": ticket2,
        })
        eb2 = r.json()
        auto_rows = await allrows(
            "SELECT id, turn_id FROM ai_agent_op_log "
            "WHERE user_id = :u AND LEFT(turn_id, 5) = 'auto_' ORDER BY id DESC LIMIT 1",
            u=UID_A)
        auto_tid = auto_rows[0][1] if auto_rows else ""
        # 兜底 id **不带标记**，所以要单独登记它的账本行 id，收尾按精确 id 删
        if auto_rows:
            extra_log_ids.append(auto_rows[0][0])
        check("R11", "反向对照：不带 turnId → 后端兜底 `auto_<hex>`（说明 R4 的精确匹配不是恒真），"
                     "且这个兜底 id 也能回退成功",
              eb2.get("success") is not False and auto_tid.startswith("auto_")
              and (await mem_flag(mem_a2)) == "2",
              f"success={eb2.get('success')} 兜底 turn_id={auto_tid!r} del_flag={await mem_flag(mem_a2)!r}")
        if auto_tid.startswith("auto_"):
            r = await client.post("/ai/agent/rollback", json={"sessionId": SESSION, "turnId": auto_tid})
            d11 = (r.json().get("data") or {})
            check("R12", "用兜底 id 回退 → reverted=1，记忆回 '0'（兜底不是死路）",
                  d11.get("reverted") == 1 and (await mem_flag(mem_a2)) == "0",
                  f"data={json.dumps(d11, ensure_ascii=False)} del_flag={await mem_flag(mem_a2)!r}")

        # ================= R13 stream 链路的 turnId 也真的透传（不需要模型）=================
        captured = {}

        async def _fake_stream(db, req):
            captured["turn_id"] = getattr(req, "turn_id", None)
            captured["session_id"] = getattr(req, "session_id", None)
            yield "data: {\"type\":\"meta\"}\n\n"

        real_stream = loop.run_agent_stream
        loop.run_agent_stream = _fake_stream
        try:
            r = await client.post("/ai/agent/stream", json={
                "message": "x", "sessionId": SESSION, "turnId": TURN_A})
            await r.aread()
            got = captured.get("turn_id")
            r = await client.post("/ai/agent/stream", json={"message": "x", "sessionId": SESSION})
            await r.aread()
            got_auto = captured.get("turn_id")
        finally:
            loop.run_agent_stream = real_stream
        check("R13", "STREAM 链路：请求体 turnId 原样到达 `AgentRequest.turn_id`"
                     "（不传时是空串 —— 负对照）",
              got == TURN_A and got_auto == "",
              f"带 turnId → {got!r}；不带 → {got_auto!r}"
              "（注：`auto_` 兜底发生在 `run_agent_stream` **内部**，本桩把它替换了，"
              "所以这里只能观察到「请求没带就是空串」；兜底本身由 R11 端到端覆盖）")
    finally:
        fastapi_app.dependency_overrides.pop(get_current_user, None)
        await client.aclose()

    # ================= M1/M2 清理与回比 =================
    # 记忆行是逻辑删（del_flag='2'），只能裸 SQL 物理删；账本行按「本探针用过的精确轮次 id」
    # 删 —— **不许**按 uid 一把删（夹具用的就是真实用户，按 uid 删会删掉别人的账本）。
    await write("DELETE FROM ai_agent_memory WHERE id IN (:a, :b, :c)",
                a=mem_a1, b=mem_a2, c=mem_b1)
    await write(
        "DELETE FROM ai_agent_op_log WHERE session_id = :s "
        "AND (POSITION(:m IN turn_id) > 0 OR LEFT(turn_id, 5) = 'auto_')",
        s=SESSION, m=MARK)

    left_mem = await one(
        "SELECT count(*) FROM ai_agent_memory WHERE POSITION(:m IN content) > 0", m=MARK)
    left_log = await one(
        "SELECT count(*) FROM ai_agent_op_log WHERE POSITION(:m IN turn_id) > 0", m=MARK)
    auto_left = 0
    for _lid in extra_log_ids:
        auto_left += int(await one(
            "SELECT count(*) FROM ai_agent_op_log WHERE id = :i", i=_lid) or 0)
    check("M1", "夹具残留 0（记忆 + 账本，按精确 id / 标记物理删）",
          left_mem == 0 and left_log == 0 and auto_left == 0,
          f"残留记忆={left_mem} 残留账本={left_log} 兜底账本残留={auto_left}")

    # 回比**全体无标记行**（不按 uid 排除 —— 夹具就是真实 uid 的行）
    after_mem = {r[0] for r in await allrows(
        "SELECT id FROM ai_agent_memory WHERE POSITION(:m IN content) = 0", m=MARK)}
    after_log = {r[0] for r in await allrows("SELECT id FROM ai_agent_op_log")}
    check("M2", "**用户自己的数据一条没少**（无标记行 id 集合仍包含跑前那批）",
          before_mem.issubset(after_mem) and before_log.issubset(after_log),
          f"记忆 {len(before_mem)}→{len(after_mem)}；账本 {len(before_log)}→{len(after_log)}")

    bad = [r for r in RESULTS if not r[2]]
    print(f"\n结果：{len(RESULTS) - len(bad)}/{len(RESULTS)} 通过"
          + (f"；红：{[r[0] for r in bad]}" if bad else "（全绿）"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
