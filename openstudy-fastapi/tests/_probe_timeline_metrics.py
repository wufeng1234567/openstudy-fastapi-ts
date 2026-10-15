# -*- coding: utf-8 -*-
"""时间线快照「会话执行统计持久化」探针 —— 连 DB，但只碰 probe 专属会话，零 LLM 成本

验证 bug 修复：底部状态条（N 轮 M 步 / LLM x ms）刷新后不丢 —— 靠把会话累计
metrics 随 timeline 快照一起存、加载时读回。

覆盖：
  1. 存「带 metrics」→ 读回 messages + metrics（新格式）
  2. 兼容旧格式：payload 是纯数组 → 读回 messages，metrics=None（老会话不倒退）
  3. 越权：他人 user_id 读不到
  4. 覆盖写：同会话二次保存以最新为准

用法
----
    .venv/Scripts/python.exe tests/_probe_timeline_metrics.py     # 全绿退出码 0
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_UID = 2_000_900_101
PROBE_UID_OTHER = 2_000_900_102
PROBE_SID = "probe_timeline_metrics_sid"

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def _cleanup():
    from sqlalchemy import delete
    from app.database import async_session_factory, engine
    from app.models.ai_chat import AiAgentTimeline

    try:
        async with async_session_factory() as db:
            await db.execute(delete(AiAgentTimeline).where(AiAgentTimeline.session_id == PROBE_SID))
            await db.commit()
    finally:
        await engine.dispose()


async def run_probe() -> int:
    from app.database import register_all_models

    register_all_models()
    from app.services.ai import conversation_service as cs

    await _cleanup()

    # ---- 1. 带 metrics 存取 ----
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}]
    metrics = {"rounds": 3, "steps": 5, "llmMs": 1234, "toolMs": 56, "ftSum": 900, "ftSamples": 3}
    await cs.save_agent_timeline(PROBE_UID, PROBE_SID, msgs, metrics)
    got = await cs.get_agent_timeline(PROBE_UID, PROBE_SID)
    check("TM-01", "读回 messages", got.get("messages") == msgs, str(got.get("messages")))
    check("TM-02", "读回 metrics", got.get("metrics") == metrics, str(got.get("metrics")))
    check("TM-03", "返回结构含 messages/metrics 两键", set(got.keys()) >= {"messages", "metrics"}, str(set(got.keys())))

    # ---- 3. 越权 ----
    other = await cs.get_agent_timeline(PROBE_UID_OTHER, PROBE_SID)
    check("TM-04", "他人读不到（空 messages + 无 metrics）", other == {"messages": [], "metrics": None}, str(other))

    # ---- 2. 旧格式兼容（手工写一份纯数组 payload）----
    from app.database import async_session_factory
    from app.models.ai_chat import AiAgentTimeline
    from datetime import datetime

    async with async_session_factory() as db:
        row = await db.get(AiAgentTimeline, PROBE_SID)
        row.payload = json.dumps([{"role": "user", "content": "legacy"}], ensure_ascii=False)
        row.update_time = datetime.now()
        await db.commit()
    legacy = await cs.get_agent_timeline(PROBE_UID, PROBE_SID)
    check("TM-05", "旧数组格式 → messages 读回", legacy.get("messages") == [{"role": "user", "content": "legacy"}], str(legacy.get("messages")))
    check("TM-06", "旧数组格式 → metrics 为 None（不倒退）", legacy.get("metrics") is None, str(legacy.get("metrics")))

    # ---- 4. 覆盖写以最新为准 ----
    await cs.save_agent_timeline(PROBE_UID, PROBE_SID, [{"role": "user", "content": "v2"}], {"rounds": 9})
    latest = await cs.get_agent_timeline(PROBE_UID, PROBE_SID)
    check("TM-07", "覆盖写：messages 为最新", latest["messages"] == [{"role": "user", "content": "v2"}], str(latest["messages"]))
    check("TM-08", "覆盖写：metrics 为最新", latest["metrics"] == {"rounds": 9}, str(latest["metrics"]))

    # ---- 5. 无 metrics 保存（回退链路会传 None 的情形）----
    await cs.save_agent_timeline(PROBE_UID, PROBE_SID, [{"role": "user", "content": "nometrics"}], None)
    nom = await cs.get_agent_timeline(PROBE_UID, PROBE_SID)
    check("TM-09", "不传 metrics → metrics=None", nom["metrics"] is None, str(nom["metrics"]))
    check("TM-10", "不传 metrics → messages 正常", nom["messages"] == [{"role": "user", "content": "nometrics"}], str(nom["messages"]))

    await _cleanup()
    print("\n---- 时间线统计持久化探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
