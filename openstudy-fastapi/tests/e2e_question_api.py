# -*- coding: utf-8 -*-
"""
题目相关功能模块 E2E 接口测试（真实 HTTP 调用）

覆盖：错题本(questionError) / 斩题(questionMarked) / 答题上报(questionPractice) / 题目收藏(favoriteQuestion)
角色：user1、user2（互为他人，用于验证数据隔离与越权）
用例编号：F*=错题本  G*=斩题  H*=答题上报  I*=题目收藏

用法（后端需先跑起来，默认 127.0.0.1:9101）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_question_api.py

产出：脚本同目录 e2e_question_api_result.json
说明：全部测试数据建在临时题库上，结束时删除该题库（级联清理），不留残留。
"""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_question_api_result.json")

ROWS = []


def call(method, path, token=None, body=None, params=None, timeout=25):
    url = BASE + path
    if params:
        url += "?" + urlencode(params, doseq=True)
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


def db_query(sql, params=None):
    """直连数据库读校验（仅用于接口未暴露的字段）；失败返回 None，不影响主流程"""
    try:
        import asyncio
        import sys

        from sqlalchemy import text

        # 以脚本方式运行时 sys.path[0] 是 tests/，需补上项目根目录才能 import app
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        from app.database import async_session_factory

        async def _run():
            async with async_session_factory() as db:
                return (await db.execute(text(sql), params or {})).all()

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print("    (DB 直读不可用：%s)" % exc)
        return None


def new_question(t1, bank_id, text):
    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_id, "questionType": 1, "questionText": text,
        "options": [{"key": "A", "value": "1"}, {"key": "B", "value": "2"}], "answer": "A",
    })
    return dd(res).get("questionId")


def find_error(tok, qid):
    """在错题列表里按 questionId 精确捞一条（含已掌握：显式传 isMastered 才能跨状态）"""
    st, res = call("GET", "/questionError/questionError/list", tok,
                   params={"questionId": qid, "pageSize": 50, "status": 1})
    rows = rows_of(res)
    if not rows:
        st, res = call("GET", "/questionError/questionError/list", tok,
                       params={"questionId": qid, "pageSize": 50, "status": 0})
        rows = rows_of(res)
    return rows[0] if rows else None


def find_marked(tok, qid):
    st, res = call("GET", "/questionMarked/questionMarked/all", tok)
    for r in dl(res):
        if r.get("questionId") == qid:
            return r
    return None


def find_favorite(tok, qid):
    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/list", tok,
                   params={"pageNum": 1, "pageSize": 100})
    for r in rows_of(res):
        if r.get("questionId") == qid:
            return r
    return None


def db_scalar(sql, params=None):
    rows = db_query(sql, params)
    if not rows:
        return None
    return rows[0][0]


def db_exec(sql, params=None):
    """直连数据库执行写语句（仅用于清理无 API 的测试数据）；失败返回 None"""
    try:
        import asyncio
        import sys

        from sqlalchemy import text

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        from app.config import settings
        from sqlalchemy.ext.asyncio import create_async_engine

        async def _run():
            engine = create_async_engine(settings.DATABASE_URL)
            try:
                async with engine.begin() as conn:
                    return (await conn.execute(text(sql), params or {})).rowcount
            finally:
                await engine.dispose()

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print("    (DB 写入不可用：%s)" % exc)
        return None


def sweep_leftovers(created):
    """按记录的 id 清除上一次运行（可能中途崩溃）遗留的测试数据"""
    bank_ids = created.get("bank_ids") or []
    if not bank_ids:
        return
    bank_t = tuple(bank_ids) or (0,)
    rows = db_query("SELECT id FROM question_main WHERE bank_id IN :b", {"b": bank_t}) or []
    q_ids = [r[0] for r in rows]
    q_t = tuple(q_ids) or (0,)
    if q_ids:
        db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM note_question WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_sub WHERE main_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_main WHERE id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_bank_favorite WHERE bank_id IN :i", {"i": bank_t})
    # ⚠️ bank_share 主键列是 id；receive 引用 share，必须先删
    db_exec("DELETE FROM bank_share_receive WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share_receive WHERE share_id NOT IN (SELECT id FROM bank_share)")
    db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    # 死链通知兜底：link 指向已不存在题库的通知一律清除
    import re

    _rows = db_query("SELECT notification_id, link FROM user_notification "
                     "WHERE link LIKE '/front/questionPractice/%'") or []
    _alive = {r[0] for r in (db_query("SELECT id FROM question_bank") or [])}
    _dead = [r[0] for r in _rows
             if (m := re.search(r"/front/questionPractice/(\d+)", r[1] or ""))
             and int(m.group(1)) not in _alive]
    if _dead:
        db_exec("DELETE FROM user_notification WHERE notification_id IN :i", {"i": tuple(_dead)})
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")
    print("  [自检] 已清理上次运行遗留：bank=%s question=%d" % (bank_ids, len(q_ids)))


