"""Wiki 页面**派生字段**的纯计算（从 `wiki_service.py` 抽出）。

  · `refresh_page_derived` —— 改完正文后刷新派生字段（正文 md / 版本号 / 更新时间）
  · `mark_page_manual` —— 把页面标记为「手工维护」并置为就绪

⚠ 依赖方向单向：`wiki_service.py` → 本模块；本模块**不反向依赖**它
   （`wiki_payload_helpers` 无项目级回引），因此不会形成循环依赖。

⚠ 「改页面 → 刷新派生字段 → 重建链接图 → 提交」这串动作原本在**四个入口**里
   逐字重复（手动编辑 / 加内链 / 删内链 / 恢复历史版本）。现在：
   派生字段的计算收在这里，**链接图重建与提交**收在 `wiki_service.py` 的
   `_finalize_page_edit` —— 两边合起来把那四份重复实现收成一份。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.rag.wiki_payload_helpers import WIKI_READY


def refresh_page_derived(page: Any, content_md: str) -> None:
    """改完正文后刷新页面的派生字段。

    ⚠️ **版本号必须 +1**：前端靠它判断「页面有没有被别人改过」，
    漏掉会让并发编辑静默覆盖（用户报的「我的修改被吃掉了」）。
    """
    page.content_md = content_md
    page.version = int(page.version or 1) + 1
    page.update_time = datetime.now()


def mark_page_manual(page: Any, generated_by: str) -> None:
    """把页面标记为「手工维护」并置为就绪。

    ⚠️ `generated_by` 记的是**这次改动是谁做的**（`manual` / 本次的动作名），
    页面图谱与后续的增量更新靠它区分「AI 生成」与「人写的」。
    """
    page.status = WIKI_READY
    page.generated_by = generated_by
