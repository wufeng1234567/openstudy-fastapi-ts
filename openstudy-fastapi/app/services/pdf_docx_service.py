"""
PDF 渲染服务（v3，2026-10-26 新增）
================================================================================

## 一句话

**DOCX → PDF**，用 LibreOffice 渲染我们的 Word 产物，让 PDF 与 Word 从
**同一份文件**出来，天然一致。

## 为什么不是「直接生成 PDF」

题库导出原本有两条独立实现：

  · `export_bank_docx()`  —— python-docx，手写 oxml，能做原生表格 / OMML 公式
  · `export_bank_pdf()`   —— reportlab，**没有 TeX 引擎**，复杂公式只能
    Unicode 近似（模块注释自己写着「可行的做法只有 ①图片公式 ②Unicode 近似」）

两条路各写一遍，就会出现「Word 里对、PDF 里错」的经典问题。实测（2026-10-26）：

    Word:  `∫₀¹ x²dx`  ← OMML 正排
    PDF :  `∫_0^1x^2dx` ← 压成一行，上下标没排上去

用户的要求是「复杂公式正确渲染，打印不走样」。既然 Word 侧已经做到了，
**让 PDF 复用它**是唯一能保证两端一致的工程方案 —— 而不是把同一件事做两遍。

## 三条候选路线的实测对比

| 方案 | 公式质量 | 耗时 | 结论 |
|---|---|---|---|
| reportlab Unicode 近似 | 差（分式压平、上下标丢失） | 0.8s | 保留为**兜底** |
| HTML+MathML + Edge 无头 | 优秀 | 1.5s | ❌ 本机渲染进程崩溃（见下） |
| **DOCX → LibreOffice → PDF** | **与 Word 逐像素一致** | **2.5s** | ✅ **采用** |

### 为什么放弃 Edge 路线

HTML + MathML 的视觉效果实测确实优秀（真分式、积分限正位）。
但在**被管制的进程环境里**，Chromium 的渲染进程起不来：

    Page.enable: {'code': -32000, 'message': 'Target crashed'}

根因是 Chromium 的多进程架构依赖**具名管道**做 IPC，而受限环境下
子进程无法打开具名管道。`/json/version`（纯 HTTP）能响应，
所以看起来「浏览器起来了」，但一开标签页渲染进程就崩。

相关实测记录（供排查时对照）：

    subprocess.run([msedge, --print-to-pdf])      → 挂到超时（120s）
    subprocess.Popen(...) + 轮询产物               → 产物 40s 内永不出现
    ShellExecuteW 启动 + CDP 打印                  → 端口就绪，但 Target crashed
    同一条命令在 PowerShell 里直接执行              → 7s 成功

**结论**：Edge 路线在普通机器上可用，在受限环境不可靠。
LibreOffice 是**单进程 + 自己的传输层**，实测稳定，所以选它。

## 实现要点

1. **不新增任何依赖**：用的是 DSH 自带的 `@deepseek-ai/libreoffice-kit`
   （预编译的 LibreOffice，无需用户装 Office / LibreOffice）。

2. **`TMP` 必须重定向**（踩过）：kit 会在 `%TMP%` 下 `mkdtemp`，
   而本机 `D:\Temp` 不可写 →

       EPERM: operation not permitted, mkdtemp 'D:\Temp\libreoffice-kit-XXXXXX'

   所以调用前把 `TMP` / `TEMP` / `TMPDIR` 全部指向我们自己的可写临时目录。

3. **失败必须回落**：任何环节出问题都返回 None，由调用方走 reportlab。
   演示当天只允许「降级」，不允许「导不出来」。

4. **`format=pdf` 行为不变**，新路是 `format=pdf_docx`（内部仍以 .pdf 返回）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from loguru import logger

# ──────────────────────────────────────────────────────────── LibreOffice kit 定位

#: kit 的 CLI 入口（相对 node_modules）
_KIT_CLI_REL = os.path.join(
    "@deepseek-ai", "dsh", "node_modules", "@deepseek-ai",
    "libreoffice-kit", "lib", "cli.js",
)


def _candidate_cli_paths() -> List[str]:
    """kit CLI 的候选位置（按优先级）"""
    out: List[str] = []

    # 1) 环境变量显式指定（部署时最可靠）
    env = os.environ.get("OS_PDF_KIT_CLI", "").strip()
    if env:
        out.append(env)

    # 2) 从 DSH 的安装位置推：DSH 会把依赖平铺在自身 node_modules 下
    dsh_home = os.environ.get("DSH_HOME", "").strip()
    for root in filter(None, [dsh_home]):
        out.append(os.path.join(root, "node_modules", _KIT_CLI_REL))

    # 3) 常见全局安装位置（Windows + nvm）
    node_prefixes = [
        os.environ.get("APPDATA", "") and os.path.join(os.environ["APPDATA"], "npm"),
        r"D:\nvm\nvm\v22.20.0\node_modules",
        r"C:\nvm\nvm\v22.20.0\node_modules",
        os.environ.get("ProgramFiles", "") and os.path.join(os.environ["ProgramFiles"], "nodejs"),
        os.environ.get("ProgramFiles(x86)", "") and os.path.join(os.environ["ProgramFiles(x86)"], "nodejs"),
    ]
    for p in filter(None, node_prefixes):
        out.append(os.path.join(p, _KIT_CLI_REL))
        out.append(os.path.join(p, "node_modules", _KIT_CLI_REL))

    # 4) 当前进程的工作目录往上找（开发环境最常命中）
    here = os.path.dirname(os.path.abspath(__file__))
    probe = here
    for _ in range(8):
        out.append(os.path.join(probe, "node_modules", _KIT_CLI_REL))
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    return [p for p in out if p and os.path.isfile(p)]


_KIT_CLI_CACHE: Optional[str] = None
_KIT_CLI_PROBED = False


def find_kit_cli() -> Optional[str]:
    """找到 libreoffice-kit 的 CLI 路径；找不到返回 None（结果缓存）"""
    global _KIT_CLI_CACHE, _KIT_CLI_PROBED
    if _KIT_CLI_PROBED:
        return _KIT_CLI_CACHE
    _KIT_CLI_PROBED = True
    hits = _candidate_cli_paths()
    _KIT_CLI_CACHE = hits[0] if hits else None
    if _KIT_CLI_CACHE:
        logger.info("[pdfdocx] 使用 LibreOffice kit: {}", _KIT_CLI_CACHE)
    else:
        logger.warning("[pdfdocx] 未找到 libreoffice-kit，DOCX→PDF 不可用")
    return _KIT_CLI_CACHE


def _find_node() -> Optional[str]:
    """找 node 可执行文件"""
    for name in ("node.exe", "node"):
        hit = shutil.which(name)
        if hit:
            return hit
    for p in (
        r"D:\nvm\nvm\v22.20.0\node.exe",
        r"C:\nvm\nvm\v22.20.0\node.exe",
        os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", "node.exe"),
    ):
        if p and os.path.isfile(p):
            return p
    return None


def is_available() -> bool:
    """本机能不能跑 DOCX→PDF"""
    return bool(find_kit_cli() and _find_node())


# ──────────────────────────────────────────────────────────── DOCX → PDF

#: 转换超时（秒）。670 题全量实测约 6~12s，留 3 倍余量。
_CONVERT_TIMEOUT = int(os.environ.get("OS_PDF_CONVERT_TIMEOUT", "180"))


def docx_to_pdf(docx_bytes: bytes, *, timeout: int = _CONVERT_TIMEOUT) -> Optional[bytes]:
    """
    DOCX 字节 → PDF 字节；失败返回 None

    流程：写临时 .docx → `node cli.js convert` → 读 .pdf

    ⚠️ `TMP` 重定向不是可选项：kit 在 `%TMP%` 下 `mkdtemp`，
       本机 `D:\Temp` 不可写会直接 EPERM 失败。见模块 docstring 第 2 点。
    """
    if not docx_bytes:
        return None

    kit = find_kit_cli()
    node = _find_node()
    if not kit or not node:
        logger.warning("[pdfdocx] 缺少 node 或 kit，跳过 DOCX→PDF")
        return None

    workdir = tempfile.mkdtemp(prefix="os_docx2pdf_")
    try:
        in_path = os.path.join(workdir, "in.docx")
        out_path = os.path.join(workdir, "out.pdf")
        with open(in_path, "wb") as f:
            f.write(docx_bytes)

        env = dict(os.environ)
        # 关键：把临时目录挪到我们自己的可写目录
        env["TMP"] = workdir
        env["TEMP"] = workdir
        env["TMPDIR"] = workdir

        cmd = [node, kit, "convert", "--input", in_path, "--output", out_path]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                # Windows 上别弹黑框
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            logger.warning("[pdfdocx] 转换超时（{}s）", timeout)
            return None

        if not os.path.isfile(out_path):
            logger.warning(
                "[pdfdocx] 转换未产出 PDF: rc={} out={!r} err={!r}",
                proc.returncode,
                (proc.stdout or "")[:300],
                (proc.stderr or "")[:300],
            )
            return None

        with open(out_path, "rb") as f:
            data = f.read()
        if len(data) < 600 or not data.startswith(b"%PDF"):
            logger.warning("[pdfdocx] 产物不是有效 PDF（{} 字节）", len(data))
            return None

        # kit 会回报缺失字体，值得记一笔（否则不知道为什么某个字显示成方块）
        try:
            info = json.loads((proc.stdout or "").strip().splitlines()[-1])
            missing = info.get("missingFonts") or []
            if missing:
                logger.warning("[pdfdocx] 缺失字体（可能显示为方块）: {}", missing)
        except Exception:  # noqa: BLE001
            pass

        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("[pdfdocx] DOCX→PDF 异常: {}", exc)
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def export_bank_pdf_via_docx(
    bank: Dict[str, Any],
    questions: List[Dict[str, Any]],
    *,
    with_answers: bool = True,
) -> Optional[bytes]:
    """
    题库 → PDF，走「先出 Word，再转 PDF」路线

    返回 None 表示不可用，调用方应回落 `export_bank_pdf`（reportlab）。
    """
    if not is_available():
        return None
    try:
        from app.services.bank_export_service import export_bank_docx

        docx = export_bank_docx(bank, questions, with_answers=with_answers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[pdfdocx] 生成 DOCX 失败: {}", exc)
        return None
    return docx_to_pdf(docx)


__all__ = [
    "find_kit_cli",
    "is_available",
    "docx_to_pdf",
    "export_bank_pdf_via_docx",
]
