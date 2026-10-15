"""
题库分享 API

链路：题库主 A 生成分享链接 / 分享码  ->  用户 B 打开链接或输入分享码  ->  B 领取
      ->  写入 B 的「题库收藏」（来源=分享，只读）+ 领取记录  ->  通知 A

设计要点
--------
1. 分享只授予**只读**：题库能否编辑永远由 question_bank.user_id 决定，
   领取方即使调接口也会被 questions.py 的写权限校验拦下。
2. 领取是幂等的：同一用户重复领取同一分享不会产生重复收藏。
3. 失效有两条来源：分享被撤销（status='1'）或超过 expire_time。

端点
----
POST   /bankShare/bankShare/create                 生成分享（仅题库主）
GET    /bankShare/bankShare/my                     我发出的分享列表
POST   /bankShare/bankShare/revoke/{share_id}      撤销分享（仅题库主）
GET    /bankShare/bankShare/info/{token}           校验分享（落地页预展示）
GET    /bankShare/bankShare/infoByCode/{code}      按分享码校验
POST   /bankShare/bankShare/receive                领取分享（token 或 code）
GET    /bankShare/bankShare/checkSource/{bank_id}  查询我与该题库的关系（是否来自分享 / 能否编辑）
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, error
from app.models.question import QuestionBank, UserBankFavorite
from app.models.bank_share import BankShare, BankShareReceive
from app.models.user import SysUser
from app.services.notification_service import create_notification

router = APIRouter()

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _now() -> datetime:
    return datetime.now()


def _gen_token() -> str:
    return secrets.token_urlsafe(24)


def _gen_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def is_share_effective(share: BankShare) -> bool:
    """分享是否仍然有效（未撤销 && 未过期）"""
    if not share:
        return False
    if share.status != "0":
        return False
    if share.expire_time and share.expire_time < _now():
        return False
    return True


def format_share(share: BankShare, bank: Optional[QuestionBank] = None, owner_name: Optional[str] = None):
    effective = is_share_effective(share)
    row = {
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
        "effective": effective,
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


async def _get_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


async def _get_owner_name(db: AsyncSession, user_id: int) -> str:
    if not user_id:
        return "未知用户"
    row = await db.scalar(
        select(SysUser.nick_name).where(SysUser.user_id == user_id)
    )
    return row or f"用户{user_id}"


async def _find_share(db: AsyncSession, token: Optional[str], code: Optional[str]) -> Optional[BankShare]:
    if token:
        result = await db.execute(select(BankShare).where(BankShare.share_token == token))
        share = result.scalar_one_or_none()
        if share:
            return share
    if code:
        result = await db.execute(
            select(BankShare)
            .where(BankShare.share_code == str(code).strip().upper())
            .order_by(BankShare.create_time.desc())
        )
        return result.scalars().first()
    return None


# ========== 生成 / 管理 ==========

@router.post("/bankShare/bankShare/create")
async def create_share(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """生成题库分享链接（仅题库主可操作）

    body: { bankId, expireDays?: number|null, message?: string }
    """
    body = await _get_body(request)
    bank_id = body.get("bankId") or body.get("bank_id")
    if not bank_id:
        return error("bankId 不能为空")

    user_id = current_user.get("user_id")

    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
    bank = bank_result.scalar_one_or_none()
    if not bank:
        return error("题库不存在")
    if bank.user_id != user_id:
        return error("只有题库主才能分享该题库", code=403)

    expire_days = body.get("expireDays")
    expire_time = None
    if expire_days not in (None, "", 0, "0"):
        try:
            expire_time = _now() + timedelta(days=int(expire_days))
        except (TypeError, ValueError):
            return error("有效期格式不正确")

    # 生成唯一分享码
    code = _gen_code()
    for _ in range(10):
        exists = await db.scalar(select(func.count()).where(BankShare.share_code == code))
        if not exists:
            break
        code = _gen_code()

    share = BankShare(
        bank_id=bank_id,
        owner_id=user_id,
        share_token=_gen_token(),
        share_code=code,
        permission="read",
        message=body.get("message"),
        expire_time=expire_time,
        status="0",
    )
    db.add(share)
    await db.flush()
    # create_time 是 server_default，flush 后该属性处于「过期」状态，
    # 不 refresh 直接读取会触发同步懒加载 -> MissingGreenlet
    await db.refresh(share)

    return success(format_share(share, bank))


@router.get("/bankShare/bankShare/my")
async def my_shares(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """我发出的分享列表"""
    user_id = current_user.get("user_id")
    result = await db.execute(
        select(BankShare)
        .where(BankShare.owner_id == user_id)
        .order_by(BankShare.create_time.desc())
    )
    shares = list(result.scalars().all())
    if not shares:
        return success([])

    bank_ids = list({s.bank_id for s in shares})
    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
    bank_map = {b.id: b for b in bank_result.scalars().all()}

    rows = [format_share(s, bank_map.get(s.bank_id)) for s in shares]
    return success(rows)


@router.post("/bankShare/bankShare/revoke/{share_id}")
async def revoke_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """撤销分享（仅题库主）—— 撤销后领取方的收藏会标记为「已失效」"""
    user_id = current_user.get("user_id")
    result = await db.execute(select(BankShare).where(BankShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        return error("分享不存在")
    if share.owner_id != user_id:
        return error("无权撤销该分享", code=403)

    share.status = "1"
    share.update_time = _now()

    # 关联的领取记录全部置为失效
    receive_result = await db.execute(
        select(BankShareReceive).where(BankShareReceive.share_id == share_id)
    )
    receives = list(receive_result.scalars().all())
    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    bank = bank_result.scalar_one_or_none()
    bank_name = bank.bank_name if bank else "题库"

    for rec in receives:
        if rec.status != "0":
            continue
        rec.status = "1"
        rec.update_time = _now()
        await create_notification(
            db,
            user_id=rec.receiver_id,
            notify_type="share_invalid",
            title="你收藏的分享题库已失效",
            content=f"题库《{bank_name}》的分享已被撤销，你仍可继续查看，但无法再跟随更新。",
            link=f"/front/myQuestion/bankCollect",
        )

    return success()


# ========== 校验 / 领取 ==========

@router.get("/bankShare/bankShare/infoByCode/{code}")
async def share_info_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按分享码校验（与 info 等价，便于前端统一处理）"""
    return await _share_info(db, current_user, code=code)


