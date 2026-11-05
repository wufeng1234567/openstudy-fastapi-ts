"""学习处方任务与解析的纯规则测试（不连数据库、不调用模型）。"""

import json

from app.services.study_prescription_service import (
    build_prescription_prompt,
    parse_prescription,
)


def _report():
    return {
        "score": 72,
        "grade": {"label": "基本可用"},
        "issues": [{"id": "structure:thin"}],
        "metrics": [],
        "sections": [
            {"index": 0, "title": "开篇", "chars": 80, "questions": 0, "images": 1, "coverageLabel": "内容过薄"},
            {"index": 1, "title": "第一章 概率空间", "chars": 600, "questions": 3, "images": 2, "coverageLabel": "讲解 + 练习"},
            {"index": 2, "title": "第二章 随机变量", "chars": 400, "questions": 1, "images": 1, "coverageLabel": "有讲解，缺练习"},
        ],
    }


def test_prescription_prompt_contains_goal_and_sections():
    prompt, selected = build_prescription_prompt(
        doc_name="概率论讲义.docx",
        report=_report(),
        days=7,
        daily_minutes=30,
        goal="exam",
        section_indexes=[1, 2],
        instruction="考前只看重点",
    )
    assert [s["title"] for s in selected] == ["第一章 概率空间", "第二章 随机变量"]
    assert "7天" in prompt or "7 天" in prompt
    assert "考前冲刺" in prompt
    assert "第一章 概率空间" in prompt
    assert "第二章 随机变量" in prompt
    assert "春节前" not in prompt


def test_parse_prescription_normalizes_and_drops_unknown_sections():
    raw = """
    这里是说明，不应该进入解析。
    {
      "title": "概率论 · 学习处方",
      "summary": "每天推进一点",
      "days": [
        {"day": 1, "theme": "先理解概率空间", "minutes": 25, "tasks": [
          {"type": "read", "title": "读第一节", "detail": "读第一章的样本空间", "sectionIndex": 1, "minutes": 10},
          {"type": "practice", "title": "做基础题", "detail": "做 3 道题", "sectionIndex": 1, "minutes": 15, "questionCount": 3}
        ]},
        {"day": 2, "theme": "进入随机变量", "minutes": 25, "tasks": [
          {"type": "review", "title": "复习", "detail": "回顾昨天的内容", "sectionIndex": 2, "minutes": 10},
          {"type": "read", "title": "非法章节", "detail": "应被丢掉", "sectionIndex": 99, "minutes": 10}
        ]}
      ],
      "checkpoints": ["第1天结束：检查是否读完"]
    }
    """
    plan = parse_prescription(raw, selected_sections=_report()["sections"][1:], days=7)
    assert plan["title"] == "概率论 · 学习处方"
    assert len(plan["days"]) == 2
    assert len(plan["days"][0]["tasks"]) == 2
    assert len(plan["days"][1]["tasks"]) == 1
    assert plan["days"][1]["tasks"][0]["sectionTitle"] == "第二章 随机变量"
    assert plan["checkpoints"] == ["第1天结束：检查是否读完"]


def test_parse_prescription_rejects_empty_plan():
    try:
        parse_prescription('{"days": []}', selected_sections=_report()["sections"][1:], days=7)
    except ValueError as exc:
        assert "没有生成" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("空计划应该被拒绝")


def test_prescription_serialization_keeps_task_types():
    plan = parse_prescription(json.dumps({
        "days": [{"day": 1, "tasks": [{"type": "practice", "sectionIndex": 1, "title": "练习"}]}]
    }), selected_sections=_report()["sections"][1:], days=7)
    assert plan["days"][0]["tasks"][0]["type"] == "practice"
