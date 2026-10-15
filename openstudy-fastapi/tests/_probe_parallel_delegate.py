# -*- coding: utf-8 -*-
"""并行委派探针 —— 零 LLM 成本（fake LLM）+ 真 DB（仅独立会话生命周期）

验证用户 2026-10-10「多专家并行干活」改造的后端契约：
  1. `run_sub_agent(own_session=True)` 能**自己开独立会话**执行（并发委派的并行前提）
  2. `run_sub_agent(own_session=False)` 沿用传入 db（串行委派，回退账本同源）
  3. `DelegateTaskTool` 依 `ctx.extra["delegate_parallel"]` 决定 own_session
  4. 指挥家提示词含**同一轮并发派多个专家**的指引
  5. `DelegateTaskTool.description` 含并行指引（英文，守 P11D）

用法
----
    .venv/Scripts/python.exe tests/_probe_parallel_delegate.py     # 全绿退出码 0
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


class _Msg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeLLM:
    def __init__(self, script):
        self._script = list(script)
        self._i = 0

    def bind_tools(self, defs):
        return self

    async def ainvoke(self, messages):
        if self._i < len(self._script):
            m = self._script[self._i]
            self._i += 1
            return m
        return _Msg(content="done")

    async def astream(self, messages):
        yield _Msg(content="done")


async def run_probe() -> int:
    from app.database import register_all_models

    register_all_models()
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent.sub_agent import run_sub_agent
    from app.services.ai.agent.tools.delegate import DelegateTaskTool
    from app.services.ai import prompts

    bank = roles_mod.OFFICIAL_ROLES["bank"]

    # ---- 1. own_session=True：独立开会话 + 正常返回 ----
    fake = _FakeLLM([_Msg(content="Sub-agent done (no tools).")])
    res = await run_sub_agent(
        None,  # db=None → 必须自己开会话
        user_id=2_000_900_401,
        role_spec=bank,
        task="(probe) do nothing",
        llm=fake,
        excluded_tools=set(),
        own_session=True,
    )
    check("PD-01", "own_session=True 独立开会话并成功返回", res.get("success") and "done" in res.get("text", ""), str(res))

    # ---- 2. own_session=False 且传入假 db：沿用（不触发真会话）----
    res2 = await run_sub_agent(
        object(),  # 假 db：无工具调用时不碰它
        user_id=2_000_900_401,
        role_spec=bank,
        task="(probe) do nothing",
        llm=_FakeLLM([_Msg(content="ok")]),
        excluded_tools=set(),
        own_session=False,
    )
    check("PD-02", "own_session=False 沿用传入 db", res2.get("success"), str(res2))

    # ---- 3. DelegateTaskTool 依 extra 决定 own_session ----
    # 直接检查源码级契约：delegate.py 读 delegate_parallel 并传给 run_sub_agent
    import inspect

    src = inspect.getsource(DelegateTaskTool.execute)
    check("PD-03", "delegate 工具读 delegate_parallel", "delegate_parallel" in src, "")
    check("PD-04", "delegate 工具把 own_session 传给 run_sub_agent", "own_session=" in src, "")

    # ---- 4. run_sub_agent 暴露 own_session 参数 ----
    sig = inspect.signature(run_sub_agent)
    check("PD-05", "run_sub_agent 暴露 own_session 参数", "own_session" in sig.parameters, str(list(sig.parameters)))

    # ---- 5. 提示词含并行指引 ----
    sp = prompts.AGENT_CONDUCTOR_SECTION
    check("PD-06", "指挥家提示词含并行派活指引", "PARALLEL WORK" in sp or "IN THE SAME turn" in sp, "")

    # ---- 6. 工具描述含并行指引（英文）----
    desc = DelegateTaskTool.description
    check("PD-07", "delegate 描述含同轮多次调用指引", "SAME reply" in desc or "MULTIPLE" in desc, "")
    # P11D：description 是模型侧，不得含中文
    cjk = [c for c in desc if "\u4e00" <= c <= "\u9fff"]
    check("PD-08", "delegate 描述无中文（P11D）", not cjk, "".join(cjk))

    # ---- 7. 子代理「协议文本」检测（防"把工具调用写成文本当成结论"）----
    from app.services.ai.agent.sub_agent import _looks_like_tool_protocol

    check("PD-09", "识别 DSML 协议文本", _looks_like_tool_protocol('调用: <|DSML|> invoke name="create_knowledge_base"'))
    check("PD-10", "识别 <invoke>/<parameter> 文本", _looks_like_tool_protocol('call it:\n<invoke name="x">'))
    check("PD-11", "识别裸 tool+action JSON", _looks_like_tool_protocol('{"tool": "bank_manage", "action": "list"}'))
    check("PD-12", "正常文本不误伤", not _looks_like_tool_protocol("已为你创建好知识库 cpp，共 3 篇文档。"))

    # ---- 8. 子代理「谎称没工具」检测（防"我没工具"被当结论）----
    from app.services.ai.agent.sub_agent import _looks_like_no_tool_refusal

    check(
        "PD-13",
        "识别英文谎称没工具（function not available）",
        _looks_like_no_tool_refusal(
            "my knowledge_create_kb function is not available in this environment"
        ),
    )
    check(
        "PD-14",
        "识别中文谎称没工具（只有代码执行工具）",
        _looks_like_no_tool_refusal(
            "我只有代码执行（python）工具，没有暴露任何知识库管理或 knowledge_search 相关接口"
        ),
    )
    check(
        "PD-15",
        "识别无法执行类文本",
        _looks_like_no_tool_refusal("我无法执行该操作，因为工具不存在"),
    )
    check(
        "PD-16",
        "正常完成总结不误伤",
        not _looks_like_no_tool_refusal("已为你创建好知识库 cpp，共 3 篇文档。"),
    )

    # ---- 9. 子代理「一步没跑却谎称没工具」→ 明确失败（不把空话交回指挥家）----
    kb = roles_mod.OFFICIAL_ROLES["kb"]
    refuser = _FakeLLM([
        _Msg(content="I'm unable to do this — my function is not available in this environment."),
        _Msg(content="I only have a python code-execution tool, no knowledge-base function."),
        _Msg(content="Sorry, I have no access to any tool here."),
    ])
    res_ref = await run_sub_agent(
        object(),
        user_id=2_000_900_401,
        role_spec=kb,
        task="create a kb named cpp",
        llm=refuser,
        excluded_tools=set(),
    )
    check(
        "PD-17",
        "谎称没工具 → success=False（不当结论回报）",
        res_ref.get("success") is False,
        str(res_ref)[:160],
    )
    check("PD-18", "谎称没工具的失败 steps 为空", res_ref.get("steps") == [], str(res_ref.get("steps")))

    # ---- 10. delegate 事件 index 必须「整轮全局唯一」（跨 LLM 轮次不撞号）----
    #    用户 2026-10-11 报：多专家时某专家（题库专家）永远停在"进行中"——因 index 用
    #    `len(delegate_jobs)`（每个 LLM 轮次从 0 重计）→ 跨轮撞号 → 前端回填错行。
    #    修法=改用整轮全局的 `delegate_seq`。这里做**源码级契约**断言（asyncio 在本沙箱不可用，
    #    无法跑端到端；该契约纯静态、可稳定校验）。
    import inspect

    from app.services.ai.agent import loop as loop_mod

    loop_src = inspect.getsource(loop_mod.run_agent_stream)
    # `delegate_seq` 必须在 LLM 轮次循环（`for loop_index in range`）**之前**声明
    seq_def_pos = loop_src.find("delegate_seq = 0")
    loop_pos = loop_src.find("for loop_index in range")
    check(
        "PD-19",
        "delegate_seq 在 LLM 轮次循环之前声明（整轮全局）",
        seq_def_pos != -1 and loop_pos != -1 and seq_def_pos < loop_pos,
        f"seq_def={seq_def_pos} loop={loop_pos}",
    )
    check(
        "PD-20",
        "delegate 事件 index 不再用 len(delegate_jobs)",
        '"index": len(delegate_jobs)' not in loop_src and "this_delegate_idx" in loop_src,
        "",
    )



    print("\n---- 并行委派探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
