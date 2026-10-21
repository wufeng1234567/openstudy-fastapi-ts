# -*- coding: utf-8 -*-
"""锁死「批量删除走一张勾选卡」全链路（用户 2026-10-17 需求）

## 现象
用户让智能体删 12 个「功能测试」知识库，模型**循环调了 12 次 delete** →
弹出 12 张确认卡（用户得点 12 次；中途点错一张就只删了一半）。

## 设计（本次实现）
1. 知识库补上 `delete_many`（题库/题目/笔记本来就有）；
2. 各工具的 `delete_many` 预览都挂一份 `draft`：
   `{kind:'batch_delete', entity, entityLabel, items:[{key,id,title,subtitle}]}`
3. 前端 `AgentDraftCard` 用 `batch_delete` 模式渲染：逐条勾选 + 全选 + 全不选；
   「取消勾选」= 这条不删（方便反悔）；
4. 用户确认 → `edited.selectedKeys` 随 `/ai/agent/confirm` 回传 →
   `loop._apply_selected_keys` 把 `*_ids` **收窄成勾选的那些**再执行；
5. 一个都不勾 → 按「取消」处理（给模型失败信封 + 中性卡片，而不是假成功「已删除 0 个」）；
6. 结果原样回灌模型：删了哪些 / 哪些没删成 / 是否被用户取消。

用法：.venv\\Scripts\\python.exe tests\\_probe_batch_delete_card.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS = []


def check(cid, name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f"  -- {detail}" if detail else ""))


class _Cfg:
    pass


def main():
    from app.services.ai.agent.tools.knowledge_base_manage import KnowledgeBaseManageTool
    from app.services.ai.agent.tools.bank_manage import BankManageTool
    from app.services.ai.agent.tools.note_manage import NoteManageTool
    from app.services.ai.agent.tools.question_manage import QuestionManageTool
    from app.services.ai.agent import loop

    kb = KnowledgeBaseManageTool()

    # T1：知识库必须有 delete_many（这是 12 次循环 delete 的根因）
    enum = kb.parameters["properties"]["action"]["enum"]
    check("T1", "knowledge_base_manage 提供 delete_many 动作", "delete_many" in enum, f"enum={enum}")

    # T2：批量参数存在
    check(
        "T2",
        "knowledge_base_manage 接受 kb_ids 批量参数",
        "kb_ids" in kb.parameters["properties"],
        f"props={list(kb.parameters['properties'])}",
    )

    # T3：delete_many 是破坏性动作（必须确认）
    check(
        "T3",
        "delete_many 被判定为破坏性（必弹确认）",
        kb.is_destructive({"action": "delete_many"}) is True,
    )

    # T4：delete_many 自动要求确认
    check(
        "T4",
        "delete_many 即使 autoConfirm=True 也要确认",
        loop.needs_user_confirmation(kb, {"action": "delete_many", "kb_ids": [1]}, True) is True,
    )

    # T5：四个工具都走同一套勾选卡
    for cid, tool, field in (
        ("T5", BankManageTool(), "bank_ids"),
        ("T6", NoteManageTool(), "note_ids"),
        ("T7", QuestionManageTool(), "question_ids"),
    ):
        params = tool.parameters["properties"]
        check(
            cid,
            f"{tool.name} 支持 delete_many + {field}",
            "delete_many" in params["action"]["enum"] and field in params,
        )

    # T8：_apply_selected_keys 会把勾选结果收窄成 ID 列表
    new_params = loop._apply_selected_keys(
        kb,
        {"action": "delete_many", "kb_ids": [584, 585, 586, 587]},
        {"selectedKeys": ["kb:585", "kb:587"]},
    )
    check(
        "T8",
        "勾选 2 个（共 4 个）→ kb_ids 收窄成那 2 个",
        isinstance(new_params, dict) and new_params.get("kb_ids") == [585, 587],
        f"got={new_params}",
    )

    # T9：一个都不勾 → 空名单（调用方据此按取消处理）
    empty = loop._apply_selected_keys(
        kb, {"action": "delete_many", "kb_ids": [1, 2]}, {"selectedKeys": []}
    )
    check(
        "T9",
        "全不勾 → 空名单（不是原样全删）",
        isinstance(empty, dict) and empty.get("kb_ids") == [],
        f"got={empty}",
    )

    # T10：非法 key 被忽略（不能因为一个脏 key 把整批搞崩）
    dirty = loop._apply_selected_keys(
        kb, {"action": "delete_many", "kb_ids": [1]}, {"selectedKeys": ["kb:2", "junk", "kb:x"]}
    )
    check(
        "T10",
        "脏 key 被忽略，只保留合法 ID",
        isinstance(dirty, dict) and dirty.get("kb_ids") == [2],
        f"got={dirty}",
    )

    # T11：非批量删除的工具不受影响（不能把 batch_import 的 edited 抢走）
    not_batch = loop._apply_selected_keys(
        kb, {"action": "delete", "kb_id": 584}, {"selectedKeys": ["kb:584"]}
    )
    check(
        "T11",
        "_apply_selected_keys 只处理 delete_many（delete/batch_import 不受影响）",
        loop._is_batch_delete_draft(kb, {"action": "delete", "kb_id": 584}) is False,
        f"delete_many={loop._is_batch_delete_draft(kb, {'action': 'delete_many'})}",
    )

    # T12：_batch_delete_ids 能读回名单（用于「一个都没勾」判断）
    check(
        "T12",
        "_batch_delete_ids 读回勾选后的名单",
        loop._batch_delete_ids(kb, {"action": "delete_many", "kb_ids": [5, 6]}) == [5, 6],
    )

    # T13：前端 AgentDraftCard 支持 batch_delete（勾选 UI + 全选 + 回传 selectedKeys）
    fe = os.path.join(
        os.path.dirname(ROOT),
        "openstudy-vue3-ts", "src", "components", "AgentDraftCard", "index.vue",
    )
    try:
        with open(fe, encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError:
        src = ""
    fe_ok = all(
        token in src
        for token in ("isBatchDelete", "selectedKeys", "toggleAll", "entityLabel", "onBatchConfirm")
    )
    check("T13", "AgentDraftCard 实现 batch_delete（勾选/全选/回传）", fe_ok)

    # T14：AgentConfirmCard 会把 batch_delete 也交给 AgentDraftCard
    cc = os.path.join(
        os.path.dirname(ROOT),
        "openstudy-vue3-ts", "src", "components", "AgentConfirmCard", "index.vue",
    )
    try:
        with open(cc, encoding="utf-8", errors="replace") as f:
            csrc = f.read()
    except OSError:
        csrc = ""
    check(
        "T14",
        "AgentConfirmCard 识别 batch_delete 草稿",
        "batch_delete" in csrc and "DRAFT_KINDS" in csrc,
    )

    # T15：提示词禁止循环 delete
    from app.services.ai import prompts

    rules = prompts.AGENT_CONFIRM_RULES
    check(
        "T15",
        "系统提示词明确禁止循环 delete、要求一次 delete_many",
        "BATCH DELETIONS" in rules and "NEVER call `delete` repeatedly" in rules,
    )

    # T16：提示词要求回报「哪些没删掉 / 是否被取消」
    check(
        "T16",
        "提示词要求回报未删除项与取消状态",
        "were NOT deleted" in rules and "cancelled" in rules,
    )

    print()
    ok = sum(1 for r in RESULTS if r)
    print(f"{ok}/{len(RESULTS)} 通过")
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
