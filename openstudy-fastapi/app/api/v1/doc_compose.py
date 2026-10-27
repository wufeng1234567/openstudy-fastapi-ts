"""
文档编排 REST 接口（2026-10-27）

============================================================================
为什么需要这一层
============================================================================

用户需求：

    「加入一个独立的"文档编排"页面 让用户可以自己手动修改或者ai修改
      给不喜欢对话的用户提供更好的操作空间」
    「还要提供一个实时预览功能 比如智能体完成了输出一份word 或者pdf
      可以点击实时预览」

聊天工具 `document_compose` 解决的是"说一句话就出文件"，
但它**没法让人改**：改一个字就要重新说一遍，说三遍模型可能三次都不一样。

所以这条 REST 链路是给**编辑器**用的：

    POST /ai/docCompose/render     内容 → 生成文件，返回可访问 URL
    POST /ai/docCompose/preview    同上，但只返回 HTML 预览（不落盘正式产物）
    GET  /ai/docCompose/templates  主题清单（前端下拉用）
    POST /ai/docCompose/polish     调 AI 改进内容（编辑器里的「AI 优化」按钮）

## 为什么返回 URL 而不是直接返回字节

编辑器要**反复预览**：改一个字就要看一次效果。
每改一次都下载一遍文件，浏览器会堆积几十个 blob，且没法在新标签页打开。

落盘 + 返回 URL 的好处：
  · 前端可以直接 `window.open(url)` 新标签页查看
  · `docx-preview` 可以 `fetch(url)` 拿 ArrayBuffer 渲染
  · 同一份内容多次预览只产生一次渲染成本（URL 可缓存）

## 与聊天工具的关系

两条路**共用同一个渲染引擎**（`doc_compose_service`），
不会出现"聊天生成的和页面生成的不一样"。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.response import error, success
from app.core.security import get_current_user
from app.services import doc_compose_service as svc
from app.services.doc_compose_model import THEMES, get_theme

router = APIRouter(tags=["文档编排"])


# ============================================================
# 请求体
# ============================================================

class RenderBody(BaseModel):
    """渲染请求

    `markdown` 与 `spec` 二选一：
      · markdown —— 手写/粘贴的内容（编辑器主路径）
      · spec     —— 结构化描述（AI 生成 / 二次编辑保留结构）
    """

    markdown: str = ""
    spec: Optional[Dict[str, Any]] = None
    title: str = ""
    subtitle: str = ""
    author: str = ""
    theme: str = "clean"
    cover: bool = False
    toc: bool = False
    header: str = ""
    footer: str = ""
    #: 是否同时产出 PDF（编辑器预览用 docx 就够，下载时再选）
    wantPdf: bool = False
    #: 文件名（不含扩展名）
    filename: str = "文档"


class PreviewBody(RenderBody):
    """预览请求：与渲染同参，但默认不产 PDF、不生成封面（预览要快）"""

    cover: bool = False
    toc: bool = False
    wantPdf: bool = False


class PolishBody(BaseModel):
    """AI 优化内容

    编辑器里的「AI 优化」按钮：用户框选/整篇给 AI，让模型改进排版结构。
    """

    markdown: str = ""
    instruction: str = Field(default="整理这段内容的排版结构", description="用户的具体要求")
    theme: str = "clean"


# ============================================================
# 渲染
# ============================================================

@router.post("/ai/docCompose/render")
async def render_document(
    body: RenderBody,
    current_user: dict = Depends(get_current_user),
):
    """把内容渲染成 docx（可选 pdf），返回可访问 URL

    ⚠️ 返回值里的 `url` 是**相对 UPLOAD_DIR 的路径**，
       前端拼 `/dev-api` + 静态文件前缀访问。
       不返回绝对 URL：部署域名可能变（本地 / 反代 / 公网），
       写死 host 会在换环境后失效。
    """
    if not body.markdown.strip() and not body.spec:
        return error("内容为空，无法生成文档")

    result = _compose(body)
    if isinstance(result, str):
        return error(result)

    files = _save_outputs(result, body.filename, want_pdf=body.wantPdf)
    if not files:
        return error("文件已生成但保存失败（请检查磁盘空间与上传目录权限）")

    return success(
        {
            "files": files,
            "url": next((f["url"] for f in files if f["type"] == "docx"), ""),
            "pdfUrl": next((f["url"] for f in files if f["type"] == "pdf"), ""),
            "pdfError": result.get("pdfError"),
            "spec": result["spec"],
            "blockCount": result["blockCount"],
            "theme": result["theme"],
            "themeLabel": result["themeLabel"],
            "analysis": result.get("analysis") or {},
        }
    )


@router.post("/ai/docCompose/preview")
async def preview_document(
    body: PreviewBody,
    current_user: dict = Depends(get_current_user),
):
    """预览：与 render 同参，但**强制只出 docx**（预览不需要 PDF）

    单独一个接口而不是给 render 加参数，是因为语义不同：
      · render  = 我要一份能下载的文件
      · preview = 我改了一个字，想立刻看效果

    预览路径要尽量快，所以：
      · 不出 PDF（LibreOffice 转换 1~3 秒）
      · 不生成封面/目录（除非请求里显式要）
    """
    if not body.markdown.strip() and not body.spec:
        return error("内容为空")

    result = _compose(body)
    if isinstance(result, str):
        return error(result)

    files = _save_outputs(result, body.filename, want_pdf=False)
    if not files:
        return error("预览文件保存失败")

    docx_file = next((f for f in files if f["type"] == "docx"), None)
    return success(
        {
            "url": docx_file["url"] if docx_file else "",
            "files": files,
            "spec": result["spec"],
            "blockCount": result["blockCount"],
            "themeLabel": result["themeLabel"],
            "analysis": result.get("analysis") or {},
        }
    )


# ============================================================
# 主题
# ============================================================

@router.get("/ai/docCompose/templates")
async def list_templates(current_user: dict = Depends(get_current_user)):
    """可用主题清单（前端下拉用）

    从 `THEMES` 动态生成，不在前端硬编码 —— 以后加主题只改后端。
    """
    items: List[Dict[str, Any]] = []
    for key, t in THEMES.items():
        items.append(
            {
                "value": key,
                "label": t.get("label", key),
                "bodyFont": t.get("bodyFont"),
                "headFont": t.get("headFont"),
                "bodySizePt": t.get("bodySizePt"),
                "lineSpacing": t.get("lineSpacing"),
                "firstLineIndentEm": t.get("firstLineIndentEm"),
                # 前端用它做"主题预览色块"
                "headColor": (t.get("headColors") or ["1F2329"])[0],
                "tableHeaderFill": t.get("tableHeaderFill"),
            }
        )
    return success({"items": items, "default": "clean"})


# ============================================================
# AI 优化
# ============================================================

@router.post("/ai/docCompose/polish")
async def polish_content(
    body: PolishBody,
    current_user: dict = Depends(get_current_user),
):
    """让 AI 整理内容结构（编辑器里的「AI 优化」按钮）

    ⚠️ 约束模型**只动结构、不动事实**：
       排版工具改写内容会造成"文档里的数字变了"这种灾难，
       而用户往往不会逐句复核 AI 改过的稿子。
    """
    if not body.markdown.strip():
        return error("内容为空")

    try:
        from app.services.ai.dynamic_ai import get_client

        client = get_client()
        prompt = (
            "你是文档排版助手。请整理下面内容的**结构**，让它适合排成正式文档。\n"
            "\n"
            "只做这些事：\n"
            "1. 补上/修正 Markdown 标题层级（# ## ###），层级不要跳\n"
            "2. 把并列信息改成列表，把表格状数据改成 Markdown 表格\n"
            "3. 按语义分段，去掉多余空行\n"
            "4. 公式保持 LaTeX 写法（行内 $...$，独立 $$...$$）\n"
            "\n"
            "绝对不要做这些事：\n"
            "- 不要改写任何事实、数字、公式、专有名词\n"
            "- 不要增加原文没有的内容\n"
            "- 不要删减原文的信息量\n"
            "- 不要加你自己的评论或总结\n"
            "\n"
            f"用户要求：{body.instruction}\n"
            "\n"
            "直接输出整理后的 Markdown，不要任何解释、不要用代码块包裹。\n"
            "\n"
            "---\n"
            f"{body.markdown}\n"
        )

        resp = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=8000,
        )
        text = (resp or "").strip()
        # 模型有时会用 ```markdown 包裹，剥掉
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        text = text.strip()

        if not text:
            return error("AI 未返回内容，请稍后重试")

        return success({"markdown": text, "theme": body.theme})
    except Exception as e:  # noqa: BLE001
        return error(f"AI 优化失败：{type(e).__name__}: {e}")


# ============================================================
# 内部
# ============================================================

def _compose(body: RenderBody) -> Any:
    """按请求体走对应解析路径；失败返回错误字符串"""
    try:
        if body.spec:
            spec = dict(body.spec)
            # 请求体里的显式字段覆盖 spec 里的同名字段
            for k in ("title", "subtitle", "author", "theme"):
                v = getattr(body, k, "")
                if v:
                    spec[k] = v
            if body.cover:
                spec["cover"] = True
            if body.toc:
                spec["toc"] = True
            if body.header:
                spec["header"] = body.header
            if body.footer:
                spec["footer"] = body.footer
            return svc.compose_from_spec(spec, want_pdf=body.wantPdf)

        return svc.compose_from_markdown(
            body.markdown,
            title=body.title,
            theme=body.theme,
            cover=body.cover,
            toc=body.toc,
            want_pdf=body.wantPdf,
        )
    except Exception as e:  # noqa: BLE001
        return f"渲染失败：{type(e).__name__}: {e}"


def _save_outputs(result: Dict[str, Any], filename: str, *, want_pdf: bool) -> List[Dict[str, Any]]:
    """落盘并返回文件元信息列表

    ⚠️ 文件名优先级：显式 filename > 文档标题 > "文档"
       实测缺陷：请求里传了 title="接口测试"，但落盘叫「文档.docx」——
       因为这里只看 `filename`（默认值"文档"）。
       用户下载下来一堆「文档.docx」根本分不清哪个是哪个。

    ⚠️ 每个文件同时给两种路径（2026-10-27 实测踩坑）：
       · `path` —— 相对 UPLOAD_DIR（落库/再处理用）
       · `url`  —— **前端可直接 fetch 的地址**

       静态文件挂在 `/profile`（见 main.py 的 app.mount），
       而 `save_export_file` 返回的是 `export/2026/...`。
       前端如果直接拿 `path` 去 fetch('/dev-api/' + path) 会拿到 404 页面
       （实测 byteLength 只有 45 字节，就是那张错误页）。
    """
    from app.services.ai.agent.tools.bank_export import save_export_file

    # 默认值 "文档" 视为"没给"，让位给真实标题
    name_hint = (filename or "").strip()
    if not name_hint or name_hint == "文档":
        name_hint = (result["spec"].get("title") or "").strip() or "文档"

    base = _safe_name(name_hint)
    files: List[Dict[str, Any]] = []

    rel, name = save_export_file(result["docx"], f"{base}.docx")
    files.append({
        "path": rel, "url": f"/profile/{rel}", "name": name,
        "type": "docx", "size": len(result["docx"]),
    })

    if want_pdf and result.get("pdf"):
        rel2, name2 = save_export_file(result["pdf"], f"{base}.pdf")
        files.append({
            "path": rel2, "url": f"/profile/{rel2}", "name": name2,
            "type": "pdf", "size": len(result["pdf"]),
        })

    return files


def _safe_name(name: str) -> str:
    import re

    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" ._")
    return (s or "文档")[:60]
