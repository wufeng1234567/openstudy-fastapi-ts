"""
题库导出服务 —— 把题库（含题目 / 选项 / 答案 / 解析）导出为 Word(.docx) 或 PDF

设计要点
========
1. **图片必须"在原位"**
   题干与解析都是 HTML（`<p>…</p><p><img src="/dev-api/profile/upload/…"></p>…`），
   图片和文字是交替出现的。如果先把 HTML 抽成纯文本、再单独把所有图片追加到末尾，
   图文顺序就丢了 —— 而"这张图对应哪道题/哪段解析"恰恰是最要紧的信息。
   所以这里不抽纯文本，而是**按块解析 HTML**，逐块转成对应的 docx / PDF 元素。

2. **图片 src 的三种形态都要能落到磁盘**
   · `/dev-api/profile/upload/…`（本地开发，带 vite 代理前缀）
   · `/profile/upload/…`（生产）
   · `http(s)://…/profile/upload/…`（绝对地址）
   统一清洗成 `UPLOAD_DIR` 下的相对路径再读盘。
   读不到就画一个占位框（并保留原 src 便于排查），**不能整篇失败**。

3. 答案格式在库里并不统一（实测 type1 既有 `'0'` 也有 `'C'`，
   type2 既有 `'A,C,E'` 也有 `'0,1,2'`），导出前统一归一化成字母。

4. 中文字体：PDF 必须显式注册 CJK 字体，否则中文全是黑方块。
   优先用系统里的思源/雅黑/宋体，找不到则退回 reportlab 内置的 STSong-Light。
"""

from __future__ import annotations

import html as _html
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.config import settings

#: PDF 里表示"上划线"的字符
#:
#: 用 U+203E(‾) 而不是组合符 U+0305：后者在微软雅黑 / 文泉驿里**没有字形**
#: （fontTools 实测 cmap 查不到），reportlab 会画成空方块。
_OVERLINE_CHAR = "\u203e"

# ──────────────────────────────────────────────────────────── 文本清洗

#: 常见 LaTeX 命令名（用于识别「控制字符 + 命令名剩余部分」的残骸）
#:
#: 用**白名单**而不是"控制字符 + 任意小写字母"的启发式：
#: 后者会把 `col1<TAB>col2` 这种正常排版误改成 `col1\tcol2`。
#: 宁可漏还原（顶多排版不完美），也不能把正常文字改坏 —— 后者是内容错误。
_LATEX_COMMANDS = frozenset({
    "times", "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "iint",
    "theta", "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
    "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "phi", "chi",
    "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Pi", "Sigma",
    "Phi", "Psi", "Omega",
    "leq", "geq", "neq", "approx", "equiv", "sim", "propto", "infty",
    "cdot", "cdots", "ldots", "dots", "pm", "mp", "div", "ast",
    "cup", "cap", "subset", "supset", "subseteq", "in", "notin", "forall",
    "exists", "emptyset", "nabla", "partial",
    "rightarrow", "leftarrow", "Rightarrow", "Leftarrow", "leftrightarrow",
    "to", "mapsto", "implies",
    "text", "mathrm", "mathbf", "mathit", "mathbb", "mathcal", "operatorname",
    "overline", "underline", "bar", "hat", "vec", "tilde", "dot",
    "begin", "end", "left", "right", "quad", "qquad",
    "binom", "choose", "log", "ln", "exp", "lim", "max", "min", "sup", "inf",
    "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
})

#: 控制字符 → 它顶替掉的首字母
#:
#: 实测（题库 172）：
#:   · `\times` 被存成了 `<TAB>imes`  —— `\t` 整体被当成制表符落库
#:   · `\frac`  被存成了 `<FF>rac`    —— `\f` 整体被当成换页符落库
#:
#: 关键理解：控制字符**占据了反斜杠和首字母两个位置**，不是插在它们之间。
#: 实测字节：`\times` → `0x09 'i' 'm' 'e' 's'`。
#: 所以还原 = 把控制字符换成「反斜杠 + 它原本代表的字母」，后面那截原样接上。
_ESCAPE_LETTER = {"\t": "t", "\f": "f", "\v": "v"}

#: 每种控制字符允许接的「命令名剩余部分」
_ESCAPES_BY_LETTER = {
    letter: frozenset(c for c in _LATEX_COMMANDS if c.startswith(letter) and len(c) > 2)
    for letter in ("t", "f", "v")
}

_BACKSLASH = chr(92)


def _build_pseudo_escape_re():
    """
    构造「控制字符 + 命令名剩余部分」的正则

    `\\times` 坏成 `<TAB>imes` 后，TAB 后面是 `imes`（不是 `times`）。
    因此每个控制字符只允许接**以它对应字母开头**的那些命令的**剩余部分**：
        TAB(\\t) → imes / heta / ext / o      （来自 \\times / \\theta / \\text / \\to）
        FF (\\f) → rac / orall                 （来自 \\frac / \\forall）
        VT (\\v) → ec / arphi                  （来自 \\vec  / \\varphi）
    这样 TAB 后面跟 `rac` 就不会被误判成 `\\trac`。
    """
    alts = []
    for letter, cmds in _ESCAPES_BY_LETTER.items():
        ctrl = next(k for k, v in _ESCAPE_LETTER.items() if v == letter)
        tails = sorted({c[1:] for c in cmds}, key=len, reverse=True)
        if tails:
            alts.append(re.escape(ctrl) + r"(?=(?:" + "|".join(tails) + r")(?![A-Za-z]))")
    return re.compile("(" + "|".join(alts) + ")")


_RE_PSEUDO_ESCAPE = _build_pseudo_escape_re()

def _repair_pseudo_escapes(s: str) -> str:
    """
    把被"吃掉"的 LaTeX 反斜杠还原：`<TAB>imes` → `\\\\times`、`<FF>rac` → `\\\\frac`

    只认白名单里的命令名，避免误伤正文里正常的制表符（见 `_LATEX_COMMANDS` 的说明）。

    ⚠️ 替换值必须由函数返回**字面量**。若直接写 `sub(pat, "\\\\t", s)`，
       `re` 会把替换串里的 `\\\\t` 再解释一遍成制表符 —— 等于什么都没换。
       用 lambda 就不经过那次解释，稳定得到「反斜杠 + t」。
    """
    if "\t" not in s and "\f" not in s and "\v" not in s:
        return s
    return _RE_PSEUDO_ESCAPE.sub(lambda m: _BACKSLASH + _ESCAPE_LETTER[m.group(1)], s)


#: XML 1.0 不接受的控制字符（与 `utils/excel_util.ILLEGAL_CHARACTERS_RE` 同源）
#:
#: ⚠️ 存量数据里确实有：题库 172 的解析就带 0x0C/0x09，
#:    直接塞进 python-docx 会抛
#:    `ValueError: All strings must be XML compatible: … no NULL bytes or control characters`
#:    并让整个导出 500。Excel 导出早就踩过一次（见 excel_util 的注释），这里同样要在入口洗掉。
#:    注意：**先** `_repair_pseudo_escapes` 再剔除，顺序不能反，否则反斜杠就没得还原了。
_RE_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(value: Any) -> str:
    """转成可安全写入 XML/PDF 的字符串（含伪转义修复）"""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    s = _repair_pseudo_escapes(s)
    # 还原完成后，剩下的控制字符才是真正的脏字符：制表符压成空格，其余剔除
    s = s.replace("\t", " ")
    return _RE_ILLEGAL_XML.sub("", s)



# ──────────────────────────────────────────────────────────── LaTeX 符号表（PDF/文本降级共用）

#: LaTeX 命令 → Unicode 数学符号
#:
#: PDF 没有 OMML 这种原生公式格式，reportlab 也不支持 TeX 排版。
#: 可行的做法只有两种：① 把公式画成图片；② 用 Unicode 数学字符 + 上下标近似。
#: 这里选 ②，理由：
#:   · 图片公式在 PDF 里不可选、不可搜索，且缩放后发虚；
#:   · 题库实际用到的命令很集中（`\overline` `\dfrac` `\frac` `\sqrt` + 希腊字母），
#:     Unicode 能表达得很好；
#:   · 生成的 PDF 文字仍可复制/检索。
#: 实测 CJK 字体（微软雅黑 / 文泉驿）覆盖了下面所有符号的码位。
_PDF_MATH_SYMBOLS = {
    # 希腊字母
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # 运算符 / 关系
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "·",
    "cdots": "⋯", "ldots": "…", "dots": "…",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝",
    "infty": "∞", "partial": "∂", "nabla": "∇",
    "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮",
    # 集合 / 逻辑
    "cup": "∪", "cap": "∩", "subset": "⊂", "supset": "⊃",
    "subseteq": "⊆", "supseteq": "⊇", "in": "∈", "notin": "∉",
    "emptyset": "∅", "forall": "∀", "exists": "∃",
    "land": "∧", "lor": "∨", "neg": "¬",
    # 箭头
    "to": "→", "rightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔",
    "mapsto": "↦",
    # 其它
    "angle": "∠", "perp": "⊥", "parallel": "∥", "degree": "°",
    "prime": "′", "ast": "∗", "star": "⋆", "bullet": "•",
}


# ──────────────────────────────────────────────────────────── 图片定位

#: `<img …>`（容忍自闭合与任意属性顺序）
_RE_IMG = re.compile(r"<img\b[^>]*>", re.I)
_RE_ATTR_SRC = re.compile(r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)

#: 把 src 前面的部署前缀剥掉，只留 `profile/...` 这种相对段
_RE_STRIP_PREFIX = re.compile(
    r"^(?:https?://[^/]+)?(?:/dev-api)?/", re.I
)


def _src_to_relpath(src: str) -> Optional[str]:
    """`<img src>` → 相对 `UPLOAD_DIR` 的路径（用 / 分隔）；无法识别返回 None"""
    if not src:
        return None
    s = _html.unescape(src.strip())
    # data: URI 不落盘，交给调用方按"内联图片"处理
    if s.startswith("data:"):
        return None
    s = _RE_STRIP_PREFIX.sub("", s)
    # 去掉查询串 / 锚点
    s = re.split(r"[?#]", s, 1)[0]
    s = s.lstrip("/")
    if not s.startswith("profile/"):
        return None
    return s[len("profile/"):]


