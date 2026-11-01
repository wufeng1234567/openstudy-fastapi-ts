# -*- coding: utf-8 -*-
"""结构化智能整理回归探针（零网络；直接读取智能整理测试集）。

覆盖：
- 01/02/04/06/08/09 编号升序
- 03 题目 1/2/3/5，答案跟随对应题目
- 04 表格行 1/2/3，公式块数量不变
- 07 第三章回到附录之前，重复标题有剔除建议
- 代码/公式/表格/答案不会被任何剔除建议命中
"""
import os
import re
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.rag import RagDocument  # noqa: E402
from app.services.file_parser import build_marked_document, parse_file  # noqa: E402
from app.services.material_organizer import analyze, build_blocks  # noqa: E402
from app.services.material_structure import apply_layouts, build_structure_plan  # noqa: E402
from app.services.rag.workspace_service import _deep_changes  # noqa: E402

TEST_DIR = os.path.join(os.path.dirname(ROOT), "智能整理测试集", "md")
ROWS = []


def ck(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append((cid, title, cond, actual))
    print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))


def load(name: str):
    path = os.path.join(TEST_DIR, name)
    parsed = parse_file(path, open(path, "rb").read())
    body, images = build_marked_document(parsed)
    doc = RagDocument(
        id=1,
        kb_id=1,
        user_id=1,
        file_name=name,
        raw_content=body,
        content_structure=parsed.get("contentStructure") or [],
        image_map={},
        facets={},
    )
    result = analyze(name, body, parsed, len(images))
    plan = build_structure_plan(body, doc.content_structure)
    changes, suggestions = _deep_changes(doc, result, {}, plan)
    return body, parsed, plan, changes, suggestions


def structure_changes(plan):
    return [item for item in plan.get("changes") or [] if item.get("layout")]


def code_texts(body, structure):
    return [block["text"] for block in build_blocks(body, structure) if block["kind"] == "code"]


