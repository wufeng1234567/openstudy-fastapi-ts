"""知航 · 活计划的纯规则测试（不连数据库、不调模型）。"""

from datetime import date, datetime

import pytest

from app.services.study_plan_service import (
    _apply_progress,
    _pack_days,
    _task_done,
    _tasks_for_banks,
    _tasks_for_stop,
    plan_dates,
)


def test_plan_dates_skips_rest_days_and_stops_before_exam():
    dates = plan_dates(
        date(2026, 11, 9),
        exam_date=date(2026, 11, 16),
        horizon_days=10,
        rest_days=[7],  # 周日
    )
    assert dates[0] == date(2026, 11, 9)
    assert date(2026, 11, 14) in dates
    assert date(2026, 11, 15) not in dates  # 周日休息
    assert date(2026, 11, 16) not in dates  # 考试当天不排
    assert all(day.isoweekday() != 7 for day in dates)


def test_pack_days_does_not_split_tasks_or_drop_them():
    tasks = [
        {"id": "a", "minutes": 20, "type": "read"},
        {"id": "b", "minutes": 30, "type": "practice"},
        {"id": "c", "minutes": 10, "type": "review"},
    ]
    days = _pack_days(tasks, [date(2026, 11, 9), date(2026, 11, 10)], daily_minutes=40)
    assert [[t["id"] for t in day["tasks"]] for day in days] == [["a"], ["b", "c"]]
    assert [t for day in days for t in day["tasks"]] == tasks


def test_task_done_is_since_semantics_not_calendar_day():
    task = {
        "type": "practice",
        "target": {"kind": "bank", "questionIds": [101]},
        "pageId": 3,
    }
    since = datetime(2026, 11, 8, 9, 0, 0)
    # 11 月 7 日做过不算「计划生成后完成」
    assert not _task_done(
        task,
        start_dt=since,
        practice_logs={101: datetime(2026, 11, 7, 22, 0, 0)},
        stops_by_page={},
    )
    # 11 月 9 日补做仍然算完成（不按 scheduled date 切）
    assert _task_done(
        task,
        start_dt=since,
        practice_logs={101: datetime(2026, 11, 9, 8, 0, 0)},
        stops_by_page={},
    )


def test_tasks_for_stop_never_invents_missing_targets():
    stop = {
        "pageId": 7,
        "title": "极限",
        "role": "repair",
        "reason": "待补",
        "learning": {"viewCount": 0, "level": "unread"},
        "practice": None,
        "weakQuestionIds": [],
    }
    tasks = _tasks_for_stop(stop, diagnosis_items={}, exam_mode=False)
    assert [task["type"] for task in tasks] == ["read"]
    assert tasks[0]["target"] == {"kind": "page", "pageId": 7}


def test_apply_progress_marks_first_open_current_and_done_tasks():
    days = [
        {
            "date": "2026-11-08",
            "minutes": 20,
            "tasks": [
                {"id": "a", "type": "read", "minutes": 8, "pageId": 1, "target": {"kind": "page", "pageId": 1}, "status": "next"},
                {"id": "b", "type": "practice", "minutes": 12, "pageId": 1, "target": {"kind": "bank", "questionIds": [9]}, "status": "next"},
            ],
        }
    ]
    stops = {1: {"learning": {"viewCount": 1, "lastActivityTime": "2026-11-08 10:00:00"}}}
    progress = _apply_progress(
        days,
        start_dt=datetime(2026, 11, 8, 9, 0, 0),
        now=datetime(2026, 11, 8, 12, 0, 0),
        practice_logs={9: datetime(2026, 11, 8, 10, 30, 0)},
        stops_by_page=stops,
    )
    assert days[0]["tasks"][0]["status"] == "done"
    assert days[0]["tasks"][1]["status"] == "done"
    assert progress["doneTasks"] == 2
    assert progress["percent"] == 100.0


def test_bank_tasks_use_real_question_ids_and_skip_legacy_banks():
    diagnosis = {
        1: {
            "questionId": 101,
            "bankId": 9,
            "bankName": "题库 A",
            "level": "repeated_failure",
            "levelText": "反复失守",
            "questionText": "题一",
            "advice": "先补前置",
            "attempts": 5,
            "accuracy": 20,
        },
        2: {
            "questionId": 102,
            "bankId": 9,
            "bankName": "题库 A",
            "level": "lapsing",
            "levelText": "一做就错",
            "questionText": "题二",
            "attempts": 3,
            "accuracy": 30,
        },
        3: {
            "questionId": 201,
            "bankId": 10,
            "bankName": "考前计划·旧库",
            "level": "repeated_failure",
            "levelText": "反复失守",
            "questionText": "旧题",
            "attempts": 3,
            "accuracy": 10,
        },
    }
    tasks = _tasks_for_banks(diagnosis, max_banks=2, max_per_bank=2)

    assert [task["target"]["questionId"] for task in tasks] == [101, 102]
    assert all(task["target"]["kind"] == "question" for task in tasks)
    assert all(task["sourceNodeId"] == "b:9" for task in tasks)
    assert all(task["axis"] == "bank" for task in tasks)
