"""
老版 .doc（OLE2 二进制格式）→ .docx 转换 —— 借本机安装的 MS Word 完成

## 为什么要绕这一道

OLE2 的 Word 二进制格式（Word 97-2003）没有可靠的纯 Python 解析方案：
正文要解析 FIB + 分片表（piece table），插图藏在 `Data` 流的 Office Art / Escher 记录里，
自己写一遍风险极高。而本机装了 Word 的话，让 Word 自己转一次最省事 ——
转出来就是标准 .docx，后面交给 `file_parser._parse_docx()`（含抽图）即可。

## 调用方

只有 `file_parser.parse_file()` 在识别出 OLE2 容器时调它。
**不要**在别处直接调 —— 解析入口只有 `parse_file` 一个（见 file_parser 模块注释）。

## 设计要点（每条都是踩过坑才这么写的）

1. **`DispatchEx` 而不是 `Dispatch`**
   新开一个独立的隐藏 Word 进程。`Dispatch` 会attach到用户已经开着的 Word 实例，
   随后 `Quit()` 会把用户正在编辑的文档一起关掉 —— 绝对不能这么干。

2. **三个开关全关**
   `DisplayAlerts=0` + `AutomationSecurity=3`（强制禁用宏）+ `ConfirmConversions=False`。
   少关一个，Word 就会弹模态框等人点，而这里没人能点 → 后端线程永久卡住。

3. **跑在专用线程里 + 超时**
   COM 调用一旦阻塞就没法从外部取消，所以起一个专用线程（顺便满足「COM 要求每个线程
   自己 CoInitialize」），`join(timeout)` 等不到就放弃这次转换。

4. **超时只杀「我们自己新起的」Word 进程**
   超时后按 PID 差集精确清理，**绝不 `taskkill /IM WINWORD.EXE`** ——
   那会把用户自己开着的、可能没保存的文档一起干掉。

5. **按内容哈希做小 LRU 缓存**
   同一份 .doc 在一次发送里会被解析两遍（前端取预览块一次 + 后端喂模型一次），
   不缓存就是启动两次 Word。Word 冷启动约 4.4s，这一条省的是大头。

## 实测数据（本机 Word 16.0）

| 阶段 | 耗时 |
|---|---|
| `DispatchEx`（Word 冷启动） | **~4.4s** ← 大头，Office 自身成本 |
| `Documents.Open` | ~0.5s |
| `SaveAs2` | ~0.1s |
| `Quit()` + 宽限 + 强杀收尾 | ~1.5s |
| 合计（冷） | **~7s** |

`Quit()` 之后必须按 PID 兜底强杀 —— 实测**它不会真的结束进程**，
每个转换都会泄漏一个隐藏的 `WINWORD.EXE`。

## 环境要求

Windows + 装了 MS Word + 装了 `pywin32`。任一不满足时 `is_available()` 返回 False，
`convert_to_docx()` 返回 None，调用方按「转换不了」处理（给出「请另存为 .docx」的提示）。
"""

import gc
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Optional

from loguru import logger

#: 单次转换的硬超时（秒）。Word 冷启动 + 打开 + 另存，正常 1~3s；
#: 超过这个数基本可以认定卡住了（弹窗 / 坏文件 / Word 本体异常）。
CONVERT_TIMEOUT_SECONDS = 45

#: `Quit()` 之后等 Word 自己退出的宽限期（秒）。等不到就按 PID 强杀。
#: ⚠️ 必须是「等一会再杀」而不是「直接杀」：Quit 会顺带刷新 Normal.dotm 之类的全局状态，
#: 杀在中途可能把它写坏。
#: 实测本机 Word 16.0 上 `Quit()` **不会**真的结束进程（每个转换泄漏一个 WINWORD.EXE），
#: 所以这道兜底不是可选项。
_WORD_EXIT_GRACE_SECONDS = 1.0

#: 转换结果缓存条数（每条约等于一个 docx 的体积，别调太大）
_CACHE_SIZE = 4

#: Word 的 WdSaveFormat 常量
_WD_FORMAT_DOCX = 16  # wdFormatDocumentDefault → .docx

