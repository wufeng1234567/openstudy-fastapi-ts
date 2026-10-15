# -*- coding: utf-8 -*-
"""零成本跑手：把 `tests/e2e_agent_api.py` 里的 M 组（知识库屏蔽闸门）**原样**跑一遍。

⚠️ 这个文件是**刻意保留**的工具（不是跑完就删的临时脚本）：M 组住在整套 e2e 里，
而整套跑会真调 embedding（花钱、需放行），于是「屏蔽闸门」这个能力在成本闸门下会
**没有可复现的验证手段**。本脚本补上那一段：把 M 组源码按标记行切出来**原样 exec**
（不是复制一份改过的断言 —— 那测的就是副本了），只补它需要的最小上下文：
in-process HTTP 夹（ASGITransport）+ 假登录。

零成本：M 组刻意不传文档、不传 query，不会走到 `embed_query`。

用法
----
    .venv/Scripts/python.exe tests/_kbdisable_probe.py            # 正常跑（应当全绿，退出码 0）
    .venv/Scripts/python.exe tests/_kbdisable_probe.py --mutate   # 变异跑（应当红，退出码 1）

`--mutate` 会把 `rag_write_service.py` 里闸门的三处过滤拆掉（= 改动之前的行为），跑完
**在 finally 里整份写回**并打 md5 前后比对；这是「用例在修复前必须是红的」那条纪律的证据。
（变异锚点每个都必须**唯一命中**，命中数不是 1 就直接 assert 失败 —— 锚点漂了就说明
 变异没落在你以为的地方。）
"""
import asyncio
import hashlib
import os
import sys
import textwrap
import time
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

SUITE = os.path.join(ROOT, "tests", "e2e_agent_api.py")
RWS = os.path.join(ROOT, "app", "services", "rag", "rag_write_service.py")

M_START = "# ================= M. 知识库屏蔽闸门"
M_END = "# ================= L. "

#: 变异：把闸门拆掉（旧行为）。三处锚点必须**各命中一次**。
MUTATIONS = (
    ("默认分支的 SQL 过滤", "RagKnowledgeBase.disabled == 0,", "# MUTATED: 闸门拆掉"),
    ("list 的 include_disabled 过滤",
     "stmt = stmt.where(RagKnowledgeBase.disabled == 0)", "pass  # MUTATED"),
    ("显式分支的静默丢弃", "        if kb.disabled:", "        if False:  # MUTATED"),
)


def extract_m_block() -> str:
    with open(SUITE, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if M_START in ln)
    end = next(i for i, ln in enumerate(lines) if i > start and M_END in ln)
    return textwrap.dedent("\n".join(lines[start:end]))


async def run_probe() -> int:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    import e2e_agent_api as suite  # 复用套件的 T()/ROWS/PREFIX（模块级无副作用）
    from app.core.security import get_current_user
    from app.database import async_session_factory, engine
    from app.main import app

    async with async_session_factory() as db:
        uid = int(
            await db.scalar(text("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1")) or 0
        )
    if not uid:
        print("库里没有用户，跑不了")
        return 2

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": uid,
        "userName": "kb-disable-probe",
    }
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://probe", timeout=60)
    client.headers.update({"Content-Type": "application/json"})

    async def execute(tool, params, confirmed=True, auto_confirm=True):
        r = await client.post(
            "/ai/agent/execute",
            json={
                "tool": tool,
                "params": params,
                "userId": uid,
                "autoConfirm": auto_confirm,
                "confirmed": confirmed,
            },
        )
        return r.json() or {}

    before = len(suite.ROWS)
    ns = {
        "client": client,
        "execute": execute,
        "uid": uid,
        "text": text,
        "re": re,
        "time": time,
        "async_session_factory": async_session_factory,
        "T": suite.T,
        "PREFIX": suite.PREFIX,
        "_RAG_FIXTURE_KB_IDS": suite._RAG_FIXTURE_KB_IDS,
    }
    body = textwrap.indent(extract_m_block(), "    ")
    exec(compile("async def __m__():\n" + body + "\n", "<M-block>", "exec"), ns)
    try:
        await ns["__m__"]()
    finally:
        # 安全网：万一 M 组自己在删之前就炸了，按**精确前缀**清掉本探针造的夹具
        # （前缀里的 `_` 在 LIKE 里是通配符 —— 所以用 LEFT(...)=...，不用 LIKE）
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM rag_knowledge_base WHERE "
                        "LEFT(COALESCE(name, ''), LENGTH(:p)) = :p"
                    ),
                    {"p": f"{suite.PREFIX}M组"},
                )
            ).all()
            for (kid,) in rows:
                for stmt in (
                    "DELETE FROM rag_qa_record WHERE kb_id = :k",
                    "DELETE FROM rag_document_chunk WHERE kb_id = :k",
                    "DELETE FROM rag_document WHERE kb_id = :k",
                    "DELETE FROM rag_knowledge_base WHERE id = :k",
                ):
                    await db.execute(text(stmt), {"k": kid})
            if rows:
                print(f"  [探针安全网] 清掉残留夹具 {len(rows)} 个：{[r[0] for r in rows]}")
            await db.commit()

    rows = suite.ROWS[before:]
    print("\n---- M 组结果 ----")
    for r in rows:
        print(f"  [{r['status']}] {r['cid']} {r['title']}\n        实际: {r['actual']}")
    red = [r for r in rows if r["status"] != "通过"]
    print(f"\nM 组：{len(rows) - len(red)}/{len(rows)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    await client.aclose()
    await engine.dispose()
    return 1 if red else 0


def main() -> int:
    mutate = "--mutate" in sys.argv
    with open(RWS, "rb") as f:
        orig = f.read()
    md5_before = hashlib.md5(orig).hexdigest()
    print(f"[md5] rag_write_service.py 跑前 = {md5_before}")

    if mutate:
        src = orig.decode("utf-8")
        for label, old, new in MUTATIONS:
            hits = src.count(old)
            assert hits == 1, f"变异锚点不唯一：{label} 命中 {hits} 次（锚点漂了）"
            src = src.replace(old, new)
            print(f"[mutate] {label}: 锚点命中 1 次 → 已替换")
        with open(RWS, "wb") as f:
            f.write(src.encode("utf-8"))
        print(f"[mutate] 已写入变异版（{len(src.encode('utf-8'))} bytes）")
        time.sleep(2)  # 让 9101 的 --reload 把变异版加载进去（探针本身是 import 现成的）

    try:
        return asyncio.run(run_probe())
    finally:
        if mutate:
            with open(RWS, "wb") as f:
                f.write(orig)
            back = hashlib.md5(open(RWS, "rb").read()).hexdigest()
            print(f"[md5] 还原后 = {back} / 与跑前一致 = {back == md5_before}")


if __name__ == "__main__":
    raise SystemExit(main())
