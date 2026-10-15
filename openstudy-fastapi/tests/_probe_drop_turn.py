# -*- coding: utf-8 -*-
"""一次性探针：**回退「这一轮对话」** = `ai_chat_message` 的逻辑删除（turn_id + del_flag）

被测对象（全部是 2026-09-23 新增的）：
  · `ai_chat_message.turn_id` / `del_flag` 两列（模型 + `database._ensure_ai_chat_message_columns`）；
  · 写入点带 turn_id：`conversation_service.save_turn`（ds-free 补写）与两条 HTTP 链路；
  · 读点补 `del_flag='0'`：`get_messages` / `get_recent_messages` / `build_context_prompt`；
  · `POST /ai/conversation/drop-turn`（端点）+ `conversation_service.drop_turn`（服务层）。
  · **`matched` 字段**（2026-09-24 新增，修「回退后刷新页面内容还在」的线上事故）：
    只回 `dropped` 时「已经删过了」与「历史里根本没有这一轮」**都是 0**，前端把后者
    当成了成功。`matched` = `(user_id, session_id, turn_id)` 命中行数，**不看 del_flag**。
    D1/D5/D9b 判「本次真的删掉了 / 删过了」，D12 判「历史里没有这一轮 → matched=0」
    （旧数据形态），D6/D6b 判越权时 matched 也为 0。
  · **空 `sessionId` 必须报错**（本次事故的形态：前端拿不到会话 id 就发空串，
    服务端一个字没说还回了个成功）→ 端点 `code=400`（D13）＋ 服务层同形状（D14）。

用法（必须用 .venv 的 python）：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_probe_drop_turn.py

退出码：0 = 全部符合预期；1 = 有红 / 环境不足（**没测到东西**也回 1）。

开头会把**被测代码的 md5**（`app/api/v1/ai.py` + `app/services/ai/conversation_service.py`）
和被 import 的 `app` 包路径打出来 —— 在镜像副本里跑变异时，这是「这一轮到底测了哪份代码」
的唯一凭据。

⚠️ 夹具规则（本仓库出过「测试清理删光真实数据」的事故）：
  · 夹具用户取**库里已存在**的 uid（`ai_chat_message.user_id` 有 FK → `sys_user`，PG 真约束）；
  · 夹具全部挂在本探针**专用的三个会话 id** 下，正文一律带 `__probe_drop_turn__` 标记；
  · 开跑前先扫掉本探针自己的历史残留（上一次崩在半路，末尾的 M1 会红得莫名其妙 —— 实测过）；
  · 收尾按**精确会话 id / 标记**物理删，并回比「不属于本探针的行一条没少、一个字段没动」。

⚠️ 本探针**不打网络、不打模型**：进程内 `httpx.ASGITransport` + `dependency_overrides`，
   所以它是秒级的，也不会因为模型上游的抖动而假红。
"""

import asyncio
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

# ⚠️ 必须先 `import app.main`：它把全量模型注册进 metadata（与同目录另几个探针同一手法）
from app.main import app as fastapi_app  # noqa: E402,F401

from app.core.security import get_current_user  # noqa: E402
from app.database import async_session_factory, init_db  # noqa: E402
from app.services.ai import conversation_service  # noqa: E402

MARK = "__probe_drop_turn__"
SESSION = MARK + "sess"
SESSION_B = MARK + "sess_b"
SESSION_W = MARK + "sess_w"
#: D12/D13/D14 专用：会话里同时有「旧数据形态」（`turn_id=''`，标记着这一轮没有轮次 id）
#: 与一轮正常的对话 —— 12/13/14 只碰这个会话，免得把别的断言的靶子一起打掉（每条只亮自己）
SESSION_L = MARK + "sess_l"
SESSIONS = (SESSION, SESSION_B, SESSION_W, SESSION_L)

TURN_1 = MARK + "turn1"
TURN_2 = MARK + "turn2"
TURN_B = MARK + "turnb"
TURN_W = MARK + "turnw"
TURN_L = MARK + "turnl"
#: D12 用：**服务端历史里根本没有**的轮次 id（旧数据形态的判据靠它）
TURN_NOSUCH = MARK + "nosuch_turn"