#: OLE2 复合文档里的标志性流名 → 真实格式（用于识别「.doc 其实是 .xls/.ppt」）
#:
#: ⚠️ 必须按 **UTF-16LE** 编码去找：OLE2 的目录项名字段是 UTF-16，
#: 直接搜 ASCII 字节永远搜不到（实测踩过：真 .doc 会被认成「认不出来」）。
_OLE2_STREAM_HINTS = (
    ("WordDocument", "doc"),
    ("Workbook", "xls"),
    ("Book", "xls"),
    ("PowerPoint Document", "ppt"),
)

#: 内容哈希 → 转换出来的 docx 字节
_docx_cache: "OrderedDict[str, bytes]" = OrderedDict()


# ============================================================
# 可用性 / 格式识别
# ============================================================
def is_available() -> bool:
    """当前环境能不能做 .doc 转换（非 Windows / 没装 pywin32 都是 False）"""
    if os.name != "nt":
        return False
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def ole2_flavor(content: bytes) -> str:
    """OLE2 容器里装的到底是什么：'doc' / 'xls' / 'ppt' / ''（认不出来）

    `.doc` / `.xls` / `.ppt` 都是 OLE2 复合文档，只看文件头分不开，
    要看容器里有没有标志性的流。流名在 OLE2 目录项里是 UTF-16LE 编码的，
    所以按 UTF-16LE 去搜（搜 ASCII 一定搜不到）。

    认不出来时返回空串 —— 调用方按 .doc 试一试（老 .doc 的流名理论上一定有，
    认不出多半是造得不太规范的第三方文件，给 Word 试一次没坏处）。
    """
    for stream, flavor in _OLE2_STREAM_HINTS:
        if stream.encode("utf-16-le") in content:
            return flavor
    return ""


# ============================================================
# 对外入口
# ============================================================
def convert_to_docx(content: bytes) -> Optional[bytes]:
    """老版 .doc 字节 → docx 字节；环境不支持 / 转换失败都返回 None

    ⚠️ 这是**阻塞**调用。本机实测一次约 **7s**，其中大头是 `DispatchEx` 的
    Word 冷启动（~4.4s，Office 自身的成本，省不掉）。所以：
      · 异步路由里调它必须用 `asyncio.to_thread` 兜住，否则会冻住事件循环；
      · 依赖下面的内容哈希缓存 —— 同一份 .doc 在一次发送里会被解析两遍
        （前端取预览块 + 后端喂模型），只有第一次真的启动 Word。
    """
    if not content or not is_available():
        return None

    key = hashlib.sha1(content).hexdigest()
    cached = _docx_cache.get(key)
    if cached is not None:
        _docx_cache.move_to_end(key)
        logger.debug("[doc-convert] 命中缓存，跳过 Word 转换")
        return cached

    converted = _convert_bounded(content)
    if converted:
        _docx_cache[key] = converted
        _docx_cache.move_to_end(key)
        while len(_docx_cache) > _CACHE_SIZE:
            _docx_cache.popitem(last=False)
    return converted


# ============================================================
# 超时控制
# ============================================================
def _convert_bounded(content: bytes) -> Optional[bytes]:
    """在专用线程里跑转换并加超时；超时就精确清理我们自己起的 Word 进程"""
    result: dict = {}
    # 转换前先记下已在运行的 Word 进程，超时/收尾时只清理「多出来的」
    pids_before = _winword_pids()

    def worker() -> None:
        try:
            result["data"] = _convert_with_word(content, pids_before)
        except Exception as e:  # noqa: BLE001 - 转换失败不该把调用方打挂
            logger.warning("[doc-convert] .doc 转换失败：{}", e)

    thread = threading.Thread(target=worker, name="doc2docx", daemon=True)
    thread.start()
    thread.join(CONVERT_TIMEOUT_SECONDS)

    if thread.is_alive():
        logger.warning(
            "[doc-convert] .doc 转换超时（{}s），放弃本次转换并清理 Word 进程",
            CONVERT_TIMEOUT_SECONDS,
        )
        _kill_winword(_winword_pids() - pids_before)
        return None
    return result.get("data")


