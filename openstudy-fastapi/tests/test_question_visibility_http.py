# -*- coding: utf-8 -*-
"""
题目读取侧可见性修复 —— 安全只读 HTTP 验证（2026-10-28 审核发现 #1/#2 第一阶段修复）

约束与设计
----------
· **只读**：全程不发任何会写库/删除的请求（不调 e2e_question_api 的建库/删库流程）。
  唯一的"写形态"请求是 POST /quickLogin（仅签发 token，账号 user1/user2 必须已存在，
  前置 SELECT 硬校验其存在，缺一则 SKIP 全部用例，不编造）。
· **硬前置**：先用 SELECT 确认 bank=181 / question=1415 的归属与私密状态、
  user2(106) 对 bank181 无分享领取记录 —— 前置不满足即 SKIP，不允许在不确定的数据上断言。
· 覆盖：匿名 / user2 不可读（详情、三个检查接口、无 bankId 列表、搜索、batch、两个导出），
  user1 与公开题库正向可读；两个 Excel 导出**解析内容**断言不含 bank181，不只看 HTTP 200。

运行：
    ./.venv/Scripts/python.exe tests/test_question_visibility_http.py
依赖：后端已在 127.0.0.1:9101 运行（本测试不启动/停止服务）。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:9101"
BANK_ID = 181
QUESTION_ID = 1415
OWNER_ID = 105   # user1
OTHER_ID = 106   # user2

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


def code_of(res):
    if isinstance(res, dict):
        return res.get("code")
    return None


def is_denied(res):
    """兼容两种拒绝形态：HTTP 401/403，或 HTTP 200 信封 code=401/403"""
    return code_of(res) in (401, 403)


def login(account):
    st, res = call("POST", "/quickLogin", body={"account": account})
    if st != 200 or code_of(res) != 200:
        return None
    return res["data"]["token"]


# ---------------------------------------------------------------- 前置 SELECT（只读）

async def load_preconditions():
    from sqlalchemy import select
    from app.database import async_session_factory, register_all_models

    register_all_models()  # ORM 关系字符串（如 SysRole）需要全量注册后才能解析

    from app.models.question import QuestionBank, QuestionMain
    from app.models.bank_share import BankShareReceive
    from app.models.user import SysUser

    async with async_session_factory() as db:
        bank = (await db.execute(
            select(QuestionBank).where(QuestionBank.id == BANK_ID)
        )).scalar_one_or_none()
        question = (await db.execute(
            select(QuestionMain).where(QuestionMain.id == QUESTION_ID)
        )).scalar_one_or_none()
        owner = (await db.execute(
            select(SysUser.user_id).where(SysUser.user_id == OWNER_ID)
        )).scalar_one_or_none()
        other = (await db.execute(
            select(SysUser.user_id).where(SysUser.user_id == OTHER_ID)
        )).scalar_one_or_none()
        share = (await db.execute(
            select(BankShareReceive.bank_id).where(
                BankShareReceive.bank_id == BANK_ID,
                BankShareReceive.receiver_id == OTHER_ID,
            )
        )).first()
        # 公开题库正向用例：任选一道 status='0' 且题库 is_public=0（公开）的题
        pub = (await db.execute(
            select(QuestionMain.id)
            .join(QuestionBank, QuestionMain.bank_id == QuestionBank.id)
            .where(QuestionBank.is_public == 0, QuestionMain.status == "0")
            .limit(1)
        )).first()

    checks = {
        "bank181 存在且 owner=105": bank is not None and int(bank.user_id or 0) == OWNER_ID,
        "bank181 是私密题库(is_public!=0)": bank is not None and int(bank.is_public or 0) != 0,
        "bank181 状态正常(status='0')": bank is not None and bank.status == "0",
        "question1415 存在且属于 bank181": question is not None and question.bank_id == BANK_ID,
        "question1415 状态正常(status='0')": question is not None and question.status == "0",
        "user1(105) 存在": owner is not None,
        "user2(106) 存在": other is not None,
        "user2(106) 对 bank181 无分享领取": share is None,
        "存在公开题库正向用例题": pub is not None,
    }
    return checks, (question, bank, pub[0] if pub else None)


# ---------------------------------------------------------------- 用例

def T(case_id, name, expected, actual, passed):
    ROWS.append({"id": case_id, "name": name, "expected": expected,
                 "actual": actual, "passed": bool(passed)})
    print(("  PASS  " if passed else "  FAIL  ") + f"{case_id} {name}\n        expected: {expected}\n        actual: {actual}")


def parse_xlsx_rows(raw: bytes):
    """解析导出 Excel 为 dict 列表（只读内存解析，不落盘）

    导出表头是中文（题目ID/题库ID…），同时保留原表头键，便于按位置取列。
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    headers = [str(h) for h in next(it)]
    rows = [dict(zip(headers, row)) for row in it]
    # 统一补英文别名，方便断言
    alias = {"题目ID": "id", "题库ID": "bankId", "题干": "questionText"}
    for r in rows:
        for zh, en in alias.items():
            if zh in r and en not in r:
                r[en] = r[zh]
    return rows


