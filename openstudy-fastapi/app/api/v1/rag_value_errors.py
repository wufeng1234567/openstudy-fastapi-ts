"""RAG 微课接口的统一 ValueError → 400 响应格式化。

从 ``rag.py`` 抽出：微课编辑/重排/重生成/插入/导入 5 个端点各自手写了一遍
``except ValueError as e: return error(str(e), code=400)``。这里收拢成一个纯函数，
只把异常格式化成 400 响应，不含 async / DB / 权限逻辑，可直接单测。

调用方仍保留 ``except ValueError as e`` 的 except 块与后面的 ``except Exception``
兜底，异常传播与响应形状不变。
"""

from app.core.response import error


def value_error_400(exc: ValueError):
    """把 ValueError 转成 code=400 的 error 响应。"""
    return error(str(exc), code=400)
