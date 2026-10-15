# -*- coding: utf-8 -*-
"""同步校验：子代理「谎称没工具 / 吐协议文本」的识别正则（无需 asyncio）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.ai.agent.sub_agent import (  # noqa: E402
    _looks_like_no_tool_refusal,
    _looks_like_tool_protocol,
    _SUB_AGENT_BASE_RULES,
    _NO_TOOL_REFUSAL_PATTERNS,
)

CASES_YES = [
    "my knowledge_create_kb function is not available in this environment, so no knowledge base was actually created.",
    "I'm unable to execute the tool call — my function is not available here.",
    "我只有代码执行（python）工具，没有暴露任何知识库管理或 knowledge_search 相关的接口。",
    "当前可用的工具中不包含知识库创建功能，我只有代码执行（python）工具。",
    "因此无法创建名为「cpp」的知识库，也无法返回 kbId。",
    "There is no tool available to perform this action.",
    "环境不支持该操作。",
]
CASES_NO = [
    "已为你创建好知识库 cpp，共 3 篇文档。",
    "Created knowledge base 'cpp' (kbId=42). Added 3 documents.",
    "工具执行失败：kb_id 不存在，请先 list 确认。",  # 跑过工具后的复述，不该判 red
    "Done. The question bank 'cpp' now has 12 questions.",
]

rows = []
for t in CASES_YES:
    rows.append(("YES ", _looks_like_no_tool_refusal(t), t))
for t in CASES_NO:
    rows.append(("NO  ", _looks_like_no_tool_refusal(t), t))

print("---- _looks_like_no_tool_refusal ----")
red = 0
for exp, got, t in rows:
    ok = (exp.strip() == "YES") == bool(got)
    if not ok:
        red += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] 期望{exp.strip():3} 实际{'YES' if got else 'NO ':3} | {t[:70]}")

# 协议文本（回归，确保没被破坏）
proto = [
    (_looks_like_tool_protocol('调用: <|DSML|> invoke name="create_knowledge_base"'), True, "DSML"),
    (_looks_like_tool_protocol('{"tool": "bank_manage", "action": "list"}'), True, "裸JSON"),
    (_looks_like_tool_protocol("已为你创建好知识库 cpp。"), False, "正常"),
]
print("---- _looks_like_tool_protocol 回归 ----")
for got, exp, name in proto:
    ok = bool(got) == exp
    if not ok:
        red += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}: got={got} exp={exp}")

print(f"\n共 {len(rows)+len(proto)} 项；红的={red}")
sys.exit(1 if red else 0)
