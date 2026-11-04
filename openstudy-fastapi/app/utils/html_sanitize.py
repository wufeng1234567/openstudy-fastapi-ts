"""HTML 安全清洗（笔记正文 / 公开分享内容）。

2026-11-04：由正则清洗切换为 **nh3（Rust ammonia）白名单清洗**。

为什么换：
- 正则只能删掉「已知的坏形状」，面对畸形 HTML、编码绕过、属性拼接时容易漏；
- nh3 用 HTML5 解析器把输入解析成 DOM，再按白名单重新序列化，未知标签/属性一律丢弃，
  从根上避免 `javascript:`、`on*`、嵌套 `<script>` 这类存储型 XSS。

保留的标签覆盖笔记编辑器会产出的正常内容（标题/列表/表格/代码/链接/图片/引用等）；
`style`、`iframe`、`script`、表单控件以外的危险标签不进入白名单。

如果部署环境缺少 nh3（例如旧镜像还没装依赖），退回原正则实现，保证服务不因缺包 500。
"""

from __future__ import annotations

import re

try:  # pragma: no cover - 仅用于旧环境降级
    import nh3
except ImportError:  # pragma: no cover
    nh3 = None  # type: ignore[assignment]

#: 允许保留的标签（笔记/分享正文的常见排版标签）
_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code",
    "col", "colgroup", "dd", "del", "details", "div", "dl", "dt", "em", "figcaption",
    "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input",
    "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "s", "samp", "small",
    "span", "strike", "strong", "sub", "summary", "sup", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "u", "ul", "var", "wbr",
}

#: 标签 → 允许的属性。`rel` 由 nh3 自动补 noopener noreferrer，不在白名单里重复声明。
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    "table": {"border", "cellpadding", "cellspacing"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align", "scope"},
    "ol": {"start"},
    "input": {"type", "checked", "disabled"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class"},
}

#: 链接协议白名单：不允许 javascript/vbscript/data 等可执行协议。
_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def _sanitize_with_nh3(text: str) -> str:
    return nh3.clean(  # type: ignore[union-attr]
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )


# ---------------------------------------------------------------------------
# 降级实现：旧版正则清洗（只在没有安装 nh3 时使用）
# ---------------------------------------------------------------------------
_BLOCK_TAGS = ("script", "style", "iframe", "object", "embed", "link", "meta", "base")
_BLOCK_RE = re.compile(
    r"<\s*(?:" + "|".join(_BLOCK_TAGS) + r")\b[^>]*>.*?<\s*/\s*(?:" + "|".join(_BLOCK_TAGS) + r")\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SELF_CLOSING_BLOCK_RE = re.compile(
    r"<\s*(?:" + "|".join(_BLOCK_TAGS) + r")\b[^>]*/?\s*>",
    re.IGNORECASE,
)
_EVENT_ATTR_RE = re.compile(r"\s+on[a-zA-Z0-9_-]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_UNQUOTED_EVENT_RE = re.compile(r"\s+on[a-zA-Z0-9_-]+\s*=\s*[^\s>]+", re.IGNORECASE)
_JS_URL_RE = re.compile(
    r"((?:href|src)\s*=\s*['\"])\s*(?:javascript|vbscript|data:text/html)\s*:[^'\"]*(['\"])",
    re.IGNORECASE,
)
_SCRIPT_TEXT_RE = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)


def _sanitize_with_regex(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _SCRIPT_TEXT_RE.sub("", text)
        text = _BLOCK_RE.sub("", text)
        text = _SELF_CLOSING_BLOCK_RE.sub("", text)
    text = _EVENT_ATTR_RE.sub("", text)
    text = _UNQUOTED_EVENT_RE.sub("", text)
    text = _JS_URL_RE.sub(r"\1#\2", text)
    return text


def sanitize_note_html(value: str | None) -> str | None:
    """清洗笔记正文；None 原样返回，空串保持空串。"""
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    if nh3 is not None:
        return _sanitize_with_nh3(text)
    return _sanitize_with_regex(text)


__all__ = ["sanitize_note_html"]
