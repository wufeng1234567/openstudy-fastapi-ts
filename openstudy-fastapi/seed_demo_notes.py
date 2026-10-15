"""演示数据：为「学习分享」页生成一批公开笔记（多选复合筛选演示用，幂等）

执行：
    cd openstudy-fastapi
    .venv\\Scripts\\python.exe seed_demo_notes.py

说明：
    · 复用 note_public_section 里已有的分区（Java / Python / 前端 / 后端 / 数据库 / 运维 / AI 大数据 / 其他）
    · 为 user1 / user2 各建一个「演示笔记」分类
    · 生成 16 篇 is_public=1 的笔记，覆盖多个分区、多个标签、不同时间（今天 / 近 7 天 / 近 30 天 / 更早）
    · 幂等：每次先删掉 filename='demo_seed' 的旧演示笔记，再重建

可演示的多选复合筛选：
    1. 分区多选：同时勾选「Java」+「Python」→ 命中两个分区的笔记（组内 OR）
    2. 时间多选：勾选「近 7 天」+「近 30 天」→ 时间并集
    3. 复合：Java + Python + 近 30 天 + 标签「面试」→ 组间 AND
    4. 关键词：输入 Spring / 爬虫 / 索引 / 动态规划 等
    5. 标签多选：勾选「面试」+「前端」等
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, delete, text

from app.database import async_session_factory, init_db
from app.models import (  # noqa: F401  确保全部模型注册
    user, role, menu, notice, question, note,
    note_question_bank, note_question, courses, words, config,
    bank_share, notification,
)
from app.models.user import SysUser
from app.models.note import Note, NoteCategory

# 演示笔记用 filename 做标记，方便幂等清理（该字段不对外返回）
SEED_MARK = "demo_seed"

DEFAULT_SECTIONS = [
    ("Java", 1),
    ("Python", 2),
    ("前端", 3),
    ("后端", 4),
    ("数据库", 5),
    ("运维", 6),
    ("AI/大数据", 7),
    ("其他", 8),
]

# (标题, 分区名, 标签, 几天前, 浏览量, 作者索引)
DEMO_NOTES = [
    ("Java 集合框架面试题整理", "Java", "Java,集合,面试", 0, 320, 0),
    ("Spring Boot 自动装配原理", "Java", "Java,Spring,面试", 0, 260, 1),
    ("Java 并发编程之 volatile", "Java", "Java,并发,面试", 35, 180, 0),
    ("Python 列表推导式与生成器", "Python", "Python,基础", 1, 210, 0),
    ("Python 爬虫 requests 实战", "Python", "Python,爬虫", 3, 150, 1),
    ("Pandas 数据清洗常用操作", "Python", "Python,数据分析", 12, 90, 0),
    ("Vue3 组合式 API 学习笔记", "前端", "Vue,JavaScript,前端", 2, 280, 1),
    ("JavaScript 闭包与作用域链", "前端", "JavaScript,前端,面试", 8, 190, 0),
    ("CSS Flex 布局速查", "前端", "CSS,前端", 20, 120, 1),
    ("MySQL 索引优化总结", "数据库", "MySQL,数据库,面试", 5, 240, 0),
    ("Redis 缓存穿透/击穿/雪崩", "后端", "Redis,后端,面试", 12, 200, 1),
    ("Docker 常用命令速查", "运维", "Docker,运维", 40, 80, 0),
    ("Linux 性能排查思路", "运维", "Linux,运维", 60, 60, 1),
    ("大模型 Prompt 编写技巧", "AI/大数据", "AI,大模型", 25, 175, 0),
    ("算法：动态规划入门", "其他", "算法,面试", 6, 130, 1),
    ("数据结构：二叉树遍历", "其他", "数据结构,算法", 15, 110, 0),
]


async def _ensure_sections(db):
    """返回 {分区名: id}，若表为空则插入默认分区"""
    rows = (await db.execute(text("SELECT id, name FROM note_public_section"))).all()
    if not rows:
        now = datetime.now()
        for name, order in DEFAULT_SECTIONS:
            await db.execute(
                text("INSERT INTO note_public_section (name, sort_order, create_time) VALUES (:n, :o, :t)"),
                {"n": name, "o": order, "t": now},
            )
        await db.flush()
        rows = (await db.execute(text("SELECT id, name FROM note_public_section"))).all()
    return {row[1]: row[0] for row in rows}


async def _ensure_user(db, user_name):
    return (await db.execute(select(SysUser).where(SysUser.user_name == user_name))).scalars().first()


async def _ensure_category(db, user_id, name="演示笔记"):
    cat = (await db.execute(
        select(NoteCategory).where(NoteCategory.user_id == user_id, NoteCategory.name == name)
    )).scalars().first()
    if not cat:
        cat = NoteCategory(user_id=user_id, name=name, order_num=0)
        db.add(cat)
        await db.flush()
    return cat


async def seed():
    await init_db()
    async with async_session_factory() as db:
        print("=" * 60)
        print("开始生成「学习分享」演示笔记 ...")
        print("=" * 60)

        sections = await _ensure_sections(db)
        print(f"[1/3] 分区（{len(sections)} 个）：{', '.join(sections.keys())}")

        user1 = await _ensure_user(db, "user1")
        user2 = await _ensure_user(db, "user2")
        if not user1 or not user2:
            print("! 未找到 user1 / user2，请先执行：.venv\\Scripts\\python.exe seed_demo_users.py")
            return
        cat1 = await _ensure_category(db, user1.user_id)
        cat2 = await _ensure_category(db, user2.user_id)
        print(f"[2/3] 分类：user1 #{cat1.id} / user2 #{cat2.id}")

        deleted = await db.execute(delete(Note).where(Note.filename == SEED_MARK))
        print(f"       清理旧演示笔记 {deleted.rowcount} 条")

        authors = [(user1.user_id, cat1.id), (user2.user_id, cat2.id)]
        section_ids = list(sections.values())
        now = datetime.now()
        created = 0
        for idx, (title, section_name, tags, days_ago, views, author_idx) in enumerate(DEMO_NOTES):
            uid, cid = authors[author_idx % len(authors)]
            body = f"# {title}\n\n（演示数据）这里整理了「{section_name}」相关的要点与面试经验，用于演示学习分享的搜索与多选筛选。"
            db.add(Note(
                user_id=uid,
                category_id=cid,
                title=title,
                filename=SEED_MARK,
                content=body,
                markdown_content=body,
                tags=tags,
                public_section_id=sections.get(section_name) or section_ids[idx % len(section_ids)],
                is_public=1,
                view_count=views,
                like_count=views // 10,
                comment_count=0,
                status="published",
                del_flag="0",
                create_time=now - timedelta(days=days_ago, hours=views % 12, minutes=views % 60),
            ))
            created += 1

        await db.commit()
        print(f"[3/3] 新增公开演示笔记 {created} 篇")
        print("=" * 60)
        print("完成！登录后进入 前台 → 学习分享（/front/notes/list）演示：")
        print("  · 分区多选：Java + Python        → 命中两个分区")
        print("  · 时间多选：近7天 + 近30天       → 时间并集")
        print("  · 复合筛选：Java + Python + 近30天 + 标签「面试」")
        print("  · 关键词：Spring / 爬虫 / 索引 / 动态规划")
        print("  · 标签多选：面试 + 前端")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
