"""
用户学习统计 API
- 总览统计:做题数/正确率/错题数/收藏数/斩题数
- 按科目分组统计
- 学习趋势(最近N天)
- 错题掌握度
- 成长记录
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, error
from app.models.question import (
    QuestionBank,
    QuestionMain,
    UserBankFavorite,
    UserQuestionFavorite,
    UserQuestionError,
    UserQuestionMarked,
    UserPracticeLog,
)
from app.models.note import Note, UserNoteFavorite
from app.models.user import SysUser

router = APIRouter(prefix="/userStats")


@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """用户学习总览

    返回:收藏题目数/题库数、错题数、斩题数、已掌握错题数、
    收藏笔记数、练习次数、正确率、题库学习总次数。
    """
    user_id = current_user.get("user_id")

    # 收藏题目数
    total_questions = await db.scalar(
        select(func.count()).where(
            UserQuestionFavorite.user_id == user_id,
            UserQuestionFavorite.favorite_status == 1,
        )
    )

    # 收藏题库数
    total_banks = await db.scalar(
        select(func.count()).where(
            UserBankFavorite.user_id == user_id,
            UserBankFavorite.favorite_status == 1,
        )
    )

    # 错题数(未掌握)
    total_errors = await db.scalar(
        select(func.count()).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.status == 1,
            UserQuestionError.is_mastered == 0,
        )
    )

    # 已掌握错题数
    total_mastered = await db.scalar(
        select(func.count()).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.is_mastered == 1,
        )
    )

    # 斩题数
    total_marked = await db.scalar(
        select(func.count()).where(
            UserQuestionMarked.user_id == user_id,
            UserQuestionMarked.marked_status == 1,
        )
    )

    # 收藏笔记数
    total_favorite_notes = await db.scalar(
        select(func.count()).where(
            UserNoteFavorite.user_id == user_id,
        )
    )

    # 练习次数与正确率：基于答题流水 user_practice_log
    # ⚠️ 原实现用 SUM(user_question_favorite.correct_times/error_times)，但前端"答对"时
    #    不上报，这两个字段从未被写入过 → 「共作答次数」「正确率」恒为 0。
    #    流水表每次作答都写一条，是唯一可靠的数据源。
    practice_query = select(
        func.count(UserPracticeLog.log_id).label("total"),
        func.coalesce(func.sum(UserPracticeLog.is_correct), 0).label("correct"),
    ).where(UserPracticeLog.user_id == user_id)
    practice_row = (await db.execute(practice_query)).one()
    total_practice = int(practice_row.total or 0)
    correct_sum = int(practice_row.correct or 0)
    correct_rate = round(correct_sum / total_practice * 100, 1) if total_practice > 0 else 0.0

    # 题库学习总次数
    bank_study_count = await db.scalar(
        select(func.coalesce(func.sum(UserBankFavorite.study_count), 0)).where(
            UserBankFavorite.user_id == user_id,
        )
    )

    # 各题型分布(JOIN QuestionMain 按 question_type 分组)
    type_query = (
        select(QuestionMain.question_type, func.count().label("count"))
        .select_from(UserQuestionFavorite.__table__.join(
            QuestionMain.__table__,
            UserQuestionFavorite.question_id == QuestionMain.id,
        ))
        .where(UserQuestionFavorite.user_id == user_id)
        .group_by(QuestionMain.question_type)
    )
    type_result = await db.execute(type_query)
    type_names = {1: "单选题", 2: "多选题", 3: "判断题", 4: "填空题", 5: "简答题", 6: "组合题"}
    by_question_type = [
        {"type": row.question_type, "typeName": type_names.get(row.question_type, "未知"), "count": row.count}
        for row in type_result.all()
    ]

    return success({
        "totalQuestions": total_questions or 0,
        "totalBanks": total_banks or 0,
        "totalErrors": total_errors or 0,
        "totalMarked": total_marked or 0,
        "totalMastered": total_mastered or 0,
        "totalFavoriteNotes": total_favorite_notes or 0,
        "totalPracticeCount": total_practice,
        "correctRate": correct_rate,
        "bankStudyCount": bank_study_count or 0,
        "byQuestionType": by_question_type,
    })


@router.get("/bySubject")
async def get_by_subject(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按科目分组统计

    返回每个科目的题库数、收藏题目数、错题数、斩题数。
    """
    user_id = current_user.get("user_id")
    stats: dict = {}

    # 收藏题库数(按科目)
    bank_query = select(
        QuestionBank.subject,
        func.count(UserBankFavorite.favorite_id).label("count"),
    ).select_from(
        UserBankFavorite.__table__.join(
            QuestionBank.__table__,
            UserBankFavorite.bank_id == QuestionBank.id,
        )
    ).where(
        UserBankFavorite.user_id == user_id,
        UserBankFavorite.favorite_status == 1,
    ).group_by(QuestionBank.subject)
    for row in (await db.execute(bank_query)).all():
        subject = row.subject or "未分类"
        stats.setdefault(subject, {"subject": subject, "bankCount": 0, "questionCount": 0, "errorCount": 0, "markedCount": 0})
        stats[subject]["bankCount"] = row.count

    # 收藏题目数(按科目)
    qfav_query = select(
        QuestionBank.subject,
        func.count(UserQuestionFavorite.favorite_id).label("count"),
    ).select_from(
        UserQuestionFavorite.__table__.join(
            QuestionBank.__table__,
            UserQuestionFavorite.bank_id == QuestionBank.id,
        )
    ).where(
        UserQuestionFavorite.user_id == user_id,
        UserQuestionFavorite.favorite_status == 1,
    ).group_by(QuestionBank.subject)
    for row in (await db.execute(qfav_query)).all():
        subject = row.subject or "未分类"
        stats.setdefault(subject, {"subject": subject, "bankCount": 0, "questionCount": 0, "errorCount": 0, "markedCount": 0})
        stats[subject]["questionCount"] = row.count

    # 错题数(未掌握,按科目)
    err_query = select(
        QuestionBank.subject,
        func.count(UserQuestionError.error_id).label("count"),
    ).select_from(
        UserQuestionError.__table__.join(
            QuestionBank.__table__,
            UserQuestionError.bank_id == QuestionBank.id,
        )
    ).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.status == 1,
        UserQuestionError.is_mastered == 0,
    ).group_by(QuestionBank.subject)
    for row in (await db.execute(err_query)).all():
        subject = row.subject or "未分类"
        stats.setdefault(subject, {"subject": subject, "bankCount": 0, "questionCount": 0, "errorCount": 0, "markedCount": 0})
        stats[subject]["errorCount"] = row.count

    # 斩题数(按科目)
    mark_query = select(
        QuestionBank.subject,
        func.count(UserQuestionMarked.marked_id).label("count"),
    ).select_from(
        UserQuestionMarked.__table__.join(
            QuestionBank.__table__,
            UserQuestionMarked.bank_id == QuestionBank.id,
        )
    ).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.marked_status == 1,
    ).group_by(QuestionBank.subject)
    for row in (await db.execute(mark_query)).all():
        subject = row.subject or "未分类"
        stats.setdefault(subject, {"subject": subject, "bankCount": 0, "questionCount": 0, "errorCount": 0, "markedCount": 0})
        stats[subject]["markedCount"] = row.count

    return success(list(stats.values()))


