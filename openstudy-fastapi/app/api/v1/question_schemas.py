"""题库接口的请求体模型（Pydantic v2）。

从 ``questions.py`` 抽出的纯 Schema 声明，不含业务逻辑。``questions.py``
会把该名字重新导入自己的模块命名空间：``save_bank_with_questions`` 等路由
在函数定义期直接求值类型注解（本模块与 questions.py 均未启用
``from __future__ import annotations``），因此回导入是必须的。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QuestionBankSaveRequest(BaseModel):
    """题库搭建一次性保存（单事务）。

    前端「保存/发布」不再逐题发多个 HTTP：题库基本信息、题目新增/更新、
    子题全量替换、显式删除旧题全部在本请求里完成。任一步失败整体回滚，
    不会留下「新题写了一半、旧题已删」的半成品。
    """
    bankId: Optional[int] = None
    bankName: str
    subject: Optional[str] = None
    description: Optional[str] = None
    coverImage: Optional[str] = None
    status: Optional[str] = "0"
    isPublic: Optional[int] = 0
    allowFork: Optional[int] = 1
    questions: List[Dict[str, Any]] = []
    deleteQuestionIds: List[int] = []
