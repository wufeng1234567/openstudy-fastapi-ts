"""
`english_wordbook` —— 英语词库 / 单词 / 练习（Agent 工具）

## 为什么需要这个工具

英语学习模块（我的词库 / 拍照识词 / 单词听写 / 阅读练习）原本是**独立**的：
用户在页面上点，智能体完全不知道它的存在 —— 15 个工具里没有一个碰词库。
于是两边各说各的：

  · 用户对智能体说「帮我把这几个词加进考研词库」→ 智能体只能说"我做不到"；
  · 用户在页面上加了词 → 智能体问「我在背什么」也只能说"看不到"。

本工具把这条边界打通，让「聊天」与「英语模块」形成闭环：

    聊天里说「给考研词库加五个四级词」
        → 写库（english_wordbook.write / batch_add_words）
        → 回执里带 `jumpUrl`，前端渲染成「去看看」卡片
        → 用户点卡片直接进词库详情，看到刚加的词
        → 再点「去听写」，闭环完成

## 动作边界（刻意这样分）

**只读**：list_books / list_words / stats / search_word
**写**：create_book / rename_book / delete_book / add_word / batch_add_words / delete_words

写操作 `write_operation = True`，但**只有真正改库的 action** 才需要确认
（见 `needs_confirmation`），理由与 `learning_stats` 一致：
`list_words` / `stats` 是最常被调用的（用户随口问「我在背什么」），
给只读弹确认卡会把最自然的对话打断。

## 归属校验

所有写操作都复用 `app/api/v1/words.py` 里的同一个判据：
**「这是不是你的书」**（`user_id == 当前用户`），系统预置书（`user_id IS NULL`）只读。
不复制一份 SQL，避免两个地方的口径漂移。

## 参数命名

对外（模型看到的）一律用**业务语义**命名：`bookId` / `bookName` / `word` / `translation`。
与后端接口、前端字段保持同一套词，模型不用在两套命名之间翻译。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update

from app.models.words import Word, WordBook
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok


def _uid(ctx: ToolContext) -> int:
    return int(ctx.user_id or 0)


def _book_brief(book: WordBook) -> Dict[str, Any]:
    """词书摘要（字段名与前端 `/wordBooks/wordBooks/list` 完全一致）"""
    return {
        "bookId": book.book_id,
        "bookName": book.book_name,
        "bookDescription": book.book_description,
        "wordCount": book.word_count,
        # 系统预置书（user_id 为空）= 所有人只读可见
        "isDefault": 1 if getattr(book, "user_id", None) is None else 0,
    }


def _word_brief(word: Word) -> Dict[str, Any]:
    """单词摘要（字段名与前端 `/words/words/list` 完全一致）"""
    return {
        "wordId": word.word_id,
        "bookId": word.book_id,
        "word": word.word,
        "phonetic": word.phonetic,
        "translation": word.translation,
        "example": word.example,
    }


async def _recount(db, book_id: int) -> None:
    """重算词书单词数（与 `api/v1/words.py::_recount_book` 同一口径）"""
    cnt = await db.scalar(
        select(func.count()).select_from(Word).where(Word.book_id == book_id)
    )
    await db.execute(
        update(WordBook).where(WordBook.book_id == book_id).values(word_count=int(cnt or 0))
    )


async def _get_owned_book(db, book_id: int, uid: int, *, for_write: bool = False):
    """取词书并校验归属（与 `api/v1/words.py::_get_owned_book` 同一判据）

    返回 `(book, err)`；`err` 非空时应原样返回给调用方。
    """
    book = (
        await db.execute(
            select(WordBook).where(
                WordBook.book_id == book_id, WordBook.del_flag == "0"
            )
        )
    ).scalar_one_or_none()

    if book is None:
        return None, fail("词书不存在", "先调 list_books 看看有哪些词书")
    if book.user_id is None:
        if for_write:
            return None, fail(
                "系统预置词书不能修改",
                "这是所有人共用的预置词书，只能读。想加词请先 create_book 建一本自己的",
            )
        return book, None
    if int(book.user_id) != int(uid):
        # 与页面口径一致：不区分"不存在"和"别人的"，避免探测
        return None, fail("词书不存在", "先调 list_books 看看有哪些词书")
    return book, None


class EnglishWordbookTool(AgentTool):
    name = "english_wordbook"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Manage the user's ENGLISH word books (vocabulary), words, and reading/listening "
        "practice data. These are the SAME books the user sees on the "
        "'英语学习 / 我的词库' page. "
        "Use this tool whenever the user talks about English words or vocabulary: "
        "'what word books do I have', 'what words am I memorising', 'add these five "
        "words to my book', 'create a word book called CET-4', 'delete that book', "
        "'how many words do I know', 'search my vocabulary for abandon'. "
        "action values: "
        "list_books=list all my books plus the built-in ones (read-only), "
        "list_words=list the words inside one book (pass `bookId`; read-only), "
        "stats=summary numbers: how many books / words / books that are still empty "
        "(read-only), "
        "search_word=find a word across all my books by spelling or meaning (read-only), "
        "create_book=create a new word book (WRITE; pass `bookName`, optional "
        "`bookDescription`), "
        "rename_book=rename an existing book (WRITE; pass `bookId` + `bookName`), "
        "delete_book=soft-delete one of my books (WRITE; pass `bookId`), "
        "add_word=add ONE word (WRITE; pass `bookId` + `word` + `translation`, optional "
        "`phonetic` / `example`), "
        "batch_add_words=add MANY words at once (WRITE; pass `bookId` + `words`, a JSON "
        "array of {word, translation, phonetic?}), "
        "delete_words=remove words by id (WRITE; pass `wordIds`). "
        "IMPORTANT: read-only actions never need confirmation; write actions do. "
        "When a write succeeds the result carries `jumpUrl` — tell the user they can open "
        "it to see the change, do NOT paste the raw URL. "
        "For 'what should I study next' style questions about English, combine this with "
        "`learning_stats` (that one covers question banks, not vocabulary)."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "英语词库"
    description_zh = (
        "管英语词书与单词：list_books=我的词书、list_words=某本书里的词、"
        "stats=词库总览、search_word=搜单词；"
        "create_book=建书、rename_book=改名、delete_book=删书、"
        "add_word=加一个词、batch_add_words=批量加词、delete_words=删词。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "list_books",
                    "list_words",
                    "stats",
                    "search_word",
                    "create_book",
                    "rename_book",
                    "delete_book",
                    "add_word",
                    "batch_add_words",
                    "delete_words",
                ],
            },
            "bookId": {
                "type": "integer",
                "description": "Word book id (required by list_words / rename_book / delete_book / add_word / batch_add_words).",
            },
            "bookName": {
                "type": "string",
                "description": "Word book name (required by create_book; optional new name for rename_book).",
            },
            "bookDescription": {
                "type": "string",
                "description": "One-line description for create_book (optional).",
            },
            "word": {
                "type": "string",
                "description": "The English word or phrase (required by add_word).",
            },
            "translation": {
                "type": "string",
                "description": "Chinese meaning for add_word (strongly recommended).",
            },
            "phonetic": {
                "type": "string",
                "description": "Phonetic transcription, e.g. /əˈbændən/ (optional).",
            },
            "example": {
                "type": "string",
                "description": "Example sentence (optional).",
            },
            "words": {
                "type": "array",
                "description": (
                    "For batch_add_words: array of objects, each "
                    "{\"word\": \"abandon\", \"translation\": \"v. 放弃\", \"phonetic\": \"...\"}. "
                    "Max 200 per call."
                ),
                "items": {"type": "object"},
            },
            "wordIds": {
                "type": "array",
                "description": "For delete_words: array of numeric word ids.",
                "items": {"type": "integer"},
            },
            "query": {
                "type": "string",
                "description": "For search_word: text to look for in the spelling or the meaning.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return for list_words / search_word (default 100, max 500).",
            },
        },
        "required": ["action"],
    }
    #: 会写库；但按 action 细分（见 needs_confirmation）
    write_operation = True

    _WRITE_ACTIONS = {
        "create_book",
        "rename_book",
        "delete_book",
        "add_word",
        "batch_add_words",
        "delete_words",
    }

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        """只有真正改库的 action 需要确认

        ⚠️ `list_books` / `list_words` / `stats` / `search_word` 是只读的，
        而它们恰恰是最常被调用的那几句（「我在背什么词」「有几个词库」）。
        按整个工具一律确认，会让最自然的提问先弹一次卡，等于打断对话。
        """
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def undo_delete_book(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """`delete_book` 是软删（`del_flag='2'`），可以撤销

        与 `bank_manage` 的软删口径一致：把 `del_flag` 改回 `'0'` 即可，
        里面的单词从未被物理删除，所以恢复后词也还在。
        """
        if str(params.get("action") or "") != "delete_book":
            return None
        book_id = params.get("bookId")
        return {"bookId": book_id, "del_flag": "0"}

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "list_books": self._list_books,
            "list_words": self._list_words,
            "stats": self._stats,
            "search_word": self._search_word,
            "create_book": self._create_book,
            "rename_book": self._rename_book,
            "delete_book": self._delete_book,
            "add_word": self._add_word,
            "batch_add_words": self._batch_add_words,
            "delete_words": self._delete_words,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list_books / list_words / stats / search_word / "
                "create_book / rename_book / delete_book / add_word / "
                "batch_add_words / delete_words",
            )
        try:
            return await handler(params, ctx)
        except Exception as e:  # noqa: BLE001 - 词库操作失败也要给模型一个可读说明
            return fail(
                f"英语词库操作失败：{e}",
                "可以稍后重试；不要凭空编造词库内容",
            )

    # ------------------------------------------------------------------
    # 只读
    # ------------------------------------------------------------------

    async def _list_books(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        uid = _uid(ctx)
        rows = (
            await ctx.db.execute(
                select(WordBook)
                .where(
                    WordBook.del_flag == "0",
                    (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
                )
                .order_by(WordBook.create_time.desc(), WordBook.book_id.desc())
            )
        ).scalars().all()

        books = [_book_brief(b) for b in rows]
        mine = [b for b in books if not b["isDefault"]]
        preset = [b for b in books if b["isDefault"]]

        if not books:
            message = "该用户还没有任何词书（也没有系统预置词书），请如实告知，不要编造。"
        else:
            total_words = sum(int(b.get("wordCount") or 0) for b in books)
            message = (
                f"共 {len(books)} 本词书（自己建的 {len(mine)} 本、系统预置 {len(preset)} 本），"
                f"合计 {total_words} 个单词"
            )

        return ok(
            action="list_books",
            count=len(books),
            books=books,
            message=message,
            # 回执里带跳转目标，前端渲染成卡片（见模块说明）
            jumpUrl="/front/english/vocabulary",
        )

    async def _list_words(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        book_id = params.get("bookId")
        if not book_id:
            return fail("缺少 bookId", "先用 list_books 拿到 bookId")

        book, err = await _get_owned_book(ctx.db, int(book_id), _uid(ctx))
        if err:
            return err

        limit = _clamp(params.get("limit"), 100, 1, 500)
        rows = (
            await ctx.db.execute(
                select(Word)
                .where(Word.book_id == int(book_id))
                .order_by(Word.sort_order.asc(), Word.word_id.asc())
                .limit(limit)
            )
        ).scalars().all()

        words = [_word_brief(w) for w in rows]
        if not words:
            message = f"「{book.book_name}」这本词书还是空的"
        else:
            message = f"「{book.book_name}」共 {book.word_count} 个单词，本次返回 {len(words)} 个"

        return ok(
            action="list_words",
            bookId=int(book_id),
            bookName=book.book_name,
            total=book.word_count,
            count=len(words),
            words=words,
            message=message,
            jumpUrl=f"/front/english/vocabulary/{int(book_id)}",
        )

    async def _stats(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        uid = _uid(ctx)
        books = (
            await ctx.db.execute(
                select(WordBook).where(
                    WordBook.del_flag == "0",
                    (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
                )
            )
        ).scalars().all()

        empty = [b.book_name for b in books if int(b.word_count or 0) == 0]
        total_words = sum(int(b.word_count or 0) for b in books if b.user_id is not None)

        if not books:
            message = "该用户还没有任何词书，请如实告知。"
        else:
            message = (
                f"共 {len(books)} 本词书、{total_words} 个单词"
                + (f"；其中 {len(empty)} 本还是空的" if empty else "")
            )

        return ok(
            action="stats",
            bookCount=len(books),
            myBookCount=sum(1 for b in books if b.user_id is not None),
            presetBookCount=sum(1 for b in books if b.user_id is None),
            totalWords=total_words,
            emptyBooks=empty,
            message=message,
        )

    async def _search_word(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        query = str(params.get("query") or "").strip()
        if not query:
            return fail("缺少 query", "告诉我要搜什么词或什么含义")

        uid = _uid(ctx)
        limit = _clamp(params.get("limit"), 50, 1, 200)

        # 只在自己 + 预置的词书里搜
        allowed = (
            await ctx.db.execute(
                select(WordBook.book_id).where(
                    WordBook.del_flag == "0",
                    (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
                )
            )
        ).scalars().all()
        if not allowed:
            return ok(action="search_word", query=query, count=0, words=[],
                      message="该用户还没有任何词书，无法搜索")

        rows = (
            await ctx.db.execute(
                select(Word)
                .where(
                    Word.book_id.in_(list(allowed)),
                    (Word.word.ilike(f"%{query}%"))
                    | (Word.translation.ilike(f"%{query}%")),
                )
                .order_by(Word.word_id.asc())
                .limit(limit)
            )
        ).scalars().all()

        words = [_word_brief(w) for w in rows]
        return ok(
            action="search_word",
            query=query,
            count=len(words),
            words=words,
            message=(
                f"在词库里找到 {len(words)} 个匹配「{query}」的词"
                if words
                else f"词库里没有匹配「{query}」的词"
            ),
        )

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    async def _create_book(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        name = str(params.get("bookName") or "").strip()
        if not name:
            return fail("缺少 bookName", "告诉我词书叫什么名字")

        book = WordBook(
            user_id=_uid(ctx),
            book_name=name[:100],
            book_description=(str(params.get("bookDescription") or "").strip() or None),
        )
        ctx.db.add(book)
        await ctx.db.flush()

        return ok(
            action="create_book",
            book=_book_brief(book),
            message=f"已创建词书「{name}」",
            jumpUrl=f"/front/english/vocabulary/{book.book_id}",
        )

    async def _rename_book(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        book_id = params.get("bookId")
        name = str(params.get("bookName") or "").strip()
        if not book_id:
            return fail("缺少 bookId", "先用 list_books 拿到 bookId")
        if not name:
            return fail("缺少 bookName", "告诉我改成什么名字")

        book, err = await _get_owned_book(ctx.db, int(book_id), _uid(ctx), for_write=True)
        if err:
            return err

        old = book.book_name
        book.book_name = name[:100]
        return ok(
            action="rename_book",
            book=_book_brief(book),
            message=f"已把「{old}」改名为「{name}」",
            jumpUrl=f"/front/english/vocabulary/{int(book_id)}",
        )

    async def _delete_book(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        book_id = params.get("bookId")
        if not book_id:
            return fail("缺少 bookId", "先用 list_books 拿到 bookId")

        book, err = await _get_owned_book(ctx.db, int(book_id), _uid(ctx), for_write=True)
        if err:
            return err

        # 软删（与页面一致），里面的单词不动
        book.del_flag = "2"
        return ok(
            action="delete_book",
            bookId=int(book_id),
            bookName=book.book_name,
            message=f"已删除词书「{book.book_name}」（软删除，可以撤销）",
        )

    async def _add_word(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        book_id = params.get("bookId")
        word_text = str(params.get("word") or "").strip()
        if not book_id:
            return fail("缺少 bookId", "先用 list_books 拿到 bookId")
        if not word_text:
            return fail("缺少 word", "告诉我要加哪个英文单词")

        book, err = await _get_owned_book(ctx.db, int(book_id), _uid(ctx), for_write=True)
        if err:
            return err

        obj = Word(
            book_id=int(book_id),
            word=word_text[:100],
            translation=(str(params.get("translation") or "").strip() or None),
            phonetic=(str(params.get("phonetic") or "").strip() or None),
            example=(str(params.get("example") or "").strip() or None),
            sort_order=0,
        )
        ctx.db.add(obj)
        await ctx.db.flush()
        await _recount(ctx.db, int(book_id))

        return ok(
            action="add_word",
            word=_word_brief(obj),
            bookName=book.book_name,
            message=f"已把「{word_text}」加进「{book.book_name}」",
            jumpUrl=f"/front/english/vocabulary/{int(book_id)}",
        )

    async def _batch_add_words(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        book_id = params.get("bookId")
        if not book_id:
            return fail("缺少 bookId", "先用 list_books 拿到 bookId")

        raw = params.get("words")
        # 模型有时会把数组序列化成字符串传进来，这里兼容一下
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return fail("words 不是合法 JSON 数组", "传 [{word, translation}, ...]")
        if not isinstance(raw, list) or not raw:
            return fail("words 必须是非空数组", "传 [{word, translation}, ...]")
        if len(raw) > 200:
            raw = raw[:200]

        book, err = await _get_owned_book(ctx.db, int(book_id), _uid(ctx), for_write=True)
        if err:
            return err

        added: List[str] = []
        skipped: List[str] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("word") or "").strip()
            if not text:
                skipped.append("（空）")
                continue
            ctx.db.add(
                Word(
                    book_id=int(book_id),
                    word=text[:100],
                    translation=(str(item.get("translation") or "").strip() or None),
                    phonetic=(str(item.get("phonetic") or "").strip() or None),
                    example=(str(item.get("example") or "").strip() or None),
                    sort_order=0,
                )
            )
            added.append(text)

        await ctx.db.flush()
        await _recount(ctx.db, int(book_id))

        # flush 后重新读一次词数（_recount 已写库）
        await ctx.db.refresh(book)
        return ok(
            action="batch_add_words",
            bookId=int(book_id),
            bookName=book.book_name,
            addedCount=len(added),
            added=added[:50],
            skippedCount=len(skipped),
            message=(
                f"已把 {len(added)} 个单词加进「{book.book_name}」"
                + (f"，跳过 {len(skipped)} 个空词条" if skipped else "")
            ),
            jumpUrl=f"/front/english/vocabulary/{int(book_id)}",
        )

    async def _delete_words(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        raw = params.get("wordIds")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return fail("wordIds 不是合法数组", "传 [1, 2, 3]")
        if not isinstance(raw, list) or not raw:
            return fail("wordIds 必须是非空数组", "先用 list_words 拿到 wordId")

        ids: List[int] = []
        for v in raw:
            try:
                ids.append(int(v))
            except (TypeError, ValueError):
                continue
        if not ids:
            return fail("wordIds 里没有合法数字", "传 [1, 2, 3]")

        uid = _uid(ctx)
        my_book_ids = (
            await ctx.db.execute(
                select(WordBook.book_id).where(
                    WordBook.user_id == uid, WordBook.del_flag == "0"
                )
            )
        ).scalars().all()
        if not my_book_ids:
            return fail("没有可删除的词书", "该用户还没有自己的词书")

        touched = (
            await ctx.db.execute(
                select(Word.book_id).where(
                    Word.word_id.in_(ids), Word.book_id.in_(list(my_book_ids))
                )
            )
        ).scalars().all()

        await ctx.db.execute(
            delete(Word).where(
                Word.word_id.in_(ids), Word.book_id.in_(list(my_book_ids))
            )
        )
        for bid in set(touched):
            await _recount(ctx.db, int(bid))

        return ok(
            action="delete_words",
            deletedCount=len(ids),
            affectedBooks=sorted(set(int(b) for b in touched)),
            message=f"已删除 {len(ids)} 个单词"
            + ("（只删了自己词书里的，预置书和别人的不受影响）" if len(touched) != len(ids) else ""),
        )


def _clamp(raw: Any, default: int, low: int, high: int) -> int:
    """把可选的整型参数收进 [low, high]"""
    if raw is None:
        return default
    try:
        return max(low, min(int(raw), high))
    except (TypeError, ValueError):
        return default


__all__ = ["EnglishWordbookTool"]
