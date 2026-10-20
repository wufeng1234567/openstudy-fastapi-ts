"""
文本向量化

支持两种后端（由 `settings.EMBEDDING_BACKEND` 控制）：
  - `local`       —— 用本机 sentence-transformers 加载 `BAAI/bge-m3`（**无需任何外部 Key**）
  - `siliconflow` —— 调硅基流动云端 embeddings 接口（需 SILICONFLOW_API_KEY）
  - `auto`（默认）—— 优先 local，本地依赖缺失/加载失败时回退 siliconflow

⚠️ 维度必须与 `models/rag.py: EMBEDDING_DIM`（= 建表时 `vector(1024)`）一致。
   `BAAI/bge-m3` 为 1024 维，正好匹配。换维度不同的模型会让插入直接失败 ——
   故这里每次调用都校验维度并给出明确报错。
"""

from __future__ import annotations

import asyncio
import os
import threading
from loguru import logger

from app.config import settings
from app.models.rag import EMBEDDING_DIM
from app.services.ai.dynamic_ai import dynamic_ai

#: 单批条数。云端 embedding 接口对 batch 大小有限制；本地逐条/小批更稳
BATCH_SIZE = 16


class EmbeddingError(RuntimeError):
    """向量化失败（配置缺失、上游报错、维度不符）"""


# ============================================================
# 本地后端（sentence-transformers）
# ============================================================
_local_model = None          # 懒加载的 SentenceTransformer 实例
_local_lock = threading.Lock()
_local_load_failed = False   # 加载失败过就不再重试（避免每次请求都卡半天）


#: 魔搭默认缓存根目录（与 `EMBEDDING_MODEL_DIR` 未配置时的下载目标一致）
DEFAULT_MODELSCOPE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "modelscope", "openstudy"
)


def _find_model_dir(root: str, model_name: str) -> str | None:
    """在 `root` 下找**已经下载完整**的模型目录；找不到返回 None。

    判据用两样东西，缺一不可：
      · `config.json`  —— SentenceTransformer 加载必需；
      · 权重文件（`pytorch_model.bin` / `model.safetensors` / `*.bin` 分片）
        —— 只有 config 没有权重时（下载中断、只剩元数据）加载会失败，
        那时应该回退去下载**补齐**，而不是拿个残缺目录硬加载。

    `model_name` 形如 `BAAI/bge-m3`：优先按 `<root>/<model_name>` 精确匹配
    （魔搭 snapshot 的实际落盘结构），匹配不到再退回全盘遍历。
    """
    exact = os.path.join(root, *model_name.split("/"))
    candidates = [exact] if os.path.isdir(exact) else []
    if not candidates:
        for cur, _dirs, files in os.walk(root):
            if "config.json" in files:
                candidates.append(cur)

    for path in candidates:
        if not os.path.isfile(os.path.join(path, "config.json")):
            continue
        names = set(os.listdir(path))
        has_weights = any(
            n in names
            for n in ("pytorch_model.bin", "model.safetensors", "tf_model.h5")
        ) or any(n.endswith(".bin") or n.endswith(".safetensors") for n in names)
        if has_weights:
            return path
        logger.warning(
            f"[embedding] 目录 {path} 只有 config.json 没有权重文件，"
            "可能上次下载未完成，将尝试重新下载"
        )
    return None


