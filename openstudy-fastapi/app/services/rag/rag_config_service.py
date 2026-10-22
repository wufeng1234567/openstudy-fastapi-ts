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
KEY_CLOUD_API_KEY = "rag.embedding.cloudApiKey"   # 硅基流动 API Key（后台可填）

DEFAULTS: Dict[str, str] = {
    KEY_BACKEND: "auto",
    KEY_MODEL: "BAAI/bge-m3",
    KEY_CHUNK_SIZE: "500",
    KEY_CHUNK_OVERLAP: "50",
    KEY_TOP_K: "5",
    KEY_RRF_K: "60",
    KEY_CLOUD_MODEL: "BAAI/bge-m3",
    KEY_AUTO_FALLBACK: "true",
    KEY_CLOUD_API_KEY: "",
}

#: 可选的后端枚举
BACKENDS = ("local", "siliconflow", "auto")

#: 云端向量化用的 provider 名（在 `sys_ai_config` 里的 provider 字段）
CLOUD_PROVIDER = "siliconflow"
#: 云端 embedding 默认模型
CLOUD_EMBEDDING_MODEL = "BAAI/bge-m3"


#: 运行时缓存的云端 API Key（进程内，避免每次向量化都查库）
_runtime_cloud_api_key: str = ""


def get_runtime_cloud_api_key() -> str:
    """给 siliconflow_client 用的同步读取（进程内缓存）。"""
    return _runtime_cloud_api_key


def refresh_runtime_cloud_api_key(key: str | None) -> None:
    """后台改了 Key 之后调用，让本进程立刻用新的。"""
    global _runtime_cloud_api_key
    _runtime_cloud_api_key = (key or "").strip()


async def load_cloud_api_key_from_db(db: AsyncSession) -> str:
    """启动时把 Key 从库里读进内存。返回实际生效的 key（可能来自 .env）。"""
    row = (
        await db.execute(select(SysConfig).where(SysConfig.config_key == KEY_CLOUD_API_KEY))
    ).scalar_one_or_none()
    key = (row.config_value or "").strip() if row else ""
    if not key:
        key = (settings.SILICONFLOW_API_KEY or "").strip()
    refresh_runtime_cloud_api_key(key)
    return key


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
        KEY_CLOUD_API_KEY: "RAG 云端 API Key（硅基流动）",
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
        KEY_CLOUD_API_KEY: "后台「知识库向量化」页可填；存入 sys_config，接口只回掩码",
    }.get(key, "")


# ============================================================
# 环境检测
# ============================================================
def detect_local_rag() -> Dict[str, Any]:
    """探测本机是否具备本地 RAG 的条件。

    ⚠️ 2026-10-22 修复：这里原先自己写了一套「找模型」的目录列表
    （`~/.cache/huggingface/hub`、`~/.cache/modelscope/hub` 等），
    **漏掉了真正在用的默认缓存目录 `~/.cache/modelscope/openstudy`**。
    结果：模型（2.27GB 的 pytorch_model.bin）明明就在硬盘上、本地向量化
    实测能跑通（1024 维 / 15.8s），页面却显示「未下载 → 本地未就绪」，
    把用户往云端引导。

    现在直接复用 `embedding.py` 的 `_find_model_dir()` + `DEFAULT_MODELSCOPE_DIR`
    —— 与真正加载模型时用的是**同一套判据**，检测结果不会再和实际行为偏差。

    返回：
      {
        "available": bool,          # 能否直接用本地
        "depsInstalled": bool,      # sentence-transformers 是否装了
        "modelCached": bool,        # 模型文件是否已下载
        "modelPath": str,           # 实际找到的模型目录
        "modelDir": str,            # 模型缓存根目录
        "modelName": str,
        "estimatedSizeMB": int,     # 模型大约多大
        "reason": str,              # 不可用时的一句话原因
        "suggestion": str,          # 给用户的可执行建议
      }
    """
    # 延迟导入：避免模块级循环依赖（embedding 会 import settings / dynamic_ai）
    from app.services.rag import embedding as emb

    model_name = emb.current_model()
    explicit_dir = (settings.EMBEDDING_MODEL_DIR or "").strip()

    # 1) 依赖是否装了
    deps = importlib.util.find_spec("sentence_transformers") is not None

    # 2) 模型是否已下载 —— 复用真实加载逻辑：先查显式目录，再查默认目录
    model_path = ""
    for root in (explicit_dir, emb.DEFAULT_MODELSCOPE_DIR):
        if not root or not os.path.isdir(root):
            continue
        found = emb._find_model_dir(root, model_name)
        if found:
            model_path = found
            break

    cached = bool(model_path)
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
        "modelPath": model_path,
        "modelDir": explicit_dir or emb.DEFAULT_MODELSCOPE_DIR,
        "modelName": model_name,
        "estimatedSizeMB": 2200,
        "reason": reason,
        "suggestion": suggestion,
    }


