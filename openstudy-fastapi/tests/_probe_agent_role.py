# -*- coding: utf-8 -*-
"""多智能体协同（阶段 1：官方角色切分）探针 —— 零 DB、零网络、零 LLM 成本

⚠️ 这是**刻意保留**的验证脚本。理由：角色切分的核心价值是「按角色收窄工具集 → 省 token
+ 降误选」，而这件事只有靠断言才能防止「某次改动静默让某工具从所有角色里消失」或
「路由漂移把用户导到错误角色」。全程**只做纯计算 + 注册表读取**，不连数据库、不发请求。

覆盖：
  1. 角色表自洽：每个角色引用的工具名都存在于注册表（防止白名单写了不存在的名字）
  2. 路由 `resolve_role`：显式指定 / 关键词命中 / 兜底 general / 平局按声明顺序稳定
  3. `compute_exclude`：白名单→黑名单换算正确、与用户屏蔽求并、general 不限工具
  4. 集成：不同角色的工具集确实收窄（definitions/describe 工具数下降）
  5. 语义红线：最终可用 = 角色白名单 ∩ (全部 − 用户屏蔽)

用法
----
    .venv/Scripts/python.exe tests/_probe_agent_role.py     # 全绿退出码 0
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


def run_probe() -> int:
    from app.services.ai.agent.registry import ensure_tools_loaded, registry
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent import orchestrator

    ensure_tools_loaded()
    all_names = set(registry.names())

    # ---- 1. 角色表自洽 ----
    ok_self = True
    bad_detail = []
    for r in roles_mod.OFFICIAL_ROLES.values():
        unknown = set(r.tools) - all_names
        if unknown:
            ok_self = False
            bad_detail.append(f"{r.key}:{sorted(unknown)}")
    check("AR-01", "每个角色引用的工具名都存在", ok_self, "; ".join(bad_detail) or "全部合法")

    check(
        "AR-02",
        "general 存在且不限工具（tools 为空）",
        roles_mod.GENERAL_ROLE in roles_mod.OFFICIAL_ROLES
        and roles_mod.OFFICIAL_ROLES[roles_mod.GENERAL_ROLE].tools == (),
        str(roles_mod.OFFICIAL_ROLES.get(roles_mod.GENERAL_ROLE)),
    )

    # 每个工具至少被一个非 general 角色引用（否则只剩 general 可用，容易让用户以为坏了）
    covered = set()
    for r in roles_mod.OFFICIAL_ROLES.values():
        if r.key != roles_mod.GENERAL_ROLE:
            covered |= set(r.tools)
    uncovered = all_names - covered
    check(
        "AR-03",
        "每个工具至少被一个非 general 角色覆盖",
        not uncovered,
        f"未覆盖={sorted(uncovered)}" if uncovered else "全覆盖",
    )

    # ---- 2. 路由 ----
    r = orchestrator.resolve_role(role="bank", message="随便说点什么")
    check("AR-04", "显式 role=bank → 直接命中", r.key == "bank", r.key)

    r = orchestrator.resolve_role(role="", message="帮我建个题库，导入这几道题")
    check("AR-05", "关键词『题库/导入』→ bank", r.key == "bank", r.key)

    r = orchestrator.resolve_role(role="", message="帮我记一下我偏好早上学习")
    check("AR-06", "关键词『记』→ memory", r.key == "memory", r.key)

    r = orchestrator.resolve_role(role="", message="我错了多少题，正确率多少")
    check("AR-07", "关键词『统计/正确率』→ stats", r.key == "stats", r.key)

    r = orchestrator.resolve_role(role="", message="今天天气怎么样")
    check("AR-08", "无命中 → 兜底 general", r.key == "general", r.key)

    r = orchestrator.resolve_role(role="不存在的角色", message="")
    check("AR-09", "非法 role → 忽略并兜底 general", r.key == "general", r.key)

    r = orchestrator.resolve_role(role="", message="")
    check("AR-10", "空消息 → general", r.key == "general", r.key)

    # 平局稳定：bank 与 note 都可能命中「题库 … 笔记」？构造一个双命中，验证不崩且确定
    r1 = orchestrator.resolve_role(role="", message="题库 笔记")
    r2 = orchestrator.resolve_role(role="", message="题库 笔记")
    check("AR-11", "平局路由稳定（两次一致）", r1.key == r2.key, f"{r1.key}/{r2.key}")

    # ---- 3. compute_exclude ----
    bank = roles_mod.OFFICIAL_ROLES["bank"]
    ex = orchestrator.compute_exclude(bank, all_tool_names=all_names, user_disabled=set())
    check(
        "AR-12",
        "bank 角色 exclude = 全部 − bank 白名单",
        ex == all_names - set(bank.tools),
        f"exclude={sorted(ex)}",
    )
    # 白名单 ∩ (全部 − exclude) == 白名单
    effective = all_names - ex
    check(
        "AR-13",
        "bank 生效工具 == 白名单",
        effective == set(bank.tools),
        f"effective={sorted(effective)}",
    )

    # 与用户屏蔽求并
    ex2 = orchestrator.compute_exclude(
        bank, all_tool_names=all_names, user_disabled={"bank_manage"}
    )
    eff2 = all_names - ex2
    check(
        "AR-14",
        "用户屏蔽 bank_manage → 生效工具再少一个（求交语义）",
        "bank_manage" not in eff2 and eff2 == set(bank.tools) - {"bank_manage"},
        f"effective={sorted(eff2)}",
    )

    # general 不限工具：只有用户屏蔽生效
    general = roles_mod.OFFICIAL_ROLES[roles_mod.GENERAL_ROLE]
    ex3 = orchestrator.compute_exclude(general, all_tool_names=all_names, user_disabled=set())
    check("AR-15", "general 无用户屏蔽 → exclude 空", ex3 == set(), f"exclude={sorted(ex3)}")

    ex4 = orchestrator.compute_exclude(
        general, all_tool_names=all_names, user_disabled={"note_manage"}
    )
    check(
        "AR-16",
        "general + 用户屏蔽 note_manage → 仅排除它",
        ex4 == {"note_manage"},
        f"exclude={sorted(ex4)}",
    )

    # 历史遗留的、已下线的工具名不该污染 exclude
    ex5 = orchestrator.compute_exclude(
        general, all_tool_names=all_names, user_disabled={"ghost_tool_xyz"}
    )
    check("AR-17", "用户屏蔽里的幽灵工具名被收敛掉", ex5 == set(), f"exclude={sorted(ex5)}")

    # ---- 4. 集成：收窄确实生效（工具数下降）----
    full_defs = registry.definitions(exclude=[])
    bank_defs = registry.definitions(exclude=sorted(ex))
    check(
        "AR-18",
        "bank 角色的 Function Calling 工具数 < 全量",
        len(bank_defs) < len(full_defs),
        f"bank={len(bank_defs)} / full={len(full_defs)}",
    )
    bank_desc = registry.describe(exclude=sorted(ex))
    full_desc = registry.describe(exclude=[])
    check(
        "AR-19",
        "bank 角色的工具清单文本比全量短",
        len(bank_desc) < len(full_desc),
        f"bank={len(bank_desc)} / full={len(full_desc)}",
    )

    # ---- 5. 语义红线（用集合运算再证一遍）----
    role_tools = set(bank.tools)
    user_disabled = {"question_manage"}
    exr = orchestrator.compute_exclude(
        bank, all_tool_names=all_names, user_disabled=user_disabled
    )
    lhs = all_names - exr
    rhs = role_tools & (all_names - user_disabled)
    check("AR-20", "红线：可用 = 白名单 ∩ (全部 − 用户屏蔽)", lhs == rhs, f"{sorted(lhs)} vs {sorted(rhs)}")

    print("\n---- 官方角色切分（阶段 1）探针结果 ----")
    for rec in ROWS:
        tail = "" if rec["status"] == "通过" else f" | 实际: {rec['actual']}"
        print(f"  [{rec['status']}] {rec['cid']} {rec['title']}{tail}")
    red = [rec for rec in ROWS if rec["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")

    # token 收益的直观数字（不参与断言，仅展示）
    print(
        f"\n[收益] 全量工具 {len(full_defs)} 个；"
        f"bank 角色 {len(bank_defs)} 个；"
        f"describe 文本 {len(full_desc)} → {len(bank_desc)} 字符"
    )
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(run_probe())
