"""教学微课 HTML / PPT 导出。

与原 `micro_course_service` 的区别：
  · 原 service 生成的是「学习站点」结构化数据（章节、导读、检查点）；
  · 本模块把资料组织成一套**可直接演示的教学课件**：
      - 自包含 HTML（16:9 幻灯片、键盘/按钮翻页、全屏）；
      - 同内容的 .pptx（python-pptx 生成，标题 + 要点）；
      - 支持把前端拿到的 HTML 再转成 PPT。

所有内容仍以原文结构为主，不伪造资料里没有的结论。
"""

from __future__ import annotations

import asyncio
import html as _html
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from app.config import settings
from app.services.micro_course_service import build_micro_course

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).resolve().parent.parent / "resources" / "micro_course_skill.md"


def _load_skill() -> str:
    try:
        return _SKILL_PATH.read_text(encoding="utf-8")[:12000]
    except Exception:
        return ""


async def _ai_deck(
    db,
    user_id: int,
    doc,
    course: Dict[str, Any],
    prompt_text: str = "",
    base_deck: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], bool]:
    """让模型围绕资料生成教学课件结构。

    模型只负责「怎么讲」：页面标题、要点、课堂提示；正文事实仍以原文为准。
    模型不可用 / 返回格式不合法时，退回按原文结构生成的 deck，不阻塞页面。
    """
    raw = str(getattr(doc, "raw_content", "") or "")[:12000]
    fallback = _deck_from_stations(course, getattr(doc, "image_map", None))
    if not raw.strip():
        return fallback, False
    image_map = getattr(doc, "image_map", None) or {}
    image_urls = [v for v in image_map.values() if isinstance(v, str)][:8]
    image_lines = "\n".join(f"- 图{i + 1}: {url}" for i, url in enumerate(image_urls))
    base_text = ""
    if base_deck:
        base_text = "\n当前版本的结构（请在此基础上按修改要求重写，不要丢掉正确内容）：\n" + json.dumps(
            base_deck, ensure_ascii=False
        )[:6000]
    user_change = f"\n用户本次的修改要求（必须优先满足）：{prompt_text.strip()[:1000]}" if prompt_text.strip() else ""
    prompt = (
        "你是一位擅长把资料改写成课堂教学课件的老师。请只依据下面的资料，"
        "设计一套 5-12 页的教学课件。不要编造资料里没有的事实。\n"
        "返回严格 JSON（不要 Markdown 代码围栏）：\n"
        '{"title":"课件标题","subtitle":"副标题",'
        '"changeSummary":"这一版相对上一版改了什么（首次生成写：首次生成，围绕资料建立完整教学框架）",'
        '"slides":[{"layout":"content","eyebrow":"环节/知识点标签","title":"页标题",'
        '"bullets":["要点1","要点2"],"note":"可选的课堂提示",'
        '"image":{"url":"可选，只能使用下面提供的图片 URL","caption":"图片说明"},'
        '"chart":{"type":"bar","title":"图表标题","labels":["A","B"],"values":[80,60],"unit":"%"},'
        '"table":{"headers":["列1","列2"],"rows":[["值1","值2"]]}}]}\n'
        "layout 可选：cover / content / image / chart / table / quote / summary。"
        "至少使用 1 页图表或表格，资料有图片时使用 1–2 页图片；不要每页只有文字。"
        "第一页做课程导入，最后一页做课堂小结；每页 bullets 2-5 条，每条不超过 60 字。\n"
        "可用图片（只能从这里选择，不能编造 URL）：\n" + (image_lines or "（这份资料没有可用图片）") + "\n"
        + user_change + base_text + "\n"
        "资料文件名：" + str(getattr(doc, "file_name", "") or "") + "\n"
        "资料正文：\n" + raw
    )
    try:
        from app.services.ai import db_config
        from app.services.ai.base_client import ChatMessage

        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是教学课件设计师，只输出合法 JSON。必须遵守下面的教学微课 Skill：\n"
                    + _load_skill()
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ]
        response = await asyncio.wait_for(
            db_config.chat_with_config(
                db,
                messages,
                temperature=0.6,
                max_tokens=5000,
                user_id=user_id,
            ),
            timeout=35,
        )
        content = (response.content or "").strip()
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            return fallback, False
        data = json.loads(content[start : end + 1])
        slides = data.get("slides") if isinstance(data, dict) else None
        if not isinstance(slides, list) or len(slides) < 2:
            return fallback, False
        cleaned = []
        for slide in slides[:12]:
            if not isinstance(slide, dict) or not str(slide.get("title") or "").strip():
                continue
            bullets = [
                str(b).strip()[:100]
                for b in (slide.get("bullets") or [])
                if str(b).strip()
            ][:6]
            if not bullets and not any(slide.get(k) for k in ("image", "chart", "table", "quote")):
                continue
            item = {
                "kind": "content",
                "layout": str(slide.get("layout") or "content")[:20],
                "eyebrow": str(slide.get("eyebrow") or "知识点")[:30],
                "title": str(slide.get("title") or "")[:100],
                "bullets": bullets,
                "note": str(slide.get("note") or "")[:160],
            }
            for key in ("image", "chart", "table", "quote"):
                if isinstance(slide.get(key), (dict, list, str)):
                    item[key] = slide[key]
            cleaned.append(item)
        if len(cleaned) < 2:
            return fallback, False
        deck = {
            "title": str(data.get("title") or getattr(doc, "file_name", "") or "教学课件")[:100],
            "subtitle": str(data.get("subtitle") or getattr(doc, "subject", "") or "教学课件")[:100],
            "changeSummary": str(data.get("changeSummary") or "").strip()[:300],
            "slides": cleaned,
        }
        return deck, True
    except Exception as e:  # noqa: BLE001 - AI 是增强项，失败必须可降级
        logger.info("[micro-course] AI 生成失败，使用资料结构兜底: %s", e)
        return fallback, False


