"""
OCR API
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File
from app.core.security import get_current_user
from app.core.response import success, error

router = APIRouter(prefix="/ocr")


@router.post("/recognize")
async def ocr_recognize(
    file: UploadFile = File(...),
    lang: str = Query("chi_sim+eng"),
    current_user: dict = Depends(get_current_user),
):
    """OCR 识别图片中的文字"""
    import io
    from PIL import Image
    import pytesseract

    content = await file.read()
    try:
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang=lang)
        return success({"text": text.strip()})
    except Exception as e:
        return error(f"OCR 识别失败: {str(e)}")