async def main() -> int:
    checks, (question, bank, pub_qid) = await load_preconditions()
    ok_pre = all(checks.values())
    for k, v in checks.items():
        print(("  PRE-OK   " if v else "  PRE-FAIL") + f" {k}")
    if not ok_pre:
        print("\nSKIP：前置数据不满足，不允许在不确定的数据上断言（不编造）。")
        return 2

    q_text = (question.question_text or "")
    keyword = q_text[:6] if len(q_text) >= 6 else q_text  # 1415 题干子串，用于列表/搜索命中

    t1 = login("user1")
    t2 = login("user2")
    if not t1 or not t2:
        print("\nSKIP：quickLogin 未取得 token（不编造）")
        return 2
    print(f"  PRE-OK   user1/user2 quickLogin 成功 token={bool(t1)}/{bool(t2)}")

    # ---------- A. 匿名：全部拒绝 ----------
    for cid, path in [
        ("A1", f"/questionMain/questionMain/{QUESTION_ID}"),
        ("A2", f"/questionMain/questionMain/simpleInfo/{QUESTION_ID}"),
        ("A3", f"/questionMain/questionMain/checkExists/{QUESTION_ID}"),
        ("A4", f"/questionMain/questionMain/checkQuestionAndUser/{QUESTION_ID}/{OWNER_ID}"),
        ("A5", f"/questionMain/questionMain/checkUserExists/{OWNER_ID}"),
    ]:
        st, res = call("GET", path)
        T(cid, f"匿名 GET {path.split('/')[-2]}/... 被拒", "code in (401,403)",
          f"HTTP {st} code={code_of(res)}", is_denied(res))

    # ---------- B. user2（他人）：单题读取与检查接口 403 ----------
    for cid, path, label in [
        ("B1", f"/questionMain/questionMain/{QUESTION_ID}", "题目详情"),
        ("B2", f"/questionMain/questionMain/simpleInfo/{QUESTION_ID}", "simpleInfo"),
        ("B3", f"/questionMain/questionMain/checkExists/{QUESTION_ID}", "checkExists"),
        ("B4", f"/questionMain/questionMain/checkQuestionAndUser/{QUESTION_ID}/{OWNER_ID}", "checkQuestionAndUser"),
    ]:
        st, res = call("GET", path, token=t2)
        T(cid, f"user2 请求{label}私密题库题目被拒", "code=403",
          f"HTTP {st} code={code_of(res)}", code_of(res) == 403)

    # ---------- C. 无 bankId 列表/搜索/batch/导出：user2 不含 bank181，user1 含 1415 ----------
    st, res = call("GET", "/questionMain/questionMain/all", token=t2)
    all_u2 = res.get("data") or [] if st == 200 else []
    leaked = [q.get("id") for q in all_u2 if q.get("bankId") == BANK_ID]
    T("C1", "user2 /questionMain/all 无 bank181 题目", "不含1415/bank181",
      f"rows={len(all_u2)} leaked={leaked}", not leaked)

    st, res = call("GET", "/questionMain/questionMain/all", token=t1)
    all_u1 = res.get("data") or [] if st == 200 else []
    has = any(q.get("id") == QUESTION_ID for q in all_u1)
    T("C2", "user1 /questionMain/all 含题1415", "含1415",
      f"rows={len(all_u1)} has={has}", has)

    st, res = call("GET", "/questionMain/questionMain/list", token=t2,
                   params={"keyword": keyword, "pageSize": 100})
    list_u2 = res.get("rows") or [] if st == 200 and code_of(res) == 200 else []
    leaked = [q.get("id") for q in list_u2 if q.get("bankId") == BANK_ID]
    T("C3", f"user2 list?keyword 命中不含 bank181（kw={keyword!r}）", "不含bank181",
      f"rows={len(list_u2)} leaked={leaked}", not leaked)

    st, res = call("GET", "/questionMain/questionMain/list", token=t1,
                   params={"keyword": keyword, "pageSize": 100})
    list_u1 = res.get("rows") or [] if st == 200 and code_of(res) == 200 else []
    has = any(q.get("id") == QUESTION_ID for q in list_u1)
    T("C4", "user1 list?keyword 含题1415", "含1415",
      f"rows={len(list_u1)} has={has}", has)

    st, res = call("GET", "/questionMain/questionMain/search", token=t2,
                   params={"keyword": keyword, "pageSize": 100})
    s_u2 = res.get("rows") or [] if st == 200 and code_of(res) == 200 else []
    leaked = [q.get("id") for q in s_u2 if q.get("bankId") == BANK_ID]
    T("C5", "user2 search 不含 bank181", "不含bank181",
      f"rows={len(s_u2)} leaked={leaked}", not leaked)

    st, res = call("GET", "/questionMain/questionMain/search", token=t1,
                   params={"keyword": keyword, "pageSize": 100})
    s_u1 = res.get("rows") or [] if st == 200 and code_of(res) == 200 else []
    has = any(q.get("id") == QUESTION_ID for q in s_u1)
    T("C6", "user1 search 含题1415", "含1415",
      f"rows={len(s_u1)} has={has}", has)

    st, res = call("POST", "/questionMain/questionMain/batchInfo", token=t2,
                   body={"questionIds": [QUESTION_ID, pub_qid]})
    rows_u2 = res.get("data") or [] if st == 200 and code_of(res) == 200 else []
    ids_u2 = [r.get("id") for r in rows_u2]
    T("C7", "user2 batchInfo 过滤私密题保留公开题", f"含{pub_qid}且不含{QUESTION_ID}",
      f"ids={ids_u2}", pub_qid in ids_u2 and QUESTION_ID not in ids_u2)

    st, res = call("POST", "/questionMain/questionMain/batchInfo", token=t1,
                   body={"questionIds": [QUESTION_ID, pub_qid]})
    rows_u1 = res.get("data") or [] if st == 200 and code_of(res) == 200 else []
    ids_u1 = [r.get("id") for r in rows_u1]
    T("C8", "user1 batchInfo 含题1415", f"含{QUESTION_ID}",
      f"ids={ids_u1}", QUESTION_ID in ids_u1)

    # ---------- D. 导出 Excel：解析内容确认 ----------
    st, raw = call("POST", "/questionBank/questionBank/export", token=t2)
    if st == 200 and isinstance(raw, bytes) and raw[:2] == b"PK":
        rows = parse_xlsx_rows(raw)
        bad = [r.get("bankId") for r in rows if int(r.get("bankId") or 0) == BANK_ID]
        T("D1", "user2 题库导出 Excel 不含 bank181", "不含181",
          f"rows={len(rows)} bad={bad}", not bad)
    else:
        T("D1", "user2 题库导出 Excel 不含 bank181", "xlsx", f"HTTP {st} ct={type(raw).__name__}", False)

    st, raw = call("POST", "/questionMain/questionMain/export", token=t2)
    if st == 200 and isinstance(raw, bytes) and raw[:2] == b"PK":
        rows = parse_xlsx_rows(raw)
        bad = [r.get("id") for r in rows if int(r.get("bankId") or 0) == BANK_ID]
        T("D2", "user2 题目导出 Excel 不含 bank181 的题", "不含bank181",
          f"rows={len(rows)} bad={bad}", not bad)
    else:
        T("D2", "user2 题目导出 Excel 不含 bank181 的题", "xlsx", f"HTTP {st} ct={type(raw).__name__}", False)

    st, raw = call("POST", "/questionMain/questionMain/export", token=t1)
    if st == 200 and isinstance(raw, bytes) and raw[:2] == b"PK":
        rows = parse_xlsx_rows(raw)
        has = any(int(r.get("id") or 0) == QUESTION_ID for r in rows)
        T("D3", "user1 题目导出 Excel 含题1415", "含1415",
          f"rows={len(rows)} has={has}", has)
    else:
        T("D3", "user1 题目导出 Excel 含题1415", "xlsx", f"HTTP {st} ct={type(raw).__name__}", False)

    # ---------- E. 正向：user1 读私密题库题目；公开题库任何登录用户可读 ----------
    st, res = call("GET", f"/questionMain/questionMain/{QUESTION_ID}", token=t1)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E1", "user1 读题1415 详情", f"data.id={QUESTION_ID}",
      f"HTTP {st} code={code_of(res)} id={d.get('id')}", d.get("id") == QUESTION_ID)

    st, res = call("GET", f"/questionMain/questionMain/simpleInfo/{QUESTION_ID}", token=t1)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E2", "user1 读题1415 simpleInfo", "code=200 且 bankId=181",
      f"HTTP {st} code={code_of(res)} bankId={d.get('bankId')}",
      code_of(res) == 200 and d.get("bankId") == BANK_ID)

    st, res = call("GET", f"/questionMain/questionMain/checkExists/{QUESTION_ID}", token=t1)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E3", "user1 checkExists 题1415", "exists=True",
      f"HTTP {st} code={code_of(res)} exists={d.get('exists')}",
      code_of(res) == 200 and d.get("exists") is True)

    st, res = call("GET", f"/questionMain/questionMain/checkQuestionAndUser/{QUESTION_ID}/{OWNER_ID}", token=t1)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E4", "user1 checkQuestionAndUser", "questionValid=True",
      f"HTTP {st} code={code_of(res)} qv={d.get('questionValid')}",
      code_of(res) == 200 and d.get("questionValid") is True)

    st, res = call("GET", f"/questionMain/questionMain/{pub_qid}", token=t2)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E5", "user2 读公开题库题目正向可读", f"data.id={pub_qid}",
      f"HTTP {st} code={code_of(res)} id={d.get('id')}", d.get("id") == pub_qid)

    st, res = call("GET", f"/questionMain/questionMain/checkUserExists/{OWNER_ID}", token=t1)
    d = res.get("data") or {} if st == 200 and code_of(res) == 200 else {}
    T("E6", "登录后 checkUserExists 已存在用户正向可读（返回结构不变）",
      "exists=True 且 userId=105",
      f"HTTP {st} code={code_of(res)} exists={d.get('exists')} userId={d.get('userId')}",
      code_of(res) == 200 and d.get("exists") is True and d.get("userId") == OWNER_ID)

    passed = sum(1 for r in ROWS if r["passed"])
    failed = len(ROWS) - passed
    print(f"\n合计：{passed} passed, {failed} failed, {len(ROWS)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
