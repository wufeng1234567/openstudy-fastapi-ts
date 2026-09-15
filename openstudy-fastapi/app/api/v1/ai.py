"""
AI 功能 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, error
from app.services.ai import dynamic_ai
from app.services.ai import db_config
from app.services.ai import conversation_service
from app.services.ai.prompts import ASSISTANT_SYSTEM_PROMPT
from app.services.ai.base_client import ChatMessage
from app.services.ai.generate_service import ai_generate_service
import json

router = APIRouter(prefix="/ai")


class ChatRequest(BaseModel):
    messages: List[dict]
    model: str = "deepseek-chat"
    provider: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000
    # 深度思考：true/false 覆盖 DB 配置；不传则跟随配置
    thinking: Optional[bool] = None


class GenerateRequest(BaseModel):
    topic: Optional[str] = None
    knowledgePoint: Optional[str] = None
    question_type: Optional[str] = "single"
    questionType: Optional[str] = None
    count: int = 5
    difficulty: int = 3
    bank_id: Optional[int] = None
    bankId: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    userId: Optional[int] = None
    # 深度思考：true/false 覆盖 DB 配置；不传则跟随配置
    thinking: Optional[bool] = None


@router.get("/models")
async def list_models(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取模型列表（从 sys_ai_config 表读取，附带系统默认模型信息）"""
    configs = await db_config.get_enabled_configs(db)
    provider_models: dict = {}
    for cfg in configs:
        provider_models.setdefault(cfg.provider, [])
        if cfg.model not in provider_models[cfg.provider]:
            provider_models[cfg.provider].append(cfg.model)

    default_cfg = await db_config.get_default_config(db)
    default_model = None
    if default_cfg:
        default_model = {
            "provider": default_cfg.provider,
            "providerName": default_cfg.provider_name or default_cfg.provider,
            "model": default_cfg.model,
        }

    return success({
        "models": provider_models,
        "default": default_model,
    })


