# -*- coding: utf-8 -*-
"""UI 测试数据播种/还原（只为「后台斩题管理」页面展示校验服务）

背景：admin(user_id=1) 的 3 条斩题记录在库里 error_times_before_mark / review_count /
      last_review_time 全是 0/NULL，页面即使接口正常也只会显示 0 / -。
      为了让浏览器测试能真正校验「表格是否展示了库里的值」，先把这几列改成非零。

用法（必须用项目 venv 的 Windows python 跑，MySQL 在 Windows 侧）：
    .venv/Scripts/python.exe tests/_ui_seed_marked.py seed      # 备份并写入非零值
    .venv/Scripts/python.exe tests/_ui_seed_marked.py restore   # 按备份还原

备份文件：tests/_ui_seed_backup.json（seed 时覆盖写）
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from app.config import settings  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

BK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ui_seed_backup.json")
COLS = ["error_times_before_mark", "correct_times_before_mark", "review_count",
        "last_review_time", "next_review_time"]
SEED_VALUES = {"error_times_before_mark": 5, "correct_times_before_mark": 3, "review_count": 7,
               "last_review_time": "2026-09-01 10:00:00", "next_review_time": "2026-09-20 10:00:00"}


async def run(mode: str):
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(text(
                "SELECT marked_id, " + ", ".join(COLS) + " FROM user_question_marked "
                "WHERE user_id = 1 AND marked_status = 1"))).all()
            if not rows:
                print("没有找到 admin 的斩题记录，跳过")
                return

            if mode == "seed":
                backup = []
                for r in rows:
                    d = dict(r._mapping)
                    backup.append({k: (str(v) if v is not None else None) for k, v in d.items()})
                with open(BK, "w", encoding="utf-8") as f:
                    json.dump(backup, f, ensure_ascii=False, indent=1)
                for r in rows:
                    await conn.execute(text(
                        "UPDATE user_question_marked SET error_times_before_mark=:e, "
                        "correct_times_before_mark=:c, review_count=:rv, last_review_time=:lr, "
                        "next_review_time=:nr WHERE marked_id=:m"),
                        {"e": SEED_VALUES["error_times_before_mark"],
                         "c": SEED_VALUES["correct_times_before_mark"],
                         "rv": SEED_VALUES["review_count"],
                         "lr": SEED_VALUES["last_review_time"],
                         "nr": SEED_VALUES["next_review_time"], "m": r._mapping["marked_id"]})
                print("已播种 %d 条（备份 -> %s）" % (len(rows), BK))

            elif mode == "restore":
                if not os.path.exists(BK):
                    print("没有备份文件，跳过还原：%s" % BK)
                    return
                with open(BK, encoding="utf-8") as f:
                    backup = json.load(f)
                for item in backup:
                    await conn.execute(text(
                        "UPDATE user_question_marked SET error_times_before_mark=:e, "
                        "correct_times_before_mark=:c, review_count=:rv, last_review_time=:lr, "
                        "next_review_time=:nr WHERE marked_id=:m"),
                        {"e": item["error_times_before_mark"], "c": item["correct_times_before_mark"],
                         "rv": item["review_count"], "lr": item["last_review_time"],
                         "nr": item["next_review_time"], "m": item["marked_id"]})
                os.remove(BK)
                print("已还原 %d 条" % len(backup))
            else:
                print("用法: _ui_seed_marked.py seed|restore")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else ""))
