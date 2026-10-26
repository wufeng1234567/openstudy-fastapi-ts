"""
资料结构树（v3 · D9-10）

## 这个模块解决什么问题

知识库把文档读进来了（`rag_document.raw_content` + 分块 + 向量），
但用户**看不到这份资料的组织结构** —— 只能看到一串分块列表，
或者跟 AI 对话时零散地聊几句。

把一份 30 页的资料拆成 13 个 chunk 之后，"它讲了哪几个主题、层级是怎么分的"
这个信息就丢失了。而这恰好是**复习时最需要的东西**：先看骨架，再填细节。

所以这个模块把原文的标题层级还原成一棵树，前端用 echarts `tree` 画出来。

## 支持哪些标题形态

实测库里 29 份文档，标题标记有三种形态，全部都要认：

| 形态 | 例子 | 出现在 |
|---|---|---|
| Markdown `#` | `### 3. 所有权` | 434（15 个）、448（8 个）、447（7 个） |
| 中文序号 | `一、基本概念` | 417（4 个）、431（8 个）、430（7 个） |
| 数字序号 | `1. 变量的可变性` | 417（111 个）、478（36 个） |

只认一种会导致大量文档画不出树 —— 那样这个功能就没意义。

## 为什么不做成"AI 总结生成大纲"

AI 生成的大纲**不是资料的结构**，是模型的理解结果：
  · 同一份资料两次生成结果不同（不可复现）
  · 可能凭空捏造章节（幻觉）
  · 慢（要跑模型）

而原文标题是**事实**。用户点开结构树想确认"这份资料到底有什么"，
给他一个模型编的骨架是欺骗。所以这里纯规则解析，不经过大模型。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

#: 一棵树的节点上限
#:
#: 超过这个数，前端画出来就是一团糊（实测 40+ 节点在 640px 宽里标签就开始压）。
#: 超限时**保留前两层 + 每层前 N 个**，并在返回值里标记 `truncated`，
#: 让前端能如实告诉用户"只显示了前 X 个"，而不是假装这就是全部。
MAX_NODES = 120

# ────────────────────────────────────────────────────────────
# 标题识别
# ────────────────────────────────────────────────────────────

#: Markdown 标题：`# 标题` / `## 标题`（1-6 级）
_RE_MD_HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

#: 中文序号标题：`一、xxx` / `（一）xxx` / `三. xxx`
_RE_CN_HEAD = re.compile(r"^[（(]?([一二三四五六七八九十]+)[）)]?\s*[、.．]\s*(.+?)\s*$")

#: 数字序号标题：`1. xxx` / `1、xxx` / `1.2 xxx` / `1.2.3 xxx`
_RE_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})[.、．)]?\s+(.+?)\s*$")

#: 明显不是标题的行（代码块围栏、分隔线、表格行）
_RE_NOT_TITLE = re.compile(r"^\s*(```|~~~|[-*_]{3,}|\|)")

#: 题库型文档的题号特征
#:
#: 实测文档 478（概率论复习题）：「1 ［单选题］」「2 ［单选题］」…共 36 条，
#: 全被当成 1 级标题 → 树是平的 36 个兄弟节点，**毫无结构信息**。
#:
#: 这不是"格式怪"，而是**文档性质不同**：题库类文档的编号是「题号」，
#: 不是「章节号」。把它们当章节画出来是错的。
#:
#: 判据：标题里出现题型标记（［单选题］之类）或"第N题"这类措辞。
_RE_EXAM_MARK = re.compile(
    r"［\s*(?:单选题|多选题|判断题|填空题|简答题|问答题|计算题|综合题|论述题|名词解释|选择题|应用题|证明题)\s*］"
    r"|^\d+\s*[.、．]\s*第\s*\d+\s*题"
)


def _clean_heading(text: str) -> str:
    """去掉标题里的 Markdown 行内标记与多余空白"""
    s = (text or "").strip()
    s = re.sub(r"`([^`]*)`", r"\1", s)          # 行内代码
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)    # 粗体
    s = re.sub(r"\*([^*]*)\*", r"\1", s)        # 斜体
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # 链接
    s = re.sub(r"\s+", " ", s).strip()
    return s[:60]


def _extract_headings(text: str) -> List[Dict[str, Any]]:
    """
    从全文提取标题序列

    返回 `[{level, title, line, kind}]`，level 从 1 开始（1 = 最顶层）。

    ── 层级判定（2026-10-26 实测修正）────────────────────────────
    三种标记的天然层级是**不同体系**的，不能直接混用：

      · Markdown `#`  → level = `#` 个数（自带明确层级）
      · 中文序号 `一、` → 天然是顶层（level 1）
      · 数字序号 `1.` → 天然是**下一层**（level 2），`1.1` → 3

    ⚠️ 踩过的坑：最初把 `1.` 也算成 level 1，于是

        一、基本概念
        1. 不可变绑定      ← 本该是"基本概念"的子节点
        2. 可变绑定

    三个都成了兄弟，树是平的、毫无意义。

    所以数字序号的层级 = `1 + 点数`（`1.` → 2，`1.1` → 3），
    这样它天然落在中文序号下面，符合中文技术文档的实际写法。
    """
    if not text:
        return []

    out: List[Dict[str, Any]] = []
    in_fence = False

    for line_no, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip()

        # 代码块内部一律不算标题（里面有 `# 注释` 之类）
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or _RE_NOT_TITLE.match(line):
            continue

        # ① Markdown
        m = _RE_MD_HEAD.match(line)
        if m:
            out.append(
                {
                    "level": len(m.group(1)),
                    "title": _clean_heading(m.group(2)),
                    "line": line_no,
                    "kind": "md",
                }
            )
            continue

        # ② 数字序号：level = 2 + 层级点数
        #
        # ⚠️ 注意 `num` 是**不含结尾点**的捕获（`_RE_NUM_HEAD` 里 `[.、．)]?` 在括号外），
        #    所以 `1.` 捕获到 `"1"`（点数 0）、`1.1` 捕获到 `"1.1"`（点数 1）。
        #    要得到「1. → 2 级、1.1 → 3 级」，公式必须是 `2 + 点数`。
        #    （最初写成 `1 + 点数`，`1.` 就成了 1 级 —— 和中文序号平级，树是平的。）
        m = _RE_NUM_HEAD.match(line)
        if m:
            num, title = m.group(1), _clean_heading(m.group(2))
            # 标题太短（如 "1. 是"）或太长（整段话）都不像标题
            if title and 1 <= len(title) <= 50:
                out.append(
                    {
                        "level": 2 + num.count("."),
                        "title": f"{num} {title}",
                        "line": line_no,
                        "kind": "num",
                    }
                )
                continue

        # ③ 中文序号：顶层
        m = _RE_CN_HEAD.match(line)
        if m:
            title = _clean_heading(m.group(2))
            if title and len(title) <= 50:
                out.append(
                    {
                        "level": 1,
                        "title": title,
                        "line": line_no,
                        "kind": "cn",
                    }
                )
                continue

    # ── 题库型文档：整体剔除题号 ──
    #
    # ⚠️ 只在「题号占绝对多数」时才剔除，不能见一个剔一个 ——
    #    正常教材里偶尔也可能出现"1. 单选题"，但那不该影响整棵树。
    #    阈值 60%：实测文档 478 是 36/36 全题号，文档 431/434 是 0/25，
    #    中间地带（一半题号一半章节）的文档很少，用 60% 足够区分。
    if out:
        exam_cnt = sum(1 for h in out if _RE_EXAM_MARK.search(h["title"]))
        if exam_cnt and exam_cnt / len(out) >= 0.6:
            out = [h for h in out if not _RE_EXAM_MARK.search(h["title"])]

    return out


# ────────────────────────────────────────────────────────────
# 标题序列 → 树
# ────────────────────────────────────────────────────────────


def build_outline_tree(
    raw_text: str,
    *,
    root_name: str = "",
    max_nodes: int = MAX_NODES,
) -> Optional[Dict[str, Any]]:
    """
    把全文标题还原成一棵树

    :return: `{"name":..., "children":[...], "truncated":bool, "count":int}`
             解析不出任何标题时返回 `None`（由调用方决定怎么提示）

    算法：维护一个「层级栈」。遇到 level=L 的标题时，
    弹出所有 level >= L 的栈顶，然后挂到当前栈顶下面。

    这是标准做法，但对**跳级**（1 → 3，中间没有 2）要特别处理：
    跳级时不能硬套层级，否则 3 级标题会被扔掉。
    这里把 level 钳制到「栈顶 + 1」，保证任何标题都能挂上树。
    """
    heads = _extract_headings(raw_text)
    if not heads:
        return None

    root: Dict[str, Any] = {
        "name": _clean_heading(root_name) or "资料结构",
        "children": [],
    }

    # 栈元素：{level, node}
    stack: List[Dict[str, Any]] = [{"level": 0, "node": root}]
    count = 0

    for h in heads:
        lv = h["level"]
        # 钳制：不能比栈顶深超过 1 级（否则父子关系断裂）
        max_allowed = stack[-1]["level"] + 1
        if lv > max_allowed:
            lv = max_allowed

        # 弹出 level >= lv 的
        while len(stack) > 1 and stack[-1]["level"] >= lv:
            stack.pop()

        node = {"name": h["title"], "children": []}
        stack[-1]["node"]["children"].append(node)
        stack.append({"level": lv, "node": node})
        count += 1

        if count >= max_nodes:
            break

    truncated = len(heads) > count

    # 收尾：把没有子节点的 children 删掉（echarts 里空数组不影响，但干净些）
    def prune(n: Dict[str, Any]) -> None:
        if not n.get("children"):
            n.pop("children", None)
        else:
            for c in n["children"]:
                prune(c)

    prune(root)

    if not root.get("children"):
        return None

    # ── 去掉「根节点与唯一子节点同名」的重复层 ──
    #
    # 实测：文档 447/448/434 的第一行就是文档自己的标题（`# C++ 核心知识要点`），
    # 于是树上出现
    #     资料结构
    #       └─ C++ 核心知识要点     ← 和文件名一样，纯冗余
    #            └─ 一、基础与类型
    # 多这一层会让本来就不宽的画布再往里缩一圈，标签更容易挤。
    # 处理：若根只有一个子节点且名字高度相似，把那个子节点**提升为根**。
    while True:
        kids = root.get("children") or []
        if len(kids) != 1:
            break
        only = kids[0]
        # 名字比较：去掉空格/括号后互相包含即视为同一个
        def _norm(s: str) -> str:
            return re.sub(r"[\s（）()【】\[\]·—\-_、,，.。]", "", s or "")

        a, b = _norm(root.get("name") or ""), _norm(only.get("name") or "")
        same = bool(a and b) and (a in b or b in a)
        if not same:
            break
        root = only

    return {
        **root,
        "truncated": truncated,
        "count": count,
        "totalHeadings": len(heads),
    }
