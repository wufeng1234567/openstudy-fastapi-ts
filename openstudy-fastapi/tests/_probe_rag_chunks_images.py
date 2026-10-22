# -*- coding: utf-8 -*-
"""验证 `/rag/document/chunks/{docId}` 是否带出 `images`（纯读接口，无需写入）

背景：知识库「分块预览」里正文的 `【图0】` 只是位置标记，前端要靠接口返回的
`images` 才能渲染成真图。此前 `list_chunks` 只回 `content`，图片信息被丢掉，
于是预览里只剩一个光秃秃的「【图0】」。

用法：
    .venv/Scripts/python.exe tests/_probe_rag_chunks_images.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE = "http://localhost:9101"


def _req(method, path, token=None, body=None):
    h = {}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def main():
    checks = []

    def ck(cid, title, cond, actual=""):
        checks.append((cid, title, cond, actual))
        print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))

    st, body = _req("POST", "/login", body={"username": "admin", "password": "123456"})
    token = body.get("data", {}).get("token")
    ck("CI-01", "登录成功", bool(token))

    # 找一个「分块里带图」的文档（直接查库，避免依赖固定 docId）
    import asyncio
    from app.database import async_session_factory
    from app.models.rag import RagDocumentChunk
    from sqlalchemy import select

    async def _find():
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(RagDocumentChunk.doc_id, RagDocumentChunk.meta_data)
                .where(RagDocumentChunk.meta_data.isnot(None))
                .limit(50)
            )).all()
            for doc_id, meta in rows:
                if isinstance(meta, dict) and meta.get("images"):
                    return doc_id
            return None

    doc_id = asyncio.run(_find())
    ck("CI-02", "库中存在带图的分块文档", doc_id is not None, f"doc_id={doc_id}")
    if not doc_id:
        print(f"\n共 {len(checks)} 项：{sum(1 for c in checks if c[2])} 通过")
        return 1

    st, body = _req("GET", f"/rag/document/chunks/{doc_id}", token)
    ck("CI-03", "chunks 接口 200", st == 200 and body.get("code") == 200, f"status={st}")
    chunks = body.get("data") or []
    with_img = [c for c in chunks if c.get("images")]
    ck("CI-04", "接口返回的 chunk 带 images 字段", any("images" in c for c in chunks),
       f"首块 keys={list(chunks[0].keys()) if chunks else []}")
    ck("CI-05", "至少一个分块的 images 非空", len(with_img) >= 1,
       f"{len(with_img)}/{len(chunks)} 块带图")
    if with_img:
        url = with_img[0]["images"][0]
        ck("CI-06", "图片 URL 形如 /profile/...", url.startswith("/profile/"), url)
        # 校验图片来源文件存在
        from app.config import settings
        rel = url[len("/profile/"):]
        disk = os.path.join(settings.UPLOAD_DIR, *rel.split("/"))
        ck("CI-07", "图片文件在磁盘存在", os.path.exists(disk), disk)

    red = [c for c in checks if not c[2]]
    print(f"\n共 {len(checks)} 项：{len(checks) - len(red)} 通过；红的 = {[c[0] for c in red] or '无'}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
