"""
RAG 向量化后端配置服务 —— 本地 / 云端开关 + 环境检测 + 可视化配置

设计要点
========
1. **两层配置**
   · `.env` 的 `EMBEDDING_BACKEND` 是**进程启动时的默认值**（运维层）；
   · 后台页面改的是 `sys_config` 里的 `rag.embedding.*`，**运行时生效**（产品层）。
   · 读取顺序：`sys_config` 有值就用它，没值才回落到 `.env`。
     这样不重启服务也能切换，而运维仍可用 .env 定基线。

2. **为什么要「检测」而不是直接切**
   本地 RAG 依赖 `sentence-transformers` + 约 2.2GB 的 bge-m3 模型文件。
   用户机器上很可能没装。直接切到 local 再失败，用户只会看到「向量化失败」，
   不知道该怎么办。所以先探测、给出可执行的建议，再让用户选。

3. **配置项都存 sys_config**
   不新增表 —— 后台「参数设置」页本来就能看到它们，运维可审计。
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import SysConfig

# ============================================================
# 配置键名（统一前缀 rag.embedding.）
# ============================================================
KEY_BACKEND = "rag.embedding.backend"          # local | siliconflow | auto
KEY_MODEL = "rag.embedding.model"              # BAAI/bge-m3
KEY_CHUNK_SIZE = "rag.embedding.chunkSize"     # 分块大小
KEY_CHUNK_OVERLAP = "rag.embedding.chunkOverlap"
KEY_TOP_K = "rag.embedding.topK"               # 检索返回条数
KEY_RRF_K = "rag.embedding.rrfK"               # RRF 平滑常数
KEY_CLOUD_MODEL = "rag.embedding.cloudModel"   # 云端模型名
KEY_AUTO_FALLBACK = "rag.embedding.autoFallback"  # 本地失败是否自动回落云端

DEFAULTS: Dict[str, str] = {
    KEY_BACKEND: "auto",
    KEY_MODEL: "BAAI/bge-m3",
    KEY_CHUNK_SIZE: "500",
    KEY_CHUNK_OVERLAP: "50",
    KEY_TOP_K: "5",
    KEY_RRF_K: "60",
    KEY_CLOUD_MODEL: "BAAI/bge-m3",
    KEY_AUTO_FALLBACK: "true",
}

#: 可选的后端枚举
BACKENDS = ("local", "siliconflow", "auto")


# ============================================================
# 读 / 写
# ============================================================
async def get_config_map(db: AsyncSession) -> Dict[str, str]:
    """读出所有 rag.embedding.* 配置（缺的用默认值补齐）"""
    rows = (
        await db.execute(select(SysConfig).where(SysConfig.config_key.like("rag.embedding.%")))
    ).scalars().all()
    got = {r.config_key: (r.config_value or "") for r in rows}
    return {k: got.get(k, v) for k, v in DEFAULTS.items()}


async def set_config(db: AsyncSession, key: str, value: str) -> None:
    """写入单个配置（不存在则创建）"""
    if key not in DEFAULTS:
        raise ValueError(f"未知配置项：{key}")
    row = (
        await db.execute(select(SysConfig).where(SysConfig.config_key == key))
    ).scalar_one_or_none()
    if row:
        row.config_value = str(value)
    else:
        db.add(
            SysConfig(
                config_name=_label_of(key),
                config_key=key,
                config_value=str(value),
                config_type="Y",
                create_by="system",
                remark=_remark_of(key),
            )
        )
    await db.flush()


async def set_configs(db: AsyncSession, items: Dict[str, Any]) -> None:
    for k, v in items.items():
        if v is None:
            continue
        await set_config(db, k, str(v).lower() if isinstance(v, bool) else str(v))


def _label_of(key: str) -> str:
    return {
        KEY_BACKEND: "RAG 向量化后端",
        KEY_MODEL: "RAG 本地向量化模型",
        KEY_CHUNK_SIZE: "RAG 分块大小",
        KEY_CHUNK_OVERLAP: "RAG 分块重叠",
        KEY_TOP_K: "RAG 检索返回条数",
        KEY_RRF_K: "RAG 混合检索 RRF 常数",
        KEY_CLOUD_MODEL: "RAG 云端向量化模型",
        KEY_AUTO_FALLBACK: "RAG 本地失败自动回落云端",
    }.get(key, key)


def _remark_of(key: str) -> str:
    return {
        KEY_BACKEND: "local=本地模型；siliconflow=云端；auto=优先本地、失败回退云端",
        KEY_MODEL: "必须是 1024 维的 embedding 模型（与表结构 vector(1024) 一致）",
        KEY_CHUNK_SIZE: "文档切片的目标字符数",
        KEY_CHUNK_OVERLAP: "相邻切片的重叠字符数，避免语义被切断",
        KEY_TOP_K: "每次检索返回的片段数",
        KEY_RRF_K: "RRF 融合的平滑常数，越大越平滑（论文建议 60）",
        KEY_CLOUD_MODEL: "硅基流动上可用的 embedding 模型名",
        KEY_AUTO_FALLBACK: "true=本地失败时自动改用云端；false=直接报错",
    }.get(key, "")


# ============================================================
# 环境检测
# ============================================================
def detect_local_rag() -> Dict[str, Any]:
    """探测本机是否具备本地 RAG 的条件。

    返回：
      {
        "available": bool,          # 能否直接用本地
        "depsInstalled": bool,      # sentence-transformers 是否装了
        "modelCached": bool,        # 模型文件是否已下载
        "modelDir": str,            # 模型缓存目录
        "modelName": str,
        "estimatedSizeMB": int,     # 模型大约多大
        "reason": str,              # 不可用时的一句话原因
        "suggestion": str,          # 给用户的可执行建议
      }
    """
    model_name = settings.AI_DEFAULT_EMBEDDING_MODEL or "BAAI/bge-m3"
    model_dir = (settings.EMBEDDING_MODEL_DIR or "").strip()

    # 1) 依赖是否装了
    deps = importlib.util.find_spec("sentence_transformers") is not None

    # 2) 模型是否已缓存
    cached = False
    search_roots = []
    if model_dir:
        search_roots.append(model_dir)
    # 常见缓存位置（HF / ModelScope / 项目内）
    home = os.path.expanduser("~")
    search_roots += [
        os.path.join(home, ".cache", "huggingface", "hub"),
        os.path.join(home, ".cache", "modelscope", "hub"),
        os.path.join(home, ".cache", "modelscope", "hub", "models"),
    ]
    safe_name = model_name.replace("/", os.sep)
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        # 直接命中模型目录，或命中 HF 的 models--org--name 形式
        candidates = [
            os.path.join(root, safe_name),
            os.path.join(root, "models--" + model_name.replace("/", "--")),
            os.path.join(root, model_name.replace("/", "_")),
        ]
        for c in candidates:
            if os.path.isdir(c) and _dir_has_weight(c):
                cached = True
                break
        if cached:
            break

    available = deps and cached
    reason = ""
    suggestion = ""
    if not deps:
        reason = "本机未安装 sentence-transformers，无法加载本地向量化模型"
        suggestion = (
            "执行 pip install -r requirements-local-embedding.txt 后重启后端；"
            "或在下方把后端切换到「云端（硅基流动）」，无需本地模型即可使用知识库检索"
        )
    elif not cached:
        reason = f"本地模型 {model_name} 尚未下载（首次使用需约 2.2GB）"
        suggestion = (
            "保持「本地」并上传第一份文档，系统会自动从魔搭下载模型；"
            "若网络受限，可切换到「云端（硅基流动）」，只需配置 SILICONFLOW_API_KEY"
        )

    return {
        "available": available,
        "depsInstalled": deps,
        "modelCached": cached,
        "modelDir": model_dir or (search_roots[0] if search_roots else ""),
        "modelName": model_name,
        "estimatedSizeMB": 2200,
        "reason": reason,
        "suggestion": suggestion,
    }


def _dir_has_weight(path: str) -> bool:
    """目录里是否有模型权重文件（粗略判断，够用）"""
    try:
        for name in os.listdir(path):
            if name.endswith((".bin", ".safetensors", ".onnx", ".pt")):
                return True
            sub = os.path.join(path, name)
            if os.path.isdir(sub) and name.startswith("snapshots"):
                for root, _dirs, files in os.walk(sub):
                    if any(f.endswith((".bin", ".safetensors", ".onnx", ".pt")) for f in files):
                        return True
    except Exception:
        return False
    return False


def detect_cloud_rag() -> Dict[str, Any]:
    """探测云端 RAG（硅基流动）是否可用"""
    key = (settings.SILICONFLOW_API_KEY or "").strip()
    return {
        "available": bool(key),
        "keyConfigured": bool(key),
        "model": settings.AI_DEFAULT_EMBEDDING_MODEL or "BAAI/bge-m3",
        "reason": "" if key else "未配置 SILICONFLOW_API_KEY，云端向量化不可用",
        "suggestion": "" if key else "在 openstudy-fastapi/.env 里填写 SILICONFLOW_API_KEY 后重启后端，或在后台「AI 配置」里添加硅基流动模型",
    }


async def get_status(db: AsyncSession) -> Dict[str, Any]:
    """后台页面用：当前配置 + 两条链路各自是否可用 + 建议"""
    cfg = await get_config_map(db)
    local = detect_local_rag()
    cloud = detect_cloud_rag()

    current = cfg[KEY_BACKEND]
    effective = current
    if current == "auto":
        effective = "local" if local["available"] else ("siliconflow" if cloud["available"] else "unavailable")

    # 一句话结论，直接显示给用户
    if effective == "local":
        summary = "当前使用本地向量化：文档不出内网，不消耗云端额度"
    elif effective == "siliconflow":
        summary = "当前使用云端向量化（硅基流动）：无需本地模型，需要联网"
    else:
        summary = "当前没有可用的向量化后端：本地未安装模型、云端也没配 Key"

    return {
        "config": cfg,
        "current": current,
        "effective": effective,
        "summary": summary,
        "local": local,
        "cloud": cloud,
    }
