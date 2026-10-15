"""
AI 对话历史服务（**纯 SQL 存储，不依赖 Redis**）

 - 会话索引：ai_chat_session
 - 消息明细：ai_chat_message（role / content / attachments）

历史实现用 Redis（`ai:conversation:{userId}:{sessionId}` + 会话索引），
已全量改为落库：重启不丢、清缓存不丢、可按用户直接查询统计，
也因此不需要 Redis 常驻（AI 功能不再受 Redis 可用性影响）。

对外函数与原 Redis 版保持一致，调用方（app/api/v1/ai.py）无需改动。
本模块自行开数据库会话（调用方不持有 db），单次操作一个短事务。

「回退本轮对话」与逻辑删除（`ai_chat_message.turn_id` / `del_flag`）
------------------------------------------------------------------
- `turn_id`：一轮对话（一次提问 + 它对应的那次回复）的 id；同一轮的两行**共用**它。
- `del_flag`：`'0'` 未删 / `'2'` 已删（**逻辑**删，口径同 `note` / `ai_agent_memory`）。
- 用户点轮末「回退」= `drop_turn()` 把该轮的行置 `'2'`，行**仍在库里**（可追溯），
  但所有读取路径都看不见它。`drop_turn` 回 `{"dropped", "matched"}` 两个数：
  `dropped` = 本次改了几行，`matched` = 这一轮在历史里到底有几行（**不看 del_flag**）。
  只有 `matched` 能把「已经删过了」与「历史里根本没有这一轮」分开（2026-09-23 的事故：
  前端只看 `dropped`，于是把「一行都没删到」当成了成功）。

⚠️ **读点清单**（改这一块时逐条对）：
  1. `get_messages`            —— 会话历史（`/ai/conversation/{sid}` 端点用它）
  2. `get_recent_messages`     —— 最近 N 条（`build_context_prompt` 的下游）
  3. `build_context_prompt`    —— **喂给模型的上下文**（漏了 = 「删了，但模型还记得这一轮」，
                                  症状是下一轮回答还在提上一轮的事）。它本身不查库、
                                  走 ②，所以 ② 修好它就跟着好 —— 但探针**分别**断言两者。
  4. `save_turn` 的返回值 / `list_sessions` 的 `messageCount` —— 都是「用户能看到几条」的口径。
     前者走 ①，后者是 `ai_chat_session.message_count` 这个**计数器**（不是查询），
     所以 `drop_turn` 必须把它重算到与实际一致（见该函数注释）。
  5. `delete_session` / `clear_messages` —— **整会话删除 / 清空**，刻意保持**物理删**
     （理由见各自 docstring）。
"""

import json
import time
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, func, select, update
from loguru import logger

from app.database import async_session_factory
from app.models.ai_chat import AiAgentTimeline, AiChatMessage, AiChatSession

# 拼接上下文时最多回溯多少条历史。
# ⚠️ 这只是**安全上限**（防止一次拉太多行），真正决定截断位置的是下面的字符预算。
#    单独用它做控制会有两个方向的毛病：
#      · 短消息（「嗯」「好」）白占额度，10 条可能只覆盖几分钟对话
#      · 长消息（贴了一大段代码）一条就能把上下文撑爆
#    所以条数上限放开到 50，由预算来定实际留下多少条。
CONTEXT_LIMIT = 10  # 保留：向后兼容外部可能传入的 limit
# 实际回溯条数（安全上限）
CONTEXT_FETCH_LIMIT = 50
# 历史上下文的**字符预算**。
# 估算口径（不做真分词，避免引入 tokenizer 依赖）：
#   · 中文约 1 字 ≈ 1 token
#   · 英文/代码约 4 字符 ≈ 1 token
# 所以按字符算对英文是**高估** token 数 —— 偏保守，不会把上下文算爆。
CONTEXT_BUDGET_CHARS = 6000
# 单条消息在上下文里的最大字符数。超出只保留**首尾**（结论常在末尾）。
CONTEXT_SINGLE_MAX_CHARS = 1500
# 无论预算怎么算，至少保留最近这么多条 —— 否则一条超长消息会把历史整个挤空，
# 模型连「上一句问了什么」都不知道，多轮对话直接断掉。
CONTEXT_MIN_KEEP = 2
# 单条被截断时的省略标记
CONTEXT_ELLIPSIS = "\n…（中间略）…\n"
# 会话列表最多返回条数
SESSIONS_LIMIT = 100
# 会话标题最长字符数
SESSION_TITLE_LIMIT = 30
# 空会话的占位标题（首条用户消息会把它替换掉）
DEFAULT_TITLE = "新会话"
# 消息内容里的附件占位（纯附件消息没有正文）
ATTACHMENT_PLACEHOLDER = "[附件]"
# `ai_chat_message.del_flag` 的两个取值（口径与 `note` / `ai_agent_memory` 完全一致）
DEL_FLAG_UNDELETED = "0"  # 未删
DEL_FLAG_DELETED = "2"  # 已删（用户点了轮末的「回退」）


