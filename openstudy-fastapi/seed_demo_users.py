"""演示数据初始化脚本（幂等，可重复执行）

用途：功能演示时，快速准备两个普通用户、一个只读游客和一个管理员的演示环境。

执行：
    cd openstudy-fastapi
    .venv\\Scripts\\python.exe seed_demo_users.py

创建内容：
    1. user1 / 123456   普通用户（role_key=common），拥有**两个**演示题库
       - 《数据结构基础（演示题库）》 私有（is_public=1），10 道题（含 1 道组合题 2 道子题）
       - 《计算机网络基础（演示题库）》 公开（is_public=0），8 道题
       → 用于演示「题库主有多个题库时，分享哪个由自己在下拉框里选」
    2. user2 / 123456   普通用户（role_key=common），无题库 —— 作为「分享接收方」
    3. guest            游客（role_key=visitor），只读演示；点赞/刷题/写笔记等操作会被要求登录
    4. admin            已存在则不改动，仅用于登录页「管理员一键登录」

    4. user1 的学习行为数据（用于演示「学习统计」等页面，**持久化在库里**）
       - 答题流水 143 条，铺在最近 14 天里（其中 3 天空档）
       - 错题记录 7 条（含 2 条「已掌握」，让掌握进度条不是 0%）
       - 斩题记录 5 条、收藏题目 8 条、收藏题库若干（多科目 → 科目分布有多个扇区）
       - 数据自洽：错题次数/最近出错时间、收藏题的练习次数**全部由流水反推**
       - 幂等：每次执行先清空 user1 的这 5 张表再按固定随机种子重建，重复运行结果一致

登录页提供「一键登录」按钮，对应账号：
    user1 / user2 / admin / guest
"""

import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import select, delete, func, update, text

from app.database import async_session_factory, init_db
from app.core.security import hash_password
from app.models import (  # noqa: F401  确保全部模型注册
    user, role, menu, notice, question, note,
    note_question_bank, note_question, courses, words, config,
    bank_share, notification,
)
from app.models.user import SysUser, SysUserRole
from app.models.role import SysRole
from app.models.question import (
    QuestionBank, QuestionMain, QuestionSub,
    UserBankFavorite, UserQuestionFavorite, UserQuestionError,
    UserQuestionMarked, UserPracticeLog,
)
from app.models.note import Note, NoteCategory, NoteComment, UserNoteFavorite
from app.models.note_question import NoteQuestion
from app.models.note_question_bank import NoteQuestionBank

DEMO_PASSWORD = "123456"


# ========== 演示题库内容 ==========

