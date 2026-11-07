"""chunk 原文字符区间计算的纯规则测试（不连数据库）。"""

from types import SimpleNamespace

from app.services.rag.rag_write_service import build_chunk_offsets


def test_chunk_offsets_allow_overlap():
    raw = "0123456789abcdefghij"
    chunks = [
        SimpleNamespace(id=11, chunk_index=0, content=raw[0:10]),
        SimpleNamespace(id=12, chunk_index=1, content=raw[6:16]),
        SimpleNamespace(id=13, chunk_index=2, content=raw[12:20]),
    ]
    offsets = build_chunk_offsets(raw, chunks)
    assert [item["start"] for item in offsets] == [0, 6, 12]
    assert [item["end"] for item in offsets] == [10, 16, 20]


def test_chunk_offsets_fallback_to_trimmed_probe():
    raw = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    chunks = [
        SimpleNamespace(id=21, chunk_index=0, content="第一段内容。\n\n第二段内容。"),
        # 历史数据可能有空白差异，但开头 160 字仍能定位。
        SimpleNamespace(id=22, chunk_index=1, content="  第二段内容。  \n\n第三段内容。  "),
    ]
    offsets = build_chunk_offsets(raw, chunks)
    assert offsets[0]["start"] == 0
    assert offsets[1]["start"] is not None
    assert raw[offsets[1]["start"] : offsets[1]["start"] + 5] == "第二段内容"


def test_chunk_offsets_never_fabricate_missing_content():
    raw = "只有这一段。"
    offsets = build_chunk_offsets(
        raw,
        [SimpleNamespace(id=31, chunk_index=0, content="根本不存在的内容")],
    )
    assert offsets == [
        {"chunkId": 31, "chunkIndex": 0, "start": None, "end": None}
    ]