def _load_image_bytes(src: str) -> Optional[bytes]:
    """按 src 读图片字节；找不到返回 None"""
    # data:image/...;base64,xxx
    if src.startswith("data:"):
        try:
            _, b64 = src.split(",", 1)
            import base64

            return base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return None

    rel = _src_to_relpath(src)
    if not rel:
        return None
    # 关键：防止 `../` 穿越到 UPLOAD_DIR 之外
    base = os.path.abspath(settings.UPLOAD_DIR)
    full = os.path.abspath(os.path.join(base, rel.replace("/", os.sep)))
    if not full.startswith(base + os.sep) and full != base:
        logger.warning("[export] 拒绝越界图片路径 {!r}", src)
        return None
    if not os.path.isfile(full):
        logger.warning("[export] 图片不存在 {!r} -> {}", src, full)
        return None
    try:
        with open(full, "rb") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("[export] 读取图片失败 {!r}: {}", full, exc)
        return None


# ──────────────────────────────────────────────────────────── HTML → 块

#: 行内标记 → 纯文本（图片单独抽出）
_RE_BR = re.compile(r"<br\s*/?>", re.I)
_RE_BLOCK_END = re.compile(r"</(?:p|div|li|h[1-6]|tr)\s*>", re.I)
_RE_TAG = re.compile(r"<[^>]+>")


def _inline_text(fragment: str) -> str:
    """把一段 HTML 转成纯文本（保留换行语义，不含图片）"""
    s = _RE_BR.sub("\n", fragment)
    s = _RE_BLOCK_END.sub("\n", s)
    s = _RE_TAG.sub("", s)
    s = _html.unescape(s)
    s = _clean_text(s)
    # 归一空白：行内多空格压成一个，但保留换行
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(lines).strip()


#: 一个"块" = 一段文字 / 一张图 / 一个表格，按 HTML 里出现的先后顺序排列
#:
#: ```python
#: ("text",  str)
#: ("image", src)
#: ("table", TableData)      # 2026-10-26 v3 新增
#: ```
#:
#: `TableData` 是 `{"headers": [str], "rows": [[str]], "align": [str]}`，
#: 单元格里允许出现**裸 LaTeX**（渲染时再由 `_add_segments` / 公式层处理）。
Block = Tuple[str, Any]  # ("text", str) | ("image", src) | ("table", TableData)

#: 表格的数据结构
#:
#: · `headers` 为空列表表示这张表**没有表头**（纯数据表），此时不画表头底纹
#: · `rows` 每行的列数必须与 `headers`（或第一行）一致 —— 由 `_normalize_table` 保证
TableData = Dict[str, Any]


#: 单个 `<table ...>`（不嵌套；嵌套表格由 `_parse_html_table` 内部拍平）
_RE_HTML_TABLE = re.compile(r"<table\b[^>]*>(.*?)</table\s*>", re.I | re.S)
_RE_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.I | re.S)
_RE_TH = re.compile(r"<t[hd]\b([^>]*)>(.*?)</t[hd]\s*>", re.I | re.S)
_RE_COLSPAN = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.I)
_RE_ROWSPAN = re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.I)

#: Markdown 表格的可选对齐行：`| --- | :--: | --: |`
_RE_MD_ALIGN_CELL = re.compile(r"^:?-{1,}:?$")


def _clean_cell(raw: str) -> str:
    """把单元格 HTML/文本清成单行可用文本（保留行内公式与换行折叠）"""
    s = _RE_BR.sub(" ", raw or "")
    s = _RE_TAG.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\r", " ").replace("\n", " ")
    return " ".join(s.split())


def _normalize_table(headers: List[str], rows: List[List[str]], align: Optional[List[str]] = None) -> TableData:
    """
    把表格规整成固定列宽结构

    Markdown 来源经常出现「某一行列数少一个」的情况（手写的表尤其常见），
    docx / reportlab 的表格都要求**每行列数一致**，否则会崩或错列。
    这里统一补齐 + 裁剪，保证下游不用再判。
    """
    ncol = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
    if ncol == 0:
        return {"headers": [], "rows": [], "align": []}
    h = list(headers) + [""] * (ncol - len(headers))
    rr = [list(r) + [""] * (ncol - len(r)) for r in rows]
    al = list(align or []) + [""] * (ncol - len(align or []))
    return {"headers": h, "rows": rr, "align": al[:ncol]}


def _parse_html_table(inner: str) -> Optional[TableData]:
    """
    解析 `<table>` 内部 → TableData

    支持：
      · `<th>` 表头行（全 `<th>` 且是第一行 → 当表头）
      · `colspan` 横向合并（用空串占位，视觉上等价）
      · `rowspan` 纵向合并（同样占位；真正的纵向合并 OMML 写起来风险高，
        这里选择"内容不会丢"，而不是"格子一定合并" —— 后者会让单元格错位）
      · 嵌套表格拍平成文本（外层列数不变）
    """
    rows_raw = _RE_TR.findall(inner)
    if not rows_raw:
        return None

    headers: List[str] = []
    rows: List[List[str]] = []
    first = True

    for tr_inner in rows_raw:
        cells = _RE_TH.findall(tr_inner)
        if not cells:
            continue
        texts: List[str] = []
        for attrs, cell_inner in cells:
            span_m = _RE_COLSPAN.search(attrs or "")
            span = int(span_m.group(1)) if span_m else 1
            span = max(1, min(span, 20))
            texts.append(_clean_cell(cell_inner))
            # colspan：额外补空单元格，保证列数对齐（不合并，但内容不丢、不错列）
            for _ in range(span - 1):
                texts.append("")
        # 第一行且全是 `<th>` → 表头
        if first and _row_is_header(tr_inner):
            headers = texts
            first = False
            continue
        rows.append(texts)
        first = False

    if not headers and not rows:
        return None
    return _normalize_table(headers, rows)


def _row_is_header(tr_inner: str) -> bool:
    """这一行是不是表头：所有单元格都是 `<th>`"""
    ths = re.findall(r"<th\b", tr_inner, re.I)
    tds = re.findall(r"<td\b", tr_inner, re.I)
    return bool(ths) and not tds


def _parse_md_table(lines: List[str]) -> Optional[TableData]:
    """
    解析 Markdown 表格 → TableData

    形如：
        | X\\Y | 0 | 1 |
        | --- | --- | --- |
        | 0   | 0.1 | 0.3 |

    对齐行（`---` / `:---:` / `---:`）同时决定列对齐：
        `:--:` → center，`--:` → right，其余 → left
    """
    if len(lines) < 2:
        return None

    def _cells(line: str) -> List[str]:
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        # 单元格内的 `\|` 是转义的竖线，不能被切开
        parts = re.split(r"(?<!\\)\|", s)
        return [p.replace("\\|", "|").strip() for p in parts]

    header = _cells(lines[0])
    sep = _cells(lines[1])

    # 第二行的每一格都必须是 `---` 形态，才认作 Markdown 表格
    if not sep or not all(_RE_MD_ALIGN_CELL.match(c.replace(" ", "")) for c in sep if c):
        return None
    if not all(_RE_MD_ALIGN_CELL.match(c.replace(" ", "")) for c in sep):
        return None

    align: List[str] = []
    for c in sep:
        c = c.replace(" ", "")
        if c.startswith(":") and c.endswith(":"):
            align.append("center")
        elif c.endswith(":"):
            align.append("right")
        elif c.startswith(":"):
            align.append("left")
        else:
            align.append("")

    rows = [_cells(ln) for ln in lines[2:] if ln.strip()]
    return _normalize_table(header, rows, align)


#: 连续的 `|...|` 行看起来像 Markdown 表格
_RE_MD_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def _extract_md_tables_from_text(text: str) -> List[Tuple[str, Any]]:
    """
    从**纯文本块**里把 Markdown 表格抠出来，返回 [("text",..)/("table",..)]

    为什么需要：Word 表格在 `file_parser` 里被转成 Markdown 存进了题干
    （`file_parser.py:717` `builder.add_text()`），所以到了导出层，
    题干里是一段**含 `| --- |` 的普通文本**。实测（题库 432 第 33 题）
    这些竖线原样印在 PDF 上。
    """
    if "|" not in text or "\n" not in text:
        return [("text", text)] if text else []

    lines = text.split("\n")
    out: List[Tuple[str, Any]] = []
    buf: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _RE_MD_TABLE_LINE.match(line) and i + 1 < len(lines) and _RE_MD_TABLE_LINE.match(lines[i + 1]):
            # 收集连续的表格行
            j = i
            block: List[str] = []
            while j < len(lines) and _RE_MD_TABLE_LINE.match(lines[j]):
                block.append(lines[j])
                j += 1
            table = _parse_md_table(block)
            if table:
                if buf:
                    t = "\n".join(buf).strip()
                    if t:
                        out.append(("text", t))
                    buf = []
                out.append(("table", table))
                i = j
                continue
        buf.append(line)
        i += 1
    if buf:
        t = "\n".join(buf).strip()
        if t:
            out.append(("text", t))
    return out


def split_blocks(raw: Optional[str]) -> List[Block]:
    """
    把题干/解析这类 HTML 拆成有序块，**保持图文原始顺序**

    做法：把 `<img>` / `<table>` 与其余文本交替切开，每段文本再按块级结束符切行。
    这样 `<p>文字</p><p><img></p><p>文字</p>` →
        [("text","文字"), ("image",src), ("text","文字")]
    而不是"所有文字 + 所有图片"。

    ── 2026-10-26 v3：新增 `("table", TableData)` 块 ──
    在此之前，表格会被 `_RE_TAG` 无差别剥成纯文本：
      · HTML `<table>` → `X\\Y01` / `00.10.3`（单元格全粘连，实测如此）
      · Markdown `| --- |` → 竖线原样印在 Word/PDF 上
    现在两种来源都转成真表格块，由 `_docx_add_seq` / PDF 侧渲染成原生表格。
    """
    if not raw:
        return []
    if not isinstance(raw, str):
        raw = str(raw)

    # 纯文本（没有标签）也要过一遍 Markdown 表格提取
    if "<" not in raw:
        t = _inline_text(raw)
        if not t:
            return []
        return _extract_md_tables_from_text(t)

    # 把 <img> 与 <table> 都当作「分隔符」，取二者位置最近的先切
    marks: List[Tuple[int, int, str, Any]] = []
    for m in _RE_IMG.finditer(raw):
        marks.append((m.start(), m.end(), "image", m.group(0)))
    for m in _RE_HTML_TABLE.finditer(raw):
        marks.append((m.start(), m.end(), "table", m.group(1)))
    marks.sort(key=lambda x: x[0])

    blocks: List[Block] = []
    pos = 0
    for start, end, kind, payload in marks:
        if start < pos:
            continue  # 嵌套（table 内部有 img）时跳过内层，交给 table 解析
        blocks.extend(_text_blocks_with_tables(raw[pos:start]))
        if kind == "image":
            src_m = _RE_ATTR_SRC.search(payload)
            src = (src_m.group(1) or src_m.group(2)) if src_m else ""
            if src:
                blocks.append(("image", _html.unescape(src.strip())))
        else:
            table = _parse_html_table(payload)
            if table:
                blocks.append(("table", table))
            # 解析不出结构时退化成文本，至少内容不丢
            elif payload.strip():
                blocks.extend(_text_blocks_with_tables(payload))
        pos = end
    blocks.extend(_text_blocks_with_tables(raw[pos:]))
    return blocks


