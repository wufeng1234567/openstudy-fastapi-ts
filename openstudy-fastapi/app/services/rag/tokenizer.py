"""
中文分词（供 PostgreSQL 全文检索使用）

为什么必须有它
--------------
PG 内置的全文检索**不切分中文**：

    to_tsvector('simple', '学习Python编程与数据结构')
    → '学习python编程与数据结构':1      ← 整串变成 1 个 token

这样中文关键词根本检索不到。而且容器里**没有** zhparser / pg_bigm（实测
`pg_available_extensions` 只有 pg_trgm），所以只能应用层先分词，
把结果空格连接存在 `rag_document_chunk.content_tokens`，
再用生成列 `to_tsvector('simple', content_tokens)` 建 GIN 索引。

检索侧必须用**同一个函数**处理查询词，否则两边切法不一致就匹配不上。
"""

from __future__ import annotations

import re
import threading

import jieba
from loguru import logger

#: 单次分词的最大字符数。jieba 对超长文本很慢，而 tsvector 本身也有 1MB 上限。
#: 超出部分截断 —— 分块上限是 800 字，实际远到不了这里，只是兜底。
MAX_TOKENIZE_CHARS = 20_000

#: 会被 `to_tsvector('simple', ...)` 当分隔符丢掉的字符，这里先清掉避免产生空 token
_NOISE_RE = re.compile(r"[\s\u3000]+")

#: 中文虚词停用表。
#:
#: ⚠️ 不过滤它们会出两个问题：
#:   1. **索引里塞满「的/是/在/和」这类高频 lexeme**，任何查询都能匹配上，
#:      关键词那一路的「是否命中」就失去了判别力（实测：问「量子纠缠和薛定谔猫」
#:      也能靠虚词匹配到讲二叉树的段落）
#:   2. 检索精度下降 —— 虚词匹配到的片段会挤进 RRF 候选，把真正相关的挤下去
#:
#: 只过滤中文虚词，**不过滤单个英文字母**：`O(n)` 与 `O(log n)` 的区别是有意义的。
STOPWORDS: frozenset[str] = frozenset(
    """
    的 了 是 在 和 与 及 或 而 但 也 都 就 还 又 很 太 更 最 不 没 无 有
    我 你 他 她 它 们 咱 您 谁 啥
    这 那 这些 那些 这个 那个 这样 那样 这么 那么 这里 那里 哪 哪个 哪些 哪里
    什么 怎么 怎样 如何 为什么 为何 多少 几 是否 能否
    一个 一些 一下 一点 一直 一样 一起 一定
    可以 能够 应该 需要 要 会 能 想 让 使 把 被 给 跟 对 对于 关于 至于
    从 到 向 往 于 为 为了 因为 所以 但是 如果 虽然 然后 并且 而且 或者 不过
    已经 正在 将要 曾经 总是 经常 有时 可能 大概 也许 其实 当然 只是 就是
    之 其 此 该 等 等等 里 中 上 下 前 后 内 外 时 时候
    请 请问 帮 帮忙 告诉 说 问 找 查 看
    """.split()
)

_init_lock = threading.Lock()
_initialized = False


def _ensure_ready() -> None:
    """jieba 首次使用要建词典缓存，预热一次避免首个请求卡顿。"""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        jieba.initialize()
        _initialized = True
        logger.info("[rag.tokenizer] jieba 词典预热完成")


def tokenize(text: str) -> str:
    """把文本切成空格连接的词序列（已过滤停用词）。

    - 中文按 jieba 分词，虚词丢弃
    - 英文/数字/代码标识符保持原样（jieba 会整体保留 `bge`、`log` 这类串）
    - 空 token 丢弃

    返回的串直接写进 `content_tokens` 列，由 PG 生成 `search_vec`。
    """
    if not text:
        return ""

    _ensure_ready()

    if len(text) > MAX_TOKENIZE_CHARS:
        text = text[:MAX_TOKENIZE_CHARS]

    # 换行/制表符等统一成空白，避免 jieba 把跨行内容粘成一个词
    normalized = _NOISE_RE.sub(" ", text)

    tokens = [t.strip() for t in jieba.cut_for_search(normalized)]
    return " ".join(t for t in tokens if t and t not in STOPWORDS)


def query_tokens(query: str) -> list[str]:
    """查询侧分词，返回 token 列表（供 `to_tsquery` 用）。

    ⚠️ 必须与 `tokenize()` 用同一套切法，否则索引里是 A、查询是 B，永远匹配不上。
    """
    return tokenize(query).split()