def _data_structure_questions():
    """《数据结构基础》10 道题

    题型编码：1=单选 2=多选 3=判断 4=填空 5=简答 6=组合题
    数据格式与线上一致：options 为字符串数组；判断题 answer 为 'true'/'false'；
    多选题 answer 形如 'A,C'。
    """
    return [
        {
            "type": 1,
            "text": "在长度为 n 的顺序表中插入一个元素，平均需要移动多少个元素？",
            "options": ["n/2", "n", "(n+1)/2", "n-1"],
            "answer": "A",
            "analysis": "元素等概率插入到 n+1 个位置，平均移动次数为 n/2。",
        },
        {
            "type": 1,
            "text": "栈的运算特点是？",
            "options": ["先进先出", "后进先出", "随机存取", "按优先级出栈"],
            "answer": "B",
            "analysis": "栈只允许在栈顶一端进行插入和删除，因此是后进先出（LIFO）。",
        },
        {
            "type": 1,
            "text": "队列的运算特点是？",
            "options": ["后进先出", "先进先出", "只能在栈顶操作", "支持任意位置插入"],
            "answer": "B",
            "analysis": "队列在队尾插入、队头删除，因此是先进先出（FIFO）。",
        },
        {
            "type": 2,
            "text": "下列属于二叉树遍历方式的有哪些？",
            "options": ["前序遍历", "中序遍历", "后序遍历", "层序遍历"],
            "answer": "A,B,C,D",
            "analysis": "前序、中序、后序属于深度优先遍历，层序遍历属于广度优先遍历，均为二叉树遍历方式。",
        },
        {
            "type": 3,
            "text": "在单链表中，访问第 i 个元素的时间复杂度是 O(1)。",
            "options": None,
            "answer": "false",
            "analysis": "单链表不支持随机存取，必须从头结点依次向后查找，时间复杂度为 O(n)。",
        },
        {
            "type": 4,
            "text": "栈是一种 ______ 进先出的线性表。（填“先”或“后”）",
            "options": None,
            "answer": "后",
            "analysis": "栈遵循后进先出（LIFO）原则。",
        },
        {
            "type": 5,
            "text": "简述栈和队列的主要区别。",
            "options": None,
            "answer": "栈只允许在一端（栈顶）进行插入和删除，遵循后进先出；队列在一端（队尾）插入、另一端（队头）删除，遵循先进先出。",
            "analysis": "关键区别在于操作端点的数量和插入/删除的位置约束。",
        },
        {
            "type": 1,
            "text": "下列排序算法中，平均时间复杂度为 O(n log n) 且不稳定的是？",
            "options": ["冒泡排序", "归并排序", "快速排序", "直接插入排序"],
            "answer": "C",
            "analysis": "快速排序平均时间复杂度为 O(n log n)，但在交换过程中可能改变相同元素的相对次序，因此不稳定。",
        },
        {
            "type": 6,
            "text": "一个有 5 个顶点、6 条边的无向图，请根据该描述完成下列小题。",
            "options": None,
            "answer": "",
            "analysis": "",
            "subs": [
                {
                    "type": 1,
                    "text": "该图的邻接矩阵中，非零元素的个数是？",
                    "options": ["6", "10", "12", "30"],
                    "answer": "C",
                    "analysis": "无向图的邻接矩阵关于主对角线对称，每条边对应 2 个非零元素，6 条边共 12 个。",
                    "score": 2,
                },
                {
                    "type": 3,
                    "text": "该图一定存在环。",
                    "options": None,
                    "answer": "true",
                    "analysis": "5 个顶点的树最多有 4 条边，该图有 6 条边，必然含有环。",
                    "score": 2,
                },
            ],
        },
        {
            "type": 1,
            "text": "哈希表使用开放定址法解决冲突时，线性探测法的主要缺点是？",
            "options": ["无法存储字符串", "容易产生堆积（聚集）现象", "需要额外的链表空间", "不能删除任何元素"],
            "answer": "B",
            "analysis": "线性探测会产生一次聚集，导致连续被占用的单元越来越多，查找效率明显下降。",
        },
    ]


def _network_questions():
    """《计算机网络基础》8 道题（公开题库，用于演示「多题库择一分享」）"""
    return [
        {
            "type": 1,
            "text": "TCP/IP 模型中，负责端到端可靠传输的是哪一层？",
            "options": ["网络接口层", "网际层", "传输层", "应用层"],
            "answer": "C",
            "analysis": "传输层（TCP）通过确认、重传、序号等机制提供端到端的可靠传输。",
        },
        {
            "type": 1,
            "text": "IPv4 地址的长度是多少位？",
            "options": ["16 位", "32 位", "64 位", "128 位"],
            "answer": "B",
            "analysis": "IPv4 地址为 32 位，通常写成点分十进制；IPv6 为 128 位。",
        },
        {
            "type": 2,
            "text": "下列属于应用层协议的有哪些？",
            "options": ["HTTP", "FTP", "TCP", "DNS"],
            "answer": "A,B,D",
            "analysis": "HTTP、FTP、DNS 都工作在应用层；TCP 属于传输层协议。",
        },
        {
            "type": 3,
            "text": "UDP 是一种面向连接的可靠传输协议。",
            "options": None,
            "answer": "false",
            "analysis": "UDP 是无连接的，不保证可靠交付，但开销小、时延低。",
        },
        {
            "type": 4,
            "text": "把域名解析为 IP 地址的协议缩写是 ______。",
            "options": None,
            "answer": "DNS",
            "analysis": "DNS（Domain Name System）负责域名与 IP 地址之间的映射。",
        },
        {
            "type": 1,
            "text": "在浏览器地址栏输入网址后，最先发生的一步通常是？",
            "options": ["建立 TCP 连接", "DNS 域名解析", "发送 HTTP 请求", "渲染页面"],
            "answer": "B",
            "analysis": "需要先通过 DNS 把域名解析成 IP 地址，才能向该地址发起连接。",
        },
        {
            "type": 1,
            "text": "三次握手中，客户端发送的第一个报文段的标志位是？",
            "options": ["SYN=1", "ACK=1", "FIN=1", "RST=1"],
            "answer": "A",
            "analysis": "三次握手的第一步由客户端发送 SYN=1、seq=x 的报文段请求建立连接。",
        },
        {
            "type": 5,
            "text": "简述 TCP 与 UDP 的主要区别。",
            "options": None,
            "answer": "TCP 面向连接、提供可靠传输（确认重传、流量控制、拥塞控制），开销较大；UDP 无连接、不保证可靠交付，但首部开销小、传输时延低，适合实时性要求高的场景。",
            "analysis": "核心区别在于是否面向连接、是否保证可靠交付，以及由此带来的开销差异。",
        },
    ]