# ──────────────────────────────────────────────────────────── 文本 → 文字/公式片段

#: LaTeX 命令起始
_RE_LATEX_CMD = re.compile(r"\\([a-zA-Z]+)")

#: 一段文字里可能混杂「普通文本 + 裸 LaTeX」；导出时要逐段处理，
#: 文字用正常字体、公式用 OMML/矢量绘制
Segment = Tuple[str, str]  # ("text", str) | ("math", latex)


def _find_bare_latex(text: str) -> List[Tuple[int, int, str]]:
    """
    定位文本里的**裸 LaTeX 命令**（无 `$` 包裹），返回 [(start, end, latex)]

    与前端 `utils/latex.ts` 的 `findBareLatexCommands` 保持同一套判定：
    只认「命令 + 至少一个 `{}` 组」，支持嵌套花括号（`\\frac{a}{k(k+1)}`）
    和连续多组（`\\dfrac{1}{2}`）。裸的 `\\n`/`\\t` 之类不碰。

    ⚠️ 另有「无参数符号」这一类：`\\times`、`\\cup`、`\\leq`、`\\lambda`…
       它们不跟花括号，但同样是公式，也要替换成数学符号（用户 2026-10-19 反馈
       PDF 里出现 `0.2 \\times 0.04` 原文就是漏了这类）。判定用 `_PDF_MATH_SYMBOLS`
       白名单，避免把正文里偶然的反斜杠当公式。

    跳过 `$...$` 内部的命令 —— 那些由调用方按行内公式统一处理。
    """
    # ⚠️ 不能只判断反斜杠：`C_7^3` / `X^{2}` / `∫_{0}^{10}` 一个反斜杠都没有，
    #    但它们是公式。裸记号交给 `_find_bare_scripts` 收。
    if not text or ("\\" not in text and not _RE_BARE_MARKER.search(text)):
        return []
    found: List[Tuple[int, int, str]] = []
    for m in _RE_LATEX_CMD.finditer(text):
        start = m.start()
        # 前面紧邻 `$` → 已在 $...$ 里
        back = start - 1
        while back >= 0 and text[back] == " ":
            back -= 1
        if back >= 0 and text[back] == "$":
            continue

        pos = m.end()
        while pos < len(text) and text[pos] == " ":
            pos += 1
        groups = 0
        scan = pos
        while scan < len(text) and text[scan] == "{":
            depth = 0
            end = -1
            for i in range(scan, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                groups += 1
                scan = end
                while scan < len(text) and text[scan] == " ":
                    scan += 1
            else:
                break
        if groups > 0:
            found.append((start, scan, text[start:scan]))
        elif m.group(1) in _PDF_MATH_SYMBOLS:
            # 无参数符号命令（\times \cup \leq …）：整条命令本身就是一个公式片段。
            # 不加这一步，`0.2 \times 0.04` 里的 `\times` 会原样留在正文里。
            found.append((start, m.end(), text[start:m.end()]))

    # ── 2026-10-26 新增：裸上标/下标与 Unicode 数学符号 ──
    #
    # 只认反斜杠命令是不够的。实测漏掉的情况（全部原样印在纸上）：
    #   `e^{-x}`      → 上标紧跟普通字符，没有反斜杠
    #   `X^{2}`       → 同上
    #   `C_7^3=35`    → 下标 + 上标组合
    #   `∫_{0}^{10}`  → Unicode 积分号 + 上下限
    #   `∑_{i=1}^{n}` → Unicode 求和号
    #
    # latex2mathml **本身完全支持这些写法**（实测 `e^{-x}` / `C_7^3` / `∫_{0}^{10}`
    # 都能转出正确的 MathML），所以这里只要把它们「圈出来」即可。
    #
    # ⚠️ 优先级（2026-10-26 修）：**裸上标必须压过它内部的反斜杠命令**。
    #    典型失败案例 `e^{-\lambda}`：
    #      · 反斜杠逻辑先把 `\lambda` 圈走（位置 3..10）
    #      · 上标逻辑再找 `e^{-\lambda}` 时被"已被占用"挡掉
    #      · 结果正文印成 `e^{-}`，公式只剩一个孤零零的 λ
    #    实测就是这么坏掉的。所以先跑上标，再把「被上标完整包含」的
    #    反斜杠片段剔掉。
    script_hits = _find_bare_scripts(text, [])
    if script_hits:
        found = [
            (s, e, lx)
            for (s, e, lx) in found
            if not any(ss <= s and e <= se for ss, se, _ in script_hits)
        ]
        found.extend(script_hits)
    found.sort(key=lambda x: x[0])
    # 去重叠：后面的片段若被前面的完整覆盖则丢弃
    merged: List[Tuple[int, int, str]] = []
    for s, e, lx in found:
        if merged and s < merged[-1][1]:
            continue
        merged.append((s, e, lx))
    return merged


#: Unicode 数学「大运算符」—— 这些字符后面紧跟 `_{...}` / `^{...}` 就是公式
_UNICODE_BIG_OPS = "∫∬∭∮∑∏∐⋃⋂√"

#: 可能出现在「底数」位置的单个数学符号（含拉丁/希腊字母与数字）
#:
#: · 单个字母：`e^{-x}`、`X^{2}`、`C_7^3`
#: · Unicode 大运算符：`∫_{0}^{10}`、`∑_{i=1}^{n}`
#: · 单个数字：`2^k`、`3^{n+1}`（概率题里极常见，如 `C/2^k`）
_RE_SCRIPT_BASE = re.compile(
    r"(?:" + "[" + re.escape(_UNICODE_BIG_OPS) + r"]"
    r"|[A-Za-zΑ-Ωα-ω](?![A-Za-z])"
    r"|[0-9](?![0-9]))"
    r"(?:[_^](?:\{[^{}]{0,40}\}|[A-Za-z0-9]))+"
)


def _find_bare_scripts(
    text: str, already: List[Tuple[int, int, str]]
) -> List[Tuple[int, int, str]]:
    """
    找出「裸上标/下标」形态的公式片段，返回 [(start, end, latex)]

    识别两类：

    ① **Unicode 大运算符 + 上下限**：`∫_{0}^{10}`、`∑_{i=1}^{n}`
       这类必须整段吃掉，否则 `_` `^` 会作为普通字符印出来。

    ② **单字符底数 + 上下标**：`e^{-x}`、`X^{2}`、`C_7^3`、`a_{n+1}`
       底数限定为**单个字母或单个 Unicode 大运算符**，理由是：
       · `abc_1` 这种多字母底数在正文里更可能是变量名而不是排版公式
       · 单字符是数学排版的常见形式，误判代价低（顶多变一个 OMML 小公式）

    ⚠️ 已经被 `already` 覆盖的区间要跳过，否则会和反斜杠命令的匹配打架。
    """
    if not text:
        return []

    occupied = [(s, e) for s, e, _ in already]

    def _is_free(s: int, e: int) -> bool:
        return not any(s < oe and e > os_ for os_, oe in occupied)

    out: List[Tuple[int, int, str]] = []
    for m in _RE_SCRIPT_BASE.finditer(text):
        s, e = m.start(), m.end()
        if not _is_free(s, e):
            continue
        # 前面若紧贴**ASCII 字母/数字/下划线**，说明是更长单词的一部分
        # （如 `value_1`、`abc^2`），不当作公式。
        #
        # ⚠️ 2026-10-26 修复：这里原本用 `str.isalnum()`，而**汉字也满足 isalnum()**，
        #    于是 `由∫_{-∞}^{+∞}f(x)dx=1` 被误挡 —— `∫` 前面是汉字「由」，
        #    整条积分式原样印在 PDF 上（实测题库 432）。
        #    正文里中文紧邻公式是常态，绝不能用 isalnum() 判断。
        if s > 0:
            prev = text[s - 1]
            if (prev.isascii() and prev.isalnum()) or prev in "_^":
                continue
        out.append((s, e, text[s:e]))
    return out


def split_text_and_math(text: str) -> List[Segment]:
    """
    把一段纯文本拆成 [("text", ...), ("math", ...), ...]，**保持原始顺序**

    这样 Word 里能用原生 OMML、PDF 里能画成矢量符号，
    而不是把 `\\overline{A}` 原样印成反斜杠（用户 2026-10-19 反馈的问题）。

    ── 2026-10-26 重写（v3）────────────────────────────────────────────
    原实现有两个硬伤，都是用户实测拍到的：

    ① **`$...$` / `$$...$$` 完全没被识别**
       `_find_bare_latex` 的 docstring 写着「跳过 `$...$` 内部的命令 ——
       那些由调用方按行内公式统一处理」，但**那个调用方从来不存在**。
       实测：题库 408（10 道题含 `$` 公式）导出后 document.xml 残留 126 个 `$`，
       PDF 里原样印出 `$\int_01 x2 dx$`。

    ② **裸上标/下标识别不出来**
       原逻辑只认「反斜杠命令 + 至少一个 `{}`」，于是
       `e^{-x}`、`X^{2}`、`C_7^3`、`∫_{0}^{10}` 全部漏掉，原样印在纸上。
       实测：20 页 PDF 里 23 行 LaTeX 泄漏。

    现在按「显式定界符优先，其次裸记号」两段处理：
      · 先吃 `$$...$$`（块级）与 `$...$`（行内）—— 定界符内的内容整体当公式，不再二次切分
      · 再对剩下的纯文本跑 `_find_bare_latex`（已扩展，见该函数）
    """
    if not text:
        return []

    # ── 第一遍：显式定界符 ──
    out: List[Segment] = []
    for kind, payload in _split_delimited_math(text):
        if kind == "text":
            # ── 第二遍：文本段里再找裸 LaTeX ──
            out.extend(_split_bare_math(payload))
        else:
            out.append((kind, payload))
    return out or [("text", text)]


#: `$$...$$`（块级）与 `$...$`（行内）
#:
#: ⚠️ 行内那一条必须排除「货币」误判：`$5` / `$ 5` 后面紧跟数字且没有配对的 `$` 时不算公式。
#:    判定方式是要求闭合 `$` 之前至少有一个非空白、非数字起始的字符，
#:    并且整段长度合理（<= 400）—— 太长的不是公式，是正文里恰好出现的 `$`。
_RE_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)
_RE_INLINE_MATH = re.compile(r"(?<![\\$])\$(?!\s)([^$\n]{1,400}?)(?<!\s)\$(?!\d)")

