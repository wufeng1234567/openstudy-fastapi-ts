# -*- coding: utf-8 -*-
"""一次性探针：Agent 工具「按主键 id」的越权闸门（跑完即删）

为什么单独写一个：`tests/e2e_agent_api.py` 是「一次跑全部组」的套件（没有分组参数），
跑一次几分钟、还要打真模型。这个探针**只在进程内**调工具层 —— 不走 HTTP、不碰 LLM，
几十秒就能给出「别人的 id 被拒 / 自己的 id 照常」的红绿，用来做变异对照。

用法（必须用 .venv 的 python）：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_probe_idor_scope.py

退出码：0 = 全部符合预期；1 = 有红 / 环境不足（库里只有一个用户 = **没测到**，也回 1）。

⚠️ 夹具规则（本仓库出过「测试清理删光真实数据」的事故）：
   · 自造数据一律带 `__probe_idor_scope__` 标记，且归属**两个不同的真实用户**；
   · 收尾只按**本探针登记的精确 id**物理删，绝不按无标记条件删、更不整表清；
   · 删完数一次标记前缀残留，作为最后一条断言。
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

# ⚠️ 必须先 `import app.main`：只 import 工具模块的话，SQLAlchemy 的 mapper 配置会在
#    第一次查询时炸（`SysUser.roles → SysRole` 那个关系解析不到 `SysRole`）——
#    模型是靠 app.main 的导入链注册全的（与 `tests/e2e_agent_api.py` 同一手法）。
from app.main import app as _app  # noqa: E402,F401

from app.database import async_session_factory  # noqa: E402
from app.services.ai.agent.base import ToolContext  # noqa: E402
from app.services.ai.agent.tools.bank_manage import BankManageTool  # noqa: E402
from app.services.ai.agent.tools.question_manage import QuestionManageTool  # noqa: E402

MARK = "__probe_idor_scope__"
BANK_OTHER = MARK + "他人库"
BANK_MINE = MARK + "自己库"
Q_OTHER = MARK + "他人题干"
Q_MINE = MARK + "自己题干"

RESULTS = []


def check(cid, desc, ok, detail):
    RESULTS.append((cid, desc, bool(ok), detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {cid} {desc}")
    print(f"         {detail}")


async def main():
    async with async_session_factory() as db:
        attacker = int(await db.scalar(
            text("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1")) or 0)
        victim = int(await db.scalar(
            text("SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1"),
            {"u": attacker}) or 0)
    if not attacker or not victim:
        print(f"!! 库里只有一个用户（attacker={attacker} victim={victim}）→ 本探针**没测到东西**，回 1")
        return 1
    print(f"attacker（登录态）= {attacker}   victim（别人）= {victim}\n")

    other_bank = other_q = mine_bank = mine_q = 0
    try:
        # ---------------- 造夹具 ----------------
        async with async_session_factory() as cdb:
            for name, owner in ((BANK_OTHER, victim), (BANK_MINE, attacker)):
                await cdb.execute(text(
                    "INSERT INTO question_bank (bank_name, subject, description, "
                    "total_questions, status, user_id, is_public) "
                    "VALUES (:n, :s, :d, 1, '0', :u, 0)"
                ), {"n": name, "s": "探针夹具", "d": MARK, "u": owner})
            await cdb.commit()
            for name, owner, tag in ((BANK_OTHER, victim, "other"), (BANK_MINE, attacker, "mine")):
                bid = int(await cdb.scalar(text(
                    "SELECT id FROM question_bank WHERE bank_name = :n AND user_id = :u "
                    "ORDER BY id DESC LIMIT 1"
                ), {"n": name, "u": owner}) or 0)
                qtext = Q_OTHER if tag == "other" else Q_MINE
                await cdb.execute(text(
                    "INSERT INTO question_main (bank_id, question_type, difficulty, "
                    "question_text, answer, has_sub_questions, sort_order, score, status) "
                    "VALUES (:b, 1, 1, :t, '0', 0, 1, 0, '0')"
                ), {"b": bid, "t": qtext})
                await cdb.commit()
                qid = int(await cdb.scalar(text(
                    "SELECT id FROM question_main WHERE bank_id = :b AND question_text = :t "
                    "ORDER BY id DESC LIMIT 1"
                ), {"b": bid, "t": qtext}) or 0)
                if tag == "other":
                    other_bank, other_q = bid, qid
                else:
                    mine_bank, mine_q = bid, qid
        print(f"夹具：他人 bank={other_bank} q={other_q} / 自己 bank={mine_bank} q={mine_q}\n")

        qt = QuestionManageTool()
        bt = BankManageTool()

        async def _run(tool, params):
            """一次调用一个**独立会话**，并**提交** —— 否则被拦下的写动作看不到副作用，
            断言会变成「结构上对、实际恒真」（变异也红不了）。"""
            async with async_session_factory() as s:
                ctx = ToolContext(db=s, user_id=attacker, session_id="probe-idor")
                out = await tool.execute(dict(params), ctx)
                await s.commit()
                return out

        async def q(params):
            return await _run(qt, params)

        async def b(params):
            return await _run(bt, params)

        async def count_q(bank_id):
            async with async_session_factory() as s:
                return int(await s.scalar(text(
                    "SELECT count(*) FROM question_main WHERE bank_id = :b"), {"b": bank_id}) or 0)

        def dump(x):
            return json.dumps(x, ensure_ascii=False)

        # X1 question_manage.list 拿别人的 bank_id
        r = await q({"action": "list", "bank_id": other_bank})
        check("X1", "question_manage.list(bank_id=别人的) → 被拒且不泄漏库名/题干",
              r.get("success") is False and BANK_OTHER not in dump(r) and Q_OTHER not in dump(r),
              f"success={r.get('success')} error={str(r.get('error'))[:46]!r} "
              f"泄漏库名={BANK_OTHER in dump(r)} 泄漏题干={Q_OTHER in dump(r)}")

        # X2 按题号 detail（question_index 也走同一份解析）
        r = await q({"action": "detail", "bank_id": other_bank, "question_index": 1})
        check("X2", "question_manage.detail(bank_id=别人的, question_index=1) → 被拒且不泄漏",
              r.get("success") is False and BANK_OTHER not in dump(r) and Q_OTHER not in dump(r),
              f"success={r.get('success')} error={str(r.get('error'))[:46]!r} "
              f"泄漏题干={Q_OTHER in dump(r)}")

        # X3 clear_questions（批量物理删）别人的库 —— 侧重点在「有副作用吗」
        before = await count_q(other_bank)
        r = await q({"action": "clear_questions", "bank_id": other_bank})
        after = await count_q(other_bank)
        check("X3", "question_manage.clear_questions(bank_id=别人的) → 被拒且一道没少",
              before > 0 and after == before and r.get("success") is False,
              f"题数 before={before} after={after} success={r.get('success')} "
              f"error={str(r.get('error'))[:46]!r}")

        # X4 别人的 question_id 直查
        r = await q({"action": "detail", "question_id": other_q})
        check("X4", "question_manage.detail(question_id=别人的) → 被拒且不泄漏题干",
              r.get("success") is False and Q_OTHER not in dump(r),
              f"success={r.get('success')} error={str(r.get('error'))[:46]!r} "
              f"泄漏题干={Q_OTHER in dump(r)}")

        # X5 bank_manage.detail 别人的 bank_id（另一份实现）
        r = await b({"action": "detail", "bank_id": other_bank})
        check("X5", "bank_manage.detail(bank_id=别人的) → 被拒且不泄漏题库名",
              r.get("success") is False and BANK_OTHER not in dump(r),
              f"success={r.get('success')} error={str(r.get('error'))[:46]!r} "
              f"泄漏库名={BANK_OTHER in dump(r)}")

        # X6 存在性预言机：「不存在的 id」与「别人的 id」必须回**同一句**话
        #    （否则拿一串 id 试一遍就能数出别人有多少题库）
        r_ghost = await q({"action": "list", "bank_id": 999999999})
        r_other = await q({"action": "list", "bank_id": other_bank})
        head = lambda x: str(x.get("error") or "").split("：")[0]
        check("X6", "「不存在」与「不是你的」回同一句（不给出存在性预言机）",
              bool(r_ghost.get("error")) and head(r_ghost) == head(r_other),
              f"不存在的 id → {head(r_ghost)!r}；别人的 id → {head(r_other)!r}")

        # X7 预览（确认卡片）不许泄漏别人的题库名 —— 这是**另一份**实现（_preview_bank）
        async with async_session_factory() as s:
            pv = await qt.preview(
                {"action": "clear_questions", "bank_id": other_bank},
                ToolContext(db=s, user_id=attacker, session_id="probe-idor"))
        check("X7", "预览 clear_questions(bank_id=别人的) → 不给别人的题库名",
              BANK_OTHER not in dump(pv),
              f"preview={dump(pv)[:100]}")

        # X8 正向对照：自己的 id 照常可用（证明上面的拒绝不是一刀切）
        r1 = await q({"action": "list", "bank_id": mine_bank})
        r2 = await q({"action": "detail", "question_id": mine_q})
        check("X8", "对照：自己的 bank_id / question_id 仍然读得到",
              r1.get("success") is True and r2.get("success") is True
              and Q_MINE in dump(r2),
              f"list.success={r1.get('success')} detail.success={r2.get('success')} "
              f"回读到自己题干={Q_MINE in dump(r2)}")
    finally:
        # ---------------- 精确物理删（子 → 父）+ 数残留 ----------------
        async with async_session_factory() as cdb:
            for bid in (other_bank, mine_bank):
                if bid:
                    await cdb.execute(text(
                        "DELETE FROM question_main WHERE bank_id = :b"), {"b": bid})
                    await cdb.execute(text(
                        "DELETE FROM question_bank WHERE id = :b"), {"b": bid})
            await cdb.commit()
        async with async_session_factory() as cdb:
            left = int(await cdb.scalar(text(
                "SELECT count(*) FROM question_bank "
                "WHERE LEFT(COALESCE(bank_name, ''), LENGTH(:p)) = :p"), {"p": MARK}) or 0)
        check("X9", "夹具残留 0（只按本探针登记的 id 删）", left == 0, f"残留={left}")

    bad = [r for r in RESULTS if not r[2]]
    print(f"\n结果：{len(RESULTS) - len(bad)}/{len(RESULTS)} 通过"
          + ("" if not bad else f"；红：{', '.join(r[0] for r in bad)}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
