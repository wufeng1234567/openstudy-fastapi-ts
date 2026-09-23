"""
LLM 输出 JSON 的**清洗与修复**（Agent 工具共用）

模型（尤其被要求吐长 JSON 数组时）几乎必然出现下面几类问题，任何一类都会让
`json.loads` 直接失败，进而让「批量导入题目」这类工具整批报废：

| 问题 | 典型表现 |
|---|---|
| 包了 markdown 围栏 | ```` ```json [ ... ] ``` ```` |
| 字段名后多空格 | `"question ":` |
| LaTeX 反斜杠未转义 | `\\overline{A}` 在 JSON 里是**非法转义**（`\\o` 不在允许集合内） |
| 括号不配对 | 长数组被截断，缺 `]` / `}` |
| 尾随逗号 | `[1,2,]` |
| 混入控制字符 | 复制来的题目里带 `\\u0000`-`\\u001F` |

处理策略（对齐 springboot3 的 `JsonParser` + `QuestionManageTool.collapseBackslashes`）：

    clean → repair → 原样 parse
                  → collapse_backslashes 后 parse      （LaTeX 场景）
                  → 逐对象提取（括号配平扫描）后逐个 parse（截断 / 局部损坏场景）

**宁可只救回一部分题目，也不要整批失败** —— 调用方拿到的是「成功 N 道 / 失败 M 道」
而不是一个空数组。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

#: JSON 里合法的单字符转义（`\uXXXX` 单独判断）
_VALID_ESCAPES = set('"\\/bfnrt')

#: 字段名后误带空格的修复规则：`"key "` → `"key"`
_TRAILING_SPACE_IN_KEY = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)\s+"\s*:')


def clean(content: Optional[str]) -> str:
    """去掉 markdown 围栏、控制字符与**键名尾部空格**

    ⚠️ 键名归一化必须放在这里（而不是只放在 `repair()` 里）：
    `{"questionText ":"Q1"}` 是**合法 JSON**（键名确实带空格），
    `json.loads` 会「解析成功」但拿到的是 `questionText ` 这个键 ——
    于是取值全是空，工具报「缺少 questionText」而模型完全看不出为什么。
    只有先把键名修掉，三套解析策略才都站在同一起跑线上。
    """
    if not content:
        return ""
    text = str(content)
    text = text.replace("```json", "").replace("```JSON", "").replace("```", "")
    # 控制字符（含 BOM）
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\ufeff]", "", text)
    # `"key ":` → `"key":`（值后面不可能是冒号，所以这条替换不会误伤字符串值）
    text = _TRAILING_SPACE_IN_KEY.sub(r'"\1":', text)
    return text.strip()


def collapse_backslashes(raw: str) -> str:
    """把 JSON 字符串里的**非法单反斜杠**加倍，使 `\\overline{A}` 变成合法转义

    逐字符扫描，规则与 springboot3 的实现保持一致：

    - `\\\\`（合法转义，表示一个反斜杠）→ 原样保留
    - `\\"` `\\/` `\\b` `\\f` `\\n` `\\r` `\\t` → 合法，保留
    - `\\uXXXX`（后 4 位是十六进制）→ 合法，保留
    - 其余（`\\o` `\\l` `\\f` 后跟非 hex 等）→ **加倍**成 `\\\\x`

    ⚠️ 只在「原样解析失败」时才调用 —— 对本来就正确的 JSON 做这件事
    会把 `\\n` 之外的序列悄悄改掉，所以调用方必须先试原样解析。
    """
    if not raw:
        return raw
    out: List[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        # 双反斜杠：合法，原样保留
        if i + 1 < n and raw[i + 1] == "\\":
            out.append("\\\\")
            i += 2
            continue

        nxt = raw[i + 1] if i + 1 < n else ""
        if nxt in _VALID_ESCAPES:
            out.append(ch)
            i += 1
        elif nxt == "u":
            # 需要 `\uXXXX` 才是合法转义
            hexpart = raw[i + 2 : i + 6]
            if len(hexpart) == 4 and all(c in "0123456789abcdefABCDEF" for c in hexpart):
                out.append(ch)
                i += 1
            else:
                out.append("\\\\")
                i += 1
        else:
            # 非法转义（\overline / \lambda 之类）：加倍
            out.append("\\\\")
            i += 1
    return "".join(out)


def repair(content: str) -> str:
    """补括号、去尾随逗号、修字段名多余空格（不解析，纯文本层面）"""
    if not content:
        return content
    text = content

    # 0. 去掉模型硬塞进来的思考字段（对我们的 schema 没意义）
    text = re.sub(r'"reasoning_content"\s*:\s*[^,}\]]*[,}]?', "", text)

    # 1. 补全缺失的括号（长数组被截断时最常见）
    open_braces, close_braces = text.count("{"), text.count("}")
    if open_braces > close_braces:
        text += "}" * (open_braces - close_braces)
    open_brackets, close_brackets = text.count("["), text.count("]")
    if open_brackets > close_brackets:
        text += "]" * (open_brackets - close_brackets)

    # 2. 尾随逗号（`,\s*}` / `,\s*]`）
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def ensure_array(content: str) -> str:
    """尽量把内容规整成 JSON 数组字符串（失败时返回 `[]`）"""
    text = clean(content)
    if text.startswith("["):
        return text
    if text.startswith("{"):
        return f"[{text}]"
    start = text.find("[")
    if start == -1:
        start = text.find("{")
    end = text.rfind("]")
    if end == -1:
        end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        extracted = text[start : end + 1]
        return f"[{extracted}]" if extracted.startswith("{") else extracted
    return "[]"


def ensure_object(content: str) -> str:
    """尽量把内容规整成 JSON 对象字符串（失败时返回 `{}`）"""
    text = clean(content)
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return "{}"


def split_top_level_objects(raw: str) -> List[str]:
    """从（可能截断 / 局部损坏的）JSON 文本里按**括号配平**切出每个顶层对象

    只在「整体解析彻底失败」时兜底使用。字符串状态与转义会被正确跳过，
    所以题目正文里出现 `{` `}` `[` `]` 也不会把切分搞乱。

    最后一个对象若括号不闭合（数组被截断），同样会被返回 —— 外层再尝试
    补右括号解析，能救回就救回。
    """
    objects: List[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for idx, ch in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(raw[start : idx + 1])
                    start = -1

    # 尾部残留（被截断的对象）也交出去试试
    if start != -1:
        objects.append(raw[start:])
    return objects


def _loads(text: str) -> Any:
    return json.loads(text)


def parse_json_array(
    content: str, *, raw_first: bool = True
) -> Tuple[List[Dict[str, Any]], List[str], Optional[str]]:
    """把模型输出解析成「对象列表」，带回退链

    Returns:
        (items, warnings, used_strategy)
        - `items`：成功解析出来的对象列表（可能比原文少，但不会因为个别坏对象全丢）
        - `warnings`：逐条说明哪一步失败了，便于回灌给模型 / 排查
        - `used_strategy`：最终生效的策略名；全失败时为 `None`
    """
    warnings: List[str] = []
    source = clean(content)

    strategies = [("原样解析", source)]
    collapsed = collapse_backslashes(source)
    if collapsed != source:
        strategies.append(("反斜杠修复", collapsed))
    repaired = repair(source)
    if repaired != source:
        strategies.append(("括号/逗号修复", repaired))
    # 组合修复：LaTeX 未转义 **且** 被截断/带尾逗号是最常见的「双料」损坏，
    # 单独任一种都救不回来，而逐对象提取虽然也能救、但会丢掉数组层面的结构
    if collapsed != source and repaired != source:
        strategies.append(("反斜杠+括号/逗号修复", repair(collapsed)))

    for label, text in strategies:
        try:
            data = _loads(text)
        except Exception as exc:  # noqa: BLE001 - 任何解析错误都继续试下一种
            warnings.append(f"{label}失败：{exc}")
            continue

        items = _coerce_items(data)
        if items:
            return items, warnings, label
        warnings.append(f"{label}成功但内容为空")

    # 最后手段：逐对象提取
    items: List[Dict[str, Any]] = []
    bad = 0
    for chunk in split_top_level_objects(source):
        for candidate in (chunk, repair(chunk), collapse_backslashes(chunk)):
            try:
                data = _loads(candidate)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, dict):
                items.append(data)
                break
            if isinstance(data, list):
                items.extend(i for i in data if isinstance(i, dict))
                break
        else:
            bad += 1
    if items:
        warnings.append(f"逐对象提取救回 {len(items)} 个对象（丢弃 {bad} 个无法解析的）")
        return items, warnings, "逐对象提取"

    return [], warnings, None


def _coerce_items(data: Any) -> List[Dict[str, Any]]:
    """把解析结果规整成对象列表（容忍「单对象」「对象里包数组」等变体）"""
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        # 常见变形：{"questions": [...]} / {"data": [...]}
        for key in ("questions", "items", "data", "list", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
        return [data]
    return []


__all__ = [
    "clean",
    "collapse_backslashes",
    "repair",
    "ensure_array",
    "ensure_object",
    "split_top_level_objects",
    "parse_json_array",
]