def main() -> int:
    # 01：编号 1..10，咖啡图/闲聊/页眉有建议，正常图片不被全删
    body, parsed, plan, changes, suggestions = load("01_智能体基础概念.md")
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    nums = [int(value) for value in re.findall(r"(?m)^(\d{1,3})[ \t]+\S", out)]
    ck("MS-01", "01 编号升序", nums == list(range(1, 11)), str(nums))
    labels = " ".join(item.get("label") or "" for item in suggestions)
    ck("MS-02", "01 保留正常图片建议", "图1" not in labels or "无关" in labels, labels)

    # 02：编号升序，代码逐字不变，无代码删除建议
    body, parsed, plan, changes, suggestions = load("02_接口调用示例.md")
    before_code = code_texts(body, parsed.get("contentStructure"))
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    after_code = code_texts(out, parsed.get("contentStructure"))
    nums = [int(value) for value in re.findall(r"(?m)^(\d{1,3})[ \t]+\S", out)]
    ck("MS-03", "02 编号升序", nums == sorted(nums), str(nums))
    ck("MS-04", "02 代码块逐字不变", before_code == after_code)
    ck("MS-05", "02 没有剔除代码建议", all("代码" not in (item.get("label") or "") for item in suggestions))

    # 03：题目 1/2/3/5，答案跟随
    body, parsed, plan, changes, suggestions = load("03_智能体练习与解析.md")
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    questions = re.findall(r"(?m)^第(\d+)题", out)
    answers = re.findall(r"(?m)^答案：(?:第(\d+)题答案)?\s*([A-D])", out)
    ck("MS-06", "03 题目顺序 1/2/3/5", questions == ["1", "2", "3", "5"], str(questions))
    ck(
        "MS-07",
        "03 答案跟随题目",
        answers == [("1", "C"), ("2", "A"), ("3", "B"), ("5", "A")],
        str(answers),
    )

    # 04：编号升序、表格行升序、公式两份原样保留
    body, parsed, plan, changes, suggestions = load("04_指标与公式.md")
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    nums = [int(value) for value in re.findall(r"(?m)^(\d{1,3})[ \t]+\S", out)]
    rows = [int(value) for value in re.findall(r"(?m)^\|\s*(\d+)\s*\|", out)]
    ck("MS-08", "04 编号升序", nums == list(range(1, 7)), str(nums))
    ck("MS-09", "04 表格行升序", rows == [1, 2, 3], str(rows))
    ck("MS-10", "04 公式块数量不变", out.count("P(a|s)") == 2, str(out.count("P(a|s)")))

    # 06：无围栏代码保护
    body, parsed, plan, changes, suggestions = load("06_纯文本示例.txt")
    before_code = code_texts(body, parsed.get("contentStructure"))
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    after_code = code_texts(out, parsed.get("contentStructure"))
    nums = [int(value) for value in re.findall(r"(?m)^(\d{1,3})[ \t]+\S", out)]
    ck("MS-11", "06 编号升序", nums == list(range(1, 9)), str(nums))
    ck("MS-12", "06 无围栏代码不被改写", before_code == after_code)
    ck("MS-13", "06 没有剔除代码建议", all("代码" not in (item.get("label") or "") for item in suggestions))

    # 07：第三章回到附录之前，重复标题有建议
    body, parsed, plan, changes, suggestions = load("07_课程资料汇编.md")
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    lines = [line for line in out.splitlines() if line.strip()]
    ch3 = next((i for i, line in enumerate(lines) if line.startswith("第三章")), -1)
    appendix = next((i for i, line in enumerate(lines) if line.startswith("附录A")), -1)
    ck("MS-14", "07 第三章在附录之前", 0 <= ch3 < appendix, f"ch3={ch3} appendix={appendix}")
    ck(
        "MS-15",
        "07 重复章节标题有剔除建议",
        any("重复" in (item.get("label") or "") for item in suggestions),
        str([item.get("label") for item in suggestions]),
    )

    # 08：编号升序，API 举例不被当闲聊删除
    body, parsed, plan, changes, suggestions = load("08_资料补充.md")
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    nums = [int(value) for value in re.findall(r"(?m)^(\d{1,3})[ \t]+\S", out)]
    ck("MS-16", "08 编号升序", nums == list(range(1, 11)), str(nums))
    ck(
        "MS-17",
        "08 API 举例不被剔除",
        all("天气" not in (item.get("before") or {}).get("value", "") for item in suggestions if isinstance(item.get("before"), dict)),
    )

    # 09：代码注释仍是代码、公式保留
    body, parsed, plan, changes, suggestions = load("09_代码与公式示例.md")
    before_blocks = build_blocks(body, parsed.get("contentStructure"))
    out = apply_layouts(body, [item["layout"] for item in structure_changes(plan)])
    after_blocks = build_blocks(out, parsed.get("contentStructure"))
    before_code = [block["text"] for block in before_blocks if block["kind"] == "code"]
    after_code = [block["text"] for block in after_blocks if block["kind"] == "code"]
    ck("MS-18", "09 代码块（含答案注释）不变", before_code == after_code)
    ck("MS-19", "09 没有把代码注释当标题", all("# 答案：B" not in block["text"] for block in after_blocks if block["kind"] == "heading"))

    # 全量：剔除建议不能命中代码/公式/表格/答案
    bad = []
    for name in sorted(os.listdir(TEST_DIR)):
        body, parsed, plan, changes, suggestions = load(name)
        blocks = build_blocks(body, parsed.get("contentStructure"))
        for suggestion in suggestions:
            rng = suggestion.get("range") or {}
            hit = next(
                (
                    block
                    for block in blocks
                    if int(block["start"]) == int(rng.get("start", -1))
                    and int(block["end"]) == int(rng.get("end", -1))
                ),
                None,
            )
            if hit and hit.get("kind") in {"code", "formula", "table", "answer"}:
                bad.append((name, hit["kind"], suggestion.get("label")))
    ck("MS-20", "全部文档的剔除建议不命中代码/公式/表格/答案", not bad, str(bad))

    # 21：ZIP 里的 Markdown 相对图片可以解析（临时构造带图 Markdown，
    #     不把图片重新写回公开的 md/ 测试目录）
    test_set = os.path.dirname(TEST_DIR)
    with tempfile.TemporaryDirectory(prefix="openstudy_zip_probe_") as tmp:
        zip_path = os.path.join(tmp, "图文说明.zip")
        asset_dir = os.path.join(test_set, "assets", "images")
        image_names = ["chart_flow.png", "circuit_control.png", "formula_a_over_b.png", "robot_handshake.png"]
        markdown = "\n".join(
            f"![图{index + 1}](../assets/images/{name})"
            for index, name in enumerate(image_names)
        )
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("课程资料/05_图文说明.md", markdown)
            for name in image_names:
                archive.write(
                    os.path.join(asset_dir, name),
                    "assets/images/" + name,
                )
        zipped = parse_file(zip_path, open(zip_path, "rb").read())
        body, urls = build_marked_document(zipped)
        ck(
            "MS-21",
            "ZIP 内 Markdown 相对图片可抽取",
            not zipped.get("error") and len(urls) == 4 and "【图0】" in body,
            f"error={zipped.get('error')} urls={len(urls)}",
        )

    passed = sum(1 for _, _, ok, _ in ROWS if ok)
    print(f"\n共 {len(ROWS)} 项：{passed} 通过；失败 {len(ROWS) - passed}")
    return 0 if passed == len(ROWS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
