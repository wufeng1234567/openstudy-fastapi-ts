"""
RAG（PostgreSQL + pgvector）后端功能测试

验证 PG 侧实现真的能用，而不是只看建表成功：
  1. Schema：vector(1024) / tsvector 生成列 / HNSW + GIN 索引
  2. 写入：知识库 → 文档 → 分块（真实调用硅基流动 embedding + jieba 分词）
  3. 生成列：`search_vec` 由 `content_tokens` 自动生成（应用层不维护）
  4. 向量检索：语义相近能命中正确的块
  5. 关键词检索：**中文**能命中（PG 内置分词不切中文，靠的是 jieba 预分词这条链）
  6. 混合检索：RRF 融合两路，两路都命中的块排最前
  7. 知识库隔离：搜 KB-A 不会漏出 KB-B 的块（这是 legacy「超取再内存过滤」的漏召回点）
  8. 清理：无论成功失败都删掉本次全部测试数据

用法：
    ./.venv/Scripts/python.exe tests/test_rag_pg.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from loguru import logger  # noqa: E402

# 测试输出里混进 INFO 日志会让人分不清哪行是断言结果
logger.remove()

from app.database import engine  # noqa: E402

# 必须先把所有模型注册进 Base.metadata，否则 rag_* 的外键
# （→ sys_user.user_id / rag_knowledge_base.id）解析不到目标表，
# 会在 flush 时抛 NoReferencedTableError。与 `database.init_db()` 的导入清单一致。
from app.models import (  # noqa: E402,F401
    ai_chat,
    ai_config,
    bank_share,
    config,
    courses,
    menu,
    note,
    note_question,
    note_question_bank,
    notice,
    notification,
    question,
    role,
    user,
    words,
)
from app.api.v1 import carousel, chat, leave_message, sensitive_word  # noqa: E402,F401

from app.models.agent_memory import MEMORY_CONTENT_MAX, AiAgentMemory  # noqa: E402
from app.models.rag import (  # noqa: E402
    DOC_VECTORIZED,
    EMBEDDING_DIM,
    RagDocument,
    RagDocumentChunk,
    RagKnowledgeBase,
    RagQaRecord,
)
from app.services.rag.embedding import embed_query, embed_texts  # noqa: E402
from app.services.rag.hybrid_search import hybrid_search, keyword_search, vector_search  # noqa: E402
from app.services.rag.tokenizer import tokenize  # noqa: E402

#: 测试数据前缀，便于清理与人工识别
PREFIX = "__rag_pg_test__"

#: 用于验证越权的假用户 id。真实 sys_user 里不存在这个 id
#: （现有 1/2/103/104/105/106/111），所以按它清理不会误伤真实数据。
FAKE_USER_ID = 9999

# 三块内容刻意这样设计：
#   A 有独特中文术语「二叉搜索树」，且与查询语义相近
#   B 有独特代码标识符 `is_public`（纯向量容易漏，关键词能精确命中）
#   C 是完全无关的干扰项（必须检索不到）
KB_A_DOC = """# 数据结构复习

## 二叉搜索树

二叉搜索树是一种有序的二叉树。左子树所有节点的值都小于根节点，
右子树所有节点的值都大于根节点。查找、插入、删除的平均时间复杂度都是 O(log n)，
最坏情况退化成链表，复杂度变为 O(n)。

红黑树与 AVL 树都是自平衡的二叉搜索树变体，用来保证最坏情况下的对数复杂度。
"""

KB_A_DOC2 = """# 项目字段约定

## 可见性字段

题库表的 `is_public` 字段语义是 0 表示公开、1 表示私有。
笔记表的 `is_public` 是反过来的：1 表示公开。这个反转是历史遗留，写反了很难查。
"""

KB_B_DOC = """# 无关内容

