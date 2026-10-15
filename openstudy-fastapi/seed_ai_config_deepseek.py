"""初始化「系统提供」的模型配置到 sys_ai_config 表（幂等）

执行：
    cd openstudy-fastapi
    .venv\\Scripts\\python.exe seed_ai_config_deepseek.py

会写入两级配置里的「系统提供」这一级：

  1) provider = deepseek —— DeepSeek 官方 API（按量计费）
       model = deepseek-flash / deepseek-v4-pro
       （2026-09 起 DS 官方模型更名为 deepseek-flash；
        旧名 deepseek-v4-flash 仍可调用但由 V4.1-Flash 提供服务）
       base_url = https://api.deepseek.com（OpenAI 兼容）
       需要 .env 里的 DEEPSEEK_API_KEY 或表里的 api_key

  2) provider = deepseek-free —— DS 官网免费版反代（**已下线**）
       统一走官方 API，该行只会被写成「停用」状态，不在下拉框出现。

幂等：按 (provider, model) 查找，存在则更新，不存在则插入；不碰用户自定义的配置，
也不删任何行。默认标记按 provider 维度唯一。
"""

import asyncio
import sys

from sqlalchemy import select, update

from app.database import async_session_factory, init_db
from app.config import settings
from app.models.ai_config import SysAiConfig

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

#: 官方模型默认的上下文预算档（见 app/services/ai/context_budget.py）。
#: 官方两个模型窗口都是 1M，默认用「基础档 200K」，长文档场景可在前台切到 1M。
DEFAULT_CONTEXT_LENGTH = "200k"


async def _upsert(db, *, provider, model, provider_name, remark, **fields):
    """按 (provider, model) 幂等写入"""
    result = await db.execute(
        select(SysAiConfig).where(
            SysAiConfig.provider == provider, SysAiConfig.model == model
        )
    )
    cfg = result.scalars().first()
    if cfg:
        for k, v in fields.items():
            if v is not None:
                setattr(cfg, k, v)
        cfg.provider_name = provider_name
        cfg.remark = remark
        return cfg, False

    cfg = SysAiConfig(
        provider=provider,
        provider_name=provider_name,
        model=model,
        status="0",
        remark=remark,
        thinking_mode="auto",
        **fields,
    )
    db.add(cfg)
    return cfg, True


async def _ensure_single_default(db, provider: str, model: str) -> None:
    """把该 provider 下指定 model 设为唯一默认"""
    await db.execute(
        update(SysAiConfig)
        .where(SysAiConfig.provider == provider, SysAiConfig.is_default == 1)
        .values(is_default=0)
    )
    result = await db.execute(
        select(SysAiConfig).where(
            SysAiConfig.provider == provider, SysAiConfig.model == model
        )
    )
    cfg = result.scalars().first()
    if cfg:
        cfg.is_default = 1


async def seed() -> None:
    await init_db()

    api_key = (settings.DEEPSEEK_API_KEY or "").strip()

    if not api_key:
        print("! 未配置 DEEPSEEK_API_KEY，DeepSeek 官方配置将不带 Key（可稍后在后台补）")
        print("  申请：https://platform.deepseek.com -> API Keys")

    async with async_session_factory() as db:
        # ---------- 1. DeepSeek 官方 API ----------
        await _upsert(
            db,
            provider="deepseek",
            model="deepseek-flash",
            provider_name="DeepSeek",
            remark="官方 API · 日常对话/出题主力模型",
            api_key=api_key or None,
            base_url=DEEPSEEK_BASE_URL,
            thinking_mode="auto",
            reasoning_effort="high",
            context_length=DEFAULT_CONTEXT_LENGTH,
            is_enabled=1,
            is_default=0,
        )
        await _upsert(
            db,
            provider="deepseek",
            model="deepseek-v4-pro",
            provider_name="DeepSeek",
            remark="官方 API · 强推理，按需切换",
            api_key=api_key or None,
            base_url=DEEPSEEK_BASE_URL,
            thinking_mode="auto",
            reasoning_effort="high",
            context_length=DEFAULT_CONTEXT_LENGTH,
            is_enabled=1,
            is_default=0,
        )
        await _ensure_single_default(db, "deepseek", "deepseek-flash")
        print("+ DeepSeek 官方：deepseek-flash（默认）+ deepseek-v4-pro")

        # ---------- 2. DS 免费（官网 Web 反代，已下线） ----------
        # 统一走官方 API：该行只保留为「停用」状态，不提供任何凭据写入
        await _upsert(
            db,
            provider="deepseek-free",
            model="deepseek-free",
            provider_name="DeepSeek Free",
            remark="已停用：官网 Web 反代方案下线，统一走官方 API",
            base_url="https://chat.deepseek.com",
            is_enabled=0,
        )
        await _ensure_single_default(db, "deepseek-free", "deepseek-free")
        print("+ deepseek-free：已停用（方案下线，统一走官方 API）")

        await db.commit()

        # ---------- 打印全表 ----------
        result = await db.execute(select(SysAiConfig).order_by(SysAiConfig.config_id.asc()))
        print("\n当前 sys_ai_config 全表：")
        print(f"  {'id':<5}{'来源':<8}{'provider':<16}{'model':<22}{'默认':<6}{'启用':<6}凭证")
        for cfg in result.scalars().all():
            src = "用户" if cfg.user_id else "系统"
            cred = ""
            if cfg.provider == "deepseek-free":
                cred = f"手机号={cfg.web_phone or '未填'} 密码={'已设' if cfg.web_password else '未设'}"
            elif cfg.api_key:
                cred = "API Key=已设"
            print(
                f"  {cfg.config_id:<5}{src:<8}{cfg.provider or '':<16}{cfg.model or '':<22}"
                f"{'是' if cfg.is_default == 1 else '-':<6}"
                f"{'是' if cfg.is_enabled == 1 else '否':<6}{cred}"
            )


if __name__ == "__main__":
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)

    from app.database import engine

    async def _main():
        try:
            await seed()
        finally:
            # 释放连接池，否则解释器退出时 aiomysql 会在已关闭的 event loop 上
            # 触发 "RuntimeError: Event loop is closed" 的噪音（无害但吓人）
            await engine.dispose()

    asyncio.run(_main())
