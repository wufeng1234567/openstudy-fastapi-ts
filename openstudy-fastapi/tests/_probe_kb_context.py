# -*- coding: utf-8 -*-
"""A2 隔离探针：`_retrieve_kb_context` 取材逻辑（mock 检索，不依赖 embedding/LLM）

为什么 mock：本地 embedding 后端（SiliconFlow key）已失效、且未装本地模型，
真实检索跑不通；但**取材这段逻辑**（拼材料、带出处、预算封顶、失败不抛）
是可以脱离外部服务精确验证的。

覆盖：
  1. 命中 → 拼出「【材料i｜来源：…】」且带正文
  2. kb_ids 为空 / query 为空 → 返回 ""（不检索）
  3. 检索抛异常 → 返回 ""（失败不抛，降级为纯生成）
  4. 单段超长 → 被截断
  5. 总量超预算 → 提前截断

用法：
    .venv/Scripts/python.exe tests/_probe_kb_context.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

CHECKS = []


def ck(cid, title, cond, actual=""):
    CHECKS.append((cid, title, cond, actual))
    print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))


async def main():
    from app.database import async_session_factory
    from app.services.ai import chat_engine
    from app.services.rag import rag_query_service as rqs

    original = rqs.search

    async def fake_search(db, user_id, query, kb_ids=None, top_k=5):
        return {
            "query": query,
            "hits": [
                {
                    "chunkId": 1, "docId": 9, "kbId": (kb_ids or [1])[0],
                    "docName": "数据结构.pdf", "chunkIndex": 2,
                    "content": "红黑树的五条性质：根黑、叶黑、红子必黑、黑高相同…",
                    "source": "数据结构.pdf 第 3 段",
                    "score": 0.5, "vectorScore": 0.7, "keywordScore": 1.2,
                },
                {
                    "chunkId": 2, "docId": 9, "kbId": (kb_ids or [1])[0],
                    "docName": "数据结构.pdf", "chunkIndex": 3,
                    "content": "性质5：从任一结点到叶子的路径黑色结点数相同。",
                    "source": "数据结构.pdf 第 4 段",
                    "score": 0.4, "vectorScore": 0.6, "keywordScore": None,
                },
            ],
            "knowledgeBases": [{"kbId": (kb_ids or [1])[0], "name": "教材库"}],
        }

    async with async_session_factory() as db:
        # 1. 命中 → 拼材料
        rqs.search = fake_search
        turn = chat_engine.ChatTurn(scene="question-generate", kb_ids=[1], user_id=1)
        ctx = await chat_engine._retrieve_kb_context(db, turn, "红黑树性质")
        ck("KBC-01", "命中时拼出材料块（含『来源：』）", "来源：数据结构.pdf 第 3 段" in ctx, ctx[:120])
        ck("KBC-02", "命中时带上原文正文", "红黑树的五条性质" in ctx, "")
        ck("KBC-03", "多段命中都在（材料1/材料2）", "【材料1" in ctx and "【材料2" in ctx, ctx[:80])

        # 2. 空 kb_ids / 空 query → 不检索
        t2 = chat_engine.ChatTurn(scene="question-generate", kb_ids=[], user_id=1)
        ck("KBC-04", "kb_ids 为空 → 返回空（不检索）", await chat_engine._retrieve_kb_context(db, t2, "x") == "", "")

        t3 = chat_engine.ChatTurn(scene="question-generate", kb_ids=[1], user_id=1)
        ck("KBC-05", "query 为空 → 返回空", await chat_engine._retrieve_kb_context(db, t3, "  ") == "", "")

        # 3. 检索抛异常 → 返回空（不抛）
        async def boom(*a, **k):
            raise RuntimeError("embedding down")

        rqs.search = boom
        raised = False
        out = ""
        try:
            out = await chat_engine._retrieve_kb_context(db, t3, "红黑树")
        except Exception:
            raised = True
        ck("KBC-06", "检索失败时不抛异常", not raised, "")
        ck("KBC-07", "检索失败时返回空（降级为纯生成）", out == "", out[:60])

        # 4. 单段超长 → 截断
        async def long_search(db, user_id, query, kb_ids=None, top_k=5):
            return {"hits": [{
                "chunkId": 1, "docId": 1, "kbId": 1, "docName": "a.pdf", "chunkIndex": 0,
                "content": "字" * 5000, "source": "a.pdf 第 1 段",
            }], "knowledgeBases": []}

        rqs.search = long_search
        ctx = await chat_engine._retrieve_kb_context(db, t3, "q")
        ck("KBC-08", "单段超长被截断（< 单段上限+余量）",
           len(ctx) < chat_engine.KB_CONTEXT_CHUNK_CHARS + 80, f"len={len(ctx)}")

        # 5. 总量超预算 → 提前截断
        async def many_search(db, user_id, query, kb_ids=None, top_k=5):
            return {"hits": [{
                "chunkId": i, "docId": 1, "kbId": 1, "docName": "a.pdf", "chunkIndex": i,
                "content": "字" * 1000, "source": f"a.pdf 第 {i} 段",
            } for i in range(20)], "knowledgeBases": []}

        rqs.search = many_search
        ctx = await chat_engine._retrieve_kb_context(db, t3, "q")
        ck("KBC-09", "总量超预算时提前截断（<= 总预算+单段余量）",
           len(ctx) <= chat_engine.KB_CONTEXT_MAX_CHARS + chat_engine.KB_CONTEXT_CHUNK_CHARS,
           f"len={len(ctx)}")

    rqs.search = original

    red = [c for c in CHECKS if not c[2]]
    print(f"\n共 {len(CHECKS)} 项：{len(CHECKS) - len(red)} 通过；红的 = {[c[0] for c in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
