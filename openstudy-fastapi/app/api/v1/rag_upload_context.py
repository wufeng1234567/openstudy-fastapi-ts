"""RAG 多文件上传的图片上下文准备（纯辅助，从 rag.py 抽出的重复实现）。

``upload_document`` 与 ``upload_to_workspace`` 各手写了一遍
``assets = _batch_image_assets(payloads)`` +
``referenced_images = _referenced_markdown_image_names(payloads)``。
这里收拢成一个纯函数：只做列表/集合计算，不含 async、不含 DB、不含权限逻辑，
可直接单测。
"""

from .rag_helpers import _batch_image_assets, _referenced_markdown_image_names


def prepare_upload_assets(payloads):
    """返回 (图片资产索引, Markdown 已引用的图片文件名集合)，顺序与原实现一致。"""
    return _batch_image_assets(payloads), _referenced_markdown_image_names(payloads)
