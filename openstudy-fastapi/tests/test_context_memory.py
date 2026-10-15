"""
历史上下文系统测试（短期预算 + 长期记忆）

覆盖：
  1. 短期上下文：按字符预算截断（保留最近的、min_keep 兜底、单条防吃满预算）
  2. 记忆写入 / 检索 / 归属隔离
  3. **淘汰按类型分别限额** —— 锁住 legacy 的 bug（它按 importance 全局淘汰，
     conversation(6) 会被 episodic(7/8) 挤掉，对话脉络反而先丢）
  4. **关键词检索转义 LIKE 通配符** —— 搜 `a_b` 不该匹配 `axb`
  5. `build_memory_context` 渲染（Agent 用英文标签）
  6. `memory_hook` 行为：读操作不记、失败不记、异常不抛

⚠️ 淘汰测试**必须用一个零记忆的用户**，否则会把真实用户的记忆删掉。
   真实用户的记忆（user 1）是只读样本、不能被当夹具，所以这里挑一个 0 条记忆的用户，
   跑完把它清回 0（恢复原状），并**断言**全表记忆总数回到跑之前的基线
   （别把条数写死 —— 库里本来就有别人留下的行，写死必然假红）。

用法：
    ./.venv/Scripts/python.exe tests/test_context_memory.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

logger.remove()

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.database import engine, register_all_models  # noqa: E402
from app.models.agent_memory import (  # noqa: E402
    MAX_PER_TYPE,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_EPISODIC,
    AiAgentMemory,
)
from app.services.ai import memory_service  # noqa: E402
from app.services.ai.conversation_service import (  # noqa: E402
    CONTEXT_BUDGET_CHARS,
    CONTEXT_MIN_KEEP,
    CONTEXT_SINGLE_MAX_CHARS,
    _clip_single,
    trim_history_by_budget,
)


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


def _mk_history(n: int, size: int) -> list[dict]:
    return [
        {"role": "assistant" if i % 2 else "user", "content": f"m{i}-" + "字" * size}
        for i in range(n)
    ]


def test_short_term_budget(c: Checker) -> None:
    """短期上下文预算（纯函数，不需要 DB）。"""
    print("\n=== 1. 短期上下文：字符预算 ===")

    short = _mk_history(30, 10)
    kept = trim_history_by_budget(short, max_chars=CONTEXT_BUDGET_CHARS)
    c.check("预算内的短消息全部保留", len(kept) == 30, f"{len(kept)}/30 条")

    long_ = _mk_history(30, 500)
    kept = trim_history_by_budget(long_, max_chars=3000)
    first = kept[0]["content"].split("-")[0]
    last = kept[-1]["content"].split("-")[0]
    c.check("超预算时截断", len(kept) < 30, f"{len(kept)}/30 条")
    c.check(
        "截断的是**最早的**，保留的是最近的",
        last == "m29" and first != "m0",
        f"首={first} 末={last}",
    )
    c.check(
        "返回仍是时间正序",
        [m["content"][:2] for m in kept] == sorted(m["content"][:2] for m in kept),
    )

    huge = _mk_history(5, 10000)
    kept = trim_history_by_budget(huge, max_chars=100, min_keep=CONTEXT_MIN_KEEP)
    c.check(
        "一条超长消息不会把历史挤空（min_keep 兜底）",
        len(kept) == CONTEXT_MIN_KEEP,
        f"{len(kept)} 条（min_keep={CONTEXT_MIN_KEEP}）",
    )

    t = "A" * 2000 + "B" * 2000
    clipped = _clip_single(t, 100)
    c.check(
        "单条截断保留首尾（结论常在末尾）",
        len(clipped) < 200 and clipped.startswith("A") and clipped.endswith("B"),
        f"len={len(clipped)}",
    )
    c.check(
        "短文本不被截断",
        _clip_single("短句", 100) == "短句",
    )
    c.check(
        "空历史返回空",
        trim_history_by_budget([], max_chars=100) == [],
    )


async def _pick_memory_free_user(db, c: Checker) -> int | None:
    """挑一个**没有任何记忆**的真实用户，避免淘汰测试误删真实数据。"""
    rows = (
        await db.execute(
            text(
                "SELECT u.user_id FROM sys_user u "
                "LEFT JOIN (SELECT user_id, count(*) c FROM ai_agent_memory GROUP BY user_id) m "
                "  ON u.user_id = m.user_id "
                "WHERE COALESCE(m.c, 0) = 0 ORDER BY u.user_id"
            )
        )
    ).all()
    if not rows:
        c.check("找到零记忆用户用于淘汰测试", False, "没有零记忆用户，跳过淘汰测试")
        return None
    uid = int(rows[0][0])
    c.check("找到零记忆用户用于淘汰测试", True, f"uid={uid}")
    return uid


async def run() -> int:
    register_all_models()
    c = Checker()
    from app.database import IS_POSTGRES

    factory = async_sessionmaker(engine, expire_on_commit=False)

    test_uid: int | None = None
    original_caps = dict(MAX_PER_TYPE)
    #: 跑之前的全表记忆总数。**基线必须现场采**，不写死数字：库里本来就有别人留下的行，
    #: 写死只会假红。收尾断言就比它（见 finally）。
    before_total: int | None = None

    async with factory() as db:
        try:
            # ---------- 0. 目标库 ----------
            print("\n=== 0. 目标库确认 ===")
            info = (await db.execute(text("SELECT current_database()"))).first()
            c.check("连的是 openstudy_v2_pgsql", info and info[0] == "openstudy_v2_pgsql", info[0] if info else "")
            c.check("是 PostgreSQL", IS_POSTGRES)

            # 记录测试前的记忆总数，最后要比对
            # ⚠️ 口径 = **活跃行**（`del_flag='0'`）：2026-09-22 起删记忆是逻辑删
            #    （撤销需求），已删的行物理还在库里，按 `count(*)` 数会把「本测试自己删掉的
            #    行」也算成变化 → 三处计数（这里 / 步骤 7 的 after_total / finally 的 left）
            #    必须用同一个口径。「少 = 删到别人的、多 = 自己的没清掉」这条含义不变。
            before_total = (
                await db.execute(
                    text("SELECT count(*) FROM ai_agent_memory WHERE del_flag = '0'")
                )
            ).scalar() or 0

            # ---------- 1. 短期预算 ----------
            test_short_term_budget(c)

            # ---------- 2. 记忆写入 / 检索 ----------
            print("\n=== 2. 记忆写入与检索 ===")
            test_uid = await _pick_memory_free_user(db, c)
            if test_uid is None:
                raise RuntimeError("没有可用的零记忆用户")

            row = await memory_service.save_episodic(
                db, test_uid, "创建了题库「测试库A」(ID=901)", tool="bank_manage"
            )
            c.check("写入 episodic 记忆", row.id > 0 and row.memory_type == MEMORY_TYPE_EPISODIC)
            c.check("metadata 存下了 tool", (row.meta_data or {}).get("tool") == "bank_manage")

            await memory_service.save_conversation_summary(
                db, test_uid, "用户询问了题库的创建方式", session_id="sess-x"
            )
            counts = await memory_service.count_by_type(db, test_uid)
            c.check(
                "两类记忆都写进去了",
                counts.get(MEMORY_TYPE_EPISODIC) == 1 and counts.get(MEMORY_TYPE_CONVERSATION) == 1,
                str(counts),
            )

            found = await memory_service.search_memories(db, test_uid, "测试库A")
            c.check("按关键词能搜到", len(found) == 1, f"{len(found)} 条")
            allm = await memory_service.list_memories(db, test_uid, limit=10)
            c.check(
                "默认按 importance DESC 排（episodic 7 在 conversation 6 之前）",
                allm[0].memory_type == MEMORY_TYPE_EPISODIC,
                f"首条={allm[0].memory_type} importance={allm[0].importance}",
            )

            # ---------- 3. 淘汰：按类型分别限额 ----------
            print("\n=== 3. 淘汰按类型分别限额（legacy bug 的修复点）===")
            # 用小额上限验证机制（真实值另做断言），避免为此插几百行
            memory_service.MAX_PER_TYPE = {
                MEMORY_TYPE_EPISODIC: 3,
                MEMORY_TYPE_CONVERSATION: 2,
            }
            try:
                base_episodic = (await memory_service.count_by_type(db, test_uid)).get(
                    MEMORY_TYPE_EPISODIC, 0
                )
                # 先把 episodic 灌到超限
                for i in range(6):
                    await memory_service.save_episodic(db, test_uid, f"操作记录-{i}")
                cnt = await memory_service.count_by_type(db, test_uid)
                c.check(
                    "episodic 超出上限后被裁到上限",
                    cnt.get(MEMORY_TYPE_EPISODIC) == 3,
                    f"episodic={cnt.get(MEMORY_TYPE_EPISODIC)}（上限 3）",
                )
                conv_now = cnt.get(MEMORY_TYPE_CONVERSATION, 0)
                c.check(
                    "**灌 episodic 不会动到 conversation**（legacy 会按 importance 一起淘汰）",
                    conv_now >= 1,
                    f"conversation={conv_now}",
                )

                # 再灌 conversation 到超限，验证它也不动 episodic
                for i in range(6):
                    await memory_service.save_conversation_summary(db, test_uid, f"对话摘要-{i}")
                cnt2 = await memory_service.count_by_type(db, test_uid)
                c.check(
                    "conversation 超出上限后被裁到上限",
                    cnt2.get(MEMORY_TYPE_CONVERSATION) == 2,
                    f"conversation={cnt2.get(MEMORY_TYPE_CONVERSATION)}（上限 2）",
                )
                c.check(
                    "**灌 conversation 不会动到 episodic**",
                    cnt2.get(MEMORY_TYPE_EPISODIC) == 3,
                    f"episodic={cnt2.get(MEMORY_TYPE_EPISODIC)}",
                )

                # 活下来的是**最新**的
                latest = await memory_service.list_memories(
                    db, test_uid, memory_type=MEMORY_TYPE_CONVERSATION, limit=10
                )
                texts = [r.content for r in latest]
                c.check(
                    "淘汰的是最旧的、保留的是最新的",
                    "对话摘要-5" in texts and "对话摘要-0" not in texts,
                    f"保留={texts}",
                )
            finally:
                memory_service.MAX_PER_TYPE = original_caps

            c.check(
                "真实上限值符合预期（episodic 200 / conversation 50）",
                original_caps[MEMORY_TYPE_EPISODIC] == 200
                and original_caps[MEMORY_TYPE_CONVERSATION] == 50,
                str(original_caps),
            )
            c.check(
                "两类上限是**独立**的（不是共用一个总额）",
                original_caps[MEMORY_TYPE_EPISODIC] != original_caps[MEMORY_TYPE_CONVERSATION],
            )

            # ---------- 4. LIKE 通配符转义 ----------
            print("\n=== 4. 关键词检索转义 LIKE 通配符 ===")
            await memory_service.clear_memories(db, test_uid)
            await memory_service.save_episodic(db, test_uid, "创建了题库 a_b")
            await memory_service.save_episodic(db, test_uid, "创建了题库 axb")
            await memory_service.save_episodic(db, test_uid, "创建了题库 100%通过")
            await memory_service.save_episodic(db, test_uid, "创建了题库 1000通过")

            hit = await memory_service.search_memories(db, test_uid, "a_b")
            c.check(
                "搜 a_b 命中字面量 a_b",
                any("a_b" in h["content"] for h in hit),
                f"{[h['content'][-12:] for h in hit]}",
            )
            c.check(
                "搜 a_b **不**误命中 axb（`_` 没被当通配符）",
                not any("axb" in h["content"] for h in hit),
                f"{[h['content'][-12:] for h in hit]}",
            )
            pct = await memory_service.search_memories(db, test_uid, "100%")
            c.check(
                "搜 100% 只命中含 % 的那条（`%` 没被当通配符）",
                any("100%" in h["content"] for h in pct)
                and not any("1000通过" in h["content"] for h in pct),
                f"{[h['content'][-14:] for h in pct]}",
            )

            # ---------- 5. 归属隔离 ----------
            print("\n=== 5. 归属隔离 ===")
            other = 1 if test_uid != 1 else 2
            c.check(
                "别人的记忆搜不到",
                len(await memory_service.search_memories(db, other, "a_b")) == 0,
            )
            one = (await memory_service.list_memories(db, test_uid, limit=1))[0]
            c.check(
                "别人的记忆按 id 也取不到",
                await memory_service.get_memory(db, other, one.id) is None,
            )
            c.check(
                "别人删不掉",
                await memory_service.delete_memory(db, other, one.id) is False,
            )
            c.check(
                "自己删得掉",
                await memory_service.delete_memory(db, test_uid, one.id) is True,
            )

            # ---------- 6. 注入渲染 ----------
            print("\n=== 6. build_memory_context 渲染 ===")
            await memory_service.clear_memories(db, test_uid)
            empty_ctx = await memory_service.build_memory_context(db, test_uid)
            c.check("没有记忆时返回空串（不注入空标签）", empty_ctx == "", repr(empty_ctx[:30]))

            await memory_service.save_episodic(db, test_uid, "创建了题库「渲染测试」(ID=999)")
            en = await memory_service.build_memory_context(db, test_uid)
            c.check(
                "默认用英文标签（Agent 系统提示词是全英文）",
                "<user_memory>" in en and "</user_memory>" in en,
                en[:60].replace("\n", " | "),
            )
            c.check("记忆正文保持中文（用户数据不翻译）", "渲染测试" in en)
            zh = await memory_service.build_memory_context(db, test_uid, lang="cn")
            c.check("lang=cn 用中文标签", "【你的记忆】" in zh, zh[:40])

            # ---------- 7. memory_hook 行为 ----------
            print("\n=== 7. memory_hook：只记成功的写操作 ===")
            from app.services.ai.agent import memory_hook
            from app.services.ai.agent.registry import ensure_tools_loaded, registry

            ensure_tools_loaded()
            bank_tool = registry.get("bank_manage")
            c.check("拿到 bank_manage 工具", bank_tool is not None)

            await memory_service.clear_memories(db, test_uid)

            # 读操作 → 不记
            await memory_hook.record_tool_memory(
                test_uid, bank_tool, {"action": "list"}, {"success": True, "count": 3}
            )
            c.check(
                "读操作（list）不记",
                (await memory_service.count_by_type(db, test_uid)) == {},
            )

            # 失败的写操作 → 不记
            await memory_hook.record_tool_memory(
                test_uid,
                bank_tool,
                {"action": "create", "name": "X"},
                {"success": False, "error": "已存在同名题库"},
            )
            c.check(
                "失败的写操作不记",
                (await memory_service.count_by_type(db, test_uid)) == {},
            )

            # 成功的写操作 → 记，且内容用工具的人话回执
            await memory_hook.record_tool_memory(
                test_uid,
                bank_tool,
                {"action": "create", "name": "X"},
                {"success": True, "message": "题库「X」创建成功（ID=888）"},
            )
            rows = await memory_service.list_memories(db, test_uid, limit=5)
            c.check("成功的写操作被记住", len(rows) == 1, f"{len(rows)} 条")
            c.check(
                "记忆内容复用工具的人话回执（不另写一套文案）",
                bool(rows) and "题库「X」创建成功（ID=888）" == rows[0].content,
                rows[0].content if rows else "",
            )
            await memory_service.clear_memories(db, test_uid)

            # 记忆落库失败 → 不抛（记忆是增强项，不拖垮用户这次操作）
            #
            # ⚠️ 这里**不能**再用「传一个坏 db」来造故障了：`record_tool_memory` 现在
            # **不接收 db**（它自己开会话）—— 借调用方的事务会让每次写操作刷一条
            # `Can't operate on closed transaction inside context manager`（见 memory_hook 的说明）。
            # 所以直接把 `save_episodic` 换成会炸的，故障点更贴近真实（写入那一刻失败）。
            _real_save = memory_service.save_episodic

            async def _boom_save(*a, **k):
                raise RuntimeError("模拟数据库故障")

            raised = False
            memory_service.save_episodic = _boom_save
            try:
                await memory_hook.record_tool_memory(
                    test_uid,
                    bank_tool,
                    {"action": "create", "name": "X"},
                    {"success": True, "message": "题库「X」创建成功（ID=1）"},
                )
            except Exception:
                raised = True
            finally:
                memory_service.save_episodic = _real_save
            c.check("记忆写入失败时不抛异常（不拖垮用户这次操作）", not raised)

            after_total = (
                await db.execute(
                    text("SELECT count(*) FROM ai_agent_memory WHERE del_flag = '0'")
                )
            ).scalar() or 0
            c.check(
                "测试期间未触碰其他用户的记忆",
                after_total == before_total,
                f"测试前 {before_total} → 现在 {after_total}（活跃口径 del_flag='0'）",
            )

        except Exception as e:
            c.failed += 1
            print(f"\n  [ERROR] 测试抛异常: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
        finally:
            memory_service.MAX_PER_TYPE = original_caps
            print("\n=== 8. 清理（把测试用户清回 0 条）===")
            try:
                await db.rollback()
                if test_uid is not None:
                    # ⚠️ 2026-09-22 起 `memory_service.clear_memories` 是**逻辑删**
                    #    （撤销需求：删掉的东西要能恢复），所以清理换成裸 SQL **物理删**：
                    #    留 `del_flag='2'` 的残骸会让下面「清理后回到跑前基线」永远为假，
                    #    而那条正是本套件最该守住的不变量（见下方注释）。
                    #    删除范围与原来一字不差：**只按 user_id**；`test_uid` 是
                    #    `_pick_memory_free_user` 挑出来的零记忆用户，这些行都是本测试造的。
                    res = await db.execute(
                        text("DELETE FROM ai_agent_memory WHERE user_id = :u"),
                        {"u": test_uid},
                    )
                    await db.commit()
                    n = res.rowcount or 0
                    print(f"  [清理] 物理删掉测试用户 {test_uid} 的 {n} 条记忆")
                left = (
                    await db.execute(
                        text("SELECT count(*) FROM ai_agent_memory WHERE del_flag = '0'")
                    )
                ).scalar() or 0
                # ⚠️ 这里**必须断言，不能只打印**。
                #    历史事故：曾经就是「只打印一句复核日志」，于是测试全绿着把真实用户的
                #    N 条记忆删光了也没人发现；事后靠源库才恢复回来。清理是否恢复原状是这套
                #    用例**最该守住**的一条不变量，所以它得能变红。
                #    基线现场采（步骤 0），不写死数字 —— 库里本来就有别人留下的行。
                #    判定点是「清理**之后**」的全表总数：比基线少 = 删到别人的、多 = 自己的没清掉。
                if before_total is None:
                    c.check(
                        "清理后记忆总数回到跑之前的基线",
                        False,
                        "基线没采到（步骤 0 之前就失败了），无法比对",
                    )
                else:
                    c.check(
                        "清理后记忆总数回到跑之前的基线（没删到别人的、也没留下自己的）",
                        left == before_total,
                        f"跑前基线 {before_total} 条 → 清理后 {left} 条（差 {left - before_total:+d}）",
                    )
            except Exception as e:
                c.check(
                    "清理与复核",
                    False,
                    f"清理失败: {type(e).__name__}: {e}",
                )

    await engine.dispose()
    print(f"\n{'='*56}\n结果：{c.passed} 通过 / {c.failed} 失败")
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