@router.get("/bankShare/bankShare/info/{token}")
async def share_info(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """校验分享链接（落地页预展示，不产生领取）"""
    return await _share_info(db, current_user, token=token)


async def _share_info(db: AsyncSession, current_user: dict, token: Optional[str] = None, code: Optional[str] = None):
    share = await _find_share(db, token, code)
    if not share:
        return error("分享不存在或已被删除", code=404)

    if share.status != "0":
        return error("该分享已被撤销", code=410)
    if share.expire_time and share.expire_time < _now():
        return error("该分享已过期", code=410)

    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    bank = bank_result.scalar_one_or_none()
    if not bank:
        return error("原题库已被删除", code=404)

    owner_name = await _get_owner_name(db, share.owner_id)
    user_id = current_user.get("user_id")

    received = False
    if user_id:
        received = bool(await db.scalar(
            select(func.count()).where(
                BankShareReceive.share_id == share.id,
                BankShareReceive.receiver_id == user_id,
            )
        ))

    data = format_share(share, bank, owner_name)
    data["received"] = received
    data["isOwner"] = bool(user_id) and share.owner_id == user_id
    return success(data)


@router.post("/bankShare/bankShare/receive")
async def receive_share(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """领取分享：写入收藏 + 领取记录（幂等），并通知题库主

    body: { token?: string, code?: string }
    """
    body = await _get_body(request)
    token = body.get("token")
    code = body.get("code")
    if not token and not code:
        return error("缺少分享参数")

    share = await _find_share(db, token, code)
    if not share:
        return error("分享不存在或已被删除", code=404)
    if share.status != "0":
        return error("该分享已被撤销", code=410)
    if share.expire_time and share.expire_time < _now():
        return error("该分享已过期", code=410)

    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id == share.bank_id))
    bank = bank_result.scalar_one_or_none()
    if not bank:
        return error("原题库已被删除", code=404)

    user_id = current_user.get("user_id")
    if share.owner_id == user_id:
        return error("这是你自己分享的题库，无需领取")

    # 幂等：已领取过则复用领取记录（不重复计数、不重复通知）
    existed = await db.scalar(
        select(BankShareReceive).where(
            BankShareReceive.share_id == share.id,
            BankShareReceive.receiver_id == user_id,
        )
    )
    first_time = existed is None

    if first_time:
        # 1) 领取记录
        db.add(BankShareReceive(
            share_id=share.id,
            bank_id=share.bank_id,
            owner_id=share.owner_id,
            receiver_id=user_id,
            source="share",
            status="0",
        ))
    elif existed.status != "0":
        # 之前被置为失效（分享撤销后又重新领取），恢复为正常
        existed.status = "0"
        existed.update_time = _now()

    # 2) 写入收藏：不存在则新建；被「取消收藏」过（记录已删）则重新加入
    #    —— 修复：以前只在没有领取记录时才建收藏，导致「取消收藏 → 再领取」永远提示已收藏却没反应
    fav_result = await db.execute(
        select(UserBankFavorite).where(
            UserBankFavorite.user_id == user_id,
            UserBankFavorite.bank_id == share.bank_id,
        )
    )
    favorite = fav_result.scalar_one_or_none()
    fav_existed = favorite is not None
    if favorite:
        favorite.favorite_status = 1
    else:
        db.add(UserBankFavorite(user_id=user_id, bank_id=share.bank_id))

    # 4) 首次领取才计数 + 通知题库主
    if first_time:
        share.receive_count = (share.receive_count or 0) + 1
        receiver_name = await _get_owner_name(db, user_id)
        await create_notification(
            db,
            user_id=share.owner_id,
            notify_type="share_receive",
            title="有人领取了你分享的题库",
            content=f"用户「{receiver_name}」领取了你分享的题库《{bank.bank_name}》。",
            link=f"/front/questionPractice/{share.bank_id}?from=myLearning",
        )

    await db.flush()

    # created: 首次领取；restored: 之前取消过收藏，本次重新加入；exists: 本来就在收藏里
    if first_time:
        result_status = "created"
    elif not fav_existed:
        result_status = "restored"
    else:
        result_status = "exists"

    return success({
        "bankId": share.bank_id,
        "bankName": bank.bank_name,
        "alreadyReceived": not first_time,
        "resultStatus": result_status,
    })


