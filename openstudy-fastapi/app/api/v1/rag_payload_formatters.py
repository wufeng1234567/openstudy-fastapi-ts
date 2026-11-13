"""RAG 上传结果与下载文件名的纯格式化辅助。

从 ``rag.py`` 抽出的低风险纯函数：失败项字典、独立图片资产 payload、
pptx 下载文件名。只做字符串/字典拼装，不含数据库、请求、权限或事务逻辑。
``rag.py`` 会把这三个名字重新导入自己的模块命名空间，路由调用点保持不变。
"""

import re
from pathlib import Path


def _upload_failure(filename: str, exc: Exception) -> dict:
    """多文件上传允许部分成功时，统一记录单个失败项（错误信息截断到 300 字）。"""
    return {"fileName": filename, "error": str(exc)[:300]}


def _standalone_image_payload(asset, kb_id: int, filename: str) -> dict:
    """独立图片资产上传成功后的返回项。"""
    return {
        "assetId": int(asset.id),
        "assetKey": str(asset.asset_key),
        "kbId": int(kb_id),
        "fileName": filename,
        "displayName": str(asset.display_name or Path(filename).stem),
    }


def _pptx_filename(display_title: str, version: int) -> str:
    """教学课件下载文件名：去掉非法字符与已有扩展名，再拼版本号。"""
    stem = re.sub(r"[\\/:*?\"<>|]", "_", display_title or "教学课件")
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", stem)
    return f"{stem}_第{version}版.pptx"


def _doc_status_payload(doc, doc_status_text: dict) -> dict:
    """文档处理进度的返回结构（批量查询与单文档轮询共用，字段逐字照搬）。"""
    return {
        "docId": doc.id,
        "status": doc.status,
        "statusText": doc_status_text.get(doc.status, "未知"),
        "chunkCount": doc.chunk_count,
        "errorMsg": doc.error_msg,
        "done": doc.status in (4, 5),
        "ok": doc.status == 5,
    }
