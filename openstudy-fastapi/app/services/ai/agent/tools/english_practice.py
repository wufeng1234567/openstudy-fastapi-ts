"""
`english_practice` —— 英语练习记录与学情诊断（Agent 工具）

## 为什么需要它

`english_wordbook` 让智能体能读写**词库**（静态的"我在背什么"），
但用户真正关心的是**练得怎么样**：

    「我最近英语练得多吗」
    「我听力正确率在涨吗」
    「哪些词我老是拼错」
    「我该重点复习哪几个词」

这些问题的答案不在 `words` 表里，而在 `english_practice_log`（练习记录）。
没有这个工具，智能体只能对着词库空谈，说不出任何关于"练习效果"的话。

## 与 `learning_stats` 的分工

    learning_stats     → 题库（刷题、错题本、知识点薄弱）
    english_practice   → 英语模块（听写 / 阅读 / 识词 的练习记录）

两者**不重叠**：前者读 `user_practice_log`（题库作答），后者读
`english_practice_log`（英语练习）。用户问「英语练得怎么样」时，
只有这里能答。

## 动作边界

全部**只读**（`write_operation = False`）：
  · recent —— 最近 N 次练习
  · stats  —— 各模式汇总 + 7 天趋势 + 最常错词
  · review —— 基于错词频次给出复习建议（**算出来的**，不是让 LLM 自由发挥）

⚠️ 为什么 `review` 也是只读：它只是把统计结果排个序、给个建议，
不写任何表。要真正"安排复习计划"得等未来的遗忘曲线排程，
那时再单独加写操作（并让它需要确认）。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from sqlalchemy import func, select

from app.models.words import EnglishPracticeLog, Word, WordBook, WordLearningState
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 一次最多看多少条记录
MAX_RECENT = 50


def _uid(ctx: ToolContext) -> int:
    return int(ctx.user_id or 0)


def _brief(row: EnglishPracticeLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "mode": row.mode,
        "title": row.title,
        "total": row.total,
        "correct": row.correct,
        "accuracy": row.accuracy,
        "duration": row.duration,
        "createTime": (
            row.create_time.strftime("%Y-%m-%d %H:%M") if row.create_time else None
        ),
    }


class EnglishPracticeTool(AgentTool):
    name = "english_practice"
    description = (
        "Read the user's ENGLISH practice history and diagnose how they are doing, "
        "AND start a listening/dictation practice session for them. "
        "This covers the three English modules: 单词听写 (dictation), 阅读练习 "
        "(reading comprehension), and 拍照识词 (OCR vocabulary capture). "
        "Use it whenever the user asks about their English practice rather than their "
        "word books: 'do I practise English often', 'is my dictation accuracy going up', "
        "'which words do I keep misspelling', 'what English should I review', "
        "'how did my last reading exercise go'. "
        "action values: "
        "stats=overall numbers: total sessions, overall accuracy, per-mode breakdown "
        "(dictation / reading / ocr), the last-7-days trend, and the words most often "
        "answered wrong. **PREFER THIS for any 'how am I doing in English' question.** "
        "recent=list the most recent practice sessions (pass `limit`, default 10, max 50). "
        "review=the computed review list: which words to re-practise, ordered by how "
        "often they were wrong. Each item carries `word`, `wrongCount` and `advice`. "
        "due=the words due for review TODAY under the spaced-repetition schedule "
        "(SM-2). Use this for 'what should I study today', 'what's due', "
        "'帮我安排今天的复习'. Each item carries word, stage, overdueDays, wrongCount. "
        "start=**START AN ACTUAL LISTENING PRACTICE** and give the user a one-click "
        "entry. Use this for '帮我生成听力练习', '我想练听力', '给我来一组听写', "
        "'开始背单词'. Optional args: `bookId` (which word book), `scope` "
        "(due=only due words [default], all=whole book, wrong=most-misspelled), "
        "`count` (how many words, default 20, max 100), `mode` "
        "(dictation=auto-play+auto-next [default], input=type with no time limit, "
        "listen=pure listening). Returns a `jumpUrl` the frontend renders as a "
        "one-click button that opens the listening page with those words preloaded. "
        "IMPORTANT: after calling `start`, tell the user they can click the button "
        "to begin, and keep your reply short — do NOT recite the word list. "
        "NOTE: stats / recent / review / due are read-only. To add or change word "
        "books use `english_wordbook`; for question-bank study stats use "
        "`learning_stats`. If the user has never practised, say so honestly — "
        "do NOT invent numbers."
    )
    label = "英语练习"
    description_zh = (
        "读英语练习记录：stats=总览（各模式正确率/7天趋势/最常错词）、"
        "recent=最近几次练习、review=该重点复习哪些词、"
        "due=今天按记忆曲线该复习哪些词、"
        "start=**直接生成一组听力练习**并给出一键进入按钮。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["stats", "recent", "review", "due", "start"],
            },
            "limit": {
                "type": "integer",
                "description": "For recent: how many sessions to return (default 10, max 50).",
            },
            "bookId": {
                "type": "integer",
                "description": "For start: which word book to practise. Omit to let it pick.",
            },
            "scope": {
                "type": "string",
                "description": (
                    "For start: due=only words due for review today (default), "
                    "all=the whole book, wrong=the most frequently misspelled words."
                ),
                "enum": ["due", "all", "wrong"],
            },
            "count": {
                "type": "integer",
                "description": "For start: how many words to include (default 20, max 100).",
            },
            "mode": {
                "type": "string",
                "description": (
                    "For start: dictation=auto play + auto next (default), "
                    "input=type the answer with no time limit, listen=pure listening."
                ),
                "enum": ["dictation", "input", "listen"],
            },
        },
        "required": ["action"],
    }
    #: 读类动作只读；start 不写库（只是生成一个入口链接），同样不需要确认
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "stats": self._stats,
            "recent": self._recent,
            "review": self._review,
            "due": self._due,
            "start": self._start,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 stats / recent / review / due / start",
            )
        try:
            return await handler(params, ctx)
        except Exception as e:  # noqa: BLE001
            return fail(
                f"读取英语练习记录失败：{e}",
                "可以稍后重试；不要凭空编造练习数据",
            )

    # ------------------------------------------------------------------

    async def _recent(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        raw = params.get("limit")
        try:
            limit = max(1, min(int(raw), MAX_RECENT)) if raw is not None else 10
        except (TypeError, ValueError):
            limit = 10

        rows = (
            await ctx.db.execute(
                select(EnglishPracticeLog)
                .where(
                    EnglishPracticeLog.user_id == _uid(ctx),
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(limit)
            )
        ).scalars().all()

        sessions = [_brief(r) for r in rows]
        if not sessions:
            return ok(
                action="recent",
                count=0,
                sessions=[],
                message="该用户还没有任何英语练习记录（没练过听写/阅读/识词）。请如实告知。",
            )

        return ok(
            action="recent",
            count=len(sessions),
            sessions=sessions,
            message=f"最近 {len(sessions)} 次英语练习：" + "、".join(
                f"{s['title']}（{s['accuracy']}%）" for s in sessions[:5]
            ),
        )

    async def _stats(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        uid = _uid(ctx)

        # ① 各模式累计
        rows = (
            await ctx.db.execute(
                select(
                    EnglishPracticeLog.mode,
                    func.count().label("sessions"),
                    func.sum(EnglishPracticeLog.total).label("total"),
                    func.sum(EnglishPracticeLog.correct).label("correct"),
                )
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .group_by(EnglishPracticeLog.mode)
            )
        ).all()

        by_mode: Dict[str, Dict[str, Any]] = {}
        for mode, sessions, total, correct in rows:
            t = int(total or 0)
            c = int(correct or 0)
            by_mode[str(mode)] = {
                "sessions": int(sessions or 0),
                "total": t,
                "correct": c,
                "accuracy": int(round(c * 100.0 / t)) if t else 0,
            }

        if not by_mode:
            return ok(
                action="stats",
                sessions=0,
                accuracy=0,
                byMode={},
                trend=[],
                topWrong=[],
                message="该用户还没有任何英语练习记录。请如实告知，不要说'你练得不错'这类无依据的话。",
            )

        # ② 最近 7 天趋势
        recent_rows = (
            await ctx.db.execute(
                select(
                    func.date(EnglishPracticeLog.create_time).label("d"),
                    func.sum(EnglishPracticeLog.total).label("total"),
                    func.sum(EnglishPracticeLog.correct).label("correct"),
                )
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                    EnglishPracticeLog.create_time
                    >= func.now() - func.make_interval(0, 0, 0, 7),
                )
                .group_by(func.date(EnglishPracticeLog.create_time))
            )
        ).all()

        trend = [
            {
                "date": str(d),
                "total": int(t or 0),
                "accuracy": (
                    int(round(int(c or 0) * 100.0 / int(t))) if int(t or 0) else 0
                ),
            }
            for d, t, c in recent_rows
        ]

        # ③ 最常错的词（扫最近 20 次明细）
        details = (
            await ctx.db.execute(
                select(EnglishPracticeLog.detail)
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(20)
            )
        ).scalars().all()

        counter: Dict[str, int] = {}
        for detail in details:
            for item in detail or []:
                if isinstance(item, dict) and not item.get("ok"):
                    w = str(item.get("word") or "").strip()
                    if w:
                        counter[w] = counter.get(w, 0) + 1

        top_wrong = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

        total = sum(v["total"] for v in by_mode.values())
        correct = sum(v["correct"] for v in by_mode.values())
        sessions = sum(v["sessions"] for v in by_mode.values())

        parts = [f"共练习 {sessions} 次、{total} 题"]
        for mode, label in (
            ("dictation", "听写"),
            ("reading", "阅读"),
            ("ocr", "识词"),
        ):
            m = by_mode.get(mode)
            if m:
                parts.append(f"{label} {m['sessions']} 次 {m['accuracy']}%")
        if top_wrong:
            parts.append(
                "最常错：" + "、".join(w for w, _ in top_wrong[:5])
            )

        return ok(
            action="stats",
            sessions=sessions,
            total=total,
            correct=correct,
            accuracy=int(round(correct * 100.0 / total)) if total else 0,
            byMode=by_mode,
            trend=trend,
            topWrong=[{"word": w, "count": c} for w, c in top_wrong],
            message="；".join(parts),
            jumpUrl="/front/english/listening",
        )

    async def _review(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """复习清单：按错次排序，给出确定性建议

        ⚠️ 建议是**算出来的**，不是让模型自由发挥：
        错 3 次以上 → 必须重学（可能根本没记住）
        错 2 次     → 重点复习
        错 1 次     → 过一遍即可
        同一份数据永远得到同一个结论，可复现、可解释。
        """
        uid = _uid(ctx)

        details = (
            await ctx.db.execute(
                select(EnglishPracticeLog.detail)
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .order_by(EnglishPracticeLog.create_time.desc())
                .limit(20)
            )
        ).scalars().all()

        counter: Dict[str, int] = {}
        for detail in details:
            for item in detail or []:
                if isinstance(item, dict) and not item.get("ok"):
                    w = str(item.get("word") or "").strip()
                    if w:
                        counter[w] = counter.get(w, 0) + 1

        if not counter:
            return ok(
                action="review",
                count=0,
                items=[],
                message="最近没有错词，暂时不需要重点复习。可以换个更难的词库继续练。",
            )

        items: List[Dict[str, Any]] = []
        for word, cnt in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
            if cnt >= 3:
                advice = "连续错多次，建议回到词库重学这个词再练"
                level = "high"
            elif cnt == 2:
                advice = "错了两次，重点复习"
                level = "medium"
            else:
                advice = "错了一次，过一遍即可"
                level = "low"
            items.append(
                {"word": word, "wrongCount": cnt, "level": level, "advice": advice}
            )

        high = sum(1 for i in items if i["level"] == "high")
        return ok(
            action="review",
            count=len(items),
            highPriority=high,
            items=items,
            message=(
                f"有 {len(items)} 个词需要复习"
                + (f"，其中 {high} 个是反复错的（建议优先处理）" if high else "")
            ),
            jumpUrl="/front/english/listening",
        )


    # ------------------------------------------------------------------
    # 记忆曲线：今天该复习什么（2026-10-26）
    # ------------------------------------------------------------------

    async def _due(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """今天按遗忘曲线该复习的词

        排序：先到期的、错得多的优先。**只含练过的词** ——
        全新词不该从「复习」进来，见 API 层 `/words/practice/due` 的注释。
        """
        uid = _uid(ctx)
        today = date.today()

        rows = (
            await ctx.db.execute(
                select(WordLearningState, Word)
                .join(Word, Word.word_id == WordLearningState.word_id)
                .where(
                    WordLearningState.user_id == uid,
                    WordLearningState.due_date.is_not(None),
                    WordLearningState.due_date <= today,
                )
                .order_by(
                    WordLearningState.due_date.asc(),
                    WordLearningState.wrong_count.desc(),
                )
                .limit(50)
            )
        ).all()

        if not rows:
            # 分两种情况说，不要笼统说"没有"
            tracked = int(
                await ctx.db.scalar(
                    select(func.count())
                    .select_from(WordLearningState)
                    .where(WordLearningState.user_id == uid)
                )
                or 0
            )
            if tracked == 0:
                return ok(
                    action="due",
                    count=0,
                    items=[],
                    message=(
                        "该用户还没有任何单词进入记忆曲线（没练过听写）。"
                        "请如实告知，并建议先去听写一轮。"
                    ),
                    jumpUrl="/front/english/listening",
                )
            return ok(
                action="due",
                count=0,
                items=[],
                message="今天没有到期该复习的词（都排在未来）。可以练新词或加量。",
                jumpUrl="/front/english/listening",
            )

        items = [
            {
                "word": w.word,
                "translation": w.translation,
                "stage": int(st.stage or 0),
                "wrongCount": int(st.wrong_count or 0),
                "overdueDays": (today - st.due_date).days if st.due_date else 0,
            }
            for st, w in rows
        ]

        overdue = sum(1 for i in items if i["overdueDays"] > 0)
        return ok(
            action="due",
            count=len(items),
            overdue=overdue,
            items=items,
            message=(
                f"今天有 {len(items)} 个词到期待复习"
                + (f"，其中 {overdue} 个已经逾期" if overdue else "")
                + "：" + "、".join(i["word"] for i in items[:8])
            ),
            jumpUrl="/front/english/listening",
        )

    # ------------------------------------------------------------------
    # 生成一组听力练习（2026-10-26）
    # ------------------------------------------------------------------

    async def _start(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """生成一组听力练习，返回带参 URL

        ## 为什么返回 URL 而不是直接开练

        智能体跑在服务端，它没法"替用户点开始"。但它可以给出一个
        **带好参数的落地链接**，前端渲染成「开始听力练习」按钮，
        点一下就直接进到已经选好词、选好模式的练习态 —— 不用用户
        再去选词库、调设置。

        ## 选词策略（scope）

            due   优先取今天到期的词；**不够则用新词补足**
            wrong 取错得最多的词
            all   整本词书（按 word_id 倒序 = 最近加入的）

        `due` 不够时补新词，是因为"今天该复习的只有 3 个"时，
        只给 3 个词的练习太敷衍；补到 count 个更像"一组练习"。
        补进来的新词按 word_id 顺序取，不随机 —— 保证同一个请求
        每次得到同样的结果，便于复现和解释。
        """
        uid = _uid(ctx)

        # 参数归一
        try:
            count = int(params.get("count") or 20)
        except (TypeError, ValueError):
            count = 20
        count = max(1, min(count, 100))

        scope = str(params.get("scope") or "due")
        if scope not in ("due", "all", "wrong"):
            scope = "due"

        mode = str(params.get("mode") or "dictation")
        if mode not in ("dictation", "input", "listen"):
            mode = "dictation"

        # 选词书：指定了就用指定的（要校验归属），否则挑用户词最多的一本
        book_id = params.get("bookId")
        book = None
        if book_id is not None:
            try:
                book = await ctx.db.scalar(
                    select(WordBook).where(
                        WordBook.book_id == int(book_id),
                        WordBook.del_flag == "0",
                    )
                )
            except (TypeError, ValueError):
                book = None
            if book is not None and book.user_id not in (None, uid):
                # 不是自己的书（且不是系统预置）→ 当作没指定
                book = None

        if book is None:
            book = await self._pick_book(ctx, uid)

        if book is None:
            return ok(
                action="start",
                count=0,
                message="该用户还没有任何词书，没法生成听力练习。请如实告知。",
            )

        words: List[Dict[str, Any]] = []
        if scope == "due":
            words = await self._pick_due_words(ctx, uid, int(book.book_id), count)
        elif scope == "wrong":
            words = await self._pick_wrong_words(ctx, uid, int(book.book_id), count)

        if len(words) < count:
            # 补新词（未进入记忆曲线的优先，其次任意未选的）
            have = {w["word"].lower() for w in words}
            extra = await self._pick_new_words(
                ctx, uid, int(book.book_id), count - len(words), have
            )
            words.extend(extra)

        if not words:
            return ok(
                action="start",
                count=0,
                message=f"词书「{book.book_name}」里还没有单词，没法练习。",
                jumpUrl=f"/front/english/vocabulary/{int(book.book_id)}",
            )

        # 组装落地链接：听写页读这些参数自动进入练习态
        from urllib.parse import quote

        seed = ",".join(w["word"] for w in words)
        jump = (
            f"/front/english/listening"
            f"?auto=1"
            f"&bookId={int(book.book_id)}"
            f"&mode={mode}"
            f"&scope={scope}"
            f"&words={quote(seed, safe=',')}"
        )

        due_n = sum(1 for w in words if w.get("isDue"))
        new_n = len(words) - due_n
        scope_text = {
            "due": f"{due_n} 个到期复习 + {new_n} 个新词" if new_n else f"{due_n} 个到期复习",
            "wrong": f"{len(words)} 个易错词",
            "all": f"「{book.book_name}」的 {len(words)} 个词",
        }[scope]

        return ok(
            action="start",
            count=len(words),
            bookId=int(book.book_id),
            bookName=book.book_name,
            mode=mode,
            scope=scope,
            words=[w["word"] for w in words],
            message=(
                f"已准备好一组听力练习：{scope_text}"
                f"（模式：{'自动听写' if mode == 'dictation' else '打字输入' if mode == 'input' else '纯听力'}）。"
                "点下面的按钮直接开始。"
            ),
            # 前端把这个渲染成「开始听力练习」按钮
            jumpUrl=jump,
        )

    # ---- 选词辅助 ----

    async def _pick_book(self, ctx: ToolContext, uid: int):
        """挑一本词书：优先用户自己建的、词最多的那本

        系统预置书（user_id IS NULL）排在后面 —— 自己的书更可能是
        当前正在背的那本。
        """
        rows = (
            await ctx.db.execute(
                select(WordBook)
                .where(WordBook.del_flag == "0")
                .where((WordBook.user_id == uid) | (WordBook.user_id.is_(None)))
                .order_by(WordBook.word_count.desc(), WordBook.book_id.asc())
                .limit(20)
            )
        ).scalars().all()

        mine = [b for b in rows if b.user_id == uid and (b.word_count or 0) > 0]
        if mine:
            return mine[0]
        preset = [b for b in rows if (b.word_count or 0) > 0]
        return preset[0] if preset else None

    async def _pick_due_words(
        self, ctx: ToolContext, uid: int, book_id: int, count: int
    ) -> List[Dict[str, Any]]:
        today = date.today()
        rows = (
            await ctx.db.execute(
                select(WordLearningState, Word)
                .join(Word, Word.word_id == WordLearningState.word_id)
                .where(
                    WordLearningState.user_id == uid,
                    WordLearningState.due_date.is_not(None),
                    WordLearningState.due_date <= today,
                    Word.book_id == book_id,
                )
                .order_by(
                    WordLearningState.due_date.asc(),
                    WordLearningState.wrong_count.desc(),
                )
                .limit(count)
            )
        ).all()
        return [
            {
                "word": w.word,
                "translation": w.translation,
                "isDue": True,
                "wrongCount": int(st.wrong_count or 0),
            }
            for st, w in rows
        ]

    async def _pick_wrong_words(
        self, ctx: ToolContext, uid: int, book_id: int, count: int
    ) -> List[Dict[str, Any]]:
        rows = (
            await ctx.db.execute(
                select(WordLearningState, Word)
                .join(Word, Word.word_id == WordLearningState.word_id)
                .where(
                    WordLearningState.user_id == uid,
                    WordLearningState.wrong_count > 0,
                    Word.book_id == book_id,
                )
                .order_by(
                    WordLearningState.wrong_count.desc(),
                    WordLearningState.lapses.desc(),
                )
                .limit(count)
            )
        ).all()
        return [
            {"word": w.word, "translation": w.translation, "isDue": False}
            for st, w in rows
        ]

    async def _pick_new_words(
        self,
        ctx: ToolContext,
        uid: int,
        book_id: int,
        count: int,
        exclude: set,
    ) -> List[Dict[str, Any]]:
        """补充没练过的词

        优先取**从未进入记忆曲线**的（真正的新词），
        其次是练过但没被 `exclude` 掉的。
        """
        if count <= 0:
            return []

        # 已有状态的 word_id
        tracked = set(
            (
                await ctx.db.execute(
                    select(WordLearningState.word_id).where(
                        WordLearningState.user_id == uid
                    )
                )
            ).scalars().all()
        )

        stmt = (
            select(Word)
            .where(Word.book_id == book_id)
            .order_by(Word.word_id.asc())
            .limit(count * 3 + len(exclude))
        )
        rows = (await ctx.db.execute(stmt)).scalars().all()

        out: List[Dict[str, Any]] = []
        for w in rows:
            if len(out) >= count:
                break
            if str(w.word).lower() in exclude:
                continue
            if int(w.word_id) in tracked:
                continue
            out.append({"word": w.word, "translation": w.translation, "isDue": False})
            exclude.add(str(w.word).lower())

        # 不够就放宽（允许复习过的词）
        if len(out) < count:
            for w in rows:
                if len(out) >= count:
                    break
                if str(w.word).lower() in exclude:
                    continue
                out.append({"word": w.word, "translation": w.translation, "isDue": False})
                exclude.add(str(w.word).lower())

        return out


__all__ = ["EnglishPracticeTool", "MAX_RECENT"]