# 每条夹具正文一个独立标记 —— 互相**不是**子串（否则「A 在不在」会被 B 的正文污染）
T1Q = MARK + "t1q"
T1A = MARK + "t1a"
T2Q = MARK + "t2q"
T2A = MARK + "t2a"
PLQ = MARK + "plq"  # 普通助手链路：**没有** turn_id（空串）
PLA = MARK + "pla"
BQ = MARK + "bq"
BA = MARK + "ba"
WQ = MARK + "wq"
WA = MARK + "wa"
#: SESSION_L：LQ/LA 是旧数据形态（无 turn_id），L2Q/L2A 是这一轮正常的对话
LQ = MARK + "lq"
LA = MARK + "la"
L2Q = MARK + "l2q"
L2A = MARK + "l2a"
#: D11 用：**同一个轮次 id 出现在两个会话里** —— 专门隔离 WHERE 里的 session_id 条件
TURN_DUP = MARK + "turndup"
DQ = MARK + "dq"
DA = MARK + "da"
DQW = MARK + "dqw"
DAW = MARK + "daw"

#: 夹具用户：库里已存在的 uid（FK → sys_user）。取值在 main() 里填。
UID_A = 0
UID_B = 0

RESULTS = []


def check(cid, desc, ok, detail):
    RESULTS.append((cid, desc, bool(ok), detail))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {cid} {desc}")
    print(f"         {detail}")


async def one(sql, **p):
    async with async_session_factory() as s:
        return await s.scalar(text(sql), p)


async def allrows(sql, **p):
    async with async_session_factory() as s:
        return (await s.execute(text(sql), p)).all()


async def write(sql, **p):
    async with async_session_factory() as s:
        r = await s.execute(text(sql), p)
        await s.commit()
        return r


async def visible_rows(session_id, uid=None):
    """某会话里**未删**的消息行数（`del_flag='0'` 是用户唯一能看到的那些）"""
    if uid is None:
        return int(await one(
            "SELECT count(*) FROM ai_chat_message "
            "WHERE session_id = :s AND del_flag = '0'", s=session_id) or 0)
    return int(await one(
        "SELECT count(*) FROM ai_chat_message "
        "WHERE session_id = :s AND user_id = :u AND del_flag = '0'",
        s=session_id, u=uid) or 0)


async def flags_of(session_id, turn_id, uid=None):
    """按轮次取 (del_flag, 行数) —— 明细串用它渲染，**不假设行一定存在**"""
    if uid is None:
        rows = await allrows(
            "SELECT del_flag, count(*) FROM ai_chat_message "
            "WHERE session_id = :s AND turn_id = :t GROUP BY del_flag",
            s=session_id, t=turn_id)
    else:
        rows = await allrows(
            "SELECT del_flag, count(*) FROM ai_chat_message "
            "WHERE session_id = :s AND turn_id = :t AND user_id = :u GROUP BY del_flag",
            s=session_id, t=turn_id, u=uid)
    # 有则渲染、无则一句人话（`rows[0][1]` 在空列表上会抛 IndexError = 探针自己崩掉）
    return ("、".join(f"del_flag={r[0]!r}×{r[1]}" for r in rows)
            if rows else "（一行都没有 —— 这一轮的行**根本不存在**）")


async def count_marker():
    return int(await one(
        "SELECT count(*) FROM ai_chat_message WHERE POSITION(:m IN content) > 0",
        m=MARK) or 0)


async def legacy_flags(session_id, uid):
    """旧数据形态（`turn_id=''`）的行按 del_flag 分组 —— **不假设行一定存在**"""
    rows = await allrows(
        "SELECT del_flag, count(*) FROM ai_chat_message "
        "WHERE session_id = :s AND user_id = :u AND turn_id = '' GROUP BY del_flag",
        s=session_id, u=uid)
    return ("、".join(f"del_flag={r[0]!r}×{r[1]}" for r in rows)
            if rows else "（一行都没有）")


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def print_revision():
    """这一轮到底测了哪份代码 —— 镜像里跑变异时唯一的凭据（读盘，不靠印象）"""
    import app as app_pkg
    print(f"被测代码：app 包={os.path.dirname(app_pkg.__file__)}")
    for rel in ("app/api/v1/ai.py", "app/services/ai/conversation_service.py"):
        p = os.path.join(ROOT, rel)
        print(f"          {rel} md5={_md5(p) if os.path.exists(p) else '（文件不存在）'}")


