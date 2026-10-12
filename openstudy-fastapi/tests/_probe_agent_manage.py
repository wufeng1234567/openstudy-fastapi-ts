# -*- coding: utf-8 -*-
"""探针：对话式创建智能体（`agent_manage` 工具 + `agent_builder` 专家）—— 用户 2026-10-12

零 DB、零网络、零 LLM 成本：只做注册表 / 角色表 / 工具纯逻辑校验。

覆盖：
  1. `agent_manage` 已注册；描述/参数为英文，label/description_zh 为中文（两条语言道）；
  2. 它是写操作工具，create/update/delete 需确认、list 不需；delete 是破坏性的；
  3. 参数 schema 合法（action 枚举、required）；
  4. `agent_builder` 角色存在、白名单恰为 agent_manage、有 capability（可被委派/可开关）；
  5. `compute_exclude(agent_builder)` → 生效工具 = {agent_manage} ∪ 全局工具；
  6. `_clean_tools`：空→None（不限）；非法工具名→被识别为 invalid；合法名→保留去重；
  7. 关键词路由：说「创建智能体 / 建一个助手」倾向命中 agent_builder。

用法：.venv/Scripts/python.exe tests/_probe_agent_manage.py   # 退出 0
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "ok": bool(cond), "actual": actual})


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def run_probe() -> int:
    from app.services.ai.agent.registry import ensure_tools_loaded, registry
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import orchestrator
    from app.services.ai.agent.tools.agent_manage import AgentManageTool

    ensure_tools_loaded()
    all_names = set(registry.names())

    # ---- 1. 注册 & 语言道 ----
    check("AM-01", "agent_manage 已注册", "agent_manage" in all_names, str(sorted(all_names)))
    tool = registry.get("agent_manage")
    check("AM-02", "registry.get 拿到 AgentManageTool", isinstance(tool, AgentManageTool), type(tool).__name__)

    desc_side = (tool.name or "") + (tool.description or "")
    params_blob = str(tool.parameters)
    ui_side = (tool.label or "") + (tool.description_zh or "")
    # name/description/parameters 为英文（无 CJK）；label/description_zh 为中文（有 CJK）
    check("AM-03", "description/parameters 无中文（模型侧英文）", not _has_cjk(tool.description) and not _has_cjk(params_blob), _has_cjk(tool.description) or _has_cjk(params_blob))
    check("AM-04", "label/description_zh 为中文（界面侧）", _has_cjk(tool.label) and _has_cjk(tool.description_zh), f"{tool.label}/{tool.description_zh}")
    check("AM-05", "name 是 snake_case agent_manage", tool.name == "agent_manage", tool.name)

    # ---- 2. 写操作 & 确认语义 ----
    check("AM-06", "write_operation=True", tool.write_operation is True)
    check("AM-07", "create 需确认", tool.needs_confirmation({"action": "create"}) is True)
    check("AM-08", "update 需确认", tool.needs_confirmation({"action": "update"}) is True)
    check("AM-09", "delete 需确认", tool.needs_confirmation({"action": "delete"}) is True)
    check("AM-10", "list 不需确认", tool.needs_confirmation({"action": "list"}) is False)
    check("AM-11", "delete 是破坏性的", tool.is_destructive({"action": "delete"}) is True)
    check("AM-12", "create 非破坏性", tool.is_destructive({"action": "create"}) is False)

    # ---- 3. 参数 schema ----
    props = (tool.parameters or {}).get("properties", {})
    req = (tool.parameters or {}).get("required", [])
    action_enum = set((props.get("action") or {}).get("enum", []))
    check("AM-13", "action 枚举含 create/update/delete/list", action_enum == {"create", "update", "delete", "list"}, str(action_enum))
    check("AM-14", "required=[action]", list(req) == ["action"], str(req))

    # ---- 4. 角色 ----
    role = roles_mod.OFFICIAL_ROLES.get("agent_builder")
    check("AM-15", "agent_builder 角色存在", role is not None)
    check("AM-16", "agent_builder 白名单恰为 (agent_manage,)", role is not None and tuple(role.tools) == ("agent_manage",), str(role.tools if role else None))
    check("AM-17", "agent_builder 有 capability（可被委派/可开关）", bool(role and role.capability))
    check("AM-18", "agent_builder 出现在 renderable_sub_agents", any(r.key == "agent_builder" for r in roles_mod.renderable_sub_agents()))

    # ---- 5. compute_exclude：专家只能看到 agent_manage + 全局工具 ----
    ex = orchestrator.compute_exclude(role, all_tool_names=all_names, user_disabled=set())
    effective = all_names - ex
    expected = {"agent_manage"} | set(roles_mod.GLOBAL_TOOLS)
    check("AM-19", "agent_builder 生效工具 = {agent_manage} ∪ 全局", effective == expected, f"effective={sorted(effective)}")

    # ---- 6. _clean_tools 校验 ----
    t = AgentManageTool()
    clean, invalid = t._clean_tools(None)
    check("AM-20", "空 tools → None（不限）", clean is None and invalid == [], f"{clean}/{invalid}")
    clean, invalid = t._clean_tools(["bank_manage", "bank_manage", "note_manage"])
    check("AM-21", "合法工具去重保留", clean == ["bank_manage", "note_manage"] and invalid == [], f"{clean}")
    clean, invalid = t._clean_tools(["bank_manage", "web_search"])
    check("AM-22", "非法工具名被识别（web_search）", invalid == ["web_search"] and clean == [], f"invalid={invalid}")

    # ---- 7. 关键词路由 ----
    r = orchestrator.resolve_role(role="", message="帮我创建一个智能体，用来当数学老师")
    check("AM-23", "『创建智能体』→ agent_builder", r.key == "agent_builder", r.key)

    ok = all(x["ok"] for x in ROWS)
    for x in ROWS:
        tail = "" if x["ok"] else f" | 实际: {x['actual']}"
        print(f"  [{'PASS' if x['ok'] else 'FAIL'}] {x['cid']} {x['title']}{tail}")
    print("结论:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run_probe())
