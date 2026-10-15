"""
题库/题目相关 Schema（对齐前端 camelCase 字段名）
"""

from pydantic import BaseModel, Field, AliasChoices, BeforeValidator
from typing import Optional, List, Union, Annotated
from datetime import datetime
import json


def _coerce_status(value):
    """兼容前端传数字状态（0 / 1）→ 统一转成字符串"""
    return None if value is None else str(value)


def _coerce_options(value):
    """
    选项兼容处理：
    - 数组：原样返回（JSON 列的标准形态）
    - JSON 字符串（如 '["A","B"]'）：解析成数组
    - 其它字符串：原样返回，交给 Pydantic 报错
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return value
    return value


# 状态字段：兼容 int / str（前端有些地方传的是数字 0）
StatusStr = Annotated[Optional[str], BeforeValidator(_coerce_status)]

# 选项字段：兼容 数组 / JSON 字符串
OptionsList = Annotated[Optional[List[Union[dict, str]]], BeforeValidator(_coerce_options)]


class QuestionBankCreate(BaseModel):
    """创建题库（前端发送 camelCase）"""
    bankName: str = Field(..., min_length=1, max_length=100)
    subject: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    coverImage: Optional[str] = Field(None, max_length=255)
    isPublic: Optional[int] = Field(0, description="是否公开：0公有 1私有")
    allowFork: Optional[int] = Field(1, description="是否允许他人复制：0否 1是")
    status: StatusStr = Field("0", description="状态：0正常 1停用")
    userId: Optional[int] = None
    bankId: Optional[int] = None


class QuestionBankUpdate(BaseModel):
    """
    更新题库（前端发送 camelCase）

    兼容说明：
    - 题库ID 同时接受 `bankId` 与 `id` 两种字段名（前端历史实现用的是 `id`）
    - status 同时接受 int / str
    """
    bankId: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("bankId", "id"),
        description="题库ID（兼容前端的 id 字段）",
    )
    bankName: Optional[str] = Field(None, max_length=100)
    subject: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    coverImage: Optional[str] = Field(None, max_length=255)
    isPublic: Optional[int] = None
    allowFork: Optional[int] = None
    status: StatusStr = None


class QuestionBankQuery(BaseModel):
    """题库查询"""
    bank_name: Optional[str] = None
    status: Optional[str] = None
    subject: Optional[str] = None


class QuestionSubCreate(BaseModel):
    """子题创建（前端发送 camelCase）"""
    questionText: Optional[str] = None
    questionType: Optional[int] = Field(1, ge=1, le=7, description="1单选 2多选 3判断 4填空 5简答 6组合题")
    options: OptionsList = None
    answer: Optional[str] = Field(None, max_length=500)
    analysis: Optional[str] = None
    sortOrder: Optional[int] = 0
    score: Optional[float] = Field(0, ge=0, le=100)


class QuestionCreate(BaseModel):
    """创建题目（前端发送 camelCase）"""
    bankId: int
    questionType: int = Field(1, ge=1, le=7, description="1单选 2多选 3判断 4填空 5简答 6组合题")
    questionText: str = Field(..., min_length=1)
    content: Optional[str] = None
    options: OptionsList = None
    answer: Optional[str] = None
    # 兼容前端 analysis / questionAnalysis 两种字段名
    questionAnalysis: Optional[str] = Field(
        None, validation_alias=AliasChoices("questionAnalysis", "analysis")
    )
    difficulty: Optional[int] = Field(1, ge=1, le=4)
    sortOrder: Optional[int] = 0
    score: Optional[float] = Field(0, ge=0, le=100)
    status: StatusStr = Field("0", description="状态：0正常 1停用")
    questionSubList: Optional[List["QuestionSubCreate"]] = None


class QuestionUpdate(BaseModel):
    """更新题目（前端发送 camelCase）"""
    id: int
    bankId: Optional[int] = None
    questionType: Optional[int] = Field(None, ge=1, le=7)
    questionText: Optional[str] = None
    content: Optional[str] = None
    options: OptionsList = None
    answer: Optional[str] = None
    # 兼容前端 analysis / questionAnalysis 两种字段名
    questionAnalysis: Optional[str] = Field(
        None, validation_alias=AliasChoices("questionAnalysis", "analysis")
    )
    difficulty: Optional[int] = Field(None, ge=1, le=4)
    sortOrder: Optional[int] = None
    score: Optional[float] = Field(None, ge=0, le=100)
    status: StatusStr = None
    questionSubList: Optional[List["QuestionSubCreate"]] = None


class QuestionQuery(BaseModel):
    """题目查询"""
    bank_id: Optional[int] = None
    question_type: Optional[int] = None
    difficulty: Optional[int] = None


class QuestionBatchInfoRequest(BaseModel):
    """批量获取题目信息请求"""
    questionIds: List[int] = Field(..., min_length=1, max_length=100)


class AiGenerateRequest(BaseModel):
    """AI 出题请求"""
    topic: str = Field(..., min_length=1, description="题目主题")
    question_type: str = Field("single", description="题目类型")
    count: int = Field(5, ge=1, le=20, description="生成数量")
    difficulty: int = Field(3, ge=1, le=5, description="难度等级")
    bank_id: Optional[int] = Field(None, description="题库ID（可选，直接保存到题库）")
    model: Optional[str] = Field(None, description="AI模型")
    provider: Optional[str] = Field(None, description="AI提供商")


# ========== 刷题核心功能请求 Schema（对齐前端 JSON body） ==========

class ErrorRecordRequest(BaseModel):
    """记录/更新错题请求"""
    userId: Optional[int] = None
    questionId: int
    bankId: Optional[int] = None
    errorTime: Optional[str] = None
    lastErrorTime: Optional[str] = None
    errorCount: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    difficultyRating: Optional[int] = None
    reviewCount: Optional[int] = None
    isMastered: Optional[int] = None
    status: Optional[int] = None


class FavoriteQuestionRequest(BaseModel):
    """收藏题目请求（前台「收藏」与后台「新增用户题目收藏」共用）

    后台新增对话框提交的字段比前台多，必须与 user_question_favorite 表对齐，
    否则 Pydantic 会静默丢弃未声明字段（表现为"填了不生效"）。
    """
    userId: Optional[int] = None
    questionId: int
    bankId: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    difficultyRating: Optional[int] = None
    errorTimes: Optional[int] = None
    correctTimes: Optional[int] = None
    lastReviewTime: Optional[str] = None
    nextReviewTime: Optional[str] = None
    reviewCount: Optional[int] = None
    isStarred: Optional[int] = None
    favoriteStatus: Optional[int] = None


class FavoriteBankRequest(BaseModel):
    """收藏题库请求（前台「收藏题库」与后台「新增用户题库收藏」共用）

    后台新增对话框提交的字段比前台多，必须与 user_bank_favorite 表对齐，
    否则 Pydantic 会静默丢弃未声明字段（表现为"填了不生效"）。
    """
    userId: Optional[int] = None
    bankId: int
    notes: Optional[str] = None
    tags: Optional[str] = None
    sortOrder: Optional[int] = None
    isStarred: Optional[int] = None
    lastStudyTime: Optional[str] = None
    studyCount: Optional[int] = None
    favoriteStatus: Optional[int] = None


class MarkedRequest(BaseModel):
    """斩题请求（前台「斩题」与后台「新增用户斩题」共用）

    后台新增对话框提交的字段比前台标记多，故这里必须与 user_question_marked 表对齐，
    否则 Pydantic 会静默丢弃未声明字段（表现为"填了不生效"）。
    """
    userId: Optional[int] = None
    questionId: int
    bankId: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    markedType: Optional[int] = None
    difficultyLevel: Optional[int] = None
    errorTimesBeforeMark: Optional[int] = None
    correctTimesBeforeMark: Optional[int] = None
    reviewCount: Optional[int] = None
    lastReviewTime: Optional[str] = None
    nextReviewTime: Optional[str] = None
    isMastered: Optional[int] = None
    masteryDate: Optional[str] = None
    markedStatus: Optional[int] = None


class BatchCheckRequest(BaseModel):
    """批量检查状态请求"""
    questionIds: List[int]


class MarkMasteredRequest(BaseModel):
    """标记错题已掌握请求"""
    questionId: int


class ErrorRecordUpdate(BaseModel):
    """修改错题记录请求"""
    errorId: int
    notes: Optional[str] = None
    tags: Optional[str] = None
    difficultyRating: Optional[int] = None
    reviewCount: Optional[int] = None
    isMastered: Optional[int] = None
    status: Optional[int] = None


class FavoriteQuestionUpdate(BaseModel):
    """修改收藏题目请求（后台「修改用户题目收藏」对话框）

    userId/questionId/bankId 允许改（后台表单里可编辑，仅管理员生效，
    服务端会做唯一约束预检，避免直接抛 IntegrityError）。
    """
    favoriteId: int
    userId: Optional[int] = None
    questionId: Optional[int] = None
    bankId: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    difficultyRating: Optional[int] = None
    errorTimes: Optional[int] = None
    correctTimes: Optional[int] = None
    lastReviewTime: Optional[str] = None
    nextReviewTime: Optional[str] = None
    reviewCount: Optional[int] = None
    isStarred: Optional[int] = None
    favoriteStatus: Optional[int] = None


class FavoriteBankUpdate(BaseModel):
    """修改收藏题库请求（后台「修改用户题库收藏」对话框）

    userId/bankId 允许改（后台表单里这两个框可编辑，仅管理员生效，
    服务端会做唯一约束预检，避免直接抛 IntegrityError）。
    """
    favoriteId: int
    userId: Optional[int] = None
    bankId: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    sortOrder: Optional[int] = None
    isStarred: Optional[int] = None
    lastStudyTime: Optional[str] = None
    studyCount: Optional[int] = None
    favoriteStatus: Optional[int] = None


class MarkedUpdate(BaseModel):
    """修改斩题记录请求（后台「修改用户斩题」对话框）

    userId/questionId/bankId 允许改（后台表单里这几个框是可编辑的，仅管理员生效，
    且服务端会做唯一约束预检，避免直接抛 IntegrityError）。
    """
    markedId: int
    userId: Optional[int] = None
    questionId: Optional[int] = None
    bankId: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    markedType: Optional[int] = None
    difficultyLevel: Optional[int] = None
    errorTimesBeforeMark: Optional[int] = None
    correctTimesBeforeMark: Optional[int] = None
    reviewCount: Optional[int] = None
    lastReviewTime: Optional[str] = None
    nextReviewTime: Optional[str] = None
    isMastered: Optional[int] = None
    masteryDate: Optional[str] = None
    markedStatus: Optional[int] = None


class ErrorRecordCreate(BaseModel):
    """新增错题记录请求（后台管理）"""
    errorId: Optional[int] = None
    userId: Optional[int] = None
    questionId: Optional[int] = None
    bankId: Optional[int] = None
    errorTime: Optional[str] = None
    lastErrorTime: Optional[str] = None
    errorCount: Optional[int] = 0
    notes: Optional[str] = None
    tags: Optional[str] = None
    difficultyRating: Optional[int] = 3
    reviewCount: Optional[int] = 0
    lastReviewTime: Optional[str] = None
    nextReviewTime: Optional[str] = None
    isMastered: Optional[int] = 0
    status: Optional[int] = 1


class RecordStudyTimeRequest(BaseModel):
    """记录刷题学习时间请求"""
    bankId: int
    questionIds: List[int] = Field(default_factory=list)


class PracticeReportRequest(BaseModel):
    """答题上报请求（答对/答错都要上报，用于学习行为统计）"""
    questionId: int
    bankId: Optional[int] = None
    isCorrect: bool
    answer: Optional[str] = None
    difficultyRating: Optional[int] = None
    # 答错时一并写入的错因备注/标签（前端已生成，可缺省）
    notes: Optional[str] = None
    tags: Optional[str] = None
