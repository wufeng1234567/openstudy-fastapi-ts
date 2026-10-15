"""初始化「DS 免费·无浏览器」系统模型（ds-free-nb）到 sys_ai_config。

前置：本机 ds 桥服务已启动（startup-scripts/ds-bridge，默认 http://127.0.0.1:9200/v1）。

执行：
    cd openstudy-fastapi
    .venv\\Scripts\\python.exe seed_ai_config_ds_free_nb.py

写一条**系统提供**行（user_id 为空，所有用户可见）：
    provider   = ds-free-nb      （不以 deepseek 开头 → 不会被判为官方域、不发 thinking 脏参数）
    model      = ds-free-nb
    base_url   = http://127.0.0.1:9200/v1   （本机 ds 桥的 OpenAI 兼容端点）
    model_kind = relay           （显式声明「中转站/非官方」，语义最稳）
    api_key    = bridge          （桥忽略该值；但后端 _build_llm 要求 key 非空）
幂等：(provider, model) 命中则更新，不做重复插入。
"""

import asyncio

from sqlalchemy import select

from app.database import async_session_factory, init_db
from app.models.ai_config import SysAiConfig

BRIDGE_BASE_URL = "http://127.0.0.1:9200/v1"
PROVIDER = "ds-free-nb"
MODEL = "ds-free-nb"


async def seed() -> None:
    await init_db()
    async with async_session_factory() as db:
        result = await db.execute(
            select(SysAiConfig).where(
                SysAiConfig.provider == PROVIDER, SysAiConfig.model == MODEL
            )
        )
        cfg = result.scalars().first()
        if cfg:
            cfg.provider_name = "DS 免费（无浏览器）"
            cfg.base_url = BRIDGE_BASE_URL
            cfg.model_kind = "relay"
            cfg.api_key = cfg.api_key or "bridge"
            cfg.is_enabled = 1
            cfg.status = "0"
            cfg.remark = "本机 ds 桥（无头 Edge，无需浏览器插件）"
            print(f"+ 已更新 ds-free-nb（config_id={cfg.config_id}）")
        else:
            cfg = SysAiConfig(
                user_id=None,
                provider=PROVIDER,
                provider_name="DS 免费（无浏览器）",
                model=MODEL,
                api_key="bridge",
                base_url=BRIDGE_BASE_URL,
                model_kind="relay",
                is_default=0,
                is_enabled=1,
                status="0",
                thinking_mode="auto",
                remark="本机 ds 桥（无头 Edge，无需浏览器插件）",
            )
            db.add(cfg)
            print("+ 已新增系统模型 ds-free-nb")
        await db.commit()
        print("完成。请在后台「AI 模型配置」或聊天模型下拉框查看「DS 免费（无浏览器）」。")


if __name__ == "__main__":
    asyncio.run(seed())
