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

    # ---- model_kind=relay：即便 provider=deepseek、base_url 指向自建网关，也不带 thinking 形状 ----
    c3 = Cfg()
    c3.provider = "deepseek"                 # 伪装成官方
    c3.provider_name = "DeepSeek"
    c3.model = "deepseek-chat"
    c3.base_url = "http://127.0.0.1:3425/v1"  # 指向本地 magpie
    c3.api_key = "magpie"
    c3.thinking_mode = "enabled"
    c3.reasoning_effort = "high"
    c3.model_kind = "relay"                  # Tab 显式标记为中转站
    captured.clear()
    try:
        class _Fake3:
            def __init__(self, **kw):
                captured.update(kw)
        dc.ChatOpenAI = _Fake3
        dc._build_llm(c3, thinking=True)
    finally:
        dc.ChatOpenAI = orig
    eb3 = captured.get("extra_body") or {}
    ok4 = "thinking" not in eb3 and eb3.get("reasoning_effort") == "high"
    print("relay extra_body =", eb3, "-> 只带 effort、不带 thinking:", ok4)

    # ---- model_kind=official：base_url 缺省也认官方，带 thinking 形状 ----
    c4 = Cfg()
    c4.provider = "deepseek"
    c4.provider_name = "DeepSeek 官方"
    c4.model = "deepseek-v4-pro"
    c4.base_url = ""                          # 官方 Tab 预置，可能留空走默认
    c4.api_key = "sk-x"
    c4.thinking_mode = "enabled"
    c4.reasoning_effort = "high"
    c4.model_kind = "official"
    captured.clear()
    try:
        class _Fake4:
            def __init__(self, **kw):
                captured.update(kw)
        dc.ChatOpenAI = _Fake4
        dc._build_llm(c4, thinking=True)
    finally:
        dc.ChatOpenAI = orig
    eb4 = captured.get("extra_body") or {}
    ok5 = eb4.get("thinking") == {"type": "enabled"}
    print("official(空base_url) extra_body =", eb4, "-> 带 thinking:", ok5)

    # ---- 老数据（无 model_kind 属性）：回退 base_url 判据，行为与 8e09bdf 一致 ----
    c5 = Cfg()
    c5.provider = "deepseek"
    c5.provider_name = "DeepSeek"
    c5.model = "deepseek-v4-pro"
    c5.base_url = "https://api.deepseek.com"
    c5.api_key = "sk-x"
    c5.thinking_mode = "enabled"
    c5.reasoning_effort = "high"
    # 不设 model_kind（模拟老配置行，OR 对象无此属性）
    captured.clear()
    try:
        class _Fake5:
            def __init__(self, **kw):
                captured.update(kw)
        dc.ChatOpenAI = _Fake5
        dc._build_llm(c5, thinking=True)
    finally:
        dc.ChatOpenAI = orig
    eb5 = captured.get("extra_body") or {}
    ok6 = eb5.get("thinking") == {"type": "enabled"}
    print("老数据(无model_kind,官方域) extra_body =", eb5, "-> 回退带 thinking:", ok6)

    sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5 and ok6) else 1)


if __name__ == "__main__":
    main()
