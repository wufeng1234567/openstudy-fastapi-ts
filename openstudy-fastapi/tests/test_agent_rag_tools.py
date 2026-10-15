"""
P4 Agent 集成测试：L1 自动注入 + L2 检索工具（knowledge_search / memory_search）

覆盖：
  1. **L1 自动注入**（`runtime_context.build_runtime_context`）
     · 长期记忆摘要 / 知识库清单两块内容分别渲染
     · 新用户 / 未指定 user_id → 返回空串（不注入空壳标签）
     · 查询失败 → 只少注入一段，不抛异常
  2. **`knowledge_search`**（只读）
     · list / search 两条 action
     · 参数校验（缺 query、未知 action）与越权（别人的 kbId → fail 而不是静默忽略）
     · 真实 embedding 检索：命中 + 带 source / chunkId / docId / chunkIndex / kbId
     · 检索不到时给的是「确实没有」而不是编造
  3. **`memory_search`**（只读）
     · list / search、memory_type 过滤、limit 夹取、非法类型被拒
     · 归属隔离：搜不到别人的记忆
  4. **只读性质**：两个工具跑完不该新增记忆（`write_operation=False`，
     否则「查了一下」也会被记成「做过什么」，把真正有用的记忆淹掉）

⚠️ 测试数据：
   · 知识库用 `__agent_tools_test__` 前缀，结束时**物理删**（`delete_knowledge_base`
     是逻辑删，会留 del_flag='2' 残骸，所以这里必须自己按外键顺序物理删）。
   · 记忆不落任何新增（两个工具都是只读的），跑完复核总数不变。

用法：
    ./.venv/Scripts/python.exe tests/test_agent_rag_tools.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

logger.remove()

from sqlalchemy import delete, func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.database import engine, register_all_models  # noqa: E402
from app.models.rag import (  # noqa: E402
    RagDocument,
    RagDocumentChunk,
    RagKnowledgeBase,
    RagQaRecord,
)
from app.services.ai.agent import runtime_context  # noqa: E402
from app.services.ai.agent.base import ToolContext  # noqa: E402
from app.services.ai.agent.registry import ensure_tools_loaded, registry  # noqa: E402
from app.services.ai.memory_service import (  # noqa: E402
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_EPISODIC,
    count_by_type,
    save_episodic,
)

PREFIX = "__agent_tools_test__"

#: 只在测试里用、跑完物理删的用户无关内容。挑两个真实用户：
#: 一个有记忆（验证注入），一个没有（验证空串）。
#: 归属隔离用例要「另一个用户」来搜同一个知识库。
DOC_TEXT = """# 数据结构复习

## 二叉搜索树

二叉搜索树是一种有序的二叉树。左子树所有节点的值都小于根节点，
右子树所有节点的值都大于根节点。查找、插入、删除的平均时间复杂度都是 O(log n)，
最坏情况退化成链表，复杂度变为 O(n)。