# 演示题库清单：user1 名下两个题库，用于演示「分享时自由选择题库」
DEMO_BANKS = [
    {
        "name": "数据结构基础（演示题库）",
        "subject": "计算机基础",
        "description": "用于分享功能演示的私有题库，包含 10 道数据结构基础题目。",
        "is_public": 1,  # 1=私有：外部搜不到，只能靠分享链接/分享码获取
        "questions": _data_structure_questions,
    },
    {
        "name": "计算机网络基础（演示题库）",
        "subject": "计算机网络",
        "description": "公开演示题库，包含 8 道计算机网络基础题目；与私有题库一起用于演示分享时选择题库。",
        "is_public": 0,  # 0=公开：题库练习里能搜到
        "questions": _network_questions,
    },
]


async def _get_or_create_common_role(db) -> SysRole:
    """确保存在 role_key=common 的普通角色"""
    role = (await db.execute(select(SysRole).where(SysRole.role_key == "common"))).scalars().first()
    if role:
        return role
    role = SysRole(
        role_name="普通角色",
        role_key="common",
        role_sort=2,
        data_scope="1",
        menu_check_strictly=True,
        dept_check_strictly=True,
        status="0",
        del_flag="0",
    )
    db.add(role)
    await db.flush()
    print("  + 创建角色 common（普通角色）")
    return role


async def _get_or_create_visitor_role(db) -> SysRole:
    """确保存在 role_key=visitor 的游客角色（只读，不绑定任何菜单权限）"""
    role = (await db.execute(select(SysRole).where(SysRole.role_key == "visitor"))).scalars().first()
    if role:
        return role
    role = SysRole(
        role_name="访客",
        role_key="visitor",
        role_sort=99,
        data_scope="1",
        menu_check_strictly=True,
        dept_check_strictly=True,
        status="0",
        del_flag="0",
    )
    db.add(role)
    await db.flush()
    print("  + 创建角色 visitor（游客，只读）")
    return role


async def _ensure_user(db, user_name: str, nick_name: str, role: SysRole) -> SysUser:
    """确保演示用户存在，并绑定指定角色"""
    existing = (await db.execute(select(SysUser).where(SysUser.user_name == user_name))).scalars().first()
    if existing:
        print(f"  = 用户 {user_name} 已存在（id={existing.user_id}），跳过创建")
        user_obj = existing
        # sys_user.create_time 没有 server_default，脚本建的账号这里会是 NULL，
        # 导致「学习统计 → 加入日期」空白。补一次即可（补过就不再动，保持幂等）
        if not user_obj.create_time:
            user_obj.create_time = datetime.now() - timedelta(days=45)
            print(f"    + 补充 {user_name} 的加入时间（45 天前）")
    else:
        user_obj = SysUser(
            user_name=user_name,
            nick_name=nick_name,
            password=hash_password(DEMO_PASSWORD),
            sex="0",
            status="0",
            del_flag="0",
            create_time=datetime.now() - timedelta(days=45),
        )
        db.add(user_obj)
        await db.flush()
        print(f"  + 创建用户 {user_name}（id={user_obj.user_id}，密码 {DEMO_PASSWORD}）")

    # 角色绑定（幂等）
    link = (await db.execute(
        select(SysUserRole).where(
            SysUserRole.user_id == user_obj.user_id,
            SysUserRole.role_id == role.role_id,
        )
    )).scalars().first()
    if not link:
        db.add(SysUserRole(user_id=user_obj.user_id, role_id=role.role_id))
        print(f"    + 绑定角色 {role.role_key} 给 {user_name}")
    return user_obj


