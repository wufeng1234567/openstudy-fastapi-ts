# -*- coding: utf-8 -*-
"""一次性验证：**真 9101 进程上的** GET/PUT /ai/agent/tools 真实往返（跑完即删）

为什么要它：`tests/_toolpref_probe.py` 是 in-process（ASGITransport + 假登录），
它证明了 app/路由/pydantic/DB 全链路，但**没经过真 token 与真 uvicorn**。
前端 API 层（tool-gate-fe-api）说它的桩编码的就是这份契约、而「真实往返」是它那侧唯一的缺口，
这里补齐：用 `/quickLogin` 白名单演示账号拿真 token，打**真 9101**，逐条打印原始 HTTP 状态 + body。

用 **guest** 账号（不是用户的 105，也不是 admin），只写一行 `ai_agent_tool_pref` 并**精确删除**，
跑前跑后整表行集合必须一致。
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import async_session_factory, engine  # noqa: E402

BASE = "http://127.0.0.1:9101"
ACCOUNT = "user2"
checks = []


def check(cid, expected, actual, ok):
    checks.append((cid, expected, actual, bool(ok)))


def show(label, r):
    body = r.text
    if len(body) > 400:
        body = body[:400] + "…"
    print(f"  {label}\n    HTTP {r.status_code}\n    {body}")


async def main() -> int:
    async with async_session_factory() as db:
        before = set(
            (r[0], r[1], r[2])
            for r in (
                await db.execute(
                    text("SELECT user_id, tool_name, disabled FROM ai_agent_tool_pref")
                )
            ).all()
        )
        uid = await db.scalar(
            text("SELECT user_id FROM sys_user WHERE user_name = :n"), {"n": ACCOUNT}
        )
    print(f"跑前 ai_agent_tool_pref 行集合 = {sorted(before)}（account={ACCOUNT} uid={uid}）")
    if uid is None:
        print("演示账号不存在，跳过")
        return 2

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/quickLogin", json={"account": ACCOUNT})
        show("POST /quickLogin", r)
        token = ((r.json() or {}).get("data") or {}).get("token")
        check("L1", "白名单账号拿到真 token", f"token={'有' if token else '无'}", bool(token))
        if not token:
            return 2
        h = {"Authorization": f"Bearer {token}"}

        r = await c.get("/ai/agent/tools", headers=h)
        show("GET /ai/agent/tools", r)
        body = r.json() or {}
        tools = body.get("tools") or []
        by_name = {((t.get("function") or {}).get("name")): t for t in tools}
        check("L2", "成功体是未包装的 {tools, actions}（无 data 外层）",
              f"keys={sorted(body.keys())}", "tools" in body and "actions" in body
              and "data" not in body)
        check("L3", "每个条目都带 int 型 disabled（0/1，非 null）",
              f"types={sorted({type(t.get('disabled')).__name__ for t in tools})} "
              f"vals={sorted({t.get('disabled') for t in tools})}",
              bool(tools) and all(isinstance(t.get("disabled"), int) for t in tools)
              and {t.get("disabled") for t in tools} <= {0, 1})
        check("L4", "被屏蔽的工具仍以整行出现（可再打开）且 function 完好",
              f"bank_manage={'有' if 'bank_manage' in by_name else '无'}",
              "bank_manage" in by_name and "parameters" in (by_name.get("bank_manage", {}).get("function") or {}))

        r = await c.put("/ai/agent/tools", headers=h, json={"tool": "note_manage", "disabled": 1})
        show("PUT /ai/agent/tools {'tool':'note_manage','disabled':1}", r)
        e = {((t.get("function") or {}).get("name")): t.get("disabled") for t in (r.json() or {}).get("tools") or []}
        check("L5", "PUT 回显与 GET 同形状，且 note_manage.disabled==1（DB 回读）",
              f"note_manage={e.get('note_manage')} keys={sorted((r.json() or {}).keys())}",
              e.get("note_manage") == 1 and "tools" in (r.json() or {}))

        r = await c.get("/ai/agent/tools", headers=h)
        e2 = {((t.get("function") or {}).get("name")): t.get("disabled") for t in (r.json() or {}).get("tools") or []}
        show("GET（独立复读）", r)
        check("L6", "独立 GET 读到 1（落库了，不只是回显）", f"note_manage={e2.get('note_manage')}",
              e2.get("note_manage") == 1)

        async with async_session_factory() as db:
            dbrow = (
                await db.execute(
                    text("SELECT disabled FROM ai_agent_tool_pref WHERE user_id = :u AND tool_name = :t"),
                    {"u": int(uid), "t": "note_manage"},
                )
            ).scalar()
        check("L7", "直连 SQL 也是 1", f"db.disabled={dbrow}", int(dbrow or 0) == 1)

        r = await c.put("/ai/agent/tools", headers=h, json={"tool": "no_such_tool__live", "disabled": 1})
        show("PUT 未知工具名", r)
        ub = r.json() or {}
        check("L8", "未知工具名 → code 400 + 无 tools 键（前端能判「没保存」）",
              f"code={ub.get('code')} msg={ub.get('msg')!r} keys={sorted(ub.keys())}",
              int(ub.get("code") or 0) == 400 and "tools" not in ub)

        r = await c.put("/ai/agent/tools", headers=h, json={"tool": "note_manage", "enable": 0})
        show("PUT 字段名写错（enable）", r)
        check("L9", "字段名写错 → HTTP 422", f"status={r.status_code}", r.status_code == 422)

        r = await c.put("/ai/agent/tools", headers=h, json={"tool": "note_manage", "disabled": 0})
        show("PUT {'tool':'note_manage','disabled':0}（打开回来）", r)
        e3 = {((t.get("function") or {}).get("name")): t.get("disabled") for t in (r.json() or {}).get("tools") or []}
        check("L10", "关得掉也开得回来（0 不等于「没传」）", f"note_manage={e3.get('note_manage')}",
              e3.get("note_manage") == 0)

    # ── 收尾：只删这次写的那一行（精确 (user_id, tool_name)）──
    async with async_session_factory() as db:
        await db.execute(
            text("DELETE FROM ai_agent_tool_pref WHERE user_id = :u AND tool_name = :t"),
            {"u": int(uid), "t": "note_manage"},
        )
        await db.commit()
        after = set(
            (r[0], r[1], r[2])
            for r in (
                await db.execute(
                    text("SELECT user_id, tool_name, disabled FROM ai_agent_tool_pref")
                )
            ).all()
        )
        left = await db.scalar(
            text("SELECT COUNT(*) FROM ai_agent_tool_pref WHERE user_id = :u"), {"u": int(uid)}
        )
    print(f"\n跑后 ai_agent_tool_pref 行集合 = {sorted(after)}（本 uid 残留 {left}）")
    check("L11", "跑前跑后整表行集合一致，且本 uid 无残留",
          f"before={sorted(before)} after={sorted(after)} left={left}",
          before == after and int(left or 0) == 0)

    print("\n---- 结果 ----")
    for cid, exp, act, ok in checks:
        print(f"  [{'通过' if ok else '失败'}] {cid} {exp}\n        实际: {act}")
    red = [c for c in checks if not c[3]]
    print(f"\n合计：{len(checks) - len(red)}/{len(checks)} 通过；红的 = {[c[0] for c in red] or '无'}")
    await engine.dispose()
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
