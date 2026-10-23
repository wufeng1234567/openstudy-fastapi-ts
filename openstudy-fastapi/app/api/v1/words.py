"""
词书/单词 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.words import WordBook, Word
from app.utils.excel_util import export_to_excel
from datetime import datetime

router = APIRouter()


def _uid(current_user: dict) -> int:
    """从登录态取用户 id（与仓库其它模块同一口径）"""
    return int((current_user or {}).get("user_id") or 0)


def format_word_book(book):
    return {
        "bookId": book.book_id,
        "bookName": book.book_name,
        "bookDescription": book.book_description,
        "wordCount": book.word_count,
        "coverImage": book.cover_image,
        "status": book.status,
        # `isDefault`：系统预置词书（user_id 为空）= 所有登录用户只读可见。
        # 前端据此显示「默认」徽标，并隐藏改名/删除入口。
        "isDefault": 1 if getattr(book, "user_id", None) is None else 0,
        "createTime": book.create_time.isoformat() if book.create_time else None,
    }


async def _get_owned_book(db: AsyncSession, book_id: int, uid: int, *, for_write: bool = False):
    """取词书并校验归属。

    · 自己的书：可读可写；
    · 系统预置书（`user_id IS NULL`）：**只读**，`for_write=True` 时拒绝；
    · 别人的书：一律拒绝（不区分"不存在"以防探测）。

    返回 `(book, err)`，`err` 非空时直接把它 return 给调用方。
    """
    book = (
        await db.execute(
            select(WordBook).where(WordBook.book_id == book_id, WordBook.del_flag == "0")
        )
    ).scalar_one_or_none()

    if book is None:
        return None, error("词书不存在")
    if book.user_id is None:
        if for_write:
            return None, error("系统预置词书不能修改")
        return book, None
    if int(book.user_id) != int(uid):
        # 刻意不说"这是别人的" —— 避免被用来探测别人有哪些词书
        return None, error("词书不存在")
    return book, None


def format_word(word):
    return {
        "wordId": word.word_id,
        "bookId": word.book_id,
        "word": word.word,
        "phonetic": word.phonetic,
        "translation": word.translation,
        "example": word.example,
        "audioUrl": word.audio_url,
        "sortOrder": word.sort_order,
        "createTime": word.create_time.isoformat() if word.create_time else None,
    }


@router.get("/wordBooks/wordBooks/list")
async def list_word_books(
    bookName: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出「我的词书」+「系统预置词书」。

    ⚠️ 2026-10-23 修：原来无条件列出**全站所有词书** ——
       用户 A 能看到用户 B 的词书，还能点进去。
       现在只返回自己的（`user_id = 我`）和系统预置的（`user_id IS NULL`）。
    """
    uid = _uid(current_user)
    query = select(WordBook).where(
        WordBook.del_flag == "0",
        (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
    )
    if bookName:
        query = query.where(WordBook.book_name.ilike(f"%{bookName}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(WordBook.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    books = list(result.scalars().all())

    return paginate(total, [format_word_book(b) for b in books])


@router.get("/wordBooks/wordBooks/all")
async def list_all_word_books(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """不分页的「我的 + 预置」词书列表（下拉框用）"""
    uid = _uid(current_user)
    query = (
        select(WordBook)
        .where(
            WordBook.del_flag == "0",
            (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
        )
        .order_by(WordBook.create_time.desc())
    )
    result = await db.execute(query)
    books = list(result.scalars().all())
    return success([format_word_book(b) for b in books])


@router.get("/wordBooks/wordBooks/{book_id}")
async def get_word_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    book, err = await _get_owned_book(db, book_id, _uid(current_user))
    if err:
        return err
    return success(format_word_book(book))


@router.post("/wordBooks/wordBooks")
async def create_word_book(
    bookName: str = Query(...),
    bookDescription: Optional[str] = Query(None),
    coverImage: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新建词书 —— 归属当前登录用户"""
    book = WordBook(
        user_id=_uid(current_user),
        book_name=bookName,
        book_description=bookDescription,
        cover_image=coverImage,
    )
    db.add(book)
    await db.flush()
    return success(format_word_book(book))


@router.put("/wordBooks/wordBooks")
async def update_word_book(
    bookId: int = Query(...),
    bookName: Optional[str] = Query(None),
    bookDescription: Optional[str] = Query(None),
    coverImage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    book, err = await _get_owned_book(db, bookId, _uid(current_user), for_write=True)
    if err:
        return err

    if bookName is not None:
        book.book_name = bookName
    if bookDescription is not None:
        book.book_description = bookDescription
    if coverImage is not None:
        book.cover_image = coverImage
    if status is not None:
        book.status = status

    return success()


@router.delete("/wordBooks/wordBooks/{book_ids}")
async def delete_word_books(
    book_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量软删词书（`del_flag='2'`）

    ⚠️ 2026-10-23 已修（此前是一个**已知缺口**）：
       原注释写着「`word_books` 没有归属列，任何登录用户拿一串 id 就能软删任意词书」，
       并说明不能靠 403 硬堵（会把普通用户删自己单词本的功能改瘫）。

       真正的修法就是当时列的第 ① 条 —— **给表加 `user_id` 归属列**
       （`deploy/db-init/15_english_wordbook_owner.sql`）。
       现在按归属过滤：只能删自己的书；系统预置书（`user_id IS NULL`）不可删。

       这既堵住了越权，又没有误伤普通用户 —— 因为判据从「你是不是管理员」
       换成了「这是不是你的书」，与角色无关。
    """
    uid = _uid(current_user)
    ids = []
    for raw in str(book_ids).split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            return error(f"词书 id 不合法：{raw}")

    if not ids:
        return error("请提供要删除的词书 id")

    # 只软删「属于当前用户」的那些；别人的 / 系统预置的 id 会被静默跳过。
    # 刻意不逐个报错：否则这个端点就成了「探测别人有哪些词书」的工具。
    stmt = (
        update(WordBook)
        .where(
            WordBook.book_id.in_(ids),
            WordBook.del_flag == "0",
            WordBook.user_id == uid,
        )
        .values(del_flag="2")
    )
    await db.execute(stmt)
    return success()


@router.get("/words/words/list")
async def list_words(
    bookId: Optional[int] = Query(None),
    word: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出单词。

    ⚠️ 归属校验：传了 `bookId` 就先确认这本书是「我的」或「系统预置的」，
       否则任何人改个 id 就能翻别人的生词本。不传 bookId 时，
       只返回属于「我的书」和「预置书」的单词（不列全站）。
    """
    uid = _uid(current_user)

    # 允许访问的词书 id 集合：我的 + 系统预置
    allowed_rows = (
        await db.execute(
            select(WordBook.book_id).where(
                WordBook.del_flag == "0",
                (WordBook.user_id == uid) | (WordBook.user_id.is_(None)),
            )
        )
    ).scalars().all()
    allowed_ids = list(allowed_rows)

    if bookId:
        if int(bookId) not in allowed_ids:
            return error("词书不存在")
        query = select(Word).where(Word.book_id == bookId)
    else:
        query = select(Word).where(Word.book_id.in_(allowed_ids))

    if word:
        query = query.where(Word.word.ilike(f"%{word}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(Word.sort_order.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    words = list(result.scalars().all())

    return paginate(total, [format_word(w) for w in words])


async def _recount_book(db: AsyncSession, book_id: int) -> None:
    """重算词书单词数

    ⚠️ 2026-10-23 修：原来批量导入写的是 `count + len(word_list)`，
       而 `count` 是**插入之前**统计的，前面又已经 `db.add` 过这批词 ——
       于是每导一次，数字就在原有基础上多叠一遍（导 10 个词，计数可能变 20）。

       现在统一"以库里实际条数为准"：单条与批量、新增与删除都调这一个函数，
       不存在两套算法漂移的可能。
    """
    cnt = await db.scalar(
        select(func.count()).select_from(Word).where(Word.book_id == book_id)
    )
    await db.execute(
        update(WordBook).where(WordBook.book_id == book_id).values(word_count=int(cnt or 0))
    )


@router.post("/words/words")
async def create_word(
    bookId: int = Query(...),
    word: str = Query(...),
    phonetic: Optional[str] = Query(None),
    translation: Optional[str] = Query(None),
    example: Optional[str] = Query(None),
    audioUrl: Optional[str] = Query(None),
    sortOrder: Optional[int] = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    book, err = await _get_owned_book(db, bookId, _uid(current_user), for_write=True)
    if err:
        return err

    word_obj = Word(
        book_id=bookId,
        word=word,
        phonetic=phonetic,
        translation=translation,
        example=example,
        audio_url=audioUrl,
        sort_order=sortOrder,
    )
    db.add(word_obj)
    await db.flush()

    await _recount_book(db, bookId)
    return success(format_word(word_obj))


@router.put("/words/words")
async def update_word(
    wordId: int = Query(...),
    word: Optional[str] = Query(None),
    phonetic: Optional[str] = Query(None),
    translation: Optional[str] = Query(None),
    example: Optional[str] = Query(None),
    audioUrl: Optional[str] = Query(None),
    sortOrder: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    word_obj = (
        await db.execute(select(Word).where(Word.word_id == wordId))
    ).scalar_one_or_none()
    if not word_obj:
        return error("单词不存在")

    # 单词的归属由它所属的词书决定
    _book, err = await _get_owned_book(db, word_obj.book_id, _uid(current_user), for_write=True)
    if err:
        return err

    if word is not None:
        word_obj.word = word
    if phonetic is not None:
        word_obj.phonetic = phonetic
    if translation is not None:
        word_obj.translation = translation
    if example is not None:
        word_obj.example = example
    if audioUrl is not None:
        word_obj.audio_url = audioUrl
    if sortOrder is not None:
        word_obj.sort_order = sortOrder

    return success()


@router.delete("/words/words/{word_ids}")
async def delete_words(
    word_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除单词（只能删自己词书里的）"""
    uid = _uid(current_user)
    ids = []
    for raw in str(word_ids).split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            return error(f"单词 id 不合法：{raw}")
    if not ids:
        return error("请提供要删除的单词 id")

    # 只删「所属词书属于我」的单词。别人的 / 预置书里的静默跳过。
    my_book_ids = (
        await db.execute(
            select(WordBook.book_id).where(WordBook.user_id == uid)
        )
    ).scalars().all()
    my_ids = list(my_book_ids)
    if not my_ids:
        return success()

    touched_books = (
        await db.execute(
            select(Word.book_id).where(
                Word.word_id.in_(ids), Word.book_id.in_(my_ids)
            )
        )
    ).scalars().all()

    await db.execute(
        delete(Word).where(Word.word_id.in_(ids), Word.book_id.in_(my_ids))
    )

    for bid in set(touched_books):
        await _recount_book(db, bid)

    return success()


@router.post("/words/words/batch")
async def batch_create_words(
    bookId: int = Query(...),
    words: str = Query(...),  # JSON 格式的单词列表
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量添加单词"""
    import json

    book, err = await _get_owned_book(db, bookId, _uid(current_user), for_write=True)
    if err:
        return err

    try:
        word_list = json.loads(words)
    except json.JSONDecodeError:
        return error("单词列表不是合法 JSON")
    if not isinstance(word_list, list):
        return error("单词列表必须是数组")

    for item in word_list:
        if not isinstance(item, dict):
            continue
        word_text = str(item.get("word") or "").strip()
        if not word_text:
            continue
        db.add(
            Word(
                book_id=bookId,
                word=word_text,
                phonetic=item.get("phonetic"),
                translation=item.get("translation"),
                example=item.get("example"),
                audio_url=item.get("audioUrl"),
                sort_order=item.get("sortOrder", 0),
            )
        )

    await db.flush()
    await _recount_book(db, bookId)
    return success()


@router.post("/words/words/export")
async def export_words(
    bookId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出单词列表为 Excel"""
    query = select(Word)
    if bookId:
        query = query.where(Word.book_id == bookId)
    query = query.order_by(Word.sort_order.asc())

    result = await db.execute(query)
    words = list(result.scalars().all())

    rows = [{
        "wordId": w.word_id,
        "bookId": w.book_id,
        "word": w.word,
        "phonetic": w.phonetic or "",
        "translation": w.translation or "",
        "example": w.example or "",
        "sortOrder": w.sort_order,
        "createTime": w.create_time.isoformat() if w.create_time else "",
    } for w in words]

    headers = [
        {"key": "wordId", "label": "单词ID"},
        {"key": "bookId", "label": "词书ID"},
        {"key": "word", "label": "单词"},
        {"key": "phonetic", "label": "音标"},
        {"key": "translation", "label": "释义"},
        {"key": "example", "label": "例句"},
        {"key": "sortOrder", "label": "排序"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "words")


@router.post("/wordBooks/wordBooks/export")
async def export_word_books(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出词书列表为 Excel"""
    query = select(WordBook).where(WordBook.del_flag == "0").order_by(WordBook.create_time.desc())
    result = await db.execute(query)
    books = list(result.scalars().all())

    rows = [{
        "bookId": b.book_id,
        "bookName": b.book_name,
        "bookDescription": b.book_description or "",
        "wordCount": b.word_count,
        "coverImage": b.cover_image or "",
        "status": "正常" if b.status == "0" else "停用",
        "createTime": b.create_time.isoformat() if b.create_time else "",
    } for b in books]

    headers = [
        {"key": "bookId", "label": "词书ID"},
        {"key": "bookName", "label": "词书名称"},
        {"key": "bookDescription", "label": "描述"},
        {"key": "wordCount", "label": "单词数"},
        {"key": "coverImage", "label": "封面图"},
        {"key": "status", "label": "状态"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "wordBooks")