async def _ensure_demo_bank(db, owner: SysUser, spec: dict) -> None:
    """确保某个演示题库存在（含其题目），已存在则跳过（幂等）"""
    existing = (await db.execute(
        select(QuestionBank).where(
            QuestionBank.user_id == owner.user_id,
            QuestionBank.bank_name == spec["name"],
        )
    )).scalars().first()

    if existing:
        count = len((await db.execute(
            select(QuestionMain.id).where(QuestionMain.bank_id == existing.id)
        )).scalars().all())
        print(f"  = 演示题库《{spec['name']}》已存在（id={existing.id}，题目数={count}），跳过创建")
        return

    bank = QuestionBank(
        bank_name=spec["name"],
        subject=spec["subject"],
        description=spec["description"],
        total_questions=0,
        status="0",
        user_id=owner.user_id,
        is_public=spec["is_public"],
    )
    db.add(bank)
    await db.flush()
    visibility = "私有" if spec["is_public"] == 1 else "公开"
    print(f"  + 创建{visibility}演示题库《{spec['name']}》（id={bank.id}，owner={owner.user_name}）")

    questions = spec["questions"]()
    sub_total = 0
    for idx, item in enumerate(questions, start=1):
        subs = item.get("subs") or []
        main = QuestionMain(
            bank_id=bank.id,
            question_type=item["type"],
            difficulty=1,
            question_text=item["text"],
            content=None,
            options=item.get("options"),
            answer=item.get("answer"),
            analysis=item.get("analysis"),
            has_sub_questions=1 if subs else 0,
            sort_order=idx,
            score=5,
            status="0",
        )
        db.add(main)
        await db.flush()

        for s_idx, sub in enumerate(subs, start=1):
            db.add(QuestionSub(
                main_id=main.id,
                question_text=sub["text"],
                question_type=sub["type"],
                options=sub.get("options"),
                answer=sub["answer"],
                analysis=sub.get("analysis"),
                sort_order=s_idx,
                score=sub.get("score", 2),
            ))
            sub_total += 1

    # 题目总数 = 状态正常的题目数
    await db.flush()
    total = len((await db.execute(
        select(QuestionMain.id).where(
            QuestionMain.bank_id == bank.id,
            QuestionMain.status == "0",
        )
    )).scalars().all())
    bank.total_questions = total
    extra = f"，含 {sub_total} 道子题" if sub_total else ""
    print(f"    + 写入 {total} 道题目{extra}")


# ========== 演示学习数据（user1 的「学习统计 / 错题本 / 斩题 / 收藏」） ==========
#
# 设计原则：**先生成答题流水，再从流水反推所有状态表**。
# 这样错题次数、最近出错时间、收藏题的练习次数全部由流水算出来，彼此自洽，
# 不会出现「错题本写着错了 5 次、流水里只查得到 2 次」这种穿帮。
#
# 幂等策略：每次执行先清空 user1 的学习行为数据，再按固定随机种子重建，
# 因此重复运行结果完全一致（不会累积）。只动 user1，不碰题库与分享记录。

# 最近 14 天的做题计划：(几天前, 答对数, 答错数)
# 刻意留出 3 天空档（14/11/8/4 天前没做题），让「连续学习天数」是个真实算得出来的数字
STUDY_PLAN = [
    (13, 6, 5), (12, 7, 4),
    (10, 8, 4), (9, 9, 3),
    (7, 10, 3), (6, 11, 2),
    (5, 11, 3),
    (3, 12, 2), (2, 13, 2), (1, 14, 1), (0, 12, 1),
]

# 练习池中这些下标的目标答错次数（合计 30，与 STUDY_PLAN 里的答错总数严格一致）
WRONG_TARGET = {0: 6, 1: 5, 2: 5, 3: 4, 4: 4, 5: 3, 6: 3}

# 其中这两道「已经掌握」→ 写 is_mastered=1 / status=0，让掌握进度条不是干巴巴的 0%
MASTERED_INDEXES = [5, 6]

# 「已斩题」：挑没错过的题，语义上更说得通
MARKED_INDEXES = [12, 13, 14, 15, 16]

# 「收藏题目」
FAVORITE_INDEXES = [0, 1, 2, 3, 4, 12, 13, 14]

