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
from typing import Dict, Iterable, List, Tuple

#: 路由兜底角色名（不确定时用它）。**必须**存在于 `OFFICIAL_ROLES`。
GENERAL_ROLE = "general"

#: **全局默认工具** —— 不绑定任何角色，而是自动叠加到**每一个**角色（含用户自定义智能体）之上。
#:
#: 为什么单独抽出来（2026-10-09 用户裁决）：记忆（`memory_search` / `memory_manage`）是
#: **跨角色的通用能力** —— 无论当前是题库/笔记/知识库/统计哪个助手，用户都可能说"记住这个"
#: 或"我之前说过什么"。把它作为一个可选角色（原"记忆助手"）既要求用户去选、又会让
#: 「记住」这类请求被路由走、离开当前业务语境。因此改为**全局默认**：对用户隐藏、
#: 对模型始终可见。
#:
#: 语义：`最终可用 = (角色白名单 ∪ 全局工具) ∩ (全部 − 用户屏蔽)`
#: —— 见 `orchestrator.compute_exclude` 的落地。
GLOBAL_TOOLS: Tuple[str, ...] = (
    "memory_search",
    "memory_manage",
)

#: **指挥家专属的元工具**名（`delegate_task`）。它**不属于任何子代理**，也**不参与**
#: 角色白名单换算 —— `orchestrator.compute_exclude` 会永远把它排除，只有指挥家模式由
#: `loop` 单独挂上（`registry.definitions` 里虽然有它，但被 exclude 挡住，子代理拿不到）。
#: 目的：从根上杜绝「子代理再委派」的递归。
DELEGATE_TOOL_NAME = "delegate_task"


