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


#: 一个"块" = 一段文字 或 一张图，按 HTML 里出现的先后顺序排列
Block = Tuple[str, Any]  # ("text", str) | ("image", src)


def split_blocks(raw: Optional[str]) -> List[Block]:
    """
    把题干/解析这类 HTML 拆成有序块，**保持图文原始顺序**

    做法：把 `<img>` 与其余文本交替切开，每段文本再按块级结束符切行。
    这样 `<p>文字</p><p><img></p><p>文字</p>` →
        [("text","文字"), ("image",src), ("text","文字")]
    而不是"所有文字 + 所有图片"。
    """
    if not raw:
        return []
    if not isinstance(raw, str):
        raw = str(raw)

    # 纯文本（没有标签）直接一段
    if "<" not in raw:
        t = _inline_text(raw)
        return [("text", t)] if t else []

    blocks: List[Block] = []
    pos = 0
    for m in _RE_IMG.finditer(raw):
        before = raw[pos:m.start()]
        for piece in _split_text_pieces(before):
            blocks.append(("text", piece))
        tag = m.group(0)
        src_m = _RE_ATTR_SRC.search(tag)
        src = (src_m.group(1) or src_m.group(2)) if src_m else ""
        if src:
            blocks.append(("image", _html.unescape(src.strip())))
        pos = m.end()
    for piece in _split_text_pieces(raw[pos:]):
        blocks.append(("text", piece))
    return blocks


def _split_text_pieces(fragment: str) -> List[str]:
    """一段 HTML → 若干非空文本行（按块级结束符/换行切）"""
    if not fragment:
        return []
    txt = _inline_text(fragment)
    if not txt:
        return []
    return [ln for ln in txt.split("\n") if ln.strip()]


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