# 演示随机种子（固定 -> 每次生成的数据完全一致）
DEMO_STUDY_SEED = 20260912

# 演示笔记（「我的积累」里的笔记数，内容与演示题库主题对应）
NOTE_CATEGORY_NAME = "学习笔记"
DEMO_NOTES = [
    (
        "栈与队列的区别",
        "栈：只允许在一端（栈顶）插入和删除，后进先出（LIFO）。\n"
        "队列：队尾插入、队头删除，先进先出（FIFO）。\n"
        "记忆点：栈像一摞盘子，队列像排队打饭。",
    ),
    (
        "TCP 三次握手为什么不能是两次",
        "两次无法确认客户端的接收能力，也挡不住「历史失效的连接请求」突然到达服务端。\n"
        "三次握手：SYN → SYN+ACK → ACK，双方都确认了「我能发、你也能收」。",
    ),
    (
        "常见排序算法对比",
        "冒泡 / 插入：O(n²)，稳定；\n"
        "快速排序：平均 O(n log n)，不稳定，最坏退化 O(n²)；\n"
        "归并排序：O(n log n)，稳定，但需要额外空间。",
    ),
]


def _time_on(day, rng) -> datetime:
    """把「有学习活动的某一天」变成当天的一个具体时刻（09:00-21:59）"""
    return datetime(day.year, day.month, day.day, rng.randint(9, 21), rng.randint(0, 59))


async def _clear_study_data(db, user_id: int) -> None:
    """清空某个用户的学习行为数据（不碰题库/分享）"""
    for model, label in [
        (UserPracticeLog, "答题流水"),
        (UserQuestionError, "错题记录"),
        (UserQuestionMarked, "斩题记录"),
        (UserQuestionFavorite, "题目收藏"),
        (UserBankFavorite, "题库收藏"),
    ]:
        res = await db.execute(delete(model).where(model.user_id == user_id))
        if res.rowcount:
            print(f"    - 清理旧{label} {res.rowcount} 条")

    # 笔记只清「演示分类」下的，避免误删用户在演示过程中真正写下的笔记
    cat_id = await db.scalar(select(NoteCategory.id).where(
        NoteCategory.user_id == user_id,
        NoteCategory.name == NOTE_CATEGORY_NAME,
    ))
    if cat_id:
        note_id_query = select(Note.note_id).where(
            Note.user_id == user_id, Note.category_id == cat_id)
        # 先删子表，避免 note_question_bank / note_question / 收藏 / 评论的外键阻塞
        for child_model, label in [
            (NoteQuestionBank, "笔记-题库关联"),
            (NoteQuestion, "笔记-题目关联"),
            (UserNoteFavorite, "笔记收藏"),
            (NoteComment, "笔记评论"),
        ]:
            child_res = await db.execute(delete(child_model).where(
                child_model.note_id.in_(note_id_query)))
            if child_res.rowcount:
                print(f"    - 清理旧{label} {child_res.rowcount} 条")

        res = await db.execute(delete(Note).where(
            Note.user_id == user_id, Note.category_id == cat_id))
        if res.rowcount:
            print(f"    - 清理旧笔记 {res.rowcount} 条")


async def _pick_favorite_banks(db, owner_id: int, limit: int = 4):
    """挑几个「其它科目」的公开题库给 user1 收藏

    目的是让「科目分布」环形图有多个扇区（只收藏自己的两个题库会全是计算机类目）。
    """
    rows = (await db.execute(
        select(QuestionBank.id, QuestionBank.subject)
        .select_from(QuestionBank.__table__.join(
            QuestionMain.__table__, QuestionMain.bank_id == QuestionBank.id))
        .where(
            QuestionBank.is_public == 0,       # 0=公开，别人能收藏
            QuestionBank.user_id != owner_id,  # 演示「收藏别人的题库」
        )
        .group_by(QuestionBank.id, QuestionBank.subject)
        .having(func.count(QuestionMain.id) > 0)
    )).all()

    picked, seen_subjects = [], set()
    for bid, subject in rows:
        key = subject or "未分类"
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        picked.append((bid, key))
        if len(picked) >= limit:
            break
    return picked


