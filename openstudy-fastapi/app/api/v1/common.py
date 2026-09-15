"""
通用接口 - 文件上传（对齐若依 /common/upload）
"""

from fastapi import APIRouter, UploadFile, File, Depends
from app.utils.file_util import save_upload_file
from app.core.response import error
from app.core.security import get_current_user

router = APIRouter()


@router.post("/common/upload")
async def upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """通用文件上传接口

    前端 ImageUpload 组件期望返回:
    { code: 200, fileName: "/profile/upload/2026/07/31/uuid.jpg" }
    """
    try:
        result = await save_upload_file(file, sub_dir="upload")
        # 返回若依兼容格式: fileName = 文件相对路径（含 profile/ 前缀）
        return {
            "code": 200,
            "msg": "操作成功",
            "fileName": result["fileUrl"],
        }
    except Exception as e:
        return error(f"上传失败: {str(e)}")
