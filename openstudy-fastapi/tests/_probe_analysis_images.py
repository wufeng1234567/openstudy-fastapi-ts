# -*- coding: utf-8 -*-
"""探针：AI 题目解析的图片读取链路（用户 2026-10-12）

背景：AI 解析题目读不到图片，且组合题（阅读理解/完形填空）的小题完全没发给 AI。
本探针验证后端三件事：
  1. `extract_image_urls_from_html` 能从题干/材料/小题 HTML 里按序去重抽出 <img src>；
  2. `stored_image_to_data_url` 能把本站相对路径 `/profile/upload/...` 读盘转成 data URL，
     并原样放行 data:/http(s)，对坏路径/非图片返回空串；
  3. `normalize_image_urls` 归一后丢弃空项（不能塞空串，否则上游 400）；
  4. `_build_analysis` 在给定 `sub_questions` 时把小题拼进提示词。

用法：.venv/Scripts/python.exe tests/_probe_analysis_images.py   # 退出 0
"""
import os
import sys
import base64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ROWS = []


def check(cid, title, cond, actual=""):
    ROWS.append({"cid": cid, "title": title, "ok": bool(cond), "actual": actual})


def main():
    from app.services.ai.chat_engine import (
        extract_image_urls_from_html,
        stored_image_to_data_url,
        normalize_image_urls,
    )
    from app.services.ai import prompts

    # 1) 抽取：题干里的多张图 + 顺序 + 去重
    html = (
        '<p>如图1</p><img src="/profile/upload/a.png" alt="x">'
        '<p>如图2</p><img class="q" src="/profile/upload/b.jpg">'
        '<img src="/profile/upload/a.png">'  # 重复，应去重
    )
    urls = extract_image_urls_from_html(html)
    check("X1", "抽出 2 张(去重保序)", urls == ["/profile/upload/a.png", "/profile/upload/b.jpg"], str(urls))
    check("X2", "无图返回空", extract_image_urls_from_html("<p>纯文本</p>") == [])
    check("X3", "单引号 src 也能抽", extract_image_urls_from_html("<img src='/profile/upload/c.png'>") == ["/profile/upload/c.png"])

    # 2) 相对路径 → data URL（读盘）
    from app.config import settings
    # 造一张真实小图落到 UPLOAD_DIR/upload/2026/01/01/probe_img.png
    rel_dir = os.path.join(settings.UPLOAD_DIR, "upload", "2026", "01", "01")
    os.makedirs(rel_dir, exist_ok=True)
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+P+/HgAFhAJ/"
        "w1cAAAAASUVORK5CYII="
    )
    png_name = "probe_img.png"
    with open(os.path.join(rel_dir, png_name), "wb") as f:
        f.write(png_bytes)
    rel_url = "/profile/upload/2026/01/01/" + png_name

    du = stored_image_to_data_url(rel_url)
    check("X4", "相对路径→data URL", du.startswith("data:image/png;base64,") and len(du) > 30, du[:40])
    # 解码回原字节，确认读的是正确文件
    try:
        b64 = du.split(",", 1)[1]
        check("X5", "data URL 内容与落盘一致", base64.b64decode(b64) == png_bytes)
    except Exception as e:
        check("X5", "data URL 内容与落盘一致", False, str(e))

    check("X6", "http(s) 原样放行", stored_image_to_data_url("https://x.com/a.png") == "https://x.com/a.png")
    check("X7", "data URL 原样放行", stored_image_to_data_url("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA")
    check("X8", "不存在文件→空串", stored_image_to_data_url("/profile/upload/nope.png") == "")
    check("X9", "非图片扩展名→空串", stored_image_to_data_url("/profile/upload/x.txt") == "")
    check("X10", "路径穿越被拒→空串", stored_image_to_data_url("/profile/upload/../../etc/passwd") == "")

    # X10b：⚠️ 用户实测 bug —— 开发环境存在 `/dev-api/profile/upload/...` 前缀
    #       （VITE_APP_BASE_API=/dev-api），旧实现只剥 `/profile/` 前缀 → 读盘路径错 → 图片被丢。
    #       同时覆盖 staging 的 `/stage-api` 与绝对域名前缀。
    du_dev = stored_image_to_data_url("/dev-api/profile/upload/2026/01/01/" + png_name)
    check("X10b", "/dev-api 前缀 → 读盘转 data URL", du_dev.startswith("data:image/png;base64,") and len(du_dev) > 30, du_dev[:40])
    du_stage = stored_image_to_data_url("/stage-api/profile/upload/2026/01/01/" + png_name)
    check("X10c", "/stage-api 前缀 → 读盘转 data URL", du_stage.startswith("data:image/png;base64,"), du_stage[:40])
    du_abs = stored_image_to_data_url("http://localhost:9101/profile/upload/2026/01/01/" + png_name)
    check("X10d", "绝对 http 原样放行（不读盘）", du_abs == "http://localhost:9101/profile/upload/2026/01/01/" + png_name, du_abs[:40])

    # 3) normalize：丢弃空项，保留有效项
    norm = normalize_image_urls([rel_url, "", "/profile/upload/nope.png", "https://x.com/a.png"])
    check("X11", "normalize 丢空留有效(2 项)", len(norm) == 2 and norm[0].startswith("data:image/png") and norm[1] == "https://x.com/a.png", str([n[:20] for n in norm]))

    # 4) 组合题小题拼进分析提示词
    msgs = prompts._build_analysis(
        "",
        question="材料正文",
        question_type="组合题",
        sub_questions="第1小题：求 x\n答案：A",
    )
    user_msg = msgs[-1]["content"]
    check("X12", "分析提示词含小题", "第1小题" in user_msg and "材料正文" in user_msg, user_msg[:60].replace("\n", " "))
    msgs2 = prompts._build_analysis("", question="单独一题")
    check("X13", "无小题时不出现『小题』节", "## 小题" not in msgs2[-1]["content"])

    # 清理
    try:
        os.remove(os.path.join(rel_dir, png_name))
    except OSError:
        pass

    ok = all(r["ok"] for r in ROWS)
    for r in ROWS:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['cid']} {r['title']}   {r['actual']}")
    print("结论:", "全部通过" if ok else "存在失败")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