async def _seed_study_data(db, user1: SysUser) -> None:
    """为 user1 生成一套自洽的学习行为演示数据"""
    uid = user1.user_id
    rng = random.Random(DEMO_STUDY_SEED)
    now = datetime.now()

    # ---------- 1. 准备练习题库（user1 名下两个演示题库的题目） ----------
    bank_rows = (await db.execute(
        select(QuestionBank.id).where(QuestionBank.user_id == uid)
    )).scalars().all()
    if not bank_rows:
        print("  ! user1 名下没有题库，跳过学习数据生成（请先完成题库初始化）")
        return

    pool = []
    for b_row in (await db.execute(
        select(QuestionMain.id, QuestionMain.bank_id)
        .where(QuestionMain.bank_id.in_(bank_rows))
        .order_by(QuestionMain.bank_id, QuestionMain.sort_order, QuestionMain.id)
    )).all():
        pool.append((b_row[0], b_row[1]))

    if len(pool) < 18:
        print(f"  ! 练习题目只有 {len(pool)} 道（少于 18），跳过学习数据生成")
        return
    pool = pool[:18]

    # ---------- 2. 清掉旧的学习数据（幂等） ----------
    await _clear_study_data(db, uid)

    # ---------- 3. 生成答题流水 ----------
    # 先把「答错次数」摊平成队列：把每道题要错几次展开，再打散到各天
    wrong_queue = []
    for idx, cnt in WRONG_TARGET.items():
        wrong_queue += [idx] * cnt
    rng.shuffle(wrong_queue)

    logs = []          # [(池下标, 是否答对, 时间)]
    w_cursor = 0
    for days_ago, n_correct, n_wrong in STUDY_PLAN:
        day_wrongs = wrong_queue[w_cursor: w_cursor + n_wrong]
        w_cursor += n_wrong

        day_items = [(i, 0) for i in day_wrongs]
        # 当天答对的题不与答错的重复（同一题一天内只做一次，更好理解）
        avail = [i for i in range(len(pool)) if i not in set(day_wrongs)]
        day_items += [(i, 1) for i in rng.sample(avail, n_correct)]
        rng.shuffle(day_items)

        if days_ago == 0:
            # 今天：从「现在」往前排，保证时间都在过去
            cnt = len(day_items)
            times = [now - timedelta(minutes=(cnt - i) * 4) for i in range(cnt)]
        else:
            day_start = (now - timedelta(days=days_ago)).replace(
                hour=rng.randint(9, 15), minute=rng.randint(0, 50), second=0, microsecond=0)
            times, t = [], day_start
            for _ in day_items:
                t = t + timedelta(minutes=rng.randint(3, 9), seconds=rng.randint(0, 59))
                times.append(t)

        for (idx, is_correct), t in zip(day_items, times):
            qid, qbid = pool[idx]
            logs.append((idx, is_correct, t))
            db.add(UserPracticeLog(
                user_id=uid, question_id=qid, bank_id=qbid,
                is_correct=is_correct, answer="（演示数据）", create_time=t,
            ))

    await db.flush()
    print(f"    + 答题流水 {len(logs)} 条（覆盖 {len(STUDY_PLAN)} 天）")

    # 「真正做过题的日子」——后面斩题/收藏的时间也从这些天里挑，
    # 否则会给没做题的那几天凭空添上"学习活动"，把「学习天数 / 连续学习」算虚。
    active_days = sorted({t.date() for _, _, t in logs}, reverse=True)

    # ---------- 4. 由流水反推每道题的统计 ----------
    stat = {}   # idx -> {correct, error, first_err, last_err, last_any}
    for idx, is_correct, t in logs:
        s = stat.setdefault(idx, {"correct": 0, "error": 0,
                                  "first_err": None, "last_err": None, "last_any": t})
        s["last_any"] = max(s["last_any"], t)
        if is_correct:
            s["correct"] += 1
        else:
            s["error"] += 1
            s["first_err"] = t if s["first_err"] is None else min(s["first_err"], t)
            s["last_err"] = t if s["last_err"] is None else max(s["last_err"], t)

    # ---------- 5. 错题本（次数与时间全部来自流水） ----------
    err_count = 0
    for idx, s in stat.items():
        if s["error"] <= 0:
            continue
        qid, qbid = pool[idx]
        mastered = 1 if idx in MASTERED_INDEXES else 0
        db.add(UserQuestionError(
            user_id=uid, question_id=qid, bank_id=qbid,
            error_count=s["error"],
            error_time=s["first_err"],
            last_error_time=s["last_err"],
            difficulty_rating=3,
            status=0 if mastered else 1,
            is_mastered=mastered,
            notes="（演示数据）易错题，建议重点复习",
            create_time=s["first_err"],
        ))
        err_count += 1
    print(f"    + 错题记录 {err_count} 条（其中 {len(MASTERED_INDEXES)} 条已掌握）")

    # ---------- 6. 斩题 ----------
    for idx in MARKED_INDEXES:
        qid, qbid = pool[idx]
        s = stat.get(idx, {"correct": 0, "error": 0})
        db.add(UserQuestionMarked(
            user_id=uid, question_id=qid, bank_id=qbid,
            marked_type=1, difficulty_level=3,
            error_times_before_mark=s["error"], correct_times_before_mark=s["correct"],
            marked_status=1, is_mastered=1,
            create_time=_time_on(rng.choice(active_days), rng),
        ))
    print(f"    + 斩题记录 {len(MARKED_INDEXES)} 条")

    # ---------- 7. 收藏题目（练习次数同样来自流水） ----------
    for idx in FAVORITE_INDEXES:
        qid, qbid = pool[idx]
        s = stat.get(idx, {"correct": 0, "error": 0, "last_any": now})
        db.add(UserQuestionFavorite(
            user_id=uid, question_id=qid, bank_id=qbid,
            favorite_status=1, is_starred=rng.choice([0, 1]),
            correct_times=s["correct"], error_times=s["error"],
            review_count=s["correct"] + s["error"],
            last_review_time=s["last_any"],
            create_time=_time_on(rng.choice(active_days), rng),
        ))
    print(f"    + 收藏题目 {len(FAVORITE_INDEXES)} 条")

    # ---------- 8. 收藏题库（多个科目 -> 科目分布图有多个扇区） ----------
    fav_banks = await _pick_favorite_banks(db, uid)
    for bid, subject in fav_banks:
        t = _time_on(rng.choice(active_days), rng)
        db.add(UserBankFavorite(
            user_id=uid, bank_id=bid,
            favorite_status=1, is_starred=0,
            study_count=rng.randint(1, 5),
            last_study_time=t,
            create_time=t,
        ))
        print(f"      · 收藏题库 id={bid}（科目：{subject}）")
    print(f"    + 收藏题库 {len(fav_banks)} 个")

    # ---------- 9. 把演示题库的题目难度铺成三档 ----------
    # 题库初始化时 difficulty 统一写 1，「错题诊断 → 按难度」只有一档、图很单薄
    await db.execute(
        update(QuestionMain)
        .where(QuestionMain.bank_id.in_(bank_rows))
        .values(difficulty=func.mod(QuestionMain.sort_order, 3) + 1)
    )
    print("    + 演示题库题目难度已铺成 1/2/3 三档")

    # ---------- 10. 笔记（「我的积累 → 笔记」这一格） ----------
    # 注意 note.category_id 在库中是 NOT NULL，必须先有分类
    cat = (await db.execute(select(NoteCategory).where(
        NoteCategory.user_id == uid,
        NoteCategory.name == NOTE_CATEGORY_NAME,
    ))).scalars().first()
    if not cat:
        cat = NoteCategory(user_id=uid, name=NOTE_CATEGORY_NAME, order_num=0)
        db.add(cat)
        await db.flush()

    for title, content in DEMO_NOTES:
        db.add(Note(
            user_id=uid, category_id=cat.id,
            title=title, content=content, markdown_content=content,
            tags="演示", is_public=0, status="published", del_flag="0",
            create_time=_time_on(rng.choice(active_days), rng),
        ))
    print(f"    + 笔记 {len(DEMO_NOTES)} 条（分类：{NOTE_CATEGORY_NAME}）")

    total_practice = len(logs)
    total_correct = sum(1 for _, c, _ in logs if c)
    rate = round(total_correct / total_practice * 100, 1) if total_practice else 0
    print(f"    => 共作答 {total_practice} 次，答对 {total_correct} 次，正确率 {rate}%")


