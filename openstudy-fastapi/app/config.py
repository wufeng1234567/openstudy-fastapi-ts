"""
应用配置管理
使用 pydantic-settings 从环境变量加载配置
"""

from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """应用配置"""

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 9101
    DEBUG: bool = True

    # MySQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "student_learning"
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    # Redis (Docker: redis-stack)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # JWT
    JWT_SECRET: str = "openstudy-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30

    # File Upload
    UPLOAD_DIR: str = "D:/ruoyi/uploadPath"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set = {
        "jpg", "jpeg", "png", "gif", "bmp",
        "pdf", "doc", "docx", "xls", "xlsx",
        "txt", "ppt", "pptx",
    }

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost", "http://localhost:3167", "http://localhost:80"]

    # AI Providers
    ZHIPU_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    SILICONFLOW_API_KEY: str = ""

    # AI Default Settings
    AI_DEFAULT_PROVIDER: str = "deepseek"
    AI_DEFAULT_MODEL: str = "deepseek-chat"
    AI_DEFAULT_EMBEDDING_MODEL: str = "embedding-3"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()
