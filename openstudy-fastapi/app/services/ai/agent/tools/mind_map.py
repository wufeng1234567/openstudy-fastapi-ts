"""
`mind_map` —— 生成**真正的思维导图**（卡片 + 连线的树形图），而不是文本大纲

============================================================================
它解决什么
============================================================================

用户实测反馈：

    「没有思维导图 看不到 他生成的 根本就不是思维导图」
    「word思维导图显示效果如图（一张纯文字大纲） 都是文字形式
      我要的思维导图是真正的思维导图 带卡片连线那种的效果」

问题根因：此前用户要求"思维导图"时，模型只能走 `document_compose`
生成 Word —— 而 Word 里能放的只有文本大纲（缩进列表），
**没有任何工具能让前端渲染出真正的树形图**。

项目里其实**早就有一个完整的 `MindMap` 组件**
（`components/MindMap`，echarts tree，卡片 + 曲线连线 + 径向布局，
支持全屏、导出、节点配色），但它只被「资料结构树」页面用到了，
对话链路完全没有入口。

所以这个工具的职责很单一：**把结构化的树吐给前端**，
前端用现成组件渲染 —— 不重复实现一套绘图逻辑。

============================================================================
为什么产物是"树"而不是"文件"
============================================================================

`bank_export` / `document_compose` 产出文件（要落盘、要下载链接）。
思维导图不同：它的价值在于**可交互**（展开/收起、全屏、缩放），
生成一张 PNG 或塞进 Word 反而是退化 —— 用户要的正是"不是文字/不是图片"。

所以这里返回 `tree`（`{name, children}` 递归结构），
由前端 `AgentToolResult` 用 `MindMap` 组件渲染成卡片连线图。

⚠️ 同时**也**支持导出成 Word/PDF 大纲（`exportFormat` 参数）：
   有些场合（打印、交作业）确实需要纸质版。但那是附带能力，
   主产物永远是那棵树。

============================================================================
节点结构（与 `MindMap` 组件的契约）
============================================================================

    {"name": "根主题", "children": [
        {"name": "分支一", "children": [{"name": "子项"}, ...]},
        ...
    ]}

⚠️ 层级不要太深：实测 4 层以上在 820px 宽的对话气泡里会挤成一团。
   工具描述里明确要求模型控制在 3~4 层。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 最多接受多少个节点（含所有层级）
#:
#: 不是技术限制，是**可读性**限制：echarts 渲染 500 个节点仍然流畅，
#: 但那样一张图人根本读不了。超过这个数说明模型把"整篇文章"塞进来了，
#: 那应该用文档而不是导图。
MAX_NODES = 120

#: 最大深度（根 = 1）
MAX_DEPTH = 5


class MindMapTool(AgentTool):
    name = "mind_map"
    label = "思维导图"
    description = (
        "Build a REAL mind map (cards connected by lines, interactive tree) — NOT a text "
        "outline and NOT a Word document. "
        "Use this whenever the user asks for 思维导图 / mind map / 脑图 / 知识结构图 / "
        "'draw me a tree of ...' / 'show this as a diagram'. "
        "\n"
        "You must supply the tree yourself: a root node plus 3-8 first-level branches, "
        "each with leaf items. Keep it to 3-4 levels deep and under ~60 nodes so it stays "
        "readable. Each node name should be SHORT (ideally under 20 characters) — long "
        "sentences make the cards unreadable. "
        "\n"
        "The front end renders it as a card-and-line diagram the user can expand, "
        "zoom and full-screen. "
        "Do NOT use `document_compose` for mind maps: that produces a flat text outline "
        "inside a Word file, which is exactly what users complain about. "
        "If the user also wants a printable version, pass exportFormat='docx' or 'pdf' — "
        "but still provide the tree."
    )
    description_zh = (
        "生成**真正的思维导图**（卡片+连线的可交互树形图），不是文字大纲、不是 Word。"
        "用户说「思维导图 / 脑图 / 知识结构图 / 画个结构图」时用它。"
        "需要你提供树结构：一个根主题 + 3~8 个一级分支，每支再挂叶子节点；"
        "控制在 3~4 层、60 个节点以内，节点名要短（20 字内），否则卡片读不了。"
        "前端会渲染成可展开/缩放/全屏的导图。"
        "⚠️ 不要用 document_compose 做导图 —— 那只会得到一份纯文字大纲。"
        "需要打印版时传 exportFormat（docx/pdf），但仍要提供 tree。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Root topic shown as the centre node.",
            },
            "tree": {
                "type": "object",
                "description": (
                    "The mind map tree: {name, children:[{name, children:[...]}]}. "
                    "Root is `title` (will be filled in if you pass it there). "
                    "3-8 first-level branches recommended."
                ),
                "properties": {
                    "name": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["name"],
            },
            "layout": {
                "type": "string",
                "enum": ["tree", "radial"],
                "description": (
                    "Diagram layout. Default 'tree' (branches grow rightwards). "
                    "Tree is the only layout that keeps long labels from overlapping "
                    "because the cards are wide; only ask for 'radial' with very short labels."
                ),
            },
            "exportFormat": {
                "type": "string",
                "enum": ["none", "docx", "pdf"],
                "description": (
                    "Optionally ALSO produce a printable outline file. "
                    "Default 'none' — the interactive diagram is the deliverable."
                ),
            },
        },
        "required": ["title", "tree"],
    }

    #: 纯展示产物，不写用户数据 → 不需要二次确认
    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext):
        title = str(params.get("title") or "").strip()
        raw_tree = params.get("tree")
        layout = str(params.get("layout") or "auto").strip().lower()
        export_fmt = str(params.get("exportFormat") or "none").strip().lower()

        if not title and not raw_tree:
            return fail("请提供 title（中心主题）和 tree（节点树）")

        # ── 归一化 + 校验树 ──
        tree, err = _normalize_tree(raw_tree, title)
        if err:
            return fail(err, hint=(
                "tree 必须是 {name: '根主题', children: [{name: '分支', children: [...]}]} 形式；"
                "每个节点至少要有 name。"
            ))
        # ⚠️ 归一化可能返回 `None` 而**不报错**（节点缺 name、或整棵树都被过滤掉）：
        #    `_norm_node` 对"空名字"的处理是返回 (None, "")，因为它逐层过滤时
        #    不该因为一个坏节点就把整棵树判死。
        #    但到了这里如果还是 None，说明整棵树是空的 —— 必须挡住，
        #    否则下面 `_count_nodes(None)` 直接 AttributeError（实测崩过）。
        if not tree:
            return fail(
                "tree 里没有任何有效节点（每个节点都要有非空的 name）",
                hint="示例：{name: '中心主题', children: [{name: '分支一', children: [{name: '叶子'}]}]}",
            )

        count = _count_nodes(tree)
        depth = _depth_of(tree)
        if count > MAX_NODES:
            return fail(
                f"节点太多（{count} 个），思维导图会看不清。"
                f"请精简到 {MAX_NODES} 个以内，或者改用文档形式（document_compose）。"
            )
        if depth > MAX_DEPTH:
            return fail(
                f"层级太深（{depth} 层），导图会挤成一团。请控制在 {MAX_DEPTH} 层以内。"
            )

        # 布局默认 tree
        #
        # ⚠️ 不要默认 radial（2026-10-27 依据组件注释修正）
        #
        #    `MindMap` 组件的注释写明了实测结论：改用卡片样式后，
        #    卡片比原来的小圆点宽很多（18 字标签约 150px），
        #    径向布局把同层节点排在同心圆上，长标签会**横向伸出去压住父节点**。
        #    试过 `position:'inside'`、`width+truncate`、加大 edgeLength 都不理想。
        #
        #    所以那个组件的默认值已经从 radial 改成 tree。
        #    这里如果还按节点数自动选 radial，等于绕开那次修复、把缺陷放回来。
        if layout not in ("tree", "radial"):
            layout = "tree"

        branches = len(tree.get("children") or [])
        payload: Dict[str, Any] = {
            "title": tree.get("name") or title,
            "tree": tree,
            "layout": layout,
            "nodeCount": count,
            "branchCount": branches,
            "depth": depth,
        }

        # ── 可选：附带一份可打印大纲 ──
        if export_fmt in ("docx", "pdf"):
            try:
                payload.update(_export_outline(tree, want_pdf=(export_fmt == "pdf")))
            except Exception as e:  # noqa: BLE001
                # 导出失败不该让整个导图失败 —— 主产物是那棵树
                payload["exportError"] = f"打印版生成失败：{type(e).__name__}: {e}"

        return ok(
            message=(
                f"已生成「{payload['title']}」思维导图："
                f"{branches} 个分支、{count} 个节点、{depth} 层"
                + ("（附打印版）" if payload.get("downloadUrl") else "")
            ),
            data=payload,
        )


# ============================================================================
# 树处理
# ============================================================================

def _normalize_tree(raw: Any, title: str) -> tuple[Optional[Dict[str, Any]], str]:
    """把模型给的各种形状归一成 `{name, children}`

    ⚠️ 模型可能给的形状（实测都要容忍）：
        · 标准 dict：{"name": "A", "children": [...]}
        · children 里混进**字符串**：{"name": "A", "children": ["a", "b"]}
        · 顶层直接给数组：[{...}, {...}]（忘了包根节点）
        · JSON 字符串（模型把 tree 序列化了）
    """
    node: Any = raw

    # 字符串 → 尝试按 JSON 解
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except json.JSONDecodeError:
            return None, "tree 不是合法的 JSON 结构"

    # 数组 → 包一层根节点
    if isinstance(node, list):
        node = {"name": title or "中心主题", "children": node}

    if not isinstance(node, dict):
        return None, "tree 必须是对象（含 name / children）"

    return _norm_node(node, title, depth=1)


def _norm_node(node: Any, title: str, *, depth: int) -> tuple[Optional[Dict[str, Any]], str]:
    """递归归一；超深直接截断（不报错，让用户至少看到前几层）"""
    if depth > MAX_DEPTH + 1:
        return None, ""

    # 叶子用字符串表示是常见写法
    if isinstance(node, str):
        text = node.strip()
        return ({"name": text} if text else None), ""

    if not isinstance(node, dict):
        return None, ""

    name = str(node.get("name") or node.get("title") or node.get("label") or "").strip()
    if not name:
        return None, ""

    out: Dict[str, Any] = {"name": name[:80]}

    kids_in = node.get("children") or node.get("nodes") or node.get("items") or []
    if isinstance(kids_in, str):
        kids_in = [kids_in]
    if isinstance(kids_in, list):
        kids: List[Dict[str, Any]] = []
        for k in kids_in:
            child, _ = _norm_node(k, title, depth=depth + 1)
            if child:
                kids.append(child)
        if kids:
            out["children"] = kids

    return out, ""


def _count_nodes(node: Dict[str, Any]) -> int:
    total = 1
    for c in node.get("children") or []:
        total += _count_nodes(c)
    return total


def _depth_of(node: Dict[str, Any]) -> int:
    kids = node.get("children") or []
    if not kids:
        return 1
    return 1 + max(_depth_of(c) for c in kids)


def _export_outline(tree: Dict[str, Any], *, want_pdf: bool) -> Dict[str, Any]:
    """把树转成可打印的大纲文档（Word / PDF）

    复用 `doc_compose_service` 的管线（markdown → 排版 → 落盘），
    这样打印版的样式与其他文档一致，不用另写一套渲染。

    ⚠️ 这是**附带**能力：用户要的是导图本身，打印版只是"顺便给一份"。
       所以这里任何失败都在调用处被吞成 `exportError`，不影响树。
    """
    lines: List[str] = []

    def walk(node: Dict[str, Any], level: int) -> None:
        name = node.get("name") or ""
        if level == 0:
            lines.append(f"# {name}")
            lines.append("")
        else:
            # 一级分支用二级标题，更深的用缩进列表 —— 比全用列表层次更清楚
            if level <= 2:
                lines.append("")
                lines.append(f"{'#' * (level + 1)} {name}")
                lines.append("")
            else:
                lines.append(f"{'  ' * (level - 3)}- {name}")
        for c in node.get("children") or []:
            walk(c, level + 1)

    walk(tree, 0)
    markdown = "\n".join(lines)

    from app.services.ai.agent.tools.bank_export import save_export_file
    from app.services.doc_compose_service import compose_from_markdown

    result = compose_from_markdown(
        markdown,
        title=str(tree.get("name") or "思维导图"),
        theme="clean",
        want_pdf=want_pdf,
    )

    # ⚠️ `compose_from_markdown` 返回的是**字节**（docx / pdf），不是下载链接 ——
    #    落盘与链接由工具层负责（与 `bank_export` / `document_compose` 同一套）。
    #    PDF 转换失败时 `pdf` 为 None 且 `pdfError` 有值，此时退回 docx 以免整个失败。
    pdf_error = result.get("pdfError")
    if want_pdf and result.get("pdf"):
        blob = result["pdf"]
        ext = "pdf"
    else:
        blob = result.get("docx") or b""
        ext = "docx"

    if not blob:
        raise RuntimeError("文档引擎没有产出任何字节")

    safe_title = str(tree.get("name") or "思维导图").replace("/", "_").replace("\\", "_")[:60]
    rel, shown = save_export_file(blob, f"{safe_title}.{ext}")
    return {
        "downloadUrl": f"/profile/{rel}",
        "fileName": shown,
        "format": ext,
        "fileSizeText": _human_size(len(blob)),
        "exportNote": pdf_error if (want_pdf and pdf_error) else "",
    }


def _human_size(n: int) -> str:
    size = float(n or 0)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"
