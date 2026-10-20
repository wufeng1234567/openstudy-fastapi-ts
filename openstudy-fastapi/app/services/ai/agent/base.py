"""
Agent 工具契约层 —— 所有「自封装工具」都实现这里的 `AgentTool`

设计参考 springboot3 的 `com.openstudy.ai.agent.AgentTool` / `AgentToolRegistry`，
但按 Python 的习惯做了两点改造：

1. **工具自带参数 JSON Schema**（OpenAI Function Calling 格式），
   既用于原生 `bind_tools()`，也用于把「工具清单」注入系统提示词
   （未来接 ds-free 的提示词协议时直接复用同一份定义，避免两套描述漂移）。
2. **`execute()` 一律返回结构化的 dict**，而不是拼好的 JSON 字符串。
   字符串在 Java 里是为了省事，在 Python 里只会让「错误自纠」更难做：
   循环层需要读 `success` / `error` / `hint` 来决定怎么回灌给模型。

统一结果信封（所有工具必须遵守）::

    {"success": True,  ...业务字段...}                    # 成功
    {"success": False, "error": "人话错误", "hint": "怎么改"}   # 失败

`hint` 是**给模型看的修复建议**，会被原样回灌进对话，
是「报错自动纠正」能闭环的关键 —— 没有它，模型只能瞎猜哪里错了。
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class ToolContext:
    """一次工具调用的运行上下文

    工具不直接读全局状态，需要什么就从这里拿 —— 便于单测时传假 db。
    """

    #: AsyncSession（写操作走 `flush`，提交交给路由层的 `get_db`）
    db: Any = None
    #: 当前用户，所有查询都必须按它过滤（Agent 只能碰自己的数据）
    user_id: int = 0
    #: 会话 id（仅用于写记忆 / 诊断）
    session_id: Optional[str] = None
    #: 场景附加参数，由循环层注入（例如知识库 id）
    extra: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# 「回退」（undo）契约 —— 工具声明、账本记账、rollback_service 执行
# ===========================================================================
# 用户口径：「每轮聊天结束的末尾添加一个回退组件，点击后自动撤销本次的所有操作」。
#
# 三个角色，别混：
#   · **工具**声明 *怎么撤*（`AgentTool.undo_plan`）+ 把 *改前状态* 塞进信封的
#     `UNDO_BEFORE_KEY`；
#   · **账本**（`ai_agent_op_log`）由 `loop._execute_tool` 用**同一个会话**写一行；
#   · **执行**在 `services/ai/agent/rollback_service.py`。
#
# ⚠️ 本层只放**取值域常量**，不放任何业务判断 —— 工具与执行器都从这里取，
#    两边各写一份字符串必然漂移（历史教训见 `backend-ai-chain` 的「一份声明」条款）。

#: 工具把「改前状态」放进 `ok()` 信封时用的键。
#:
#: ⚠️ 这个键**必须**由 `loop._execute_tool` 摘掉，绝不能留在 `result` 里：
#:    它会随 `tool_result` 事件下发到界面、也会进 `ToolMessage` 回灌给模型 ——
#:    留着就等于把「上一版的旧值」喂给模型（既费 token，又可能被它当作用户意图）。
UNDO_BEFORE_KEY = "__undo_before__"

# ---- 撤销动作名（账本 `op` 列的取值域；执行器按它分派）----
#: 把行恢复成「未删除」（逻辑删 → 恢复）
OP_RESTORE = "restore"
#: 把行标成「已删除」（逻辑删；`create` 的逆操作）
OP_SOFT_DELETE = "soft_delete"
#: 把若干列写回 `before` 里的旧值（更新类的逆操作）
OP_RESTORE_FIELDS = "restore_fields"
#: 恢复一条被逻辑删的长期记忆（复用 `memory_service.restore_memory`）
OP_RESTORE_MEMORY = "restore_memory"
#: 物理删掉一行（`add_record` 新建那条的逆操作）
OP_DELETE_RECORD = "delete_record"
#: 把被物理删掉的行按 `before` 插回来（`remove_record` 的逆操作）
OP_INSERT_RECORD = "insert_record"
#: 把**整棵题库树**按 `before` 插回来（2026-10-20：题库 / 题目删除的逆操作）
#:
#: ⚠️ 为什么它不是 `insert_record` 的特例：`insert_record` 只管**一张表的一行**，
#:    而题库删除是**应用层级联**（`question_write_service.delete_banks` 一次清掉
#:    question_bank / question_main / question_sub / 三张个人标记表 / 笔记关联 /
#:    分享与领取记录）。回退必须把这一整组行按正确顺序、用**原主键**插回去，
#:    否则用户看到的是「库回来了但题目没了」，比不回来更糟。
#:
#: ⚠️ 为什么不用「软删除 + 读点全量过滤」那条路（已实测否决）：
#:    实测 `with_loader_criteria` 只对 ORM 实体 select 生效，对 **Core 列 select 无效**；
#:    而全仓按 `QuestionBank` / `QuestionMain` 的读点有 129 处，其中大量是 Core 列 select。
#:    漏任何一处，已删的题库就会重新出现在列表里 —— 那比「不能回退」严重得多。
#:    快照重插只碰**删除路径**，读取代码一行都不用改，回归风险为零。
OP_RESTORE_TREE = "restore_tree"

# ---- 不可回退 / 部分回退的原因码（账本 `reason` 列的取值域）----
#: 这个操作**没有声明** undo（默认不可回退 —— 宁可为空，绝不谎报）
REASON_NOT_DECLARED = "not_declared"
#: 目标表还是**物理删**（题库 / 题目：没有 del_flag 列），这一阶段做不了
REASON_MISSING_SOFT_DELETE = "missing_soft_delete"
#: 内容已被**物理销毁**（知识库文档 / 分块；分块带向量，重建要重算 embedding）
REASON_CONTENT_DESTROYED = "content_destroyed"
#: 影响到了**别人**（题库分享撤销：把领取方的记录置失效 + 已发通知收不回）
REASON_AFFECTS_OTHERS = "affects_others"
#: 拿不到**改前值**（更新类没有先读旧值 / 工具层看不到旧值）
REASON_NO_BEFORE_STATE = "no_before_state"
#: 回执里没有可定位的**行 id**，无从下手（防御分支，正常路径不该出现）
REASON_MISSING_TARGET_ID = "missing_target_id"
#: 本轮（V1）不做的操作
REASON_NOT_IN_V1 = "not_in_v1"
#: `undoable=True` 但只补回了一部分（如知识库恢复、里面的文档分块已没了）
REASON_DOCUMENTS_DESTROYED = "documents_destroyed"


def jsonable(value: Any) -> Any:
    """把要进 JSON 列的「改前值」转成可序列化形态（递归）。

    ⚠️ 为什么必须有它：账本的 `before` / `target_ids` 是 **JSON 列**，
    而 `before` 里天然会出现 `datetime`（如 `last_error_time`）与 `Decimal`
    （如题目的 `score`）—— `json.dumps` 遇到它们直接抛 `TypeError`，
    而抛在 `_execute_tool` 的记账环节 = 用户的写操作被判失败（或静默丢账）。
    `datetime` 一律转 ISO 字符串，执行器按**目标列的类型**再解析回 `datetime`
    （见 `rollback_service._coerce`），两边口径在这一个函数里对齐。
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def ok(**payload: Any) -> Dict[str, Any]:
    """成功信封"""
    return {"success": True, **payload}


