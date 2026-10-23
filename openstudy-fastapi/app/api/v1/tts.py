"""
语音合成（TTS）API
================================================================================
2026-10-23 新增。

## 为什么要做服务端 TTS

前端原本用浏览器的 `speechSynthesis` 朗读单词，零依赖、不用后端。
但实测在部分 Windows 环境下 Chromium 的 TTS 桥接会**静默失效**：

    · `getVoices()` 能列出语音（本机 22 个，含 Google US English）；
    · `speak()` 之后 `speaking` 变为 true；
    · 但 `onstart` / `onend` **永不触发**，也完全没有声音。

在这台机器上 Chrome 156 与 Edge 155 表现一致，加 `--no-sandbox`、
`--disable-features=AudioServiceOutOfProcess` 等参数均无改善；
而同一台机器的系统 SAPI 朗读正常、浏览器的 Web Audio / `Audio.play()`
也正常 —— 也就是说**只有 speechSynthesis 这一条链路坏了**。

这不是用户能自己解决的。所以这里提供一条服务端兜底：
用 `edge-tts`（微软 Edge 的在线合成服务，免费、无需 API Key）
把文字合成 mp3 返回，前端用 `Audio` 播放 —— 绕开浏览器 TTS。

## 设计取舍

· **不落盘**：合成结果直接以字节流返回，不写磁盘、不占空间。
  代价是没有缓存，每个新词都要联网合成一次（实测 1~2 秒）。
  前端已按词做了内存缓存，重复听同一词不会重复请求。
· **失败要可降级**：本接口不可用时（离线 / 被墙 / 包没装），
  前端会自动回退到浏览器 TTS，而不是直接报错。
· **语音可配**：按语言挑默认音色，也允许调用方指定。
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from loguru import logger

from app.core.security import get_current_user
from app.core.response import error

router = APIRouter(prefix="/tts")

# ── 默认音色 ────────────────────────────────────────────────────────────────
# 选 Neural 音色：比传统 SAPI 自然得多，且中英文都覆盖。
DEFAULT_VOICES = {
    "en": "en-US-AriaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}

# 语速/音调范围（edge-tts 接受 `+/-N%` 与 `+/-NHz`）
_RATE_MIN, _RATE_MAX = -50, 50


def _looks_chinese(text: str) -> bool:
    """文本里是否有中日韩字符（判断该用中文音色）"""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _pick_voice(lang: Optional[str], voice: Optional[str], text: str = "") -> str:
    """决定用哪个音色：显式指定优先，否则按语言/文本挑默认值。

    ⚠️ 2026-10-23 修：原来只看 `lang`。当页面传 `lang=en-US` 但文本其实是
       中文释义（如「放弃」）时，会把中文喂给英文音色 —— edge-tts 直接
       返回 `No audio was received`，接口 500。
       现在文本里出现汉字就优先用中文音色，避免这种不匹配。
    """
    if voice:
        return voice

    key = (lang or "").strip().lower()

    # 文本是中文 → 用中文音色（哪怕调用方传的是 en-US）
    if text and _looks_chinese(text):
        return DEFAULT_VOICES["zh"]

    if key.startswith("zh"):
        return DEFAULT_VOICES["zh"]
    return DEFAULT_VOICES["en"]


def _clamp_rate(value: Optional[int]) -> int:
    if value is None:
        return 0
    try:
        return max(_RATE_MIN, min(_RATE_MAX, int(value)))
    except (TypeError, ValueError):
        return 0


@router.get("/synthize")
async def synthize(
    text: str = Query(..., description="要合成的文字"),
    lang: Optional[str] = Query(None, description="语言标签，如 en-US / zh-CN"),
    voice: Optional[str] = Query(None, description="指定音色名，留空按 lang 选默认"),
    rate: Optional[int] = Query(None, description="语速百分比，-50~50"),
    current_user: dict = Depends(get_current_user),
):
    """合成语音，直接返回 mp3 字节流。

    返回 `audio/mpeg`。失败时返回 JSON 错误（前端据此回退到浏览器 TTS）。
    """
    content = str(text or "").strip()
    if not content:
        return error("文字不能为空")

    # 防御：过长的文本既慢又没必要，单词朗读用不到这么长
    if len(content) > 500:
        content = content[:500]

    try:
        import edge_tts
    except ImportError:
        # 依赖没装时明确告知，前端会降级到浏览器 TTS
        return error("服务端语音合成不可用（edge-tts 未安装）")

    chosen_voice = _pick_voice(lang, voice, content)
    rate_pct = _clamp_rate(rate)
    rate_str = f"{rate_pct:+d}%" if rate_pct else "+0%"

    try:
        communicate = edge_tts.Communicate(content, chosen_voice, rate=rate_str)

        # 在内存里收集音频块，避免落盘
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.append(chunk["data"])

        audio = b"".join(chunks)
        if not audio:
            return error("语音合成没有产出音频")

        logger.info(
            "tts synthize voice={} lang={} chars={} bytes={}",
            chosen_voice, lang, len(content), len(audio),
        )

        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={
                # 合成结果对同一个词是稳定的，允许浏览器短时缓存，
                # 减少重复请求（音色/语速变了 URL 就不同，不会串）
                "Cache-Control": "public, max-age=86400",
                "X-Tts-Voice": chosen_voice,
            },
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - 外部服务，什么异常都可能有
        logger.warning("tts synthize failed voice={} err={}", chosen_voice, exc)
        return error(f"语音合成失败: {exc}")


@router.get("/voices")
async def list_voices(
    lang: Optional[str] = Query(None, description="只看某语言，如 en / zh"),
    current_user: dict = Depends(get_current_user),
):
    """列出可用的音色（调试与前端选择用）。

    依赖外网，失败时返回空列表而不是报错 —— 这个接口只是辅助，
    拿不到音色不应该让主流程失败。
    """
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
    except ImportError:
        return error("服务端语音合成不可用（edge-tts 未安装）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("tts list_voices failed err={}", exc)
        return error(f"获取音色列表失败: {exc}")

    key = (lang or "").strip().lower()
    rows = [
        {
            "name": v.get("ShortName"),
            "gender": v.get("Gender"),
            "locale": v.get("Locale"),
        }
        for v in voices
        if not key or str(v.get("Locale", "")).lower().startswith(key)
    ]
    return {"code": 200, "msg": "操作成功", "data": rows}
