"""RAG 文档导出接口的下载响应构造（从 rag.py 抽出的重复实现）。

``export_document`` / ``export_document_with_content`` /
``export_workspace_study_prescription`` 三处原本手写完全相同的
``Response(content=..., media_type=..., headers={"Content-Disposition": ...})``。
这里收拢成一个纯函数：同样懒加载 ``content_disposition``，返回同样的 Response，
响应头与状态码行为不变。
"""

from fastapi.responses import Response


def document_download_response(content, media_type, filename):
    """构造带 Content-Disposition 的文件下载 Response。"""
    from app.services.document_export_service import content_disposition

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )
