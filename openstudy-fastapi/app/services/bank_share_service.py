"""
题库分享 / 领取 的领域服务（给 `bank_share_manage` 工具用）

先弄清三件事分别是什么（**照抄既有实现，不另造语义**）
------------------------------------------------------
· **分享（share）**：题库主为自己的题库生成一个 `share_token`（长串）与 `share_code`
  （6 位码），任何人拿这两个之一都能校验/领取。**没有「分享给某个用户」这回事**
  —— 语义是「发出去一把钥匙」，谁拿到谁能领取，所以它是一笔对第三方可见的副作用。
· **领取（receive）**：别人拿 token/code 换取**只读**访问：写一条
  `bank_share_receive` 记录 + 在**领取方**名下写一条题库收藏（`user_bank_favorite`），
  首次领取还会 `receive_count += 1` 并**给题库主发一条通知**。
  题库能否编辑永远由 `question_bank.user_id` 决定 —— 分享只授予只读。
· **复制（copy）**：领取方想要「可编辑的自己的副本」时做的**深拷贝**，见
  `bank_copy_service.copy_bank_to_user`（题库 + 题目 + 子题，不带个人数据）。
  非题库主复制时**必须**题库主开放了 `allow_fork`。

⚠️ 与 `app/api/v1/bankShare.py` 的关系：**同一套语义的第二份实现，刻意暂时重复**
（该文件把逻辑写在路由处理函数里，抽出来要动 5 个正在被 e2e 覆盖的端点；
本轮的工具需求不值得为此改路由 —— 与 `user_stats_service` 的取舍理由相同）。
两份实现的对照点（改任何一边时请对照另一边）：

    bankShare.py:59   is_share_effective   ↔ 本模块 `is_share_effective`
    bankShare.py:70   format_share         ↔ 本模块 `format_share`
    bankShare.py:114  _find_share          ↔ 本模块 `find_share`
    bankShare.py:132  create_share         ↔ 本模块 `create_share`
    bankShare.py:215  revoke_share         ↔ 本模块 `revoke_share`
    bankShare.py:314  receive_share        ↔ 本模块 `receive_share`
    bankShare.py:417  check_source.canCopy ↔ 本模块 `allow_fork_ok`

⚠️ 本模块**只 `flush()`，从不 `commit()`**：它会被 `loop._execute_tool` 的 SAVEPOINT
包住（实测：在 SAVEPOINT 里 `commit()` 会抛
`Can't operate on closed transaction inside context manager`，而数据已经写进去了
—— 用户看到「失败」但其实改了）。路由的 `get_db` 负责最后那次 commit。
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_share import BankShare, BankShareReceive
from app.models.question import QuestionBank, UserBankFavorite
from app.models.user import SysUser
from app.services.notification_service import create_notification

_CODE_ALPHABET = string.ascii_uppercase + string.digits

#: 分享码长度（与 bankShare.py 一致）
CODE_LENGTH = 6


class ShareError(Exception):
    """可预期的业务失败。`code` 与既有路由返回的 `code` 对齐（403/404/410…）"""

    def __init__(self, message: str, code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def now() -> datetime:
    """本地朴素时间（与 bankShare.py 的 `_now()` 同一口径，别改成 UTC）"""
    return datetime.now()


def is_share_effective(share: Optional[BankShare]) -> bool:
    """分享是否仍然有效（未撤销 && 未过期）"""
    if not share:
        return False
    if share.status != "0":
        return False
    if share.expire_time and share.expire_time < now():
        return False
    return True


def gen_token() -> str:
    return secrets.token_urlsafe(24)


def gen_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def format_share(
    share: BankShare,
    bank: Optional[QuestionBank] = None,
    owner_name: Optional[str] = None,
) -> Dict[str, Any]:
    """分享记录 → camelCase 字典（键名与 bankShare.format_share 逐个相同）"""
    row: Dict[str, Any] = {
        "shareId": share.id,
        "bankId": share.bank_id,
        "ownerId": share.owner_id,
        "shareToken": share.share_token,
        "shareCode": share.share_code,
        "permission": share.permission or "read",
        "message": share.message,
        "expireTime": share.expire_time.isoformat() if share.expire_time else None,
        "receiveCount": share.receive_count or 0,
        "status": share.status,
        "effective": is_share_effective(share),
        "createTime": share.create_time.isoformat() if share.create_time else None,
    }
    if bank is not None:
        row["bankName"] = bank.bank_name
        row["subject"] = bank.subject
        row["coverImage"] = bank.cover_image
        row["totalQuestions"] = bank.total_questions
        row["isPublic"] = bank.is_public
    if owner_name is not None:
        row["ownerName"] = owner_name
        row["ownerNickName"] = owner_name
    return row


async def owner_name_of(db: AsyncSession, user_id: int) -> str:
    """用户昵称（拿不到就退回「用户{id}」，与 bankShare.py:105 同口径）"""
    if not user_id:
        return "未知用户"
    name = await db.scalar(select(SysUser.nick_name).where(SysUser.user_id == user_id))
    return name or f"用户{user_id}"


async def find_share(
    db: AsyncSession, token: Optional[str] = None, code: Optional[str] = None
) -> Optional[BankShare]:
    """按 token 或 code 找分享（先 token 后 code，与 bankShare.py:114 一致）"""
    if token:
        share = (
            await db.execute(select(BankShare).where(BankShare.share_token == token))
        ).scalar_one_or_none()
        if share:
            return share
    if code:
        return (
            await db.execute(
                select(BankShare)
                .where(BankShare.share_code == str(code).strip().upper())
                .order_by(BankShare.create_time.desc())
            )
        ).scalars().first()
    return None


async def get_share(db: AsyncSession, share_id: Any) -> BankShare:
    try:
        sid = int(share_id)
    except (TypeError, ValueError):
        raise ShareError(f"分享 ID 无法识别：{share_id}", 400)
    share = (
        await db.execute(select(BankShare).where(BankShare.id == sid))
    ).scalar_one_or_none()
    if share is None:
        raise ShareError(f"分享不存在：share_id={sid}", 404)
    return share


async def get_own_share(db: AsyncSession, owner_id: int, share_id: Any) -> BankShare:
    """取**自己发出的**分享。

    ⚠️ 归属校验落在 SQL 里（`owner_id`），不是在调用方 —— 分享表的 id 是全局自增，
    只按 id 取就能撤销/查看别人的分享。
    """
    try:
        sid = int(share_id)
    except (TypeError, ValueError):
        raise ShareError(f"分享 ID 无法识别：{share_id}", 400)
    share = (
        await db.execute(
            select(BankShare).where(BankShare.id == sid, BankShare.owner_id == owner_id)
        )
    ).scalar_one_or_none()
    if share is None:
        # 不区分「不存在」与「不是你的」，避免探测他人分享
        raise ShareError(f"没有找到属于你的分享：share_id={sid}", 404)
    return share


def allow_fork_ok(bank: QuestionBank, user_id: int) -> bool:
    """能不能复制这个题库：自己的随便复制；别人的要看 `allow_fork`

    `allow_fork`：0 = 不允许，1 = 允许（列默认 1）。判定与
    `bankShare.py:462` 的 `canCopy` 一致。
    """
    if int(bank.user_id or 0) == int(user_id or 0):
        return True
    return int(getattr(bank, "allow_fork", 1) or 0) != 0


async def load_copyable_bank(db: AsyncSession, user_id: int, bank_id: Any) -> QuestionBank:
    """取「要复制的源题库」，并校验这个用户**有权复制它**。

    两道闸门，缺一不可：
      1. **可见性**：题库必须是他自己的、公开的（`is_public=0`）、或他领取过分享的
         —— 否则「复制」就成了一条读别人私密题库的旁路；
      2. **`allow_fork`**：非题库主复制时，题库主必须开放了复制（0=不允许）。

    ⚠️ 第 2 条**只在源题库是别人的时候才有意义** —— 自己的题库恒可复制。
    所以「复制源必须是自己的库」这种说法与 `allow_fork` 是互斥的：真那么限制，
    `allow_fork` 就永远不会生效，列上那个开关也就成了摆设。

    可见性判定复用 `question_record_service.can_view_bank`（与路由 `_can_view_bank`
    同一套规则）—— 延迟 import 是为了不给模块之间留下循环依赖的可能。
    """
    from app.services.question_record_service import can_view_bank

    try:
        bid = int(bank_id)
    except (TypeError, ValueError):
        raise ShareError(f"题库 ID 无法识别：{bank_id}", 400)

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == bid))
    ).scalar_one_or_none()
    if bank is None:
        raise ShareError(f"题库不存在：bank_id={bid}", 404)
    if not await can_view_bank(db, user_id, bank):
        # 不区分「不存在」与「无权访问」，避免用复制接口探测别人的私密题库
        raise ShareError(f"题库不存在或无权访问：bank_id={bid}", 403)
    if not allow_fork_ok(bank, user_id):
        raise ShareError(
            f"题库「{bank.bank_name}」的主人不允许别人复制它（allow_fork=0）", 403
        )
    return bank


async def count_active_receivers(db: AsyncSession, share_id: int) -> int:
    """这条分享下**还有效**的领取人数（撤销前告诉用户会影响多少人）"""
    return int(
        await db.scalar(
            select(func.count()).where(
                BankShareReceive.share_id == share_id,
                BankShareReceive.status == "0",
            )
        )
        or 0
    )


# ---------------------------------------------------------------- 分享 / 撤销


async def create_share(
    db: AsyncSession,
    user_id: int,
    bank_id: Any,
    *,
    expire_days: Optional[Any] = None,
    message: Optional[str] = None,
) -> Tuple[BankShare, QuestionBank]:
    """为自己的题库生成分享（仅题库主）。返回 `(share, bank)`。"""
    try:
        bid = int(bank_id)
    except (TypeError, ValueError):
        raise ShareError(f"题库 ID 无法识别：{bank_id}", 400)

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == bid))
    ).scalar_one_or_none()
    if bank is None:
        raise ShareError("题库不存在", 404)
    if int(bank.user_id or 0) != int(user_id or 0):
        # 与路由的 403 同码：只有题库主才能分享
        raise ShareError("只有题库主才能分享该题库", 403)

    expire_time = None
    if expire_days not in (None, "", 0, "0"):
        try:
            expire_time = now() + timedelta(days=int(expire_days))
        except (TypeError, ValueError):
            raise ShareError("有效期格式不正确（expire_days 应为天数，或留空表示永不过期）", 400)
        if expire_time <= now():
            raise ShareError("有效期必须大于 0 天", 400)

    code = gen_code()
    for _ in range(10):
        exists = await db.scalar(select(func.count()).where(BankShare.share_code == code))
        if not exists:
            break
        code = gen_code()

    share = BankShare(
        bank_id=bid,
        owner_id=user_id,
        share_token=gen_token(),
        share_code=code,
        permission="read",
        message=(message or None),
        expire_time=expire_time,
        status="0",
    )
    db.add(share)
    # create_time 是 server_default：flush 后属性过期，不 refresh 直接读会触发
    # 同步懒加载 → 异步下 MissingGreenlet（bankShare.py:186 记着同一个坑）
    await db.flush()
    await db.refresh(share)
    return share, bank


async def my_shares(db: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
    """我发出的分享（带题库名），未过期的排前面、其余按时间倒序"""
    shares = (
        await db.execute(
            select(BankShare)
            .where(BankShare.owner_id == user_id)
            .order_by(BankShare.create_time.desc())
        )
    ).scalars().all()
    if not shares:
        return []
    bank_ids = {s.bank_id for s in shares}
    banks = (
        await db.execute(select(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
    ).scalars().all()
    bank_map = {b.id: b for b in banks}
    return [format_share(s, bank_map.get(s.bank_id)) for s in shares]


async def revoke_share(db: AsyncSession, owner_id: int, share_id: Any) -> Dict[str, Any]:
    """撤销自己发出的分享：分享置失效 + 领取记录置失效 + 逐个通知领取方

    不可逆（`status` 从 '0' 变 '1'，没有恢复入口），且会让**别人**手里的收藏失效
    —— 所以工具层把它算作破坏性操作，必须二次确认。
    """
    share = await get_own_share(db, owner_id, share_id)
    if share.status != "0":
        raise ShareError(f"这条分享已经是撤销状态了：share_id={share.id}", 400)

    share.status = "1"
    share.update_time = now()

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    ).scalar_one_or_none()
    bank_name = bank.bank_name if bank else "题库"

    receives = (
        await db.execute(
            select(BankShareReceive).where(BankShareReceive.share_id == share.id)
        )
    ).scalars().all()

    notified = 0
    for rec in receives:
        if rec.status != "0":
            continue
        rec.status = "1"
        rec.update_time = now()
        await create_notification(
            db,
            user_id=rec.receiver_id,
            notify_type="share_invalid",
            title="你收藏的分享题库已失效",
            content=f"题库《{bank_name}》的分享已被撤销，你仍可继续查看，但无法再跟随更新。",
            link="/front/myQuestion/bankCollect",
        )
        notified += 1

    await db.flush()
    return {
        "shareId": share.id,
        "bankId": share.bank_id,
        "bankName": bank_name,
        "invalidatedReceivers": notified,
    }


# ---------------------------------------------------------------- 校验 / 领取


async def share_info(
    db: AsyncSession,
    viewer_id: int,
    *,
    token: Optional[str] = None,
    code: Optional[str] = None,
) -> Dict[str, Any]:
    """校验分享（只读，不产生领取）—— 给确认卡片用：**先让用户看清要领的是什么**"""
    share = await find_share(db, token=token, code=code)
    if share is None:
        raise ShareError("分享不存在或已被删除", 404)
    if share.status != "0":
        raise ShareError("该分享已被撤销", 410)
    if share.expire_time and share.expire_time < now():
        raise ShareError("该分享已过期", 410)

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    ).scalar_one_or_none()
    if bank is None:
        raise ShareError("原题库已被删除", 404)

    data = format_share(share, bank, await owner_name_of(db, share.owner_id))
    data["received"] = bool(
        await db.scalar(
            select(func.count()).where(
                BankShareReceive.share_id == share.id,
                BankShareReceive.receiver_id == viewer_id,
            )
        )
    )
    data["isOwner"] = int(share.owner_id or 0) == int(viewer_id or 0)
    return data


async def receive_share(
    db: AsyncSession,
    user_id: int,
    *,
    token: Optional[str] = None,
    code: Optional[str] = None,
) -> Dict[str, Any]:
    """领取分享：写领取记录 + 写收藏（只读），首次领取计数并通知题库主

    幂等：重复领取不重复计数、不重复通知（与 `bankShare.receive` 一致）。
    """
    share = await find_share(db, token=token, code=code)
    if share is None:
        raise ShareError("分享不存在或已被删除", 404)
    if share.status != "0":
        raise ShareError("该分享已被撤销", 410)
    if share.expire_time and share.expire_time < now():
        raise ShareError("该分享已过期", 410)

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    ).scalar_one_or_none()
    if bank is None:
        raise ShareError("原题库已被删除", 404)

    if int(share.owner_id or 0) == int(user_id or 0):
        raise ShareError("这是你自己分享的题库，无需领取", 400)

    existed = (
        await db.execute(
            select(BankShareReceive).where(
                BankShareReceive.share_id == share.id,
                BankShareReceive.receiver_id == user_id,
            )
        )
    ).scalar_one_or_none()
    first_time = existed is None

    if first_time:
        db.add(
            BankShareReceive(
                share_id=share.id,
                bank_id=share.bank_id,
                owner_id=share.owner_id,
                receiver_id=user_id,
                source="share",
                status="0",
            )
        )
    elif existed.status != "0":
        # 撤销后又重新领取：恢复为正常
        existed.status = "0"
        existed.update_time = now()

    favorite = (
        await db.execute(
            select(UserBankFavorite).where(
                UserBankFavorite.user_id == user_id,
                UserBankFavorite.bank_id == share.bank_id,
            )
        )
    ).scalar_one_or_none()
    fav_existed = favorite is not None
    if favorite:
        favorite.favorite_status = 1
    else:
        db.add(UserBankFavorite(user_id=user_id, bank_id=share.bank_id))

    if first_time:
        share.receive_count = (share.receive_count or 0) + 1
        receiver_name = await owner_name_of(db, user_id)
        await create_notification(
            db,
            user_id=share.owner_id,
            notify_type="share_receive",
            title="有人领取了你分享的题库",
            content=f"用户「{receiver_name}」领取了你分享的题库《{bank.bank_name}》。",
            link=f"/front/questionPractice/{share.bank_id}?from=myLearning",
        )

    await db.flush()
    if first_time:
        result_status = "created"
    elif not fav_existed:
        result_status = "restored"
    else:
        result_status = "exists"
    return {
        "bankId": share.bank_id,
        "bankName": bank.bank_name,
        "alreadyReceived": not first_time,
        "resultStatus": result_status,
    }


__all__ = [
    "CODE_LENGTH",
    "ShareError",
    "allow_fork_ok",
    "count_active_receivers",
    "create_share",
    "find_share",
    "format_share",
    "gen_code",
    "gen_token",
    "get_own_share",
    "get_share",
    "is_share_effective",
    "load_copyable_bank",
    "my_shares",
    "now",
    "owner_name_of",
    "receive_share",
    "revoke_share",
    "share_info",
]
