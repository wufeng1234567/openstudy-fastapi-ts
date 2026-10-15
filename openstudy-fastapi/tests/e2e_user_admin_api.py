# -*- coding: utf-8 -*-
"""后台管理「用户管理」模块 E2E 接口测试（真实 HTTP 调用）

被测页面：openstudy-vue3-ts/src/views/system/user/index.vue
          openstudy-vue3-ts/src/views/system/user/authRole.vue
被测接口：app/api/v1/users.py + app/api/v1/system.py 的角色列表

覆盖：用户列表/筛选、新增、详情、修改、删除、重置密码、状态切换、角色分配。
数据纪律：测试用户统一以「后台对接测试用户_」开头，启动自检 + 结束 finally 物理删除，
        不留 sys_user / sys_user_role 残留。

用法（后端需先跑起来，默认 127.0.0.1:9101）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_user_admin_api.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_user_admin_api_result.json")
PREFIX = "后台对接测试用户_"

ROWS = []
CREATED_USER_IDS = []


def call(method, path, token=None, body=None, params=None, timeout=25):
    url = BASE + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                try:
                    return r.status, json.loads(raw.decode("utf-8"))
                except Exception:
                    return r.status, raw
            return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, raw


def login(account):
    st, res = call("POST", "/quickLogin", body={"account": account})
    assert st == 200 and res.get("code") == 200, "quickLogin(%s) 失败: %s" % (account, res)
    return res["data"]["token"]


def T(cid, module, title, pre, steps, expected, ok, actual):
    ROWS.append({
        "cid": cid, "module": module, "title": title, "pre": pre,
        "steps": steps, "expected": expected, "actual": actual,
        "status": "通过" if ok else "失败",
    })
    print(("  [PASS] " if ok else "  [FAIL] ") + cid + " " + title + " -> " + str(actual))


def ok(res, extra=""):
    return isinstance(res, dict) and res.get("code") == 200 or extra


def code_of(res):
    return res.get("code") if isinstance(res, dict) else "-"


def raw_data(res):
    return res.get("data") if isinstance(res, dict) else None


def dd(res):
    d = raw_data(res)
    return d if isinstance(d, dict) else {}


def dl(res):
    d = raw_data(res)
    return d if isinstance(d, list) else []


def rows_of(res):
    return (res.get("rows") or []) if isinstance(res, dict) else []


def desc(res, st=200):
    msg = (res.get("msg") or "")[:80] if isinstance(res, dict) else ""
    return "HTTP %s code=%s %s" % (st, code_of(res), msg)


def first_leaf(nodes):
    """从后端 deptTree 结构中取第一个叶子部门，保证新增用户能落到具体部门。"""
    for node in nodes or []:
        children = node.get("children") or []
        if children:
            found = first_leaf(children)
            if found:
                return found
        else:
            return node.get("id")
    return None


# ---------------------------------------------------------------- DB 直连（物理清理）
def _db(sql, params=None, write=False):
    try:
        import asyncio

        from sqlalchemy import text

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        from app.config import settings
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        async def _run():
            engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
            try:
                if write:
                    async with engine.begin() as conn:
                        return (await conn.execute(text(sql), params or {})).rowcount
                async with engine.connect() as conn:
                    return (await conn.execute(text(sql), params or {})).all()
            finally:
                await engine.dispose()

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print("    (DB %s 不可用：%s)" % ("写入" if write else "直读", exc))
        return None


def db_query(sql, params=None):
    return _db(sql, params, write=False)


def db_exec(sql, params=None):
    return _db(sql, params, write=True)


def cleanup_test_users(verbose=True):
    """按用户名前缀物理删除用户及其角色关联，兼容中途崩溃残留。"""
    rows = db_query("SELECT user_id FROM sys_user WHERE user_name LIKE :p", {"p": PREFIX + "%"})
    if rows is None:
        return 0
    ids = [r[0] for r in rows]
    if not ids:
        if verbose:
            print("  [清理] 无残留测试用户")
        return 0

    ids_t = tuple(ids)
    deleted_roles = db_exec("DELETE FROM sys_user_role WHERE user_id IN :ids", {"ids": ids_t}) or 0
    deleted_users = db_exec("DELETE FROM sys_user WHERE user_id IN :ids", {"ids": ids_t}) or 0
    if verbose:
        print("  [清理] 物理删除测试用户 %d 个、角色关联 %d 条：%s" % (deleted_users, deleted_roles, ids))
    for uid in ids:
        if uid in CREATED_USER_IDS:
            CREATED_USER_IDS.remove(uid)
    return deleted_users


def main():
    print("=" * 78)
    print("后台管理「用户管理」模块 E2E 测试")
    print("=" * 78)
    print("[启动自检] 清理上次运行残留…")
    cleanup_test_users()

    admin = login("admin")
    now = datetime.now()
    suffix = now.strftime("%H%M%S%f")[:10]
    user_name = PREFIX + suffix
    nick_name = "临时用户" + suffix[-3:]

    created_uid = None

    try:
        # ---------- 前置数据：角色 / 部门 ----------
        st, res = call("GET", "/system/role/list", admin, params={"pageNum": 1, "pageSize": 100})
        roles = rows_of(res)
        common_role = next((r for r in roles if r.get("roleKey") == "common"), None)
        visitor_role = next((r for r in roles if r.get("roleKey") == "visitor"), None)
        T("U01", "用户管理", "角色列表可用（创建/分配角色的前置）",
          "admin 已登录", "GET /system/role/list", "code=200 且存在 common 角色",
          st == 200 and common_role is not None,
          "roles=%d common=%s" % (len(roles), common_role and common_role.get("roleId")))

        st, res = call("GET", "/system/user/deptTree", admin)
        dept_nodes = dl(res)
        dept_id = first_leaf(dept_nodes)
        T("U02", "用户管理", "归属部门树可用",
          "admin 已登录", "GET /system/user/deptTree", "code=200 且能取到叶子部门",
          st == 200 and dept_id is not None,
          "deptId=%s 节点数=%d" % (dept_id, len(dept_nodes)))

        # ---------- 新增表单选项 ----------
        st, res = call("GET", "/system/user/", admin)
        options = dd(res)
        T("U03", "用户管理", "新增用户弹窗能拿到角色下拉（GET /system/user/）",
          "admin 已登录", "GET /system/user/", "code=200，data.roles / 顶层 roles 均非空",
          st == 200 and len(options.get("roles") or []) >= 2 and len(res.get("roles") or []) >= 2,
          "dataRoles=%d topRoles=%d" % (len(options.get("roles") or []), len(res.get("roles") or [])))

        # ---------- 列表按登录账号筛选 ----------
        st, res = call("GET", "/system/user/list", admin, params={"userName": "admin", "pageNum": 1, "pageSize": 20})
        found = rows_of(res)
        T("U04", "用户管理", "列表支持 userName 筛选（camelCase 参数）",
          "admin 已登录", "GET /system/user/list?userName=admin", "只返回 admin",
          st == 200 and len(found) == 1 and found[0].get("userName") == "admin",
          "rows=%d first=%s" % (len(found), found[0].get("userName") if found else None))

        # ---------- 新增用户 ----------
        payload = {
            "deptId": dept_id,
            "userName": user_name,
            "nickName": nick_name,
            "password": "Temp#123456",
            "email": "tmp_%s@example.com" % suffix,
            "phonenumber": "1390000" + suffix[-4:],
            "sex": "0",
            "status": "0",
            "remark": "接口联调临时数据，测试结束物理删除",
            "postIds": [],
            "roleIds": [common_role["roleId"]],
        }
        st, res = call("POST", "/system/user", admin, body=payload)
        uid = dd(res).get("user_id")
        created_uid = uid
        if uid:
            CREATED_USER_IDS.append(uid)
        T("U05", "用户管理", "新增用户（camelCase 请求体）",
          "已取到 common 角色与部门 deptId", "POST /system/user", "code=200 且返回 user_id",
          st == 200 and bool(uid), "uid=%s %s" % (uid, desc(res, st)))

        # 等 get_db 在响应后提交
        time.sleep(0.8)

        # ---------- 详情 ----------
        st, res = call("GET", "/system/user/%s" % uid, admin)
        detail = dd(res)
        T("U06", "用户管理", "新增后可查详情并回显角色/部门",
          "用户已创建", "GET /system/user/{id}", "deptId/roleIds/userName 与创建一致，且顶层 roleIds 兼容旧前端",
          st == 200 and detail.get("userName") == user_name
          and detail.get("deptId") == dept_id
          and common_role["roleId"] in (detail.get("roleIds") or [])
          and common_role["roleId"] in (res.get("roleIds") or []),
          "detail=%s" % json.dumps(detail, ensure_ascii=False)[:180])

        # ---------- 列表能搜到新用户 ----------
        st, res = call("GET", "/system/user/list", admin, params={"userName": user_name, "pageNum": 1, "pageSize": 20})
        found = rows_of(res)
        T("U07", "用户管理", "列表能按新用户登录账号精确命中",
          "用户已创建", "GET /system/user/list?userName=新账号", "返回 1 条且 dept.deptName 有值",
          st == 200 and len(found) == 1
          and found[0].get("userId") == uid
          and bool(((found[0].get("dept") or {}).get("deptName"))),
          "rows=%d dept=%s" % (len(found), found[0].get("dept") if found else None))

        # ---------- 重复创建校验（用户仍处于正常状态） ----------
        st, res = call("POST", "/system/user", admin, body=payload)
        T("U15", "用户管理", "重复登录账号创建被拦截",
          "用户已创建且未删除", "再次 POST 同 userName", "非 200 且提示用户名已存在",
          code_of(res) != 200 and "用户名已存在" in (res.get("msg") or ""),
          desc(res, st))

        # ---------- 修改用户 ----------
        new_nick = nick_name + "改"
        update_payload = {
            "userId": uid,
            "nickName": new_nick,
            "email": "updated_%s@example.com" % suffix,
            "phonenumber": "1391111" + suffix[-4:],
            "sex": "1",
            "deptId": dept_id,
            "status": "0",
            "remark": "已修改",
            "roleIds": [common_role["roleId"], visitor_role["roleId"]] if visitor_role else [common_role["roleId"]],
        }
        st, res = call("PUT", "/system/user", admin, body=update_payload)
        time.sleep(0.8)
        st2, res2 = call("GET", "/system/user/%s" % uid, admin)
        detail2 = dd(res2)
        expect_role_ids = set(update_payload["roleIds"])
        T("U08", "用户管理", "修改用户基础字段与角色",
          "用户已创建", "PUT /system/user 后 GET 详情", "昵称/邮箱/性别/角色均更新",
          st == 200 and detail2.get("nickName") == new_nick
          and detail2.get("email") == update_payload["email"]
          and detail2.get("sex") == "1"
          and expect_role_ids == set(detail2.get("roleIds") or []),
          "nick=%s roles=%s" % (detail2.get("nickName"), detail2.get("roleIds")))

        # ---------- 重置密码 ----------
        st, res = call("PUT", "/system/user/resetPwd", admin, body={"userId": uid, "password": "Temp#654321"})
        T("U09", "用户管理", "重置密码（camelCase JSON body）",
          "用户已创建", "PUT /system/user/resetPwd", "code=200",
          st == 200 and code_of(res) == 200, desc(res, st))

        # ---------- 状态切换 ----------
        st, res = call("PUT", "/system/user/changeStatus", admin, body={"userId": uid, "status": "1"})
        time.sleep(0.8)
        st2, res2 = call("GET", "/system/user/%s" % uid, admin)
        status_after = dd(res2).get("status")
        T("U10", "用户管理", "停用用户（PUT JSON body）",
          "用户已创建", "PUT /system/user/changeStatus {status:1}", "code=200 且详情 status=1",
          st == 200 and status_after == "1", "status=%s %s" % (status_after, desc(res, st)))

        st, res = call("PUT", "/system/user/changeStatus", admin, body={"userId": uid, "status": "0"})
        time.sleep(0.8)
        st2, res2 = call("GET", "/system/user/%s" % uid, admin)
        status_after = dd(res2).get("status")
        T("U11", "用户管理", "启用用户",
          "用户已停用", "PUT /system/user/changeStatus {status:0}", "code=200 且详情 status=0",
          st == 200 and status_after == "0", "status=%s %s" % (status_after, desc(res, st)))

        # ---------- 角色授权页数据 ----------
        st, res = call("GET", "/system/user/authRole/%s" % uid, admin)
        auth_roles = res.get("roles") if isinstance(res, dict) else None
        role_ids = {r.get("roleId") for r in (auth_roles or [])}
        common_row = next((r for r in (auth_roles or []) if r.get("roleId") == common_role["roleId"]), None)
        T("U12", "用户管理", "分配角色页返回全部角色且已授权 flag=true",
          "用户拥有 common 角色", "GET /system/user/authRole/{id}",
          "角色列表包含 common 且 flag=true，不是只返回已分配角色",
          st == 200 and common_role["roleId"] in role_ids and common_row and common_row.get("flag") is True,
          "roles=%d commonFlag=%s" % (len(auth_roles or []), common_row and common_row.get("flag")))

        # ---------- 分配角色 ----------
        target_role_ids = [common_role["roleId"]]
        if visitor_role:
            target_role_ids.append(visitor_role["roleId"])
        st, res = call(
            "PUT", "/system/user/authRole", admin,
            params={"userId": uid, "roleIds": ",".join(str(x) for x in target_role_ids)},
        )
        time.sleep(0.8)
        st2, res2 = call("GET", "/system/user/%s" % uid, admin)
        assigned = set(dd(res2).get("roleIds") or [])
        T("U13", "用户管理", "分配角色（PUT + query userId/roleIds）",
          "已打开分配角色页", "PUT /system/user/authRole", "详情 roleIds 与分配一致",
          st == 200 and set(target_role_ids) == assigned, "assigned=%s %s" % (sorted(assigned), desc(res, st)))

        # ---------- 删除 ----------
        st, res = call("DELETE", "/system/user/%s" % uid, admin)
        time.sleep(0.8)
        st2, res2 = call("GET", "/system/user/list", admin, params={"userName": user_name, "pageNum": 1, "pageSize": 20})
        rows_after = rows_of(res2)
        T("U14", "用户管理", "删除用户（逻辑删除后列表不可见）",
          "用户已创建", "DELETE /system/user/{id} 后查列表", "code=200 且列表 0 条",
          st == 200 and len(rows_after) == 0,
          "rows=%d %s" % (len(rows_after), desc(res, st)))

    finally:
        print("[结束清理] 物理删除本次/残留测试用户…")
        cleanup_test_users()

    passed = sum(1 for r in ROWS if r["status"] == "通过")
    failed = len(ROWS) - passed
    print("=" * 78)
    print("用例结果：通过 %d / 失败 %d / 共 %d" % (passed, failed, len(ROWS)))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "overview": {"total": len(ROWS), "passed": passed, "failed": failed},
            "rows": ROWS,
            "cleanup": {"prefix": PREFIX, "created_user_ids": CREATED_USER_IDS},
        }, f, ensure_ascii=False, indent=2)
    print("结果文件：%s" % OUT)


if __name__ == "__main__":
    main()
