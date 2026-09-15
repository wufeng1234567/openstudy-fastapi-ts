# -*- coding: utf-8 -*-
"""后台管理页面「斩题管理」模块 E2E 接口测试（真实 HTTP 调用）

被测页面：openstudy-vue3-ts/src/views/questionMarked/questionMarked/index.vue
被测接口：app/api/v1/questions.py 的 /questionMarked/questionMarked/*
账号角色：admin(1) 管理员 / user1(105) 普通用户 / user2(106) 普通用户
用例编号：N*（N=后台斩题管理）

与既有 G 模块（e2e_question_api.py，前台「我的斩题」）的区别：
  G 只覆盖 **普通用户操作自己的数据**；
  本套件专门覆盖 **后台管理页面** 的语义：管理员跨用户查询/筛选/代录/修改/删除/导出。

判定口径（与同项目「错题管理」后台模块 questionError 对齐，也与 SpringBoot 参考版一致）：
  - list 支持 userId/questionId/bankId/markedType/difficultyLevel/isMastered/notes/tags + 时间范围
  - 管理员不传 userId → 可看全部用户；普通用户 → 只能看自己
  - 新增：管理员可代任意用户写入（payload.userId），普通用户代他人写入必须 403
  - 详情/修改/删除：管理员可操作任意用户记录，普通用户越权必须 403
  - 记录字段：errorTimesBeforeMark/correctTimesBeforeMark/reviewCount/lastReviewTime/
    nextReviewTime/masteryDate/markedStatus 均需能写入并能回显

用法（后端需先跑起来，默认 127.0.0.1:9101）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_marked_admin_api.py

产出：脚本同目录 e2e_marked_admin_api_result.json
说明：全部测试数据建在临时题库上，结束时删除该题库（级联清理），不留残留。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_marked_admin_api_result.json")

ROWS = []


def call(method, path, token=None, body=None, params=None, timeout=25):
    url = BASE + path
    if params:
        # 跳过 None（与 axios 行为一致：null/undefined 不入 query）
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


def dl(res):
    d = raw_data(res)
    return d if isinstance(d, list) else []


def rows_of(res):
    return (res.get("rows") or []) if isinstance(res, dict) else []


def is_file(res):
    return isinstance(res, (bytes, bytearray)) and len(res) > 0


def desc(res, st=200):
    if is_file(res):
        return "HTTP %s 文件流 大小=%d 字节" % (st, len(res))
    msg = (res.get("msg") or "")[:80] if isinstance(res, dict) else ""
    return "HTTP %s code=%s %s" % (st, code_of(res), msg)


# ---------------------------------------------------------------- DB 直连（校验接口未暴露的字段）
def _db(sql, params=None, write=False):
    try:
        import asyncio

        from sqlalchemy import text

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        # 自建 engine 并在同一协程内 dispose：反复 asyncio.run 复用全局 engine 会串连接池
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


def new_question(t1, bank_id, text):
    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_id, "questionType": 1, "questionText": text,
        "options": [{"key": "A", "value": "1"}, {"key": "B", "value": "2"}], "answer": "A",
    })
    return dd(res).get("questionId")


def sweep_leftovers(created):
    """按记录的 id 清除上一次运行（可能中途崩溃）遗留的测试数据"""
    bank_ids = created.get("bank_ids") or []
    if not bank_ids:
        return
    bank_t = tuple(bank_ids) or (0,)
    rows = db_query("SELECT id FROM question_main WHERE bank_id IN :b", {"b": bank_t}) or []
    q_ids = [r[0] for r in rows]
    if q_ids:
        q_t = tuple(q_ids)
        db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM note_question WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_sub WHERE main_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_main WHERE id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_bank_favorite WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share_receive WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    print("  [自检] 已清理上次运行遗留：bank=%s question=%d" % (bank_ids, len(q_ids)))


def main():
    prev = OUT
    if os.path.exists(prev):
        try:
            with open(prev, encoding="utf-8") as f:
                sweep_leftovers(json.load(f).get("cleanup") or {})
        except Exception as exc:  # noqa: BLE001
            print("  [自检] 读取上次结果失败：%s" % exc)

    P = "斩题整理"
    BANK = P + "后台管理测试题库"

    print("=" * 78)
    print("后台管理「斩题管理」模块 E2E 测试   前缀 =", P)
    print("=" * 78)

    ta = login("admin")
    t1 = login("user1")
    t2 = login("user2")

    # ---------- 准备：临时题库 / 题目 ----------
    st, ca = call("POST", "/questionBank/questionBank", t1, {"bankName": BANK})
    bank_id = dd(ca).get("id")
    uid1 = dd(ca).get("userId")

    st, cb = call("POST", "/questionBank/questionBank", ta, {"bankName": P + "管理员探针"})
    uid_admin = dd(cb).get("userId")
    call("DELETE", "/questionBank/questionBank/%s" % dd(cb).get("id"), ta)

    st, cc = call("POST", "/questionBank/questionBank", t2, {"bankName": P + "用户2探针"})
    uid2 = dd(cc).get("userId")
    call("DELETE", "/questionBank/questionBank/%s" % dd(cc).get("id"), t2)

    q1 = new_question(t1, bank_id, P + "-用户已有记录题A")
    q2 = new_question(t1, bank_id, P + "-筛选校验题B")
    q3 = new_question(t1, bank_id, P + "-后台新增题C")
    q4 = new_question(t1, bank_id, P + "-后台修改题D")
    q5 = new_question(t1, bank_id, P + "-后台单删题E")
    q6 = new_question(t1, bank_id, P + "-后台批量删题F")
    q7 = new_question(t1, bank_id, P + "-后台批量删题G")
    q8 = new_question(t1, bank_id, P + "-越权删题H")
    q9 = new_question(t1, bank_id, P + "-用户2自有题I")
    q10 = new_question(t1, bank_id, P + "-越权新增题J")
    print("bank=%s uid_admin=%s uid1=%s uid2=%s" % (bank_id, uid_admin, uid1, uid2))
    print("q1..q10 =", q1, q2, q3, q4, q5, q6, q7, q8, q9, q10)

    # 造 user1 的基线数据：q1、q2 各一条斩题
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q1, "bankId": bank_id})
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q2, "bankId": bank_id})
    # 造 user2 的基线数据：q9 一条斩题（用于验证「普通用户只看到自己」非空场景）
    call("POST", "/questionMarked/questionMarked", t2, {"questionId": q9, "bankId": bank_id})
    m2 = db_one("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                {"u": uid1, "q": q2})
    call("PUT", "/questionMarked/questionMarked", t1, {
        "markedId": (m2 or {}).get("marked_id"), "markedType": 3, "difficultyLevel": 4,
        "isMastered": 1, "notes": P + "-筛选样本", "tags": "难题,重点"})

    # 期望值一律从库里取，避免硬编码
    exp_user1_total = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE user_id=:u AND marked_status=1",
                             {"u": uid1})
    exp_user1_total = (exp_user1_total or {}).get("c")
    exp_user2_total = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE user_id=:u AND marked_status=1",
                             {"u": uid2})
    exp_user2_total = (exp_user2_total or {}).get("c")
    exp_bank_total = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE bank_id=:b AND marked_status=1",
                            {"b": bank_id})
    exp_bank_total = (exp_bank_total or {}).get("c")
    exp_user1_bank = db_one("SELECT COUNT(*) c FROM user_question_marked "
                            "WHERE user_id=:u AND bank_id=:b AND marked_status=1",
                            {"u": uid1, "b": bank_id})
    exp_user1_bank = (exp_user1_bank or {}).get("c")
    exp_type3 = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE marked_type=3 AND marked_status=1",
                       {})
    exp_type3 = (exp_type3 or {}).get("c")
    exp_not_mastered = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE is_mastered=0 AND marked_status=1",
                              {})
    exp_not_mastered = (exp_not_mastered or {}).get("c")
    print("基线：user1活跃斩题=%s，user2活跃斩题=%s，测试题库活跃斩题=%s，全库 markedType=3=%s，未掌握=%s"
          % (exp_user1_total, exp_user2_total, exp_bank_total, exp_type3, exp_not_mastered))

    M = "斩题管理(后台)"

    # ==================== N1 列表查询与筛选（对应后台列表页 getList 入参） ====================
    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"pageNum": 1, "pageSize": 10})
    T("N01", M, "列表-管理员查询返回分页结构",
      "admin 已登录", "GET /questionMarked/questionMarked/list?pageNum=1&pageSize=10",
      "code=200；顶层包含 total 与 rows（若依分页契约）",
      code_of(res) == 200 and "total" in res and "rows" in res,
      "code=%s total=%s rows=%d" % (code_of(res), res.get("total"), len(rows_of(res))))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"userId": uid1, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N02", M, "列表-按用户ID筛选（后台按用户查斩题）",
      "user1(%s) 有 %s 条活跃斩题" % (uid1, exp_user1_total),
      "admin 请求 list?userId=%s" % uid1,
      "total=%s 且 rows 的 userId 全为 %s" % (exp_user1_total, uid1),
      code_of(res) == 200 and res.get("total") == exp_user1_total
      and len(rows) > 0 and all(r.get("userId") == uid1 for r in rows),
      "total=%s rows=%d userId集合=%s" % (res.get("total"), len(rows),
                                          sorted({r.get("userId") for r in rows})[:5]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"questionId": q1, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N03", M, "列表-按题目ID精确筛选",
      "user1 在 q1=%s 上有 1 条斩题" % q1,
      "admin 请求 list?questionId=%s" % q1,
      "命中 1 条且 questionId=q1",
      code_of(res) == 200 and len(rows) == 1 and rows[0].get("questionId") == q1,
      "命中 %d 条 questionIds=%s" % (len(rows), [r.get("questionId") for r in rows][:5]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"bankId": bank_id, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N04", M, "列表-按所属题库筛选",
      "测试题库 bank=%s 有 %s 条活跃斩题" % (bank_id, exp_bank_total),
      "admin 请求 list?bankId=%s" % bank_id,
      "total=%s 且 rows 的 bankId 全为该题库" % exp_bank_total,
      code_of(res) == 200 and res.get("total") == exp_bank_total and len(rows) > 0
      and all(r.get("bankId") == bank_id for r in rows),
      "total=%s rows=%d bankId集合=%s" % (res.get("total"), len(rows),
                                          sorted({r.get("bankId") for r in rows})[:5]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"markedType": 3, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N05", M, "列表-按斩题类型筛选",
      "全库 markedType=3 共 %s 条" % exp_type3,
      "admin 请求 list?markedType=3",
      "total=%s 且 rows 的 markedType 全为 3" % exp_type3,
      code_of(res) == 200 and res.get("total") == exp_type3 and len(rows) > 0
      and all(r.get("markedType") == 3 for r in rows),
      "total=%s rows=%d markedType集合=%s" % (res.get("total"), len(rows),
                                              sorted({r.get("markedType") for r in rows})[:5]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"difficultyLevel": 4, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N06", M, "列表-按难度等级筛选",
      "存在 difficultyLevel=4 的记录", "admin 请求 list?difficultyLevel=4",
      "code=200 且 rows 的 difficultyLevel 全为 4",
      code_of(res) == 200 and len(rows) > 0 and all(r.get("difficultyLevel") == 4 for r in rows),
      "total=%s rows=%d difficulty集合=%s" % (res.get("total"), len(rows),
                                              sorted({r.get("difficultyLevel") for r in rows})[:5]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"isMastered": 0, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N07", M, "列表-按掌握状态筛选",
      "全库未掌握(isMastered=0)共 %s 条" % exp_not_mastered,
      "admin 请求 list?isMastered=0",
      "total=%s 且 rows 的 isMastered 全为 0" % exp_not_mastered,
      code_of(res) == 200 and res.get("total") == exp_not_mastered and len(rows) > 0
      and all(r.get("isMastered") == 0 for r in rows),
      "total=%s rows=%d isMastered集合=%s" % (res.get("total"), len(rows),
                                              sorted({r.get("isMastered") for r in rows})[:5]))

    exp_range = db_one("SELECT COUNT(*) c FROM user_question_marked "
                       "WHERE create_time BETWEEN :b AND :e AND marked_status=1",
                       {"b": "2020-01-01 00:00:00", "e": "2030-12-31 23:59:59"})
    exp_range = (exp_range or {}).get("c")
    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"beginCreateTime": "2020-01-01", "endCreateTime": "2030-12-31",
                           "pageNum": 1, "pageSize": 100})
    T("N08", M, "列表-按斩题时间范围筛选",
      "全库活跃斩题 %s 条 create_time 均落在 2020~2030" % exp_range,
      "admin 请求 list?beginCreateTime=2020-01-01&endCreateTime=2030-12-31",
      "code=200；total=%s（时间条件生效且不丢他人数据）" % exp_range,
      code_of(res) == 200 and res.get("total") == exp_range,
      "total=%s" % res.get("total"))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"pageNum": 1, "pageSize": 2})
    rows = rows_of(res)
    T("N09", M, "列表-分页返回条数受 pageSize 约束",
      "全库活跃斩题 > 2 条", "admin 请求 list?pageSize=2",
      "code=200；rows 条数 <= 2；total 为全量条数",
      code_of(res) == 200 and len(rows) <= 2 and (res.get("total") or 0) > 2,
      "total=%s rows=%d" % (res.get("total"), len(rows)))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    owners = sorted({r.get("userId") for r in rows})
    T("N10", M, "列表-管理员不传 userId 时可看到全部用户的记录",
      "admin 与 user1 均有斩题记录", "admin 请求 list（不传 userId）",
      "rows 中出现 >=2 个不同 userId（后台总览语义）",
      code_of(res) == 200 and len(owners) >= 2,
      "total=%s 涉及用户=%s" % (res.get("total"), owners[:6]))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"userId": uid1, "bankId": bank_id, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N11", M, "列表-组合条件筛选（userId + bankId）",
      "user1 在测试题库下 %s 条" % exp_user1_bank, "admin 请求 list?userId=%s&bankId=%s" % (uid1, bank_id),
      "total=%s 且 rows 同时满足 userId/bankId" % exp_user1_bank,
      code_of(res) == 200 and res.get("total") == exp_user1_bank and len(rows) > 0
      and all(r.get("userId") == uid1 and r.get("bankId") == bank_id for r in rows),
      "total=%s rows=%d" % (res.get("total"), len(rows)))

    # ==================== N2 新增（后台「添加用户斩题」对话框全字段） ====================
    add_body = {
        "userId": uid1, "questionId": q3, "bankId": bank_id,
        "markedType": 2, "difficultyLevel": 4, "isMastered": 1, "markedStatus": 1,
        "errorTimesBeforeMark": 3, "correctTimesBeforeMark": 2, "reviewCount": 5,
        "lastReviewTime": "2026-09-01 10:00:00", "nextReviewTime": "2026-09-20 10:00:00",
        "notes": P + "-后台新增备注", "tags": "难题,重点",
    }
    st, res = call("POST", "/questionMarked/questionMarked", ta, add_body)
    T("N12", M, "新增-管理员代 user1 录入斩题（提交后台表单全字段）",
      "q3=%s 未被斩题" % q3,
      "admin 请求 POST /questionMarked/questionMarked  body 含 userId=%s 与全部表单字段" % uid1,
      "code=200",
      code_of(res) == 200, desc(res, st))

    row3 = db_one("""SELECT user_id, bank_id, marked_type, difficulty_level, is_mastered, marked_status,
                            error_times_before_mark, correct_times_before_mark, review_count,
                            last_review_time, next_review_time, notes, tags
                     FROM user_question_marked WHERE question_id=:q""", {"q": q3})
    T("N13", M, "新增-表单字段全部落库（归属=被代录用户）",
      "N12 已提交全字段",
      "直读 user_question_marked WHERE question_id=q3，逐字段比对",
      "user_id=%s；markedType=2 难度=4 已掌握=1 状态=1；错误次数=3 正确次数=2 复习=5；"
      "lastReviewTime/nextReviewTime 非空；备注/标签一致" % uid1,
      bool(row3) and row3.get("user_id") == uid1
      and row3.get("bank_id") == bank_id and row3.get("marked_type") == 2
      and row3.get("difficulty_level") == 4 and row3.get("is_mastered") == 1
      and row3.get("marked_status") == 1
      and row3.get("error_times_before_mark") == 3 and row3.get("correct_times_before_mark") == 2
      and row3.get("review_count") == 5
      and row3.get("last_review_time") is not None and row3.get("next_review_time") is not None
      and row3.get("notes") == P + "-后台新增备注" and row3.get("tags") == "难题,重点",
      "库中=%s" % row3)

    m3 = db_one("SELECT marked_id FROM user_question_marked WHERE question_id=:q", {"q": q3})
    mid3 = (m3 or {}).get("marked_id")
    st, res = call("GET", "/questionMarked/questionMarked/%s" % mid3, ta)
    d3 = dd(res)
    need_fields = ["markedId", "userId", "questionId", "bankId", "markedType", "difficultyLevel",
                   "errorTimesBeforeMark", "correctTimesBeforeMark", "reviewCount", "isMastered",
                   "markedStatus", "lastReviewTime", "nextReviewTime", "createTime", "notes", "tags"]
    missing = [f for f in need_fields if f not in d3]
    T("N14", M, "详情-后台修改对话框所需字段完整回显",
      "markedId=%s" % mid3, "admin 请求 GET /questionMarked/questionMarked/{markedId}",
      "返回体包含后台列表/表单展示的 16 个字段（缺一即后台显示 0/空）",
      code_of(res) == 200 and not missing,
      "code=%s 缺失字段=%s" % (code_of(res), missing or "无"))

    st, res = call("POST", "/questionMarked/questionMarked", ta, add_body)
    T("N15", M, "新增-同一用户重复斩同一题给出业务提示",
      "user1 在 q3 已有斩题记录", "admin 再次 POST 同一 body",
      "code=400 且提示「已标记」，不应 500",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionMarked/questionMarked", ta,
                   {"userId": uid1, "questionId": 99999999, "bankId": bank_id})
    T("N16", M, "新增-题目不存在时的异常处理",
      "题目 99999999 不存在", "admin POST body={questionId:99999999}",
      "code!=200 且提示「题目不存在」",
      code_of(res) != 200 and "题目不存在" in (res.get("msg") or ""),
      "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ==================== N3 修改（后台「修改用户斩题」对话框） ====================
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q4, "bankId": bank_id})
    m4 = db_one("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                {"u": uid1, "q": q4})
    mid4 = (m4 or {}).get("marked_id")
    upd_body = {
        "markedId": mid4, "markedType": 5, "difficultyLevel": 2, "isMastered": 1, "markedStatus": 1,
        "errorTimesBeforeMark": 9, "correctTimesBeforeMark": 4, "reviewCount": 7,
        "lastReviewTime": "2026-09-05 08:30:00", "nextReviewTime": "2026-09-25 08:30:00",
        "notes": P + "-修改后备注", "tags": "易错,高频",
    }
    st, res = call("PUT", "/questionMarked/questionMarked", t1, upd_body)
    row4 = db_one("""SELECT marked_type, difficulty_level, is_mastered, marked_status,
                            error_times_before_mark, correct_times_before_mark, review_count,
                            last_review_time, next_review_time, notes, tags
                     FROM user_question_marked WHERE marked_id=:m""", {"m": mid4})
    T("N17", M, "修改-本人提交后台表单全字段，字段全部更新",
      "markedId=%s（user1 本人记录）" % mid4,
      "user1 请求 PUT /questionMarked/questionMarked，body 含后台表单全部字段",
      "code=200；库中 markedType=5 难度=2 已掌握=1 状态=1；错误次数=9 正确次数=4 复习=7；"
      "lastReviewTime/nextReviewTime 非空；备注/标签一致",
      code_of(res) == 200 and bool(row4)
      and row4.get("marked_type") == 5 and row4.get("difficulty_level") == 2
      and row4.get("is_mastered") == 1 and row4.get("marked_status") == 1
      and row4.get("error_times_before_mark") == 9 and row4.get("correct_times_before_mark") == 4
      and row4.get("review_count") == 7
      and row4.get("last_review_time") is not None and row4.get("next_review_time") is not None
      and row4.get("notes") == P + "-修改后备注" and row4.get("tags") == "易错,高频",
      "code=%s 库中=%s" % (code_of(res), row4))

    upd_admin = dict(upd_body)
    upd_admin.update({"markedType": 4, "notes": P + "-管理员修改备注", "reviewCount": 11})
    st, res = call("PUT", "/questionMarked/questionMarked", ta, upd_admin)
    row4b = db_one("SELECT marked_type, notes, review_count FROM user_question_marked WHERE marked_id=:m",
                   {"m": mid4})
    T("N18", M, "修改-管理员可修改他人（user1）的斩题记录",
      "markedId=%s 属于 user1；admin 登录" % mid4,
      "admin 请求 PUT /questionMarked/questionMarked  body={markedId:%s,...}" % mid4,
      "code=200；库中 markedType=4、reviewCount=11、备注已更新",
      code_of(res) == 200 and bool(row4b) and row4b.get("marked_type") == 4
      and row4b.get("review_count") == 11 and row4b.get("notes") == P + "-管理员修改备注",
      "code=%s msg=%s 库中=%s" % (code_of(res), res.get("msg"), row4b))

    st, res = call("GET", "/questionMarked/questionMarked/%s" % mid4, ta)
    d4 = dd(res)
    T("N19", M, "详情-管理员可查看他人斩题记录",
      "markedId=%s 属于 user1" % mid4, "admin 请求 GET /questionMarked/questionMarked/{markedId}",
      "code=200 且 userId=%s，reviewCount=11（与库一致）" % uid1,
      code_of(res) == 200 and d4.get("userId") == uid1 and d4.get("reviewCount") == 11,
      "code=%s userId=%s reviewCount=%s" % (code_of(res), d4.get("userId"), d4.get("reviewCount")))

    st, res = call("PUT", "/questionMarked/questionMarked", ta, {"markedId": 99999999, "notes": "x"})
    T("N20", M, "修改-记录不存在时的异常处理",
      "markedId=99999999 不存在", "admin PUT body={markedId:99999999}",
      "code!=200 且提示「斩题记录不存在」",
      code_of(res) != 200 and "不存在" in (res.get("msg") or ""),
      "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ==================== N4 删除（后台列表行内删除 / 批量删除） ====================
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q5, "bankId": bank_id})
    m5 = db_one("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                {"u": uid1, "q": q5})
    mid5 = (m5 or {}).get("marked_id")
    st, res = call("DELETE", "/questionMarked/questionMarked/%s" % mid5, ta)
    gone5 = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE marked_id=:m", {"m": mid5})
    T("N21", M, "删除-管理员删除他人（user1）单条斩题记录",
      "markedId=%s 属于 user1" % mid5, "admin 请求 DELETE /questionMarked/questionMarked/{markedId}",
      "code=200；库中该记录已物理删除",
      code_of(res) == 200 and (gone5 or {}).get("c") == 0,
      "code=%s msg=%s 剩余=%s" % (code_of(res), res.get("msg"), (gone5 or {}).get("c")))

    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q6, "bankId": bank_id})
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q7, "bankId": bank_id})
    ids = db_query("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id IN :i",
                   {"u": uid1, "i": (q6, q7)}) or []
    id_join = ",".join(str(r[0]) for r in ids)
    st, res = call("DELETE", "/questionMarked/questionMarked/%s" % id_join, ta)
    gone67 = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE marked_id IN :i",
                    {"i": tuple(r[0] for r in ids)})
    T("N22", M, "删除-管理员批量删除他人斩题记录（逗号分隔 id）",
      "user1 在 q6/q7 各 1 条，ids=%s" % id_join,
      "admin 请求 DELETE /questionMarked/questionMarked/{ids}",
      "code=200；库中这两条均已删除",
      code_of(res) == 200 and (gone67 or {}).get("c") == 0,
      "code=%s msg=%s 剩余=%s" % (code_of(res), res.get("msg"), (gone67 or {}).get("c")))

    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q8, "bankId": bank_id})
    m8 = db_one("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                {"u": uid1, "q": q8})
    mid8 = (m8 or {}).get("marked_id")
    st, res = call("DELETE", "/questionMarked/questionMarked/%s" % mid8, t2)
    still8 = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE marked_id=:m", {"m": mid8})
    T("N23", M, "删除-普通用户不能删除他人记录（越权拦截）",
      "markedId=%s 属于 user1；user2 登录" % mid8,
      "user2 请求 DELETE /questionMarked/questionMarked/{markedId}",
      "code=403；user1 的记录仍存在",
      code_of(res) == 403 and (still8 or {}).get("c") == 1,
      "code=%s msg=%s 仍存在=%s" % (code_of(res), res.get("msg"), (still8 or {}).get("c")))

    st, res = call("DELETE", "/questionMarked/questionMarked/99999999", ta)
    T("N24", M, "删除-不存在的 id 不应 500",
      "markedId=99999999 不存在", "admin 请求 DELETE /questionMarked/questionMarked/99999999",
      "返回业务响应（200 幂等 或 明确提示），不得 500",
      st != 500 and code_of(res) != 500,
      desc(res, st))

    # ==================== N5 导出 ====================
    st, res = call("POST", "/questionMarked/questionMarked/export", ta)
    T("N25", M, "导出-管理员导出斩题列表为 Excel",
      "admin 已登录", "POST /questionMarked/questionMarked/export",
      "HTTP 200 且返回文件流（非 JSON）",
      st == 200 and is_file(res), desc(res, st))

    st, res = call("POST", "/questionMarked/questionMarked/export", ta,
                   params={"beginCreateTime": "2020-01-01", "endCreateTime": "2030-12-31"})
    rows_in_xlsx = None
    if is_file(res):
        try:
            import io

            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(res), read_only=True)
            ws = wb.active
            rows_in_xlsx = ws.max_row - 1  # 去掉表头
        except Exception as exc:  # noqa: BLE001
            print("    (xlsx 解析失败：%s)" % exc)
    T("N26", M, "导出-带时间范围参数（query）导出内容非空",
      "存在 2020~2030 的斩题记录", "POST export?beginCreateTime=2020-01-01&endCreateTime=2030-12-31",
      "HTTP 200；xlsx 数据行数 > 0",
      st == 200 and is_file(res) and (rows_in_xlsx is None or rows_in_xlsx > 0),
      "%s 数据行=%s" % (desc(res, st), rows_in_xlsx))

    # 修复点：前端 utils/request.download 已把筛选参数从 form-urlencoded 请求体改拼到 URL 上，
    # 后端 export 的筛选（时间范围 / userId / 题库 / 类型…）因此真正生效。
    st, res = call("POST", "/questionMarked/questionMarked/export", ta,
                   params={"beginCreateTime": "1990-01-01", "endCreateTime": "1990-01-02"})
    n_empty_rows = None
    if is_file(res):
        try:
            import io

            from openpyxl import load_workbook

            n_empty_rows = load_workbook(io.BytesIO(res), read_only=True).active.max_row - 1
        except Exception:  # noqa: BLE001
            pass
    T("N36", M, "导出-筛选条件真正生效（空区间应导出 0 行）",
      "1990-01-01~1990-01-02 区间内无斩题记录",
      "POST export?beginCreateTime=1990-01-01&endCreateTime=1990-01-02"
      "（等价于修复后 utils/request.download 拼出的 URL）",
      "HTTP 200 且 xlsx 数据行=0（页面搜索条件应带进导出）",
      st == 200 and is_file(res) and n_empty_rows == 0,
      "%s 数据行=%s" % (desc(res, st), n_empty_rows))

    st, res = call("POST", "/questionMarked/questionMarked/export", ta,
                   params={"userId": uid1})
    cur_user1 = db_one("SELECT COUNT(*) c FROM user_question_marked "
                       "WHERE user_id=:u AND marked_status=1", {"u": uid1})
    exp_cur_user1 = (cur_user1 or {}).get("c")
    n_user_rows = None
    if is_file(res):
        try:
            import io

            from openpyxl import load_workbook

            n_user_rows = load_workbook(io.BytesIO(res), read_only=True).active.max_row - 1
        except Exception:  # noqa: BLE001
            pass
    T("N38", M, "导出-管理员可按 userId 导出指定用户",
      "user1 当前活跃斩题 %s 条" % exp_cur_user1,
      "admin POST export?userId=%s" % uid1,
      "HTTP 200；xlsx 数据行数 = user1 活跃斩题数",
      st == 200 and is_file(res) and n_user_rows == exp_cur_user1,
      "数据行=%s 期望=%s" % (n_user_rows, exp_cur_user1))

    # ==================== N6 权限（前台角色误用后台接口） ====================
    st, res = call("GET", "/questionMarked/questionMarked/list", t2,
                   params={"pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N27", M, "权限-普通用户列表只能看自己的记录",
      "user2 自己有 %s 条斩题，且 user1 也有记录" % exp_user2_total,
      "user2 请求 list?pageSize=100",
      "total=%s；rows 的 userId 全为 %s（不得出现 user1 的记录）" % (exp_user2_total, uid2),
      code_of(res) == 200 and res.get("total") == exp_user2_total and len(rows) > 0
      and all(r.get("userId") == uid2 for r in rows),
      "total=%s rows=%d userId集合=%s" % (res.get("total"), len(rows),
                                          sorted({r.get("userId") for r in rows})[:5]))

    st, res = call("POST", "/questionMarked/questionMarked", t1,
                   {"userId": uid2, "questionId": q10, "bankId": bank_id})
    p1_row = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                    {"u": uid1, "q": q10})
    p2_row = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                    {"u": uid2, "q": q10})
    T("N28", M, "权限-普通用户不能代他人新增斩题记录",
      "user1 登录，body 里 userId=%s（q10 双方均无记录）" % uid2,
      "user1 请求 POST /questionMarked/questionMarked  body={userId:user2,questionId:q10}",
      "code=403；user2 名下不新增记录，user1 名下也不应被悄悄写入",
      code_of(res) == 403 and (p2_row or {}).get("c") == 0 and (p1_row or {}).get("c") == 0,
      "code=%s msg=%s；user2记录=%s user1记录=%s"
      % (code_of(res), res.get("msg"), (p2_row or {}).get("c"), (p1_row or {}).get("c")))

    st, res = call("GET", "/questionMarked/questionMarked/%s" % mid4, t2)
    T("N29", M, "权限-普通用户不能查看他人斩题详情",
      "markedId=%s 属于 user1" % mid4, "user2 请求 GET /questionMarked/questionMarked/{markedId}",
      "code=403",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionMarked/questionMarked/list", None, params={"pageNum": 1})
    T("N30", M, "权限-未登录访问被拒绝",
      "不带 token", "GET /questionMarked/questionMarked/list",
      "HTTP 401 或 code=401",
      st == 401 or code_of(res) == 401, "HTTP %s code=%s" % (st, code_of(res)))

    # ==================== N7 前端契约（模拟后台页面真实请求/字段依赖） ====================
    page_params = {"pageNum": 1, "pageSize": 10, "userId": uid1, "questionId": q2,
                   "bankId": bank_id, "markedType": 3, "difficultyLevel": 4, "isMastered": 1}
    st, res = call("GET", "/questionMarked/questionMarked/list", ta, params=page_params)
    rows = rows_of(res)
    T("N31", M, "前端契约-后台列表页 8 个查询条件同时生效",
      "user1 在测试题库 q2 上的一条筛选样本（类型3/难度4/已掌握）",
      "按后台 index.vue 的 queryParams 原样请求：userId+questionId+bankId+markedType+difficultyLevel+isMastered",
      "命中 1 条且各字段与条件一致",
      code_of(res) == 200 and len(rows) == 1
      and rows[0].get("userId") == uid1 and rows[0].get("questionId") == q2
      and rows[0].get("bankId") == bank_id and rows[0].get("markedType") == 3
      and rows[0].get("difficultyLevel") == 4 and rows[0].get("isMastered") == 1,
      "命中 %d 条" % len(rows))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"bankId": bank_id, "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    sample = rows[0] if rows else {}
    table_cols = ["markedId", "userId", "questionId", "bankId", "markedType", "difficultyLevel",
                  "errorTimesBeforeMark", "isMastered", "reviewCount", "createTime",
                  "lastReviewTime", "notes", "tags"]
    missing_cols = [c for c in table_cols if c not in sample]
    T("N32", M, "前端契约-列表返回字段覆盖后台表格所有列",
      "测试题库下存在斩题记录", "GET list?bankId=... 后比对 index.vue 表格 el-table-column 的 prop",
      "返回字段包含表格全部 13 个 prop（缺失即该列恒显示 0/-）",
      code_of(res) == 200 and bool(rows) and not missing_cols,
      "缺失字段=%s" % (missing_cols or "无"))

    st, res = call("GET", "/questionMarked/questionMarked/list", ta,
                   params={"notes": P + "-筛选样本", "pageNum": 1, "pageSize": 100})
    rows = rows_of(res)
    T("N33", M, "列表-按备注关键字筛选",
      "存在备注含「%s-筛选样本」的记录" % P, "admin 请求 list?notes=%s-筛选样本" % P,
      "code=200；命中且 rows 的 notes 均命中关键字",
      code_of(res) == 200 and len(rows) > 0
      and all((P + "-筛选样本") in (r.get("notes") or "") for r in rows),
      "命中 %d 条" % len(rows))

    # ---- 后台自己操作自己记录（基本 CRUD 可用性，与跨用户能力区分开）----
    call("POST", "/questionMarked/questionMarked", ta, {"questionId": q10, "bankId": bank_id})
    ma = db_one("SELECT marked_id FROM user_question_marked WHERE user_id=:u AND question_id=:q",
                {"u": uid_admin, "q": q10})
    mid_a = (ma or {}).get("marked_id")
    st, res = call("PUT", "/questionMarked/questionMarked", ta,
                   {"markedId": mid_a, "notes": P + "-管理员自己的备注", "markedType": 2})
    ra = db_one("SELECT notes, marked_type FROM user_question_marked WHERE marked_id=:m", {"m": mid_a})
    T("N34", M, "修改-管理员修改本人记录（基础 CRUD 可用性）",
      "admin 在 q10 有自己的记录 markedId=%s" % mid_a,
      "admin PUT /questionMarked/questionMarked  body={markedId,notes,markedType:2}",
      "code=200；库中备注与斩题类型已更新",
      code_of(res) == 200 and (ra or {}).get("notes") == P + "-管理员自己的备注"
      and (ra or {}).get("marked_type") == 2,
      "code=%s 库中=%s" % (code_of(res), ra))

    # ---- 业务闭环：后台代录后，用户前台「我的斩题」应立即可见 ----
    st, res = call("GET", "/questionMarked/questionMarked/all", t1)
    lst1 = dl(res)
    hit3 = [x for x in lst1 if x.get("questionId") == q3]
    T("N35", M, "业务闭环-后台代录后用户前台「我的斩题」立即可见",
      "N12 已由后台为 user1 录入 q3 的斩题",
      "user1 请求 GET /questionMarked/questionMarked/all 并查找 q3",
      "user1 的斩题列表包含 q3（后台代录数据落到被代录用户名下）",
      len(hit3) == 1, "user1 列表 %d 条，命中 q3=%d 条" % (len(lst1), len(hit3)))

    # ==================== N8 清理 ====================
    st, res = call("DELETE", "/questionBank/questionBank/%s" % bank_id, t1)
    st2, res2 = call("GET", "/questionBank/questionBank/%s" % bank_id, t1)
    T("N39", M, "清理-删除临时题库（级联清理测试斩题数据）",
      "测试题库 bank=%s" % bank_id, "DELETE /questionBank/questionBank/{bank_id} 后查详情",
      "code=200；删除后详情不可见",
      code_of(res) == 200 and code_of(res2) != 200,
      "删除=%s 详情code=%s" % (code_of(res), code_of(res2)))

    q_t = tuple([q for q in (q1, q2, q3, q4, q5, q6, q7, q8, q9, q10) if q])
    db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM note_question WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM question_sub WHERE main_id IN :i", {"i": q_t})
    db_exec("DELETE FROM question_main WHERE id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_bank_favorite WHERE bank_id IN :i", {"i": (bank_id,)})
    db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": (bank_id,)})

    left_marked = db_one("SELECT COUNT(*) c FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
    left_q = db_one("SELECT COUNT(*) c FROM question_main WHERE id IN :i", {"i": q_t})
    left_bank = db_one("SELECT COUNT(*) c FROM question_bank WHERE id=:i", {"i": bank_id})
    T("N40", M, "清理-无测试数据残留（不污染演示数据）",
      "清理完成", "直连库核对测试题目/题库/斩题记录",
      "题目=0 题库=0 斩题记录=0",
      all((x or {}).get("c") == 0 for x in (left_marked, left_q, left_bank)),
      "斩题残留=%s 题目残留=%s 题库残留=%s"
      % ((left_marked or {}).get("c"), (left_q or {}).get("c"), (left_bank or {}).get("c")))

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
            "prefix": P, "uid_admin": uid_admin, "uid1": uid1, "uid2": uid2, "rows": ROWS,
            "cleanup": {"bank_ids": [bank_id]},
        }, f, ensure_ascii=False, indent=2)
    print("结果已写入", OUT)


if __name__ == "__main__":
    main()
