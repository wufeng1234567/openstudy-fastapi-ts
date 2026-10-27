"""
文档对比与表格整理服务（2026-10-27）

============================================================================
它解决什么
============================================================================

用户需求原话：

    「需要迭代的 方向有 表格整理功能 比如 用户向智能体提问
      我这里有两份文件 很混乱 或者 说 有什么区别
      需要智能体可以梳理 并且清晰的指点出来」

真实场景是这几种：

  ① 用户有两版合同/方案，想知道"改了哪几处"
  ② 用户有一份自己维护的表格和一份同事发的，想知道"数字差在哪"
  ③ 用户有一堆散乱的数据，想"整理成一张能看的表"

这三件事的共同点：**用户要的不是"两份原文"，而是差异结论**。
把两份文件都丢给模型让它"自己看"是不可靠的 ——
长文档里最容易漏的就是"少了一行"、"某个数字从 3.5 变成 3.6"。

所以要先把差异**结构化地算出来**（本模块），再让模型基于结论做解释。

============================================================================
为什么不直接用 difflib 了事
============================================================================

`difflib` 给的是**字符/行级**差异，对"两份 Word 文档"不够：

    · Word 里换行位置经常不同，逐行 diff 会把整段都标成"变了"
    · 中文没有空格分词，字符级 diff 会碎成一地
    · **表格**是最需要精确对比的地方，逐行 diff 完全看不出"第 3 行第 2 列变了"

所以分三层：

    ① 结构层：标题/段落/表格/列表 的数量与内容对比
    ② 表格层：按"关键列"对齐，逐格比出"新增行 / 删除行 / 单元格变化"
    ③ 文本层：段落级 diff（先做段落归一化，再比）

============================================================================
表格对比的关键设计：怎么"对齐"两行
============================================================================

两张表要逐格比，必须先知道"哪一行对应哪一行"。

朴素做法（按行号对齐）在插入一行后就全错位：

    表 A: 苹果 10 / 香蕉 20 / 橘子 30
    表 B: 苹果 10 / 西瓜 15 / 香蕉 20 / 橘子 30     ← 插入一行，后面全错位

正确做法：**用第一列（或最像"键"的那一列）做行标识**。

本模块的 `align_rows()`：
  · 优先用第 1 列作为键（中文表格里第 1 列几乎总是名称/编号）
  · 若第 1 列重复严重（>40% 重复），改用"整行拼接"做键
  · 对不上的行 → 分别记为"新增 / 删除"

这样上面那个例子能正确得出：
    新增行：西瓜 15
    其余行：无变化
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 公共入口
# ============================================================

def compare_documents(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    left_name: str = "文件 A",
    right_name: str = "文件 B",
) -> Dict[str, Any]:
    """对比两份已解析的文档

    Args:
        left / right: `file_parser.parse_file()` 的返回，或
                      `{"blocks": [...], "textContent": "..."}` 形式的等价结构
        left_name / right_name: 显示名（用户在对话里说的文件名）

    Returns:
        {
          "summary": {...},           # 一句话结论 + 数量统计
          "structure": {...},         # 结构层差异
          "tables": [...],            # 每个表的逐格差异
          "text": {...},              # 段落级差异
          "markdown": "..."           # 可直接塞进文档导出的 Markdown 版对比报告
        }
    """
    L = _blocks(left)
    R = _blocks(right)

    structure = _compare_structure(L, R)
    table_diffs = _compare_tables(L, R)
    text_diff = _compare_text(L, R)

    summary = _build_summary(structure, table_diffs, text_diff, left_name, right_name)
    markdown = _build_markdown(summary, structure, table_diffs, text_diff, left_name, right_name)

    return {
        "summary": summary,
        "structure": structure,
        "tables": table_diffs,
        "text": text_diff,
        "markdown": markdown,
        "leftName": left_name,
        "rightName": right_name,
    }


def tidy_table(
    table: Dict[str, Any],
    *,
    fill_forward: bool = True,
    strip_whitespace: bool = True,
    drop_empty_rows: bool = True,
    merge_duplicate_headers: bool = True,
) -> Dict[str, Any]:
    """整理一张混乱的表格

    "混乱"的典型形态（都是从真实数据里见的）：

      · 合并单元格被拆开后，第 1 列一堆空格（其实是"同上"）
      · 表头重复出现（从 PDF 多页复制）
      · 单元格里前后空格不一致
      · 整行全空
      · 表头里有重名列

    返回整理后的表 + 做了哪些改动的说明（让用户知道我们动了什么）。
    """
    headers = [str(h) for h in (table.get("headers") or [])]
    rows = [[str(c) for c in r] for r in (table.get("rows") or [])]
    changes: List[str] = []

    if strip_whitespace:
        before = [c for r in rows for c in r]
        headers = [h.strip() for h in headers]
        rows = [[c.strip() for c in r] for r in rows]
        changed = sum(
            1 for a, b in zip(before, [c for r in rows for c in r]) if a != b
        )
        if changed:
            changes.append(f"清理了 {changed} 处多余空格")

    if drop_empty_rows:
        keep = [r for r in rows if any(c for c in r)]
        dropped = len(rows) - len(keep)
        if dropped:
            changes.append(f"删除了 {dropped} 个空行")
        rows = keep

    if fill_forward and rows:
        # 第 1 列为空 → 用上一行的值填（合并单元格拆开后的典型残留）
        filled = 0
        last = ""
        for r in rows:
            if r and not r[0]:
                r[0] = last
                filled += 1
            elif r:
                last = r[0]
        if filled:
            changes.append(f"用上一行的值填补了 {filled} 个空的首列单元格（合并单元格残留）")

    if merge_duplicate_headers and headers:
        seen: Dict[str, int] = {}
        for i, h in enumerate(headers):
            if not h:
                headers[i] = f"列{i + 1}"
                continue
            if h in seen:
                seen[h] += 1
                headers[i] = f"{h}_{seen[h]}"
            else:
                seen[h] = 1
        dup = sum(1 for k, v in seen.items() if v > 1)
        if dup:
            changes.append(f"为 {dup} 个重名列加了编号后缀")

    width = max(len(headers), max((len(r) for r in rows), default=0))
    if width:
        headers = headers + [f"列{i + 1}" for i in range(len(headers), width)]
        rows = [r + [""] * (width - len(r)) for r in rows]
        for r in rows:
            for i, c in enumerate(r):
                if not c:
                    continue

    return {
        "table": {"headers": headers, "rows": rows, "align": ["left"] * width},
        "changes": changes,
        "changeCount": len(changes),
    }


def tables_to_markdown(tables: List[Dict[str, Any]]) -> str:
    """把多张表拼成一份 Markdown（用户说"整理成一张表"时用）"""
    out: List[str] = []
    for idx, t in enumerate(tables or [], 1):
        headers = t.get("headers") or []
        rows = t.get("rows") or []
        if not headers and not rows:
            continue
        out.append(f"## 表 {idx}")
        out.append("")
        width = max(len(headers), max((len(r) for r in rows), default=0))
        headers = list(headers) + [""] * (width - len(headers))
        out.append("| " + " | ".join(_md_cell(h) for h in headers) + " |")
        out.append("|" + "|".join(["---"] * width) + "|")
        for r in rows:
            r = list(r) + [""] * (width - len(r))
            out.append("| " + " | ".join(_md_cell(c) for c in r) + " |")
        out.append("")
    return "\n".join(out)


# ============================================================
# 内部：块提取
# ============================================================

def _blocks(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """取出 blocks；没有就用 textContent 现造一个"""
    bs = doc.get("blocks")
    if isinstance(bs, list) and bs:
        return [b for b in bs if isinstance(b, dict)]
    text = doc.get("textContent") or ""
    return [{"type": "text", "content": text}] if text else []


def _block_text(b: Dict[str, Any]) -> str:
    return (b.get("content") or b.get("text") or "").strip()


def _block_type(b: Dict[str, Any]) -> str:
    t = str(b.get("type") or "text")
    return t if t in ("text", "table", "image") else "text"


# ============================================================
# 内部：结构对比
# ============================================================

def _compare_structure(L: List[Dict[str, Any]], R: List[Dict[str, Any]]) -> Dict[str, Any]:
    """比标题（# 开头）与各类块的数量"""
    l_heads = _extract_headings(L)
    r_heads = _extract_headings(R)

    counts = {
        "left": _count_types(L),
        "right": _count_types(R),
    }

    only_left = [h for h in l_heads if h not in r_heads]
    only_right = [h for h in r_heads if h not in l_heads]

    return {
        "headings": {
            "left": l_heads,
            "right": r_heads,
            "onlyLeft": only_left[:40],
            "onlyRight": only_right[:40],
            "onlyLeftCount": len(only_left),
            "onlyRightCount": len(only_right),
        },
        "counts": counts,
    }


