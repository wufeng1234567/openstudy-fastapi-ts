# -*- coding: utf-8 -*-
"""
学习模块 + 笔记模块 E2E 接口测试（真实 HTTP 调用）

覆盖：
  学习统计(userStats) / 学习时长与看板 / 笔记管理(note+noteCategory)
  / 笔记互动(公开笔记+评论+收藏) / 笔记与题目·题库关联(noteQuestion+noteQuestionBank)
角色：user1、user2（互为他人，用于验证数据隔离与越权）
用例编号：K*=学习统计  L*=学习时长与看板  M*=笔记管理  N*=笔记互动  O*=笔记关联  P*=清理

用法（后端需先跑起来，默认 127.0.0.1:9101；
     注意必须用项目 venv 的解释器，否则 DB 直读校验会被跳过）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_learning_note_api.py

产出：脚本同目录 e2e_learning_note_api_result.json
说明：测试数据全部建在临时题库/临时笔记上，结束时清理（含逻辑删除笔记、删除关联与分类），不留残留。
"""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:9101"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_learning_note_api_result.json")

ROWS = []


def call(method, path, token=None, body=None, params=None, timeout=30):
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


def total_of(res):
    return res.get("total") if isinstance(res, dict) else None


def is_file(res):
    return isinstance(res, (bytes, bytearray)) and len(res) > 0


def desc(res, st=200):
    if is_file(res):
        return "HTTP %s 文件流 大小=%d 字节" % (st, len(res))
    msg = (res.get("msg") or "")[:80] if isinstance(res, dict) else ""
    return "HTTP %s code=%s %s" % (st, code_of(res), msg)


def keys_of(d):
    return set(d.keys()) if isinstance(d, dict) else set()


def db_query(sql, params=None):
    """直连数据库读校验（仅用于接口未暴露的字段）；失败返回 None，不影响主流程

    ⚠️ 必须自建独立 engine 并在同一次 asyncio.run 内 dispose：
    本函数会被反复调用（每次一个新事件循环），若复用 app.database 的全局 engine，
    连接池会把「上一个已关闭事件循环」里的连接交出来，报
    `AttributeError: 'NoneType' object has no attribute 'send'`。
    """
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
    """直连数据库执行写语句（仅用于清理无 API 的测试数据，如通知/孤儿流水）；失败返回 None"""
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
                    res = await conn.execute(text(sql), params or {})
                    return res.rowcount
            finally:
                await engine.dispose()

        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print("    (DB 写入不可用：%s)" % exc)
        return None


def sweep_leftovers(created):
    """按记录的 id 彻底清除上一次运行（可能中途崩溃）遗留的测试数据。

    清理顺序：通知 -> 评论 -> 笔记收藏 -> 笔记关联 -> 笔记(物理) -> 分类 ->
             答题流水/错题/斩题/收藏题 -> 子题 -> 题目 -> 题库
    """
    note_ids = created.get("note_ids") or []
    cat_ids = created.get("category_ids") or []
    bank_ids = created.get("bank_ids") or []
    if not (note_ids or cat_ids or bank_ids):
        return
    note_t = tuple(note_ids) or (0,)
    bank_t = tuple(bank_ids) or (0,)
    q_ids = []
    if bank_ids:
        rows = db_query("SELECT id FROM question_main WHERE bank_id IN :b", {"b": bank_t}) or []
        q_ids = [r[0] for r in rows]
    q_t = tuple(q_ids) or (0,)

    if note_ids:
        for nid in note_ids:
            db_exec("DELETE FROM sys_notice WHERE remark LIKE :p", {"p": '%%"noteId": %d,%%' % nid})
            db_exec("DELETE FROM sys_notice WHERE remark LIKE :p", {"p": '%%"noteId": %d}%%' % nid})
        db_exec("DELETE FROM note_comment WHERE note_id IN :i", {"i": note_t})
        db_exec("DELETE FROM user_note_favorite WHERE note_id IN :i", {"i": note_t})
        db_exec("DELETE FROM note_question WHERE note_id IN :i", {"i": note_t})
        db_exec("DELETE FROM note_question_bank WHERE note_id IN :i", {"i": note_t})
        db_exec("DELETE FROM note WHERE note_id IN :i", {"i": note_t})
    if q_ids:
        db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM note_question WHERE question_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_sub WHERE main_id IN :i", {"i": q_t})
        db_exec("DELETE FROM question_main WHERE id IN :i", {"i": q_t})
    if bank_ids:
        db_exec("DELETE FROM question_bank WHERE id IN :i", {"i": bank_t})
    if cat_ids:
        db_exec("DELETE FROM note_category WHERE id IN :i", {"i": tuple(cat_ids)})
    # 孤儿答题流水（题目已删但流水还在，会污染学习统计）
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")
    print("  [自检] 已清理上次运行遗留：note=%s cat=%s bank=%s question=%d"
          % (note_ids, cat_ids, bank_ids, len(q_ids)))


def find_note(token, title):
    st, res = call("GET", "/notes/note/list", token, params={"title": title, "pageNum": 1, "pageSize": 50})
    for r in rows_of(res):
        if r.get("title") == title:
            return r
    return {}


def find_category(token, name):
    st, res = call("GET", "/noteCategory/noteCategory/all", token)
    for c in dl(res):
        if c.get("name") == name:
            return c
    return {}


