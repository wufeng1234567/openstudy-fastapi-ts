"""文档体检的纯规则测试（不连数据库、不调用模型）。

覆盖三件事：
  1. `第X章 / 第X节` 能被识别成章节，且章标题不会单独变成「内容过薄」；
  2. 体检分数、问题清单、章节热力字段结构稳定；
  3. 无标题文档会给出「结构」类问题，而不是伪造章节。
"""

from types import SimpleNamespace

from app.services.document_health_service import build_document_health, find_section_for_offset


def _doc(raw: str, *, image_map=None, material_type="讲义", structure=None):
    return SimpleNamespace(
        id=9001,
        file_name="测试讲义.docx",
        raw_content=raw,
        image_map=image_map or {},
        content_structure=structure or [],
        material_type=material_type,
    )


def test_health_report_recognizes_chapter_and_section():
    raw = "\n".join(
        [
            "高中物理 · 力学基础讲义",
            "第一章  运动的描述",
            "1.1  参考系与质点",
            "描述物体的运动，先要选定参考系。研究一辆小车在平直轨道上的运动时，可以以地面为参考系，取轨道方向为正方向。",
            "当物体的形状和大小对研究问题影响很小时，可以把物体看成质点。质点是一种理想化模型。",
            "例题：以地面为参考系判断小车是否运动。",
            "1.2  位移与速度",
            "位移描述位置的变化，是矢量；速度描述位置变化的快慢，等于位移与时间的比值。",
            "第二章  牛顿运动定律",
            "2.1  牛顿第一定律",
            "一切物体总保持匀速直线运动状态或静止状态，直到有外力迫使它改变这种状态为止。惯性是物体保持原有运动状态的性质。",
        ]
    )
    report = build_document_health(_doc(raw))

    assert report["score"] > 0
    assert report["grade"]["label"]
    assert report["stats"]["headingCount"] >= 5
    titles = [s["title"] for s in report["sections"]]
    assert "1.1 参考系与质点" in titles
    assert "2.1 牛顿第一定律" in titles
    # 章节标题不能单独成为「内容过薄」的红色区块
    assert "第一章 运动的描述" not in titles

    first = next(s for s in report["sections"] if s["title"] == "1.1 参考系与质点")
    assert first["coverage"] == "good"
    assert first["chars"] > 40
    assert report["metrics"][0]["key"] == "structure"
    assert report["metrics"][1]["key"] == "image"
    assert report["metrics"][2]["key"] == "coverage"
    assert report["metrics"][3]["key"] == "learnability"


def test_health_report_no_heading_flags_structure_issue():
    raw = "这是一份没有章节标题的资料。\n它只有连续正文，没有标题层级，也没有题目。\n" * 6
    report = build_document_health(_doc(raw))

    assert report["stats"]["headingCount"] == 0
    assert any(i["id"] == "structure:no-heading" for i in report["issues"])
    assert report["sections"][0]["title"] == "全文"


def test_health_report_image_issue_and_section_lookup():
    raw = "【图0】\n第一章 总论\n" + "这里是一段较长的正文，用来充当章节内容。" * 8 + "\n"
    report = build_document_health(_doc(raw, image_map={"0": "/profile/upload/a.png"}))

    assert report["stats"]["imageCount"] == 1
    # 图片位于第一个章节之前，找不到题目/章节归属时应进入问题清单
    assert any(i["id"].startswith("image:") for i in report["issues"])

    section = report["sections"][0]
    found = find_section_for_offset(report["sections"], int(section["start"]))
    assert found is not None
    assert found["title"] == section["title"]
    assert find_section_for_offset(report["sections"], -1) is None
    assert find_section_for_offset(report["sections"], 10**9) is None


def test_health_report_empty_doc_does_not_crash():
    report = build_document_health(_doc(""))

    assert report["score"] >= 0
    assert report["stats"]["sectionCount"] == 1
    assert any(i["id"] == "structure:no-heading" for i in report["issues"])


def test_health_headings_ignore_code_numeric_lines():
    # 代码作业里的 `10  0.6782 0.8139` 不是章节标题；不能把整篇切成上百个红块。
    raw = "\n".join(
        [f"{i}  {i * 0.1:.4f} {i * 0.2:.4f}" for i in range(1, 40)]
        + ["第一章 总论", "1.1 基本概念", "这是一段正文。" * 30]
    )
    report = build_document_health(_doc(raw))

    assert report["stats"]["headingCount"] < 10
    assert report["stats"]["sectionCount"] < 10


def test_health_orphan_image_is_reported():
    raw = "第一章 总论\n" + "正文内容。" * 50
    report = build_document_health(_doc(raw, image_map={"0": "/profile/upload/a.png"}))
    assert any(i["id"] == "image:orphan" for i in report["issues"])
    assert report["metrics"][1]["score"] < 100
