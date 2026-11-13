"""RAG 查询参数的纯解析辅助。

从 ``rag.py`` 抽出的重复实现：`get_study_graph` / `get_study_plan` 里
``bankIds`` / ``restDays`` / ``sectionIndexes`` 共 4 处手写相同的
「空串返回 []、否则按逗号切分转 int」逻辑。这里收拢成一个纯函数，
不依赖 FastAPI / 数据库，可直接单测。

非法项仍抛 ``ValueError``，由各路由按原有文案转成 400 响应；
空串（含全空白）仍返回空列表，行为不变。
"""

from __future__ import annotations


def parse_csv_ints(value: str) -> list[int]:
    """把逗号分隔的整数查询参数解析为 int 列表；空串返回 []；非法项抛 ValueError。"""
    if not value.strip():
        return []
    return [int(x) for x in value.split(",") if x.strip()]