@router.get("/trend")
async def get_trend(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """学习趋势(最近N天)

    基于答题流水 user_practice_log（真实作答行为）：
    - practiceCount: 当天作答总数
    - correctCount / errorCount: 当天答对 / 答错次数（同一题重复做错会累计到当天）
    - markedCount: 当天新增斩题数
    """
    user_id = current_user.get("user_id")
    start_date = datetime.now() - timedelta(days=days)

    # 答题流水按日期（一次聚合拿到 总数 / 答对 / 答错）
    # ⚠️ 原实现用 user_question_error.create_time 统计"错题数"，那只是"第一次做错"的日期，
    #    今天重做一道老错题不会计入今天，趋势会假性平坦；用题目收藏 create_time 当"练习"
    #    更是完全错位（收藏 ≠ 练习）。
    prac_query = select(
        func.date(UserPracticeLog.create_time).label("date"),
        func.count(UserPracticeLog.log_id).label("total"),
        func.coalesce(func.sum(UserPracticeLog.is_correct), 0).label("correct"),
    ).where(
        UserPracticeLog.user_id == user_id,
        UserPracticeLog.create_time >= start_date,
    ).group_by(func.date(UserPracticeLog.create_time))
    prac_map: dict = {}
    for row in (await db.execute(prac_query)).all():
        total = int(row.total or 0)
        correct = int(row.correct or 0)
        prac_map[str(row.date)] = {"total": total, "correct": correct, "error": total - correct}

    # 斩题按日期
    mark_query = select(
        func.date(UserQuestionMarked.create_time).label("date"),
        func.count(UserQuestionMarked.marked_id).label("count"),
    ).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.create_time >= start_date,
    ).group_by(func.date(UserQuestionMarked.create_time))
    mark_map = {
        str(row.date): row.count
        for row in (await db.execute(mark_query)).all()
    }

    # 生成完整日期范围(含无数据日期,填0)
    result = []
    today = datetime.now().date()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        date_str = str(d)
        day = prac_map.get(date_str) or {"total": 0, "correct": 0, "error": 0}
        result.append({
            "date": date_str,
            "practiceCount": day["total"],
            "correctCount": day["correct"],
            "errorCount": day["error"],
            "markedCount": mark_map.get(date_str, 0),
        })

    return success(result)