@router.get("/bankShare/bankShare/checkSource/{bank_id}")
async def check_source(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户与该题库的关系，供详情页决定按钮显示

    返回: { isOwner, isShare, shareStatus: 'valid'|'invalid'|null, ownerName, canEdit, canCopy }
    """
    user_id = current_user.get("user_id")
    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
    bank = bank_result.scalar_one_or_none()
    if not bank:
        return error("题库不存在")

    is_owner = bank.user_id == user_id
    owner_name = await _get_owner_name(db, bank.user_id) if not is_owner else None

    is_share = False
    share_status = None
    if not is_owner:
        rec_result = await db.execute(
            select(BankShareReceive)
            .where(
                BankShareReceive.bank_id == bank_id,
                BankShareReceive.receiver_id == user_id,
            )
            .order_by(BankShareReceive.create_time.desc())
        )
        rec = rec_result.scalars().first()
        if rec:
            is_share = True
            share_result = await db.execute(select(BankShare).where(BankShare.id == rec.share_id))
            share = share_result.scalar_one_or_none()
            share_status = "valid" if is_share_effective(share) else "invalid"

    return success({
        "bankId": bank_id,
        "isOwner": is_owner,
        "isShare": is_share,
        "shareStatus": share_status,
        "ownerName": owner_name,
        "canEdit": is_owner,
        # 非题库主 + 题库主开放了复制，才允许复制
        "canCopy": (not is_owner) and int(getattr(bank, "allow_fork", 1) or 0) != 0,
    })
