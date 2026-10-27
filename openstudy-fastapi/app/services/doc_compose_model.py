"""
文档编排引擎：数据模型层

============================================================================
为什么要有这一层（2026-10-27）
============================================================================

用户需求：
    「实现 word pdf 图文编排 排版 插入表格 图片 美化等能力
      用户给我们一段文字 或者 一个混乱的word 图文混乱
      我们可以给他进行优化重构 等操作
      用户通过对话 上传文件 或者 口述 让我们的ai自己制作一个出来 也可以」

要把「混乱内容 → 排版精美的 Word/PDF」做成能力，必须把**内容**和**呈现**分开：

    输入（Markdown / 混乱 DOCX / 口述）
        ↓  ① 解析 + 规范化（doc_compose_parser）
    DocumentSpec（纯 JSON 中间层，无任何 docx 概念）
        ↓  ② 渲染（doc_compose_renderer）
    .docx / .pdf

中间层用纯 JSON 的理由：
  · AI 可以直接生成它（LLM 输出结构化 JSON 比直接生成 docx 稳得多）
  · 同一份内容能渲成不同样式（学术 / 简洁 / 报告），改样式不动内容
  · 可单测：不装 Word、不开文件就能校验结构
  · 能存进数据库（用户以后能"再导一次，换个模板"）

⚠️ 不复用 `bank_export_service` 的 Block 元组
   `Block = ("text", str) | ("image", src) | ("table", TableData)`
   那套是给**题库导出**用的扁平结构（只有题目/选项/解析三种语义），
   而通用文档需要标题层级、列表、引用块、封面、页眉页脚。
   强行复用会让两边都变复杂。
   但**渲染时的底层工具函数复用**（字体、表格边框、OMML 公式、图片尺寸），
   那一部分直接 import，不重写。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

# ============================================================
# 块类型
# ============================================================

BlockType = Literal[
    "heading",   # 标题（level 1~4）
    "paragraph",  # 正文段落（可含行内公式 / 加粗 / 斜体 / 链接）
    "list",      # 列表（有序 / 无序，可嵌套）
    "table",     # 表格
    "image",     # 图片
    "quote",     # 引用块
    "code",      # 代码块（等宽字体 + 灰底）
    "divider",   # 分隔线
    "math",      # 独立公式块（行间公式）
    "callout",   # 提示框（信息/警告/成功，带色块）
]


@dataclass
class Block:
    """一个内容块

    ⚠️ 用 dataclass 而不是裸 dict：渲染层能拿到明确的字段，
       错拼字段名会立刻报错，而不是静默渲染出一片空白。
    """

    type: BlockType

    #: 标题层级（type="heading" 时用），1~4
    level: int = 1

    #: 纯文本内容（paragraph / quote / code / math 用）
    text: str = ""

    #: 列表项（type="list" 时用）
    items: List[Any] = field(default_factory=list)

    #: 列表是否有序（1. 2. 3. vs • • •）
    ordered: bool = False

    #: 表格数据：{"headers": [...], "rows": [[...]], "align": [...]}
    table: Optional[Dict[str, Any]] = None

    #: 图片：{"src": 相对路径或 data URL, "caption": 图注, "widthCm": 可选}
    image: Optional[Dict[str, Any]] = None

    #: 提示框类型（type="callout" 时用）：info / warn / success
    tone: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # 去掉与本块类型无关的字段，让 JSON 干净（AI 生成时也不容易被干扰）
        if self.type != "heading":
            d.pop("level", None)
        if self.type != "list":
            d.pop("items", None)
            d.pop("ordered", None)
        if self.type != "table":
            d.pop("table", None)
        if self.type != "image":
            d.pop("image", None)
        if self.type != "callout":
            d.pop("tone", None)
        if self.type in ("table", "image"):
            d.pop("text", None)
        return d


@dataclass
class DocumentSpec:
    """一份文档的完整描述（纯 JSON，可存库、可直接由 AI 生成）"""

    #: 文档标题（渲染成封面大标题 / 页眉）
    title: str = ""

    #: 副标题（封面用，可空）
    subtitle: str = ""

    #: 作者 / 机构（封面用，可空）
    author: str = ""

    #: 日期字符串（不传则由渲染层填今天）
    date: str = ""

    #: 正文块
    blocks: List[Block] = field(default_factory=list)

    #: 样式主题：academic（学术）| clean（简洁）| report（报告）
    theme: str = "clean"

    #: 是否生成封面页
    cover: bool = False

    #: 是否生成目录页（块数 >= 6 且有多级标题时才起作用）
    toc: bool = False

    #: 页眉文字（空则用 title）
    header: str = ""

    #: 页脚文字（空则只显示页码）
    footer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "date": self.date,
            "theme": self.theme,
            "cover": self.cover,
            "toc": self.toc,
            "header": self.header,
            "footer": self.footer,
            "blocks": [b.to_dict() if isinstance(b, Block) else b for b in self.blocks],
        }

    # ------------------------------------------------------------
    # 统计（渲染层用来决定要不要出目录、要不要缩字号）
    # ------------------------------------------------------------

    def heading_levels(self) -> List[int]:
        return sorted({b.level for b in self.blocks if b.type == "heading"})


# ============================================================
# 主题定义
# ============================================================
#
# 一个主题就是一组排版参数。这样"换个样式"只改这里，不动内容解析也不动渲染逻辑。

THEMES: Dict[str, Dict[str, Any]] = {
    # 学术：宋体 / 小四 / 1.5 倍行距 / 首行缩进 2 字符（中文论文惯例）
    "academic": {
        "label": "学术论文",
        "bodyFont": "宋体",
        "headFont": "黑体",
        "bodySizePt": 12,    # 小四
        "lineSpacing": 1.5,
        "firstLineIndentEm": 2,
        "spaceAfterPt": 0,
        "headColors": ["000000", "000000", "000000", "000000"],
        "headSizesPt": [16, 14, 12, 12],   # 三号 / 四号 / 小四 / 小四
        "titleAlign": "center",
        "tableHeaderFill": "D9D9D9",
        "quoteBarColor": "999999",
    },
    # 简洁：微软雅黑 / 五号 / 1.4 倍 / 无缩进（现代文档、说明页）
    "clean": {
        "label": "简洁现代",
        "bodyFont": "微软雅黑",
        "headFont": "微软雅黑",
        "bodySizePt": 10.5,
        "lineSpacing": 1.4,
        "firstLineIndentEm": 0,
        "spaceAfterPt": 6,
        "headColors": ["1F2329", "1F2329", "374151", "374151"],
        "headSizesPt": [18, 15, 13, 12],
        "titleAlign": "left",
        "tableHeaderFill": "EFF6FF",
        "quoteBarColor": "409EFF",
    },
    # 报告：微软雅黑 / 五号 / 1.5 倍 / 段落间距大（带封面的正式文档）
    "report": {
        "label": "正式报告",
        "bodyFont": "微软雅黑",
        "headFont": "微软雅黑",
        "bodySizePt": 11,
        "lineSpacing": 1.5,
        "firstLineIndentEm": 0,
        "spaceAfterPt": 8,
        "headColors": ["0B4C8C", "1A5FA8", "2563EB", "374151"],
        "headSizesPt": [20, 16, 13.5, 12],
        "titleAlign": "center",
        "tableHeaderFill": "DBEAFE",
        "quoteBarColor": "2563EB",
    },
}

DEFAULT_THEME = "clean"


def get_theme(name: Optional[str]) -> Dict[str, Any]:
    """取主题；名字不认识时退回默认，**不抛异常**

    ⚠️ 故意容错：主题名多半来自 AI 或用户的自然语言，
       拼错一个字母就整篇渲染失败是不能接受的。
    """
    return THEMES.get((name or "").strip().lower(), THEMES[DEFAULT_THEME])
