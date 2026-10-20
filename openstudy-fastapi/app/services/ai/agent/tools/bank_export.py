"""
`bank_export` —— 把题库导出成 Word / PDF（Agent 自封装）

为什么需要它（2026-10-20，用户口径）
------------------------------------
导出功能此前**只存在于题库详情页的一个按钮上**：用户对着对话说「把这个题库导成
无答案的 Word 发给学生」，助手做不到 —— 它的工具清单里根本没有「导出」这件事。
于是「一切皆对话」在这里断掉了一环，而这恰恰是**最有演示价值**的一环（产物能被
Office / WPS 打开，评委一眼看得懂）。

本工具把 `bank_export_service.export_bank_docx / export_bank_pdf` 接进 Agent，
并额外把生成的文件**落盘**（`data/uploadPath/export/…`），回执里给一个可下载的
URL —— 这样对话里的产物卡片就能直接给「下载」按钮，而不是让用户自己去题库页点。

⚠️ 为什么不直接复用 HTTP 路由 `GET /questionBank/questionBank/{id}/export`
--------------------------------------------------------------------
路由返回的是 `StreamingResponse`（字节直接冲给浏览器），工具拿不到「一个 URL」。
而且工具跑在服务端、需要把产物**存下来**才能让前端下载（流式响应是一次性的，
对话记录刷新后那条卡片还得能重新下载）。所以这里走 service 层 + 落盘。

⚠️ 导出的是**用户能看到的**题库，不只是自己的
--------------------------------------------
可见性复用 `api/v1/questions.py:_can_view_bank`（公开库 / 自己的库 / 已领取分享）。
既然用户能在页面上看到它、能点那个导出按钮，对话里说一句「导出这个库」也不该被拦 ——
两边口径不一致才是最让人困惑的。

⚠️ 只读工具？不是。它会写盘。
--------------------------------
`write_operation = True` 的理由：产物落盘是一次真实的写入（且要进回退账本吗？
**不进** —— 见下面 `undo_plan` 的说明）。写操作标志的意义在 `loop._execute_tool`：
它给工具包 SAVEPOINT、并让 `memory_hook` 记一条长期记忆。导出落盘失败要能回滚
（半截文件比没有文件更糟），所以标志照开；但 `undo_plan` 明确返回「不可回退」，
因为**删掉一个刚生成的导出文件**对用户没有任何价值（他不是误删了东西，而是想拿到
那份文件）。账本里如实记一条 `not_declared` 比强行造一个逆操作更诚实。

⚠️ 工具名是 `bank_export`，不是 `export`
--------------------------------------
`name` 会成为 Function Calling 的 function name，也是 `ai_agent_op_log.tool` 列的值。
带域前缀（`bank_`）与 `bank_manage` / `bank_share_manage` 成组，一眼看出归属。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.question import QuestionBank, QuestionMain
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 支持导出的格式（新增格式时这里 + service + 前端下拉三处一起改）
SUPPORTED_FORMATS = ("docx", "pdf")

#: 产物落盘的子目录（相对 `UPLOAD_DIR`）。放在 `export/` 下而非 `upload/`：
#: `upload/` 是用户上传的输入，`export/` 是系统产出的结果，混在一起会让
#: 「清理上传目录」这类运维动作误删用户刚导出的试卷。
EXPORT_SUB_DIR = "export"

#: 单次导出的题目上限。不是性能限制，是**产物可用性**限制：
#: 几千道题的 Word 打开要几分钟，用户会以为导出坏了。超过就明确拒绝并给建议。
MAX_QUESTIONS = 2000


def save_export_file(
    data: bytes, filename: str
) -> Tuple[str, str]:
    """把产物字节落盘到 `export/` 目录；返回 `(相对 UPLOAD_DIR 的路径, 文件名)`

    抽成模块级函数（而不是 `BankExportTool` 的静态方法）是为了让**别的工具**也能复用
    —— 学情诊断报告（`learning_stats.diagnose_report`）产出的 PDF 走的是同一套落盘
    与下载链路，前端那张产物卡片也是同一个组件。两处各写一份路径拼接必然漂移。

    ⚠️ 文件名带 uuid 前缀：同一个题库 / 同一份学情报告可以导出很多次，用原名会让
    后一次覆盖前一次 —— 而用户可能正开着前一份在改。
    """
    unique = f"{uuid.uuid4().hex[:12]}_{filename}"
    full = os.path.join(_export_dir(), unique)
    with open(full, "wb") as fh:
        fh.write(data)
    rel = os.path.relpath(full, settings.UPLOAD_DIR).replace("\\", "/")
    return rel, filename

#: `with_answers` 的「假值」词表 —— 模型把布尔写成字符串是常态。
#:
#: ⚠️ 这些是**用户/模型可能原样带回的词**，不是散文描述，所以出现中文是合理的。
#: （P11d 只扫 `description` / `describe()`，不扫运行时代码；但为了不让后来者
#:  误以为本文件可以随便写中文，注释说清它是「词表」而非「文案」。）
_FALSE_WORDS = frozenset(
    {"false", "0", "no", "none", "off", "", "null", "否", "不要", "不用", "无答案"}
)


def _safe_filename(name: str, fallback: str = "题库") -> str:
    """把题库名清洗成可做文件名的形式（保留中文，去掉 Windows 非法字符）

    与 `api/v1/bank_export.py:_safe_filename` 同一规则 —— 但**不 import 它**：
    路由模块会把整个 `questions.py`（3600 行）拖进来，工具层不该背这个依赖。
    这条规则很短（正则 + 空白折叠），重复一份的代价远小于那条依赖。
    """
    import re

    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s or fallback)[:80]


def _export_dir() -> str:
    """产物目录（自动建）—— 按天分目录，避免单目录堆十万个文件"""
    today = datetime.now().strftime("%Y/%m/%d")
    path = os.path.join(settings.UPLOAD_DIR, EXPORT_SUB_DIR, today)
    os.makedirs(path, exist_ok=True)
    return path


def _human_size(size: int) -> str:
    """字节数 → 人话（回执里给模型看，也显示在卡片上）"""
    value = float(size or 0)
    for unit in ("B", "KB", "MB"):
        if value < 1024 or unit == "MB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} MB"


class BankExportTool(AgentTool):
    name = "bank_export"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Export a question bank into a real Word (.docx) or PDF file the user can "
        "download, print and hand out. Use it whenever the user asks to export, "
        "download, save as Word/PDF, make a paper / worksheet / exam, print it out, "
        "or produce a version to hand to students. "
        "Two independent switches: "
        "`format` = docx (Word, editable, native equations) or pdf (fixed layout, "
        "good for printing / phone viewing); "
        "`with_answers` = true (teacher copy: questions + answers + explanations) or "
        "false (student copy: questions only, with blank space to write on). "
        "Both switches are genuinely different files — if the user says 'no answers' / "
        "'student version', pass with_answers=false. "
        "When the user asks for BOTH versions, call this tool TWICE (once per version). "
        "The reply carries a `downloadUrl` that is already ready to download; do "
        "NOT paste the raw URL into your reply, just tell the user the file is ready. "
        "NOTE: this only produces a FILE — to change the bank or its questions, use "
        "`bank_manage` / `question_manage`."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "题库导出"
    description_zh = (
        "把题库导出成 Word / PDF 文件：format=docx 或 pdf，"
        "with_answers=false 导出「无答案学生卷」。导出后可在对话里直接下载。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "bank_id": {
                "type": "integer",
                "description": (
                    "Bank ID to export. Get it from `bank_manage` action=list. "
                    "If the user named the bank instead of giving an id, resolve the id "
                    "with `bank_manage` first — do NOT guess an id."
                ),
            },
            "format": {
                "type": "string",
                "description": (
                    "Output format: docx = Word (editable, native equations, best when the "
                    "user will edit or send it to colleagues), "
                    "pdf = fixed layout (best for printing or phone viewing). Default docx."
                ),
                "enum": list(SUPPORTED_FORMATS),
            },
            "with_answers": {
                "type": "boolean",
                "description": (
                    "true (default) = teacher copy with answers and explanations; "
                    "false = student copy without answers (short-answer questions get "
                    "blank space to write in). Set false when the user asks for a "
                    "student version / no answers."
                ),
            },
        },
        "required": ["bank_id"],
    }
    write_operation = True

    # ------------------------------------------------------------------
    # 确认策略：导出**不需要**确认
    # ------------------------------------------------------------------
    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        """导出一律不弹确认卡

        ⚠️ 虽然 `write_operation=True`（要落盘），但「确认」这个交互存在的意义是
        **防止不可逆的破坏**或**代价高昂的操作**。导出两样都不是：它不删不改任何
        用户数据，最坏情况是多一个文件。为它弹卡只会让「说一句话拿到试卷」这件事
        每次都多一次点击，把最顺的那条演示动线打断。

        代价：它因此不会被记进回退账本（`record_op` 的门槛含 `needs_confirmation`）。
        这正好符合预期 —— 见模块 docstring 关于 `undo_plan` 的说明。
        """
        return False

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """明确声明「不可回退」，并给一句人话原因

        返回一个**带 reason 的 dict**（而不是裸 `None`）是有意的：裸 `None` 会让
        账本记 `not_declared`、界面显示「这个操作还没有回退实现」—— 那句话对导出
        来说是**假的**：我们是想清楚了不该撤，不是没做。

        为什么不该撤：用户的意图是「拿到这份文件」，撤销它等于把刚做好的东西删掉。
        真正的回退需求是「我导错了版本」→ 重新导出一次（幂等、便宜），不是撤销。
        """
        return {
            "undoable": False,
            "reason": "导出的文件是结果不是改动，不需要撤销；导错了版本重新导一次即可",
        }

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片用（本工具不弹卡，但保持契约：给得出信息就别留空）"""
        try:
            bank = await self._resolve_bank(params, ctx)
            if isinstance(bank, dict):
                return {}
            fmt = self._normalize_format(params.get("format"))
            return {
                "bankName": bank.bank_name,
                "subject": bank.subject,
                "totalQuestions": bank.total_questions or 0,
                "format": "Word（可编辑）" if fmt == "docx" else "PDF（固定版式）",
                "version": "含答案与解析" if self._with_answers(params) else "无答案（学生卷）",
            }
        except Exception:  # noqa: BLE001 - 预览失败不许抛
            return {}

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        bank = await self._resolve_bank(params, ctx)
        if isinstance(bank, dict):  # fail 信封
            return bank
        if bank is None:  # pragma: no cover - 仅用于类型收窄
            return fail("未指定题库", "请提供 bank_id（可先用 bank_manage list 查）")

        fmt = self._normalize_format(params.get("format"))
        with_answers = self._with_answers(params)

        # 题目：按 sort_order 排（与练习顺序一致）；子题一并预取，避免 N+1
        q_rows = (
            await ctx.db.execute(
                select(QuestionMain)
                .options(selectinload(QuestionMain.sub_questions))
                .where(QuestionMain.bank_id == bank.id, QuestionMain.status == "0")
                .order_by(QuestionMain.sort_order, QuestionMain.id)
            )
        ).scalars().all()

        if not q_rows:
            return fail(
                f"题库「{bank.bank_name}」里还没有题目，没有内容可导出",
                "请先用 question_manage 添加或导入题目；如果是空题库，告诉用户先加题",
            )
        if len(q_rows) > MAX_QUESTIONS:
            return fail(
                f"题库「{bank.bank_name}」有 {len(q_rows)} 道题目，超过单次导出上限 "
                f"{MAX_QUESTIONS} 道",
                "请告诉用户题目太多、建议分批导出，或先在页面上按章节拆分题库",
            )

        bank_dict, questions = self._build_payload(bank, q_rows)

        try:
            data, media_type, ext = self._render(fmt, bank_dict, questions, with_answers)
        except Exception as e:  # noqa: BLE001 - 渲染失败要给人话原因
            return fail(
                f"生成文件失败：{type(e).__name__}: {e}",
                "这是服务端渲染问题，不是用户数据的问题。请如实告诉用户导出失败，"
                "不要把失败说成成功；可以让用户改用另一种格式（docx ↔ pdf）再试一次",
            )

        # 落盘：产物必须能被**重新下载**（对话记录刷新后卡片还在，链接不能失效）
        try:
            rel_path, filename = self._save(data, bank.bank_name, ext, with_answers)
        except OSError as e:
            return fail(
                f"文件已生成但保存失败：{e}",
                "磁盘可能已满或没有写权限。请告诉用户稍后重试，不要谎称导出成功",
            )

        size = len(data)
        version_text = "含答案与解析" if with_answers else "无答案（学生卷）"
        return ok(
            action="export",
            bankId=bank.id,
            bankName=bank.bank_name,
            format=fmt,
            withAnswers=with_answers,
            version=version_text,
            questionCount=len(q_rows),
            fileName=filename,
            fileSize=size,
            fileSizeText=_human_size(size),
            # 前端产物卡片据此渲染「下载」按钮；`/profile` 是 `UPLOAD_DIR` 的静态挂载点
            downloadUrl=f"/profile/{rel_path}",
            message=(
                f"已导出「{bank.bank_name}」的{version_text}"
                f"{'Word' if fmt == 'docx' else 'PDF'}（{len(q_rows)} 道题，"
                f"{_human_size(size)}），可以直接下载"
            ),
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_format(raw: Any) -> str:
        """归一格式；非法值退 `docx`（默认格式，比报错更友好 —— 用户大多要 Word）"""
        text = str(raw or "").strip().lower().lstrip(".")
        if text in ("word", "doc", "w"):
            return "docx"
        if text in SUPPORTED_FORMATS:
            return text
        return "docx"

    @staticmethod
    def _with_answers(params: Dict[str, Any]) -> bool:
        """解析 `with_answers`（默认 True = 含答案）

        ⚠️ 必须接受字符串：模型常把布尔值写成 `"false"` / `"0"` / `"no"`。
        `bool("false")` 是 **True** —— 直接用它会把「学生卷」悄悄做成「答案卷」，
        而这种错用户交上去才会发现。所以这里逐字判一次。
        """
        raw = params.get("with_answers")
        if raw is None:
            return True
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        text = str(raw).strip().lower()
        # ⚠️ 这里**可以**写中文：「否」「不要」是**用户输入词**（模型可能原样带回），
        #    不是散文描述。P11d 扫的是 `description` / `describe()` 里的中文段，
        #    不扫 `execute()` 里的运行时代码 —— 但为了不让人误读本文件的语言约定，
        #    这条判断用一个显式常量而不是散在表达式里。
        return text not in _FALSE_WORDS

    async def _resolve_bank(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Any:
        """按 `bank_id` 取题库并校验**可见性**；失败返回 `fail()` 信封（dict）

        可见性走 `_can_view_bank`（公开 / 自己的 / 已领取分享），与页面上那个
        导出按钮**同一套判定** —— 两边不一致才是最让人困惑的。

        ⚠️ 「不存在」与「无权」回**同一句**：分开说等于给攻击者一个「这个题库存在」
        的探测预言机（与 `bank_manage._resolve_bank` 同口径）。
        """
        bank_id = params.get("bank_id")
        if bank_id is None:
            return fail(
                "导出需要 bank_id",
                "先用 bank_manage action=list 查到题库 ID（不要猜），再调用本工具",
            )
        try:
            bid = int(bank_id)
        except (TypeError, ValueError):
            return fail(f"bank_id 不是合法数字：{bank_id!r}", "请传整数题库 ID")

        bank = (
            await ctx.db.execute(select(QuestionBank).where(QuestionBank.id == bid))
        ).scalars().first()
        if bank is None:
            return fail(
                f"题库不存在或你无权访问：bank_id={bid}",
                "请先用 bank_manage action=list 确认题库 ID",
            )

        # 延迟 import：`questions.py` 有 3600 行，工具模块顶层 import 它会让
        # 每次 `ensure_tools_loaded()` 都拖进来（注册表在应用启动时就会加载一次）
        from app.api.v1.questions import _can_view_bank

        if not await _can_view_bank(ctx.db, bank, ctx.user_id):
            return fail(
                f"题库不存在或你无权访问：bank_id={bid}",
                "这是别人的私密题库。公开题库、你自己的题库、以及你已领取分享的题库才能导出",
            )
        return bank

    @staticmethod
    def _build_payload(
        bank: QuestionBank, q_rows: List[QuestionMain]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """ORM 行 → 导出 service 要的字典（复用路由层的 format_* 保证字段一致）"""
        from app.api.v1.questions import format_question
        from app.services.question_write_service import QUESTION_TYPE_TEXT

        def type_text(qtype: Any) -> str:
            return QUESTION_TYPE_TEXT.get(int(qtype or 1), "未知")

        bank_dict: Dict[str, Any] = {
            "id": bank.id,
            "bankId": bank.id,
            "bankName": bank.bank_name,
            "subject": bank.subject,
            "description": bank.description,
            "totalQuestions": bank.total_questions or 0,
            "createTime": bank.create_time.isoformat() if bank.create_time else "",
        }
        questions: List[Dict[str, Any]] = []
        for q in q_rows:
            item = format_question(q)
            item["questionTypeText"] = type_text(q.question_type)
            for sub in item.get("subQuestions") or []:
                sub["questionTypeText"] = type_text(sub.get("questionType") or 1)
            questions.append(item)
        return bank_dict, questions

    @staticmethod
    def _render(
        fmt: str,
        bank_dict: Dict[str, Any],
        questions: List[Dict[str, Any]],
        with_answers: bool,
    ) -> Tuple[bytes, str, str]:
        """渲染成字节；返回 `(bytes, media_type, ext)`"""
        from app.services import bank_export_service as svc

        if fmt == "pdf":
            return (
                svc.export_bank_pdf(bank_dict, questions, with_answers=with_answers),
                "application/pdf",
                "pdf",
            )
        return (
            svc.export_bank_docx(bank_dict, questions, with_answers=with_answers),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        )

    @staticmethod
    def _save(
        data: bytes, bank_name: str, ext: str, with_answers: bool
    ) -> Tuple[str, str]:
        """把字节落盘；返回 `(相对 UPLOAD_DIR 的路径, 文件名)`（实现见模块级函数）"""
        filename = f"{_safe_filename(bank_name)}{'' if with_answers else '-无答案'}.{ext}"
        return save_export_file(data, filename)


__all__ = [
    "BankExportTool",
    "SUPPORTED_FORMATS",
    "MAX_QUESTIONS",
    "EXPORT_SUB_DIR",
    "save_export_file",
]