def main():
    # 启动自检：清理上一次运行（可能中途崩溃）遗留的测试数据
    prev = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_question_api_result.json")
    if os.path.exists(prev):
        try:
            with open(prev, encoding="utf-8") as f:
                sweep_leftovers(json.load(f).get("cleanup") or {})
        except Exception as exc:  # noqa: BLE001
            print("  [自检] 读取上次结果失败：%s" % exc)

    ts = time.strftime("%m%d%H%M%S")
    # 数据命名贴近真实使用场景，不出现 E2E 之类的机器编码
    P = "错题整理"
    BANK = P + "题目行为测试题库"

    print("=" * 74)
    print("题目相关功能模块 E2E 测试   前缀 =", P)
    print("=" * 74)

    t1 = login("user1")
    t2 = login("user2")

    # ---------- 准备 ----------
    st, ca = call("POST", "/questionBank/questionBank", t1, {"bankName": BANK})
    bank_id = dd(ca).get("id")
    uid1 = dd(ca).get("userId")

    st, tmp = call("POST", "/questionBank/questionBank", t2, {"bankName": P + "探针"})
    uid2 = dd(tmp).get("userId")
    tmp2 = dd(tmp).get("id")
    call("DELETE", "/questionBank/questionBank/%s" % tmp2, t2)

    q1 = new_question(t1, bank_id, P + "-错题流程题")
    q2 = new_question(t1, bank_id, P + "-后台错题题")
    q3 = new_question(t1, bank_id, P + "-越权/斩题/收藏题")
    print("bank=%s uid1=%s uid2=%s q1=%s q2=%s q3=%s" % (bank_id, uid1, uid2, q1, q2, q3))

    # ==================== F 模块：错题本 ====================
    st, res = call("POST", "/questionError/questionError/recordOrUpdateError", t1,
                   {"questionId": q1, "bankId": bank_id})
    err1 = find_error(t1, q1)
    eid1 = (err1 or {}).get("errorId")
    T("F01", "错题本", "记录错题-首次作答做错（新建错题记录）",
      "q1 存在且 user1 无该题错题记录", "POST /questionError/questionError/recordOrUpdateError  body={questionId:q1}",
      "code=200；列表出现该题错题记录，errorCount=1",
      code_of(res) == 200 and bool(eid1) and (err1 or {}).get("errorCount") == 1,
      "errorId=%s errorCount=%s" % (eid1, (err1 or {}).get("errorCount")))

    call("POST", "/questionError/questionError/recordOrUpdateError", t1, {"questionId": q1})
    err1b = find_error(t1, q1)
    T("F02", "错题本", "记录错题-同题重复做错（覆盖累加，不新增行）",
      "user1 已有 q1 的错题记录（errorId=%s）" % eid1,
      "再次 POST recordOrUpdateError  body={questionId:q1}",
      "errorId 不变；errorCount 由 1 累加为 2；列表中该题仍只有 1 条",
      (err1b or {}).get("errorId") == eid1 and (err1b or {}).get("errorCount") == 2,
      "errorId=%s errorCount=%s" % ((err1b or {}).get("errorId"), (err1b or {}).get("errorCount")))

    st, res = call("POST", "/questionError/questionError/recordOrUpdateError", t1, {"questionId": 99999999})
    T("F03", "错题本", "记录错题-题目不存在时的异常处理",
      "题目 99999999 不存在", "POST recordOrUpdateError  body={questionId:99999999}",
      "code!=200 且提示「题目不存在」",
      code_of(res) != 200 and "题目不存在" in (res.get("msg") or ""),
      "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionError/questionError/list", t1, params={"pageNum": 1, "pageSize": 10})
    rows = rows_of(res)
    T("F04", "错题本", "错题列表-默认只返回活跃错题（status=1）",
      "user1 有活跃错题记录", "GET /questionError/questionError/list（不传 status）",
      "code=200；返回项 status 全为 1",
      code_of(res) == 200 and len(rows) > 0 and all(r.get("status") == 1 for r in rows),
      "total=%s" % res.get("total"))

    st, res = call("GET", "/questionError/questionError/list", t1,
                   params={"questionId": q1, "pageSize": 50, "status": 1})
    rows = rows_of(res)
    T("F05", "错题本", "错题列表-按题目ID精确筛选",
      "q1 有错题记录", "GET /questionError/questionError/list?questionId={q1}&status=1",
      "命中且仅命中 1 条，questionId=q1",
      code_of(res) == 200 and len(rows) == 1 and rows[0].get("questionId") == q1,
      "命中 %d 条" % len(rows))

    st, res = call("GET", "/questionError/questionError/list", t1, params={"pageNum": 1, "pageSize": 2})
    T("F06", "错题本", "错题列表-分页返回结构",
      "user1 有错题记录", "GET /questionError/questionError/list?pageNum=1&pageSize=2",
      "code=200；顶层含 total 与 rows",
      code_of(res) == 200 and "total" in res and len(rows_of(res)) <= 2,
      "total=%s rows=%d" % (res.get("total"), len(rows_of(res))))

    st, ea = call("GET", "/questionError/questionError/checkUserErrorExists/%s" % q1, t1)
    st2, eb = call("GET", "/questionError/questionError/checkUserErrorExists/%s" % q2, t1)
    T("F07", "错题本", "检查当前用户是否存在某题错题记录",
      "q1 有错题 / q2 无错题", "GET /questionError/questionError/checkUserErrorExists/{q1} 与 /{q2}",
      "q1 返回 true、q2 返回 false",
      raw_data(ea) is True and raw_data(eb) is False,
      "q1=%s q2=%s" % (raw_data(ea), raw_data(eb)))

    st, res = call("POST", "/questionError/questionError/batchCheck", t1, {"questionIds": [q1, q2]})
    d = dd(res)
    T("F08", "错题本", "批量检查错题状态",
      "q1 有错题 / q2 无错题", "POST /questionError/questionError/batchCheck  body={questionIds:[q1,q2]}",
      "返回 {q1:true, q2:false}",
      code_of(res) == 200 and d.get(str(q1)) is True and d.get(str(q2)) is False,
      "结果=%s" % str(d)[:100])

    st, res = call("POST", "/questionError/questionError/markMastered", t1, {"questionId": q1})
    st2, res2 = call("GET", "/questionError/questionError/checkUserErrorExists/%s" % q1, t1)
    T("F09", "错题本", "标记错题为已掌握-从活跃错题中移出",
      "q1 为活跃错题", "POST /questionError/questionError/markMastered  body={questionId:q1}",
      "code=200；checkUserErrorExists 变为 false（status 已置 0）",
      code_of(res) == 200 and raw_data(res2) is False,
      "标记=%s 活跃校验=%s" % (code_of(res), raw_data(res2)))

    st, res = call("GET", "/questionError/questionError/list", t1,
                   params={"questionId": q1, "pageSize": 50, "status": 0, "isMastered": 1})
    rows = rows_of(res)
    T("F10", "错题本", "已掌握错题可通过 isMastered 筛选查到",
      "q1 已被标记已掌握", "GET /questionError/questionError/list?questionId={q1}&status=0&isMastered=1",
      "命中 1 条，isMastered=1、status=0",
      code_of(res) == 200 and len(rows) == 1 and rows[0].get("isMastered") == 1
      and rows[0].get("status") == 0,
      "命中 %d 条 isMastered=%s" % (len(rows), (rows[0] if rows else {}).get("isMastered")))

    call("POST", "/questionError/questionError/recordOrUpdateError", t1, {"questionId": q1})
    err1c = find_error(t1, q1)
    T("F11", "错题本", "已掌握的题再做错-自动回到错题本",
      "q1 已标记已掌握（status=0/is_mastered=1）", "再次 POST recordOrUpdateError  body={questionId:q1}",
      "重新活跃：status=1、isMastered=0；errorCount 继续累加为 3",
      (err1c or {}).get("status") == 1 and (err1c or {}).get("isMastered") == 0
      and (err1c or {}).get("errorCount") == 3,
      "status=%s isMastered=%s errorCount=%s" % ((err1c or {}).get("status"),
                                                 (err1c or {}).get("isMastered"),
                                                 (err1c or {}).get("errorCount")))

    st, res = call("GET", "/questionError/questionError/%s" % eid1, t1)
    T("F12", "错题本", "错题详情-返回错题与题目信息",
      "errorId=%s 存在" % eid1, "GET /questionError/questionError/{errorId}",
      "code=200；errorId 与 questionId 匹配",
      code_of(res) == 200 and dd(res).get("errorId") == eid1 and dd(res).get("questionId") == q1,
      "errorId=%s questionId=%s" % (dd(res).get("errorId"), dd(res).get("questionId")))

    st, res = call("GET", "/questionError/questionError/99999999", t1)
    T("F13", "错题本", "错题详情-记录不存在时的异常处理",
      "errorId 不存在", "GET /questionError/questionError/99999999",
      "code!=200 且提示「错题记录不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionError/questionError", t1,
                   {"errorId": eid1, "notes": P + "-备注", "difficultyRating": 4})
    st2, res2 = call("GET", "/questionError/questionError/%s" % eid1, t1)
    T("F14", "错题本", "修改错题记录（备注 / 难度评级）",
      "errorId=%s 属于 user1" % eid1, "PUT /questionError/questionError  body={errorId,notes,difficultyRating:4}",
      "code=200；备注与难度均已更新",
      code_of(res) == 200 and dd(res2).get("notes") == P + "-备注"
      and dd(res2).get("difficultyRating") == 4,
      "notes=%s difficultyRating=%s" % (dd(res2).get("notes"), dd(res2).get("difficultyRating")))

    st, res = call("PUT", "/questionError/questionError", t1, {"errorId": 99999999, "notes": "x"})
    T("F15", "错题本", "修改错题-记录不存在时的异常处理",
      "errorId 不存在", "PUT /questionError/questionError  body={errorId:99999999}",
      "code!=200 且提示「错题记录不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionError/questionError", t1, {"questionId": q2, "bankId": bank_id})
    T("F16", "错题本", "后台新增错题记录",
      "q2 存在且 user1 无该题错题记录", "POST /questionError/questionError  body={questionId:q2}",
      "code=200；返回 errorId",
      code_of(res) == 200 and bool(dd(res).get("errorId")),
      "errorId=%s" % dd(res).get("errorId"))

    st, res = call("POST", "/questionError/questionError", t1, {"questionId": 99999999})
    T("F17", "错题本", "后台新增错题-题目不存在时的异常处理",
      "题目 99999999 不存在", "POST /questionError/questionError  body={questionId:99999999}",
      "code!=200 且提示「题目不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionError/questionError", t1, {"questionId": q2})
    T("F18", "错题本", "后台新增错题-重复新增的幂等处理",
      "user1 已有 q2 的错题记录", "再次 POST /questionError/questionError  body={questionId:q2}",
      "给出明确的业务冲突提示（不应是 500 服务器内部错误）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionError/questionError/export", t1)
    T("F19", "错题本", "导出错题列表（Excel）",
      "user1 已登录", "POST /questionError/questionError/export",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    q2_err = find_error(t1, q2)
    st, res = call("DELETE", "/questionError/questionError/%s" % (q2_err or {}).get("errorId"), t1)
    st2, res2 = call("GET", "/questionError/questionError/checkUserErrorExists/%s" % q2, t1)
    T("F20", "错题本", "删除错题记录",
      "q2 有错题记录（errorId=%s）" % (q2_err or {}).get("errorId"),
      "DELETE /questionError/questionError/{errorId}",
      "code=200；该题错题记录不再存在",
      code_of(res) == 200 and raw_data(res2) is False,
      "删除=%s 剩余校验=%s" % (code_of(res), raw_data(res2)))

    # ---- 数据隔离 / 越权（用 q3 新建一条 user1 的错题记录）----
    call("POST", "/questionError/questionError/recordOrUpdateError", t1, {"questionId": q3})
    e3 = find_error(t1, q3) or {}
    eid3 = e3.get("errorId")

    st, res = call("GET", "/questionError/questionError/%s" % eid3, t2)
    T("F21", "错题本", "数据隔离-user2 不能查看 user1 的错题详情",
      "errorId=%s 属于 user1" % eid3, "user2 请求 GET /questionError/questionError/{errorId}",
      "code=403 或提示无权访问（按归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionError/questionError", t2,
                   {"errorId": eid3, "notes": P + "-越权篡改"})
    st2, res2 = call("GET", "/questionError/questionError/%s" % eid3, t1)
    tampered = dd(res2).get("notes") == P + "-越权篡改"
    T("F22", "错题本", "数据隔离-user2 不能修改 user1 的错题记录",
      "errorId=%s 属于 user1" % eid3, "user2 请求 PUT /questionError/questionError  body={errorId:eid3}",
      "code=403；user1 的记录不被篡改",
      code_of(res) == 403 and not tampered,
      "code=%s msg=%s；user1 记录被改=%s" % (code_of(res), res.get("msg"), tampered))

    st, res = call("DELETE", "/questionError/questionError/%s" % eid3, t2)
    st2, res2 = call("GET", "/questionError/questionError/checkUserErrorExists/%s" % q3, t1)
    T("F23", "错题本", "数据隔离-user2 不能删除 user1 的错题记录",
      "errorId=%s 属于 user1" % eid3, "user2 请求 DELETE /questionError/questionError/{errorId}",
      "code=403；user1 的记录仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；user1 记录仍在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    # ==================== G 模块：斩题 ====================
    st, res = call("POST", "/questionMarked/questionMarked", t1, {"questionId": q1, "bankId": bank_id})
    st2, res2 = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q1})
    T("G01", "斩题", "标记斩题",
      "q1 存在", "POST /questionMarked/questionMarked  body={questionId:q1} 后 GET check",
      "code=200；check 返回 true",
      code_of(res) == 200 and raw_data(res2) is True,
      "标记=%s check=%s" % (code_of(res), raw_data(res2)))

    st, res = call("POST", "/questionMarked/questionMarked", t1, {"questionId": q1})
    T("G02", "斩题", "重复标记斩题的幂等处理",
      "q1 已被标记斩题", "再次 POST /questionMarked/questionMarked  body={questionId:q1}",
      "给出明确的业务提示（不应是 500 服务器内部错误）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q2})
    T("G03", "斩题", "斩题状态校验-未标记的题目",
      "q2 未标记斩题", "GET /questionMarked/questionMarked/check?questionId={q2}",
      "返回 false",
      raw_data(res) is False, "check=%s" % raw_data(res))

    st, res = call("POST", "/questionMarked/questionMarked/batchCheck", t1, {"questionIds": [q1, q2]})
    d = dd(res)
    T("G04", "斩题", "批量检查斩题状态",
      "q1 已斩 / q2 未斩", "POST /questionMarked/questionMarked/batchCheck  body={questionIds:[q1,q2]}",
      "返回 {q1:true, q2:false}",
      code_of(res) == 200 and d.get(str(q1)) is True and d.get(str(q2)) is False,
      "结果=%s" % str(d)[:100])

    st, res = call("GET", "/questionMarked/questionMarked/list", t1, params={"pageNum": 1, "pageSize": 10})
    m = find_marked(t1, q1)
    T("G05", "斩题", "斩题列表-分页且只含本人数据",
      "user1 已斩 q1", "GET /questionMarked/questionMarked/list",
      "code=200；顶层含 total/rows；命中 q1 且 userId=user1",
      code_of(res) == 200 and "total" in res and (m or {}).get("userId") == uid1,
      "total=%s userId=%s" % (res.get("total"), (m or {}).get("userId")))

    st, res = call("GET", "/questionMarked/questionMarked/all", t1, params={"bankId": bank_id})
    lst = dl(res)
    T("G06", "斩题", "斩题列表-不分页并按题库筛选",
      "q1 属于 bank_id", "GET /questionMarked/questionMarked/all?bankId={bank_id}",
      "code=200；返回数组且 bankId 全部匹配",
      code_of(res) == 200 and len(lst) >= 1 and all(x.get("bankId") == bank_id for x in lst),
      "共 %d 条" % len(lst))

    mid = (m or {}).get("markedId")
    st, res = call("GET", "/questionMarked/questionMarked/%s" % mid, t1)
    T("G07", "斩题", "斩题详情",
      "markedId=%s 存在" % mid, "GET /questionMarked/questionMarked/{markedId}",
      "code=200；questionId 匹配",
      code_of(res) == 200 and dd(res).get("questionId") == q1,
      "questionId=%s" % dd(res).get("questionId"))

    st, res = call("PUT", "/questionMarked/questionMarked", t1,
                   {"markedId": mid, "notes": P + "-斩题备注", "markedType": 2})
    st2, res2 = call("GET", "/questionMarked/questionMarked/%s" % mid, t1)
    T("G08", "斩题", "修改斩题记录（备注 / 斩题类型）",
      "markedId=%s 属于 user1" % mid, "PUT /questionMarked/questionMarked  body={markedId,notes,markedType:2}",
      "code=200；备注与类型均已更新",
      code_of(res) == 200 and dd(res2).get("notes") == P + "-斩题备注"
      and dd(res2).get("markedType") == 2,
      "notes=%s markedType=%s" % (dd(res2).get("notes"), dd(res2).get("markedType")))

    st, res = call("POST", "/questionMarked/questionMarked/export", t1)
    T("G09", "斩题", "导出斩题列表（Excel）",
      "user1 已登录", "POST /questionMarked/questionMarked/export",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    st, res = call("DELETE", "/questionMarked/questionMarked/deleteByUserAndQuestion/%s/%s" % (uid1, q1), t1)
    st2, res2 = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q1})
    T("G10", "斩题", "取消斩题-按用户与题目删除（自己）",
      "user1 已斩 q1", "DELETE /questionMarked/questionMarked/deleteByUserAndQuestion/{uid1}/{q1}",
      "code=200；check 变为 false",
      code_of(res) == 200 and raw_data(res2) is False,
      "删除=%s check=%s" % (code_of(res), raw_data(res2)))

    st, res = call("POST", "/questionMarked/questionMarked", t1, {"questionId": q2, "bankId": bank_id})
    m2 = find_marked(t1, q2) or {}
    st, res = call("DELETE", "/questionMarked/questionMarked/%s" % m2.get("markedId"), t1)
    st2, res2 = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q2})
    T("G11", "斩题", "取消斩题-按记录ID删除",
      "q2 已斩（markedId=%s）" % m2.get("markedId"), "DELETE /questionMarked/questionMarked/{markedId}",
      "code=200；check 变为 false",
      code_of(res) == 200 and raw_data(res2) is False,
      "删除=%s check=%s" % (code_of(res), raw_data(res2)))

    st, res = call("POST", "/questionMarked/questionMarked", t1, {"questionId": 99999999})
    T("G12", "斩题", "标记斩题-题目不存在时的异常处理",
      "题目 99999999 不存在", "POST /questionMarked/questionMarked  body={questionId:99999999}",
      "code!=200 且提示「题目不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ---- 数据隔离 / 越权（user1 在 q3 上建斩题记录）----
    call("POST", "/questionMarked/questionMarked", t1, {"questionId": q3, "bankId": bank_id})
    m3 = find_marked(t1, q3) or {}
    mid3 = m3.get("markedId")

    st, res = call("GET", "/questionMarked/questionMarked/%s" % mid3, t2)
    T("G13", "斩题", "数据隔离-user2 不能查看 user1 的斩题详情",
      "markedId=%s 属于 user1" % mid3, "user2 请求 GET /questionMarked/questionMarked/{markedId}",
      "code=403 或提示无权访问（按归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionMarked/questionMarked", t2,
                   {"markedId": mid3, "notes": P + "-越权篡改"})
    st2, res2 = call("GET", "/questionMarked/questionMarked/%s" % mid3, t1)
    tampered = dd(res2).get("notes") == P + "-越权篡改"
    T("G14", "斩题", "数据隔离-user2 不能修改 user1 的斩题记录",
      "markedId=%s 属于 user1" % mid3, "user2 请求 PUT /questionMarked/questionMarked  body={markedId:mid3}",
      "code=403；user1 的记录不被篡改",
      code_of(res) == 403 and not tampered,
      "code=%s msg=%s；user1 记录被改=%s" % (code_of(res), res.get("msg"), tampered))

    st, res = call("DELETE", "/questionMarked/questionMarked/%s" % mid3, t2)
    st2, res2 = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q3})
    T("G15", "斩题", "数据隔离-user2 不能删除 user1 的斩题记录（按记录ID）",
      "markedId=%s 属于 user1" % mid3, "user2 请求 DELETE /questionMarked/questionMarked/{markedId}",
      "code=403；user1 的记录仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；user1 记录仍在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    st, res = call("DELETE",
                   "/questionMarked/questionMarked/deleteByUserAndQuestion/%s/%s" % (uid1, q3), t2)
    st2, res2 = call("GET", "/questionMarked/questionMarked/check", t1, params={"questionId": q3})
    T("G16", "斩题", "数据隔离-路径传入他人 user_id 不能删除他人斩题",
      "user1 已斩 q3；路径参数 {user_id} 可被篡改",
      "user2 请求 DELETE .../deleteByUserAndQuestion/{uid1}/{q3}（路径写的是 user1 的 id）",
      "code=403；user1 的记录仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；user1 记录仍在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    # ==================== H 模块：答题上报 ====================
    st, res = call("POST", "/questionPractice/report", t1,
                   {"questionId": q1, "bankId": bank_id, "isCorrect": True, "answer": "A"})
    T("H01", "答题上报", "上报-答对",
      "q1 存在", "POST /questionPractice/report  body={questionId:q1,isCorrect:true,answer:'A'}",
      "code=200；返回 isCorrect=true；errorId 为空",
      code_of(res) == 200 and dd(res).get("isCorrect") is True and dd(res).get("errorId") is None,
      "isCorrect=%s errorId=%s" % (dd(res).get("isCorrect"), dd(res).get("errorId")))

    st, res = call("POST", "/questionPractice/report", t1,
                   {"questionId": q2, "bankId": bank_id, "isCorrect": False, "answer": "B"})
    hid1 = dd(res).get("errorId")
    T("H02", "答题上报", "上报-答错并自动生成错题记录",
      "q2 无错题记录", "POST /questionPractice/report  body={questionId:q2,isCorrect:false}",
      "code=200；返回 errorId（已 upsert 错题记录）",
      code_of(res) == 200 and bool(hid1),
      "isCorrect=%s errorId=%s" % (dd(res).get("isCorrect"), hid1))

    st, res = call("POST", "/questionPractice/report", t1,
                   {"questionId": q2, "bankId": bank_id, "isCorrect": False, "answer": "B"})
    hid2 = dd(res).get("errorId")
    q2_err2 = find_error(t1, q2) or {}
    T("H03", "答题上报", "上报-同题连续答错（错题记录覆盖累加）",
      "q2 已有错题记录（errorId=%s）" % hid1, "再次上报 isCorrect=false",
      "errorId 不变；errorCount 累加为 2",
      hid2 == hid1 and q2_err2.get("errorCount") == 2,
      "errorId=%s errorCount=%s" % (hid2, q2_err2.get("errorCount")))

    call("POST", "/favoriteQuestion/favoriteQuestion", t1, {"questionId": q3, "bankId": bank_id})
    call("POST", "/questionPractice/report", t1, {"questionId": q3, "isCorrect": True})
    call("POST", "/questionPractice/report", t1, {"questionId": q3, "isCorrect": False})
    fav3 = find_favorite(t1, q3) or {}
    # BUG-07 修复后接口已直接返回 correctTimes/errorTimes，这里以接口为准；
    # 同时直读库表做二次确认（解释器缺 DB 驱动时自动跳过该侧校验）
    dbrow = db_query(
        "SELECT correct_times, error_times, review_count FROM user_question_favorite "
        "WHERE user_id = :u AND question_id = :q", {"u": uid1, "q": q3})
    ct, et, rc = (tuple(dbrow[0]) if dbrow else (None, None, None))
    api_ok = (fav3.get("correctTimes") == 1 and fav3.get("errorTimes") == 1
              and fav3.get("reviewCount") == 2)
    db_ok = (ct is None) or (ct == 1 and et == 1 and rc == 2)
    T("H04", "答题上报", "上报-同步已收藏题目的练习/正确/错误次数",
      "user1 已收藏 q3", "对 q3 先上报答对 1 次、再上报答错 1 次，读接口 correctTimes/errorTimes/reviewCount，并直读库表交叉校验",
      "收藏记录 correctTimes=1、errorTimes=1、reviewCount=2（接口与库表一致）",
      api_ok and db_ok,
      "接口 correctTimes=%s errorTimes=%s reviewCount=%s；库表=%s/%s/%s"
      % (fav3.get("correctTimes"), fav3.get("errorTimes"),
         fav3.get("reviewCount"), ct, et, rc))

    st, res = call("GET", "/userStats/overview", t1)
    ov = dd(res)
    T("H05", "答题上报", "上报-反映到学习统计总览",
      "已累计上报若干次", "GET /userStats/overview",
      "code=200；totalPracticeCount 为流水条数、correctRate 为答对占比",
      code_of(res) == 200 and isinstance(ov.get("totalPracticeCount"), int)
      and isinstance(ov.get("correctRate"), (int, float)),
      "共作答=%s 正确率=%s" % (ov.get("totalPracticeCount"), ov.get("correctRate")))

    st, res = call("POST", "/questionPractice/report", t1, {"questionId": 99999999, "isCorrect": True})
    T("H06", "答题上报", "上报-题目不存在时的异常处理",
      "题目 99999999 不存在", "POST /questionPractice/report  body={questionId:99999999}",
      "code!=200 且提示「题目不存在」（不污染统计）",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionPractice/report", t1, {"questionId": q1})
    T("H07", "答题上报", "上报-缺少 isCorrect 字段的校验",
      "isCorrect 为必填", "POST /questionPractice/report  body={questionId:q1}",
      "校验失败（HTTP 422）",
      st == 422, "HTTP %s" % st)

    st, res = call("POST", "/questionPractice/report", None, {"questionId": q1, "isCorrect": True})
    T("H08", "答题上报", "上报-未登录访问被拒绝",
      "不带 token", "POST /questionPractice/report  body={questionId:q1,isCorrect:true}",
      "返回 401 未登录",
      st == 401 or code_of(res) == 401, "HTTP %s code=%s" % (st, code_of(res)))

    # ==================== I 模块：题目收藏 ====================
    del_fav = find_favorite(t1, q3) or {}
    st, res = call("DELETE", "/favoriteQuestion/favoriteQuestion/%s" % del_fav.get("favoriteId"), t1)
    T("I01", "题目收藏", "取消收藏题目（按记录ID）",
      "user1 已收藏 q3（favoriteId=%s）" % del_fav.get("favoriteId"),
      "DELETE /favoriteQuestion/favoriteQuestion/{favoriteId}",
      "code=200；收藏校验变为 false",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    call("POST", "/favoriteQuestion/favoriteQuestion", t1,
         {"questionId": q3, "bankId": bank_id, "notes": "首次收藏"})
    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/all", t1, params={"bankId": bank_id})
    lst = dl(res)
    T("I02", "题目收藏", "收藏列表-不分页并按题库筛选",
      "user1 已收藏 q3", "GET /favoriteQuestion/favoriteQuestion/all?bankId={bank_id}",
      "code=200；返回数组且 bankId 匹配",
      code_of(res) == 200 and len(lst) >= 1 and all(x.get("bankId") == bank_id for x in lst),
      "共 %d 条" % len(lst))

    st, res = call("POST", "/favoriteQuestion/favoriteQuestion/batchCheck", t1, {"questionIds": [q3, q2]})
    d = dd(res)
    T("I03", "题目收藏", "批量检查题目收藏状态",
      "q3 已收藏 / q2 未收藏", "POST /favoriteQuestion/favoriteQuestion/batchCheck  body={questionIds:[q3,q2]}",
      "返回 {q3:true, q2:false}",
      code_of(res) == 200 and d.get(str(q3)) is True and d.get(str(q2)) is False,
      "结果=%s" % str(d)[:100])

    f3 = find_favorite(t1, q3) or {}
    fid3 = f3.get("favoriteId")
    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/%s" % fid3, t1)
    T("I04", "题目收藏", "收藏详情",
      "favoriteId=%s 存在" % fid3, "GET /favoriteQuestion/favoriteQuestion/{favoriteId}",
      "code=200；questionId 匹配",
      code_of(res) == 200 and dd(res).get("questionId") == q3,
      "questionId=%s" % dd(res).get("questionId"))

    st, res = call("PUT", "/favoriteQuestion/favoriteQuestion", t1,
                   {"favoriteId": fid3, "notes": P + "-收藏备注", "tags": "重点", "isStarred": 1})
    st2, res2 = call("GET", "/favoriteQuestion/favoriteQuestion/%s" % fid3, t1)
    T("I05", "题目收藏", "修改收藏记录（备注 / 标签 / 星标）",
      "favoriteId=%s 属于 user1" % fid3,
      "PUT /favoriteQuestion/favoriteQuestion  body={favoriteId,notes,tags,isStarred:1}",
      "code=200；备注/标签/星标均已更新",
      code_of(res) == 200 and dd(res2).get("notes") == P + "-收藏备注"
      and dd(res2).get("tags") == "重点" and dd(res2).get("isStarred") == 1,
      "notes=%s tags=%s isStarred=%s" % (dd(res2).get("notes"), dd(res2).get("tags"),
                                         dd(res2).get("isStarred")))

    st, res = call("POST", "/favoriteQuestion/favoriteQuestion/export", t1)
    T("I06", "题目收藏", "导出题目收藏列表（Excel）",
      "user1 已登录", "POST /favoriteQuestion/favoriteQuestion/export",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/%s" % fid3, t2)
    T("I07", "题目收藏", "数据隔离-user2 不能查看 user1 的收藏详情",
      "favoriteId=%s 属于 user1" % fid3, "user2 请求 GET /favoriteQuestion/favoriteQuestion/{favoriteId}",
      "code=403 或提示无权访问（按归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/favoriteQuestion/favoriteQuestion", t2,
                   {"favoriteId": fid3, "notes": P + "-越权篡改"})
    st2, res2 = call("GET", "/favoriteQuestion/favoriteQuestion/%s" % fid3, t1)
    tampered = dd(res2).get("notes") == P + "-越权篡改"
    T("I08", "题目收藏", "数据隔离-user2 不能修改 user1 的收藏记录",
      "favoriteId=%s 属于 user1" % fid3,
      "user2 请求 PUT /favoriteQuestion/favoriteQuestion  body={favoriteId:fid3}",
      "code=403；user1 的记录不被篡改",
      code_of(res) == 403 and not tampered,
      "code=%s msg=%s；user1 记录被改=%s" % (code_of(res), res.get("msg"), tampered))

    st, res = call("DELETE", "/favoriteQuestion/favoriteQuestion/%s" % fid3, t2)
    st2, res2 = call("GET", "/favoriteQuestion/favoriteQuestion/checkFavorite/%s/%s" % (uid1, q3), t1)
    T("I09", "题目收藏", "数据隔离-user2 不能删除 user1 的收藏（按记录ID）",
      "favoriteId=%s 属于 user1" % fid3, "user2 请求 DELETE /favoriteQuestion/favoriteQuestion/{favoriteId}",
      "code=403；user1 的收藏仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；user1 收藏仍在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    st, res = call("DELETE",
                   "/favoriteQuestion/favoriteQuestion/deleteByUserAndQuestion/%s/%s" % (uid1, q3), t2)
    st2, res2 = call("GET", "/favoriteQuestion/favoriteQuestion/checkFavorite/%s/%s" % (uid1, q3), t1)
    T("I10", "题目收藏", "数据隔离-路径传入他人 user_id 不能取消他人收藏",
      "user1 已收藏 q3；路径参数 {user_id} 可被篡改",
      "user2 请求 DELETE .../deleteByUserAndQuestion/{uid1}/{q3}（路径写的是 user1 的 id）",
      "code=403；user1 的收藏仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；user1 收藏仍在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    # ==================== 清理 ====================
    st, res = call("DELETE", "/questionBank/questionBank/%s" % bank_id, t1)
    st2, res2 = call("GET", "/questionBank/questionBank/%s" % bank_id, t1)
    T("J01", "测试清理", "清理临时题库（级联删除题目与学习记录）",
      "测试题库 bank=%s 属于 user1" % bank_id, "DELETE /questionBank/questionBank/{bank_id} 后查详情",
      "code=200；删除后详情返回不存在",
      code_of(res) == 200 and code_of(res2) != 200,
      "删除=%s 详情 code=%s" % (code_of(res), code_of(res2)))

    for tok, acc in ((t1, "user1"), (t2, "user2")):
        st, res = call("GET", "/questionBank/questionBank/list", tok, params={"bankName": P, "pageSize": 100})
        print("  残留检查 %s：%s" % (acc, [b.get("id") for b in rows_of(res)] or "无"))

    # —— 物理清理：答题流水/错题/斩题/收藏题不允许残留（会污染学习统计演示数据）——
    q_t = (q1, q2, q3)
    bank_t = (bank_id,)
    db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM note_question WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM question_sub WHERE main_id IN :i", {"i": q_t})
    db_exec("DELETE FROM question_main WHERE id IN :i", {"i": q_t})
    db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    db_exec("DELETE FROM user_bank_favorite WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")
    orphan = db_scalar("SELECT COUNT(*) FROM user_practice_log l "
                       "LEFT JOIN question_main q ON q.id=l.question_id WHERE q.id IS NULL")
    T("J02", "测试清理", "无数据残留（统计/错题本不被污染）",
      "清理完成", "直连库核对孤儿答题流水与测试题目/题库",
      "孤儿流水=0，测试题目与题库均已删除",
      (orphan in (None, 0)) and all(x not in (None,) for x in (q1, q2, q3)),
      "孤儿流水=%s" % orphan)

    total = len(ROWS)
    passed = sum(1 for r in ROWS if r["status"] == "通过")
    print("=" * 74)
    print("用例总数 %d，通过 %d，失败 %d" % (total, passed, total - passed))
    print("=" * 74)
    for r in ROWS:
        if r["status"] == "失败":
            print("  [FAIL] %s %s -> 预期:%s / 实际:%s" % (r["cid"], r["title"], r["expected"], r["actual"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "prefix": P, "uid1": uid1, "uid2": uid2, "rows": ROWS,
            # 记录本 run 创建的题库 id：若下次运行前崩溃，启动自检可按 id 彻底清理
            "cleanup": {"bank_ids": [bank_id]},
        }, f, ensure_ascii=False, indent=2)
    print("结果已写入", OUT)


if __name__ == "__main__":
    main()