def _dir_has_weight(path: str) -> bool:
    """⚠️ 已废弃（2026-10-22）。

    原先用于判断「目录里有没有模型权重」，但它只看一层 + snapshots 子目录，
    漏掉了魔搭的真实落盘结构 `openstudy/BAAI/bge-m3/pytorch_model.bin`，
    导致误报「模型未下载」。现在检测统一走 `embedding._find_model_dir()`，
    与实际加载逻辑同源。此函数保留只为兼容可能的旧引用，新代码不要再用。
    """
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


async def detect_cloud_rag(db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """探测云端 RAG（硅基流动）是否可用。

    ⚠️ 2026-10-22 修复：原来只读 `.env` 的 `SILICONFLOW_API_KEY`，
    而**后台根本没有让用户填 Key 的入口** —— 页面上「云端（硅基流动）」
    永远显示「缺 Key」，用户有 Key 也没地方填。

    现在按优先级查三处：
      1. `sys_config` 的 `rag.embedding.cloudApiKey`（RAG 页专用，最贴近使用场景）
      2. `sys_ai_config` 里 provider=siliconflow 且启用的记录（后台「AI 配置」页可加）
      3. `.env` 的 `SILICONFLOW_API_KEY`（运维基线）
    """
    from app.models.ai_config import SysAiConfig  # 延迟导入，避免循环依赖

    key = ""
    source = ""

    if db is not None:
        # ① RAG 页自己存的 Key（最直接）
        row = (
            await db.execute(
                select(SysConfig).where(SysConfig.config_key == KEY_CLOUD_API_KEY)
            )
        ).scalar_one_or_none()
        if row and (row.config_value or "").strip():
            key = row.config_value.strip()
            source = "rag"

        # ② 后台「AI 配置」里加的硅基流动模型记录
        if not key:
            try:
                row = (
                    await db.execute(
                        select(SysAiConfig)
                        .where(SysAiConfig.provider == CLOUD_PROVIDER)
                        .where(SysAiConfig.status == "0")
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if row and (row.api_key or "").strip():
                    key = row.api_key.strip()
                    source = "ai_config"
            except Exception:
                pass

    # ③ .env 兜底
    if not key:
        env_key = (settings.SILICONFLOW_API_KEY or "").strip()
        if env_key:
            key = env_key
            source = "env"

    return {
        "available": bool(key),
        "keyConfigured": bool(key),
        "keySource": source,
        # 只回掩码，绝不把完整 Key 返给前端
        "keyMasked": (key[:6] + "••••" + key[-4:]) if len(key) > 12 else ("••••" if key else ""),
        "model": settings.AI_DEFAULT_EMBEDDING_MODEL or CLOUD_EMBEDDING_MODEL,
        "reason": "" if key else "还没有配置硅基流动的 API Key",
        "suggestion": "" if key else "在下方「云端 API Key」处粘贴你的硅基流动 Key（sk- 开头），保存后即可使用云端向量化",
    }


async def get_status(db: AsyncSession) -> Dict[str, Any]:
    """后台页面用：当前配置 + 两条链路各自是否可用 + 建议"""
    cfg = await get_config_map(db)
    local = detect_local_rag()
    cloud = await detect_cloud_rag(db)

    # ⚠️ 不要把 API Key 原值回给前端（哪怕 cfg 里有）
    cfg_safe = {k: v for k, v in cfg.items() if k != KEY_CLOUD_API_KEY}
    cfg_safe[KEY_CLOUD_API_KEY] = ""  # 前端只显示掩码，不回显原文

    current = cfg[KEY_BACKEND]
    effective = current
    if current == "auto":
        effective = "local" if local["available"] else ("siliconflow" if cloud["available"] else "unavailable")

    # 用户选了云端但没 Key / 选了本地但没模型时，要明确指出「差什么」
    blocked = ""
    if current == "siliconflow" and not cloud["available"]:
        blocked = "云端模式需要 API Key，请在上方填写"
    elif current == "local" and not local["available"]:
        blocked = "本地模式需要下载模型，可切换到云端或先安装本地模型"

    # 一句话结论，直接显示给用户
    if effective == "local":
        summary = "当前使用本地向量化：文档不出内网，不消耗云端额度"
    elif effective == "siliconflow":
        summary = "当前使用云端向量化（硅基流动）：无需本地模型，需要联网"
    else:
        summary = "当前没有可用的向量化后端：本地未安装模型、云端也没配 Key"

    return {
        "config": cfg_safe,
        "current": current,
        "effective": effective,
        "summary": summary,
        "blocked": blocked,
        "local": local,
        "cloud": cloud,
    }
