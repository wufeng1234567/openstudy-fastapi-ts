# -*- coding: utf-8 -*-
"""后台管理页面「评论管理」模块 E2E 接口测试（真实 HTTP 调用）

被测页面：openstudy-vue3-ts/src/views/comment/comment/index.vue
被测接口：/system/comment/*（app/api/v1/systemComment.py，本次新增）
账号角色：admin(1) 管理员 / user1(105) 普通用户 / user2(106) 普通用户
用例编号：R*（R=评论管理）

背景（修复前的真实状况）：
  `/system/comment/*` 后端 **完全没实现**，请求全部落到 catch_all 兜底：
    - GET  list          → 兜底 paginate(0, [])      → 列表永远空
    - GET  /{id}         → 兜底 success(None)        → 查看对话框空白
    - PUT  /             → 兜底 success(None)        → 提示「修改成功」但数据没变
    - DELETE /{ids}      → 兜底 success(None)        → 提示「删除成功」但没删
  所以本套件的核心断言是「**数据真的变了**」，而不是「接口返回 200」。

用法（后端需先跑起来，默认 127.0.0.1:9101）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_comment_admin_api.py

产出：脚本同目录 e2e_comment_admin_api_result.json
说明：评论建在已有演示笔记上，结束按 id 物理删除评论并清理通知，不留残留。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_comment_admin_api_result.json")

ROWS = []


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
    return res["data"]["token"]


def T(cid, module, title, pre, steps, expected, ok, actual):
    ROWS.append({
        "cid": cid, "module": module, "title": title, "pre": pre,
        "steps": steps, "expected": expected, "actual": actual,
        "status": "通过" if ok else "失败",
    })
    print(("  [PASS] " if ok else "  [FAIL] ") + cid + " " + title + " -> " + str(actual))


def code_of(res):
    return res.get("code") if isinstance(res, dict) else "-"


def raw_data(res):
    return res.get("data") if isinstance(res, dict) else None


def dd(res):
    d = raw_data(res)
    return d if isinstance(d, dict) else {}


def rows_of(res):
    return (res.get("rows") or []) if isinstance(res, dict) else []


def desc(res, st=200):
    msg = (res.get("msg") or "")[:80] if isinstance(res, dict) else ""
    return "HTTP %s code=%s %s" % (st, code_of(res), msg)


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


def db_one(sql, params=None):
    rows = db_query(sql, params)
    if not rows:
        return None
    return dict(rows[0]._mapping)


def sweep_leftovers(created):
    ids = created.get("comment_ids") or []
    if not ids:
        return
    t = tuple(ids) or (0,)
    db_exec("DELETE FROM note_comment WHERE id IN :i OR parent_id IN :i", {"i": t})
    db_exec("DELETE FROM sys_notice WHERE remark LIKE '%\"commentId\"%' AND remark LIKE '%话题%'")
    print("  [自检] 已清理上次运行遗留评论：%s" % ids)


def main():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                sweep_leftovers(json.load(f).get("cleanup") or {})
        except Exception as exc:  # noqa: BLE001
            print("  [自检] 读取上次结果失败：%s" % exc)

    print("=" * 78)
    print("后台管理「评论管理」模块 E2E 测试")
    print("=" * 78)

    ta = login("admin")
    t1 = login("user1")
    t2 = login("user2")

    # ---- 准备：挑两条演示笔记，造评论/回复 ----
    notes = [dict(r._mapping) for r in (db_query(
        "SELECT note_id, title, comment_count FROM note WHERE del_flag='0' ORDER BY note_id LIMIT 2") or [])]
    if len(notes) < 2:
        print("!! 需要至少 2 条笔记用于测试，已退出")
        return
    note_a, note_b = notes[0]["note_id"], notes[1]["note_id"]
    uid1 = db_one("SELECT user_id FROM sys_user WHERE user_name='user1'")["user_id"]
    uid2 = db_one("SELECT user_id FROM sys_user WHERE user_name='user2'")["user_id"]
    uid_admin = db_one("SELECT user_id FROM sys_user WHERE user_name='admin'")["user_id"]
    print("noteA=%s noteB=%s uid1=%s uid2=%s" % (note_a, note_b, uid1, uid2))

    # 记录通知基线，便于结束后清理（评论/回复会写 sys_notice）
    base_notices = {r[0] for r in (db_query("SELECT notice_id FROM sys_notice") or [])}

    created = []

    def create_comment(tok, note_id, content, **extra):
        params = {"noteId": note_id, "content": content}
        params.update(extra)
        st, res = call("POST", "/notes/comment/create", tok, params=params)
        cid = dd(res).get("commentId")
        if cid:
            created.append(cid)
        return cid, res

    stamp = time.strftime("%m%d%H%M")
    body_a1 = "评论管理校验-一级评论A1-" + stamp
    c1, r1 = create_comment(t1, note_a, body_a1)
    c2, r2 = create_comment(t2, note_a, "评论管理校验-一级评论A2-" + stamp)
    c3, r3 = create_comment(t1, note_b, "评论管理校验-笔记B评论-" + stamp)
    # user2 回复 c1（回复对象=user1）
    c4, r4 = create_comment(t2, note_a, "评论管理校验-回复A1-" + stamp,
                            parentId=c1, replyToUserId=uid1)
    print("评论：c1=%s c2=%s c3=%s 回复c4=%s" % (c1, c2, c3, c4))

    M = "评论管理(后台)"

    # ==================== R1 列表与筛选 ====================
    st, res = call("GET", "/system/comment/list", ta, params={"pageNum": 1, "pageSize": 10})
    T("R01", M, "列表-管理员查询返回分页结构",
      "已造 4 条评论（含 1 条回复）", "GET /system/comment/list",
      "code=200；顶层含 total 与 rows（修复前列表永远为空）",
      code_of(res) == 200 and "total" in res and "rows" in res and len(rows_of(res)) > 0,
      "code=%s total=%s rows=%d" % (code_of(res), res.get("total"), len(rows_of(res))))

    st, res = call("GET", "/system/comment/list", ta,
                   params={"noteId": note_a, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    ids = {r.get("commentId") for r in rows}
    T("R02", M, "列表-按笔记ID筛选",
      "noteA=%s 下有 3 条评论" % note_a, "admin 请求 list?noteId=%s" % note_a,
      "rows 的 noteId 全为 noteA，且命中 c1/c2/c4",
      code_of(res) == 200 and len(rows) >= 3 and all(r.get("noteId") == note_a for r in rows)
      and {c1, c2, c4} <= ids,
      "命中 %d 条 noteId集合=%s" % (len(rows), sorted({r.get("noteId") for r in rows})))

    st, res = call("GET", "/system/comment/list", ta,
                   params={"content": stamp, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("R03", M, "列表-按评论内容模糊筛选",
      "本次造的评论内容都含「%s」" % stamp, "admin 请求 list?content=%s" % stamp,
      "命中 4 条且 content 均含关键字",
      code_of(res) == 200 and len(rows) >= 4 and all(stamp in (r.get("content") or "") for r in rows),
      "命中 %d 条" % len(rows))

    st, res = call("GET", "/system/comment/list", ta,
                   params={"userName": "演示用户2", "noteId": note_a, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("R04", M, "列表-按用户名称筛选",
      "noteA 下 user2 有 2 条评论", "admin 请求 list?noteId=noteA&userName=演示用户2",
      "命中且 userId 全为 user2",
      code_of(res) == 200 and len(rows) >= 2 and all(r.get("userId") == uid2 for r in rows),
      "命中 %d 条 userId集合=%s" % (len(rows), sorted({r.get("userId") for r in rows})))

    st, res = call("GET", "/system/comment/list", ta,
                   params={"noteId": note_a, "status": "0", "pageNum": 1, "pageSize": 100})
    rows0 = rows_of(res)
    T("R05", M, "列表-按状态筛选（正常）",
      "noteA 的评论当前都是正常(0)", "admin 请求 list?noteId=noteA&status=0",
      "命中且 status 全为 '0'（字符串，页面用 === '0' 判断）",
      code_of(res) == 200 and len(rows0) >= 3 and all(r.get("status") == "0" for r in rows0),
      "命中 %d 条 status集合=%s" % (len(rows0), sorted({r.get("status") for r in rows0})))

    # RuoYi 日期范围惯例：params[beginTime] / params[endTime]（axios 会把 params 对象序列化成这个形状）
    st, res = call("GET", "/system/comment/list", ta,
                   params={"noteId": note_a, "params[beginTime]": "2020-01-01",
                           "params[endTime]": "2030-12-31", "pageNum": 1, "pageSize": 100})
    rows_t = rows_of(res)
    st2, res2 = call("GET", "/system/comment/list", ta,
                     params={"noteId": note_a, "params[beginTime]": "1990-01-01",
                             "params[endTime]": "1990-01-02", "pageNum": 1, "pageSize": 100})
    T("R06", M, "列表-按评论时间范围筛选（params[beginTime]/params[endTime]）",
      "评论 create_time 在 2020~2030", "分别用宽区间与空区间请求",
      "宽区间命中 >=3；空区间命中 0",
      code_of(res) == 200 and len(rows_t) >= 3 and code_of(res2) == 200 and len(rows_of(res2)) == 0,
      "宽区间=%d 空区间=%d" % (len(rows_t), len(rows_of(res2))))

    st, res = call("GET", "/system/comment/list", ta, params={"pageNum": 1, "pageSize": 2})
    T("R07", M, "列表-分页返回条数受 pageSize 约束",
      "评论总数 > 2", "admin 请求 list?pageSize=2",
      "rows<=2 且 total>=3",
      code_of(res) == 200 and len(rows_of(res)) <= 2 and (res.get("total") or 0) >= 3,
      "total=%s rows=%d" % (res.get("total"), len(rows_of(res))))

    st, res = call("GET", "/system/comment/list", ta,
                   params={"noteId": note_a, "pageNum": 1, "pageSize": 100})
    sample = next((r for r in rows_of(res) if r.get("commentId") == c1), {})
    need = ["commentId", "noteId", "noteTitle", "userName", "content", "status", "createTime"]
    missing = [f for f in need if f not in sample]
    T("R08", M, "前端契约-列表字段覆盖页面表格",
      "c1=%s" % c1, "比对 index.vue 表格 prop 与返回字段",
      "含 commentId/noteId/noteTitle/userName/content/status/createTime，且 status 为字符串",
      code_of(res) == 200 and bool(sample) and not missing and isinstance(sample.get("status"), str),
      "缺失=%s status类型=%s" % (missing or "无", type(sample.get("status")).__name__))

    # ==================== R2 详情 ====================
    st, res = call("GET", "/system/comment/%s" % c4, ta)
    d = dd(res)
    T("R09", M, "详情-返回完整字段（含回复对象）",
      "c4=%s 是 user2 对 c1 的回复" % c4, "admin GET /system/comment/{c4}",
      "code=200；commentId/replyUserName/content/noteTitle 均正确",
      code_of(res) == 200 and d.get("commentId") == c4 and d.get("replyUserName")
      and d.get("replyToUserId") == uid1 and (stamp in (d.get("content") or ""))
      and bool(d.get("noteTitle")),
      "code=%s replyUserName=%s replyToUserId=%s"
      % (code_of(res), d.get("replyUserName"), d.get("replyToUserId")))

    st, res = call("GET", "/system/comment/99999999", ta)
    T("R10", M, "详情-评论不存在时的异常处理",
      "commentId=99999999 不存在", "admin GET /system/comment/99999999",
      "code!=200（修复前会落到 catch_all 返回 success(null)）",
      code_of(res) != 200, desc(res, st))

    # ==================== R3 修改（显示/隐藏） ====================
    st, res = call("PUT", "/system/comment", ta, {"commentId": c1, "status": "1"})
    db_stat = db_one("SELECT status FROM note_comment WHERE id=:i", {"i": c1})
    st2, pub = call("GET", "/notes/comment/list", params={"noteId": note_a, "pageNum": 1, "pageSize": 100})
    pub_ids = {x.get("commentId") for x in (dd(pub).get("list") or [])}
    T("R11", M, "修改-隐藏评论（status=1）真正生效",
      "c1=%s 当前为正常" % c1, "admin PUT /system/comment {commentId,status:'1'} 后直读库 + 查前台列表",
      "code=200；库中 status=1；前台评论列表不再返回 c1（修复前只是假成功）",
      code_of(res) == 200 and (db_stat or {}).get("status") == 1 and c1 not in pub_ids,
      "code=%s 库status=%s 前台含c1=%s" % (code_of(res), (db_stat or {}).get("status"), c1 in pub_ids))

    st, res = call("PUT", "/system/comment", ta, {"commentId": c1, "status": "0"})
    db_stat = db_one("SELECT status FROM note_comment WHERE id=:i", {"i": c1})
    st2, pub = call("GET", "/notes/comment/list", params={"noteId": note_a, "pageNum": 1, "pageSize": 100})
    pub_ids = {x.get("commentId") for x in (dd(pub).get("list") or [])}
    T("R12", M, "修改-重新显示评论（status=0）真正生效",
      "c1 已被隐藏", "admin PUT {commentId,status:'0'} 后直读库 + 查前台列表",
      "code=200；库中 status=0；前台列表恢复返回 c1",
      code_of(res) == 200 and (db_stat or {}).get("status") == 0 and c1 in pub_ids,
      "code=%s 库status=%s 前台含c1=%s" % (code_of(res), (db_stat or {}).get("status"), c1 in pub_ids))

    st, res = call("PUT", "/system/comment", ta, {"commentId": 99999999, "status": "1"})
    T("R13", M, "修改-评论不存在时的异常处理",
      "commentId=99999999 不存在", "admin PUT {commentId:99999999}",
      "code!=200（修复前假成功）",
      code_of(res) != 200, desc(res, st))

    # ==================== R4 删除 ====================
    cnt_before = db_one("SELECT comment_count FROM note WHERE note_id=:n", {"n": note_a})
    cnt_before = (cnt_before or {}).get("comment_count")
    real_before = db_one("SELECT COUNT(*) c FROM note_comment WHERE note_id=:n", {"n": note_a})
    real_before = (real_before or {}).get("c")

    st, res = call("DELETE", "/system/comment/%s" % c1, ta)
    left = db_one("SELECT COUNT(*) c FROM note_comment WHERE id IN :i", {"i": (c1, c4)})
    real_after = db_one("SELECT COUNT(*) c FROM note_comment WHERE note_id=:n", {"n": note_a})
    real_after = (real_after or {}).get("c")
    cnt_after = db_one("SELECT comment_count FROM note WHERE note_id=:n", {"n": note_a})
    cnt_after = (cnt_after or {}).get("comment_count")
    T("R14", M, "删除-删一级评论连带删除其下回复",
      "c1=%s 有 1 条回复 c4=%s" % (c1, c4),
      "admin DELETE /system/comment/{c1} 后直读库",
      "code=200；c1 与 c4 均已删除（修复前只是假成功）",
      code_of(res) == 200 and (left or {}).get("c") == 0,
      "code=%s c1/c4剩余=%s" % (code_of(res), (left or {}).get("c")))

    T("R15", M, "删除-同步扣减笔记评论数",
      "noteA 原 comment_count=%s，实际评论 %s 条" % (cnt_before, real_before),
      "删除 c1+c4 后对比 note.comment_count 与实际条数",
      "comment_count = %s（= 原值 - 2）；且与实际评论条数一致（%s）"
      % ((cnt_before or 0) - 2, real_after),
      cnt_after == (cnt_before or 0) - 2 and cnt_after == real_after,
      "comment_count=%s 实际=%s" % (cnt_after, real_after))

    st, res = call("DELETE", "/system/comment/99999999", ta)
    T("R16", M, "删除-不存在的 id 不应 500",
      "commentId=99999999 不存在", "admin DELETE /system/comment/99999999",
      "返回业务响应（200 幂等），不得 500",
      st != 500 and code_of(res) != 500, desc(res, st))

    # ==================== R5 权限 ====================
    st1, a1 = call("GET", "/system/comment/list", t1, params={"pageNum": 1, "pageSize": 10})
    st2, a2 = call("GET", "/system/comment/%s" % c2, t1)
    st3, a3 = call("PUT", "/system/comment", t1, {"commentId": c2, "status": "1"})
    st4, a4 = call("DELETE", "/system/comment/%s" % c2, t1)
    still = db_one("SELECT COUNT(*) c FROM note_comment WHERE id=:i", {"i": c2})
    T("R17", M, "权限-普通用户不能使用评论管理（列表/详情/修改/删除均 403）",
      "user1 登录（评论管理属后台功能）",
      "user1 依次请求 list / {id} / PUT / DELETE",
      "四个接口均 code=403；c2 未被改动删除",
      code_of(a1) == 403 and code_of(a2) == 403 and code_of(a3) == 403 and code_of(a4) == 403
      and (still or {}).get("c") == 1,
      "list=%s get=%s put=%s delete=%s 仍存在=%s"
      % (code_of(a1), code_of(a2), code_of(a3), code_of(a4), (still or {}).get("c")))

    # ==================== R6 清理 ====================
    ids_t = tuple(created) or (0,)
    db_exec("DELETE FROM note_comment WHERE id IN :i", {"i": ids_t})
    new_notices = [r[0] for r in (db_query("SELECT notice_id FROM sys_notice") or [])
                   if r[0] not in base_notices]
    if new_notices:
        db_exec("DELETE FROM sys_notice WHERE notice_id IN :i", {"i": tuple(new_notices)})
    # 评论数按真实剩余条数校正
    for nid in (note_a, note_b):
        db_exec("UPDATE note SET comment_count = (SELECT COUNT(*) FROM note_comment WHERE note_id=:n) "
                "WHERE note_id=:n", {"n": nid})

    left_test = db_one("SELECT COUNT(*) c FROM note_comment WHERE id IN :i", {"i": ids_t})
    left_orphan = db_one("SELECT COUNT(*) c FROM note_comment c LEFT JOIN note n ON n.note_id=c.note_id "
                         "WHERE n.note_id IS NULL")
    left_notice = db_one("SELECT COUNT(*) c FROM sys_notice WHERE create_by='system' AND remark LIKE '%commentId%' "
                         "AND remark LIKE :s", {"s": "%" + stamp + "%"})
    T("R18", M, "清理-无测试数据残留（评论/通知）",
      "清理完成", "直连库核对测试评论、孤儿评论、本次通知",
      "测试评论=0、孤儿评论=0、本次通知=0",
      all((x or {}).get("c") == 0 for x in (left_test, left_orphan, left_notice)),
      "测试评论=%s 孤儿评论=%s 本次通知=%s"
      % ((left_test or {}).get("c"), (left_orphan or {}).get("c"), (left_notice or {}).get("c")))

    total = len(ROWS)
    passed = sum(1 for r in ROWS if r["status"] == "通过")
    print("=" * 78)
    print("用例总数 %d，通过 %d，失败 %d" % (total, passed, total - passed))
    print("=" * 78)
    for r in ROWS:
        if r["status"] == "失败":
            print("  [FAIL] %s %s" % (r["cid"], r["title"]))
            print("         预期: %s" % r["expected"])
            print("         实际: %s" % r["actual"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "prefix": "评论管理", "uid1": uid1, "uid2": uid2, "uid_admin": uid_admin, "rows": ROWS,
            "cleanup": {"comment_ids": created},
        }, f, ensure_ascii=False, indent=2)
    print("结果已写入", OUT)


if __name__ == "__main__":
    main()
