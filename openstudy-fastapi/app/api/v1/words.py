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


def format_word_book(book):
    return {
        "bookId": book.book_id,
        "bookName": book.book_name,
        "bookDescription": book.book_description,
        "wordCount": book.word_count,
        "coverImage": book.cover_image,
        "status": book.status,
        "createTime": book.create_time.isoformat() if book.create_time else None,
    }


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
    query = select(WordBook).where(WordBook.del_flag == "0")
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
):
    query = select(WordBook).where(WordBook.del_flag == "0").order_by(WordBook.create_time.desc())
    result = await db.execute(query)
    books = list(result.scalars().all())
    return success([format_word_book(b) for b in books])


@router.get("/wordBooks/wordBooks/{book_id}")
async def get_word_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
):
    query = select(WordBook).where(WordBook.book_id == book_id, WordBook.del_flag == "0")
    result = await db.execute(query)
    book = result.scalar_one_or_none()
    if not book:
        return error("词书不存在")
    return success(format_word_book(book))


@router.post("/wordBooks/wordBooks")
async def create_word_book(
    bookName: str = Query(...),
    bookDescription: Optional[str] = Query(None),
    coverImage: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    book = WordBook(
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
    query = select(WordBook).where(WordBook.book_id == bookId, WordBook.del_flag == "0")
    result = await db.execute(query)
    book = result.scalar_one_or_none()
    if not book:
        return error("词书不存在")

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

    ⚠️ 这里 `current_user` **拿到了却没用**，是一个**已知的、有意暂时保留**的缺口：
    `word_books` 没有归属列（实测列：book_id / book_name / book_description /
    word_count / cover_image / status / del_flag / create_time，没有 user_id），
    所以任何登录用户拿一串 id 就能软删任意词书。

    2026-09-22 实测**不能**按「非管理员一律 403」来堵 —— 那会把**用户端功能改瘫**：
      · `src/views/dictation/dictation/index.vue:25,41` 的「删除单词本」按钮是
        `v-hasRole="['common']"`（**普通用户**），`:603` 调的就是本端点；
      · 菜单实测：`sys_menu` 2006/2018（单词本 / 单词练习）都授给了角色 `common`，
        且 2010「单词本删除」= `wordBooks:wordBooks:remove` 也在 `common` 名下；
      · 真实用户（uid=105 `user1`）的角色就是 `common` —— 加 403 他立刻删不掉自己的单词本。
    ⚠️ **不要**改成「非管理员一律 403」，**也不要**按权限点 `wordBooks:wordBooks:remove`
    做后端闸门 —— 后者对本例是**假修**：`common` 本来就持有该权限点（见上），闸门等于
    没闸，只挡得住没有该权限的账号。「词书是全局资源、只有管理员能删」这条也没有依据：
    删词书本来就是普通用户功能（team-lead 2026-09-22 复核后同意不改）。
      · 角色实测（`sys_user_role` + `sys_role`）：全库**只有 uid=1（admin）是 `admin`**，
        uid=2/103/104/105/106 **全是 `common`**，而用户自己的真实数据在 uid=105（user1）
        —— 所以「只有管理员能删」= 把除 admin 外的所有账号（含用户平时用的那个）锁在门外。
      · 现状实测（**别把这个洞写成「用户数据正在被删」**）：v2 里英语模块是**空的** ——
        `word_books` **0 行**、`words` **0 行**（对照 `courses` 10 行），
        即目前没有任何真实词书可伤；`addWordBooks` 与它同属一个开放端点，建了才谈得上删。
    保持原状，等定下后续两条路：
      ① **给 `word_books` 加归属列**（`user_id`），用户只列/只删自己的 —— 真正的修法，
         但属于**加功能**：已按 information_schema 实测该表只有 8 列且无归属列，
         所以这是**真要改表**（+ 前端只列自己的），建议和题库那条线一起排；
      ② **先只给词书加恢复入口** —— 它本来就已经是软删（`del_flag='2'`），加恢复最便宜，
         而且与「用户端删除全部逻辑删除、一键恢复」的总方向一致。
    """
    ids = [int(id) for id in book_ids.split(",")]
    stmt = update(WordBook).where(WordBook.book_id.in_(ids)).values(del_flag="2")
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
    query = select(Word)
    if bookId:
        query = query.where(Word.book_id == bookId)
    if word:
        query = query.where(Word.word.ilike(f"%{word}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(Word.sort_order.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    words = list(result.scalars().all())

    return paginate(total, [format_word(w) for w in words])


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

    # 更新词书单词数
    book_query = select(WordBook).where(WordBook.book_id == bookId)
    book_result = await db.execute(book_query)
    book = book_result.scalar_one_or_none()
    if book:
        count_query = select(func.count()).where(Word.book_id == bookId)
        count = await db.scalar(count_query)
        book.word_count = count

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
    query = select(Word).where(Word.word_id == wordId)
    result = await db.execute(query)
    word_obj = result.scalar_one_or_none()
    if not word_obj:
        return error("单词不存在")

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
    ids = [int(id) for id in word_ids.split(",")]
    stmt = delete(Word).where(Word.word_id.in_(ids))
    await db.execute(stmt)
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
    word_list = json.loads(words)

    for item in word_list:
        word_obj = Word(
            book_id=bookId,
            word=item.get("word", ""),
            phonetic=item.get("phonetic"),
            translation=item.get("translation"),
            example=item.get("example"),
            audio_url=item.get("audioUrl"),
            sort_order=item.get("sortOrder", 0),
        )
        db.add(word_obj)

    # 更新词书单词数
    book_query = select(WordBook).where(WordBook.book_id == bookId)
    book_result = await db.execute(book_query)
    book = book_result.scalar_one_or_none()
    if book:
        count_query = select(func.count()).where(Word.book_id == bookId)
        count = await db.scalar(count_query)
        book.word_count = count + len(word_list)

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
