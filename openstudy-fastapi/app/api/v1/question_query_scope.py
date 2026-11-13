"""题库列表 / 导出接口共用的「归属范围」查询构造（纯 query 构造，无 DB I/O）。

从 ``questions.py`` 抽出的重复实现：4 组「列表 / 导出」端点共 8 处手写相同的
身份分支 —— 管理员可按 userId 过滤（不传则看全部），普通用户强制只看自己。
这里收拢成一个纯函数，给定 query + 模型类 + 身份信息返回新 query，可直接单测
生成的 SQL；判定条件与 where 表达式逐字照搬，权限行为不变。
"""

from __future__ import annotations


def apply_owner_scope(query, model, *, is_admin: bool, current_id, user_id=None):
    """按当前身份收窄查询归属；权限语义与原内联 if/else 完全一致。"""
    if is_admin:
        # 后台管理：传 userId 则按该用户筛选，不传则查看全部用户
        if user_id is not None:
            query = query.where(model.user_id == user_id)
    else:
        # 普通用户：只能看自己的错题
        query = query.where(model.user_id == current_id)
    return query
