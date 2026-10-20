"""
`note_manage` —— 笔记管理工具（Agent 自封装）

对齐 `bank_manage` 的形态：把 list / detail / create / update / delete / delete_many
收进**一个**工具，用 `action` 区分。理由同 `bank_manage`：工具清单越长，模型选错的
概率越高，而参数 schema 里的 `action` 枚举本身就是「能给模型看的文档」。

⚠️ **刻意不做 `delete_by_name`**（`bank_manage` 有，这里不能照抄）：
   `bank_manage` 能做按名删，是因为题库名被要求唯一（见其 `_update` 里的重名校验）。
   **笔记标题天生不唯一** —— 用户完全可能有好几篇《错题整理》。
   按标题删会删错，且删的是逻辑删除、用户还不一定能立刻发现。
   所以「删那篇讲牛顿定律的」这条路径设计成：先用 `list`（带 `keyword`）拿到 `noteId`，
   再 `delete`。多一轮，但不会删错东西。

写库细节全部在 `app/services/note_write_service.py`（NOT NULL 兜底、逻辑删除、
`refresh` 时机等四个坑都记在那儿），本文件只负责「参数校验 + 人话回执」。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select

from app.models.note import Note
from app.services import note_draft_service as nds
from app.services import note_write_service as nws
from app.services.ai.agent.base import (
    OP_RESTORE,
    OP_RESTORE_FIELDS,
    OP_SOFT_DELETE,
    REASON_MISSING_TARGET_ID,
    UNDO_BEFORE_KEY,
    AgentTool,
    ToolContext,
    fail,
    ok,
)

#: 需要用户确认的动作（都会写数据）
_WRITE_ACTIONS = {
    "create",
    "create_category",
    "update",
    "delete",
    "delete_many",
    "save_draft",
}

#: 删除类动作：即使 autoConfirm 开着也必须二次确认
_DESTRUCTIVE_ACTIONS = {"delete", "delete_many"}

#: 确认卡片样例最多给几条标题
_PREVIEW_SAMPLE = 5

#: `update` 要把「改动前的值」留一份给回退（见 `undo_plan`）。
#: 列的就是 `note` 的可变列 —— 与 `note_write_service.update_note` 返回的 `changed`
#: **同一套名字**（那边返回的就是这些列名），所以回退时能按 `changed` 精确过滤。
_NOTE_UNDO_FIELDS = (
    "title",
    "content",
    "markdown_content",
    "tags",
    "category_id",
    "is_public",
    "status",
)


def _note_ids_of(result: Dict[str, Any]) -> List[int]:
    """从回执里取被写到的笔记 id（`create`/`update` 在 `note.noteId`，删除类在 `deleted[]`）

    只认 id，不认标题 —— 标题天生不唯一（见本模块 docstring），拿它当回退依据会撤错行。
    """
    out: List[int] = []

    def _push(value: Any) -> None:
        nid = _to_int(value)
        if nid is not None and nid not in out:
            out.append(nid)

    note = result.get("note")
    if isinstance(note, dict):
        _push(note.get("noteId"))
    for item in result.get("deleted") or []:
        if isinstance(item, dict):
            _push(item.get("noteId"))
    return out


class NoteManageTool(AgentTool):
    name = "note_manage"
    #: ⚠️ 描述与参数说明一律英文 —— 它们会同时进两处「提示词注入」通道：
    #:   ① `registry.describe()` → 系统提示词的 `{{TOOLS}}` 占位
    #:   ② `registry.definitions()` → Function Calling 的 `tools` 参数
    #: 系统提示词是全英文的，这里混中文会让模型面对两套语言约定。
    description = (
        "Manage the user's study notes. action values: "
        # ⚠️ save_draft 故意排在**最前**（用户 2026-10-11 实测：ai 总爱选 create 建普通笔记、
        #    把"存草稿"做成了真实笔记）——把"草稿"入口放在最前并加重语气，扭转模型的默认选择。
        "save_draft=save the user's WORK-IN-PROGRESS draft. **STRONGLY PREFER THIS whenever the "
        "user asks to save a draft / not finished / save for later / keep it for now** — it goes "
        "to the user's editor draft (NO noteId, NEVER shown in their note list, reopened in the "
        "note editor next time). Requires `title`. If the user already has a draft it is "
        "OVERWRITTEN after confirmation. Do NOT create a normal note (action=create) when the "
        "user asked for a draft. "
        "create=create a PUBLISHED note (a real note that appears in the user's note list; "
        "requires `title`). Use ONLY when the user wants a finished, saved note — NOT for drafts "
        "or work-in-progress. "
        "list=list notes (optional fuzzy `keyword` matching title/content/tags, "
        "optional `category_id` filter), "
        "detail=read one note's full content, "
        "list_categories=list the user's note categories, "
        "create_category=create a note category by `name` (idempotent: returns the "
        "existing category if one with that exact name already exists), "
        "update=update fields of an existing note, "
        "delete=delete one note by `note_id`, "
        "delete_many=delete SEVERAL notes at once (pass `note_ids`). "
        "NOTE: every note belongs to a category. If you omit both `category_id` and "
        "`category_name`, the note goes to the user's default category (created "
        "automatically when the user has none). "
        "NOTE: a non-empty `category_name` must MATCH an existing category or the "
        "create FAILS. To put a note in a category that may not exist yet, either pass "
        "`create_category_if_missing=true` on action=create (the category is created "
        "for you), or call action=create_category first and then action=create. "
        "NOTE: there is deliberately NO delete-by-title action - note titles are NOT "
        "unique. To delete a note you must first call action=list (with `keyword`) to "
        "get its `noteId`, then call action=delete."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "笔记管理"
    description_zh = (
        "笔记的增删改查与分类：list=列笔记（按标题 / 正文 / 标签模糊找）、"
        "detail=读全文、list_categories=列分类、create_category=新建分类、"
        "create=新建（分类不存在时可传 create_category_if_missing=true 自动建）、"
        "update=修改、delete=删除、delete_many=批量删。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "list",
                    "detail",
                    "list_categories",
                    "create_category",
                    "create",
                    "update",
                    "delete",
                    "delete_many",
                    "save_draft",
                ],
            },
            "note_id": {
                "type": "integer",
                "description": "Note ID (used by detail/update/delete)",
            },
            "note_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Note IDs to delete in bulk (used by delete_many).",
            },
            "title": {
                "type": "string",
                "description": (
                    "Note title. Required for create; optional for update. "
                    "Titles need NOT be unique."
                ),
            },
            "content": {
                "type": "string",
                "description": "Plain-text body of the note.",
            },
            "markdown_content": {
                "type": "string",
                "description": (
                    "Markdown body of the note. Prefer this over `content` when the "
                    "note uses headings / lists / code blocks."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags, e.g. [\"Math\", \"Review\"]. Replaces the whole tag list.",
            },
            "keyword": {
                "type": "string",
                "description": (
                    "Fuzzy search text for action=list. Matches title, body and tags. "
                    "Use this to find a note's `noteId` before updating or deleting it."
                ),
            },
            "category_id": {
                "type": "integer",
                "description": (
                    "Target note category ID. Call action=list_categories to see the "
                    "available ones. Optional - defaults to the user's first category."
                ),
            },
            "category_name": {
                "type": "string",
                "description": "Target category by EXACT name. Ignored when `category_id` is given.",
            },
            "name": {
                "type": "string",
                "description": (
                    "Category name to create (used by action=create_category). "
                    "Idempotent: if a category with this exact name already exists, "
                    "its existing categoryId is returned."
                ),
            },
            "order_num": {
                "type": "integer",
                "description": "Sort order for the new category (optional, used by create_category). Defaults to 0.",
            },
            "create_category_if_missing": {
                "type": "boolean",
                "description": (
                    "For action=create only: when true and `category_name` does not exist, "
                    "the category is created automatically instead of failing. "
                    "Default false (unknown category names fail)."
                ),
            },
            "is_public": {
                "type": "integer",
                "description": (
                    "Note visibility: 1=public, 0=private (default). "
                    "WARNING: this is the OPPOSITE of question banks, where 0=public and "
                    "1=private. Do not copy the bank convention here."
                ),
            },
            # ⚠️ 刻意**没有** `status` 参数（用户 2026-10-11）：历史上模型爱用
            #    `create status=draft` 冒充"存草稿"，结果在 note 表建了一条带 noteId 的真实笔记
            #    （用户以为是系统草稿，实际进了笔记列表）。为彻底断掉这条误用路径，`create` 一律
            #    建**正式（已发布）笔记**，不再暴露 status；"草稿"语义**唯一**归 `action=save_draft`。
        },
        "required": ["action"],
    }
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _DESTRUCTIVE_ACTIONS

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """长正文（≥3000 字）的笔记 / 草稿写入强制确认；短内容直接执行

        规模只看正文长度（`markdown_content` 优先，与 `_create` / `_save_draft`
        取正文的口径一致）。⚠️ 热路径：解析失败一律不弹卡。
        """
        try:
            if str(params.get("action") or "") not in ("create", "save_draft"):
                return False
            body = params.get("markdown_content") or params.get("content") or ""
            return len(str(body)) >= 3000
        except Exception:  # noqa: BLE001
            return False

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """声明「这一笔笔记操作怎么撤」（契约见 `base.AgentTool.undo_plan`）

        笔记是**逻辑删**（`del_flag`，与 `api/v1/notes.py:770` 同口径），所以三类都能撤、
        而且都很便宜 —— 之前缺的只是「谁能把它改回 '0'」（今天没有任何恢复入口）：

          · `create` → 把新建的那行**软删**（`del_flag='2'`）
          · `delete` / `delete_many` → 把软删的行**恢复**（`del_flag='0'`）
          · `update` → 把改动过的列**写回旧值**（旧值走 `UNDO_BEFORE_KEY`，见 `_update`）

        ⚠️ `delete_many` 也在这里声明（spec 的 V1 清单只点了 create/update/delete）：
        它和 `delete` 是**同一个逆操作、同一张表**，回执里本来就有 `deleted[].noteId`；
        不声明的话，「把这两篇笔记都删了」之后用户点回退会得到一句「不支持」——
        与「撤销本次的所有操作」这个用户口径直接冲突。要收回只需删掉这一行。
        """
        action = str(params.get("action") or "")
        # `save_draft` 写的是**用户草稿**（无 noteId、非 note 表），不走 note 的软删/恢复那一套；
        # 草稿本就是临时内容、可再存，无需提供回退。明确告诉用户「不可撤销」即可
        # （否则会落到下面的「定位不到行」文案，含义不对）。
        if action == "save_draft":
            return {"undoable": False, "reason": "「存草稿」是临时的、可直接再存覆盖，无需撤销"}
        # `create_category` 建的是**笔记分类**，不是笔记本身 —— 回执形状也不同
        # （`category.categoryId`，不是 `note.noteId`）。分类是用户手工维护的轻量结构，
        # 删掉它会把里面的笔记变成「未分类」而不是删掉笔记，所以**不声明逆操作**，
        # 但要说清为什么（原来这里落到 `missing_target_id`，文案是「回执里没有可定位的
        # 数据行 ID」—— 对用户来说等于没说）。
        if action == "create_category":
            return {
                "undoable": False,
                "reason": "新建的笔记分类不会自动撤销（删分类会把里面的笔记变成未分类）；"
                "需要的话在「我的学习 · 笔记管理」里手动删掉它",
            }
        ids = _note_ids_of(result)
        if not ids:
            # 说得出怎么撤却定位不到行 → 明说，不许静默成「点了没反应」
            return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
        if action == "create":
            return {
                "op": OP_SOFT_DELETE,
                "targetTable": "note",
                "targetIds": ids,
                "undoable": True,
            }
        if action == "update":
            return {
                "op": OP_RESTORE_FIELDS,
                "targetTable": "note",
                "targetIds": ids,
                "undoable": True,
            }
        if action in ("delete", "delete_many"):
            return {
                "op": OP_RESTORE,
                "targetTable": "note",
                "targetIds": ids,
                "undoable": True,
            }
        return None

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片上给「会动到什么」，而不是光秃秃一个 id

        · 删除类：把将被删的笔记**标题**反查出来（`count` + `sample`，前端按样例列表渲染）
        · 创建/更新：把标题、目标分类、正文字数摊开，让用户看清要存的是什么

        失败**不允许**抛出 —— 循环层会兜住，但别依赖它。
        """
        action = str(params.get("action") or "")
        try:
            if action in _DESTRUCTIVE_ACTIONS:
                return await self._preview_delete(params, ctx)
            if action == "create":
                return await self._preview_create(params, ctx)
            if action == "create_category":
                return await self._preview_create_category(params, ctx)
            if action == "update":
                return await self._preview_update(params, ctx)
            if action == "save_draft":
                return await self._preview_save_draft(params, ctx)
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}
        return {}

    async def _preview_delete(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        ids: List[int] = []
        if params.get("note_id") is not None:
            ids.append(params["note_id"])
        ids += _int_list(params.get("note_ids"))
        ids = [i for i in ids if i is not None]
        if not ids:
            return {}
        rows = (
            await ctx.db.execute(
                select(Note.note_id, Note.title).where(
                    Note.note_id.in_(ids),
                    Note.user_id == ctx.user_id,
                    Note.del_flag == "0",
                )
            )
        ).all()
        titles = [str(r[1]) for r in rows]
        if not titles:
            # 一条都不匹配：让确认卡片直接说清「没找到」，而不是显示 count: 0
            return {"count": 0, "sample": ["（没有找到属于你的、未删除的笔记）"]}
        out = {
            "count": len(titles),
            "sample": titles[:_PREVIEW_SAMPLE],
        }
        # 勾选卡（用户 2026-10-17 需求）：一张卡列出全部待删笔记，用户可逐条反悔
        order = {int(i): n for n, i in enumerate(ids)}
        items = [
            {"key": f"note:{r[0]}", "id": int(r[0]), "title": str(r[1] or "")}
            for r in rows
        ]
        items.sort(key=lambda it: order.get(it["id"], 9999))
        out["draft"] = {
            "kind": "batch_delete",
            "entity": "note",
            "entityLabel": "笔记",
            "items": items,
        }
        return out

    async def _preview_save_draft(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """草稿确认卡的预览：说清「要存什么」+「是否覆盖已有草稿」

        用户 2026-10-11 明确：**已有草稿时要先提示、让用户确认再覆盖**。这里把
        `overwrite` 与已有草稿标题一并给出，前端/模型据此告诉用户「这会覆盖你已有的草稿」。
        """
        out: Dict[str, Any] = {}
        title = (params.get("title") or "").strip()
        if title:
            out["title"] = title
        body = params.get("markdown_content") or params.get("content") or ""
        out["contentLength"] = len(str(body))
        try:
            existing = await nds.get_draft(ctx.db, ctx.user_id)
        except Exception:  # noqa: BLE001
            existing = None
        out["overwrite"] = existing is not None
        if existing is not None:
            out["existingTitle"] = existing.title or "（无标题草稿）"
        return out

    async def _preview_create(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        title = (params.get("title") or "").strip()
        if title:
            out["title"] = title
        body = params.get("markdown_content") or params.get("content") or ""
        out["contentLength"] = len(str(body))
        cat, _err = await nws.resolve_category(
            ctx.db,
            ctx.user_id,
            category_id=params.get("category_id"),
            category_name=params.get("category_name"),
        )
        if cat is not None:
            out["categoryName"] = cat.name
        elif _to_bool(params.get("create_category_if_missing")):
            # 分类不存在、但用户/模型要求自动建：确认卡片要先说清「会顺手新建这个分类」
            missing = (params.get("category_name") or "").strip()
            if missing and params.get("category_id") is None:
                out["willCreateCategory"] = missing
        tags = nws.normalize_tags(params.get("tags"))
        if tags:
            out["tags"] = tags
        # 笔记 1=公开 / 0=私密（与题库相反，见 note_write_service 的坑 4）
        out["visibility"] = "公开" if _to_int(params.get("is_public")) == 1 else "私密"
        return out

    async def _preview_create_category(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """新建分类的确认卡：只需告诉用户要建的分类名（同名时不会重复建）"""
        name = (params.get("name") or "").strip()
        if not name:
            return {}
        return {"name": name}

    async def _preview_update(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        note = await nws.get_user_note(ctx.db, ctx.user_id, params.get("note_id"))
        if note is None:
            return {}
        out: Dict[str, Any] = {"title": note.title}
        # 字段名 → 中文**白名单**。确认卡片会把 `willChange` 直接打在用户脸上
        # （前端 `AgentConfirmCard` 的 `PREVIEW_LABELS.willChange` = 「将修改」），
        # 拼英文键名（`title、is_public`）就是给用户看 schema —— 与本文件里
        # `visibility` 早就是「公开/私密」同一条策略：**人话在后端产出**。
        # 多个参数映射到同一个词时去重（`content` 与 `markdown_content` 都是「正文」）。
        changed_labels: List[str] = []
        for key, label in (
            ("title", "标题"),
            ("content", "正文"),
            ("markdown_content", "正文"),
            ("tags", "标签"),
            ("is_public", "可见性"),
            ("status", "状态"),
            ("category_id", "分类"),
            ("category_name", "分类"),
        ):
            value = params.get(key)
            if key == "category_name":
                # 空串不算「要改分类」——与 `_update` 的判定一致（那边用 `(… or "").strip()`）
                present = bool(str(value or "").strip())
            else:
                present = value is not None
            if present and label not in changed_labels:
                changed_labels.append(label)
        if changed_labels:
            out["willChange"] = "、".join(changed_labels)
        return out

    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handlers = {
            "list": self._list,
            "detail": self._detail,
            "list_categories": self._list_categories,
            "create_category": self._create_category,
            "create": self._create,
            "update": self._update,
            "delete": self._delete,
            "delete_many": self._delete_many,
            "save_draft": self._save_draft,
        }
        handler = handlers.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / detail / list_categories / create_category / "
                "create / update / delete / delete_many / save_draft",
            )
        return await handler(params, ctx)

    # ------------------------------------------------------------------
    # 各 action
    # ------------------------------------------------------------------

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        category_id = _to_int(params.get("category_id"))
        if category_id is not None:
            # 分类也要校验归属：否则模型传了别人的分类 id 会得到空列表，
            # 它会以为「用户没有笔记」，而不是「分类 id 错了」。
            cat, err = await nws.resolve_category(ctx.db, ctx.user_id, category_id=category_id)
            if err:
                return err
            category_id = cat.id

        notes, total = await nws.list_user_notes(
            ctx.db,
            ctx.user_id,
            keyword=params.get("keyword"),
            category_id=category_id,
        )
        return ok(
            action="list",
            count=len(notes),
            total=total,
            notes=[nws.note_brief(n) for n in notes],
        )

    async def _list_categories(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """列出分类 —— 模型拿到分类名后才能在 `category_name` 上重试

        没有这个 action，「分类名写错 → 报错 → 模型改对」这个自纠环闭不上。
        """
        cats = await nws.list_user_categories(ctx.db, ctx.user_id)
        return ok(
            action="list_categories",
            count=len(cats),
            categories=[
                {"categoryId": c.id, "name": c.name, "orderNum": c.order_num}
                for c in cats
            ],
        )

    async def _create_category(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """新建笔记分类（**幂等**：同名分类直接返回已有的那一个）

        支持「把笔记放进某个分类，没有就新建」的两步走：先本动作拿 `categoryId`，
        再 `create`；或者直接 `create` 传 `create_category_if_missing=true`。
        """
        name = (params.get("name") or "").strip()
        if not name:
            return fail("创建分类需要分类名", "请提供 name（分类名称）")
        cat = await nws.create_category(
            ctx.db, ctx.user_id, name, order_num=params.get("order_num")
        )
        return ok(
            action="create_category",
            category={
                "categoryId": cat.id,
                "name": cat.name,
                "orderNum": cat.order_num,
            },
            message=f"已创建分类「{cat.name}」",
        )

    async def _detail(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        note = await nws.get_user_note(ctx.db, ctx.user_id, params.get("note_id"))
        if note is None:
            # 给候选而不是干巴巴「不存在」：模型下一轮就能改对 id
            return await self._note_not_found(params, ctx)
        return ok(action="detail", note=nws.note_detail(note))

    async def _save_draft(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """把内容存成**用户的编辑器草稿**（不是一篇笔记）

        用户 2026-10-11 报：此前智能体用 `create status=draft` 会**在 note 表建一条带 noteId 的
        真实笔记**，而用户理解的「草稿」是「写笔记」页里那份**未发布、无 noteId、不进笔记列表**的
        临时内容。故新增本动作：写 `user_note_draft`（用户维度、一篇），前端「写笔记」页加载时合并。

        覆盖语义：一个用户至多一篇草稿，已有则**覆盖**（确认卡会在 preview 里标明 overwrite）。
        """
        title = (params.get("title") or "").strip()
        if not title:
            return fail("存草稿需要标题", "请提供 title（可先随便起，用户后续可改）")
        content = params.get("content")
        markdown = params.get("markdown_content")
        body = markdown or content
        if not body or not str(body).strip():
            return fail("草稿正文为空", "请提供 markdown_content 或 content，否则存下来是空草稿")

        existed = await nds.has_draft(ctx.db, ctx.user_id)
        draft = await nds.upsert_draft(
            ctx.db,
            ctx.user_id,
            title=title,
            content=content,
            markdown_content=markdown,
            category_id=_to_int(params.get("category_id")),
            tags=params.get("tags"),
            is_public=params.get("is_public"),
            public_section_id=_to_int(params.get("public_section_id")),
        )
        verb = "已覆盖你之前的草稿" if existed else "已存为草稿"
        return ok(
            action="save_draft",
            draft=nds.draft_to_dict(draft),
            overwrote=existed,
            message=f"{verb}「{title}」。下次打开「写笔记」时可直接继续编辑。",
        )

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        title = (params.get("title") or "").strip()
        if not title:
            return fail("创建笔记需要标题", "请提供 title")

        content = params.get("content")
        markdown = params.get("markdown_content")
        if not (content or markdown):
            return fail(
                "创建笔记需要正文",
                "请提供 markdown_content（推荐）或 content，否则存下来是一篇空笔记",
            )

        # ⚠️ `create` 一律建**正式（已发布）笔记**：不再接受/推断 status（用户 2026-10-11）。
        #    想存"草稿"必须用 `action=save_draft`（写 user_note_draft，不进笔记列表）。
        #    见 parameters 里"刻意没有 status 参数"的说明。
        status_norm = "published"

        category_name = (params.get("category_name") or "").strip()
        cat, err = await nws.resolve_category(
            ctx.db,
            ctx.user_id,
            category_id=params.get("category_id"),
            category_name=params.get("category_name"),
        )
        if err:
            # 分类不存在、但调用方明确要求自动建：先建分类再继续。
            # 只对 `category_name` 生效 —— `category_id` 给错属于调用错误，不该顺手新建。
            if (
                _to_bool(params.get("create_category_if_missing"))
                and params.get("category_id") is None
                and category_name
            ):
                cat = await nws.create_category(ctx.db, ctx.user_id, category_name)
            else:
                return err

        note = await nws.create_note(
            ctx.db,
            ctx.user_id,
            title=title,
            category=cat,
            content=content,
            markdown_content=markdown,
            tags=params.get("tags"),
            is_public=params.get("is_public"),
            status=status_norm,
        )
        return ok(
            action="create",
            note=nws.note_brief(note),
            message=f"笔记「{note.title}」已保存到分类「{cat.name}」（ID={note.note_id}）",
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        note = await nws.get_user_note(ctx.db, ctx.user_id, params.get("note_id"))
        if note is None:
            return await self._note_not_found(params, ctx)

        # ⚠️ 不再处理 `status`（用户 2026-10-11）：parameters 里已移除该字段，"草稿/发布"语义
        #    改由前端编辑器管理，智能体只需 create（=发布）/ save_draft（=草稿）。

        # 分类：只在显式传了分类参数时才解析 —— 否则会「顺手」把笔记挪到第一个分类
        category = None
        if params.get("category_id") is not None or (params.get("category_name") or "").strip():
            category, err = await nws.resolve_category(
                ctx.db,
                ctx.user_id,
                category_id=params.get("category_id"),
                category_name=params.get("category_name"),
            )
            if err:
                return err

        # ⚠️ **改前值必须在 `update_note` 之前抓**：它是在已加载的 ORM 对象上
        #    原地赋值的（`note.title = ...`），调用返回后旧值就没了。
        #    这里抓的是**普通 Python 值**（str/int），不是 ORM 引用，所以不会被后续赋值改掉。
        #    先全抓、调用后用 `changed` 过滤 —— 只留真正动过的列（`changed` 是服务层
        #    自己的产物，口径不会漂），正文很长时也不会把没改的正文塞进账本。
        before_all = {name: getattr(note, name, None) for name in _NOTE_UNDO_FIELDS}

        changed = await nws.update_note(
            ctx.db,
            note,
            title=params.get("title"),
            content=params.get("content"),
            markdown_content=params.get("markdown_content"),
            tags=params.get("tags"),
            category=category,
            is_public=params.get("is_public"),
        )
        if not changed:
            return fail(
                "没有提供任何要修改的字段",
                "请至少给出 title / content / markdown_content / tags / "
                "category_id / category_name / is_public 之一",
            )
        before = {name: before_all[name] for name in changed if name in before_all}
        payload: Dict[str, Any] = {
            "action": "update",
            "note": nws.note_brief(note),
            "changed": changed,
            "message": f"笔记「{note.title}」已更新（{', '.join(changed)}）",
        }
        if before:
            # 改前值**不进回执**（那是给模型/界面看的），走这个键让 `_execute_tool` 摘走
            payload[UNDO_BEFORE_KEY] = before
        return ok(**payload)

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        note_id = params.get("note_id")
        if note_id is None:
            return fail(
                "删除笔记需要 note_id",
                "笔记标题不唯一、不支持按名删。请先用 action=list（可带 keyword）查到 noteId",
            )
        note = await nws.get_user_note(ctx.db, ctx.user_id, note_id)
        if note is None:
            return await self._note_not_found(params, ctx)

        result = await nws.delete_notes(ctx.db, ctx.user_id, [note.note_id])
        if not result["deleted"]:
            return await self._note_not_found(params, ctx)
        return ok(
            action="delete",
            deleted=result["deleted"],
            message=f"已删除笔记「{note.title}」",
        )

    async def _delete_many(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """一次删除多篇笔记（「把这几篇都删了」只需一次调用）

        只删**属于当前用户**的；找不到的 id 如实回报，方便模型下一轮纠正。
        """
        ids = _int_list(params.get("note_ids"))
        if not ids:
            return fail(
                "delete_many 需要 note_ids",
                "请给出要删除的笔记 ID 列表。标题不唯一，所以不支持按名批量删 —— "
                "请先用 action=list（可带 keyword）查到 noteId",
            )

        result = await nws.delete_notes(ctx.db, ctx.user_id, ids)
        deleted = result["deleted"]
        parts = [f"已删除 {len(deleted)} 篇笔记"]
        if deleted:
            parts.append("、".join(f"「{d['title']}」" for d in deleted))
        if result["missing"]:
            parts.append(
                "不存在或不属于你：" + ", ".join(str(i) for i in result["missing"])
            )
        return ok(
            action="delete_many",
            deleted=deleted,
            missingIds=result["missing"],
            message="；".join(parts),
        )

    # ------------------------------------------------------------------

    async def _note_not_found(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """笔记找不到时的统一失败信封：带上最接近的候选，让模型能自己改对

        候选来自 `subject` 之外的两条线索：给了 `title` 就按标题模糊找，
        没给就看 `keyword`。都没有候选时给一句可执行的指引。
        """
        note_id = params.get("note_id")
        probe = (params.get("title") or params.get("keyword") or "").strip()
        if probe:
            matches = await nws.find_notes_by_title(ctx.db, ctx.user_id, probe)
            if matches:
                titles = "、".join(f"「{m.title}」(ID={m.note_id})" for m in matches[:_PREVIEW_SAMPLE])
                return fail(
                    f"没有找到笔记：note_id={note_id}",
                    f"标题里含「{probe}」的笔记有：{titles}。请用准确的 noteId 重试",
                )
        return fail(
            f"没有找到笔记：note_id={note_id}",
            "请先用 action=list（可带 keyword 模糊搜标题/正文/标签）确认笔记 ID",
        )


# ----------------------------------------------------------------------


def _to_int(value: Any) -> Any:
    """能转 int 就转，转不了原样返回（让 `is not None` 判断仍然成立）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    """入参容错：真布尔 / 数字 / "true"/"1"/"yes" 都算真（其余为假）"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _int_list(value: Any) -> List[int]:
    """入参容错：数组 / 逗号串 / JSON 串 / 单个数字都收下（丢弃转不成整数的项）"""
    if value is None:
        return []
    items: Any = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            import json

            try:
                parsed = json.loads(text)
            except Exception:  # noqa: BLE001 - 解析不了就退回逗号分隔
                parsed = None
            items = parsed if isinstance(parsed, list) else text.replace("，", ",").split(",")
        else:
            items = text.replace("，", ",").split(",")
    elif not isinstance(items, (list, tuple, set)):
        items = [items]

    out: List[int] = []
    for item in items:
        n = _to_int(item)
        if n is not None and n not in out:
            out.append(n)
    return out


__all__ = ["NoteManageTool"]
