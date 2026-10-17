# -*- coding: utf-8 -*-
"""探针：校验每个官方专家「实际可用工具」是否符合预期。

背景（2026-10-17）：用户让「学习统计专家」分析错题，它却回「我没有错题本相关权限」。
根因是 `roles.py` 里 stats 角色的工具白名单只写了 learning_stats + bank_share_manage，
而**具体错题清单**在 question_flag_manage 里 —— 白名单缺项，专家手里没有该工具。

本探针把这个约束固化下来，防止以后再漏：
  · stats 必须能用 question_flag_manage（读错题 / 收藏 / 斩题清单）；
  · stats 必须仍能用 learning_stats（汇总数字）；
  · 白名单里的每个工具名都必须真实存在于 registry（写错名字不会报错，只会静默失效）。

用法：.venv/Scripts/python.exe tests/_check_role_tools.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须显式 import tools 包，registry 才会被填充
import app.services.ai.agent.tools  # noqa: F401,E402
from app.services.ai.agent.roles import GLOBAL_TOOLS, OFFICIAL_ROLES  # noqa: E402
from app.services.ai.agent.registry import registry  # noqa: E402


def main() -> int:
    allnames = set(registry.names())
    if not allnames:
        print("FAIL: registry 为空，工具没被加载")
        return 1

    failures = []

    # 1) 每个角色白名单里的名字都必须真实存在（拼错会静默失效，这里必须挡住）
    for key, spec in OFFICIAL_ROLES.items():
        for name in spec.tools:
            if name not in allnames:
                failures.append(f"{key}: 白名单里的工具 `{name}` 在 registry 中不存在")
    for name in GLOBAL_TOOLS:
        if name not in allnames:
            failures.append(f"GLOBAL_TOOLS: 工具 `{name}` 在 registry 中不存在")

    # 2) stats 必须能读「具体错题清单」
    stats_tools = set(OFFICIAL_ROLES["stats"].tools) | set(GLOBAL_TOOLS)
    if "question_flag_manage" not in stats_tools:
        failures.append(
            "stats: 缺少 question_flag_manage —— 学习统计专家将无法列出具体错题"
        )
    if "learning_stats" not in stats_tools:
        failures.append("stats: 缺少 learning_stats —— 无法给汇总数字")
    if "question_manage" in stats_tools:
        failures.append("stats: 不该有 question_manage（统计专家不应改题）")

    # 3) 输出每个角色的实际可用工具，便于人工核对
    print(f"registry 工具数: {len(allnames)}")
    for key, spec in OFFICIAL_ROLES.items():
        allowed = sorted((set(spec.tools) | set(GLOBAL_TOOLS)) & allnames)
        print(f"  {key:8s} -> {allowed}")

    if failures:
        print("\n失败项:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
