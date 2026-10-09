"""
官方智能体（Agent 角色）定义表 —— 「按系统功能域切分」的单一事实来源

背景：为什么要做角色切分
========================
原先是**一个 Agent 背着全部 11 个工具**。两个直接后果：

1. **费 token**：`registry.definitions()` 把 11 个工具的完整 JSON Schema 每轮发给模型，
   实测约 6,000 token；系统提示词里的工具清单（ds-free 路径）另算。
2. **易选错**：工具越多，模型挑错工具的概率越高（`question_mark_manage.py` 的模块
   docstring 里有一条亲身教训：「同一域 list/detail/create/update/delete 收进一个工具、
   用 action 区分」，理由正是「工具清单越长，模型选错的概率越高」）。

按「功能域」把工具切成几组，让**每个角色只挂自己那组**，上面两个问题同时缓解。

⚠️ 为什么是**代码常量表**、不是数据库表
=====================================
官方角色是**平台自研的产品定义**，应当与代码版本一起演进：
  · 若是 DB 表，代码升级（比如某工具改名 / 合并）后 DB 里还是旧工具集，
    会出现「提示词里写着 A、注册表里没有 A」的漂移；
  · 用户自定义智能体（那是用户数据，需要可增删改）才登记到
    `ai_agent_config` 表 —— 两张东西性质不同，别合并。

工具名必须与 `registry.names()` 完全一致
=======================================
下面 `tools` 里的每个字符串都会参与「白名单 → exclude」换算（见 `orchestrator.py`）。
写错一个名字不会报错，只会让那个工具**永远不可用**（被算进 exclude）。所以
`tests/_probe_agent_role.py` 有一条断言：**每个角色引用的工具名都必须存在于注册表**。
新增工具时若忘了加进任何角色，它只会在 `general` 里可用 —— 这也是刻意的（安全兜底）。

语言两条道（与工具契约同一条红线）
================================
  · `name` / `description` —— **中文**，只给前端渲染角色选择器看；
  · `prompt_fragment` —— **英文**，会被拼进**全英文的系统提示词**。
    ⚠️ 绝对不要在 `prompt_fragment` 里写中文：`tests/_toolpref_probe.py` 的 P11d
    会扫描系统提示词里的连续中文段，白名单里只有 4 个既有「中文数据」，新增即判红。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

#: 路由兜底角色名（不确定时用它）。**必须**存在于 `OFFICIAL_ROLES`。
GENERAL_ROLE = "general"


@dataclass(frozen=True)
class RoleSpec:
    """一个官方智能体的定义

    Attributes:
        key: 角色标识（前端传 `role` 用的值；snake_case）。
        name: 界面上显示的中文名（**只给前端**）。
        description: 界面用的一句话说明（**只给前端**）。
        tools: 该角色**允许使用**的工具名白名单。空元组 = 不做限制（等价于全部工具）。
        prompt_fragment: 追加到系统提示词的**英文**角色专属指令（可为空串）。
        keywords: 规则路由关键词（**小写**）：用户在消息里命中任一即倾向选此角色。
                  中文词直接写中文（用户输入就是中文）；英文词写小写（匹配前会 lower）。
    """

    key: str
    name: str
    description: str
    tools: Tuple[str, ...]
    prompt_fragment: str = ""
    keywords: Tuple[str, ...] = field(default_factory=tuple)


# ============================================================
# 官方角色表（单一事实来源）
# ============================================================
#
# 切分原则：按「系统功能域」而非「业务场景」。每个角色工具集尽量正交、不重叠，
# 这样「路由到谁」不改变能做的事（只是收窄了模型的选择空间），用户不会因为
# 路由结果不同而「这个功能突然没了」。
#
# ⚠️ 角色之间工具**可以**有少量重叠（如 stats 里也放 bank_share_manage），
#    但**不允许**出现「某工具在任何角色里都没有」—— 那它只剩 general 可用，
#    容易让普通用户以为功能坏了。每次新增工具都回来看一眼这张表。

OFFICIAL_ROLES: Dict[str, RoleSpec] = {
    # ---- 题库/题目域 ----
    "bank": RoleSpec(
        key="bank",
        name="题库助手",
        description="管理题库与题目：建库、增删改查题目、批量导入、题目标记",
        tools=(
            "bank_manage",
            "question_manage",
            "question_flag_manage",
        ),
        prompt_fragment=(
            "## Role: Question Bank Assistant\n"
            "You are specialised in managing the user's question banks and questions. "
            "Before creating or importing, make sure you know the target bank (ask or "
            "list first). Prefer bulk actions over many single calls."
        ),
        keywords=(
            "题库", "建库", "题目", "出题", "导题", "导入", "录题", "试卷", "刷题",
            "错题", "收藏", "斩题", "题目难",
            "bank", "question", "import", "exam", "quiz",
        ),
    ),
    # ---- 笔记域 ----
    "note": RoleSpec(
        key="note",
        name="笔记助手",
        description="管理学习笔记：新建、编辑、归类、关联题目",
        tools=("note_manage",),
        prompt_fragment=(
            "## Role: Note Assistant\n"
            "You are specialised in the user's study notes. Help create, edit, organise "
            "and link notes. Keep the note content faithful to what the user provides."
        ),
        keywords=("笔记", "note", "记录一下", "整理笔记"),
    ),
    # ---- 知识库域 ----
    "kb": RoleSpec(
        key="kb",
        name="知识库助手",
        description="管理知识库：建库、写入文档、检索资料",
        tools=(
            "knowledge_search",
            "knowledge_ingest",
            "knowledge_base_manage",
        ),
        prompt_fragment=(
            "## Role: Knowledge Base Assistant\n"
            "You are specialised in the user's knowledge bases (document collections). "
            "Search inside them with `knowledge_search`; to save content use "
            "`knowledge_ingest` (vectorisation runs in the background, so tell the user "
            "the document is still being processed)."
        ),
        keywords=(
            "知识库", "资料", "文档库", "存进", "存入", "检索", "查一下资料",
            "knowledge", "document",
        ),
    ),
    # ---- 记忆域 ----
    "memory": RoleSpec(
        key="memory",
        name="记忆助手",
        description="管理长期记忆：记住/回忆用户偏好与历史",
        tools=("memory_search", "memory_manage"),
        prompt_fragment=(
            "## Role: Memory Assistant\n"
            "You are specialised in the user's long-term memory. Use `memory_search` to "
            "recall and `memory_manage` to store or update preferences and facts the "
            "user wants remembered."
        ),
        keywords=("记住", "记忆", "之前说过", "我偏好", "回忆", "memory", "remember"),
    ),
    # ---- 统计域 ----
    "stats": RoleSpec(
        key="stats",
        name="学习统计助手",
        description="学习数据统计与题库分享情况",
        tools=("learning_stats", "bank_share_manage"),
        prompt_fragment=(
            "## Role: Learning Stats Assistant\n"
            "You are specialised in the user's learning statistics (wrong-question "
            "counts, mastery rate, difficulty breakdown) and bank-share status. Report "
            "numbers plainly; do not draw conclusions the data does not support."
        ),
        keywords=(
            "统计", "多少题", "正确率", "掌握", "学习情况", "分享", "数据",
            "stats", "statistic", "report",
        ),
    ),
    # ---- 兜底：通用助手（全工具）----
    # ⚠️ 路由不确定时**必须**退到这里（`tools=()` 表示不做白名单限制 = 全部工具），
    #    绝不能因为路由失败就让模型没有工具可用 —— 那比多花 token 严重得多。
    "general": RoleSpec(
        key="general",
        name="通用助手",
        description="通用助手，可使用全部工具（无法判断意图时的兜底）",
        tools=(),
        prompt_fragment="",
        keywords=(),
    ),
}


def role_or_none(key: str) -> RoleSpec | None:
    """按 key 取角色；不存在返回 None（调用方据此判断是否传入非法 role）。"""
    return OFFICIAL_ROLES.get(str(key or "").strip())


def all_role_metas() -> List[RoleSpec]:
    """全部角色（供前端渲染角色选择器；`general` 也在内）。"""
    return list(OFFICIAL_ROLES.values())


__all__ = [
    "GENERAL_ROLE",
    "RoleSpec",
    "OFFICIAL_ROLES",
    "role_or_none",
    "all_role_metas",
]
