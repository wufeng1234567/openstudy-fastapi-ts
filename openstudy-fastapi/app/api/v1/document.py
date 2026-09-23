"""
文档 API
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File
from app.core.security import get_current_user
from app.core.response import success, error

router = APIRouter(prefix="/document")


@router.get("/formats")
async def get_supported_formats(
    current_user: dict = Depends(get_current_user),
):
    """获取支持的文档格式"""
    return success({
        "formats": ["pdf", "doc", "docx", "txt", "md"]
    })


@router.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    target_format: str = Query("txt"),
    current_user: dict = Depends(get_current_user),
):
    """转换文档格式(提取为纯文本)"""
    import asyncio

    from app.services.file_parser import parse_file

    content = await file.read()
    try:
        # ⚠️ 丢到线程池：解析是同步的，老版 .doc 还会借 Word COM 转换，别冻住事件循环
        parsed = await asyncio.to_thread(parse_file, file.filename, content)
        return success({
            "textContent": parsed.get("textContent", ""),
            "format": target_format,
            "fileName": file.filename,
        })
    except Exception as e:
        return error(f"转换失败: {str(e)}")


@router.get("/check")
async def check_conversion_support(
    source: str = Query(...),
    target: str = Query("txt"),
):
    """检查转换支持"""
    supported = ["pdf", "doc", "docx", "txt", "md"]
    return success({
        "supported": source.lower().lstrip(".") in supported,
        "source": source,
        "target": target,
    })
