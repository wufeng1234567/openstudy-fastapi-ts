# -*- coding: utf-8 -*-
"""子代理工具集探针 —— 零 DB、零网络、零 LLM

复现「知识库专家创建知识库失败」时子代理**实际拿到的工具集**：
验证 kb 子代理的 tool_defs 是否真的含 knowledge_base_manage（等 3 个）。

用法：
    .venv/Scripts/python.exe tests/_probe_subagent_tools.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


class _RecLLM:
    """记录 bind_tools 收到的工具名，不倒腾网络"""
    def __init__(self):
        self.bound = None

    def bind_tools(self, tool_defs):
        self.bound = [d.get("function", {}).get("name") for d in tool_defs]
        return self

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content="done")


async def run_probe() -> int:
    from app.services.ai.agent.registry import ensure_tools_loaded, registry
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import orchestrator
    from app.services.ai.agent.sub_agent import run_sub_agent

    ensure_tools_loaded()
    all_names = set(registry.names())

    check("ST-01", "注册表含 knowledge_base_manage", "knowledge_base_manage" in all_names, str(sorted(all_names)))

    kb = roles_mod.OFFICIAL_ROLES["kb"]
    ex_kb = orchestrator.compute_exclude(kb, all_tool_names=all_names, user_disabled=set())
    # 关键断言：kb 自己的工具**绝不在**排除集里
    check(
        "ST-02",
        "kb 白名单工具不被排除",
        not (set(kb.tools) & ex_kb),
        f"被误排除={sorted(set(kb.tools) & ex_kb)}",
    )

    rec = _RecLLM()
    try:
        await run_sub_agent(
            object(), user_id=1, role_spec=kb, task="create a kb named cpp",
            llm=rec, excluded_tools=ex_kb,
        )
    except Exception as e:  # noqa: BLE001
        check("ST-03", "run_sub_agent 不抛异常", False, str(e))

    names = rec.bound or []
    check("ST-03", "子代理绑定了工具（非空）", bool(names), str(names))
    check(
        "ST-04",
        "子代理拿到 knowledge_base_manage",
        "knowledge_base_manage" in names,
        str(names),
    )
    check(
        "ST-05",
        "子代理拿到 knowledge_ingest / knowledge_search",
        {"knowledge_ingest", "knowledge_search"}.issubset(set(names)),
        str(names),
    )

    print("\n---- 子代理工具集探针 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS)-len(red)} 通过；红的={[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