def _clean(text: str) -> str:
    text = re.sub(r"```.*?```", "", text or "", flags=re.S)
    text = re.sub(r"[#*_`>]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _bullets(text: str, limit: int = 4) -> List[str]:
    text = _clean(text)
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[。；;!?！？]\s*", text) if p.strip()]
    if len(parts) <= 1:
        # 长句按逗号切，保证每页不出现一大段
        parts = [p.strip() for p in re.split(r"[，,]\s*", text) if p.strip()]
    out = []
    for part in parts:
        if len(part) < 4:
            continue
        out.append(part if len(part) <= 74 else part[:73] + "…")
        if len(out) >= limit:
            break
    return out or [text[:74] + ("…" if len(text) > 74 else "")]


def _deck_from_stations(course: Dict[str, Any], image_map: Dict[str, Any] | None = None) -> Dict[str, Any]:
    doc = course.get("document") or {}
    stations = course.get("stations") or []
    title = doc.get("fileName") or "教学微课"
    subject = doc.get("subject") or "综合"
    slides: List[Dict[str, Any]] = [
        {
            "kind": "cover",
            "layout": "cover",
            "eyebrow": "AI 教学课件",
            "title": title,
            "subtitle": f"{subject} · 约 {course.get('overview', {}).get('stationCount', len(stations))} 个知识点",
            "bullets": [
                "先看整体结构，再逐个知识点理解",
                "每页都可以直接投屏演示，也可以下载为 PPT",
            ],
        }
    ]
    image_urls = [v for v in (image_map or {}).values() if isinstance(v, str)]
    if image_urls:
        slides.append(
            {
                "kind": "content",
                "layout": "image",
                "eyebrow": "先看一张图",
                "title": "把知识放进一张图里",
                "bullets": ["先观察结构，再进入具体知识点"],
                "image": {"url": image_urls[0], "caption": "资料配图"},
            }
        )
    for idx, station in enumerate(stations):
        bullets = _bullets(station.get("summary") or "", 3)
        if station.get("points"):
            bullets = [str(p) for p in station["points"][:4]] or bullets
        slides.append(
            {
                "kind": "content",
                "eyebrow": f"知识点 {idx + 1:02d}",
                "title": station.get("title") or f"第 {idx + 1} 节",
                "bullets": bullets,
                "note": station.get("checkpoint") or "",
            }
        )
    if len(slides) == 1:
        slides.append(
            {
                "kind": "content",
                "eyebrow": "学习提示",
                "title": "这份资料可以这样学",
                "bullets": ["先通读原文，再合上资料复述要点", "遇到不理解的词，回到原文定位上下文"],
            }
        )
    slides.append(
        {
            "kind": "summary",
            "eyebrow": "课堂小结",
            "title": "把这份资料串起来",
            "bullets": [
                f"共 {len(stations)} 个知识点，建议按顺序学习",
                "每学完一页，试着用自己的话讲一遍",
                "最后用相关题库做一次检测",
            ],
        }
    )
    return {"title": title, "subtitle": subject, "slides": slides}


def _chart_html(chart: Dict[str, Any]) -> str:
    labels = [str(x) for x in (chart.get("labels") or [])][:8]
    values = []
    for x in (chart.get("values") or [])[:8]:
        try:
            values.append(float(x))
        except (TypeError, ValueError):
            values.append(0.0)
    unit = _html.escape(str(chart.get("unit") or ""))
    top = max(values or [1.0])
    rows = []
    for label, value in zip(labels, values):
        width = max(2, round(value / top * 100, 1)) if top else 2
        rows.append(
            f'<div class="bar-row"><span>{_html.escape(label)}</span>'
            f'<div class="bar-track"><i style="width:{width}%"></i></div>'
            f'<b>{value:g}{unit}</b></div>'
        )
    title = _html.escape(str(chart.get("title") or ""))
    return f'<div class="chart">{f"<h3>{title}</h3>" if title else ""}{"".join(rows)}</div>'


def _table_html(table: Dict[str, Any]) -> str:
    headers = [str(x) for x in (table.get("headers") or [])]
    rows = table.get("rows") or []
    head = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows[:8]
    )
    return f'<div class="table-wrap"><table class="data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _design_from_prompt(prompt: str) -> Dict[str, Any]:
    """把用户对演示效果的要求转成渲染参数。

    这是提示词能真正影响 HTML 的关键：以前 prompt 只影响 deck JSON，
    CSS 动画时长写死在模板里，用户说“延长到 4s”当然不会变化。
    """
    text = (prompt or "").strip().lower()
    design: Dict[str, Any] = {
        "enabled": True,
        "duration_ms": 420,
        "stagger_ms": 55,
    }
    if not text:
        return design
    if re.search(r"(不要|关闭|取消).{0,8}(动画|动效|过渡)|no\s+animation|disable\s+animation", text):
        design["enabled"] = False
        return design
    match = re.search(r"(\d+(?:\.\d+)?)\s*(毫秒|ms|秒|s)\b", text, flags=re.I)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        duration = value if unit in ("毫秒", "ms") else value * 1000
        design["duration_ms"] = max(200, min(10000, int(duration)))
    elif any(word in text for word in ("延长", "慢一点", "更慢", "slow")):
        design["duration_ms"] = 900
    elif any(word in text for word in ("快一点", "更快", "fast")):
        design["duration_ms"] = 260
    return design


