"""回退能力矩阵（权威版）—— 逐项核实「哪些操作可撤、怎么撤、不可撤怎么告知」

用法：
    cd apps/fastapi-v2/openstudy-fastapi
    PYTHONPATH=. ./.venv/Scripts/python.exe <本文件>

与上一版（`undo_matrix2.py`）的差别：**必须带上每个工具真正需要的参数**。
上一版对 `question_flag_manage` 只传了 `action`、没传 `flag_type`，
于是它内部 `_flag_type()` 返回错误 → `undo_plan` 返回 None →
矩阵把它误判成「没实现」。这个矩阵把每个工具的**最小必要参数**显式写出来，
并且对多分支工具（按 flag_type / 按 action）逐个分支跑一遍。

结果三分类：
    OK    —— 有明确的逆操作（op 非空）
    PART  —— 能撤一部分，但带 reason（界面标「部分回退」）
    NO    —— 不可撤，但**必须**有可读的中文原因（reasonText）
    BAD   —— 不可撤且只有机器码（不合格）
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.services.ai.agent import rollback_service as rs
from app.services.ai.agent.registry import ensure_tools_loaded

r = ensure_tools_loaded()

#: 整树快照（bank/question 的删除回退靠它）
SNAP = {
    "kind": "bank_tree", "rowCount": 5, "bankIds": [11], "questionIds": [11],
    "banks": [], "questions": [], "subs": [], "questionFavorites": [],
    "questionErrors": [], "questionMarkeds": [], "bankFavorites": [], "noteQuestions": [],
}

#: 每个工具的「一次典型调用」= (参数, 回执, before)，逐分支列出。
#:
#: ⚠️ 回执形状必须照着各工具 `return ok(...)` 的真实字段抄 —— 这正是上一版
#:    矩阵出错的地方（假回执导致 undo_plan 找不到 id，误报成「没实现」）。
CASES = [
    # ---- 题库 ----
    ("bank_manage", "create", {"bank_name": "x"}, {"bank": {"bankId": 11}, "success": True}, None),
    ("bank_manage", "update", {"bank_id": 11, "bank_name": "y"},
     {"bank": {"bankId": 11}, "changed": ["bankName"], "success": True}, None),
    ("bank_manage", "delete", {"bank_id": 11},
     {"deleted": [{"id": 11, "bankName": "x"}], "success": True}, SNAP),
    ("bank_manage", "delete_by_name", {"bank_name": "x"},
     {"deleted": [{"id": 11, "bankName": "x"}], "success": True}, SNAP),
    ("bank_manage", "delete_many", {"bank_ids": [11]},
     {"deleted": [{"id": 11, "bankName": "x"}], "success": True}, SNAP),

    # ---- 题目 ----
    ("question_manage", "create", {"bank_id": 11, "question_text": "q"},
     {"questionId": 11, "success": True}, None),
    ("question_manage", "batch_import", {"bank_id": 11, "questions": "[]"},
     {"bankId": 11, "imported": 3, "success": True}, None),
    ("question_manage", "update", {"bank_id": 11, "question_index": 1},
     {"questionId": 11, "changed": ["questionText"], "success": True}, None),
    ("question_manage", "delete", {"bank_id": 11, "question_index": 1},
     {"questionId": 11, "success": True}, SNAP),
    ("question_manage", "delete_many", {"bank_id": 11, "question_indexes": [1]},
     {"bankId": 11, "deleted": 1, "success": True}, SNAP),
    ("question_manage", "clear_questions", {"bank_id": 11},
     {"bankId": 11, "deleted": 3, "success": True}, SNAP),

    # ---- 笔记 ----
    ("note_manage", "create", {"title": "t"}, {"note": {"noteId": 11}, "success": True}, None),
    ("note_manage", "update", {"note_id": 11, "title": "t2"},
     {"note": {"noteId": 11}, "success": True}, {"title": "t"}),
    ("note_manage", "delete", {"note_id": 11}, {"deleted": [{"noteId": 11}], "success": True}, None),
    ("note_manage", "delete_many", {"note_ids": [11]},
     {"deleted": [{"noteId": 11}], "success": True}, None),
    ("note_manage", "create_category", {"name": "c"}, {"category": {"categoryId": 11}, "success": True}, None),
    ("note_manage", "save_draft", {"title": "t", "content": "c"}, {"success": True}, None),

    # ---- 记忆 ----
    ("memory_manage", "forget", {"memory_id": 11}, {"memoryId": 11, "success": True}, None),
    ("memory_manage", "clear", {}, {"memoryIds": [11], "success": True}, {"memoryIds": [11]}),

    # ---- 题目标记（三种 flag_type × 三个动作）----
    #
    # ⚠️ `add` 的 id 键**按 flag_type 各自命名**（`_ID_KEY` = errorId/favoriteId/markedId），
    #    不是统一的 `recordId` —— 回执里必须给对应的那个键，否则 undo_plan 判「定位不到行」
    #    （本矩阵第一版就是这么误报的：给了 recordId，于是三项 add 全被算成不可回退）。
    ("question_flag_manage", "add", {"flag_type": "error", "question_id": 11},
     {"created": True, "recordId": 11, "errorId": 11, "success": True}, None),
    ("question_flag_manage", "add", {"flag_type": "favorite", "question_id": 11},
     {"created": True, "recordId": 11, "favoriteId": 11, "success": True}, None),
    ("question_flag_manage", "add", {"flag_type": "marked", "question_id": 11},
     {"created": True, "recordId": 11, "markedId": 11, "success": True}, None),
    ("question_flag_manage", "master", {"flag_type": "error", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0, "status": 1}),
    ("question_flag_manage", "master", {"flag_type": "favorite", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0}),
    ("question_flag_manage", "master", {"flag_type": "marked", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0}),
    ("question_flag_manage", "remove", {"flag_type": "error", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0}),
    ("question_flag_manage", "remove", {"flag_type": "favorite", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0}),
    ("question_flag_manage", "remove", {"flag_type": "marked", "record_id": 11},
     {"recordId": 11, "success": True}, {"is_mastered": 0}),

    # ---- 知识库 ----
    ("knowledge_base_manage", "create", {"name": "kb"},
     {"kbId": 11, "success": True}, None),
    ("knowledge_base_manage", "update", {"kb_id": 11, "name": "kb2"},
     {"kbId": 11, "success": True}, {"name": "kb"}),
    ("knowledge_base_manage", "delete", {"kb_id": 11},
     {"kbId": 11, "success": True}, {"name": "kb", "del_flag": "0"}),
    ("knowledge_base_manage", "delete_many", {"kb_ids": [11]},
     {"deleted": 1, "success": True}, None),
    ("knowledge_base_manage", "delete_document", {"kb_id": 11, "doc_id": 11},
     {"docId": 11, "success": True}, None),

    # ---- 知识入库 ----
    ("knowledge_ingest", "from_text", {"kb_id": 11, "text": "t"},
     {"docId": 11, "kbId": 11, "success": True}, None),
    ("knowledge_ingest", "from_attachment", {"kb_id": 11},
     {"docId": 11, "kbId": 11, "success": True}, None),

    # ---- 分享 ----
    ("bank_share_manage", "share", {"bank_id": 11}, {"shareId": 11, "success": True}, None),
    ("bank_share_manage", "revoke", {"share_id": 11}, {"shareId": 11, "success": True}, None),
    ("bank_share_manage", "receive", {"code": "abc123"},
     {"receiveId": 11, "success": True}, None),
    ("bank_share_manage", "copy", {"bank_id": 11},
     {"bank": {"bankId": 12}, "sourceBankId": 11, "success": True}, None),

    # ---- 智能体 ----
    ("agent_manage", "create", {"name": "a"}, {"agent": {"agentId": 11}, "success": True}, None),
    ("agent_manage", "update", {"agent_id": 11, "name": "b"}, {"agentId": 11, "success": True}, None),
    ("agent_manage", "delete", {"agent_id": 11}, {"agentId": 11, "success": True}, None),

    # ---- 学情 ----
    ("learning_stats", "plan_review", {"action": "plan_review"},
     {"updated": 3, "success": True}, None),

    # ---- 导出（产文件，本就不该撤）----
    ("bank_export", "export", {"bank_id": 11},
     {"fileName": "x.docx", "downloadUrl": "/p/x.docx", "success": True}, None),
]


def classify(tool_name, action, params, result, before):
    tool = r.get(tool_name)
    if tool is None:
        return "BAD", "-", "工具不在注册表里"
    # ⚠️ 参数里**必须**带 `action`：`needs_confirmation` 就是靠它判「这是不是一个
    #    需要确认的写操作」，而 `record_op` 的记账门槛又问它一遍。
    #    第一版矩阵漏了这个键 → 全部被判「不需要确认」→ 43 项 SKIP、一个都没测到。
    call_params = dict(params)
    call_params.setdefault("action", action)
    if not tool.needs_confirmation(call_params):
        return "SKIP", "-", "不需要确认（不记账）"
    try:
        plan = tool.undo_plan(call_params, result, before)
    except Exception as e:  # noqa: BLE001
        return "BAD", "-", f"undo_plan 抛异常：{type(e).__name__}: {e}"

    if plan is None:
        reason = rs._reason_for(tool_name, action, None)
        text = rs.REASON_TEXT.get(reason, "")
        return ("NO" if text else "BAD"), "-", text or f"只有机器码 {reason}"

    op = plan.get("op") or ""
    reason = plan.get("reason") or ""
    if plan.get("undoable") is False or not op:
        if reason and reason in rs.REASON_TEXT:
            return "NO", "-", rs.REASON_TEXT[reason]
        if reason and len(reason) > 4 and not reason.replace("_", "").isalnum():
            return "NO", "-", reason          # 工具直接写的中文说明
        text = rs.REASON_TEXT.get(reason or "", "")
        return ("NO" if text else "BAD"), "-", text or str(reason or "无原因")
    if reason:
        return "PART", op, rs.REASON_TEXT.get(reason, reason)
    return "OK", op, ""


def main():
    rows = []
    for name, action, params, result, before in CASES:
        kind, op, note = classify(name, action, params, result, before)
        rows.append((name, action, kind, op, note))

    pad = max(len(f"{n}.{a}") for n, a, _k, _o, _n in rows) + 2
    print(f"{'操作'.ljust(pad)} {'结果':5s} {'逆操作':13s} 说明")
    print("-" * 108)
    order = {"BAD": 0, "NO": 1, "PART": 2, "OK": 3, "SKIP": 4}
    for name, action, kind, op, note in sorted(rows, key=lambda x: (order[x[2]], x[0])):
        label = f"{name}.{action}".ljust(pad)
        icon = {"OK": "✅", "PART": "◐", "NO": "⛔", "SKIP": "·", "BAD": "❌"}[kind]
        print(f"{label} {icon:5s} {op:13s} {note}")

    print()
    tally = {}
    for *_x, kind, _o, _n in [(r[0], r[1], r[2], r[3], r[4]) for r in rows]:
        tally[kind] = tally.get(kind, 0) + 1
    print(f"合计 {len(rows)} 项：", end="")
    print("  ".join(f"{k}={tally.get(k,0)}" for k in ("OK", "PART", "NO", "SKIP", "BAD")))
    if tally.get("BAD"):
        print("\n❌ 有 BAD 项 —— 不可回退却没有给用户可读的原因，必须修。")
        return 1
    print("\n✅ 全部合规：能撤的都声明了逆操作；不能撤的都说清了为什么。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
