# -*- coding: utf-8 -*-
"""同步探针：note_manage.save_draft 写「用户草稿」而非建 note 行（用户 2026-10-11 bug）

沙箱 asyncio 不可用 → 用**源码级 + 纯逻辑**断言（不跑 async）。
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.ai.agent.tools import note_manage as nm

rows = []


def check(cid, title, cond, actual=""):
    rows.append((cid, title, bool(cond), actual))


src = inspect.getsource(nm)

check("ND-01", "action 枚举含 save_draft", "save_draft" in nm.NoteManageTool.parameters["properties"]["action"]["enum"])
check("ND-02", "save_draft 进 _WRITE_ACTIONS（需确认）", "save_draft" in nm._WRITE_ACTIONS)
check("ND-03", "execute 分发含 save_draft", '"save_draft": self._save_draft' in src)
check("ND-04", "有 _save_draft 方法", hasattr(nm.NoteManageTool, "_save_draft"))
check("ND-05", "有 _preview_save_draft 方法", hasattr(nm.NoteManageTool, "_preview_save_draft"))
# 核心：_save_draft **不** import/调用 note 表的写入服务（不建 note 行）
save_src = inspect.getsource(nm.NoteManageTool._save_draft)
check("ND-06", "_save_draft 用 note_draft_service", "nds." in save_src and "nws.create_note" not in save_src)
check("ND-07", "_save_draft 不调 note_write_service 建笔记", "create_note" not in save_src)
# undo_plan 对 save_draft 特判（不落到"定位不到行"）
undo_src = inspect.getsource(nm.NoteManageTool.undo_plan)
check("ND-08", "undo_plan 对 save_draft 特判", 'action == "save_draft"' in undo_src)
# 描述里明确 save_draft 非正式笔记
desc = nm.NoteManageTool.description
check("ND-09", "描述含 save_draft 指引", "save_draft" in desc)
check("ND-10", "描述含勿用 create 冒充草稿的强提示", "Do NOT create a normal note" in desc)
# P11d：模型侧描述无中文
cjk = [c for c in desc if "\u4e00" <= c <= "\u9fff"]
check("ND-11", "description 无中文（P11d）", not cjk, "".join(cjk))
# status 参数已**移除**（用户 2026-10-11：彻底断掉 create+status=draft 冒充草稿的路径）
check(
    "ND-12",
    "parameters 已移除 status 参数",
    "status" not in nm.NoteManageTool.parameters["properties"],
    str(list(nm.NoteManageTool.parameters["properties"].keys())),
)
# save_draft 在 description 中排在 create= 之前（扭转模型默认选择）
check(
    "ND-16",
    "description 里 save_draft 排在 create 之前",
    desc.index("save_draft") < desc.index("create="),
)
# _create 硬编码 published
create_src = inspect.getsource(nm.NoteManageTool._create)
check("ND-17", "create 硬编码 published", 'status_norm = "published"' in create_src)
check("ND-18", "create 不再读 status 参数", 'params.get("status")' not in create_src)

# 草稿服务存在 + 字段互补
from app.services import note_draft_service as nds
check("ND-13", "note_draft_service 有 upsert/clear/get", all(hasattr(nds, x) for x in ("upsert_draft", "clear_draft", "get_draft", "has_draft")))
ups = inspect.getsource(nds.upsert_draft)
check("ND-14", "upsert 做 content/markdown 互补", "markdown_content = content" in ups or ("content and not markdown_content" in ups))
# 模型注册
from app.models.note import UserNoteDraft
check("ND-15", "UserNoteDraft 表名正确", UserNoteDraft.__tablename__ == "user_note_draft")

print("\n---- 笔记草稿探针 ----")
red = 0
for cid, title, ok, actual in rows:
    if not ok:
        red += 1
    tail = "" if ok else f" | 实际: {actual}"
    print(f"  [{'通过' if ok else '失败'}] {cid} {title}{tail}")
print(f"\n共 {len(rows)} 项；红的={[r[0] for r in rows if not r[2]] or '无'}")
sys.exit(1 if red else 0)
