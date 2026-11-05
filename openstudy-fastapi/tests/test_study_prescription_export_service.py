"""学习处方导出格式测试（不连数据库、不调用模型）。"""

import io
import zipfile

from app.services.study_prescription_export_service import export_prescription


def _plan():
    return {
        "title": "概率论 · 学习处方",
        "summary": "先读后练，再复测。",
        "days": [
            {
                "day": 1,
                "theme": "随机事件",
                "minutes": 30,
                "tasks": [
                    {
                        "type": "read",
                        "title": "读第一章",
                        "detail": "理解 $P(A)=0.4$ 与 $P(B|A)$",
                        "sectionTitle": "第一章 随机事件",
                        "minutes": 15,
                        "questionCount": 0,
                        "done": True,
                    },
                    {
                        "type": "practice",
                        "title": "做基础题",
                        "detail": "完成 3 道基础题",
                        "sectionTitle": "第一章 随机事件",
                        "minutes": 15,
                        "questionCount": 3,
                        "done": False,
                    },
                ],
            }
        ],
        "checkpoints": ["第7天：复诊一次"],
    }


def test_markdown_export_contains_tasks_and_status():
    body, filename, media = export_prescription(
        doc_name="概率论讲义.docx",
        plan=_plan(),
        fmt="md",
        meta={"goalLabel": "考前冲刺"},
    )
    text = body.decode("utf-8")
    assert filename.endswith(".md")
    assert "概率论 · 学习处方" in text
    assert "第 1 天" in text
    assert "[x]" in text and "[ ]" in text
    assert "复诊节点" in text
    assert media.startswith("text/markdown")


def test_txt_export_is_plain_readable():
    body, filename, media = export_prescription(doc_name="资料.pdf", plan=_plan(), fmt="txt")
    text = body.decode("utf-8")
    assert filename.endswith(".txt")
    assert "学习目标" in text
    assert "已完成" in text
    assert "未完成" in text
    assert media.startswith("text/plain")


def test_docx_and_pdf_export_have_file_signatures():
    docx, _, _ = export_prescription(doc_name="资料.docx", plan=_plan(), fmt="word")
    pdf, _, _ = export_prescription(doc_name="资料.docx", plan=_plan(), fmt="pdf")
    assert docx[:2] == b"PK"
    assert pdf[:5] == b"%PDF-"
    assert len(docx) > 1000
    assert len(pdf) > 1000
    with zipfile.ZipFile(io.BytesIO(docx)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "<m:oMath" in xml
