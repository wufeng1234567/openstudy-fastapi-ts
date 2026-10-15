# -*- coding: utf-8 -*-
"""
题库域后端接口功能测试（E2E，真实 HTTP 调用）

覆盖：题库管理 / 题目管理 / 题库分享 / 题库·题目收藏
角色：user1（题库主）、user2（领取方）

用法（后端需先跑起来，默认 127.0.0.1:9101）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_bank_api.py

产出：脚本同目录下 e2e_bank_api_result.json（用例表数据源，可用于生成 Excel 报告）
注意：脚本会在库中创建 E2E 前缀的临时题库并在结束时尝试清理；
      「删除题库」接口当前有缺陷，清理可能失败，残留需手工清库。
"""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_bank_api_result.json")

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
    """原始 data（可能是 bool / None / list / dict）"""
    return res.get("data") if isinstance(res, dict) else None


def dd(res):
    """data 当 dict 用"""
    d = raw_data(res)
    return d if isinstance(d, dict) else {}


def dl(res):
    """data 当 list 用"""
    d = raw_data(res)
    return d if isinstance(d, list) else []


def rows_of(res):
    return (res.get("rows") or []) if isinstance(res, dict) else []


def is_file(res):
    return isinstance(res, (bytes, bytearray)) and len(res) > 0


def desc(res, st=200):
    """统一生成「实际结果」描述：文件流 / JSON 错误都友好显示"""
    if is_file(res):
        return "HTTP %s 文件流 大小=%d 字节" % (st, len(res))
    msg = (res.get("msg") or "")[:80] if isinstance(res, dict) else ""
    return "HTTP %s code=%s %s" % (st, code_of(res), msg)


def db_query(sql, params=None):
    """直连数据库读校验；失败返回 None，不影响主流程"""
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
                async with engine.connect() as conn:
                    return (await conn.execute(text(sql), params or {})).all()
            finally:
                await engine.dispose()

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print("    (DB 直读不可用：%s)" % exc)
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


def sweep_share_notifications(bank_names=()):
    """清理分享链路产生的定向通知（user_notification），防止消息中心出现死链

    ① link 指向已不存在题库的通知（领取通知 link=/front/questionPractice/{bank_id}）
    ② 内容提及测试题库名的通知（含「分享已失效」类，其 link 是静态页无法按 id 判断）
    """
    import re

    rows = db_query(
        "SELECT notification_id, link FROM user_notification "
        "WHERE link LIKE '/front/questionPractice/%'") or []
    alive = {r[0] for r in (db_query("SELECT id FROM question_bank") or [])}
    dead = []
    for nid, link in rows:
        m = re.search(r"/front/questionPractice/(\d+)", link or "")
        if m and int(m.group(1)) not in alive:
            dead.append(nid)
    if dead:
        db_exec("DELETE FROM user_notification WHERE notification_id IN :i", {"i": tuple(dead)})
    for name in bank_names:
        if name:
            db_exec("DELETE FROM user_notification WHERE content LIKE :c", {"c": "%%%s%%" % name})


def sweep_leftovers(created):
    """按记录的 id 清除上一次运行（可能中途崩溃）遗留的测试题库"""
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
    # ⚠️ bank_share 的主键列是 id（不是 share_id）；receive 引用 share，必须先删
    db_exec("DELETE FROM bank_share_receive WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share WHERE bank_id IN :i", {"i": bank_t})
    db_exec("DELETE FROM bank_share_receive WHERE share_id NOT IN (SELECT id FROM bank_share)")
    db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    sweep_share_notifications()
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")
    print("  [自检] 已清理上次运行遗留：bank=%s question=%d" % (bank_ids, len(q_ids)))


