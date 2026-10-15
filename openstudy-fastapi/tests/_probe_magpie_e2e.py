# -*- coding: utf-8 -*-
"""端到端：走 OpenStudy 的 build_agent_llm 调 magpie，验证能拿到 reasoning_content"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


async def main():
    from app.database import async_session_factory
    from app.services.ai import db_config
    from langchain_core.messages import HumanMessage

    async with async_session_factory() as db:
        # 用户 105 的 openai/magpie 配置
        llm, cfg = await db_config.build_agent_llm(
            db, provider="openai", model="group/auto-deepseek-v4-1-flash", user_id=105
        )
        print("config: provider=%r model=%r base=%r effort=%r mode=%r"
              % (cfg.provider, cfg.model, cfg.base_url, cfg.reasoning_effort, cfg.thinking_mode))
        # 打印本客户端绑定的 extra_body
        print("llm.extra_body =", getattr(llm, "extra_body", None))

        n_reason = 0
        n_text = 0
        sample = []
        async for chunk in llm.astream([HumanMessage(content="9.11 与 9.8 哪个大？简答。")]):
            kw = getattr(chunk, "additional_kwargs", {}) or {}
            r = kw.get("reasoning_content") or kw.get("reasoning")
            if r:
                n_reason += 1
                if len(sample) < 1:
                    sample.append(r)
            if getattr(chunk, "content", None):
                n_text += 1
        print(f"reasoning 分片={n_reason} | content 分片={n_text}")
        if sample:
            print("reasoning 样例:", repr(sample[0][:100]))
        print("结论:", "✅ 后端能拿到 reasoning（修复生效）" if n_reason else "❌ 仍拿不到 reasoning")
    return 0 if n_reason else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
