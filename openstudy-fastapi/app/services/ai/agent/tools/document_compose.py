"""
文档编排工具 —— 让用户在对话里直接产出排版好的 Word / PDF（2026-10-27）

============================================================================
它解决什么
============================================================================

用户的原话：

    「实现 word pdf 图文编排 排版 插入表格 图片 美化等能力
      用户给我们一段文字 或者 一个混乱的word 图文混乱
      我们可以给他进行优化重构 等操作
      用户通过对话 上传文件 或者 口述 让我们的ai自己制作一个出来 也可以」

三种用法对应工具的三个来源：

  ① `source="text"`  + `content`
     用户口述 / 贴一段文字 → AI 整理后产出文档

  ② `source="outline"` + `content`
     AI **直接生成**结构化描述（标题层级 / 表格 / 图片占位），
     交给渲染层出版

  ③ `source="file"`  + `file_id`
     用户上传了一个混乱的 Word → 解析 → 重新排版

## 为什么不做成 `bank_export` 的一个 action

`bank_export` 的语义是「把**题库**导出来」，参数是 `bank_id`，
数据源是数据库里的题目。这里的数据源是**用户给的任意内容**，
产物是通用文档。两者只有"最后都生成 docx"这一点相同。

混在一起的后果很具体：模型看到 `bank_export` 有 `action=compose`，
就会在"用户想要一份通用文档"时去传 `bank_id`，然后报错重试。

## 为什么这些参数都是可选的

模型经常只给一部分。比如用户说"帮我排个版"，模型可能只给 `content`
就完事。所有参数都设了合理默认值，**任何一种组合都要能出文件** ——
宁可样式朴素，也不能因为少了个参数就报错。

## 产物

走 `bank_export.save_export_file()` 落盘到 `export/`，
与其他导出产物共用同一套下载链路与前端卡片组件。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.ai.agent.tools.bank_export import save_export_file, _human_size

#: 可用主题（与 doc_compose_model.THEMES 一致，这里列出来是为了给模型看）
THEME_ALIASES = {
    "academic": "academic",
    "学术": "academic", "论文": "academic", "正式": "academic",
    "clean": "clean",
    "简洁": "clean", "现代": "clean", "默认": "clean",
    "report": "report",
    "报告": "report", "公文": "report",
}

#: 单次最多渲染多少字，超过就截断并告知
#:
#: 不是技术限制，是"一份文档超过 5 万字就不像文档、像数据集"的产品判断。
MAX_CONTENT_CHARS = 60000


class DocumentComposeTool(AgentTool):
    name = "document_compose"
    #: 界面显示名（中文，简短）
    label = "文档编排"
    description = (
        "Compose a well-formatted, print-ready Word (.docx) or PDF document "
        "from arbitrary content. Use this whenever the user wants a document "
        "produced with real layout: headings, lists, tables, images, cover page, "
        "table of contents, page numbers. "
        "Typical triggers: 'lay this out as a Word file', 'turn this into a "
        "report', 'make a PDF out of this', 'clean up this messy document'. "
        "\n"
        "Three sources:\n"
        "  · source='text'    — content is plain text / messy Markdown; it will be "
        "normalised (heading levels fixed, pseudo-tables converted to real tables, "
        "runaway paragraphs split, bullets standardised) then laid out.\n"
        "  · source='outline' — content is a JSON DocumentSpec you composed "
        "yourself ({title, subtitle, author, cover, toc, blocks:[{type,...}]}). "
        "Block types: heading(level 1-4) | paragraph | list | table | image | "
        "quote | code | divider | math | callout.\n"
        "  · source='file'    — file_path points at an already-uploaded document; "
        "it will be parsed and re-laid-out.\n"
        "\n"
        "The renderer reuses the same OMML pipeline as question-bank export, so "
        "LaTeX like $\\frac{a}{b}$ becomes a REAL Word equation, not backslashes."
    )
    description_zh = (
        "把任意内容排版成 Word / PDF：支持标题层级、列表、原生表格、图片、"
        "封面、目录、页眉页脚页码。三种来源——口述文字、AI 生成的结构化大纲、"
        "已上传的文件。会自动整理混乱的排版（标题层级、伪表格、粘连段落）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["text", "outline", "file"],
                "description": (
                    "Where the content comes from. 'text' = plain/messy markdown, "
                    "'outline' = a JSON DocumentSpec you wrote, "
                    "'file' = an already-uploaded document to re-layout."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Document content. Required when source is 'text' or 'outline'. "
                    "For 'outline' this must be a JSON object string matching "
                    "DocumentSpec: {title, subtitle, author, theme, cover, toc, "
                    "blocks:[{type,...}]}. Use $...$ for inline math and $$...$$ for "
                    "display math; the renderer converts them to native equations."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Path of an already-uploaded document (relative to the upload "
                    "directory, e.g. 'upload/2026/10/abc.docx'). Required when "
                    "source is 'file'."
                ),
            },
            "title": {
                "type": "string",
                "description": "Document title. Shown on the cover / as the top heading.",
            },
            "theme": {
                "type": "string",
                "description": (
                    "Layout theme. 'clean' (modern default), 'academic' "
                    "(serif, 1.5 line spacing, first-line indent — for papers), "
                    "'report' (formal, coloured headings — for reports)."
                ),
            },
            "format": {
                "type": "string",
                "enum": ["docx", "pdf", "both"],
                "description": "Output format. Default 'docx' (opens everywhere, user can save as PDF).",
            },
            "cover": {
                "type": "boolean",
                "description": "Generate a cover page. Recommended for documents over ~1500 characters.",
            },
            "toc": {
                "type": "boolean",
                "description": "Generate a table of contents. Only useful when there are 3+ headings.",
            },
            "author": {
                "type": "string",
                "description": "Author / organisation shown on the cover.",
            },
        },
        "required": ["source"],
    }

    #: 只读工具：不碰用户数据，只是生成文件 → 不需要二次确认
    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext):
        source = str(params.get("source") or "text").strip().lower()
        content = params.get("content") or ""
        file_path = str(params.get("file_path") or "").strip()
        title = str(params.get("title") or "").strip()
        author = str(params.get("author") or "").strip()
        theme = _normalize_theme(params.get("theme"))
        cover = _as_bool(params.get("cover"))
        toc = _as_bool(params.get("toc"))
        fmt = str(params.get("format") or "docx").strip().lower()
        if fmt not in ("docx", "pdf", "both"):
            fmt = "docx"
        want_pdf = fmt in ("pdf", "both")

        # ── 前置校验：按来源检查必需参数 ──
        if source == "file":
            if not file_path:
                return fail(
                    "请提供 file_path（要重新排版的文件路径）。"
                    "如果用户还没有上传文件，先请他上传，或改用 source='text' 直接排版文字。"
                )
        elif source == "outline":
            if not str(content).strip():
                return fail("source='outline' 需要在 content 里给出 JSON 结构（DocumentSpec）。")
        else:
            if not str(content).strip():
                return fail(
                    "内容为空，无法生成文档。请把用户要排版的文字放进 content，"
                    "或先与用户确认他要写什么。"
                )

        # ── 内容长度保护 ──
        note = ""
        if source != "outline" and len(str(content)) > MAX_CONTENT_CHARS:
            content = str(content)[:MAX_CONTENT_CHARS]
            note = f"（内容超过 {MAX_CONTENT_CHARS} 字，已截取前 {MAX_CONTENT_CHARS} 字）"

        # ── 按来源产出 ──
        #
        # ⚠️ `svc` 必须在这里导入：后面 outline / text / 重排三条分支都用它。
        #    原来写在 elif 内部，导致前面先用的分支 UnboundLocalError。
        from app.services import doc_compose_service as svc

        try:
            if source == "file":
                result = _compose_from_file(file_path, title=title, theme=theme,
                                            cover=cover, toc=toc, want_pdf=want_pdf)
            elif source == "outline":
                # ⚠️ 兼容 dict / JSON 字符串 / 被模型写坏的 JSON（2026-10-27 修）
                #
                # 用户反馈：「然后他反复报错 重试」
                #
                # 根因：`source='outline'` 要求 content 是**JSON 字符串**，
                # 但工具参数本身已经是 JSON 了，模型很自然地直接传一个**对象**
                # 或 Markdown 代码块包裹的字符串，于是 `json.loads(str(dict))`
                # 得到 `"{'title': …}"`（单引号）→ 必定 JSONDecodeError → 重试 → 又错。
                #
                # 实测那段对话里连续自我纠正了 2 次才成功，用户全程看着报错。
                #
                # 现在三条路都认：
                #   ① 已经是 dict / list → 直接用
                #   ② 字符串 → 先剥 ```json 围栏，再解析
                #   ③ 仍失败但看起来像 Markdown → 自动降级按 text 排（不是报错）
                spec_dict = _coerce_spec_content(content)
                if spec_dict is None:
                    # ③ 降级：把这段内容当成 Markdown 排
                    #
                    #    ⚠️ 不报错。用户要的是"一份好看的文档"，
                    #       outline 与 text 的区别对用户毫无意义，
                    #       能排出结果就比让他看着报错重试强。
                    result = svc.compose_from_markdown(
                        str(content), title=title, theme=theme,
                        cover=cover, toc=toc, want_pdf=want_pdf,
                    )
                    note += "（内容被当作 Markdown 排版；如需精确控制结构，可用 JSON 结构描述）"
                else:
                    if author and isinstance(spec_dict, dict) and not spec_dict.get("author"):
                        spec_dict["author"] = author
                    result = svc.compose_from_spec(spec_dict, want_pdf=want_pdf)
            else:
                result = svc.compose_from_markdown(
                    str(content), title=title, theme=theme,
                    cover=cover, toc=toc, want_pdf=want_pdf,
                )
                if author:
                    # 作者只在封面用到，重新渲一次成本很低（几十毫秒）
                    from app.services.doc_compose_model import DocumentSpec  # noqa: F401
                    result["spec"]["author"] = author
                    recomposed = svc.compose_from_spec(result["spec"], want_pdf=want_pdf)
                    result = recomposed
        except Exception as e:  # pragma: no cover - 兜底，避免整轮对话崩掉
            return fail(f"文档生成失败：{type(e).__name__}: {e}")

        # ── 落盘 ──
        base_name = _safe_name(title or result["spec"].get("title") or "文档")
        files = []

        try:
            rel, name = save_export_file(result["docx"], f"{base_name}.docx")
            files.append({"path": rel, "url": f"/profile/{rel}", "name": name,
                          "type": "docx", "size": len(result["docx"])})
        except OSError as e:
            return fail(f"Word 文件已生成但保存失败：{e}")

        if want_pdf and result.get("pdf"):
            try:
                rel2, name2 = save_export_file(result["pdf"], f"{base_name}.pdf")
                files.append({"path": rel2, "url": f"/profile/{rel2}", "name": name2,
                              "type": "pdf", "size": len(result["pdf"])})
            except OSError as e:
                note += f"（PDF 保存失败：{e}）"

        # ── 汇总给模型的信息 ──
        diag = result.get("analysis") or {}
        summary_bits = [
            f"已生成 {base_name}",
            f"共 {result['blockCount']} 个内容块",
            f"主题「{result['themeLabel']}」",
        ]
        issues = diag.get("issues") or []
        if issues:
            summary_bits.append(f"整理了 {len(issues)} 类排版问题：" + "、".join(issues[:4]))

        if want_pdf and not result.get("pdf"):
            summary_bits.append(f"PDF 未生成（{result.get('pdfError') or '未知原因'}）")

        # ⚠️ 补齐前端产物卡片所需的字段（2026-10-27 修）
        #
        # 前端 `AgentToolResult` 的产物卡片只认 `downloadUrl` / `fileName` /
        # `fileSizeText` / `format` 这几个**顶层**字段
        # （那是 `bank_export` 工具定的契约）。
        #
        # 最初这里只返回 `files: [{path, name, type, size}]`，
        # 结果对话里生成的 Word **根本没有下载卡片** —— 模型嘴上说"已生成"，
        # 用户手里什么都没有。这是实测发现的真缺陷。
        #
        # 现在两者都给：
        #   · 顶层 downloadUrl 等 → 前端卡片直接可用
        #   · files 数组        → 保留给需要多文件（docx+pdf）的场景
        #
        # ⚠️ 主文件必须**按用户要的格式**选（2026-10-27 修的真缺陷）
        #
        # 用户原话：「然后他说有一个pdf下载入口 我没看到有」
        #
        # 根因：`files` 里 docx 总是先 append、pdf 后 append，
        # 而这里取 `files[0]` —— 于是 `format='pdf'` 时
        # `downloadUrl` 指向 **.docx**、`format` 还硬写成 `"docx"`。
        # 前端产物卡片据此渲染，用户点下载拿到的是 Word，
        # 而模型在回复里说的是"PDF 已生成"。
        #
        # 现在：用户要 pdf 就把 pdf 当主文件；pdf 生成失败则回退 docx
        # 并把原因带出去（不能假装 PDF 有）。
        pdf_file = next((f for f in files if f["type"] == "pdf"), None)
        docx_file = next((f for f in files if f["type"] == "docx"), None)

        if fmt == "pdf" and pdf_file:
            primary, primary_fmt = pdf_file, "pdf"
        elif fmt == "both" and pdf_file:
            # both：主文件给 pdf（那是"最终交付物"形态），docx 仍可另取
            primary, primary_fmt = pdf_file, "pdf"
        else:
            primary, primary_fmt = docx_file or (files[0] if files else None), "docx"

        return ok(
            message="；".join(summary_bits) + note,
            data={
                "files": files,
                "downloadUrl": primary["url"] if primary else "",
                "fileName": primary["name"] if primary else "",
                "format": primary_fmt,
                "fileSize": primary["size"] if primary else 0,
                "fileSizeText": _human_size(primary["size"]) if primary else "",
                # docx 单独给一份：用户想继续编辑时要用
                "docxDownloadUrl": docx_file["url"] if docx_file else "",
                "docxFileName": docx_file["name"] if docx_file else "",
                "docxFileSizeText": _human_size(docx_file["size"]) if docx_file else "",
                # PDF 单独给一份（主文件可能就是它；重复给便于前端统一读）
                "pdfDownloadUrl": pdf_file["url"] if pdf_file else "",
                "pdfFileName": pdf_file["name"] if pdf_file else "",
                "pdfFileSizeText": _human_size(pdf_file["size"]) if pdf_file else "",
                "blockCount": result["blockCount"],
                "headingLevels": result["headingLevels"],
                "theme": result["theme"],
                "themeLabel": result["themeLabel"],
                "analysis": diag,
                "pdfError": result.get("pdfError"),
            },
        )


# ============================================================
# 辅助
# ============================================================

def _normalize_theme(raw: Any) -> str:
    """主题别名归一（模型可能传中文，也可能传大写）"""
    s = str(raw or "").strip().lower()
    if not s:
        return "clean"
    return THEME_ALIASES.get(s, "clean")


def _coerce_spec_content(content: Any) -> Optional[Dict[str, Any]]:
    """把 `content` 归一成 DocumentSpec 字典；实在不是结构化内容则返回 None

    这是为了消掉一类**反复失败重试**（2026-10-27 实测）：

        模型传 content = {title: "...", blocks: [...]}   ← 对象
        → `json.loads(str(content))` 得到 "{'title': ...}"（单引号，非 JSON）
        → JSONDecodeError → 重试 → 又传对象 → 又错

    工具参数**本身就是 JSON**，要求再套一层 JSON 字符串是反直觉的，
    模型写错几乎是必然而不是偶然。

    支持四种形态：
      ① dict / list          → 直接接受
      ② 纯 JSON 字符串        → json.loads
      ③ ```json 围栏包裹       → 剥围栏后 json.loads
      ④ 其他（像是 Markdown）  → 返回 None，调用方降级按 text 排
    """
    import json
    import re

    if isinstance(content, (dict, list)):
        return content if isinstance(content, dict) else {"blocks": content}

    if not isinstance(content, str):
        return None

    text = content.strip()
    if not text:
        return None

    # 剥 ```json / ``` 围栏（模型很爱包一层）
    m = re.match(r"^```(?:json|JSON)?\s*\n(.*?)\n?```\s*$", text, re.S)
    if m:
        text = m.group(1).strip()

    if not (text.startswith("{") or text.startswith("[")):
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # 第五种情况：单引号 / 尾逗号这类"近似 JSON"，
        # 用 ast 兜一次（它对 Python 字面量容错更好）。
        try:
            import ast

            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"blocks": parsed}
    return None


def _as_bool(v: Any) -> bool:
    """把模型给的各种"假值"写法统一成 False

    ⚠️ 模型把布尔写成字符串是常态：`"false"` / `"0"` / `"no"` 直接用
       `bool()` 都会得到 True（非空字符串就是真），必须显式判。
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s not in ("", "false", "0", "no", "none", "off", "null", "否", "不要", "不用")


def _safe_name(name: str) -> str:
    """清洗成合法文件名（保留中文，去掉 Windows 非法字符）"""
    import re

    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" ._")
    return (s or "文档")[:60]


def _compose_from_file(
    file_path: str,
    *,
    title: str,
    theme: str,
    cover: bool,
    toc: bool,
    want_pdf: bool,
) -> Dict[str, Any]:
    """读取已上传的文件 → 解析 → 重排

    ⚠️ 路径必须限制在 UPLOAD_DIR 之下：
       模型给的 `file_path` 来自工具返回值，但用户也可能在对话里
       直接说一个路径。不做限制就等于给了任意文件读取能力。
    """
    from app.config import settings
    from app.services import doc_compose_service as svc
    from app.services.file_parser import parse_file

    raw = file_path.replace("\\", "/").lstrip("/")
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    full = os.path.abspath(os.path.join(upload_root, raw))

    if not full.startswith(upload_root):
        raise ValueError("文件路径不在允许的上传目录内")

    if not os.path.isfile(full):
        # 再试一次：模型可能把 `upload/xxx` 写成 `xxx`
        alt = os.path.abspath(os.path.join(upload_root, os.path.basename(raw)))
        if alt.startswith(upload_root) and os.path.isfile(alt):
            full = alt
        else:
            raise ValueError(f"找不到文件：{file_path}")

    with open(full, "rb") as fh:
        blob = fh.read()

    parsed = parse_file(os.path.basename(full), blob)
    if parsed.get("error"):
        raise ValueError(f"文件解析失败：{parsed['error']}")

    return svc.compose_from_file(
        parsed, title=title, theme=theme, cover=cover, toc=toc, want_pdf=want_pdf
    )