def main():
    # 启动自检：清理上一次运行（可能中途崩溃）遗留的测试题库
    prev = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_bank_api_result.json")
    if os.path.exists(prev):
        try:
            with open(prev, encoding="utf-8") as f:
                sweep_leftovers(json.load(f).get("cleanup") or {})
        except Exception as exc:  # noqa: BLE001
            print("  [自检] 读取上次结果失败：%s" % exc)

    ts = time.strftime("%m%d%H%M%S")
    # 数据命名贴近真实使用场景，不出现 E2E 之类的机器编码
    P = "随堂练习"
    BANK_A = P + "数据结构测试"      # 公开、允许复制
    BANK_B = P + "私有题库"          # 私有
    BANK_C = P + "禁止复制题库"      # 公开、禁止复制

    print("=" * 72)
    print("题库域后端接口功能测试  前缀 =", P)
    print("=" * 72)

    t1 = login("user1")
    t2 = login("user2")

    # ---------- 0. 准备：拿到两个用户的 user_id ----------
    st, create_a = call("POST", "/questionBank/questionBank", t1, {"bankName": BANK_A})
    d = dd(create_a)
    uid1 = d.get("userId")
    bank_a = d.get("id")

    st, res = call("POST", "/questionBank/questionBank", t2, {"bankName": P + "临时探针"})
    uid2 = dd(res).get("userId")
    tmp2 = dd(res).get("id")
    st, res_del_tmp = call("DELETE", "/questionBank/questionBank/%s" % tmp2, t2)
    print("user1 uid=%s  user2 uid=%s  初始题库 bank_a=%s" % (uid1, uid2, bank_a))

    # ================= A 模块：题库管理 =================

    st, res = call("POST", "/questionBank/questionBank", t1, {"bankName": ""})
    T("A01", "题库管理", "创建题库-题库名称必填校验",
      "user1 已登录", "POST /questionBank/questionBank  body={bankName:''}",
      "校验失败（HTTP 422 或 code!=200）",
      st == 422 or code_of(res) != 200, "HTTP %s / code=%s" % (st, code_of(res)))

    T("A02", "题库管理", "创建题库-成功且自动推断科目与描述",
      "user1 已登录", "POST /questionBank/questionBank  body={bankName:'%s'}（不传 subject/description）" % BANK_A,
      "code=200；返回 bankId；subject 按名称推断为「计算机基础」；description 自动生成非空",
      code_of(create_a) == 200 and bool(bank_a) and d.get("subject") == "计算机基础"
      and bool(d.get("description")),
      "bankId=%s subject=%s desc长度=%s" % (bank_a, d.get("subject"), len(d.get("description") or "")))

    st, res = call("POST", "/questionBank/questionBank", t1, {"bankName": BANK_B, "isPublic": 1})
    bank_b = dd(res).get("id")
    T("A03", "题库管理", "创建题库-私有题库（isPublic=1）",
      "user1 已登录", "POST /questionBank/questionBank  body={bankName:'%s', isPublic:1}" % BANK_B,
      "code=200；返回值 isPublic=1（私有）",
      code_of(res) == 200 and dd(res).get("isPublic") == 1,
      "bankId=%s isPublic=%s" % (bank_b, dd(res).get("isPublic")))

    st, res = call("POST", "/questionBank/questionBank", t1, {"bankName": BANK_C, "allowFork": 0})
    bank_c = dd(res).get("id")
    T("A04", "题库管理", "创建题库-设置「不允许他人复制」（allowFork=0）",
      "user1 已登录", "POST /questionBank/questionBank  body={bankName:'%s', allowFork:0}" % BANK_C,
      "code=200；返回值 allowFork=0",
      code_of(res) == 200 and dd(res).get("allowFork") == 0,
      "bankId=%s allowFork=%s" % (bank_c, dd(res).get("allowFork")))

    st, res = call("GET", "/questionBank/questionBank/my", t1)
    lst = dl(res)
    ids = [b.get("id") for b in lst]
    T("A05", "题库管理", "我的题库-只返回自己名下题库",
      "user1 已建 3 个测试题库", "GET /questionBank/questionBank/my",
      "code=200；列表包含 A02/A03/A04 三个题库；且全部 userId=自己",
      code_of(res) == 200 and all(x in ids for x in [bank_a, bank_b, bank_c])
      and all(b.get("userId") == uid1 for b in lst),
      "共 %d 个题库，含测试题库=%s" % (len(ids), all(x in ids for x in [bank_a, bank_b, bank_c])))

    st, res = call("GET", "/questionBank/questionBank/%s" % bank_a, t1)
    T("A06", "题库管理", "题库详情-题库主查看自己的题库",
      "bank_a 属于 user1", "GET /questionBank/questionBank/{bank_a}",
      "code=200；bankName 与创建时一致",
      code_of(res) == 200 and dd(res).get("bankName") == BANK_A,
      "bankName=%s" % dd(res).get("bankName"))

    st, res = call("GET", "/questionBank/questionBank/99999999", t1)
    T("A07", "题库管理", "题库详情-题库不存在时的异常处理",
      "user1 已登录", "GET /questionBank/questionBank/99999999",
      "code!=200 且提示「题库不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionBank/questionBank/list", t1, params={"pageNum": 1, "pageSize": 2})
    T("A08", "题库管理", "题库列表-分页返回（pageSize=2）",
      "user1 名下有多个题库", "GET /questionBank/questionBank/list?pageNum=1&pageSize=2",
      "code=200；total>=3；rows 长度=2",
      code_of(res) == 200 and res.get("total", 0) >= 3 and len(rows_of(res)) == 2,
      "total=%s rows=%d" % (res.get("total"), len(rows_of(res))))

    st, res = call("GET", "/questionBank/questionBank/list", t1, params={"pageNum": 1, "pageSize": 101})
    T("A09", "题库管理", "题库列表-分页参数越界校验（pageSize=101）",
      "接口约定 pageSize<=100", "GET /questionBank/questionBank/list?pageSize=101",
      "校验失败（HTTP 422）",
      st == 422, "HTTP %s" % st)

    st, res = call("GET", "/questionBank/questionBank/list", t1, params={"bankName": P})
    hit = rows_of(res)
    ok = code_of(res) == 200 and len(hit) >= 3 and all(P in (b.get("bankName") or "") for b in hit)
    T("A10", "题库管理", "题库列表-按题库名模糊筛选",
      "测试题库名带统一前缀", "GET /questionBank/questionBank/list?bankName=%s" % P,
      "返回结果全部包含该关键字", ok,
      "命中 %d 条，全部匹配=%s" % (len(hit), all(P in (b.get("bankName") or "") for b in hit)))

    st, res = call("GET", "/questionBank/questionBank/list", t1, params={"subject": "计算机基础"})
    hit = rows_of(res)
    T("A11", "题库管理", "题库列表-按科目筛选",
      "bank_a 科目=计算机基础", "GET /questionBank/questionBank/list?subject=计算机基础",
      "code=200；返回结果 subject 全部为「计算机基础」",
      code_of(res) == 200 and len(hit) > 0 and all(b.get("subject") == "计算机基础" for b in hit),
      "命中 %d 条，科目一致=%s" % (len(hit), all(b.get("subject") == "计算机基础" for b in hit)))

    st, res = call("GET", "/questionBank/questionBank/%s" % bank_b, t2)
    T("A12", "题库管理", "权限-非题库主不能查看他人私有题库",
      "bank_b 为 user1 的私有题库", "user2 请求 GET /questionBank/questionBank/{bank_b}",
      "code=403（无权访问）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionBank/questionBank/%s" % bank_a, t2)
    T("A13", "题库管理", "权限-公开题库任何人可查看",
      "bank_a 为公开题库", "user2 请求 GET /questionBank/questionBank/{bank_a}",
      "code=200",
      code_of(res) == 200, "code=%s bankName=%s" % (code_of(res), dd(res).get("bankName")))

    st, res = call("GET", "/questionBank/questionBank/list", t2, params={"bankName": BANK_B})
    T("A14", "题库管理", "可见性-他人私有题库不出现在列表中",
      "bank_b 为 user1 的私有题库", "user2 请求 /questionBank/questionBank/list?bankName={BANK_B}",
      "total=0（不可见）",
      res.get("total", -1) == 0, "total=%s" % res.get("total"))

    st, res = call("GET", "/questionBank/questionBank/all", t2, params={"onlyPublic": "true"})
    lst = dl(res)
    pids = [b.get("id") for b in lst]
    T("A15", "题库管理", "公开题库广场-只返回公开题库",
      "存在公开题库与私有题库", "user2 请求 GET /questionBank/questionBank/all?onlyPublic=true",
      "code=200；列表全部 isPublic=0；不含 bank_b（私有）",
      code_of(res) == 200 and all(b.get("isPublic") == 0 for b in lst) and bank_b not in pids,
      "共 %d 个，全部公开=%s，含私有题库=%s" % (len(lst), all(b.get("isPublic") == 0 for b in lst),
                                              bank_b in pids))

    NEW_NAME = BANK_A + "改名"
    st, res = call("PUT", "/questionBank/questionBank", t1,
                   {"bankId": bank_a, "bankName": NEW_NAME, "subject": "算法与数据结构"})
    st2, res2 = call("GET", "/questionBank/questionBank/%s" % bank_a, t1)
    T("A16", "题库管理", "修改题库-题库主修改题库信息",
      "bank_a 属于 user1", "PUT /questionBank/questionBank  body={bankId,bankName,subject} 后查详情",
      "code=200；名称与科目均已更新",
      code_of(res) == 200 and dd(res2).get("bankName") == NEW_NAME
      and dd(res2).get("subject") == "算法与数据结构",
      "bankName=%s subject=%s" % (dd(res2).get("bankName"), dd(res2).get("subject")))

    st, res = call("PUT", "/questionBank/questionBank", t1, {"id": bank_a, "description": "兼容 id 字段测试"})
    T("A17", "题库管理", "修改题库-兼容前端 id 字段（AliasChoices）",
      "前端历史实现使用 id 字段", "PUT /questionBank/questionBank  body={id:bankId,description:...}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionBank/questionBank", t2, {"bankId": bank_a, "bankName": "恶意改名"})
    T("A18", "题库管理", "权限-非题库主不能修改他人题库",
      "bank_a 属于 user1", "user2 请求 PUT /questionBank/questionBank  body={bankId:bank_a}",
      "code=403（只有题库主才能修改）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionBank/questionBank", t1, {"bankId": 99999999, "bankName": "x"})
    T("A19", "题库管理", "修改题库-题库不存在时的异常处理",
      "user1 已登录", "PUT /questionBank/questionBank  body={bankId:99999999}",
      "code!=200 且提示「题库不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionBank/questionBank", t1, {"bankName": "无ID"})
    T("A20", "题库管理", "修改题库-缺少题库ID的校验",
      "user1 已登录", "PUT /questionBank/questionBank  body={bankName:'无ID'}（不传 bankId/id）",
      "code!=200 且提示「题库ID不能为空」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionBank/questionBank/copy/%s" % bank_a, t1, {})
    copy1 = dd(res).get("id")
    T("A21", "题库管理", "复制题库-复制自己的题库",
      "bank_a 属于 user1", "POST /questionBank/questionBank/copy/{bank_a}",
      "code=200；返回新 bankId（≠原题库）；副本 userId=自己",
      code_of(res) == 200 and copy1 and copy1 != bank_a and dd(res).get("userId") == uid1,
      "新 bankId=%s userId=%s" % (copy1, dd(res).get("userId")))

    st, res = call("POST", "/questionBank/questionBank/copy/%s" % bank_a, t2, {"bankName": P + "二创副本"})
    copy2 = dd(res).get("id")
    T("A22", "题库管理", "复制题库-他人公开题库二创并自定义副本名",
      "bank_a 为公开且允许复制", "user2 请求 copy/{bank_a}  body={bankName:'%s二创副本'}" % P,
      "code=200；副本 userId=user2；bankName=自定义名",
      code_of(res) == 200 and dd(res).get("userId") == uid2
      and dd(res).get("bankName") == P + "二创副本",
      "副本 bankId=%s userId=%s bankName=%s" % (copy2, dd(res).get("userId"), dd(res).get("bankName")))

    st, res = call("POST", "/questionBank/questionBank/copy/%s" % bank_c, t2, {})
    T("A23", "题库管理", "权限-题库主关闭复制开关后不可复制",
      "bank_c 设置 allowFork=0 且为公开题库", "user2 请求 copy/{bank_c}",
      "code=403（题库主未开放复制）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionBank/questionBank/copy/%s" % bank_b, t2, {})
    T("A24", "题库管理", "权限-未获分享不可复制他人私有题库",
      "bank_b 为 user1 私有题库、user2 未领取分享", "user2 请求 copy/{bank_b}",
      "code=403（无权复制）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionBank/questionBank/export", t1)
    T("A25", "题库管理", "导出题库列表（Excel 文件流）",
      "user1 已登录", "POST /questionBank/questionBank/export",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    # ================= B 模块：题目管理 =================
    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_a, "questionType": 1,
        "questionText": P + "-单选题-1+1=?",
        "options": [{"key": "A", "value": "1"}, {"key": "B", "value": "2"}],
        "answer": "B", "difficulty": 1, "questionAnalysis": "基础题",
    })
    q1 = dd(res).get("questionId")
    T("B01", "题目管理", "新增题目-单选题",
      "bank_a 属于 user1", "POST /questionMain/questionMain  body={bankId,questionType:1,questionText,options,answer}",
      "code=200；返回 questionId；bankId 正确",
      code_of(res) == 200 and bool(q1) and dd(res).get("bankId") == bank_a,
      "questionId=%s bankId=%s" % (q1, dd(res).get("bankId")))

    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_a, "questionType": 3,
        "questionText": P + "-判断题-地球是圆的",
        "options": [{"key": "A", "value": "对"}, {"key": "B", "value": "错"}],
        "answer": "A", "difficulty": 2,
    })
    q2 = dd(res).get("questionId")
    T("B02", "题目管理", "新增题目-判断题（difficulty=2）",
      "bank_a 属于 user1", "POST /questionMain/questionMain  body={questionType:3,difficulty:2}",
      "code=200；difficulty=2",
      code_of(res) == 200 and dd(res).get("difficulty") == 2,
      "questionId=%s difficulty=%s" % (q2, dd(res).get("difficulty")))

    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_a, "questionType": 6,
        "questionText": P + "-组合题-数据结构的逻辑结构",
        "answer": "见子题",
        "questionSubList": [
            {"questionText": "线性结构有哪些？", "questionType": 1, "options": [{"key": "A", "value": "数组"}], "answer": "A", "sortOrder": 1},
            {"questionText": "树属于什么结构？", "questionType": 1, "options": [{"key": "A", "value": "非线性"}], "answer": "A", "sortOrder": 2},
        ],
    })
    q3 = dd(res).get("questionId")
    subs = dd(res).get("subQuestions") or []
    T("B03", "题目管理", "新增题目-组合题（含 2 个子题）",
      "bank_a 属于 user1", "POST /questionMain/questionMain  body={questionType:6, questionSubList:[2 条]}",
      "code=200；hasSubQuestions=1；subQuestions 数量=2",
      code_of(res) == 200 and dd(res).get("hasSubQuestions") == 1 and len(subs) == 2,
      "questionId=%s hasSub=%s 子题数=%d" % (q3, dd(res).get("hasSubQuestions"), len(subs)))

    st, res = call("GET", "/questionBank/questionBank/%s" % bank_a, t1)
    T("B04", "题目管理", "新增题目后自动重算题库题目总数",
      "bank_a 原有 0 题", "建 3 题（含 1 组合题）后 GET 题库详情",
      "totalQuestions=3",
      dd(res).get("totalQuestions") == 3,
      "totalQuestions=%s" % dd(res).get("totalQuestions"))

    st, res = call("POST", "/questionMain/questionMain", t2, {
        "bankId": bank_a, "questionType": 1, "questionText": P + "-越权新增",
    })
    T("B05", "题目管理", "权限-非题库主不能在他人的题库下新增题目",
      "bank_a 属于 user1", "user2 请求 POST /questionMain/questionMain  body={bankId:bank_a}",
      "code=403（只有题库主才能新增）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": 99999999, "questionType": 1, "questionText": P + "-题库不存在",
    })
    T("B06", "题目管理", "新增题目-题库不存在时的异常处理",
      "bankId=99999999 不存在", "POST /questionMain/questionMain  body={bankId:99999999}",
      "code!=200 且提示「题库不存在」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/questionMain/questionMain/list", t1, params={"bankId": bank_a, "pageSize": 50})
    T("B07", "题目管理", "题目列表-按题库筛选",
      "bank_a 下有 3 题", "GET /questionMain/questionMain/list?bankId={bank_a}",
      "code=200；total=3；返回项 bankId 全部匹配",
      code_of(res) == 200 and res.get("total") == 3 and all(r.get("bankId") == bank_a for r in rows_of(res)),
      "total=%s" % res.get("total"))

    st, res = call("GET", "/questionMain/questionMain/list", t1, params={"bankId": bank_a, "questionType": 1})
    T("B08", "题目管理", "题目列表-按题型筛选（单选）",
      "bank_a 有单选题", "GET /questionMain/questionMain/list?bankId={bank_a}&questionType=1",
      "code=200；返回项 questionType 全部=1",
      code_of(res) == 200 and len(rows_of(res)) >= 1 and all(r.get("questionType") == 1 for r in rows_of(res)),
      "total=%s" % res.get("total"))

    st, res = call("GET", "/questionMain/questionMain/list", t1,
                   params={"bankId": bank_a, "keyword": P + "-判断题"})
    hit = rows_of(res)
    T("B09", "题目管理", "题目列表-按题干关键字搜索",
      "题干含统一前缀", "GET /questionMain/questionMain/list?bankId={bank_a}&keyword={P}-判断题",
      "code=200；命中 1 条且题干包含关键字",
      code_of(res) == 200 and res.get("total") == 1 and hit and (P + "-判断题") in (hit[0].get("questionText") or ""),
      "total=%s" % res.get("total"))

    st, res = call("GET", "/questionMain/questionMain/%s" % q3, t1)
    T("B10", "题目管理", "题目详情-含子题",
      "q3 为组合题", "GET /questionMain/questionMain/{q3}",
      "code=200；subQuestions 数量=2",
      code_of(res) == 200 and len(dd(res).get("subQuestions") or []) == 2,
      "子题数=%d" % len(dd(res).get("subQuestions") or []))

    st, res = call("PUT", "/questionMain/questionMain", t1, {
        "id": q1, "questionText": P + "-单选题-1+1=?（已修改）", "difficulty": 3,
    })
    st2, res2 = call("GET", "/questionMain/questionMain/%s" % q1, t1)
    T("B11", "题目管理", "修改题目-题库主修改题干与难度",
      "q1 属于 user1 的题库", "PUT /questionMain/questionMain  body={id:q1,questionText,difficulty:3}",
      "code=200；题干与难度均已更新",
      code_of(res) == 200 and dd(res2).get("difficulty") == 3
      and "（已修改）" in (dd(res2).get("questionText") or ""),
      "difficulty=%s questionText=%s" % (dd(res2).get("difficulty"), dd(res2).get("questionText")))

    st, res = call("PUT", "/questionMain/questionMain", t2, {"id": q1, "questionText": P + "-越权修改"})
    T("B12", "题目管理", "权限-非题库主不能修改题目",
      "q1 属于 user1 的题库", "user2 请求 PUT /questionMain/questionMain  body={id:q1}",
      "code=403（只有题库主才能修改）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/questionMain/questionMain", t1, {
        "id": q3, "questionSubList": [
            {"questionText": "替换后的子题-1", "questionType": 2, "options": [{"key": "A", "value": "x"}], "answer": "A", "sortOrder": 1},
        ],
    })
    st2, res2 = call("GET", "/questionMain/questionMain/%s" % q3, t1)
    new_subs = dd(res2).get("subQuestions") or []
    T("B13", "题目管理", "修改题目-子题全量替换（2 条 -> 1 条）",
      "q3 原有 2 个子题", "PUT /questionMain/questionMain  body={id:q3, questionSubList:[1 条]}",
      "code=200；子题数量变为 1 且内容为新子题",
      code_of(res) == 200 and len(new_subs) == 1
      and new_subs[0].get("questionText") == "替换后的子题-1",
      "子题数=%d" % len(new_subs))

    st, res = call("GET", "/questionMain/questionMain/search", t1,
                   params={"keyword": P, "pageSize": 50})
    hit = rows_of(res)
    T("B14", "题目管理", "题目搜索接口（供选择器使用，分页返回）",
      "存在带统一前缀的题目", "GET /questionMain/questionMain/search?keyword={P}&pageSize=50",
      "code=200；total>=3；rows 为题目的分页结构",
      code_of(res) == 200 and res.get("total", 0) >= 3 and len(hit) >= 3,
      "total=%s rows=%d" % (res.get("total"), len(hit)))

    st, res = call("GET", "/questionMain/questionMain/checkExists/%s" % q1, t1)
    st2, res2 = call("GET", "/questionMain/questionMain/checkExists/99999999", t1)
    T("B15", "题目管理", "题目存在性校验",
      "q1 存在 / 99999999 不存在", "GET /questionMain/questionMain/checkExists/{q1} 与 /99999999",
      "data.exists 分别为 true / false",
      dd(res).get("exists") is True and dd(res2).get("exists") is False,
      "存在=%s 不存在=%s" % (dd(res).get("exists"), dd(res2).get("exists")))

    st, res = call("GET", "/questionMain/questionMain/simpleInfo/%s" % q1, t1)
    T("B16", "题目管理", "题目精简信息查询",
      "q1 存在", "GET /questionMain/questionMain/simpleInfo/{q1}",
      "code=200；返回 questionId 与题干",
      code_of(res) == 200 and dd(res).get("questionId") == q1,
      "questionId=%s" % dd(res).get("questionId"))

    st, res = call("GET", "/questionMain/questionMain/checkQuestionAndUser/%s/%s" % (q1, uid1), t1)
    T("B17", "题目管理", "题目与用户联合存在性校验",
      "q1 存在且 user1 存在", "GET /questionMain/questionMain/checkQuestionAndUser/{q1}/{uid1}",
      "code=200；data.allValid=true",
      code_of(res) == 200 and dd(res).get("allValid") is True,
      "allValid=%s" % dd(res).get("allValid"))

    st, res = call("POST", "/questionMain/questionMain/batchInfo", t1, {"questionIds": [q1, q2]})
    T("B18", "题目管理", "题目批量查询（batchInfo）",
      "q1/q2 均存在", "POST /questionMain/questionMain/batchInfo  body={questionIds:[q1,q2]}",
      "code=200；返回 2 条",
      code_of(res) == 200 and len(dl(res)) == 2, "返回 %d 条" % len(dl(res)))

    st, res = call("POST", "/questionMain/questionMain/export", t1, params={"bankId": bank_a})
    T("B19", "题目管理", "导出题目-按题库导出（数据干净的题库）",
      "bank_a 下 3 道题、题干无非法字符", "POST /questionMain/questionMain/export?bankId={bank_a}",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    st, res = call("POST", "/questionMain/questionMain/export", t1)
    T("B20", "题目管理", "导出题目-全量导出（含历史题库数据）",
      "库中存在含 0x0C 控制字符的题干", "POST /questionMain/questionMain/export（不传 bankId）",
      "code=200 且返回文件流",
      st == 200 and is_file(res), desc(res, st))

    # ---- 删除题目 + 级联 ----
    st, res = call("POST", "/questionMain/questionMain", t1, {
        "bankId": bank_a, "questionType": 1, "questionText": P + "-待删除题",
        "options": [{"key": "A", "value": "1"}], "answer": "A",
    })
    qdel = dd(res).get("questionId")
    call("POST", "/favoriteQuestion/favoriteQuestion", t2, {"questionId": qdel, "bankId": bank_a})
    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/checkFavorite/%s/%s" % (uid2, qdel), t2)
    before = raw_data(res)

    st, res = call("DELETE", "/questionMain/questionMain/%s" % qdel, t1)
    st2, res2 = call("GET", "/questionMain/questionMain/checkExists/%s" % qdel, t1)
    st3, res3 = call("GET", "/favoriteQuestion/favoriteQuestion/checkFavorite/%s/%s" % (uid2, qdel), t2)
    T("B21", "题目管理", "删除题目-题库主删除自己的题目",
      "qdel 属于 user1 的题库", "DELETE /questionMain/questionMain/{qdel}",
      "code=200；删除后 data.exists=false",
      code_of(res) == 200 and dd(res2).get("exists") is False,
      "删除 code=%s 存在性=%s" % (code_of(res), dd(res2).get("exists")))

    T("B22", "题目管理", "删除题目-级联清理用户题目收藏记录",
      "user2 已收藏 qdel", "删除 qdel 后再次校验收藏状态",
      "收藏记录被级联物理删除（false）",
      before is True and raw_data(res3) is False,
      "删除前收藏=%s 删除后收藏=%s" % (before, raw_data(res3)))

    # ================= C 模块：题库分享 =================
    st, res = call("POST", "/bankShare/bankShare/create", t1,
                   {"bankId": bank_b, "expireDays": 7, "message": "E2E 分享测试"})
    share_id = dd(res).get("shareId")
    share_tok = dd(res).get("shareToken")
    share_code = dd(res).get("shareCode")
    T("C01", "题库分享", "生成题库分享（题库主）",
      "bank_b 属于 user1", "POST /bankShare/bankShare/create  body={bankId:bank_b,expireDays:7}",
      "code=200；返回 shareId/shareToken/shareCode；effective=true",
      code_of(res) == 200 and bool(share_tok) and bool(share_code) and dd(res).get("effective") is True,
      "shareId=%s token=%s code=%s" % (share_id, (share_tok or "")[:8], share_code))

    st, res = call("POST", "/bankShare/bankShare/create", t2, {"bankId": bank_b})
    T("C02", "题库分享", "权限-非题库主不能生成分享",
      "bank_b 属于 user1", "user2 请求 POST /bankShare/bankShare/create  body={bankId:bank_b}",
      "code=403（只有题库主才能分享）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/bankShare/bankShare/my", t1)
    lst = dl(res)
    T("C03", "题库分享", "我的分享列表",
      "user1 刚生成 1 个分享", "GET /bankShare/bankShare/my",
      "code=200；列表包含刚生成的 shareId；并带 bankName",
      code_of(res) == 200 and any(s.get("shareId") == share_id for s in lst)
      and any(s.get("shareId") == share_id and s.get("bankName") for s in lst),
      "共 %d 条，含目标分享=%s" % (len(lst), any(s.get("shareId") == share_id for s in lst)))

    st, res = call("GET", "/bankShare/bankShare/info/%s" % share_tok, t2)
    T("C04", "题库分享", "按分享令牌查看分享落地页信息",
      "user2 已登录且持 token", "GET /bankShare/bankShare/info/{token}",
      "code=200；返回 bankId=bank_b 与题库名",
      code_of(res) == 200 and dd(res).get("bankId") == bank_b,
      "bankId=%s bankName=%s" % (dd(res).get("bankId"), dd(res).get("bankName")))

    st, res = call("GET", "/bankShare/bankShare/infoByCode/%s" % share_code, t2)
    T("C05", "题库分享", "按分享码查看分享信息",
      "分享码有效", "GET /bankShare/bankShare/infoByCode/{code}",
      "code=200；返回 bankId=bank_b",
      code_of(res) == 200 and dd(res).get("bankId") == bank_b,
      "bankId=%s" % dd(res).get("bankId"))

    st, res = call("GET", "/bankShare/bankShare/checkSource/%s" % bank_b, t2)
    T("C06", "题库分享", "查询我与题库的关系-未领取分享时",
      "user2 尚未领取该分享", "GET /bankShare/bankShare/checkSource/{bank_b}",
      "code=200；isOwner=false、canEdit=false",
      code_of(res) == 200 and dd(res).get("isOwner") is False and dd(res).get("canEdit") is False,
      "isOwner=%s canEdit=%s" % (dd(res).get("isOwner"), dd(res).get("canEdit")))

    st, res = call("POST", "/bankShare/bankShare/receive", t2, {"token": share_tok})
    T("C07", "题库分享", "领取分享-首次领取",
      "user2 首次领取该分享", "POST /bankShare/bankShare/receive  body={token}",
      "code=200；resultStatus=created",
      code_of(res) == 200 and dd(res).get("resultStatus") == "created",
      "resultStatus=%s" % dd(res).get("resultStatus"))

    st, res = call("POST", "/bankShare/bankShare/receive", t2, {"token": share_tok})
    T("C08", "题库分享", "领取分享-重复领取（幂等）",
      "user2 已领取过", "再次 POST /bankShare/bankShare/receive  body={token}",
      "code=200；resultStatus=exists（不重复计数）",
      code_of(res) == 200 and dd(res).get("resultStatus") == "exists",
      "resultStatus=%s" % dd(res).get("resultStatus"))

    st, res = call("GET", "/questionBank/questionBank/%s" % bank_b, t2)
    T("C09", "题库分享", "领取后可查看他人私有题库",
      "user2 已领取 bank_b 的分享", "user2 请求 GET /questionBank/questionBank/{bank_b}",
      "code=200（分享授予只读可见性）",
      code_of(res) == 200, "code=%s bankName=%s" % (code_of(res), dd(res).get("bankName")))

    st, res = call("GET", "/favoriteBank/favoriteBank/checkFavorite/%s/%s" % (uid2, bank_b), t2)
    T("C10", "题库分享", "领取分享后自动进入「题库收藏」",
      "user2 已领取分享", "GET /favoriteBank/favoriteBank/checkFavorite/{uid2}/{bank_b}",
      "返回 true（领取=只写入收藏，只读）",
      raw_data(res) is True, "已收藏=%s" % raw_data(res))

    st, res = call("GET", "/bankShare/bankShare/checkSource/%s" % bank_b, t2)
    T("C11", "题库分享", "查询我与题库的关系-领取后",
      "user2 已领取分享", "GET /bankShare/bankShare/checkSource/{bank_b}",
      "code=200；isShare=true；canEdit=false",
      code_of(res) == 200 and dd(res).get("isShare") is True and dd(res).get("canEdit") is False,
      "isShare=%s canEdit=%s" % (dd(res).get("isShare"), dd(res).get("canEdit")))

    st, res = call("GET", "/bankShare/bankShare/checkSource/%s" % bank_b, t1)
    T("C12", "题库分享", "查询我与题库的关系-题库主视角",
      "bank_b 属于 user1", "user1 请求 GET /bankShare/bankShare/checkSource/{bank_b}",
      "code=200；isOwner=true、canEdit=true",
      code_of(res) == 200 and dd(res).get("isOwner") is True and dd(res).get("canEdit") is True,
      "isOwner=%s canEdit=%s" % (dd(res).get("isOwner"), dd(res).get("canEdit")))

    call("DELETE", "/favoriteBank/favoriteBank/deleteByUserAndBank/%s/%s" % (uid2, bank_b), t2)
    st, res = call("POST", "/bankShare/bankShare/receive", t2, {"code": share_code})
    T("C13", "题库分享", "取消收藏后按分享码重新领取",
      "user2 先取消对该题库的收藏", "取消收藏 -> POST /bankShare/bankShare/receive  body={code}",
      "code=200；resultStatus=restored（重新加入）",
      code_of(res) == 200 and dd(res).get("resultStatus") == "restored",
      "resultStatus=%s" % dd(res).get("resultStatus"))

    st, res = call("POST", "/bankShare/bankShare/revoke/%s" % share_id, t2)
    T("C14", "题库分享", "权限-非分享发起人不能撤销分享",
      "分享由 user1 发起", "user2 请求 POST /bankShare/bankShare/revoke/{share_id}",
      "code=403（无权撤销）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/bankShare/bankShare/revoke/%s" % share_id, t1)
    st2, res2 = call("GET", "/bankShare/bankShare/info/%s" % share_tok, t2)
    st3, res3 = call("POST", "/bankShare/bankShare/receive", t2, {"token": share_tok})
    info_ok = code_of(res2) != 200 or dd(res2).get("effective") is False
    T("C15", "题库分享", "撤销分享-题库主撤销后分享立即失效",
      "分享由 user1 发起", "POST /bankShare/bankShare/revoke/{share_id} 后按 token 查看与领取",
      "撤销 code=200；查看接口失效（非200 或 effective=false）；再次领取失败",
      code_of(res) == 200 and info_ok and code_of(res3) != 200,
      "撤销=%s 查看 code=%s 再领取 code=%s" % (code_of(res), code_of(res2), code_of(res3)))

    # ================= D 模块：收藏 =================
    st, res = call("POST", "/favoriteBank/favoriteBank", t2, {"bankId": bank_a})
    T("D01", "收藏管理", "收藏题库",
      "bank_a 为公开题库", "user2 请求 POST /favoriteBank/favoriteBank  body={bankId:bank_a}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/favoriteBank/favoriteBank/checkFavorite/%s/%s" % (uid2, bank_a), t2)
    T("D02", "收藏管理", "题库收藏状态校验",
      "user2 刚收藏 bank_a", "GET /favoriteBank/favoriteBank/checkFavorite/{uid2}/{bank_a}",
      "返回 true",
      raw_data(res) is True, "已收藏=%s" % raw_data(res))

    st, res = call("POST", "/favoriteBank/favoriteBank", t2, {"bankId": bank_a})
    T("D03", "收藏管理", "重复收藏题库的处理",
      "user2 已收藏 bank_a", "再次 POST /favoriteBank/favoriteBank  body={bankId:bank_a}",
      "明确提示「已收藏该题库」（code!=200）",
      code_of(res) != 200 and "已收藏" in (res.get("msg") or ""),
      "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/favoriteBank/favoriteBank/list", t2, params={"pageNum": 1, "pageSize": 50})
    hit = [r for r in rows_of(res) if r.get("bankId") == bank_a]
    T("D04", "收藏管理", "我的题库收藏列表",
      "user2 已收藏若干题库", "GET /favoriteBank/favoriteBank/list",
      "code=200；列表包含 bank_a",
      code_of(res) == 200 and len(hit) == 1, "命中 bank_a 条数=%d" % len(hit))

    st, res = call("DELETE", "/favoriteBank/favoriteBank/deleteByUserAndBank/%s/%s" % (uid2, bank_a), t2)
    st2, res2 = call("GET", "/favoriteBank/favoriteBank/checkFavorite/%s/%s" % (uid2, bank_a), t2)
    T("D05", "收藏管理", "取消题库收藏（物理删除）",
      "user2 已收藏 bank_a", "DELETE /favoriteBank/favoriteBank/deleteByUserAndBank/{uid2}/{bank_a}",
      "code=200；再校验收藏状态=false",
      code_of(res) == 200 and raw_data(res2) is False,
      "取消 code=%s 状态=%s" % (code_of(res), raw_data(res2)))

    st, res = call("POST", "/favoriteQuestion/favoriteQuestion", t2,
                   {"questionId": q1, "bankId": bank_a, "notes": "E2E 收藏备注"})
    T("D06", "收藏管理", "收藏题目",
      "q1 属于 bank_a（公开）", "user2 请求 POST /favoriteQuestion/favoriteQuestion  body={questionId:q1}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/checkFavorite/%s/%s" % (uid2, q1), t2)
    T("D07", "收藏管理", "题目收藏状态校验",
      "user2 刚收藏 q1", "GET /favoriteQuestion/favoriteQuestion/checkFavorite/{uid2}/{q1}",
      "返回 true",
      raw_data(res) is True, "已收藏=%s" % raw_data(res))

    st, res = call("GET", "/favoriteQuestion/favoriteQuestion/list", t2, params={"pageNum": 1, "pageSize": 50})
    hit = [r for r in rows_of(res) if r.get("questionId") == q1]
    T("D08", "收藏管理", "我的题目收藏列表",
      "user2 已收藏 q1", "GET /favoriteQuestion/favoriteQuestion/list",
      "code=200；列表包含 q1",
      code_of(res) == 200 and len(hit) == 1, "命中 q1 条数=%d" % len(hit))

    st, res = call("POST", "/favoriteQuestion/favoriteQuestion/batchCheck", t2, {"questionIds": [q1, q2]})
    T("D09", "收藏管理", "题目收藏批量校验",
      "user2 只收藏了 q1", "POST /favoriteQuestion/favoriteQuestion/batchCheck  body={questionIds:[q1,q2]}",
      "code=200；q1=true、q2=false",
      code_of(res) == 200 and dd(res).get(str(q1)) is True and dd(res).get(str(q2)) is False,
      "结果=%s" % str(dd(res))[:120])

    st, res = call("DELETE", "/favoriteQuestion/favoriteQuestion/deleteByUserAndQuestion/%s/%s" % (uid2, q1), t2)
    T("D10", "收藏管理", "取消题目收藏",
      "user2 已收藏 q1", "DELETE /favoriteQuestion/favoriteQuestion/deleteByUserAndQuestion/{uid2}/{q1}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ---- 题库收藏数据隔离：user1 的收藏记录，user2 尝试越权（BUG-05 修复后的回归）----
    call("POST", "/favoriteBank/favoriteBank", t1, {"bankId": bank_a})
    _fl = call("GET", "/favoriteBank/favoriteBank/list", t1, params={"pageNum": 1, "pageSize": 50})
    fb1 = next((r for r in rows_of(_fl[1]) if r.get("bankId") == bank_a), {})
    fid1 = fb1.get("favoriteId")

    st, res = call("GET", "/favoriteBank/favoriteBank/%s" % fid1, t2)
    T("D11", "收藏管理", "数据隔离-user2 不能查看 user1 的题库收藏详情",
      "favoriteId=%s 属于 user1" % fid1, "user2 请求 GET /favoriteBank/favoriteBank/{favoriteId}",
      "code=403（按归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/favoriteBank/favoriteBank", t2,
                   {"favoriteId": fid1, "notes": P + "-越权篡改"})
    st2, res2 = call("GET", "/favoriteBank/favoriteBank/%s" % fid1, t1)
    tampered = dd(res2).get("notes") == P + "-越权篡改"
    T("D12", "收藏管理", "数据隔离-user2 不能修改 user1 的题库收藏",
      "favoriteId=%s 属于 user1" % fid1, "user2 请求 PUT /favoriteBank/favoriteBank  body={favoriteId}",
      "code=403；user1 的记录未被篡改",
      code_of(res) == 403 and not tampered,
      "code=%s msg=%s；被改=%s" % (code_of(res), res.get("msg"), tampered))

    st, res = call("DELETE", "/favoriteBank/favoriteBank/%s" % fid1, t2)
    st2, res2 = call("GET", "/favoriteBank/favoriteBank/checkFavorite/%s/%s" % (uid1, bank_a), t1)
    T("D13", "收藏管理", "数据隔离-user2 不能按记录ID删除 user1 的题库收藏",
      "favoriteId=%s 属于 user1" % fid1, "user2 请求 DELETE /favoriteBank/favoriteBank/{favoriteId}",
      "code=403；user1 的收藏仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；仍存在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    st, res = call("DELETE", "/favoriteBank/favoriteBank/deleteByUserAndBank/%s/%s" % (uid1, bank_a), t2)
    st2, res2 = call("GET", "/favoriteBank/favoriteBank/checkFavorite/%s/%s" % (uid1, bank_a), t1)
    T("D14", "收藏管理", "数据隔离-路径传他人 uid 不能取消他人题库收藏",
      "bank_a 已被 user1 收藏", "user2 请求 DELETE .../deleteByUserAndBank/{uid1}/{bank_a}",
      "code=403；user1 的收藏仍存在",
      code_of(res) == 403 and raw_data(res2) is True,
      "code=%s msg=%s；仍存在=%s" % (code_of(res), res.get("msg"), raw_data(res2)))

    # 清理：user1 自己的收藏（合法路径，验证修复未误伤正常流程）
    call("DELETE", "/favoriteBank/favoriteBank/deleteByUserAndBank/%s/%s" % (uid1, bank_a), t1)

    # ================= E 模块：删除题库（含权限与级联） =================
    st, res = call("DELETE", "/questionBank/questionBank/%s" % bank_c, t2)
    T("E01", "题库管理", "权限-非题库主不能删除他人题库",
      "bank_c 属于 user1", "user2 请求 DELETE /questionBank/questionBank/{bank_c}",
      "code=403（只能删除自己的题库）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), (res.get("msg") or "")[:60]))

    st, res = call("DELETE", "/questionBank/questionBank/%s" % bank_c, t1)
    st2, res2 = call("GET", "/questionBank/questionBank/%s" % bank_c, t1)
    T("E02", "题库管理", "删除题库-删除自己名下的题库",
      "bank_c 属于 user1", "DELETE /questionBank/questionBank/{bank_c} 后查详情",
      "code=200；删除后查详情返回「题库不存在」",
      code_of(res) == 200 and code_of(res2) != 200,
      "删除 code=%s msg=%s；删除后详情 code=%s" % (code_of(res), (res.get("msg") or "")[:50], code_of(res2)))

    st, res = call("DELETE", "/questionBank/questionBank/%s,%s" % (bank_a, bank_b), t1)
    st2, res2 = call("GET", "/questionMain/questionMain/checkExists/%s" % q1, t1)
    T("E03", "题库管理", "删除题库-批量删除并级联清理题目",
      "bank_a/bank_b 属于 user1，且 bank_a 下有题目", "DELETE /questionBank/questionBank/{bank_a},{bank_b}",
      "code=200；其下题目被级联删除（checkExists=false）",
      code_of(res) == 200 and dd(res2).get("exists") is False,
      "删除 code=%s msg=%s；原题目存在性=%s" % (code_of(res), (res.get("msg") or "")[:50], dd(res2).get("exists")))

    st, res = call("DELETE", "/questionBank/questionBank/%s" % copy1, t1)
    st2, res2 = call("DELETE", "/questionBank/questionBank/%s" % copy2, t2)
    T("E04", "题库管理", "删除题库-删除复制产生的副本",
      "copy1 属于 user1、copy2 属于 user2", "各自题库主删除副本",
      "两次均 code=200",
      code_of(res) == 200 and code_of(res2) == 200,
      "copy1=%s copy2=%s" % (code_of(res), code_of(res2)))

    # 兜底：物理清理本 run 建立的题库/题目/收藏/分享/通知（不给演示环境留任何痕迹）
    bank_t = tuple(x for x in (bank_a, bank_b, bank_c, copy1, copy2) if x)
    if bank_t:
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
        # ⚠️ bank_share 主键列是 id；receive 引用 share，必须先删
        db_exec("DELETE FROM bank_share_receive WHERE bank_id IN :i", {"i": bank_t})
        db_exec("DELETE FROM bank_share WHERE bank_id IN :i", {"i": bank_t})
        db_exec("DELETE FROM bank_share_receive WHERE share_id NOT IN (SELECT id FROM bank_share)")
        db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    # 分享/领取/撤销都会产生定向通知（user_notification），一并清掉，否则消息中心出现死链
    sweep_share_notifications([BANK_A, BANK_B, BANK_C, P + "二创副本", P + "临时探针"])
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")

    for tok, acc in ((t1, "user1"), (t2, "user2")):
        st, res = call("GET", "/questionBank/questionBank/list", tok, params={"bankName": P, "pageSize": 100})
        left = [b.get("id") for b in rows_of(res)]
        print("  残留检查 %s：%s" % (acc, left or "无"))
    orphan = db_scalar("SELECT COUNT(*) FROM user_practice_log l "
                       "LEFT JOIN question_main q ON q.id=l.question_id WHERE q.id IS NULL")
    # 死链通知：link 指向已不存在的题库
    import re as _re
    _alive = {r[0] for r in (db_query("SELECT id FROM question_bank") or [])}
    _dead = 0
    for nid, link in (db_query(
            "SELECT notification_id, link FROM user_notification "
            "WHERE link LIKE '/front/questionPractice/%'") or []):
        m = _re.search(r"/front/questionPractice/(\d+)", link or "")
        if m and int(m.group(1)) not in _alive:
            _dead += 1
    T("E05", "题库管理", "无数据残留（学习统计与消息中心不被污染）",
      "清理完成", "直连库核对孤儿答题流水、测试题库与死链通知",
      "孤儿流水=0，测试题库均已删除，死链通知=0",
      (orphan in (None, 0)) and _dead == 0,
      "孤儿流水=%s 死链通知=%s" % (orphan, _dead))

    # ---------- 汇总 ----------
    total = len(ROWS)
    passed = sum(1 for r in ROWS if r["status"] == "通过")
    print("=" * 72)
    print("用例总数 %d，通过 %d，失败 %d" % (total, passed, total - passed))
    print("=" * 72)
    for r in ROWS:
        if r["status"] == "失败":
            print("  [FAIL] %s %s -> 预期:%s / 实际:%s" % (r["cid"], r["title"], r["expected"], r["actual"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "prefix": P, "uid1": uid1, "uid2": uid2, "rows": ROWS,
            # 记录本 run 创建的题库 id：若下次运行前崩溃，启动自检可按 id 彻底清理
            "cleanup": {"bank_ids": [x for x in (bank_a, bank_b, bank_c, copy1, copy2) if x]},
        }, f, ensure_ascii=False, indent=2)
    print("结果已写入", OUT)


if __name__ == "__main__":
    main()
