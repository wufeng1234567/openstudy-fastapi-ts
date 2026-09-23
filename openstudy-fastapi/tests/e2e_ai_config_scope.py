# -*- coding: utf-8 -*-
"""
AI 模型配置「可见范围 / 归属」回归测试 —— E2E，进程内真实 HTTP

为什么要有它：
    个人中心 →「我的模型」曾经把**系统提供的 3 个官方模型**也列出来（用户报过），
    根因是三层都缺 user_id 概念：
      ① `GET /system/ai/config/list` 无条件返回全表；
      ② `add_ai_config` 从不写 user_id → 用户自己加的模型变成「系统级」，
         既会泄漏给别人，又因为按 source 过滤反而在自己页面上看不见；
      ③ update / delete / set-default **没有任何归属校验** → 任何登录用户
         都能改删官方配置。
    这套行为一旦回归不会有编译错误、不会有异常，只会「悄悄多出几行」，
    所以固化成本脚本。

覆盖：
    · 非管理员 `scope=mine` 只看到自己的模型（核心 bug）
    · 非管理员不传 scope 自动降级为 available，且系统行 api_key 脱敏
    · 管理员不传 scope 拿到全部
    · 新增模型归属当前用户；mine/available/系统行数三者联动正确
    · 非管理员改 / 删 / 设为默认 / 测试 系统行 一律被拒
    · 非管理员能删自己的行，删完 mine 归零
    · `GET /{id}` 看别人的行时 api_key 脱敏

用法（只要 DB 可用）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_ai_config_scope.py

产出：同目录 e2e_ai_config_scope_result.json；结束时清理本次创建的临时配置。
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_ai_config_scope_result.json")

#: 本次测试创建的临时模型名（结束时按 id 删除，另有兜底 SQL 清理）
TEMP_MODEL = "__e2e_scope__model"

ROWS = []


def T(cid, module, title, pre, steps, expected, ok, actual):
    ROWS.append({
        "cid": cid, "module": module, "title": title, "pre": pre,
        "steps": steps, "expected": expected, "actual": actual,
        "status": "通过" if ok else "失败",
    })
    print(("  [PASS] " if ok else "  [FAIL] ") + cid + " " + title + " -> " + str(actual))


async def main():
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    from app.core.security import get_current_user
    from app.database import async_session_factory
    from app.main import app

    async with async_session_factory() as db:
        uid = int(await db.scalar(text("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1")) or 0)
    if not uid:
        print("找不到任何用户，无法测试")
        return

    # 同一个人，两种身份：普通用户 / 管理员（管理员靠 perms 通配判定）
    PLAIN = {"user_id": uid, "userName": "e2e-plain", "roles": ["common"], "perms": []}
    ADMIN = {"user_id": uid, "userName": "e2e-admin", "roles": ["admin"], "perms": ["*:*:*"]}

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://e2e", timeout=60)
    client.headers.update({"Content-Type": "application/json"})

    def as_user(who):
        app.dependency_overrides[get_current_user] = lambda: dict(who)

    created_ids = []

    async def cleanup():
        """删掉本次创建的临时配置（先走接口，失败再直接 SQL）"""
        for cid in list(created_ids):
            try:
                await client.delete(f"/system/ai/config/{cid}")
            except Exception:  # noqa: BLE001
                pass
        try:
            async with async_session_factory() as db2:
                await db2.execute(
                    text("DELETE FROM sys_ai_config WHERE model = :m"), {"m": TEMP_MODEL}
                )
                await db2.commit()
        except Exception as e:  # noqa: BLE001
            print("兜底清理失败:", e)
        for sid in [TEMP_MODEL]:
            pass

    async def list_cfg(scope=None, as_admin=False):
        body = {"params": {}}
        if scope:
            body["params"]["scope"] = scope
        as_user(ADMIN if as_admin else PLAIN)
        r = await client.get("/system/ai/config/list", **body)
        return r.json()

    try:
        # ---------- 只读：可见范围 ----------
        j = await list_cfg("mine")
        rows = j.get("rows") or []
        T("S1", "可见范围", "非管理员 scope=mine 只返回自己的模型",
          "库里没有归属该用户的配置", "GET list?scope=mine",
          "rows == []", rows == [], f"count={len(rows)} models={[r.get('model') for r in rows]}")

        j = await list_cfg(None)
        rows = j.get("rows") or []
        sources = sorted({r.get("source") for r in rows})
        keys_masked = all(not r.get("apiKey") for r in rows)
        T("S2", "可见范围", "非管理员不传 scope → 自动降级 available，且系统行 api_key 脱敏",
          "库里有 3 条 user_id 为空的官方配置", "GET list（不带 scope）",
          "全部 source=system 且 apiKey 均为空",
          sources == ["system"] and keys_masked,
          f"count={len(rows)} sources={sources} apiKey全空={keys_masked}")

        j = await list_cfg(None, as_admin=True)
        rows = j.get("rows") or []
        has_any_key_visible = any(r.get("apiKey") for r in rows) or not any(
            r.get("source") == "system" and r.get("provider") != "deepseek-free" for r in rows
        )
        T("S3", "可见范围", "管理员不传 scope 拿到全部，且 api_key 未脱敏",
          "管理员身份", "GET list（不带 scope）",
          "source 全为 system，apiKey 字段不被清空",
          sources == ["system"] and has_any_key_visible,
          f"count={len(rows)} apiKey可见={has_any_key_visible}")

        system_count = len(rows)

        # ---------- 写：归属 ----------
        as_user(PLAIN)
        r = await client.post("/system/ai/config", json={
            "provider": "openai", "providerName": "OpenAI", "model": TEMP_MODEL,
            "apiKey": "sk-e2e-scope-test", "baseUrl": "https://api.openai.com",
            "isDefault": 0, "isEnabled": 1,
        })
        body = r.json()
        cfg = (body.get("data") or {})
        if cfg.get("configId"):
            created_ids.append(cfg["configId"])
        T("S4", "归属", "普通用户新增模型 → user_id = 自己、source = user",
          "以普通用户身份 POST", "POST /system/ai/config",
          "success 且 data.userId == 当前用户、source == 'user'",
          body.get("code") == 200 and cfg.get("userId") == uid and cfg.get("source") == "user",
          f"code={body.get('code')} userId={cfg.get('userId')} source={cfg.get('source')}")

        j = await list_cfg("mine")
        mine_rows = j.get("rows") or []
        j2 = await list_cfg(None)
        avail_rows = j2.get("rows") or []
        j3 = await list_cfg(None, as_admin=True)
        all_rows = j3.get("rows") or []
        T("S5", "归属", "新增后 mine/available/系统行数三者联动正确",
          f"系统行 {system_count} 条 + 自己的 1 条",
          "GET list?scope=mine / list / list(admin)",
          "mine=1，available=系统+1，admin 总数=系统+1",
          len(mine_rows) == 1 and len(avail_rows) == system_count + 1
          and len(all_rows) == system_count + 1,
          f"mine={len(mine_rows)} available={len(avail_rows)} all={len(all_rows)}")

        # ---------- 越权：改 / 删 / 设默认 / 测试 系统行 ----------
        j = await list_cfg(None, as_admin=True)
        sys_row = next((r for r in (j.get("rows") or []) if r.get("source") == "system"), None)
        if sys_row:
            sid = sys_row["configId"]

            as_user(PLAIN)
            r = await client.put("/system/ai/config", json={"configId": sid, "remark": "被篡改"})
            b = r.json()
            T("S6", "越权", "普通用户修改系统行被拒",
              f"系统配置 id={sid}", "PUT /system/ai/config",
              "code!=200 且提示无权",
              b.get("code") != 200 and "无权" in str(b.get("msg")),
              f"code={b.get('code')} msg={b.get('msg')}")

            r = await client.put(f"/system/ai/config/default/{sid}")
            b = r.json()
            T("S7", "越权", "普通用户把系统行设为默认被拒",
              f"系统配置 id={sid}", "PUT /system/ai/config/default/{id}",
              "code!=200 且提示无权",
              b.get("code") != 200 and "无权" in str(b.get("msg")),
              f"code={b.get('code')} msg={b.get('msg')}")

            r = await client.post("/system/ai/config/test", json={"configId": sid})
            b = r.json()
            T("S8", "越权", "普通用户测试系统行连接被拒",
              f"系统配置 id={sid}", "POST /system/ai/config/test",
              "code!=200 且提示无权",
              b.get("code") != 200 and "无权" in str(b.get("msg")),
              f"code={b.get('code')} msg={b.get('msg')}")

            r = await client.get(f"/system/ai/config/{sid}")
            b = r.json()
            data = b.get("data") or {}
            T("S9", "脱敏", "普通用户看系统行详情 api_key 被脱敏",
              f"系统配置 id={sid}", "GET /system/ai/config/{id}",
              "apiKey 为空字符串",
              b.get("code") == 200 and data.get("apiKey") == "",
              f"apiKey={data.get('apiKey')!r}")

            r = await client.delete(f"/system/ai/config/{sid}")
            b = r.json()
            T("S10", "越权", "普通用户删除系统行被拒",
              f"系统配置 id={sid}", "DELETE /system/ai/config/{id}",
              "code!=200 且提示无权",
              b.get("code") != 200 and "无权" in str(b.get("msg")),
              f"code={b.get('code')} msg={b.get('msg')}")
        else:
            for cid, title in [
                ("S6", "普通用户修改系统行被拒"), ("S7", "普通用户把系统行设为默认被拒"),
                ("S8", "普通用户测试系统行连接被拒"), ("S9", "普通用户看系统行详情 api_key 被脱敏"),
                ("S10", "普通用户删除系统行被拒"),
            ]:
                T(cid, "越权", title, "库里无系统行", "-", "-", False, "跳过：没有系统行可测")

        # ---------- 自己的行可删 ----------
        if created_ids:
            my_id = created_ids[0]
            as_user(PLAIN)
            r = await client.delete(f"/system/ai/config/{my_id}")
            b = r.json()
            deleted = b.get("code") == 200
            if deleted:
                created_ids.remove(my_id)
            j = await list_cfg("mine")
            rows = j.get("rows") or []
            T("S11", "归属", "普通用户可以删自己的行，删完 mine 归零",
              f"自己的配置 id={my_id}", "DELETE 自己 + GET list?scope=mine",
              "code=200 且 mine 回到空",
              deleted and rows == [], f"code={b.get('code')} mine={len(rows)}")
        else:
            T("S11", "归属", "普通用户可以删自己的行", "-", "-", "-", False, "跳过：没有创建成功")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        T("XX", "执行", "脚本异常", "-", "-", "-", False, repr(e))
    finally:
        try:
            await cleanup()
        except Exception as e:  # noqa: BLE001
            print("cleanup 异常:", e)
        app.dependency_overrides.pop(get_current_user, None)
        await client.aclose()

    passed = len([r for r in ROWS if r["status"] == "通过"])
    print(f"\n{passed}/{len(ROWS)} 通过")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"total": len(ROWS), "passed": passed, "rows": ROWS},
                  f, ensure_ascii=False, indent=2)
    print("产出:", OUT)


asyncio.run(main())
