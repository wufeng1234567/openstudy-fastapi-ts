"""题目原文锚点的参数归一化测试（不连数据库）。"""

from app.services.ai.agent.tools.question_manage import QuestionManageTool


def test_source_params_camel_and_snake_case():
    tool = QuestionManageTool()
    assert tool._source_params(
        {"sourceDocId": 12, "sourceQuote": "原文一句", "sourceChunkId": 3}
    ) == {"docId": 12, "quote": "原文一句", "chunkId": 3}
    assert tool._source_params(
        {"doc_id": 12, "source_quote": "原文一句", "chunk_id": 3}
    ) == {"docId": 12, "quote": "原文一句", "chunkId": 3}


def test_source_params_empty_means_no_anchor():
    tool = QuestionManageTool()
    assert tool._source_params({}) == {}
    assert tool._source_params({"questionText": "没有来源的题"}) == {}