async def _sync_all_sequences(db) -> None:
    """把所有表的自增序列同步到「当前最大 ID」。

    ⚠️ 为什么必须做：部署 SQL（pg_dump 导出）用**显式 ID** INSERT 了种子数据
    （如 sys_user 插了 id=1/2），但**没有同步序列**（setval）。于是序列仍停在初始值，
    后续脚本/接口用 nextval 取 ID 时会从头开始 → 撞已有主键
    （典型报错：`duplicate key value violates unique constraint "sys_user_pkey"`）。

    这里遍历所有含序列的表，用 pg_get_serial_sequence 找到其序列，
    统一 setval 到 max(id)。仅 PostgreSQL 需要；MySQL 直接跳过。
    幂等：重复执行结果一致，不会破坏数据。
    """
    from app.config import settings

    if not settings.IS_POSTGRES:
        return

    rows = (await db.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND column_default LIKE 'nextval(%'"
    ))).all()

    fixed = 0
    for table_name, column_name in rows:
        try:
            # pg_get_serial_sequence 需要带 schema 的标识符字符串
            await db.execute(text(
                f"SELECT setval("
                f"  pg_get_serial_sequence('public.{table_name}', '{column_name}'),"
                f"  COALESCE((SELECT MAX({column_name}) FROM public.{table_name}), 0) + 1,"
                f"  false)"
            ))
            fixed += 1
        except Exception as e:  # pragma: no cover - 个别表异常不应中断整体
            await db.rollback()
            print(f"    ! 跳过 {table_name}.{column_name}（{e}）")
    await db.commit()
    print(f"  + 已同步 {fixed} 个自增序列到各表当前最大 ID")


