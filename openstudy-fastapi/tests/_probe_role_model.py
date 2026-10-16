# -*- coding: utf-8 -*-
"""专家模型覆盖探针 —— 连 DB（probe 专属 uid），零 LLM 成本

验证「给官方专家挑模型」（用户 × 专家 的 model 覆盖）：
  1. `set_role_model` → `role_model_map` 往返（写入能读回）
  2. 空模型 = 清空覆盖（map 里不再有该 key）
  3. 清空**不会**删掉 disabled=1 的行（关闭状态与模型覆盖互不影响）
  4. set_role_disabled 也不动 model 覆盖

用法
----
    .venv/Scripts/python.exe tests/_probe_role_model.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_UID = 2_000_900_302

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

    await _cleanup()

    # ---- 1. round-trip ----
    check("RM-01", "默认无模型覆盖（空 map）", await svc.role_model_map(PROBE_UID) == {}, str(await svc.role_model_map(PROBE_UID)))
    await svc.set_role_model(PROBE_UID, "note", "deepseek-v4-pro")
    check(
        "RM-02",
        "set_role_model 后 role_model_map 读回",
        await svc.role_model_map(PROBE_UID) == {"note": "deepseek-v4-pro"},
        str(await svc.role_model_map(PROBE_UID)),
    )
    await svc.set_role_model(PROBE_UID, "bank", "deepseek-flash")
    check(
        "RM-03",
        "第二个专家的覆盖不干扰第一个",
        await svc.role_model_map(PROBE_UID) == {"note": "deepseek-v4-pro", "bank": "deepseek-flash"},
        str(await svc.role_model_map(PROBE_UID)),
    )

    # ---- 2. 空模型 = 清空（且只清 model，不动 disabled）----
    await svc.set_role_disabled(PROBE_UID, "bank", 1)
    check("RM-04", "先关掉 bank（disabled=1）", await svc.disabled_role_keys(PROBE_UID) == {"bank"}, str(await svc.disabled_role_keys(PROBE_UID)))
    await svc.set_role_model(PROBE_UID, "bank", "")
    check(
        "RM-05",
        "空 model 清空覆盖（map 不再有 bank）",
        "bank" not in await svc.role_model_map(PROBE_UID),
        str(await svc.role_model_map(PROBE_UID)),
    )
    check(
        "RM-06",
        "清空 model 不删 disabled=1 的行（bank 仍是关闭的）",
        await svc.disabled_role_keys(PROBE_UID) == {"bank"},
        str(await svc.disabled_role_keys(PROBE_UID)),
    )

    # ---- 3. disabled upsert 不动 model 覆盖 ----
    await svc.set_role_disabled(PROBE_UID, "note", 1)
    check(
        "RM-07",
        "set_role_disabled(1) 不清掉 note 的模型覆盖",
        (await svc.role_model_map(PROBE_UID)).get("note") == "deepseek-v4-pro",
        str(await svc.role_model_map(PROBE_UID)),
    )
    await svc.set_role_disabled(PROBE_UID, "note", 0)
    check(
        "RM-08",
        "set_role_disabled(0) 不清掉有覆盖的行（模型覆盖必须保留）",
        (await svc.role_model_map(PROBE_UID)).get("note") == "deepseek-v4-pro"
        and "note" not in await svc.disabled_role_keys(PROBE_UID),
        f"map={await svc.role_model_map(PROBE_UID)} closed={await svc.disabled_role_keys(PROBE_UID)}",
    )

    # ---- 4. 批量「全选开启」同样不能抹掉覆盖 ----
    await svc.set_role_disabled(PROBE_UID, "bank", 1)
    await svc.set_all_roles_disabled(PROBE_UID, ["bank", "note"], 0)
    check(
        "RM-09",
        "set_all_roles_disabled(0) 保留有覆盖的行（note 覆盖还在）",
        (await svc.role_model_map(PROBE_UID)).get("note") == "deepseek-v4-pro",
        str(await svc.role_model_map(PROBE_UID)),
    )
    await svc.set_role_disabled(PROBE_UID, "bank", 1)
    await svc.set_role_disabled(PROBE_UID, "bank", 0)
    check(
        "RM-10",
        "无覆盖的行关→开仍走稀疏还原（bank 行被删干净）",
        "bank" not in await svc.role_model_map(PROBE_UID)
        and "bank" not in await svc.disabled_role_keys(PROBE_UID),
        f"map={await svc.role_model_map(PROBE_UID)} closed={await svc.disabled_role_keys(PROBE_UID)}",
    )

    await _cleanup()
    print("\n---- 专家模型覆盖探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
