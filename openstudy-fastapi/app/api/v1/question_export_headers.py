"""题库模块各 Excel 导出接口的表头常量。

从 ``questions.py`` 抽出的纯数据（``{"key", "label"}`` 列表），不含任何逻辑。
``questions.py`` 把 6 个常量导入后仍赋给局部变量 ``headers`` 再传给
``export_to_excel``，因此导出列顺序、文案与响应行为完全不变。
"""

BANK_HEADERS = [
    {"key": "id", "label": "题库ID"},
    {"key": "bankName", "label": "题库名称"},
    {"key": "subject", "label": "科目"},
    {"key": "description", "label": "描述"},
    {"key": "totalQuestions", "label": "题目总数"},
    {"key": "isPublic", "label": "是否公开"},
    {"key": "createTime", "label": "创建时间"},
]

QUESTION_HEADERS = [
    {"key": "id", "label": "题目ID"},
    {"key": "bankId", "label": "题库ID"},
    {"key": "questionType", "label": "题型"},
    {"key": "questionText", "label": "题干"},
    {"key": "options", "label": "选项"},
    {"key": "answer", "label": "答案"},
    {"key": "analysis", "label": "解析"},
    {"key": "difficulty", "label": "难度"},
    {"key": "sortOrder", "label": "排序"},
]

FAVORITE_BANK_HEADERS = [
    {"key": "favoriteId", "label": "收藏ID"},
    {"key": "userId", "label": "用户ID"},
    {"key": "bankId", "label": "题库ID"},
    {"key": "bankName", "label": "题库名称"},
    {"key": "subject", "label": "科目"},
    {"key": "notes", "label": "收藏备注"},
    {"key": "tags", "label": "标签"},
    {"key": "sortOrder", "label": "排序"},
    {"key": "isStarred", "label": "是否标星"},
    {"key": "lastStudyTime", "label": "最后学习时间"},
    {"key": "studyCount", "label": "学习次数"},
    {"key": "favoriteStatus", "label": "收藏状态"},
    {"key": "createTime", "label": "收藏时间"},
]

FAVORITE_QUESTION_HEADERS = [
    {"key": "favoriteId", "label": "收藏ID"},
    {"key": "userId", "label": "用户ID"},
    {"key": "questionId", "label": "题目ID"},
    {"key": "bankId", "label": "题库ID"},
    {"key": "bankName", "label": "题库名称"},
    {"key": "questionType", "label": "题型"},
    {"key": "questionText", "label": "题干"},
    {"key": "answer", "label": "答案"},
    {"key": "notes", "label": "收藏备注"},
    {"key": "tags", "label": "标签"},
    {"key": "difficultyRating", "label": "难度评级"},
    {"key": "errorTimes", "label": "错误次数"},
    {"key": "correctTimes", "label": "正确次数"},
    {"key": "reviewCount", "label": "复习次数"},
    {"key": "lastReviewTime", "label": "最后复习时间"},
    {"key": "nextReviewTime", "label": "下次复习时间"},
    {"key": "isStarred", "label": "是否星标"},
    {"key": "favoriteStatus", "label": "收藏状态"},
    {"key": "createTime", "label": "收藏时间"},
]

ERROR_HEADERS = [
    {"key": "errorId", "label": "错题ID"},
    {"key": "questionId", "label": "题目ID"},
    {"key": "questionText", "label": "题干"},
    {"key": "questionType", "label": "题型"},
    {"key": "answer", "label": "正确答案"},
    {"key": "errorCount", "label": "错误次数"},
    {"key": "isMastered", "label": "是否已掌握"},
    {"key": "lastErrorTime", "label": "最近错误时间"},
    {"key": "notes", "label": "备注"},
]

MARKED_HEADERS = [
    {"key": "markedId", "label": "斩题ID"},
    {"key": "userId", "label": "用户ID"},
    {"key": "questionId", "label": "题目ID"},
    {"key": "questionText", "label": "题干"},
    {"key": "questionType", "label": "题型"},
    {"key": "answer", "label": "答案"},
    {"key": "markedType", "label": "斩题类型"},
    {"key": "difficultyLevel", "label": "难度等级"},
    {"key": "errorTimesBeforeMark", "label": "错误次数"},
    {"key": "reviewCount", "label": "复习次数"},
    {"key": "isMastered", "label": "是否已掌握"},
    {"key": "lastReviewTime", "label": "最后复习时间"},
    {"key": "notes", "label": "备注"},
    {"key": "tags", "label": "标签"},
    {"key": "createTime", "label": "斩题时间"},
]