async def seed_demo():
    # 先确保所有表存在（含分享/通知等新表），create_all 幂等、不会删数据
    await init_db()

    async with async_session_factory() as db:
        print("=" * 60)
        print("开始初始化演示数据 ...")
        print("=" * 60)

        print("[0/5] 同步自增序列（修复 SQL 导入后序列未对齐导致的主键冲突）")
        await _sync_all_sequences(db)

        print("[1/5] 演示角色（common / visitor）")
        role = await _get_or_create_common_role(db)
        visitor_role = await _get_or_create_visitor_role(db)

        print("[2/5] 演示用户 user1 / user2 / guest")
        user1 = await _ensure_user(db, "user1", "演示用户1", role)
        user2 = await _ensure_user(db, "user2", "演示用户2", role)
        await _ensure_user(db, "guest", "游客", visitor_role)

        print("[3/5] 演示题库（user1 名下 2 个：私有 1 个 + 公开 1 个）")
        for spec in DEMO_BANKS:
            await _ensure_demo_bank(db, user1, spec)

        print("[4/5] user1 的学习行为数据（学习统计 / 错题本 / 斩题 / 收藏）")
        await _seed_study_data(db, user1)

        print("[5/5] 管理员账号（一键登录用，不修改已有密码）")
        admin = (await db.execute(select(SysUser).where(SysUser.user_name == "admin"))).scalars().first()
        if admin:
            print(f"  = admin 已存在（id={admin.user_id}），保持原密码不变")
        else:
            print("  ! 未找到 admin 账号，请先执行 init_data.py")

        await db.commit()

        print("=" * 60)
        print("演示数据准备完成！")
        print("-" * 60)
        print("  登录页「一键登录」入口：")
        print("    演示用户1  ->  user1  （2 个题库：私有 10 题 + 公开 8 题；已有完整学习统计）")
        print("    演示用户2  ->  user2  （接收方，无题库，领取分享后进「题库收藏」）")
        print("    游客       ->  guest  （只读浏览；刷题 / 写笔记 / 点赞等操作会提示登录）")
        print("    管理员     ->  admin  （进入后台管理）")
        print("-" * 60)
        print("  用 user1 登录后可直接演示：")
        print("    · 我的学习 → 学习统计   正确率环形图 / 7 天趋势 / 科目分布 / 错题诊断")
        print("    · 我的学习 → 我的错题   含 2 道「已掌握」，可演示掌握进度")
        print("    · 我的学习 → 我的斩题 / 题目收藏 / 题库收藏（多科目）")
        print("-" * 60)
        print(f"  普通账号密码（如需手动登录）：user1 / {DEMO_PASSWORD} ，user2 / {DEMO_PASSWORD}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_demo())
