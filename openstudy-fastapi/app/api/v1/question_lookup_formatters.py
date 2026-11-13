"""题库「查询 / 校验」类接口的纯响应格式化。

从 ``questions.py`` 抽出的 3 个纯函数：只把已查好的 ORM 对象 / 值拼成
``success`` 的 data dict，不连数据库、不做权限判断、不参与事务。
字段名、顺序、条件表达式逐字照搬原内联字典，响应行为不变。
"""


def simple_question_info_payload(question, bank_name) -> dict:
    """题目简要信息（simpleInfo）的返回对象。"""
    return {
        "questionId": question.id,
        "questionText": question.question_text,
        "questionType": question.question_type,
        "bankId": question.bank_id,
        "bankName": bank_name,
        "difficulty": question.difficulty,
        "analysis": question.analysis,
    }


def favorite_bank_exists_payload(bank) -> dict:
    """收藏题库存在性校验（bank 存在时）的返回对象。"""
    return {
        "exists": True,
        "bankId": bank.id,
        "bankName": bank.bank_name,
        "description": bank.description,
        "subject": bank.subject,
        "totalQuestions": bank.total_questions,
        "isPublic": bank.is_public,
        "userId": bank.user_id,
    }


def favorite_question_payload(q, text, bank_name) -> dict:
    """收藏题目存在性校验（question 存在时）的返回对象。"""
    return {
        "exists": True,
        "questionId": q.id,
        "title": (text[:50] + "...") if len(text) > 50 else text,
        "questionText": text,
        "bankId": q.bank_id,
        "bankName": bank_name,
        "difficulty": q.difficulty,
    }
