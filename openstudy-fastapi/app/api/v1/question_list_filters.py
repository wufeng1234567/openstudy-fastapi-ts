"""题库「列表 / 导出」接口共用的查询过滤条件（纯 query 构造，无数据库 I/O）。

从 ``questions.py`` 抽出的重复实现：收藏题库、收藏题目两组端点各自在
列表接口与导出接口里手写了一份完全相同的 where 条件。这里收拢成两个
纯函数，给定 query + 可选筛选值返回新 query，可直接单测生成的 SQL。

权限相关的 ``is_admin`` / 归属判定仍留在各路由内，本模块不涉及权限逻辑。
条件顺序、ilike 写法、日期边界（``_begin_of_date`` / ``_end_of_date``）
均逐字照搬，查询行为不变。
"""

from sqlalchemy import select

from app.models.question import QuestionBank, UserBankFavorite, UserQuestionFavorite

from .question_helpers import _begin_of_date, _end_of_date


def apply_favorite_bank_filters(
    query,
    *,
    favoriteStatus=None,
    bankId=None,
    bankName=None,
    notes=None,
    tags=None,
    isStarred=None,
    studyCount=None,
    lastStudyTime=None,
):
    """收藏题库列表 / 导出共用的筛选条件。"""
    # 默认只看有效收藏，除非显式指定 favoriteStatus（后台可查已失效记录）
    if favoriteStatus is not None:
        query = query.where(UserBankFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserBankFavorite.favorite_status == 1)

    if bankId is not None:
        query = query.where(UserBankFavorite.bank_id == bankId)
    if bankName:
        query = query.where(UserBankFavorite.bank_id.in_(
            select(QuestionBank.id).where(QuestionBank.bank_name.ilike(f"%{bankName}%"))
        ))
    if notes:
        query = query.where(UserBankFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserBankFavorite.tags.ilike(f"%{tags}%"))
    if isStarred is not None:
        query = query.where(UserBankFavorite.is_starred == isStarred)
    if studyCount is not None:
        query = query.where(UserBankFavorite.study_count == studyCount)
    if lastStudyTime:
        query = query.where(
            UserBankFavorite.last_study_time >= _begin_of_date(lastStudyTime),
            UserBankFavorite.last_study_time <= _end_of_date(lastStudyTime),
        )
    return query


def apply_favorite_question_filters(
    query,
    *,
    favoriteStatus=None,
    questionId=None,
    bankId=None,
    notes=None,
    tags=None,
    difficultyRating=None,
    errorTimes=None,
    correctTimes=None,
    reviewCount=None,
    isStarred=None,
    lastReviewTime=None,
    nextReviewTime=None,
):
    """收藏题目列表 / 导出共用的筛选条件。"""
    # 默认只看有效收藏，除非显式指定 favoriteStatus（后台可查已取消/待复习等状态）
    if favoriteStatus is not None:
        query = query.where(UserQuestionFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserQuestionFavorite.favorite_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionFavorite.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionFavorite.bank_id == bankId)
    if notes:
        query = query.where(UserQuestionFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionFavorite.tags.ilike(f"%{tags}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionFavorite.difficulty_rating == difficultyRating)
    if errorTimes is not None:
        query = query.where(UserQuestionFavorite.error_times == errorTimes)
    if correctTimes is not None:
        query = query.where(UserQuestionFavorite.correct_times == correctTimes)
    if reviewCount is not None:
        query = query.where(UserQuestionFavorite.review_count == reviewCount)
    if isStarred is not None:
        query = query.where(UserQuestionFavorite.is_starred == isStarred)
    if lastReviewTime:
        query = query.where(
            UserQuestionFavorite.last_review_time >= _begin_of_date(lastReviewTime),
            UserQuestionFavorite.last_review_time <= _end_of_date(lastReviewTime),
        )
    if nextReviewTime:
        query = query.where(
            UserQuestionFavorite.next_review_time >= _begin_of_date(nextReviewTime),
            UserQuestionFavorite.next_review_time <= _end_of_date(nextReviewTime),
        )
    return query
