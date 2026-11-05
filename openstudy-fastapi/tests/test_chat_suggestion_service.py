"""新会话提问推测的纯函数测试（不连数据库、不调模型）。"""

from types import SimpleNamespace

from app.services.rag.chat_suggestion_service import STARTER_SUGGESTIONS, _fallback_from_docs


def test_starter_suggestions_are_actionable():
    assert len(STARTER_SUGGESTIONS) == 4
    assert all(item["text"] for item in STARTER_SUGGESTIONS)
    assert any(item["action"] == "upload" for item in STARTER_SUGGESTIONS)


def test_document_fallback_uses_real_file_name():
    suggestions = _fallback_from_docs([SimpleNamespace(file_name="概率论讲义.docx")])
    assert len(suggestions) == 4
    assert any("概率论讲义.docx" in item["text"] for item in suggestions)