def _docx_add_image(doc, src: str, max_width_cm: float = 15.5) -> bool:
    """
    往文档里插一张图；成功返回 True

    图片按**原始像素比例**缩放到版心宽度以内，不拉伸变形 ——
    题目里的截图常是宽图，等比缩放后位置才对得上。
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
        doc.add_picture(io.BytesIO(data), width=Cm(width_cm), height=Cm(height_cm))
        # 居中，与网页里的排版观感一致
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[export] docx 插图失败 {}: {}", src, exc)
        return False


def _docx_add_blocks(doc, blocks: List[Block], *, indent_cm: float = 0.0) -> None:
    """把有序块写进 docx：文字成段、图片原地插入"""
    from docx.shared import Cm

    max_w = 15.5 - indent_cm
    for kind, payload in blocks:
        if kind == "text":
            p = doc.add_paragraph()
            if indent_cm:
                p.paragraph_format.left_indent = Cm(indent_cm)
            _add_run(p, payload, size=10.5)
        else:
            if not _docx_add_image(doc, payload, max_width_cm=max_w):
                p = doc.add_paragraph()
                if indent_cm:
                    p.paragraph_format.left_indent = Cm(indent_cm)
                _add_run(p, f"[图片缺失] {payload}", size=9, color=(0x99, 0x99, 0x99))


def export_bank_docx(bank: Dict[str, Any], questions: List[Dict[str, Any]]) -> bytes:
    """题库 → .docx 字节"""
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

        # 题干（图文按原序）
        stem_html = q.get("questionText") or q.get("content") or ""
        _docx_add_blocks(doc, split_blocks(stem_html), indent_cm=0.45)

        # 选项
        opts = _option_rows(q.get("options"), qtype)
        for letter, text in opts:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.space_after = Pt(2)
            _add_run(p, f"{letter}. ", size=10.5, bold=True)
            _add_run(p, text, size=10.5)

        # 子题（组合题）
        for s_idx, sub in enumerate(q.get("subQuestions") or [], start=1):
            sp = doc.add_paragraph()
            sp.paragraph_format.left_indent = Cm(0.45)
            st = sub.get("questionTypeText") or ""
            _add_run(sp, f"({s_idx}) ", size=10.5, bold=True)
            _docx_add_blocks(doc, split_blocks(sub.get("questionText") or ""), indent_cm=0.75)
            for letter, text in _option_rows(sub.get("options"), _as_int(sub.get("questionType")) or 1):
                op = doc.add_paragraph()
                op.paragraph_format.left_indent = Cm(1.05)
                op.paragraph_format.space_after = Pt(2)
                _add_run(op, f"{letter}. ", size=10, bold=True)
                _add_run(op, text, size=10)
            sub_ans = normalize_answer(sub.get("answer"), _as_int(sub.get("questionType")) or 1)
            if sub_ans:
                ap = doc.add_paragraph()
                ap.paragraph_format.left_indent = Cm(0.75)
                _add_run(ap, "答案：", size=10, bold=True, color=(0x11, 0x66, 0x33))
                _add_run(ap, sub_ans, size=10, color=(0x11, 0x66, 0x33))

        # 答案
        ans = normalize_answer(q.get("answer"), qtype, len(opts))
        if ans:
            ap = doc.add_paragraph()
            ap.paragraph_format.left_indent = Cm(0.45)
            ap.paragraph_format.space_before = Pt(4)
            _add_run(ap, "答案：", size=10.5, bold=True, color=(0x0F, 0x7A, 0x3D))
            _add_run(ap, ans, size=10.5, color=(0x0F, 0x7A, 0x3D))

        # 解析（图文按原序）
        ana_blocks = split_blocks(q.get("analysis") or q.get("questionAnalysis") or "")
        if ana_blocks:
            label = doc.add_paragraph()
            label.paragraph_format.left_indent = Cm(0.45)
            label.paragraph_format.space_before = Pt(4)
            _add_run(label, "解析：", size=10.5, bold=True, color=(0x55, 0x55, 0x55))
            _docx_add_blocks(doc, ana_blocks, indent_cm=0.45)

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


def _pdf_add_blocks(story: List[Any], blocks: List[Block], font: str, *, indent: float = 0.0,
                    body_size: float = 10.5) -> None:
    """把有序块写进 PDF story：文字成段、图片原地插入"""
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
            story.append(Paragraph(_escape_for_rl(payload), style))
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


def export_bank_pdf(bank: Dict[str, Any], questions: List[Dict[str, Any]]) -> bytes:
    """题库 → .pdf 字节"""
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
            parts.append(Paragraph(f"<b>{letter}.</b> {_escape_for_rl(text)}", st_opt))

        for s_idx, sub in enumerate(q.get("subQuestions") or [], start=1):
            parts.append(Paragraph(f"<b>({s_idx})</b>", st_head))
            _pdf_add_blocks(
                parts, split_blocks(sub.get("questionText") or ""), font, indent=0.45, body_size=10
            )
            for letter, text in _option_rows(sub.get("options"), _as_int(sub.get("questionType")) or 1):
                parts.append(Paragraph(f"<b>{letter}.</b> {_escape_for_rl(text)}", st_opt))
            sub_ans = normalize_answer(sub.get("answer"), _as_int(sub.get("questionType")) or 1)
            if sub_ans:
                parts.append(Paragraph(f"<b>答案：</b>{_escape_for_rl(sub_ans)}", st_ans))

        ans = normalize_answer(q.get("answer"), qtype, len(opts))
        if ans:
            parts.append(Paragraph(f"<b>答案：</b>{_escape_for_rl(ans)}", st_ans))

        ana_blocks = split_blocks(q.get("analysis") or q.get("questionAnalysis") or "")
        if ana_blocks:
            st_ana_lbl = ParagraphStyle(
                "al", fontName=font, fontSize=10.5, leading=16.5, leftIndent=0.45 * cm,
                textColor=colors.HexColor("#555555"), spaceBefore=3,
            )
            parts.append(Paragraph("<b>解析：</b>", st_ana_lbl))
            _pdf_add_blocks(parts, ana_blocks, font, indent=0.45)

        parts.append(Paragraph("─" * 34, st_sep))

        # 整题绑定：优先不跨页。但带长解析/大图的题可能**本身就超过一页** ——
        # 那种情况下 KeepTogether 会让 reportlab 反复重排却放不下，
        # 所以 `_keep_together_if_fits` 会先量高度：装得下才绑定，否则逐项展开。
        _keep_together_if_fits(story, parts, doc)

    doc.build(story)
    return buf.getvalue()

