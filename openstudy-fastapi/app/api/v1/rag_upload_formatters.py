"""RAG 多文件上传的「汇总响应」纯格式化。

从 ``rag.py`` 抽出的近似重复实现：`upload_document`（含独立图片）与
`upload_to_workspace`（不含图片）各手写了一份汇总 dict。这里收拢为一个
纯函数：`images=None` 走工作空间分支，否则走文档上传分支。
两种分支的字段、顺序、count 口径与 totalSize 计算逐字照搬，响应不变。
"""


def upload_summary_payload(documents, failed, payloads, images=None) -> dict:
    """多文件上传的汇总 data（单文件 / 全失败分支仍留在各路由内）。"""
    if images is None:
        return {
            "documents": documents,
            "failed": failed,
            "count": len(documents),
            "totalSize": sum(len(raw) for _, raw in payloads),
        }
    return {
        "documents": documents,
        "images": images,
        "failed": failed,
        "count": len(documents) + len(images),
        "totalSize": sum(len(raw) for _, raw in payloads),
    }
