"""知识图谱纯函数测试：不连数据库，不调用模型。"""

from app.services.rag.knowledge_graph_service import _canonical_key, _norm_name, _parse_json_payload


def test_normalize_entity_name_strips_spacing_and_quotes():
    assert _norm_name(" 《随机变量》 ") == "随机变量"
    assert _norm_name("LLM  智能体") == "llm智能体"
    assert _norm_name("随机 变量") == "随机变量"


def test_parse_json_payload_accepts_fenced_json():
    payload = _parse_json_payload(
        """```json
        {"entities":[{"name":"随机变量","type":"概念"}],"relations":[]}
        ```"""
    )
    assert payload["entities"][0]["name"] == "随机变量"


def test_parse_json_payload_accepts_bare_array():
    payload = _parse_json_payload('[{"name":"贝叶斯公式","type":"定理/公式"}]')
    assert payload["entities"][0]["type"] == "定理/公式"


def test_canonical_key_merges_explanatory_suffix_aliases():
    assert _canonical_key("智能体定义") == _canonical_key("智能体")
    assert _canonical_key("贝叶斯公式概念") == _canonical_key("贝叶斯公式")
    assert _canonical_key("函数图像") != _canonical_key("函数")