def new_session_id() -> str:
    """生成一个新的会话 id"""
    return f"asst_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def _ms(dt: Optional[datetime]) -> int:
    """datetime -> 毫秒时间戳（前端按毫秒处理）"""
    if not dt:
        return int(time.time() * 1000)
    try:
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


def _parse_attachments(raw: Optional[str]) -> Optional[list]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def _to_message_dict(row: AiChatMessage) -> dict:
    """DB 行 -> 前端使用的消息结构（字段名与旧 Redis 版保持一致，前端无需改动）"""
    item: dict = {
        "role": row.role,
        "content": row.content or "",
        "timestamp": _ms(row.create_time),
    }
    attachments = _parse_attachments(row.attachments)
    if attachments:
        item["attachments"] = attachments
    return item


async def list_sessions(user_id: Optional[int]) -> List[dict]:
    """获取会话列表（按最后更新时间倒序）"""
    async with async_session_factory() as db:
        result = await db.execute(
            select(AiChatSession)
            .where(AiChatSession.user_id == (user_id or 0))
            .order_by(AiChatSession.update_time.desc())
            .limit(SESSIONS_LIMIT)
        )
        rows = result.scalars().all()
        return [
            {
                "sessionId": row.session_id,
                "title": row.title or DEFAULT_TITLE,
                "createdAt": _ms(row.create_time),
                "updatedAt": _ms(row.update_time),
                "messageCount": row.message_count or 0,
            }
            for row in rows
        ]


async def touch_session(
    user_id: Optional[int],
    session_id: str,
    title: Optional[str] = None,
    delta_messages: int = 0,
) -> None:
    """在会话索引里新建 / 更新一个会话（title 只在首次写入时生效）"""
    async with async_session_factory() as db:
        now = datetime.now()
        row = await db.get(AiChatSession, session_id)

        if row is None:
            db.add(
                AiChatSession(
                    session_id=session_id,
                    user_id=user_id or 0,
                    title=(title or DEFAULT_TITLE)[:SESSION_TITLE_LIMIT],
                    message_count=delta_messages or 0,
                    create_time=now,
                    update_time=now,
                )
            )
        else:
            # 空会话的占位标题，会被首条用户消息替换
            if title and row.title in (None, "", DEFAULT_TITLE):
                row.title = title[:SESSION_TITLE_LIMIT]
            row.update_time = now
            if delta_messages:
                row.message_count = (row.message_count or 0) + delta_messages

        await db.commit()


