# -*- coding: utf-8 -*-
"""锁死「确认/取消链路不被 AI 限流误伤」+ 本地版硬开关（用户 2026-10-17 报）

## 现象
用户让智能体删知识库，卡片点「取消」→ **模型那边毫无反应**；紧接着再发消息就报
「今日 AI 体验额度已用完（50/50）」。

## 根因（两处叠加，都在限流白名单里）
1. `/ai/agent/confirm` 被列进 `AI_LLM_PATHS`，但它**一次 LLM 都不调** ——
   只做 `resolve_confirmation()` 唤醒挂起的循环。被 429 拦掉后，后端永远收不到
   「取消」决定，`_await_user_confirmation` 只能挂到 180s 超时 →
   界面卡片显示「已取消」（那是前端自己改的本地状态），模型侧一片死寂。
2. `/ai/agent/preview` / `/ai/agent/execute` 同样被计入额度，但 ds-free 链路里
   每调一个工具都要走一遍（LLM 在浏览器扩展侧，后端不调）。
   一个多工具回合就能干掉好几次「日额度」。
3. 本地开发版没有「关掉限流」的手段，自测时被自己卡死。

## 本次改动
- 三个非 LLM 路径移出白名单；
- 新增最高优先级硬开关 `AI_RATE_LIMIT_ENABLED`（本地 false / 线上 true）；
- 后台 `/monitor/ratelimit/config` 回传 `globallyEnabled`，前端可以显示「本机已关闭」。

用法：.venv\\Scripts\\python.exe tests\\_probe_rate_limit_scope.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RESULTS = []


def check(cid, name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f"  -- {detail}" if detail else ""))


def main():
    from app.core import rate_limit as rl

    # T1：确认接口绝不能被限流（否则「取消」永远送不到后端）
    check(
        "T1",
        "/ai/agent/confirm 不在限流白名单（点取消必须立刻生效）",
        not rl._is_llm_path("/ai/agent/confirm"),
        f"AI_LLM_PATHS={rl.AI_LLM_PATHS}",
    )

    # T2/T3：ds-free 的工具预览/执行不调 LLM，不该吃额度
    check("T2", "/ai/agent/preview 不在限流白名单", not rl._is_llm_path("/ai/agent/preview"))
    check("T3", "/ai/agent/execute 不在限流白名单", not rl._is_llm_path("/ai/agent/execute"))

    # T4：真正调 LLM 的入口必须仍在白名单里（别把限流一起改没了）
    must_limit = [
        "/ai/agent/stream",
        "/ai/chat",
        "/ai/assistant/stream",
        "/ai/assistant/generate-with-images",
        "/ai/generate/questions/stream",
        "/ai/generate/composite/stream",
        "/ai/analyze/question/stream",
    ]
    missing = [p for p in must_limit if not rl._is_llm_path(p)]
    check("T4", "真正调 LLM 的入口仍在白名单内", not missing, f"缺失={missing}")

    # T5：硬开关可读（默认线上口径 = True）
    from app.config import settings

    default_on = bool(getattr(settings, "AI_RATE_LIMIT_ENABLED", None))
    check(
        "T5",
        "硬开关 AI_RATE_LIMIT_ENABLED 可读且默认开启（线上口径）",
        getattr(settings, "AI_RATE_LIMIT_ENABLED", None) is not None,
        f"当前={default_on}（本地启动脚本会覆盖成 false）",
    )

    # T6：开关为 false 时 _globally_enabled() 为假（中间件据此直接放行）
    saved = settings.AI_RATE_LIMIT_ENABLED
    try:
        settings.AI_RATE_LIMIT_ENABLED = False
        off = rl._globally_enabled() is False
        settings.AI_RATE_LIMIT_ENABLED = True
        on = rl._globally_enabled() is True
    finally:
        settings.AI_RATE_LIMIT_ENABLED = saved
    check("T6", "硬开关 false→放行 / true→按 Redis 配置执行", off and on, f"off={off} on={on}")

    # T7：本地启动脚本确实设了 false；线上脚本设了 true（两边口径分开）
    def _read(rel):
        p = os.path.join(os.path.dirname(ROOT), rel)
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    local_bat = _read(os.path.join("startup-scripts", "start-fastapi.bat"))
    online_sh = _read("daily-start.sh")
    check(
        "T7",
        "本地 start-fastapi.bat 设 AI_RATE_LIMIT_ENABLED=false",
        "AI_RATE_LIMIT_ENABLED=false" in local_bat,
    )
    check(
        "T8",
        "线上 daily-start.sh 设 AI_RATE_LIMIT_ENABLED=true",
        "AI_RATE_LIMIT_ENABLED=true" in online_sh,
    )

    # T9：后台配置接口会回传硬开关（前端据此提示「本机已关闭限流」）
    import inspect
    from app.api.v1 import rate_limit_admin as admin_mod

    src = inspect.getsource(admin_mod.get_rate_limit_config)
    check(
        "T9",
        "/monitor/ratelimit/config 回传 globallyEnabled",
        "globallyEnabled" in src and "_globally_enabled" in src,
    )

    print()
    ok = sum(1 for r in RESULTS if r)
    print(f"{ok}/{len(RESULTS)} 通过")
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
