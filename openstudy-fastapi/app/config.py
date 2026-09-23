"""
应用配置管理
使用 pydantic-settings 从环境变量加载配置
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """应用配置"""

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 9101
    DEBUG: bool = True

    # ---- 数据库引擎选择 ----
    # `postgres`（默认，主线） / `mysql`（**回滚用**，迁移完成后仍保留，改这一个值即可切回）
    # 两套连接参数并存，互不干扰；业务代码一行都不用改（SQLAlchemy ORM 是方言无关的）。
    DB_DRIVER: str = "postgres"

    # MySQL（回滚备用，openstudy_v2）
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "openstudy_v2"
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"

    # PostgreSQL（主线，openstudy_v2_pgsql；需 pgvector + pg_trgm 扩展）
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_NAME: str = "openstudy_v2_pgsql"
    PG_USER: str = "root"
    PG_PASSWORD: str = ""

    @property
    def IS_POSTGRES(self) -> bool:
        return (self.DB_DRIVER or "").strip().lower() != "mysql"

    @property
    def PG_URL(self) -> str:
        # 凭据里的特殊字符必须转义，否则含 @ : / 的密码会把 URL 拼坏
        return (
            f"postgresql+asyncpg://{quote_plus(self.PG_USER)}:{quote_plus(self.PG_PASSWORD)}"
            f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_NAME}"
        )

    @property
    def MYSQL_URL(self) -> str:
        return (
            f"mysql+aiomysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def DATABASE_URL(self) -> str:
        """业务代码只认这一个入口；切库只改 DB_DRIVER。"""
        return self.MYSQL_URL if not self.IS_POSTGRES else self.PG_URL

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

    # DeepSeek Web 模式（反代网页端 API）—— ⚠️ 已废弃，仅作历史开关保留
    #    ds-free 现由浏览器扩展实现（apps/deepseek-proxy 代发 chat.deepseek.com），
    #    后端不再注册反代客户端，这几个变量对运行时**没有任何影响**。
    #    下面这些值只在直接调用 app/services/ai/deepseek_web_client.py 时才会被读取。
    DEEPSEEK_WEB_ENABLED: bool = False
    DEEPSEEK_WEB_PHONE: str = ""
    DEEPSEEK_WEB_PASSWORD: str = ""
    DEEPSEEK_WEB_AREA_CODE: str = "+86"
    # ---- 浏览器会话材料导入（会话导入模式）----
    # 以下值从 chat.deepseek.com 的 localStorage / Application 面板抄出，
    # 属于用户自己的会话数据；填了就优先用它们，不再走脚本登录。
    DEEPSEEK_WEB_TOKEN: str = ""
    DEEPSEEK_WEB_COOKIE: str = ""
    DEEPSEEK_WEB_HIF_DLIQ: str = ""
    DEEPSEEK_WEB_HIF_LEIM: str = ""
    DEEPSEEK_WEB_DEVICE_ID: str = ""

    # AI Default Settings
    AI_DEFAULT_PROVIDER: str = "deepseek"
    # 官方模型名：`deepseek-flash`（DeepSeek-V4.1-Flash） / `deepseek-v4-pro`
    # ⚠️ 旧名 `deepseek-v4-flash` 仍可调用，但对应模型**已下线**（请求由 V4.1-Flash 提供服务），
    #    新配置一律用 `deepseek-flash`。别名收敛见 `services/ai/deepseek_client.py` 的 MODEL_ALIASES。
    AI_DEFAULT_MODEL: str = "deepseek-flash"
    # RAG 向量化的模型。实测：DeepSeek 官方**没有** embeddings 接口，智谱 key 余额不足，
    # 所以走硅基流动。1024 维，必须与 `models/rag.py: EMBEDDING_DIM` 保持一致。
    AI_DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()
