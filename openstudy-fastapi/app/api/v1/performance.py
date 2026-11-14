"""前端性能采样接收与可读日志。

前端 PerformanceMonitor 每 10 秒上报一次 FPS / 长任务 / 节点规模，
这里把记录同时追加到 `logs/performance.log` 并保留最近 500 条，
方便在页面卡顿时回看具体时间、节点数和 hover/缩放场景。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.response import success
from app.core.security import get_current_user

router = APIRouter(prefix="/rag/performance")
logger = logging.getLogger("openstudy.performance")

_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
_LOG_FILE = _LOG_DIR / "performance.log"
_RECENT: Deque[Dict[str, Any]] = deque(maxlen=500)
_LOCK = threading.Lock()


class PerformanceSample(BaseModel):
    t: float = 0
    fps: float = 0
    frameMs: float = 0
    longTasks: int = 0


class PerformanceReport(BaseModel):
    sessionId: str = ""
    page: str = "knowledge-graph"
    kbId: int = 0
    nodeCount: int = 0
    edgeCount: int = 0
    fps: float = 0
    avgFrameMs: float = 0
    minFps: float = 0
    longTasks: int = 0
    action: str = ""
    samples: List[PerformanceSample] = Field(default_factory=list)


def _append(record: Dict[str, Any]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        # 简单轮转，避免长期运行把日志盘写满。
        try:
            if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > 5 * 1024 * 1024:
                backup = _LOG_FILE.with_suffix(".log.1")
                if backup.exists():
                    backup.unlink()
                os.replace(_LOG_FILE, backup)
        except OSError:
            pass
        with _LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        _RECENT.appendleft(record)
    logger.info("[perf] %s", line)


@router.post("/log")
async def report_performance(data: PerformanceReport, current_user: dict = Depends(get_current_user)):
    uid = int(current_user.get("userId") or current_user.get("user_id") or 0)
    record = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "userId": uid,
        **data.model_dump(),
    }
    _append(record)
    return success({"logged": True})


@router.get("/logs")
async def read_performance_logs(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """读取当前用户最近的性能采样，便于排查“某次hover/缩放特别卡”。"""
    uid = int(current_user.get("userId") or current_user.get("user_id") or 0)
    with _LOCK:
        items = [item for item in _RECENT if int(item.get("userId") or 0) == uid][: max(1, min(limit, 200))]
    return success({"items": items, "file": str(_LOG_FILE)})
