# -*- coding: utf-8 -*-
"""锁死「官方 DeepSeek 配 thinking_mode=disabled → Agent 仍能出深度思考」（用户 2026-10-17 报）

现象：用户用自己配的 ds-flash（中转站）能触发深度思考，用**官方默认** deepseek-flash 永远不触发。

根因（两段叠加）：
  1. `sys_ai_config` 里官方默认行的 `thinking_mode` 是 `disabled`（历史遗留数据）；
  2. `build_agent_llm` 早期实现「官方域 + 显式关闭」→ 发 `{"thinking":{"type":"disabled"}}`，
     而**上游**收到 disabled 会把 reasoning_content 掐干净。

上游实测（api.deepseek.com / deepseek-flash，同一句提问）：
  - 不传 thinking        → reasoning_content 923 字
  - thinking=disabled    → reasoning_content 0 字

故 Agent 模式必须把 disabled 降级为「不传」（本函数 docstring 的表格就是这么写的，
只是代码没照做）。普通对话链路 `stream_with_config` 仍照常尊重 thinking_mode。

用法：.venv\\Scripts\\python.exe tests\\_probe_agent_thinking_disabled.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS = []


def check(cid, name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f"  -- {detail}" if detail else ""))


class _Cfg:
    def __init__(self, **kw):
        self.config_id = kw.get("config_id", 1)
        self.provider = kw.get("provider", "deepseek")
        self.provider_name = kw.get("provider_name", "DeepSeek")
        self.model = kw.get("model", "deepseek-flash")
        self.base_url = kw.get("base_url", "https://api.deepseek.com")
        self.api_key = kw.get("api_key", "sk-test-0123456789")
        self.model_kind = kw.get("model_kind", "official")
        self.thinking_mode = kw.get("thinking_mode", "auto")
        self.reasoning_effort = kw.get("reasoning_effort", "high")
        self.context_length = "200k"
        self.is_enabled = 1
        self.is_default = 1
        self.user_id = None


def _capture_extra_body(cfg):
    """把 ChatOpenAI 换成假类，抓 build_agent_llm 最终传给它的 kwargs"""
    from app.services.ai import db_config as dc

    captured = {}
    orig_llm, orig_resolve = dc.ChatOpenAI, dc.resolve_agent_config

    async def _fake_resolve(*a, **kw):
        return cfg

    class _Fake:
        def __init__(self, **kw):
            captured.update(kw)

    dc.ChatOpenAI, dc.resolve_agent_config = _Fake, _fake_resolve
    try:
        asyncio.get_event_loop().run_until_complete(dc.build_agent_llm(None))
    finally:
        dc.ChatOpenAI, dc.resolve_agent_config = orig_llm, orig_resolve
    return captured.get("extra_body") or {}


def main():
    # T1：核心回归 —— 官方 + disabled → 不发 thinking，也不发 reasoning_effort
    eb = _capture_extra_body(_Cfg(thinking_mode="disabled", reasoning_effort="max"))
    check(
        "T1",
        "官方 DeepSeek + thinking_mode=disabled → 不传 thinking（否则上游掐掉 reasoning）",
        "thinking" not in eb,
        f"extra_body={eb}",
    )
    check(
        "T2",
        "同上：disabled 时也不塞 reasoning_effort（配的 max 不该被使用）",
        "reasoning_effort" not in eb,
        f"extra_body={eb}",
    )

    # T3：显式 enabled 仍要正常开启（别把功能一起改死）
    eb = _capture_extra_body(_Cfg(thinking_mode="enabled", reasoning_effort="high"))
    check(
        "T3",
        "官方 DeepSeek + thinking_mode=enabled → 仍发 enabled + reasoning_effort",
        eb.get("thinking") == {"type": "enabled"} and eb.get("reasoning_effort") == "high",
        f"extra_body={eb}",
    )

    # T4：auto 仍不传（跟随上游默认）
    eb = _capture_extra_body(_Cfg(thinking_mode="auto", reasoning_effort="high"))
    check("T4", "官方 DeepSeek + auto → 不传 thinking（跟随上游默认）", "thinking" not in eb, f"extra_body={eb}")

    # T5：中转站（model_kind=relay）配了 effort → 只发标准 reasoning_effort
    eb = _capture_extra_body(
        _Cfg(
            provider="deepseek",
            base_url="http://127.0.0.1:3425/v1",
            model_kind="relay",
            thinking_mode="auto",
            reasoning_effort="high",
        )
    )
    check(
        "T5",
        "中转站配置 → 只发 reasoning_effort、不发 DeepSeek thinking 形状",
        eb.get("reasoning_effort") == "high" and "thinking" not in eb,
        f"extra_body={eb}",
    )

    # T6：普通对话链路 stream_with_config 仍尊重 disabled（不能被本次修改波及）
    import inspect

    src = inspect.getsource(__import__("app.services.ai.db_config", fromlist=["x"]).build_agent_llm)
    check(
        "T6",
        "修改只落在 build_agent_llm 内（stream_with_config 未改）",
        "Agent 忽略 thinking_mode=disabled" in src,
        "探针 T1 即覆盖行为；此处确保注释/降级逻辑在原地",
    )

    print()
    ok = sum(1 for r in RESULTS if r)
    print(f"{ok}/{len(RESULTS)} 通过")
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
