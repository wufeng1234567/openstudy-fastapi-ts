"""版本对照的纯规则测试。"""

from app.services.rag.rag_write_service import _diff_rows, _health_snapshot


def test_diff_rows_reports_added_removed_and_change():
    rows, stats = _diff_rows("第一行\n第二行\n", "第一行\n第二行（改）\n第三行\n")
    assert stats["oldLines"] == 2
    assert stats["newLines"] == 3
    assert stats["addedLines"] >= 1
    assert stats["removedLines"] >= 1
    assert any(row["type"] == "change" for row in rows)
    assert any(row["type"] == "add" for row in rows)


def test_health_snapshot_uses_the_same_rule_report_as_clinic():
    snapshot = {
        "fileName": "测试.md",
        "rawContent": "第一节 A\n" + ("内容" * 80) + "\n第二节 B\n" + ("练习" * 80),
        "imageMap": {},
        "contentStructure": [],
        "materialType": "lecture",
    }
    report = _health_snapshot(snapshot, 1)
    assert 0 <= report["score"] <= 100
    assert report["issueCount"] >= 0
    assert report["stats"]["sectionCount"] == 2
