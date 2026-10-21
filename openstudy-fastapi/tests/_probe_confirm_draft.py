# -*- coding: utf-8 -*-
"""确认流程「可编辑草稿」探针 —— 连 DB（probe 专属 uid），零 LLM 成本

验证需求二的后端两条主链（不启服务、直接调模块函数）：
  A. `question_manage.batch_import` 的 preview 里带**完整可编辑草稿**
     （kind / 题库信息 / **全部**题目，不只前 5 条；子题结构原样保留；
      与导入共用同一个解析器 + 同一个 MAX_BATCH_SIZE 上限）。
  B. 确认时回传的 `edited`：
     · `resolve_confirmation(id, True, edited=...)` 能把改动存住并读回；
     · `loop._apply_edited_params` 把改动覆盖到工具参数（questions → JSON 字符串；bank → 改库）；
     · 结构坏掉时**退回原参数**（绝不丢导入）。
  C. 取消导入时清理「本轮新建的空题库」（`_rollback_empty_created_bank`）。

用法
----
    .venv/Scripts/python.exe tests/_probe_confirm_draft.py     # 全绿退出码 0
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_UID = 2_000_900_311

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def _cleanup():
    from sqlalchemy import delete, select

    from app.database import async_session_factory, engine
    from app.models.question import QuestionBank, QuestionMain

    try:
        async with async_session_factory() as db:
            bank_ids = [
                int(r[0])
                for r in (
                    await db.execute(
                        select(QuestionBank.id).where(QuestionBank.user_id == PROBE_UID)
                    )
                ).all()
            ]
            if bank_ids:
                await db.execute(
                    delete(QuestionMain).where(QuestionMain.bank_id.in_(bank_ids))
                )
                await db.execute(delete(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
            await db.commit()
    finally:
        await engine.dispose()


async def run_probe() -> int:
    from app.database import async_session_factory, register_all_models

    register_all_models()
    await _cleanup()

    from app.services import question_write_service as qws
    from app.services.ai.agent import loop as agent_loop
    from app.services.ai.agent.base import ToolContext
    from app.services.ai.agent.tools.question_manage import (
        MAX_BATCH_SIZE,
        QuestionManageTool,
    )

    tool = QuestionManageTool()

    # 建一个探针题库（user_id 无外键，无需造 sys_user）
    async with async_session_factory() as db:
        bank = await qws.create_bank(
            db,
            user_id=PROBE_UID,
            bank_name="CD 探针题库",
            subject="CDSubject",
            description="探针用",
            is_public=0,
        )
        await db.commit()
        bank_id = int(bank.id)

    questions = [
        {
            "questionType": 1,
            "questionText": f"探针题 {i}",
            "options": ["A", "B"],
            "answer": "0",
            "analysis": f"解析 {i}",
        }
        for i in range(1, 6)
    ]
    questions.append(
        {
            "questionType": 6,
            "questionText": "阅读理解大题",
            "content": "阅读材料正文",
            "has_sub_questions": 1,
            "subQuestions": [
                {"questionType": 1, "questionText": "子题1", "options": ["A"], "answer": "0"},
                {"questionType": 2, "questionText": "子题2", "options": ["A", "B"], "answer": "0,1"},
            ],
        }
    )
    questions.append(
        {"questionType": 2, "questionText": "多选题", "options": ["A", "B", "C"], "answer": "0,1"}
    )
    params = {
        "action": "batch_import",
        "bank_id": bank_id,
        "questions": json.dumps(questions, ensure_ascii=False),
    }

    # ---- A. 完整可编辑草稿 ----
    async with async_session_factory() as db:
        ctx = ToolContext(db=db, user_id=PROBE_UID, session_id=None, extra={"image_urls": []})
        preview = await tool.preview(params, ctx)

    draft = preview.get("draft") or {}
    check(
        "CD-01",
        "preview 带 kind=question_bank_import 的草稿",
        draft.get("kind") == "question_bank_import",
        str(draft.get("kind")),
    )
    check(
        "CD-02",
        "草稿含**全部**题目（7 条，不只 sample 5 条），且 count 一致",
        isinstance(draft.get("questions"), list)
        and len(draft["questions"]) == 7
        and preview.get("count") == 7,
        f"draft={len(draft.get('questions') or [])} count={preview.get('count')}",
    )
    draft_bank = draft.get("bank") or {}
    check(
        "CD-03",
        "草稿题库信息 = 反查到的真实题库（bankId/bankName/subject/isPublic）",
        draft_bank.get("bankId") == bank_id
        and draft_bank.get("bankName") == "CD 探针题库"
        and draft_bank.get("subject") == "CDSubject"
        and draft_bank.get("isPublic") == 0,
        str(draft_bank),
    )
    composite = [q for q in (draft.get("questions") or []) if q.get("questionType") == 6]
    check(
        "CD-04",
        "复合题（6）的 subQuestions 原样保留在草稿里",
        bool(composite)
        and isinstance(composite[0].get("subQuestions"), list)
        and len(composite[0]["subQuestions"]) == 2,
        str(composite[0] if composite else None),
    )

    # 预览与导入共用解析器 + 上限
    big = json.dumps(
        [{"questionType": 1, "questionText": f"n{i}"} for i in range(MAX_BATCH_SIZE + 10)]
    )
    items, _warns, _strategy = QuestionManageTool._parse_questions({"questions": big})
    check(
        "CD-05",
        f"_parse_questions 按 MAX_BATCH_SIZE({MAX_BATCH_SIZE}) 截断（预览=导入同一上限）",
        len(items) == MAX_BATCH_SIZE,
        str(len(items)),
    )

    # ---- B. edited 存取 + 覆盖工具参数 ----
    agent_loop.resolve_confirmation("cfm_cd_ok", True, edited={"questions": questions})
    approved, edited = await agent_loop._await_user_confirmation("cfm_cd_ok")
    check(
        "CD-06",
        "resolve_confirmation(id, True, edited=...) 存住并读回 (True, edited)",
        approved is True and isinstance(edited, dict) and edited.get("questions") == questions,
        f"approved={approved} keys={list((edited or {}).keys())}",
    )

    agent_loop.resolve_confirmation("cfm_cd_cancel", False)
    approved2, edited2 = await agent_loop._await_user_confirmation("cfm_cd_cancel")
    check(
        "CD-07",
        "取消（approved=False）读到 (False, None)",
        approved2 is False and edited2 is None,
        f"approved={approved2} edited={edited2}",
    )

    edited_questions = [
        {"questionType": 1, "questionText": "改过的题", "options": ["A", "B"], "answer": "1"}
    ]
    async with async_session_factory() as db:
        ctx2 = ToolContext(db=db, user_id=PROBE_UID, session_id=None, extra={"image_urls": []})
        new_params = await agent_loop._apply_edited_params(
            tool, dict(params), {"questions": edited_questions}, ctx2
        )
        reparsed, _w, _s = QuestionManageTool._parse_questions(new_params)
    check(
        "CD-08",
        "edited.questions（数组）→ 覆盖成 JSON 字符串，内容就是编辑后的题",
        isinstance(new_params.get("questions"), str)
        and len(reparsed) == 1
        and reparsed[0].get("questionText") == "改过的题",
        f"type={type(new_params.get('questions')).__name__} n={len(reparsed)}",
    )

    async with async_session_factory() as db:
        ctx3 = ToolContext(db=db, user_id=PROBE_UID, session_id=None, extra={"image_urls": []})
        await agent_loop._apply_edited_params(
            tool,
            dict(params),
            {"bank": {"bankId": bank_id, "subject": "CD_EDITED", "isPublic": 1}},
            ctx3,
        )
        await db.commit()

    from app.models.question import QuestionBank

    async with async_session_factory() as db:
        refreshed = await db.get(QuestionBank, bank_id)
    check(
        "CD-09",
        "edited.bank 只把给出的字段写回题库（subject=CD_EDITED / isPublic=1）",
        refreshed is not None
        and refreshed.subject == "CD_EDITED"
        and int(refreshed.is_public) == 1,
        f"subject={getattr(refreshed, 'subject', None)} isPublic={getattr(refreshed, 'is_public', None)}",
    )

    # 坏结构 → 退回原参数（不丢导入）
    async with async_session_factory() as db:
        ctx4 = ToolContext(db=db, user_id=PROBE_UID, session_id=None, extra={"image_urls": []})
        fallback = await agent_loop._apply_edited_params(
            tool, dict(params), {"questions": "not-a-list"}, ctx4
        )
    check(
        "CD-10",
        "edited 结构坏掉（questions 非数组）→ 退回原 questions 字符串",
        fallback.get("questions") == params["questions"],
        "unchanged" if fallback.get("questions") == params["questions"] else "CHANGED",
    )

    # ---- C. 取消导入：清掉「本轮新建的空题库」----
    async with async_session_factory() as db:
        empty_bank = await qws.create_bank(
            db, user_id=PROBE_UID, bank_name="CD 空库", subject="X", description="x"
        )
        await db.commit()
        empty_id = int(empty_bank.id)

    async with async_session_factory() as db:
        ctx5 = ToolContext(db=db, user_id=PROBE_UID, session_id=None, extra={"image_urls": []})
        created = {empty_id, bank_id}
        await agent_loop._rollback_empty_created_bank(
            ctx5, "question_manage", {"action": "batch_import", "bank_id": empty_id}, created
        )
    async with async_session_factory() as db:
        gone = await db.get(QuestionBank, empty_id)
        kept = await db.get(QuestionBank, bank_id)
    check(
        "CD-11",
        "取消导入 → 删除本轮新建的**空**题库",
        gone is None,
        f"empty_bank={gone}",
    )
    check(
        "CD-12",
        "已有内容的题库不受影响（bank_id 仍在）",
        kept is not None,
        f"kept={kept}",
    )

    await _cleanup()
    print("\n---- 确认流程可编辑草稿探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
