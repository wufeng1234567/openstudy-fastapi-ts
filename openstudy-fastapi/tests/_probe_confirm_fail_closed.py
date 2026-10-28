# -*- coding: utf-8 -*-
"""确认流程 fail-closed 探针 —— 零 DB、零网络、零 LLM 成本

锁住两个修复（2026-10-28）：

  A. `sub_agent` 确认流程异常 → **fail-closed**：
     确认环节（needs_user_confirmation / _await_user_confirmation / 草稿覆盖 …）任何异常，
     工具**绝不执行**（`_execute_tool` 零调用），模型收到带 hint 的失败信封；
     `cancelled=False`（异常 ≠ 用户取消，界面事件不得显示「已取消」）。
     旧实现是 fail-open（run_tool=True「按原样执行」）：测试桩签名不匹配这类异常
     会被静默转成「未授权直接执行」——本探针的 FC-01 就是当时的现实触发路径。

  B. `loop._await_user_confirmation` 的 finally 同时清理 `_pending_confirms` 与
     `_pending_decisions`，覆盖 成功 / 超时 / 任务取消 三条路径；
     「决定先到」早退分支行为不变。

用法：
    .venv/Scripts/python.exe tests/_probe_confirm_fail_closed.py     # 全绿退出码 0
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


def _dicts_clean(loop_mod, cid_):
    return cid_ not in loop_mod._pending_confirms and cid_ not in loop_mod._pending_decisions


async def _t_subagent_confirm_exception() -> None:
    """A 组：确认流程抛异常 → 工具零执行 + 失败信封 + cancelled=False"""
    from app.services.ai.agent.registry import ensure_tools_loaded
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import loop as loop_mod
    from app.services.ai.agent.sub_agent import run_sub_agent

    ensure_tools_loaded()
    bank = roles_mod.OFFICIAL_ROLES["bank"]

    orig_needs = loop_mod.needs_user_confirmation
    orig_exec = loop_mod._execute_tool
    orig_await = loop_mod._await_user_confirmation

    executed = []

    async def fake_exec(t, params, ctx):
        executed.append(dict(params))
        return {"success": True, "message": "ok", "action": params.get("action")}

    async def boom(confirm_id):
        raise RuntimeError("confirm pipeline boom")

    loop_mod.needs_user_confirmation = lambda t, p, ac, cw=None: True
    loop_mod._execute_tool = fake_exec
    loop_mod._await_user_confirmation = boom

    try:
        events = []

        async def on_event(ev):
            events.append(ev)

        fake = _FakeLLM(_tool_call_script())
        res = await asyncio.wait_for(
            run_sub_agent(
                object(), user_id=1, role_spec=bank, task="list banks",
                llm=fake, excluded_tools=set(),
                on_event=on_event,
            ),
            timeout=5,
        )
        check("FC-01", "确认异常 → _execute_tool 零调用", executed == [], str(executed))
        check(
            "FC-02", "确认异常 → 子代理不崩溃，正常收尾",
            res.get("success") is True and res.get("text") == "done",
            str(res)[:160],
        )
        check("FC-03", "确认异常 → steps 不计入该工具", res.get("steps") == [], str(res.get("steps")))
        round2 = _msgs_text(fake.calls[1] if len(fake.calls) > 1 else [])
        check(
            "FC-04",
            "模型收到「确认流程异常」失败信封（非「用户取消」）",
            "确认流程异常" in round2 and "用户取消了这次操作" not in round2,
            round2[:160],
        )
        check(
            "FC-05",
            "失败信封带 hint（模型可自纠）",
            "这不是用户取消" in round2,
            round2[:160],
        )
        tool_results = [
            e for e in events
            if e.get("phase") == "tool_result" and e.get("tool") == "bank_manage"
        ]
        tr = tool_results[-1] if tool_results else {}
        check(
            "FC-06",
            "界面事件 success=False 且 message 非「已取消」（cancelled=False）",
            tr.get("success") is False and tr.get("message") != "已取消",
            str(tr)[:160],
        )
        check(
            "FC-07",
            "界面事件 message 指明「未执行」",
            "未执行" in str(tr.get("message") or ""),
            str(tr.get("message"))[:160],
        )
    finally:
        loop_mod.needs_user_confirmation = orig_needs
        loop_mod._execute_tool = orig_exec
        loop_mod._await_user_confirmation = orig_await


async def _t_await_cleanup() -> None:
    """B 组：_await_user_confirmation 三条退出路径的字典清理 + 早退分支回归"""
    from app.services.ai.agent import loop as loop_mod

    orig_timeout = loop_mod.CONFIRM_TIMEOUT_SECONDS
    try:
        # ---- 超时：两个字典都不留 confirmId ----
        loop_mod.CONFIRM_TIMEOUT_SECONDS = 0.05
        cid_t = "cfm_fc_timeout"
        approved_t, edited_t = await loop_mod._await_user_confirmation(cid_t)
        check(
            "FC-08", "超时 → 返回 (False, None)",
            approved_t is False and edited_t is None,
            f"{approved_t!r} {edited_t!r}",
        )
        check(
            "FC-09", "超时 → _pending_confirms / _pending_decisions 均无该 id",
            _dicts_clean(loop_mod, cid_t),
            str((cid_t in loop_mod._pending_confirms, cid_t in loop_mod._pending_decisions)),
        )

        # ---- 正常批准（带 edited）：读回决定且两字典干净 ----
        loop_mod.CONFIRM_TIMEOUT_SECONDS = 5
        cid_a = "cfm_fc_approve"
        task = asyncio.create_task(loop_mod._await_user_confirmation(cid_a))
        await asyncio.sleep(0.02)
        loop_mod.resolve_confirmation(cid_a, True, edited={"x": 1})
        approved_a, edited_a = await asyncio.wait_for(task, timeout=5)
        check(
            "FC-10", "批准 → 读回 (True, edited)",
            approved_a is True and edited_a == {"x": 1},
            f"{approved_a!r} {edited_a!r}",
        )
        check("FC-11", "批准 → 两字典干净", _dicts_clean(loop_mod, cid_a), "")

        # ---- 正常取消 ----
        cid_c = "cfm_fc_cancel"
        task = asyncio.create_task(loop_mod._await_user_confirmation(cid_c))
        await asyncio.sleep(0.02)
        loop_mod.resolve_confirmation(cid_c, False)
        approved_c, edited_c = await asyncio.wait_for(task, timeout=5)
        check(
            "FC-12", "取消 → 读回 (False, None)",
            approved_c is False and edited_c is None,
            f"{approved_c!r} {edited_c!r}",
        )
        check("FC-13", "取消 → 两字典干净", _dicts_clean(loop_mod, cid_c), "")

        # ---- 决定先到（早退分支，行为不变） ----
        cid_d = "cfm_fc_decision_first"
        loop_mod.resolve_confirmation(cid_d, True, edited={"q": 9})
        approved_d, edited_d = await loop_mod._await_user_confirmation(cid_d)
        check(
            "FC-14", "决定先到 → 早退分支读回 (True, edited)",
            approved_d is True and edited_d == {"q": 9},
            f"{approved_d!r} {edited_d!r}",
        )
        check(
            "FC-15", "决定先到 → 决定被 pop、event 从未注册",
            _dicts_clean(loop_mod, cid_d),
            str((cid_d in loop_mod._pending_confirms, cid_d in loop_mod._pending_decisions)),
        )

        # ---- 任务被取消：finally 也清理 ----
        cid_k = "cfm_fc_cancelled_task"
        task = asyncio.create_task(loop_mod._await_user_confirmation(cid_k))
        await asyncio.sleep(0.02)
        task.cancel()
        got_cancelled = False
        try:
            await task
        except asyncio.CancelledError:
            got_cancelled = True
        check("FC-16", "外部取消 → CancelledError 向上传播", got_cancelled, "")
        check(
            "FC-17", "外部取消 → 两字典干净",
            _dicts_clean(loop_mod, cid_k),
            str((cid_k in loop_mod._pending_confirms, cid_k in loop_mod._pending_decisions)),
        )
    finally:
        loop_mod.CONFIRM_TIMEOUT_SECONDS = orig_timeout


async def _t_subagent_timeout_no_exec() -> None:
    """C 组：子代理级超时（真实 _await_user_confirmation）→ 按取消处理，工具不执行"""
    from app.services.ai.agent.registry import ensure_tools_loaded
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import loop as loop_mod
    from app.services.ai.agent.sub_agent import run_sub_agent

    ensure_tools_loaded()
    bank = roles_mod.OFFICIAL_ROLES["bank"]

    orig_needs = loop_mod.needs_user_confirmation
    orig_exec = loop_mod._execute_tool
    orig_timeout = loop_mod.CONFIRM_TIMEOUT_SECONDS

    executed = []

    async def fake_exec(t, params, ctx):
        executed.append(dict(params))
        return {"success": True, "message": "ok", "action": params.get("action")}

    loop_mod.needs_user_confirmation = lambda t, p, ac, cw=None: True
    loop_mod._execute_tool = fake_exec
    loop_mod.CONFIRM_TIMEOUT_SECONDS = 0.05

    try:
        events = []

        async def on_event(ev):
            events.append(ev)

        fake = _FakeLLM(_tool_call_script())
        res = await asyncio.wait_for(
            run_sub_agent(
                object(), user_id=1, role_spec=bank, task="list banks",
                llm=fake, excluded_tools=set(),
                on_event=on_event,
            ),
            timeout=10,
        )
        check("FC-18", "确认超时 → 工具不执行", executed == [], str(executed))
        round2 = _msgs_text(fake.calls[1] if len(fake.calls) > 1 else [])
        check(
            "FC-19", "确认超时 → 模型收到「用户取消了这次操作」信封",
            "用户取消了这次操作" in round2,
            round2[:160],
        )
        check(
            "FC-20", "确认超时 → 子代理正常收尾（success=True）",
            res.get("success") is True,
            str(res)[:160],
        )
        # 残留检查：子代理跑完后不该有 confirmId 挂在全局字典里
        leftover = [
            cid for cid in loop_mod._pending_confirms
            if str(cid).startswith("cfm_")
        ]
        check(
            "FC-21", "子代理跑完 → _pending_confirms 无 cfm_ 残留", leftover == [], str(leftover)
        )
    finally:
        loop_mod.needs_user_confirmation = orig_needs
        loop_mod._execute_tool = orig_exec
        loop_mod.CONFIRM_TIMEOUT_SECONDS = orig_timeout


async def run_probe() -> int:
    await _t_subagent_confirm_exception()
    await _t_await_cleanup()
    await _t_subagent_timeout_no_exec()

    print("\n---- 确认流程 fail-closed 探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的={[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