@router.get("/errorAnalysis")
async def get_error_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """错题分析

    返回:错题总数、已掌握数、掌握率、按难度分组、错误次数最多的5道题。
    """
    user_id = current_user.get("user_id")

    # 错题总数（全部记录，含已掌握）—— 作为"掌握度"的分母
    total_errors = await db.scalar(
        select(func.count()).where(UserQuestionError.user_id == user_id)
    )

    # 待消灭错题（仍活跃在错题本里的）
    active_errors = await db.scalar(
        select(func.count()).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.status == 1,
        )
    )

    # 已掌握错题数
    # ⚠️ 原实现写成 status==1 AND is_mastered==1，但标记已掌握的接口会同时写 status=0，
    #    两个条件互斥 → 掌握数恒为 0、掌握率恒为 0%；且标记后题目从分析里彻底消失。
    mastered = await db.scalar(
        select(func.count()).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.is_mastered == 1,
        )
    )
    master_rate = round(mastered / total_errors * 100, 1) if (total_errors or 0) > 0 else 0.0

    # 按难度分组(JOIN question_main 获取 difficulty)
    diff_query = select(
        QuestionMain.difficulty,
        func.count(UserQuestionError.error_id).label("count"),
    ).select_from(
        UserQuestionError.__table__.join(
            QuestionMain.__table__,
            UserQuestionError.question_id == QuestionMain.id,
        )
    ).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.status == 1,
    ).group_by(QuestionMain.difficulty)
    by_difficulty = [
        {"difficulty": row.difficulty or 1, "count": row.count}
        for row in (await db.execute(diff_query)).all()
    ]

    # 按题型分布
    type_query = (
        select(QuestionMain.question_type, func.count().label("count"))
        .select_from(UserQuestionError.__table__.join(
            QuestionMain.__table__,
            UserQuestionError.question_id == QuestionMain.id,
        ))
        .where(UserQuestionError.user_id == user_id, UserQuestionError.status == 1)
        .group_by(QuestionMain.question_type)
    )
    type_names = {1: "单选题", 2: "多选题", 3: "判断题", 4: "填空题", 5: "简答题", 6: "组合题"}
    by_question_type = [
        {"type": row.question_type, "typeName": type_names.get(row.question_type, "未知"), "count": row.count}
        for row in (await db.execute(type_query)).all()
    ]

    # 按科目分布(JOIN QuestionBank 获取 subject)
    subject_query = (
        select(QuestionBank.subject, func.count().label("count"))
        .select_from(
            UserQuestionError.__table__.join(
                QuestionMain.__table__, UserQuestionError.question_id == QuestionMain.id,
            ).join(
                QuestionBank.__table__, QuestionMain.bank_id == QuestionBank.id,
            )
        )
        .where(UserQuestionError.user_id == user_id, UserQuestionError.status == 1)
        .group_by(QuestionBank.subject)
    )
    by_subject = [
        {"subject": row.subject or "未分类", "count": row.count}
        for row in (await db.execute(subject_query)).all()
    ]

    # 错误次数最多的5道题
    top_query = select(
        UserQuestionError.question_id,
        UserQuestionError.error_count,
        QuestionMain.question_text,
    ).select_from(
        UserQuestionError.__table__.join(
            QuestionMain.__table__,
            UserQuestionError.question_id == QuestionMain.id,
        )
    ).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.status == 1,
    ).order_by(UserQuestionError.error_count.desc()).limit(5)
    top_errors = [
        {
            "questionId": row.question_id,
            "questionText": (row.question_text or "")[:100],
            "errorCount": row.error_count,
        }
        for row in (await db.execute(top_query)).all()
    ]

    return success({
        "totalErrors": total_errors or 0,
        "activeErrors": active_errors or 0,
        "mastered": mastered or 0,
        "masterRate": master_rate,
        "byDifficulty": by_difficulty,
        "byQuestionType": by_question_type,
        "bySubject": by_subject,
        "topErrors": top_errors,
    })