async def snapshot_rows():
    """不属于本探针会话的全部行：id → (del_flag, turn_id)。

    ⚠️ 这是「用户自己的数据」的守卫：跑完必须**逐行完全相同**。
       并发插入不影响它（新 id 不在快照里），只有「别人删/改了一行」才会红。
    """
    rows = await allrows(
        "SELECT id, del_flag, turn_id FROM ai_chat_message "
        "WHERE session_id NOT IN (:s1, :s2, :s3, :s4)",
        s1=SESSIONS[0], s2=SESSIONS[1], s3=SESSIONS[2], s4=SESSIONS[3])
    return {r[0]: (r[1], r[2]) for r in rows}


def texts(msgs):
    return "\n".join(str(m.get("content") or "") for m in msgs)


async def main():
    global UID_A, UID_B

    print("=" * 78)
    print("回退本轮对话探针：turn_id + del_flag + POST /ai/conversation/drop-turn")
    print("=" * 78)
    print_revision()

    # ---------- 环境前提 ----------
    # 补列是 `init_db()` 里的 `_ensure_ai_chat_message_columns` 干的（幂等 ALTER）。
    # ASGITransport **不跑 lifespan**，所以这里显式跑一次 —— 顺带证明加列幂等（连跑两遍都绿）
    await init_db()
    cols = {r[0] for r in await allrows(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ai_chat_message'")}
    check("E0", "ai_chat_message 已有 turn_id + del_flag 两列（init_db 的幂等 ALTER 生效）",
          {"turn_id", "del_flag"} <= cols,
          f"列={sorted(cols)}")

    UID_A = int(await one("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1") or 0)
    UID_B = int(await one(
        "SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1",
        u=UID_A) or 0)
    if not UID_A or not UID_B:
        print(f"!! 库里只有一个用户（a={UID_A} b={UID_B}）→ 越权用例无法构造 → **没测到东西**，回 1")
        return 1

    # ---------- 开跑前：清掉本探针自己的历史残留 ----------
    # 判据只用「本探针专用的会话 id」+「本探针的标记」，用户数据一个字节都不碰。
    for s in SESSIONS:
        await write("DELETE FROM ai_chat_message WHERE session_id = :s", s=s)
        await write("DELETE FROM ai_chat_session WHERE session_id = :s", s=s)
    await write("DELETE FROM ai_chat_message WHERE POSITION(:m IN content) > 0", m=MARK)
    if await count_marker():
        print("!! 残留清理没干净 → 先手工看一眼，别把上一轮的红算到这一轮头上")
        return 1

    before_rows = await snapshot_rows()
    print(f"\n环境：uid_a={UID_A} uid_b={UID_B}；不属于本探针的行 {len(before_rows)} 条（跑完必须逐行不变）")

    # ---------- W1 服务层写入点带 turn_id（运行时）----------
    await conversation_service.save_turn(
        UID_A, SESSION, user_text=T1Q, assistant_text=T1A, turn_id=TURN_1)
    t1_rows = await allrows(
        "SELECT role, turn_id FROM ai_chat_message "
        "WHERE session_id = :s AND user_id = :u AND turn_id = :t ORDER BY id",
        s=SESSION, u=UID_A, t=TURN_1)
    check("W1", "save_turn(..., turn_id=) 把轮次 id **逐字**写进两行（提问 + 回复）",
          [r[0] for r in t1_rows] == ["user", "assistant"]
          and all(r[1] == TURN_1 for r in t1_rows),
          f"行={[(r[0], r[1]) for r in t1_rows]}")

    # ---------- W2 HTTP 补写链路（ds-free）收得下 turnId ----------
    # ⚠️ 这里测的是**请求体模型声明**（pydantic 默认忽略未知字段 → 不声明就被静默丢掉，
    #    落库全是空串、回退按前端的 t_... 一行都匹配不到）。用 HTTP 打一遍最实在。
    from httpx import ASGITransport, AsyncClient

    fastapi_app.dependency_overrides[get_current_user] = (
        lambda: {"user_id": UID_A, "roles": [], "user_name": "probe"})
    client = AsyncClient(transport=ASGITransport(app=fastapi_app),
                         base_url="http://probe", timeout=30)
    try:
        r = await client.post(f"/ai/conversation/{SESSION_W}/messages", json={
            "userMessage": WQ, "assistantMessage": WA, "turnId": TURN_W})
        w_rows = await allrows(
            "SELECT role, turn_id FROM ai_chat_message "
            "WHERE session_id = :s AND user_id = :u ORDER BY id",
            s=SESSION_W, u=UID_A)
        check("W2", "POST /ai/conversation/{sid}/messages 的 turnId **不是**静默丢掉："
                    "两行都带上它（`SaveConversationBody.turnId` 声明生效）",
              r.status_code == 200 and [x[0] for x in w_rows] == ["user", "assistant"]
              and all(x[1] == TURN_W for x in w_rows),
              f"HTTP={r.status_code} 行={[(x[0], x[1]) for x in w_rows]}")

        # ---------- W3 源码级：两条链路的写入点各就各位（**不是**运行时断言）----------
        loop_src = open(os.path.join(ROOT, "app/services/ai/agent/loop.py"),
                        encoding="utf-8").read()
        engine_src = open(os.path.join(ROOT, "app/services/ai/chat_engine.py"),
                          encoding="utf-8").read()
        loop_calls = [loop_src[m.start():m.start() + 400]
                      for m in re.finditer(r"conversation_service\.save_message\(", loop_src)]
        engine_calls = [engine_src[m.start():m.start() + 400]
                        for m in re.finditer(r"conversation_service\.save_message\(", engine_src)]
        check("W3", "源码级：agent 循环的 2 个 save_message 调用点都传 `turn_id=turn_id`；"
                    "普通助手链路（chat_engine）**不传**（保持空串）",
              len(loop_calls) == 2 and all("turn_id=turn_id" in c for c in loop_calls)
              and len(engine_calls) == 2
              and all("turn_id" not in c for c in engine_calls),
              f"loop.py 调用点={len(loop_calls)}（带 turn_id 的="
              f"{sum('turn_id=turn_id' in c for c in loop_calls)}）；"
              f"chat_engine.py 调用点={len(engine_calls)}（带 turn_id 的="
              f"{sum('turn_id' in c for c in engine_calls)}）"
              "  ［源码级断言：把两行改成静态检查，是因为跑真循环要打模型］")

        # ---------- 夹具：会话 SESSION = 两轮 + 两行「没有轮次 id」的历史写法 ----------
        await conversation_service.save_turn(
            UID_A, SESSION, user_text=T2Q, assistant_text=T2A, turn_id=TURN_2)
        # 普通助手链路的写法：**不传** turn_id → 空串（空值绝不是通配符，见 D7/D8）
        await conversation_service.save_message(UID_A, SESSION, "user", PLQ)
        await conversation_service.save_message(UID_A, SESSION, "assistant", PLA)

        # SESSION_L：**旧数据形态**（`turn_id=''`，线上 32 行就是这个样子）+ 一轮正常对话。
        # D12/D13/D14 只碰这个会话 —— 与 SESSION 里那对空 turn_id 行隔开，每条断言只亮自己的灯。
        await conversation_service.save_message(UID_A, SESSION_L, "user", LQ)
        await conversation_service.save_message(UID_A, SESSION_L, "assistant", LA)
        await conversation_service.save_turn(
            UID_A, SESSION_L, user_text=L2Q, assistant_text=L2A, turn_id=TURN_L)

        # 越权夹具（裸 SQL，免得污染 A 的会话计数）：
        #   · B 的两行落在**同一个会话 id** 下 → 专门隔离「WHERE 少了 user_id」这一条
        #   · 另有 B 自己的会话 SESSION_B → 隔离「WHERE 少了 session_id」
        for c, t in ((BQ, TURN_B), (BA, TURN_B)):
            await write(
                "INSERT INTO ai_chat_message "
                "(session_id, user_id, role, content, attachments, turn_id, del_flag, create_time) "
                "VALUES (:s, :u, 'user', :c, NULL, :t, '0', now())",
                s=SESSION, u=UID_B, c=c, t=t)
        await write(
            "INSERT INTO ai_chat_session "
            "(session_id, user_id, title, message_count, create_time, update_time) "
            "VALUES (:s, :u, :t, 2, now(), now())",
            s=SESSION_B, u=UID_B, t=MARK + "b_sess")
        for c in (BQ, BA):
            await write(
                "INSERT INTO ai_chat_message "
                "(session_id, user_id, role, content, attachments, turn_id, del_flag, create_time) "
                "VALUES (:s, :u, 'user', :c, NULL, :t, '0', now())",
                s=SESSION_B, u=UID_B, c=c, t=TURN_B)
        print(f"\n夹具：A 的会话可见行={await visible_rows(SESSION, UID_A)}；"
              f"B 在 A 的会话里 {await flags_of(SESSION, TURN_B, UID_B)}；"
              f"B 自己的会话可见行={await visible_rows(SESSION_B, UID_B)}；"
              f"SESSION_L 可见行={await visible_rows(SESSION_L, UID_A)}"
              f"（旧数据形态 {await legacy_flags(SESSION_L, UID_A)}）")

        # ---------- D1 端点：回退第一轮 ----------
        # ⚠️ 判据同时看 `dropped` 与 `matched`：
        #    · 只判 dropped 时「删掉了 2 行」与「恰好也有 2 行本来没删」分不出；
        #    · matched=2 说明服务端**确实看见**这一轮的两行 —— 事故当天它是 0（历史里没有
        #      轮次标记），前端却只看 dropped。
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": TURN_1})
        b1 = r.json()
        d1 = b1.get("data") or {}
        check("D1", "POST /ai/conversation/drop-turn → dropped=2 **且 matched=2**；"
                    "两行**仍在库里**（逻辑删，不是物理删）且 del_flag='2'",
              r.status_code == 200 and b1.get("code") == 200 and d1.get("dropped") == 2
              and d1.get("matched") == 2 and "dropped" in d1 and "matched" in d1
              and int(d1.get("matched", -1)) >= int(d1.get("dropped", -1)),
              f"HTTP={r.status_code} body={json.dumps(b1, ensure_ascii=False)}；"
              f"该轮现状：{await flags_of(SESSION, TURN_1, UID_A)}")

        # ---------- D2/D3/D4 三个读点：看不到这一轮（但看得到别的行 —— 正对照）----------
        msgs = await conversation_service.get_messages(UID_A, SESSION)
        joined = texts(msgs)
        check("D2", "读点① get_messages：被回退的那一轮**看不见**；第二轮 / 无 turn_id 的行还在",
              T1Q not in joined and T1A not in joined
              and T2Q in joined and T2A in joined and PLQ in joined and PLA in joined,
              f"返回 {len(msgs)} 条；含 t1q={T1Q in joined} t1a={T1A in joined} "
              f"t2q={T2Q in joined} plq={PLQ in joined}")

        recent = await conversation_service.get_recent_messages(UID_A, SESSION, 50)
        rj = texts(recent)
        check("D3", "读点② get_recent_messages：同上（这一条是上下文的下游）",
              T1Q not in rj and T1A not in rj and T2Q in rj and PLQ in rj,
              f"返回 {len(recent)} 条；含 t1q={T1Q in rj} t1a={T1A in rj} t2q={T2Q in rj}")

        ctx = await conversation_service.build_context_prompt(UID_A, SESSION, lang="en")
        check("D4", "读点③ build_context_prompt（**喂给模型的上下文**）：被回退的那一轮不在里面",
              T1Q not in ctx and T1A not in ctx and T2Q in ctx,
              f"上下文长度={len(ctx)}；含 t1q={T1Q in ctx} t1a={T1A in ctx} "
              f"t2q={T2Q in ctx}；片段={ctx[:80]!r}")

        # ---------- D5 幂等 ----------
        # ⚠️ **本次修复的关键分辨力就在这一条**：`dropped=0` 有两种含义，必须分开 ——
        #    · `matched=2` = 这一轮的两行确实在（都已经 '2' 了）→「已经删过了」，幂等成功；
        #    · `matched=0` = 这一轮在服务端历史里**根本没有**（事故当天的形态）。
        #    把 matched 也算上、而不是只看 dropped，就是这一条在守。
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": TURN_1})
        b5 = r.json()
        d5 = b5.get("data") or {}
        check("D5", "同一轮再删一次 → dropped=0（幂等，不是报错）**但 matched=2**"
                    "（=「已经删过了」，与「历史里没有这一轮」的 matched=0 分得开）",
              b5.get("code") == 200 and d5.get("dropped") == 0 and d5.get("matched") == 2,
              f"body={json.dumps(b5, ensure_ascii=False)}；"
              f"该轮现状：{await flags_of(SESSION, TURN_1, UID_A)}")

        # ---------- D6 越权：别人的轮次删不动（**能红**：WHERE 去掉 user_id 就会红）----------
        # ⚠️ matched 也必须是 0：COUNT 里少了 user_id，matched 会变成 2（B 的两行）→ 红。
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": TURN_B})
        b6 = r.json()
        d6 = b6.get("data") or {}
        b_same_session = await flags_of(SESSION, TURN_B, UID_B)
        check("D6", "越权：以 uid_a 身份删 **uid_b** 在同一会话里的轮次 → dropped=0 且 matched=0，"
                    "B 的两行仍是 '0'",
              b6.get("code") == 200 and d6.get("dropped") == 0 and d6.get("matched") == 0
              and await one(
                  "SELECT count(*) FROM ai_chat_message WHERE session_id = :s "
                  "AND turn_id = :t AND del_flag = '0'", s=SESSION, t=TURN_B) == 2,
              f"data={json.dumps(d6, ensure_ascii=False)}；B 的行现状：{b_same_session}")

        # ---------- D6b 越权：别人的会话 id（隔离 session_id 条件）----------
        b_counter_before = int(await one(
            "SELECT message_count FROM ai_chat_session WHERE session_id = :s",
            s=SESSION_B) or -1)
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION_B, "turnId": TURN_B})
        b6b = r.json()
        d6b = b6b.get("data") or {}
        b_counter_after = int(await one(
            "SELECT message_count FROM ai_chat_session WHERE session_id = :s",
            s=SESSION_B) or -1)
        check("D6b", "越权②：别人的会话 id → dropped=0 且 matched=0，B 的行仍是 '0'，"
                     "且 **B 的会话计数没被改**（重算步骤也不许碰别人的会话行）",
              b6b.get("code") == 200 and d6b.get("dropped") == 0 and d6b.get("matched") == 0
              and await one(
                  "SELECT count(*) FROM ai_chat_message WHERE session_id = :s "
                  "AND turn_id = :t AND del_flag = '0'", s=SESSION_B, t=TURN_B) == 2
              and b_counter_before == b_counter_after == 2,
              f"data={json.dumps(d6b, ensure_ascii=False)}；B 会话计数 {b_counter_before}→{b_counter_after}")

        # ---------- D9a 会话列表计数 == 实际可见条数 ----------
        sessions = await conversation_service.list_sessions(UID_A)
        mine = next((x for x in sessions if x["sessionId"] == SESSION), None)
        actual = await visible_rows(SESSION, UID_A)
        check("D9a", "会话列表 messageCount == 该会话**实际可见**条数（4 = 第二轮 2 + 无轮次 2）",
              mine is not None and mine.get("messageCount") == actual == 4,
              f"列表里的 messageCount={mine.get('messageCount') if mine else '（会话不在列表里）'}"
              f"；实际可见={actual}")

        # ---------- D9b 计数器漂移后仍被**重算**到实际值（不是「按删除条数减」）----------
        await write("UPDATE ai_chat_session SET message_count = 99 WHERE session_id = :s",
                    s=SESSION)
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": TURN_2})
        b9 = r.json()
        sessions2 = await conversation_service.list_sessions(UID_A)
        mine2 = next((x for x in sessions2 if x["sessionId"] == SESSION), None)
        actual2 = await visible_rows(SESSION, UID_A)
        check("D9b", "计数器被人为改成 99 后回退第二轮 → messageCount 被**重算**成 2（= 实际可见），"
                     "而不是「99-2=97」（口径：计数器只用来给用户看真实条数）；"
                     "且 dropped=2 与 matched=2 一致（本次真的删掉了）",
              (b9.get("data") or {}).get("dropped") == 2
              and (b9.get("data") or {}).get("matched") == 2
              and mine2 is not None and mine2.get("messageCount") == actual2 == 2,
              f"data={json.dumps(b9.get('data'), ensure_ascii=False)}；"
              f"messageCount={mine2.get('messageCount') if mine2 else 'n/a'}；实际可见={actual2}")

        # ---------- D7/D8 空 turnId 的两道闸门 ----------
        # ⚠️ 刻意排在**最后**（D9a/D9b 之后）：这两条验证的是「空值会不会被当通配符」，
        #    而被测对象万一真的把空值当通配符，它会删掉会话里 `turn_id=''` 的那两行
        #    （普通助手链路写的历史）—— 排在前面就会把后面依赖「还有几条可见行」的断言
        #    一起拖红，看不出到底是谁的锅。排在最后 = 每条断言只亮自己的灯。
        #
        # 端点闸门：删光整个会话的历史写法就是这里要挡的
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": ""})
        b7 = r.json()
        visible_after_empty = await visible_rows(SESSION, UID_A)
        check("D7", "turnId 为空 → code=400，且**一行都没被删**"
                    "（此时会话里只剩 2 行 `turn_id=''` 的历史写法，正是空值通配符会命中的靶子）",
              b7.get("code") == 400 and visible_after_empty == 2,
              f"body={json.dumps(b7, ensure_ascii=False)}；该会话未删行={visible_after_empty}（期望 2）")

        # 服务层闸门：端点挡在前面，这里**直调服务层**隔离它
        dropped_empty = await conversation_service.drop_turn(UID_A, SESSION, "")
        check("D8", "服务层 drop_turn(..., '') → {'dropped': 0, 'matched': 0}，且一行都没删"
                    "（与端点各挡一层；空 turn_id 若当通配符会命中那 2 行）",
              dropped_empty == {"dropped": 0, "matched": 0}
              and await visible_rows(SESSION, UID_A) == 2,
              f"返回={dropped_empty!r}；该会话未删行={await visible_rows(SESSION, UID_A)}（期望 2）")

        # ---------- D11 同一个轮次 id 出现在两个会话 → 只删指定会话里的那些 ----------
        # ⚠️ 这一条专门隔离 WHERE 里的 `session_id`：少了它，删一个会话会把**别的会话里
        #    同 id 的轮次**一起删掉（前端的轮次 id 是每轮新生成的，但历史/兜底 id 可能撞）。
        await conversation_service.save_turn(
            UID_A, SESSION, user_text=DQ, assistant_text=DA, turn_id=TURN_DUP)
        await conversation_service.save_turn(
            UID_A, SESSION_W, user_text=DQW, assistant_text=DAW, turn_id=TURN_DUP)
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION, "turnId": TURN_DUP})
        b11 = r.json()
        other_kept = await one(
            "SELECT count(*) FROM ai_chat_message WHERE session_id = :s "
            "AND turn_id = :t AND del_flag = '0'", s=SESSION_W, t=TURN_DUP)
        check("D11", "同一个 turnId 落在两个会话 → 只删**指定会话**里的两行（dropped=2 **且 matched=2**）；"
                     "另一个会话里同 id 的两行仍是 '0'（隔离 WHERE / COUNT 的 session_id 条件）",
              (b11.get("data") or {}).get("dropped") == 2
              and (b11.get("data") or {}).get("matched") == 2
              and other_kept == 2,
              f"data={json.dumps(b11.get('data'), ensure_ascii=False)}；"
              f"目标会话：{await flags_of(SESSION, TURN_DUP, UID_A)}；"
              f"**另一个会话**里同 id 未删行数={other_kept}（期望 2）")

        # ---------- D10 负对照：证明 D1 的判据不是恒真（catch_all 假 200）----------
        r = await client.post("/ai/conversation/drop-tur",
                              json={"sessionId": SESSION, "turnId": TURN_2})
        b10 = r.json()
        check("D10", "负对照：路径打错一个字母 → catch_all 假 200，且 **data 里没有 dropped**"
                     "（D1/D5/D9b 判的就是这个形状）",
              r.status_code == 200 and b10.get("data") is None
              and "dropped" not in json.dumps(b10),
              f"HTTP={r.status_code} body={json.dumps(b10, ensure_ascii=False)[:110]}")

        # ---------- D12 **旧数据形态**：服务端历史里根本没有这一轮 ----------
        # 线上事故的形态：`ai_chat_message` 里 32 行 `turn_id` 全是空串（前端补写时没带
        # turnId），前端却拿 `t_...` 去回退 —— 一行都匹配不到，服务端回 `{"dropped": 0}`，
        # 前端当成功。这一条守的就是「此时 `matched` 必须是 0」：
        #   · 少了 `matched` 字段（本次修复前）→ 红；
        #   · `matched` 忘了按 `turn_id` 过滤（变成「这个会话里有多少行」= 4）→ 红；
        #   · `matched` 忘了按 `user_id` 过滤 → 这里没有别人的行，不亮（那是 D6 的灯）。
        l_legacy_before = await legacy_flags(SESSION_L, UID_A)
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": SESSION_L, "turnId": TURN_NOSUCH})
        b12 = r.json()
        d12 = b12.get("data") or {}
        l_visible = await visible_rows(SESSION_L, UID_A)
        check("D12", "旧数据形态：会话里只有 `turn_id=''` 的历史行 + 另一轮，"
                     "用一个**不存在的 turnId** 回退 → matched=0 且 dropped=0"
                     "（=「这一轮在服务端历史里没有轮次标记」，而不是「删过了」）；"
                     "这个会话的行一行都没动",
              b12.get("code") == 200 and d12.get("matched") == 0 and d12.get("dropped") == 0
              and l_visible == 4
              and await flags_of(SESSION_L, TURN_L, UID_A) == "del_flag='0'×2",
              f"data={json.dumps(d12, ensure_ascii=False)}；SESSION_L 可见行={l_visible}（期望 4）；"
              f"TURN_L 现状：{await flags_of(SESSION_L, TURN_L, UID_A)}；"
              f"旧数据形态 {l_legacy_before} → {await legacy_flags(SESSION_L, UID_A)}")

        # ---------- D13/D14 空 sessionId：**不许静默返 0** ----------
        # 本次事故的直接形态：前端拿不到会话 id 时发了空串，服务层静默返 0，端点回
        # `{"dropped": 0}` = 前端眼里的成功，而服务端**一行都没删**。
        # ⚠️ 与 D7/D8 同一理由排在**最后**（万一被测对象把空值当通配符，它会删东西）。
        #
        # D14 先直调服务层（把端点闸门摘出去，隔离服务层那一层）
        svc_empty_sid = await conversation_service.drop_turn(UID_A, "", TURN_L)
        check("D14", "服务层 drop_turn(uid, '', turnId) → {'dropped': 0, 'matched': 0}，"
                     "且那一轮的两行仍是 '0'（空 session_id 不当通配符）",
              svc_empty_sid == {"dropped": 0, "matched": 0}
              and await flags_of(SESSION_L, TURN_L, UID_A) == "del_flag='0'×2",
              f"返回={svc_empty_sid!r}；TURN_L 现状：{await flags_of(SESSION_L, TURN_L, UID_A)}")

        # D13 端点：空 sessionId 必须回 code=400（**不是**回一个「成功但 dropped=0」）
        r = await client.post("/ai/conversation/drop-turn",
                              json={"sessionId": "", "turnId": TURN_L})
        b13 = r.json()
        check("D13", "空 sessionId → code=400 且提示里点到 sessionId"
                     "（修复前：code=200 + {\"dropped\": 0} = 静默成功），一行都没被删",
              b13.get("code") == 400 and "sessionId" in json.dumps(b13, ensure_ascii=False)
              and b13.get("data") is None
              and await visible_rows(SESSION_L, UID_A) == 4
              and await flags_of(SESSION_L, TURN_L, UID_A) == "del_flag='0'×2",
              f"body={json.dumps(b13, ensure_ascii=False)}；"
              f"SESSION_L 可见行={await visible_rows(SESSION_L, UID_A)}（期望 4）；"
              f"TURN_L 现状：{await flags_of(SESSION_L, TURN_L, UID_A)}")
    finally:
        fastapi_app.dependency_overrides.pop(get_current_user, None)
        await client.aclose()

    # ================= M1/M2 清理与回比 =================
    for s in SESSIONS:
        await write("DELETE FROM ai_chat_message WHERE session_id = :s", s=s)
        await write("DELETE FROM ai_chat_session WHERE session_id = :s", s=s)

    left_marker = await count_marker()
    left_sess = 0
    for s in SESSIONS:
        left_sess += int(await one(
            "SELECT count(*) FROM ai_chat_message WHERE session_id = :s", s=s) or 0)
    check("M1", "夹具残留 0（消息 + 会话行，按本探针专用 id / 标记物理删）",
          left_marker == 0 and left_sess == 0,
          f"带标记的行={left_marker}；本探针会话下的行={left_sess}")

    after_rows = await snapshot_rows()
    changed = {k: (before_rows[k], after_rows[k]) for k in before_rows
               if k in after_rows and before_rows[k] != after_rows[k]}
    missing = [k for k in before_rows if k not in after_rows]
    check("M2", "**用户自己的数据一条没少、一个字段没动**"
                "（不属于本探针会话的行：id → (del_flag, turn_id) 跑前跑后完全相同）",
          not changed and not missing,
          f"{len(before_rows)} → {len(after_rows)} 行；被改动的={len(changed)}{list(changed.items())[:3]}；"
          f"消失的={len(missing)}{missing[:5]}")

    bad = [r for r in RESULTS if not r[2]]
    print(f"\n结果：{len(RESULTS) - len(bad)}/{len(RESULTS)} 通过"
          + (f"；红：{[r[0] for r in bad]}" if bad else "（全绿）"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
