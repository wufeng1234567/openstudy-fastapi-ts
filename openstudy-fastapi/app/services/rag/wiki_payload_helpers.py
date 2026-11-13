"""知识百科页面生成用的常量与纯辅助函数。

从 ``wiki_service.py`` 抽出的低风险部分：模块级常量、学习态快照计算、
关系类型映射、图片资产键解析。不连数据库、不调用模型，只依赖标准库。

``wiki_service.py`` 会把这些名字重新导入到自己的模块命名空间，因此
``tests/test_wiki_service.py`` / ``tests/test_learning_route_service.py``
从 ``app.services.rag.wiki_service`` 导入 ``build_learning_snapshot``、
``_asset_source_ref`` 等既有写法保持不变。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


#: 每个主题页最多取多少条来源 chunk；足够形成要点，又不会撑爆模型上下文。
MAX_SOURCE_CHUNKS = 12
#: 单次接口最多生成多少页，避免一个请求把模型额度打穿。
DEFAULT_BUILD_LIMIT = 30
#: 单页最多保留多少个正文小节。
MAX_SECTIONS = 6
#: 单节正文上限（字符）。
MAX_SECTION_CHARS = 1600
#: 页面状态。
WIKI_DRAFT = "draft"
WIKI_READY = "ready"
WIKI_STALE = "stale"
WIKI_FAILED = "failed"

_SOURCE_TYPES = {"包含", "属于", "定义", "推导", "应用", "前置", "对比", "相关", "产生", "属于领域"}


#: 学习态标签；前端只认 level，label 作为无障碍/提示文案。
LEARNING_LABELS = {
    "unread": "未学习",
    "reading": "已阅读",
    "practicing": "练习中",
    "mastered": "已掌握",
}


#: 这些关系更像“目录/结构”，不应作为页面里最重要的“洞察”反复出现。
_GENERIC_RELATIONS = {"包含", "属于", "定义", "相关"}

#: 实体类型 → 主题页类型。前端按 pageType 上色（摘要/实体/概念/综合/对比）。
_ENTITY_PAGE_TYPES = {
    "人物": "entity",
    "机构": "entity",
    "事件": "entity",
    "作品": "entity",
    "其他": "entity",
    "概念": "concept",
    "定理/公式": "concept",
    "方法": "concept",
    "术语": "concept",
    "变量/符号": "concept",
}


def build_learning_snapshot(
    *,
    view_count: int = 0,
    practice_count: int = 0,
    correct_count: int = 0,
    last_view_time: Optional[datetime] = None,
    last_practice_time: Optional[datetime] = None,
) -> dict:
    """把阅读次数与练习结果折成可解释的学习态。

    不存“掌握度”字段，全部按事实实时算，避免练习记录更新后图谱还是旧状态：
      · 阅读只给基础分 25；
      · 练习按正确率给分，并用练习量做成熟度折扣（1 题不会直接满分）；
      · 只有练过且总分 ≥ 80 才标记“已掌握”。
    """
    views = max(0, int(view_count or 0))
    practices = max(0, int(practice_count or 0))
    correct = max(0, min(practices, int(correct_count or 0)))
    accuracy = round(correct / practices * 100, 1) if practices else 0.0
    read_score = 25 if views > 0 else 0
    if practices:
        volume = min(1.0, 0.4 + practices / 5 * 0.6)
        practice_score = round((25 + 50 * (correct / practices)) * volume)
        score = min(100, read_score + practice_score)
        level = "mastered" if score >= 80 else "practicing"
    elif views:
        score = read_score
        level = "reading"
    else:
        score = 0
        level = "unread"

    times = [value for value in (last_view_time, last_practice_time) if value is not None]
    last_activity = max(times) if times else None
    return {
        "viewCount": views,
        "practiceCount": practices,
        "correctCount": correct,
        "wrongCount": max(0, practices - correct),
        "accuracy": accuracy,
        "masteryScore": score,
        "level": level,
        "label": LEARNING_LABELS[level],
        "lastViewTime": last_view_time.isoformat(sep=" ") if last_view_time else None,
        "lastPracticeTime": last_practice_time.isoformat(sep=" ") if last_practice_time else None,
        "lastActivityTime": last_activity.isoformat(sep=" ") if last_activity else None,
    }


def _link_type_for_relation(relation_type: str) -> str:
    if relation_type == "前置":
        return "prerequisite"
    if relation_type == "对比":
        return "contrast"
    if relation_type in {"属于", "包含", "定义"}:
        return "part_of"
    return "related"


def _asset_source_ref(asset_key: str) -> tuple[str, int, Optional[str]]:
    key = str(asset_key or "").strip()
    if key.startswith("doc:"):
        parts = key.split(":")
        if len(parts) >= 3 and parts[1].isdigit():
            return "document_image", int(parts[1]), parts[2]
    if key.startswith("chat:"):
        tail = key.rsplit(":", 1)[-1]
        if tail.isdigit():
            return "chat_image", int(tail), None
    raise ValueError("不支持的图片资产键")
