"""
题库/题目仓库（对齐 DB 实际 schema，物理删除）
"""

from typing import Optional, Tuple, List
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.question import QuestionBank, QuestionMain, QuestionSub


class QuestionBankRepository:
    """题库仓库"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_banks(
        self,
        bank_name: Optional[str] = None,
        status: Optional[str] = None,
        subject: Optional[str] = None,
        user_id: Optional[int] = None,
        page_num: int = 1,
        page_size: int = 10,
    ) -> Tuple[int, List[QuestionBank]]:
        """查询题库列表（status='0' 为正常）"""
        query = select(QuestionBank).where(QuestionBank.status == "0")

        if bank_name:
            query = query.where(QuestionBank.bank_name.ilike(f"%{bank_name}%"))
        if status:
            query = query.where(QuestionBank.status == status)
        if subject:
            query = query.where(QuestionBank.subject == subject)
        if user_id:
            query = query.where(QuestionBank.user_id == user_id)

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # 分页
        query = query.order_by(QuestionBank.create_time.desc())
        query = query.offset((page_num - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return total, list(result.scalars().all())

    async def get_by_id(self, bank_id: int) -> Optional[QuestionBank]:
        """根据ID查询题库"""
        query = select(QuestionBank).where(QuestionBank.id == bank_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, bank: QuestionBank) -> QuestionBank:
        """创建题库"""
        self.db.add(bank)
        await self.db.flush()
        await self.db.refresh(bank)
        return bank

    async def update(self, bank: QuestionBank) -> None:
        """更新题库"""
        await self.db.merge(bank)

    async def delete_by_ids(self, ids: List[int]) -> None:
        """物理删除题库（DB ON DELETE CASCADE 会自动清理子表）"""
        stmt = delete(QuestionBank).where(QuestionBank.id.in_(ids))
        await self.db.execute(stmt)

    async def update_total_questions(self, bank_id: int) -> None:
        """重算题库题目总数（COUNT status='0' 的题目，与 SpringBoot 一致）"""
        count_query = (
            select(func.count())
            .select_from(QuestionMain)
            .where(
                QuestionMain.bank_id == bank_id,
                QuestionMain.status == "0",
            )
        )
        count = await self.db.scalar(count_query)

        from sqlalchemy import update as sa_update
        stmt = (
            sa_update(QuestionBank)
            .where(QuestionBank.id == bank_id)
            .values(total_questions=count or 0)
        )
        await self.db.execute(stmt)


class QuestionRepository:
    """题目仓库"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_questions(
        self,
        bank_id: Optional[int] = None,
        question_type: Optional[int] = None,
        difficulty: Optional[int] = None,
        page_num: int = 1,
        page_size: int = 10,
    ) -> Tuple[int, List[QuestionMain]]:
        """查询题目列表（status='0' 为正常）"""
        query = select(QuestionMain).where(QuestionMain.status == "0")

        if bank_id:
            query = query.where(QuestionMain.bank_id == bank_id)
        if question_type:
            query = query.where(QuestionMain.question_type == question_type)
        if difficulty:
            query = query.where(QuestionMain.difficulty == difficulty)

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # 分页（按 sort_order, id 排序，与 SpringBoot 一致）
        query = query.order_by(QuestionMain.sort_order, QuestionMain.id)
        query = query.offset((page_num - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return total, list(result.scalars().all())

    async def get_by_id(self, question_id: int) -> Optional[QuestionMain]:
        """根据ID查询题目（含子题）"""
        query = select(QuestionMain).where(
            QuestionMain.id == question_id,
        ).options(selectinload(QuestionMain.sub_questions))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, question: QuestionMain) -> QuestionMain:
        """创建题目"""
        self.db.add(question)
        await self.db.flush()
        await self.db.refresh(question)
        return question

    async def update(self, question: QuestionMain) -> None:
        """更新题目"""
        await self.db.merge(question)

    async def delete_by_ids(self, ids: List[int]) -> None:
        """物理删除题目（DB ON DELETE CASCADE 会自动清理子表）"""
        stmt = delete(QuestionMain).where(QuestionMain.id.in_(ids))
        await self.db.execute(stmt)

    async def delete_sub_questions(self, main_id: int) -> None:
        """删除指定主题的所有子题（全量替换时使用）"""
        stmt = delete(QuestionSub).where(QuestionSub.main_id == main_id)
        await self.db.execute(stmt)

    async def get_bank_ids_by_question_ids(self, ids: List[int]) -> List[int]:
        """根据题目ID列表查询受影响的题库ID（去重）"""
        query = select(QuestionMain.bank_id).where(QuestionMain.id.in_(ids)).distinct()
        result = await self.db.execute(query)
        return [row[0] for row in result.all()]
