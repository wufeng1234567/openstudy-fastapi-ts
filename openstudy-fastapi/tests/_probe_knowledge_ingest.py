# -*- coding: utf-8 -*-
"""`knowledge_ingest` 工具探针 —— 零 DB、零网络、零 embedding 成本

⚠️ 这是**刻意保留**的验证脚本，不是跑完就删的临时文件。理由：该工具会真调
embedding（花钱），而整套 e2e 走真实链路时「写入知识库」这条能力没有零成本的可复现
验证手段。本脚本补上：全程 **monkeypatch** 掉
  · `rag_write_service.get_knowledge_base` / `create_document`
  · `document_pipeline.process_document`
  · `asyncio` 的后台任务调度（记录被调度的 doc_id，不真跑）
所以不碰数据库、不发网络请求、不花一分钱，却能锁定工具的关键契约。

覆盖：
  1. 元数据（name / write_operation / needs_confirmation / is_destructive）
  2. `preview()`：只预估块数 + embedCalls，**不落库不调 embedding**
  3. `from_text`：落库 status=DOC_PENDING、后台任务被调度、回执字段齐全
  4. 失败分支：未知 action / 缺 kb_id / 空 text / 超长 / 附件越界 / 无附件
  5. `from_attachment`：从 `ctx.extra["attachments"]` 取正文
  6. `undo_plan`：物理删该文档、undoable=True、reason=content_destroyed

用法
----
    .venv/Scripts/python.exe tests/_probe_knowledge_ingest.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

#: 断言计数（红=失败）
ROWS = []


def check(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


class _FakeKb:
    def __init__(self, kid=1, name="计算机网络", user_id=777):
        self.id = kid
        self.name = name
        self.user_id = user_id
        self.doc_count = 0
        self.chunk_count = 0


class _FakeDoc:
    def __init__(self, doc_id=4242, kb_id=1, file_name="t.txt"):
        self.id = doc_id
        self.kb_id = kb_id
        self.file_name = file_name
        self.status = 1


async def run_probe() -> int:
    from app.services.ai.agent.base import ToolContext
    from app.services.ai.agent.tools import knowledge_ingest as ki
    from app.services.rag import rag_write_service as rws
    from app.services.rag.rag_write_service import RagNotFound

    scheduled: list[int] = []
    created: list[dict] = []
    current_kb = _FakeKb()

    # ---- monkeypatch：全部替换成零成本假实现 ----
    async def fake_get_kb(db, user_id, kb_id):
        if int(kb_id) != current_kb.id or user_id != current_kb.user_id:
            raise RagNotFound(f"知识库不存在或无权访问：{kb_id}")
        return current_kb

    async def fake_create_document(db, user_id, kb_id, *, file_name, raw_content, **kw):
        # 忠实模拟真实 create_document：**内部会先 get_knowledge_base 校验归属**，
        # 不属于自己直接抛 RagNotFound（否则测试会误判「越权写入成功」）。
        await fake_get_kb(db, user_id, kb_id)
        created.append({"kb_id": kb_id, "file_name": file_name, "raw": raw_content, **kw})
        return _FakeDoc(doc_id=9000 + len(created), kb_id=kb_id, file_name=file_name)

    orig_get_kb = rws.get_knowledge_base
    orig_create = rws.create_document
    rws.get_knowledge_base = fake_get_kb
    rws.create_document = fake_create_document

    # 后台处理调度：拦下 create_task，只记录 doc_id，不真跑流水线
    orig_schedule = ki.KnowledgeIngestTool._schedule_processing

    def fake_schedule(doc_id):
        scheduled.append(doc_id)

    ki.KnowledgeIngestTool._schedule_processing = staticmethod(fake_schedule)

    try:
        tool = ki.KnowledgeIngestTool()
        ctx = ToolContext(db=object(), user_id=777, session_id="s1", extra={})

        # ---- 1. 元数据口径 ----
        check("KI-01", "name 正确", tool.name == "knowledge_ingest", tool.name)
        check("KI-02", "是写操作", tool.write_operation is True, str(tool.write_operation))
        check("KI-03", "所有 action 都需确认", tool.needs_confirmation({"action": "from_text"}) is True)
        check("KI-04", "非破坏性（新建不毁数据）", tool.is_destructive({"action": "from_text"}) is False)

        # ---- 2. preview 只预估不落库 ----
        before_created = len(created)
        text_short = "计算机网络的分层模型：应用层、传输层、网络层、链路层。" * 3
        pv = await tool.preview({"action": "from_text", "kb_id": 1, "text": text_short}, ctx)
        check("KI-05", "preview 反查到库名", pv.get("kbName") == "计算机网络", str(pv))
        check("KI-06", "preview 给出块数", pv.get("chunks", 0) >= 1, str(pv.get("chunks")))
        check(
            "KI-07",
            "preview 给出 embedCalls 估算",
            pv.get("embedCalls", 0) >= 1,
            str(pv.get("embedCalls")),
        )
        check("KI-08", "preview 绝不落库", len(created) == before_created, f"created={len(created)}")

        # ---- 3. from_text 正常路径 ----
        r = await tool.execute({"action": "from_text", "kb_id": 1, "text": text_short}, ctx)
        check("KI-09", "from_text 成功", r.get("success") is True, str(r))
        check("KI-10", "落库 status=DOC_PENDING(1)", r.get("status") == 1, str(r.get("status")))
        check("KI-11", "回执带 docId", isinstance(r.get("docId"), int), str(r.get("docId")))
        check("KI-12", "回执带 kbName", r.get("kbName") == "计算机网络", str(r.get("kbName")))
        check("KI-13", "create_document 收到正文", created and created[-1]["raw"] == text_short)
        check(
            "KI-14",
            "create_document 收到 status=DOC_PENDING",
            created and created[-1].get("status") == 1,
            str(created[-1].get("status") if created else None),
        )
        check("KI-15", "后台向量化任务被调度", scheduled and scheduled[-1] == r["docId"], str(scheduled))

        # ---- 4. 失败分支 ----
        bad = await tool.execute({"action": "nope", "kb_id": 1, "text": "x"}, ctx)
        check("KI-16", "未知 action → fail", bad.get("success") is False and "hint" in bad, str(bad))

        bad = await tool.execute({"action": "from_text", "text": "x"}, ctx)
        check("KI-17", "缺 kb_id → fail", bad.get("success") is False, str(bad))

        bad = await tool.execute({"action": "from_text", "kb_id": 1, "text": "   "}, ctx)
        check("KI-18", "空 text → fail", bad.get("success") is False, str(bad))

        bad = await tool.execute(
            {"action": "from_text", "kb_id": 1, "text": "a" * (ki.MAX_RAW_LENGTH + 1)}, ctx
        )
        check("KI-19", "超长 text → fail", bad.get("success") is False, str(bad))

        bad = await tool.execute({"action": "from_text", "kb_id": 999, "text": "x"}, ctx)
        check("KI-20", "kb 不属于自己 → fail", bad.get("success") is False, str(bad))

        # ---- 5. from_attachment ----
        bad = await tool.execute({"action": "from_attachment", "kb_id": 1}, ctx)
        check("KI-21", "无附件 → fail", bad.get("success") is False and "hint" in bad, str(bad))

        ctx_att = ToolContext(
            db=object(),
            user_id=777,
            extra={"attachments": [{"name": "a.md", "text": "附件正文内容"}]},
        )
        r = await tool.execute({"action": "from_attachment", "kb_id": 1, "file_name": "a.md"}, ctx_att)
        check("KI-22", "from_attachment 成功", r.get("success") is True, str(r))
        check(
            "KI-23",
            "from_attachment 取到附件正文",
            created and created[-1]["raw"] == "附件正文内容",
            str(created[-1]["raw"] if created else None),
        )

        bad = await tool.execute({"action": "from_attachment", "kb_id": 1, "index": 5}, ctx_att)
        check("KI-24", "附件序号越界 → fail", bad.get("success") is False, str(bad))

        # ---- 6. undo_plan ----
        plan = tool.undo_plan({"action": "from_text"}, {"docId": 4242})
        check("KI-25", "undo_plan 可回退", plan and plan.get("undoable") is True, str(plan))
        check(
            "KI-26",
            "undo_plan 目标表/op 正确",
            plan and plan.get("targetTable") == "rag_document" and plan.get("targetIds") == [4242],
            str(plan),
        )
        check(
            "KI-27",
            "undo_plan reason=content_destroyed（删了重建要花钱）",
            plan and plan.get("reason") == "content_destroyed",
            str(plan.get("reason")),
        )
        plan_none = tool.undo_plan({}, {})
        check(
            "KI-28",
            "回执无 docId → 不可回退(missing_target_id)",
            plan_none and plan_none.get("undoable") is False,
            str(plan_none),
        )

    finally:
        rws.get_knowledge_base = orig_get_kb
        rws.create_document = orig_create
        ki.KnowledgeIngestTool._schedule_processing = staticmethod(orig_schedule)

    print("\n---- knowledge_ingest 探针结果 ----")
    for r in ROWS:
        print(f"  [{r['status']}] {r['cid']} {r['title']}" + (f" | 实际: {r['actual']}" if r["status"] != "通过" else ""))
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
