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
import asyncio
import os


async def _warmup_embedding() -> None:
    """后台预热本地 embedding 模型 + jieba 分词器（失败只记日志，绝不抛）

    见 `lifespan` 里关于「第一次出题卡 60 秒」的说明。

    ⚠️ 两件事都要预热（2026-10-21 实测发现）：
      只预热 embedding 时，首个思考仍需 5.1s —— 日志显示
      `embedding 预热完成` 之后 **20 秒**才出现 `jieba 词典预热完成`，
      说明 jieba 首次 `initialize()` 也在首个检索的同步路径上。
      两个懒加载都清了，首字延迟才真正降下来。
    """
    from loguru import logger

    # ① jieba 分词词典（RAG 检索的全文查询要用；首次建缓存约数秒）
    try:
        from app.services.rag import tokenizer as tok

        t0 = asyncio.get_event_loop().time()
        await asyncio.to_thread(tok._ensure_ready)  # noqa: SLF001 - 预热专用
        logger.info(
            "[startup] jieba 预热完成，耗时 {:.1f}s", asyncio.get_event_loop().time() - t0
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[startup] jieba 预热失败（首次检索会慢）: {}", e)

    # ② embedding 模型（2.17GB，冷启动实测 43s）
    try:
        from app.services.rag import embedding as emb

        t0 = asyncio.get_event_loop().time()
        await emb.embed_query("预热")
        logger.info(
            "[startup] embedding 预热完成，耗时 {:.1f}s（首次出题不再卡）",
            asyncio.get_event_loop().time() - t0,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[startup] embedding 预热失败（服务仍可用，首次检索会慢）: {}", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    await redis_client.connect()
    await init_db()

    # 创建上传目录
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # ── 从 sys_config 载入 RAG 运行时配置（2026-10-22）──────────────
    #
    # 后台「AI 配置 → 知识库向量化」改的值存在 sys_config 里，进程重启后
    # 内存里的覆盖值就没了。这里读一次塞回 embedding 模块，
    # 保证「后台改过的配置」在重启后依然生效，而不是悄悄回到 .env 的默认值。
    from loguru import logger as _logger

    try:
        from app.database import async_session_factory
        from app.services.rag import embedding as emb
        from app.services.rag import rag_config_service

        async with async_session_factory() as _db:
            _cfg = await rag_config_service.get_config_map(_db)
            # 同时把云端 API Key 读进内存（后台填的优先，其次 .env）
            _cloud_key = await rag_config_service.load_cloud_api_key_from_db(_db)
        emb.refresh_runtime_config(
            backend=_cfg.get(rag_config_service.KEY_BACKEND),
            model=_cfg.get(rag_config_service.KEY_MODEL),
        )
        _logger.info(
            "[startup] RAG 配置已加载：backend={} model={} cloudKey={}",
            emb.current_backend(),
            emb.current_model(),
            "已配置" if _cloud_key else "未配置",
        )
    except Exception as e:  # noqa: BLE001
        _logger.warning("[startup] RAG 配置加载失败（回落 .env 默认值）: {}", e)

    # ── 后台预热 embedding 模型（2026-10-21）────────────────────────────
    #
    # ★ 为什么必须预热 ★
    #   用户报：「第一次进入足足等待了 60 多秒，ai 生成那边才生成深度思考的内容」。
    #
    #   实测冷启动成本（独立进程，等价于后端刚起来）：
    #     · 首次 embed_query（含加载 BAAI/bge-m3，2.17GB）: **43.22s**
    #     · 第二次（纯推理）                              : 0.15s
    #
    #   而「出题 + 知识库」的链路是：
    #     _retrieve_kb_context → rqs.search → embed_query   ← 要等 43s
    #     → 组装 prompts → 调模型 → 才吐出第一个思考
    #
    #   这段等待发生在**模型调用之前**，所以用户连"思考中"都看不到，
    #   感知就是"点了完全没反应"。这就是"第一次卡一分钟"的大头。
    #
    #   为什么不在请求里懒加载：那等于让**第一个用户**替所有人付这笔钱。
    #   移到启动阶段，代价由部署过程吸收，第一个请求就是快的。
    #
    # ⚠️ 必须**不阻塞启动**（create_task 而非 await）：
    #   加载几十秒，若 await 在这里，这段时间整个服务不可用
    #   （健康检查、登录、静态资源全卡），比慢一点更糟。
    #   后台跑，失败也只是"首次检索仍慢"，不影响其它功能。
    warmup_task = None
    try:
        warmup_task = asyncio.create_task(_warmup_embedding())
    except Exception:  # noqa: BLE001
        warmup_task = None

    yield

    # Shutdown
    if warmup_task and not warmup_task.done():
        warmup_task.cancel()
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
