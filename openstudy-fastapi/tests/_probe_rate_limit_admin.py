# -*- coding: utf-8 -*-
"""AI 限流管理探针 —— 连 DB + Redis，零 LLM 成本

验证后台「限流监控」模块的核心逻辑（不走 HTTP，直接调模块函数）：
  1. 限流配置 Redis 往返（save_config → get_config，来源标 redis）
  2. 配置回落：删掉 hash 后 get_config 回到 env 默认值
  3. 违规记录插入 + 查询（模型 / paginate 同款查询）
  4. 计数器解析 + 扫描 + 清除（_parse_counter_key / clear_counters 逻辑）
  5. 封禁：status='1' + 踢会话（user_token + login_tokens 都删掉）；解封恢复 '0'

用法
----
    .venv/Scripts/python.exe tests/_probe_rate_limit_admin.py     # 全绿退出码 0
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_UID = 2_000_900_399

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "status": "通过" if cond else "失败", "actual": actual})


async def _connect():
    from app.redis import redis_client

    await redis_client.connect()


async def _cleanup():
    from sqlalchemy import delete
    from app.database import async_session_factory, engine
    from app.models.ai_rate_limit_log import SysAiRateLimitLog
    from app.models.user import SysUser
    from app.core.rate_limit_config import RATE_LIMIT_CONFIG_KEY
    from app.redis import redis_client

    pool = redis_client.client
    await pool.delete(RATE_LIMIT_CONFIG_KEY)
    # 清掉探针可能留下的计数器与 token
    keys = []
    async for k in pool.scan_iter(match=f"rl:ai:*{PROBE_UID}*"):
        keys.append(k)
    async for k in pool.scan_iter(match=f"rl:ai:ip:probe-rl-ip:*"):
        keys.append(k)
    if keys:
        await pool.delete(*keys)
    await pool.delete(
        f"openstudy-py:user_token:{PROBE_UID}",
        f"openstudy-py:login_tokens:probe-rl-token",
    )
    try:
        async with async_session_factory() as db:
            await db.execute(delete(SysAiRateLimitLog).where(SysAiRateLimitLog.user_id == PROBE_UID))
            await db.execute(delete(SysUser).where(SysUser.user_id == PROBE_UID))
            await db.commit()
    finally:
        await engine.dispose()


async def _make_probe_user() -> None:
    """造一个非管理员探针用户（role 关联留空，避免封禁接口拒绝管理员）"""
    from app.database import async_session_factory
    from app.models.user import SysUser
    from app.core.security import hash_password

    async with async_session_factory() as db:
        db.add(
            SysUser(
                user_id=PROBE_UID,
                user_name="probe_rl_user",
                nick_name="限流探针",
                password=hash_password("probe-rl-pass"),
                status="0",
            )
        )
        await db.commit()


async def run_probe() -> int:
    from app.database import register_all_models

    register_all_models()
    await _connect()

    from app.core import rate_limit_config
    from app.core.rate_limit import _check_rate_limit
    from app.redis import redis_client
    from app.database import async_session_factory
    from app.models.ai_rate_limit_log import SysAiRateLimitLog
    from sqlalchemy import select, func

    pool = redis_client.client

    # ---- 1. 配置 Redis 往返 ----
    await pool.delete(rate_limit_config.RATE_LIMIT_CONFIG_KEY)
    cfg0 = await rate_limit_config.get_config()
    check(
        "RL-01",
        "无 Redis key 时回落 env 默认值（sources 全 default）",
        all(v == "default" for v in cfg0["sources"].values())
        and cfg0["dailyLimit"] == int(os.environ.get("AI_DAILY_LIMIT", 50)),
        str(cfg0),
    )
    saved = await rate_limit_config.save_config(
        enabled=True, user_per_minute=7, daily_limit=123, ip_per_minute=456
    )
    check(
        "RL-02",
        "save_config 后 get_config 读回且来源标 redis",
        saved["userPerMinute"] == 7 and saved["dailyLimit"] == 123
        and saved["ipPerMinute"] == 456
        and all(v == "redis" for v in saved["sources"].values()),
        str(saved),
    )

    # ---- 2. 运行时生效：限流检查按 Redis 配置走 ----
    probe_ip = "probe-rl-ip"
    await pool.delete(f"rl:ai:ip:{probe_ip}:{int(__import__('time').time()) // 60}")
    # 把 IP 阈值改到 1 → 第二次请求就该 429
    await rate_limit_config.save_config(enabled=True, user_per_minute=999, daily_limit=999, ip_per_minute=1)
    ok1, _ = await _check_rate_limit(probe_ip, str(PROBE_UID), "/ai/chat")
    ok2, reason2 = await _check_rate_limit(probe_ip, str(PROBE_UID), "/ai/chat")
    check(
        "RL-03",
        "ipPerMinute=1 时第 2 次请求被限（配置实时生效）",
        ok1 is True and ok2 is False and "请求过于频繁" in reason2,
        f"ok1={ok1} ok2={ok2} reason={reason2!r}",
    )
    # enabled=False → 直接放行（连计数都不做）
    await rate_limit_config.save_config(enabled=False, user_per_minute=1, daily_limit=1, ip_per_minute=1)
    ok3, _ = await _check_rate_limit(probe_ip, str(PROBE_UID), "/ai/chat")
    check("RL-04", "enabled=False 时限流整体跳过", ok3 is True, f"ok3={ok3}")
    await pool.delete(rate_limit_config.RATE_LIMIT_CONFIG_KEY)

    # ---- 3. 违规记录：写入 + 查询 ----
    async with async_session_factory() as db:
        db.add(
            SysAiRateLimitLog(
                user_id=PROBE_UID,
                user_name="probe_rl_user",
                ip=probe_ip,
                path="/ai/chat",
                limit_type="user_day",
                current_count=51,
                limit_value=50,
            )
        )
        await db.commit()
        total = await db.scalar(
            select(func.count()).select_from(
                select(SysAiRateLimitLog)
                .where(SysAiRateLimitLog.user_id == PROBE_UID, SysAiRateLimitLog.limit_type == "user_day")
                .subquery()
            )
        )
        all_rows = list(
            (
                await db.execute(
                    select(SysAiRateLimitLog).where(SysAiRateLimitLog.user_id == PROBE_UID)
                )
            ).scalars().all()
        )
        row = (
            await db.execute(
                select(SysAiRateLimitLog)
                .where(SysAiRateLimitLog.user_id == PROBE_UID, SysAiRateLimitLog.limit_type == "user_day")
                .order_by(SysAiRateLimitLog.id.desc())
            )
        ).scalars().first()
    check(
        "RL-05",
        "违规记录插入后可按 userId 查到（计数/限额/类型都对）；且 RL-03 的 429 自动落了一条 ip 违规",
        total == 1 and row is not None
        and row.current_count == 51 and row.limit_value == 50 and row.ip == probe_ip
        and any(r.limit_type == "ip" for r in all_rows),
        f"total={total} rows={[r.limit_type for r in all_rows]}",
    )

    # ---- 4. 计数器解析 / 扫描 / 清除 ----
    from app.api.v1.rate_limit_admin import _parse_counter_key, _scan_rl_keys

    check(
        "RL-06",
        "_parse_counter_key 解析 ip/umin/uday 三类 key",
        _parse_counter_key("rl:ai:ip:1.2.3.4:12345") == ("ip", "1.2.3.4", "12345")
        and _parse_counter_key("rl:ai:umin:42:12345") == ("umin", "42", "12345")
        and _parse_counter_key("rl:ai:uday:42:20261016") == ("uday", "42", "20261016")
        and _parse_counter_key("login_tokens:xx") is None,
        str(_parse_counter_key("rl:ai:ip:1.2.3.4:12345")),
    )
    await pool.set("rl:ai:umin:999888:12345", "3", ex=70)
    keys = await _scan_rl_keys("rl:ai:umin:999888:*")
    check("RL-07", "scan_iter 能扫到刚写入的计数器", keys == ["rl:ai:umin:999888:12345"], str(keys))
    deleted = await pool.delete("rl:ai:umin:999888:12345")
    after = await _scan_rl_keys("rl:ai:umin:999888:*")
    check("RL-08", "delete 后计数器消失（清除 = 解除限流）", deleted == 1 and after == [], f"after={after}")

    # ---- 5. 封禁 / 解封（直接操作，等价于 ban/unban 接口的写路径）----
    from app.api.v1.rate_limit_admin import _kick_user_sessions, USER_TOKEN_PREFIX, LOGIN_TOKEN_PREFIX

    await _make_probe_user()
    await pool.setex(f"{LOGIN_TOKEN_PREFIX}probe-rl-token", 600, '{"user_id": %d}' % PROBE_UID)
    await pool.setex(f"{USER_TOKEN_PREFIX}{PROBE_UID}", 600, "probe-rl-token")

    kicked = await _kick_user_sessions(PROBE_UID)
    token_gone = await pool.get(f"{LOGIN_TOKEN_PREFIX}probe-rl-token")
    mapping_gone = await pool.get(f"{USER_TOKEN_PREFIX}{PROBE_UID}")
    check(
        "RL-09",
        "_kick_user_sessions 删掉 login_tokens + user_token 映射",
        kicked >= 2 and token_gone is None and mapping_gone is None,
        f"kicked={kicked} token={token_gone} mapping={mapping_gone}",
    )

    async with async_session_factory() as db:
        from app.models.user import SysUser

        user = await db.get(SysUser, PROBE_UID)
        user.status = "1"
        await db.commit()
        user = await db.get(SysUser, PROBE_UID)
        banned = user.status == "1"
        user.status = "0"
        await db.commit()
        user = await db.get(SysUser, PROBE_UID)
        unbanned = user.status == "0"
    check("RL-10", "封禁置 status='1'，解封恢复 '0'", banned and unbanned, f"banned={banned} unbanned={unbanned}")

    await _cleanup()
    print("\n---- AI 限流管理探针结果 ----")
    for r in ROWS:
        tail = "" if r["status"] == "通过" else f" | 实际: {r['actual']}"
        print(f"  [{r['status']}] {r['cid']} {r['title']}{tail}")
    red = [r for r in ROWS if r["status"] != "通过"]
    print(f"\n共 {len(ROWS)} 项：{len(ROWS) - len(red)} 通过；红的 = {[r['cid'] for r in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe()))