@router.get("/growth")
async def get_growth(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """成长记录

    返回:加入日期、学习天数、收藏题库/题目/笔记总数、里程碑。
    """
    user_id = current_user.get("user_id")

    # 用户加入日期
    user_row = (await db.execute(
        select(SysUser.create_time).where(SysUser.user_id == user_id)
    )).first()
    join_date = user_row.create_time if user_row else None

    # 收集所有有学习活动的日期（含答题流水：只有它记录了"今天真的做了题"）
    dates_set = set()

    for model, col in [
        (UserPracticeLog, UserPracticeLog.create_time),   # 答题行为（最权威）
        (UserQuestionError, UserQuestionError.create_time),
        (UserQuestionMarked, UserQuestionMarked.create_time),
        (UserQuestionFavorite, UserQuestionFavorite.create_time),
        (UserBankFavorite, UserBankFavorite.create_time),
    ]:
        q = select(func.distinct(func.date(col))).where(model.user_id == user_id)
        for row in (await db.execute(q)).all():
            if row[0] is not None:
                dates_set.add(str(row[0]))

    study_days = len(dates_set)

    # 计算连续刷题天数(从今天往前回溯的最长连续天数)
    consecutive_days = 0
    if dates_set:
        sorted_dates = sorted(dates_set, reverse=True)
        today = datetime.now().date()
        # 从今天或昨天开始回溯
        check_date = today
        if str(today) not in dates_set:
            check_date = today - timedelta(days=1)
        while str(check_date) in dates_set:
            consecutive_days += 1
            check_date -= timedelta(days=1)

    # 总收藏题库数
    total_banks = await db.scalar(
        select(func.count()).where(
            UserBankFavorite.user_id == user_id,
            UserBankFavorite.favorite_status == 1,
        )
    )
    # 总收藏题目数
    total_questions = await db.scalar(
        select(func.count()).where(
            UserQuestionFavorite.user_id == user_id,
            UserQuestionFavorite.favorite_status == 1,
        )
    )
    # 总笔记数(用户自己创建的笔记)
    total_notes = await db.scalar(
        select(func.count()).where(
            Note.user_id == user_id,
            Note.del_flag == "0",
        )
    )
    # 已掌握错题数(用于里程碑)
    mastered_count = await db.scalar(
        select(func.count()).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.is_mastered == 1,
        )
    )
    # 斩题数(用于里程碑)
    marked_count = await db.scalar(
        select(func.count()).where(
            UserQuestionMarked.user_id == user_id,
            UserQuestionMarked.marked_status == 1,
        )
    )

    # 里程碑定义
    milestones = [
        {"type": "bank", "count": 5, "title": "收藏5个题库", "achieved": (total_banks or 0) >= 5},
        {"type": "bank", "count": 10, "title": "收藏10个题库", "achieved": (total_banks or 0) >= 10},
        {"type": "marked", "count": 50, "title": "斩题50道", "achieved": (marked_count or 0) >= 50},
        {"type": "marked", "count": 100, "title": "斩题100道", "achieved": (marked_count or 0) >= 100},
        {"type": "mastered", "count": 20, "title": "掌握20道错题", "achieved": (mastered_count or 0) >= 20},
        {"type": "mastered", "count": 50, "title": "掌握50道错题", "achieved": (mastered_count or 0) >= 50},
    ]

    return success({
        "joinDate": join_date.strftime("%Y-%m-%d") if join_date else None,
        "studyDays": study_days,
        "consecutiveDays": consecutive_days,
        "totalBanks": total_banks or 0,
        "totalQuestions": total_questions or 0,
        "totalNotes": total_notes or 0,
        "milestones": milestones,
    })