今天天气不错，适合出门散步。顺便记录一下晚餐做了什么菜。
"""

QUERY_SEMANTIC = "二叉搜索树的时间复杂度是多少"
QUERY_KEYWORD = "is_public 字段语义"


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


async def _cleanup(session) -> None:
    """按外键顺序删掉本次测试数据。

    ⚠️ 前缀匹配用 `LEFT(col, LENGTH(:p)) = :p`，**不能用 LIKE** ——
    `PREFIX` 里含 `_`，而 `_` 在 LIKE 里是单字符通配符，会匹配到真实数据。
    （这是项目里已记录过的踩坑，见 `.codebuddy/rules/testing.md`）

    ⚠️ **删除顺序必须照顾全部外键**：`rag_qa_record` 也指向 `rag_knowledge_base`，
    漏掉它会导致 KB 删不掉（`ForeignKeyViolationError`），残留一路累积到下一轮，
    下次运行就撞「已存在同名知识库」。
    """
    kb_ids = [
        r[0]
        for r in (
            await session.execute(
                select(RagKnowledgeBase.id).where(
                    func.left(RagKnowledgeBase.name, len(PREFIX)) == PREFIX
                )
            )
        ).all()
    ]
    if not kb_ids:
        return

    # 1) 问答记录（同时清掉用假用户 9999 造的、kb_id 为空的那条）
    await session.execute(delete(RagQaRecord).where(RagQaRecord.kb_id.in_(kb_ids)))
    await session.execute(delete(RagQaRecord).where(RagQaRecord.user_id == FAKE_USER_ID))

    # 2) 分块 → 3) 文档 → 4) 知识库
    doc_ids = [
        r[0]
        for r in (
            await session.execute(select(RagDocument.id).where(RagDocument.kb_id.in_(kb_ids)))
        ).all()
    ]
    if doc_ids:
        await session.execute(delete(RagDocumentChunk).where(RagDocumentChunk.doc_id.in_(doc_ids)))
        await session.execute(delete(RagDocument).where(RagDocument.id.in_(doc_ids)))
    await session.execute(delete(RagKnowledgeBase).where(RagKnowledgeBase.id.in_(kb_ids)))
    await session.commit()
    print(f"  [清理] 删除 {len(kb_ids)} 个知识库 / {len(doc_ids)} 篇文档及相关分块与问答记录")


async def run() -> int:
    c = Checker()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        try:
            # 开跑前先清一次：上一轮若中途失败会留下同名知识库，
            # 不清的话这一轮会在 create 阶段直接撞 RagConflict，测不到后面的东西。
            # 这样脚本可重复执行。
            await _cleanup(db)

            # ---------- 0. 确认目标库（红线：执行任何 SQL 前先确认库名） ----------
            print("\n=== 0. 目标库确认 ===")
            info = (
                await db.execute(
                    text("SELECT current_database(), version()")
                )
            ).first()
            c.check(
                "连的是预期库 openstudy_v2_pgsql",
                info and info[0] == "openstudy_v2_pgsql",
                info[0] if info else "未知",
            )
            c.check(
                "是 PostgreSQL（RAG 表只在 PG 下可用）",
                info and "PostgreSQL" in (info[1] or ""),
                (info[1] or "").split(",")[0] if info else "",
            )

            # ---------- 1. Schema ----------
            print("\n=== 1. Schema ===")
            col = (
                await db.execute(
                    text(
                        "SELECT data_type, udt_name FROM information_schema.columns "
                        "WHERE table_name='rag_document_chunk' AND column_name='embedding'"
                    )
                )
            ).first()
            c.check("embedding 列类型是 vector(1024)", col and col[1] == "vector", str(col))

            gen = (
                await db.execute(
                    text(
                        "SELECT is_generated, generation_expression FROM information_schema.columns "
                        "WHERE table_name='rag_document_chunk' AND column_name='search_vec'"
                    )
                )
            ).first()
            c.check(
                "search_vec 是生成列且用 to_tsvector",
                gen and gen[0] == "ALWAYS" and "to_tsvector" in (gen[1] or ""),
                f"generated={gen[0] if gen else None}",
            )

            idx = {
                r[0]: r[1]
                for r in (
                    await db.execute(
                        text(
                            "SELECT indexname, indexdef FROM pg_indexes "
                            "WHERE tablename='rag_document_chunk'"
                        )
                    )
                ).all()
            }
            c.check(
                "HNSW 向量索引存在",
                "hnsw" in idx.get("idx_rag_chunk_embedding", "") and "vector_cosine_ops" in idx.get("idx_rag_chunk_embedding", ""),
            )
            c.check("GIN 全文索引存在", "gin" in idx.get("idx_rag_chunk_fts", ""))
            c.check("GIN trigram 索引存在", "gin_trgm_ops" in idx.get("idx_rag_chunk_trgm", ""))
            c.check("kb_id 过滤索引存在", "idx_rag_chunk_kb" in idx)

            # ---------- 2. 写入（真实 embedding） ----------
            print("\n=== 2. 写入知识库 / 文档 / 分块 ===")
            kb_a = RagKnowledgeBase(
                user_id=1, name=f"{PREFIX}知识库A", description="功能测试用"
            )
            kb_b = RagKnowledgeBase(
                user_id=1, name=f"{PREFIX}知识库B", description="功能测试用"
            )
            db.add_all([kb_a, kb_b])
            await db.commit()

            async def add_doc(kb: RagKnowledgeBase, name: str, raw: str) -> RagDocument:
                # 每段一个 chunk，模拟分块器的产物
                paras = [p for p in raw.split("\n\n") if p.strip()]
                doc = RagDocument(
                    kb_id=kb.id,
                    user_id=kb.user_id,
                    file_name=f"{PREFIX}{name}",
                    file_type="txt",
                    raw_content=raw,
                    chunk_count=len(paras),
                    status=DOC_VECTORIZED,
                )
                db.add(doc)
                await db.flush()

                vectors = await embed_texts(paras)
                for i, (p, vec) in enumerate(zip(paras, vectors)):
                    db.add(
                        RagDocumentChunk(
                            kb_id=kb.id,
                            doc_id=doc.id,
                            chunk_index=i,
                            content=p,
                            content_length=len(p),
                            content_tokens=tokenize(p),
                            embedding=vec,
                            meta_data={"file_name": doc.file_name},
                        )
                    )
                return doc

            await add_doc(kb_a, "数据结构.txt", KB_A_DOC)
            await add_doc(kb_a, "字段约定.txt", KB_A_DOC2)
            await add_doc(kb_b, "天气.txt", KB_B_DOC)
            await db.commit()

            # 期望块数 = 各文档按空行切出的非空段落数（标题行也是独立段落）
            expected_chunks = sum(
                len([p for p in raw.split("\n\n") if p.strip()])
                for raw in (KB_A_DOC, KB_A_DOC2, KB_B_DOC)
            )
            total = (
                await db.execute(
                    select(RagDocumentChunk.id).where(RagDocumentChunk.kb_id.in_([kb_a.id, kb_b.id]))
                )
            ).all()
            c.check(
                "分块写入成功（真实 embedding）",
                len(total) == expected_chunks,
                f"写入 {len(total)} 块，期望 {expected_chunks} 块",
            )

            # ---------- 3. 生成列 ----------
            print("\n=== 3. 生成列 search_vec ===")
            row = (
                await db.execute(
                    text(
                        "SELECT search_vec IS NOT NULL, search_vec::text FROM rag_document_chunk "
                        "WHERE kb_id = :kb ORDER BY chunk_index LIMIT 1"
                    ),
                    {"kb": kb_a.id},
                )
            ).first()
            c.check("search_vec 自动生成（应用层未写）", bool(row and row[0]))

            # 挑真正含中文术语的那一块来验分词（第 0 块是标题行，验不出「二叉搜索树」）
            cn_row = (
                await db.execute(
                    text(
                        "SELECT content, search_vec::text FROM rag_document_chunk "
                        "WHERE kb_id = :kb AND content LIKE '%二叉搜索树%' LIMIT 1"
                    ),
                    {"kb": kb_a.id},
                )
            ).first()
            c.check("找到含「二叉搜索树」的块", cn_row is not None)
            c.check(
                "生成的 lexeme 含中文词（证明 jieba 分词链路生效）",
                bool(cn_row and "二叉" in (cn_row[1] or "") and "搜索" in (cn_row[1] or "")),
                (cn_row[1] or "")[:90] + "..." if cn_row else "未找到",
            )

            # ---------- 4. 向量检索 ----------
            print("\n=== 4. 向量检索（语义） ===")
            qv = await embed_query(QUERY_SEMANTIC)
            c.check("查询向量维度 = 1024", len(qv) == EMBEDDING_DIM, f"{len(qv)} 维")

            vec_hits = await vector_search(db, qv, [kb_a.id], top_k=3)
            c.check("向量检索有结果", len(vec_hits) > 0, f"{len(vec_hits)} 条")
            c.check(
                "向量检索命中「二叉搜索树」那块",
                bool(vec_hits) and "二叉搜索树" in vec_hits[0].content,
                f"top1 相似度={vec_hits[0].vector_score:.4f}" if vec_hits else "无结果",
            )
            print(f"        出处：{vec_hits[0].source}" if vec_hits else "")

            # ---------- 5. 关键词检索（中文） ----------
            print("\n=== 5. 关键词检索（中文 + 代码标识符） ===")
            kw_hits = await keyword_search(db, QUERY_KEYWORD, [kb_a.id], top_k=3)
            c.check("关键词检索有结果", len(kw_hits) > 0, f"{len(kw_hits)} 条")
            c.check(
                "关键词命中含 is_public 的那块",
                bool(kw_hits) and "is_public" in kw_hits[0].content,
                f"top1 rank={kw_hits[0].keyword_score:.4f}" if kw_hits else "无结果",
            )
            kw_cn = await keyword_search(db, "二叉搜索树", [kb_a.id], top_k=3)
            c.check(
                "纯中文关键词能命中（PG 内置分词做不到，靠 jieba 这条链）",
                bool(kw_cn) and "二叉搜索树" in kw_cn[0].content,
            )

            # ---------- 6. 混合检索（RRF） ----------
            print("\n=== 6. 混合检索（RRF 融合） ===")
            hy = await hybrid_search(db, QUERY_SEMANTIC, qv, [kb_a.id], top_k=3)
            c.check("混合检索有结果", len(hy) > 0, f"{len(hy)} 条")
            c.check(
                "混合检索仍然命中「二叉搜索树」",
                bool(hy) and "二叉搜索树" in hy[0].content,
                f"融合分={hy[0].score:.6f}" if hy else "无结果",
            )
            hy_kw = await hybrid_search(db, QUERY_KEYWORD, await embed_query(QUERY_KEYWORD), [kb_a.id], top_k=3)
            c.check(
                "混合检索命中 is_public 那块（关键词那一路救回来的）",
                bool(hy_kw) and "is_public" in hy_kw[0].content,
            )
            two_leg = [h for h in hy_kw if h.vector_score is not None and h.keyword_score is not None]
            c.check(
                "RRF 保留了双路命中信息（便于回溯）",
                len(two_leg) > 0 or len(kw_hits) > 0,
                f"双路命中 {len(two_leg)} 条",
            )

            # ---------- 7. 知识库隔离 ----------
            print("\n=== 7. 知识库隔离（legacy 的漏召回点） ===")
            only_b = await hybrid_search(db, "天气 晚餐", await embed_query("天气 晚餐"), [kb_b.id], top_k=5)
            c.check("搜 KB-B 能拿到 KB-B 的块", len(only_b) > 0, f"{len(only_b)} 条")
            c.check(
                "搜 KB-B 不会漏出 KB-A 的块",
                all(h.kb_id == kb_b.id for h in only_b),
                f"kb_id 集合={sorted({h.kb_id for h in only_b})}",
            )
            exact_kb_only = await hybrid_search(db, QUERY_SEMANTIC, qv, [kb_a.id], top_k=3)
            c.check(
                "限定 KB-A 时不会混入 KB-B 的块",
                bool(exact_kb_only) and all(h.kb_id == kb_a.id for h in exact_kb_only),
                f"kb_id 集合={sorted({h.kb_id for h in exact_kb_only})}",
            )
            # legacy 的失败模式：先超取 topK×3 再在内存里按 kb 过滤 ——
            # 当另一个 KB 的向量排在前面时，过滤后相关的块会被**挤掉**。
            # 这里验证：把 KB-B 一起纳入检索，KB-A 的命中依然在。
            with_b = await hybrid_search(db, QUERY_SEMANTIC, qv, [kb_a.id, kb_b.id], top_k=3)
            c.check(
                "多 KB 一起检索时，相关块不会被另一库挤掉（legacy 超取过滤的坑）",
                {h.chunk_id for h in exact_kb_only} <= {h.chunk_id for h in with_b},
                f"单独={sorted(h.chunk_id for h in exact_kb_only)} 合并={sorted(h.chunk_id for h in with_b)}",
            )
            # 换成与 KB-B 相关的查询，KB-B 要能被检索到（证明 kb 过滤没把它误杀）
            qv_b = await embed_query("今天天气 晚餐")
            kb_b_hits = await hybrid_search(db, "今天天气 晚餐", qv_b, [kb_a.id, kb_b.id], top_k=5)
            c.check(
                "换相关查询后 KB-B 能出现在结果里（kb 过滤没有误杀）",
                any(h.kb_id == kb_b.id for h in kb_b_hits),
                f"kb_id 集合={sorted({h.kb_id for h in kb_b_hits})}",
            )
            empty = await hybrid_search(db, "任意", qv, [], top_k=5)
            c.check("kb_ids 为空时返回空（不会退化成检索全库）", empty == [], f"{len(empty)} 条")

            # ---------- 8. 分块器 ----------
            print("\n=== 8. 分块器 ===")
            from app.services.rag.chunker import chunk_text

            def has_overlap(prev: str, nxt: str) -> bool:
                """上一块的尾部（长度 8~100）是否是下一块的开头。"""
                for length in range(min(len(prev), 100), 7, -1):
                    if nxt.startswith(prev[-length:]):
                        return True
                return False

            # 三段各 500 字：两两合并必超 800，必然触发 flush
            # （这条用例锁的是一个真实 bug —— 之前 flush 后直接 continue，
            #   会把触发 flush 的那一段**整个丢掉**，丢的内容永远检索不到）
            text3 = ("A" * 500) + "\n\n" + ("B" * 500) + "\n\n" + ("C" * 500)
            chunks3 = chunk_text(text3)
            joined = "".join(ck.content for ck in chunks3)
            c.check(
                "分块不丢内容（A/B/C 三段都在）",
                all(seg * 50 in joined for seg in ("A", "B", "C")),
                f"{len(chunks3)} 块",
            )
            c.check(
                "普通块之间真的有重叠（legacy 缺这一步）",
                len(chunks3) >= 2 and has_overlap(chunks3[0].content, chunks3[1].content),
                f"块0 尾={chunks3[0].content[-12:]!r} 块1 头={chunks3[1].content[:16]!r}",
            )

            md = "# 标题一\n\n" + ("段落甲。" * 30) + "\n\n# 标题二\n\n" + ("段落乙。" * 30)
            chunks_md = chunk_text(md)
            c.check(
                "标题边界起新块",
                any(ck.content.lstrip().startswith("# 标题二") for ck in chunks_md),
                f"{len(chunks_md)} 块",
            )
            c.check(
                "Markdown 内容不丢",
                "段落甲" in "".join(ck.content for ck in chunks_md)
                and "段落乙" in "".join(ck.content for ck in chunks_md),
            )

            # 超长单段要硬切且带重叠，且同样不能丢
            hard = chunk_text("标" * 2000)
            c.check("超长单段被硬切", len(hard) >= 3, f"{len(hard)} 块")
            c.check(
                "硬切块之间有重叠且无内容丢失",
                has_overlap(hard[0].content, hard[1].content)
                and len("".join(ck.content for ck in hard)) >= 2000,
            )
            over = chunk_text("字" * 60_000)
            c.check(
                "超长内容被截断（不会一次产出天量块）",
                len(over) <= 100,
                f"{len(over)} 块",
            )

            # ---------- 10. 服务层（写入 + 检索 + 越权） ----------
            print("\n=== 10. 服务层 rag_write_service / rag_query_service ===")
            from app.services.rag import rag_query_service, rag_write_service
            from app.services.rag.rag_write_service import RagNotFound

            svc_kb = await rag_write_service.create_knowledge_base(
                db, 1, f"{PREFIX}服务层知识库", description="服务层测试"
            )
            c.check("create_knowledge_base 成功", svc_kb.id > 0, f"kbId={svc_kb.id}")

            try:
                await rag_write_service.create_knowledge_base(db, 1, f"{PREFIX}服务层知识库")
                c.check("同名知识库被拒", False, "竟然创建成功了")
            except rag_write_service.RagConflict as e:
                c.check("同名知识库被拒", True, str(e))

            doc = await rag_write_service.create_document(
                db,
                1,
                svc_kb.id,
                file_name=f"{PREFIX}服务层文档.txt",
                raw_content=KB_A_DOC,
                file_type="txt",
            )
            from app.services.rag.chunker import chunk_text as _ct

            contents = [ck.content for ck in _ct(KB_A_DOC)]
            vecs = await embed_texts(contents)
            n = await rag_write_service.replace_chunks(db, doc, contents, vecs)
            c.check("replace_chunks 写入分块", n == len(contents), f"{n} 块")

            await db.refresh(svc_kb)
            c.check(
                "知识库计数被刷新（重算而非累加）",
                svc_kb.doc_count == 1 and svc_kb.chunk_count == n,
                f"doc={svc_kb.doc_count} chunk={svc_kb.chunk_count}",
            )

            found = await rag_query_service.search(db, 1, "二叉搜索树", [svc_kb.id], top_k=3)
            c.check("服务层检索命中", len(found["hits"]) > 0, f"{len(found['hits'])} 条")
            c.check(
                "命中带出处（legacy 没有 citations）",
                bool(found["hits"]) and found["hits"][0].get("source"),
                found["hits"][0]["source"] if found["hits"] else "",
            )

            # 越权：另一个用户碰不到这个知识库
            try:
                await rag_write_service.get_knowledge_base(db, FAKE_USER_ID, svc_kb.id)
                c.check("别的用户读不到该知识库（越权防护）", False, "竟然读到了")
            except RagNotFound:
                c.check("别的用户读不到该知识库（越权防护）", True)
            try:
                await rag_query_service.search(db, FAKE_USER_ID, "二叉搜索树", [svc_kb.id], top_k=3)
                c.check("别的用户检索该知识库被拒（越权防护）", False, "竟然检索到了")
            except RagNotFound:
                c.check("别的用户检索该知识库被拒（越权防护）", True)
            try:
                await rag_write_service.delete_knowledge_base(db, FAKE_USER_ID, svc_kb.id)
                c.check("别的用户删不掉该知识库（越权防护）", False, "竟然删掉了")
            except RagNotFound:
                c.check("别的用户删不掉该知识库（越权防护）", True)

            # 空 kb 的边界：`kb_ids` 省略/为空 = 检索该用户**全部**知识库（比 legacy
            # 「必须绑定单个 kb 否则报未绑定」可用）。真正「没有可检索的知识库」是指
            # 该用户一个知识库都没有 —— 用不存在的用户来验。
            c.check(
                "kb_ids 为空 = 检索该用户全部知识库（不是报错）",
                len((await rag_query_service.search(db, 1, "二叉搜索树", [], top_k=3)).get("hits", [])) > 0,
            )
            c.check(
                "该用户没有任何知识库时才返回「没有可检索的知识库」",
                (await rag_query_service.search(db, FAKE_USER_ID, "任意", [], top_k=3)).get("reason")
                == "没有可检索的知识库",
            )

            # ---------- 11. RAG 问答（真实调用模型） ----------
            print("\n=== 11. RAG 问答（真实 LLM） ===")
            ans = await rag_query_service.answer(db, 1, "二叉搜索树的时间复杂度是多少", [svc_kb.id])
            c.check("问答返回了答案", bool(ans.get("answer")), (ans.get("answer") or "")[:70])
            c.check("问答带 citations", len(ans.get("citations", [])) > 0, f"{len(ans.get('citations', []))} 条")
            c.check("found=True（确实检索到了）", ans.get("found") is True)
            c.check(
                "切题问题不是低置信（关键词路有命中）",
                ans.get("lowConfidence") is False,
            )

            # 跑题问题：BGE 的「相似度地板」会让它照样检索到片段（实测无关查询 top1=0.62），
            # 所以这里验证的是「模型会明确说没找到」+「被标为低置信」，
            # 而不是假装阈值能把它拦掉（见 hybrid_search.DEFAULT_MIN_SIMILARITY 的实测数据）。
            miss = await rag_query_service.answer(
                db, 1, "量子纠缠和薛定谔猫到底是什么关系", [svc_kb.id]
            )
            c.check(
                "跑题问题不会被硬答（模型明确说没找到）",
                "没有找到" in (miss.get("answer") or ""),
                (miss.get("answer") or "")[:60],
            )
            c.check(
                "跑题问题被标为低置信（关键词那一路零命中）",
                miss.get("lowConfidence") is True,
            )

            # 真正的确定性兜底：知识库里根本没有可检索内容 → 不调模型、不编答案
            empty_kb = await rag_write_service.create_knowledge_base(db, 1, f"{PREFIX}空知识库")
            miss2 = await rag_query_service.answer(db, 1, "随便问点什么", [empty_kb.id])
            c.check(
                "知识库为空时走确定性兜底（不调模型、返回固定话术）",
                miss2.get("found") is False
                and miss2.get("answer") == rag_query_service.NO_HIT_ANSWER,
                (miss2.get("answer") or "")[:50],
            )
            await rag_write_service.delete_knowledge_base(db, 1, empty_kb.id)

            # 问答记录落库（legacy 的问答流程根本不写 rag_qa_record）
            qa_count = (
                await db.execute(
                    select(func.count()).select_from(RagQaRecord).where(RagQaRecord.user_id == 1)
                )
            ).scalar() or 0
            c.check("问答记录写入 rag_qa_record（legacy 不写这张表）", qa_count >= 2, f"{qa_count} 条")

            # ---------- 12. 级联删除 ----------
            print("\n=== 12. 级联删除 ===")
            del_info = await rag_write_service.delete_knowledge_base(db, 1, svc_kb.id)
            c.check(
                "删除知识库连带清掉文档与分块",
                del_info["documents"] >= 1 and del_info["chunks"] >= 1,
                f"doc={del_info['documents']} chunk={del_info['chunks']}",
            )
            leftover = (
                await db.execute(
                    select(func.count())
                    .select_from(RagDocumentChunk)
                    .where(RagDocumentChunk.kb_id == svc_kb.id)
                )
            ).scalar() or 0
            c.check("分块被物理清干净（不留可能被检索到的残骸）", leftover == 0, f"{leftover} 块")

            # ---------- 13. PG 专有：写库前一律 sanitize_text ----------
            # 审计发现三处写库点漏清 NUL（知识库改名 / 问答记录 / 记忆正文）——
            # JSON 能编码 NUL，PG 的 text 列拒收 0x00，写入直接 500。
            print("\n=== 13. NUL 清理（PG 拒收 0x00；MySQL 会静默存下来） ===")
            from app.services.ai import memory_service
            from app.services.rag.rag_write_service import sanitize_text

            c.check(
                "sanitize_text 只清 NUL（不做 trim / 不替换空白）",
                sanitize_text("  a\u0000b\tc  ") == "  ab\tc  ",
                repr(sanitize_text("  a\u0000b\tc  ")),
            )

            # 记忆正文（save_memory）
            baseline_mem = (
                await db.execute(
                    select(func.count())
                    .select_from(AiAgentMemory)
                    .where(AiAgentMemory.user_id == 1)
                )
            ).scalar() or 0
            mem_ok, mem_id, mem_content, mem_err = False, 0, "", ""
            try:
                mem = await memory_service.save_memory(
                    db, 1, "记忆正文\u0000带空字节", memory_type="episodic"
                )
                mem_ok, mem_id, mem_content = True, mem.id, mem.content or ""
            except Exception as e:  # 红态是 PG 报 CharacterNotInRepertoireError
                mem_err = f"{type(e).__name__}: {str(e)[:60]}"
                await db.rollback()
            c.check("记忆正文带 NUL 能写入（不再 500）", mem_ok, mem_err)
            c.check(
                "入库的记忆正文里没有 NUL",
                mem_ok and "\x00" not in mem_content,
                repr(mem_content)[:50],
            )

            # 先清再裁：把 NUL 放在 `_clip` 会**保留**的前缀里 ——
            # 若先裁后清（或压根不清），它就会被原样写进库、PG 直接拒收。
            long_ok, long_id, long_content, long_err = False, 0, "", ""
            try:
                long_mem = await memory_service.save_memory(
                    db,
                    1,
                    ("字" * 100) + "\u0000" + ("字" * 500),  # 601 字，必触发 _clip
                    memory_type="episodic",
                )
                long_ok, long_id, long_content = True, long_mem.id, long_mem.content or ""
            except Exception as e:
                long_err = f"{type(e).__name__}: {str(e)[:60]}"
                await db.rollback()
            c.check(
                "超长记忆：NUL 落在被裁剪保留的前缀里也不漏过（先清后裁）",
                long_ok
                and "\x00" not in long_content
                and len(long_content) <= MEMORY_CONTENT_MAX,
                long_err or f"len={len(long_content)}",
            )

            # 只删自己造的那两条（**绝不用 clear_memories**）
            # ⚠️ 2026-09-22 起 `memory_service.delete_memory` 是**逻辑删**
            #    （撤销需求：用户删掉的记忆要能在「最近删除」里恢复），所以这里换成
            #    裸 SQL **物理删** —— 这是「清掉测试自己造的行」，留 `del_flag='2'` 的
            #    残骸会让下面「真实用户记忆条数不变」永远为假（残骸把计数顶上去）。
            #    删的范围一字不差：就是本用例自己拿到的那两个 id。
            for rid in (mem_id, long_id):
                if rid:
                    await db.execute(
                        text("DELETE FROM ai_agent_memory WHERE id = :i"), {"i": rid}
                    )
            await db.commit()
            after_mem = (
                await db.execute(
                    select(func.count())
                    .select_from(AiAgentMemory)
                    .where(AiAgentMemory.user_id == 1)
                )
            ).scalar() or 0
            c.check(
                "只删本用例造的 2 条，真实用户记忆条数不变",
                after_mem == baseline_mem,
                f"{baseline_mem} -> {after_mem}",
            )

            # 问答记录（rag_query_service.answer → rag_qa_record.question / answer）
            nul_kb = await rag_write_service.create_knowledge_base(db, 1, f"{PREFIX}NUL库")
            # ⚠️ 先把 id 取出来：下面失败分支会 `db.rollback()`，那会把实例标记为 expired，
            #    之后再读 `nul_kb.id` 会触发同步懒加载 → MissingGreenlet（只在缺陷态出现）
            nul_kb_id = nul_kb.id
            ask_ok, ask_err = False, ""
            try:
                await rag_query_service.answer(db, 1, "死锁\u0000的必要条件", [nul_kb_id])
                ask_ok = True
            except Exception as e:
                ask_err = f"{type(e).__name__}: {str(e)[:60]}"
                await db.rollback()
            c.check("问答 query 带 NUL 不报错（不再 500）", ask_ok, ask_err)
            q_rows = (
                await db.execute(
                    select(RagQaRecord.question).where(RagQaRecord.kb_id == nul_kb_id)
                )
            ).scalars().all()
            c.check(
                "落库的 question 已无 NUL",
                len(q_rows) >= 1 and all("\x00" not in (q or "") for q in q_rows),
                f"{len(q_rows)} 条: {[(q or '')[:14] for q in q_rows]}",
            )

            # get_document 必须校验所属知识库的 del_flag
            gone_kb = await rag_write_service.create_knowledge_base(db, 1, f"{PREFIX}待逻辑删库")
            gone_doc = await rag_write_service.create_document(
                db,
                1,
                gone_kb.id,
                file_name=f"{PREFIX}gone.txt",
                raw_content="残留正文",
                file_type="txt",
            )
            gone_doc_id = gone_doc.id
            await db.execute(
                text("UPDATE rag_knowledge_base SET del_flag = '2' WHERE id = :i"),
                {"i": gone_kb.id},
            )
            await db.commit()
            try:
                await rag_write_service.get_document(db, 1, gone_doc_id)
                c.check(
                    "已逻辑删知识库的文档取不到（get_document 校验 del_flag）",
                    False,
                    "竟然取到了残留文档",
                )
            except RagNotFound:
                c.check("已逻辑删知识库的文档取不到（get_document 校验 del_flag）", True)

        except Exception as e:
            c.failed += 1
            print(f"\n  [ERROR] 测试过程中抛异常: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("\n=== 9. 清理测试数据 ===")
            try:
                # 前面若在 flush 阶段抛异常，会话处于「需 rollback」状态，
                # 不先回滚的话清理语句本身也会失败，留下脏数据。
                await db.rollback()
                await _cleanup(db)
            except Exception as e:
                print(f"  [WARN] 清理失败（需手工检查）: {e}")

    await engine.dispose()

    print(f"\n{'='*56}\n结果：{c.passed} 通过 / {c.failed} 失败")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