async def delete_session(user_id: Optional[int], session_id: str) -> None:
    """删除会话：同时清掉消息和会话行

    ⚠️ 这里是**物理删**（`delete(AiChatMessage)`），也**刻意不带 `del_flag` 过滤** ——
    连同之前被回退（`'2'`）的行一起清掉。理由有两条：

      1. 语义不同：轮末「回退」= 让那一轮从历史里消失（可追溯，故逻辑删）；
         删会话 = 用户明确说「这个会话我不要了」—— 留一堆谁也看不见的行是纯垃圾。
      2. 逻辑删的行**没有任何 UI 能到达**（读点全部过滤 `'0'`），留在库里就永远清不掉。
         本仓库对「逻辑删后的清理」一贯要求**物理删**（同 `rag_knowledge_base`）。
    """
    uid = user_id or 0
    async with async_session_factory() as db:
        row = await db.get(AiChatSession, session_id)
        # 属于别人的会话不动（避免越权删除）
        if row is not None and (row.user_id or 0) != uid:
            return
        await db.execute(
            delete(AiChatMessage).where(
                AiChatMessage.session_id == session_id,
                AiChatMessage.user_id == uid,
            )
        )
        # 顺带删掉智能体时间线快照，避免留下孤儿数据
        tl = await db.get(AiAgentTimeline, session_id)
        if tl is not None:
            await db.delete(tl)
        if row is not None:
            await db.delete(row)
        await db.commit()


