"""
学习统计的只读服务 —— 给 `learning_stats` 工具用

⚠️ 本模块**故意不重写一句 SQL**：它直接调用 `app/api/v1/user_stats.py` 里那五个
路由处理函数（FastAPI 的 `@router.get(...)` 装饰器返回的就是原函数），把
`success()` 信封里的 `data` 取出来。

为什么宁可「绕」一下也不写一份更干净的查询
------------------------------------------
这些数字用户在自己的「学习统计」页面上都能看到。**Agent 报出来的必须与页面上
一模一样** —— 两边各写一份 SQL，迟早会漂移（某次只在一侧修了 bug，用户就会觉得
助手在胡说）。这与「一个声明只写一遍」是同一条规则，不是图省事。

越权检查为什么不在这里
----------------------
这五个端点**没有任何按 userId 取的入参**，`user_id` 只从登录态拿
（`current_user.get("user_id")`）。所以调用它们不可能造出越权：我们传进去的是
`{"user_id": int(ctx.user_id)}`，而 `ctx.user_id` 来自服务端解析的登录态。
反过来，如果哪天有人给这些端点加了 `userId` 入参，本模块就会跟着一起错
—— 那种改动应当被 review 拦下（见 `backend-db-security.md` 的 IDOR 一节）。

改的是什么
----------
只做**展示层键名归一**，不碰任何数字：

· `byQuestionType` 里的 `type` / `typeName` → `questionType` / `questionTypeText`。
  前端的字段字典对 `questionTypeText` 有「有文案就不显示数字」的规则，
  对 `questionType` 有题型枚举翻译；沿用原名（`type`）则两样都拿不到，
  用户会看到一行原始英文键名 + 一个裸数字。
其余字段一律原样透传。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

#: ⚠️ 导入的是**路由模块**：`@router.get` 装饰器返回的就是原函数本身
#: （`router.get(path)` → `decorator(func)` → `return func`），所以可以直接 await。
#: 反向依赖是不存在的（`user_stats` 只依赖 database / core / models），不会有环。
from app.api.v1 import user_stats as _routes

#: `get_trend` 的入参边界（与路由签名上的 `Query(7, ge=1, le=90)` 保持一致 ——
#: 直接调用函数会绕过 FastAPI 的校验，所以这里必须自己钳一次）
TREND_MIN_DAYS = 1
TREND_MAX_DAYS = 90
TREND_DEFAULT_DAYS = 7


def _unwrap(res: Any) -> Any:
    """拆 `success()` 信封；非 200 一律当错误抛（调用方会转成 `fail()`）"""
    if not isinstance(res, dict) or res.get("code") != 200:
        msg = res.get("msg") if isinstance(res, dict) else "返回体不是 JSON 对象"
        raise ValueError(str(msg or "查询失败"))
    return res.get("data")


def _rename_question_type(items: Any) -> List[Dict[str, Any]]:
    """`[{type, typeName, count}]` → `[{questionType, questionTypeText, count}]`

    **只改键名**：数字、排序、条数一个都没动 —— 见模块 docstring 的说明。
    """
    out: List[Dict[str, Any]] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "questionType": row.get("type"),
                "questionTypeText": row.get("typeName"),
                "count": row.get("count"),
            }
        )
    return out


async def overview(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """总览：收藏题目/题库数、错题数、斩题数、练习次数、正确率…"""
    data = _unwrap(await _routes.get_overview(db=db, current_user={"user_id": int(user_id)}))
    data = dict(data or {})
    if "byQuestionType" in data:
        data["byQuestionType"] = _rename_question_type(data["byQuestionType"])
    return data


async def by_subject(db: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
    """按科目分组：题库数 / 收藏题目数 / 错题数 / 斩题数"""
    data = _unwrap(await _routes.get_by_subject(db=db, current_user={"user_id": int(user_id)}))
    return list(data or [])


async def trend(
    db: AsyncSession, user_id: int, days: int = TREND_DEFAULT_DAYS
) -> List[Dict[str, Any]]:
    """最近 N 天的学习趋势（每天一行，没有数据的天也补 0）"""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = TREND_DEFAULT_DAYS
    days = max(TREND_MIN_DAYS, min(TREND_MAX_DAYS, days))
    data = _unwrap(
        await _routes.get_trend(
            days=days, db=db, current_user={"user_id": int(user_id)}
        )
    )
    return list(data or [])


async def error_analysis(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """错题分析：总数 / 待消灭 / 已掌握 / 掌握率 + 按难度·题型·科目分组 + TOP5"""
    data = _unwrap(
        await _routes.get_error_analysis(db=db, current_user={"user_id": int(user_id)})
    )
    data = dict(data or {})
    if "byQuestionType" in data:
        data["byQuestionType"] = _rename_question_type(data["byQuestionType"])
    return data


async def growth(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """成长记录：加入日期 / 学习天数 / 连续天数 / 累计收藏 / 里程碑"""
    data = _unwrap(await _routes.get_growth(db=db, current_user={"user_id": int(user_id)}))
    return dict(data or {})


__all__ = [
    "TREND_DEFAULT_DAYS",
    "TREND_MAX_DAYS",
    "TREND_MIN_DAYS",
    "by_subject",
    "error_analysis",
    "growth",
    "overview",
    "trend",
]