#: `\[...\]`（块级）与 `\(...\)`（行内）—— **LaTeX 原生定界符**
#:
#: 2026-10-26 补。实测：让 AI 出一道带公式的题，模型吐的是
#: `概率为 \(P(X=1)=2p(1-p)\)`，而不是 `$...$`。
#:
#: 为什么会这样：`\(...\)` / `\[...\]` 是 MathJax / KaTeX 的**默认行内/块级语法**，
#: 也是大量数学语料（arXiv、数学 StackExchange、LaTeX 文档）的写法。
#: 按这些语料训练出的模型自然会这么写。
#:
#: 只认 `$...$` 的后果很具体：这些内容会被当**普通文本**原样印在 Word/PDF 上，
#: 用户看到满页的 `\(` `\)`。实测题库 432 表 2 里就印出了 `\((1-p)^2\)`。
#:
#: 判定要点：
#:   · 用非贪婪匹配，成对才算（`\(` 必须找到对应的 `\)`）
#:   · 闭合符是**字面** `\)`，转义成 `\\)` 是因为在正则里 `)` 本身没特殊含义，
#:     但 `\(` 的 `(` 有 —— 两者都转义保持对称，读起来不易错
#:   · 内容不能为空（`\(\)` 是模型偶尔吐出的空壳，不该产出空公式）
_RE_PAREN_DISPLAY_MATH = re.compile(r"\\\[(.+?)\\\]", re.S)
_RE_PAREN_INLINE_MATH = re.compile(r"\\\((.+?)\\\)", re.S)


def _split_delimited_math(text: str) -> List[Segment]:
    """按 `$$...$$` / `$...$` / `\\[...\\]` / `\\(...\\)` 切成 text / math 交替的片段"""
    # ⚠️ 早退条件要同时看 `$` 和 `\`：
    #    只看 `$` 的话，只有 `\(...\)` 的文本会直接返回，公式永远不会被识别。
    if "$" not in text and "\\(" not in text and "\\[" not in text:
        return [("text", text)]

    out: List[Segment] = []
    pos = 0
    # 先把块级公式圈出来，再在剩下的空隙里找行内
    spans: List[Tuple[int, int, str]] = []

    # ① 块级：先 `$$...$$`，再 `\[...\]`
    for rx in (_RE_DISPLAY_MATH, _RE_PAREN_DISPLAY_MATH):
        for m in rx.finditer(text):
            body = m.group(1).strip()
            if body:
                spans.append((m.start(), m.end(), body))
    covered = [(s, e) for s, e, _ in spans]

    # ② 行内：先 `$...$`，再 `\(...\)`
    for rx in (_RE_INLINE_MATH, _RE_PAREN_INLINE_MATH):
        for m in rx.finditer(text):
            s, e = m.start(), m.end()
            if any(cs <= s < ce for cs, ce in covered):
                continue
            body = m.group(1).strip()
            # 空壳 `\(\)` 跳过：产出空公式会在文档里留一个空白 OMML，比原样显示更怪
            if not body:
                continue
            spans.append((s, e, body))

    if not spans:
        return [("text", text)]

    spans.sort(key=lambda x: x[0])
    for s, e, body in spans:
        if s < pos:
            continue
        if s > pos:
            chunk = text[pos:s]
            if chunk:
                out.append(("text", chunk))
        out.append(("math", body))
        pos = e
    if pos < len(text):
        rest = text[pos:]
        if rest:
            out.append(("text", rest))
    return out


def _split_bare_math(text: str) -> List[Segment]:
    """文本段里再找「裸露的 LaTeX」（没有 `$` 包裹）"""
    if not text:
        return []
    # 只有「有反斜杠」或「有裸数学记号」时才值得跑一遍正则（纯中文正文直接放行）
    if "\\" not in text and not _RE_BARE_MARKER.search(text):
        return [("text", text)]

    pieces = _find_bare_latex(text)
    if not pieces:
        return [("text", text)]

    out: List[Segment] = []
    cursor = 0
    for start, end, latex in pieces:
        if start > cursor:
            chunk = text[cursor:start]
            if chunk.strip() or chunk:
                out.append(("text", chunk))
        out.append(("math", latex))
        cursor = end
    if cursor < len(text):
        tail = text[cursor:]
        if tail.strip() or tail:
            out.append(("text", tail))
    return out or [("text", text)]


#: 「裸数学记号」的粗筛：出现这些字符才值得进 `_find_bare_latex`
#:
#: 注意 `^` 和 `_` 单独出现太常见（`a_b` 变量名、`2^10`），
#: 所以真正的判定在 `_find_bare_latex` 里做，这里只做"要不要跑"的快速判断。
_RE_BARE_MARKER = re.compile(r"[\^_\\∫∑∏√∞≤≥≠≈±×÷∪∩∈⊂⊆→←⇒⇔∂∇]")


def _split_text_pieces(fragment: str) -> List[str]:
    """一段 HTML → 若干非空文本行（按块级结束符/换行切）"""
    if not fragment:
        return []
    txt = _inline_text(fragment)
    if not txt:
        return []
    return [ln for ln in txt.split("\n") if ln.strip()]


def _text_blocks_with_tables(fragment: str) -> List[Block]:
    """
    HTML 片段 → 有序块，**其中连续的 Markdown 表格行合成一个 table 块**

    ⚠️ 为什么不能直接用 `_split_text_pieces`（2026-10-26 v3 踩到）：
       它把文本按 `\\n` 拆成**独立的一行一块**。而 Markdown 表格必须看到
       **连续多行**（表头 + `| --- |` + 数据行）才能判定成表格。
       拆散之后每行单独看都不像表格，于是照样退化成竖线文本 ——
       实测题库 432 第 33 题就是这么漏掉的。

    所以这里先在"整段文本"层面找连续的 `|...|` 行，再对非表格部分按行切。
    """
    if not fragment:
        return []

    txt = _inline_text(fragment)
    if not txt:
        return []

    # 没有竖线 → 老老实实按行切，不走表格逻辑
    if "|" not in txt:
        return [("text", ln) for ln in txt.split("\n") if ln.strip()]

    blocks: List[Block] = []
    # 先把整段文本按 Markdown 表格提取一次（它会保留非表格文本）
    for kind, payload in _extract_md_tables_from_text(txt):
        if kind == "table":
            blocks.append(("table", payload))
        else:
            for ln in str(payload).split("\n"):
                if ln.strip():
                    blocks.append(("text", ln))
    return blocks


# ──────────────────────────────────────────────────────────── 答案归一化

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _index_to_letter(idx: int) -> Optional[str]:
    return _LETTERS[idx] if 0 <= idx < len(_LETTERS) else None


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def normalize_answer(answer: Any, question_type: int, option_count: int = 0) -> str:
    """
    把库里的各种答案写法统一成**人能读的字母/中文**

    · 单选(1)：`0` → A；`C` / `c` → C
    · 多选(2)：`0,1,2` → A, B, C；`A,C,E` → A, C, E（升序去重）
    · 判断(3)：`true/false` / `1/0` / `对/错` → 正确 / 错误
    · 其他：原样返回（填空、简答是自由文本）
    """
    if answer is None:
        return ""
    qt = _as_int(question_type) or 0
    raw = answer.strip() if isinstance(answer, str) else answer

    if qt == 3:
        s = str(raw).strip().lower()
        if s in ("true", "1", "对", "正确", "t", "yes"):
            return "正确"
        if s in ("false", "0", "错", "错误", "f", "no"):
            return "错误"
        return str(raw)

    if qt in (1, 2):
        # 多选可能给数组
        if isinstance(raw, (list, tuple)):
            items = [str(x).strip() for x in raw if str(x).strip()]
        else:
            s = str(raw).strip()
            if not s:
                return ""
            items = [p.strip() for p in re.split(r"[,，;；、\s]+", s) if p.strip()]

        letters: List[str] = []
        for it in items:
            n = _as_int(it)
            if n is not None:
                # 数字 = 选项下标
                ltr = _index_to_letter(n)
                if ltr:
                    letters.append(ltr)
            else:
                up = it.upper()
                if len(up) == 1 and up in _LETTERS:
                    letters.append(up)
                else:
                    # 认不出的写法原样保留，别丢信息
                    letters.append(it)
        # 去重＋排序（字母才排，混入的非字母放后面）
        alpha = sorted({x for x in letters if len(x) == 1 and x in _LETTERS})
        other = [x for x in letters if not (len(x) == 1 and x in _LETTERS)]
        out = alpha + other
        return ", ".join(out) if qt == 2 else (out[0] if out else "")

    return str(raw)


def _option_rows(raw_options: Any, question_type: int) -> List[Tuple[str, str]]:
    """选项 → [(字母, 文本)]；判断题固定两项"""
    qt = _as_int(question_type) or 0
    if qt == 3:
        return [("A", "正确"), ("B", "错误")]
    items: List[str] = []
    if isinstance(raw_options, list):
        items = ["" if o is None else str(o) for o in raw_options]
    elif isinstance(raw_options, str) and raw_options.strip():
        s = raw_options.strip()
        try:
            import json

            parsed = json.loads(s)
            if isinstance(parsed, list):
                items = ["" if o is None else str(o) for o in parsed]
        except Exception:  # noqa: BLE001
            items = [p.strip() for p in re.split(r"[\n,;，；]+", s) if p.strip()]
    return [(_index_to_letter(i) or str(i + 1), t) for i, t in enumerate(items)]


# ──────────────────────────────────────────────────────────── Word 导出

def _docx_set_cjk_font(run, name: str = "微软雅黑", size=None, bold=None, color=None) -> None:
    """给 run 设置中英文字体（python-docx 只设 ascii 时中文会退回默认字体）"""
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def _add_run(paragraph, text: Any, **kwargs):
    """
    往段落里加一段文字（**统一在这里清洗控制字符**）

    所有正文写入都走这个函数，避免某处漏了 `_clean_text` 就整篇 500
    （python-docx 对控制字符是硬失败，不是降级）。
    """
    run = paragraph.add_run(_clean_text(text))
    if kwargs:
        _docx_set_cjk_font(run, **kwargs)
    return run


