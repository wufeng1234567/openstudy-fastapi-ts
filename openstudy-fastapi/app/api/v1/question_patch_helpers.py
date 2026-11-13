"""题库接口里「把请求体可选字段写入 ORM 对象」的纯辅助。

从 ``questions.py`` 抽出的低风险纯函数：只读 payload、写 ORM 对象属性，
不连数据库、不做权限判断、不参与事务、不改响应。
与既有 ``question_field_helpers.py`` 的 ``_apply_*_fields`` 属同一族。

每个字段的判定条件与赋值表达式都逐字照搬原路由内联块。
"""


def _apply_question_fields(question, payload) -> None:
    """update_question：只覆盖请求里显式传入的主题字段，None 表示不动。"""
    if payload.bankId is not None:
        question.bank_id = payload.bankId
    if payload.questionType is not None:
        question.question_type = payload.questionType
    if payload.questionText is not None:
        question.question_text = payload.questionText
    if payload.content is not None:
        question.content = payload.content
    if payload.options is not None:
        question.options = payload.options
    if payload.answer is not None:
        question.answer = payload.answer
    if payload.questionAnalysis is not None:
        question.analysis = payload.questionAnalysis
    if payload.difficulty is not None:
        question.difficulty = payload.difficulty
    if payload.sortOrder is not None:
        question.sort_order = payload.sortOrder
    if payload.score is not None:
        question.score = payload.score
    if payload.status is not None:
        question.status = payload.status


def _apply_error_optional_fields(record, payload) -> None:
    """错题记录新增/修改/练习上报共用的 3 个可选字段，None 表示不动。"""
    if payload.notes is not None:
        record.notes = payload.notes
    if payload.tags is not None:
        record.tags = payload.tags
    if payload.difficultyRating is not None:
        record.difficulty_rating = payload.difficultyRating
