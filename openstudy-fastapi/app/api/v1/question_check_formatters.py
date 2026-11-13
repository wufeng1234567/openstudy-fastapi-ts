"""题库「存在性校验」类接口的纯响应格式化。

从 ``questions.py`` 抽出的 3 个纯函数：只把已查好的 ORM 对象 / 布尔值拼成
``success`` 的 data dict，不连数据库、不做权限判断、不参与事务。
字段名、顺序、条件表达式逐字照搬原内联字典，响应行为不变。
"""


def check_question_payload(question, bank_name) -> dict:
    """题目存在时 checkQuestionExists 的返回对象。"""
    return {
        "exists": True,
        "questionId": question.id,
        "questionText": question.question_text,
        "bankId": question.bank_id,
        "bankName": bank_name,
        "difficulty": question.difficulty,
    }


def check_user_payload(user) -> dict:
    """用户存在时 checkUserExists 的返回对象。"""
    return {
        "exists": True,
        "userId": user.user_id,
        "userName": user.user_name,
        "nickName": user.nick_name,
    }


def check_question_and_user_payload(
    question_exists: bool,
    user_exists: bool,
    user,
    user_id: int,
    question_id: int,
    question,
) -> dict:
    """同时校验题目与用户时的返回对象（question / user 均可能为 None）。"""
    return {
        "questionValid": question_exists,
        "questionExists": question_exists,
        "userValid": user_exists,
        "userExists": user_exists,
        "allValid": question_exists and user_exists,
        "userId": user_id,
        "userName": user.user_name if user else None,
        "nickName": user.nick_name if user else None,
        "questionId": question_id,
        "questionText": question.question_text if question else None,
        "bankId": question.bank_id if question else None,
        "difficulty": question.difficulty if question else None,
    }
