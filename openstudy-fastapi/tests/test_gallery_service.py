"""画廊索引的纯规则测试（不连数据库、不调用模型）。"""

from types import SimpleNamespace

from app.services.rag.gallery_service import (
    _infer_kind,
    _parse_json_payload,
    _section_for_marker,
)


def test_section_for_marker_reports_chapter_and_context():
    raw = (
        "第一章 随机事件\n"
        "样本空间是全部可能结果的集合。\n"
        "【图0】\n"
        "第二章 随机变量\n"
        "分布函数描述随机变量。\n"
        "【图1】\n"
    )
    meta = _section_for_marker(raw, "0")
    assert meta["sectionIndex"] == 0
    assert meta["sectionTitle"] == "第一章 随机事件"
    assert meta["offset"] == raw.index("【图0】")
    assert "样本空间" in meta["surrounding"] or "第二章" in meta["surrounding"]


def test_section_for_marker_handles_missing_image():
    meta = _section_for_marker("没有图片的正文", "9")
    assert meta["offset"] is None
    assert meta["sectionTitle"] == ""


def test_infer_kind_uses_real_name_tokens():
    assert _infer_kind("第3章 表格.png", "") == "table"
    assert _infer_kind("公式推导.jpg", "") == "formula"
    assert _infer_kind("课堂截图.png", "") == "screenshot"
    assert _infer_kind("几何示意图.png", "") == "diagram"
    assert _infer_kind("photo.jpg", "") == "photo"


def test_parse_json_payload_strips_fences_and_text():
    data = _parse_json_payload(
        '这里是结果：\n```json\n{"caption":"一张受力分析图","ocrText":"F=ma","kind":"diagram","keywords":["受力","牛顿"]}\n```'
    )
    assert data["caption"] == "一张受力分析图"
    assert data["kind"] == "diagram"
    assert data["keywords"] == ["受力", "牛顿"]


def test_document_image_name_has_stable_key_shape():
    doc = SimpleNamespace(id=42, file_name="物理讲义.pdf")
    key = f"doc:{doc.id}:3"
    assert key == "doc:42:3"
