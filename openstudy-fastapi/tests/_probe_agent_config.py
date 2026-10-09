# -*- coding: utf-8 -*-
"""用户自定义智能体（阶段 2）探针 —— 纯逻辑部分零依赖；CRUD 部分用独立 probe uid 连 DB

覆盖：
  1. `orchestrator.build_user_role`：dict → RoleSpec 转换（工具白名单 / 人设 / key 前缀）
  2. CRUD：create / list / get / update / delete（逻辑删除）+ 名字冲突 + 额度无关
  3. IDOR：他人 user_id 取不到、改不动、删不掉
  4. 工具名校验：非法工具名被 API 层 `_validate_agent_tools` 拒绝
  5. 与编排层联动：用户 Agent 的工具白名单确实收窄了可绑工具

⚠️ 这是**刻意保留**的验证脚本。用 `PROBE_UID`（一个不存在的用户 id）造数据，
跑完在 finally 里按 uid 精确清理，**不碰真实用户数据**。

用法
----
    .venv/Scripts/python.exe tests/_probe_agent_config.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

#: 探针专用用户 id（远大于真实自增用户 id，且服务层要求 uid>0）。
#: 用正数是因为 `create_agent` 把 `uid <= 0` 判为「未登录」—— 那是服务层的正确防护，
#: 探针不该绕过它，而应提供**合法的正数 uid**。
PROBE_UID = 2_000_900_001
PROBE_UID_OTHER = 2_000_900_002

ROWS = []


def check(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def _cleanup() -> None:
    """按 probe uid 精确清理（含逻辑删除的行）。"""
    from sqlalchemy import delete

    from app.database import async_session_factory, engine
    from app.models.agent_config import AiAgentConfig

    try:
        async with async_session_factory() as db:
            await db.execute(
                delete(AiAgentConfig).where(AiAgentConfig.user_id.in_([PROBE_UID, PROBE_UID_OTHER]))
            )
            await db.commit()
    finally:
        await engine.dispose()


async def run_probe() -> int:
    # ⚠️ 必须先注册全部 ORM 模型：`SysUser` 有 `relationship('SysRole')`，若只 import
    #    自己需要的模型，mapper 解析时会因 `SysRole` 未加载而报
    #    `InvalidRequestError: expression 'SysRole' failed to locate a name`。
    from app.database import register_all_models

    register_all_models()

    from app.services.ai.agent import agent_config_service as svc
    from app.services.ai.agent import orchestrator

    # ---- 1. build_user_role（纯逻辑，零依赖）----
    r = orchestrator.build_user_role(
        {
            "agentId": 7,
            "name": "数学老师",
            "personaPrompt": "You are a strict math tutor.",
            "tools": ["bank_manage", "question_manage"],
            "model": "deepseek-chat",
        }
    )
    check("AC-01", "user RoleSpec key 带 user: 前缀", r.key == "user:7", r.key)
    check("AC-02", "user RoleSpec 工具白名单正确", r.tools == ("bank_manage", "question_manage"), str(r.tools))
    check("AC-03", "user RoleSpec 人设进 prompt_fragment", "strict math tutor" in r.prompt_fragment, r.prompt_fragment[:60])
    check("AC-04", "user RoleSpec 名字保留中文", r.name == "数学老师", r.name)

    r2 = orchestrator.build_user_role({"agentId": 8, "name": "哑巴", "personaPrompt": "", "tools": []})
    check("AC-05", "空人设 → prompt_fragment 为空", r2.prompt_fragment == "", repr(r2.prompt_fragment))
    check("AC-06", "空工具 → tools 为空（= 不限制）", r2.tools == (), str(r2.tools))

    # ---- 2. CRUD（连 DB）----
    await _cleanup()  # 先清一次，保证起点干净

    created = await svc.create_agent(
        PROBE_UID,
        name="语文助手",
        persona_prompt="You help with Chinese essays.",
        description="作文辅导",
        tools=["note_manage"],
        model="",
    )
    aid = created["agentId"]
    check("AC-07", "create 返回 agentId", isinstance(aid, int) and aid > 0, str(aid))
    check("AC-08", "create 工具白名单归一", created["tools"] == ["note_manage"], str(created["tools"]))

    lst = await svc.list_agents(PROBE_UID)
    check("AC-09", "list 含新建的", any(a["agentId"] == aid for a in lst), f"count={len(lst)}")

    got = await svc.get_agent_dict(PROBE_UID, aid)
    check("AC-10", "get 取到本人智能体", got and got["agentId"] == aid, str(got)[:80])

    upd = await svc.update_agent(PROBE_UID, aid, name="语文助教", persona_prompt="Updated persona.")
    check("AC-11", "update 改名成功", upd["name"] == "语文助教", upd["name"])
    check("AC-12", "update 人设生效", "Updated persona" in upd["personaPrompt"], upd["personaPrompt"])

    # 名字冲突
    await svc.create_agent(PROBE_UID, name="数学助手", persona_prompt="x")
    conflict = False
    try:
        await svc.create_agent(PROBE_UID, name="语文助教", persona_prompt="y")
    except svc.AgentConfigError:
        conflict = True
    check("AC-13", "重名 → AgentConfigError", conflict, f"conflict={conflict}")

    # ---- 3. IDOR ----
    other_get = await svc.get_agent_dict(PROBE_UID_OTHER, aid)
    check("AC-14", "他人无法 get 到", other_get is None, str(other_get))
    other_upd_blocked = False
    try:
        await svc.update_agent(PROBE_UID_OTHER, aid, name="hacked")
    except svc.AgentConfigError:
        other_upd_blocked = True
    check("AC-15", "他人无法 update", other_upd_blocked, f"blocked={other_upd_blocked}")
    other_del_blocked = False
    try:
        await svc.delete_agent(PROBE_UID_OTHER, aid)
    except svc.AgentConfigError:
        other_del_blocked = True
    check("AC-16", "他人无法 delete", other_del_blocked, f"blocked={other_del_blocked}")

    # ---- 4. 逻辑删除 ----
    await svc.delete_agent(PROBE_UID, aid)
    after_del = await svc.get_agent_dict(PROBE_UID, aid)
    check("AC-17", "删除后 get 不到（逻辑删除生效）", after_del is None, str(after_del))
    lst2 = await svc.list_agents(PROBE_UID)
    check("AC-18", "删除后 list 不含它", all(a["agentId"] != aid for a in lst2), f"count={len(lst2)}")

    # ---- 5. 工具名校验（复用 API 层的校验口径）----
    from app.api.v1.ai import _validate_agent_tools

    try:
        _validate_agent_tools(["bank_manage", "ghost_tool_xyz"])
        bad_ok = False
    except ValueError:
        bad_ok = True
    check("AC-19", "非法工具名被拒", bad_ok, f"raised={bad_ok}")
    try:
        norm = _validate_agent_tools(["bank_manage", "note_manage"])
        ok_pass = norm == ["bank_manage", "note_manage"]
    except ValueError:
        ok_pass = False
    check("AC-20", "合法工具名通过", ok_pass, str(norm if ok_pass else None))

    # ---- 6. 与编排层联动：用户 Agent 白名单收窄可绑工具 ----
    from app.services.ai.agent.registry import ensure_tools_loaded, registry

    ensure_tools_loaded()
    all_names = set(registry.names())
    user_role = orchestrator.build_user_role(
        {"agentId": 1, "name": "x", "personaPrompt": "p", "tools": ["bank_manage"]}
    )
    ex = orchestrator.compute_exclude(user_role, all_tool_names=all_names, user_disabled=set())
    effective = all_names - ex
    check("AC-21", "用户 Agent 生效工具 == 其白名单", effective == {"bank_manage"}, str(sorted(effective)))

    await _cleanup()
    print("\n---- 用户自定义智能体（阶段 2）探针结果 ----")
    for rec in ROWS:
        tail = "" if rec["status"] == "通过" else f" | 实际: {rec['actual']}"
        print(f"  [{rec['status']}] {rec['cid']} {rec['title']}{tail}")
    red = [rec for rec in ROWS if rec["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
