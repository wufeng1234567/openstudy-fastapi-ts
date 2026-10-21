---
name: 不要 gitignore 掉 _probe_*.py 探针
description: 本仓库的 tests/_probe_*.py 是刻意保留入库的验证工具，禁止加忽略规则
type: feedback
from: Agent
---

**不要给 `tests/_probe_*.py` 之类探针文件添加 `.gitignore` 忽略规则——它们是仓库正式资产（刻意保留入库的验证工具）。**

**Why:** 2026-10-09 在 `delivery` 分支整理 `.gitignore` 时，Agent 误加了一条过宽规则 `openstudy-fastapi/tests/_probe_*.py`。实测仓库里既有探针（如 `_probe_nested_commit.py` 被 docstring 引为证据、`_kbdisable_probe.py`）**全部已被 git 跟踪**，说明它们是刻意保留的。忽略规则虽不影响已跟踪文件，却会挡住**新探针**（如 `_probe_knowledge_ingest.py`）入库。
**How to apply:** 整理 `.gitignore` 时，探针 `.py` 源码（`tests/_probe_*.py`）应保持可入库；只忽略探针的**输出**（`_probe_*.txt` / `_probe_*.json`）与运行时证据目录（`tests/_evidence/`、`tests/_ui_evidence/`）。判定前先确认既有同类文件是否已被 `git ls-files` 跟踪。