@router.get("/diagnose")
async def get_diagnose(
    limit: int = Query(30, ge=1, le=200, description="最多返回多少道需要关注的题"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    逐题学情诊断（2026-10-26 v3 新增）

    ── 为什么单独开一个接口 ─────────────────────────────────────
    `study_diagnosis_service.diagnose()` 早就写好了，数据质量也很高：

      · 每道题有 `masteryLevel`（repeated_failure / lapsing / overdue /
        due_soon / on_track / mastered / fresh 七档）
      · 有 `byLevel` / `bySubject` / `activity` 三组可直接画图的聚合
      · 有 `headline`（一句人话结论）与 `suggestions`（下一步建议）

    但它**只挂在 AI 工具链上**（`learning_stats` 的 `diagnose` action），
    用户必须去对话里问一句才看得到，而且默认输出是一份 PDF 下载。

    前端 `myStats` 页面完全没有这个数据 —— 那里只有"总览/趋势/科目/错题"
    四张基于 SQL 聚合的图，缺的正是"每道题现在什么状态、什么时候该复习"。

    所以这个接口的作用是：**把已有的诊断能力暴露成普通 REST**，
    让前端可以直接画成页内图表（而不是让用户下载 PDF 才有信息）。

    返回结构与 `diagnose()` 完全一致，前端不需要再做一层映射。
    """
    from app.services.study_diagnosis_service import diagnose

    user_id = current_user.get("user_id")
    data = await diagnose(db, user_id=user_id, limit=limit)
    return success(data)


@router.get("/reviewSheet")
async def get_review_sheet(
    limit: int = Query(
        20, ge=1, le=100, description="复习卷最多收录多少道题（按优先级取前 N）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    按薄弱点生成复习卷 Word（2026-10-26 v3 新增）

    ── 这个接口串起了三件已经存在的东西 ─────────────────────────
      1. `diagnose()` 算出的「该先复习谁」优先级
      2. `bank_export_service` 的公式 / 表格渲染能力（v3 刚修好的）
      3. 用户手上现成的错题数据

    做成一份可直接打印的 Word：

        卷首  掌握度分档表 + 学科情况表     ← 真表格
        正文  按优先级排的题目（含作答空间）
        卷尾  未来七天复习计划表           ← 真表格
        附页  答案与解析（单独起页，方便裁掉）

    ── 为什么不让 AI 生成 ───────────────────────────────────────
    复习卷的内容是**确定的**：哪些题、什么档位、哪天复习，
    全部来自 `diagnose()` 的确定性算法。让 AI 再"创作"一遍只会引入
    不一致（同一个用户两次生成结果不同）和额外延迟。

    所以这条路径**完全不经过大模型**，3 秒内出文件。

    ── 返回 ─────────────────────────────────────────────────────
    直接返回 .docx 二进制流（`StreamingResponse`），与题库导出接口一致 ——
    前端已有的下载逻辑可以直接复用，不需要先拿 URL 再拉一次。
    """
    import io
    import re as _re
    from urllib.parse import quote

    from fastapi.responses import StreamingResponse
    from sqlalchemy.orm import selectinload

    from app.services.review_sheet_service import build_review_sheet
    from app.services.study_diagnosis_service import diagnose

    user_id = current_user.get("user_id")

    # ① 先诊断（这一步决定"复习哪几道"）
    #
    # ⚠️ `diagnose(limit=N)` 的 N 是「**每一档**最多几道」，不是总数 ——
    #    七档乘起来能到好几十题（实测 user1 传 30 拿到 71 题）。
    #    复习卷需要的是"总数可控"，所以在下面取完题后再按总数截断一次。
    diag = await diagnose(db, user_id=user_id, limit=limit)
    items = diag.get("items") or []
    if not items:
        return error(
            "还没有足够的练习记录来生成复习卷。先做几道题，诊断才有依据。",
            code=400,
        )

    # 先按总数截断（诊断已按「该先处理谁」排好序，取前 N 就是最该做的 N 道）
    items = items[:limit]

    # ② 按诊断给出的顺序取完整题目
    #
    # ⚠️ 不能直接用 `diag["items"][i]["questionText"]`：那是**截断到 120 字**的
    #    预览文本，只够列表展示。复习卷要完整题干、选项、答案。
    qids = [int(it["questionId"]) for it in items if it.get("questionId")]
    stmt = (
        select(QuestionMain)
        .where(QuestionMain.id.in_(qids), QuestionMain.status == "0")
        .options(selectinload(QuestionMain.sub_questions))
    )
    rows = (await db.execute(stmt)).scalars().all()

    from app.api.v1.questions import format_question

    by_id = {q.id: format_question(q) for q in rows}

    # 保持诊断的优先级顺序（IN 查询不保证顺序）
    level_text_of = {int(it["questionId"]): it.get("levelText") for it in items if it.get("questionId")}
    ordered = []
    for qid in qids:
        q = by_id.get(qid)
        if not q:
            continue
        # 把分档标签挂在题目上，复习卷正文要用它标"这题为什么被选进来"
        q["_levelText"] = level_text_of.get(qid)
        ordered.append(q)

    if not ordered:
        return error(
            "诊断出的题目都已被删除或停用，暂时无法生成复习卷。",
            code=400,
        )

    # ③ 出文件
    data = build_review_sheet(diag, ordered)

    stamp = datetime.now().strftime("%Y%m%d")
    filename = f"薄弱点复习卷_{stamp}.docx"
    ascii_fallback = _re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "review.docx"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{quote(filename, safe='')}"
            ),
            # 让前端能读到实际收录了多少题（CORS 下默认不暴露自定义头）
            "X-Review-Count": str(len(ordered)),
            "Access-Control-Expose-Headers": "X-Review-Count, Content-Disposition",
        },
    )