def _add_omml(paragraph, latex: str, *, size: Optional[float] = None) -> bool:
    """
    把一段 LaTeX 作为**原生 Word 公式（OMML）**写进段落；成功返回 True

    为什么不用图片：图片公式在 Word 里不能编辑、缩放会糊，
    而且 WPS 常把它当普通图片处理导致基线错位。
    OMML 是 Word 与 WPS 都认的原生公式格式，是唯一能同时兼容两者的做法。

    `size`：公式字号（pt）。OMML 默认继承段落字号，但实测发现：
      · 上下限会被自动缩到 ~60%（11.9pt → 7.2pt），这是标准排版行为
      · 当正文 10.5pt 时，公式里的上标只有 6.3pt，**打印出来偏小**
    给公式单独设一个略大于正文的字号，能让上下标也保持在可读区间。

    失败（latex2mathml 不支持该命令等）时返回 False，调用方退回纯文本。
    """
    from app.services.mathml_omml import latex_to_omml, omml_to_xml_string

    om = latex_to_omml(latex)
    if om is None:
        return False
    try:
        from docx.oxml import parse_xml

        xml = omml_to_xml_string(om)
        el = parse_xml(xml)

        # 给公式里每个 m:r 挂一个 w:rPr 指定字号。
        # ⚠️ 必须挂在 m:r 下的 w:rPr（不是 m:rPr）：前者是"文字属性"（字号/字体），
        #    后者控制的是数学属性（是否斜体、是否正体）。
        if size:
            _apply_omml_font_size(el, size)

        paragraph._p.append(el)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] OMML 插入失败 {!r}: {}", latex, exc)
        return False


def _apply_omml_font_size(omml_el, size_pt: float) -> None:
    """
    给 OMML 里所有 `m:r` 加字号

    结构（Word 规范）::

        <m:r>
          <w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
          <m:t>e</m:t>
        </m:r>

    `w:sz` 的单位是**半磅**，所以 11pt 要写 22。
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        half = str(int(round(size_pt * 2)))
        m_ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
        for r in omml_el.iter(f"{{{m_ns}}}r"):
            # 避免重复添加
            old = r.find(qn("w:rPr"))
            if old is not None:
                r.remove(old)
            rpr = OxmlElement("w:rPr")
            for tag in ("w:sz", "w:szCs"):
                el = OxmlElement(tag)
                el.set(qn("w:val"), half)
                rpr.append(el)
            # w:rPr 必须是 m:r 的第一个子元素
            r.insert(0, rpr)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] OMML 字号设置失败: {}", exc)


def _add_segments(paragraph, text: str, **font_kwargs) -> None:
    """
    把「文字 + 裸 LaTeX」混排进同一个段落

    文字走普通 run，公式走 OMML —— 这样 `P(AB)=P(\\overline{A} \\overline{B})`
    在 Word 里就是「普通文字 + 真正的 A̅ B̅」，而不是一串反斜杠。
    """
    for kind, payload in split_text_and_math(_clean_text(text)):
        if kind == "math":
            # 公式字号比正文大一档：OMML 的上下限会被自动缩到 ~60%，
            # 若公式本身与正文同号，上标只有 6pt 左右，打印出来偏小。
            body_size = font_kwargs.get("size") or 10.5
            if not _add_omml(paragraph, payload, size=float(body_size) * 1.12):
                # 兜底：转不成就原样输出，至少信息不丢
                _add_run(paragraph, payload, **font_kwargs)
        else:
            _add_run(paragraph, payload, **font_kwargs)


def _docx_add_image(container, src: str, max_width_cm: float = 15.5) -> bool:
    """
    往文档里插一张图；成功返回 True

    图片按**原始像素比例**缩放到版心宽度以内，不拉伸变形 ——
    题目里的截图常是宽图，等比缩放后位置才对得上。

    `container` 可以是 `Document`（普通插图）**或 `_Cell`**（表格单元格内插图）。
    两者都有 `add_picture`，签名一致，所以这里不用分支。
    """
    data = _load_image_bytes(src)
    if not data:
        return False
    try:
        from docx.shared import Cm
        from PIL import Image

        # 先量尺寸算等比缩放（python-docx 只给一边的话会按原始 dpi 撑爆版心）
        with Image.open(io.BytesIO(data)) as im:
            w_px, h_px = im.size
        if w_px <= 0 or h_px <= 0:
            return False
        width_cm = max_width_cm
        height_cm = width_cm * h_px / w_px
        # 太高的图（长截图）按高度再压一次，避免一张图占满整页
        max_height_cm = 18.0
        if height_cm > max_height_cm:
            width_cm = width_cm * max_height_cm / height_cm
            height_cm = max_height_cm
        container.add_picture(io.BytesIO(data), width=Cm(width_cm), height=Cm(height_cm))
        # 居中，与网页里的排版观感一致。
        # `_Cell` 没有 `.paragraphs[-1].alignment` 的直接通路时用 last paragraph。
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        try:
            last = container.paragraphs[-1] if hasattr(container, "paragraphs") else None
            if last is not None:
                last.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] docx 插图失败 {}: {}", src, exc)
        return False


def _docx_set_cell_shading(cell, fill_hex: str) -> None:
    """
    给单元格加底纹（`w:shd`）

    python-docx 1.1.2 **没有**暴露底纹 API，只能手写 oxml。
    表头底纹是"看起来像真表格"最直观的标志，所以必须做。
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tc_pr = cell._tc.get_or_add_tcPr()
        # 同一格重复设置时先删旧的，避免出现两个 w:shd
        for old in tc_pr.findall(qn("w:shd")):
            tc_pr.remove(old)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill_hex)
        tc_pr.append(shd)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] 单元格底纹失败: {}", exc)


def _docx_set_cell_margins(cell, top=60, bottom=60, left=90, right=90) -> None:
    """单元格内边距（`w:tcMar`），单位 dxa（1/20 pt）"""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tc_pr = cell._tc.get_or_add_tcPr()
        for old in tc_pr.findall(qn("w:tcMar")):
            tc_pr.remove(old)
        mar = OxmlElement("w:tcMar")
        for side, val in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:w"), str(val))
            el.set(qn("w:type"), "dxa")
            mar.append(el)
        tc_pr.append(mar)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] 单元格边距失败: {}", exc)


def _docx_set_table_borders(table, color: str = "BFBFBF", sz: int = 4) -> None:
    """
    给整表加边框（`w:tblBorders`）

    ⚠️ 不用 `table.style = "Table Grid"`：那是**英文样式名**，
    WPS 中文版 / 部分精简 Office 里可能不存在，届时表格会变成无框线，
    而"看起来像表格"恰恰依赖框线。手写 oxml 与样式名无关，最稳。
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tbl_pr = table._tbl.tblPr
        for old in tbl_pr.findall(qn("w:tblBorders")):
            tbl_pr.remove(old)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
            borders.append(el)
        tbl_pr.append(borders)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] 表格边框失败: {}", exc)


def _docx_mark_header_row(row) -> None:
    """
    把某行标记为「跨页重复表头」（`w:tblHeader`）

    表格跨页时，Word 会在下一页自动重复这一行。
    python-docx 1.1.2 没有 API（`row.repeat_table_header` 不存在），必须手撸。
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tr_pr = row._tr.get_or_add_trPr()
        for old in tr_pr.findall(qn("w:tblHeader")):
            tr_pr.remove(old)
        el = OxmlElement("w:tblHeader")
        el.set(qn("w:val"), "true")
        tr_pr.append(el)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] 表头重复标记失败: {}", exc)


