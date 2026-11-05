"""资料装配任务组装的纯规则测试（不连数据库、不调用模型）。"""

from app.services.study_pack_service import MODE_LABELS, build_study_pack_prompt


def _doc():
    return {
        "sections": [
            {"index": 0, "title": "开篇", "start": 0, "end": 4},
            {"index": 1, "title": "第一章 概率空间", "start": 4, "end": 20},
            {"index": 2, "title": "第二章 随机变量", "start": 20, "end": 40},
        ]
    }


def test_study_pack_uses_full_selected_text_not_excerpt():
    raw = "开篇\n第一章 概率空间\n样本空间与事件。\n第二章 随机变量\n随机变量的分布函数。"
    prompt, selected = build_study_pack_prompt(
        doc_name="概率论讲义.docx",
        raw=raw,
        report=_doc(),
        mode="review",
        section_indexes=[1, 2],
        instruction="面向期末复习",
    )
    assert [s["title"] for s in selected] == ["第一章 概率空间", "第二章 随机变量"]
    assert "样本空间与事件" in prompt
    assert "随机变量的分布函数" in prompt
    assert "每节压到 300 字" not in prompt
    assert "面向期末复习" in prompt


def test_study_pack_defaults_to_all_meaningful_sections_and_rejects_empty():
    prompt, selected = build_study_pack_prompt(
        doc_name="讲义.docx",
        raw="开篇\n第一章 概率空间\n样本空间。\n第二章 随机变量\n分布函数。",
        report=_doc(),
        mode="lecture",
    )
    assert [s["title"] for s in selected] == ["第一章 概率空间", "第二章 随机变量"]
    assert MODE_LABELS["lecture"] in prompt

    try:
        build_study_pack_prompt(
            doc_name="空.docx",
            raw="",
            report={"sections": []},
            mode="outline",
        )
    except ValueError as exc:
        assert "没有可装配" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("空章节应被拒绝")
