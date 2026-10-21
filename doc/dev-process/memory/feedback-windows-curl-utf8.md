---
name: Windows/bash 下 curl 传中文需用 --data-binary 保证 UTF-8
description: 在 Windows bash 环境用 curl 发送含中文的请求体时，须用 --data-binary 而非 -d，否则中文会按 GBK 编码导致乱码
type: feedback
from: Agent
---

在 Windows bash 环境下用 `curl` 向服务端 API 发送**含中文**的请求体（如写仓库 description）时，必须用 `--data-binary` 并以 UTF-8 编码发送，**不要用 `-d`**。更稳妥的做法是用 Python（显式设置 UTF-8）发请求。

**Why:** 2026-10-09 建 GitCode 仓库时用 `curl -d` 传中文 description，Windows bash 下按 GBK 编码发出，导致仓库描述在 GitCode 上显示为乱码，需后续用 API 重新修复。
**How to apply:** 凡是在本 Windows 环境用 curl 往外部系统提交含中文的内容（仓库描述、提交信息、API 字段），一律用 `--data-binary`（或 Python + UTF-8）；写入后如条件允许刷新确认显示是否正常。