def _docx_forbid_row_split(row) -> None:
    """禁止某一行被分页切断（`w:cantSplit`）"""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tr_pr = row._tr.get_or_add_trPr()
        for old in tr_pr.findall(qn("w:cantSplit")):
            tr_pr.remove(old)
        tr_pr.append(OxmlElement("w:cantSplit"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] 行禁止分页失败: {}", exc)


def _docx_fill_cell(cell, text: str, *, base_size: float = 10, bold: bool = False,
                    align: str = "") -> None:
    """
    往一个单元格里写内容：**文字 + 原生 OMML 公式**，并按需居中/右对齐

    这是把现有能力复用进表格的关键点：
    `_add_segments` / `_add_omml` 的参数都是 **paragraph**，
    而单元格里的段落同样是 `w:p` —— 所以零改动就能用（已实测通过）。

    单元格里若含 `<img>`（表格里嵌截图很常见），也一并插图：
    先按 `<img>` 切开，文字写段落、图片插进同一个 cell。
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    cell.text = ""  # 清掉默认空段落里的内容，复用它的段落
    p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    raw = str(text or "")

    # 单元格里有图 → 先插图，再把文字写进段落（图在 Word 单元格里是单独一段）
    if "<img" in raw.lower():
        for kind, payload in split_blocks(raw):
            if kind == "image":
                _docx_add_image(cell, payload, max_width_cm=6.0)
            else:
                if bold:
                    _add_run(p, str(payload), size=base_size, bold=True)
                else:
                    _add_segments(p, str(payload), size=base_size)
        return

    if bold:
        _add_run(p, raw, size=base_size, bold=True)
        return
    # 单元格里也可能有公式（如概率分布表里的 `C_7^3`）
    _add_segments(p, raw, size=base_size)


def _docx_add_table(doc, table_data: TableData, *, indent_cm: float = 0.0) -> None:
    """
    表格块 → Word **原生表格**

    六项能力全部实现（2026-10-26 实测通过）：
      ① 表头底纹（w:shd）      ② 边框（w:tblBorders）
      ③ 固定列宽（w:gridCol）  ④ 跨页重复表头（w:tblHeader）
      ⑤ 单元格内原生 OMML 公式 ⑥ 单元格内图片

    列宽策略：按各列「最长内容长度」分配，总宽固定 15.5cm（版心内）。
    不按字数绝对比例，而是加一个下限，避免"1"这种极短列被压成 0.3cm。
    """
    from docx.shared import Cm

    headers: List[str] = list(table_data.get("headers") or [])
    rows: List[List[str]] = [list(r) for r in (table_data.get("rows") or [])]
    aligns: List[str] = list(table_data.get("align") or [])

    ncol = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
    if ncol <= 0:
        return

    total_rows = (1 if headers else 0) + len(rows)
    if total_rows <= 0:
        return

    avail_w = max(6.0, 15.5 - indent_cm)

    # ── 列宽：按内容长度加权，每列至少 1.5cm ──
    col_max = [1] * ncol
    for r in ([headers] if headers else []) + rows:
        for j in range(min(ncol, len(r))):
            # 中文字符按 2 个宽度算，避免中文列被压窄
            ln = sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(r[j]))
            col_max[j] = max(col_max[j], min(ln, 40))
    weight_sum = sum(col_max) or ncol
    widths = [max(1.5, avail_w * (c / weight_sum)) for c in col_max]
    # 归一化到 avail_w
    scale = avail_w / sum(widths) if sum(widths) > 0 else 1
    widths = [w * scale for w in widths]

    table = doc.add_table(rows=total_rows, cols=ncol)
    # ⚠️ 不设 table.style：手写边框，与样式名无关（WPS 兼容）
    table.autofit = False

    _docx_set_table_borders(table)

    # 固定列宽（同时写 tblGrid 与每个 tc 的 tcW，Word/WPS 都认）
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        tbl_pr = table._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tbl_pr.append(layout)
    except Exception:  # noqa: BLE001
        pass

    for j, w in enumerate(widths):
        try:
            table.columns[j].width = Cm(w)
        except Exception:  # noqa: BLE001
            pass
        for row in table.rows:
            try:
                row.cells[j].width = Cm(w)
            except Exception:  # noqa: BLE001
                pass

    # ── 写内容 ──
    r0 = 0
    if headers:
        hrow = table.rows[0]
        _docx_mark_header_row(hrow)
        _docx_forbid_row_split(hrow)
        for j in range(ncol):
            cell = hrow.cells[j]
            _docx_set_cell_shading(cell, "E8EEF7")
            _docx_set_cell_margins(cell)
            _docx_fill_cell(cell, str(headers[j]) if j < len(headers) else "",
                            base_size=9.5, bold=True, align="center")
        r0 = 1

    for i, r in enumerate(rows):
        row = table.rows[r0 + i]
        _docx_forbid_row_split(row)
        for j in range(ncol):
            cell = row.cells[j]
            _docx_set_cell_margins(cell)
            txt = str(r[j]) if j < len(r) else ""
            al = aligns[j] if j < len(aligns) else ""
            _docx_fill_cell(cell, txt, base_size=9.5, align=al)

    # 表格后留一点空隙，避免紧贴下一题
    doc.add_paragraph()


def _docx_add_blocks(doc, blocks: List[Block], *, indent_cm: float = 0.0) -> None:
    """把有序块写进 docx：文字成段（含公式）、图片原地插入、表格成真表格"""
    from docx.shared import Cm

    max_w = 15.5 - indent_cm
    for kind, payload in blocks:
        if kind == "text":
            p = doc.add_paragraph()
            if indent_cm:
                p.paragraph_format.left_indent = Cm(indent_cm)
            # 文字里可能夹着裸 LaTeX / $...$ —— 交给 _add_segments 混排成「文字 + 原生公式」
            _add_segments(p, payload, size=10.5)
        elif kind == "table":
            # 2026-10-26 v3：表格 → Word 原生表格（不再退化成竖线文本）
            _docx_add_table(doc, payload, indent_cm=indent_cm)
        else:
            if not _docx_add_image(doc, payload, max_width_cm=max_w):
                p = doc.add_paragraph()
                if indent_cm:
                    p.paragraph_format.left_indent = Cm(indent_cm)
                _add_run(p, f"[图片缺失] {payload}", size=9, color=(0x99, 0x99, 0x99))


def export_bank_docx(
    bank: Dict[str, Any],
    questions: List[Dict[str, Any]],
    *,
    with_answers: bool = True,
) -> bytes:
    """
    题库 → .docx 字节

    with_answers=False 时输出「学生卷」：只保留题干 / 选项 / 组合题的子题题干，
    **去掉答案与解析**（用户 2026-10-19 要求支持有答案/无答案两种版本）。
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    doc = Document()

    # 版心：A4 + 常规页边距
    section = doc.sections[0]
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)

    # ── 封面区：题库名 / 科目 / 统计 ──
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(title_p, str(bank.get("bankName") or "未命名题库"), size=20, bold=True)

    meta_bits = []
    if bank.get("subject"):
        meta_bits.append(f"科目：{bank['subject']}")
    meta_bits.append(f"题目数：{len(questions)}")
    if bank.get("createTime"):
        meta_bits.append(f"创建时间：{str(bank['createTime'])[:10]}")
    # 无答案版在封面上明确标出来，避免老师把学生卷当成答案卷发出去
    if not with_answers:
        meta_bits.append("版本：无答案")
    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(meta_p, "　·　".join(meta_bits), size=9, color=(0x66, 0x66, 0x66))

    if bank.get("description"):
        desc_p = doc.add_paragraph()
        desc_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(desc_p, str(bank["description"]), size=9.5, color=(0x77, 0x77, 0x77))

    doc.add_paragraph()

    # ── 题目正文 ──
    for idx, q in enumerate(questions, start=1):
        qtype = _as_int(q.get("questionType")) or 1
        type_text = q.get("questionTypeText") or ""

        # 题号 + 题型徽标
        head = doc.add_paragraph()
        _add_run(head, f"{idx}. ", size=11, bold=True, color=(0x1A, 0x1A, 0x1A))
        if type_text:
            _add_run(head, f"［{type_text}］", size=8.5, color=(0x88, 0x88, 0x88))

        # 题干（图文按原序，文字里的裸 LaTeX 转原生公式）
        stem_html = q.get("questionText") or q.get("content") or ""
        _docx_add_blocks(doc, split_blocks(stem_html), indent_cm=0.45)

        # 选项（选项里也可能有公式，如 `A. \dfrac{1}{2}`）
        opts = _option_rows(q.get("options"), qtype)
        for letter, text in opts:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.space_after = Pt(2)
            _add_run(p, f"{letter}. ", size=10.5, bold=True)
            _add_segments(p, text, size=10.5)

        # 子题（组合题）
        for s_idx, sub in enumerate(q.get("subQuestions") or [], start=1):
            sp = doc.add_paragraph()
            sp.paragraph_format.left_indent = Cm(0.45)
            _add_run(sp, f"({s_idx}) ", size=10.5, bold=True)
            _docx_add_blocks(doc, split_blocks(sub.get("questionText") or ""), indent_cm=0.75)
            for letter, text in _option_rows(sub.get("options"), _as_int(sub.get("questionType")) or 1):
                op = doc.add_paragraph()
                op.paragraph_format.left_indent = Cm(1.05)
                op.paragraph_format.space_after = Pt(2)
                _add_run(op, f"{letter}. ", size=10, bold=True)
                _add_segments(op, text, size=10)
            if with_answers:
                sub_ans = normalize_answer(sub.get("answer"), _as_int(sub.get("questionType")) or 1)
                if sub_ans:
                    ap = doc.add_paragraph()
                    ap.paragraph_format.left_indent = Cm(0.75)
                    _add_run(ap, "答案：", size=10, bold=True, color=(0x11, 0x66, 0x33))
                    _add_segments(ap, sub_ans, size=10, color=(0x11, 0x66, 0x33))

        if with_answers:
            # 答案
            ans = normalize_answer(q.get("answer"), qtype, len(opts))
            if ans:
                ap = doc.add_paragraph()
                ap.paragraph_format.left_indent = Cm(0.45)
                ap.paragraph_format.space_before = Pt(4)
                _add_run(ap, "答案：", size=10.5, bold=True, color=(0x0F, 0x7A, 0x3D))
                _add_segments(ap, ans, size=10.5, color=(0x0F, 0x7A, 0x3D))

            # 解析（图文按原序）
            ana_blocks = split_blocks(q.get("analysis") or q.get("questionAnalysis") or "")
            if ana_blocks:
                label = doc.add_paragraph()
                label.paragraph_format.left_indent = Cm(0.45)
                label.paragraph_format.space_before = Pt(4)
                _add_run(label, "解析：", size=10.5, bold=True, color=(0x55, 0x55, 0x55))
                _docx_add_blocks(doc, ana_blocks, indent_cm=0.45)
        else:
            # 无答案版：留出作答空间（简答题直接空行，选择题选项已给出）
            if qtype in (4, 5):
                blank = doc.add_paragraph()
                blank.paragraph_format.left_indent = Cm(0.45)
                _add_run(blank, "答：", size=10.5, color=(0x99, 0x99, 0x99))
                for _ in range(3):
                    doc.add_paragraph()

        # 题间分隔
        sep = doc.add_paragraph()
        sep.paragraph_format.space_before = Pt(6)
        sep.paragraph_format.space_after = Pt(6)
        _add_run(sep, "─" * 34, size=8, color=(0xDD, 0xDD, 0xDD))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────── PDF 导出

_CJK_FONT_NAME = "OpenStudyCJK"
_cjk_registered = False