def _render_html(deck: Dict[str, Any]) -> str:
    design = deck.get("design") if isinstance(deck.get("design"), dict) else {}
    duration = max(200, min(10000, int(design.get("duration_ms") or 420)))
    stagger = max(0, min(500, int(design.get("stagger_ms") or 55)))
    motion_off = "" if design.get("enabled", True) else " motion-off"
    version_label = f" · 第{deck.get('version')}版" if deck.get("version") else ""
    slides_html = []
    for i, slide in enumerate(deck["slides"]):
        layout = str(slide.get("layout") or ("cover" if i == 0 else "content"))
        bullets = "".join(f"<li>{_html.escape(str(b))}</li>" for b in slide.get("bullets") or [])
        note = (
            f'<div class="note">{_html.escape(str(slide.get("note") or ""))}</div>'
            if slide.get("note")
            else ""
        )
        extras = ""
        image = slide.get("image")
        if isinstance(image, dict) and image.get("url"):
            caption = _html.escape(str(image.get("caption") or ""))
            extras += (
                f'<figure class="visual-image"><img src="{_html.escape(str(image["url"]))}" alt="{caption}">'
                f'{f"<figcaption>{caption}</figcaption>" if caption else ""}</figure>'
            )
        chart = slide.get("chart")
        if isinstance(chart, dict):
            extras += _chart_html(chart)
        table = slide.get("table")
        if isinstance(table, dict):
            extras += _table_html(table)
        quote = slide.get("quote")
        if quote:
            extras += f'<blockquote class="quote-box">{_html.escape(str(quote))}</blockquote>'
        slides_html.append(
            f"""
            <section class="slide{' active' if i == 0 else ''} layout-{_html.escape(layout)}"
              data-index="{i}" data-page-index="{i + 1}"
              data-page-title="{_html.escape(str(slide.get('title') or ''), quote=True)}">
              <!-- page:{i + 1} -->
              <div class="slide-inner">
                <div class="eyebrow">{_html.escape(str(slide.get('eyebrow') or ''))}</div>
                <h1>{_html.escape(str(slide.get('title') or ''))}</h1>
                <ul>{bullets}</ul>
                {extras}
                {note}
              </div>
              <div class="slide-footer"><span>{_html.escape(deck['title'])}{version_label}</span><span>{i + 1} / {len(deck['slides'])}</span></div>
            </section>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(deck['title'])}{version_label} · 教学课件</title>
<style>
  :root {{ --ink:#111827; --muted:#6b7280; --accent:#2563eb; --line:#e5e7eb; --soft:#f8fafc; --motion-duration:{duration}ms; --motion-stagger:{stagger}ms; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:radial-gradient(circle at 12% 8%, #f3f7ff 0, #eef2f7 42%, #e9eef6 100%); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif; overflow:hidden; overscroll-behavior:none; }}
  .deck {{ width:100vw; height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }}
  .slide {{ display:none; width:min(1180px,100%); aspect-ratio:16/9; max-height:calc(100vh - 48px); background:#fff; border-radius:20px; box-shadow:0 20px 60px rgba(15,23,42,.14); padding:clamp(28px,5vw,70px); position:relative; }}
  .slide.active {{ display:flex; flex-direction:column; animation:micro-slide-in var(--motion-duration) cubic-bezier(.22,.8,.3,1) both; }}
  .slide.active .eyebrow {{ animation:micro-rise var(--motion-duration) .02s both; }}
  .slide.active h1 {{ animation:micro-rise var(--motion-duration) .07s both; }}
  .slide.active ul {{ animation:micro-rise var(--motion-duration) .12s both; }}
  .slide.active .visual-image, .slide.active .chart, .slide.active .table-wrap, .slide.active .quote-box {{ animation:micro-fade var(--motion-duration) .16s both; }}
  .slide.active .note {{ animation:micro-fade var(--motion-duration) .22s both; }}
  .motion-off .slide.active, .motion-off .slide.active .eyebrow, .motion-off .slide.active h1,
  .motion-off .slide.active ul, .motion-off .slide.active .visual-image, .motion-off .slide.active .chart,
  .motion-off .slide.active .table-wrap, .motion-off .slide.active .quote-box, .motion-off .slide.active .note {{ animation:none; }}
  .slide-inner {{ flex:1; min-height:0; overflow:auto; }}
  .eyebrow {{ color:var(--accent); font-size:13px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin-bottom:20px; }}
  h1 {{ font-size:clamp(26px,4.2vw,52px); line-height:1.15; letter-spacing:-1px; margin:0 0 26px; max-width:950px; }}
  ul {{ margin:0; padding-left:26px; }}
  li {{ font-size:clamp(15px,1.8vw,22px); line-height:1.7; margin:10px 0; color:#374151; }}
  .note {{ margin-top:22px; padding:12px 16px; border-left:3px solid var(--accent); background:var(--soft); color:var(--muted); font-size:14px; line-height:1.6; border-radius:0 8px 8px 0; }}
  .visual-image {{ display:flex; align-items:center; justify-content:center; margin:22px auto 8px; max-width:900px; border-radius:12px; overflow:hidden; background:var(--soft); }}
  .visual-image img {{ display:block; max-width:100%; max-height:390px; object-fit:contain; }}
  .visual-image figcaption {{ padding:7px 12px; color:var(--muted); font-size:12px; text-align:center; }}
  .chart {{ margin:22px auto 0; max-width:880px; padding:18px 22px; border:1px solid var(--line); border-radius:12px; background:#fff; }}
  .chart h3 {{ margin:0 0 12px; font-size:15px; color:#374151; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:9px 0; font-size:12px; color:#4b5563; }}
  .bar-row > span {{ width:125px; flex:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .bar-track {{ flex:1; height:10px; overflow:hidden; border-radius:999px; background:#eef2f7; }}
  .bar-track i {{ display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#93b4ff,#4176e6); }}
  .bar-row b {{ width:58px; flex:none; text-align:right; color:#111827; }}
  .table-wrap {{ margin:20px auto 0; max-width:980px; overflow:auto; border:1px solid var(--line); border-radius:10px; }}
  .data-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  .data-table th, .data-table td {{ padding:9px 12px; border-bottom:1px solid #f0f2f5; text-align:left; }}
  .data-table th {{ background:#f8fafc; color:#4b5563; font-weight:600; }}
  .data-table tr:last-child td {{ border-bottom:0; }}
  .quote-box {{ margin:26px auto; padding:22px 28px; max-width:900px; border-left:4px solid var(--accent); background:var(--soft); font-size:22px; line-height:1.6; color:#374151; border-radius:0 10px 10px 0; }}
  .slide-footer {{ display:flex; justify-content:space-between; gap:12px; color:#9ca3af; font-size:12px; padding-top:16px; border-top:1px solid var(--line); }}
  .controls {{ position:fixed; left:50%; bottom:20px; transform:translateX(-50%); display:flex; gap:8px; align-items:center; padding:8px; background:rgba(17,24,39,.86); border-radius:999px; box-shadow:0 8px 24px rgba(0,0,0,.2); z-index:10; }}
  .controls button {{ border:0; background:transparent; color:#fff; cursor:pointer; padding:8px 14px; border-radius:999px; font-size:13px; }}
  .controls button:hover {{ background:rgba(255,255,255,.14); }}
  .controls .counter {{ color:#d1d5db; font-size:12px; padding:0 8px; }}
  .progress {{ position:fixed; left:0; top:0; height:3px; background:var(--accent); transition:width .2s; z-index:2; }}
  @keyframes micro-slide-in {{
    from {{ opacity:0; transform:translateY(10px) scale(.994); }}
    to {{ opacity:1; transform:translateY(0) scale(1); }}
  }}
  @keyframes micro-rise {{
    from {{ opacity:0; transform:translateY(8px); }}
    to {{ opacity:1; transform:translateY(0); }}
  }}
  @keyframes micro-fade {{
    from {{ opacity:0; }}
    to {{ opacity:1; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .slide.active, .slide.active .eyebrow, .slide.active h1, .slide.active ul,
    .slide.active .visual-image, .slide.active .chart, .slide.active .table-wrap,
    .slide.active .quote-box, .slide.active .note {{ animation:none; }}
  }}
</style>
</head>
<body class="motion{motion_off}">
<div class="progress" id="progress"></div>
<div class="deck">{''.join(slides_html)}</div>
<div class="controls">
  <button type="button" onclick="show(current-1)">← 上一页</button>
  <span class="counter" id="counter">1 / {len(deck['slides'])}</span>
  <button type="button" onclick="show(current+1)">下一页 →</button>
  <button type="button" onclick="fullscreen()">全屏</button>
</div>
<script>
  var current = 0;
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var wheelLock = false;
  function show(next) {{
    current = Math.max(0, Math.min(slides.length - 1, next));
    slides.forEach(function (s, i) {{ s.classList.toggle('active', i === current); }});
    document.getElementById('counter').textContent = (current + 1) + ' / ' + slides.length;
    document.getElementById('progress').style.width = ((current + 1) / slides.length * 100) + '%';
  }}
  function fullscreen() {{
    if (!document.fullscreenElement) document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
    else document.exitFullscreen && document.exitFullscreen();
  }}
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {{ e.preventDefault(); show(current + 1); }}
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') {{ e.preventDefault(); show(current - 1); }}
  }});
  window.addEventListener('wheel', function (e) {{
    if (Math.abs(e.deltaY) < 24) return;
    e.preventDefault();
    if (wheelLock) return;
    wheelLock = true;
    show(current + (e.deltaY > 0 ? 1 : -1));
    setTimeout(function () {{ wheelLock = false; }}, 420);
  }}, {{ passive: false }});
  show(0);
</script>
</body>
</html>"""


def _slides_from_html(html_text: str, fallback: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从我们生成的 HTML 中提取标题/列表；否则使用结构化 deck。"""
    if not html_text:
        return fallback["slides"]
    sections = re.findall(r'<section class="slide[^"]*"[^>]*>(.*?)</section>', html_text, flags=re.S | re.I)
    if not sections:
        return fallback["slides"]
    slides = []
    for sec in sections:
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", sec, flags=re.S | re.I)
        if not title_m:
            continue
        bullets = [
            _clean(re.sub("<[^>]+>", " ", m))
            for m in re.findall(r"<li[^>]*>(.*?)</li>", sec, flags=re.S | re.I)
        ]
        slides.append(
            {
                "kind": "content",
                "title": _clean(re.sub("<[^>]+>", " ", title_m.group(1))),
                "bullets": [b for b in bullets if b][:6],
            }
        )
    return slides or fallback["slides"]


def _image_file(url: str) -> str | None:
    """把 /profile/... URL 映射到本地文件；外部 URL 暂不下载。"""
    url = str(url or "").strip()
    if not url:
        return None
    if url.startswith("/profile/"):
        path = os.path.join(settings.UPLOAD_DIR, url[len("/profile/"):])
        return path if os.path.isfile(path) else None
    if url.startswith("file://"):
        path = url[7:]
        return path if os.path.isfile(path) else None
    return None


def _add_fade_transition(slide, duration_ms: int = 700) -> None:
    """给单页 PPT 加淡入切换（PowerPoint 的 Fade transition）。

    python-pptx 没有动画 API，这里直接写 OOXML。它不会改变内容，
    只让用户在放映时看到页与页之间的淡入效果。
    """
    try:
        sld = slide.element
        for old in sld.findall(qn("p:transition")):
            sld.remove(old)
        transition = OxmlElement("p:transition")
        transition.set("spd", "med")
        transition.set("advClick", "1")
        fade = OxmlElement("p:fade")
        transition.append(fade)
        # p14:dur 是 PowerPoint 2010+ 的毫秒时长；老版本忽略它也不会坏。
        try:
            transition.set(
                "{http://schemas.microsoft.com/office/powerpoint/2010/main}dur",
                str(max(200, int(duration_ms))),
            )
        except Exception:
            pass
        sld.append(transition)
    except Exception:
        pass


def build_pptx_bytes(deck: Dict[str, Any], html_text: str = "") -> bytes:
    """生成 16:9 PPT，支持文字、图片、柱状图、表格与引用。"""
    slides = deck.get("slides") or _slides_from_html(html_text, deck)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    accent = RGBColor(0x25, 0x63, 0xEB)
    ink = RGBColor(0x11, 0x18, 0x27)
    muted = RGBColor(0x6B, 0x72, 0x80)

    def add_text(slide, left, top, width, height, text, size, color=ink, bold=False):
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = box.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.bold = bold
        return box

    for idx, s in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        bar = slide.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
        add_text(slide, 0.8, 0.55, 11.7, 0.4, (s.get("eyebrow") or ("知识点" if idx else "AI 教学课件")), 12, accent, True)
        add_text(slide, 0.8, 1.05, 11.7, 1.2, s.get("title") or "", 28, ink, True)

        layout = str(s.get("layout") or "content")
        text_top = 2.65
        image = s.get("image") if isinstance(s.get("image"), dict) else None
        if image and _image_file(image.get("url")):
            try:
                slide.shapes.add_picture(
                    _image_file(image.get("url")),
                    Inches(0.85), Inches(2.35), width=Inches(10.6),
                )
                text_top = 6.15
            except Exception:
                image = None

        chart = s.get("chart") if isinstance(s.get("chart"), dict) else None
        if chart and (chart.get("labels") or []):
            try:
                labels = [str(x) for x in chart.get("labels") or []][:8]
                values = []
                for value in (chart.get("values") or [])[:8]:
                    try:
                        values.append(float(value))
                    except (TypeError, ValueError):
                        values.append(0)
                chart_data = CategoryChartData()
                chart_data.categories = labels
                chart_data.add_series("系列 1", values)
                chart_type = XL_CHART_TYPE.PIE if str(chart.get("type")).lower() == "pie" else XL_CHART_TYPE.COLUMN_CLUSTERED
                slide.shapes.add_chart(
                    chart_type, Inches(0.8), Inches(2.35), Inches(11.7), Inches(3.8), chart_data
                )
                text_top = 6.2
            except Exception:
                pass

        table = s.get("table") if isinstance(s.get("table"), dict) else None
        if table and (table.get("headers") or table.get("rows")):
            headers = [str(x) for x in table.get("headers") or []]
            rows = [list(map(str, row)) for row in (table.get("rows") or [])][:8]
            if headers:
                rows = [headers] + rows
            if rows:
                try:
                    shape = slide.shapes.add_table(
                        len(rows), max(len(r) for r in rows),
                        Inches(0.8), Inches(2.35), Inches(11.7), Inches(0.5 + 0.42 * len(rows))
                    )
                    for r, row in enumerate(rows):
                        for c, value in enumerate(row):
                            shape.table.cell(r, c).text = value
                    text_top = 6.1
                except Exception:
                    pass

        bullets = s.get("bullets") or []
        y = text_top
        for b in bullets[:6]:
            if y > 6.45:
                break
            add_text(slide, 0.95, y, 11.5, 0.55, "• " + str(b), 16, RGBColor(0x37, 0x41, 0x51))
            y += 0.55
        quote = s.get("quote")
        if quote:
            add_text(slide, 1.0, min(y, 6.0), 11.2, 0.8, str(quote), 18, muted)
        add_text(slide, 0.8, 6.75, 9.0, 0.3, deck.get("title") or "", 9, muted)
        add_text(slide, 11.3, 6.75, 1.2, 0.3, f"{idx + 1} / {len(slides)}", 9, muted)
        _add_fade_transition(slide, int((deck.get("design") or {}).get("duration_ms") or 700))
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


async def build_micro_course_export(
    db,
    user_id: int,
    doc,
    prompt: str = "",
    base_deck: Dict[str, Any] | None = None,
    version: int = 0,
) -> Dict[str, Any]:
    course = await build_micro_course(db, user_id, doc)
    deck, ai_generated = await _ai_deck(
        db, user_id, doc, course, prompt_text=prompt, base_deck=base_deck
    )
    deck["design"] = _design_from_prompt(prompt)
    if version:
        deck["version"] = int(version)
    if not str(deck.get("changeSummary") or "").strip():
        deck["changeSummary"] = (
            f"按提示词修改：{prompt.strip()[:120]}"
            if prompt.strip()
            else "首次生成：围绕资料建立完整教学框架"
        )
    html = _render_html(deck)
    return {
        "document": course["document"],
        "overview": course["overview"],
        "deck": deck,
        "html": html,
        "slides": len(deck["slides"]),
        "aiGenerated": ai_generated,
    }


def _record_payload(record, include_html: bool = True) -> Dict[str, Any]:
    meta = record.meta_json or {}
    payload = {
        "recordId": int(record.id),
        "docId": int(record.doc_id),
        "version": int(record.version),
        "title": record.title,
        "changeSummary": record.change_summary or "",
        "slides": len((record.deck_json or {}).get("slides") or []),
        "aiGenerated": bool(record.ai_generated),
        "createdAt": record.create_time.isoformat() if record.create_time else "",
        "fileName": record.source_file_name or "",
        "status": getattr(record, "generation_status", "ready") or "ready",
        "progress": getattr(record, "progress_json", None) or {},
        "errorMsg": getattr(record, "error_msg", None) or "",
    }
    if include_html:
        payload["deck"] = record.deck_json or {}
        payload["html"] = record.html or ""
        payload["document"] = meta.get("document") or {
            "id": int(record.doc_id),
            "fileName": record.source_file_name or record.title,
        }
        payload["overview"] = meta.get("overview") or {
            "stationCount": payload["slides"],
            "totalMinutes": 0,
            "estimatedSessions": 1,
        }
    return payload


async def get_or_create_micro_course_record(
    db,
    user_id: int,
    doc,
    refresh: bool = False,
    prompt: str = "",
) -> Dict[str, Any]:
    """返回最新微课版本；refresh=True 或 prompt 非空时生成新版本。"""
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    latest = (
        await db.execute(
            select(RagMicroCourse)
            .where(
                RagMicroCourse.user_id == int(user_id),
                RagMicroCourse.doc_id == int(doc.id),
            )
            .order_by(RagMicroCourse.version.desc(), RagMicroCourse.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest and not refresh and not prompt.strip():
        payload = _record_payload(latest, include_html=True)
        payload["fromHistory"] = True
        return payload

    next_version = int(latest.version or 0) + 1 if latest else 1
    export = await build_micro_course_export(
        db,
        user_id,
        doc,
        prompt=prompt,
        base_deck=(latest.deck_json or {}) if latest else None,
        version=next_version,
    )
    version = next_version
    record = RagMicroCourse(
        user_id=int(user_id),
        doc_id=int(doc.id),
        version=version,
        title=str((export.get("deck") or {}).get("title") or doc.file_name or "教学课件")[:255],
        change_summary=str((export.get("deck") or {}).get("changeSummary") or "")[:300],
        html=export["html"],
        deck_json=export["deck"],
        meta_json={
            "document": export.get("document") or {},
            "overview": export.get("overview") or {},
        },
        ai_generated=1 if export.get("aiGenerated") else 0,
        source_file_name=doc.file_name,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    payload = _record_payload(record, include_html=True)
    payload["fromHistory"] = False
    return payload


async def start_micro_course_generation(
    db,
    user_id: int,
    doc,
    prompt: str = "",
    refresh: bool = False,
) -> Dict[str, Any]:
    """创建一次渐进式生成任务，立即返回一个可预览的初始版本。

    前端拿到 recordId 后轮询 `/status`，后台每生成一页就更新一次 HTML。
    """
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    latest = (
        await db.execute(
            select(RagMicroCourse)
            .where(
                RagMicroCourse.user_id == int(user_id),
                RagMicroCourse.doc_id == int(doc.id),
            )
            .order_by(RagMicroCourse.version.desc(), RagMicroCourse.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest and not refresh and not prompt.strip():
        if (latest.generation_status or "ready") == "generating":
            return _record_payload(latest, include_html=True)
        return _record_payload(latest, include_html=True)

    version = int(latest.version or 0) + 1 if latest else 1
    course = await build_micro_course(db, int(user_id), doc)
    if latest and prompt.strip() and isinstance(latest.deck_json, dict):
        initial_deck = json.loads(json.dumps(latest.deck_json, ensure_ascii=False))
    else:
        initial_deck = _deck_from_stations(course, doc.image_map or {})
    initial_deck["design"] = _design_from_prompt(prompt)
    initial_deck["version"] = version
    initial_deck["changeSummary"] = (
        f"正在按提示词更新：{prompt.strip()[:120]}" if prompt.strip() else "正在生成教学页面..."
    )
    record = RagMicroCourse(
        user_id=int(user_id),
        doc_id=int(doc.id),
        version=version,
        title=str(initial_deck.get("title") or doc.file_name or "教学课件")[:255],
        change_summary=initial_deck["changeSummary"][:300],
        html=_render_html(initial_deck),
        deck_json=initial_deck,
        meta_json={"document": {"id": int(doc.id), "fileName": doc.file_name}},
        ai_generated=1,
        source_file_name=doc.file_name,
        generation_status="generating",
        progress_json={"current": 1, "total": len(initial_deck.get("slides") or []) or 1, "phase": "正在生成页面"},
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    payload = _record_payload(record, include_html=True)
    payload["fromHistory"] = False
    return payload


async def run_micro_course_generation(
    record_id: int,
    user_id: int,
    doc_id: int,
    prompt: str = "",
    base_deck: Dict[str, Any] | None = None,
) -> None:
    """后台逐页更新生成结果；每页都是局部刷新。"""
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.rag import RagDocument, RagMicroCourse

    async with async_session_factory() as db:
        record = await db.scalar(select(RagMicroCourse).where(RagMicroCourse.id == int(record_id)))
        if not record:
            return
        doc = await db.scalar(select(RagDocument).where(RagDocument.id == int(doc_id)))
        if not doc:
            record.generation_status = "failed"
            record.error_msg = "原资料不存在"
            await db.commit()
            return
        try:
            export = await build_micro_course_export(
                db,
                int(user_id),
                doc,
                prompt=prompt,
                base_deck=base_deck,
                version=int(record.version),
            )
            deck = export["deck"]
            slides = deck.get("slides") or []
            for i in range(1, len(slides) + 1):
                partial = json.loads(json.dumps(deck, ensure_ascii=False))
                partial["slides"] = slides[:i]
                partial["version"] = int(record.version)
                partial["changeSummary"] = deck.get("changeSummary") or "正在生成教学页面..."
                record.html = _render_html(partial)
                record.deck_json = partial
                record.title = str(partial.get("title") or record.title)[:255]
                record.progress_json = {
                    "current": i,
                    "total": len(slides),
                    "phase": f"正在生成第 {i} 页 / 共 {len(slides)} 页",
                }
                record.generation_status = "generating"
                await db.commit()
                await asyncio.sleep(0.12)
            record.html = export["html"]
            record.deck_json = deck
            record.title = str(deck.get("title") or record.title)[:255]
            record.change_summary = str(deck.get("changeSummary") or "")[:300]
            record.generation_status = "ready"
            record.error_msg = None
            record.progress_json = {"current": len(slides), "total": len(slides), "phase": "生成完成"}
            await db.commit()
        except Exception as exc:
            await db.rollback()
            record = await db.scalar(select(RagMicroCourse).where(RagMicroCourse.id == int(record_id)))
            if record:
                record.generation_status = "failed"
                record.error_msg = str(exc)[:300]
                record.progress_json = {"phase": "生成失败"}
                await db.commit()
            logger.exception("micro course progressive generation failed: %s", exc)


async def get_micro_course_generation_status(db, user_id: int, doc_id: int) -> Dict[str, Any] | None:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    record = (
        await db.execute(
            select(RagMicroCourse)
            .where(
                RagMicroCourse.user_id == int(user_id),
                RagMicroCourse.doc_id == int(doc_id),
            )
            .order_by(RagMicroCourse.version.desc(), RagMicroCourse.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _record_payload(record, include_html=True) if record else None


async def list_micro_course_history(db, user_id: int, doc_id: int) -> List[Dict[str, Any]]:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    rows = (
        await db.execute(
            select(RagMicroCourse)
            .where(
                RagMicroCourse.user_id == int(user_id),
                RagMicroCourse.doc_id == int(doc_id),
            )
            .order_by(RagMicroCourse.version.desc(), RagMicroCourse.id.desc())
        )
    ).scalars().all()
    return [_record_payload(r, include_html=False) for r in rows]


async def get_micro_course_record(db, user_id: int, record_id: int) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    record = (
        await db.execute(
            select(RagMicroCourse).where(
                RagMicroCourse.id == int(record_id),
                RagMicroCourse.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise ValueError("微课历史版本不存在或无权访问")
    payload = _record_payload(record, include_html=True)
    payload["fromHistory"] = True
    return payload


async def _save_slide_version(db, user_id: int, base, deck: Dict[str, Any], summary: str) -> Dict[str, Any]:
    """把修改后的 deck 保存为新版本，保留当前版本作为对比基线。"""
    from sqlalchemy import func, select
    from app.models.rag import RagMicroCourse

    latest_version = await db.scalar(
        select(func.max(RagMicroCourse.version)).where(
            RagMicroCourse.user_id == int(user_id),
            RagMicroCourse.doc_id == int(base.doc_id),
        )
    )
    version = int(latest_version or 0) + 1
    deck = json.loads(json.dumps(deck, ensure_ascii=False))
    deck["version"] = version
    record = RagMicroCourse(
        user_id=int(user_id),
        doc_id=int(base.doc_id),
        version=version,
        title=str(deck.get("title") or base.title or "教学课件")[:255],
        change_summary=summary[:300],
        html=_render_html(deck),
        deck_json=deck,
        meta_json=base.meta_json or {},
        ai_generated=int(base.ai_generated or 0),
        source_file_name=base.source_file_name,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    payload = _record_payload(record, include_html=True)
    payload["fromHistory"] = False
    return payload


async def edit_micro_course_slide(
    db, user_id: int, record_id: int, slide_index: int, patch: Dict[str, Any]
) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    base = (
        await db.execute(
            select(RagMicroCourse).where(
                RagMicroCourse.id == int(record_id),
                RagMicroCourse.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not base:
        raise ValueError("微课版本不存在或无权编辑")
    deck = json.loads(json.dumps(base.deck_json or {}, ensure_ascii=False))
    slides = deck.get("slides") or []
    index = int(slide_index)
    if index < 0 or index >= len(slides):
        raise ValueError("页码超出范围")
    before = slides[index]
    after = dict(before)
    for key in ("layout", "eyebrow", "title", "bullets", "note", "image", "chart", "table", "quote"):
        if key in patch:
            after[key] = patch[key]
    if not str(after.get("title") or "").strip():
        raise ValueError("页面标题不能为空")
    slides[index] = after
    deck["slides"] = slides
    summary = f"单页编辑：第 {index + 1} 页「{after.get('title', '')}」"
    payload = await _save_slide_version(db, user_id, base, deck, summary)
    payload["before"] = before
    payload["after"] = after
    return payload


async def reorder_micro_course_slides(
    db, user_id: int, record_id: int, from_index: int, to_index: int
) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    base = (
        await db.execute(
            select(RagMicroCourse).where(
                RagMicroCourse.id == int(record_id),
                RagMicroCourse.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not base:
        raise ValueError("微课版本不存在或无权编辑")
    deck = json.loads(json.dumps(base.deck_json or {}, ensure_ascii=False))
    slides = deck.get("slides") or []
    if not (0 <= int(from_index) < len(slides) and 0 <= int(to_index) < len(slides)):
        raise ValueError("拖动位置超出范围")
    moved = slides.pop(int(from_index))
    slides.insert(int(to_index), moved)
    deck["slides"] = slides
    summary = f"调整页面顺序：第 {int(from_index) + 1} 页移动到第 {int(to_index) + 1} 页"
    return await _save_slide_version(db, user_id, base, deck, summary)


async def regenerate_micro_course_slide(
    db, user_id: int, record_id: int, slide_index: int, prompt: str = ""
) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.rag import RagDocument, RagMicroCourse

    base = (
        await db.execute(
            select(RagMicroCourse).where(
                RagMicroCourse.id == int(record_id),
                RagMicroCourse.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not base:
        raise ValueError("微课版本不存在或无权编辑")
    doc = await db.scalar(select(RagDocument).where(RagDocument.id == int(base.doc_id)))
    if not doc:
        raise ValueError("原资料不存在")
    export = await build_micro_course_export(
        db,
        user_id,
        doc,
        prompt=(prompt or "只重写这一页，保持其他页面不变")[:1000],
        base_deck=base.deck_json or {},
    )
    new_slides = (export.get("deck") or {}).get("slides") or []
    if not new_slides:
        raise ValueError("AI 没有生成有效页面")
    deck = json.loads(json.dumps(base.deck_json or {}, ensure_ascii=False))
    slides = deck.get("slides") or []
    index = max(0, min(int(slide_index), len(slides) - 1))
    # 保留原页面标题作为锚点；优先使用 AI 返回的同位置页，避免整份跑偏
    slides[index] = new_slides[index] if index < len(new_slides) else new_slides[0]
    deck["slides"] = slides
    summary = f"单页重新生成：第 {index + 1} 页"
    payload = await _save_slide_version(db, user_id, base, deck, summary)
    payload["before"] = (base.deck_json or {}).get("slides", [])[index] if (base.deck_json or {}).get("slides") else {}
    payload["after"] = slides[index]
    return payload


async def insert_micro_course_slide(
    db, user_id: int, record_id: int, slide_index: int, slide: Dict[str, Any]
) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    base = (
        await db.execute(
            select(RagMicroCourse).where(
                RagMicroCourse.id == int(record_id),
                RagMicroCourse.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not base:
        raise ValueError("微课版本不存在或无权编辑")
    deck = json.loads(json.dumps(base.deck_json or {}, ensure_ascii=False))
    slides = deck.get("slides") or []
    index = max(0, min(int(slide_index), len(slides)))
    slides.insert(index, slide)
    deck["slides"] = slides
    summary = f"插入新页面：第 {index + 1} 页「{slide.get('title', '')}」"
    return await _save_slide_version(db, user_id, base, deck, summary)



async def get_latest_micro_course_record(db, user_id: int, doc_id: int):
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    return (
        await db.execute(
            select(RagMicroCourse)
            .where(
                RagMicroCourse.user_id == int(user_id),
                RagMicroCourse.doc_id == int(doc_id),
            )
            .order_by(RagMicroCourse.version.desc(), RagMicroCourse.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _deck_from_imported_html(html_text: str, title: str = "") -> Dict[str, Any]:
    """把用户导入的 HTML 粗略拆成 deck，用于导出 PPT；原 HTML 仍保留给在线演示。"""
    text = html_text or ""
    # 优先识别我们约定的 <section class="slide"> 结构
    sections = re.findall(r'<section[^>]*class="[^"]*slide[^"]*"[^>]*>(.*?)</section>', text, flags=re.S | re.I)
    slides: List[Dict[str, Any]] = []
    if sections:
        for sec in sections:
            h = re.search(r"<h[12][^>]*>(.*?)</h[12]>", sec, flags=re.S | re.I)
            if not h:
                continue
            bullets = [
                _clean(re.sub("<[^>]+>", " ", x))
                for x in re.findall(r"<li[^>]*>(.*?)</li>", sec, flags=re.S | re.I)
            ]
            slides.append(
                {
                    "kind": "content",
                    "layout": "content",
                    "eyebrow": "导入课件",
                    "title": _clean(re.sub("<[^>]+>", " ", h.group(1)))[:100],
                    "bullets": [b for b in bullets if b][:6],
                }
            )
    if not slides:
        # 普通网页：按 h1/h2 切页，取紧随其后的段落和列表
        matches = list(re.finditer(r"<h[12][^>]*>(.*?)</h[12]>", text, flags=re.S | re.I))
        for idx, match in enumerate(matches[:12]):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = re.sub(r"<[^>]+>", " ", text[match.end():end])
            body = _clean(body)
            bullets = [b.strip() for b in re.split(r"[。；;]\s*", body) if len(b.strip()) >= 6][:3]
            slides.append(
                {
                    "kind": "content",
                    "layout": "content",
                    "eyebrow": "导入课件",
                    "title": _clean(re.sub("<[^>]+>", " ", match.group(1)))[:100] or f"第 {idx + 1} 页",
                    "bullets": bullets,
                }
            )
    plain = _clean(re.sub(r"<[^>]+>", " ", text))
    if not slides and plain:
        slides = [{"kind": "content", "layout": "content", "eyebrow": "导入内容", "title": title or "导入的课件", "bullets": [plain[:120]]}]
    if not slides:
        raise ValueError("HTML 里没有可识别的内容")
    return {"title": title or slides[0]["title"] or "导入的课件", "subtitle": "用户导入", "slides": slides}


async def import_micro_course_html(db, user_id: int, doc, html_text: str, title: str = "") -> Dict[str, Any]:
    """保存一份用户导入的 HTML 作为新版本。"""
    from sqlalchemy import select
    from app.models.rag import RagMicroCourse

    raw = (html_text or "").strip()
    if not raw:
        raise ValueError("导入的 HTML 不能为空")
    if len(raw) > 2_000_000:
        raise ValueError("HTML 文件过大，请控制在 2MB 以内")
    if "<" not in raw:
        raise ValueError("这不像 HTML，请检查文件内容")
    deck = _deck_from_imported_html(raw, title=title)
    course = await build_micro_course(db, user_id, doc)
    latest = await get_latest_micro_course_record(db, user_id, doc.id)
    version = int(latest.version or 0) + 1 if latest else 1
    deck["version"] = version
    record = RagMicroCourse(
        user_id=int(user_id),
        doc_id=int(doc.id),
        version=version,
        title=str(deck.get("title") or title or doc.file_name or "导入课件")[:255],
        change_summary=f"导入 HTML：{title or doc.file_name or '外部课件'}"[:300],
        html=raw,
        deck_json=deck,
        meta_json={"document": course.get("document") or {}, "overview": course.get("overview") or {}},
        ai_generated=0,
        source_file_name=doc.file_name,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    payload = _record_payload(record, include_html=True)
    payload["fromHistory"] = False
    payload["imported"] = True
    return payload


__all__ = [
    "build_micro_course_export",
    "build_pptx_bytes",
    "build_micro_course",
    "get_or_create_micro_course_record",
    "list_micro_course_history",
    "get_micro_course_record",
    "get_latest_micro_course_record",
    "import_micro_course_html",
]
