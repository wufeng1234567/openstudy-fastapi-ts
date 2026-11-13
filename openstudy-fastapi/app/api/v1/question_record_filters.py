"""题库「错题 / 斩题」列表与导出端点共用的查询过滤条件（纯 query 构造，无 DB I/O）。

从 ``questions.py`` 抽出的重复实现：错题 列表/导出、斩题 列表/导出 共 4 处手写
的 where 条件。收拢成两个纯函数，给定 query + 可选筛选值返回新 query，
可直接单测生成的 SQL。

⚠️ 刻意保留的预存在行为差异：错题列表的 ``beginErrorTime`` 走
``_begin_of_date()``，错题导出却直接用原值。因此日期边界值由**调用方**预先
算好再以 ``begin_error_time`` / ``end_error_time`` 传入，helper 只做
``>=`` / ``<=`` 比较，不替调用方决定归一化方式 —— 两边行为逐字不变。

斩题导出端点本来就没有 ``errorTimesBeforeMark`` / ``reviewCount`` 两个查询参数，
调用时不传即可（helper 里相应 where 被跳过），与原行为一致。
"""

from app.models.question import UserQuestionError, UserQuestionMarked


def apply_error_filters(
    query,
    *,
    status=None,
    questionId=None,
    bankId=None,
    errorCount=None,
    notes=None,
    difficultyRating=None,
    isMastered=None,
    begin_error_time=None,
    end_error_time=None,
):
    """错题列表 / 导出共用的筛选条件（日期边界由调用方预先算好传入）。"""
    # 默认只查活跃记录，除非显式指定 status
    if status is not None:
        query = query.where(UserQuestionError.status == status)
    else:
        query = query.where(UserQuestionError.status == 1)

    # 动态过滤条件
    if questionId is not None:
        query = query.where(UserQuestionError.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionError.bank_id == bankId)
    if errorCount is not None:
        query = query.where(UserQuestionError.error_count == errorCount)
    if notes:
        query = query.where(UserQuestionError.notes.ilike(f"%{notes}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionError.difficulty_rating == difficultyRating)
    if isMastered is not None:
        query = query.where(UserQuestionError.is_mastered == isMastered)
    if begin_error_time is not None:
        query = query.where(UserQuestionError.error_time >= begin_error_time)
    if end_error_time is not None:
        query = query.where(UserQuestionError.error_time <= end_error_time)
    return query


def apply_marked_filters(
    query,
    *,
    markedStatus=None,
    questionId=None,
    bankId=None,
    markedType=None,
    difficultyLevel=None,
    isMastered=None,
    errorTimesBeforeMark=None,
    reviewCount=None,
    notes=None,
    tags=None,
    begin_create_time=None,
    end_create_time=None,
):
    """斩题列表 / 导出共用的筛选条件（日期边界由调用方预先算好传入）。"""
    # 默认只看有效斩题，除非显式指定 markedStatus（后台可查已失效记录）
    if markedStatus is not None:
        query = query.where(UserQuestionMarked.marked_status == markedStatus)
    else:
        query = query.where(UserQuestionMarked.marked_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionMarked.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionMarked.bank_id == bankId)
    if markedType is not None:
        query = query.where(UserQuestionMarked.marked_type == markedType)
    if difficultyLevel is not None:
        query = query.where(UserQuestionMarked.difficulty_level == difficultyLevel)
    if isMastered is not None:
        query = query.where(UserQuestionMarked.is_mastered == isMastered)
    if errorTimesBeforeMark is not None:
        query = query.where(UserQuestionMarked.error_times_before_mark == errorTimesBeforeMark)
    if reviewCount is not None:
        query = query.where(UserQuestionMarked.review_count == reviewCount)
    if notes:
        query = query.where(UserQuestionMarked.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionMarked.tags.ilike(f"%{tags}%"))
    if begin_create_time is not None:
        query = query.where(UserQuestionMarked.create_time >= begin_create_time)
    if end_create_time is not None:
        query = query.where(UserQuestionMarked.create_time <= end_create_time)
    return query