def _register_cjk_font() -> str:
    """
    注册一个支持中文的字体，返回字体名

    依次尝试常见系统字体；全都没有就退回 reportlab 自带的 STSong-Light
    （reportlab 内置 CID 字体，不依赖外部文件，但只有在支持 CJK 的环境下才可用）。
    """
    global _cjk_registered, _CJK_FONT_NAME
    if _cjk_registered:
        return _CJK_FONT_NAME

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        # Windows
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        # Linux（容器里装的是 fonts-wqy-zenhei，见 Dockerfile）
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            # .ttc 是字体集合，reportlab 需要指定 face index
            if path.lower().endswith(".ttc"):
                pdfmetrics.registerFont(TTFont(_CJK_FONT_NAME, path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(_CJK_FONT_NAME, path))
            _cjk_registered = True
            logger.info("[export] PDF 使用字体 {}", path)
            return _CJK_FONT_NAME
        except Exception as exc:  # noqa: BLE001
            logger.debug("[export] 字体 {} 不可用: {}", path, exc)
            continue

    # 兜底：reportlab 内置 CID 中文字体
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _CJK_FONT_NAME = "STSong-Light"
    except Exception:  # noqa: BLE001
        _CJK_FONT_NAME = "Helvetica"  # 最后兜底：至少不崩，中文会变方框
    _cjk_registered = True
    logger.warning("[export] 未找到系统 CJK 字体，回退到 {}", _CJK_FONT_NAME)
    return _CJK_FONT_NAME


# ──────────────────────────────────────────────────────────── PDF 公式（Unicode 降级）

#: 带上划线语义的命令
_RE_OVERLINE_CMD = re.compile(r"\\overline\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
#: 带下划线语义的命令
_RE_UNDERLINE_CMD = re.compile(r"\\underline\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
#: 分数（含 dfrac/tfrac）
_RE_FRAC_CMD = re.compile(
    r"\\(?:d|t)?frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
)
#: 平方根
_RE_SQRT_CMD = re.compile(r"\\sqrt\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
#: 上标 `x^{2}`
_RE_SUP = re.compile(r"\^\{([^{}]*)\}|\^(\w)")
#: 下标 `a_{i}`
_RE_SUB = re.compile(r"_\{([^{}]*)\}|_(\w)")


def _latex_to_pdf_markup(latex: str) -> str:
    """
    把一段 LaTeX 转成 reportlab `Paragraph` 的内联标记

    · `\\overline{X}` → `X` + 组合上划线 U+0305（渲染出来就是横杠压在字上）
    · `\\dfrac{a}{b}` → `a⁄b`（用分数斜线 U+2044，比 `a/b` 更像公式）
    · `\\sqrt{x}`    → `√x`（加括号避免歧义：`√(x)`）
    · `x^{2}` / `a_{i}` → `<super>` / `<sub>`（reportlab 原生支持）
    · 其余符号 → `_PDF_MATH_SYMBOLS` 查表；查不到的保留原样，信息不丢
    """
    s = latex.strip()
    if not s:
        return ""

    # ① 上划线
    #
    # ⚠️ 三种写法都试过，只有 `‾`(U+203E) 前置可用：
    #    · 组合上划线 U+0305 —— 微软雅黑/文泉驿的 cmap 里**根本没有这个码位**
    #      （fontTools 实测 `0x305 in cmap = False`），渲染成空方块；
    #    · reportlab 的 `<u>` 标签 —— 线画在**下方**，数学语义反了；
    #    · `‾` 前置 —— 实测输出 `P(‾A‾B)`，视觉上就是 A、B 各自带一横，可用。
    # 多字符（如 `\overline{AB}`）时逐字加前缀，横线才连得起来。
    def _ov(m: re.Match) -> str:
        inner = m.group(1)
        # 已经含 LaTeX 命令就递归处理一次
        if "\\" in inner:
            inner = _latex_to_pdf_markup(inner)
        return "".join(f"{_OVERLINE_CHAR}{ch}" if ch.strip() else ch for ch in inner)

    s = _RE_OVERLINE_CMD.sub(_ov, s)

    # ② 下划线（组合下划线 U+0332）
    def _ul(m: re.Match) -> str:
        inner = m.group(1)
        if "\\" in inner:
            inner = _latex_to_pdf_markup(inner)
        return "".join(ch + "\u0332" if ch.strip() else ch for ch in inner)

    s = _RE_UNDERLINE_CMD.sub(_ul, s)

    # ③ 分数
    def _frac(m: re.Match) -> str:
        num, den = m.group(1), m.group(2)
        if "\\" in num:
            num = _latex_to_pdf_markup(num)
        if "\\" in den:
            den = _latex_to_pdf_markup(den)
        # 分子/分母需要括号时补上，避免 ⁄ 结合歧义
        if len(num) > 1 and not num.startswith("("):
            num = f"({num})"
        if len(den) > 1 and not den.startswith("("):
            den = f"({den})"
        return f"{num}\u2044{den}"

    s = _RE_FRAC_CMD.sub(_frac, s)

    # ④ 根号
    def _sqrt(m: re.Match) -> str:
        inner = m.group(1)
        if "\\" in inner:
            inner = _latex_to_pdf_markup(inner)
        return f"√({inner})"

    s = _RE_SQRT_CMD.sub(_sqrt, s)

    # ⑤ 上下标 → reportlab 标签
    s = _RE_SUP.sub(lambda m: f"<super>{m.group(1) or m.group(2)}</super>", s)
    s = _RE_SUB.sub(lambda m: f"<sub>{m.group(1) or m.group(2)}</sub>", s)

    # ⑥ 剩余命令 → Unicode 符号；未收录的原样保留
    def _sym(m: re.Match) -> str:
        name = m.group(1)
        return _PDF_MATH_SYMBOLS.get(name, "\\" + name)

    s = re.sub(r"\\([a-zA-Z]+)", _sym, s)

    # ⑦ 花括号在公式里只是分组语法，输出时去掉（内容已展开）
    s = s.replace("{", "").replace("}", "")
    # ⑧ 转义后交给 reportlab（注意：此时已含 <super>/<sub> 标签，不能再整体转义）
    return _escape_keeping_tags(s)


def _escape_keeping_tags(s: str) -> str:
    """转义 & < >，但保留 `<super>` / `<sub>` 这类我们主动加的内联标签"""
    # 先把自家标签换成占位符 → 转义 → 换回来
    keep = {
        "<super>": "\u0001SUP\u0001",
        "</super>": "\u0001/SUP\u0001",
        "<sub>": "\u0001SUB\u0001",
        "</sub>": "\u0001/SUB\u0001",
        "<b>": "\u0001B\u0001",
        "</b>": "\u0001/B\u0001",
        "<i>": "\u0001I\u0001",
        "</i>": "\u0001/I\u0001",
    }
    for tag, ph in keep.items():
        s = s.replace(tag, ph)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for tag, ph in keep.items():
        s = s.replace(ph, tag)
    return s


def _rl_text_with_math(text: str, font: str, body_size: float = 10.5) -> str:
    """
    一段可能含裸 LaTeX 的文字 → reportlab Paragraph 标记

    普通文字保持原样（含换行 → `<br/>`），公式片段交给 `_latex_to_pdf_markup`。
    """
    if not text:
        return ""
    # 先清洗控制字符（与 docx 同口径），再拆公式
    cleaned = _clean_text(text)
    pieces = split_text_and_math(cleaned)
    out: List[str] = []
    for kind, payload in pieces:
        if kind == "math":
            out.append(_latex_to_pdf_markup(payload))
        else:
            # 普通文字：先转义，再把 `C_7^3` 这类**纯文本上下标**转成 <sub>/<super>
            esc = (
                payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br/>")
            )
            out.append(_plain_subsup(esc))
    return "".join(out)


def _plain_subsup(text: str) -> str:
    """
    把纯文本里的 `x_2` / `x^3` 转成 reportlab 的 `<sub>` / `<super>`

    为什么需要：题库里大量上下标**不是 LaTeX**，而是直接写的 `C_7^3`、`x^2`
    （Word/WPS 导入时被转平了）。不动它的话 PDF 里就原样显示下划线符号，
    而数学上那应该是下标。

    保守规则（宁可漏转）：
      · 只有「单个字母或 ) + `_`/`^` + 一到多个字母数字」才转；
      · `x^2` 这种单字符指数转，`a_b` 单字符下标转；
      · 避免误伤正常文字里的下划线（如 `user_name`）：要求 `_` 后面紧跟
        字母数字、且前面是**单个字符**（`C_7` 可以，`user_name` 的 `r_name` 不匹配
        因为前面是多字符单词 —— 用 `(?<![A-Za-z0-9]{2})` 这种后顾实现）。
    """
    # 上标：a^2（裸形式；`a^{...}` 由 _latex_to_pdf_markup 处理）
    text = re.sub(r"(?<![A-Za-z0-9])(\w)\^(\w+)", r"\1<super>\2</super>", text)
    # 下标：C_7 —— 前面只能是一个字符（避免 user_name 被转）
    text = re.sub(r"(?<![A-Za-z0-9])(\w)_(\w+)", r"\1<sub>\2</sub>", text)
    return text


def _pdf_add_table(story: List[Any], table_data: TableData, font: str, *,
                   indent: float = 0.0, body_size: float = 9.5) -> None:
    """
    表格块 → PDF **原生表格**（reportlab `Table`）

    实现的能力：
      · 表头底纹（BACKGROUND）           · 全表网格线（GRID）
      · **跨页重复表头**（`repeatRows=1`）· 单元格内公式（走 `_rl_text_with_math`）
      · 列宽按内容加权，总宽压在版心内
      · 单元格垂直居中 + 内边距，避免文字贴边

    ⚠️ 为什么不用 `LongTable`：`Table` + `repeatRows` 已经能在跨页时重复表头，
    而 `LongTable` 的分页行为更激进（它会把一行拆开），题目表格宁可不拆行。
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph
    from reportlab.platypus import Table as RLTable
    from reportlab.platypus import TableStyle

    headers: List[str] = list(table_data.get("headers") or [])
    rows: List[List[str]] = [list(r) for r in (table_data.get("rows") or [])]
    aligns: List[str] = list(table_data.get("align") or [])

    ncol = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
    if ncol <= 0:
        return

    avail_w = max(6.0, 15.5 - indent) * cm

    # 单元格样式（比正文小一号，表格里塞 10.5pt 会很挤）
    cell_style = ParagraphStyle(
        "tcell", fontName=font, fontSize=body_size, leading=body_size * 1.45,
    )
    head_style = ParagraphStyle(
        "tcellh", fontName=font, fontSize=body_size, leading=body_size * 1.45,
        alignment=1,  # 居中
    )

    def _cell(text: str, style) -> Any:
        """单元格内容：公式走 _rl_text_with_math，普通文字转义后用 Paragraph"""
        s = str(text or "")
        try:
            return Paragraph(_rl_text_with_math(s, font, body_size), style)
        except Exception:  # noqa: BLE001
            return Paragraph(_escape_for_rl(s), style)

    data: List[List[Any]] = []
    if headers:
        data.append([_cell(headers[j] if j < len(headers) else "", head_style) for j in range(ncol)])
    for r in rows:
        data.append([_cell(r[j] if j < len(r) else "", cell_style) for j in range(ncol)])

    if not data:
        return

    # ── 列宽：按内容长度加权，每列至少 1.6cm ──
    col_max = [1] * ncol
    for r in ([headers] if headers else []) + rows:
        for j in range(min(ncol, len(r))):
            ln = sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(r[j]))
            col_max[j] = max(col_max[j], min(ln, 40))
    min_w = 1.6 * cm
    weight_sum = sum(col_max) or ncol
    widths = [max(min_w, avail_w * (c / weight_sum)) for c in col_max]
    # 归一化：总宽必须 <= avail_w，否则 reportlab 会告警并自动缩
    total = sum(widths)
    if total > avail_w:
        widths = [w * avail_w / total for w in widths]

    try:
        table = RLTable(data, colWidths=widths, repeatRows=1 if headers else 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] PDF 表格构建失败: {}", exc)
        # 退化成纯文本，至少内容不丢
        for r in data:
            story.append(Paragraph(_escape_for_rl(str(r)), cell_style))
        return

    ts = [
        # 网格线
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if headers:
        ts.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")))

    # 对齐方式（表头已居中；数据列按 md 对齐标记）
    for j in range(ncol):
        al = aligns[j] if j < len(aligns) else ""
        if al == "center":
            ts.append(("ALIGN", (j, 1 if headers else 0), (j, -1), "CENTER"))
        elif al == "right":
            ts.append(("ALIGN", (j, 1 if headers else 0), (j, -1), "RIGHT"))

    table.setStyle(TableStyle(ts))
    if indent:
        table.hAlign = "LEFT"
    else:
        table.hAlign = "CENTER"

    story.append(table)
    story.append(_pdf_spacer(4))


def _pdf_spacer(h: float) -> Any:
    """表格后的空隙（延迟 import，避免模块级依赖 reportlab）"""
    from reportlab.platypus import Spacer

    return Spacer(1, h)


def _pdf_add_blocks(story: List[Any], blocks: List[Block], font: str, *, indent: float = 0.0,
                    body_size: float = 10.5) -> None:
    """把有序块写进 PDF story：文字成段（含公式）、图片原地插入、表格成真表格"""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, Spacer

    style = ParagraphStyle(
        "body", fontName=font, fontSize=body_size, leading=body_size * 1.65,
        leftIndent=indent * cm, spaceAfter=2,
    )
    max_w = (21.0 - 2.4 - 2.4 - indent) * cm  # A4 宽 - 页边距 - 缩进

    for kind, payload in blocks:
        if kind == "text":
            # 文字里可能夹着 $...$ / 裸 LaTeX → 用 Paragraph 内联标记画成公式
            story.append(Paragraph(_rl_text_with_math(payload, font, body_size), style))
        elif kind == "table":
            # 2026-10-26 v3：表格 → PDF 原生表格（不再退化成竖线文本）
            _pdf_add_table(story, payload, font, indent=indent, body_size=max(8.5, body_size - 1))
        else:
            data = _load_image_bytes(payload)
            if not data:
                miss = ParagraphStyle(
                    "miss", fontName=font, fontSize=8.5, textColor="#999999",
                    leftIndent=indent * cm,
                )
                story.append(Paragraph(_escape_for_rl(f"[图片缺失] {payload}"), miss))
                continue
            try:
                from PIL import Image as PILImage

                with PILImage.open(io.BytesIO(data)) as im:
                    w_px, h_px = im.size
                if w_px <= 0 or h_px <= 0:
                    continue
                # 等比缩放到版心内
                draw_w = max_w
                draw_h = draw_w * h_px / w_px
                # 高度上限压在 ~14cm（页面可用高度约 25.7cm）：
                # 题干 + 图片 + 选项 + 答案 + 解析是一组，图太大会把同题的文字顶到上一页，
                # 造成"图单独一页、文字在别处"的割裂。
                max_h = 14.0 * cm
                if draw_h > max_h:
                    draw_w = draw_w * max_h / draw_h
                    draw_h = max_h
                img = RLImage(io.BytesIO(data), width=draw_w, height=draw_h)
                img.hAlign = "CENTER"
                story.append(Spacer(1, 4))
                story.append(img)
                story.append(Spacer(1, 4))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[export] PDF 插图失败 {}: {}", payload, exc)


def _escape_for_rl(text: str) -> str:
    """Paragraph 的迷你标记语言里 & < > 要转义，并剔除控制字符"""
    return (
        _clean_text(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        # 保留换行为 <br/>，否则多行文本会被压成一整段
        .replace("\n", "<br/>")
    )


def _keep_together_if_fits(story: List[Any], parts: List[Any], doc) -> None:
    """
    尽量把一组 flowable 绑在同一页；若这组本身就超过一页则可读性优先，退回流式排布

    为什么需要它：reportlab 的 `KeepTogether` 遇到「单个不可拆分的块比整页还高」时
    会反复重排却放不下；带长解析的题（简答题答案常常上千字）正是这种。
    所以先自己量高度：装得下才绑定，否则把元素逐项塞进 story（允许跨页）。

    ⚠️ 不能返回 list —— story 里只接受 flowable 实例，
       `AttributeError: 'list' object has no attribute 'getKeepWithNext'`。
    """
    from reportlab.platypus import KeepTogether

    try:
        avail_w = doc.width
        avail_h = doc.height
        total_h = 0.0
        for f in parts:
            _, h = f.wrap(avail_w, avail_h)
            total_h += h
        # 留 2cm 余量，避免卡在临界点上反复分页
        if total_h <= avail_h - 56.7:
            story.append(KeepTogether(parts))
            return
    except Exception:  # noqa: BLE001
        pass
    story.extend(parts)


def export_bank_pdf(
    bank: Dict[str, Any],
    questions: List[Dict[str, Any]],
    *,
    with_answers: bool = True,
) -> bytes:
    """
    题库 → .pdf 字节

    with_answers=False 时输出「学生卷」：去掉答案与解析，简答题留作答空行。
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font = _register_cjk_font()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.4 * cm, rightMargin=2.4 * cm,
        topMargin=2.2 * cm, bottomMargin=2.0 * cm,
        title=str(bank.get("bankName") or "题库导出"),
    )

    st_title = ParagraphStyle(
        "t", fontName=font, fontSize=20, leading=28, alignment=TA_CENTER, spaceAfter=6,
    )
    st_meta = ParagraphStyle(
        "m", fontName=font, fontSize=9, leading=14, alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"), spaceAfter=2,
    )
    st_desc = ParagraphStyle(
        "d", fontName=font, fontSize=9.5, leading=15, alignment=TA_CENTER,
        textColor=colors.HexColor("#777777"), spaceAfter=10,
    )
    st_head = ParagraphStyle(
        "h", fontName=font, fontSize=11, leading=17, spaceBefore=6, spaceAfter=3,
    )
    st_opt = ParagraphStyle(
        "o", fontName=font, fontSize=10.5, leading=16.5, leftIndent=0.75 * cm, spaceAfter=1,
    )
    st_ans = ParagraphStyle(
        "a", fontName=font, fontSize=10.5, leading=16.5, leftIndent=0.45 * cm,
        textColor=colors.HexColor("#0F7A3D"), spaceBefore=3,
    )
    st_sep = ParagraphStyle(
        "s", fontName=font, fontSize=8, textColor=colors.HexColor("#DDDDDD"),
        spaceBefore=8, spaceAfter=8,
    )

    story: List[Any] = []
    story.append(Paragraph(_escape_for_rl(str(bank.get("bankName") or "未命名题库")), st_title))

    meta_bits = []
    if bank.get("subject"):
        meta_bits.append(f"科目：{bank['subject']}")
    meta_bits.append(f"题目数：{len(questions)}")
    if bank.get("createTime"):
        meta_bits.append(f"创建时间：{str(bank['createTime'])[:10]}")
    if not with_answers:
        meta_bits.append("版本：无答案")
    story.append(Paragraph(_escape_for_rl("　·　".join(meta_bits)), st_meta))
    if bank.get("description"):
        story.append(Paragraph(_escape_for_rl(str(bank["description"])), st_desc))
    else:
        story.append(Spacer(1, 8))

    for idx, q in enumerate(questions, start=1):
        qtype = _as_int(q.get("questionType")) or 1
        type_text = q.get("questionTypeText") or ""

        # 每道题的元素先收进独立列表，最后整组塞进 KeepTogether ——
        # 否则分页会把「题干」和「配图」拆到两页，读者要在两页间对图。
        parts: List[Any] = []

        head_txt = f"<b>{idx}.</b>"
        if type_text:
            head_txt += f' <font size="8.5" color="#888888">［{_escape_for_rl(type_text)}］</font>'
        parts.append(Paragraph(head_txt, st_head))

        # 题干：文字块沿用 st_head 的缩进感 —— 用 body 样式
        _pdf_add_blocks(parts, split_blocks(q.get("questionText") or q.get("content") or ""), font)

        opts = _option_rows(q.get("options"), qtype)
        for letter, text in opts:
            # 选项里可能有公式（`A. \dfrac{1}{2}`）→ 走公式渲染
            parts.append(Paragraph(f"<b>{letter}.</b> {_rl_text_with_math(text, font)}", st_opt))

        for s_idx, sub in enumerate(q.get("subQuestions") or [], start=1):
            parts.append(Paragraph(f"<b>({s_idx})</b>", st_head))
            _pdf_add_blocks(
                parts, split_blocks(sub.get("questionText") or ""), font, indent=0.45, body_size=10
            )
            for letter, text in _option_rows(sub.get("options"), _as_int(sub.get("questionType")) or 1):
                parts.append(Paragraph(f"<b>{letter}.</b> {_rl_text_with_math(text, font)}", st_opt))
            if with_answers:
                sub_ans = normalize_answer(sub.get("answer"), _as_int(sub.get("questionType")) or 1)
                if sub_ans:
                    parts.append(Paragraph(f"<b>答案：</b>{_rl_text_with_math(sub_ans, font)}", st_ans))

        if with_answers:
            ans = normalize_answer(q.get("answer"), qtype, len(opts))
            if ans:
                parts.append(Paragraph(f"<b>答案：</b>{_rl_text_with_math(ans, font)}", st_ans))

            ana_blocks = split_blocks(q.get("analysis") or q.get("questionAnalysis") or "")
            if ana_blocks:
                st_ana_lbl = ParagraphStyle(
                    "al", fontName=font, fontSize=10.5, leading=16.5, leftIndent=0.45 * cm,
                    textColor=colors.HexColor("#555555"), spaceBefore=3,
                )
                parts.append(Paragraph("<b>解析：</b>", st_ana_lbl))
                _pdf_add_blocks(parts, ana_blocks, font, indent=0.45)
        else:
            # 无答案版：主观题留出作答空间
            if qtype in (4, 5):
                st_blank = ParagraphStyle(
                    "bl", fontName=font, fontSize=10.5, leading=16.5, leftIndent=0.45 * cm,
                    textColor=colors.HexColor("#999999"), spaceBefore=4,
                )
                parts.append(Paragraph("答：", st_blank))
                for _ in range(2):
                    parts.append(Spacer(1, 18))

        parts.append(Paragraph("─" * 34, st_sep))

        # 整题绑定：优先不跨页。但带长解析/大图的题可能**本身就超过一页** ——
        # 那种情况下 KeepTogether 会让 reportlab 反复重排却放不下，
        # 所以 `_keep_together_if_fits` 会先量高度：装得下才绑定，否则逐项展开。
        _keep_together_if_fits(story, parts, doc)

    doc.build(story)
    return buf.getvalue()