def _convert_with_word(content: bytes, pids_before: set) -> Optional[bytes]:
    """真正干活的同步转换（在专用线程里执行）"""
    import pythoncom
    import win32com.client

    workdir = tempfile.mkdtemp(prefix="os-doc-convert-")
    src = os.path.join(workdir, "source.doc")
    dst = os.path.join(workdir, "converted.docx")
    with open(src, "wb") as f:
        f.write(content)

    # COM 要求每个线程自己初始化一次；这个线程是我们专用的，不会和别处串
    pythoncom.CoInitialize()
    word = None
    doc = None
    owned_pids: set = set()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        # DispatchEx 之后多出来的那个 Word 就是我们的，收尾时兜底清理它
        owned_pids = _winword_pids() - pids_before
        word.Visible = False
        word.DisplayAlerts = 0  # 不弹任何对话框（弹了没人点 → 卡死）
        word.AutomationSecurity = 3  # msoAutomationSecurityForceDisable：禁用宏
        doc = word.Documents.Open(
            src, ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False
        )
        doc.SaveAs2(dst, FileFormat=_WD_FORMAT_DOCX)
        doc.Close(False)
        doc = None

        if not os.path.exists(dst):
            return None
        with open(dst, "rb") as f:
            data = f.read()
        logger.info("[doc-convert] 老版 .doc 已转成 docx（{} bytes）", len(data))
        return data
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:  # noqa: BLE001 - 收尾失败不影响结果
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                pass
        # 必须显式放掉 COM 代理 + 强制回收，Quit 才可能真正生效
        del doc
        del word
        gc.collect()

        # ⚠️ 实测本机 Word 16.0 上 Quit() 不足以结束进程，必须按 PID 兜底清理。
        #    文件已经 SaveAs2 落盘了，这里杀掉是安全的。
        _await_winword_exit_then_kill(owned_pids)

        pythoncom.CoUninitialize()
        shutil.rmtree(workdir, ignore_errors=True)


# ============================================================
# Word 进程清理（只动我们自己起的）
# ============================================================
def _creation_flags() -> int:
    """让 tasklist / taskkill 不闪黑框"""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_tasklist(args: list) -> str:
    """跑一条 tasklist / taskkill 并拿到文本

    ⚠️ 不能用 `text=True`：中文 Windows 上 tasklist 输出是 GBK，
    Python 会按 UTF-8 解码并抛 UnicodeDecodeError（实测踩过）。
    这里按字节拿回来，再用 mbcs（= 系统 ANSI 代码页）解码。
    """
    completed = subprocess.run(
        args, capture_output=True, timeout=10, creationflags=_creation_flags()
    )
    raw = completed.stdout or b""
    for encoding in ("mbcs", "utf-8"):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


def _winword_pids() -> set:
    """当前 WINWORD.EXE 的 PID 集合；拿不到就返回空集（宁可漏杀也不误杀）"""
    try:
        text = _run_tasklist(
            ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"]
        )
    except Exception:  # noqa: BLE001
        return set()

    pids = set()
    for line in text.splitlines():
        # CSV 形如："WINWORD.EXE","12345","Console","1","123,456 K"
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].upper() == "WINWORD.EXE":
            try:
                pids.add(int(parts[1]))
            except ValueError:
                continue
    return pids


def _kill_winword(pids) -> None:
    """按 PID 强杀 Word 进程

    ⚠️ 绝不能改成 `taskkill /IM WINWORD.EXE`：那会把用户自己开着的、
    可能还没保存的文档一起干掉。这里只会收到「我们自己新起的」那些 PID。
    """
    for pid in sorted(pids or ()):
        try:
            _run_tasklist(["taskkill", "/PID", str(pid), "/F"])
            logger.warning("[doc-convert] 已强制结束 Word 进程 pid={}", pid)
        except Exception:  # noqa: BLE001
            logger.warning("[doc-convert] 结束 Word 进程 pid={} 失败", pid)


def _await_winword_exit_then_kill(pids) -> None:
    """先给 `Quit()` 一点时间让 Word 自己退；到点还没退就按 PID 强杀

    ⚠️ 只 sleep 一次再查一次 —— 别写成「每 0.2s 轮询一次」：
    每次调 tasklist 都要新起一个进程（~0.2s），轮询下来光查进程就多花一两秒。
    文件此时已经 SaveAs2 落盘，所以强杀不会丢数据。
    """
    remaining = set(pids or ())
    if not remaining:
        return
    time.sleep(_WORD_EXIT_GRACE_SECONDS)
    remaining &= _winword_pids()
    if remaining:
        _kill_winword(remaining)
