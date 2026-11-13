"""题库接口里把请求体字段写入 ORM 对象的纯映射辅助。

从 ``questions.py`` 抽出的两个 ``_apply_*`` 函数：只读 payload、写 ORM 对象，
不碰数据库会话、不发请求。``questions.py`` 会把这两个名字重新导入自己的
模块命名空间，路由调用点保持不变。

与 ``question_helpers.py`` 里已有的 ``_apply_favorite_question_fields`` 属同一族；
本模块不改动那个既有文件（超出授权范围），仅收拢剩余两个。
"""

from .question_helpers import _parse_dt


def _apply_favorite_bank_fields(fav, payload):
    """把请求体里的收藏业务字段写入 ORM 对象（新增/修改/恢复共用）

    只覆盖请求里显式传入的字段，None 表示"不动该字段"，避免误清空。
    """
    if getattr(payload, "notes", None) is not None:
        fav.notes = payload.notes
    if getattr(payload, "tags", None) is not None:
        fav.tags = payload.tags
    if getattr(payload, "sortOrder", None) is not None:
        fav.sort_order = payload.sortOrder
    if getattr(payload, "isStarred", None) is not None:
        fav.is_starred = payload.isStarred
    if getattr(payload, "favoriteStatus", None) is not None:
        fav.favorite_status = payload.favoriteStatus
    if getattr(payload, "studyCount", None) is not None:
        fav.study_count = payload.studyCount
    if getattr(payload, "lastStudyTime", None) is not None:
        # 允许传空字符串表示清空
        fav.last_study_time = _parse_dt(payload.lastStudyTime) if payload.lastStudyTime else None
    return fav


def _apply_marked_fields(marked, payload, question=None):
    """把请求体里的斩题业务字段写入 ORM 对象（新增/修改/恢复共用）

    只覆盖请求里显式传入的字段，None 表示"不动该字段"，避免误清空。
    """
    if payload.notes is not None:
        marked.notes = payload.notes
    if getattr(payload, "tags", None) is not None:
        marked.tags = payload.tags
    if payload.markedType is not None:
        marked.marked_type = payload.markedType
    if payload.difficultyLevel is not None:
        marked.difficulty_level = payload.difficultyLevel
    if getattr(payload, "errorTimesBeforeMark", None) is not None:
        marked.error_times_before_mark = payload.errorTimesBeforeMark
    if getattr(payload, "correctTimesBeforeMark", None) is not None:
        marked.correct_times_before_mark = payload.correctTimesBeforeMark
    if getattr(payload, "reviewCount", None) is not None:
        marked.review_count = payload.reviewCount
    if getattr(payload, "lastReviewTime", None):
        marked.last_review_time = _parse_dt(payload.lastReviewTime)
    if getattr(payload, "nextReviewTime", None):
        marked.next_review_time = _parse_dt(payload.nextReviewTime)
    if getattr(payload, "isMastered", None) is not None:
        marked.is_mastered = payload.isMastered
    if getattr(payload, "masteryDate", None):
        marked.mastery_date = _parse_dt(payload.masteryDate)
    if getattr(payload, "markedStatus", None) is not None:
        marked.marked_status = payload.markedStatus
    if getattr(payload, "bankId", None) is not None:
        marked.bank_id = payload.bankId
    return marked
