# -*- coding: utf-8 -*-
"""探针：后端经 ds-free-nb（本机 ds 桥）完成一次最小聊天。

前置：本机 ds 桥服务在 http://127.0.0.1:9200/v1 运行；sys_ai_config 有 ds-free-nb 系统行。
用法：.venv/Scripts/python.exe tests/_probe_ds_free_nb.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


async def main():
    from app.database import async_session_factory
    from app.services.ai import db_config
    from app.services.ai.base_client import ChatMessage

    async with async_session_factory() as db:
        cfg = await db_config.resolve_config(db, provider=None, model="ds-free-nb", user_id=None)
        if cfg is None:
            print("FAIL: 未找到 ds-free-nb 配置（先跑 seed_ai_config_ds_free_nb.py）")
            return 1
        print(f"config: id={cfg.config_id} provider={cfg.provider} model={cfg.model} "
              f"base={cfg.base_url} kind={cfg.model_kind} key={bool(cfg.api_key)}")

        msgs = [ChatMessage(role="user", content="用一句话介绍你自己")]
        text = ""
        try:
            async for chunk in db_config.stream_with_config(
                db, msgs, provider=None, model="ds-free-nb", user_id=None
            ):
                text += chunk
        except Exception as e:
            print(f"FAIL: 调用异常 {type(e).__name__}: {e}")
            return 1

        print(f"回复长度={len(text)}")
        print("回复:", text[:200])
        ok = len(text) > 0
        print("结论:", "通过" if ok else "失败（空回复）")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
