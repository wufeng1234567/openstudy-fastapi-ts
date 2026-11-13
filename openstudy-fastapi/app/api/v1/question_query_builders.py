"""题库接口共用的纯查询构造（消除重复的 ``select().where()`` 字面量）。

从 ``questions.py`` 抽出：`QuestionBank.id == ?` / `QuestionMain.id == ?` /
`SysUser.user_id == ?` 三种按主键查询在几十处路由里被逐字重复书写。
这里收拢成 3 个纯函数，只构造 SQLAlchemy ``Select``、不执行、不连库，
可直接单测（对比 ``str(stmt)``）；返回的语句与原表达式完全一致，
后续继续链式 ``.where()`` / ``await db.execute(...)`` 的用法不变。
"""

from sqlalchemy import select

from app.models.question import QuestionBank, QuestionMain
from app.models.user import SysUser


def bank_by_id_query(bank_id):
    """select(QuestionBank).where(QuestionBank.id == bank_id)"""
    return select(QuestionBank).where(QuestionBank.id == bank_id)


def question_by_id_query(question_id):
    """select(QuestionMain).where(QuestionMain.id == question_id)"""
    return select(QuestionMain).where(QuestionMain.id == question_id)


def user_id_query(user_id):
    """select(SysUser.user_id).where(SysUser.user_id == user_id)"""
    return select(SysUser.user_id).where(SysUser.user_id == user_id)