def _resolve_local_model_path(model_name: str, cache_dir: str | None) -> str:
    """把模型名解析为**本地目录路径**。

    ⚠️ 国内服务器访问不了 huggingface.co（被墙），直接 `SentenceTransformer("BAAI/bge-m3")`
    会因下载失败而报错。这里**优先从魔搭（ModelScope）下载**到本地目录 —— 国内直连、快。
    只有魔搭不可用时才回退让 sentence-transformers 自己去 HF 下（可能失败）。

    返回可直接传给 SentenceTransformer 的路径（本地目录或原始模型名）。
    """
    # ① 先看**已经下载好的**模型（离线优先）
    #
    # ⚠️ 这里修过一个严重 bug（2026-10-20）：
    #   原代码只在 `cache_dir` 非空时才去查本地目录，而 `EMBEDDING_MODEL_DIR`
    #   默认是空串 → `cache_dir = None` → **复用分支永远不执行**。
    #   可下面第 ③ 步的下载目标 `cache_dir or DEFAULT_MODELSCOPE_DIR` 用的正是
    #   同一个默认目录 —— 也就是说：模型明明已经完整躺在默认目录里（2.17GB），
    #   代码却视而不见，每次都重新 `snapshot_download`，然后卡在下载锁上。
    #
    #   现象（用户报的"向量化一直失败"）：
    #     [embedding] 魔搭下载失败（[Errno 13] Permission denied: '...\.mdl'），
    #                 回退直连 HuggingFace（国内可能不通）
    #     → 对 huggingface.co 反复重试 5 轮、每轮 10s 超时 → 文档永远停在 status=3。
    #
    #   修法：默认目录也要检查。先查「显式配置的目录」，再查「默认缓存目录」。
    for root in (cache_dir, DEFAULT_MODELSCOPE_DIR):
        if not root or not os.path.isdir(root):
            continue
        found = _find_model_dir(root, model_name)
        if found:
            logger.info(f"[embedding] 复用已下载的本地模型目录：{found}")
            return found

    # ② 本地没有 → 从魔搭下载
    try:
        from modelscope import snapshot_download  # 延迟导入

        target = cache_dir or DEFAULT_MODELSCOPE_DIR
        logger.info(f"[embedding] 从魔搭(ModelScope)下载模型 {model_name} 到 {target}（首次较慢）…")
        try:
            local_dir = snapshot_download(model_name, cache_dir=target)
        except Exception as e:  # noqa: BLE001
            # 下载锁冲突（.mdl Permission denied）常见于「上次进程被杀后锁残留」或
            # 「两个进程同时下载」。此时**再查一次**本地目录 —— 很可能别人已经下完了，
            # 没必要回退到墙外的 HuggingFace 去空转超时。
            logger.warning(f"[embedding] 魔搭下载异常（{e}），复查本地目录…")
            found = _find_model_dir(target, model_name)
            if found:
                logger.info(f"[embedding] 下载异常但本地已完整，直接使用：{found}")
                return found
            raise
        logger.info(f"[embedding] 魔搭下载完成：{local_dir}")
        return local_dir
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[embedding] 魔搭下载失败（{e}），回退直连 HuggingFace（国内可能不通）")
        return model_name


def _load_local_model():
    """懒加载本地模型（线程安全）。失败时抛 EmbeddingError。"""
    global _local_model, _local_load_failed
    if _local_model is not None:
        return _local_model
    with _local_lock:
        if _local_model is not None:
            return _local_model
        if _local_load_failed:
            raise EmbeddingError("本地 embedding 模型此前加载失败，已跳过（不再重试）")
        try:
            # 延迟导入：没装 sentence-transformers 时不影响其它功能
            from sentence_transformers import SentenceTransformer
        except Exception as e:  # noqa: BLE001
            _local_load_failed = True
            raise EmbeddingError(
                f"本地 embedding 需要 sentence-transformers，但导入失败：{e}。"
                "请在 requirements 安装 sentence-transformers（或设 EMBEDDING_BACKEND=siliconflow）。"
            ) from e
        model_name = settings.AI_DEFAULT_EMBEDDING_MODEL
        cache_dir = (settings.EMBEDDING_MODEL_DIR or "").strip() or None
        try:
            path_or_name = _resolve_local_model_path(model_name, cache_dir)
            logger.info(f"[embedding] 加载本地模型 {path_or_name} …")
            _local_model = SentenceTransformer(path_or_name)
            logger.info("[embedding] 本地模型加载完成")
        except Exception as e:  # noqa: BLE001
            _local_load_failed = True
            raise EmbeddingError(
                f"本地 embedding 模型 {model_name} 加载失败：{e}。"
                "请检查网络能否从魔搭下载模型，或设 EMBEDDING_BACKEND=siliconflow 走云端。"
            ) from e
        return _local_model


