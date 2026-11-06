"""`gallery_manage` 的纯规则测试（不连数据库、不调用模型）。

覆盖：
  · 画廊对象 → 前端资产卡契约（assetKey / imageName / url / meta / 可用图片源）；
  · 自然语言搜索能按「来源资料 + 章节 + 描述」拆分命中，而不是整串子串；
  · 未描述图片不会被说成有描述；
  · 缺 query / 缺 asset_key / 非法筛选在打开数据库前就被拒绝。
"""

from __future__ import annotations

import asyncio

from app.services.ai.agent.base import ToolContext
from app.services.ai.agent.tools.gallery_manage import (
    GalleryManageTool,
    _asset_to_card,
    _filters,
    _has_description,
    _rank_items,
    _search_terms,
)


def test_asset_to_card_matches_frontend_asset_contract():
    card = _asset_to_card(
        {
            "assetKey": "doc:42:3",
            "fileName": "概率论与数理统计.pdf · 图4",
            "url": "/profile/upload/2026/10/abc.png",
            "sourceType": "document",
            "sourceName": "概率论与数理统计.pdf",
            "sectionTitle": "第三章 随机变量",
            "caption": "分布函数的图像",
            "keywords": ["分布函数", "随机变量"],
            "descriptionStatus": "done",
            "kind": "diagram",
        }
    )
    assert card["assetKey"] == "doc:42:3"
    assert card["imageName"].startswith("概率论")
    assert card["url"].startswith("/profile/")
    assert card["meta"] == "概率论与数理统计.pdf · 第三章 随机变量"
    assert card["usableAsImageSource"] is True
    # 不伪造 chat_file_manage 才有的 imageId
    assert "imageId" not in card


def test_search_terms_split_natural_chinese_query():
    terms = _search_terms("概率论第三章的分布图")
    assert "概率论第三章的分布图" in terms
    assert "概率" in terms
    assert "分布" in terms


def test_rank_items_matches_source_section_and_caption():
    items = [
        {
            "assetKey": "doc:1:0",
            "fileName": "电路分析.pdf · 图1",
            "sourceName": "电路分析.pdf",
            "sectionTitle": "第一章 电路基础",
            "caption": "一个电路图",
        },
        {
            "assetKey": "doc:2:1",
            "fileName": "概率论与数理统计.pdf · 图4",
            "sourceName": "概率论与数理统计.pdf",
            "sectionTitle": "第三章 随机变量",
            "caption": "分布函数的图像",
        },
        {
            "assetKey": "doc:3:2",
            "fileName": "人工智能实操.docx · 图12",
            "sourceName": "人工智能实操.docx",
            "sectionTitle": "5. 获取测试集中第10张图片的真实标签与预测标签",
            "caption": "一张机器人语音对话接听的业务流程图，展示两种模式下的分流判断。",
            "kind": "diagram",
        },
    ]
    ranked = _rank_items(items, "概率论第三章的分布图")
    assert [x["assetKey"] for x in ranked] == ["doc:2:1"]


def test_missing_description_is_not_treated_as_described():
    card = _asset_to_card(
        {
            "assetKey": "doc:1:0",
            "fileName": "资料.pdf · 图1",
            "url": "/profile/upload/x.png",
            "descriptionStatus": "pending",
        }
    )
    assert _has_description(card) is False
    assert card["descriptionStatusText"] == "未生成描述"


def test_tool_rejects_bad_input_before_database():
    async def run():
        tool = GalleryManageTool()
        r = await tool.execute({"action": "search"}, ToolContext(user_id=1))
        assert r["success"] is False
        assert "query" in r["error"]

        r = await tool.execute({"action": "get"}, ToolContext(user_id=1))
        assert r["success"] is False
        assert "asset_key" in r["error"]

        r = await tool.execute({"action": "wat"}, ToolContext(user_id=1))
        assert r["success"] is False

    asyncio.run(run())


def test_filters_reject_unknown_enum():
    assert _filters({"source": "wechat"})["ok"] is False
    assert _filters({"status": "processingx"})["ok"] is False
    assert _filters({"source": "document", "status": "done"})["ok"] is True
