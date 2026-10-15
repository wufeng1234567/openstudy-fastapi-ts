"""ds-free（DeepSeek 网页端反代）连通性测试

用法：
    cd openstudy-fastapi
    # 方式一：参数传入
    .venv\\Scripts\\python.exe test_ds_free.py --phone 199xxxxxxxx --password xxxxxx

    # 方式二：不传参数，自动读 .env 的 DEEPSEEK_WEB_PHONE / DEEPSEEK_WEB_PASSWORD
    .venv\\Scripts\\python.exe test_ds_free.py

它做了什么：
    1. 用手机号 + 密码调 /api/v0/users/login 换 token
    2. 建一个 chat_session
    3. 取 PoW challenge → 求解 → 带上 X-Ds-Pow-Response 发一句「你好」
    4. 把每一步的 HTTP 状态和原始响应体打出来

看结果：
    · 卡在 login         → 账号密码问题，或被风控直接拒
    · 卡在 pow           → wasm 求解器没就绪（见 app/services/ai/pow_wasm/README.md）
    · 卡在 completion    → PoW 有值但服务端不认（指纹/遥测层），会看到 400/403/429
    · 全绿               → ds-free 可用，可以接进 OpenStudy
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_env_credentials():
    """不装 dotenv 也能读 .env"""
    phone = os.environ.get("DEEPSEEK_WEB_PHONE", "")
    password = os.environ.get("DEEPSEEK_WEB_PASSWORD", "")
    area_code = os.environ.get("DEEPSEEK_WEB_AREA_CODE", "+86")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "DEEPSEEK_WEB_PHONE" and not phone:
                    phone = v
                elif k == "DEEPSEEK_WEB_PASSWORD" and not password:
                    password = v
                elif k == "DEEPSEEK_WEB_AREA_CODE":
                    area_code = v or area_code
                elif k in (
                    "DEEPSEEK_WEB_TOKEN",
                    "DEEPSEEK_WEB_COOKIE",
                    "DEEPSEEK_WEB_HIF_DLIQ",
                    "DEEPSEEK_WEB_HIF_LEIM",
                    "DEEPSEEK_WEB_DEVICE_ID",
                ) and v:
                    # 会话导入模式：把 .env 里的 token / cookie 塞进环境变量，
                    # 客户端会直接复用，不做脚本登录
                    os.environ.setdefault(k, v)
    return phone, password, area_code


async def main():
    parser = argparse.ArgumentParser(description="ds-free 连通性测试")
    parser.add_argument("--phone", default=None, help="手机号（不传则读 .env）")
    parser.add_argument("--password", default=None, help="密码（不传则读 .env）")
    parser.add_argument("--area-code", default=None, help="区号，默认 +86")
    args = parser.parse_args()

    env_phone, env_password, env_area = _load_env_credentials()
    phone = args.phone or env_phone
    password = args.password or env_password
    area_code = args.area_code or env_area

    if not phone or not password:
        print("! 没有拿到手机号/密码。请用 --phone/--password 传入，")
        print("  或在 openstudy-fastapi/.env 里配置 DEEPSEEK_WEB_PHONE / DEEPSEEK_WEB_PASSWORD")
        sys.exit(1)

    print(f"· 手机号: {phone[:3]}****{phone[-4:]}  区号: {area_code}")

    from app.services.ai.deepseek_web_client import DeepSeekWebClient, NodeWasmPowSolver, POW_WASM_DIR

    solver = NodeWasmPowSolver()
    print(f"· PoW 求解器: {solver.describe()}")
    if not solver.available:
        print(f"  ⚠️ 未就绪：需要 node + {POW_WASM_DIR} 下的官方 wasm")
        print("     详见 app/services/ai/pow_wasm/README.md（缺 wasm 会回退到纯 Python 近似实现，基本过不了）")

    client = DeepSeekWebClient(phone=phone, password=password, area_code=area_code)
    print("· 开始测试 ...\n")

    result = await client.self_test()

    # 控制台可能是 GBK，中文会乱码 —— 同时把完整结果写成 UTF-8 的 JSON 文件
    diag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ds_diag.json")
    payload = {
        "result": result,
        "last_diagnostics": client.last_diagnostics,
        "has_token": bool(client._token),
        "has_cookie": bool(client._cookie),
    }
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"· 完整诊断已写入 {diag_path}")

    print("================ 结果 ================")
    print(f"整体: {'可用 ✅' if result.get('ok') else '失败 ❌'}  —  {result.get('detail')}")
    print(f"求解器: {result.get('solver')}")
    print("-------------------------------------")
    for stage in result.get("stages", []):
        mark = "OK  " if stage.get("ok") else "FAIL"
        print(f"[{mark}] {stage.get('stage')}  (HTTP {stage.get('httpStatus')})")
        detail = str(stage.get("detail") or "")
        if detail:
            for line in detail.splitlines():
                print(f"        {line}")
    print("=====================================")
    print("\n完整诊断对象:")
    print(json.dumps(client.last_diagnostics, ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    asyncio.run(main())