@dataclass(frozen=True)
class RoleSpec:
    """一个官方智能体（在本架构里 = 一个**可被指挥家调用的子代理**）的定义

    Attributes:
        key: 角色标识（前端传 `role` 用的值；snake_case）。
        name: 界面上显示的中文名（**只给前端**）。
        description: 界面用的一句话说明（**只给前端**）。
        tools: 该子代理**允许使用**的工具名白名单。空元组 = 不做限制（等价于全部工具）。
        capability: **给指挥家看的能力摘要**（英文）：一句话回答"什么时候该把任务派给我"。
                    会被拼进指挥家的系统提示词（子代理通讯录），是指挥家路由决策的依据。
        persona: **子代理自己的系统人设**（英文，第一人称）：回答"我是谁、我负责什么、
                 我不负责什么"。当指挥家把任务派给它时，用它作为该子代理的系统提示词。
        prompt_fragment: 追加到系统提示词的**英文**角色专属指令（旧字段，保留兼容；
                         用于"用户显式选择、子代理直接面向用户"时的补充说明）。
        keywords: 规则路由关键词（**小写**）：用户在消息里命中任一即倾向选此角色。
                  中文词直接写中文（用户输入就是中文）；英文词写小写（匹配前会 lower）。
    """

    key: str
    name: str
    description: str
    tools: Tuple[str, ...]
    capability: str = ""
    persona: str = ""
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
    # ⚠️ `knowledge_search` 是**只读**检索工具，这里挂给题库专家，是为了打通
    #    「基于我的资料出题」：用户说「根据我上传的《计算机网络》出题」时，专家
    #    要能先去知识库取原文，再据此出题（而不是凭模型记忆编）。
    #    它不会让题库专家变成「知识库管理」角色 —— 建库/传资料仍是 kb 专家的职责，
    #    这里只借「检索」这一只读能力。
    "bank": RoleSpec(
        key="bank",
        name="题库专家",
        description=(
            "帮你建题库、导入题目、改题删题，也能整理错题本和收藏，还能根据你的资料出题，"
            "以及把题库导出成 Word / PDF 试卷"
        ),
        tools=(
            "bank_manage",
            "question_manage",
            "question_flag_manage",
            "knowledge_search",
            # 2026-10-22 工作空间：用户说「用我空间里那份 XX 资料出题」时，
            # 先用 workspace_search 把**文件**找出来（返回 docId），
            # 再用 knowledge_search 读正文。少这一步，模型只能瞎猜是哪份。
            "workspace_search",
            # 2026-10-20：导出是**题库域**最常用的收尾动作（「出完题，导出来发给我」）。
            # 不挂在这里的话，用户必须换到「通用」角色才导得出，而路由是按关键词走的 ——
            # 消息里只要带「题库」二字就会被路由到 bank 角色，于是「导出题库」永远够不着导出工具。
            "bank_export",
        ),
        capability=(
            "Question banks and questions. Use it when the user wants to: create or "
            "rename a bank, add / edit / delete questions, import a batch of questions "
            "(from text or an uploaded file/image), or tidy up their wrong-question "
            "book, favourites and 'to-conquer' marks. ALSO use it when the user wants "
            "questions generated FROM THEIR OWN MATERIALS — e.g. 'make questions based "
            "on my textbook', 'use the document I uploaded', '出题 based on my knowledge "
            "base'. In that case first call `knowledge_search` to pull the source "
            "passages, then build the questions from that text (never from memory). "
            "ALSO use it when the user wants a bank EXPORTED as a Word/PDF file "
            "('导出这个题库', '生成试卷', '给我一份打印版', '发一份无答案的给学生') — that is "
            "`bank_export`."
        ),
        persona=(
            "You are the Question Bank Specialist of OpenStudy. You manage the user's "
            "question banks and questions: create/list/rename/delete banks, add/edit/"
            "delete/batch-import questions, and manage their wrong-question book, "
            "favorites and marked questions. "
            "When the user wants questions based on THEIR OWN MATERIALS (a textbook, an "
            "uploaded document, their knowledge base), you MUST first use "
            "`knowledge_search` to retrieve the relevant passages and then generate the "
            "questions from that retrieved text — you must NOT invent questions from "
            "memory. Quote the source (document name + section) so the user can verify. "
            "If `knowledge_search` returns nothing relevant, say so plainly instead of "
            "fabricating. "
            "You do NOT handle notes, study statistics or memory — those belong to other "
            "specialists. Note: creating/ingesting new knowledge bases is NOT your job "
            "(that is the knowledge-base specialist); you only READ from existing ones. "
            "Before creating or importing, make sure the target bank is known (ask or "
            "list first). Prefer one bulk call over many single calls."
        ),
        prompt_fragment=(
            "## Role: Question Bank Assistant\n"
            "You are specialised in managing the user's question banks and questions. "
            "When the user asks for questions based on their own materials (textbook / "
            "uploaded file / knowledge base), FIRST call `knowledge_search` to get the "
            "source passages, then generate questions from that text and cite the source; "
            "never fabricate. Before creating or importing, make sure you know the target "
            "bank (ask or list first). Prefer bulk actions over many single calls."
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
        name="笔记专家",
        description="帮你写笔记、改笔记、给笔记归类，还能把笔记挂到题目上",
        tools=("note_manage",),
        capability=(
            "Study notes. Use it when the user wants to write something down, tidy up "
            "or reorganise their notes, look them up, or link a note to a question."
        ),
        persona=(
            "You are the Note Specialist of OpenStudy. You help the user create, edit, "
            "organise and link study notes. Keep note content faithful to what the user "
            "provides — do not invent facts. You do NOT handle question banks, knowledge "
            "bases or statistics."
        ),
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
        name="知识库专家",
        description="帮你建知识库、把资料（文字或文件）存进去，也能在里面查东西",
        tools=(
            "knowledge_search",
            "knowledge_ingest",
            "knowledge_base_manage",
            # 2026-10-22：知识库专家也要能「先找文件再处理」——
            # 用户说「把我空间里那份资料存进知识库」时用得上
            "workspace_search",
        ),
        capability=(
            "Knowledge bases (collections of the user's own material). Use it when the "
            "user wants to create a knowledge base, save some text or a file into it so "
            "it becomes searchable, or look something up inside it. Saving takes a "
            "moment to process in the background, so a just-saved item is not searchable "
            "immediately."
        ),
        persona=(
            "You are the Knowledge Base Specialist of OpenStudy. You manage the user's "
            "knowledge bases (document collections): create/list/delete bases, ingest "
            "text or attachments as searchable documents, and search inside them with "
            "`knowledge_search`. Saving a document triggers background vectorisation, so "
            "tell the user it is still being processed. You do NOT handle the question "
            "bank or notes."
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
    # ---- 记忆：不是角色，而是**全局默认工具**（见下面 GLOBAL_TOOLS）----
    # 历史：这里曾有一个 "memory" 独立角色（记忆助手），工具 = memory_search/memory_manage。
    # 2026-10-09 用户裁决：记忆能力应当**每个助手都有**、对用户**隐藏**、作为默认工具全局使用，
    # 而不是让用户去选一个"记忆助手"。于是删除该角色，把这两个工具提到 GLOBAL_TOOLS，
    # 由编排层自动叠加到**所有**角色（含用户自定义智能体）之上。
    # ---- 统计域 ----
    "stats": RoleSpec(
        key="stats",
        name="学习统计专家",
        description="帮你看学习数据：错题多少、正确率、掌握情况，以及题库分享记录",
        # ⚠️ 2026-10-17 补 `question_flag_manage`：
        #    `learning_stats` 只给**汇总数字**（总数 / 掌握率 / 按难度分布），
        #    要列"具体哪几道错题"必须走 `question_flag_manage`（flag_type=error）。
        #    之前这里只配了两个工具，于是用户让它"分析我的错题"时，它手里没有任何
        #    能读错题清单的工具，只能回一句"我没有错题本相关权限"——看起来像权限 bug，
        #    实际是**角色工具白名单缺项**。
        #    白名单是"允许用"，不是"必须用"：这里只放开读，写操作由下面的 persona 约束。
        tools=("learning_stats", "bank_share_manage", "question_flag_manage"),
        capability=(
            "The user's own learning numbers and sharing records. Use it for questions "
            "like 'how am I doing', 'how many did I get wrong', 'what's my accuracy', "
            "'which questions did I get wrong', or 'who shared a bank with me / what did "
            "I share'."
        ),
        persona=(
            "You are the Learning Analytics Specialist of OpenStudy. You report the "
            "user's learning statistics (wrong-question counts, mastery rate, difficulty "
            "breakdown) and bank-share status. Report numbers plainly; do not draw "
            "conclusions the data does not support. "
            "For headline numbers use `learning_stats` (error_analysis / by_subject / "
            "trend / overview). To list the ACTUAL wrong / favourite / marked questions "
            "use `question_flag_manage` with flag_type=error / favorite / marked and "
            "action=list or detail - that tool is READ-ONLY for you: never call its "
            "create / update / remove actions, and never modify the user's data. "
            "You do NOT edit banks or notes."
        ),
        prompt_fragment=(
            "## Role: Learning Stats Assistant\n"
            "You are specialised in the user's learning statistics (wrong-question "
            "counts, mastery rate, difficulty breakdown) and bank-share status. Report "
            "numbers plainly; do not draw conclusions the data does not support.\n"
            "Numbers come from `learning_stats`; the concrete question list comes from "
            "`question_flag_manage` (flag_type=error|favorite|marked, action=list|detail). "
            "Treat that tool as read-only: never create / update / remove anything."
        ),
        keywords=(
            "统计", "多少题", "正确率", "掌握", "学习情况", "分享", "数据",
            "stats", "statistic", "report",
        ),
    ),
    # ---- 智能体域：对话式创建 / 管理用户自己的智能体 ----
    # 用户 2026-10-12：在智能体页面对话里说「帮我建一个数学老师」，由本专家调用
    # `agent_manage` 工具**按对话创建智能体**（名称 / 人设 / 工具白名单 / 模型）。
    "agent_builder": RoleSpec(
        key="agent_builder",
        name="智能体专家",
        description="帮你按对话创建智能体：起名字、写人设、配可用工具和模型，也能改删、查看",
        tools=("agent_manage",),
        capability=(
            "Creating and managing the user's OWN custom assistants (agents / personas). "
            "Use it when the user wants to build, design or set up a new assistant "
            "(e.g. 'make me a math-teacher assistant', 'create an assistant that only "
            "helps with notes'), change or delete an existing assistant, or list their "
            "assistants."
        ),
        persona=(
            "You are the Agent Builder of OpenStudy. You help the user design and create "
            "their OWN custom assistants: a name, an English persona/system prompt that "
            "defines the assistant's behaviour, a one-line intro, an optional greeting, a "
            "tool whitelist and an optional bound model. "
            "Ask for the essentials the user has not given yet (especially the NAME and "
            "what the assistant should do) before creating; write `persona_prompt` in "
            "English. Use `agent_manage` (actions: create / update / delete / list). "
            "Do NOT run other business tools (question banks, notes, knowledge bases) "
            "yourself — creating them is another expert's job."
        ),
        prompt_fragment=(
            "## Role: Agent Builder\n"
            "You design and create the user's custom assistants via `agent_manage`. Ask "
            "for the name and purpose first, and write the persona prompt in English."
        ),
        keywords=(
            "智能体", "助手", "人设", "角色", "创建智能体", "建一个助手", "做个助手",
            "自定义助手", "agent", "assistant", "persona",
        ),
    ),
    # ---- 兜底：通用助手（全工具）----
    # ⚠️ 指挥家模式下，它同时是「指挥家自己的身份」：指挥家默认用通用工具直接答，
    #    只在明确属于某专家时才委派。`tools=()` = 不做白名单限制 = 全部工具。
    "general": RoleSpec(
        key="general",
        name="智能助手",
        description="主助手（指挥家），什么都能聊，需要时会请对应的专家帮忙",
        tools=(),
        capability="",
        persona="",
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


def renderable_sub_agents(disabled_keys: Iterable[str] = ()) -> List[RoleSpec]:
    """**可被指挥家委派的子代理**：有 `capability` 的角色（`general` 排除——指挥家自身）。

    顺序按 `OFFICIAL_ROLES` 声明顺序，稳定可测。

    Args:
        disabled_keys: 用户**已关闭**的专家 key 集合 —— 这些专家不列入（也不可被委派）。
    """
    closed = {str(k) for k in disabled_keys}
    return [r for r in OFFICIAL_ROLES.values() if r.capability and r.key not in closed]


def render_sub_agents_briefing(
    extra_agents: List[Dict[str, str]] | None = None,
    disabled_keys: Iterable[str] = (),
) -> str:
    """渲染「子代理通讯录」文本，供指挥家的系统提示词使用

    每行形如：`- bank (题库助手): <capability>`

    Args:
        extra_agents: 额外要列入的**用户自定义智能体**（运行时从 DB 读）。
                      每项 `{"key": "user:12", "name": "数学老师", "capability": "..."}`。
                      传 None / 空则只列官方子代理。
        disabled_keys: 用户**已关闭**的专家 key 集合 —— 被关闭的**官方专家**不列入通讯录，
                      于是 LLM 实时知道"这个专家叫不到"（用户 2026-10-10 要求）。

    Returns:
        多行文本（每行一个子代理）。指挥家靠它决定"派给谁"。
    """
    lines: List[str] = []
    for r in renderable_sub_agents(disabled_keys=disabled_keys):
        lines.append(f"- {r.key} ({r.name}): {r.capability}")
    for a in extra_agents or []:
        key = str(a.get("key") or "").strip()
        if not key:
            continue
        name = str(a.get("name") or key).strip()
        cap = str(a.get("capability") or "").strip() or "(user-defined custom assistant)"
        lines.append(f"- {key} ({name}): {cap}")
    return "\n".join(lines)


__all__ = [
    "GENERAL_ROLE",
    "GLOBAL_TOOLS",
    "RoleSpec",
    "OFFICIAL_ROLES",
    "role_or_none",
    "all_role_metas",
    "renderable_sub_agents",
    "render_sub_agents_briefing",
]
