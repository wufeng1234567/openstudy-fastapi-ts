"""
OpenStudy FastAPI 应用入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db, close_db
from app.redis import redis_client
from app.core.exceptions import (
    ServiceException,
    service_exception_handler,
    http_exception_handler,
    general_exception_handler,
)
from app.core.middleware import RequestIdMiddleware, LogMiddleware
from app.core.rate_limit import AiRateLimitMiddleware
from fastapi.exceptions import HTTPException
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    await redis_client.connect()
    await init_db()

    # 创建上传目录
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    yield

    # Shutdown
    await redis_client.disconnect()
    await close_db()


import logging

# 抑制 uvicorn 冗余异常日志（由 custom handler 处理）
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)

app = FastAPI(
    title="OpenStudy API",
    description="OpenStudy Online Learning Platform",
    version="1.0.0",
    docs_url="/swagger-ui.html",
    openapi_url="/v3/api-docs",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware
app.add_middleware(RequestIdMiddleware)
app.add_middleware(LogMiddleware)
app.add_middleware(AiRateLimitMiddleware)

# Exception handlers
app.add_exception_handler(ServiceException, service_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Static files (with placeholder fallback)
from app.core.static_files import StaticFilesWithPlaceholder
app.mount("/profile", StaticFilesWithPlaceholder(directory=settings.UPLOAD_DIR), name="uploads")

# 预置轮播图静态资源（随镜像打包，见 app/static/carousel/）
# 首页轮播图的图片地址取自 sys 库 carousel.image_url，种子数据指向 /carousel-static/xxx.jpg
import os as _os
_carousel_dir = _os.path.join(_os.path.dirname(__file__), "static", "carousel")
_os.makedirs(_carousel_dir, exist_ok=True)
app.mount("/carousel-static", StaticFiles(directory=_carousel_dir), name="carousel-static")

# Include routers
# ⚠️ 注意：notices 和 notice_front 都有 /system/notice/listAll 端点
# 由于 notices 先注册，它的 /listAll 会优先匹配并处理请求
# notice_front 的 /listAll 被忽略，如需使用请先注册 notice_front
from app.api.v1 import (
    auth, users, notices, questions, ai, dashboard,
    carousel, courses, words, notes, system, leave_message,
    sensitive_word, chat, ocr, document, notice_front, user_front,
    noteQuestionBank, noteQuestion, user_stats,
    common, catch_all, ai_config, bankShare, notification, systemComment,
    rag, rate_limit_admin, bank_export,
)

app.include_router(auth.router, tags=["认证"])
app.include_router(users.router, tags=["用户管理"])
app.include_router(notices.router, tags=["通知公告"])  # ⚠️ 先注册，/listAll 优先匹配
# ⚠️ 题库导出必须**先于** questions 注册：questions 里有 `/questionBank/questionBank/{bank_id}`，
#    若它先注册，`/questionBank/questionBank/12/export` 不会被它匹配（段数不同），
#    但 `/questionBank/questionBank/export` 这类同段数路径会被当成 bank_id 解析 → 422。
#    导出端点路径更具体，先注册更稳。
app.include_router(bank_export.router, tags=["题库导出"])
app.include_router(questions.router, tags=["题库题目"])
app.include_router(ai.router, tags=["AI功能"])
app.include_router(dashboard.router, tags=["仪表盘"])
app.include_router(carousel.router, tags=["轮播图"])
app.include_router(courses.router, tags=["课程"])
app.include_router(words.router, tags=["词书单词"])
app.include_router(notes.router, tags=["笔记"])
app.include_router(noteQuestionBank.router, tags=["笔记题库关联"])
app.include_router(noteQuestion.router, tags=["笔记题目关联"])
app.include_router(system.router, tags=["系统管理"])
app.include_router(leave_message.router, tags=["留言板"])
app.include_router(sensitive_word.router, tags=["敏感词"])
app.include_router(chat.router, tags=["聊天"])
app.include_router(ocr.router, tags=["OCR"])
app.include_router(document.router, tags=["文档"])
app.include_router(notice_front.router, tags=["前台通知"])
app.include_router(user_front.router, tags=["前台用户"])
app.include_router(user_stats.router, tags=["用户统计"])
app.include_router(common.router, tags=["通用接口"])
app.include_router(ai_config.router, tags=["AI模型配置"])
app.include_router(bankShare.router, tags=["题库分享"])
app.include_router(notification.router, tags=["站内通知"])
app.include_router(systemComment.router, tags=["评论管理"])  # 后台 /system/comment/*（此前缺失，落到 catch_all 假成功）
app.include_router(rag.router, tags=["RAG知识库"])
app.include_router(rate_limit_admin.router, tags=["AI限流管理"])
# Catch-all 路由必须最后注册
app.include_router(catch_all.router, tags=["默认路由"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "code": 200,
        "msg": "OpenStudy API is running",
        "data": {
            "version": "1.0.0",
            "docs": "/swagger-ui.html",
        },
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
