"""聊天上传文件的持久化（2026-10-27）

============================================================================
它解决什么
============================================================================

用户反馈原话：

    「图片 文件类的东西 ai他无法进行持久化操作
      比如我上传了一个word给他排版 他无法获得到里面的图片
      并且无法让图片可以插入到我们的题库、笔记、word之类的里面
      文件类数据持久化也没有做到
      比如用户第一次询问 然后第二次让他插入图片 他也没办法获取到
      用户之前上传过的图片
      需要一个合理的方案解决这个问题
      比如需要给ai提供一个接口让他可以获取到
      当前聊天记录上传过的文件 包括图片 、 文档等等
      不仅仅是可以阅读 是要可以进行操作
      就是指挥调用这些系统内已经储存好了的用户文件」

============================================================================
为什么必须新建一张表
============================================================================

在此之前，聊天附件是**纯内存态**的：

    `AssistantAttachment` 的 docstring 明确写着「不落存储」；
    `_collect_attachments()` 把附件解析成文本塞进当轮 prompt，
    请求结束就全部丢弃。

后果有两个，都是用户实测踩到的：

    ① **同一轮里拿不到图**
       Word 里的插图确实被 `file_parser` 提取出来了（base64 data URL），
       但 `compose_from_file()` 只用了 blocks、**完全没用 images**，
       所以排版出来的新文档里图片全丢。
       （用户看到的回复说"没有获得到 word 里面的图片"，就是这个。）

    ② **下一轮完全拿不到**
       用户第一轮传文件、第二轮说「把刚才那张图插到第 4 题」——
       附件字节已经不在了，AI 无从下手，只能说"你把图再发一次"。

`rag_document` 解决不了：那是知识库文档，属于「检索语料」，
与「这次对话里用户给我的素材」是两种语义（前者可被语义检索打散成 chunk，
后者要求原样保真、按文件取用）。

============================================================================
设计要点
============================================================================

① **按 session 归组，而不是按消息**
   用户说"我之前上传的"通常是跨轮次的。挂在 session 上才能"这个对话里传过的都算"。
   没带 sessionId 的临时对话也要能存（session_id 允许空串）。

② **图片单独拆出来存**
   一个 docx 里可能有 5 张图，用户只想取第 3 张插到某题里。
   所以除文件本身外，还要把内嵌图片逐张落盘、逐张入库 ——
   每张图有自己的 id，AI 才能"把第 2 张图插入"。

③ **正文与图片都留可访问 URL**
   题库/笔记/文档编排的图片字段要的都是 URL 或 data URL。
   存 data URL 到数据库会把库撑爆（一张截图 500KB），
   所以落盘 + 存 `/profile/...` 相对路径。

④ **保留解析后的纯文本 / blocks**
   "第二次让他插入图片"这类请求不需要重解析；但"把这份文档重新排版"要。
   把 `parse_file` 的结果缓存进 `parsed_json`，避免重复解析（老 .doc 还会调 Word COM）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatUploadFile(Base):
    """聊天窗口上传的一个文件（持久化）

    生命周期：用户发一条带附件的消息 → 落盘 + 入库 → 之后任何一轮都能按 id 取用。
    """

    __tablename__ = "chat_upload_file"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: 归属用户（越权防护的根：所有查询都必须带 user_id）
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    #: 会话 id；空串表示"未归属到具体会话"（临时对话）
    #:
    #: ⚠️ 不用 nullable=True：`WHERE session_id = ''` 比 `IS NULL` 的写法更统一，
    #:    也避免"同一个字段两种空值语义"（NULL vs ''）。
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)

    #: 原始文件名（展示用；用户就是靠这个名字认文件的）
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: 扩展名（小写，不带点），如 `docx` / `png`
    file_ext: Mapped[str] = mapped_column(String(20), nullable=False, default="")

    #: MIME，如 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    #: 字节数（前端展示 + 判断是否需要分页）
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: 相对 UPLOAD_DIR 的路径，如 `chat/2026/10/27/ab12cd34_题库测试.docx`
    rel_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    #: 可直接被前端 / 文档引擎访问的 URL，如 `/profile/chat/2026/10/27/...`
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    #: 解析后的纯文本（"读一下这份文件"直接给模型用，不必重解析）
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: `file_parser.parse_file()` 的完整结果（JSON 字符串）
    #:
    #: 存它而不是每次重解析：老 .doc 会走 Word COM，一次几秒；
    #: 而"重新排版这份文档"这类请求在对话里可能反复出现。
    #:
    #: ⚠️ 存字符串不存 JSONB：里面的结构（blocks/images）是给 Python 用的，
    #:    不需要数据库层面按字段查询，存 TEXT 更省事也更快。
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False, default="")

    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    #: 用户手动删除时打标记（软删），避免"取用时发现文件没了"
    deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ChatUploadImage(Base):
    """文件内嵌的图片（逐张落盘，可被单独引用）

    存在的理由：一个 docx 里 5 张图，用户要的是"把第 2 张插到第 4 题"。
    如果只存整个 docx，AI 没法表达"第 2 张"。
    """

    __tablename__ = "chat_upload_image"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    #: 来源文件 id（0 表示用户直接贴的图片，不来自某个文件）
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, index=True)

    #: 在这份文件里的顺序（从 0 开始）—— AI 按"第 N 张"引用时靠它定位
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: 原始图片名，如 `image1.png`
    image_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    mime_type: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    rel_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    #: `/profile/chat-images/...` —— 可直接塞进题库/笔记的图片字段
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
