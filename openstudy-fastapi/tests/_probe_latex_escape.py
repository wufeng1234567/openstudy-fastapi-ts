"""LaTeX 过度转义修复回归（2026-10-28）

用户实测：题库导入后 `\overline{A}` 显示成单独一行的 `overlineA`，
`\sim` / `\lambda` / `\cup` 也同样变成裸单词。

根因：模型在 `questions` 的 JSON 字符串里多转义了一层反斜杠，
数据入库后是 `\\overline`（两个反斜杠）；KaTeX 把 `\\` 解释成换行，
后面的 `overline` 自然就成了普通文字。渲染层没有错，错的是数据。

本探针锁死三件事：
  1) `normalize_latex_escapes` 能收回一层，但不碰矩阵换行 `\\`；
  2) `question_manage._parse_questions` 在预览/导入共用的入口上真的清洗；
  3) 选项、答案、解析、子题都能被清洗。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai.agent.json_repair import normalize_latex_escapes
from app.services.ai.agent.tools.question_manage import QuestionManageTool

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  OK   {name}" + (f"  {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f"  {detail}" if detail else ""))


def main():
    bs1 = chr(92)
    bs2 = bs1 * 2
    bs4 = bs1 * 4

    # 1) 直接清洗：常见符号
    check("overline 收一层", normalize_latex_escapes(f"$P({bs2}overline{{A}})$") == f"$P({bs1}overline{{A}})$")
    check("sim 收一层", normalize_latex_escapes(f"$X{bs2}sim P({bs2}lambda)$") == f"$X{bs1}sim P({bs1}lambda)$")
    check("cup/subset 收一层", normalize_latex_escapes(f"$A{bs2}cup B{bs2}subset C$") == f"$A{bs1}cup B{bs1}subset C$")
    check("le 收一层", normalize_latex_escapes(f"$x{bs2}le1$") == f"$x{bs1}le1$")
    check("间距逗号收一层", normalize_latex_escapes(f"$2A{bs2},dx$") == f"$2A{bs1},dx$")
    check("百分号收一层", normalize_latex_escapes(f"$4.8{bs2}%$") == f"$4.8{bs1}%$")
    check("矩阵换行 \\\\ 不被误伤", normalize_latex_escapes(f"$\\begin{{matrix}}a&b{bs2}c&d\\end{{matrix}}$") == f"$\\begin{{matrix}}a&b{bs2}c&d\\end{{matrix}}$")
    check("幂等：再洗一次不变", normalize_latex_escapes(normalize_latex_escapes(f"${bs2}frac{{a}}{{b}}$")) == f"${bs1}frac{{a}}{{b}}$")
    from app.services.ai.agent.json_repair import normalize_overline_spacing
    check(
        "相邻 overline 自动补细空格",
        normalize_overline_spacing(f"$P({bs1}overline{{A}}{bs1}overline{{B}})$")
        == f"$P({bs1}overline{{A}}{bs1},{bs1}overline{{B}})$",
    )
    check(
        "单个 overline{AB} 不被拆开",
        normalize_overline_spacing(f"$P({bs1}overline{{AB}})$") == f"$P({bs1}overline{{AB}})$",
    )

    # 2) 批量导入入口：模拟模型传进来的 4 个反斜杠（Python 字符串实际值）
    raw = (
        '[{"questionType":1,"questionText":"$P(' + bs4 + 'overline{A})$",'
        '"options":["$' + bs4 + 'lambda$","B"],'
        '"answer":"$' + bs4 + 'frac12$",'
        '"analysis":"$' + bs4 + 'sim$",'
        '"subQuestions":[{"questionText":"$' + bs4 + 'cup$"}]}]'
    )
    items, warnings, strategy = QuestionManageTool._parse_questions({"questions": raw})
    check("批量导入解析出 1 题", len(items) == 1, f"{len(items)} 题 / {strategy}")
    if items:
        q = items[0]
        check("题干收为一层", q.get("questionText") == f"$P({bs1}overline{{A}})$", repr(q.get("questionText")))
        check("选项收为一层", (q.get("options") or [""])[0] == f"${bs1}lambda$", repr(q.get("options")))
        check("答案收为一层", q.get("answer") == f"${bs1}frac12$", repr(q.get("answer")))
        check("解析收为一层", q.get("analysis") == f"${bs1}sim$", repr(q.get("analysis")))
        sub = (q.get("subQuestions") or [{}])[0]
        check("子题收为一层", sub.get("questionText") == f"${bs1}cup$", repr(sub.get("questionText")))
        draft = QuestionManageTool._build_import_draft(None, {"bank_name": "测试"}, items)
        check(
            "导入预览草稿也用清洗后的题干",
            (draft.get("questions") or [{}])[0].get("questionText") == f"$P({bs1}overline{{A}})$",
            repr((draft.get("questions") or [{}])[0].get("questionText")),
        )
    check("没有把题目丢掉", len(items) == 1 and not warnings, str(warnings[-1:]))

    print()
    print(f"结果：{PASS} / {PASS + FAIL} 项通过")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
