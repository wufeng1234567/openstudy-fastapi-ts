# ============================================================
# OpenStudy FastAPI 后端镜像
# ------------------------------------------------------------
# 基础镜像 python:3.11-slim（Debian），与开发机 Python 3.11 对齐。
# 构建上下文为 openstudy-fastapi/ 目录。
#
# 说明：
#   - pywin32 在 requirements.txt 里已用 sys_platform=="win32" 标记，
#     Linux 构建时 pip 会自动跳过，不会报错。
#   - .doc(OLE2) 转 .docx 依赖 Windows + MS Word，容器内不可用，
#     代码里 doc_converter.is_available() 会自动降级（不影响启动）。
#   - tesseract 系可选依赖（OCR 链路已被多模态取代），这里一并预装
#     中文包，避免用户上传图片识别时缺系统库。
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 系统依赖：
#   - build-essential / libpq-dev：asyncpg、cryptography 等编译期需要
#   - tesseract-ocr + 中文包：图片文字识别（可选能力，预装更省心）
#   - curl：健康检查用
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        tesseract-ocr \
        tesseract-ocr-chi-sim; \
    rm -rf /var/lib/apt/lists/*

# 先装依赖，利用 Docker 层缓存：requirements 不变则不会重复安装
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制应用代码
COPY . .

# 上传目录（可被 compose 的 volume 覆盖）
RUN mkdir -p /app/data/uploadPath

ENV HOST=0.0.0.0 \
    PORT=9101

EXPOSE 9101

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=10 \
    CMD curl -fsS http://localhost:9101/health || exit 1

# 生产模式：不带 --reload，交给 uvicorn 直接托管
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9101", "--log-level", "info"]
