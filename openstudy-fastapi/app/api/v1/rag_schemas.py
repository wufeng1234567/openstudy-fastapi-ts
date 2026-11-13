"""RAG 接口的请求体模型（Pydantic v2）。

从 ``rag.py`` 抽出的纯数据声明，不含任何业务流程。``rag.py`` 会把这些名字
重新导入到自己的模块命名空间：FastAPI 在路由注册时用函数 ``__globals__``
解析（``from __future__ import annotations`` 下的）字符串注解，因此回导入是
必须的；同时 ``tests/_probe_material_features.py`` 等从 ``app.api.v1.rag``
导入 ``AssetUsageRequest`` 的既有写法也保持不变。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================ 知识库

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class KnowledgeBaseUpdate(BaseModel):
    # ⚠️⚠️ `extra='forbid'` 是**必选项**，不是洁癖。
    #    pydantic v2 默认 `extra='ignore'`（实测 `pydantic==2.10.4`）：
    #    前端把字段名写成 `blocked` / `isDisabled` / `enabled`（或后端改了名没同步）
    #    → 未知字段被**静默丢弃** → PUT 照回 200、前端 `loadKbs()` 也照成功，
    #    而库里一个字节没变。表现就是「开关翻过去了、模型照样读到这个库」——
    #    这条链路上任何静态检查都查不出来（前端静态检查不查类型）。
    #    改成 forbid 之后，字段名对不上会立刻变 **422**，当场暴露。
    #    既有前端只发 name / description（都是声明过的字段），不受影响。
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    #: 屏蔽开关：0 = 启用，1 = 已屏蔽（其余非零值在服务层归一成 1）。
    #: 字段名端到端冻结为 `disabled`（DB 列 / ORM 属性 / 请求体键 / `_kb_brief` /
    #: GET 详情 / 前端类型，六处同名），配合上面的 extra='forbid' 才拦得住写错。
    #: 走既有的 PUT 而不是新开 `/knowledgeBase/{id}/block`：`catch_all` 是按
    #: **路径关键字**分发的，没有关键字的路由会兜底成 `success(None)` ——
    #: 即「路径写错 = 看起来成功的 200 + data:null」，这种坑不值得为对称性踩一次。
    disabled: Optional[int] = None


# ============================================================ 文档

class TextImport(BaseModel):
    kbId: int
    content: str
    fileName: Optional[str] = "未命名文档.txt"


# ============================================================ 在线网页

class WebSearchRequest(BaseModel):
    """知识库「在线网页」手动入口：先搜索，再让用户选择导入。"""

    query: str = Field(..., min_length=1, max_length=500)
    count: int = Field(6, ge=1, le=10)


class WebImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kbId: int = Field(..., gt=0)
    url: str = Field(..., min_length=8, max_length=2000)
    note: Optional[str] = Field(None, max_length=200)


class DocumentContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(..., min_length=1)


class DocumentExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = Field(default="markdown", pattern="^(markdown|docx)$")
    content: Optional[str] = None


# ============================================================ 资料装配 / 图谱 / 百科 / 学习处方

class StudyPackStreamRequest(BaseModel):
    """资料装配：把选中章节交给 LLM 重组为学习资产。"""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="review", pattern="^(review|lecture|outline)$")
    sectionIndexes: List[int] = Field(default_factory=list)
    instruction: str = Field(default="", max_length=800)


class KnowledgeGraphBuildRequest(BaseModel):
    """知识图谱抽取：对一个资料夹内的文档做实体/关系抽取。"""

    model_config = ConfigDict(extra="forbid")

    kbId: int = Field(..., gt=0)
    docIds: Optional[List[int]] = None
    force: bool = False


class WikiBuildRequest(BaseModel):
    """知识百科生成：把实体图整理成可读主题页。"""

    model_config = ConfigDict(extra="forbid")

    kbId: int = Field(..., gt=0)
    force: bool = False
    limit: int = Field(default=30, ge=1, le=30)


class WikiPageCreateRequest(BaseModel):
    """手动创建知识百科主题页（不调用模型）。"""

    model_config = ConfigDict(extra="forbid")

    kbId: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field("", max_length=500)
    sections: List[dict] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list, max_length=8)


class WikiPageUpdateRequest(BaseModel):
    """手动编辑主题页；只改传入字段，未传字段保留原值。"""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, max_length=255)
    summary: Optional[str] = Field(None, max_length=500)
    sections: Optional[List[dict]] = None
    aliases: Optional[List[str]] = Field(None, max_length=8)
    changeType: str = Field(default="manual", pattern="^(manual|agent)$")
    baseVersion: Optional[int] = Field(None, ge=1)


class WikiPageLinkCreateRequest(BaseModel):
    """手动添加页面内链：锚文本必须在正文中真实存在。"""

    model_config = ConfigDict(extra="forbid")

    targetPageId: int = Field(..., gt=0)
    anchorText: str = Field(..., min_length=1, max_length=120)
    sectionIndex: Optional[int] = Field(None, ge=-1, description="-1=摘要，0=第一个小节")


class WikiImageAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assetKey: str = Field(..., min_length=1, max_length=120)
    quote: str = Field("", max_length=800)


class StudyPrescriptionRequest(BaseModel):
    """学习处方：按资料体检和章节生成按天执行的学习计划。"""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, ge=3, le=30)
    dailyMinutes: int = Field(default=30, ge=10, le=180)
    goal: str = Field(default="exam", pattern="^(foundation|exam|weakness)$")
    sectionIndexes: List[int] = Field(default_factory=list)
    instruction: str = Field(default="", max_length=800)


class StudyPrescriptionExportRequest(BaseModel):
    """学习处方导出：plan 是当前前端正在展示的结构化处方。"""

    model_config = ConfigDict(extra="forbid")

    format: str = Field(..., pattern="^(pdf|word|docx|md|markdown|txt|text)$")
    plan: dict
    meta: dict = Field(default_factory=dict)


# ============================================================ 微课

class MicroCourseSlidePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: Optional[str] = None
    eyebrow: Optional[str] = None
    title: Optional[str] = None
    bullets: Optional[List[str]] = None
    note: Optional[str] = None
    image: Optional[dict] = None
    chart: Optional[dict] = None
    table: Optional[dict] = None
    quote: Optional[str] = None


class MicroCourseReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fromIndex: int = Field(..., ge=0)
    toIndex: int = Field(..., ge=0)


class MicroCourseSlideRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field("", max_length=1000)


class MicroCourseSlideInsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(0, ge=0)
    slide: dict


class MicroCoursePptxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: Optional[str] = None
    recordId: Optional[int] = None


class MicroCourseImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str = Field(..., min_length=1, max_length=2_000_000)
    title: Optional[str] = Field(None, max_length=200)


class DocumentStatusBatchRequest(BaseModel):
    docIds: list[int] = Field(default_factory=list, max_length=50)


class DocumentSearchableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


# ============================================================ 检索与问答

class SearchRequest(BaseModel):
    query: str
    kbIds: Optional[List[int]] = None
    topK: int = Field(5, ge=1, le=20)


class AskRequest(BaseModel):
    query: str
    kbIds: Optional[List[int]] = None
    topK: int = Field(5, ge=1, le=20)
    sessionId: Optional[str] = None


class RagConfigUpdate(BaseModel):
    """可更新项全部可选 —— 前端只传改过的字段。"""

    backend: Optional[str] = Field(None, description="local | siliconflow | auto")
    model: Optional[str] = None
    chunkSize: Optional[int] = Field(None, ge=100, le=4000)
    chunkOverlap: Optional[int] = Field(None, ge=0, le=1000)
    topK: Optional[int] = Field(None, ge=1, le=50)
    rrfK: Optional[int] = Field(None, ge=1, le=200)
    cloudModel: Optional[str] = None
    autoFallback: Optional[bool] = None
    #: 硅基流动 API Key。传空串或不传 = 不改；传 "__CLEAR__" = 清空
    cloudApiKey: Optional[str] = None


# ============================================================ 资产 / 画廊 / 智能整理

class AssetUsageRequest(BaseModel):
    """记录一张图片资产被哪个题目/笔记使用。"""

    model_config = ConfigDict(extra="forbid")

    assetKey: str = Field(..., min_length=1, max_length=120)
    assetUrl: Optional[str] = Field(None, max_length=500)
    targetType: str = Field(..., pattern="^(question|note|document)$")
    targetId: int


class GalleryDescribeRequest(BaseModel):
    """批量补图片描述：传 docId 或 assetKeys，二选一。

    不提供“全库自动跑”的隐藏行为——用户点哪次就描述哪批，成本可控。
    """

    model_config = ConfigDict(extra="forbid")

    docId: Optional[int] = Field(None, gt=0)
    assetKeys: Optional[List[str]] = None
    limit: int = Field(20, ge=1, le=40)


class ContentReferenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceType: str = Field(..., pattern="^(document|document_image|chat_image|note|question)$")
    sourceId: int = Field(..., gt=0)
    sourceSubId: Optional[str] = Field(None, max_length=64)
    targetType: str = Field(..., pattern="^(document|note|question|image|wiki_page)$")
    targetId: int = Field(..., gt=0)
    quote: str = Field("", max_length=4000)
    startOffset: Optional[int] = None
    endOffset: Optional[int] = None


class OrganizeRequest(BaseModel):
    """智能整理：传 docIds（单个/多个）或 kbId（整资料夹）。"""

    model_config = ConfigDict(extra="forbid")

    docIds: Optional[List[int]] = None
    kbId: Optional[int] = None


class OrganizePreviewRequest(BaseModel):
    """单文档智能整理预览（仅深度/智能整理）。"""

    model_config = ConfigDict(extra="forbid")

    docId: int = Field(..., gt=0)
    mode: str = Field(default="deep", pattern="^deep$")
    options: dict = Field(default_factory=dict)


class OrganizeApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planId: int = Field(..., gt=0)
    changeIds: Optional[List[str]] = None
    exclusionIds: Optional[List[str]] = None


class OrganizeRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batchId: str = Field(..., min_length=1, max_length=64)