def _extract_headings(blocks: List[Dict[str, Any]]) -> List[str]:
    """抽标题：Markdown 的 `#`，以及短且独占一行的文本（启发式）"""
    out: List[str] = []
    for b in blocks:
        if _block_type(b) != "text":
            continue
        for line in _block_text(b).split("\n"):
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^(#{1,6})\s+(.+)$", s)
            if m:
                out.append(m.group(2).strip())
    return out


def _count_types(blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    c = {"text": 0, "table": 0, "image": 0}
    for b in blocks:
        c[_block_type(b)] = c.get(_block_type(b), 0) + 1
    return c


# ============================================================
# 内部：表格对比
# ============================================================

def _compare_tables(L: List[Dict[str, Any]], R: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把所有表格两两配对比较

    配对策略：先按顺序配。数量不等时多出来的记为"只在某侧存在"。
    （真实场景里两份文档的表格数量通常一致或只差一两个）
    """
    lt = [_tbl(b) for b in L if _block_type(b) == "table"]
    rt = [_tbl(b) for b in R if _block_type(b) == "table"]
    lt = [t for t in lt if t]
    rt = [t for t in rt if t]

    results: List[Dict[str, Any]] = []
    for i in range(max(len(lt), len(rt))):
        a = lt[i] if i < len(lt) else None
        b = rt[i] if i < len(rt) else None

        if a and b:
            results.append({"index": i + 1, "kind": "pair", "diff": _diff_table(a, b)})
        elif a:
            results.append({
                "index": i + 1, "kind": "leftOnly",
                "note": f"第 {i + 1} 张表只在前一份里存在（{len(a['rows'])} 行）",
                "headers": a["headers"],
            })
        else:
            results.append({
                "index": i + 1, "kind": "rightOnly",
                "note": f"第 {i + 1} 张表只在后一份里存在（{len(b['rows'])} 行）",
                "headers": b["headers"],
            })
    return results


def _tbl(b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    headers = b.get("headers")
    rows = b.get("rows")
    if not isinstance(headers, list) and not isinstance(rows, list):
        # 尝试从 markdown 内容里现解一张表
        md = _block_text(b)
        parsed = _parse_md_table(md)
        return parsed
    return {
        "headers": [str(h) for h in (headers or [])],
        "rows": [[str(c) for c in r] for r in (rows or [])],
    }


def _parse_md_table(text: str) -> Optional[Dict[str, Any]]:
    """从文本里解一张 Markdown 表（表格块没带结构化字段时的兜底）"""
    lines = [ln for ln in (text or "").split("\n") if ln.strip().startswith("|")]
    if len(lines) < 2:
        return None
    rows = []
    for ln in lines:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    if not rows:
        return None
    return {"headers": rows[0], "rows": rows[1:]}


def _diff_table(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """两张表逐格对比"""
    lh, rh = a["headers"], b["headers"]
    lr, rr = a["rows"], b["rows"]

    header_changed = lh != rh
    col_diff: List[Dict[str, Any]] = []
    if header_changed:
        width = max(len(lh), len(rh))
        for i in range(width):
            l = lh[i] if i < len(lh) else ""
            r = rh[i] if i < len(rh) else ""
            if l != r:
                col_diff.append({"col": i + 1, "left": l, "right": r})

    added, removed, changed = align_rows(lr, rr)

    return {
        "rowCount": {"left": len(lr), "right": len(rr)},
        "headerChanged": header_changed,
        "columnChanges": col_diff,
        "added": added,
        "removed": removed,
        "changed": changed,
        "changedCount": len(changed),
        "addedCount": len(added),
        "removedCount": len(removed),
        "identical": not header_changed and not added and not removed and not changed,
    }


def align_rows(
    left_rows: List[List[str]],
    right_rows: List[List[str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按"行键"对齐两组行，返回 (新增, 删除, 单元格变化)

    行键的选择（见模块顶部说明）：
      ① 默认用第 1 列
      ② 若第 1 列重复率 > 40%，改用整行拼接
      ③ 仍冲突就带序号后缀

    ⚠️ 为什么不用 `difflib.SequenceMatcher` 对整行做序列比对：
       插入一行会让它把后面所有行都标成"改变"，
       而用户想知道的是"就多了一行西瓜"，不是"后面 10 行都变了"。
    """
    lkey = _row_keys(left_rows)
    rkey = _row_keys(right_rows)

    lmap = {k: r for k, r in zip(lkey, left_rows)}
    rmap = {k: r for k, r in zip(rkey, right_rows)}

    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []

    for k, r in rmap.items():
        if k not in lmap:
            added.append({"key": k, "row": r})

    for k, r in lmap.items():
        if k not in rmap:
            removed.append({"key": k, "row": r})
            continue
        cells = _diff_cells(r, rmap[k])
        if cells:
            changed.append({"key": k, "left": r, "right": rmap[k], "cells": cells})

    return added, removed, changed


def _row_keys(rows: List[List[str]]) -> List[str]:
    """为一组行生成唯一键"""
    if not rows:
        return []

    first = [r[0] if r else "" for r in rows]
    non_empty = [f for f in first if f]
    dup_ratio = 0.0
    if non_empty:
        dup_ratio = 1 - len(set(non_empty)) / len(non_empty)

    # 第 1 列重复太多 → 用整行
    use_whole = dup_ratio > 0.4

    keys: List[str] = []
    seen: Dict[str, int] = {}
    for r in rows:
        base = " | ".join(r) if use_whole else (r[0] if r else "")
        base = base.strip()
        if not base:
            base = " | ".join(r).strip() or "(空行)"
        if base in seen:
            seen[base] += 1
            base = f"{base}#{seen[base]}"
        else:
            seen[base] = 1
        keys.append(base)
    return keys


def _diff_cells(l: List[str], r: List[str]) -> List[Dict[str, Any]]:
    """比较两行的每一格"""
    out: List[Dict[str, Any]] = []
    width = max(len(l), len(r))
    for i in range(width):
        lv = l[i] if i < len(l) else ""
        rv = r[i] if i < len(r) else ""
        if lv != rv:
            out.append({"col": i + 1, "left": lv, "right": rv})
    return out


# ============================================================
# 内部：文本对比
# ============================================================

def _compare_text(L: List[Dict[str, Any]], R: List[Dict[str, Any]]) -> Dict[str, Any]:
    """段落级对比

    先把两侧的文本块合成段落列表（按空行切），
    再用 SequenceMatcher 找"整段新增 / 删除 / 修改"。

    ⚠️ 不做字符级 diff：中文没有空格，字符级结果碎成一地，
       用户在对话里读不下去。段级 + 提示"这一段变了"更实用。
    """
    lp = _paragraphs(L)
    rp = _paragraphs(R)

    sm = difflib.SequenceMatcher(None, lp, rp, autojunk=False)
    added: List[str] = []
    removed: List[str] = []
    modified: List[Dict[str, Any]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            added.extend(rp[j1:j2])
        elif tag == "delete":
            removed.extend(lp[i1:i2])
        elif tag == "replace":
            # 长度相同的替换对，逐对当"修改"；否则分开算增删
            left_seg = lp[i1:i2]
            right_seg = rp[j1:j2]
            for k in range(min(len(left_seg), len(right_seg))):
                modified.append({
                    "left": left_seg[k],
                    "right": right_seg[k],
                    "similarity": round(
                        difflib.SequenceMatcher(None, left_seg[k], right_seg[k]).ratio(), 2
                    ),
                })
            if len(left_seg) > len(right_seg):
                removed.extend(left_seg[len(right_seg):])
            elif len(right_seg) > len(left_seg):
                added.extend(right_seg[len(left_seg):])

    return {
        "paragraphCount": {"left": len(lp), "right": len(rp)},
        "added": added[:40],
        "removed": removed[:40],
        "modified": modified[:40],
        "addedCount": len(added),
        "removedCount": len(removed),
        "modifiedCount": len(modified),
    }


def _paragraphs(blocks: List[Dict[str, Any]]) -> List[str]:
    """文本块 → 段落列表（按空行切，去重空段）"""
    out: List[str] = []
    for b in blocks:
        if _block_type(b) != "text":
            continue
        text = _block_text(b)
        for para in re.split(r"\n\s*\n", text):
            p = para.strip()
            if p:
                # 标题也当作独立段落参与对比（"改了个标题"是最常见的差异）
                out.append(p)
    return out


# ============================================================
# 内部：结论与报告
# ============================================================

def _build_summary(
    structure: Dict[str, Any],
    tables: List[Dict[str, Any]],
    text: Dict[str, Any],
    left_name: str,
    right_name: str,
) -> Dict[str, Any]:
    t_add = sum(t.get("diff", {}).get("addedCount", 0) for t in tables if t.get("kind") == "pair")
    t_rem = sum(t.get("diff", {}).get("removedCount", 0) for t in tables if t.get("kind") == "pair")
    t_chg = sum(t.get("diff", {}).get("changedCount", 0) for t in tables if t.get("kind") == "pair")

    head_ol = structure["headings"]["onlyLeftCount"]
    head_or = structure["headings"]["onlyRightCount"]

    total = (
        t_add + t_rem + t_chg
        + text["addedCount"] + text["removedCount"] + text["modifiedCount"]
        + head_ol + head_or
    )

    if total == 0:
        verdict = "两份文档内容基本一致，未发现实质差异。"
    else:
        bits = []
        if text["modifiedCount"]:
            bits.append(f"{text['modifiedCount']} 段内容被改动")
        if text["addedCount"]:
            bits.append(f"{text['addedCount']} 段新增")
        if text["removedCount"]:
            bits.append(f"{text['removedCount']} 段删除")
        if t_add:
            bits.append(f"表格新增 {t_add} 行")
        if t_rem:
            bits.append(f"表格删除 {t_rem} 行")
        if t_chg:
            bits.append(f"{t_chg} 个表格单元格数值变化")
        if head_or:
            bits.append(f"{head_or} 个标题只出现在后一份")
        if head_ol:
            bits.append(f"{head_ol} 个标题只出现在前一份")
        verdict = "；".join(bits) + "。"

    return {
        "verdict": verdict,
        "diffCount": total,
        "textChanged": text["modifiedCount"],
        "textAdded": text["addedCount"],
        "textRemoved": text["removedCount"],
        "tableRowsAdded": t_add,
        "tableRowsRemoved": t_rem,
        "tableCellsChanged": t_chg,
        "headingsOnlyLeft": head_ol,
        "headingsOnlyRight": head_or,
        "leftName": left_name,
        "rightName": right_name,
    }


def _build_markdown(
    summary: Dict[str, Any],
    structure: Dict[str, Any],
    tables: List[Dict[str, Any]],
    text: Dict[str, Any],
    left_name: str,
    right_name: str,
) -> str:
    """生成可直接导出的对比报告（Markdown）

    用户说"帮我出一份对比报告"时，这份 Markdown 直接进文档编排引擎出 Word。
    """
    L: List[str] = []
    L.append(f"# 文档对比报告：{left_name} vs {right_name}")
    L.append("")
    L.append("## 一、总体结论")
    L.append("")
    L.append(summary["verdict"])
    L.append("")
    L.append(f"- 差异总数：**{summary['diffCount']}**")
    L.append(f"- 段落修改：{summary['textChanged']} ｜ 新增：{summary['textAdded']} ｜ 删除：{summary['textRemoved']}")
    L.append(
        f"- 表格：新增 {summary['tableRowsAdded']} 行 ｜ 删除 {summary['tableRowsRemoved']} 行 ｜ "
        f"数值变化 {summary['tableCellsChanged']} 处"
    )
    L.append("")

    # ── 表格差异 ──
    pair_tables = [t for t in tables if t.get("kind") == "pair"]
    if pair_tables:
        L.append("## 二、表格差异")
        L.append("")
        for t in pair_tables:
            d = t["diff"]
            L.append(f"### 表 {t['index']}")
            L.append("")
            if d["identical"]:
                L.append("完全一致。")
                L.append("")
                continue

            if d["headerChanged"]:
                L.append("**表头有变化：**")
                L.append("")
                L.append("| 列 | 前一份 | 后一份 |")
                L.append("|----|--------|--------|")
                for c in d["columnChanges"][:12]:
                    L.append(f"| 第 {c['col']} 列 | {_md_cell(c['left'])} | {_md_cell(c['right'])} |")
                L.append("")

            if d["added"]:
                L.append(f"**新增 {d['addedCount']} 行：**")
                L.append("")
                L.append("| 行标识 | 内容 |")
                L.append("|--------|------|")
                for a in d["added"][:15]:
                    L.append(f"| {_md_cell(a['key'])} | {_md_cell(' ｜ '.join(a['row']))} |")
                L.append("")

            if d["removed"]:
                L.append(f"**删除 {d['removedCount']} 行：**")
                L.append("")
                L.append("| 行标识 | 原内容 |")
                L.append("|--------|--------|")
                for a in d["removed"][:15]:
                    L.append(f"| {_md_cell(a['key'])} | {_md_cell(' ｜ '.join(a['row']))} |")
                L.append("")

            if d["changed"]:
                L.append(f"**{d['changedCount']} 行的单元格发生变化：**")
                L.append("")
                L.append("| 行标识 | 列 | 前一份 | 后一份 |")
                L.append("|--------|----|--------|--------|")
                for c in d["changed"][:20]:
                    for cell in c["cells"][:4]:
                        L.append(
                            f"| {_md_cell(c['key'])} | 第 {cell['col']} 列 | "
                            f"{_md_cell(cell['left'])} | {_md_cell(cell['right'])} |"
                        )
                L.append("")

    # ── 标题差异 ──
    h = structure["headings"]
    if h["onlyLeftCount"] or h["onlyRightCount"]:
        L.append("## 三、标题差异")
        L.append("")
        if h["onlyLeftCount"]:
            L.append(f"**只在前一份（{len(h['onlyLeft'])} 个）：**")
            L.append("")
            for x in h["onlyLeft"]:
                L.append(f"- {x}")
            L.append("")
        if h["onlyRightCount"]:
            L.append(f"**只在后一份（{len(h['onlyRight'])} 个）：**")
            L.append("")
            for x in h["onlyRight"]:
                L.append(f"- {x}")
            L.append("")

    # ── 正文差异 ──
    if text["modifiedCount"] or text["addedCount"] or text["removedCount"]:
        L.append("## 四、正文差异")
        L.append("")
        if text["modified"]:
            L.append(f"### 被修改的段落（{text['modifiedCount']} 处）")
            L.append("")
            for i, m in enumerate(text["modified"][:12], 1):
                L.append(f"**{i}. （相似度 {int(m['similarity'] * 100)}%）**")
                L.append("")
                L.append(f"> 前：{_md_cell(_truncate(m['left'], 160))}")
                L.append(">")
                L.append(f"> 后：{_md_cell(_truncate(m['right'], 160))}")
                L.append("")
        if text["added"]:
            L.append(f"### 新增段落（{text['addedCount']} 段）")
            L.append("")
            for x in text["added"][:10]:
                L.append(f"- {_md_cell(_truncate(x, 160))}")
            L.append("")
        if text["removed"]:
            L.append(f"### 删除段落（{text['removedCount']} 段）")
            L.append("")
            for x in text["removed"][:10]:
                L.append(f"- {_md_cell(_truncate(x, 160))}")
            L.append("")

    L.append("---")
    L.append("")
    L.append("*本报告由文档对比工具自动生成，差异按段落与表格单元格粒度计算。*")

    return "\n".join(L)


def _md_cell(s: Any) -> str:
    """清理成表格单元格安全的内容"""
    t = str(s or "").replace("|", "／").replace("\n", " ").strip()
    return t


def _truncate(s: str, n: int) -> str:
    t = (s or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"
