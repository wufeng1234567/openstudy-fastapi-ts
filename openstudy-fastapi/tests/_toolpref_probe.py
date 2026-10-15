# -*- coding: utf-8 -*-
"""零成本跑手：**Agent 工具开关闸门** + **空会话懒建**（2026-09-21）

为什么单独一个跑手（与 `_kbdisable_probe.py` 同一条理由）
----------------------------------------------------------
这两件事的验收点住在 `tests/e2e_agent_api.py` 里最花钱的那一段旁边，而整套 e2e 会真调
SiliconeFlow 的 embedding 与付费 DeepSeek —— 在成本闸门下「工具开关」这个能力会**没有
可复现的验证手段**。本脚本把能零成本验的都验掉：

    · 全程 in-process（ASGITransport）+ 假登录（依赖覆盖），不打任何模型 / embedding 请求；
    · 唯一的「真实调用」是对数据库的读写 —— 用**专用一次性 uid**（`PROBE_UID`），
      收尾按精确匹配清掉，并断言「真实用户的行集合一字未变」。

本脚本**不**验证（并明确标为 NOT RUN，见结尾打印）：任何需要 LLM 往返的路径
（api 付费循环里「模型真去调一个被屏蔽的工具」那一幕）。

用法
----
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py              # 应当全绿，退出码 0
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate gate      # 应当红
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate api       # 应当红
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate guard     # 应当红（execute/preview 闸门）
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate inloop    # 应当红（付费循环内联闸门）
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate sessions  # 应当红
    ./.venv/Scripts/python.exe tests/_toolpref_probe.py --mutate all       # 应当红

`--mutate` = 把某一处闸门**改回改动之前的样子**（锚点必须各命中**一次**，不是一次就
直接 assert 失败 —— 锚点漂了说明变异没落在你以为的地方），跑完在 `finally` 里整份写回
并打 md5 前后比对。这就是「用例在修复前必须是红的」那条纪律的证据。

⚠️ 变异会让 9101 的 `--reload` 重新加载这几个文件（变异体语法合法，不会把服务弄崩），
   跑完即还原。
"""

import argparse
import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

#: 专用一次性 uid —— 绝不能是真实用户（105 / 1）。
#: 收尾按 `user_id = PROBE_UID` 精确删除，并断言其它用户的行集合一字未变。
PROBE_UID = 999999

LOOP_PY = Path(ROOT) / "app" / "services" / "ai" / "agent" / "loop.py"
AI_PY = Path(ROOT) / "app" / "api" / "v1" / "ai.py"

#: 变异模式 → [(文件, 说明, 旧文本, 新文本), ...]
MUTATIONS = {
    # 「不把被屏蔽的工具广播出去」这三处出口（loop.py）改回旧行为
    "gate": [
        (
            LOOP_PY,
            "提示词工具清单不再排除",
            "tools_text=registry.describe(exclude=sorted(disabled_tools)),",
            "tools_text=registry.describe(),",
        ),
        (
            LOOP_PY,
            "Function Calling 工具定义不再排除",
            "tool_defs = registry.definitions(exclude=sorted(disabled_tools))",
            "tool_defs = registry.definitions()",
        ),
        (
            LOOP_PY,
            "meta 事件的可用工具不再过滤",
            "                if t.name not in disabled_tools\n",
            "",
        ),
    ],
    # 执行侧闸门：`_prepare_tool_call`（ds-free 的 execute / preview）改回旧行为
    "guard": [
        (
            LOOP_PY,
            "_prepare_tool_call 不再检查屏蔽",
            "    disabled = await tool_pref_service.disabled_tool_names(user_id)\n"
            "    if tool_name in disabled:\n"
            "        return None, dict(params or {}), _disabled_fail(tool_name)\n",
            "    pass  # MUTATED: 执行侧闸门拆掉\n",
        ),
    ],
    # 执行侧闸门：api 付费循环的**内联分支**改回旧行为（与上面那个是两处独立代码路径，
    # 少一个就有一个口子 —— 所以变异也要分开做，否则分不清哪一处没在防）
    "inloop": [
        (
            LOOP_PY,
            "run_agent_stream 内联分支不再拦屏蔽工具",
            "            if tool_name in disabled_tools:\n"
            "                result = _disabled_fail(tool_name)\n",
            "            if False:  # MUTATED: 内联闸门拆掉\n"
            "                result = _disabled_fail(tool_name)\n",
        ),
    ],
    # `/ai/agent/tools` 的读写两侧改回旧行为：
    #   ① 路由「不存在」（改名 → 落到 catch_all 的假 200，这正是改动之前的样子）
    #   ② GET 不挂 disabled 兄弟字段
    "api": [
        (
            AI_PY,
            "PUT 路由名改掉（= 改动之前不存在这条路由）",
            '@router.put("/agent/tools")',
            '@router.put("/agent/tools__mutated_off")',
        ),
        (
            AI_PY,
            "GET 不再挂 disabled 标记",
            '        tools.append({**entry, "disabled": 1 if name in disabled else 0})',
            "        tools.append({**entry})  # MUTATED",
        ),
    ],
    # 新建会话回到「立刻写一行」的旧行为
    "sessions": [
        (
            AI_PY,
            "create_session 恢复 touch_session",
            '    return success({"sessionId": conversation_service.new_session_id()})',
            "    _sid = conversation_service.new_session_id()\n"
            "    await conversation_service.touch_session(_user_id, _sid, title=\"新会话\")\n"
            '    return success({"sessionId": _sid})',
        ),
    ],
}
MUTATIONS["all"] = [
    item
    for mode in ("gate", "guard", "inloop", "api", "sessions")
    for item in MUTATIONS[mode]
]

#: 本脚本的结果行（`cid` / 标题 / 期望 / 实际 / 通过与否）
ROWS: list = []


def T(cid: str, title: str, expected: str, actual: str, ok: bool, detail: str = "") -> None:
    ROWS.append(
        {"cid": cid, "title": title, "expected": expected, "actual": actual, "ok": bool(ok),
         "detail": detail}
    )


