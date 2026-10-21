# -*- coding: utf-8 -*-
"""服务端强制合并 delete → delete_many（修「12 次单独删除卡」）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS = []


def check(cid, name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f"  -- {detail}" if detail else ""))


def call(name, id_, cid):
    return {"name": name, "args": {"action": "delete", "kb_id": id_}, "id": cid}


def main():
    from app.services.ai.agent import loop

    # T1：12 次 delete → 1 次 delete_many（核心）
    calls = [call("knowledge_base_manage", i, f"c{i}") for i in range(584, 596)]
    merged, note = loop.coalesce_delete_tool_calls(calls)
    check(
        "T1",
        "12 次 delete 合并成 1 次 delete_many",
        len(merged) == 1
        and merged[0]["args"]["action"] == "delete_many"
        and len(merged[0]["args"]["kb_ids"]) == 12,
        f"len={len(merged)} args={merged[0]['args'] if merged else None}",
    )
    check(
        "T2",
        "合并信息报告了正确的数量与 ID 列表",
        note and note["count"] == 12 and note["ids"] == list(range(584, 596)),
        f"note={note}",
    )

    # T3：单个 delete 不合并（保持原体验）
    one = [call("knowledge_base_manage", 584, "c1")]
    m1, n1 = loop.coalesce_delete_tool_calls(one)
    check(
        "T3",
        "只有 1 个 delete 时保持原样（不合并）",
        len(m1) == 1 and m1[0]["args"]["action"] == "delete" and n1 is None,
        f"args={m1[0]['args']}",
    )

    # T4：不同工具互不干扰（题库 delete 不受知识库影响）
    mixed = [
        call("knowledge_base_manage", 1, "a"),
        call("knowledge_base_manage", 2, "b"),
        {"name": "bank_manage", "args": {"action": "delete", "bank_id": 9}, "id": "c"},
    ]
    m4, n4 = loop.coalesce_delete_tool_calls(mixed)
    kinds = sorted(str(c["args"].get("action")) for c in m4)
    check(
        "T4",
        "只合并同一个工具的删除（其他工具原样保留）",
        kinds == ["delete", "delete_many"] and len(m4) == 2,
        f"actions={kinds}",
    )

    # T5：题库走 bank_ids
    bank = [
        {"name": "bank_manage", "args": {"action": "delete", "bank_id": i}, "id": f"b{i}"}
        for i in (11, 12, 13)
    ]
    m5, n5 = loop.coalesce_delete_tool_calls(bank)
    check(
        "T5",
        "题库 delete → delete_many + bank_ids",
        len(m5) == 1 and m5[0]["args"]["bank_ids"] == [11, 12, 13],
        f"args={m5[0]['args'] if m5 else None}",
    )

    # T6：笔记 / 题目也能合并
    for tool, field, cid in (
        ("note_manage", "note_ids", "T6"),
        ("question_manage", "question_ids", "T7"),
    ):
        one_field = field[:-1]  # note_ids → note_id
        calls = [
            {"name": tool, "args": {"action": "delete", one_field: i}, "id": f"{tool}{i}"}
            for i in (1, 2, 3)
        ]
        mm, _ = loop.coalesce_delete_tool_calls(calls)
        check(
            cid,
            f"{tool} 的多次 delete 合并到 {field}",
            len(mm) == 1 and mm[0]["args"].get(field) == [1, 2, 3],
            f"args={mm[0]['args'] if mm else None}",
        )

    # T8：非 delete 动作不受影响（batch_import / create 不能被吞）
    other = [
        {"name": "question_manage", "args": {"action": "create", "question_id": 1}, "id": "x"},
        {"name": "question_manage", "args": {"action": "create", "question_id": 2}, "id": "y"},
    ]
    m8, n8 = loop.coalesce_delete_tool_calls(other)
    check(
        "T8",
        "非 delete 动作完全不受影响",
        len(m8) == 2 and n8 is None,
        f"len={len(m8)}",
    )

    # T9：合并后保留调用 id（tool_call_id 必须一一对应，否则上游报错）
    c9, _ = loop.coalesce_delete_tool_calls([call("knowledge_base_manage", i, f"k{i}") for i in (1, 2)])
    check(
        "T9",
        "合并保留了第一个调用的 id（tool_call_id 对得上）",
        c9[0].get("id") == "k1",
        f"id={c9[0].get('id')}",
    )

    # T10：delete_many 本身不会被再次合并（幂等）
    already = [
        {"name": "knowledge_base_manage", "args": {"action": "delete_many", "kb_ids": [1, 2]}, "id": "z"}
    ]
    m10, n10 = loop.coalesce_delete_tool_calls(already)
    check(
        "T10",
        "已经是 delete_many 的调用不再处理（幂等）",
        len(m10) == 1 and n10 is None and m10[0]["args"]["kb_ids"] == [1, 2],
    )

    print()
    ok = sum(1 for r in RESULTS if r)
    print(f"{ok}/{len(RESULTS)} 通过")
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
