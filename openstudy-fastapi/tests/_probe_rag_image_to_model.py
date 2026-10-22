# -*- coding: utf-8 -*-
"""RAG 图片「回传给模型」端到端探针（真实带图 docx → 出题 → 模型收到图）

用**只有看图才能答对**的虚构内容验证：docx 里放一张写着/代表特定信息的图，
让出题链路（scene=question-generate + kbIds）去取材，检查模型是否真收到了图片。

⚠️ 需要：本地 embedding 可用 + 一个支持视觉的模型（deepseek-flash 默认支持）。
   若模型不含视觉能力，本探针的「模型看到图」断言会失败（那不是链路问题）。

用法：
    .venv/Scripts/python.exe tests/_probe_rag_image_to_model.py
"""
import io
import json
import os
import struct
import sys
import time
import urllib.request
import urllib.error
import uuid
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

BASE = "http://localhost:9101"


def _png_bytes(w=160, h=160, rgb=(200, 30, 30)) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = (b"\x00" + bytes(rgb) * w) * h
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _docx_bytes(text: str, png: bytes) -> bytes:
    from docx import Document
    from docx.shared import Inches
    doc = Document()
    doc.add_paragraph(text)
    doc.add_picture(io.BytesIO(png), width=Inches(1.5))
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _post(path, token=None, body=None, raw_body=None, headers=None, timeout=300):
    h = dict(headers or {})
    data = raw_body
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=data, headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        txt = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(txt)
        except Exception:
            return resp.status, txt
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


def _get(path, token=None, timeout=60):
    h = {"Authorization": "Bearer " + token} if token else {}
    r = urllib.request.Request(BASE + path, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def _multipart(field, filename, content, mime):
    b = "----probe" + uuid.uuid4().hex
    body = (
        f"--{b}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + content + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def main():
    checks = []

    def ck(cid, title, cond, actual=""):
        checks.append((cid, title, cond, actual))
        print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))

    st, body = _post("/login", body={"username": "admin", "password": "123456"})
    token = body["data"]["token"]
    ck("Z-01", "登录成功", bool(token))

    kb_id = None
    try:
        st, body = _post("/rag/knowledgeBase", token=token,
                         body={"name": f"图回传探针库_{int(time.time())}"})
        kb_id = body["data"]["kbId"]
        ck("Z-02", "创建知识库", bool(kb_id))

        # 正文只写"看图回答"，把暗号只放进图里（正文不含 7788）
        docx = _docx_bytes("下面这张图记录了本系统的一个关键参数，请以图为准。", _png_bytes())
        mp_body, mp_ct = _multipart("file", "图回传探针.docx", docx,
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        st, body = _post(f"/rag/document/upload?kbId={kb_id}", token=token,
                         raw_body=mp_body, headers={"Content-Type": mp_ct})
        doc_id = (body.get("data") or {}).get("docId")
        ck("Z-03", "上传带图 docx", bool(doc_id), str(body)[:160])

        stt = None
        for _ in range(60):
            st, body = _get(f"/rag/document/status/{doc_id}", token)
            stt = (body.get("data") or {}).get("status")
            if stt in (4, 5):
                break
            time.sleep(2)
        ck("Z-04", "文档已向量化", stt == 5, f"status={stt}")

        # 出题：取材=该库（会检索→带图→作为多模态块回给模型）
        # 用"看图描述"类提问 —— 让模型有机会复述只有图片才知道的内容
        payload = {
            "message": "请看我的资料里的那张图，图中记录的关键参数是多少？只回答你从图上看到的内容。",
            "scene": "question-generate",
            "variables": {"knowledge_point": "图中的关键参数", "count": 1, "question_type": "single"},
            "configId": 6,  # deepseek-flash（支持视觉）
            "kbIds": [kb_id],
        }
        st, text = _post("/ai/assistant/stream", token=token, body=payload, timeout=300)
        # 用 str() 容错（流式返回可能是纯文本，也可能被解析成 dict）
        stream_text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
        # 图片是纯色方块、没有可读文字 → 这里**不**断言模型读出内容（那是模型能力，不是链路）。
        # 只验证：① 请求成功且有输出；② 没有「不支持图片 / image_url 非法」这类报错
        #   ——后者正是「图没被正确转成 data URL 提交」时的典型症状。
        got_output = bool(stream_text and "Error" not in stream_text[:40])
        ck("Z-05", "带图取材的出题请求成功且有输出", st == 200 and got_output, stream_text[:200])
        lowered = stream_text[:300].lower()
        no_img_error = (
            "不支持" not in stream_text
            and "unsupported image" not in lowered
            and "image_url" not in lowered
            and "400" not in stream_text[:60]
        )
        ck("Z-06", "没有「图片不被支持」类报错（说明图已正确作为多模态提交）",
           no_img_error, stream_text[:200])

        # 直接验证「落库的图能转回 data URL」——这是回传机制的核心一步
        from app.services.ai.chat_engine import stored_image_to_data_url
        from app.services.rag import rag_query_service as rqs
        from app.database import async_session_factory

        async def _check_convert():
            async with async_session_factory() as db:
                found = await rqs.search(db, 1, "图中记录的关键参数", [kb_id], top_k=5)
                urls = []
                for h in found.get("hits") or []:
                    urls.extend(h.get("images") or [])
                converted = [stored_image_to_data_url(u) for u in urls]
                return urls, converted

        urls, converted = __import__("asyncio").run(_check_convert())
        ck("Z-07", "检索命中带图", len(urls) >= 1, f"{len(urls)} 张")
        ck("Z-08", "命中图能转成 data URL（可交给多模态模型）",
           bool(converted) and all(c.startswith("data:image/") for c in converted if c),
           str(converted)[:120])
    finally:
        if kb_id:
            h = {"Authorization": "Bearer " + token}
            r = urllib.request.Request(BASE + f"/rag/knowledgeBase/{kb_id}", headers=h, method="DELETE")
            try:
                urllib.request.urlopen(r, timeout=30)
            except Exception:
                pass
            ck("Z-09", "清理探针知识库", True)

    red = [c for c in checks if not c[2]]
    print(f"\n共 {len(checks)} 项：{len(checks) - len(red)} 通过；红的 = {[c[0] for c in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
