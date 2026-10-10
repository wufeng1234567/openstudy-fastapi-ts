# -*- coding: utf-8 -*-
"""复现：kb 子代理在真实 loop 环境下 tool_defs 为何为空（零网络，纯同步）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.ai.agent.registry import ensure_tools_loaded, registry
from app.services.ai.agent import roles as roles_mod
from app.services.ai.agent import orchestrator

ensure_tools_loaded()
all_names = set(registry.names())
print("registry 工具数:", len(all_names))
print("工具:", sorted(all_names))
print()

kb = roles_mod.OFFICIAL_ROLES["kb"]
print("kb.tools:", kb.tools)
print()

# 场景 1：disabled_role_keys = 空（用户没关任何专家）
sub_roles = {s.key: s for s in roles_mod.renderable_sub_agents(disabled_keys=set())}
print("场景1 renderable_sub_agents keys:", sorted(sub_roles.keys()))
ex1 = orchestrator.compute_exclude(kb, all_tool_names=all_names, user_disabled=set())
defs1 = registry.definitions(exclude=sorted(ex1))
print("  场景1 kb exclude:", sorted(ex1))
print("  场景1 kb tool_defs:", [d["function"]["name"] for d in defs1])
print()

# 场景 2：用户关掉了 kb 专家
for closed in ({"kb"}, {"kb", "bank"}, {"bank", "note", "kb", "stats"}):
    subs = {s.key: s for s in roles_mod.renderable_sub_agents(disabled_keys=closed)}
    print(f"关闭={sorted(closed)} → renderable keys={sorted(subs.keys())}  kb in subs={'kb' in subs}")
print()

# 场景 3：用户关了全部工具（把 kb 的三个工具都 disable）
for dis in (
    set(),
    {"knowledge_base_manage"},
    {"knowledge_search", "knowledge_ingest", "knowledge_base_manage"},
    all_names,  # ⚠️ 关键：用户在「可用工具」面板里把工具全关了
):
    ex = orchestrator.compute_exclude(kb, all_tool_names=all_names, user_disabled=dis)
    defs = registry.definitions(exclude=sorted(ex))
    print(f"user_disabled={len(dis)}个 → kb tool_defs={[d['function']['name'] for d in defs]}")