@router.get("/switch-model")
async def switch_model(
    provider: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """切换模型"""
    return success({"provider": provider})


@router.post("/chat")
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 聊天（优先使用 sys_ai_config 表配置）"""
    try:
        messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in data.messages]
        response = await db_config.chat_with_config(
            db,
            messages=messages,
            provider=data.provider,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            thinking=data.thinking,
        )
        return success({
            "content": response.content,
            "usage": response.usage,
        })
    except Exception as e:
        return error(str(e))


@router.post("/generate/questions")
async def generate_questions(
    data: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 出题"""
    try:
        topic = data.topic or data.knowledgePoint or ""
        question_type = data.questionType or data.question_type or "single"
        bank_id = data.bank_id or data.bankId

        questions = await ai_generate_service.generate_questions(
            topic=topic,
            question_type=question_type,
            count=data.count,
            difficulty=data.difficulty,
            model=data.model,
            provider=data.provider,
            db=db,
            thinking=data.thinking,
        )

        # 如果指定了题库，保存到题库
        if bank_id and questions:
            from app.database import async_session_factory
            from app.repositories.question_repo import QuestionRepository, QuestionBankRepository
            from app.models.question import QuestionMain

            async with async_session_factory() as db:
                question_repo = QuestionRepository(db)
                # AI 返回的题型映射: 字符串→数字
                _type_map = {
                    "single": 1, "单选": 1, "1": 1,
                    "multiple": 2, "多选": 2, "2": 2,
                    "judge": 3, "判断": 3, "3": 3,
                    "fill": 4, "填空": 4, "4": 4,
                    "essay": 5, "short_answer": 5, "简答": 5, "5": 5,
                    "composite": 6, "组合": 6, "6": 6,
                }
                for q in questions:
                    raw_type = q.get("questionType", q.get("question_type", 1))
                    q_type = _type_map.get(str(raw_type).lower(), _type_map.get(str(raw_type), 1)) if raw_type else 1
                    question = QuestionMain(
                        bank_id=bank_id,
                        question_type=q_type,
                        question_text=q.get("question_text", q.get("question_content", q.get("questionText", ""))),
                        answer=q.get("answer", q.get("question_answer", "")),
                        analysis=q.get("analysis", q.get("question_analysis", "")),
                        options=q.get("options"),
                        difficulty=data.difficulty,
                        status="0",
                    )
                    await question_repo.create(question)

                bank_repo = QuestionBankRepository(db)
                await bank_repo.update_total_questions(bank_id)
                await db.commit()

        return success(questions)
    except Exception as e:
        return error(str(e))


@router.get("/generate/questions/stream")
async def generate_questions_stream(
    knowledgePoint: str = Query(...),
    questionType: str = Query("single"),
    count: int = Query(5),
    provider: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成题目（thinking=true 时开启深度思考，仅输出正式回答）"""
    async def event_generator():
        try:
            prompt = f"""请生成 {count} 道关于 "{knowledgePoint}" 的题目。

题型：{questionType}

请以 JSON 数组格式返回，每道题包含：
- questionText: 题目内容
- answer: 正确答案
- analysis: 解析
- options: 选项数组（选择题需要）

只返回 JSON，不要有其他文字。"""

            messages = [
                ChatMessage(role="system", content="你是一个专业的出题助手。"),
                ChatMessage(role="user", content=prompt),
            ]

            async for chunk in db_config.stream_with_config(db, messages, provider=provider, temperature=0.8, thinking=thinking):
                yield chunk
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


@router.post("/generate/questions/sync")
async def generate_questions_sync(
    data: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """非流式生成题目"""
    try:
        topic = data.topic or data.knowledgePoint or ""
        question_type = data.questionType or data.question_type or "single"

        questions = await ai_generate_service.generate_questions(
            topic=topic,
            question_type=question_type,
            count=data.count,
            difficulty=data.difficulty,
            model=data.model,
            provider=data.provider,
            db=db,
            thinking=data.thinking,
        )
        return success(questions)
    except Exception as e:
        return error(str(e))


@router.get("/generate/reading/stream")
async def generate_reading_stream(
    requirement: str = Query(...),
    questionCount: int = Query(5),
    provider: Optional[str] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成阅读理解题（thinking=true 开启深度思考，仅输出正式回答）"""
    async def event_generator():
        try:
            prompt = f"""请根据以下要求生成 {questionCount} 道阅读理解题：

{requirement}

请以 JSON 数组格式返回。"""

            messages = [
                ChatMessage(role="system", content="你是一个专业的出题助手。"),
                ChatMessage(role="user", content=prompt),
            ]

            async for chunk in db_config.stream_with_config(db, messages, provider=provider, temperature=0.8, thinking=thinking):
                yield chunk
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


@router.get("/generate/composite/stream")
async def generate_composite_stream(
    requirement: str = Query(...),
    questionCount: int = Query(5),
    wordCount: int = Query(300),
    provider: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成组合题（thinking=true 开启深度思考，仅输出正式回答）"""
    async def event_generator():
        try:
            prompt = f"""请根据以下要求生成 {questionCount} 道组合题：

{requirement}

文章字数约 {wordCount} 字。

请以 JSON 格式返回。"""

            messages = [
                ChatMessage(role="system", content="你是一个专业的出题助手。"),
                ChatMessage(role="user", content=prompt),
            ]

            async for chunk in db_config.stream_with_config(db, messages, provider=provider, temperature=0.8, thinking=thinking):
                yield chunk
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


@router.post("/generate/composite/sync")
async def generate_composite_sync(
    data: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """非流式生成组合题"""
    try:
        topic = data.topic or data.knowledgePoint or ""

        prompt = f"""请生成关于 "{topic}" 的组合题，包含阅读材料和问题。

请以 JSON 格式返回。"""

        messages = [
            ChatMessage(role="system", content="你是一个专业的出题助手。"),
            ChatMessage(role="user", content=prompt),
        ]

        response = await db_config.chat_with_config(
            db, messages, provider=data.provider, temperature=0.8, thinking=data.thinking
        )

        try:
            result = json.loads(response.content)
            # 敏感词过滤(replace 模式)
            if isinstance(result, list):
                result = await ai_generate_service._filter_sensitive(result)
            elif isinstance(result, dict):
                filtered = await ai_generate_service._filter_sensitive([result])
                result = filtered[0] if filtered else result
            return success(result)
        except:
            return success(response.content)
    except Exception as e:
        return error(str(e))


@router.get("/assistant/stream")
async def assistant_stream(
    message: str = Query(...),
    provider: Optional[str] = Query(None),
    sessionId: str = Query("assistant"),
    userId: Optional[int] = Query(None),
    thinking: Optional[bool] = Query(
        None, description="深度思考：true=开启 / false=关闭 / 不传=跟随模型配置"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """助手流式聊天（带会话上下文；provider 为空时使用 sys_ai_config 表默认模型）

    深度思考由 `thinking` 参数控制（覆盖 DB 里的 thinking_mode）；
    只输出正式回答，思考过程不下发（前端用「思考中」动画占位）。
    """
    user_id = userId or current_user.get("user_id") or 0

    # 先取历史上下文、再保存本轮用户消息，避免当前问题在上下文里重复出现
    context = await conversation_service.build_context_prompt(user_id, sessionId)
    await conversation_service.save_message(user_id, sessionId, "user", message)
    full_message = f"{context}\n【当前问题】\n{message}" if context else message

    async def event_generator():
        full_response = ""
        try:
            messages = [
                ChatMessage(role="system", content=ASSISTANT_SYSTEM_PROMPT),
                ChatMessage(role="user", content=full_message),
            ]

            async for chunk in db_config.stream_with_config(
                db, messages, provider=provider, thinking=thinking
            ):
                full_response += chunk
                yield chunk
            # 流式结束后把 AI 回复写入会话历史
            await conversation_service.save_message(user_id, sessionId, "assistant", full_response)
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


class GenerateWithImagesRequest(BaseModel):
    """AI 搭建题库：支持图片的生成请求"""
    message: str
    images: List[str] = []  # base64 data URLs，如 ["data:image/jpeg;base64,..."]
    provider: Optional[str] = None
    thinking: Optional[bool] = None


@router.post("/assistant/generate-with-images")
async def generate_with_images(
    req: GenerateWithImagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 搭建题库专用：支持图片的流式生成（DeepSeek Flash 视觉模型）

    images 为 base64 data URL 数组，前端将上传的图片编码后传入。
    """
    from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock

    # 构建多模态消息内容
    user_content = []
    if req.message:
        user_content.append(TextBlock(type="text", text=req.message))
    for img_url in req.images:
        user_content.append(ImageBlock(type="image_url", image_url={"url": img_url}))

    async def event_generator():
        full_response = ""
        try:
            messages = [
                ChatMessage(role="system", content=ASSISTANT_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_content),
            ]

            async for chunk in db_config.stream_with_config(
                db, messages, provider=req.provider, thinking=req.thinking
            ):
                full_response += chunk
                yield chunk
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


@router.get("/conversation/{session_id}")
async def get_conversation(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取对话历史"""
    user_id = userId or current_user.get("user_id") or 0
    return success(await conversation_service.get_messages(user_id, session_id))


@router.delete("/conversation/{session_id}")
async def clear_conversation(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """删除某个会话（消息 + 会话列表条目）"""
    user_id = userId or current_user.get("user_id") or 0
    await conversation_service.delete_session(user_id, session_id)
    return success()


# ===================== 会话列表 =====================

@router.get("/sessions")
async def list_sessions(
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的会话列表（按最后更新时间倒序）"""
    user_id = userId or current_user.get("user_id") or 0
    return success(await conversation_service.list_sessions(user_id))


@router.post("/sessions")
async def create_session(
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """新建会话：立即写入会话列表（标题暂为「新会话」，首条消息后自动替换）"""
    user_id = userId or current_user.get("user_id") or 0
    session_id = conversation_service.new_session_id()
    await conversation_service.touch_session(user_id, session_id, title="新会话")
    return success({"sessionId": session_id})


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """删除会话（消息 + 会话列表条目）"""
    user_id = userId or current_user.get("user_id") or 0
    await conversation_service.delete_session(user_id, session_id)
    return success()


@router.get("/bank/context/{bank_id}")
async def get_bank_context(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取题库 AI 上下文"""
    from app.models.question import QuestionBank, QuestionMain
    from sqlalchemy import select, func

    # 获取题库信息
    bank_query = select(QuestionBank).where(QuestionBank.id == bank_id, QuestionBank.status == "0")
    bank_result = await db.execute(bank_query)
    bank = bank_result.scalar_one_or_none()

    if not bank:
        return error("题库不存在")

    # 获取题目数量
    count_query = select(func.count()).where(QuestionMain.bank_id == bank_id, QuestionMain.status == "0")
    question_count = await db.scalar(count_query) or 0

    return success({
        "bankId": bank.id,
        "bankName": bank.bank_name,
        "questionCount": question_count,
    })


@router.delete("/conversation/bank/{bank_id}")
async def clear_bank_conversation(
    bank_id: int,
    current_user: dict = Depends(get_current_user),
):
    """清空题库对话上下文"""
    from app.utils.redis_util import delete_cache

    user_id = current_user.get("user_id")
    key = f"ai:bank_conversation:{user_id}:{bank_id}"
    await delete_cache(key)

    return success()


@router.post("/question-bank/parse-files-blocks")
async def parse_files_blocks(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """解析上传文件为结构化块"""
    from app.services.file_parser import parse_file

    results = []
    for file in files:
        content = await file.read()
        try:
            parsed = parse_file(file.filename, content)
            results.append(parsed)
        except Exception as e:
            results.append({
                "fileName": file.filename,
                "textContent": "",
                "blocks": [],
                "images": [],
                "totalTextLength": 0,
                "error": str(e),
            })

    # 单文件直接返回,多文件合并为数组返回
    if len(results) == 1:
        return success(results[0])
    return success(results)


@router.get("/analyze/question/stream")
async def analyze_question_stream(
    question: str = Query(...),
    questionType: Optional[str] = Query(None),
    options: Optional[str] = Query(None),
    correctAnswer: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    deepThink: Optional[bool] = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """题目智能解析"""
    async def event_generator():
        try:
            prompt = f"""请作为专业教师，对以下题目进行详细解析。

## 题目信息
- 题型：{questionType or '未知'}
- 题目：{question}
"""
            if options:
                prompt += f"- 选项：\n{options}\n"
            if correctAnswer:
                prompt += f"- 正确答案：{correctAnswer}\n"

            prompt += """
## 解析要求
请按以下结构输出：

📋 【考点分析】
说明本题考查的核心知识点和能力要求。

💡 【解题思路】
分步骤详细说明解题过程，逻辑清晰。

✅ 【答案详解】
解释为什么正确答案是对的，其他选项为什么错（如有选项）。

📌 【易错点提示】
指出学生容易犯的错误和注意事项。

⭐ 【拓展建议】
给出相关知识点的学习建议或举一反三的思路。
"""

            messages = [
                ChatMessage(role="system", content="你是一位经验丰富的教师，擅长对各学科题目进行深入浅出的解析。请用 Markdown 格式输出，结构清晰，语言通俗易懂。"),
                ChatMessage(role="user", content=prompt),
            ]

            # 深度思考统一由 thinking 参数控制（走 DB 配置的模型，不再硬编码 reasoner）；
            # 只下发正式回答（content），思考过程不下发，前端用「思考中」动画占位。
            async for chunk in db_config.stream_with_config(
                db, messages, provider=provider, thinking=deepThink
            ):
                yield chunk
            yield "[DONE]"
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")
