"""
Agent **确认票据**（confirmTicket）—— 破坏性操作的服务端二次确认凭据

为什么需要它（用户裁决，2026-09-21）
------------------------------------
ds-free 链路的破坏性操作此前**只靠前端弹卡片**：`/ai/agent/execute` 直接信任请求体里的
`confirmed: true`，而前端 `executeTool` 是**无条件**填 true 的。也就是说「用户确认」这件事
在服务端**根本不存在** —— 任何人拿一个 HTTP 客户端、带上 `confirmed: true` 就能删库。
前端弹卡片是**体验**，不是**授权**。

现在的形状（契约 v1）
---------------------
1. `POST /ai/agent/preview`：**只在该次调用确实需要用户确认时**在 `data` 里多下发一个
   `confirmTicket` 字符串（判定函数与执行侧同一个：`loop.needs_user_confirmation`）。
2. `POST /ai/agent/execute`：请求体新增可选 `confirmTicket`；需要确认的操作必须带一张
   **校验通过**的票据，否则**绝不执行工具**，只回一个 `fail()` 信封。
3. `confirmed: true` 字段**保留**，但**不再是充分条件**（存量调用方不会因为少传票据而静默成功）。

票据格式
--------
    base64url(payload_json) + "." + base64url(HMAC_SHA256(secret, 域前缀 + payload_b64))

    payload = {"uid": int, "tool": str, "paramsHash": str, "exp": int(unix秒), "jti": str}

* secret 用 `settings.JWT_SECRET`，HMAC **前**加域隔离前缀（同一个 secret 在本项目还有
  别的用途，不隔离就可能被跨用途复用）；
* `paramsHash` 由 `guard.params_hash()` 算（**同一份过滤规则**，见那边）；
* TTL = 180 秒，与 `loop.CONFIRM_TIMEOUT_SECONDS` **同口径**：用户在卡片上犹豫多久，
  票据就活多久 —— 两者不一致时会出现「卡片还在等、票据已经过期」这种装不上门的组合。

⚠️ 这里只做「票据」，**不做**持久化 / 跨进程限流：已用集合（`_USED_JTI`）是**进程内**的。
   本机后端是单进程（`uvicorn` + `--reload`，没有多 worker），重启后已用集合清空 ——
   而票据 TTL 只有 180 秒，重放窗口极小，不值得为它引入 Redis 依赖。
   真要跨进程的话换 Redis 实现这两个函数即可（`verify` 的语义不变）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Tuple

from app.config import settings

#: HMAC 的**域隔离前缀** —— 与项目里其它用到同一个 secret 的签名用途隔开
DOMAIN = b"agent-confirm-ticket:v1:"

#: 票据有效期（秒）。⚠️ 与 `loop.CONFIRM_TIMEOUT_SECONDS` 同口径，改一个必须改另一个
TTL_SECONDS = 180

#: 「已用过」的 jti → 过期时间（unix 秒）。一次性：用过就不认（重放必须被拒）。
_USED_JTI: Dict[str, float] = {}


def _b64url(raw: bytes) -> str:
    """base64url（去掉 `=` 填充，便于直接放进 JSON / URL 查询串）"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64url(text: str) -> bytes:
    """base64url 解码（自己补回被去掉的 `=`）"""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    """对 `域前缀 + payload_b64` 做 HMAC-SHA256，返回 base64url 字符串"""
    mac = hmac.new(
        str(settings.JWT_SECRET).encode("utf-8"),
        DOMAIN + payload_b64.encode("ascii"),
        hashlib.sha256,
    )
    return _b64url(mac.digest())


def _purge_used(now: float) -> None:
    """清掉已过期的「已用」记录（否则这个 dict 会随进程寿命一直长）"""
    for jti, exp in list(_USED_JTI.items()):
        if exp < now:
            _USED_JTI.pop(jti, None)


def issue(
    uid: int, tool: str, params_hash: str, ttl: int = TTL_SECONDS
) -> str:
    """签发一张确认票据

    Args:
        uid: 票据只能被这个用户使用（执行侧会与 `resolve_user_scope` 的结果对账）
        tool: 工具名（与执行时的工具名**逐字**相等）
        params_hash: `guard.params_hash(归一化后的 params)`
        ttl: 有效期（秒）；测试会传负数造「已过期」的票据
    """
    now = int(time.time())
    payload: Dict[str, Any] = {
        "uid": int(uid),
        "tool": str(tool),
        "paramsHash": str(params_hash),
        "exp": now + int(ttl),
        "jti": secrets.token_urlsafe(16),
    }
    body = _b64url(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return f"{body}.{_sign(body)}"


def verify(
    token: str, uid: int, tool: str, params_hash: str
) -> Tuple[bool, str]:
    """校验票据，返回 `(是否有效, 失败原因)`

    四项**全过**才算有效：① 签名正确 ② `uid` 等于本次执行的那个用户
    ③ `tool` + `paramsHash` 与本次**归一化后**的参数一致 ④ 未过期；
    随后**立即作废**（`jti` 记入进程内已用集合）—— 所以重放同一张票必被拒。

    ⚠️ 失败原因**只给日志**：回给客户端的一律是同一句话（别告诉攻击者哪一项没过，
    那等于一个「参数探测」预言机）。
    """
    text = (token or "").strip()
    if not text:
        return False, "empty"
    if text.count(".") != 1:
        return False, "malformed"
    body, sig = text.split(".", 1)
    if not body or not sig:
        return False, "malformed"

    try:
        expected = _sign(body)
        if not hmac.compare_digest(expected, sig):
            return False, "bad_signature"
    except Exception:  # noqa: BLE001 - 非 ASCII / 畸形的签名段都算签名不过
        return False, "bad_signature"

    try:
        payload = json.loads(_unb64url(body).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False, "bad_payload"
    if not isinstance(payload, dict):
        return False, "bad_payload"

    try:
        token_uid = int(payload.get("uid"))
    except (TypeError, ValueError):
        return False, "bad_payload"
    if token_uid != int(uid):
        return False, "uid_mismatch"
    if str(payload.get("tool") or "") != str(tool):
        return False, "tool_mismatch"
    if str(payload.get("paramsHash") or "") != str(params_hash):
        return False, "params_mismatch"

    try:
        exp = float(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return False, "bad_exp"
    now = time.time()
    if exp <= now:
        return False, "expired"

    jti = str(payload.get("jti") or "")
    if not jti:
        return False, "bad_payload"
    _purge_used(now)
    if jti in _USED_JTI:
        return False, "replayed"
    # ⚠️ 到这里**四项全过**才作废 —— 校验不过的票据不该消耗掉用户真正那张票的有效性
    _USED_JTI[jti] = exp
    return True, ""


__all__ = ["DOMAIN", "TTL_SECONDS", "issue", "verify"]
