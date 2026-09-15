"""
文件工具函数
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import settings


def generate_filename(original_filename: str) -> str:
    """生成唯一文件名"""
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return unique_name


def get_upload_path(sub_dir: str = "upload") -> str:
    """获取上传目录路径"""
    today = datetime.now().strftime("%Y/%m/%d")
    upload_path = os.path.join(settings.UPLOAD_DIR, sub_dir, today)
    os.makedirs(upload_path, exist_ok=True)
    return upload_path


def get_file_url(relative_path: str) -> str:
    """获取文件访问 URL（统一使用正斜杠）"""
    return f"/profile/{relative_path.replace(chr(92), '/')}"


def validate_file(file: UploadFile, allowed_extensions: set = None) -> bool:
    """验证文件类型"""
    if not allowed_extensions:
        allowed_extensions = settings.ALLOWED_EXTENSIONS

    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: .{ext}",
        )
    return True


async def save_upload_file(
    file: UploadFile,
    sub_dir: str = "upload",
    max_size: int = None,
) -> dict:
    """保存上传文件"""
    # 验证文件类型
    validate_file(file)

    # 验证文件大小
    if max_size is None:
        max_size = settings.MAX_FILE_SIZE

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制: {max_size // (1024*1024)}MB",
        )

    # 生成文件路径
    filename = generate_filename(file.filename)
    upload_path = get_upload_path(sub_dir)
    file_path = os.path.join(upload_path, filename)

    # 保存文件
    with open(file_path, "wb") as f:
        f.write(content)

    # 返回相对路径（统一正斜杠）
    relative_path = os.path.relpath(file_path, settings.UPLOAD_DIR).replace("\\", "/")
    return {
        "fileName": file.filename,
        "filePath": relative_path,
        "fileUrl": get_file_url(relative_path),
        "fileSize": len(content),
    }


def delete_file(file_path: str) -> bool:
    """删除文件"""
    full_path = os.path.join(settings.UPLOAD_DIR, file_path)
    if os.path.exists(full_path):
        os.remove(full_path)
        return True
    return False
