# -*- coding: utf-8 -*-
"""验证 build_agent_llm / _build_llm 对非 deepseek 网关透传 reasoning_effort（用户 2026-10-12）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    from app.services.ai import db_config as dc

    # 构造一条 config（模拟用户库里 provider=openai + magpie 网关）
    Cfg = type("Cfg", (), {})
    c = Cfg()
    c.provider = "openai"
    c.provider_name = "OpenAI"
    c.model = "group/auto-deepseek-v4-1-flash"
    c.base_url = "http://127.0.0.1:3425/v1"
    c.api_key = "magpie"
    c.thinking_mode = "auto"
    c.reasoning_effort = "high"

    captured = {}

    # 拦 ChatOpenAI 构造，抓 extra_body
    orig = dc.ChatOpenAI
    try:
        class _Fake:
            def __init__(self, **kw):
                captured.update(kw)
        dc.ChatOpenAI = _Fake
        llm = dc._build_llm(c, thinking=True)
    finally:
        dc.ChatOpenAI = orig

    eb = captured.get("extra_body")
    print("extra_body =", eb)
    ok1 = isinstance(eb, dict) and eb.get("reasoning_effort") == "high"
    ok2 = "thinking" not in (eb or {})  # 非 deepseek 不应带 thinking 形状
    print("  带 reasoning_effort=high:", ok1)
    print("  不带 DeepSeek thinking 形状:", ok2)

    # deepseek 系：仍应带 thinking
    c2 = Cfg()
    c2.provider = "deepseek"
    c2.provider_name = "DeepSeek"
    c2.model = "deepseek-v4-pro"
    c2.base_url = "https://api.deepseek.com"
    c2.api_key = "sk-x"
    c2.thinking_mode = "enabled"
    c2.reasoning_effort = "high"
    captured.clear()
    try:
        class _Fake2:
            def __init__(self, **kw):
                captured.update(kw)
        dc.ChatOpenAI = _Fake2
        dc._build_llm(c2, thinking=True)
    finally:
        dc.ChatOpenAI = orig
    eb2 = captured.get("extra_body") or {}
    ok3 = eb2.get("thinking") == {"type": "enabled"} and eb2.get("reasoning_effort") == "high"
    print("deepseek 系 extra_body =", eb2, "-> 带 thinking+effort:", ok3)

    sys.exit(0 if (ok1 and ok2 and ok3) else 1)


if __name__ == "__main__":
    main()
