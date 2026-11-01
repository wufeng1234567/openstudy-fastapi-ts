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

import html as _html
import io
import re
from typing import Any, Dict, List

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from app.services.micro_course_service import build_micro_course


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


def _deck_from_stations(course: Dict[str, Any]) -> Dict[str, Any]:
    doc = course.get("document") or {}
    stations = course.get("stations") or []
    title = doc.get("fileName") or "教学微课"
    subject = doc.get("subject") or "综合"
    slides: List[Dict[str, Any]] = [
        {
            "kind": "cover",
            "eyebrow": "AI 教学课件",
            "title": title,
            "subtitle": f"{subject} · 约 {course.get('overview', {}).get('stationCount', len(stations))} 个知识点",
            "bullets": [
                "先看整体结构，再逐个知识点理解",
                "每页都可以直接投屏演示，也可以下载为 PPT",
            ],
        }
    ]
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


def _render_html(deck: Dict[str, Any]) -> str:
    slides_html = []
    for i, slide in enumerate(deck["slides"]):
        bullets = "".join(f"<li>{_html.escape(str(b))}</li>" for b in slide.get("bullets") or [])
        note = (
            f'<div class="note">{_html.escape(str(slide.get("note") or ""))}</div>'
            if slide.get("note")
            else ""
        )
        slides_html.append(
            f"""
            <section class="slide{' active' if i == 0 else ''}" data-index="{i}">
              <div class="slide-inner">
                <div class="eyebrow">{_html.escape(str(slide.get('eyebrow') or ''))}</div>
                <h1>{_html.escape(str(slide.get('title') or ''))}</h1>
                <ul>{bullets}</ul>
                {note}
              </div>
              <div class="slide-footer"><span>{_html.escape(deck['title'])}</span><span>{i + 1} / {len(deck['slides'])}</span></div>
            </section>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(deck['title'])} · 教学课件</title>
<style>
  :root {{ --ink:#111827; --muted:#6b7280; --accent:#2563eb; --line:#e5e7eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#eef2f7; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; overflow:hidden; }}
  .deck {{ width:100vw; height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }}
  .slide {{ display:none; width:min(1180px,100%); aspect-ratio:16/9; max-height:calc(100vh - 48px); background:#fff; border-radius:20px; box-shadow:0 20px 60px rgba(15,23,42,.14); padding:clamp(28px,5vw,70px); position:relative; }}
  .slide.active {{ display:flex; flex-direction:column; }}
  .slide-inner {{ flex:1; min-height:0; overflow:auto; }}
  .eyebrow {{ color:var(--accent); font-size:13px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin-bottom:20px; }}
  h1 {{ font-size:clamp(26px,4.2vw,52px); line-height:1.15; letter-spacing:-1px; margin:0 0 30px; max-width:900px; }}
  ul {{ margin:0; padding-left:26px; }}
  li {{ font-size:clamp(16px,2vw,24px); line-height:1.7; margin:12px 0; color:#374151; }}
  .note {{ margin-top:26px; padding:14px 18px; border-left:3px solid var(--accent); background:#f8fafc; color:var(--muted); font-size:14px; line-height:1.6; border-radius:0 8px 8px 0; }}
  .slide-footer {{ display:flex; justify-content:space-between; gap:12px; color:#9ca3af; font-size:12px; padding-top:18px; border-top:1px solid var(--line); }}
  .controls {{ position:fixed; left:50%; bottom:20px; transform:translateX(-50%); display:flex; gap:8px; align-items:center; padding:8px; background:rgba(17,24,39,.86); border-radius:999px; box-shadow:0 8px 24px rgba(0,0,0,.2); }}
  .controls button {{ border:0; background:transparent; color:#fff; cursor:pointer; padding:8px 14px; border-radius:999px; font-size:13px; }}
  .controls button:hover {{ background:rgba(255,255,255,.14); }}
  .controls .counter {{ color:#d1d5db; font-size:12px; padding:0 8px; }}
  .progress {{ position:fixed; left:0; top:0; height:3px; background:var(--accent); transition:width .2s; z-index:2; }}
</style>
</head>
<body>
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


def build_pptx_bytes(deck: Dict[str, Any], html_text: str = "") -> bytes:
    """生成 16:9 PPT。html_text 有值时先尝试按 HTML 的 slide 结构转换。"""
    slides = _slides_from_html(html_text, deck)
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
        # 顶部细色条
        bar = slide.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
        add_text(slide, 0.8, 0.55, 11.7, 0.4, (s.get("eyebrow") or ("知识点" if idx else "AI 教学课件")), 12, accent, True)
        add_text(slide, 0.8, 1.05, 11.7, 1.2, s.get("title") or "", 28, ink, True)
        bullets = s.get("bullets") or []
        y = 2.65
        for b in bullets[:6]:
            add_text(slide, 0.95, y, 11.5, 0.55, "• " + str(b), 16, RGBColor(0x37, 0x41, 0x51))
            y += 0.62
        add_text(slide, 0.8, 6.75, 9.0, 0.3, deck.get("title") or "", 9, muted)
        add_text(slide, 11.3, 6.75, 1.2, 0.3, f"{idx + 1} / {len(slides)}", 9, muted)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


async def build_micro_course_export(db, user_id: int, doc) -> Dict[str, Any]:
    course = await build_micro_course(db, user_id, doc)
    deck = _deck_from_stations(course)
    html = _render_html(deck)
    return {
        "document": course["document"],
        "overview": course["overview"],
        "deck": deck,
        "html": html,
        "slides": len(deck["slides"]),
    }


__all__ = ["build_micro_course_export", "build_pptx_bytes", "build_micro_course"]
