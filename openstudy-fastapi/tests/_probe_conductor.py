# -*- coding: utf-8 -*-
"""指挥家模式探针 —— 零 DB、零网络、零 LLM 成本

覆盖「指挥家（Orchestrator）+ 子代理（Sub-Agents）」改造（见
`docs/fastapi_v2_指挥家模式方案.md`）：
  1. 每个可委派子代理都有 capability；general 不在可委派清单
  2. `render_sub_agents_briefing()` 输出正确（含官方 + 可附加用户智能体）
  3. `delegate_task` 被 `compute_exclude` **永远排除**（防子代理递归委派）
  4. `build_agent_system_prompt(sub_agents_text=...)` 注入指挥家段与通讯录
  5. `DelegateTaskTool` 元数据 + 缺环境时 fail（不假装成功）
  6. `run_sub_agent` 用**假 LLM** 跑通：窄工具裁剪、返回文本、工具步数记录

用法
----
    .venv/Scripts/python.exe tests/_probe_conductor.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


class _FakeAIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeLLM:
    """假 LLM：按预设脚本依次返回 AIMessage。

    · `bind_tools` 记下被绑定的工具名（供断言"子代理拿到窄工具集"）；
    · `ainvoke` 每次弹出脚本下一条；`bind_tools` 后的实例共享脚本游标。
    """

    def __init__(self, script):
        self._script = list(script)
        self._i = 0
        self.bound_tool_names = None

    def bind_tools(self, tool_defs):
        self.bound_tool_names = [d.get("function", {}).get("name") for d in tool_defs]
        return self

    async def ainvoke(self, messages):
        if self._i < len(self._script):
            msg = self._script[self._i]
            self._i += 1
            return msg
        return _FakeAIMessage(content="(no more script)")


async def run_probe() -> int:
    from app.services.ai.agent.registry import ensure_tools_loaded, registry
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import orchestrator
    from app.services.ai import prompts
    from app.services.ai.agent.tools.delegate import DelegateTaskTool
    from app.services.ai.agent.sub_agent import run_sub_agent

    ensure_tools_loaded()
    all_names = set(registry.names())

    # ---- 1. 子代理定义自洽 ----
    subs = roles_mod.renderable_sub_agents()
    check("CD-01", "存在可委派子代理", len(subs) >= 4, f"count={len(subs)}")
    check(
        "CD-02",
        "每个可委派子代理都有 capability",
        all(r.capability.strip() for r in subs),
        str([r.key for r in subs if not r.capability.strip()]),
    )
    check(
        "CD-03",
        "general 不在可委派清单",
        all(r.key != roles_mod.GENERAL_ROLE for r in subs),
        str([r.key for r in subs]),
    )
    check(
        "CD-04",
        "每个可委派子代理都有 persona（自我认知）",
        all(r.persona.strip() for r in subs),
        str([r.key for r in subs if not r.persona.strip()]),
    )

    # ---- 2. 通讯录渲染 ----
    brief = roles_mod.render_sub_agents_briefing()
    check("CD-05", "通讯录含 bank 子代理", "bank" in brief, brief[:120])
    check("CD-06", "通讯录含 capability 文本", "Question banks" in brief, brief[:160])
    check("CD-07", "通讯录不含 general", "general" not in brief, brief[:120])
    brief2 = roles_mod.render_sub_agents_briefing(
        [{"key": "user:9", "name": "数学老师", "capability": "Math tutoring."}]
    )
    check("CD-08", "通讯录可附加用户智能体", "user:9" in brief2 and "Math tutoring" in brief2, brief2[-120:])

    # ---- 3. delegate_task 永远被排除 ----
    general = roles_mod.OFFICIAL_ROLES[roles_mod.GENERAL_ROLE]
    ex_general = orchestrator.compute_exclude(general, all_tool_names=all_names, user_disabled=set())
    check(
        "CD-09",
        "general 的 exclude 含 delegate_task（元工具永不外发）",
        roles_mod.DELEGATE_TOOL_NAME in ex_general,
        str(sorted(ex_general)),
    )
    bank = roles_mod.OFFICIAL_ROLES["bank"]
    ex_bank = orchestrator.compute_exclude(bank, all_tool_names=all_names, user_disabled=set())
    check(
        "CD-10",
        "子代理(bank) 的 exclude 也含 delegate_task（防递归委派）",
        roles_mod.DELEGATE_TOOL_NAME in ex_bank,
        str(sorted(ex_bank)[:6]),
    )

    # ---- 4. 指挥家提示词 ----
    sp = prompts.build_agent_system_prompt(
        include_tools=False, include_doc_workflow=False, sub_agents_text=brief
    )
    check("CD-11", "指挥家提示词含 CONDUCTOR 段", "CONDUCTOR" in sp, sp[:80])
    check("CD-12", "指挥家提示词含子代理通讯录", "Question Bank Specialist" in sp or "bank (" in sp, "")
    check("CD-13", "指挥家提示词含 delegate_task 指引", "delegate_task" in sp, "")
    # 不传通讯录则不注入指挥家段
    sp2 = prompts.build_agent_system_prompt(include_tools=False, include_doc_workflow=False)
    check("CD-14", "非指挥家模式不注入 CONDUCTOR 段", "CONDUCTOR MODE" not in sp2, "")

    # ---- 5. DelegateTaskTool 元数据 + 缺环境 fail ----
    tool = DelegateTaskTool()
    check("CD-15", "delegate_task 名正确", tool.name == "delegate_task", tool.name)
    check("CD-16", "delegate_task 不是写操作", tool.write_operation is False, str(tool.write_operation))
    check(
        "CD-17",
        "delegate_task 参数含 sub_agent/task",
        set(tool.parameters.get("required", [])) == {"sub_agent", "task"},
        str(tool.parameters.get("required")),
    )
    from app.services.ai.agent.base import ToolContext

    r = await tool.execute(
        {"sub_agent": "bank", "task": "list banks"},
        ToolContext(db=object(), user_id=1, extra={}),  # 无 delegate 环境
    )
    check("CD-18", "缺委派环境 → fail（不假装成功）", r.get("success") is False, str(r)[:120])

    # ---- 6. run_sub_agent：假 LLM 跑通 ----
    # 脚本：先请求调用 bank_manage（子代理白名单内），再给最终文字
    fake = _FakeLLM([
        _FakeAIMessage(content="", tool_calls=[{"name": "bank_manage", "args": {"action": "list"}, "id": "c1"}]),
        _FakeAIMessage(content="Found 2 banks: A, B."),
    ])

    # mock 工具执行：不真连 DB
    from app.services.ai.agent import loop as loop_mod

    orig_exec = loop_mod._execute_tool

    async def fake_exec(t, params, ctx):
        return {"success": True, "message": "ok", "action": params.get("action")}

    loop_mod._execute_tool = fake_exec
    try:
        res = await run_sub_agent(
            object(),
            user_id=1,
            role_spec=bank,
            task="List the user's banks.",
            llm=fake,
            excluded_tools=ex_bank,
        )
    finally:
        loop_mod._execute_tool = orig_exec

    check("CD-19", "run_sub_agent 成功返回文本", res.get("success") and res.get("text") == "Found 2 banks: A, B.", str(res))
    check("CD-20", "子代理用的是窄工具集（不含 delegate_task）", fake.bound_tool_names is not None and roles_mod.DELEGATE_TOOL_NAME not in fake.bound_tool_names, str(fake.bound_tool_names))
    check("CD-21", "子代理工具集 ⊇ bank 白名单", fake.bound_tool_names and set(bank.tools).issubset(set(fake.bound_tool_names)), str(fake.bound_tool_names))
    check("CD-22", "记录了工具执行步数", res.get("steps") == ["bank_manage"], str(res.get("steps")))

    # 不再调工具（空 tool_calls）→ 直接结束
    fake2 = _FakeLLM([_FakeAIMessage(content="Nothing to do.")])
    res2 = await run_sub_agent(object(), user_id=1, role_spec=bank, task="hi", llm=fake2, excluded_tools=ex_bank)
    check("CD-23", "子代理无工具调用时直接返回", res2.get("success") and res2.get("steps") == [], str(res2))

    print("\n---- 指挥家模式探针结果 ----")
    for rec in ROWS:
        tail = "" if rec["status"] == "通过" else f" | 实际: {rec['actual']}"
        print(f"  [{rec['status']}] {rec['cid']} {rec['title']}{tail}")
    red = [rec for rec in ROWS if rec["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
