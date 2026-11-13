"""Agent 循环的**确认判定与删除合并**（从 `loop.py` 抽出）。

  · **`needs_user_confirmation`** —— 这次操作要不要弹确认卡片（口径见函数注释）
  · **`coalesce_delete_tool_calls`** —— 把同一轮里「同一个工具、多次单对象 delete」
    合并成一次 `delete_many`
  · **`_is_batch_delete_draft` / `_batch_delete_ids` / `_apply_selected_keys`**
    —— 批量删除勾选卡的**收窄**逻辑（用户勾了哪些就只删哪些）

⚠️ 本模块**不做 IO、不碰数据库**，全是纯判定 —— 可独立测试。
   `loop.py` 侧照旧把这些名字 import 进来 → **外部的 `loop.XXX` 引用照旧可用**
   （`sub_agent.py` 的 `loop_mod.needs_user_confirmation` 等一律不受影响）。

⚠️ 确认卡的**时序与挂起 / 唤醒**仍然留在 `loop.py`（`_pending_confirms`、
   `_pending_decisions`、`_await_user_confirmation`、`resolve_confirmation`）——
   本模块只回答「**要不要问**」与「**问的时候带什么**」，不碰挂起状态。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.ai.agent.base import AgentTool


#: 「单对象删除」→（批量动作名, 批量参数名, 单值参数名）
#: 只收录**真正等价**的组合：delete 能删的，delete_many 都能批量删。
_DELETE_MERGE_MAP: Dict[str, Dict[str, str]] = {
    "knowledge_base_manage": {
        "action": "delete",
        "many_action": "delete_many",
        "many_field": "kb_ids",
        "one_field": "kb_id",
    },
    "bank_manage": {
        "action": "delete",
        "many_action": "delete_many",
        "many_field": "bank_ids",
        "one_field": "bank_id",
    },
    "note_manage": {
        "action": "delete",
        "many_action": "delete_many",
        "many_field": "note_ids",
        "one_field": "note_id",
    },
    "question_manage": {
        "action": "delete",
        "many_action": "delete_many",
        "many_field": "question_ids",
        "one_field": "question_id",
    },
}


def coalesce_delete_tool_calls(
    tool_calls: List[Any],
) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    """把同一轮里「同一个工具、多次单对象 delete」合并成一次 `delete_many`

    背景（用户 2026-10-17）：「删 12 个知识库」时模型会循环发起 12 个 `delete` 调用。
    本循环**串行执行**每个调用，第一个 `delete` 就弹确认卡并**挂起等用户**，
    于是用户只看到第一张卡（kbId=584），根本走不到第 2~12 个。提示词约束不可靠 ——
    必须在执行前把调用列表归一。

    Returns:
        (新的 tool_calls, 合并信息 or None)
        合并信息形如 `{"tool": "knowledge_base_manage", "ids": [..], "count": 12}`，
        供前端提示「已把 N 次删除合并成一次批量删除」。
    """
    if not tool_calls:
        return tool_calls, None

    # 按工具分组：哪些是「可合并的单对象删除」
    groups: Dict[str, List[int]] = {}
    for idx, call in enumerate(tool_calls):
        name = str((call or {}).get("name") or "")
        spec = _DELETE_MERGE_MAP.get(name)
        if not spec:
            continue
        args = (call or {}).get("args") or {}
        if str(args.get("action") or "") != spec["action"]:
            continue
        if args.get(spec["one_field"]) is None:
            continue
        groups.setdefault(name, []).append(idx)

    # 只有 2 个以上才值得合并（单个 delete 保持原样，用户体验不变）
    mergeable = {k: v for k, v in groups.items() if len(v) >= 2}
    if not mergeable:
        return tool_calls, None

    # 一次只合并**一个工具**的多个删除（同一轮里通常也只会有一种）。
    # 多个工具都在批量删的情况：按工具逐个合并，但确认卡会用第一条的语义；
    # 这种极端场景交给模型下一轮自己处理（不在这里堆复杂度）。
    tool_name = max(mergeable, key=lambda k: len(mergeable[k]))
    idxs = mergeable[tool_name]
    spec = _DELETE_MERGE_MAP[tool_name]

    ids: List[int] = []
    for idx in idxs:
        args = tool_calls[idx].get("args") or {}
        try:
            value = int(args.get(spec["one_field"]))
        except (TypeError, ValueError):
            continue
        if value not in ids:
            ids.append(value)
    if len(ids) < 2:
        return tool_calls, None

    # 保留第一个 delete 的 call_id 与其余参数（题库/题目可能有额外的定位字段）
    first = tool_calls[idxs[0]]
    merged_args: Dict[str, Any] = dict(first.get("args") or {})
    merged_args["action"] = spec["many_action"]
    merged_args[spec["many_field"]] = ids
    merged_args.pop(spec["one_field"], None)
    # 题库按名字删的另一路在批量里没有意义（勾选卡给的是 ID）
    merged_args.pop("bank_names", None)

    merged_call = {
        "name": tool_name,
        "args": merged_args,
        "id": first.get("id") or "call_merged",
    }

    # 重建调用列表：被合并的那些位置上只留第一个，其余删掉
    drop = set(idxs[1:])
    new_calls: List[Any] = []
    for idx, call in enumerate(tool_calls):
        if idx in drop:
            continue
        new_calls.append(merged_call if idx == idxs[0] else call)

    logger.info(
        "[agent] 合并 {} 次 {} → 1 次 {}（ids={}）",
        len(ids), spec["action"], spec["many_action"], ids,
    )
    return new_calls, {
        "tool": tool_name,
        "action": spec["many_action"],
        "ids": ids,
        "count": len(ids),
    }


def needs_user_confirmation(
    tool: AgentTool,
    params: Dict[str, Any],
    auto_confirm: bool,
    confirmed_writes: Optional[Any] = None,
) -> bool:
    """是否需要弹确认卡片

    三种情形：
      1. 用户关掉了「自动执行」（`auto_confirm=False`）→ 所有写操作都确认；
      2. **破坏性操作（删除类）→ 无论自动执行是否开启都必须确认**；
      3. 规模闸门（工具自带的 `confirm_policy`）→ 首次确认，**本轮内同类动作不再重复问**。

    ⚠️ 原来这里写的是「删错无法撤销」——2026-09-23 起**不再准确**：记忆 / 笔记 /
    知识库（库行）/ 题目标记这几类已经**可回退**（用户点轮末的「回退」撤这一轮，
    见 `rollback_service`）。但题库 / 题目 / 知识库文档分块 / 撤销分享**仍是不可逆的**
    （物理删或影响他人），所以第 2 条**一个字都不用放宽**：确认是给「代价高」留的，
    不是给「不可逆」留的 —— 别因为「反正能回退」就把破坏性操作移出确认流程。

    ⚠️ 第 3 条为什么可以「本轮只问一次」（2026-10-17 用户报的 bug）：
        `question_manage.batch_import` 在 **≥5 题** 时强制确认，
        `knowledge_ingest.from_text` 在 **≥3000 字 / ≥8 块** 时强制确认。
        模型把 40 道题拆成 15+14+11 的三批导入、把知识点分几块写库时，
        **每一批都命中闸门** → 一次任务连弹 6 张确认卡，用户原话是
        「反复让我确认执行导入题目和知识库之类的确认卡片 很奇怪」。

        闸门的本意是「这么大的写入，先让你看一眼再落库」，而不是「每批都问一遍」。
        用户在**同一轮**里对同一工具的同一动作点过一次「确认」，就视为已授权，
        后续批次直接执行。判据只按 `tool:action`（`GuardState.confirmed_writes`），
        不按参数 —— 第二批的题目内容不同，但「我要导入题目」这个意愿是同一个。

        ⚠️ 破坏性操作（第 2 条）**不受**这个"已批准"影响：删 N 次就要确认 N 次，
           因为每一次删的东西都不一样、后果不可逆。
    """
    if not tool.needs_confirmation(params):
        return False
    if tool.is_destructive(params):
        return True

    action = str(params.get("action") or "")
    # 规模闸门：工具可声明自己的确认策略（base 里的可选钩子；不存在时 getattr 兜底）。
    policy = getattr(tool, "confirm_policy", None)
    if callable(policy) and policy(params):
        # 本轮已批准过同一工具的同一动作 → 不再重复弹卡
        if confirmed_writes is not None and hasattr(confirmed_writes, "is_confirmed"):
            if confirmed_writes.is_confirmed(tool.name, action):
                return False
        return True
    return not auto_confirm


def _is_batch_delete_draft(tool: AgentTool, params: Dict[str, Any]) -> bool:
    """这个工具调用是否走「批量删除勾选卡」（见各工具的 `delete_many` 动作）"""
    action = str(params.get("action") or "")
    if action != "delete_many":
        return False
    return tool.name in (
        "knowledge_base_manage",
        "bank_manage",
        "question_manage",
        "note_manage",
    )


def _batch_delete_ids(tool: AgentTool, params: Dict[str, Any]) -> List[int]:
    """读回批量删除参数里的 ID 列表（用于判断「用户一个都没勾」）"""
    field = {
        "knowledge_base_manage": "kb_ids",
        "bank_manage": "bank_ids",
        "question_manage": "question_ids",
        "note_manage": "note_ids",
    }.get(tool.name)
    if not field:
        return []
    return [int(v) for v in (params.get(field) or []) if v is not None]


def _apply_selected_keys(
    tool: AgentTool, params: Dict[str, Any], edited: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """把用户勾选结果写回工具的批量参数（`kb_ids` / `bank_ids` / ...）

    Returns:
        新参数 dict；`None` = 这次 edited 不适用（调用方退回原参数）。
        用户全不选时返回的名单为空 —— 调用方据此按「用户取消」处理。
    """
    raw = edited.get("selectedKeys")
    if not isinstance(raw, list):
        return None

    # `key` 形如 `kb:584` / `bank:12` / `question:33` / `note:7`
    ids: List[int] = []
    for key in raw:
        text = str(key or "")
        _prefix, _sep, num = text.partition(":")
        try:
            ids.append(int(num))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))

    # 各工具批量参数名不同（与工具 schema 保持一致）
    field = {
        "knowledge_base_manage": "kb_ids",
        "bank_manage": "bank_ids",
        "question_manage": "question_ids",
        "note_manage": "note_ids",
    }.get(tool.name)
    if not field:
        return None

    new_params = dict(params)
    new_params[field] = ids
    # 按名字删的那一路在勾选模式下没有意义（勾的是 ID），清掉避免重复/歧义
    for extra in ("bank_names", "question_indexes"):
        new_params.pop(extra, None)
    logger.info(
        "[agent] 按勾选结果收窄批量删除：{} {} → {} 项", tool.name, field, len(ids)
    )
    return new_params
