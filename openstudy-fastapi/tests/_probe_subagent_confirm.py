# -*- coding: utf-8 -*-
"""子代理确认闸门探针 —— 零 DB、零网络、零 LLM 成本

复现并锁住用户报的「委派出去的任务永远不弹确认卡片」缺陷：
子代理在 `_run_sub_agent_inner` 里跑**需要确认**的写操作时，必须与指挥家**同规则**
地在**执行前**发 `tool_confirm`、挂起等用户决定、并 honor 它（含可编辑草稿 `edited`）。

断言：
  1. 需要确认的工具 → 子代理发出 `tool_confirm`（带 confirmId / tool / action / params /
     preview / destructive）
  2. 未 `resolve_confirmation` 前工具**不执行**（挂起）
  3. approve → 执行一次
  4. cancel → 不执行 + 模型收到「用户取消了这次操作」的失败信封
  5. `edited` → 覆盖参数后再执行
  6. 不需要确认 → 不弹卡、直接执行（闸门只在需要时开）

用法：
    .venv/Scripts/python.exe tests/_probe_subagent_confirm.py     # 全绿退出码 0
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
    """假 LLM：按脚本依次返回；记录每次 `ainvoke` 收到的消息（供断言回灌内容）"""

    def __init__(self, script):
        self._script = list(script)
        self._i = 0
        self.calls = []

    def bind_tools(self, defs):
        return self

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        if self._i < len(self._script):
            m = self._script[self._i]
            self._i += 1
            return m
        return _Msg(content="(no more script)")


def _tool_call_script():
    return [
        _Msg(content="", tool_calls=[{"name": "bank_manage", "args": {"action": "list"}, "id": "c1"}]),
        _Msg(content="done"),
    ]


def _msgs_text(messages):
    out = []
    for m in messages:
        c = getattr(m, "content", "")
        out.append(c if isinstance(c, str) else str(c))
    return "\n".join(out)


async def run_probe() -> int:
    from app.services.ai.agent.registry import ensure_tools_loaded
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import loop as loop_mod
    from app.services.ai.agent.sub_agent import run_sub_agent

    ensure_tools_loaded()
    bank = roles_mod.OFFICIAL_ROLES["bank"]

    orig_needs = loop_mod.needs_user_confirmation
    orig_exec = loop_mod._execute_tool
    orig_apply = loop_mod._apply_edited_params

    executed = []
    applied = []

    async def fake_exec(t, params, ctx):
        executed.append(dict(params))
        return {"success": True, "message": "ok", "action": params.get("action")}

    async def fake_apply(t, params, edited, ctx):
        applied.append(edited)
        p = dict(params)
        p["__edited_applied__"] = True
        return p

    # 让「所有工具都需确认」，从而聚焦验证子代理侧的闸门接线（规则本身由草稿探针覆盖）
    loop_mod.needs_user_confirmation = lambda t, p, ac: True
    loop_mod._execute_tool = fake_exec
    loop_mod._apply_edited_params = fake_apply

    try:
        # ---- T1/T2：需要确认 → 发 tool_confirm；未 resolve 前不执行；approve 后执行 ----
        executed.clear()
        events = []
        seen = asyncio.Event()

        async def on_event(ev):
            events.append(ev)
            if ev.get("type") == "tool_confirm":
                seen.set()

        fake = _FakeLLM(_tool_call_script())
        task = asyncio.create_task(run_sub_agent(
            object(), user_id=1, role_spec=bank, task="list banks",
            llm=fake, excluded_tools=set(), on_event=on_event,
        ))
        await asyncio.wait_for(seen.wait(), timeout=5)

        confirms = [e for e in events if e.get("type") == "tool_confirm"]
        check("SC-01", "子代理发出 tool_confirm 事件", len(confirms) == 1, str(len(confirms)))
        c0 = confirms[0] if confirms else {}
        check("SC-02", "tool_confirm 带 confirmId", bool(c0.get("confirmId")), str(c0.get("confirmId")))
        check("SC-03", "confirmId 形如 cfm_<hex>", str(c0.get("confirmId", "")).startswith("cfm_"), str(c0.get("confirmId")))
        check(
            "SC-04",
            "tool_confirm 载荷含 tool/action/message/params/preview/destructive",
            all(k in c0 for k in ("tool", "action", "message", "params", "preview", "destructive")),
            str(sorted(c0.keys())),
        )
        check("SC-05", "未 resolve 前工具不执行（挂起）", executed == [], str(executed))

        loop_mod.resolve_confirmation(c0["confirmId"], True)
        res = await asyncio.wait_for(task, timeout=5)
        check("SC-06", "approve → 执行工具一次", len(executed) == 1, str(executed))
        check("SC-07", "approve → 子代理正常返回文本", res.get("success") and res.get("text") == "done", str(res))

        # ---- T4：cancel → 不执行 + 模型收到失败信封 ----
        executed.clear()
        seen2 = asyncio.Event()

        async def on_event_cancel(ev):
            if ev.get("type") == "tool_confirm":
                loop_mod.resolve_confirmation(ev["confirmId"], False)
                seen2.set()

        fake2 = _FakeLLM(_tool_call_script())
        res2 = await asyncio.wait_for(run_sub_agent(
            object(), user_id=1, role_spec=bank, task="list banks",
            llm=fake2, excluded_tools=set(), on_event=on_event_cancel,
        ), timeout=5)
        check("SC-08", "cancel → 工具不执行", executed == [], str(executed))
        check("SC-09", "cancel → success 不因取消被误判为失败", res2.get("success") is True, str(res2)[:120])
        check(
            "SC-10",
            "cancel → 模型收到「用户取消了这次操作」失败信封",
            "用户取消了这次操作" in _msgs_text(fake2.calls[1] if len(fake2.calls) > 1 else []),
            str(len(fake2.calls)),
        )

        # ---- T5：edited → 覆盖参数后再执行 ----
        executed.clear()
        applied.clear()
        seen3 = asyncio.Event()

        async def on_event_edited(ev):
            if ev.get("type") == "tool_confirm":
                loop_mod.resolve_confirmation(ev["confirmId"], True, edited={"questions": [{"q": 1}]})
                seen3.set()

        fake3 = _FakeLLM(_tool_call_script())
        await asyncio.wait_for(run_sub_agent(
            object(), user_id=1, role_spec=bank, task="list banks",
            llm=fake3, excluded_tools=set(), on_event=on_event_edited,
        ), timeout=5)
        check("SC-11", "edited 传给 _apply_edited_params", applied == [{"questions": [{"q": 1}]}], str(applied))
        check(
            "SC-12",
            "edited 覆盖后的参数被执行（__edited_applied__）",
            bool(executed) and executed[0].get("__edited_applied__") is True,
            str(executed),
        )

        # ---- T6：不需要确认 → 不弹卡、直接执行 ----
        loop_mod.needs_user_confirmation = lambda t, p, ac: False
        executed.clear()
        events6 = []

        async def on_event6(ev):
            events6.append(ev)

        fake6 = _FakeLLM(_tool_call_script())
        await asyncio.wait_for(run_sub_agent(
            object(), user_id=1, role_spec=bank, task="list banks",
            llm=fake6, excluded_tools=set(), on_event=on_event6,
        ), timeout=5)
        check("SC-13", "不需要确认 → 不发 tool_confirm", not any(e.get("type") == "tool_confirm" for e in events6), "")
        check("SC-14", "不需要确认 → 直接执行", len(executed) == 1, str(executed))

        # ---- T7：指挥家侧接线（源码级契约；asyncio 端到端不启服务）----
        import inspect

        from app.services.ai.agent.tools.delegate import DelegateTaskTool

        loop_src = inspect.getsource(loop_mod.run_agent_stream)
        check(
            "SC-15",
            "指挥家把 auto_confirm 放进 delegate_extra",
            '"auto_confirm": bool(req.auto_confirm)' in loop_src,
            "",
        )
        check(
            "SC-16",
            "指挥家把子代理 tool_confirm 透传为真事件（非 subagent_event）",
            '== "tool_confirm"' in loop_src and "yield _event(_ev)" in loop_src,
            "",
        )
        d_src = inspect.getsource(DelegateTaskTool.execute)
        check("SC-17", "delegate 防御性补 auto_confirm", 'setdefault("auto_confirm"' in d_src, "")
    finally:
        loop_mod.needs_user_confirmation = orig_needs
        loop_mod._execute_tool = orig_exec
        loop_mod._apply_edited_params = orig_apply

    print("\n---- 子代理确认闸门探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的={[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
