"""题库「批量检查」接口的纯结果格式化。

从 ``questions.py`` 抽出的重复实现：`batch_check_favorite_question` /
`batch_check_error` / `batch_check_marked` 三个端点各手写了一份相同的
「已有 id 集合 → {questionId(str): bool}」拼装。这里收拢成一个纯函数，
不连数据库、不依赖 FastAPI，可直接单测。

``if not payload.questionIds: return success({})`` 的短路分支仍留在各路由内。
"""


def batch_check_result(rows, question_ids) -> dict:
    """把查询结果行与请求的 id 列表拼成 {str(id): bool} 响应 data。"""
    existing_ids = {row[0] for row in rows}
    return {str(qid): (qid in existing_ids) for qid in question_ids}
