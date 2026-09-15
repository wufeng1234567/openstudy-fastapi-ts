"""
AI 出题服务
"""

import json
import re
from typing import List, Optional

from loguru import logger

from app.services.ai import dynamic_ai
from app.services.ai.base_client import ChatMessage


class AiGenerateService:
    """AI 出题服务"""

    async def generate_questions(
        self,
        topic: str,
        question_type: str = "single",
        count: int = 5,
        difficulty: int = 3,
        model: str = None,
        provider: str = None,
        db=None,
        thinking: Optional[bool] = None,
    ) -> List[dict]:
        """生成题目（传入 db 时优先使用 sys_ai_config 表配置）

        thinking: True/False 覆盖 DB 的 thinking_mode，None 表示跟随配置。
        """
        prompt = self._build_prompt(topic, question_type, count, difficulty)

        messages = [
            ChatMessage(role="system", content="你是一个专业的出题助手，擅长生成各种类型的题目。"),
            ChatMessage(role="user", content=prompt),
        ]

        if db is not None:
            from app.services.ai import db_config
            response = await db_config.chat_with_config(
                db, messages, provider=provider, temperature=0.8, thinking=thinking
            )
        else:
            response = await dynamic_ai.chat(
                messages=messages,
                model=model or "deepseek-chat",
                provider=provider,
                temperature=0.8,
            )

        # 解析返回的 JSON
        try:
            questions = json.loads(response.content)
            if not isinstance(questions, list):
                questions = [questions]
        except json.JSONDecodeError:
            questions = self._extract_json_from_text(response.content) or []

        # 敏感词过滤(replace 模式,不阻塞流程)
        questions = await self._filter_sensitive(questions)
        return questions

    async def _filter_sensitive(self, questions: List[dict]) -> List[dict]:
        """对题目字段做敏感词过滤(replace 模式)。

        覆盖 question_text/questionText/question_content、analysis、options[*].content。
        敏感词服务不可用时不影响出题流程。
        """
        try:
            from app.services.sensitive_filter import get_sensitive_filter
            sf = await get_sensitive_filter()
        except Exception as e:
            logger.warning(f"Sensitive filter unavailable, skip filtering: {e}")
            return questions

        text_fields = ("question_text", "questionText", "question_content", "analysis")
        for q in questions:
            if not isinstance(q, dict):
                continue
            for field in text_fields:
                val = q.get(field)
                if isinstance(val, str) and val:
                    res = sf.check(val, mode="replace")
                    if res["hasSensitive"]:
                        logger.info(f"Sensitive words filtered in {field}: {res['words']}")
                        q[field] = res["replacedText"]
            options = q.get("options")
            if isinstance(options, list):
                for opt in options:
                    if isinstance(opt, dict):
                        c = opt.get("content")
                        if isinstance(c, str) and c:
                            r = sf.check(c, mode="replace")
                            if r["hasSensitive"]:
                                opt["content"] = r["replacedText"]
        return questions

    def _build_prompt(
        self,
        topic: str,
        question_type: str,
        count: int,
        difficulty: int,
    ) -> str:
        """构建出题提示词"""
        type_desc = {
            "single": "单选题（4个选项，1个正确答案）",
            "multiple": "多选题（4个选项，多个正确答案）",
            "judge": "判断题（正确或错误）",
            "fill": "填空题",
            "short_answer": "简答题",
        }

        return f"""请生成 {count} 道关于 "{topic}" 的 {type_desc.get(question_type, question_type)}。

难度等级：{difficulty}/5

请以 JSON 数组格式返回，每道题包含以下字段：
- question_text: 题目内容
- answer: 正确答案
- analysis: 答案解析
- options: 选项数组（选择题需要，每个选项包含 label 和 content）

示例格式：
[
  {{
    "question_text": "题目内容",
    "options": [
      {{"label": "A", "content": "选项A"}},
      {{"label": "B", "content": "选项B"}},
      {{"label": "C", "content": "选项C"}},
      {{"label": "D", "content": "选项D"}}
    ],
    "answer": "A",
    "analysis": "解析内容"
  }}
]

只返回 JSON，不要有其他文字。"""

    def _extract_json_from_text(self, text: str) -> Optional[list]:
        """从文本中提取并修复 JSON 数组"""
        if not text:
            return None

        # 1. 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 2. 尝试从 JSON_START/JSON_END 标记中提取
        start_match = re.search(r'JSON_START\s*\n?', text)
        end_match = re.search(r'JSON_END', text)
        if start_match and end_match:
            json_str = text[start_match.end():end_match.start()].strip()
            try:
                result = json.loads(json_str)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                json_str = self._fix_json(json_str)
                try:
                    result = json.loads(json_str)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass

        # 3. 尝试从代码块中提取
        code_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', text)
        if code_match:
            try:
                result = json.loads(code_match.group(1))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                fixed = self._fix_json(code_match.group(1))
                try:
                    result = json.loads(fixed)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass

        # 4. 智能提取:找第一个 [ 到最后一个 ]
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            try:
                result = json.loads(json_str)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                fixed = self._fix_json(json_str)
                try:
                    result = json.loads(fixed)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass

        return None

    def _fix_json(self, json_str: str) -> str:
        """修复常见 JSON 问题"""
        # 移除控制字符
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)

        # 移除 reasoning_content 字段(DeepSeek 思考过程会破坏 JSON)
        json_str = re.sub(r'"reasoning_content"\s*:\s*"[^"]*"\s*,?', '', json_str)

        # 清理 Markdown 代码块标记
        json_str = re.sub(r'^```(?:json)?\s*', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'\s*```$', '', json_str, flags=re.MULTILINE)

        # 中文引号转英文引号
        json_str = json_str.replace('\u201c', '"').replace('\u201d', '"')
        json_str = json_str.replace('\u2018', "'").replace('\u2019', "'")

        # 移除尾逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 补对象间缺失逗号: }{ → },{  }] → }]  ]{ → ],{
        json_str = re.sub(r'}\s*{', '},{', json_str)
        json_str = re.sub(r'}\s*]', '}]', json_str)
        json_str = re.sub(r']\s*{', '],{', json_str)

        # 补全缺失的闭合括号
        open_brackets = json_str.count('[') - json_str.count(']')
        open_braces = json_str.count('{') - json_str.count('}')
        if open_brackets > 0:
            json_str += ']' * open_brackets
        if open_braces > 0:
            json_str += '}' * open_braces

        return json_str


# 全局服务实例
ai_generate_service = AiGenerateService()