def _names(tools) -> list:
    out = []
    for t in tools or []:
        if isinstance(t, dict):
            fn = t.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                out.append(fn["name"])
            elif t.get("name"):
                out.append(t["name"])
    return out


def _desc_tools(text: str) -> list:
    """从 `describe()` 的输出里取出**工具条目名**：只认行首 `- <name>:` 那种条目行。

    ⚠️ 判据必须是「条目行」这个**结构**，不能拿整个字符串做 `"note_manage" in text` ——
    别的工具的 description 里会**引用**它（实测 `memory_search` 的描述里就写着
    「re-read the live data with `bank_manage` / `note_manage` / `question_manage`」），
    于是「排除后还不含 note_manage」这条断言**恒假**、测试等于没测。
    （首轮跑真踩到了：`desc排除后=True`。这就是「数东西时先排除看起来像数据的东西」。）
    """
    names = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            names.append(line[2:].split(":", 1)[0].strip())
    return names


async def run_probe() -> int:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    from app.core.security import get_current_user
    from app.database import async_session_factory, engine
    from app.main import app
    from app.services.ai import conversation_service
    from app.services.ai.agent import tool_pref_service
    from app.services.ai.agent.registry import ensure_tools_loaded, registry

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://probe", timeout=90)
    client.headers.update({"Content-Type": "application/json"})
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": PROBE_UID,
        "userName": "toolpref-probe",
    }

    created_sessions: list = []

    # ---------- 前置①：新表 ----------
    # ⚠️ 建表这件事只能由**应用启动路径**负责（`main.py` lifespan → `init_db()`，
    #    而 `init_db()` 靠 `register_all_models()` 把模型模块 import 进来、
    #    `create_all` 才看得见 `ai_agent_tool_pref`）。忘了往那份清单里加一行，
    #    症状就是「表静默地从来没被建出来」—— 这条用例专门盯它。
    #    本探针进程走 ASGITransport（**不跑 lifespan**），所以表缺失时按同一条应用路径
    #    补建一次（`init_db` 是幂等的），这样跑手自己也能立起来；
    #    模型没注册的话 `init_db` 同样建不出来 → 下面那条照样红。
    async with async_session_factory() as db:
        table_exists = await _table_exists(db, "ai_agent_tool_pref")
    bootstrapped = False
    if not table_exists:
        from app.database import init_db

        await init_db()
        bootstrapped = True
        async with async_session_factory() as db:
            table_exists = await _table_exists(db, "ai_agent_tool_pref")

    T(
        "P0a",
        "新表已由 create_all 建出来（模型模块进了 register_all_models）",
        "ai_agent_tool_pref 存在",
        f"跑前 exists={not bootstrapped and table_exists} "
        f"（{'探针按 init_db 补建后' if bootstrapped else '本来就'} exists={table_exists}）",
        table_exists,
        "表不存在时下面所有开关用例都会连带红 —— 这条单独判，便于定位",
    )

    # ---------- 前置②：真实数据体检（一次性 uid 不能撞上真实用户） ----------
    async with async_session_factory() as db:
        pre_pref = set(
            (r[0], r[1], r[2])
            for r in (
                await db.execute(
                    text("SELECT user_id, tool_name, disabled FROM ai_agent_tool_pref")
                )
            ).all()
        ) if table_exists else set()
        pre_sessions = set(
            r[0] for r in (await db.execute(text("SELECT session_id FROM ai_chat_session"))).all()
        )
        pre_msgs = set(
            r[0] for r in (await db.execute(text("SELECT id FROM ai_chat_message"))).all()
        )
        probe_rows = (
            await db.execute(
                text("SELECT COUNT(*) FROM ai_chat_session WHERE user_id = :u"),
                {"u": PROBE_UID},
            )
        ).scalar()
    T(
        "P0b",
        "专用 uid 是干净的",
        f"ai_chat_session 里 user_id={PROBE_UID} 的行数为 0",
        f"count={probe_rows}",
        int(probe_rows or 0) == 0,
    )

    async def put(body):
        r = await client.put("/ai/agent/tools", json=body)
        try:
            return r.status_code, r.json()
        except Exception:  # noqa: BLE001
            return r.status_code, {}

    async def get_tools():
        r = await client.get("/ai/agent/tools")
        try:
            return r.status_code, r.json()
        except Exception:  # noqa: BLE001
            return r.status_code, {}

    async def execute(tool, params, confirmed=True, auto_confirm=True):
        r = await client.post(
            "/ai/agent/execute",
            json={
                "tool": tool,
                "params": params,
                "userId": PROBE_UID,
                "autoConfirm": auto_confirm,
                "confirmed": confirmed,
            },
        )
        try:
            return r.status_code, r.json() or {}
        except Exception:  # noqa: BLE001
            return r.status_code, {}

    try:
        ensure_tools_loaded()

        # ================= P1. 注册表级 exclude（两条提示词出口的机制） =================
        # 红/绿自证：**未过滤**的调用仍然含目标工具（这就是「改动之前」的样子），
        # 所以这条断言不是恒真的 —— 它区分得开「exclude 生效」与「工具压根没注册」。
        full_defs = _names(registry.definitions())
        ex_defs = _names(registry.definitions(exclude=["note_manage"]))
        full_desc = _desc_tools(registry.describe())
        ex_desc = _desc_tools(registry.describe(exclude=["note_manage"]))
        T(
            "P1",
            "definitions/describe 的 exclude 真的在过滤（两边口径一致）",
            "未过滤含 note_manage；exclude 后不含；其余工具两边一致；"
            "describe 的条目名与 definitions 的工具名集合相同",
            f"defs含={'note_manage' in full_defs} defs排除后={'note_manage' in ex_defs} "
            f"desc条目含={'note_manage' in full_desc} desc排除后={'note_manage' in ex_desc} "
            f"desc条目={full_desc}",
            ("note_manage" in full_defs and "note_manage" not in ex_defs
             and "note_manage" in full_desc and "note_manage" not in ex_desc
             and set(full_defs) - {"note_manage"} == set(ex_defs)
             # 自检：解析器没坏（否则「不含」可能是解析出来的假象）
             and set(full_desc) == set(full_defs)),
        )

        # ================= P2/P3. PUT 落库 + GET 反映（含「还能关回来」） =================
        st, body = await put({"tool": "note_manage", "disabled": 1})
        put_ok = st == 200 and "tools" in (body or {})
        entry = next(
            (t for t in (body.get("tools") or []) if (t.get("function") or {}).get("name") == "note_manage"),
            None,
        )
        T(
            "P2a",
            "PUT 返回与 GET 同形状（含 tools 键）",
            "HTTP 200 且 body 有 tools 键（catch_all 的假 200 没有）",
            f"status={st} has_tools={'tools' in (body or {})}",
            put_ok,
            f"body_keys={list((body or {}).keys())}",
        )
        T(
            "P2b",
            "被屏蔽的工具**仍以整行出现**且 disabled=1",
            "note_manage 在清单里、disabled=1、function 子对象完好",
            f"found={entry is not None} disabled={None if entry is None else entry.get('disabled')}",
            bool(entry) and entry.get("disabled") == 1
            and isinstance(entry.get("function"), dict)
            and "parameters" in entry["function"],
            "这条就是「用户还能把它打开回来」的性质：过滤掉就再也点不到了",
        )
        other_zero = all(
            t.get("disabled") == 0
            for t in (body.get("tools") or [])
            if (t.get("function") or {}).get("name") != "note_manage"
        )
        T(
            "P2c",
            "其余工具未被误伤（disabled 全为 0）",
            "除 note_manage 外每一项 disabled 都是整数 0",
            f"all_zero={other_zero}",
            other_zero,
        )

        # 独立复读：另一发 GET + 直连数据库。**只断言 PUT 的 200 证明不了任何事**
        # （pydantic extra='ignore' 与写库失败都能造出「200 但没保存」）。
        st2, body2 = await get_tools()
        e2 = next(
            (t for t in (body2.get("tools") or []) if (t.get("function") or {}).get("name") == "note_manage"),
            None,
        )
        async with async_session_factory() as db:
            db_flag = (
                await db.execute(
                    text(
                        "SELECT disabled FROM ai_agent_tool_pref "
                        "WHERE user_id = :u AND tool_name = :t"
                    ),
                    {"u": PROBE_UID, "t": "note_manage"},
                )
            ).scalar()
        T(
            "P3",
            "开关真的落库（复读 GET + 直连 SQL 两路一致）",
            "GET.disabled==1 且库里的 disabled==1",
            f"get_disabled={None if e2 is None else e2.get('disabled')} db_disabled={db_flag}",
            bool(e2) and e2.get("disabled") == 1 and int(db_flag or 0) == 1,
        )

        # ================= P4. 字段名写错 → 422（extra='forbid'） =================
        st_bad, body_bad = await put({"tool": "note_manage", "enable": 0})
        st_good, body_good = await put({"tool": "note_manage", "disabled": 1})
        T(
            "P4a",
            "字段名写错 → 422（不是静默 200）",
            "HTTP 422",
            f"status={st_bad} body_keys={list((body_bad or {}).keys())}",
            st_bad == 422,
            "pydantic v2 默认 extra='ignore' 会把它吃成 200 + 什么都没保存",
        )
        T(
            "P4b",
            "正对照：字段名写对 → 200 且带 tools",
            "HTTP 200 且有 tools 键",
            f"status={st_good} has_tools={'tools' in (body_good or {})}",
            st_good == 200 and "tools" in (body_good or {}),
        )

        # ================= P5. 未知工具名 → 拒绝（不是静默成功） =================
        st_unk, body_unk = await put({"tool": "no_such_tool__probe", "disabled": 1})
        # ⚠️ 只断言「没有 tools 键」是不够的 —— catch_all 的假 200（路由万一没注册上）
        #    同样没有 tools 键，那样这条会**恒绿**。所以同时咬住 code/msg：
        #    真拒绝是 `error("工具不存在：…", code=400)`；假成功是 `{code:200,msg:'操作成功'}`。
        T(
            "P5",
            "未知工具名 → 明确拒绝（且不是 catch_all 的假 200）",
            "code==400 且 msg 指明工具不存在；body 里没有 tools 键",
            f"status={st_unk} code={body_unk.get('code')} msg={body_unk.get('msg')!r} "
            f"keys={list((body_unk or {}).keys())}",
            int(body_unk.get("code") or 0) == 400
            and "工具不存在" in str(body_unk.get("msg") or "")
            and "tools" not in (body_unk or {}),
        )

        # ================= P6. 执行侧闸门（ds-free 单步 + 预演），零成本 =================
        st_ex, res_ex = await execute("note_manage", {"action": "list"})
        T(
            "P6a",
            "被屏蔽时 /ai/agent/execute 返回 fail 信封且无业务数据",
            "success is False、有 error 与 hint、且没有 notes 字段",
            f"success={res_ex.get('success')} error={res_ex.get('error')!r} "
            f"has_hint={bool(res_ex.get('hint'))} has_notes={'notes' in res_ex}",
            res_ex.get("success") is False and bool(res_ex.get("error"))
            and bool(res_ex.get("hint")) and "notes" not in res_ex,
        )
        r_prev = await client.post(
            "/ai/agent/preview",
            json={
                "tool": "note_manage",
                "params": {"action": "delete", "note_id": 1},
                "userId": PROBE_UID,
            },
        )
        prev_body = r_prev.json() or {}
        T(
            "P6b",
            "被屏蔽时预演同样被拒（两条链路一致）",
            "success is False（不给预览）",
            f"keys={list(prev_body.keys())} success={prev_body.get('success')}",
            prev_body.get("success") is False,
        )

        # 打开回来 → 同一个调用必须成功（负/正对照，证明上面那条不是因为接口本来就坏）
        await put({"tool": "note_manage", "disabled": 0})
        st_ok, res_ok = await execute("note_manage", {"action": "list"})
        T(
            "P6c",
            "重新打开后同一调用成功（正对照）",
            "success is True 且带 notes 字段",
            f"success={res_ok.get('success')} has_notes={'notes' in res_ok}",
            res_ok.get("success") is True and "notes" in res_ok,
        )
        # 未被屏蔽的另一个工具不受影响
        st_b, res_b = await execute("bank_manage", {"action": "list"})
        T(
            "P6d",
            "屏蔽是**按工具**的，同用户其它工具照常",
            "bank_manage.list 仍然 success is True",
            f"success={res_b.get('success')} keys={sorted(res_b.keys())[:6]}",
            res_b.get("success") is True,
        )

        # ================= P7. POST /ai/sessions 不再写行；首条消息懒建 =================
        r_new = await client.post(f"/ai/sessions?userId={PROBE_UID}")
        new_body = r_new.json() or {}
        sid = ((new_body.get("data") or {}) or {}).get("sessionId")
        created_sessions.append(sid)
        async with async_session_factory() as db:
            n_rows = (
                await db.execute(
                    text("SELECT COUNT(*) FROM ai_chat_session WHERE session_id = :s"),
                    {"s": sid},
                )
            ).scalar()
        T(
            "P7a",
            "POST /ai/sessions 只发 id、不写库",
            "响应有 sessionId，且库里查不到这一行",
            f"status={r_new.status_code} sessionId={sid} rows={n_rows}",
            bool(sid) and int(n_rows or 0) == 0,
        )

        first_msg = f"__toolpref_probe__ 第一条消息 {int(time.time())}"
        await conversation_service.save_message(PROBE_UID, sid, "user", first_msg)
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT title, message_count FROM ai_chat_session WHERE session_id = :s"
                    ),
                    {"s": sid},
                )
            ).first()
        # ⚠️ 标题会被 `SESSION_TITLE_LIMIT`（30 字）截断 —— 拿完整消息去比会**永远红**。
        #    按同一个常量算期望值，才是「标题取首条用户消息」这条性质本身。
        from app.services.ai.conversation_service import SESSION_TITLE_LIMIT

        expect_title = first_msg.replace("\n", " ")[:SESSION_TITLE_LIMIT]
        T(
            "P7b",
            "首条消息把它懒建出来，且标题取首条用户消息",
            f"行存在、title == 首条消息截到 {SESSION_TITLE_LIMIT} 字、message_count == 1",
            f"row={row} expect_title={expect_title!r}",
            bool(row) and str(row[0] or "") == expect_title and int(row[1] or 0) == 1,
        )
        async with async_session_factory() as db:
            ids = set(
                r[0]
                for r in (
                    await db.execute(
                        text("SELECT session_id FROM ai_chat_session WHERE user_id = :u"),
                        {"u": PROBE_UID},
                    )
                ).all()
            )
        T(
            "P7c",
            "懒建只造出这一个会话（没有顺手多写）",
            f"user_id={PROBE_UID} 的会话集合 == {{刚建的那个}}",
            f"ids={sorted(ids)}",
            ids == {sid},
        )

        # ================= P8. 两条**真实出口**（走 run_agent_stream，不调模型） ==========
        # 手法：消费到第一个 `waiting` 事件就 close —— `waiting` 在 `llm.astream()` **之前**下发，
        # 所以系统提示词已经组好、工具定义已经算完，而一个模型请求都没发出去。
        await put({"tool": "note_manage", "disabled": 1})
        await put({"tool": "memory_search", "disabled": 1})

        from app.services.ai import prompts as prompts_mod

        real_build = prompts_mod.build_agent_system_prompt
        captured: dict = {}

        def _spy(*args, **kwargs):
            captured["tools_text"] = kwargs.get("tools_text", "")
            return real_build(*args, **kwargs)

        prompts_mod.build_agent_system_prompt = _spy

        async def probe_exits(tag: str):
            """跑一遍 run_agent_stream，收集 meta 事件 + 系统提示词里的工具清单"""
            from app.services.ai.agent.loop import AgentRequest, run_agent_stream

            captured.clear()
            events = []
            async with async_session_factory() as db:
                gen = run_agent_stream(db, AgentRequest(message="hi", user_id=PROBE_UID))
                try:
                    async for line in gen:
                        line = (line or "").strip()
                        if not line or line == "[DONE]":
                            continue
                        import json as _json

                        try:
                            ev = _json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        events.append(ev)
                        if ev.get("type") in ("meta", "error", "done"):
                            if ev.get("type") == "meta":
                                continue
                            break
                        if ev.get("type") == "waiting":
                            break
                finally:
                    await gen.aclose()
            return events

        ev_on = await probe_exits("disabled")
        meta_on = next((e for e in ev_on if e.get("type") == "meta"), None)
        err_on = next((e for e in ev_on if e.get("type") == "error"), None)
        if meta_on is None:
            T(
                "P8a",
                "meta 事件的可用工具 = 生效后清单",
                "meta.tools 不含被屏蔽的两个、含 bank_manage",
                f"没有拿到 meta 事件；error={err_on}",
                False,
                "拿不到 meta（多半是模型配置问题）→ 本组其余用例一并作废",
            )
            T("P8b", "系统提示词的工具清单同样排除", "describe(exclude=…) 生效", "未测到", False)
            T("P8c", "正对照：没有屏蔽时两者都含 note_manage", "含", "未测到", False)
        else:
            names_on = [t.get("name") for t in (meta_on.get("tools") or [])]
            T(
                "P8a",
                "meta 事件的可用工具 = 生效后清单",
                "不含 note_manage / memory_search，含 bank_manage",
                f"names={sorted(names_on)}",
                "note_manage" not in names_on
                and "memory_search" not in names_on
                and "bank_manage" in names_on,
            )
            text_on = captured.get("tools_text") or ""
            entries_on = _desc_tools(text_on)
            T(
                "P8b",
                "系统提示词的工具清单同样排除（describe(exclude=…)）",
                "tools_text 的条目行里没有 note_manage / memory_search，但有 bank_manage",
                f"entries={entries_on}",
                "note_manage" not in entries_on
                and "memory_search" not in entries_on
                and "bank_manage" in entries_on,
                "⚠️ 按条目行判，不按子串 —— memory_search 的描述里会引用 note_manage",
            )
            # 正对照：全部打开 → 两处都该出现（证明上面不是恒红）
            await put({"tool": "note_manage", "disabled": 0})
            await put({"tool": "memory_search", "disabled": 0})
            ev_off = await probe_exits("enabled")
            meta_off = next((e for e in ev_off if e.get("type") == "meta"), None)
            names_off = [t.get("name") for t in ((meta_off or {}).get("tools") or [])]
            entries_off = _desc_tools(captured.get("tools_text") or "")
            T(
                "P8c",
                "正对照：没有屏蔽时两处都含 note_manage",
                "meta 与提示词的条目行都含 note_manage / memory_search",
                f"meta={sorted(names_off)} prompt_entries={entries_off}",
                "note_manage" in names_off and "note_manage" in entries_off
                and "memory_search" in names_off and "memory_search" in entries_off,
            )
        prompts_mod.build_agent_system_prompt = real_build

        # ================= P10. 内联执行分支的闸门（用假 LLM 驱动，仍然零成本）=========
        # 这一条补的是「api 付费循环里模型真的发起一个被屏蔽工具」那一幕 —— 平时它
        # 必须花一次 LLM 往返才能走到，这里把**模型那一层换掉**：
        #   `db_config.build_agent_llm` 换成假的（返回一个脚本化的 LLM），
        #   于是循环的其余部分（工具定义、闸门、回灌、收尾）全都是**真代码**。
        # 一举验三样：绑给模型的 tools 里没有它、调用被拒（fail 信封 + hint）、
        # 循环继续跑到收尾（不是死掉）。
        from langchain_core.messages import AIMessage

        from app.services.ai import db_config as db_config_mod

        class _FakeLLM:
            """只实现循环用到的那两个方法：bind_tools / astream"""

            def __init__(self, script):
                self.script = script
                self.calls = 0
                self.bound_tools = None

            def bind_tools(self, tools, **kwargs):
                self.bound_tools = list(tools)
                return self

            async def astream(self, messages):
                idx = min(self.calls, len(self.script) - 1)
                self.calls += 1
                for chunk in self.script[idx]:
                    yield chunk

        class _FakeCfg:
            model = "fake-model"
            provider = "fake"

        class _FakeScript:
            """第 1 轮：模型请求调用 note_manage；第 2 轮：给一句收尾正文"""

            def __init__(self):
                self.llm = _FakeLLM(
                    [
                        [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "note_manage",
                                        "args": {"action": "list"},
                                        "id": "call_probe_1",
                                        "type": "tool_call",
                                    }
                                ],
                            )
                        ],
                        [AIMessage(content="收尾：我没有可用的笔记工具。")],
                    ]
                )

        real_build_agent_llm = db_config_mod.build_agent_llm
        # 假 LLM 实例要能被外面取到（才能断言 bind_tools 收到了什么）→ 用一个可变盒子
        holder: dict = {}

        async def _fake_build_agent_llm(_db, **kwargs):
            llm_obj = _FakeScript().llm
            holder["llm"] = llm_obj
            return llm_obj, _FakeCfg()

        # 前提：这个用户此刻屏蔽着 note_manage（P8 的 else 分支刚把它打开过）
        await put({"tool": "note_manage", "disabled": 1})
        db_config_mod.build_agent_llm = _fake_build_agent_llm
        try:
            from app.services.ai.agent.loop import AgentRequest, run_agent_stream

            events = []
            fake_llm = None
            async with async_session_factory() as db:
                gen = run_agent_stream(
                    db, AgentRequest(message="列一下我的笔记", user_id=PROBE_UID)
                )
                try:
                    async for line in gen:
                        line = (line or "").strip()
                        if not line or line == "[DONE]":
                            continue
                        import json as _json

                        try:
                            events.append(_json.loads(line))
                        except Exception:  # noqa: BLE001
                            continue
                finally:
                    await gen.aclose()
                fake_llm = holder.get("llm")

            bound_names = _names(fake_llm.bound_tools if fake_llm else [])
            tr = [
                e
                for e in events
                if e.get("type") == "tool_result" and e.get("tool") == "note_manage"
            ]
            sc = [
                e
                for e in events
                if e.get("type") == "self_correct" and e.get("tool") == "note_manage"
            ]
            done = next((e for e in events if e.get("type") == "done"), None)
            T(
                "P10a",
                "内联循环：绑给模型的 tools 里没有被屏蔽的工具",
                "bind_tools 收到的名字里不含 note_manage",
                f"bound={sorted(bound_names)}",
                "note_manage" not in bound_names and "bank_manage" in bound_names,
                "这是出口 #1（真·Function Calling 参数），不是提示词文本",
            )
            T(
                "P10b",
                "内联循环：模型硬调被屏蔽工具 → 被拒并回灌（含 hint）",
                "有 tool_result(success=False, 文案含「屏蔽」) 与 self_correct",
                f"tool_result={tr[:1]} self_correct={sc[:1]}",
                len(tr) == 1
                and tr[0].get("success") is False
                and "屏蔽" in str(tr[0].get("message") or "")
                and (tr[0].get("data") or {}).get("hint")
                and len(sc) == 1
                and "屏蔽" in str(sc[0].get("reason") or ""),
            )
            T(
                "P10c",
                "内联循环：被拒后循环**继续**跑到收尾（不是死掉）",
                "拿到 done 事件，且 answer 是第 2 轮的正文",
                f"done={None if done is None else done.get('answer')!r} "
                f"types={[e.get('type') for e in events]}",
                bool(done) and "收尾" in str(done.get("answer") or ""),
                "这一条就是「不要因为用户关了工具就把整轮弄死」的机器断言",
            )
        finally:
            db_config_mod.build_agent_llm = real_build_agent_llm

        # ---------- P11：界面中文层 + 「全选」批量写 ----------
        # 用户需求：「可用工具有英汉双份 —— 给用户展示中文，给 ai 发送英文；工具要有一键全选」。
        # 这一组盯的是**两条道不许串**：中文只走 `label` / `descriptionZh`（`function` 外面），
        # 模型侧（definitions / describe / function 子对象）不许出现中文层的内容。
        import json as _json2
        import re as _re2

        _CJK = _re2.compile(r"[\u4e00-\u9fff]")

        def _cjk_runs(s: str) -> set:
            """取出串里**每一段**连续中文 —— 白名单比对用。

            ⚠️ 不能把整串的中文拼成一个指纹：一句话里出现两个中文词时，拼起来会得到
            一个根本不存在的词（本探针第一版得到 `错题本斩题`，白名单永远对不上）。
            也**不能**把每个字单拆：那样「二次函数」被拆成四个字，白名单读起来没有意义。
            按「连续段」取，才是人读得懂、又能精确比对的最小单位。
            """
            return set(_re2.findall(r"[\u4e00-\u9fff]+", s))

        def _leaf_strings(o, out=None):
            out = [] if out is None else out
            if isinstance(o, str):
                out.append(o)
            elif isinstance(o, dict):
                for v in o.values():
                    _leaf_strings(v, out)
            elif isinstance(o, list):
                for v in o:
                    _leaf_strings(v, out)
            return out

        _get_resp = await client.get("/ai/agent/tools")
        _st_get = _get_resp.status_code
        try:
            _payload = _get_resp.json()
        except Exception:  # noqa: BLE001
            _payload = {}
        _payload = _payload if isinstance(_payload, dict) else {}
        _items = _payload.get("tools") or []
        _n_tools = len(registry.names())

        # P11a：10 个工具的中文都填了（含 CJK，防英文占位）
        _bad_zh = [
            (it.get("function") or {}).get("name")
            for it in _items
            if not (it.get("label") or "").strip()
            or not (it.get("descriptionZh") or "").strip()
            or not _CJK.search(it.get("label") or "")
            or not _CJK.search(it.get("descriptionZh") or "")
        ]
        T(
            "P11a",
            "界面中文层：每个工具的 label / descriptionZh 都非空且含中文",
            f"{_n_tools} 个工具，0 个不合格",
            f"tools={len(_items)} 不合格={_bad_zh}",
            _st_get == 200 and len(_items) == _n_tools and not _bad_zh,
            "「给用户展示中文」的前提 —— 中文缺一个，面板上就会露出英文标识或空白",
        )

        # P11b：载荷形状 —— 中文在 `function` 外面，`function` 的键一个不多一个不少
        _shape = [
            {
                "name": (it.get("function") or {}).get("name"),
                "fn_keys": sorted((it.get("function") or {}).keys()),
                "top_keys": sorted(it.keys()),
            }
            for it in _items
        ]
        _bad_shape = [
            s
            for s in _shape
            if s["fn_keys"] != ["description", "name", "parameters"]
            or "label" not in s["top_keys"]
            or "descriptionZh" not in s["top_keys"]
        ]
        T(
            "P11b",
            "载荷：中文挂在 `function` **外面**，`function` 的键恰好 {name,description,parameters}",
            "0 个形状不对",
            f"不合格={_bad_shape[:2]} 首项={_shape[:1]}",
            len(_shape) == _n_tools and not _bad_shape,
            "ds-free 前端直接拿 function.name/.parameters 拼提示词 —— "
            "中文一旦进了 function 就会跟着进提示词",
        )

        # P11c：核心守卫 —— 中文层**不许泄漏**到模型侧（这就是「给 ai 发送英文」）
        _model_text = (
            _json2.dumps(registry.definitions(), ensure_ascii=False)
            + "\n"
            + registry.describe()
        )
        _leaked = []
        for _it in _items:
            for _k in ("label", "descriptionZh"):
                _v = (_it.get(_k) or "").strip()
                if _v and _v in _model_text:
                    _leaked.append(((_it.get("function") or {}).get("name"), _k, _v))
        T(
            "P11c",
            "核心守卫：模型侧（definitions / describe）里**不含**任何 label / descriptionZh 的内容",
            "0 处泄漏",
            f"泄漏={_leaked[:3]}",
            not _leaked,
            "这条就是「给 ai 发送英文」的机器保证："
            "中文层只存在于 function 外面的兄弟字段里",
        )

        # P11d：中文普查 —— 模型侧**新增**中文会被发现（既有的 4 处是有意为之的数据/词条）
        #
        # 白名单（按「连续中文段」比对，英文措辞改动不该让它红）：
        #   · 错题本   —— 产品术语，用户嘴上就叫这个名字，模型要能对上（`flag_type=error`）
        #   · 斩题     —— 同上，`master` 这个动作在界面上就叫「斩题」
        #   · 二次函数 —— 检索关键词的**中文示例**（用户数据本来就是中文）
        #   · 副本     —— `copy` 真的会生成的默认库名（是数据，不是散文）
        # 这四处都是「中文**数据**」，不是「中文**散文**」，所以留着。
        # ⚠️ 新增工具时把中文描述写进 `description`、或再引入第五处中文 → 这条立刻红。
        # ⚠️ 反过来，若某处中文被删掉，**这条也会红** —— 那是要你回来把白名单一起改掉的
        #    信号（白名单不许悄悄过期）。
        _ALLOW_CJK = {"错题本", "斩题", "二次函数", "副本"}
        _runs: set = set()
        for _s in _leaf_strings(registry.definitions()):
            _runs |= _cjk_runs(_s)
        _runs |= _cjk_runs(registry.describe())
        T(
            "P11d",
            "模型侧中文普查：只允许已知的 4 处（中文数据/词条），新增一处就红",
            f"中文段集合 == {sorted(_ALLOW_CJK)}",
            f"实际={sorted(_runs)}",
            _runs == _ALLOW_CJK,
            "白名单在注释里逐条写着理由；动这条之前先确认那处中文是「数据」还是「散文」",
        )

        # P11e：「全选」批量写 —— 一次事务改全部，且是**稀疏**语义（全部启用 = 删行）
        _st_all, _body_all = await put({"all": True, "disabled": 1})
        _after_on = {
            (it.get("function") or {}).get("name"): it.get("disabled")
            for it in (_body_all.get("tools") or [])
        }
        async with async_session_factory() as db:
            _rows_on = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM ai_agent_tool_pref "
                        "WHERE user_id = :u AND disabled = 1"
                    ),
                    {"u": PROBE_UID},
                )
            ).scalar()
        _st_off, _body_off = await put({"all": True, "disabled": 0})
        _after_off = {
            (it.get("function") or {}).get("name"): it.get("disabled")
            for it in (_body_off.get("tools") or [])
        }
        async with async_session_factory() as db:
            _rows_off = (
                await db.execute(
                    text("SELECT COUNT(*) FROM ai_agent_tool_pref WHERE user_id = :u"),
                    {"u": PROBE_UID},
                )
            ).scalar()
        # 再往返一次（幂等）
        _st_r1, _ = await put({"all": True, "disabled": 1})
        _st_r2, _body_r2 = await put({"all": True, "disabled": 0})
        _after_r2 = {
            (it.get("function") or {}).get("name"): it.get("disabled")
            for it in (_body_r2.get("tools") or [])
        }
        T(
            "P11e",
            "「全选」批量写：全屏蔽 → 全部 disabled=1；全部启用 → 稀疏还原（0 行）",
            f"屏蔽后 {_n_tools} 行 disabled=1 / 启用后 0 行，两次往返结果一致",
            f"on: rows={_rows_on} full={len(_after_on)} all1="
            f"{all(v == 1 for v in _after_on.values())} | "
            f"off: rows={_rows_off} full={len(_after_off)} all0="
            f"{all(v == 0 for v in _after_off.values())} | 往返 {_st_r1}/{_st_r2}",
            _st_all == 200
            and len(_after_on) == _n_tools
            and int(_rows_on or 0) == _n_tools
            and all(v == 1 for v in _after_on.values())
            and _st_off == 200
            and len(_after_off) == _n_tools
            and int(_rows_off or 0) == 0
            and all(v == 0 for v in _after_off.values())
            and (_st_r1, _st_r2) == (200, 200)
            and len(_after_r2) == _n_tools
            and all(v == 0 for v in _after_r2.values()),
            "稀疏语义：没有行 = 启用，所以「全部启用」的正解是删行而不是写一堆 0 留着；"
            "响应体必须有 `tools`（catch_all 假 200 的 body 里没有它）",
        )

        # P11f：含糊/缺失的目标一律不许猜 —— 静默猜一个会一次改掉整个面板
        #
        # ⚠️ 口径：本项目的 **400 走的是 HTTP 200 + body.code=400**（`error()` 的封装），
        #    所以 400 那三条必须**读 body 的 code**，不能读 HTTP 状态码 ——
        #    读状态码会把「被拒绝」当成「保存成功」，那正是这条断言要防的事。
        #    422 是 pydantic 校验失败，走的是真 HTTP 状态码。
        _st_miss, _ = await put({"all": True})
        _st_none, _ = await put({})
        _st_both, _b_both = await put({"all": True, "tool": "bank_manage", "disabled": 1})
        _st_unknown, _b_unknown = await put({"tool": "no_such_tool", "disabled": 1})
        _st_empty, _b_empty = await put({"tool": "", "disabled": 1})

        def _code(b) -> int:
            try:
                return int(((b or {}).get("code")) or 0)
            except Exception:  # noqa: BLE001
                return 0

        T(
            "P11f",
            "目标校验：缺 disabled / 空体 → 422；`all` 与 `tool` 同给、都不给、未知工具名 → 400",
            "422 / 422 / 400 / 400 / 400（400 读 body.code）",
            f"all-only={_st_miss} none={_st_none} both={_st_both}/code={_code(_b_both)} "
            f"unknown={_st_unknown}/code={_code(_b_unknown)} "
            f"empty-tool={_st_empty}/code={_code(_b_empty)}",
            (_st_miss, _st_none) == (422, 422)
            and _code(_b_both) == 400
            and _code(_b_unknown) == 400
            and _code(_b_empty) == 400,

            "含糊的请求不许猜：猜错会静默改掉用户整个面板",
        )

        # P11g：IDOR —— 批量写只动调用者自己的行
        _OTHER_UID = PROBE_UID + 1
        try:
            async with async_session_factory() as db:
                await db.execute(
                    text(
                        "INSERT INTO ai_agent_tool_pref "
                        "(user_id, tool_name, disabled, create_time, update_time) "
                        "VALUES (:u, :t, 0, NOW(), NOW())"
                    ),
                    {"u": _OTHER_UID, "t": "bank_manage"},
                )
                await db.commit()
            await put({"all": True, "disabled": 1})
            async with async_session_factory() as db:
                _other_flag = (
                    await db.execute(
                        text(
                            "SELECT disabled FROM ai_agent_tool_pref "
                            "WHERE user_id = :u AND tool_name = :t"
                        ),
                        {"u": _OTHER_UID, "t": "bank_manage"},
                    )
                ).scalar()
            await put({"all": True, "disabled": 0})
            async with async_session_factory() as db:
                _other_left = (
                    await db.execute(
                        text("SELECT COUNT(*) FROM ai_agent_tool_pref WHERE user_id = :u"),
                        {"u": _OTHER_UID},
                    )
                ).scalar()
            T(
                "P11g",
                "IDOR：批量写只动登录用户自己的行（另一个 uid 的行一字未变、也没被删掉）",
                "另一个 uid 的行 disabled 仍为 0，且「全部启用」后它还在",
                f"other_flag={_other_flag} rows_left={_other_left}",
                int(_other_flag or 0) == 0 and int(_other_left or 0) == 1,
                "归属只来自 current_user；「全部启用」的删行也必须限定 user_id"
                "（否则等于清掉别人的配置）",
            )
        finally:
            # 只删本探针自己造的那一行（这是测试数据，不是用户数据）
            async with async_session_factory() as db:
                await db.execute(
                    text("DELETE FROM ai_agent_tool_pref WHERE user_id = :u"),
                    {"u": _OTHER_UID},
                )
                await db.commit()

    finally:
        # ---------- 收尾：只删本次探针造的数据（精确匹配） ----------
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM ai_agent_tool_pref WHERE user_id = :u"), {"u": PROBE_UID}
            )
            for sid in created_sessions:
                if not sid:
                    continue
                await db.execute(
                    text("DELETE FROM ai_chat_message WHERE user_id = :u AND session_id = :s"),
                    {"u": PROBE_UID, "s": sid},
                )
                await db.execute(
                    text("DELETE FROM ai_agent_timeline WHERE user_id = :u AND session_id = :s"),
                    {"u": PROBE_UID, "s": sid},
                )
                await db.execute(
                    text("DELETE FROM ai_chat_session WHERE user_id = :u AND session_id = :s"),
                    {"u": PROBE_UID, "s": sid},
                )
            await db.commit()

            post_pref = set(
                (r[0], r[1], r[2])
                for r in (
                    await db.execute(
                        text("SELECT user_id, tool_name, disabled FROM ai_agent_tool_pref")
                    )
                ).all()
            )
            post_sessions = set(
                r[0]
                for r in (await db.execute(text("SELECT session_id FROM ai_chat_session"))).all()
            )
            post_msgs = set(
                r[0] for r in (await db.execute(text("SELECT id FROM ai_chat_message"))).all()
            )
            left_pref = (
                await db.execute(
                    text("SELECT COUNT(*) FROM ai_agent_tool_pref WHERE user_id = :u"),
                    {"u": PROBE_UID},
                )
            ).scalar()

        # 真实数据一字未变：工具开关表**整表**回比（不只是本 uid）
        pre_pref_cmp = set(pre_pref or set())
        T(
            "P9a",
            "工具开关表：真实用户的行一字未变（整表回比）",
            "跑前集合 == 跑后集合，且本 uid 残留 0 行",
            f"before={len(pre_pref_cmp)} after={len(post_pref)} left_probe={left_pref}",
            pre_pref == post_pref and int(left_pref or 0) == 0,
            "⚠️ 若本次是**探针自己补建**的表（跑前不存在），跑前快照是空集，"
            "这条就只等于「探针没留下残留行」；表本来就存在时它才是「真实用户行集合的回比」"
            f"（本次 bootstrapped={bootstrapped}）",
        )
        T(
            "P9b",
            "ai_chat_session / ai_chat_message 真实数据一字未变",
            "会话 id 集合与消息 id 集合都与跑前完全相同",
            f"sessions {len(pre_sessions)}→{len(post_sessions)} msgs {len(pre_msgs)}→{len(post_msgs)}",
            pre_sessions == post_sessions and pre_msgs == post_msgs,
        )

        await client.aclose()

    print("\n---- 结果 ----")
    for r in ROWS:
        print(f"  [{'通过' if r['ok'] else '失败'}] {r['cid']} {r['title']}")
        print(f"        期望: {r['expected']}")
        print(f"        实际: {r['actual']}")
        if r["detail"]:
            print(f"        说明: {r['detail']}")
    red = [r for r in ROWS if not r["ok"]]
    print(f"\n合计：{len(ROWS) - len(red)}/{len(ROWS)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    print("NOT RUN（本跑手不覆盖；不是「通过」）：")
    print("  · **真实**模型端到端：真 provider 流式返回 tool_call 那一段（P10 把模型那一层")
    print("    换成了假 LLM —— 循环其余部分是真代码，但「真模型会不会真去调被屏蔽的工具」")
    print("    仍需一次付费 LLM 往返）")
    print("  · 全部工具被屏蔽时「退化成纯聊天」的回复质量（同上，要一次 LLM 往返；")
    print("    本跑手只保证了不 bind_tools、提示词里说了本轮没有工具、不报服务端配置错）")
    print("  · 前端工具面板的开关 UI 与 ds-free 消费侧（属前端产权，需浏览器，本跑手不碰）")
    return 1 if red else 0


async def _table_exists(db, name: str) -> bool:
    from sqlalchemy import text

    return bool(
        await db.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :n"
            ),
            {"n": name},
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="工具开关闸门 + 空会话懒建（零成本）")
    ap.add_argument("--mutate", default="", choices=["", *MUTATIONS.keys()],
                    help="把某处闸门改回旧行为（应当红）")
    args = ap.parse_args()

    originals: dict = {}
    md5_before: dict = {}
    for path in {LOOP_PY, AI_PY}:
        originals[path] = path.read_bytes()
        md5_before[path] = hashlib.md5(originals[path]).hexdigest()
        print(f"[md5] {path.name} 跑前 = {md5_before[path]}")

    if args.mutate:
        todo = MUTATIONS[args.mutate]
        edited: dict = {}
        for path, label, old, new in todo:
            src = edited.get(path, originals[path].decode("utf-8"))
            hits = src.count(old)
            assert hits == 1, f"变异锚点不唯一：{label} 命中 {hits} 次（锚点漂了）"
            edited[path] = src.replace(old, new)
            print(f"[mutate:{args.mutate}] {label}: 命中 1 次 → 已替换")
        for path, text_src in edited.items():
            path.write_bytes(text_src.encode("utf-8"))
        print(f"[mutate:{args.mutate}] 已写入变异体")
        time.sleep(1.5)

    try:
        return asyncio.run(run_probe())
    finally:
        for path, blob in originals.items():
            path.write_bytes(blob)
            back = hashlib.md5(path.read_bytes()).hexdigest()
            print(f"[md5] {path.name} 还原后 = {back} / 与跑前一致 = {back == md5_before[path]}")


if __name__ == "__main__":
    raise SystemExit(main())