红黑树与 AVL 树都是自平衡的二叉搜索树变体，用来保证最坏情况下的对数复杂度。
"""

#: 与文档无关的提问，用来验证「确实没有」而不是编造
IRRELEVANT_QUERY = "红烧肉的正宗做法是什么"


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  [PASS] {name}" + (f" -> {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"  [FAIL] {name}" + (f" -> {detail}" if detail else ""))


# ---------------------------------------------------------------- 清理


async def _clear_test_memories(db, user_id: int) -> int:
    """只清**本测试写的**记忆（正文带 PREFIX 标记）。

    ⚠️ 绝对不要用 `memory_service.clear_memories(db, user_id)` 了事 ——
    那是「清空该用户的**全部**记忆」。本测试为了验隔离会挑一个**真实用户**
    （有记忆的那个）来读，一句 clear 就会把他的真实记忆全删掉。
    （本测试第一版正是这么写的，把用户 1 的 27 条真实记忆删光了，
    靠 `openstudy_v2`（MySQL 回滚库）才恢复回来。）
    """
    result = await db.execute(
        text("DELETE FROM ai_agent_memory WHERE user_id = :u AND POSITION(:p IN content) > 0"),
        {"u": user_id, "p": PREFIX},
    )
    await db.commit()
    return result.rowcount or 0


async def _memory_count(db, user_id: int) -> int:
    return int(
        await db.scalar(
            text("SELECT count(*) FROM ai_agent_memory WHERE user_id = :u"), {"u": user_id}
        )
        or 0
    )


async def _cleanup(db) -> dict:
    """物理删掉本测试造的知识库及其文档/分块/问答记录。

    删除顺序照顾外键：qa_record → chunk → document → kb。
    （`rag_qa_record` 也指向 kb，漏了它 KB 就删不掉，残留会一路累积。）
    """
    kb_ids = [
        r[0]
        for r in (
            await db.execute(
                select(RagKnowledgeBase.id).where(
                    func.left(RagKnowledgeBase.name, len(PREFIX)) == PREFIX
                )
            )
        ).all()
    ]
    if not kb_ids:
        await db.commit()
        return {"kb": 0, "doc": 0, "chunk": 0, "qa": 0}

    doc_ids = [
        r[0]
        for r in (
            await db.execute(select(RagDocument.id).where(RagDocument.kb_id.in_(kb_ids)))
        ).all()
    ]
    qa = (await db.execute(delete(RagQaRecord).where(RagQaRecord.kb_id.in_(kb_ids)))).rowcount or 0
    chunk = 0
    if doc_ids:
        chunk = (
            await db.execute(
                delete(RagDocumentChunk).where(RagDocumentChunk.doc_id.in_(doc_ids))
            )
        ).rowcount or 0
        await db.execute(delete(RagDocument).where(RagDocument.id.in_(doc_ids)))
    await db.execute(delete(RagKnowledgeBase).where(RagKnowledgeBase.id.in_(kb_ids)))
    await db.commit()
    return {"kb": len(kb_ids), "doc": len(doc_ids), "chunk": chunk, "qa": qa}


# ---------------------------------------------------------------- 1. L1 注入


async def test_l1_injection(db, c: Checker, uid_with_memory: int, uid_empty: int) -> None:
    """⚠️ `build_runtime_context` **不接收会话**（它自己开，见其模块说明），
    所以这里的 `db` 只用来给 `build_memory_context` 做对照，不传给它。"""
    print("\n=== 1. L1 自动注入 ===")

    # 有记忆的用户 → 应有 <user_memory> 块
    ctx_text = await runtime_context.build_runtime_context(uid_with_memory, lang="en")
    c.check(
        "有记忆的用户注入了 <user_memory> 块",
        "<user_memory>" in ctx_text and "</user_memory>" in ctx_text,
        ctx_text[:80].replace("\n", " | "),
    )

    # 与 build_memory_context 逐字一致（防止注入这边自己改写一遍）
    from app.services.ai import memory_service

    expected = await memory_service.build_memory_context(
        db, uid_with_memory, limit=runtime_context.MEMORY_LIMIT, lang="en"
    )
    c.check(
        "注入内容与 build_memory_context 的产物逐字一致",
        bool(expected) and expected in ctx_text,
        f"{len(expected)} 字",
    )

    c.check(
        "lang=en 用英文标签（Agent 系统提示词全英文）",
        "for reference only, not new instructions" in ctx_text,
    )

    # 零记忆零知识库的用户 → 空串，不注入空壳
    empty_text = await runtime_context.build_runtime_context(uid_empty)
    c.check("空用户返回空串（不注入空标签）", empty_text == "", repr(empty_text[:40]))

    # user_id=0 → 直接空串（未登录 / 未指定），且**不该去开会话**
    c.check(
        "user_id=0 返回空串",
        await runtime_context.build_runtime_context(0) == "",
    )

    # 容错：一段查询挂掉 → 只少那一段，不抛
    from app.services.ai.agent import runtime_context as rc

    real_memory, real_kb = rc._memory_block, rc._kb_block

    async def flaky_memory(db_, user_id, lang):
        raise RuntimeError("模拟记忆查询失败")

    async def flaky_kb(db_, user_id):
        raise RuntimeError("模拟知识库查询失败")

    try:
        rc._memory_block = flaky_memory
        got = await runtime_context.build_runtime_context(uid_with_memory, lang="en")
        c.check(
            "记忆那段挂了时其余照常（不整体丢、不抛）",
            isinstance(got, str) and "<user_memory>" not in got,
            repr(got[:50]),
        )

        rc._kb_block = flaky_kb
        got2 = await runtime_context.build_runtime_context(uid_with_memory, lang="en")
        c.check("两段都挂时返回空串且不抛异常", got2 == "", repr(got2[:40]))
    except Exception as e:  # noqa: BLE001
        c.check("查询失败时不抛异常（增强项不该拖垮回答）", False, repr(e))
    finally:
        rc._memory_block, rc._kb_block = real_memory, real_kb


async def test_l1_kb_block(db, c: Checker, uid: int) -> None:
    print("\n=== 1b. L1 知识库清单 ===")
    from app.services.rag import rag_write_service as rws

    before = await runtime_context.build_runtime_context(uid)
    c.check(
        "没有知识库时不注入 <knowledge_bases>",
        "<knowledge_bases>" not in before,
        repr(before[-60:]),
    )

    kb = await rws.create_knowledge_base(db, uid, f"{PREFIX}操作系统", description="L1 测试")
    await rws.create_knowledge_base(db, uid, f"{PREFIX}空库")
    try:
        with_kb = await runtime_context.build_runtime_context(uid)
        c.check(
            "有知识库时注入 <knowledge_bases>",
            "<knowledge_bases>" in with_kb and "</knowledge_bases>" in with_kb,
        )
        c.check(
            "清单里带 kbId（模型才能按库检索）",
            f"[kbId={kb.id}]" in with_kb,
            f"kbId={kb.id}",
        )
        c.check("清单里带库名与文档数", f"{PREFIX}操作系统" in with_kb and "EMPTY" in with_kb)
        c.check(
            "空库被标为 EMPTY（避免模型去检索一个必然是空的库）",
            f"[kbId={kb.id}] {PREFIX}操作系统 (EMPTY - nothing uploaded)" in with_kb,
        )
    finally:
        await _cleanup(db)


# ---------------------------------------------------------------- 2/3. knowledge_search


async def test_knowledge_search_params(db, c: Checker, ks, uid: int, other: int) -> None:
    print("\n=== 2. knowledge_search：参数校验与越权 ===")
    ctx = ToolContext(db=db, user_id=uid)

    r = await ks.execute({"action": "bogus"}, ctx)
    c.check("未知 action 被拒", not r.get("success") and "action" in str(r.get("hint")))

    r = await ks.execute({"action": "search"}, ctx)
    c.check("缺 query 被拒", not r.get("success") and "query" in str(r.get("error")))

    r = await ks.execute({"action": "search", "query": "任意", "kb_ids": [999999]}, ctx)
    c.check(
        "不存在的 kbId → fail（不静默忽略）",
        not r.get("success") and "999999" in str(r.get("error")),
        str(r.get("error"))[:60],
    )

    # 越权：别人的知识库 id 必须查不到
    r = await ks.execute({"action": "search", "query": "任意", "kb_ids": [999999]}, ToolContext(db=db, user_id=other))
    c.check("换个人用同样的 id 也照样被拒", not r.get("success"))

    r = await ks.execute({"action": "list"}, ctx)
    c.check(
        "list 返回 success 且形状正确",
        r.get("success") and isinstance(r.get("knowledgeBases"), list),
        f"count={r.get('count')}",
    )


async def test_knowledge_search_retrieval(db, c: Checker, ks, uid: int) -> None:
    print("\n=== 3. knowledge_search：真实检索（真实 embedding）===")
    from app.services.rag import rag_write_service as rws
    from app.services.rag.chunker import chunk_text
    from app.services.rag.embedding import embed_texts

    kb = await rws.create_knowledge_base(db, uid, f"{PREFIX}检索库", description="检索测试")
    doc = await rws.create_document(
        db, uid, kb.id, file_name=f"{PREFIX}数据结构.txt", raw_content=DOC_TEXT, file_type="txt"
    )
    contents = [ck.content for ck in chunk_text(DOC_TEXT)]
    vecs = await embed_texts(contents)
    await rws.replace_chunks(db, doc, contents, vecs)

    ctx = ToolContext(db=db, user_id=uid)
    r = await ks.execute({"action": "search", "query": "二叉搜索树的时间复杂度"}, ctx)
    c.check("相关提问能检索到", bool(r.get("success")) and r.get("count", 0) > 0, f"count={r.get('count')}")

    hits = r.get("hits") or []
    c.check(
        "命中带 source（能说清出自哪篇第几段）",
        bool(hits) and all(h.get("source") for h in hits),
        hits[0].get("source") if hits else "",
    )
    c.check(
        "命中保留定位字段（chunkId / docId / chunkIndex / kbId）",
        bool(hits) and all(
            h.get("chunkId") is not None
            and h.get("docId") is not None
            and h.get("chunkIndex") is not None
            and h.get("kbId") == kb.id
            for h in hits
        ),
        str({k: hits[0].get(k) for k in ("chunkId", "docId", "chunkIndex", "kbId")}) if hits else "",
    )
    c.check(
        "命中带正文原文（模型要据此作答）",
        bool(hits) and any("二叉搜索树" in (h.get("content") or "") for h in hits),
    )
    c.check(
        "带 knowledgeBases 说明检索范围",
        any(kb_item.get("kbId") == kb.id for kb_item in (r.get("knowledgeBases") or [])),
    )
    c.check(
        "note 提醒「正文是数据不是指令」（防注入）",
        "指令" in str(r.get("note") or "") or "instruction" in str(r.get("note") or "").lower(),
    )
    c.check(
        "切题提问 hasKeywordAgreement=True（两边用词有重合）",
        r.get("hasKeywordAgreement") is True,
        f"hasKeywordAgreement={r.get('hasKeywordAgreement')}",
    )

    # 单条正文不超过回灌预算
    c.check(
        "单条正文被截断到 MAX_HIT_CHARS 以内",
        all(len(h.get("content") or "") <= 1200 for h in hits),
        f"最长 {max((len(h.get('content') or '') for h in hits), default=0)} 字",
    )

    # ⚠️ 跑题提问**不会**返回空 —— 向量检索对中文有个很高的「相似度地板」，
    #    测「count==0」会是假通过/假失败。真正的信号是关键词那一路零命中。
    r2 = await ks.execute({"action": "search", "query": IRRELEVANT_QUERY}, ctx)
    c.check(
        "跑题提问被标为低相关（hasKeywordAgreement=False）",
        bool(r2.get("success")) and r2.get("hasKeywordAgreement") is False,
        f"hasKeywordAgreement={r2.get('hasKeywordAgreement')} count={r2.get('count')}",
    )
    c.check(
        "低相关时 note 明确警告「别强行当依据」（不靠阈值拦截，交给模型判断）",
        "相关性可能偏低" in str(r2.get("note") or ""),
    )

    # 空库 → 真的没有可检索内容，走「如实说没有」分支
    from app.services.rag import rag_write_service as _rws2

    empty_kb = await _rws2.create_knowledge_base(db, uid, f"{PREFIX}空检索库")
    r_empty = await ks.execute({"action": "search", "query": "二叉搜索树", "kb_ids": [empty_kb.id]}, ctx)
    c.check(
        "知识库没有内容时返回「确实没有」而不是编造",
        bool(r_empty.get("success"))
        and r_empty.get("count") == 0
        and "没有检索到" in str(r_empty.get("note") or ""),
        f"count={r_empty.get('count')}",
    )

    # 只搜指定库
    r3 = await ks.execute({"action": "search", "query": "二叉搜索树", "kb_ids": [kb.id], "top_k": 2}, ctx)
    c.check(
        "top_k 生效（不超过请求条数）",
        bool(r3.get("success")) and len(r3.get("hits") or []) <= 2,
        f"{len(r3.get('hits') or [])} 条",
    )
    r4 = await ks.execute({"action": "search", "query": "二叉搜索树", "top_k": 999}, ctx)
    c.check(
        "top_k 被夹到上限（不给模型把上下文打穿的机会）",
        bool(r4.get("success")) and len(r4.get("hits") or []) <= 8,
        f"{len(r4.get('hits') or [])} 条（上限 8）",
    )


# ---------------------------------------------------------------- 4. memory_search


async def test_memory_search(db, c: Checker, ms, uid: int, other: int) -> None:
    print("\n=== 4. memory_search ===")
    ctx = ToolContext(db=db, user_id=uid)

    r = await ms.execute({"action": "bogus"}, ctx)
    c.check("未知 action 被拒", not r.get("success"))

    r = await ms.execute({"action": "search"}, ctx)
    c.check("search 缺 query 被拒", not r.get("success"))

    r = await ms.execute({"action": "list", "memory_type": "nope"}, ctx)
    c.check("非法 memory_type 被拒", not r.get("success"), str(r.get("error"))[:40])

    await _clear_test_memories(db, uid)
    await save_episodic(db, uid, f"{PREFIX}建了题库甲")
    await save_episodic(db, uid, f"{PREFIX}删了题库乙")

    r = await ms.execute({"action": "list"}, ctx)
    c.check("list 取到记忆", r.get("count") == 2, f"count={r.get('count')}")
    c.check(
        "返回字段齐（memoryId / memoryType / content / importance / createTime）",
        bool(r.get("memories"))
        and all(
            m.get("memoryId") is not None
            and m.get("memoryType")
            and m.get("content")
            and m.get("importance") is not None
            and m.get("createTime")
            for m in r["memories"]
        ),
    )
    c.check(
        "带 note 提醒「记忆是过去时刻，确认现状要重新查」（防模型把过期记忆当现状）",
        "过期" in str(r.get("note") or "") or "past" in str(r.get("note") or "").lower(),
    )

    r = await ms.execute({"action": "search", "query": "题库甲"}, ctx)
    c.check("按关键词搜到", r.get("count") == 1, f"count={r.get('count')}")

    r = await ms.execute({"action": "search", "query": "不存在的关键词zzz"}, ctx)
    c.check(
        "搜不到时如实告知且不编造",
        r.get("success") and r.get("count") == 0 and "不要编造" in str(r.get("message")),
        str(r.get("message"))[:50],
    )

    r = await ms.execute({"action": "list", "memory_type": MEMORY_TYPE_EPISODIC}, ctx)
    c.check("memory_type 过滤生效（episodic）", r.get("count") == 2)
    r = await ms.execute({"action": "list", "memory_type": MEMORY_TYPE_CONVERSATION}, ctx)
    c.check("memory_type 过滤生效（conversation 为空）", r.get("count") == 0)

    r = await ms.execute({"action": "list", "limit": 9999}, ctx)
    c.check(
        "limit 被夹到上限",
        bool(r.get("success")) and r.get("count") <= 20,
        f"count={r.get('count')}（上限 20）",
    )

    # 归属隔离
    r = await ms.execute({"action": "search", "query": "题库甲"}, ToolContext(db=db, user_id=other))
    c.check("搜不到别人的记忆", r.get("success") and r.get("count") == 0)

    # 只读：查一下不该新增记忆
    before = await count_by_type(db, uid)
    for _ in range(3):
        await ms.execute({"action": "list"}, ctx)
        await ms.execute({"action": "search", "query": "题库"}, ctx)
    after = await count_by_type(db, uid)
    c.check(
        "memory_search 是只读的（查记忆不产生新记忆）",
        before == after,
        f"{before} → {after}",
    )
    c.check(
        "两个工具都声明 write_operation=False（不会被 memory_hook 记）",
        registry.get("memory_search").write_operation is False
        and registry.get("knowledge_search").write_operation is False,
    )
    c.check(
        "两个工具都声明不需要确认（只读工具不该弹确认卡片）",
        not registry.get("memory_search").needs_confirmation({"action": "search"})
        and not registry.get("knowledge_search").needs_confirmation({"action": "search"}),
    )

    await _clear_test_memories(db, uid)


# ---------------------------------------------------------------- 主流程


async def run() -> int:
    register_all_models()
    ensure_tools_loaded()
    c = Checker()
    from app.database import IS_POSTGRES

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        try:
            print("\n=== 0. 目标库确认 ===")
            info = (await db.execute(text("SELECT current_database()"))).first()
            c.check("连的是 openstudy_v2_pgsql", bool(info) and info[0] == "openstudy_v2_pgsql", info[0] if info else "")
            c.check("是 PostgreSQL", IS_POSTGRES)

            # 挑两个真实用户：一个有记忆（注入非空），一个没有（注入为空）
            uid_with_memory = int(
                await db.scalar(
                    text(
                        "SELECT user_id FROM ai_agent_memory GROUP BY user_id "
                        "ORDER BY count(*) DESC LIMIT 1"
                    )
                )
                or 0
            )
            uid_empty = int(
                await db.scalar(
                    text(
                        "SELECT u.user_id FROM sys_user u "
                        "LEFT JOIN (SELECT user_id, count(*) c FROM ai_agent_memory GROUP BY user_id) m "
                        "  ON u.user_id = m.user_id "
                        "WHERE COALESCE(m.c, 0) = 0 AND u.user_id <> :a ORDER BY u.user_id LIMIT 1"
                    ),
                    {"a": uid_with_memory},
                )
                or 0
            )
            c.check("找到「有记忆」的用户", uid_with_memory > 0, f"uid={uid_with_memory}")
            c.check("找到「零记忆」的用户（隔离用）", uid_empty > 0, f"uid={uid_empty}")
            if not uid_with_memory or not uid_empty:
                raise RuntimeError("缺少可用测试用户")

            before_total = int(
                await db.scalar(text("SELECT count(*) FROM ai_agent_memory")) or 0
            )
            # ⚠️ 真实用户的记忆条数：本测试**只读**它，跑完必须一模一样。
            #    这是防止「清理时顺手把真实用户的记忆清了」的硬约束 ——
            #    本测试第一版就犯过这个错（一句 clear_memories 删光了用户 1 的 27 条）。
            real_user_memories = await _memory_count(db, uid_with_memory)
            c.check(
                "真实用户（有记忆那个）在跑之前有记忆可保护",
                real_user_memories > 0,
                f"uid={uid_with_memory} 共 {real_user_memories} 条",
            )

            # 预清历史残留
            await _cleanup(db)

            ks = registry.get("knowledge_search")
            ms = registry.get("memory_search")
            c.check("knowledge_search 已注册", ks is not None)
            c.check("memory_search 已注册", ms is not None)

            await test_l1_injection(db, c, uid_with_memory, uid_empty)
            # 知识库清单属于「这个用户有什么」，用零记忆用户建库不会污染
            await test_l1_kb_block(db, c, uid_empty)
            await test_knowledge_search_params(
                db, c, ks, uid_with_memory, uid_empty
            )
            await test_knowledge_search_retrieval(db, c, ks, uid_with_memory)
            # 记忆读写用零记忆用户（跑完清回 0，不碰真实数据）
            await test_memory_search(db, c, ms, uid_empty, uid_with_memory)

            after_total = int(await db.scalar(text("SELECT count(*) FROM ai_agent_memory")) or 0)
            c.check(
                "测试期间未新增任何记忆（两个工具都是只读的）",
                after_total == before_total,
                f"测试前 {before_total} → 现在 {after_total}",
            )
            now_real = await _memory_count(db, uid_with_memory)
            c.check(
                "**真实用户的记忆一条没少**（只读，绝不 clear）",
                now_real == real_user_memories,
                f"uid={uid_with_memory}: {real_user_memories} → {now_real}",
            )

        except Exception as e:
            c.failed += 1
            print(f"\n  [ERROR] 测试抛异常: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("\n=== 5. 清理测试数据 ===")
            try:
                await db.rollback()
                removed = await _cleanup(db)
                print(
                    f"  [清理] 物理删除 知识库 {removed['kb']} / 文档 {removed['doc']} "
                    f"/ 分块 {removed['chunk']} / 问答记录 {removed['qa']}"
                )
                # ⚠️ 只按标记清本测试写的记忆。**不要** clear_memories(uid_with_memory) ——
                #    那是清空真实用户的全部记忆（本测试第一版就这么干过）。
                if uid_empty:
                    n = await _clear_test_memories(db, uid_empty)
                    if n:
                        print(f"  [清理] 清掉用户 {uid_empty} 的 {n} 条测试记忆")
                # 真实用户的记忆：跑完复核一遍，少了就是 bug，直接红
                if uid_with_memory:
                    left = await _memory_count(db, uid_with_memory)
                    c.check(
                        "清理后复核：真实用户的记忆仍是原样",
                        left == real_user_memories,
                        f"uid={uid_with_memory}: {real_user_memories} → {left}",
                    )
                left_kb = int(await db.scalar(text("SELECT count(*) FROM rag_knowledge_base")) or 0)
                left_mem = int(await db.scalar(text("SELECT count(*) FROM ai_agent_memory")) or 0)
                print(f"  [复核] 知识库剩 {left_kb} 条；记忆剩 {left_mem} 条")
            except Exception as e:
                print(f"  [WARN] 清理失败: {e}")

    await engine.dispose()
    print(f"\n{'='*60}\n结果：{c.passed} 通过 / {c.failed} 失败")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
