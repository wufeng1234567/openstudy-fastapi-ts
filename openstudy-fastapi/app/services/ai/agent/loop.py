"""
Agent 循环（`LLM → 工具调用 → 执行 → 回灌 → 再 LLM`）

参考实现：springboot3 `com.openstudy.ai.agent.AgentService`（三阶段 Flux 循环）
+ `DsAgentLoopService`（DS 网页端那套提示词协议）。本项目这一版做了几处取舍：

| 关注点 | springboot3 | 这里 |
|---|---|---|
| 阶段划分 | 思考(非流式) → 工具(流式) → 回复(流式)，**三次 LLM 调用** | **一次**流式调用，同轮既吐文字又可能带 tool_calls（省一次往返，流式体验更好） |
| 工具调用 | 原生 Function Calling + 提示词协议双实现 | 先做原生（官方 API）；提示词协议留好接缝（工具描述已可从注册表取） |
| 报错自纠 | 错误文本回灌 + 死循环检测 | 同上，**额外**：参数归一化 / schema 校验 / 逐题 SAVEPOINT / 连续重复先警告再中断 |
| 轮数用尽 | 直接回一句「已达上限」 | 再做一次**不带工具**的调用，让模型给个收尾总结（用户至少知道做到哪了） |

## 事件契约（换行分隔的 JSON，前端 `api/ai/agent.ts` 依赖，改动要同步）

| type | 载荷 | 含义 |
|---|---|---|
| `meta` | `tools` / `model` | 开局下发，前端用于渲染工具清单 |
| `text` | `content` | 模型正文增量（可能是工具调用前的引子） |
| `thinking` | `content` | **模型深度思考的推理正文增量**（前端渲染成可折叠卡片） |
| `waiting` | `message` | **每一轮模型调用开始前**下发 → 前端显示「等待中」占位（工具执行完到下一轮回复之间不再空白） |
| `tool_start` | `tool` / `message` / `params` | 工具开始执行 |
| `tool_result` | `tool` / `action` / `success` / `message` / `data` | 工具执行完毕 |
| `self_correct` | `attempt` / `tool` / `reason` | **模型正在自我纠正**（参数非法或工具报错后重试） |
| `metrics` | `rounds` / `steps` / `llmMs` / `toolMs` / `firstTokenMs` / `firstTokenSamples` | **执行统计**（底部状态条用）。⚠️ **口径必须与 ds-free 链路逐字一致，别按字面猜**（实现处的注释见 `_metrics_event` 上方）：`rounds` = **完成的 LLM 往返数**（一轮 = 一次 `astream` 跑完，**抛异常的轮不算**）；`steps` = **模型本轮请求的工具调用条目数**（**在遍历工具前一次加完**，与遍历是否被打断**无关**；含「工具不存在」「参数校验不过」这些**没有真正执行**的 —— **不是**「工具执行次数」）；`llmMs` = LLM 调用累计耗时；`toolMs` = 工具**真正执行**的累计耗时（没执行的自然不占时间）。每轮 LLM 结束后发一次、该轮工具全跑完再发一次 → 计数与耗时**实时**上涨。⚠️ 这里发的一律是**本轮（单次提问）的累计值**，不是会话总量也不是增量 —— 前端负责把它累加成会话总量。`firstTokenMs` 是各轮平均值，**没有样本时是 `null`**（前端显示 `—`，别给 0）；`firstTokenSamples` 是它的**样本数**，供前端跨提问正确加权（平均值不能直接相加） |
| `warning` | `message` | 非致命问题（死循环警告 / 图片丢失 / 轮数用尽） |
| `error` | `message` | 致命错误，本轮结束 |
| `done` + `[DONE]` | — | 收尾（`[DONE]` 兼容既有解析器约定） |

## 语言策略（改代码前先读这条）

| 内容 | 语言 | 理由 |
|---|---|---|
| 系统提示词 / 工具 `description` / 参数 schema / 注册表枚举提示 | **英文** | 纯模型面向的「指令」，英文省 token 且指令跟随更稳；从不直接展示给用户 |
| 工具 `ok(message)` / `fail(error,hint)`、事件 `reason`/`message`、`_tool_start_message()` | **中文** | 会在前端执行时间线里**直接显示**给用户（UI 是中文） |
| 模型的最终回复 | **跟随用户提问语言** | 由 `prompts.AGENT_LANGUAGE_RULES` 约束 |

工具结果里的中文**不代表**模型要用中文回复 —— `AGENT_LANGUAGE_RULES` 里已显式说明
「tool results may come back in Chinese, that is not a language instruction」。
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import conversation_service, db_config, model_capabilities, prompts
from app.services.ai.agent.base import (
    UNDO_BEFORE_KEY,
    AgentTool,
    ToolContext,
    fail,
)
from app.services.ai.agent.confirm_ticket import (
    issue as issue_confirm_ticket,
    verify as verify_confirm_ticket,
)
from app.services.ai.agent.guard import ExecutionGuard, GuardState, params_hash
from app.services.ai.agent import memory_hook
from app.services.ai.agent import orchestrator
from app.services.ai.agent import roles as roles_mod
from app.services.ai.agent.loop_helpers import (
    detect_user_language as _detect_user_language,
    dumps as _dumps,
    friendly_llm_error as _friendly_llm_error,
    reasoning_of as _reasoning_of,
    safe_params as _safe_params,
    text_of as _text_of,
    tool_start_message as _tool_start_message,
)
from app.services.ai.agent import rollback_service
from app.services.ai.agent import runtime_context
from app.services.ai.agent import tool_pref_service
from app.services.ai.agent import agent_role_pref_service
from app.services.ai.agent.registry import ensure_tools_loaded, registry
from app.services.file_parser import IMAGE_MARKER_TMPL, build_marked_document

# ---------------------------------------------------------------------------
from app.services.ai.agent.loop_events import (
    error_event,
    text_event,
    thinking_event,
    tool_result_cancelled_event,
    tool_result_event,
    tool_start_event,
    warning_event,
    waiting_event,
)

from app.services.ai.agent.loop_tool_events import (
    tool_self_correction_event,
)

from app.services.ai.agent.loop_tool_result import (
    tool_result_message,
)
# 抽离出去的**纯辅助 / 常量 / 类型**模块（2026-11 可读性重构）
#
# 下面这些名字**原本就定义在 loop.py 里**，现在从配套模块 import 回来 ——
# 于是 `loop.XXX` / `from ...loop import XXX` 这些既有引用**一个字都不用改**。
#
# ⚠ 依赖方向单向：loop.py → 三个新模块；它们**不反向依赖** loop.py
#    （`loop_support` 零项目级 import，`base.py` / `file_parser` 也都没有回引），
#    因此不会形成循环依赖。
#
# ⚠ 标了 noqa 的那几个是**只出不进**的可见性保留：
#    它们在 loop.py 内已无调用点，但此前是 `loop.XXX` 的既有名字，
#    外部脚本可能按模块属性访问 —— 去掉就等于悄悄改了公开面。
# ---------------------------------------------------------------------------
from app.services.ai.agent.loop_support import (
    AgentRequest,
    DEFAULT_AGENT_PROMPT,
    DEFAULT_AGENT_TEMPERATURE,  # noqa: F401 - 只出不进：保留既有可见性
    DEAD_LOOP_STRIKES,
    MAX_AGENT_LOOPS,
    REASONING_DELTA_KEYS,  # noqa: F401 - 只出不进：保留既有可见性
    SAME_CALL_LIMIT,
    TAG_ATTACHMENTS,
    TAG_CONVERSATION_HISTORY,
    TAG_DOCUMENT,
    TAG_USER_REQUEST,
    _event,
    _safe_attr,  # noqa: F401 - 只产出：保留既有可见性
    _wrap_tag,
)
from app.services.ai.agent.loop_attachments import (
    _IMAGE_EXT,
    _attachment_field,  # noqa: F401 - 只产出：保留既有可见性
    _attachment_plain_text,  # noqa: F401 - 只产出：保留既有可见性
    _collect_attachments,
)
from app.services.ai.agent.loop_confirm_policy import (
    _apply_selected_keys,
    _batch_delete_ids,
    _DELETE_MERGE_MAP,  # noqa: F401 - 只产出：保留既有可见性
    _is_batch_delete_draft,
    coalesce_delete_tool_calls,
    needs_user_confirmation,
)
from app.services.ai.agent.loop_stream_helpers import (
    _async_empty_list,
    _disabled_fail,
    _read_decision,
    _resolve_turn_id,
    build_human_text,
    build_vision_blocks,
)
from app.services.ai.agent.loop_validation_formatters import params_validation_failure

#: 图片标记模板 —— 定义已挪到 `file_parser`
#:
#: ⚠️ 这是**数据标记**，不是提示词文案 —— 即使系统提示词全英文，它也保持中文：
#: 模型把它原样写进题干 → 工具用 `【图(\d+)】` 正则替换成 `<img>` → 缺一不可。
#: 别为了「全英文」把它改成 `[IMAGE_N]`，那会让整条图片链路失效。
#:
#: 挪家的原因：聊天链路（`chat_engine`）也要用同一套标记，两处各写一份必然漂移。
#: 这里直接 import 过来，`loop.IMAGE_MARKER_TMPL` / `loop.build_marked_document`
#: 这两个既有引用照旧可用。


# ============================================================
# 附件 → 带【图N】标记的正文
# ============================================================


def build_tool_context(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    extra: Dict[str, Any],
) -> ToolContext:
    """工具执行上下文。

    ⚠ 这三个基本字段（db / user_id / session_id）原本在**三处**各写一遍 ——
    尤其 `session_id or None` 这个归一化，新增调用点时很容易漏掉，
    结果就是「有的地方传空串、有的地方传 None」。收敛到一处就不会再漂。
    """
    return ToolContext(
        db=db,
        user_id=user_id,
        session_id=session_id or None,
        extra=extra,
    )


async def persist_agent_images(data_urls: List[str]) -> List[str]:
    """把图片 data URL 落盘，返回可访问 URL（规则与 `/common/upload` 完全一致）

    ⚠️ 必须落盘而不是把 base64 直接写进题目：题目正文是 TEXT 列，
    塞几张 data URL 就会把行撑爆，且前端渲染会巨慢。
    """
    from app.services.ai.chat_engine import data_url_to_bytes
    from app.utils.file_util import save_bytes

    urls: List[str] = []
    for index, raw in enumerate(data_urls or []):
        if not raw:
            urls.append("")
            continue
        try:
            content, mime = data_url_to_bytes(raw)
            ext = _IMAGE_EXT.get((mime or "").lower().split(";")[0].strip())
            if ext is None:
                urls.append("")
                logger.warning("[agent] 跳过非图片附件 {}（mime={}）", index, mime)
                continue
            result = await asyncio.to_thread(
                save_bytes, content, f"agent-image-{index + 1}{ext}", "upload"
            )
            urls.append(result["fileUrl"])
        except Exception as e:  # noqa: BLE001 - 单张图失败不影响任务
            logger.warning("[agent] 图片 {} 落盘失败: {}", index, e)
            urls.append("")
    return urls


# ============================================================
# 事件
# ============================================================


async def _load_user_agent_briefing(user_id: int) -> List[Dict[str, str]]:
    """读用户自定义智能体 → 通讯录项列表（`render_sub_agents_briefing` 的 `extra_agents`）

    ⚠️ fail-open：读库失败返回空列表（本轮只是"通讯录里少几个用户 Agent"，不该阻断对话）。
    与 `build_runtime_context` 一样**自己开会话**，故可与它 `asyncio.gather` 并行。
    """
    from app.services.ai.agent import agent_config_service

    try:
        out: List[Dict[str, str]] = []
        for a in await agent_config_service.list_agents(user_id):
            out.append(
                {
                    "key": f"user:{a.get('agentId')}",
                    "name": a.get("name") or "",
                    "capability": a.get("description") or a.get("personaPrompt") or "",
                }
            )
        return out
    except Exception as e:  # noqa: BLE001 - 通讯录读失败不该阻断本轮
        logger.warning("[agent] 读取用户智能体做通讯录失败: {}", e)
        return []


# ============================================================
# 主流程
# ============================================================


async def _execute_tool(
    tool: AgentTool, params: Dict[str, Any], ctx: ToolContext
) -> Dict[str, Any]:
    """执行一个工具，保证「永远返回结构化结果、永远不把异常抛给循环」

    - 写操作包一层 SAVEPOINT：失败只回滚这次工具，不污染外层的会话事务
      （否则一次失败的写入会让后续所有 SQL 报 "current transaction is aborted"）
      ⚠️⚠️ **写工具不许调用「自己会 `commit()` 的服务」**。SAVEPOINT 里的 `commit()` 会把
      **外层事务一并提交掉**，紧接着的 `refresh()` 又新开一个事务 —— 退出 `begin_nested()`
      时那个嵌套事务早已失效，抛
      `Can't operate on closed transaction inside context manager`。
      当前是安全的：`note_write_service` / `question_write_service` / `bank_manage`
      只 `flush()+refresh()`，不 `commit()`。但 `rag_write_service` 与 `memory_service`
      **是会自己 commit 的** —— 哪天有工具直接转调它们，这个坑立刻复现
      （`memory_hook` 就踩过，已改成独立会话，见那边的说明）。
    - 任何异常都转成 `fail()` 信封，交给模型自我纠正
    - 成功的**写操作**顺手记一条长期记忆（见 `memory_hook`）—— 放在这里是因为
      它是 api 主循环与 ds-free 单步执行**唯一的收口**，挂一处两边都覆盖
    """
    try:
        if tool.write_operation:
            async with ctx.db.begin_nested():
                result = await tool.execute(params, ctx)
        else:
            result = await tool.execute(params, ctx)
    except Exception as e:  # noqa: BLE001 - 业务异常也回灌给模型
        logger.exception("[agent] 工具 {} 执行异常: {}", tool.name, e)
        return fail(
            f"工具执行异常：{type(e).__name__}: {e}",
            "请检查参数是否符合要求；如果是数据本身的问题，"
            "请修正后重试，或换一种方式完成目标",
        )

    # 工具声明的「改前状态」快照必须先摘掉（见 base.UNDO_BEFORE_KEY）：
    # ⚠️⚠️ 它会随下面的 `tool_result` 事件下发到界面、也会进 ToolMessage 回灌给模型 ——
    #    留着就是把「上一版的旧值」当上下文喂给模型（既费 token，又可能被读成用户意图）。
    undo_before = None
    if isinstance(result, dict):
        undo_before = result.pop(UNDO_BEFORE_KEY, None)

    # 回退账本（`ai_agent_op_log`）：**与工具写入同一个会话**，所以它和数据一起提交、
    # 一起回滚 —— 不会出现「账本里有这行、数据却没落」或反过来的分叉。
    # api 链路靠下面 `run_agent_stream` 的显式 commit（写工具那一段），
    # ds-free 靠 `get_db` 的 teardown commit（非流式接口，见那边调用点的说明）。
    # 内部自己吞异常（记账失败不能让用户这次操作失败）。
    if isinstance(result, dict):
        await rollback_service.record_op(
            ctx.db, tool=tool, params=params, result=result, ctx=ctx, before=undo_before
        )

    # 记忆是增强项：record_tool_memory 内部自己吞异常、**自己开会话**，
    # 既不抛给循环，也不借用 ctx.db 的事务（借用会让每次写操作刷一条 warning，见 memory_hook）
    await memory_hook.record_tool_memory(ctx.user_id, tool, params, result)

    if isinstance(result, dict):
        return result
    return {"success": True, "data": result}


async def _prepare_tool_call(
    tool_name: str, params: Optional[Dict[str, Any]], user_id: int = 0
) -> tuple[Optional[AgentTool], Dict[str, Any], Optional[Dict[str, Any]]]:
    """工具调用的**前半段**：加载注册表 → 取工具 → **检查用户屏蔽** → 参数归一化 → schema 校验。

    返回 `(tool, 归一化后的 params, err)`；`err` 非空时把它**原样返回**给调用方即可
    （是 `fail()` 信封），此时 `tool` 为 None。

    为什么抽成一个函数：`/ai/agent/execute`（ds-free 单步执行）与 `/ai/agent/preview`
    （确认卡片的预演）**必须走同一套**归一化与校验 —— 预览描述的参数一旦和真正执行的参数
    不是同一组，预览就是假的：模型传 `"bank_id": "123"` 时，可能出现「预览显示题库 A、
    实际删的是 B」这种最坏情况。

    为什么是 `async` 且要 `user_id`：屏蔽闸门查的是「**这个用户**关掉了哪些工具」。
    放在这里（而不是只放在 `run_agent_stream` 里）是必须的 —— ds-free 的工具循环跑在
    **前端**，它压根不经过 `run_agent_stream`，拦截点只能在这里。
    """
    ensure_tools_loaded()
    tool = registry.get(tool_name)
    if tool is None:
        return None, dict(params or {}), fail(
            f"工具不存在：{tool_name}",
            f"可用工具只有：{', '.join(registry.names())}",
        )

    # 用户屏蔽闸门（**执行侧**，不只是「不广播」）：
    # 工具没被广播 ≠ 不能被调用 —— 模型完全可能凭上下文里的旧名字发起调用。
    disabled = await tool_pref_service.disabled_tool_names(user_id)
    if tool_name in disabled:
        return None, dict(params or {}), _disabled_fail(tool_name)

    guard_ = ExecutionGuard()
    normalized = guard_.normalize_params(tool, params or {})
    errors, hints = guard_.validate_params(tool, normalized)
    if errors:
        return tool, normalized, params_validation_failure(errors, hints)
    return tool, normalized, None


async def execute_agent_tool(
    db: AsyncSession,
    *,
    tool_name: str,
    params: Dict[str, Any],
    user_id: int = 0,
    session_id: str = "",
    #: 本轮对话 id（前端透传）。ds-free 的工具循环在前端，一轮里的多次调用靠它归组 ——
    #: 没带时 `_resolve_turn_id` 兜一个 per-request 的 id（安全退化，见该函数说明）
    turn_id: str = "",
    auto_confirm: bool = True,
    image_urls: Optional[List[str]] = None,
    confirmed: bool = False,
    confirm_ticket: str = "",
) -> Dict[str, Any]:
    """供 ds-free（浏览器扩展）客户端循环调用：执行单个工具并返回结构化结果。

    与 `run_agent_stream` 内联的工具执行逻辑保持一致：参数归一化 → schema 校验 →
    确认策略 → SAVEPOINT 包裹执行。死循环检测在客户端循环里做（单次执行无上下文），
    这里不重复。返回的字典直接是 `ok()` / `fail()` 信封，客户端据此渲染 `tool_result`。

    ## 确认闸门（v1 契约，2026-09-21）

    需要确认的操作必须带一张**校验通过的服务端票据**（`confirmTicket`），否则**绝不执行工具**。

    ⚠️ `confirmed` 参数**保留但不再是充分条件**：前端 `executeTool` 是**无条件**填
    `confirmed: true` 的 —— 只看它等于「服务端根本没有授权」，一个 HTTP 客户端带上 true
    就能删库。保留这个参数只是为了存量调用方零改动（不传即可）。

    票据的四项校验（签名 / uid / tool+paramsHash / 未过期）与「一次性」语义都在
    `agent/confirm_ticket.py` 里；这里只负责**在需要确认时**把它接上。
    `paramsHash` 用的是**归一化后**的参数（`_prepare_tool_call` 的产物），
    与 preview 下发票据时用的那份**同一组**（见 `preview_agent_tool`）。
    """
    # 前半段（取工具 + 屏蔽闸门 + 归一化 + 校验）与 preview 共用同一个实现，
    # 见 `_prepare_tool_call`。⚠️ 必须把 user_id 传进去 —— 屏蔽是**按用户**的。
    tool, params, err = await _prepare_tool_call(tool_name, params, user_id)
    if err:
        return err
    # err 为空 ⇒ tool 一定非空（`_prepare_tool_call` 的唯一返回 None 分支）
    if tool is None:  # pragma: no cover - 仅用于类型收窄
        return fail(f"工具不存在：{tool_name}", f"可用工具只有：{', '.join(registry.names())}")

    # 需要确认（破坏性操作恒需要；autoConfirm=false 时所有写操作）→ 必须带有效票据
    if needs_user_confirmation(tool, params, auto_confirm):
        ticket_ok, reason = verify_confirm_ticket(
            confirm_ticket, user_id, tool_name, params_hash(params)
        )
        if not ticket_ok:
            logger.warning(
                "[agent] 确认票据校验未过，拒绝执行 tool={} user={} reason={}",
                tool_name, user_id, reason,
            )
            return fail(
                "这次操作需要确认，但服务端没有收到有效的确认票据",
                "请先在界面上确认这次操作。客户端应先调用 /ai/agent/preview 拿到 "
                "confirmTicket，再在执行时把它放进 confirmTicket 字段带回来"
                "（票据与服务端认定的用户、工具、归一化后的参数绑定，只能用一次，180 秒内有效）",
                # 前端据此继续弹确认卡片（形状与旧实现一致，旧调用方不会因此变哑）
                needsConfirm=True,
            )

    ctx = build_tool_context(
        db,
        user_id,
        session_id,
        {
            "image_urls": image_urls or [],
            "tool_registry": registry,
            # 回退账本的归组键（每个工具调用都从 ctx 里读，见 rollback_service.record_op）
            "turn_id": _resolve_turn_id(turn_id),
            # ⚠️ 这条是 ds-free 的**单步执行**链路，只拿到一个工具名 + 参数，
            #    **没有附件解析上下文**（附件在前端循环里、不在后端）。所以这里只给空列表：
            #    `knowledge_ingest.from_attachment` 在此链路会返回明确的 fail 引导，
            #    不会「以为有附件」而空写。附件入库走 api 主链路的 run_agent_stream。
            "attachments": [],
        },
    )
    return await _execute_tool(tool, params, ctx)


async def preview_agent_tool(
    db: AsyncSession,
    *,
    tool_name: str,
    params: Dict[str, Any],
    user_id: int = 0,
    session_id: str = "",
    auto_confirm: bool = True,
) -> Dict[str, Any]:
    """**只预演、不执行**：给确认卡片产出 `preview`（前端据此告诉用户「要删的是哪个」）

    与 `execute_agent_tool` 的前半段完全同源（`_prepare_tool_call`），差别只有一处：
    走到「构 ctx」之后**只调 `tool.preview()`**，绝不执行工具、不写库、不 commit。

    为什么 ds-free 需要它：api 付费链路在**后端循环里**就能拿到 preview
    （`run_agent_stream` 弹 `tool_confirm` 事件时带上），ds-free 的循环跑在前端、
    确认卡片由前端弹，所以它得**自己来取**这一份 —— 否则两条链路的确认卡片不对等
    （付费链路说「将删除题库「X」，含 23 道题」，免费链路只有一句 action 名）。

    **确认票据（v1 契约，2026-09-21）**：确实需要确认时，除了 `preview` 再下发一个
    `confirmTicket` 字符串；`/ai/agent/execute` 会要求把它带回来（见那边）。
    判定用的是**同一个** `needs_user_confirmation`，且 `auto_confirm` 由调用方透传 ——
    客户端给 preview 与 execute 的必须是**同一个** autoConfirm 值，
    否则会出现「preview 按 autoConfirm=true 判成不需要 → 不发票 / execute 按
    autoConfirm=false 说要票 → 拒绝」这种**互相打架、根本没法完成**的组合。

    行为约定：
      · 不需要确认的操作 → `{"preview": {}}`（与循环里 `if tool.needs_confirmation(params)` 同口径）
      · 参数非法 / 工具不存在 → 返回 `fail()` 信封（调用方原样转发，前端照常弹卡片）
      · `preview()` 自己抛异常 → 只记 warning，`preview` 仍为空对象
        ⚠️ **必须不阻断**：拿不到预览只是卡片信息少一点，报错卡住就等于「用户删不掉东西了」，
        比没有预览严重得多。⚠️ 但**票据照发** —— 预览失败不该让用户连确认按钮都点不动
        （那已经不是「信息少一点」，而是功能没了）。
    """
    # 与 execute_agent_tool 同源（含**同一道屏蔽闸门**）：被屏蔽的工具连预演都不给，
    # 否则「确认卡片为 A 弹出来了、点确认却拿到一句已被屏蔽」——两条链路不一致。
    tool, params, err = await _prepare_tool_call(tool_name, params, user_id)
    if err:
        return err
    if tool is None:  # pragma: no cover - 仅用于类型收窄
        return fail(f"工具不存在：{tool_name}", f"可用工具只有：{', '.join(registry.names())}")

    if not tool.needs_confirmation(params):
        return {"preview": {}}

    ctx = build_tool_context(
        db,
        user_id,
        session_id,
        # 同 execute_agent_tool：ds-free 单步链路没有附件解析上下文，给空列表，
        # 让 `knowledge_ingest.from_attachment` 的 preview 落到「没有可用附件」分支
        # （而不是 KeyError / 假装有附件）。
        {"image_urls": [], "tool_registry": registry, "attachments": []},
    )
    try:
        preview: Dict[str, Any] = await tool.preview(params, ctx)
    except Exception as e:  # noqa: BLE001 - 预览是增强项，失败绝不阻断
        logger.warning("[agent] preview 失败 {}: {}", tool_name, e)
        preview = {}

    result: Dict[str, Any] = {"preview": preview}
    if needs_user_confirmation(tool, params, auto_confirm):
        # 票据绑的是**归一化后**的 params（与 execute 侧同一组），用户 / 工具 / 参数 / 有效期
        # 都进了签名，所以「换个参数复用这张票」「换个人用这张票」都会被拒。
        result["confirmTicket"] = issue_confirm_ticket(
            user_id, tool_name, params_hash(params)
        )
    return result


# ============================================================
# 写操作二次确认：循环「挂起」→ 前端弹确认卡片 → 用户点击 → 唤醒继续
# ============================================================
#: 等待确认的超时（秒）。超时按「取消」处理，避免请求永久挂住。
CONFIRM_TIMEOUT_SECONDS = 180

#: confirmId → asyncio.Event（等前端 POST /ai/agent/confirm 唤醒）
_pending_confirms: Dict[str, asyncio.Event] = {}
#: confirmId → 用户决定 `{"approved": bool, "edited": dict|None}`
#: `edited` 是草稿编辑器回传的用户改动（需求二的可编辑草稿）；为 None = 按原样执行。
_pending_decisions: Dict[str, Dict[str, Any]] = {}


async def _await_user_confirmation(
    confirm_id: str,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """挂起当前 Agent 循环，直到前端确认 / 取消（或超时）

    返回 `(approved, edited)`：`approved=False` = 用户取消；`edited` = 用户在草稿里
    改过的内容（没有则为 None）。

    无论从哪条出口离开（成功 / 超时 / 被取消），`confirmId` 都会从
    `_pending_confirms` 与 `_pending_decisions` 两个字典里清掉。
    """
    # 极端竞态：前端可能比后端先到（决定已经在 `_pending_decisions` 里）→ 直接采用
    if confirm_id in _pending_decisions:
        return _read_decision(_pending_decisions.pop(confirm_id))

    event = asyncio.Event()
    _pending_confirms[confirm_id] = event
    try:
        await asyncio.wait_for(event.wait(), timeout=CONFIRM_TIMEOUT_SECONDS)
        # ⚠️ 读取决定必须在 finally **之前**：finally 会把两个字典都清掉（见下），
        #   成功路径先 pop 决定再进 finally，后者对已 pop 的键是 no-op。
        return _read_decision(_pending_decisions.pop(confirm_id, {}))
    except asyncio.TimeoutError:
        logger.warning("[agent] 等待用户确认超时: {}", confirm_id)
        return False, None
    finally:
        # 三条退出路径（成功 / 超时 / 任务被取消）都不留 confirmId：
        # 旧实现只清 `_pending_confirms`，超时或取消后「迟到的决定」会一直躺在
        # `_pending_decisions` 里，直到 200 条防御性清理才被冲掉（纯垃圾内存）。
        _pending_confirms.pop(confirm_id, None)
        _pending_decisions.pop(confirm_id, None)


def resolve_confirmation(
    confirm_id: str,
    approved: bool,
    edited: Optional[Dict[str, Any]] = None,
) -> bool:
    """前端点了确认 / 取消 → 唤醒挂起的循环

    **先记决定再唤醒**：这样「先到 / 后到」都能正确处理（无竞态）。
    `edited`：草稿编辑器回传的用户改动（可选；仅 `approved=True` 时有意义）。
    """
    _pending_decisions[confirm_id] = {"approved": bool(approved), "edited": edited}
    # 防御性清理：只保留最近一批，避免异常调用把 dict 撑大
    if len(_pending_decisions) > 200:
        for key in list(_pending_decisions.keys())[:-100]:
            _pending_decisions.pop(key, None)
    event = _pending_confirms.get(confirm_id)
    if event is not None:
        event.set()
    return True



# ============================================================
# 可编辑草稿（需求二）：用户在确认卡片里改过内容 → 覆盖工具参数后再执行
# ============================================================


async def _apply_edited_params(
    tool: AgentTool,
    params: Dict[str, Any],
    edited: Any,
    ctx: ToolContext,
) -> Dict[str, Any]:
    """把草稿编辑器回传的用户改动**覆盖到工具参数**上（目前只支持建库导入草稿）

    目前唯一支持的草稿是 `question_manage.batch_import`（需求二：可编辑草稿）：
      · `edited["questions"]`（数组）→ 覆盖 `params["questions"]`（工具接受 JSON 字符串）；
      · `edited["bank"]`（含 `bankId` + 改动字段）→ 在导入前把题库字段改掉。

    ⚠️ **防御性**：`edited` 结构不对、或某一项坏掉 → **退回原参数**（宁可导入原始内容，
       也绝不因为一次编辑把整批导入弄丢）。
    """
    if not isinstance(edited, dict):
        return params

    # ---- 批量删除：按用户在卡片上**勾选的名单**收窄要删的对象 ----
    # 契约（前端 `AgentDraftCard` 的 batch_delete 模式回传）::
    #     {"selectedKeys": ["kb:584", "kb:587"], "cancelled": false}
    # 语义：
    #   · `cancelled=true`（用户点「全部不删」）→ 返回空名单，由调用方按「取消」处理；
    #   · `selectedKeys` 是**最终要删的**（未勾选 = 用户反悔、留着）；
    #   · 未知 / 空名单一律退回原参数（宁可多删一次让用户看见，也不静默少删）。
    if _is_batch_delete_draft(tool, params):
        narrowed = _apply_selected_keys(tool, params, edited)
        if narrowed is not None:
            return narrowed
        return params

    if tool.name != "question_manage" or str(params.get("action") or "") != "batch_import":
        return params

    new_params = dict(params)
    questions = edited.get("questions")
    if isinstance(questions, list) and questions:
        # `questions` 现在是真正的数组（2026-10-28）：编辑器回传的也是数组，
        # 直接透传，不再 json.dumps 成第二层字符串。少一层序列化 = 少一类转义 bug。
        new_params["questions"] = questions

    bank_edit = edited.get("bank")
    if isinstance(bank_edit, dict) and bank_edit:
        try:
            await _apply_edited_bank(ctx, new_params, bank_edit)
        except Exception as e:  # noqa: BLE001 - 改库失败不该阻断导入
            logger.warning("[agent] 按草稿更新题库失败（继续导入）: {}", e)
    return new_params


async def _apply_edited_bank(
    ctx: ToolContext, params: Dict[str, Any], bank_edit: Dict[str, Any]
) -> None:
    """按草稿里改过的题库字段更新题库（**只在有 bankId 且题库属于本用户时**）

    走 `question_write_service.update_bank`（与 `bank_manage._update` 同一路径），
    只应用草稿里**确实给出**的字段；改名重名时保留原名、其余字段照常。
    """
    from app.models.question import QuestionBank
    from app.services import question_write_service as qws

    bank_id = bank_edit.get("bankId")
    if bank_id is None:
        bank_id = params.get("bank_id")
    try:
        bank_id = int(bank_id)
    except (TypeError, ValueError):
        return
    bank = await ctx.db.get(QuestionBank, bank_id)
    if bank is None or int(bank.user_id or 0) != int(ctx.user_id):
        return
    changed, conflict = await qws.update_bank(
        ctx.db,
        bank,
        bank_name=bank_edit.get("bankName"),
        subject=bank_edit.get("subject"),
        description=bank_edit.get("description"),
        is_public=bank_edit.get("isPublic"),
    )
    if conflict is not None:
        logger.warning("[agent] 草稿改名冲突，保留原题库名: {}", bank.bank_name)
    if changed:
        logger.info("[agent] 按草稿更新题库 {}：{}", bank_id, changed)


async def _rollback_empty_created_bank(
    ctx: ToolContext,
    tool_name: str,
    params: Dict[str, Any],
    created_banks: set,
) -> None:
    """用户取消 `batch_import` 时，若目标题库是**本轮刚建的**且仍是**空库** → 删掉它

    背景：模型常先 `bank_manage create` 建库、再 `batch_import` 导题；用户在导入卡片上
    点「取消」时，若不处理，就会留下一个空题库。

    ⚠️ 只删「本轮 create 出来」（`created_banks` 记录）且「当前 0 题」的库 —— 已有库、
       已导过题的库一律不碰。删除走 `question_write_service.delete_banks`（与后台删库 /
       `bank_manage` 同一路径，内部已做归属过滤），随后**显式提交**（取消发生在流式响应
       中，不能依赖 teardown 的 commit，否则会出现「说删了、刷新还在」）。
    ⚠️ 这是**最小实现**，只覆盖「本轮新建 + 空库」这一种情况，不复用 `rollback_service`
       的账本（账本按 turn 回退整轮，语义是「用户主动点回退」，与「取消单次导入」不同）。
    """
    if tool_name != "question_manage" or str(params.get("action") or "") != "batch_import":
        return
    if not created_banks:
        return

    from sqlalchemy import func, select

    from app.models.question import QuestionMain
    from app.services import question_write_service as qws

    try:
        bank_id = int(params.get("bank_id"))
    except (TypeError, ValueError):
        bank_id = None
    if bank_id is None:
        name = (params.get("bank_name") or "").strip()
        if not name:
            return
        bank = await qws.find_bank_by_name(ctx.db, ctx.user_id, name)
        if bank is None:
            return
        bank_id = int(bank.id)
    if bank_id not in created_banks:
        return

    try:
        count = int(
            await ctx.db.scalar(
                select(func.count()).where(QuestionMain.bank_id == bank_id)
            )
            or 0
        )
        if count:
            return
        await qws.delete_banks(ctx.db, ctx.user_id, [bank_id])
        await ctx.db.commit()
        created_banks.discard(bank_id)
        logger.info("[agent] 用户取消导入：删除本轮新建的空题库 bank_id={}", bank_id)
    except Exception as e:  # noqa: BLE001 - 清理是增强项，失败不影响「已取消」
        logger.warning("[agent] 取消导入后清理空题库失败 bank_id={}: {}", bank_id, e)


async def run_agent_stream(
    db: AsyncSession, req: AgentRequest
) -> AsyncIterator[str]:
    """执行一次 Agent 任务并流式下发事件

    流程：
        组提示词 → 逐轮「LLM → 若调工具则执行并回灌」→ 输出最终回复 → 落库
    """
    ensure_tools_loaded()
    guard = ExecutionGuard(same_call_limit=SAME_CALL_LIMIT)
    state = GuardState()
    user_id = req.user_id or 0
    session_id = (req.session_id or "").strip()
    # 本轮对话 id：前端带上来就用它（并在 `meta` 事件里**原样回显**），没带就兜一个。
    # 它只用于回退账本的归组 —— 后端不定义轮边界（见 `_resolve_turn_id`）。
    turn_id = _resolve_turn_id(req.turn_id)

    # ---- ① 工具与客户端准备（失败在这里就要明确报出来）----
    # 用户级工具开关：**默认全部开启**（稀疏存储：没有行就是启用）。
    # 这一个集合同时喂给四处「面向模型 / 面向前端」的出口：Function Calling 的 tools、
    # 系统提示词的工具清单、`meta` 事件的可用工具列表，以及两处执行闸门
    # （`_prepare_tool_call` 与下面内联分支里的 `_disabled_fail`）。
    # ⚠️ `definitions()` / `describe()` **本来就收 `exclude=`**，别另写一套过滤。
    #
    # ⚡ 「工具屏蔽」与「专家开关」是两次独立 DB 读，用 gather 并行（避免串行叠加首字延迟）。
    disabled_tools, disabled_role_keys = await asyncio.gather(
        tool_pref_service.disabled_tool_names(user_id),
        agent_role_pref_service.disabled_role_keys(user_id),
    )

    # ---- 多智能体编排层（指挥家 + 子代理）----
    # 两条入口（见 docs/fastapi_v2_指挥家模式方案.md）：
    #   · **显式选择**（用户点名某子代理：`req.agent_id` 非空，或 `req.role` 是具名子代理）
    #     → 该子代理**直接面向用户**（用户就要它答），不启用指挥家、不挂 delegate_task。
    #   · **自动路由**（`req.role` 为空）→ **指挥家模式**：主体是 `general`（全工具）+
    #     元工具 `delegate_task` + 子代理通讯录；指挥家自行决定自己答 or 委派。
    #
    # ⚠️ `excluded_tools` 仍是"交给注册表的黑名单"，但指挥家模式要**额外把 delegate_task
    #    加回**（`compute_exclude` 永远排除它，见 orchestrator 说明）。
    # ⚠️ `disabled_tools`（纯用户屏蔽）保留原义，供 ds-free 路径的 `_prepare_tool_call` 用。
    user_agent_model: Optional[str] = None
    role_spec = None
    explicit_agent = None  # 用户显式点名的子代理（user RoleSpec 或官方具名 RoleSpec）
    if req.agent_id:
        try:
            from app.services.ai.agent import agent_config_service

            agent_dict = await agent_config_service.get_agent_dict(user_id, int(req.agent_id))
            if agent_dict:
                explicit_agent = orchestrator.build_user_role(agent_dict)
                # 用户 Agent 可绑模型；仅在请求**未显式指定** model 时生效（请求优先）。
                user_agent_model = (agent_dict.get("model") or "").strip() or None
        except Exception as e:  # noqa: BLE001 - 用户 Agent 解析失败 → 退回官方角色
            logger.warning("[agent] 解析用户智能体失败（退回官方角色）agent_id={}: {}", req.agent_id, e)

    if explicit_agent is None:
        # 未传 agent_id：看 req.role 是否是**具名官方子代理**（点名要它）
        # ⚠️ 已被用户关闭的专家**不可点名**（关掉 = 叫不到）→ 忽略，退自动（指挥家）路由。
        named = roles_mod.role_or_none(req.role)
        if (
            named is not None
            and named.key != roles_mod.GENERAL_ROLE
            and named.key not in disabled_role_keys
        ):
            explicit_agent = named

    if explicit_agent is not None:
        # 用户点名 → 子代理直接面向用户
        role_spec = explicit_agent
        conductor_mode = False
    else:
        # 自动路由 → 指挥家模式
        role_spec = orchestrator.resolve_role(
            role="", message="", disabled_role_keys=disabled_role_keys
        )  # = general（全工具）
        conductor_mode = True

    excluded_tools = orchestrator.compute_exclude(
        role_spec,
        all_tool_names=registry.names(),
        user_disabled=disabled_tools,
        # ⚠️ **方案 A（2026-10-10）**：指挥家模式（role_spec=general，不限工具）时，
        #    把「被用户关闭的专家」名下的工具**一并排除** —— 否则关了专家、指挥家自己
        #    仍能直接调那些工具，等于"关了没关"（用户报的 bug）。
        #    显式点名某子代理时（conductor_mode=False，role_spec=该子代理）它本就用白名单，
        #    传不传都不影响结果（白名单之外自然被排），一并传保持一致。
        disabled_role_keys=disabled_role_keys,
    )
    # 本轮是否有**可委派的专家**（官方未关闭 + 用户自定义）。决定指挥家是否值得挂 delegate_task：
    # 若一个专家都没有（用户关掉了全部、且没建自定义智能体），挂委派工具只会让模型
    # 白白发起一次注定失败的委派 —— 不加回，退化为"纯聊天 + 通用工具"更干净。
    has_any_sub_agent = bool(roles_mod.renderable_sub_agents(disabled_keys=disabled_role_keys))
    if conductor_mode and has_any_sub_agent:
        # 指挥家额外拿回元工具（仅在真有专家可派时）
        excluded_tools = {t for t in excluded_tools if t != roles_mod.DELEGATE_TOOL_NAME}
    tool_defs = registry.definitions(exclude=sorted(excluded_tools))

    if not registry.names():
        # 注册表本身为空 = 服务端配置问题（工具没被 `tools/__init__.py` 注册）
        yield _event(error_event("Agent 没有可用工具，请检查服务端配置"))
        yield "[DONE]"
        return

    # 「注册表非空、但被这个用户全部屏蔽」是**另一回事**：那是用户自己的选择，
    # 说「请检查服务端配置」对他就是一句假话。这种情况退化成**纯聊天**：
    #   · 不报错、不中止；系统提示词里如实说明本轮没有工具（见下面的 system_notes）；
    #   · 不调 `llm.bind_tools`（实测 `bind_tools([])` 会生成 `{"tools": []}` 并原样
    #     发到上游，OpenAI 兼容端点是会 400 的 —— 见 `tools_all_disabled` 的用法）。
    tools_all_disabled = not tool_defs

    try:
        llm, config = await db_config.build_agent_llm(
            db,
            provider=req.provider,
            # 模型优先级：请求显式指定 > 用户 Agent 绑定 > 用户默认（build_agent_llm 内部兜底）。
            model=req.model or user_agent_model,
            temperature=req.temperature,
            # 带上用户作用域：用户自己配的模型（个人中心 → 我的模型）也能被 Agent 选中
            user_id=user_id,
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=req.config_id,
        )
    except Exception as e:  # noqa: BLE001 - 配置类错误直接给用户看
        yield _event(error_event(str(e)))
        yield "[DONE]"
        return

    # ---- ② 附件 → 正文 + 图片 ----
    # ⚠️ 丢到线程池里执行：文档解析是同步的，老版 .doc 还会借 Word COM 转换
    #    （1~3s，最坏 CONVERT_TIMEOUT_SECONDS）。直接在事件循环里跑会把整个后端冻住。
    #
    # ⚠️ 进度事件（用户 2026-10-11 方案 C）：`_collect_attachments` 是同步阻塞、**执行期间发不出
    #    事件**（事件只能由 async 生成器 yield）。故把"文档处理"拆成「发事件 → 解析 → 发事件」三段：
    #    解析**前**告知"开始解析（N 个文件）"，解析**后**汇报"提取了多少文本/图片"。前端据此把
    #    "干等转圈"变成有信息量的步骤清单。**非思维链内容**，只是耗时环节的进度提示。
    file_count = len(req.files or [])
    if file_count:
        yield _event(
            {
                "type": "progress",
                "id": "doc_parse",
                "icon": "📄",
                "state": "running",
                "message": f"正在解析文档（共 {file_count} 个文件）…",
            }
        )
    file_text, doc_images, warnings, attachments = await asyncio.to_thread(
        _collect_attachments, req
    )

    # ---- ②-b 附件持久化（2026-10-27 新增）----
    #
    # ⚠️ 修的是用户实测反馈的核心问题：
    #
    #     「文件类数据持久化也没有做到。比如用户第一次询问，
    #       然后第二次让他插入图片，他也没办法获取到用户之前上传过的图片」
    #
    # 在此之前 `AssistantAttachment` 是纯内存态（docstring 明确写「不落存储」）：
    # 附件解析成文本塞进当轮 prompt，请求结束全部丢弃。于是：
    #   · 第二轮说「把刚才那张图插到第 4 题」→ 图已经不在了，只能说"你再发一次"；
    #   · Word 里的插图虽然被解析出来了，但排版时没用上（见 `compose_from_file`）。
    #
    # 现在：把字节落盘 + 元信息入库（含逐张拆出的内嵌图片），
    # 之后任何一轮都能通过 `chat_file_manage` 工具按 id 取用。
    #
    # ⚠️ 失败必须**静默降级**：持久化是"锦上添花"的能力，
    #    不能因为它出错就让整轮对话失败（用户此刻要的是那份 Word，不是报错）。
    #
    # ⚠️⚠️ 必须用**独立的 session**，不能复用 `db`（2026-10-27 实测踩坑）
    #
    #    `get_db()` 的事务边界是：
    #
    #        async with async_session_factory() as session:
    #            yield session          # ← 路由处理期间
    #            await session.commit() # ← yield 返回后立刻提交
    #
    #    而 `run_agent_stream` 是**流式生成器**，它在 `StreamingResponse`
    #    里被迭代 —— 那时 `get_db` 的 `yield` 早就返回、`commit()` 也早就跑完了。
    #
    #    所以在这里往 `db` 里写东西（哪怕自己 commit）**永远进不了库**：
    #    实测现象是「进度事件说'已保存 1 个附件'，但表里 0 条记录」。
    #    （它自己的 commit 会被后续的 session 生命周期覆盖/丢弃。）
    #
    #    用独立 session 才能保证「写入即落库」，与流式响应解耦。
    if file_count or (req.images or []):
        try:
            from app.database import async_session_factory as _session_factory
            from app.services import chat_upload_service as _upload_svc

            async with _session_factory() as _upload_db:
                persisted = await _upload_svc.persist_attachments(
                    _upload_db,
                    user_id=user_id,
                    session_id=session_id,
                    attachments=list(req.files or []),
                    images=list(req.images or []),
                )
            if persisted:
                _n_img = sum(p.get("imageCount") or 0 for p in persisted)
                yield _event(
                    {
                        "type": "progress",
                        "id": "doc_persist",
                        "icon": "💾",
                        "state": "done",
                        "message": (
                            f"已保存 {len(persisted)} 个附件到本次对话"
                            + (f"（含 {_n_img} 张图片，后续可以直接引用）" if _n_img else "")
                        ),
                    }
                )
        except Exception as e:  # noqa: BLE001
            # 不中断对话，但**把原因带出来**：
            # 只记一条笼统的 warning 会让"为什么没存上"变成黑盒
            # （实测第一版就是这样：事件说"已保存"，库里 0 条，查不出原因）。
            import traceback as _tb

            _detail = f"{type(e).__name__}: {e}"
            logger.warning(
                f"[upload] 附件持久化失败（不影响本轮对话）: {_detail}\n"
                f"{_tb.format_exc()[:1200]}"
            )
            yield _event(
                {
                    "type": "warning",
                    "message": f"附件已解析但未能保存到对话记录（{_detail}），下一轮可能无法再次引用",
                }
            )
    if file_count:
        # 解析完成：汇报真实产出（文本长度 + 图片张数），失败/无正文也如实说。
        text_len = len(file_text or "")
        img_n = len(doc_images or [])
        parts = []
        if text_len:
            parts.append(f"文本约 {text_len} 字")
        if img_n:
            parts.append(f"图片 {img_n} 张")
        detail = "、".join(parts) if parts else "未提取到可用内容"
        yield _event(
            {
                "type": "progress",
                "id": "doc_parse",
                "icon": "📄",
                "state": "done",
                "message": f"文档解析完成（{detail}）",
            }
        )
    all_images = [u for u in (req.images or []) if u] + doc_images
    # ⚠️ 用户 2026-10-11 修 400 `Unsupported image_url format`：
    #    **喂给多模态模型的图片必须是「data URL 或 http(s) 绝对 URL」**，不能是落盘后的
    #    相对路径 `/profile/upload/...`（OpenAI 兼容端点会直接 400 拒收）。
    #    故这里把两条用途**分流**（同一批图、顺序一一对应，编号天然一致）：
    #      · `vision_images` = 原始 data URL（req.images + 文档插图原样）→ **喂模型**
    #      · `image_urls`    = 落盘后的 `/profile/...` 路径 → **供题目回插** `<img src>`
    #    （题目正文是 TEXT 列，回插必须用短路径而非 base64；而喂模型必须 base64/绝对 URL。）
    vision_images = list(all_images)
    if all_images:
        # 图片落盘（base64 → /profile/... 路径）也要点时间，给个进度提示（用户 2026-10-11 方案 C）
        yield _event(
            {
                "type": "progress",
                "id": "save_images",
                "icon": "🖼",
                "state": "running",
                "message": f"正在保存图片（共 {len(all_images)} 张）…",
            }
        )
    image_urls = await persist_agent_images(all_images) if all_images else []
    if all_images:
        saved_n = len([u for u in image_urls if u])
        yield _event(
            {
                "type": "progress",
                "id": "save_images",
                "icon": "🖼",
                "state": "done" if saved_n else "failed",
                "message": f"图片已保存（{saved_n} 张）" if saved_n else "图片保存失败",
            }
        )
    if doc_images and not any(image_urls):
        warnings.append("文档插图未能保存到服务器，题目里的图片标记会被忽略")

    # ---- 视觉模型兜底（用户 2026-10-11）----
    # 本轮有图片（含**文档内嵌插图**）要喂给模型，但当前选中的模型若「只支持文本」
    # （如 deepseek-v4-pro），上游会直接 400 把整轮请求打回 —— 用户会看到莫名报错。
    # 这里仿 `chat_engine._resolve_vision_safe_model` 的做法：**回退到默认视觉模型**
    # （`deepseek-flash`，多模态）。注意 `llm` 早在第 857 行就构造了（那时还不知道有没有图），
    # 所以这里按需**重建** llm。
    # ⚠️ 只认「正在用的模型」——`config` 是 `build_agent_llm` 返回的已解析配置。
    if vision_images:
        try:
            using_model = (getattr(config, "model", None) or req.model or user_agent_model or "")
            if not model_capabilities.supports_vision(using_model):
                llm, config = await db_config.build_agent_llm(
                    db,
                    provider=None,
                    model=model_capabilities.DEFAULT_VISION_MODEL,
                    temperature=req.temperature,
                    user_id=user_id,
                )
                warnings.append(
                    f"当前模型不支持图片，已自动改用 {model_capabilities.DEFAULT_VISION_MODEL} 识别图片"
                )
                logger.info(
                    "[agent] 本轮含图片，模型 {} 不支持视觉 → 回退 {}",
                    using_model, model_capabilities.DEFAULT_VISION_MODEL,
                )
        except Exception as e:  # noqa: BLE001 - 兜底失败不阻断，让上游报错更直观
            logger.warning("[agent] 视觉模型兜底失败，按原模型发起：{}", e)

    typed = (req.message or "").strip()
    if not typed and not file_text:
        if all_images:
            typed = DEFAULT_AGENT_PROMPT
        else:
            detail = f"（{'；'.join(warnings)}）" if warnings else "请输入你的需求，或上传文档 / 图片"
            yield _event(error_event(f"没有可发送的内容：{detail}"))
            yield "[DONE]"
            return
    # 只传了附件（正文空）时给一句最小指令，让模型明确要对附件做什么。
    if not typed and all_images:
        typed = DEFAULT_AGENT_PROMPT

    # 系统侧补充说明（**进 SystemMessage，不进用户消息**）。
    # 这样「系统说的话」和「用户说的话」在消息层面就是分开的，模型不会把
    # 「本次带了 3 张图」当成用户请求的一部分。
    system_notes: List[str] = []

    # 有图片时明确告诉模型编号规则，它才敢在题干里写【图N】。
    # ⚠️ 用户 2026-10-11：**文档内嵌图片现在也会作为多模态图片一起喂给模型**（见下方
    #    `vision_images` 组块）。所以这里按 `vision_images`（=用户图 + 文档图，顺序与编号一致）
    #    统一给一份编号说明，告诉模型「共几张、按 0..N-1 编号、既有用户上传图也有文档插图」，
    #    视图里所有图都能被模型「看到」。不再像以前那样把"用户图/文档图"拆成两段分别说
    #    （那会让模型以为文档图不可见、只敢保留标记而不敢据图作答）。
    if vision_images:
        last = len(vision_images) - 1
        if last == 0:
            marker_hint = f"reference it as {IMAGE_MARKER_TMPL.format(0)}"
        else:
            marker_hint = (
                f"reference them in order as {IMAGE_MARKER_TMPL.format(0)} ... "
                f"{IMAGE_MARKER_TMPL.format(last)}"
            )
        parts = []
        if req.images:
            parts.append(f"{len(req.images)} image(s) the user uploaded")
        if doc_images:
            parts.append(f"{len(doc_images)} inline illustration(s) extracted from the document(s)")
        source_desc = " and ".join(parts) if parts else f"{len(vision_images)} image(s)"
        system_notes.append(
            f"## Image Attachments (all viewable)\n"
            f"This turn includes {len(vision_images)} image(s) total: {source_desc}. "
            f"You can SEE all of them in this message. {marker_hint} in question text. "
            f"Document illustrations are already numbered in the text above — keep the "
            f"{IMAGE_MARKER_TMPL.format(0)}-style markers verbatim; the system will replace "
            f"them with real URLs. Use the image CONTENT when writing questions/explanations "
            f"(e.g. a geometry figure, a circuit, or a formula shown as an image)."
        )

    # 「工具全被这个用户关掉了」→ 明确告诉模型本轮没有工具。
    # 用户的原始要求就是「全部被屏蔽时适当给 LLM 提示」：不说的话，模型会照着
    # 提示词里那份（已经被换成 "(no tools available)" 的）工具清单硬猜，
    # 或者干脆声称自己「已经帮你查了」—— 那是最糟的结果（用户没数据、还被告知做完了）。
    # ⚠️ 用英文：这一段进的是**全英文的系统提示词**（同 system_notes 既有两条的语种），
    #    模型回复的语言由 `AGENT_LANGUAGE_RULES` 跟着用户提问走，不受这里影响。
    if tools_all_disabled:
        system_notes.append(
            "## Tool Availability\n"
            "The user has turned OFF every tool in the tool settings, so NO tools are "
            "available for this turn. Do not claim or imply that you used a tool, and "
            "do not attempt to call one. Answer the request directly from your own "
            "knowledge. If the request genuinely cannot be answered without a tool, say "
            "so in one short sentence and mention that the needed tool can be re-enabled "
            "in the tool settings panel."
        )

    yield _event(
        {
            "type": "meta",
            # 「可用工具」= **角色生效后的**清单（角色外工具与用户屏蔽掉的都不该出现）。
            # 前端用它渲染本轮工具条，报的是「模型这一轮真的能调什么」。
            "tools": [
                {"name": t.name, "description": t.description}
                for t in registry.all()
                if t.name not in excluded_tools
            ],
            # 本轮智能体（多智能体协同）：前端据此显示「当前由 题库助手 回答」。
            # kind：用户自定义智能体 key 形如 `user:<id>`，官方角色是纯 key。
            "agent": {
                "id": role_spec.key,
                "name": role_spec.name,
                "kind": "user" if role_spec.key.startswith("user:") else "official",
            },
            "model": config.model,
            "provider": config.provider,
            "warnings": warnings,
            "imageCount": len([u for u in image_urls if u]),
            # 本轮 id **原样回显**（前端带上来的就回显它，没带就回显兜底值）。
            # 用途：回退组件要用它来调回退；回显也让「服务端实际按哪个 id 记的账」可对账。
            "turnId": turn_id,
        }
    )

    # ---- ③ 系统提示词与初始消息 ----
    # 系统内置指令（含本轮动态补充）全部进 SystemMessage；用户内容一律进 HumanMessage。
    #
    # L1 自动注入：把「这个用户有什么」（长期记忆摘要 + 知识库清单）追加到系统提示词。
    # ⚠️ 放在 `req.system_prompt` 的**外部**（`or` 的左边）—— 显式传入 system_prompt 是
    #    调用方要**完全接管**提示词（测试与 ds-free 会这么做），此时不该再叠我们的背景。
    # ⚠️ 它内部**自己开会话**，不要改成把请求会话 `db` 传进去：借用请求会话会让每次
    #    流式请求漏一条连接（实测 1/2/3 递增，直到连接池耗尽），原因见
    #    `runtime_context` 的模块说明。
    if req.system_prompt:
        # ⚠️ 调用方完全接管系统提示词时，**不注入角色人设** —— 那是「显式覆盖」的语义
        #    （测试与 ds-free 会这么做）。角色只在走默认提示词时生效。
        system_prompt = req.system_prompt
    else:
        # ⚡ 首字延迟优化：`build_runtime_context`（读记忆摘要 + 知识库清单）与
        #   指挥家模式下读用户智能体通讯录（`list_agents`）是**两次互相独立的 DB 往返**，
        #   原先串行 await = 两次往返时间在用户「发出→看到首个 token」之间叠加（实测这段
        #   能有~1 秒的停顿）。二者**各自独立开会话**（build_runtime_context 自己开会话、
        #   list_agents 也自己开会话），并行安全 —— 用 gather 并发发起。
        runtime_ctx, extra_agents = await asyncio.gather(
            runtime_context.build_runtime_context(user_id, lang="en"),
            _load_user_agent_briefing(user_id) if conductor_mode else _async_empty_list(),
        )
        # 本轮是否需要「建库重型规则」：带了附件、或消息命中建库/导题关键词时才注入
        # （题型编码 / 建库字段推断 / 文档导题流程，约 2.6KB）。普通聊天不发，省 token
        # 也把注意力留给真正相关的规则。见 prompts.needs_doc_workflow。
        has_docs = bool(file_text) or bool(req.images) or bool(req.files)
        doc_workflow = prompts.needs_doc_workflow(typed, has_attachments=has_docs)

        # 子代理通讯录（仅指挥家模式）：让指挥家"知道每个子代理能干什么"，据此决定派给谁。
        # 含官方子代理 + 用户自定义智能体（后者由上面的 gather 并行读出）。
        sub_agents_text = (
            roles_mod.render_sub_agents_briefing(
                extra_agents, disabled_keys=disabled_role_keys
            ) if conductor_mode else ""
        )

        # 显式点名子代理时：用它的 `persona`（第一人称自我认知）作角色指令；
        # 指挥家模式下 role_spec 是 general（无 persona），角色感由通讯录段承担。
        role_prompt = ""
        if not conductor_mode:
            role_prompt = (role_spec.persona or role_spec.prompt_fragment or "").strip()

        system_prompt = prompts.build_agent_system_prompt(
            # ⚠️ 付费链路**不再**把工具清单写进系统提示词：`bind_tools(tool_defs)` 已经把
            #    完整工具定义（含 JSON Schema）交给模型，那是官方 Function Calling 的权威来源。
            #    在提示词里再写一遍是**重复**（实测 describe() 约 2.7K token/轮）。
            #    `tools_text` 仍传（供 ds-free 走 `req.system_prompt` 之外的兼容路径，
            #    以及万一有人在别处复用本函数）。
            include_tools=False,
            include_doc_workflow=doc_workflow,
            sub_agents_text=sub_agents_text,
            tools_text=registry.describe(exclude=sorted(excluded_tools)),
            extra="\n\n".join(
                [s for s in [role_prompt, *system_notes, runtime_ctx] if s]
            ),
        )
    lc_messages: List[Any] = [SystemMessage(content=system_prompt)]

    context = ""
    if req.persist:
        # lang="en" → 历史上下文用 <conversation_history> 英文标签包裹，
        # 与下面的 <user_request> 明确区分（中文版的「【对话历史】」只给聊天助手用）
        # 历史预算按「该模型配置的上下文档位」定（200K/1M）—— 见 context_budget。
        # ⚠️ `config` 由上面的 build_agent_llm 返回，直接用，不再重复解析（省一次 DB 往返）。
        from app.services.ai import context_budget
        _ctx_key = getattr(config, "context_length", None)
        context = await conversation_service.build_context_prompt(
            user_id, session_id, lang="en",
            max_chars=context_budget.history_char_budget(_ctx_key),
            single_max_chars=context_budget.single_message_char_budget(_ctx_key),
        )
        history_text = typed or conversation_service.ATTACHMENT_PLACEHOLDER
        try:
            await conversation_service.save_message(
                user_id,
                session_id,
                "user",
                history_text,
                # 本轮 id：**同一轮的两行（提问 / 回复）共用它**，用户点轮末「回退」时
                # 靠它把这一轮从历史里逻辑删掉（`conversation_service.drop_turn`）。
                turn_id=turn_id,
                attachments=[a for a in (req.attachments or []) if a] or None,
            )
        except Exception as e:  # noqa: BLE001 - 落库失败不影响本次任务
            logger.warning("[agent] 用户消息落库失败: {}", e)

    # ---- 用户内容：标签包裹，明确「这是数据不是指令」----
    human_text = build_human_text(context, typed, file_text)

    # ⚠️ 用户 2026-10-11：多模态组块要用 **`vision_images`（= 用户直传图 + 文档内嵌插图，
    #    均为原始 data URL）**，不能只遍历 `req.images`。
    #    旧实现只喂 `req.images` → **文档里的图片模型根本看不到**（只看到正文的【图N】标记），
    #    于是"只能解析 Word 文字、解析不了 Word 图片"（用户实测痛点）。改后模型能**看到**
    #    文档插图内容（几何图/电路图/公式截图 …），再按【图N】回插到题目。
    #    顺序与编号天然一致：`vision_images` = 用户图在前 + 文档图顺延，`build_marked_document`
    #    的 offset 也是从"用户图数量"起编号。
    #    条件从 `if req.images:` 放宽为 `if vision_images:` —— 否则"只传文档、不传图"的用户
    #    永远进不了多模态分支（那正是本次要修的场景）。
    #    ⚠️⚠️ **必须用 `vision_images`（data URL）而不是 `image_urls`（落盘相对路径）**：
    #       OpenAI 兼容多模态端点只接受 `data:image/...;base64,` 或 `http(s)://` 绝对 URL；
    #       相对路径 `/profile/upload/...` 会被直接 400（`Unsupported image_url format`，
    #       用户 2026-10-11 实测）。落盘路径只用于**题目回插** `<img src>`（见 ctx.extra["image_urls"]）。
    if vision_images:
        lc_messages.append(HumanMessage(content=build_vision_blocks(human_text, vision_images)))
    else:
        lc_messages.append(HumanMessage(content=human_text))

    # 工具全被屏蔽时不绑定（= 纯聊天）。**不要**改成无条件 `bind_tools(tool_defs)`：
    # 实测 `bind_tools([])` 生成的是 `{"tools": []}`，会原样进请求体，
    # OpenAI 兼容端点对空 tools 数组是直接 400 的（「用户自己关了全部工具」变成报错，最糟）。
    bound_llm = llm if tools_all_disabled else llm.bind_tools(tool_defs)
    # 指挥家模式的「委派环境」：把 llm / 子代理定义 / 各自排除集 / 透传 extra 塞进 ctx.extra，
    # 供 `delegate_task` 工具取用（见 delegate.py 的模块说明）。非指挥家模式则为空。
    delegate_env: Dict[str, Any] = {}
    if conductor_mode:
        all_names_now = registry.names()
        sub_roles: Dict[str, Any] = {}
        sub_excludes: Dict[str, Any] = {}
        # ⚠️ 子代理的 exclude **不叠加 `user_disabled`（用户工具屏蔽）**：那是「指挥家自己能
        #    调什么」的裁剪面板，现已被「专家」开关取代。子代理是**某个专家本人**，它用自己
        #    白名单里的工具，能力是否可用应由**专家开关**（`disabled_role_keys`）控制，而不是
        #    被"用户把工具开关全关"波及 —— 否则旧工具面板残留的"全量 disabled"会让**所有子
        #    代理工具集为空 → 委派全线瘫痪**（用户 2026-10-11 实测：kb 子代理报"没有可用工具"，
        #    真因=旧 `ai_agent_tool_pref` 把工具全关了）。见 roles.py「子代理就是那个专家本人」。
        for sub in roles_mod.renderable_sub_agents(disabled_keys=disabled_role_keys):
            sub_roles[sub.key] = sub
            sub_excludes[sub.key] = orchestrator.compute_exclude(
                sub, all_tool_names=all_names_now, user_disabled=set()
            )
        # 用户自定义智能体也可被委派（转成 RoleSpec）
        try:
            from app.services.ai.agent import agent_config_service

            for a in await agent_config_service.list_agents(user_id):
                ur = orchestrator.build_user_role(a)
                sub_roles[ur.key] = ur
                sub_excludes[ur.key] = orchestrator.compute_exclude(
                    ur, all_tool_names=all_names_now, user_disabled=set()
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent] 读取用户智能体做委派清单失败: {}", e)
        # 用户给某专家挑了模型覆盖（专家设置面板）→ 为这些专家单独构建 LLM。
        # 没覆盖的专家复用指挥家的 llm（delegate_llms 里没有 key 时 delegate.py 走默认）。
        # ⚠️ build_agent_llm 是异步的，必须在这里（已是 async 上下文）构建，工具里只查表。
        delegate_llms: Dict[str, Any] = {}
        try:
            role_models = await agent_role_pref_service.role_model_map(user_id)
            overridden = {
                key: m
                for key, m in role_models.items()
                if key in sub_roles and str(m or "").strip()
            }
            if overridden:
                logger.info(
                    "[agent] 专家模型覆盖 {} 个: {}", len(overridden), sorted(overridden)
                )
            for key, override_model in overridden.items():
                try:
                    sub_llm, _ = await db_config.build_agent_llm(
                        db,
                        provider=req.provider,
                        model=override_model,
                        temperature=req.temperature,
                        user_id=user_id,
                        config_id=req.config_id,
                    )
                    delegate_llms[key] = sub_llm
                except Exception as e:  # noqa: BLE001 - 单个专家模型坏 → 回退默认，别拖垮整轮
                    logger.warning(
                        "[agent] 构建专家「{}」的覆盖模型 {} 失败（回退默认）: {}",
                        key, override_model, e,
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent] 读取专家模型覆盖失败（全部走默认）: {}", e)
        delegate_env = {
            "delegate_llm": llm,
            "delegate_roles": sub_roles,
            "delegate_exclude": sub_excludes,
            # 每专家的模型覆盖（仅含有覆盖的 key；没覆盖的由 delegate.py 回退 delegate_llm）
            "delegate_llms": delegate_llms,
            # 透传给子代理 ToolContext.extra 的键（附件等，子代理可能需要）
            # `user_language`：子代理的总结会原样显示在专家卡片上，必须与用户语言一致
            # （否则全英文系统提示词会让它回英文 —— 用户 2026-10-16 报）。
            "delegate_extra": {
                "attachments": attachments,
                "user_language": _detect_user_language(typed),
                # 确认策略透传给子代理：子代理跑需要确认的写操作时，与指挥家**同规则**弹卡
                #（见 sub_agent 的确认闸门）。
                "auto_confirm": bool(req.auto_confirm),
            },
        }

    ctx = build_tool_context(
        db,
        user_id,
        session_id,
        {
            "image_urls": image_urls,
            "tool_registry": registry,
            # 回退账本的归组键。⚠️ 这个 ctx 在**循环外**创建一次，所以一整轮里所有
            # 工具调用共用同一个 turn_id（这正是「回退这一轮」要的粒度）。
            "turn_id": turn_id,
            # 本轮附件正文（结构化），供 `knowledge_ingest.from_attachment` 取用：
            # [{"name": ..., "text": ...}]。没有附件时是空列表。
            "attachments": attachments,
            **delegate_env,
        },
    )

    full_text: List[str] = []
    last_tool_message = ""
    exhausted = False
    aborted = False
    dead_loop_strikes = 0
    #: 本轮由 `bank_manage create` 建出来的题库 id。**只**用于「用户取消 batch_import」时
    #: 清掉空库（见 `_rollback_empty_created_bank`）—— 不是通用回退机制（通用回退是
    #: `rollback_service` 的账本）。放本地变量是因为「本轮」= 这一次 `run_agent_stream`。
    created_banks: set = set()

    # ---- 执行统计（`metrics` 事件，底部状态条用）----
    # ⚠️⚠️ **口径必须与 ds-free 链路逐字一致**（`openstudy-vue3-ts/src/api/ai/agentDsFree.ts`），
    #    否则用户换个模型就会看到同一次提问给出两套数字（双链路同口径是红线）：
    #      · `rounds` = **完成的 LLM 往返次数**（一轮 = 一次 astream 跑完）
    #      · `steps`  = **模型请求过的工具调用条目数**（含「工具不存在」「参数校验不过」这些没真正执行的）
    #      · `llmMs`  = LLM 调用累计耗时；`toolMs` = 工具**真正执行**的累计耗时（没执行的自然不占时间）
    metrics: Dict[str, Any] = {"rounds": 0, "steps": 0, "llmMs": 0, "toolMs": 0}
    #: 每一轮「发起 LLM 调用 → 收到第一个非空可读内容」的耗时（毫秒）
    first_token_ms: List[float] = []

    def _metrics_event() -> Dict[str, Any]:
        """组装 `metrics` 事件。

        `firstTokenMs` 取**平均**，分母**只算真的收到了第一个内容 token 的轮** ——
        把失败轮按 0 计入会把平均值拉低，那不是用户想看的数。
        没有任何样本时给 `None`（前端渲染成 `—`）：**不能给 0**，0 会被读成「瞬间返回」。
        """
        ev: Dict[str, Any] = dict(metrics)
        ev["type"] = "metrics"
        ev["firstTokenMs"] = (
            round(sum(first_token_ms) / len(first_token_ms)) if first_token_ms else None
        )
        #: 首 token 的**样本数**（真的收到过第一个内容 token 的轮数）。
        # 为什么单独给一个：前端要把「本次会话」里多次提问汇总成一个平均首 token，
        # 而**平均值不能直接相加** —— 必须同时拿到总和与样本数才能正确加权。
        # 只给平均值的话，前端只能按 `rounds` 加权，那是错的：只吐 tool_calls、
        # 一个正文都没有的轮不会进样本，`rounds` 会大于样本数。
        ev["firstTokenSamples"] = len(first_token_ms)
        return ev

    # ---- ④ 主循环 ----
    # ⚠️ `delegate_seq`：**整轮（一次用户提问）内跨 LLM 轮次累积的委派序号**，供前端
    #    "一行一专家"卡片用 index 精确定位回填。**绝不能**用「每个 LLM 轮次内 `len(delegate_jobs)`」
    #    当 index —— 因为一次提问里指挥家**可能分多个 LLM 轮次**派活（一轮派几个、看结果再派几个），
    #    各轮若都从 0 重新计数就会**撞号**：后轮 index=0 的新行会被前端回填到**前轮已完成的
    #    index=0 行**上，导致它自己永远停在「进行中」（用户 2026-10-11 报：题库已建好、正文也出了，
    #    但「题库专家」那行还在转圈，其他专家正常）。故 index 必须是**整轮全局唯一**的序号。
    delegate_seq = 0
    #: 确认卡的「一次一张」闸门（用户 2026-10-17 报的 bug）。
    #:
    #: 问题：并行派两个专家时，两个子代理都会走到"需要确认"这一步，各自发一张卡片并挂起。
    #:      前端一下子收到两张，用户滚到底部只看得见**最后那张**；他点了确认，第一张却还挂着
    #:      → 后端整整等满 180 秒才超时，用户感知就是「点完确认页面傻愣着」。
    #:
    #: 方案：整轮运行共用一把 asyncio.Lock。谁拿到锁谁才能**发卡片并等待**，
    #:      另一个专家在锁外排队 —— 它那一行仍显示"正在处理…"，但不会抢着弹第二张卡。
    #:      用户确认完第一张，第二张才出现，永远不会出现"看不见的挂起卡片"。
    #:
    #: ⚠️ 必须是**每轮运行一个实例**（不是模块级全局）：
    #:    全局锁会让 A 用户的确认卡把 B 用户堵住。
    confirm_lock = asyncio.Lock()
    for loop_index in range(max(int(req.max_loops or MAX_AGENT_LOOPS), 1)):
        logger.debug("[agent] 第 {} 轮，消息数={}", loop_index + 1, len(lc_messages))
        # 每轮模型调用前先发 `waiting`：让前端在「工具跑完 → 等模型下一轮」这段也显示等待态
        #（否则只有最开始的回复有等待效果，中间工具调用过程一片空白）。
        yield _event(
            {
                "type": "waiting",
                "message": "正在理解你的需求…" if loop_index == 0 else "正在处理工具结果…",
            }
        )
        try:
            accumulated = None
            #: 兜底：某些上游/包装层返回的分片没有正确参与 `+` 合并，
            #: 导致合并后 `tool_calls` 丢失（症状是「模型明明调了工具却什么也没发生」）。
            #: 这里额外记住「最后一个非空 tool_calls」，合并结果为空时用它。
            last_tool_calls: List[Any] = []
            #: 本轮的等待提示是否已经为「工具/专家」发过（避免每个分片都发一条）
            announced_wait: Optional[str] = None
            # 指标：这一轮 LLM 的耗时与首 token 就在这里量。
            # 「首 token」= 第一个**非空可读内容**分片 —— 思考正文与正文都算（深度思考开着时，
            # 用户实际看到的第一样东西是思考卡片，只算正文会把首 token 报得偏晚）。
            llm_started = time.perf_counter()
            first_token_at: Optional[float] = None
            async for chunk in bound_llm.astream(lc_messages):
                # 思考正文先发：同一分片里既可能有思考也可能有正文，
                # 先思考后正文才符合「先想再说」的阅读顺序（UI 那边也依赖这个顺序）。
                reasoning = _reasoning_of(chunk)
                if reasoning:
                    yield _event(thinking_event(reasoning))
                text = chunk.content
                if isinstance(text, str) and text:
                    full_text.append(text)
                    yield _event(text_event(text))
                if first_token_at is None and (reasoning or (isinstance(text, str) and text)):
                    first_token_at = time.perf_counter()
                accumulated = chunk if accumulated is None else accumulated + chunk
                chunk_calls = getattr(chunk, "tool_calls", None)
                if chunk_calls:
                    last_tool_calls = list(chunk_calls)
                    # ------------------------------------------------------------
                    # 「正文说完 → 卡片出现」之间那段空白，必须有等待提示。
                    #
                    # 用户 2026-10-17 报：模型说完「我同时派两位专家并行处理…」后界面卡住，
                    # 过一会儿才直接冒出「专家协同中（2 位）」。
                    # 原因：`waiting` 只在每轮开头发一次，正文一到就被前端摘掉；而模型接下来
                    # 还在流式生成 **tool_call 的参数 JSON**（两个专家的任务描述可能很长），
                    # 这段没有任何事件 → 界面看起来像卡死。
                    #
                    # 这里在**第一个 tool_call 出现时**补一条等待提示，并区分两种文案：
                    #   · delegate_task → 「正在调用专家…」（用户明确要求与工具调用区分）
                    #   · 其它工具      → 「正在调用工具…」
                    # 前端拿到后显示统一的等待行；随后 delegate_start / tool_start 一到就替换掉。
                    # ------------------------------------------------------------
                    if announced_wait is None:
                        names = set()
                        for _tc in chunk_calls:
                            _fn = getattr(_tc, "function", None)
                            _nm = getattr(_fn, "name", None) if _fn is not None else None
                            if _nm:
                                names.add(str(_nm))
                        if names:
                            is_delegate = roles_mod.DELEGATE_TOOL_NAME in names
                            announced_wait = "delegate" if is_delegate else "tool"
                            yield _event(
                                {
                                    "type": "waiting",
                                    "message": (
                                        "正在调用专家…"
                                        if is_delegate
                                        else "正在调用工具…"
                                    ),
                                }
                            )

            # 这一轮 LLM 成功跑完才计入（抛异常的轮不算「往返」也不进首 token 分母）
            metrics["rounds"] += 1
            metrics["llmMs"] += (time.perf_counter() - llm_started) * 1000
            if first_token_at is not None:
                first_token_ms.append((first_token_at - llm_started) * 1000)
        except Exception as e:  # noqa: BLE001 - 模型调用失败
            reason = _friendly_llm_error(e)
            logger.exception("[agent] 模型调用失败: {}", reason)
            yield _event(error_event(reason))
            break

        # 这一轮的 LLM 部分已结束 → 先把「轮数 / LLM 耗时 / 首 token 平均」推给前端
        yield _event(_metrics_event())

        tool_calls = list(getattr(accumulated, "tool_calls", None) or last_tool_calls)
        if not tool_calls:
            # 没有工具调用 = 模型认为任务完成，这一轮的正文就是最终回复
            break

        # ⚠️ 服务端强制合并：模型常为「删 N 个对象」循环发起 N 个 delete 调用，而本循环
        #    **串行执行** —— 第一个 delete 就弹确认卡并挂起等用户，后面 N-1 个永远走不到，
        #    用户只看到一张「只删一个」的卡（用户 2026-10-17 报的正是这个）。
        #    必须在**写 AIMessage / 执行**之前把调用列表归一，否则 tool_call_id 会对不上。
        tool_calls, merged_note = coalesce_delete_tool_calls(tool_calls)
        if merged_note:
            yield _event(
                warning_event(
                    f"已将 {merged_note['count']} 次单独删除合并为一次批量删除，"
                    "请在卡片里勾选要删的条目"
                )
            )

        # 把「模型的这一轮」原样记进对话（含 tool_calls，否则下一轮上下文不完整）
        lc_messages.append(
            AIMessage(
                content=_text_of(accumulated),
                tool_calls=[
                    {
                        "name": call.get("name") or "",
                        "args": call.get("args") or {},
                        "id": call.get("id") or f"call_{loop_index}_{i}",
                        "type": "tool_call",
                    }
                    for i, call in enumerate(tool_calls)
                ],
            )
        )

        # 「步」= **模型本轮请求的工具调用条目数**，在遍历前**一次加完** ——
        # 放在这个位置，与下面遍历里是否被打断**无关**（止损 `break` 也影响不到它；
        # 若在遍历体内计数，`break` 之后那些条目就不算，口径会随 break 的位置漂移）。
        # 它**也**包含「工具不存在」「参数校验不过」这些**没有真正执行**的条目，
        # 所以它**不是**「工具执行次数」。
        metrics["steps"] += len(tool_calls)

        # ⚡ 并发委派（用户 2026-10-10 要求「多专家并行干活」）：
        #    同一轮里模型可能一次发起多个 `delegate_task`（"同时做 A/B/C"）。这些**委派**工具
        #    被收集到这里，等本轮所有**非委派**工具串行跑完后，再一次性 `asyncio.gather` 并发执行。
        #    为什么只有委派能并发：委派是 `write_operation=False` 且子代理各自**独立开会话**
        #    （见 run_sub_agent 的 own_session），天然并行安全；而普通写工具会共用指挥家会话的
        #    SAVEPOINT，并发会在同一条 asyncpg 连接上冲突 —— 故它们仍严格串行。
        #    每项 = (call_id, tool, params, 占位 ToolMessage 在 lc_messages 里的下标)
        delegate_jobs: List[Any] = []

        for call in tool_calls:
            tool_name = str(call.get("name") or "")
            call_id = str(call.get("id") or f"call_{loop_index}")
            raw_args = call.get("args") or {}

            tool = registry.get(tool_name)
            if tool is None:
                result = fail(
                    f"工具不存在：{tool_name}",
                    f"可用工具只有：{', '.join(registry.names())}",
                )
                lc_messages.append(tool_result_message(result, call_id))
                state.corrections += 1
                yield tool_self_correction_event(state.corrections, tool_name, result.get("error", ""))
                continue

            # 工具闸门（内联路径的**执行侧**）——拦两类：①用户屏蔽的工具；②**角色外**工具。
            # 「不广播」不等于「调用不了」：模型完全可能凭上下文里的旧工具名发起调用，
            # 这里不拦的话它会真的执行、真的写库（角色白名单也就形同虚设）。回灌一个带
            # hint 的失败信封让循环继续跑（不是 `break`），模型下一轮会改用现有工具或直接回答。
            # ⚠️ 用 `excluded_tools`（角色外 ∪ 用户屏蔽），不是 `disabled_tools`。
            if tool_name in excluded_tools:
                if tool_name in disabled_tools:
                    result = _disabled_fail(tool_name)
                else:
                    # 角色外工具：不是被用户关掉，而是本轮角色用不到它。文案要区分，
                    # 否则用户会以为「我没关这个工具，怎么用不了」。
                    result = fail(
                        f"工具 {tool_name} 不在当前智能体「{role_spec.name}」的可用范围内",
                        f"当前角色可用工具：{', '.join(sorted(registry.names() - excluded_tools))}",
                    )
                lc_messages.append(tool_result_message(result, call_id))
                state.corrections += 1
                yield tool_self_correction_event(state.corrections, tool_name, result.get("error", ""))
                # 也发一条 `tool_result`（失败态）：让用户在时间线里**看得见**「它想调用
                # 一个我关掉的工具」。没有这一条，界面上就是「它说了句话然后什么都不干」。
                # 「没有前置 `tool_start` 的 tool_result」在本循环里已是既有形态 ——
                # 用户取消那一条也是这么发的（见上面的 cancelled 分支）。
                yield _event(
                    tool_result_event(
                        tool_name,
                        raw_args.get("action"),
                        False,
                        result.get("error", ""),
                        result,
                    )
                )
                continue

            # 参数归一化 + 校验：**校验不过就不执行**，把错误当结果回灌让模型改
            params = guard.normalize_params(tool, raw_args)
            errors, hints = guard.validate_params(tool, params)
            if errors:
                result = params_validation_failure(errors, hints)
                state.corrections += 1
                state.errors.extend(errors)
                lc_messages.append(tool_result_message(result, call_id))
                yield tool_self_correction_event(state.corrections, tool_name, "；".join(errors))
                logger.info("[agent] 参数校验失败，回灌模型重试: {}", errors)
                continue

            # 死循环检测：先警告（模型多半会自己换招），警告无效才硬中断
            loop_reason = guard.note_call(state, tool_name, params)
            if loop_reason:
                dead_loop_strikes += 1
                state.errors.append(loop_reason)
                if dead_loop_strikes > DEAD_LOOP_STRIKES:
                    lc_messages.append(
                        ToolMessage(
                            content=_dumps(fail(loop_reason, "请换一种完全不同的做法")),
                            tool_call_id=call_id,
                        )
                    )
                    yield _event(warning_event(loop_reason))
                    yield _event(
                        text_event(f"\n\n（{loop_reason}）")
                    )
                    aborted = True
                    break
                # 把提示塞进工具结果，模型看到就会改参数 / 换做法
                lc_messages.append(
                    ToolMessage(
                        content=_dumps(
                            fail(
                                loop_reason,
                                "你刚刚已经用完全相同的参数调用过这个工具了，"
                                "请不要重复调用：改参数、换工具，或直接给出最终回复",
                            )
                        ),
                        tool_call_id=call_id,
                    )
                )
                yield _event(warning_event(loop_reason))
                continue

            preview: Dict[str, Any] = {}
            if tool.needs_confirmation(params):
                try:
                    preview = await tool.preview(params, ctx)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[agent] preview 失败 {}: {}", tool_name, e)

            # 确认策略：需要确认 → **挂起本轮循环**，前端弹确认卡片，用户点了再继续
            # （破坏性操作即使 autoConfirm 开着也走这里）
            #
            # ⚠️ 传 `state` 进去（2026-10-17）：让"规模闸门"这一类确认**本轮只问一次**。
            #    否则模型把 40 题拆成 3 批导入、知识点分几块写库时，会连着弹 6 张确认卡。
            if needs_user_confirmation(tool, params, req.auto_confirm, state):
                confirm_id = f"cfm_{uuid.uuid4().hex[:12]}"
                # 一次只发一张卡：拿到锁之后再发 + 等（见 `confirm_lock` 的说明）
                async with confirm_lock:
                    yield _event(
                        {
                            "type": "tool_confirm",
                            "confirmId": confirm_id,
                            "tool": tool_name,
                            "action": params.get("action"),
                            "message": _tool_start_message(tool_name, params),
                            "params": _safe_params(params),
                            "preview": preview,
                            "destructive": tool.is_destructive(params),
                        }
                    )
                    approved, edited = await _await_user_confirmation(confirm_id)
                    yield _event(
                        {
                            "type": "tool_confirm_resolved",
                            "confirmId": confirm_id,
                            "approved": approved,
                        }
                    )
                # 用户批准 → 记住「本轮已授权这个工具的这类写操作」，后续批次不再追问。
                # ⚠️ 只记**非破坏性**动作：删除要一次一问（每次删的东西都不一样、不可逆）。
                if approved and not tool.is_destructive(params):
                    state.mark_confirmed(tool_name, str(params.get("action") or ""))
                if not approved:
                    # 给模型的是**失败信封**（让它别重复同一个操作），但给**界面**的必须是
                    # 「取消」而不是「失败」：cancel 不是错误，渲染成红色失败卡片是 bug
                    # （用户 2026-10-16 报「取消批量删除却显示批量删除失败 / 执行结果为空」）。
                    # 故 UI 事件带 `cancelled:true`、中性文案、`data:None`（没有 fail 信封 →
                    # 前端不会去渲染那份空的「执行结果」）。
                    result = fail(
                        "用户取消了这次操作",
                        "不要重复尝试同一个操作；若仍需完成目标，请换一种方式或先询问用户",
                    )
                    lc_messages.append(tool_result_message(result, call_id))
                    # 取消导入时清掉「本轮刚建、且仍为空」的题库（避免留垃圾库）
                    await _rollback_empty_created_bank(
                        ctx, tool_name, params, created_banks
                    )
                    yield _event(
                        tool_result_cancelled_event(
                            tool_name, params.get("action"), "已取消"
                        )
                    )
                    continue

                # 用户确认了这次操作：若草稿编辑器回传了改动，**先用改动覆盖工具参数**
                # 再执行（见 `_apply_edited_params`）。改不动 / 改坏了都退回原参数，
                # 绝不因为一次编辑让整批导入失败。
                if edited:
                    params = await _apply_edited_params(tool, params, edited, ctx)
                    # 用户在批量删除卡上**一个都不勾**（或点了「全部不删」）→ 等同取消：
                    # 不能带着空名单去执行（那会返回一条「已删除 0 个」的假成功），
                    # 也不能默默跳过 —— 要和普通取消一样给模型一个失败信封 + 中性卡片。
                    if _is_batch_delete_draft(tool, params) and not _batch_delete_ids(
                        tool, params
                    ):
                        result = fail(
                            "用户取消了这次操作（没有勾选任何要删除的对象）",
                            "不要重复尝试同一个操作；若仍需完成目标，请先询问用户",
                        )
                        lc_messages.append(tool_result_message(result, call_id))
                        yield _event(
                            tool_result_cancelled_event(
                                tool_name,
                                params.get("action"),
                                "已取消（未勾选任何对象）",
                            )
                        )
                        continue

            # 指挥家委派：**不在这里执行**，而是收集起来，等本轮非委派工具跑完后**并发**执行
            # （见上面 `delegate_jobs` 的说明）。这里先发一条 `delegate_start`，让前端时间线
            # **立刻**显示「<子代理> 开始干活」（一行一个），并占一个 ToolMessage 位（保序）。
            if tool_name == roles_mod.DELEGATE_TOOL_NAME:
                sub_key = str(params.get("sub_agent") or "")
                sub = (ctx.extra.get("delegate_roles") or {}).get(sub_key)
                sub_name = getattr(sub, "name", sub_key) if sub else sub_key
                # ⚠️ index 取**整轮全局**的 `delegate_seq`（不用 `len(delegate_jobs)`，后者每个
                #    LLM 轮次从 0 重计、会跨轮撞号 → 前端回填错行、该行永远转圈）。见 `delegate_seq` 注释。
                this_delegate_idx = delegate_seq
                delegate_seq += 1
                yield _event(
                    {
                        "type": "delegate_start",
                        "agent": {"id": sub_key, "name": sub_name},
                        "task": str(params.get("task") or "")[:200],
                        "index": this_delegate_idx,
                    }
                )
                # 占位 ToolMessage（内容稍后回填）——保证回灌模型的 tool 结果**顺序**与
                # 模型发起的 tool_calls 一致（部分 OpenAI 兼容端点对此严格）。
                placeholder = ToolMessage(content="", tool_call_id=call_id)
                lc_messages.append(placeholder)
                delegate_jobs.append(
                    (call_id, tool, params, len(lc_messages) - 1, sub_key, sub_name, this_delegate_idx)
                )
                continue

            yield _event(
                tool_start_event(
                    tool_name,
                    params.get("action"),
                    _tool_start_message(tool_name, params),
                    _safe_params(params),
                    preview,
                    tool.needs_confirmation(params),
                )
            )

            # 只量**真正执行**的那一段（上面的「工具不存在」「参数校验不过」已 continue 走了，
            # 它们几乎不耗时，也不该混进 `toolMs`）
            tool_started = time.perf_counter()
            result = await _execute_tool(tool, params, ctx)
            metrics["toolMs"] += (time.perf_counter() - tool_started) * 1000

            # ⚠️ 写操作**显式提交** —— 不要依赖请求结束时的自动 commit：
            #    本接口是**流式响应**，而项目挂了 `BaseHTTPMiddleware`
            #    （RequestId / Log / OperationLog），它会让依赖注入的 teardown
            #    （`get_db` 里的 `commit()`）在「流还没发完」时就跑掉/跑在另一个上下文里 ——
            #    结果是工具写入被回滚，症状是「模型说建好了、刷新却什么都没有」
            #    （api 付费链路一直存在的问题；ds-free 走非流式接口所以正常）。
            if tool.write_operation and result.get("success"):
                try:
                    await ctx.db.commit()
                except Exception as e:  # noqa: BLE001 - 提交失败不影响本轮任务
                    logger.warning("[agent] 工具写入提交失败: {}", e)

            # 记下「本轮新建的题库」，供「取消导入」时清理空库（见 _rollback_empty_created_bank）
            if (
                tool_name == "bank_manage"
                and str(params.get("action") or "") == "create"
                and result.get("success")
            ):
                bank_info = result.get("bank")
                created_id = bank_info.get("bankId") if isinstance(bank_info, dict) else None
                try:
                    if created_id is not None:
                        created_banks.add(int(created_id))
                except (TypeError, ValueError):
                    pass

            # 报错自纠计数 + 让前端看得见「它在自己修」
            if not result.get("success"):
                state.corrections += 1
                reason = str(result.get("error") or "工具执行失败")
                state.errors.append(reason)
                yield tool_self_correction_event(state.corrections, tool_name, reason)

            compressed = guard.compress_result(tool_name, result)
            message = str(result.get("message") or result.get("error") or "")

            yield _event(
                tool_result_event(
                    tool_name,
                    result.get("action") or params.get("action"),
                    bool(result.get("success")),
                    message,
                    result,
                )
            )
            # 委派（delegate_task）**不会走到这里**：它在上面的收集分支已 `continue`，
            # 由本轮末尾的并发批次统一执行并回发 delegate_done（见 `delegate_jobs`）。
            if message:
                last_tool_message = message

            lc_messages.append(
                ToolMessage(content=_dumps(compressed), tool_call_id=call_id)
            )

        # ⚡ 本轮收集到的委派任务：**并发执行**（多专家同时干活）
        if delegate_jobs:
            # 标记并发：让每个 `delegate_task` 的子代理**独立开会话**（避免共用指挥家会话冲突）
            ctx.extra["delegate_parallel"] = True
            # ⚠️ 这里**不再**发 `waiting "正在安排专家并行处理…"`：本行之前每个委派都已经发过
            #    `delegate_start`（前端据它建好了「专家协同」卡片、每行都在转圈）。此时再插一句
            #    waiting 占位，只会在专家卡**下面**多冒一个转圈气泡，而专家明明已经在跑了
            #    —— 用户 2026-10-16 报「庄家已经在干活了，下方还显示正在安排专家」。

            # 每个 job 的**观测回传队列**：子代理的中间过程（`subagent_event`）与完成通知都从这里
            # 依次取出。⚠️ 为什么不再用 `asyncio.gather`：gather 会**阻塞生成器**直到整批跑完，
            #    期间一根事件都 yield 不出去（用户看不到子代理在干什么）。改成「起任务 + 边跑边取」，
            #    子代理一发事件就即时 yield 给前端。
            q: asyncio.Queue = asyncio.Queue()

            def _emit_for(job: Any):
                # ⚠️ 每个 job 一个**独立的**回调：把事件 + 本 job 的全局 seq/agent 一起塞进队列
                #    （seq 与 delegate_start/delegate_done 的 index 同源，前端据此定位卡片）。
                _cid, _tool, _params, _idx, _key, _name, _seq = job

                async def _emit(ev: Dict[str, Any]) -> None:
                    await q.put(("sub", _seq, _key, _name, ev))

                return _emit

            async def _run_delegate(job: Any) -> None:
                _cid, _tool, _params, _idx, _key, _name, _seq = job
                _res: Dict[str, Any] = {
                    "success": False,
                    "error": "委派子代理未返回结果",
                }
                try:
                    # ⚠️ `ctx.extra` 是**多个 job 共享**的：必须给每个 job 一份**浅拷贝**、各自注入
                    #    自己的 `delegate_emit`（绝不动共享的那份，否则并发时互相覆盖）。
                    job_ctx = dataclasses.replace(
                        ctx,
                        extra={
                            **ctx.extra,
                            "delegate_emit": _emit_for(job),
                            # 并行的多个专家共用同一把确认锁 → 确认卡「一次一张」，
                            # 不会出现"用户只看见最后一张、前面的挂着不动"的死锁。
                            "confirm_lock": confirm_lock,
                        },
                    )
                    _res = await _execute_tool(_tool, _params, job_ctx)
                except Exception as e:  # noqa: BLE001 - 单个委派异常不该整轮崩（_execute_tool 已吞；这里兜底）
                    logger.warning("[agent] 委派异常: {}", e)
                    _res = {"success": False, "error": str(e)}
                finally:
                    # 完成通知：无论成功失败都推一条，主循环据此回填 + 发 delegate_done
                    await q.put(("done", _seq, _key, _name, {
                        "callId": _cid,
                        "idx": _idx,
                        "key": _key,
                        "name": _name,
                        "seq": _seq,
                        "result": _res,
                    }))

            tasks = [asyncio.create_task(_run_delegate(j)) for j in delegate_jobs]
            completed = 0
            # 边跑边取：子代理事件即时下发；完成通知到了才回填 / 发 delegate_done。
            # 顺序可能是**完成顺序**（而非 job 顺序）—— 前端按 index 定位，不受影响。
            while completed < len(tasks):
                kind, *payload = await q.get()
                if kind == "sub":
                    _seq, _key, _name, _ev = payload
                    # 子代理跑需要确认的写操作时，会把 `tool_confirm` 经队列推上来 —— 它要的是
                    # **真正的**确认卡片（前端据此弹卡、POST /ai/agent/confirm 唤醒），不能裹成
                    # subagent_event（那样前端认不出、卡片永远不弹）。原样透传即可。
                    if (_ev or {}).get("type") == "tool_confirm":
                        yield _event(_ev)
                        continue
                    yield _event(
                        {
                            "type": "subagent_event",
                            "index": _seq,
                            "agent": {"id": _key, "name": _name},
                            **(_ev or {}),
                        }
                    )
                    continue
                _seq, _key, _name, item = payload
                res = item["result"]
                compressed = guard.compress_result(roles_mod.DELEGATE_TOOL_NAME, res)
                # ⚠️ `DelegateTaskTool` 成功时返回的是 `ok(subAgent, subAgentName, result, steps)`——
                #    **没有 `message` 字段**，子代理的结论在 `result` 里。若只取 message/error，
                #    成功时这里恒为空串 → 前端专家卡片「它的结论」显示「（无输出）」。
                #    故结论口径=result → message → error（用户 2026-10-11 报的"无输出"根因）。
                message = str(res.get("message") or res.get("error") or "")
                expert_summary = str(res.get("result") or res.get("message") or res.get("error") or "")
                # 回填占位 ToolMessage（保序回灌给模型）
                lc_messages[item["idx"]] = ToolMessage(
                    content=_dumps(compressed), tool_call_id=item["callId"]
                )
                yield _event(
                    tool_result_event(
                        roles_mod.DELEGATE_TOOL_NAME,
                        "delegate",
                        bool(res.get("success")),
                        message,
                        res,
                    )
                )
                yield _event(
                    {
                        "type": "delegate_done",
                        "agent": {"id": item["key"], "name": item["name"]},
                        "success": bool(res.get("success")),
                        "summary": expert_summary[:500],
                        # ⚠️ 用整轮全局的 `seq`（与 `delegate_start` 的 index 同源），**不是** `idx`
                        #    （`idx` 是占位 ToolMessage 在 lc_messages 里的下标，语义完全不同）。
                        "index": item["seq"],
                    }
                )
                if message:
                    last_tool_message = message
                completed += 1

            ctx.extra.pop("delegate_parallel", None)

        # 这一轮的工具全跑完了 → 再推一次，「步数 / 工具耗时」跟着涨
        yield _event(_metrics_event())

        if aborted:
            break
    else:
        # for 正常跑完 = 轮数用尽（没有被 break 打断）
        exhausted = True

    # ---- ⑤ 轮数用尽：再要一次「不带工具」的收尾总结 ----
    if exhausted:
        notice = f"已达到最大工具调用轮数（{req.max_loops}），任务可能尚未全部完成"
        yield _event(warning_event(notice))
        yield _event(waiting_event("正在整理执行结果…"))
        try:
            # 这句是**系统补发**的指令，不是用户说的话 → 用 <system_instruction> 标签
            # 明确标注（与 <user_request> 区分），并显式重申语言策略。
            summary_messages = lc_messages + [
                HumanMessage(
                    content=_wrap_tag(
                        "system_instruction",
                        "Summarize in 2-3 sentences: what has been completed and what is "
                        "still pending. Do NOT call any tools. Reply in the same language "
                        "as the user's latest message.",
                    )
                )
            ]
            async for chunk in llm.astream(summary_messages):
                # ⚠️ 这里**刻意不发 thinking**：收尾总结发生在正文之后，
                #    此时再吐思考会让 UI 在答案下方又冒出一块「深度思考」，是噪声。
                text = chunk.content
                if isinstance(text, str) and text:
                    full_text.append(text)
                    yield _event(text_event(text))
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent] 收尾总结失败: {}", e)

    # ---- ⑥ 收尾：落库 + 结束事件 ----
    answer = "".join(full_text).strip()
    if not answer and last_tool_message:
        answer = last_tool_message  # 一个字都没说时，至少把工具结论留下

    if req.persist and (answer or last_tool_message):
        suffix = "；".join(warnings)
        content = (
            f"{answer}\n\n> ⚠️ {suffix}" if (answer and suffix) else (answer or f"> ⚠️ {suffix}")
        )
        try:
            # 与上面那条提问**同一个 turn_id**（回退就是把这两行一起逻辑删掉）
            await conversation_service.save_message(
                user_id, session_id, "assistant", content, turn_id=turn_id
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent] Agent 回复落库失败: {}", e)

    if state.corrections:
        logger.info(
            "[agent] 任务结束：轮数={} 自纠{}次 错误={}",
            len(lc_messages),
            state.corrections,
            state.errors[:5],
        )

    yield _event(
        {
            "type": "done",
            "corrections": state.corrections,
            "errors": state.errors[:10],
            "answer": answer,
        }
    )
    yield "[DONE]"


__all__ = [
    "AgentRequest",
    "DEFAULT_AGENT_PROMPT",
    "MAX_AGENT_LOOPS",
    "TAG_USER_REQUEST",
    "TAG_ATTACHMENTS",
    "TAG_DOCUMENT",
    "TAG_CONVERSATION_HISTORY",
    "build_marked_document",
    "persist_agent_images",
    "execute_agent_tool",
    "run_agent_stream",
]