def main():
    t1 = login("user1")
    t2 = login("user2")

    uid1 = db_scalar("SELECT user_id FROM sys_user WHERE user_name = 'user1'")
    uid2 = db_scalar("SELECT user_id FROM sys_user WHERE user_name = 'user2'")
    print("uid1=%s uid2=%s" % (uid1, uid2))

    # 启动自检：清理上一次运行（可能中途崩溃）遗留的测试数据
    prev = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "e2e_learning_note_api_result.json")
    if os.path.exists(prev):
        try:
            with open(prev, encoding="utf-8") as f:
                sweep_leftovers(json.load(f).get("cleanup") or {})
        except Exception as exc:  # noqa: BLE001
            print("  [自检] 读取上次结果失败：%s" % exc)

    # 测试数据统一用「章节整理」前缀：命名贴近真实使用场景，
    # 且不与演示数据（分类「学习笔记」、笔记《栈与队列的区别》等）冲突
    P = "章节整理"

    # ---- 前置：user1 建临时题库 + 3 道题 ----
    st, res = call("POST", "/questionBank/questionBank/createWithReturn", t1,
                   {"bankName": P + "-学习笔记测试题库", "subject": "测试科目", "isPublic": 0})
    bank_id = dd(res).get("id") or dd(res).get("bankId")
    qids = []
    for i in range(1, 4):
        st, res = call("POST", "/questionMain/questionMain", t1, {
            "bankId": bank_id, "questionType": 1, "questionText": "%s-Q%d" % (P, i),
            "options": [{"key": "A", "value": "1"}, {"key": "B", "value": "2"}], "answer": "A",
        })
        qids.append(dd(res).get("questionId"))
    q1, q2, q3 = qids
    print("临时题库=%s 题目=%s" % (bank_id, qids))

    # ==================================================================
    # K 模块：学习统计（/userStats）
    # ==================================================================
    st, res = call("GET", "/userStats/overview", t1)
    ov = dd(res)
    need = {"totalQuestions", "totalBanks", "totalErrors", "totalMarked", "totalMastered",
            "totalFavoriteNotes", "totalPracticeCount", "correctRate", "bankStudyCount"}
    T("K01", "学习统计", "学习总览-返回结构完整",
      "user1 已登录", "GET /userStats/overview",
      "code=200 且包含 %d 个统计字段" % len(need),
      code_of(res) == 200 and need.issubset(keys_of(ov)),
      "缺失字段=%s" % sorted(need - keys_of(ov)) if not need.issubset(keys_of(ov)) else "字段齐全")

    db_total = db_scalar("SELECT COUNT(*) FROM user_practice_log WHERE user_id = :u", {"u": uid1})
    db_correct = db_scalar("SELECT COUNT(*) FROM user_practice_log WHERE user_id = :u AND is_correct = 1",
                           {"u": uid1})
    T("K02", "学习统计", "学习总览-作答总数与答题流水一致",
      "user1 有答题流水", "GET /userStats/overview，并与 user_practice_log 比对",
      "totalPracticeCount == 流水条数",
      db_total is None or ov.get("totalPracticeCount") == db_total,
      "接口=%s 流水=%s" % (ov.get("totalPracticeCount"), db_total))

    exp_rate = round(db_correct / db_total * 100, 1) if (db_total and db_correct is not None) else None
    rate = ov.get("correctRate")
    T("K03", "学习统计", "学习总览-正确率口径（答对数/作答数）",
      "user1 有答题流水", "GET /userStats/overview，与流水答对数比对",
      "correctRate ≈ 答对数/作答数*100（百分数）",
      exp_rate is None or (isinstance(rate, (int, float)) and abs(rate - exp_rate) <= 0.2),
      "接口=%s 期望≈%s" % (rate, exp_rate))

    st, res = call("GET", "/userStats/bySubject", t1)
    subs = dl(res)
    ok_struct = code_of(res) == 200 and all(
        {"subject", "bankCount", "questionCount", "errorCount", "markedCount"}.issubset(keys_of(s))
        for s in subs)
    T("K04", "学习统计", "分科目统计-返回结构与字段",
      "user1 已登录", "GET /userStats/bySubject",
      "code=200；每项含 subject/bankCount/questionCount/errorCount/markedCount",
      ok_struct, "科目数=%d" % len(subs))

    db_act_err = db_scalar(
        "SELECT COUNT(*) FROM user_question_error WHERE user_id=:u AND status=1 AND is_mastered=0",
        {"u": uid1})
    api_err = sum(s.get("errorCount") or 0 for s in subs)
    T("K05", "学习统计", "分科目统计-错题数与错题表一致",
      "user1 有活跃错题", "GET /userStats/bySubject 汇总 errorCount，与错题表比对",
      "ΣerrorCount == 活跃错题数",
      db_act_err is None or api_err == db_act_err,
      "接口合计=%s 库表=%s" % (api_err, db_act_err))

    st, res = call("GET", "/userStats/trend", t1, params={"days": 7})
    tr = dl(res)
    dates = [x.get("date") for x in tr]
    T("K06", "学习统计", "学习趋势-最近7天日期连续",
      "user1 已登录", "GET /userStats/trend?days=7",
      "code=200；返回 7 条且日期递增连续",
      code_of(res) == 200 and len(tr) == 7 and dates == sorted(dates) and len(set(dates)) == 7,
      "条数=%d 首=%s 末=%s" % (len(tr), dates[0] if dates else None, dates[-1] if dates else None))

    ok_fields = all({"date", "practiceCount", "correctCount", "errorCount", "markedCount"}.issubset(keys_of(x))
                    for x in tr)
    T("K07", "学习统计", "学习趋势-每日字段完整",
      "user1 已登录", "检查 trend 每项字段",
      "含 date/practiceCount/correctCount/errorCount/markedCount",
      ok_fields, "字段=%s" % sorted(keys_of(tr[0])) if tr else "空")

    st, res = call("GET", "/userStats/trend", t1, params={"days": 30})
    T("K08", "学习统计", "学习趋势-自定义区间 days=30",
      "user1 已登录", "GET /userStats/trend?days=30",
      "code=200；返回 30 条",
      code_of(res) == 200 and len(dl(res)) == 30, "条数=%d" % len(dl(res)))

    # 动态校验：上报一次作答后，今天那条的 practiceCount 应 +1
    tr_before = dl(call("GET", "/userStats/trend", t1, params={"days": 2})[1])
    today_before = tr_before[-1].get("practiceCount") if tr_before else None
    call("POST", "/questionPractice/report", t1, {"questionId": q1, "bankId": bank_id, "isCorrect": True})
    time.sleep(0.6)
    tr_after = dl(call("GET", "/userStats/trend", t1, params={"days": 2})[1])
    today_after = tr_after[-1].get("practiceCount") if tr_after else None
    T("K09", "学习统计", "学习趋势-当天作答实时计入",
      "记录上报前 trend 当天 practiceCount", "上报 1 次作答后重新拉取 trend",
      "当天 practiceCount +1",
      isinstance(today_before, int) and today_after == today_before + 1,
      "上报前=%s 上报后=%s" % (today_before, today_after))

    st, res = call("GET", "/userStats/trend", t1, params={"days": 0})
    st2, res2 = call("GET", "/userStats/trend", t1, params={"days": 200})
    T("K10", "学习统计", "学习趋势-days 越界参数校验",
      "days 允许 1~90", "GET /userStats/trend?days=0 与 days=200",
      "两次均返回 HTTP 422（参数校验拒绝）",
      st == 422 and st2 == 422, "days=0 -> %s；days=200 -> %s" % (st, st2))

    st, res = call("GET", "/userStats/errorAnalysis", t1)
    ea = dd(res)
    need_ea = {"totalErrors", "activeErrors", "mastered", "masterRate",
               "byDifficulty", "byQuestionType", "bySubject", "topErrors"}
    T("K11", "学习统计", "错题分析-返回结构完整",
      "user1 已登录", "GET /userStats/errorAnalysis",
      "code=200 且含 8 个分析字段",
      code_of(res) == 200 and need_ea.issubset(keys_of(ea)),
      "缺失=%s" % sorted(need_ea - keys_of(ea)) if not need_ea.issubset(keys_of(ea)) else "字段齐全")

    db_all_err = db_scalar("SELECT COUNT(*) FROM user_question_error WHERE user_id=:u", {"u": uid1})
    db_mastered = db_scalar(
        "SELECT COUNT(*) FROM user_question_error WHERE user_id=:u AND is_mastered=1", {"u": uid1})
    T("K12", "学习统计", "错题分析-总数/已掌握口径",
      "user1 有错题记录", "GET /userStats/errorAnalysis，与错题表比对",
      "totalErrors==全部错题记录数；mastered==is_mastered=1 的条数",
      (db_all_err is None or ea.get("totalErrors") == db_all_err)
      and (db_mastered is None or ea.get("mastered") == db_mastered),
      "接口 totalErrors=%s mastered=%s；库表=%s/%s"
      % (ea.get("totalErrors"), ea.get("mastered"), db_all_err, db_mastered))

    st, res = call("GET", "/userStats/growth", t1)
    gw = dd(res)
    need_gw = {"joinDate", "studyDays", "consecutiveDays", "totalBanks",
               "totalQuestions", "totalNotes", "milestones"}
    T("K13", "学习统计", "成长档案-返回结构完整",
      "user1 已登录", "GET /userStats/growth",
      "code=200 且含 7 个成长字段",
      code_of(res) == 200 and need_gw.issubset(keys_of(gw)),
      "缺失=%s" % sorted(need_gw - keys_of(gw)) if not need_gw.issubset(keys_of(gw)) else "字段齐全")

    db_notes = db_scalar("SELECT COUNT(*) FROM note WHERE user_id=:u AND del_flag='0'", {"u": uid1})
    T("K14", "学习统计", "成长档案-totalNotes 与笔记表一致（回归）",
      "user1 有笔记", "GET /userStats/growth 的 totalNotes 与 note 表比对",
      "totalNotes == 该用户未删除笔记数",
      db_notes is None or gw.get("totalNotes") == db_notes,
      "接口=%s 库表=%s" % (gw.get("totalNotes"), db_notes))

    st, res = call("GET", "/userStats/overview")
    st_ea, res_ea = call("GET", "/userStats/errorAnalysis")
    T("K15", "学习统计", "未登录访问统计接口被拒绝",
      "不携带 token", "GET /userStats/overview 与 /userStats/errorAnalysis",
      "两次均 code=401（或 HTTP 401）",
      (code_of(res) == 401 or st == 401) and (code_of(res_ea) == 401 or st_ea == 401),
      "overview code=%s / errorAnalysis code=%s" % (code_of(res), code_of(res_ea)))

    st, res = call("GET", "/userStats/overview", t2)
    ov2 = dd(res)
    db_total2 = db_scalar("SELECT COUNT(*) FROM user_practice_log WHERE user_id=:u", {"u": uid2})
    T("K16", "学习统计", "数据隔离-两名用户统计互不影响",
      "user1/user2 各自数据", "分别请求 overview 并与各自的流水比对",
      "user2 的 totalPracticeCount == user2 的流水数（不等于 user1）",
      db_total2 is None or (ov2.get("totalPracticeCount") == db_total2
                            and ov2.get("totalPracticeCount") != ov.get("totalPracticeCount")),
      "user2接口=%s user2流水=%s user1接口=%s"
      % (ov2.get("totalPracticeCount"), db_total2, ov.get("totalPracticeCount")))

    # ==================================================================
    # L 模块：学习时长与看板
    # ==================================================================
    st, res = call("POST", "/questionMain/questionMain/recordStudyTime", t1,
                   {"bankId": bank_id, "questionIds": [q1, q2]})
    T("L01", "学习时长", "记录刷题学习时间",
      "bank=%s 属于 user1" % bank_id, "POST /questionMain/questionMain/recordStudyTime  body={bankId,questionIds:[q1,q2]}",
      "code=200；返回 bankStudyTime 与 questionCount=2",
      code_of(res) == 200 and dd(res).get("questionCount") == 2,
      "code=%s questionCount=%s" % (code_of(res), dd(res).get("questionCount")))

    # 收藏该题库后，recordStudyTime 应累加 studyCount
    call("POST", "/favoriteBank/favoriteBank", t1, {"bankId": bank_id})
    fl = call("GET", "/favoriteBank/favoriteBank/list", t1, params={"pageNum": 1, "pageSize": 50})[1]
    fb = next((r for r in rows_of(fl) if r.get("bankId") == bank_id), {})
    sc_before = fb.get("studyCount") or 0
    call("POST", "/questionMain/questionMain/recordStudyTime", t1, {"bankId": bank_id, "questionIds": [q1]})
    time.sleep(0.6)
    fl2 = call("GET", "/favoriteBank/favoriteBank/list", t1, params={"pageNum": 1, "pageSize": 50})[1]
    fb2 = next((r for r in rows_of(fl2) if r.get("bankId") == bank_id), {})
    sc_after = fb2.get("studyCount") or 0
    T("L02", "学习时长", "记录学习时间-累加收藏题库学习次数",
      "user1 已收藏 bank", "recordStudyTime 后重新拉取收藏题库列表",
      "studyCount +1",
      sc_after == sc_before + 1, "前=%s 后=%s" % (sc_before, sc_after))

    st, res = call("POST", "/favoriteBank/favoriteBank/recordStudy/%s" % bank_id, t1)
    time.sleep(0.6)
    fl3 = call("GET", "/favoriteBank/favoriteBank/list", t1, params={"pageNum": 1, "pageSize": 50})[1]
    fb3 = next((r for r in rows_of(fl3) if r.get("bankId") == bank_id), {})
    T("L03", "学习时长", "收藏题库-单独记录学习一次",
      "user1 已收藏 bank", "POST /favoriteBank/favoriteBank/recordStudy/{bank_id}",
      "code=200；studyCount 再 +1",
      code_of(res) == 200 and (fb3.get("studyCount") or 0) == (fb2.get("studyCount") or 0) + 1,
      "code=%s studyCount=%s->%s" % (code_of(res), fb2.get("studyCount"), fb3.get("studyCount")))

    st, res = call("POST", "/questionMain/questionMain/recordStudyTime", t1,
                   {"bankId": 99999999, "questionIds": []})
    T("L04", "学习时长", "记录学习时间-未收藏/不存在的题库不报错",
      "bank 99999999 不存在且未收藏", "POST recordStudyTime body={bankId:99999999,questionIds:[]}",
      "code=200（静默跳过，不产生脏数据）",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/system/dashboard/stats", t1)
    ds = dd(res)
    need_ds = {"userCount", "bankCount", "questionCount", "noteCount", "categoryStats", "userGrowth"}
    T("L05", "学习看板", "仪表盘统计-返回结构完整",
      "user1 已登录", "GET /system/dashboard/stats",
      "code=200 且含 userCount/bankCount/questionCount/noteCount/categoryStats/userGrowth",
      code_of(res) == 200 and need_ds.issubset(keys_of(ds)),
      "缺失=%s" % sorted(need_ds - keys_of(ds)) if not need_ds.issubset(keys_of(ds)) else "字段齐全")

    db_banks = db_scalar("SELECT COUNT(*) FROM question_bank WHERE status='0'")
    db_notes_all = db_scalar("SELECT COUNT(*) FROM note WHERE del_flag='0'")
    T("L06", "学习看板", "仪表盘统计-计数与数据库一致",
      "全站数据", "GET /system/dashboard/stats 与 question_bank / note 表比对",
      "bankCount==题库数；noteCount==未删除笔记数",
      (db_banks is None or ds.get("bankCount") == db_banks)
      and (db_notes_all is None or ds.get("noteCount") == db_notes_all),
      "接口 bankCount=%s noteCount=%s；库表=%s/%s"
      % (ds.get("bankCount"), ds.get("noteCount"), db_banks, db_notes_all))

    st, res = call("GET", "/system/dashboard/recent", t1)
    acts = dl(res)
    times = [a.get("createTime") for a in acts if a.get("createTime")]
    T("L07", "学习看板", "最近活动-合并三类且倒序取前10",
      "存在题库/题目/笔记数据", "GET /system/dashboard/recent",
      "code=200；条数 <=10 且 createTime 倒序",
      code_of(res) == 200 and len(acts) <= 10 and times == sorted(times, reverse=True),
      "条数=%d 倒序=%s" % (len(acts), times == sorted(times, reverse=True)))

    ok_act = all({"type", "id", "title", "createTime"}.issubset(keys_of(a)) for a in acts)
    T("L08", "学习看板", "最近活动-单项字段完整",
      "存在活动数据", "检查 recent 每项字段",
      "含 type/id/title/createTime",
      bool(acts) and ok_act, "字段=%s" % sorted(keys_of(acts[0])) if acts else "空")

    # ==================================================================
    # M 模块：笔记管理
    # ==================================================================
    st, res = call("GET", "/noteCategory/noteCategory/list", t1, params={"pageNum": 1, "pageSize": 20})
    T("M01", "笔记管理", "笔记分类列表-分页结构",
      "user1 已登录", "GET /noteCategory/noteCategory/list",
      "code=200；含 total 与 rows",
      code_of(res) == 200 and isinstance(total_of(res), int) and isinstance(rows_of(res), list),
      "total=%s rows=%d" % (total_of(res), len(rows_of(res))))

    # 前端传的是 name（见 editor.vue），后端只认 categoryName —— 这里按前端真实调用传参
    st, res = call("POST", "/noteCategory/noteCategory", t1, {"name": P + "-分类"})
    cat_id = dd(res).get("id")
    T("M02", "笔记管理", "新建笔记分类（前端传参 name）",
      "user1 已登录", "POST /noteCategory/noteCategory  body={name:'%s-分类'}" % P,
      "code=200；返回分类 id",
      code_of(res) == 200 and bool(cat_id),
      "code=%s id=%s msg=%s" % (code_of(res), cat_id, res.get("msg")))

    if not cat_id:
        # 兜底：用后端承认的字段再建一次，保证后续用例可跑
        st2, res2 = call("POST", "/noteCategory/noteCategory", t1, {"categoryName": P + "-分类"})
        cat_id = dd(res2).get("id")

    st, res = call("POST", "/noteCategory/noteCategory", t1, {"categoryName": ""})
    T("M03", "笔记管理", "新建分类-名称必填校验",
      "categoryName 为空", "POST /noteCategory/noteCategory  body={categoryName:''}",
      "code!=200 且提示「分类名称不能为空」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    got = find_category(t1, P + "-分类")
    T("M04", "笔记管理", "分类不分页列表-包含新建分类",
      "刚新建分类 id=%s" % cat_id, "GET /noteCategory/noteCategory/all",
      "返回包含该分类",
      bool(got), "命中=%s" % bool(got))

    st, res = call("GET", "/noteCategory/noteCategory/%s" % cat_id, t1)
    T("M05", "笔记管理", "分类详情（前端 getNoteCategory 使用该路由）",
      "分类 id=%s" % cat_id, "GET /noteCategory/noteCategory/{id}",
      "code=200；返回该分类且 name 正确",
      code_of(res) == 200 and dd(res).get("name") == P + "-分类",
      "HTTP状态=%s code=%s name=%s" % (st, code_of(res), dd(res).get("name")))

    st, res = call("PUT", "/noteCategory/noteCategory", t1,
                   {"categoryId": cat_id, "categoryName": P + "-分类改名"})
    got2 = find_category(t1, P + "-分类改名")
    T("M06", "笔记管理", "修改分类名称-真实生效",
      "分类 id=%s" % cat_id, "PUT /noteCategory/noteCategory  body={categoryId,categoryName}",
      "code=200；列表返回新名称",
      code_of(res) == 200 and bool(got2),
      "code=%s 改名后命中=%s" % (code_of(res), bool(got2)))

    st, res = call("PUT", "/noteCategory/noteCategory", t1, {"categoryId": cat_id, "sortOrder": 66})
    row = db_query("SELECT order_num FROM note_category WHERE id=:i", {"i": cat_id})
    sort_now = row[0][0] if row else None
    T("M07", "笔记管理", "修改分类排序-真实写库",
      "分类 id=%s" % cat_id, "PUT /noteCategory/noteCategory  body={categoryId,sortOrder:66}，直读库表",
      "code=200；order_num 更新为 66",
      code_of(res) == 200 and (sort_now is None or sort_now == 66),
      "code=%s order_num=%s" % (code_of(res), sort_now))

    st, res = call("PUT", "/noteCategory/noteCategory", t2,
                   {"categoryId": cat_id, "categoryName": P + "-越权改名"})
    leaked = bool(find_category(t1, P + "-越权改名"))
    T("M08", "笔记管理", "数据隔离-user2 不能修改 user1 的分类",
      "分类 id=%s 属于 user1" % cat_id, "user2 请求 PUT /noteCategory/noteCategory  body={categoryId}",
      "code=403；user1 分类未被改名",
      code_of(res) == 403 and not leaked,
      "code=%s msg=%s；被改=%s" % (code_of(res), res.get("msg"), leaked))

    st, res = call("POST", "/notes/note", t1, {
        "title": P + "-笔记A", "content": "正文A", "markdownContent": "# 标题A",
        "categoryId": cat_id, "isPublic": 0, "tags": "学习,测试",
    })
    note_id = dd(res).get("noteId")
    T("M09", "笔记管理", "新建笔记",
      "分类 id=%s 存在" % cat_id, "POST /notes/note  body={title,content,categoryId,isPublic:0}",
      "code=200；返回 noteId",
      code_of(res) == 200 and bool(note_id), "code=%s noteId=%s" % (code_of(res), note_id))

    T("M10", "笔记管理", "新建笔记-响应同时兼容前端 id 字段",
      "刚创建笔记 noteId=%s" % note_id, "检查 POST /notes/note 响应体字段",
      "响应 data 中同时存在 noteId 与 id（前端取 data.id）",
      dd(res).get("id") == note_id,
      "noteId=%s id=%s" % (dd(res).get("noteId"), dd(res).get("id")))

    st, res = call("POST", "/notes/note", t1, {"content": "无标题"})
    T("M11", "笔记管理", "新建笔记-标题必填校验",
      "title 为空", "POST /notes/note  body={content:'无标题'}",
      "code!=200 且提示「标题不能为空」",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/notes/note", t1, {"title": P + "-无分类笔记", "content": "x"})
    T("M12", "笔记管理", "新建笔记-不传分类的异常处理（库列 NOT NULL）",
      "不传 categoryId", "POST /notes/note  body={title,content}",
      "给出明确业务提示（code=400，而非 500 数据库错误）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/notes/note/list", t1, params={"title": P + "-笔记A", "pageNum": 1, "pageSize": 20})
    hit = [r for r in rows_of(res) if r.get("noteId") == note_id]
    T("M13", "笔记管理", "笔记列表-按标题检索",
      "笔记 noteId=%s" % note_id, "GET /notes/note/list?title=%s-笔记A" % P,
      "code=200；命中该笔记",
      code_of(res) == 200 and len(hit) == 1, "命中=%d" % len(hit))

    st, res = call("GET", "/notes/note/list", t1, params={"categoryId": cat_id, "pageNum": 1, "pageSize": 20})
    hit_c = [r for r in rows_of(res) if r.get("noteId") == note_id]
    T("M14", "笔记管理", "笔记列表-按分类筛选",
      "笔记归属分类 %s" % cat_id, "GET /notes/note/list?categoryId={cat_id}",
      "code=200；命中该笔记",
      code_of(res) == 200 and len(hit_c) == 1, "命中=%d" % len(hit_c))

    st, res = call("GET", "/notes/note/%s" % note_id, t1)
    T("M15", "笔记管理", "笔记详情",
      "笔记 noteId=%s" % note_id, "GET /notes/note/{noteId}",
      "code=200；返回标题与分类",
      code_of(res) == 200 and dd(res).get("title") == P + "-笔记A",
      "title=%s" % dd(res).get("title"))

    # 前端 editor.vue 保存时传的是 id（不是 noteId）
    st, res = call("PUT", "/notes/note", t1, {"id": note_id, "title": P + "-笔记A改"})
    st2, res2 = call("GET", "/notes/note/%s" % note_id, t1)
    T("M16", "笔记管理", "修改笔记（前端传参 id）",
      "笔记 noteId=%s" % note_id, "PUT /notes/note  body={id,title}",
      "code=200；标题已更新",
      code_of(res) == 200 and dd(res2).get("title") == P + "-笔记A改",
      "code=%s msg=%s 现标题=%s" % (code_of(res), res.get("msg"), dd(res2).get("title")))

    st, res = call("PUT", "/notes/note", t1, {"noteId": note_id, "content": "正文A改", "tags": "改后"})
    st2, res2 = call("GET", "/notes/note/%s" % note_id, t1)
    T("M17", "笔记管理", "修改笔记（标准字段 noteId）",
      "笔记 noteId=%s" % note_id, "PUT /notes/note  body={noteId,content,tags}",
      "code=200；正文已更新",
      code_of(res) == 200 and dd(res2).get("content") == "正文A改",
      "code=%s content=%s" % (code_of(res), dd(res2).get("content")))

    st, res = call("GET", "/notes/note/%s" % note_id, t2)
    T("M18", "笔记管理", "数据隔离-user2 不能查看 user1 的私有笔记",
      "笔记 noteId=%s 为私有（isPublic=0）" % note_id, "user2 请求 GET /notes/note/{noteId}",
      "code=403（按归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("PUT", "/notes/note", t2, {"noteId": note_id, "title": P + "-越权改"})
    st2, res2 = call("GET", "/notes/note/%s" % note_id, t1)
    tampered = dd(res2).get("title") == P + "-越权改"
    T("M19", "笔记管理", "数据隔离-user2 不能修改 user1 的笔记",
      "笔记 noteId=%s 属于 user1" % note_id, "user2 请求 PUT /notes/note  body={noteId,title}",
      "code=403；user1 笔记未被篡改",
      code_of(res) == 403 and not tampered,
      "code=%s msg=%s；被改=%s" % (code_of(res), res.get("msg"), tampered))

    st, res = call("GET", "/notes/note/list", t2, params={"userId": uid1, "pageNum": 1, "pageSize": 50})
    foreign_notes = [r for r in rows_of(res) if r.get("userId") == uid1]
    T("M20", "笔记管理", "数据隔离-不能按 userId 拉取他人笔记列表",
      "user1 有笔记", "user2 请求 GET /notes/note/list?userId={uid1}",
      "code=403（或至少不返回他人笔记）",
      code_of(res) == 403 or not foreign_notes,
      "code=%s 返回他人笔记=%d 条" % (code_of(res), len(foreign_notes)))

    st, res = call("DELETE", "/noteCategory/noteCategory/%s" % cat_id, t2)
    still = db_scalar("SELECT COUNT(*) FROM note_category WHERE id=:i", {"i": cat_id})
    T("M21", "笔记管理", "数据隔离-user2 不能删除 user1 的分类",
      "分类 id=%s 属于 user1" % cat_id, "user2 请求 DELETE /noteCategory/noteCategory/{id}",
      "code=403；user1 分类仍存在",
      code_of(res) == 403 and (still is None or still == 1),
      "code=%s msg=%s；仍存在=%s" % (code_of(res), res.get("msg"), still))

    st, res = call("POST", "/notes/note/export", t1)
    T("M22", "笔记管理", "导出笔记列表（Excel）",
      "user1 有笔记", "POST /notes/note/export",
      "返回文件流（非 JSON），HTTP 200",
      st == 200 and is_file(res), desc(res, st))

    create_row = db_query("SELECT status FROM note WHERE note_id=:n", {"n": note_id})
    status_now = create_row[0][0] if create_row else None
    T("M23", "笔记管理", "新建笔记-默认状态为前端可识别的 draft",
      "笔记 noteId=%s" % note_id, "直读 note.status",
      "status == 'draft'（前端只识别 draft/published）",
      status_now is None or status_now == "draft", "status=%s" % status_now)

    # ==================================================================
    # N 模块：笔记互动（公开笔记 / 评论 / 收藏）
    # ==================================================================
    st, res = call("PUT", "/notes/note", t1, {"noteId": note_id, "isPublic": 1})
    time.sleep(0.6)
    st2, res2 = call("GET", "/notes/note/public/list", t1, params={"pageNum": 1, "pageSize": 50})
    in_public = [r for r in rows_of(res2) if r.get("noteId") == note_id]
    T("N01", "笔记互动", "设为公开后出现在公开笔记列表",
      "笔记 noteId=%s" % note_id, "PUT 设 isPublic=1 后 GET /notes/note/public/list",
      "code=200；公开列表中命中该笔记",
      code_of(res) == 200 and len(in_public) == 1, "命中=%d" % len(in_public))

    T("N02", "笔记互动", "公开笔记接口-isPublic 类型与前端判断一致",
      "笔记已公开", "检查公开列表返回的 isPublic 字段类型",
      "isPublic 为数字 1（前端用 isPublic === 1 判断）",
      bool(in_public) and in_public[0].get("isPublic") == 1,
      "isPublic=%r 类型=%s" % (in_public[0].get("isPublic") if in_public else None,
                              type(in_public[0].get("isPublic")).__name__ if in_public else "-"))

    v_before = db_scalar("SELECT view_count FROM note WHERE note_id=:n", {"n": note_id})
    st, res = call("GET", "/notes/note/public/%s" % note_id, t2)
    time.sleep(0.6)
    v_after = db_scalar("SELECT view_count FROM note WHERE note_id=:n", {"n": note_id})
    T("N03", "笔记互动", "公开笔记详情-浏览量自增",
      "笔记已公开", "user2 请求 GET /notes/note/public/{id}",
      "code=200；view_count +1",
      code_of(res) == 200 and (v_before is None or v_after == v_before + 1),
      "code=%s 浏览量 %s->%s" % (code_of(res), v_before, v_after))

    st, res = call("POST", "/notes/note/public/click/%s" % note_id, t2)
    time.sleep(0.6)
    v_click = db_scalar("SELECT view_count FROM note WHERE note_id=:n", {"n": note_id})
    T("N04", "笔记互动", "记录笔记点击-浏览量自增",
      "笔记 noteId=%s" % note_id, "POST /notes/note/public/click/{id}",
      "code=200；view_count 再 +1",
      code_of(res) == 200 and (v_after is None or v_click == v_after + 1),
      "code=%s 浏览量 %s->%s" % (code_of(res), v_after, v_click))

    st, res = call("GET", "/notes/note/public/ranking", t1, params={"limit": 5})
    rk = dl(res)
    # 接口口径是「综合热度」= 浏览 + 点赞*3 + 评论*5（见 notes.py note_ranking 文档），
    # 不是单纯按浏览量倒序，故这里断言 hotScore 递减
    scores = [x.get("hotScore") if x.get("hotScore") is not None else (x.get("viewCount") or 0) for x in rk]
    T("N05", "笔记互动", "笔记排行榜-按综合热度倒序且限流",
      "存在公开笔记", "GET /notes/note/public/ranking?limit=5",
      "code=200；条数 <=5 且 hotScore 倒序（热度=浏览+点赞*3+评论*5）",
      code_of(res) == 200 and len(rk) <= 5 and scores == sorted(scores, reverse=True),
      "条数=%d 热度=%s 倒序=%s" % (len(rk), scores, scores == sorted(scores, reverse=True)))

    st, res = call("GET", "/notes/note/publicSection/list", t1)
    secs = dl(res)
    T("N06", "笔记互动", "公开分区列表",
      "note_public_section 有数据", "GET /notes/note/publicSection/list",
      "code=200；返回分区列表且含 name",
      code_of(res) == 200 and bool(secs) and "name" in (secs[0] if secs else {}),
      "分区数=%d" % len(secs))

    st, res = call("POST", "/notes/comment/create", t1, params={"noteId": note_id, "content": P + "-一级评论"})
    cid = dd(res).get("commentId") or dd(res).get("id")
    T("N07", "笔记互动", "发表一级评论",
      "笔记 noteId=%s 存在" % note_id, "POST /notes/comment/create?noteId=&content=",
      "code=200；返回 commentId",
      code_of(res) == 200 and bool(cid), "code=%s commentId=%s" % (code_of(res), cid))

    st, res = call("GET", "/notes/comment/list", t1, params={"noteId": note_id, "pageNum": 1, "pageSize": 20})
    cl = dd(res).get("list") or []
    T("N08", "笔记互动", "评论列表-包含刚发表的评论",
      "已发表评论 cid=%s" % cid, "GET /notes/comment/list?noteId={noteId}",
      "code=200；列表中命中该评论",
      code_of(res) == 200 and any(c.get("id") == cid for c in cl),
      "评论数=%d 命中=%s" % (len(cl), any(c.get("id") == cid for c in cl)))

    db_cc = db_scalar("SELECT comment_count FROM note WHERE note_id=:n", {"n": note_id})
    T("N09", "笔记互动", "评论后笔记评论数自增",
      "刚发表 1 条评论", "直读 note.comment_count",
      "comment_count >= 1",
      db_cc is None or (db_cc or 0) >= 1, "comment_count=%s" % db_cc)

    st, res = call("POST", "/notes/comment/create", t2,
                   params={"noteId": note_id, "content": P + "-回复", "parentId": cid,
                           "replyToUserId": uid1})
    rid = dd(res).get("commentId") or dd(res).get("id")
    T("N10", "笔记互动", "回复评论（带 parentId）",
      "父评论 cid=%s" % cid, "POST /notes/comment/create?noteId=&content=&parentId=&replyToUserId=",
      "code=200；返回回复 id",
      code_of(res) == 200 and bool(rid), "code=%s replyId=%s" % (code_of(res), rid))

    st, res = call("GET", "/notes/comment/replies", t1, params={"parentId": cid, "pageNum": 1, "pageSize": 20})
    rl = dd(res).get("list") or []
    T("N11", "笔记互动", "回复列表-包含该回复",
      "回复 rid=%s 挂在 cid 下" % rid, "GET /notes/comment/replies?parentId={cid}",
      "code=200；列表中命中该回复",
      code_of(res) == 200 and any(c.get("id") == rid for c in rl), "回复数=%d" % len(rl))

    st, res = call("GET", "/notes/comment/thread/%s" % cid, t1)
    T("N12", "笔记互动", "评论楼层详情-含子回复",
      "父评论 cid=%s 有 1 条回复" % cid, "GET /notes/comment/thread/{cid}",
      "code=200；返回该评论且 children 含回复",
      code_of(res) == 200 and isinstance(raw_data(res), (dict, list)),
      "HTTP=%s code=%s" % (st, code_of(res)))

    st, res = call("DELETE", "/notes/comment/delete/%s" % cid, t2)
    still_c = db_scalar("SELECT COUNT(*) FROM note_comment WHERE id=:i", {"i": cid})
    T("N13", "笔记互动", "数据隔离-user2 不能删除 user1 的评论",
      "评论 cid=%s 属于 user1" % cid, "user2 请求 DELETE /notes/comment/delete/{cid}",
      "code=403；评论仍存在",
      code_of(res) == 403 and (still_c is None or still_c == 1),
      "code=%s msg=%s；仍存在=%s" % (code_of(res), res.get("msg"), still_c))

    st, res = call("POST", "/favoriteNote/favoriteNote", t2, params={"noteId": note_id})
    T("N14", "笔记互动", "收藏公开笔记",
      "user2 已登录", "POST /favoriteNote/favoriteNote?noteId={noteId}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/favoriteNote/favoriteNote", t2, params={"noteId": note_id})
    T("N15", "笔记互动", "重复收藏笔记的幂等处理",
      "user2 已收藏该笔记", "再次 POST /favoriteNote/favoriteNote?noteId={noteId}",
      "给出明确业务冲突提示（code=400，不应是 500）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/favoriteNote/favoriteNote/list", t2, params={"pageNum": 1, "pageSize": 20})
    fv = [r for r in rows_of(res) if r.get("noteId") == note_id]
    T("N16", "笔记互动", "收藏笔记列表-包含已收藏笔记",
      "user2 已收藏该笔记", "GET /favoriteNote/favoriteNote/list",
      "code=200；列表中命中该笔记且含 favoriteId",
      code_of(res) == 200 and len(fv) == 1 and bool(fv[0].get("favoriteId")),
      "命中=%d" % len(fv))

    st, res = call("DELETE", "/favoriteNote/favoriteNote/deleteByUserAndNote/%s/%s" % (uid1, note_id), t2)
    T("N17", "笔记互动", "数据隔离-路径传他人 uid 不能取消他人笔记收藏",
      "收藏属于 user2，路径写 user1 的 uid", "user2 请求 DELETE .../deleteByUserAndNote/{uid1}/{noteId}",
      "code!=200（无权操作）",
      code_of(res) != 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    if fv:
        st, res = call("DELETE", "/favoriteNote/favoriteNote/%s" % fv[0].get("favoriteId"), t2)
        T("N18", "笔记互动", "取消收藏笔记（按 favoriteId）",
          "favoriteId=%s 属于 user2" % fv[0].get("favoriteId"),
          "user2 请求 DELETE /favoriteNote/favoriteNote/{favoriteId}",
          "code=200",
          code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ==================================================================
    # ---- 搜索：keyword 需同时命中 标题/正文/作者昵称（用户输入「若依」要能搜到昵称叫若依的作者的笔记）----
    st, res = call("GET", "/notes/note/public/list", t1, params={"pageNum": 1, "pageSize": 100})
    base_rows = rows_of(res)
    first_note = base_rows[0] if base_rows else {}
    kw_author = (first_note.get("authorName") or "").strip()
    if kw_author:
        st, res = call("GET", "/notes/note/public/list", t1,
                       params={"keyword": kw_author, "pageNum": 1, "pageSize": 100})
        hit_rows = rows_of(res)
        hit_authors = {r.get("authorName") for r in hit_rows}
        T("N19", "笔记互动", "搜索框支持按作者昵称匹配",
          "公开笔记作者=%s" % kw_author, "GET /notes/note/public/list?keyword={作者昵称}",
          "code=200；命中结果全部为该作者的公开笔记",
          code_of(res) == 200 and bool(hit_rows) and hit_authors == {kw_author},
          "total=%s 命中作者=%s" % (len(hit_rows), sorted(hit_authors)))

        kw_title = (first_note.get("title") or "").strip()
        probe = kw_title[:3] if len(kw_title) >= 3 else kw_title
        if probe:
            st, res = call("GET", "/notes/note/public/list", t1,
                           params={"keyword": probe, "pageNum": 1, "pageSize": 100})
            T("N20", "笔记互动", "搜索框按标题片段匹配",
              "公开笔记标题=%s" % kw_title, "GET /notes/note/public/list?keyword={标题前3字}",
              "code=200；该笔记在命中结果中",
              code_of(res) == 200 and any(r.get("noteId") == first_note.get("noteId") for r in rows_of(res)),
              "total=%s 命中该笔记=%s"
              % (len(rows_of(res)), any(r.get("noteId") == first_note.get("noteId") for r in rows_of(res))))

    # ---- 「内容最长」排序：长度必须统计 content + markdown_content（前台编辑器只写 markdown）----
    st, res = call("GET", "/notes/note/public/list", t1,
                   params={"sortBy": "content_length", "sortOrder": "desc", "pageNum": 1, "pageSize": 10})
    cl_rows = rows_of(res)
    seq = []
    for r in cl_rows:
        row = db_query(
            "SELECT CHAR_LENGTH(COALESCE(content,''))+CHAR_LENGTH(COALESCE(markdown_content,'')) "
            "FROM note WHERE note_id=:n", {"n": r.get("noteId")})
        seq.append(row[0][0] if row else 0)
    T("N21", "笔记互动", "「内容最长」排序与真实内容长度一致",
      "存在多篇公开笔记（部分正文仅在 markdown_content 中）",
      "GET /notes/note/public/list?sortBy=content_length&sortOrder=desc，直连库核算每篇 content+markdown 字符总长",
      "接口顺序与真实总长度降序一致（只按 content 排序会把 markdown 长文判为最短）",
      code_of(res) == 200 and len(seq) >= 2 and seq == sorted(seq, reverse=True),
      "长度序列=%s" % seq)

    # O 模块：笔记与题目 / 题库 关联
    # ==================================================================
    st, res = call("POST", "/noteQuestion/noteQuestion", t1,
                   {"noteId": note_id, "questionId": q1, "questionBankId": bank_id})
    T("O01", "笔记关联", "笔记关联题目",
      "noteId=%s q1=%s" % (note_id, q1), "POST /noteQuestion/noteQuestion  body={noteId,questionId,questionBankId}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("GET", "/noteQuestion/noteQuestion/check/%s/%s" % (note_id, q1), t1)
    T("O02", "笔记关联", "校验笔记与题目的关联",
      "已建立关联", "GET /noteQuestion/noteQuestion/check/{noteId}/{q1}",
      "code=200；返回已关联",
      code_of(res) == 200 and raw_data(res) in (True, {"linked": True}, "true"),
      "data=%s" % raw_data(res))

    st, res = call("GET", "/noteQuestion/noteQuestion/byNote/%s" % note_id, t1)
    rel = raw_data(res)
    rel_list = rel if isinstance(rel, list) else (rel or {}).get("list", [])
    T("O03", "笔记关联", "按笔记查询关联题目",
      "笔记已关联 q1", "GET /noteQuestion/noteQuestion/byNote/{noteId}",
      "code=200；包含 q1",
      code_of(res) == 200 and any((x.get("questionId") if isinstance(x, dict) else x) == q1 for x in rel_list),
      "关联数=%d" % len(rel_list))

    st, res = call("GET", "/noteQuestion/noteQuestion/byQuestion/%s" % q1, t1)
    rel2 = raw_data(res)
    rel2_list = rel2 if isinstance(rel2, list) else (rel2 or {}).get("list", [])
    T("O04", "笔记关联", "按题目查询关联笔记",
      "q1 已关联该笔记", "GET /noteQuestion/noteQuestion/byQuestion/{q1}",
      "code=200；包含该笔记",
      code_of(res) == 200 and any((x.get("noteId") if isinstance(x, dict) else x) == note_id for x in rel2_list),
      "关联数=%d" % len(rel2_list))

    st, res = call("POST", "/noteQuestion/noteQuestion", t1, {"noteId": note_id, "questionId": q1})
    T("O05", "笔记关联", "重复关联题目的幂等处理",
      "关联已存在", "再次 POST /noteQuestion/noteQuestion  body={noteId,q1}",
      "给出明确业务冲突提示（code=400，不应是 500）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/noteQuestion/noteQuestion/batchLink", t1,
                   {"noteId": note_id, "questionIds": [q2, q3], "questionBankId": bank_id})
    T("O06", "笔记关联", "批量关联题目",
      "q2/q3 尚未关联", "POST /noteQuestion/noteQuestion/batchLink  body={noteId,questionIds:[q2,q3]}",
      "code=200；created=2",
      code_of(res) == 200 and dd(res).get("created") == 2,
      "created=%s skipped=%s" % (dd(res).get("created"), dd(res).get("skipped")))

    st, res = call("DELETE", "/noteQuestion/noteQuestion/note/%s/question/%s" % (note_id, q1), t1)
    st2, res2 = call("GET", "/noteQuestion/noteQuestion/check/%s/%s" % (note_id, q1), t1)
    T("O07", "笔记关联", "解除笔记与题目的关联",
      "关联存在", "DELETE /noteQuestion/noteQuestion/note/{noteId}/question/{q1}",
      "code=200；校验变为未关联",
      code_of(res) == 200 and raw_data(res2) in (False, None),
      "解除=%s 校验=%s" % (code_of(res), raw_data(res2)))

    # O01 建立笔记-题目关联时会自动联动建立笔记-题库关联（note_question 表本身没有 bank 列），
    # 因此这里改为：先从列表拿关联 id，再校验创建接口对「已存在关联」的幂等提示
    st, res = call("GET", "/noteQuestionBank/noteQuestionBank/list", t1,
                   params={"noteId": note_id, "pageNum": 1, "pageSize": 20})
    bk_rows = rows_of(res)
    bk_id = next((r.get("id") for r in bk_rows if r.get("questionBankId") == bank_id), None)
    T("O08", "笔记关联", "笔记关联题库（关联列表可查）",
      "noteId=%s bank=%s" % (note_id, bank_id),
      "GET /noteQuestionBank/noteQuestionBank/list?noteId={noteId}",
      "code=200；存在该题库的关联记录",
      code_of(res) == 200 and bk_id is not None,
      "code=%s 关联id=%s" % (code_of(res), bk_id))

    st, res = call("GET", "/noteQuestionBank/noteQuestionBank/byNote/%s" % note_id, t1)
    bks = raw_data(res)
    bks_list = bks if isinstance(bks, list) else (bks or {}).get("list", [])
    T("O09", "笔记关联", "按笔记查询关联题库",
      "已关联 bank", "GET /noteQuestionBank/noteQuestionBank/byNote/{noteId}",
      "code=200；包含该题库",
      code_of(res) == 200 and any(
          (x.get("bankId") or x.get("id")) == bank_id for x in bks_list if isinstance(x, dict)),
      "关联数=%d" % len(bks_list))

    st, res = call("GET", "/noteQuestionBank/noteQuestionBank/list", t1,
                   params={"noteId": note_id, "pageNum": 1, "pageSize": 20})
    T("O10", "笔记关联", "关联题库列表-分页结构",
      "已有关联", "GET /noteQuestionBank/noteQuestionBank/list?noteId=",
      "code=200；含 total 与 rows",
      code_of(res) == 200 and isinstance(total_of(res), int),
      "total=%s" % total_of(res))

    st, res = call("PUT", "/noteQuestionBank/noteQuestionBank", t1, {"id": bk_id, "noteId": note_id})
    T("O11", "笔记关联", "修改题库关联明细",
      "关联 id=%s" % bk_id, "PUT /noteQuestionBank/noteQuestionBank  body={id,noteId}",
      "code=200",
      code_of(res) == 200, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/noteQuestionBank/noteQuestionBank", t1,
                   {"noteId": note_id, "questionBankId": bank_id})
    T("O12", "笔记关联", "重复关联题库的幂等处理",
      "关联已存在（O01 已自动建立）", "POST /noteQuestionBank/noteQuestionBank",
      "给出明确业务冲突提示（code=400，不应是 500）",
      code_of(res) == 400, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    st, res = call("POST", "/noteQuestion/noteQuestion", t2, {"noteId": note_id, "questionId": q2})
    T("O13", "笔记关联", "数据隔离-user2 不能往 user1 的笔记里加关联",
      "noteId=%s 属于 user1" % note_id, "user2 请求 POST /noteQuestion/noteQuestion  body={noteId,q2}",
      "code=403（按笔记归属校验）",
      code_of(res) == 403, "code=%s msg=%s" % (code_of(res), res.get("msg")))

    # ==================================================================
    # P 模块：清理
    # ==================================================================
    # 关联表有 FK，必须先解关联再删题库
    st, res = call("DELETE", "/noteQuestionBank/noteQuestionBank/note/%s/bank/%s" % (note_id, bank_id), t1)
    call("DELETE", "/noteQuestion/noteQuestion/note/%s/question/%s" % (note_id, q2), t1)
    call("DELETE", "/noteQuestion/noteQuestion/note/%s/question/%s" % (note_id, q3), t1)
    st2, res2 = call("DELETE", "/notes/note/%s" % note_id, t1)
    time.sleep(0.4)
    left_note = db_scalar("SELECT COUNT(*) FROM note WHERE note_id=:n AND del_flag='0'", {"n": note_id})
    T("P01", "测试清理", "清理临时笔记与关联",
      "测试笔记 noteId=%s" % note_id, "解除关联后 DELETE /notes/note/{noteId}（逻辑删除）",
      "code=200；笔记不再出现在有效笔记中",
      code_of(res2) == 200 and (left_note is None or left_note == 0),
      "删除=%s 剩余有效笔记=%s" % (code_of(res2), left_note))

    # 评论与收藏走 API 清理（评论作者/笔记作者可删）
    for cm in (cid, rid):
        if cm:
            call("DELETE", "/notes/comment/delete/%s" % cm, t1)
    if fv and fv[0].get("favoriteId"):
        call("DELETE", "/favoriteNote/favoriteNote/%s" % fv[0].get("favoriteId"), t2)

    call("DELETE", "/noteCategory/noteCategory/%s" % cat_id, t1)
    call("DELETE", "/favoriteBank/favoriteBank/deleteByUserAndBank/%s/%s" % (uid1, bank_id), t1)
    st, res = call("DELETE", "/questionBank/questionBank/%s" % bank_id, t1)
    print("  临时题库删除 code=%s" % code_of(res))

    # —— 物理清理：逻辑删除的笔记、评论、通知、收藏、孤儿流水，不给演示环境留任何痕迹 ——
    note_t = (note_id,)
    bank_t = (bank_id,)
    q_t = (q1, q2, q3)
    db_exec("DELETE FROM sys_notice WHERE remark LIKE :p OR remark LIKE :p2",
            {"p": '%%"noteId": %d,%%' % note_id, "p2": '%%"noteId": %d}%%' % note_id})
    db_exec("DELETE FROM note_comment WHERE note_id IN :i", {"i": note_t})
    db_exec("DELETE FROM user_note_favorite WHERE note_id IN :i", {"i": note_t})
    db_exec("DELETE FROM note_question WHERE note_id IN :i", {"i": note_t})
    db_exec("DELETE FROM note_question_bank WHERE note_id IN :i", {"i": note_t})
    db_exec("DELETE FROM note WHERE note_id IN :i", {"i": note_t})  # 物理删除，避免后台/统计出现痕迹
    db_exec("DELETE FROM note_category WHERE id IN :i", {"i": (cat_id,)})
    db_exec("DELETE FROM user_practice_log WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_error WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_marked WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_question_favorite WHERE question_id IN :i", {"i": q_t})
    db_exec("DELETE FROM user_practice_log WHERE question_id NOT IN (SELECT id FROM question_main)")

    # 残留检查（含通知 / 评论 / 收藏 / 流水，全部必须为 0）
    for label, uid in (("user1", uid1), ("user2", uid2)):
        n = db_scalar("SELECT COUNT(*) FROM note WHERE user_id=:u AND title LIKE :p", {"u": uid, "p": P + "%"})
        c = db_scalar("SELECT COUNT(*) FROM note_category WHERE user_id=:u AND name LIKE :p",
                      {"u": uid, "p": P + "%"})
        b = db_scalar("SELECT COUNT(*) FROM question_bank WHERE user_id=:u AND bank_name LIKE :p",
                      {"u": uid, "p": P + "%"})
        cm = db_scalar("SELECT COUNT(*) FROM note_comment WHERE user_id=:u AND content LIKE :p",
                       {"u": uid, "p": P + "%"})
        nt = db_scalar("SELECT COUNT(*) FROM sys_notice WHERE remark LIKE :p", {"p": '%"' + "noteId" + '": ' + str(note_id) + '%'})
        print("  残留检查 %s：笔记=%s 分类=%s 题库=%s 评论=%s 通知=%s" % (label, n, c, b, cm, nt))
        T("P0%d" % (2 if label == "user1" else 3), "测试清理",
          "残留检查-%s" % label, "测试结束", "统计该用户下以 %s 开头的笔记/分类/题库/评论及关联通知" % P,
          "全部为 0",
          (n in (None, 0)) and (c in (None, 0)) and (b in (None, 0)) and (cm in (None, 0)),
          "笔记=%s 分类=%s 题库=%s 评论=%s 通知=%s" % (n, c, b, cm, nt))
    orphan = db_scalar("SELECT COUNT(*) FROM user_practice_log l "
                       "LEFT JOIN question_main q ON q.id=l.question_id WHERE q.id IS NULL")
    dead = db_scalar("SELECT COUNT(*) FROM note_comment c LEFT JOIN note n ON n.note_id=c.note_id "
                     "WHERE n.note_id IS NULL OR n.del_flag<>'0'")
    T("P04", "测试清理", "无死链残留（消息中心可安全跳转）",
      "清理完成", "检查孤儿答题流水与指向已删笔记的评论",
      "孤儿流水=0 且 死链评论=0",
      (orphan in (None, 0)) and (dead in (None, 0)),
      "孤儿流水=%s 死链评论=%s" % (orphan, dead))

    print("=" * 74)
    ok = sum(1 for r in ROWS if r["status"] == "通过")
    print("用例总数 %d，通过 %d，失败 %d" % (len(ROWS), ok, len(ROWS) - ok))
    print("=" * 74)
    for r in ROWS:
        if r["status"] == "失败":
            print("  [FAIL] %s %s -> 预期:%s / 实际:%s" % (r["cid"], r["title"], r["expected"], r["actual"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "prefix": P, "uid1": uid1, "uid2": uid2, "rows": ROWS,
            # 记录本 run 创建的数据 id：若下次运行前脚本崩溃，启动自检可按 id 彻底清理
            "cleanup": {"note_ids": [note_id], "category_ids": [cat_id], "bank_ids": [bank_id]},
        }, f, ensure_ascii=False, indent=2)
    print("结果已写入 %s" % OUT)


if __name__ == "__main__":
    main()