def as_list(value: Any) -> List[Any]:
    """把「单个值 / 数组 / JSON 字符串 / 逗号串」统一成列表

    模型传数组的形态不总是规范（`"1,2"`、`'[1,2]'`、`1` 都可能），
    共享这一个归一处，工具侧就不必各自兜底。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001 - 退化成逗号分隔
            return [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def fail(error: str, hint: str = "", **payload: Any) -> Dict[str, Any]:
    """失败信封

    Args:
        error: 人话描述（会展示给用户，也会回灌给模型）
        hint:  给模型的修复建议，例如「action 只能是 list/create/... 之一」
    """
    result: Dict[str, Any] = {"success": False, "error": error}
    if hint:
        result["hint"] = hint
    result.update(payload)
    return result


class AgentTool(ABC):
    """Agent 工具基类

    子类声明五个类属性 + 实现 `execute()`：

        class BankManageTool(AgentTool):
            name = "bank_manage"
            description = "Manage question banks. ..."   # 英文（给模型）
            label = "题库管理"                            # 中文（只给界面）
            description_zh = "题库的增删改查：..."          # 中文（只给界面）
            parameters = {...}                           # JSON Schema

            async def execute(self, params, ctx):
                return ok(banks=[...])

    ⚠️ **两条道，语言不同，永远不许混**：

    ================================  ==========  ==================================
    类属性                            语言        谁读它
    ================================  ==========  ==================================
    `name` / `description` / `parameters`  **英文**    `registry.definitions()` / `describe()`（模型侧）
    `label` / `description_zh`        **中文**      `GET /ai/agent/tools` 的兄弟字段（**界面侧**）
    ================================  ==========  ==================================

    左侧三个属性会被拼进**全英文**的系统提示词与 Function Calling 的 `tools` 参数，
    写中文会让模型面对两套语言约定；右侧两个属性**只给前端渲染工具面板**，
    写英文则是把面向模型的文本直接糊到用户脸上（这正是本次要修的那个缺陷）。

    因此：`registry.definitions()` / `registry.describe()` **永远不许读** `label` /
    `description_zh` —— 那两条道是模型侧的。谁要渲染界面，走
    `api/v1/ai.py: _agent_tools_payload` 里的兄弟字段（在 `function` **外面**）。
    反向同理：`label` 里写英文、或把中文塞进 `description`，都会被
    `tests/_toolpref_probe.py` 的 CJK 守卫当场判红。
    """

    #: 工具名（模型看到的 function name），snake_case
    name: str = ""
    #: 工具描述（模型据此决定何时调用；要写清 action 取值与前置条件）—— **英文**
    description: str = ""
    #: 参数 JSON Schema（OpenAI Function Calling 格式，description 也是**英文**）
    parameters: Dict[str, Any] = {}
    #: 写操作工具（执行成功后需要留痕 / 写记忆）
    write_operation: bool = False

    # ------------------------------------------------------------------
    # 界面专用（**只在 `function` 外面下发，永远不进模型侧**）
    # ------------------------------------------------------------------
    #: 界面显示用的中文名（**只给前端看**）。`registry.definitions()` /
    #: `registry.describe()` 不许读它 —— 那两条道是模型侧的，语言必须是英文。
    label: str = ""
    #: 界面显示用的中文一句说明（**只给前端看**，同上）。
    #: 写「这个工具能干什么」+ action 取值，短句直说，不要逐字翻译 `description`。
    description_zh: str = ""

    # ------------------------------------------------------------------
    # 可选覆写
    # ------------------------------------------------------------------

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        """这个工具 + 这组参数是否需要用户确认后才能执行

        默认：不需要。写操作工具按 action 覆写（delete 必须确认，list 不需要）。
        """
        return False

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        """是否为**破坏性**操作（删除类）

        破坏性操作**即使 `autoConfirm` 开着也必须二次确认** —— 删错了没法撤销，
        让用户多点一次远比误删一个题库划算。子类按 action 覆写。
        """
        return False

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """按**数据规模 / 重要性**决定是否强制弹确认卡（旁路 `autoConfirm`）

        返回 True → 无论用户是否开启「自动执行」都要确认；默认 False（维持现状）。
        与另两个钩子的分工：
          · `needs_confirmation`：这是不是一个需要确认的**写操作**；
          · `is_destructive`：破坏性操作（删除类），一律强制确认；
          · `confirm_policy`：**规模足够大**的普通写操作（如一次导入几十道题、
            写入一大篇文档）也强制确认 —— 代价来自「量」，未必「不可逆」。

        ⚠️ 跑在**流式热路径**里：必须防御式解析参数，解析失败一律返回 False（不弹卡），
        绝不允许抛出。
        """
        return False

    async def preview(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """确认前展示给用户看的补充信息（如按 bank_id 反查出的题库名）

        默认无预览。失败**不允许**抛出 —— 循环层会兜住，但别依赖它。
        """
        return {}

    # ------------------------------------------------------------------
    # 回退（undo）—— 「这一轮做了什么」的逆操作由工具自己声明
    # ------------------------------------------------------------------

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """声明**这次操作该怎么撤**；返回 `None` = 不可回退（默认）。

        ⚠️⚠️ **默认不可回退**：没声明就是 `undoable=False`，账本会记
        `reason=not_declared`。宁可为空，绝不谎报 —— 「回退按钮点下去说成功了、
        数据其实没动」比「这条不支持回退」严重得多。

        返回的 dict（键名固定，取值域见本模块的 `OP_*` / `REASON_*`）::

            {
              "op": "restore",                 # 撤销动作名（OP_*）
              "targetTable": "note",           # 目标表（ORM __tablename__）
              "targetIds": [123],              # 目标行 id（批量操作给多个）
              "before": {...},                 # 改前状态（可选；更新类必需）
              "undoable": True,                # 省略时：op 非空即为 True
              "reason": "",                    # 非空时：不可回退的原因，或「部分回退」的说明
            }

        Args:
            params: 本次工具调用的参数（已归一化）。
            result: 工具回执（**已摘掉** `UNDO_BEFORE_KEY`）。
            before: 工具塞在信封里的「改前状态」（`UNDO_BEFORE_KEY` 的内容），
                由 `record_op` 原样传进来。

                ⚠️ **为什么要有这个参数**（2026-10-20 新增）：
                `_execute_tool` 会**先** `pop(UNDO_BEFORE_KEY)` 再调 `record_op`，
                而 `record_op` 才调本函数 —— 所以 `result` 里**永远看不到**那份快照。
                题库/题目删除的整树快照（`bank_tree_snapshot`）恰恰只能从 `before`
                里读，否则本函数无法判断「快照到底存下来了没有」，
                只能盲目声明「可回退」，最后在恢复阶段失败（比诚实地说
                「快照不可用」糟糕得多）。
                可选参数、默认 None —— 存量实现不改签名也照常工作。

        实现约定：
        · **只从 `result`（回执）/ `params` / `before` 里取 id** —— 三者都是给模型或
          账本看的，id 本来就该在回执里（如 `noteId` / `recordId`）；
        · 改前值**不要**塞进回执（那是给模型看的），走 `UNDO_BEFORE_KEY`：
          在 `execute()` 里 `return ok(..., **{UNDO_BEFORE_KEY: before})`，
          `_execute_tool` 会把它摘出来交给账本，并把 `before` 合并进本函数返回的 plan；
        · 本方法**不许抛异常**（循环层会兜住，但兜住的结果是「当作没声明」——
          见 `rollback_service.record_op` 的 try/except）。
        """
        return None

    # ------------------------------------------------------------------
    # 必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """执行工具

        ⚠️ 实现约定：
        - **不要抛异常**给调用方处理业务错误，返回 `fail(...)` 即可 ——
          异常只留给「真的不该发生」的情况，循环层也兜得住，但错误信息会
          丢失 `hint`，模型的自我纠正能力会变差。
        - 所有查询必须按 `ctx.user_id` 过滤。
        """
        raise NotImplementedError


__all__ = [
    "AgentTool",
    "ToolContext",
    "UNDO_BEFORE_KEY",
    "OP_RESTORE",
    "OP_SOFT_DELETE",
    "OP_RESTORE_FIELDS",
    "OP_RESTORE_MEMORY",
    "OP_DELETE_RECORD",
    "OP_INSERT_RECORD",
    "OP_RESTORE_TREE",
    "REASON_NOT_DECLARED",
    "REASON_MISSING_SOFT_DELETE",
    "REASON_CONTENT_DESTROYED",
    "REASON_AFFECTS_OTHERS",
    "REASON_NO_BEFORE_STATE",
    "REASON_MISSING_TARGET_ID",
    "REASON_NOT_IN_V1",
    "REASON_DOCUMENTS_DESTROYED",
    "as_list",
    "fail",
    "jsonable",
    "ok",
]
