# -*- coding: utf-8 -*-
"""A2 端到端探针：知识库取材出题（真实后端 + 真实本地 embedding + 真实 LLM）

用**独占标记**避免「模型本来就懂」造成的假阳性：把一段虚构事实写进知识库，
问一个只有读了这段资料才能答对的问题。

用法：
    .venv/Scripts/python.exe tests/_probe_kb_question_e2e.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:9101"
# 独占虚构标记：模型先验知识里**不可能**有，只有读过知识库才能复述
MARKER = "紫晶协议"
MATERIAL = (
    f"{MARKER}是 OpenStudy 内部定义的虚构通信协议，其核心参数如下："
    "握手端口固定为 7788，默认心跳间隔 42 秒，加密算法代号为 ZXQ-7。"
    f"以上均为 {MARKER} 的虚构定义，仅存在于本资料中。"
)
QUESTION = f"{MARKER}的握手端口是多少、心跳间隔是多少秒？"


def _req(method, path, token=None, body=None, timeout=180, raw=False):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        text = resp.read().decode("utf-8", "replace")
        return resp.status, (text if raw else json.loads(text))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            return e.code, (text if raw else json.loads(text))
        except Exception:
            return e.code, text


def main():
    checks = []

    def ck(cid, title, cond, actual=""):
        checks.append((cid, title, cond, actual))
        print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))

    st, body = _req("POST", "/login", body={"username": "admin", "password": "123456"})
    token = body["data"]["token"]
    ck("E-01", "登录成功", bool(token))

    kb_id = None
    try:
        st, body = _req("POST", "/rag/knowledgeBase", token,
                        {"name": f"紫晶协议探针库_{int(time.time())}", "description": "e2e"})
        kb_id = body["data"]["kbId"]
        ck("E-02", "创建知识库", bool(kb_id), str(body))

        st, body = _req("POST", "/rag/document/uploadText", token,
                        {"kbId": kb_id, "content": MATERIAL, "fileName": "紫晶协议.txt"})
        doc_id = body["data"]["docId"]
        ck("E-03", "导入资料文本", bool(doc_id), str(body))

        stt = None
        for _ in range(90):
            st, body = _req("GET", f"/rag/document/status/{doc_id}", token)
            stt = (body.get("data") or {}).get("status")
            if stt in (4, 5):
                break
            time.sleep(2)
        ck("E-04", "资料已向量化（status=5）", stt == 5, f"status={stt}")

        # 带 kbIds 出题：应能复述知识库里的虚构参数
        payload = {
            "message": QUESTION,
            "scene": "question-generate",
            "variables": {"knowledge_point": MARKER, "count": 2, "question_type": "single"},
            "configId": 6,
            "kbIds": [kb_id],
        }
        st, text = _req("POST", "/ai/assistant/stream", token, payload, timeout=240, raw=True)
        ok_kb = ("7788" in text) or ("42" in text) or ("ZXQ-7" in text)
        ck("E-05", "带 kbIds：答案复述了知识库里的虚构参数", ok_kb, text[:240])
        ck("E-06", "带 kbIds：解析里带出处（来源：…）", "来源" in text, text[:240])

        # 对照：不带 kbIds（应无法知道虚构参数）
        payload2 = dict(payload)
        payload2.pop("kbIds")
        st, text2 = _req("POST", "/ai/assistant/stream", token, payload2, timeout=240, raw=True)
        ck("E-07", "不带 kbIds：无法复述虚构参数（对照）",
           not (("7788" in text2) and ("42" in text2)), text2[:200])

    finally:
        if kb_id:
            st, body = _req("DELETE", f"/rag/knowledgeBase/{kb_id}", token)
            ck("E-08", "清理探针知识库", st == 200, str(body))

    red = [c for c in checks if not c[2]]
    print(f"\n共 {len(checks)} 项：{len(checks) - len(red)} 通过；红的 = {[c[0] for c in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