def _embed_local(texts: list[str]) -> list[list[float]]:
    """本地向量化（同步，调用方用 to_thread 包）。"""
    model = _load_local_model()
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=BATCH_SIZE)
    return [list(map(float, v)) for v in vecs]


async def _embed_via_local(texts: list[str]) -> list[list[float]]:
    # encode 是 CPU 密集同步调用 → 丢线程池，避免阻塞事件循环
    return await asyncio.to_thread(_embed_local, texts)


async def _embed_via_siliconflow(texts: list[str]) -> list[list[float]]:
    model = settings.AI_DEFAULT_EMBEDDING_MODEL
    return await dynamic_ai.embeddings(texts=texts, model=model)


def _resolve_backend() -> str:
    """决定本次用哪个后端。auto 时先试 local（依赖能导入就算可用）。"""
    backend = (settings.EMBEDDING_BACKEND or "auto").strip().lower()
    if backend in ("local", "siliconflow"):
        return backend
    # auto
    try:
        import sentence_transformers  # noqa: F401
        if not _local_load_failed:
            return "local"
    except Exception:  # noqa: BLE001
        pass
    return "siliconflow"


# ============================================================
# 对外接口
# ============================================================
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。返回顺序与入参一一对应。"""
    if not texts:
        return []

    model = settings.AI_DEFAULT_EMBEDDING_MODEL
    backend = _resolve_backend()
    logger.info(f"[embedding] backend={backend} model={model} 条数={len(texts)}")

    # auto 模式下：本地失败（模型下载不了 / 依赖缺失 / 维度不符）时，自动回退硅基流动
    auto_fallback = (settings.EMBEDDING_BACKEND or "auto").strip().lower() not in ("local", "siliconflow")

    async def _do(bk: str, batch: list[str]) -> list[list[float]]:
        if bk == "local":
            return await _embed_via_local(batch)
        return await _embed_via_siliconflow(batch)

    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        try:
            got = await _do(backend, batch)
        except EmbeddingError as e:
            if backend == "local" and auto_fallback:
                logger.warning(f"[embedding] 本地向量化失败，自动回退硅基流动：{e}")
                backend = "siliconflow"
                try:
                    got = await _do(backend, batch)
                except Exception as e2:  # noqa: BLE001
                    raise EmbeddingError(
                        f"本地与云端向量化均失败。本地：{e}；云端：{e2}"
                    ) from e2
            else:
                raise
        except Exception as e:  # 上游/网络/额度问题统一收口
            if backend == "local" and auto_fallback:
                logger.warning(f"[embedding] 本地向量化异常，自动回退硅基流动：{e}")
                backend = "siliconflow"
                try:
                    got = await _do(backend, batch)
                except Exception as e2:  # noqa: BLE001
                    raise EmbeddingError(
                        f"本地与云端向量化均失败。本地：{e}；云端：{e2}"
                    ) from e2
            else:
                raise EmbeddingError(f"向量化调用失败（backend={backend}, model={model}）: {e}") from e

        if len(got) != len(batch):
            raise EmbeddingError(
                f"向量化返回条数不符：请求 {len(batch)} 条，返回 {len(got)} 条"
            )
        vectors.extend(got)

    _validate_dim(vectors, model)
    return vectors


async def embed_query(text: str) -> list[float]:
    """查询词向量化。返回单个向量。"""
    vectors = await embed_texts([text])
    if not vectors:
        raise EmbeddingError("查询向量化返回空结果")
    return vectors[0]


def _validate_dim(vectors: list[list[float]], model: str) -> None:
    """只校验第一条 —— 同一模型同一次调用不会有不同维度，逐条查是浪费。"""
    if not vectors:
        return
    got = len(vectors[0])
    if got != EMBEDDING_DIM:
        raise EmbeddingError(
            f"向量维度不符：model={model} 返回 {got} 维，"
            f"但表结构是 vector({EMBEDDING_DIM})。"
            f"请改用 {EMBEDDING_DIM} 维的 embedding 模型"
            f"（或在 models/rag.py 改 EMBEDDING_DIM 并重建向量索引）。"
        )
