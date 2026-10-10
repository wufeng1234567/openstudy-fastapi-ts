# -*- coding: utf-8 -*-
"""专家开关探针 —— 连 DB（probe 专属 uid），零 LLM 成本

验证用户 2026-10-10 的「可用工具 → 专家」改造：
  1. 专家开关 service：默认全开、关闭后读回、重新开启（稀疏删行）
  2. `resolve_role(disabled_role_keys=...)`：显式点名被关专家 → 忽略；关键词路由跳过被关专家
  3. `render_sub_agents_briefing(disabled_keys=...)`：被关专家不进通讯录
  4. `renderable_sub_agents(disabled_keys=...)`：被关专家不可委派

用法
----
    .venv/Scripts/python.exe tests/_probe_agent_expert.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_UID = 2_000_900_301

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def _cleanup():
    from sqlalchemy import delete
    from app.database import async_session_factory, engine
    from app.models.agent_role_pref import AiAgentRolePref

    try:
        async with async_session_factory() as db:
            await db.execute(delete(AiAgentRolePref).where(AiAgentRolePref.user_id == PROBE_UID))
            await db.commit()
    finally:
        await engine.dispose()


async def run_probe() -> int:
    from app.database import register_all_models

    register_all_models()
    from app.services.ai.agent import agent_role_pref_service as svc
    from app.services.ai.agent import orchestrator
    from app.services.ai.agent import roles as roles_mod

    await _cleanup()

    # ---- 1. service ----
    check("EX-01", "默认全部专家开启（无行）", await svc.disabled_role_keys(PROBE_UID) == set())
    await svc.set_role_disabled(PROBE_UID, "note", 1)
    check("EX-02", "关闭 note → 读到 note", await svc.disabled_role_keys(PROBE_UID) == {"note"}, str(await svc.disabled_role_keys(PROBE_UID)))
    await svc.set_role_disabled(PROBE_UID, "note", 0)
    check("EX-03", "重新开启 note → 稀疏删行", await svc.disabled_role_keys(PROBE_UID) == set())
    await svc.set_all_roles_disabled(PROBE_UID, ["bank", "kb"], 1)
    check("EX-04", "批量关闭 bank/kb", await svc.disabled_role_keys(PROBE_UID) == {"bank", "kb"}, str(await svc.disabled_role_keys(PROBE_UID)))
    await _cleanup()

    # ---- 2. resolve_role 过滤 ----
    r = orchestrator.resolve_role(role="bank", message="", disabled_role_keys={"bank"})
    check("EX-05", "点名被关的 bank → 不选它（退 general）", r.key == "general", r.key)

    r = orchestrator.resolve_role(role="bank", message="", disabled_role_keys=set())
    check("EX-06", "点名未关的 bank → 命中", r.key == "bank", r.key)

    # 关键词路由：消息命中 note，但 note 被关 → 不应路由到 note
    r = orchestrator.resolve_role(role="", message="帮我整理笔记", disabled_role_keys={"note"})
    check("EX-07", "关键词命中 note 但 note 被关 → 不选 note", r.key != "note", r.key)

    r = orchestrator.resolve_role(role="", message="帮我整理笔记", disabled_role_keys=set())
    check("EX-08", "关键词命中 note 且未关 → 命中 note", r.key == "note", r.key)

    # ---- 3. 通讯录过滤 ----
    brief_all = roles_mod.render_sub_agents_briefing()
    check("EX-09", "通讯录默认含 bank 行", "- bank (" in brief_all, brief_all[:80])
    brief_no_bank = roles_mod.render_sub_agents_briefing(disabled_keys={"bank"})
    # ⚠️ 用「行首 - bank (」判定，别用子串 "bank"：其他专家的 capability 里可能出现
    #    "a bank"（如 stats 的 "who shared a bank with me"），子串匹配会误命中。
    check("EX-10", "关闭 bank 后通讯录不含 bank 行", "- bank (" not in brief_no_bank, brief_no_bank[:80])
    check("EX-11", "关闭 bank 后通讯录仍含 note 行", "- note (" in brief_no_bank, "")

    # ---- 4. renderable_sub_agents 过滤 ----
    subs_all = {s.key for s in roles_mod.renderable_sub_agents()}
    subs_no = {s.key for s in roles_mod.renderable_sub_agents(disabled_keys={"bank", "kb"})}
    check("EX-12", "默认可委派专家含 bank/kb", {"bank", "kb"}.issubset(subs_all), str(sorted(subs_all)))
    check("EX-13", "关闭 bank/kb 后不可委派", "bank" not in subs_no and "kb" not in subs_no, str(sorted(subs_no)))

    await _cleanup()
    print("\n---- 专家开关探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
