"""
Agent 工具执行守卫 —— 「**报错自动纠正**」的落地层

这一层不碰业务，只做四件事，但正是这四件事决定了 Agent 能不能自己从错误里爬出来：

1. **参数归一化**（`normalize_params`）
   模型最爱犯的三种小错，在调用工具前先顺手治好：
   · 驼峰字段名（`bankName` / `questionType`）→ schema 里的 snake_case；
   · 数字传成字符串或浮点（`"167"` / `167.0`）→ 按 schema 转 `int`；
   · 该给字符串的字段给了数组（`options: ["A","B"]`）→ JSON 序列化成字符串。

2. **参数校验**（`validate_params`）
   必填缺失 / 枚举值非法 / 类型转不动 → **不执行工具**，直接把
   `{"success": false, "error": ..., "hint": ...}` 当成工具结果回灌进对话。
   ⚠️ 这一条是核心：把「参数错误」变成模型能读到的**反馈**，它下一轮就会自己改。
   如果直接让工具抛异常，异常文本里没有 `hint`，模型只能瞎猜。

3. **死循环检测**（`note_call`）
   `list → list → list` 这种原地打转必须打断，否则烧完 15 轮预算也不会产出。

4. **结果压缩**（`compress_result`）
   一次 `list` 可能返回几十个题库的完整 JSON，全塞回上下文既慢又贵，
   而且容易把模型「淹」得住不下笔。压缩成一行摘要即可。

状态集中在 `GuardState` 里，由循环层持有并传入 —— 守卫本身无状态，方便单测。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.ai.agent.base import AgentTool

#: 驼峰 → 下划线（模型的通用习惯，schema 里全用 snake_case）
_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")

#: 回灌给模型的 list / search 最多保留几条（留 ID 之后条数要收着点，别把上下文撑爆）
MAX_COMPRESS_ITEMS = 20

#: 常见同义字段名 → schema 正式名
_ALIASES = {
    "id": "bank_id",
    "bankid": "bank_id",
    "bankname": "bank_name",
    "questionid": "question_id",
    "questionindex": "question_index",
    "questiontype": "question_type",
    "questiontext": "question_text",
    "questioncontent": "question_text",
    "questionanalysis": "analysis",
    "correctanswer": "answer",
    "subquestions": "sub_questions",
    "hassubquestions": "has_sub_questions",
    "articlecontent": "content",
    "text": "question_text",
    "type": "question_type",
    "keyword": "question_text",
}

#: 工具描述里不写的内部字段（注入用）
_INTERNAL_PREFIX = "_"


def params_payload(params: Dict[str, Any]) -> str:
    """把参数序列化成**稳定字符串**（剔除 `_` 前缀的内部字段）

    「稳定」指 `sort_keys=True`：同一组参数无论字典顺序如何都得到同一串。

    ⚠️ 这是**唯一一份**序列化实现，两个用途共用它：
      · `ExecutionGuard.call_key()` —— 死循环检测的指纹；
      · `params_hash()` —— 确认票据的 `paramsHash`。
    各写一套必然漂移，而漂移的后果很具体：票据验签时对不上 → 用户确认完却执行不了，
    或者更糟 —— 「用户确认的那组参数」与「真正执行的那组参数」不是同一组。
    """
    try:
        return json.dumps(
            {k: v for k, v in (params or {}).items() if not k.startswith(_INTERNAL_PREFIX)},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    except Exception:  # noqa: BLE001 - 序列化不了就退化成 str（与 call_key 同口径）
        return str(params)


def params_hash(params: Dict[str, Any]) -> str:
    """参数指纹（sha256 hex）—— 确认票据用它把「用户确认的那组参数」钉死"""
    return hashlib.sha256(params_payload(params).encode("utf-8")).hexdigest()


def _snake(name: str) -> str:
    return _CAMEL.sub("_", name).lower()


@dataclass
class GuardState:
    """一次 Agent 运行期间的守卫状态"""

    #: 上一次工具调用的指纹（`tool:args`），用于死循环检测
    last_call_key: Optional[str] = None
    #: 连续重复次数
    repeat_streak: int = 0
    #: 每个工具被调用的总次数
    tool_totals: Dict[str, int] = field(default_factory=dict)
    #: 模型自我纠正次数（参数非法 / 工具报错后重试的轮次）
    corrections: int = 0
    #: 累计错误（用于最后收尾时如实汇报）
    errors: List[str] = field(default_factory=list)
    #: 本轮已经批准过的写操作「工具:动作」集合（见 `mark_confirmed` / `is_confirmed`）。
    #:
    #: ⚠️ 为什么需要它（2026-10-17 用户报的 bug）：
    #:    `question_manage.batch_import` 有「≥5 题强制确认」、`knowledge_ingest.from_text`
    #:    有「≥3000 字/≥8 块强制确认」的**规模闸门**。模型把 40 道题拆成 3 批（15/14/11）
    #:    导入时，每批都命中闸门 ⇒ 用户要连点 3 次「确认执行」；再加上写入同一个知识库的
    #:    多个文本块，一次任务里能弹 6 张确认卡 —— 用户的原话是「反复让我确认…很奇怪」。
    #:    闸门本意是「这么大的写入，先让你看一眼」，而不是「每批都问一遍」：
    #:    用户在**同一轮**里对同一工具的同类写操作点过一次「确认」，就应当视为已授权。
    #:
    #: 只按 `tool:action` 记，**不按参数**：同一轮里第二次导入的题不一样，但用户的意愿一样。
    #: 破坏性操作（删除类）不受它影响，永远走确认（见 `needs_user_confirmation`）。
    confirmed_writes: Set[str] = field(default_factory=set)

    def write_key(self, tool_name: str, action: str) -> str:
        return f"{tool_name}:{(action or '').strip().lower()}"

    def mark_confirmed(self, tool_name: str, action: str) -> None:
        """记录一次「用户已批准」的写操作"""
        self.confirmed_writes.add(self.write_key(tool_name, action))

    def is_confirmed(self, tool_name: str, action: str) -> bool:
        """本轮是否已批准过同一工具的同一动作"""
        return self.write_key(tool_name, action) in self.confirmed_writes


class ExecutionGuard:
    """参数处理 + 结果压缩 + 死循环检测（无状态，状态在 `GuardState`）

    Args:
        same_call_limit: 同一 `tool:args` 连续出现多少次算「原地打转」
        same_tool_limit: 同一工具在一次运行里最多调用多少次（防长尾）

            ⚠️ 别把这个值调小（2026-10-27 实测教训）：
               `question_flag_manage` / `bank_manage` 这类工具用 `action`
               区分十来种操作，一次正常的整理流程（收藏、斩题、错题、
               查三类列表、标记已掌握、取消…）轻易就 9~15 次，
               而每一次的参数都不同 —— 那是正常干活，不是打转。
               真正的死循环由 `repeat_streak`（参数完全相同）拦，
               比"调了几次"精准得多。
    """

    def __init__(self, same_call_limit: int = 2, same_tool_limit: int = 24) -> None:
        self.same_call_limit = same_call_limit
        self.same_tool_limit = same_tool_limit

    # ------------------------------------------------------------------
    # 参数
    # ------------------------------------------------------------------

    def normalize_params(
        self, tool: AgentTool, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """字段名 / 类型归一化（只修不报错，修不动的留给校验层）"""
        raw = dict(params or {})
        schema_props: Dict[str, Any] = (tool.parameters or {}).get("properties", {}) or {}

        normalized: Dict[str, Any] = {}
        for key, value in raw.items():
            if key.startswith(_INTERNAL_PREFIX):
                # 循环层注入的内部字段（如 _knowledge_base_id）原样透传
                normalized[key] = value
                continue

            target = key if key in schema_props else None
            if target is None:
                snake = _snake(key)
                if snake in schema_props:
                    target = snake
                else:
                    lowered = key.lower()
                    candidate = _ALIASES.get(lowered) or _ALIASES.get(snake)
                    if candidate and candidate in schema_props and candidate not in normalized:
                        target = candidate
                    else:
                        target = key  # 保持原样，交给校验层报「未知参数」

            if target in normalized and normalized[target] not in (None, ""):
                continue  # 不覆盖已有值（同义字段出现两次时以先到的为准）
            normalized[target] = self._coerce(schema_props.get(target, {}), value)

        return normalized

    def _coerce(self, prop: Dict[str, Any], value: Any) -> Any:
        """按 JSON Schema 的 type 做一次温和的类型转换"""
        expected = (prop or {}).get("type")

        if value is None:
            return None

        if expected == "integer":
            return self._to_int(value)
        if expected == "number":
            number = self._to_float(value)
            return number if number is not None else value
        if expected == "boolean":
            if isinstance(value, str):
                low = value.strip().lower()
                if low in ("true", "1", "yes", "y", "是"):
                    return True
                if low in ("false", "0", "no", "n", "否"):
                    return False
            return value
        if expected == "string":
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple, dict)):
                # 典型：options 给了数组，工具侧期望 JSON 字符串
                try:
                    return json.dumps(value, ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    return str(value)
            return str(value)
        if expected == "array":
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, list) else [parsed]
                except Exception:  # noqa: BLE001
                    return [value] if value.strip() else []
            return value
        if expected == "object":
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, dict) else {"value": parsed}
                except Exception:  # noqa: BLE001
                    return {"value": value}
            return value

        # 没声明 type：只把枚举做大小写归一
        enum = (prop or {}).get("enum")
        if enum and isinstance(value, str):
            for candidate in enum:
                if str(candidate).lower() == value.strip().lower():
                    return candidate
        return value

    @staticmethod
    def _to_int(value: Any) -> Any:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return value
            try:
                return int(text)
            except ValueError:
                try:
                    return int(float(text))  # "167.0" / "167.9"
                except ValueError:
                    return value
        return value

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    def validate_params(
        self, tool: AgentTool, params: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        """校验归一化后的参数

        Returns:
            (errors, hints) —— `errors` 面向用户，`hints` 面向模型（怎么改）。
            两个都为空表示通过。
        """
        schema: Dict[str, Any] = tool.parameters or {}
        props: Dict[str, Any] = schema.get("properties") or {}
        required: List[str] = list(schema.get("required") or [])

        errors: List[str] = []
        hints: List[str] = []

        for key in required:
            value = params.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"缺少必填参数 {key}")
                desc = (props.get(key) or {}).get("description") or ""
                hints.append(f"必须提供 {key}（{desc}）" if desc else f"必须提供 {key}")

        for key, value in params.items():
            if key.startswith(_INTERNAL_PREFIX) or value is None:
                continue
            prop = props.get(key)
            if prop is None:
                errors.append(f"不支持的参数 {key}")
                hints.append(f"请只使用这些参数：{', '.join(props.keys())}")
                continue

            enum = prop.get("enum")
            if enum and value not in enum:
                errors.append(f"参数 {key} 取值非法：{value}")
                hints.append(f"{key} 只能是 {' / '.join(map(str, enum))} 之一")

            expected = prop.get("type")
            if expected == "integer" and not isinstance(value, int):
                errors.append(f"参数 {key} 需要整数，收到 {type(value).__name__}")
                hints.append(f"{key} 请传整数，例如 12（不要带引号或小数点）")
            elif expected == "string" and not isinstance(value, str):
                errors.append(f"参数 {key} 需要字符串")
                hints.append(f"{key} 请传字符串")

        # 业务级前置条件（跨字段）
        if tool.name == "question_manage":
            action = params.get("action")
            if action in ("create", "batch_import"):
                if action == "create" and not params.get("question_text"):
                    errors.append("create 动作缺少 question_text")
                    hints.append("创建题目必须给 question_text（题干）")
                if action == "batch_import" and not params.get("questions"):
                    errors.append("batch_import 动作缺少 questions")
                    hints.append(
                        "batch_import 必须给 questions（JSON 数组字符串，"
                        '形如 [{"questionType":1,"questionText":"...","answer":"0"}]）'
                    )
            # 注意：`search` **不要求**题库 —— 「帮我找关于二次函数的题」这类请求
            # 要在用户自己的全部题库里搜（题库给了就只在该题库内搜，是可选项）。
            if action in ("list", "create", "batch_import"):
                if not params.get("bank_id") and not params.get("bank_name"):
                    errors.append(f"{action} 动作需要 bank_id 或 bank_name")
                    hints.append("请提供 bank_name（题库名称）或 bank_id")
            if action in ("detail", "update", "delete"):
                if not params.get("question_id") and not params.get("question_index"):
                    errors.append(f"{action} 动作需要 question_id 或 question_index")
                    hints.append("请提供 question_id 或 question_index（第几题）")

        if tool.name == "bank_manage":
            action = params.get("action")
            if action in ("create", "delete_by_name") and not params.get("bank_name"):
                errors.append(f"{action} 动作需要 bank_name")
                hints.append("请提供 bank_name（题库名称）")
            if action in ("detail", "update", "delete") and not params.get("bank_id"):
                errors.append(f"{action} 动作需要 bank_id")
                hints.append("请提供 bank_id；如果只知道名称，请先调用 list 查询")

        return errors, hints

    # ------------------------------------------------------------------
    # 死循环
    # ------------------------------------------------------------------

    def call_key(self, tool_name: str, params: Dict[str, Any]) -> str:
        """工具调用的指纹（参数按键排序，保证同一调用得到同一指纹）

        序列化走模块级的 `params_payload()` —— 与确认票据的 `params_hash()` **同一份实现**
        （各自写一套会漂移，见那边的注释）。
        """
        return f"{tool_name}:{params_payload(params)}"

    def note_call(
        self, state: GuardState, tool_name: str, params: Dict[str, Any]
    ) -> Optional[str]:
        """记录一次调用；返回「需要中断」的原因，`None` 表示可以继续

        两种情况判定为打转：
        - 同一个 `tool:args` 连续重复到 `same_call_limit` 次；
        - 同一工具累计调用超过 `same_tool_limit` 次。

        ⚠️ 第二个判据只该拦「真的在打转」，不能拦「一个工具干很多件不同的事」
        （2026-10-27 修：用户实测被误杀）

        实测场景：用户让 AI 依次做「收藏 → 斩题 → 错题本 → 查三类列表 →
        标记已掌握 → 取消收藏」共 9 步，全部是**参数不同的正常操作**，
        但都落在 `question_flag_manage` 这一个工具上，
        于是第 9 次被拦下，回了一句「被调用了 9 次，超出上限，已停止」——
        用户看不懂，而且这一步真的没执行。

        这类"多功能工具"（`question_flag_manage` / `bank_manage` /
        `question_manage` / `note_manage`）用 `action` 区分十来种操作，
        一次完整的整理流程本来就该调很多次。所以：

          · `same_tool_limit` 默认从 8 提到 24
            （正常操作流程很少超过 24 步；真死循环会先被上面的
             `repeat_streak` 抓住 —— 那条判据看的是"参数完全相同"，更准）；
          · 真正的兜底仍然在：`MAX_AGENT_LOOPS = 12` 轮硬上限，
            每轮里工具的调用总量不可能无限增长。

        换句话说：**防死循环靠 `repeat_streak`（参数相同）+ 轮数上限，
        不靠"单个工具被调了几次"** —— 后者误伤正常的长流程。
        """
        key = self.call_key(tool_name, params)
        if key == state.last_call_key:
            state.repeat_streak += 1
        else:
            state.last_call_key = key
            state.repeat_streak = 1

        state.tool_totals[tool_name] = state.tool_totals.get(tool_name, 0) + 1

        if state.repeat_streak >= self.same_call_limit:
            return (
                f"检测到重复调用（{tool_name} 以完全相同的参数连续调用了 "
                f"{state.repeat_streak} 次），已自动停止以免空转"
            )
        if state.tool_totals[tool_name] > self.same_tool_limit:
            return (
                f"工具 {tool_name} 在一次任务里被调用了 "
                f"{state.tool_totals[tool_name]} 次，超出上限，已停止"
            )
        return None

    # ------------------------------------------------------------------
    # 结果压缩
    # ------------------------------------------------------------------

    def compress_result(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """把长结果压成摘要再回灌给模型（失败结果不压缩，模型需要看完整错误）

        ⚠️ 压缩**只能压「给人看的描述」，不能压掉「给模型用的标识」**。

        早期版本把 list / search 压成一串题干（`summary: "题干1；题干2…"`），
        `questionId` / `sortOrder` / `bankId` / `bankName` 全部丢掉 —— 于是模型
        永远拿不到定位题目所需的 ID，遇到「删掉某某那道题」只能
        `search → list → list` 一路翻，最后放弃并回头问用户。
        （已复现：见 tests/e2e_agent_api.py 的 F 组用例。）

        现在保留结构化字段，只截短 `text`、限制条数，并带上 `total` / `hasMore`
        让模型知道还能用 offset 继续翻。

        ⚠️ 前端 `api/ai/agentDsFree.ts: compressResult` 是这份逻辑的**镜像**
        （ds-free 链路跑在前端），改这里必须同步改那边。
        """
        if not isinstance(result, dict) or not result.get("success"):
            return result

        action = result.get("action")
        note = "完整字段已通过 tool_result 展示给用户，无需重复输出"

        if tool_name == "bank_manage" and action == "list":
            banks = result.get("banks") or result.get("items") or []
            if not isinstance(banks, list):
                return result

            # ⚠️ 口径与 question_manage 那一支**完全一致**（`bank_manage._list` 补了分页之后，
            # `banks` 只是**当前一页**）：`offset` / `total` 必须从工具结果里读，
            # 只回一页而不报总量的话，模型会把「本次返回 20 个」当成「一共 20 个」。
            # 读不到（老实现 / 别的调用方）时退化成「这一页就是全部」。
            offset = result.get("offset")
            offset = int(offset) if isinstance(offset, int) else 0
            total = result.get("total")
            total = int(total) if isinstance(total, int) else offset + len(banks)

            items: List[Dict[str, Any]] = []
            for bank in banks[:MAX_COMPRESS_ITEMS]:
                if not isinstance(bank, dict):
                    continue
                item: Dict[str, Any] = {
                    # bankId 必须留着：delete_many / update / detail 都认它，
                    # 而且工具 schema 里明确写了「bank_ids is preferred when known」
                    "bankId": bank.get("bankId") or bank.get("bank_id"),
                    "bankName": bank.get("bankName") or bank.get("bank_name") or "?",
                    "totalQuestions": bank.get("totalQuestions")
                    or bank.get("total_questions")
                    or 0,
                }
                if bank.get("subject"):
                    item["subject"] = bank["subject"]
                items.append(item)
            return {
                "success": True,
                "action": "list",
                "count": len(items),
                "total": total,
                "hasMore": offset + len(items) < total,
                "offset": offset,
                "banks": items,
                "note": "用 bankId（或 bank_name）继续 detail / update / delete；" + note,
            }

        if tool_name == "question_manage" and action in ("list", "search"):
            questions = result.get("questions") or result.get("items") or []
            if not isinstance(questions, list):
                return result

            offset = result.get("offset")
            offset = int(offset) if isinstance(offset, int) else 0
            total = result.get("total")
            total = int(total) if isinstance(total, int) else offset + len(questions)

            # `list` 在**顶层**带 bankId / bankName（单题库）；`search` 不带 ——
            # 它可能横跨多个题库，归属挂在**每条**上。跨库搜索时模型必须知道
            # 命中的是哪一库，否则删 / 改会落到错的库。
            top_bank_id = result.get("bankId") or result.get("bank_id")
            top_bank_name = result.get("bankName") or result.get("bank_name")

            items = []
            for i, question in enumerate(questions[:MAX_COMPRESS_ITEMS]):
                if not isinstance(question, dict):
                    continue
                text = question.get("questionText") or question.get("question_text") or ""
                item: Dict[str, Any] = {
                    # 1-based **绝对**题号（含 offset）—— 与 delete_many 的
                    # `question_indexes` 同一个口径（「resolved against the same
                    # order as list」），所以必须加上 offset 而不是页内序号
                    "questionIndex": offset + i + 1,
                    "questionId": question.get("questionId")
                    or question.get("question_id"),
                    "text": text[:50] + ("…" if len(text) > 50 else ""),
                }
                if not top_bank_id and (question.get("bankId") or question.get("bank_id")):
                    item["bankId"] = question.get("bankId") or question.get("bank_id")
                if not top_bank_name and (
                    question.get("bankName") or question.get("bank_name")
                ):
                    item["bankName"] = question.get("bankName") or question.get("bank_name")
                items.append(item)

            payload: Dict[str, Any] = {
                "success": True,
                "action": action,
                "count": len(items),
                "total": total,
                "hasMore": offset + len(items) < total,
                "offset": offset,
                "questions": items,
                "note": (
                    "定位题目请用 questionId（question_ids）或 questionIndex"
                    "（question_indexes，1-based），不要重复罗列题目内容；" + note
                ),
            }
            if top_bank_id:
                payload["bankId"] = top_bank_id
            if top_bank_name:
                payload["bankName"] = top_bank_name
            return payload

        return result


__all__ = ["ExecutionGuard", "GuardState", "params_hash", "params_payload"]