async def get_messages(user_id: Optional[int], session_id: str) -> List[dict]:
    """获取某个会话的全部历史消息（按时间正序）

    ⚠️ **必须带 `del_flag == '0'`**：用户点了轮末「回退」的那一轮已经逻辑删除，
    这里再放出来就是「回退之后刷新，那一轮又回来了」（读点清单见模块 docstring）。
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(AiChatMessage)
            .where(
                AiChatMessage.user_id == (user_id or 0),
                AiChatMessage.session_id == session_id,
                AiChatMessage.del_flag == DEL_FLAG_UNDELETED,
            )
            .order_by(AiChatMessage.id.asc())
        )
        return [_to_message_dict(row) for row in result.scalars().all()]


async def get_recent_messages(
    user_id: Optional[int], session_id: str, limit: int = CONTEXT_LIMIT
) -> List[dict]:
    """获取最近 N 条历史消息（返回时仍按时间正序）

    ⚠️ **必须带 `del_flag == '0'`**：它是 `build_context_prompt` 的下游，也就是
    「喂给模型的上下文」。漏掉这一处，被回退掉的那一轮仍然会进上下文 —— 模型的
    下一轮回答还在提上一轮的事，而聊天记录里那一轮已经不见了（最难查的一类不一致）。
    """
    async with async_session_factory() as db:
        stmt = (
            select(AiChatMessage)
            .where(
                AiChatMessage.user_id == (user_id or 0),
                AiChatMessage.session_id == session_id,
                AiChatMessage.del_flag == DEL_FLAG_UNDELETED,
            )
            .order_by(AiChatMessage.id.desc())
        )
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [_to_message_dict(row) for row in rows]


async def save_message(
    user_id: Optional[int],
    session_id: str,
    role: str,
    content: str,
    turn_id: str = "",
    **extra,
) -> None:
    """追加一条消息到会话历史

    extra 目前支持 attachments（附件元信息列表），其余键忽略，
    不写库以免表结构随调用方变化。

    `turn_id`：这一条属于哪一轮对话（同一轮的两行共用它）。
      · api 付费链路（`loop.run_agent_stream`）传本轮 id，回退才定位得到这两行；
      · ds-free 链路补写历史走 `save_turn`，同样传；
      · 普通助手链路（`chat_engine`）没有轮次概念 → **不传**，落空串
        （空串在回退里**不是通配符**，见 `drop_turn`）。
    ⚠️ 是**关键字参数、放在 `content` 之后**：位置参数一个都没动，既有调用方无需改。
    """
    uid = user_id or 0
    attachments = extra.get("attachments")
    text = content or ""

    async with async_session_factory() as db:
        now = datetime.now()
        db.add(
            AiChatMessage(
                session_id=session_id,
                user_id=uid,
                role=role,
                content=text,
                attachments=(
                    json.dumps(attachments, ensure_ascii=False) if attachments else None
                ),
                turn_id=(turn_id or "")[:64],
                del_flag=DEL_FLAG_UNDELETED,
                create_time=now,
            )
        )

        # 同步维护会话索引：用首条用户消息作为会话标题
        title = None
        if role == "user" and text.strip():
            title = text.strip().replace("\n", " ")

        row = await db.get(AiChatSession, session_id)
        if row is None:
            db.add(
                AiChatSession(
                    session_id=session_id,
                    user_id=uid,
                    title=(title or DEFAULT_TITLE)[:SESSION_TITLE_LIMIT],
                    message_count=1,
                    create_time=now,
                    update_time=now,
                )
            )
        else:
            if title and row.title in (None, "", DEFAULT_TITLE):
                row.title = title[:SESSION_TITLE_LIMIT]
            row.update_time = now
            row.message_count = (row.message_count or 0) + 1

        await db.commit()


async def save_turn(
    user_id: Optional[int],
    session_id: str,
    user_text: str = "",
    assistant_text: str = "",
    attachments: Optional[list] = None,
    turn_id: str = "",
) -> List[dict]:
    """把「一轮对话」原子写库（提问 + 回复同一个事务）

    为什么需要它：
      ds-free（浏览器扩展直连 chat.deepseek.com）链路完全不经过后端，历史只能
      由前端补写。之前前端分两次 save_message（先 user、再 assistant），各自
      一个事务，一旦第二条插入失败 / 请求被中断，库里就留下「只有提问、没有
      AI 回复」的半截会话 —— 前端刷新后看起来就是「历史丢了」。
      放进一个事务后，两行要么都在、要么都不在。

    入参语义：
      - user_text / attachments：用户这一轮的提问（attachments 只存缩略图）
      - assistant_text：AI 回复正文
      - 只传 assistant_text 表示「补写回复」（前端先写提问、拿到回复再补一次）
      - 只传 user_text / attachments 表示「先落提问」，回复稍后单独补写

    `turn_id`：这一轮对话的 id（**同一轮的两行共用**），由调用方带上来
    （ds-free 链路的 `POST /ai/conversation/{sid}/messages` 的 `turnId`）。
    补写（先提问、后补回复）会分两次调用 —— 两次**都要带同一个 turn_id**，
    否则回退时那两行分不到一轮里。⚠️ 关键字参数、放在最后：位置参数一个都没动。
    """
    uid = user_id or 0
    user_text = user_text or ""
    assistant_text = assistant_text or ""
    atts = attachments or None
    tid = (turn_id or "")[:64]
    has_user = bool(user_text.strip() or atts)
    has_assistant = bool(assistant_text.strip())

    if not has_user and not has_assistant:
        # 两边都空：不写空行，直接把当前历史回给前端
        return await get_messages(uid, session_id)

    async with async_session_factory() as db:
        now = datetime.now()

        title: Optional[str] = None
        if has_user:
            text = user_text if user_text.strip() else ATTACHMENT_PLACEHOLDER
            db.add(
                AiChatMessage(
                    session_id=session_id,
                    user_id=uid,
                    role="user",
                    content=text,
                    attachments=(
                        json.dumps(atts, ensure_ascii=False) if atts else None
                    ),
                    turn_id=tid,
                    del_flag=DEL_FLAG_UNDELETED,
                    create_time=now,
                )
            )
            # 用首条用户消息作为会话标题
            if text.strip():
                title = text.strip().replace("\n", " ")

        if has_assistant:
            db.add(
                AiChatMessage(
                    session_id=session_id,
                    user_id=uid,
                    role="assistant",
                    content=assistant_text,
                    turn_id=tid,
                    del_flag=DEL_FLAG_UNDELETED,
                    create_time=now,
                )
            )

        added = int(has_user) + int(has_assistant)

        # 同步维护会话索引：没有会话行就建（首条提问定标题），有就累加计数
        row = await db.get(AiChatSession, session_id)
        if row is None:
            db.add(
                AiChatSession(
                    session_id=session_id,
                    user_id=uid,
                    title=(title or DEFAULT_TITLE)[:SESSION_TITLE_LIMIT],
                    message_count=added,
                    create_time=now,
                    update_time=now,
                )
            )
        else:
            if title and row.title in (None, "", DEFAULT_TITLE):
                row.title = title[:SESSION_TITLE_LIMIT]
            row.update_time = now
            row.message_count = (row.message_count or 0) + added

        await db.commit()

    # 留痕：线上排查「历史为什么没存上」时，先看这几行
    logger.info(
        "save_turn session={} user={} user_len={} atts={} assistant_len={}",
        session_id, uid, len(user_text), len(atts or []), len(assistant_text),
    )
    return await get_messages(uid, session_id)


async def clear_messages(user_id: Optional[int], session_id: str) -> bool:
    """清空某个会话的历史消息（保留会话本身）

    ⚠️ 与 `delete_session` 同一口径：**物理删**、不过滤 `del_flag`
    （被回退过的行一并清掉），理由见 `delete_session` 的 docstring。
    顺手把 `message_count` 归 0 —— 它本来就是这个函数在维护的计数器，
    清空之后必须与实际（0 条可见消息）一致。
    """
    uid = user_id or 0
    async with async_session_factory() as db:
        await db.execute(
            delete(AiChatMessage).where(
                AiChatMessage.session_id == session_id,
                AiChatMessage.user_id == uid,
            )
        )
        # 时间线快照同步清掉
        tl = await db.get(AiAgentTimeline, session_id)
        if tl is not None:
            await db.delete(tl)
        row = await db.get(AiChatSession, session_id)
        if row is not None:
            row.message_count = 0
            row.update_time = datetime.now()
        await db.commit()
    return True


async def drop_turn(
    user_id: Optional[int], session_id: str, turn_id: str
) -> dict:
    """把「一轮对话」（提问 + 回复）从历史里**逻辑删除**。

    返回 `{"dropped": n, "matched": m}`：

      · `dropped` = 本次真的被改成 `'2'` 的行数（`'0'` → `'2'`；提问 + 回复 = 2 是常态）；
      · `matched` = 这一轮在这个会话的历史里**到底有几行**
        （`(user_id, session_id, turn_id)` 命中数，**不看 `del_flag`**）；
      · 关系恒为 `dropped <= matched`：
          - `matched == 0`：这一轮在这里**根本没有行**（旧数据 `turn_id` 是空串、
            id 传错、会话传错、或者不是这个用户的）；
          - `dropped == 0 且 matched > 0`：**已经删过了**（幂等，不是失败）；
          - `matched == dropped > 0`：本次真的删掉了。

    ⚠️ **只回 `dropped` 分不出前两种（都是 0）** —— 2026-09-23 的线上事故正是如此：
    前端把 `{"dropped": 0}` 当成功、UI 上这一轮消失了，而服务端历史**一行都没动**，
    刷新页面那一轮又回来了。`matched` 就是给调用方分辨「删过了 / 没删到」用的。

    用户点轮末「回退」时由 `POST /ai/conversation/drop-turn` 调用。与
    `ai/agent/rollback`（撤销这一轮的**写操作**）是两个动作，前端各调一次。

    删除范围**只按三个条件**：`user_id = 登录用户` **且** `session_id` **且**
    `turn_id = 精确值`。三者缺一不可 —— 少 `user_id` 就是越权删别人的会话，
    少 `turn_id` 就是把整个会话扫进来（见下面的空值闸门）。

    为什么是**逻辑**删（`'2'`）而不是物理删：回退是高频、可误点的操作，行留在库里
    才说得清「这一轮本来是什么」；物理删则完全不可追溯。行数不再是 `'0'` 的那些
    由「删除整个会话」两个入口（`delete_session` / `clear_messages`）物理清掉。

    幂等：同一轮删两次，第二次命中 0 行 → `dropped=0`（**不是**错误）。
    `del_flag` 条件同时挡住「把已经删掉的行再刷一遍」，回执才诚实。

    ⚠️ **空 turn_id / 空 session_id 绝不当通配符**：空串会匹配所有「没有轮次 id」
    的历史行（普通助手链路写的就是空串），一次点击就把整个会话删光。
    服务层与端点各挡一层（这里返回 `{"dropped": 0, "matched": 0}`，不自作主张删）。
    """
    uid = user_id or 0
    sid = str(session_id or "")
    tid = str(turn_id or "").strip()
    if not tid or not sid:
        # 空轮次 id / 空会话 id：什么都不做（调用方按 matched=0 报「没删到」）
        logger.warning("[conversation] drop_turn 缺少定位条件：session={} turn={}", sid, tid)
        return {"dropped": 0, "matched": 0}

    async with async_session_factory() as db:
        result = await db.execute(
            update(AiChatMessage)
            .where(
                AiChatMessage.user_id == uid,
                AiChatMessage.session_id == sid,
                AiChatMessage.turn_id == tid,
                AiChatMessage.del_flag == DEL_FLAG_UNDELETED,
            )
            .values(del_flag=DEL_FLAG_DELETED)
        )
        dropped = int(result.rowcount or 0)

        # ---- matched：这一次请求在服务端历史里到底命中了多少行（不看 del_flag）----
        # ⚠️ 三个要点，别改回去：
        #   1. **不筛 `del_flag`**：它的语义是「这一轮在历史里有没有行」，不是
        #      「还有几行没删」。筛了 del_flag 就退化成第二个 `dropped`，
        #      「已经删过了」与「历史里根本没有这一轮」又分不开 —— 那正是本次事故。
        #   2. **必须与 UPDATE 同一个会话、同一个事务**（就是上面的 `db`）：分成两个
        #      会话/事务读，并发下会出现 `dropped > matched` 这种自相矛盾的读数。
        #   3. **刻意排在 UPDATE 之后**：这样 `matched - dropped` 恰好等于「本来就是
        #      `'2'` 的行数」，`dropped <= matched` 恒成立（反过来先 COUNT 再 UPDATE，
        #      并发插入会让读数矛盾）。
        matched = int(
            await db.scalar(
                select(func.count())
                .select_from(AiChatMessage)
                .where(
                    AiChatMessage.user_id == uid,
                    AiChatMessage.session_id == sid,
                    AiChatMessage.turn_id == tid,
                )
            )
            or 0
        )

        # ---- 会话列表的计数：**重算**，不按 `dropped` 减 ----
        # `message_count` 是个**计数器**（`save_message` / `save_turn` 每次 +1），
        # `list_sessions` 直接读它而不是查库。于是有两条口径可选：
        #   · 按 `dropped` 减：便宜，但一旦计数器本来就有偏差（历史行 / 当年
        #     `create_session` 落过空壳 / 中途失败），偏差会**永久留着**；
        #   · 重算（`count(*) where del_flag='0'`）：一次索引内计数，多重算的代价换来
        #     「计数器永远等于用户真实能看到的条数」—— 计数器的唯一用途就是给人看
        #     这个数，偏差没有任何信息价值。这里选重算。
        row = await db.get(AiChatSession, sid)
        if row is not None and (row.user_id or 0) == uid:
            visible = await db.scalar(
                select(func.count())
                .select_from(AiChatMessage)
                .where(
                    AiChatMessage.user_id == uid,
                    AiChatMessage.session_id == sid,
                    AiChatMessage.del_flag == DEL_FLAG_UNDELETED,
                )
            )
            row.message_count = int(visible or 0)
            # 会话内容变了，列表排序（按 update_time 倒序）跟着走 —— 与 clear_messages 同口径
            row.update_time = datetime.now()

        await db.commit()

    logger.info(
        "drop_turn session={} user={} turn={} dropped={} matched={}",
        sid, uid, tid, dropped, matched,
    )
    return {"dropped": dropped, "matched": matched}


def _render_text(msg: dict) -> str:
    """取一条消息用于拼上下文的正文。纯附件消息给占位符。"""
    text = msg.get("content") or ""
    if not text and msg.get("attachments"):
        return ATTACHMENT_PLACEHOLDER
    return text


def _clip_single(text: str, limit: int = CONTEXT_SINGLE_MAX_CHARS) -> str:
    """单条过长时只保留首尾。

    为什么保留末尾：结论、报错、最终答案几乎都在末尾，只留开头会正好丢掉最有用的部分。
    """
    if len(text) <= limit:
        return text
    # 首比尾多留一点 —— 开头通常交代了「在说什么」
    head = limit * 6 // 10
    tail = limit - head
    return text[:head] + CONTEXT_ELLIPSIS + text[-tail:]


def trim_history_by_budget(
    history: List[dict],
    max_chars: int = CONTEXT_BUDGET_CHARS,
    min_keep: int = CONTEXT_MIN_KEEP,
) -> List[dict]:
    """从**最近往前**累加，超出字符预算就停，返回仍按时间正序的历史。

    为什么从最近的开始算：越近的消息对当前这轮越重要，预算不够时要丢的是最早的。

    `min_keep` 是兜底：即使第一条就超预算，也保证最近 `min_keep` 条在 ——
    否则一条超长消息会把历史整个挤空，模型连「上一句问了什么」都不知道。
    """
    if not history:
        return []

    kept: List[dict] = []
    used = 0
    for msg in reversed(history):
        cost = len(_render_text(msg))
        if kept and (used + cost > max_chars and len(kept) >= min_keep):
            break
        kept.append(msg)
        used += cost

    kept.reverse()
    if len(kept) < len(history):
        logger.info(
            f"[context] 历史按预算截断：{len(history)} 条 → {len(kept)} 条"
            f"（{used} 字符 / 预算 {max_chars}）"
        )
    return kept


async def build_context_prompt(
    user_id: Optional[int],
    session_id: str,
    limit: Optional[int] = None,
    lang: str = "cn",
    max_chars: int = CONTEXT_BUDGET_CHARS,
    single_max_chars: int = CONTEXT_SINGLE_MAX_CHARS,
) -> str:
    """把最近的历史对话拼接成上下文提示词（对齐 springboot3 的 buildContextPrompt）

    Args:
        limit: 最多回溯多少条。`None`（默认）用 `CONTEXT_FETCH_LIMIT`（50）——
               条数只是安全上限，**真正决定留下多少条的是 `max_chars` 预算**。
               传 0 或负数表示不限制条数。
        lang: 包装语言。
              - `"cn"`（默认）：`【对话历史】` + `用户/AI：` —— 聊天助手场景沿用，
                行为与改造前完全一致，不要动。
              - `"en"`：`<conversation_history>` + `User/Assistant:` —— Agent 场景使用。
                Agent 的系统提示词是全英文的，历史上下文也必须是英文标签，否则模型要
                在两种语言的分隔约定之间来回切换，容易把历史里的中文当成用户新指令。
        max_chars: 历史正文的字符预算（见 `CONTEXT_BUDGET_CHARS` 的估算口径）。
                   由调用方按「模型配置的上下文档位」传入 —— 见
                   `app/services/ai/context_budget.py`。
        single_max_chars: 单条历史消息的字符上限（超出只保留首尾）。
    """
    fetch = CONTEXT_FETCH_LIMIT if limit is None else limit
    history = await get_recent_messages(user_id, session_id, fetch)
    if not history:
        return ""

    history = trim_history_by_budget(history, max_chars)

    if (lang or "cn").lower().startswith("en"):
        lines = ["<conversation_history>"]
        for msg in history:
            role_name = "Assistant" if msg.get("role") == "assistant" else "User"
            lines.append(f"{role_name}: {_clip_single(_render_text(msg), single_max_chars)}")
        lines.append("</conversation_history>")
        return "\n".join(lines)

    lines = ["【对话历史】"]
    for msg in history:
        role_name = "AI" if msg.get("role") == "assistant" else "用户"
        lines.append(f"{role_name}：{_clip_single(_render_text(msg), single_max_chars)}")
    lines.append("---")
    return "\n".join(lines)


async def save_agent_timeline(
    user_id: Optional[int], session_id: str, messages: list,
    metrics: Optional[dict] = None,
) -> None:
    """保存智能体的**完整时间线快照**（含工具调用卡片 + 会话执行统计）

    与 save_turn 的分工：
      - `save_turn` / `ai_chat_message`：只存「提问 + 最终回复」两行 —— 供会话列表统计、
        后端拼上下文用，**不含卡片**；
      - 本函数：把前端 `useAgentChat` 的整条消息流原样存一份 JSON —— 供前端刷新后
        复原 UI（工具卡片、状态、自我纠正都在）。一个会话只保留最新一份（覆盖写）。

    为什么要单独存：只从 `ai_chat_message` 复原的话，刷新后工具卡片全丢、只剩纯文本，
    用户看到的就是「卡片没了 / 变成死数据」。

    ⚠️ 2026-10-10 起 payload 由「纯数组」升级为对象 `{"messages": [...], "metrics": {...}}`：
        多存一份**会话累计执行统计**（轮数/步数/耗时）—— 否则底部状态条刷新后归零
        （用户报的 bug）。读取端 `get_agent_timeline` 对**旧数组格式**做兼容。

    Args:
        messages: 前端消息流 [{role,type,content,tool,action,status,params,data,...}]
        metrics: 会话累计统计 {rounds, steps, llmMs, toolMs, ftSum, ftSamples}；None 则不存
    """
    uid = user_id or 0
    payload_obj: dict = {"messages": messages or []}
    if metrics:
        payload_obj["metrics"] = metrics
    payload = json.dumps(payload_obj, ensure_ascii=False)
    async with async_session_factory() as db:
        row = await db.get(AiAgentTimeline, session_id)
        now = datetime.now()
        if row is None:
            db.add(
                AiAgentTimeline(
                    session_id=session_id,
                    user_id=uid,
                    payload=payload,
                    update_time=now,
                )
            )
        else:
            row.payload = payload
            row.update_time = now
        await db.commit()
    logger.info(
        "save_agent_timeline session={} user={} messages={} has_metrics={} bytes={}",
        session_id, uid, len(messages or []), bool(metrics), len(payload),
    )


async def get_agent_timeline(
    user_id: Optional[int], session_id: str
) -> dict:
    """读取智能体的完整时间线快照

    返回 `{"messages": [...], "metrics": {...} | None}`：
      · 没有快照 / 不属于该用户 → `{"messages": [], "metrics": None}`
        （前端据此退回读 `ai_chat_message`，老会话仍能看到纯文本问答）；
      · **兼容旧格式**：升级前 payload 是**纯数组**，此时 `metrics` 为 None（旧会话无统计，
        状态条显示 0，与升级前一致、不倒退）。
    """
    uid = user_id or 0
    empty = {"messages": [], "metrics": None}
    async with async_session_factory() as db:
        row = await db.get(AiAgentTimeline, session_id)
        if row is None:
            return empty
        # user_id 为 0 视为「未知归属」，宽松放行；非 0 且不匹配则不返回（避免越权读）
        if row.user_id and row.user_id != uid:
            return empty
        try:
            data = json.loads(row.payload or "[]")
        except Exception:  # noqa: BLE001
            return empty
        # 新格式：{"messages": [...], "metrics": {...}}
        if isinstance(data, dict):
            msgs = data.get("messages")
            mt = data.get("metrics")
            return {
                "messages": msgs if isinstance(msgs, list) else [],
                "metrics": mt if isinstance(mt, dict) else None,
            }
        # 旧格式：纯数组（无统计）—— 兼容保留
        if isinstance(data, list):
            return {"messages": data, "metrics": None}
        return empty


async def delete_agent_timeline(user_id: Optional[int], session_id: str) -> None:
    """删除某会话的时间线快照（删会话 / 清空历史时同步调用）"""
    uid = user_id or 0
    async with async_session_factory() as db:
        row = await db.get(AiAgentTimeline, session_id)
        if row is None:
            return
        if row.user_id and row.user_id != uid:
            return
        await db.delete(row)
        await db.commit()


__all__ = [
    "CONTEXT_LIMIT",
    "CONTEXT_FETCH_LIMIT",
    "CONTEXT_BUDGET_CHARS",
    "CONTEXT_SINGLE_MAX_CHARS",
    "CONTEXT_MIN_KEEP",
    "new_session_id",
    "touch_session",
    "list_sessions",
    "delete_session",
    "save_message",
    "save_turn",
    "get_messages",
    "get_recent_messages",
    "trim_history_by_budget",
    "clear_messages",
    "drop_turn",
    "build_context_prompt",
    "save_agent_timeline",
    "get_agent_timeline",
    "delete_agent_timeline",
]

logger.debug("conversation_service loaded (SQL backend)")
