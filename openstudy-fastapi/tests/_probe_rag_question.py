# -*- coding: utf-8 -*-
"""RAG × 出题 关联（A1/A2）探针 —— 零 DB、零网络、零 LLM 成本

验证「知识库取材」链路的关键判定点：
  1. `ChatTurn` 有了 `kb_ids` 字段（默认空 = 不检索，跟随原行为）
  2. 出题类场景的模板在拿到 `source_context` 时会把它拼进 user 消息，并要求注明出处
  3. 未传 `source_context` 时，模板输出与改造前**逐字一致**（不回归）
  4. 题库专家（bank）的白名单已含 `knowledge_search`（只读检索打通），且不越界到建库
  5. `knowledge_search` 仍是只读工具（不会被误标成写操作）

用法：
    .venv/Scripts/python.exe tests/_probe_rag_question.py     # 全绿退出码 0
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


def run_probe() -> int:
    from app.services.ai import prompts
    from app.services.ai.chat_engine import ChatTurn
    from app.services.ai.agent import roles as roles_mod
    from app.services.ai.agent.registry import ensure_tools_loaded, registry

    # ---- 1. ChatTurn.kb_ids ----
    t = ChatTurn()
    check("RQ-01", "ChatTurn 默认 kb_ids 为空（不检索 = 原行为）", t.kb_ids is None or t.kb_ids == [], str(t.kb_ids))

    t2 = ChatTurn(scene="question-generate", kb_ids=[3, 4])
    check("RQ-02", "ChatTurn 能带上 kb_ids", t2.kb_ids == [3, 4], str(t2.kb_ids))

    # ---- 2. 出题模板：无 source_context 时与改造前一致（不回归）----
    msgs_plain = prompts.build_scene_messages(
        prompts.SCENE_QUESTION_GENERATE,
        prompt="二叉树",
        count=5,
        knowledge_point="二叉树",
        question_type="single",
    )
    user_plain = msgs_plain[-1]["content"]
    check("RQ-03", "无材料时不含『原文材料』段", "必须依据的原文材料" not in user_plain, user_plain[:60])
    check(
        "RQ-04",
        "无材料时仍保留原有出题指令",
        "请生成 5 道关于" in user_plain and "只返回 JSON" in user_plain,
        user_plain[:80],
    )

    # ---- 3. 出题模板：有 source_context 时注入材料 + 要求注明出处 ----
    msgs_kb = prompts.build_scene_messages(
        prompts.SCENE_QUESTION_GENERATE,
        prompt="二叉树",
        count=5,
        knowledge_point="二叉树",
        question_type="single",
        source_context="【材料1｜来源：数据结构.pdf 第 3 段】\n二叉树每个结点至多两棵子树…",
    )
    user_kb = msgs_kb[-1]["content"]
    check("RQ-05", "有材料时注入『必须依据的原文材料』段", "必须依据的原文材料" in user_kb, user_kb[:80])
    check("RQ-06", "有材料时要求注明出处（来源：…）", "来源：" in user_kb and "第N段" in user_kb, user_kb[-160:])
    check("RQ-07", "材料正文被原样带进 messages", "二叉树每个结点至多两棵子树" in user_kb, "")
    check("RQ-08", "有材料时仍保留出题指令", "请生成 5 道关于" in user_kb, "")

    # reading / composite 同样支持
    for scene in (prompts.SCENE_READING, prompts.SCENE_COMPOSITE):
        m = prompts.build_scene_messages(
            scene, requirement="随便", question_count=3,
            source_context="【材料1｜来源：x.pdf 第 1 段】\n材料内容…",
        )
        check(f"RQ-09:{scene}", f"{scene} 支持 source_context", "必须依据的原文材料" in m[-1]["content"], "")

    # question-bank（AI 搭建题库）走 _build_plain，也要支持
    m = prompts.build_scene_messages(
        prompts.SCENE_QUESTION_BANK, prompt="把下面题目转 JSON",
        source_context="【材料1｜来源：y.pdf 第 2 段】\n材料…",
    )
    check("RQ-10", "question-bank（_build_plain）支持 source_context", "必须依据的原文材料" in m[-1]["content"], "")
    # 不传材料时 _build_plain 不改变正文（不回归）
    m2 = prompts.build_scene_messages(prompts.SCENE_QUESTION_BANK, prompt="把下面题目转 JSON")
    check("RQ-11", "question-bank 无材料时正文不变", m2[-1]["content"] == "把下面题目转 JSON", m2[-1]["content"])

    # ---- 4. 题库专家接入 knowledge_search ----
    bank = roles_mod.OFFICIAL_ROLES["bank"]
    check("RQ-12", "bank 白名单含 knowledge_search（检索打通）", "knowledge_search" in bank.tools, str(bank.tools))
    check(
        "RQ-13",
        "bank 不含建库类工具（只借只读检索，不越界）",
        "knowledge_base_manage" not in bank.tools and "knowledge_ingest" not in bank.tools,
        str(bank.tools),
    )
    check(
        "RQ-14",
        "bank capability/persona 提到用 knowledge_search 取材",
        "knowledge_search" in bank.capability and "knowledge_search" in bank.persona,
        "",
    )

    # ---- 5. knowledge_search 仍是只读 ----
    ensure_tools_loaded()
    ks = registry.get("knowledge_search")
    check("RQ-15", "knowledge_search 已注册", ks is not None, "")
    check("RQ-16", "knowledge_search 不是写操作（只读）", ks is not None and ks.write_operation is False, "")

    print("\n---- RAG × 出题 关联（A1/A2）探针结果 ----")
    for rec in ROWS:
        tail = "" if rec["status"] == "通过" else f" | 实际: {rec['actual']}"
        print(f"  [{rec['status']}] {rec['cid']} {rec['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(run_probe())
