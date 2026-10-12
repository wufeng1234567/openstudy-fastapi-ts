"""
AI 模型配置模型（sys_ai_config 表）
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, SmallInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SysAiConfig(Base):
    """AI 模型配置表"""
    __tablename__ = "sys_ai_config"

    config_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[Optional[str]] = mapped_column(String(100))
    # 「模型类型」：official=我方预置的官方 API；relay=用户自建/中转站。
    # 与 provider 解耦，作为「是否发 DeepSeek 专有 thinking 形状」的唯一判据
    # （旧逻辑靠猜 base_url 是否含 deepseek.com，会被"provider=deepseek + 自建网关"骗到）。
    # 可空 = 老数据；为空时 db_config 回退旧的 base_url 判据。
    model_kind: Mapped[Optional[str]] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[Optional[str]] = mapped_column(String(500))
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    # ---- DeepSeek 网页端反代（provider = deepseek-free）专用凭据 ----
    # 用于以手机号 + 密码登录 chat.deepseek.com 换取 token。
    # 注意：这是明文存储，仅适合自用环境；接口返回时会做脱敏处理。
    web_phone: Mapped[Optional[str]] = mapped_column(String(50))
    web_password: Mapped[Optional[str]] = mapped_column(String(200))
    web_area_code: Mapped[Optional[str]] = mapped_column(String(10))
    is_default: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_enabled: Mapped[int] = mapped_column(SmallInteger, default=1)
    status: Mapped[Optional[str]] = mapped_column(String(1), default="0")
    remark: Mapped[Optional[str]] = mapped_column(String(500))
    thinking_mode: Mapped[Optional[str]] = mapped_column(String(20))
    reasoning_effort: Mapped[Optional[str]] = mapped_column(String(20))
    context_length: Mapped[Optional[str]] = mapped_column(String(20))
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_by: Mapped[Optional[str]] = mapped_column(String(64))
    update_by: Mapped[Optional[str]] = mapped_column(String(64))
