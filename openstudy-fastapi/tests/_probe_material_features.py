# -*- coding: utf-8 -*-
"""「我的资料」本轮新增能力回归探针（零网络；真实 DB）：
1. material_organizer：自动命名 / 学科 / 类型 / facet
2. workspace overview：文件名、imageMap、imageCount、subject、materialType、facets
3. material_asset_usage：写入幂等 + 汇总 + 清理
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

# 让 ORM 解析 sys_user 外键；否则 Flask/SQLAlchemy 探针会在 flush 时找不到表
import app.models.user  # noqa: E402,F401
import app.models.role  # noqa: E402,F401
import app.models.menu  # noqa: E402,F401
import app.models.rag  # noqa: E402,F401

ROWS = []


def ck(cid: str, title: str, cond: bool, actual: str = "") -> None:
    ROWS.append((cid, title, cond, actual))
    print(f"  [{'通过' if cond else '失败'}] {cid} {title}" + (f" | {actual}" if not cond else ""))


async def main() -> int:
    from app.database import async_session_factory
    from app.api.v1.rag import (
        AssetUsageRequest,
        asset_usage_summary,
        get_document_content,
        get_document_outline,
        list_workspace_standalone_images,
        record_asset_usage,
    )
    from app.services.material_organizer import analyze
    from app.services.rag import workspace_service as ws

    # 1. 自动命名 / 学科 / 类型 / facet
    r = analyze("新建文档(3).docx", "## 概率论第三章 联合分布\n设随机变量 $X$ 的分布律如下：\n| X | 0 | 1 |\n| --- | --- | --- |\n| P | 0.4 | 0.6 |")
    ck("MF-01", "无意义文件名改为正文标题", r["display_name"].startswith("概率论第三章 联合分布"), r["display_name"])
    ck("MF-02", "自动识别数学学科", r["subject"] == "数学", r["subject"])
    ck("MF-03", "公式/表格 facet 被统计", r["facets"]["formulaCount"] >= 1 and r["facets"]["tableCount"] >= 1, str(r["facets"]))
    ck("MF-04", "保留原始文件名", r["original_file_name"] == "新建文档(3).docx", r["original_file_name"])

    r2 = analyze("讲义.docx", "数据结构 二叉树 遍历")
    ck("MF-05", "非无意义文件名保持原样", r2["display_name"] == "讲义.docx", r2["display_name"])
    ck("MF-06", "自动识别资料类型", r2["material_type"] == "讲义", r2["material_type"])

    # 2. 工作区 overview：数据来自真实用户 105 的默认资料夹
    async with async_session_factory() as db:
        overview = await ws.overview(db, 105)
        default = next((k for k in overview["knowledgeBases"] if k["isDefault"] == 1), None)
        ck("MF-07", "默认资料夹存在", default is not None)
        if default:
            ck("MF-08", "默认资料夹名称已统一", default["name"] == "默认资料夹", default["name"])
            ck("MF-09", "默认资料夹有文档", len(default["files"]) > 0, str(len(default["files"])))
            f = default["files"][0]
            ck("MF-10", "文件返回 imageMap", isinstance(f.get("imageMap"), dict), str(type(f.get("imageMap"))))
            ck("MF-11", "文件返回 imageCount", int(f.get("imageCount") or 0) > 0, str(f.get("imageCount")))
            ck("MF-12", "文件返回 subject/materialType/facets", bool(f.get("subject")) and bool(f.get("materialType")) and isinstance(f.get("facets"), dict), str({k: f.get(k) for k in ("subject", "materialType", "facets")}))

        # 2b. 单文档解剖依赖的接口
        content = await get_document_content(478, {"user_id": 105}, db)
        ck("MF-17", "文档解剖 content 接口可用", content.get("code") == 200 and len((content.get("data") or {}).get("content", "")) > 0, str(content.get("code")))
        ck("MF-18", "文档解剖返回 22 张图片", len(((content.get("data") or {}).get("imageMap") or {})) == 22, str(len(((content.get("data") or {}).get("imageMap") or {}))))
        outline = await get_document_outline(478, 120, {"user_id": 105}, db)
        ck("MF-19", "无章节文档如实返回 hasOutline=false", outline.get("code") == 200 and not (outline.get("data") or {}).get("hasOutline"), str(outline.get("data")))

        # 2c. 聊天独立图片接口
        standalone = await list_workspace_standalone_images(100, {"user_id": 105}, db)
        ck("MF-20", "聊天独立图片接口可用", standalone.get("code") == 200 and isinstance(standalone.get("data"), list), str(standalone.get("code")))

        # 3. 用途账本写入、幂等、汇总、清理
        req = AssetUsageRequest(
            assetKey="test:material:probe",
            assetUrl="/profile/test-probe.png",
            targetType="document",
            targetId=0,
        )
        r1 = await record_asset_usage(req, {"user_id": 105}, db)
        r2 = await record_asset_usage(req, {"user_id": 105}, db)
        summary = await asset_usage_summary({"user_id": 105}, db)
        ck("MF-13", "用途账本写入成功", r1.get("code") == 200, str(r1))
        ck("MF-14", "用途账本幂等", r2.get("code") == 200, str(r2))
        ck("MF-15", "汇总包含测试资产且计数为 1", (summary.get("data") or {}).get("test:material:probe") == 1, str(summary.get("data")))

        from sqlalchemy import text
        await db.execute(text("DELETE FROM material_asset_usage WHERE asset_key='test:material:probe'"))
        await db.commit()
        ck("MF-16", "测试数据清理完成", True)

    passed = sum(1 for _, _, ok, _ in ROWS if ok)
    print(f"\n共 {len(ROWS)} 项：{passed} 通过；失败 {len(ROWS) - passed}")
    return 0 if passed == len(ROWS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
