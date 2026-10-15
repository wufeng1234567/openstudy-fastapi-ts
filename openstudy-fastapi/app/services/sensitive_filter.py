"""
敏感词过滤服务
- 从数据库加载敏感词,构建 Trie 树(前缀树)实现高效匹配
- 支持 replace / block / tag 三种模式
- 提供 check(text) -> {hasSensitive, words, replacedText}
- 单例 + TTL 缓存,避免每次请求都查数据库
"""

import time
from typing import List, Optional

from loguru import logger


class _TrieNode:
    """Trie 树节点"""

    __slots__ = ("children", "is_end", "word")

    def __init__(self):
        self.children = {}  # char -> _TrieNode
        self.is_end = False  # 是否构成一个完整敏感词
        self.word = ""  # 完整敏感词文本(仅 is_end=True 时有效)


class SensitiveFilter:
    """敏感词过滤器(基于 Trie 树)"""

    # 单例 + 缓存
    _instance: Optional["SensitiveFilter"] = None
    _cache_ts: float = 0.0
    _cache_ttl: float = 300.0  # 缓存有效期 5 分钟

    def __init__(self):
        self._root = _TrieNode()
        self._word_count = 0

    # ----------------------------------------------------------
    # 加载
    # ----------------------------------------------------------
    def load_words(self, words: List[str]) -> None:
        """加载敏感词列表,构建(重建)Trie 树"""
        self._root = _TrieNode()
        self._word_count = 0
        for word in words:
            self._add_word(word)

    def _add_word(self, word: str) -> None:
        word = (word or "").strip()
        if not word:
            return
        node = self._root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = _TrieNode()
            node = node.children[ch]
        node.is_end = True
        node.word = word
        self._word_count += 1

    @property
    def word_count(self) -> int:
        return self._word_count

    # ----------------------------------------------------------
    # 检查
    # ----------------------------------------------------------
    def check(self, text: str, mode: str = "replace") -> dict:
        """检查文本中的敏感词。

        Args:
            text: 待检查文本
            mode: 处理模式
                - replace: 将敏感词替换为 ***
                - block: 仅检测,返回 hasSensitive=True 但不替换
                - tag: 标记敏感词位置,返回 words 列表(不替换)

        Returns:
            {
                "hasSensitive": bool,
                "words": [(word, start_index), ...],
                "replacedText": str,
            }
        """
        if not text:
            return {"hasSensitive": False, "words": [], "replacedText": text or ""}

        matches = self._search_trie(text)
        has_sensitive = len(matches) > 0

        if mode == "block":
            return {
                "hasSensitive": has_sensitive,
                "words": matches,
                "replacedText": text,
            }

        if mode == "tag":
            return {
                "hasSensitive": has_sensitive,
                "words": matches,
                "replacedText": text,
            }

        # replace 模式:按倒序替换,避免索引偏移
        replaced = text
        for word, start in sorted(matches, key=lambda x: x[1], reverse=True):
            end = start + len(word)
            replaced = replaced[:start] + "*" * len(word) + replaced[end:]

        return {
            "hasSensitive": has_sensitive,
            "words": matches,
            "replacedText": replaced,
        }

    # ----------------------------------------------------------
    # Trie 搜索
    # ----------------------------------------------------------
    def _search_trie(self, text: str) -> List[tuple]:
        """在 Trie 中搜索所有敏感词出现位置。

        返回 [(word, start_index), ...],同一位置若多个词命中取最长。
        """
        result = []
        n = len(text)
        i = 0
        while i < n:
            node = self._root
            j = i
            last_match_word = ""
            last_match_end = -1
            # 从 i 开始尽可能长地匹配
            while j < n and text[j] in node.children:
                node = node.children[text[j]]
                j += 1
                if node.is_end:
                    last_match_word = node.word
                    last_match_end = j
            if last_match_end != -1:
                # 命中:记录最长匹配,跳过已匹配部分
                result.append((last_match_word, i))
                i = last_match_end
            else:
                i += 1
        return result


# ============================================================
# 单例 + TTL 缓存工厂
# ============================================================
async def get_sensitive_filter(db=None) -> SensitiveFilter:
    """获取敏感词过滤器单例(带 TTL 缓存)。

    首次调用或缓存过期时从数据库重新加载敏感词。
    Args:
        db: 可选的 AsyncSession;若不传则内部新建会话。
    """
    now = time.time()
    if (
        SensitiveFilter._instance is not None
        and SensitiveFilter._cache_ts > 0
        and (now - SensitiveFilter._cache_ts) < SensitiveFilter._cache_ttl
    ):
        return SensitiveFilter._instance

    # 从数据库加载
    words = await _load_words_from_db(db)

    if SensitiveFilter._instance is None:
        SensitiveFilter._instance = SensitiveFilter()
    SensitiveFilter._instance.load_words(words)
    SensitiveFilter._cache_ts = now
    logger.info(f"Sensitive filter loaded {len(words)} words from database")
    return SensitiveFilter._instance


async def _load_words_from_db(db=None) -> List[str]:
    """从 sys_sensitive_word 表加载启用中的敏感词"""
    from sqlalchemy import select

    # 复用 sensitive_word API 中定义的模型
    from app.api.v1.sensitive_word import SensitiveWord

    owns_session = False
    session = db
    if session is None:
        from app.database import async_session_factory
        session = async_session_factory()
        owns_session = True

    try:
        query = select(SensitiveWord.word).where(SensitiveWord.status == "0")
        result = await session.execute(query)
        return [row[0] for row in result.all() if row[0]]
    except Exception as e:
        logger.warning(f"Failed to load sensitive words from db: {e}")
        return []
    finally:
        if owns_session:
            await session.close()


def invalidate_cache() -> None:
    """清除缓存,强制下次重新加载(增删改敏感词后调用)"""
    SensitiveFilter._cache_ts = 0.0
