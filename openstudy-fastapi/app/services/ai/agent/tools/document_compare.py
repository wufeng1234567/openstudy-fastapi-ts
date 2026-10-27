"""
文档对比工具 —— 让用户在对话里问"这两份文件有什么区别"（2026-10-27）

============================================================================
它解决什么
============================================================================

用户需求原话：

    「需要迭代的 方向有 表格整理功能 比如 用户向智能体提问
      我这里有两份文件 很混乱 或者 说 有什么区别
      需要智能体可以梳理 并且清晰的指点出来
      并且需要用户是否需要下载等等操作」

三种说话方式要能对应到同一个动作：

    ① 「这两份文件有什么区别」        → action=compare
    ② 「帮我把这个表格整理一下」      → action=tidy_table
    ③ 「整理完给我一份对比报告」      → action=compare + want_report=true

============================================================================
为什么必须有这个工具（而不是让模型自己读两份文件比）
============================================================================

长文档对比是模型最容易出错的地方，而且**错了很难被发现**：

    · 「少了一行」—— 模型经常漏
    · 「3.5 变成 3.6」—— 数字差异最容易被忽略
    · 「第 3 行第 2 列变了」—— 表格里的差异模型基本看不准

所以差异要**先算出来**（`doc_compare_service`），再让模型基于结论做解释。
模型负责"怎么跟用户讲"，不负责"哪里不一样"。

============================================================================
下载
============================================================================

对比报告本身就是一份文档，走 `document_compose` 同一个渲染引擎出 docx。
`want_report=true` 时直接生成文件并返回下载链接 —— 用户问完就能拿到。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.ai.agent.tools.bank_export import save_export_file
from app.services import doc_compare_service as cmp


class DocumentCompareTool(AgentTool):
    name = "document_compare"
    label = "文档对比"
    description = (
        "Compare two uploaded documents and report the differences precisely, "
        "or tidy up a messy table. Use this when the user has two versions of a "
        "file and asks what changed, or hands over an ugly table that needs "
        "clean-up. "
        "\n"
        "Actions:\n"
        "  · compare    — diff two documents. Returns a structured summary "
        "(paragraphs changed/added/removed, table rows added/removed, individual "
        "cell values that changed, headings that only exist on one side). "
        "Set want_report=true to also produce a downloadable .docx report.\n"
        "  · tidy_table — clean a messy table: fill blank leading cells left by "
        "merged cells, drop empty rows, de-duplicate repeated headers, trim "
        "whitespace. Returns the cleaned table plus a list of what was changed.\n"
        "\n"
        "IMPORTANT: the differences are computed by a deterministic engine, not "
        "guessed. Trust the returned numbers and cell-level diffs — do not "
        "re-derive them from the raw text. Your job is to explain them to the "
        "user clearly, not to find them."
    )
    description_zh = (
        "对比两份文档并精确指出差异（段落改动/增删、表格行增删、单元格数值变化、"
        "标题差异），也可整理混乱的表格（填补合并单元格残留、删空行、重名表头去重）。"
        "可选生成一份可下载的对比报告。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["compare", "tidy_table"],
                "description": "compare = diff two documents; tidy_table = clean up a messy table.",
            },
            "left_path": {
                "type": "string",
                "description": (
                    "Path of the first / older document (relative to the upload "
                    "directory, e.g. 'upload/2026/10/abc.docx'). Required for compare."
                ),
            },
            "right_path": {
                "type": "string",
                "description": (
                    "Path of the second / newer document. Required for compare."
                ),
            },
            "left_name": {
                "type": "string",
                "description": "Display name for the first document, e.g. '合同 v1'.",
            },
            "right_name": {
                "type": "string",
                "description": "Display name for the second document, e.g. '合同 v2'.",
            },
            "want_report": {
                "type": "boolean",
                "description": (
                    "Also generate a downloadable .docx diff report. "
                    "Set true when the user asks for a file / report / 报告."
                ),
            },
            "table_markdown": {
                "type": "string",
                "description": (
                    "For tidy_table: the messy table as Markdown, or plain text "
                    "with columns separated by tabs / multiple spaces. "
                    "Read it from the user's message or from an uploaded file."
                ),
            },
        },
        "required": ["action"],
    }

    #: 只读：不写用户数据，只生成可选报告文件
    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext):
        action = str(params.get("action") or "").strip().lower()

        if action == "tidy_table":
            return self._tidy_table(params)
        if action == "compare":
            return self._compare(params)

        return fail(
            f"未知 action：{action}（只能是 compare 或 tidy_table）",
            hint="action 只能是 compare（对比两份文档）或 tidy_table（整理表格）",
        )

    # ------------------------------------------------------------
    # 对比
    # ------------------------------------------------------------

    def _compare(self, params: Dict[str, Any]):
        left_path = str(params.get("left_path") or "").strip()
        right_path = str(params.get("right_path") or "").strip()

        if not left_path or not right_path:
            return fail(
                "对比需要两份文件。请提供 left_path 与 right_path"
                "（用户上传文件后，工具返回里会带 path）。",
                hint="如果用户还没上传文件，先请他把两份文件都发上来。",
            )

        left_name = str(params.get("left_name") or "").strip() or _base(left_path)
        right_name = str(params.get("right_name") or "").strip() or _base(right_path)

        try:
            lp = _load_parsed(left_path)
            rp = _load_parsed(right_path)
        except Exception as e:  # noqa: BLE001
            return fail(f"读取文件失败：{e}")

        result = cmp.compare_documents(lp, rp, left_name=left_name, right_name=right_name)
        summary = result["summary"]

        # ── 生成可下载报告 ──
        files: List[Dict[str, Any]] = []
        if _as_bool(params.get("want_report")):
            try:
                from app.services import doc_compose_service as svc
                from app.services.ai.agent.tools.bank_export import _human_size

                title = f"{left_name} 与 {right_name} 对比报告"
                composed = svc.compose_from_markdown(
                    result["markdown"], title=title, theme="report", cover=True, toc=False
                )
                rel, name = save_export_file(composed["docx"], f"{_safe(title)}.docx")
                files.append({
                    "path": rel,
                    "url": f"/profile/{rel}",
                    "name": name,
                    "type": "docx",
                    "size": len(composed["docx"]),
                    "sizeText": _human_size(len(composed["docx"])),
                })
            except Exception as e:  # noqa: BLE001
                # 报告生成失败不影响对比结论
                summary = dict(summary)
                summary["reportError"] = f"报告生成失败：{e}"

        # ⚠️ 顶层字段：前端产物卡片（`AgentToolResult`）只认这几个，
        #    只给 `files` 数组的话，用户在对话里**看不到下载按钮**。
        primary = files[0] if files else None

        return ok(
            message=summary["verdict"],
            data={
                "summary": summary,
                "structure": result["structure"],
                "tables": result["tables"],
                "text": result["text"],
                # 给模型一份可直接引用的 Markdown（也可直接展示给用户）
                "markdown": result["markdown"],
                "files": files,
                "downloadUrl": primary["url"] if primary else "",
                "fileName": primary["name"] if primary else "",
                "format": "docx",
                "fileSize": primary["size"] if primary else 0,
                "fileSizeText": primary.get("sizeText", "") if primary else "",
                "leftName": left_name,
                "rightName": right_name,
            },
        )

    # ------------------------------------------------------------
    # 表格整理
    # ------------------------------------------------------------

    def _tidy_table(self, params: Dict[str, Any]):
        raw = str(params.get("table_markdown") or "").strip()
        if not raw:
            return fail(
                "没有拿到表格内容。请把表格放进 table_markdown，"
                "或先请用户上传文件 / 把表格贴进对话。"
            )

        from app.services.doc_compose_parser import parse_markdown

        # 用文档解析层的表格识别（同时支持 Markdown 表格与制表符对齐的伪表格）
        spec = parse_markdown(raw)
        tables = [b.table for b in spec.blocks if b.type == "table" and b.table]
        if not tables:
            return fail(
                "没能从内容里识别出表格。表格需要至少两行、列数一致"
                "（Markdown 用 | 分隔，或纯文本用 Tab / 多个空格对齐）。"
            )

        tidied = [cmp.tidy_table(t) for t in tables]
        md = cmp.tables_to_markdown([t["table"] for t in tidied])

        total_changes = sum(t["changeCount"] for t in tidied)
        all_changes: List[str] = []
        for t in tidied:
            all_changes.extend(t["changes"])

        msg = (
            f"整理完成，共识别 {len(tables)} 张表、做了 {total_changes} 项调整。"
            if total_changes
            else f"识别到 {len(tables)} 张表，没有需要调整的地方（本来就整齐）。"
        )

        return ok(
            message=msg,
            data={
                "tables": [t["table"] for t in tidied],
                "changes": all_changes,
                "changeCount": total_changes,
                "markdown": md,
                "tableCount": len(tables),
            },
        )


# ============================================================
# 辅助
# ============================================================

def _load_parsed(file_path: str) -> Dict[str, Any]:
    """读取已上传文件并解析

    ⚠️ 路径必须限制在 UPLOAD_DIR 之下：
       模型给的 path 来自工具返回值，但用户也可能在对话里直接说一个路径。
       不做限制就等于给了任意文件读取能力。
    """
    from app.config import settings
    from app.services.file_parser import parse_file

    raw = file_path.replace("\\", "/").lstrip("/")
    upload_root = os.path.abspath(settings.UPLOAD_DIR)

    candidates = [os.path.abspath(os.path.join(upload_root, raw))]
    # 模型有时会把 `upload/xxx` 写成 `xxx`
    candidates.append(os.path.abspath(os.path.join(upload_root, os.path.basename(raw))))

    full: Optional[str] = None
    for c in candidates:
        if not (c == upload_root or c.startswith(upload_root + os.sep)):
            continue
        if os.path.isfile(c):
            full = c
            break

    if not full:
        raise FileNotFoundError(f"找不到文件：{file_path}")

    with open(full, "rb") as fh:
        blob = fh.read()

    parsed = parse_file(os.path.basename(full), blob)
    if parsed.get("error"):
        raise ValueError(f"文件解析失败：{parsed['error']}")
    return parsed


def _base(p: str) -> str:
    return os.path.basename((p or "").replace("\\", "/")) or p


def _as_bool(v: Any) -> bool:
    """把模型给的各种"假值"写法统一成 False"""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s not in ("", "false", "0", "no", "none", "off", "null", "否", "不要", "不用")


def _safe(name: str) -> str:
    import re

    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" ._")
    return (s or "对比报告")[:60]
