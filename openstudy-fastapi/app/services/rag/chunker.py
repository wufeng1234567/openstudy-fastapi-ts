"""
文档分块

参数对齐 SpringBoot 实现（`RagDocumentChunker`）：CHUNK_SIZE=800 / OVERLAP=100。
但修掉了它一个实际存在的缺陷：

    legacy 只在「单个段落超过 800 字」时才走带重叠的硬切；
    由多个段落合并出来的**普通块之间没有任何重叠**。
    这与文档宣称的「相邻分块 100 字重叠」不符，且会切掉跨段的语义
    （比如「定义在上一段末尾、解释在下一段开头」这种）。

这里改成：**每次 flush 都把上一块的尾部 OVERLAP 字符留到下一块开头**，
标题边界除外 —— 标题意味着新章节，跨章节留尾巴只会引入噪声。
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

#: 单块最大字符数
CHUNK_SIZE = 800
#: 相邻块重叠字符数
OVERLAP_SIZE = 100
#: 单文档最大块数（上限之外的内容丢弃，避免一次传太多 embedding）
MAX_CHUNKS = 100
#: 单文档最大字符数（对齐 SpringBoot）
MAX_CONTENT_LENGTH = 50_000

#: 段落分隔符
PARA_SEP = "\n\n"


@dataclass
class Chunk:
    index: int
    content: str

    @property
    def length(self) -> int:
        return len(self.content)


def _is_heading(paragraph: str) -> bool:
    """Markdown 标题行（`#` 开头）。作为章节边界。"""
    return paragraph.lstrip().startswith("#")


def _tail_for_overlap(text: str) -> str:
    """取上一块的尾部作为下一块的重叠前缀。

    优先从段落边界截断 —— 从句子中间切出来的尾巴读起来是断片，检索时也是噪声。
    """
    if len(text) <= OVERLAP_SIZE:
        return text
    tail = text[-OVERLAP_SIZE:]
    # 尽量在一个段落开头处断开
    for sep in (PARA_SEP, "\n", "。", "；", "！", "？", ". ", "; "):
        pos = tail.find(sep)
        if 0 <= pos < len(tail) // 2:
            return tail[pos + len(sep) :]
    return tail


def _split_long_paragraph(text: str) -> list[str]:
    """单个超长段落硬切（带重叠）。"""
    parts: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + CHUNK_SIZE, length)
        parts.append(text[start:end])
        if end >= length:
            break
        next_start = end - OVERLAP_SIZE
        if next_start <= start:  # 防御：OVERLAP 配错时会死循环
            next_start = end
        start = next_start
    return parts


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = OVERLAP_SIZE,
    max_chunks: int = MAX_CHUNKS,
) -> list[Chunk]:
    """把整篇文本切成块。

    规则：
      1. 先按空行切段，空段丢弃
      2. 段落贪心合并，直到再加一段会超过 chunk_size
      3. **Markdown 标题**强制起新块（不跨章节重叠）
      4. 超长段落硬切，段内带 overlap
      5. 普通块之间也带 overlap（legacy 缺这一步）
    """
    if not text:
        return []

    if len(text) > MAX_CONTENT_LENGTH:
        logger.info(
            f"[rag.chunker] 内容超长，截断到 {MAX_CONTENT_LENGTH} 字符"
            f"（原 {len(text)}）"
        )
        text = text[:MAX_CONTENT_LENGTH]

    paragraphs = [p.strip() for p in text.split(PARA_SEP)]
    paragraphs = [p for p in paragraphs if p]

    if not paragraphs:
        stripped = text.strip()
        return [Chunk(0, stripped)] if stripped else []

    raw: list[str] = []
    buffer = ""
    carry = ""  # 上一块的尾部，作为下一块的重叠前缀

    def join(prefix: str, para: str) -> str:
        return f"{prefix}{PARA_SEP}{para}" if prefix else para

    def flush(next_is_heading: bool) -> None:
        nonlocal buffer, carry
        if not buffer:
            return
        raw.append(buffer)
        # 标题边界不留尾巴：跨章节的重叠只会引入无关内容
        carry = "" if next_is_heading else _tail_for_overlap(buffer)
        buffer = ""

    for para in paragraphs:
        heading = _is_heading(para)

        # 标题 → 先收掉当前块，且不带尾巴
        if heading and buffer:
            flush(next_is_heading=True)

        if len(para) > chunk_size:
            # 超长段落：先收掉当前块，再单独硬切
            if buffer:
                flush(next_is_heading=False)
            pieces = _split_long_paragraph(para)
            raw.extend(pieces[:-1])
            buffer = pieces[-1]
            carry = ""
            continue

        if buffer and len(join(buffer, para)) > chunk_size:
            flush(next_is_heading=False)
            # ⚠️ 这里**不能 continue** —— 那会把当前段落整个丢掉，
            #    被丢的内容永远检索不到（实测过：A/B/C 三段会丢掉 B）。
            #    用 flush 之后的新状态（buffer 空、carry 是上一块尾巴）重算。

        buffer = join(carry if not buffer else buffer, para)

    if buffer:
        raw.append(buffer)

    chunks = [Chunk(i, c.strip()) for i, c in enumerate(raw) if c.strip()]
    if len(chunks) > max_chunks:
        logger.info(
            f"[rag.chunker] 分块数 {len(chunks)} 超过上限 {max_chunks}，截断"
            f"（超出的内容不会被向量化，也就检索不到）"
        )
        chunks = chunks[:max_chunks]

    return [Chunk(i, c.content) for i, c in enumerate(chunks)]
