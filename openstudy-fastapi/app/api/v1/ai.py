"""
AI 功能 API

本文件只做两件事：
  1. 会话 / 模型列表 / 附件解析等**非流式**接口；
  2. 把**流式**请求搬到 `app/services/ai/chat_engine.py`（薄壳，见文件下半部分）。

`base64` / `re` / `Any` / `dynamic_ai` 这些 import 在流式逻辑搬走后已无人使用，
顺手清掉 —— 需要的工具都在 chat_engine 里。
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from app.database import get_db
from app.core.security import get_current_user, resolve_user_scope
from app.core.response import success, error
# `fail` 是 Agent 工具的统一失败信封（{success: False, error, hint}）。
# `/ai/agent/execute` 的越权拒绝必须用它而不是 `error()` —— 前端判的是 `success` 字段，
# 详见该端点里的注释。
from app.services.ai.agent.base import fail
from app.services.ai import db_config
from app.services.ai import conversation_service
from app.services.ai import chat_engine
from app.services.ai import prompts
from app.services.ai.prompts import ASSISTANT_SYSTEM_PROMPT
from app.services.ai.base_client import ChatMessage
from app.services.ai.generate_service import ai_generate_service
from loguru import logger
import json

router = APIRouter(prefix="/ai")


@router.get("/prompts/assistant")
async def get_assistant_prompt(
    current_user: dict = Depends(get_current_user),
):
    """下发助手系统提示词（只读，不调模型）

    用途：ds-free 走前端直连（浏览器扩展代发 DS 网页版），不经过后端的
    assistant/stream，因此前端需要自己拿到系统提示词。

    这里把它做成接口，是为了保持**单一事实来源** —— 提示词只在
    `app/services/ai/prompts.py` 维护一份，官方 API 链路与 ds-free 链路
    自动一致，不需要在前端再抄一遍。
    """
    return success({"assistant": ASSISTANT_SYSTEM_PROMPT})


class ChatRequest(BaseModel):
    messages: List[dict]
    model: str = "deepseek-chat"
    provider: Optional[str] = None
    # configId：精确指定选中哪条配置（区分同名模型）
    configId: Optional[int] = None
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
    # configId：精确指定选中哪条配置（区分同名模型）
    configId: Optional[int] = None
    userId: Optional[int] = None
    # 深度思考：true/false 覆盖 DB 配置；不传则跟随配置
    thinking: Optional[bool] = None


@router.get("/models")
async def list_models(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取模型列表（从 sys_ai_config 表读取，附带默认模型信息）

    只回传「该用户可用的」配置：系统提供 + 他自己在个人中心加的自定义模型。
    """
    uid = current_user.get("user_id")
    configs = await db_config.get_enabled_configs(db, uid)
    provider_models: dict = {}
    for cfg in configs:
        provider_models.setdefault(cfg.provider, [])
        if cfg.model not in provider_models[cfg.provider]:
            provider_models[cfg.provider].append(cfg.model)

    default_cfg = await db_config.get_default_config(db, uid)
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
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=data.configId,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            thinking=data.thinking,
            user_id=current_user.get("user_id"),
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
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=data.configId,
            db=db,
            thinking=data.thinking,
            user_id=current_user.get("user_id"),
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
    model: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成题目（scene=question-generate）

    一次性生成，不传 sessionId → **不写聊天历史**；温度 0.8 保持原有出题风格。
    """
    turn = chat_engine.ChatTurn(
        scene=prompts.SCENE_QUESTION_GENERATE,
        prompt=knowledgePoint,
        provider=provider,
        model=model,
        thinking=thinking,
        temperature=0.8,
        variables={
            "count": count,
            "knowledge_point": knowledgePoint,
            "question_type": questionType,
        },
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


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
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=data.configId,
            db=db,
            thinking=data.thinking,
            user_id=current_user.get("user_id"),
        )
        return success(questions)
    except Exception as e:
        return error(str(e))


@router.get("/generate/reading/stream")
async def generate_reading_stream(
    requirement: str = Query(...),
    questionCount: int = Query(5),
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成阅读理解题（scene=reading；一次性生成，不写聊天历史）"""
    turn = chat_engine.ChatTurn(
        scene=prompts.SCENE_READING,
        prompt=requirement,
        provider=provider,
        model=model,
        thinking=thinking,
        temperature=0.8,
        variables={"requirement": requirement, "question_count": questionCount},
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


@router.get("/generate/composite/stream")
async def generate_composite_stream(
    requirement: str = Query(...),
    questionCount: int = Query(5),
    wordCount: int = Query(300),
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    thinking: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """流式生成组合题（scene=composite；一次性生成，不写聊天历史）"""
    turn = chat_engine.ChatTurn(
        scene=prompts.SCENE_COMPOSITE,
        prompt=requirement,
        provider=provider,
        model=model,
        thinking=thinking,
        temperature=0.8,
        variables={
            "requirement": requirement,
            "question_count": questionCount,
            "word_count": wordCount,
        },
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


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
            db,
            messages,
            provider=data.provider,
            # configId：精确指定选中哪条配置（区分同名模型）
            config_id=data.configId,
            temperature=0.8,
            thinking=data.thinking,
            model=data.model,
            user_id=current_user.get("user_id"),
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


# ========== 流式对话路由（全部只是 chat_engine 的薄壳） ==========
#
# 本文件**不再有任何流式逻辑**。取配置、组 messages、多模态附件、视觉兜底、
# 落库、事件契约统一由 `app/services/ai/chat_engine.py` 负责；系统提示词与用户
# 模板统一由 `app/services/ai/prompts.py` 按 scene 提供。这里的每个路由都只是
# 「HTTP 参数 → ChatTurn」的搬运工。
#
# ⚠️ 新增 AI 能力请去 `prompts.py` 加一个 scene，**不要在这里再写一个流式接口**。
#    出题 / 阅读 / 组合 / 解析等一次性生成场景不传 sessionId（不写聊天历史）；
#    只有聊天助手（scene=assistant）带 sessionId，才会读写会话上下文。


@router.get("/assistant/stream")
async def assistant_stream(
    message: str = Query(...),
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    sessionId: str = Query("assistant"),
    userId: Optional[int] = Query(None),
    scene: Optional[str] = Query(
        None, description="场景（见 prompts.SCENE_*），默认 assistant"
    ),
    thinking: Optional[bool] = Query(
        None, description="深度思考：true=开启 / false=关闭 / 不传=跟随模型配置"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """助手流式聊天（GET 版，**保留向后兼容 / 便于浏览器直贴调试**）

    ⚠️ 应用内不再调用它 —— 前端统一走 `POST /ai/assistant/stream`（见 ai.ts 的
    `postAiStream`）。保留 GET 是为了能在浏览器地址栏直接贴 URL 排查问题
    （GET 版本只支持纯文本，长文本还会撞 URL 长度上限，所以不再作为主入口）。

    历史落库（纯 SQL，不依赖 Redis）、「提问 / 回复成对写入」、统一事件契约
    全部由 `chat_engine.stream_turn()` 保证，此处不再重复实现。
    """
    # 越权防护：不接受以他人身份发起对话（见 security.resolve_user_scope）。
    # ⚠️ 形状必须是 HTTP 403 + error()：前端 `postAiStream` 判的是 `response.ok`。
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return JSONResponse(status_code=403, content=error(err, code=403))

    turn = chat_engine.ChatTurn(
        scene=scene or prompts.SCENE_ASSISTANT,
        prompt=message,
        # GET 只能带一个文本参数，这里把它同时填进各模板的主变量
        # （knowledge_point / requirement / question），出题类 scene 也能直接用。
        # 模板只会取自己需要的那一个，多填不生效，也不会互相干扰。
        variables={
            "knowledge_point": message,
            "requirement": message,
            "question": message,
        },
        provider=provider,
        model=model,
        thinking=thinking,
        session_id=sessionId,
        user_id=user_id,
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


class AssistantAttachment(BaseModel):
    """附件载荷：前端读成 data URL 后随请求提交（不落存储）"""
    name: str = "file"
    type: Optional[str] = ""
    base64: str = ""


class AssistantStreamRequest(BaseModel):
    """**全平台统一的流式请求体**（带图片 / 文档附件）

    前端所有 AI 流式能力都提交这个结构，用 `scene` 区分场景 —— 这样一个
    「AI 搭建题库」和「OS 助手」走的就是**同一个接口**，不再各调一个。
    """
    message: str = ""
    #: 图片的 base64 data URL，直接作为多模态内容块下发
    images: List[str] = []
    #: 文档附件（pdf / docx / txt / md…），服务端抽正文后并入提示词
    files: List[AssistantAttachment] = []
    #: 只用于历史落库的缩略图元信息 [{name,type,thumb}]，不参与推理
    attachments: List[dict] = []
    #: 场景，见 `prompts.SCENE_*`（assistant / question-bank / question-generate /
    #: reading / composite / analysis）。决定系统提示词与用户模板。
    scene: str = "assistant"
    #: 场景模板变量（出题类场景用：count / knowledge_point / question_type /
    #: requirement / question / options / correct_answer …）
    variables: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    # configId：精确指定选中哪条配置（区分同名模型）
    configId: Optional[int] = None
    #: 会话 id。**只有聊天助手会传**（且形如 `asst_xxx`）；留空 = 不写聊天历史。
    sessionId: str = ""
    userId: Optional[int] = None
    thinking: Optional[bool] = None
    #: 采样温度。不传 = 0.7（聊天默认）；出题类历史口径是 0.8，由前端显式传。
    temperature: Optional[float] = None
    #: 「注入历史记忆」开关（**仅 ds-free-nb 端有意义**，API 端忽略）：
    #: True = 把当前会话历史拼进正文并**作为附件投递**给 DS 网页（避免长历史灌输入框卡死）。
    injectHistory: bool = False


@router.post("/assistant/stream")
async def assistant_stream_with_attachments(
    req: AssistantStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**统一的 AI 流式入口**（多模态；聊天助手 / AI 搭建题库 … 共用）

    场景由 `scene` 决定（`prompts.SCENE_*`）：

    | scene | 用途 | 是否写聊天历史 |
    |---|---|---|
    | `assistant` | OS / 聊天助手 | 只有 `sessionId` 非空才写 |
    | `question-bank` | AI 搭建题库 | 否 |
    | `question-generate` / `reading` / `composite` / `analysis` | 出题类 | 否 |

    附件语义：
      - `images`：图片的 base64 data URL → 多模态 `image_url` 内容块；
      - `files` ：文档附件 → 由 `chat_engine` 用 `file_parser` 抽正文并入提示词，
        docx 里的插图也一并作为图片块交给模型；
      - `attachments`：**只用于历史落库**的缩略图元信息（前端生成）。
        原图不落库，避免把 `ai_chat_message.attachments` 撑爆（该列已是 MEDIUMTEXT）。

    模型能力兜底：所选模型若不支持图片（例如 deepseek-v4-pro），由 `chat_engine`
    统一回退到视觉模型；前端在发送前也会做同样的切换并提示用户，本处是防御性兜底。
    """
    # 越权防护：不接受以他人身份发起对话（见 security.resolve_user_scope）。
    # ⚠️ 形状必须是 HTTP 403 + error()：前端 `postAiStream` 判的是 `response.ok`。
    user_id, err = resolve_user_scope(current_user, req.userId)
    if err:
        return JSONResponse(status_code=403, content=error(err, code=403))

    turn = chat_engine.ChatTurn(
        scene=req.scene or prompts.SCENE_ASSISTANT,
        prompt=req.message,
        images=list(req.images or []),
        files=list(req.files or []),
        attachments=[a for a in (req.attachments or []) if a],
        variables=req.variables or {},
        provider=req.provider,
        model=req.model,
        # configId：精确指定选中哪条配置（区分同名模型）
        config_id=req.configId,
        thinking=req.thinking,
        # 不传则用 ChatTurn 的默认 0.7（聊天口径）；出题类由前端传 0.8
        temperature=req.temperature if req.temperature is not None else 0.7,
        session_id=req.sessionId,
        user_id=user_id,
        inject_history=bool(req.injectHistory),
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


class GenerateWithImagesRequest(BaseModel):
    """AI 搭建题库：支持图片的生成请求"""
    message: str = ""
    images: List[str] = []  # base64 data URLs，如 ["data:image/jpeg;base64,..."]
    provider: Optional[str] = None
    model: Optional[str] = None
    thinking: Optional[bool] = None


# ============================================================
# Agent（工具调用）
# ============================================================


class AgentStreamRequest(BaseModel):
    """**Agent 模式请求体**：让模型自己调用工具完成任务

    与 `AssistantStreamRequest`（普通流式对话）的区别：
    - 这里是**多轮工具调用循环**，事件流是「换行分隔的 JSON」而不是纯文本分片；
    - 必须选官方 API 模型（ds-free 走扩展代发，协议上挂不了 `tools`）。
    """

    message: str = ""
    #: 图片 base64 data URL —— 模型能**看到**这些图（可能整张图就是题目）
    images: List[str] = []
    #: 文档附件；服务端抽正文并把插图编号成【图N】供题目引用
    files: List[AssistantAttachment] = []
    #: 仅历史落库用的附件元信息
    attachments: List[dict] = []
    provider: Optional[str] = None
    model: Optional[str] = None
    # configId：精确指定选中哪条配置（区分同名模型）
    configId: Optional[int] = None
    temperature: Optional[float] = None
    #: 会话 id；非空才写聊天历史
    sessionId: str = ""
    #: **轮次 id（前端每轮生成）**：回退账本（`ai_agent_op_log`）的归组键 ——
    #: 用户点「回退这一轮」时，服务端按 `(user_id, sessionId, turnId)` 取回这一轮的
    #: 全部写操作并倒序撤销。后端**不定义轮边界**（轮边界在前端：一次 runStream = 一轮），
    #: 只负责原样记账 + 在 `meta` 事件里回显。
    #: ⚠️ 这个字段**必须**在这里显式声明：pydantic 默认忽略未知字段，前端传上来会被
    #:    静默丢掉，后端只能兜一个 `auto_<hex>`，而轮末标记带的是前端的 `t_...`
    #:    → 回退查不到账本行（表现为「点了没反应」）。
    turnId: str = ""
    userId: Optional[int] = None
    #: 写操作是否自动执行（默认 True —— Agent 自动建题库/导题需要它）
    autoConfirm: bool = True
    #: 最大「模型 → 工具」往返轮数（默认 12）
    maxLoops: Optional[int] = None
    #: **官方智能体角色 key**（题库/笔记/知识库/记忆/统计/通用，见 `agent/roles.py`）。
    #: 显式指定时用该角色的窄工具集与专属指令；为空则后端按消息**规则路由**（零 LLM 成本），
    #: 路由不确定会退 `general`（全工具）。见 `agent/orchestrator.py`。
    role: str = ""
    #: **用户自定义智能体 id**（阶段 2 落地）。现仅透传占位，编排层暂不消费。
    agentId: Optional[int] = None
    #: 「注入历史记忆」开关（**仅 ds-free-nb 端有意义**，API 端忽略）：
    #: True = 把当前会话历史拼进本轮并把正文作为附件投递给 DS 网页（避免长历史灌输入框卡死）。
    injectHistory: bool = False


@router.post("/agent/stream")
async def agent_stream(
    req: AgentStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**Agent 流式入口**：上传题库文档 / 图片 → 模型调用工具自动建题库、导题目

    事件契约见 `services/ai/agent/loop.py` 的模块 docstring（换行分隔的 JSON），
    前端由 `api/ai/agent.ts` 解析。

    典型的「自动搭建题库」全过程：
        meta → tool_start(bank_manage.create) → tool_result
             → tool_start(question_manage.batch_import) → tool_result
             → text（总结）→ done → [DONE]

    模型填错参数会被 `ExecutionGuard` 拦下并**回灌给模型自己改**（事件里表现为
    `self_correct`），所以前端能看到「它正在纠正自己」。
    """
    from app.services.ai.agent.loop import AgentRequest, run_agent_stream

    # 越权防护：不接受以他人身份跑 Agent（工具会真实写库，这条尤其重要）。
    # ⚠️ 形状必须是 HTTP 403 + error()：前端 `postAgentStream` 判的是 `response.ok`。
    user_id, err = resolve_user_scope(current_user, req.userId)
    if err:
        return JSONResponse(status_code=403, content=error(err, code=403))

    agent_req = AgentRequest(
        message=req.message,
        images=list(req.images or []),
        files=list(req.files or []),
        attachments=[a for a in (req.attachments or []) if a],
        provider=req.provider,
        model=req.model,
        # configId：精确指定选中哪条配置（区分同名模型）
        config_id=req.configId,
        temperature=req.temperature if req.temperature is not None else 0.3,
        max_loops=req.maxLoops or 12,
        auto_confirm=bool(req.autoConfirm),
        session_id=req.sessionId,
        user_id=user_id,
        # 回退账本的归组键：前端每轮生成，原样透传（见 AgentStreamRequest.turnId）
        turn_id=req.turnId or "",
        # 多智能体协同：官方角色 key（空则由后端规则路由）+ 用户自定义智能体 id（阶段 2）
        role=req.role or "",
        agent_id=req.agentId,
        inject_history=bool(req.injectHistory),
    )
    return StreamingResponse(
        run_agent_stream(db, agent_req),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AgentExecuteRequest(BaseModel):
    """**Agent 工具执行请求**：ds-free（浏览器扩展）客户端循环每解析出一个 tool_call 就调一次

    ds-free 协议上挂不了原生 Function Calling，工具调用循环跑在**前端**。
    前端驱动模型 → 解析出 `tool_call` → 调本接口在**服务端**执行真实工具（写库 / 查库）
    → 把结果回灌模型。本接口只做「单次、无循环」的执行，返回 `ok()` / `fail()` 信封。
    """

    tool: str
    params: Dict[str, Any] = {}
    #: 用户上传的图片 data URL（用于题目里【图N】标记替换）
    images: List[str] = []
    userId: Optional[int] = None
    sessionId: str = ""
    #: **轮次 id（前端透传）**：ds-free 的工具循环跑在前端，**一轮里会发多次**
    #: `/ai/agent/execute`（每次工具调用一次），靠它把这些调用归到同一轮 ——
    #: 否则每次调用各自兜一个 `auto_<hex>`，「回退这一轮」只能退回最后一次。
    #: 与 `AgentStreamRequest.turnId` 同义（见那里的说明）。
    turnId: str = ""
    #: 写操作是否自动执行（前端开关透传）
    autoConfirm: bool = True
    #: 前端是否已经弹过确认卡片且用户点了「确认」
    #: ⚠️ v1 契约（2026-09-21）起**保留但不再是充分条件** —— 前端 `executeTool` 是
    #: 无条件填 true 的，只看它等于「服务端没有授权」。真正的授权是 `confirmTicket`
    #: （服务端签发、与用户/工具/参数绑定、一次性、180 秒有效）。
    confirmed: bool = False
    #: **服务端确认票据**：从 `POST /ai/agent/preview` 的 `confirmTicket` 拿回来。
    #: 需要确认的操作（破坏性动作恒需要；`autoConfirm=false` 时所有写操作）必须带，
    #: 否则直接 `fail()` 且**不执行工具**。不需要确认的操作不要求（存量调用方零改动）。
    confirmTicket: str = ""


@router.post("/agent/execute")
async def agent_execute(
    req: AgentExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**Agent 工具执行入口（ds-free 客户端循环用）**

    与 `/ai/agent/stream`（后端多轮循环）互补：这里只执行单个工具，循环由前端维护。

    ⚠️ 需要确认的操作必须带 `confirmTicket`（见 `AgentExecuteRequest` 的字段说明）：
    票据由 `/ai/agent/preview` 签发，校验签名 / 用户 / 工具+参数 / 有效期，且**一次性**。
    """
    from app.services.ai.agent.loop import execute_agent_tool, persist_agent_images
    from loguru import logger

    # 越权防护：本接口会真实读写用户数据，**绝不许以他人身份执行**
    # （见 security.resolve_user_scope）。
    # ⚠️ 错误形状**必须**是 `fail()` 信封，不能是 `error()`：
    #    前端 ds-free 循环判的是 `result.success !== false`，而 `error()` 的形状是
    #    `{code, msg, data}` —— **没有 `success` 字段** → `undefined !== false` 为真
    #    → 会被判成**成功**，界面上出现一张绿色成功卡片、数据却是空的。
    user_id, err = resolve_user_scope(current_user, req.userId)
    if err:
        return JSONResponse(status_code=403, content=fail(err, "只能操作自己的数据"))

    image_urls: List[str] = []
    if req.images:
        try:
            image_urls = await persist_agent_images(req.images)
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent/execute] 图片落盘失败: {}", e)

    result = await execute_agent_tool(
        db,
        tool_name=req.tool,
        params=req.params or {},
        user_id=user_id,
        session_id=req.sessionId,
        # 回退账本的归组键：同一轮里的多次工具调用共用（见 AgentExecuteRequest.turnId）
        turn_id=req.turnId or "",
        auto_confirm=bool(req.autoConfirm),
        image_urls=image_urls or None,
        confirmed=bool(req.confirmed),
        # ⚠️ 票据校验用的是**服务端认定的** user_id（`resolve_user_scope` 的产物），
        #    不是请求体里的 userId —— 否则改一下 userId 就能用别人的票。
        confirm_ticket=req.confirmTicket or "",
    )
    return result


async def _agent_tools_payload(user_id: int) -> Dict[str, Any]:
    """Agent 工具清单的**唯一组装处**（`GET` 与 `PUT /ai/agent/tools` 共用）。

    ⚠️ 返回的是**全量**清单（含被用户屏蔽的工具），每一项挂一个 `disabled` 兄弟字段：

      · 前端的工具面板要靠这一份渲染「开 / 关」开关 —— 把被屏蔽的工具在这里
        **过滤掉**，用户就再也打开不回来了（他自己的开关随之从界面上消失）。
        这正是知识库那次的坑：**管理列表**（要全量）与**模型可见列表**（要生效后）
        是两个需求，不能共用一个出口；
      · `function` 子对象**一个字都不动** —— 它是 OpenAI Function Calling 的形状，
        ds-free 前端直接拿它拼提示词（`tools[i].function.name` / `.parameters`）。
      · 界面要用的**中文**走另外两个兄弟字段 `label` / `descriptionZh`（同样在 `function`
        外面）—— 见 `AgentTool.label` / `description_zh`。中文一旦进了 `function`，就会
        跟着进提示词，那是 `backend-ai-chain.md` 的 Language policy 明确禁止的。

    `actions`（写操作 / 破坏性操作清单）内容保持原样、仍按**全部**已注册工具推导：
    前端会用同一份响应里的 `disabled` 自行排除被屏蔽的工具，后端不替它做这个减法。
    """
    from app.services.ai.agent import tool_pref_service
    from app.services.ai.agent.loop import ensure_tools_loaded
    from app.services.ai.agent.registry import registry

    ensure_tools_loaded()
    disabled = await tool_pref_service.disabled_tool_names(user_id)

    tools: List[Dict[str, Any]] = []
    for entry in registry.definitions():
        name = str((entry.get("function") or {}).get("name") or "")
        # 兄弟字段（不塞进 `function` 里）：0 = 启用，1 = 已屏蔽。整数，永不 null ——
        # 前端的开关是受控的，拿到 undefined/null 会当场翻转一次并回写（见
        # `rag_write_service.kb_disabled_flag` 里 el-switch 的那条实测说明）。
        #
        # `label` / `descriptionZh` 是**纯界面字段**（中文名 + 中文一句说明）：工具自己声明，
        # 注册表不参与。它们**必须留在 `function` 外面** —— 里面那三个键是模型侧的形状，
        # ds-free 前端直接拿 `function.name` / `.parameters` 拼提示词。
        tool = registry.get(name)
        tools.append(
            {
                **entry,
                "disabled": 1 if name in disabled else 0,
                "label": str(getattr(tool, "label", "") or ""),
                "descriptionZh": str(getattr(tool, "description_zh", "") or ""),
            }
        )

    # 「写操作 / 破坏性操作」清单也一起下发：ds-free 的前端循环要据此决定是否弹二次确认卡片。
    # 由后端工具声明推导（唯一事实来源），避免前端硬编码 action 清单漂移。
    actions: Dict[str, Dict[str, List[str]]] = {}
    for name in registry.names():
        tool = registry.get(name)
        if tool is None:
            continue
        enum = (
            (tool.parameters or {})
            .get("properties", {})
            .get("action", {})
            .get("enum")
            or []
        )
        write = [a for a in enum if tool.needs_confirmation({"action": a})]
        destructive = [a for a in enum if tool.is_destructive({"action": a})]
        if write or destructive:
            actions[name] = {"write": write, "destructive": destructive}

    return {"tools": tools, "actions": actions}


@router.get("/agent/tools")
async def agent_tools(current_user: dict = Depends(get_current_user)):
    """**Agent 工具清单（Function Calling schema + 每个工具的开关状态）**

    ds-free（浏览器扩展）跑客户端循环时需要它来拼「tool_call 协议」提示词 ——
    工具名 / 参数 / 枚举都以后端注册表为唯一事实来源，避免前端硬编码漂移。
    ds-free 的**系统提示词也以这一份为唯一来源**（前端据此拼工具清单），
    所以「被用户屏蔽的工具」在这一层不能消失、只能带标记（见 `_agent_tools_payload`）。

    用户 id **只取自登录态**（`current_user`）：本路由不带 `userId` 参数，
    也就不需要（也不该有）`resolve_user_scope` 那一步 —— 开关是纯私有的。
    """
    return await _agent_tools_payload(int((current_user or {}).get("user_id") or 0))


@router.get("/agent/roles")
async def agent_roles():
    """**官方智能体角色清单**（多智能体协同，阶段 1）

    供前端渲染「智能体选择器」：官方角色（题库/笔记/知识库/记忆/统计/通用）的中文名、
    说明与各自可用工具。**不含任何用户数据**，因此不需要登录态、也不需要用户作用域。

    ⚠️ 返回的 `tools` 是**角色白名单**（`general` 为空数组 = 不限制）。
    前端若要显示「某角色实际能用哪些工具」，需自行与 `GET /ai/agent/tools` 的用户开关求交。
    """
    from app.services.ai.agent.roles import all_role_metas

    # ⚠️ 返回**裸 dict**（与 `GET /ai/agent/tools` 同形状：直接是业务对象，不套
    #    `success()` 的 `{code,msg,data}`）—— 前端两个端点用同一套解析。
    return {
        "roles": [
            {
                "key": r.key,
                "name": r.name,
                "description": r.description,
                "tools": list(r.tools),
            }
            for r in all_role_metas()
        ]
    }


# ============================================================
# 专家（官方角色）开关 —— 用户 2026-10-10 裁决
# ============================================================
# 原先界面开关的是「可用工具」（工具粒度），对普通用户没意义（不懂 bank_manage 是啥）。
# 改为**专家粒度**：用户开关「题库专家 / 笔记专家 / 知识库专家 / 学习统计专家」。
# 关闭某专家 = 指挥家的子代理通讯录里不再出现它 → LLM 实时知道「这个专家叫不到」。


class AgentExpertPrefBody(BaseModel):
    """启用 / 关闭单个专家的请求体（`PUT /ai/agent/experts`）

    与 `AgentToolPrefBody` 同款约束（`extra="forbid"` + `disabled` 必填），理由见其 docstring。
    """

    model_config = ConfigDict(extra="forbid")

    #: 专家 key（官方角色 key，如 bank/note/kb/stats），必须存在于 `OFFICIAL_ROLES`。
    #: 与 `all` 二选一。
    expert: str = ""
    #: `true` = 一次改**全部**专家开关（面板「全选」）。与 `expert` 二选一。
    all: bool = False
    #: 1 = 关闭，0 = 启用。必填。
    disabled: int


def _agent_experts_payload(user_id: int, disabled_keys: Any) -> Dict[str, Any]:
    """专家清单的**唯一组装处**（`GET` 与 `PUT /ai/agent/experts` 共用）

    只列**可委派的专家**（`renderable_sub_agents`，排除 general —— 那是指挥家自身）。
    每项带：`key` / `name`（中文名）/ `description`（一句话，给用户看）/ `disabled`（0|1）。
    """
    from app.services.ai.agent.roles import renderable_sub_agents

    closed = {str(k) for k in (disabled_keys or set())}
    return {
        "experts": [
            {
                "key": r.key,
                "name": r.name,
                "description": r.description,
                "disabled": 1 if r.key in closed else 0,
            }
            for r in renderable_sub_agents()
        ]
    }


@router.get("/agent/experts")
async def agent_experts(current_user: dict = Depends(get_current_user)):
    """**专家清单**（含当前用户的开关状态）—— 供设置面板渲染「专家」开关

    与 `GET /ai/agent/roles` 的区别：本端点**含用户数据**（每个人的开关不同），故需登录态。
    """
    from app.services.ai.agent import agent_role_pref_service

    uid = int((current_user or {}).get("user_id") or 0)
    closed = await agent_role_pref_service.disabled_role_keys(uid)
    return _agent_experts_payload(uid, closed)


@router.put("/agent/experts")
async def update_agent_expert(
    body: AgentExpertPrefBody,
    current_user: dict = Depends(get_current_user),
):
    """**启用 / 关闭一个专家**（按登录用户保存，只影响他自己）

    - `expert` 与 `all` 必须**正好给一个**（缺了 / 两个都给 → 400）。
    - 关闭某专家 = 指挥家通讯录里不再出现它、显式路由也叫不到（见 `loop.run_agent_stream`）。
    """
    from app.services.ai.agent import agent_role_pref_service
    from app.services.ai.agent.roles import renderable_sub_agents

    uid = int((current_user or {}).get("user_id") or 0)

    has_one = bool(str(body.expert or "").strip())
    if has_one == bool(body.all):
        return error("请恰好指定 expert 或 all 之一", code=400)

    # 合法名单 = 可委派专家（排除 general —— 它是指挥家自身，不该出现在开关里）
    valid = {r.key for r in renderable_sub_agents()}

    try:
        if body.all:
            await agent_role_pref_service.set_all_roles_disabled(
                uid, sorted(valid), body.disabled
            )
        else:
            name = str(body.expert or "").strip()
            if name not in valid:
                # 校验放路由层（合法名单只有 roles 知道），服务层保持纯净
                return error(
                    f"未知专家：{name}；合法专家见 GET /ai/agent/experts",
                    code=400,
                )
            await agent_role_pref_service.set_role_disabled(uid, name, body.disabled)
    except Exception as e:  # noqa: BLE001 - 写失败如实回错，别静默
        logger.exception(f"保存专家开关失败 user={uid}: {e}")
        return error(f"保存失败: {e}")

    closed = await agent_role_pref_service.disabled_role_keys(uid)
    return success(_agent_experts_payload(uid, closed), "已保存")


# ============================================================
# 用户自定义智能体 CRUD（多智能体协同，阶段 2）
# ============================================================
# 用户创建 / 命名 / 保存自己的智能体（人设 + 工具白名单 + 可选模型），复用 AI 工作流。
# ⚠️ 全部按**登录态**归属（`current_user["user_id"]`），不接受请求体里的 userId ——
#    服务层把归属写进 SQL 的 WHERE，杜绝 IDOR（拿别人 id 读写）。


class AgentConfigBody(BaseModel):
    """新建 / 更新用户智能体的请求体

    ⚠️ `extra="forbid"`：字段名写错（如 `persona`、`toolNames`）直接 422，而不是
    被 pydantic 静默丢弃后「返回 200 但什么都没改」（先例见 `AgentToolPrefBody`）。
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""
    greeting: str = ""
    #: 人设提示词（英文，进 SystemMessage）
    personaPrompt: str = ""
    #: 工具白名单；空数组 / 不传 = 不限制（全部工具）。元素必须是合法工具名。
    tools: Optional[List[str]] = None
    #: 可选绑定模型名；空串 = 跟随用户默认模型。
    model: str = ""
    #: 是否启用（阶段 2 新增字段的更新接口才用得上）
    isEnabled: Optional[int] = None


def _validate_agent_tools(tools: Optional[List[str]]) -> Optional[List[str]]:
    """校验工具白名单里的名字都在注册表里；返回归一后的列表（None = 不限制）。

    与 `tool_pref_service.set_tool_disabled` 同一口径：**合法名单只有注册表知道**，
    校验放路由层（服务层不依赖注册表，避免导入顺序踩循环依赖）。
    """
    if tools is None:
        return None
    from app.services.ai.agent.registry import ensure_tools_loaded, registry

    ensure_tools_loaded()
    valid = set(registry.names())
    unknown = [t for t in tools if str(t) not in valid]
    if unknown:
        raise ValueError(f"未知工具名：{', '.join(map(str, unknown))}；合法工具见 GET /ai/agent/tools")
    return [str(t) for t in tools]


@router.get("/agent/configs")
async def list_agent_configs(
    includeDisabled: bool = Query(False, description="是否包含已暂停的智能体"),
    current_user: dict = Depends(get_current_user),
):
    """**列出我的智能体**（只返回当前登录用户的）。"""
    from app.services.ai.agent import agent_config_service

    uid = int((current_user or {}).get("user_id") or 0)
    return {"agents": await agent_config_service.list_agents(uid, include_disabled=includeDisabled)}


@router.post("/agent/configs")
async def create_agent_config(
    body: AgentConfigBody,
    current_user: dict = Depends(get_current_user),
):
    """**新建一个用户智能体**（归属自动取登录用户）。"""
    from app.services.ai.agent import agent_config_service
    from app.services.ai.agent.agent_config_service import AgentConfigError

    uid = int((current_user or {}).get("user_id") or 0)
    try:
        tools = _validate_agent_tools(body.tools)
    except ValueError as e:
        return JSONResponse(status_code=400, content=error(str(e), code=400))
    try:
        info = await agent_config_service.create_agent(
            uid,
            name=body.name,
            persona_prompt=body.personaPrompt,
            description=body.description,
            greeting=body.greeting,
            tools=tools,
            model=body.model,
        )
    except AgentConfigError as e:
        return JSONResponse(status_code=400, content=error(str(e), code=400))
    return success(info, "智能体已创建")


@router.put("/agent/configs/{agent_id}")
async def update_agent_config(
    agent_id: int,
    body: AgentConfigBody,
    current_user: dict = Depends(get_current_user),
):
    """**更新我的某个智能体**（归属写进 SQL，他人 id 一律不可见）。"""
    from app.services.ai.agent import agent_config_service
    from app.services.ai.agent.agent_config_service import AgentConfigError

    uid = int((current_user or {}).get("user_id") or 0)
    try:
        tools = _validate_agent_tools(body.tools)
    except ValueError as e:
        return JSONResponse(status_code=400, content=error(str(e), code=400))
    try:
        info = await agent_config_service.update_agent(
            uid,
            int(agent_id),
            name=body.name or None,
            persona_prompt=body.personaPrompt,
            description=body.description,
            greeting=body.greeting,
            tools=tools,
            model=body.model,
            is_enabled=body.isEnabled,
        )
    except AgentConfigError as e:
        # 服务层对「不存在」与「不属于你」返回同一句，这里统一 404（不区分，防探测）
        return JSONResponse(status_code=404, content=error(str(e), code=404))
    return success(info, "智能体已更新")


@router.delete("/agent/configs/{agent_id}")
async def delete_agent_config(
    agent_id: int,
    current_user: dict = Depends(get_current_user),
):
    """**删除我的某个智能体**（逻辑删除，可恢复；归属写进 SQL）。"""
    from app.services.ai.agent import agent_config_service
    from app.services.ai.agent.agent_config_service import AgentConfigError

    uid = int((current_user or {}).get("user_id") or 0)
    try:
        info = await agent_config_service.delete_agent(uid, int(agent_id))
    except AgentConfigError as e:
        return JSONResponse(status_code=404, content=error(str(e), code=404))
    return success(info, "智能体已删除")


class AgentToolPrefBody(BaseModel):
    """启用 / 屏蔽单个 Agent 工具的请求体（`PUT /ai/agent/tools`）

    ⚠️⚠️ `extra="forbid"` 是**必选项**，不是洁癖：pydantic v2 默认 `extra='ignore'`
    （实测 `pydantic==2.10.4`），前端把字段名写成 `name` / `toolName` / `enable`
    （或后端改了名没同步）时，未知字段会被**静默丢弃** → PUT 照回 200、
    界面照显示「已切换」，而库里一个字节没变。forbid 之后字段名对不上直接 **422**，
    当场暴露。（先例：`api/v1/rag.py` 的 `KnowledgeBaseUpdate`。）
    """

    model_config = ConfigDict(extra="forbid")

    #: 工具名，必须与 `registry.names()` 完全一致（未知名字会被拒绝，不是静默成功）。
    #: 与 `all` **二选一**，必须正好给一个（缺了或两个都给 → 400，见处理器）。
    tool: str = ""
    #: `true` = 一次改**全部**已注册工具（面板上的「全选」）。与 `tool` 二选一。
    all: bool = False
    #: 1 = 屏蔽，0 = 启用。必填 —— 给默认值的话，「前端忘了带上它」会变成
    #: 「悄悄按默认值写库」，那正是 extra='forbid' 想堵住的那类静默失败。
    disabled: int


@router.put("/agent/tools")
async def update_agent_tool(
    body: AgentToolPrefBody,
    current_user: dict = Depends(get_current_user),
):
    """**启用 / 屏蔽一个 Agent 工具**（按登录用户保存，只影响他自己）

    四个刻意的约定，改之前先看完：

    1. **复用 `GET` 的同一个路径**（而不是新开 `/agent/tools/toggle`）：
       本项目 `app/main.py` 最后注册了 `catch_all.router`，**任何没匹配上的路径都会回
       HTTP 200 + `{code:200, msg:'操作成功', data:null}`**。新路径一旦被写错
       （少一个 `s`、多一个连字符），前端看到的是「假成功」而不是 404 ——
       这种坑不值得为路径对称性踩一次。`/agent/tools` 已经注册过了，风险为零。
    2. **未知工具名必须能被前端认出「没保存成功」**：回 `error(..., code=400)`
       （`error()` 的形状没有 `tools` 键，与成功响应对比即可判定），
       而不是回一份清单假装成功。
    3. **响应形状与 `GET` 完全一致**（刷新后的全量清单）：前端一次调用就能重画面板；
       同时也让「路径写错 → catch_all 假 200」当场可辨（假 200 的 body 里没有 `tools`）。
    4. **只写登录用户**：`user_id` 只来自 `current_user`，请求体里没有、也不接受 userId
       （IDOR 红线：开关是用户私有数据，不能靠请求体指定归属）。
    5. **两种目标共用这一个路径**：`{"tool": "x", "disabled": 1}` 改一个；
       `{"all": true, "disabled": 1}` 改全部（面板上的「全选」）。二者**必须恰好给一个**，
       含糊或都不给一律 400 —— 静默猜一个会一次改掉整个面板。
    """
    from app.services.ai.agent import tool_pref_service
    from app.services.ai.agent.loop import ensure_tools_loaded
    from app.services.ai.agent.registry import registry

    ensure_tools_loaded()

    # 归属：只认登录态
    user_id = int((current_user or {}).get("user_id") or 0)

    # 请求必须**恰好**指定一个目标。含糊的请求不许猜 —— 猜错会一次改掉整个面板。
    target = str(body.tool or "").strip()
    if body.all and target:
        return error("请求含糊：`tool` 与 `all` 只能给一个", code=400)
    if not body.all and not target:
        return error("请求缺少目标：给 `tool` 或 `all=true`", code=400)

    if body.all:
        # 「全选」：一次事务改全部（见 `set_all_tools_disabled`）—— 不许半开半关。
        try:
            await tool_pref_service.set_all_tools_disabled(
                user_id, list(registry.names()), body.disabled
            )
        except Exception as e:  # noqa: BLE001 - 写库失败必须让用户知道，不能静默
            logger.exception(f"工具全选保存失败 user={user_id}: {e}")
            return error(f"工具设置保存失败：{e}")
        return await _agent_tools_payload(user_id)

    # 工具名白名单 = 注册表（唯一事实来源）。**不校验就写库**会让垃圾名字进表：
    # 那些行永远匹配不到任何工具，用户却以为「关掉了一个东西」。
    if target not in registry.names():
        return error(f"工具不存在：{target}", code=400)

    try:
        await tool_pref_service.set_tool_disabled(user_id, target, body.disabled)
    except Exception as e:  # noqa: BLE001 - 写库失败必须让用户知道，不能静默
        logger.exception(f"工具开关保存失败 user={user_id} tool={target}: {e}")
        return error(f"工具设置保存失败：{e}")

    return await _agent_tools_payload(user_id)


async def _own_session_history(user_id: int, session_id: str) -> str:
    """取「属于该用户」的会话短期历史（不属于 / 不存在 / 归属不明 → 空串）

    内容**必须**是 `conversation_service.build_context_prompt(user_id, session_id, lang="en")`
    的原样产物 —— 那是 api 链路（`loop.run_agent_stream`）注入到 HumanMessage 的同一份文本。
    两条链路的历史口径只允许有一个来源，这里不重新拼、也不改预算参数。

    归属校验是**红线**：会话历史是私密数据，拿到别人的 sessionId 不能把对方的历史读出来。
    `build_context_prompt` 内部（`get_recent_messages`）已经按 `user_id` 过滤消息，这里再补
    一道显式的会话归属检查，两处各管一段：

      · `user_id <= 0`（登录态里没有有效用户）→ 直接空串。否则消息过滤会退化成
        `user_id == 0`，把库里「归属不明」的历史行读给任意调用方；
      · 会话行属于**别人** → 直接空串。这是防「消息行的 user_id 与会话行不一致」的兜底 ——
        只靠消息过滤时，那种情况下的隔离全押在写入侧，而写入侧的分支不受本接口控制。

    归属为 0 / 会话行不存在时**放行**（交给消息过滤去判），与 `get_agent_timeline` 同口径 ——
    老数据（user_id=0）不该因为这次改动突然丢历史，而那种情况下读到的只会是调用方自己的消息。
    """
    if user_id <= 0 or not session_id:
        return ""

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.ai_chat import AiChatSession

    async with async_session_factory() as db:
        owner = await db.scalar(
            select(AiChatSession.user_id).where(
                AiChatSession.session_id == session_id
            )
        )
    if owner and int(owner) != user_id:
        logger.warning(
            "[agent/context] 会话不属于当前用户，拒绝下发历史 session={} owner={} user={}",
            session_id, owner, user_id,
        )
        return ""

    return await conversation_service.build_context_prompt(
        user_id, session_id, lang="en"
    )


@router.get("/agent/context")
async def agent_runtime_context(
    sessionId: str = Query("", description="会话 ID（可选）：传了就一并下发该会话的短期历史"),
    current_user: dict = Depends(get_current_user),
):
    """**Agent 运行时背景**（长期记忆摘要 + 知识库清单 + 当前会话的短期历史）

    给 ds-free 用的：它的循环跑在**前端**，系统提示词也在前端拼，所以拿不到
    api 付费链路里的 L1 自动注入（那段在 `loop.run_agent_stream` 里）。
    两条链路喂给模型的上下文必须一致，否则同一个问题在免费链路和付费链路
    回答质量不一样 —— 这里把那段文本原样下发，前端拼提示词时追加到末尾。

    `sessionId` 是**可选**的第二个口子，补的是 ds-free 的另一处缺口：它的历史全靠
    DS 网页自己的记忆，而那份记忆**不属于**任何一个 OpenStudy 会话（换会话不切、
    新会话不清）。传了 sessionId 就把该会话的短期历史（`<conversation_history>`）
    一并下发，与 api 链路同源；不传就是空串，老调用方行为一字不变。

    与 `/agent/tools` 一样：内容由后端**单一来源**产出，前端不自己拼。
    取不到时返回空串（前端原样跳过），绝不因此让 Agent 起不来。
    """
    from app.services.ai.agent.runtime_context import build_runtime_context

    user_id = int((current_user or {}).get("user_id") or 0)
    context = await build_runtime_context(user_id, lang="en")

    history = ""
    sid = (sessionId or "").strip()
    if sid:
        # 历史下发是**增强项**：任何一步出错都只少一段历史，绝不能让这次提问失败
        # （前端只判 `typeof history === 'string'`，空串它自己会跳过）。
        try:
            history = await _own_session_history(user_id, sid)
        except Exception as e:  # noqa: BLE001
            logger.warning("[agent/context] 会话历史下发失败 session={}: {}", sid, e)
            history = ""

    return {"context": context, "history": history}


class AgentPreviewRequest(BaseModel):
    """**Agent 工具预演请求**（ds-free 的二次确认卡片用）

    与 `/agent/execute` 同一套参数归一化与 schema 校验，但**只调 `preview()`，绝不执行工具**。
    """

    tool: str
    params: Dict[str, Any] = {}
    userId: Optional[int] = None
    sessionId: str = ""
    #: 写操作是否自动执行。**可选**（默认 True = 与存量调用方完全一致）。
    #:
    #: 为什么新增这个字段：preview 要判断「这次操作是否需要用户确认」才能决定发不发
    #: `confirmTicket`，而判定用的 `needs_user_confirmation` 依赖这个开关
    #: （`autoConfirm=false` 时**所有**写操作都需要确认，不只破坏性动作）。
    #: 客户端必须把**与 execute 相同的值**传进来，否则会出现
    #: 「preview 按 true 判成不需要 → 不发票 / execute 按 false 说要票 → 拒绝」这种死锁。
    #: ⚠️ 默认值是 True 而不是 False：老调用方（不传）的行为一个字不变 ——
    #:    旧行为本就是「只破坏性动作下发预览」，而那正好等于 auto_confirm=True 的判定。
    autoConfirm: bool = True


@router.post("/agent/preview")
async def agent_preview(
    req: AgentPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**Agent 工具预演（只读）**：确认卡片要显示的「到底是哪个东西」

    api 付费链路的确认卡片在后端弹（`run_agent_stream` 的 `tool_confirm` 事件带 `preview`），
    但 ds-free 的循环跑在**前端**、卡片也由前端弹 —— 它只能自己来取这一份，否则两条链路的
    卡片不对等：付费链路说「将删除题库「X」，含 23 道题」，免费链路只显示一句 action 名，
    用户根本不知道自己要删什么。

    四条约定：
      · **只预演**：不执行工具、不写库、不 commit（语义就是「预演」，见 `preview_agent_tool`）
      · 不需要确认的操作 → `{"preview": {}}`；取不到预览也只会是 `{}`，**绝不 500**
        （拿不到预览只是卡片少点信息；让前端因此卡住等于「用户删不掉东西了」）
      · 越权拒绝的形状与 `/agent/execute` **完全一致**：HTTP 403 + `fail()` 信封
        ⚠️ 不能用 `error()` —— 它没有 `success` 字段，前端判 `success !== false` 会把它
        当成**成功**（详见 `/agent/execute` 里的注释）
      · 确实需要确认时多下发一个 `confirmTicket`（v1 契约）：执行时必须把它带回来，
        否则 `fail()` 且不执行（见 `AgentExecuteRequest.confirmTicket`）
    """
    from app.services.ai.agent.loop import preview_agent_tool

    # 越权防护：预演会按 user_id 反查数据（题库名等），**不许以他人身份预演**
    user_id, err = resolve_user_scope(current_user, req.userId)
    if err:
        return JSONResponse(status_code=403, content=fail(err, "只能操作自己的数据"))

    try:
        return await preview_agent_tool(
            db,
            tool_name=req.tool,
            params=req.params or {},
            user_id=user_id,
            session_id=req.sessionId,
            # 与 execute 同一个开关值（客户端必须传同一个）—— 票据发不发由它决定
            auto_confirm=bool(req.autoConfirm),
        )
    except Exception as e:  # noqa: BLE001 - 预览是增强项，任何失败都不许把确认流程卡住
        logger.warning("[agent/preview] 预演失败（不影响确认卡片）: {}", e)
        return {"preview": {}}


class AgentConfirmBody(BaseModel):
    """写操作二次确认的应答（前端点了「确认」/「取消」）"""

    confirmId: str
    approved: bool = False


@router.post("/agent/confirm")
async def agent_confirm(
    body: AgentConfirmBody,
    current_user: dict = Depends(get_current_user),
):
    """唤醒挂起的 Agent 循环（写操作二次确认）

    `/ai/agent/stream` 遇到「需要确认」的写操作（破坏性操作，或用户关掉了自动执行）时，
    会先下发 `tool_confirm` 事件并**挂起**；前端弹卡片，用户点击后调本接口唤醒它继续。
    """
    from app.services.ai.agent.loop import resolve_confirmation

    resolved = resolve_confirmation(body.confirmId, bool(body.approved))
    return success({"resolved": resolved})


@router.post("/assistant/generate-with-images")
async def generate_with_images(
    req: GenerateWithImagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 搭建题库专用：支持图片的流式生成（scene=question-bank）

    与聊天助手走**同一条底层链路**（`chat_engine.stream_turn`），区别只有两点：
      - scene = question-bank（提示词与助手一致，均为 ASSISTANT_SYSTEM_PROMPT）；
      - 不带 sessionId → 一次性生成，**不写聊天历史**。

    历史实现是自己在路由里手写一遍 generator，与助手各写一份多模态逻辑 ——
    这正是「题库搭建单独调一个、OS 助手又单独调一个」的根源，现已合并。
    """
    turn = chat_engine.ChatTurn(
        scene=prompts.SCENE_QUESTION_BANK,
        prompt=req.message,
        images=list(req.images or []),
        provider=req.provider,
        model=req.model,
        thinking=req.thinking,
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


@router.post("/ds-bridge/show")
async def ds_bridge_show(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """调试：打开/显示本机 ds-free-nb 桥的 DS 浏览器窗口（当前登录态）。

    无头模式下会把无头浏览器切成**有头**（复用磁盘 profile，登录态不丢），
    便于用户直接看到卡在哪一步（上传附件 / 等回复）。桥地址取 ds-free-nb
    配置的 base_url（缺省 http://127.0.0.1:9200）。
    """
    import httpx

    # 取 ds-free-nb 的 base_url 作为桥地址（去掉结尾的 /v1）
    base = "http://127.0.0.1:9200"
    try:
        cfg = await db_config.resolve_config(db, None, "ds-free-nb", user_id=current_user.get("id"))
        if cfg and cfg.base_url:
            base = cfg.base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
    except Exception:  # noqa: BLE001 - 取不到就用默认本机地址
        pass

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{base}/bridge/show")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if not data.get("ok"):
                return error(data.get("message") or "打开 DS 浏览器失败")
            return success(data)
    except Exception as e:  # noqa: BLE001 - 桥没起 / 连不上
        logger.warning(f"[ds-bridge] show 失败: {e}")
        return error("DS 桥未运行（请先启动 ds-free-nb 桥）")


async def get_conversation(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取对话历史"""
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    return success(await conversation_service.get_messages(user_id, session_id))


class SaveConversationBody(BaseModel):
    """回填一轮对话（供 ds-free 前端直连链路使用）

    ds-free 的请求由浏览器扩展代发给 chat.deepseek.com，完全不经过后端，
    因此后端没有机会保存历史 —— 刷新页面后会话就是空的。
    历史统一落在 SQL（ai_chat_session / ai_chat_message），**不依赖 Redis**。
    """

    userMessage: str = ""
    assistantMessage: str = ""
    #: **轮次 id（前端每轮生成）**：这一轮对话的归组键 —— 用户点轮末「回退」时，
    #: `POST /ai/conversation/drop-turn` 按 `(user_id, sessionId, turnId)` 把这一轮的
    #: 提问与回复一起逻辑删掉。**同一轮补写两次也要带同一个 id**（先落提问、后补回复）。
    #: ⚠️ 这个字段**必须**在这里显式声明：pydantic 默认忽略未知字段，前端传上来的
    #:    turnId 会被**静默丢掉**，落库的行 `turn_id` 全是空串 → 回退按前端的 `t_...`
    #:    一行都匹配不到（表现为「点了没反应」，且日志里什么都看不到）。
    #:    同类坑见 `AgentStreamRequest.turnId` 的注释。
    turnId: str = ""
    # 附件元信息（JSON 字符串）：[{name, type, thumb}]，thumb 是前端生成的小缩略图
    # （只存缩略图、不存原图，避免把 ai_chat_message 撑大）
    attachments: List[dict] = []


@router.post("/conversation/{session_id}/messages")
async def save_conversation_messages(
    session_id: str,
    body: SaveConversationBody,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """把一轮对话写入会话历史（原子补写，供前端直连链路调用）

    与 /assistant/stream 里的保存逻辑保持一致，但要求「提问 + 回复同事务」。

    两种用法（前端 ds-free 链路会调用两次）：
      1. 发送后立刻：userMessage + attachments（可选带 assistantMessage）
         —— 先保证提问一定落库，刷新后历史不会是空的；
      2. 回复文本确定后：只传 assistantMessage —— 补写 AI 回复。
    两次写入 id 严格递增（前端会串行调用），历史顺序不会错乱。
    """
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)

    try:
        messages = await conversation_service.save_turn(
            user_id,
            session_id,
            user_text=body.userMessage or "",
            assistant_text=body.assistantMessage or "",
            attachments=body.attachments or None,
            turn_id=body.turnId or "",
        )
    except Exception as e:
        # 之前这里是「静默失败」（前端 void 掉、后端 500 也没人看），
        # 于是「历史存不上」完全无线索。这里显式打全栈并回错。
        logger.exception(f"会话历史落库失败 session={session_id}: {e}")
        return error(f"会话历史落库失败: {e}")

    return success(messages)


# ===================== 回退「这一轮对话」（历史里消失） =====================
# 与 `POST /ai/agent/rollback`（撤销这一轮的**写操作**）是**两个动作**，用户点一次
# 轮末的「回退」，前端两个都要调：一个让这一轮从聊天记录里消失（这里），一个把这一轮
# 改过的数据改回去（rollback_service）。两边都按 `(user_id, sessionId, turnId)` 定位，
# 归属**只认登录态**。


class DropTurnBody(BaseModel):
    """把某一轮对话从历史里删掉

    ⚠️ 两个字段都**不是归属凭据**：归属由登录态决定（本请求体**没有** `userId` ——
    不是「收了但忽略」，是压根不收）。`sessionId` 只用来把删除范围缩到某一个会话。

    ⚠️ `sessionId` 是**必填**（两个字段缺一不可，端点各回一句 code=400）：
    「拿不到会话 id 就发空串」在 2026-09-23 造成过线上事故 —— 服务层把空值
    静默返 0，端点回了个 `{"dropped": 0}`，前端当成功，而这一轮一行都没删。
    """

    sessionId: str = ""
    turnId: str = ""


@router.post("/conversation/drop-turn")
async def drop_conversation_turn(
    body: DropTurnBody,
    current_user: dict = Depends(get_current_user),
):
    """**回退这一轮对话**：把这一轮的提问与回复从历史里**逻辑删除**

    响应 `success({"dropped": n, "matched": m})`：

      · `matched` = 这一轮在服务端历史里**到底有几行**（`(登录用户, sessionId,
        turnId)` 命中数，**不看 `del_flag`**）—— 即「这一轮在历史里有没有轮次标记」；
      · `dropped` = 本次真的改掉的（`'0'` → `'2'`）行数（提问 + 回复 = 2 是常态）；
      · 关系恒为 `dropped <= matched`：
          - `matched == 0` = 这一轮在服务端历史里**没有行**（旧数据 `turn_id` 是空串、
            id 传错、会话传错、或那一轮不是你的）；
          - `dropped == 0 且 matched > 0` = **已经删过了**（幂等，**不是失败**）；
          - `matched == dropped > 0` = 本次真的删掉了。

    ⚠️ **只判 `dropped` 会把「没删到」误当成成功** —— 2026-09-23 的线上事故就是
    这样：库里 32 行 `turn_id` 全是空串，每次回退都回 `{"dropped": 0}`，前端把它
    当成功、UI 上这一轮消失了，刷新页面这一轮又回来（服务端**一行都没动**）。
    调用方要在 UI 上区分「已删除 / 没删到」就必须读 `matched`。

    ⚠️ 本仓库有 `catch_all`（未匹配路径也回 HTTP 200 `{code:200, data:null}`），
    所以调用方判的是「`code===200` **且** `data` 里有 `dropped` 这个形状」，
    不是 HTTP 码。

    ⚠️ 这里是**逻辑**删（`ai_chat_message.del_flag='2'`，口径同 `note` /
    `ai_agent_memory`）：行留在库里，只是所有读取路径（会话历史 / 上下文 /
    会话列表计数）都看不见它。物理清理由「删除整个会话」那两个入口负责
    （`delete_session` / `clear_messages`，见 `conversation_service` 的 docstring）。

    ⚠️ 空 `turnId` / 空 `sessionId` **都不许静默返 0**，各回一句 `code=400`：
    空串在这里会变成「匹配所有没有轮次 id 的历史行」的通配符。
    服务层 `drop_turn` 也挡了一层（两层都要有）。
    """
    user_id = int(current_user.get("user_id") or 0)
    turn_id = str(body.turnId or "").strip()
    session_id = str(body.sessionId or "").strip()
    if not session_id:
        # ⚠️ 这一句就是本次事故缺的那一句：前端拿不到会话 id 时发了空串，服务端
        #    一个字没说、还回了个「成功」，前端于是把这一轮从本地 UI 摘掉了。
        return error("缺少会话 id（sessionId），无法回退", code=400)
    if not turn_id:
        return error("缺少轮次 id（turnId），无法回退", code=400)

    try:
        result = await conversation_service.drop_turn(user_id, session_id, turn_id)
    except Exception as e:  # noqa: BLE001 - 落库失败要给前端一句话，不能只 500
        logger.exception(f"回退本轮对话失败 session={session_id} turn={turn_id}: {e}")
        return error(f"回退本轮对话失败: {e}")

    # 只放行契约里的两个字段（服务层多回什么都不给接口漏出来）
    return success({"dropped": int(result["dropped"]), "matched": int(result["matched"])})


class AgentTimelineBody(BaseModel):
    """智能体整条消息流（含工具调用卡片字段）—— 前端刷新后据此复原 UI"""

    messages: List[dict] = []
    #: **会话累计的执行统计**（轮数/步数/耗时），随快照一起存。
    #: 底部状态条（`N 轮 M 步 / LLM x ms`）靠它 —— 否则刷新后统计归零（用户报的 bug）。
    #: 形状与前端 `SessionAgg` 一致：`{rounds, steps, llmMs, toolMs, ftSum, ftSamples}`。
    #: 缺省 `None`（老前端 / 不带此字段）→ 服务层按「无统计」处理。
    metrics: Optional[dict] = None


@router.get("/conversation/{session_id}/agent-timeline")
async def get_agent_timeline_route(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """读取智能体的完整时间线快照（没有则返回空数组 + 无统计，前端退回普通消息行）"""
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    data = await conversation_service.get_agent_timeline(user_id, session_id)
    # data = {"messages": [...], "metrics": {...} | None}（见 conversation_service）
    return success({"messages": data["messages"], "metrics": data.get("metrics")})


@router.put("/conversation/{session_id}/agent-timeline")
async def save_agent_timeline_route(
    session_id: str,
    body: AgentTimelineBody,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """保存智能体的完整时间线快照（一个会话一份，覆盖写）

    与 `/conversation/{sid}/messages`（只存「提问 + 回复」两行）互补：这里存的是
    前端 `useAgentChat` 的**整条消息流**，包含工具调用卡片 —— 刷新后 UI 才能复原，
    否则卡片全丢、只剩纯文本。
    """
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    try:
        await conversation_service.save_agent_timeline(
            user_id, session_id, body.messages, body.metrics
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"智能体时间线落库失败 session={session_id}: {e}")
        return error(f"智能体时间线落库失败: {e}")
    return success({"ok": True})


@router.delete("/conversation/{session_id}")
async def clear_conversation(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """删除某个会话（消息 + 会话列表条目）"""
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    await conversation_service.delete_session(user_id, session_id)
    return success()


# ===================== 会话列表 =====================

@router.get("/sessions")
async def list_sessions(
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的会话列表（按最后更新时间倒序）"""
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    return success(await conversation_service.list_sessions(user_id))


@router.post("/sessions")
async def create_session(
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """新建会话：**只发一个 id，不写库**（会话行由第一条真正的消息建出来）

    ⚠️ 这里以前会立刻 `touch_session(...)` 落一行「新会话」，那是错的：
    智能体页与 OS 助手**点一下「新会话」就写一行**，甚至在没有会话的页面首次挂载时
    也写一行 —— 于是「我明明没聊过」的一大堆**空壳会话**堆进了会话列表，
    而那个列表用户是当成「我的历史」在读的（实测：14 行空壳，13 行属于 uid=105）。
    一行 `message_count=0` + 没有任何消息 + 没有时间线的会话，承载的信息量是**零**。

    改法（在**端点**上改，不按页面加开关）：只生成 id。行由第一次真正写入时懒建 ——
    `conversation_service.save_message` / `save_turn` 里都有 `if row is None: create`，
    且 `save_message` 本来就用首条用户消息当标题。所以：
      · 响应形状一字不变（仍是 `success({"sessionId": ...})`），两个页面都不需要改；
      · 智能体页与 OS 助手行为一致（同一个端点，同一套语义）。

    `userId` 仍在（前端兼容 + 越权拒绝形状不变），但**不再使用它的值** ——
    本接口不写任何数据，归属由后续的落库调用自己校验。
    """
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）。
    # 保留这一步是为了「传别人的 id 依然被拒」这个既有行为不漂 —— 尽管本接口不再写库。
    _user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
    return success({"sessionId": conversation_service.new_session_id()})


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    userId: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """删除会话（消息 + 会话列表条目）"""
    # 越权防护：不允许传别人的 userId 冒充他人读写会话（见 security.resolve_user_scope）
    user_id, err = resolve_user_scope(current_user, userId)
    if err:
        return error(err, code=403)
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
    """清空题库对话上下文（保留为兼容接口，幂等空操作）

    历史实现把「题库对话上下文」放在 Redis 的
    `ai:bank_conversation:{userId}:{bankId}` 里，但后来改成前端拼上下文、
    题目直接落 SQL 之后，**已经没有任何地方写这个 key**，只剩这里在删 ——
    属于纯死代码，而且一旦 Redis 没起来这个接口还会 500。

    现在 AI 相关的持久化（会话 / 消息 / 题目）全走 SQL：这里就不再做任何事了，
    接口签名保持不变，前端 QuestionBuilder 的调用不受影响。
    """
    _ = bank_id
    return success()


@router.post("/question-bank/parse-files-blocks")
async def parse_files_blocks(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """解析上传文件为结构化块"""
    import asyncio

    from app.services.file_parser import parse_file

    results = []
    for file in files:
        content = await file.read()
        try:
            # ⚠️ 丢到线程池：解析是同步的，老版 .doc 还会借 Word COM 转换
            #    （1~3s，最坏 CONVERT_TIMEOUT_SECONDS），别冻住事件循环
            parsed = await asyncio.to_thread(parse_file, file.filename, content)
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
    model: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    deepThink: Optional[bool] = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """题目智能解析（scene=analysis，5 段式结构；一次性生成，不写聊天历史）

    `deepThink` 即 thinking 开关，走 DB 配置的模型（不再硬编码 reasoner）；
    只下发正式回答（content），思考过程不下发，前端用「思考中」动画占位。
    """
    turn = chat_engine.ChatTurn(
        scene=prompts.SCENE_ANALYSIS,
        prompt=question,
        provider=provider,
        model=model,
        thinking=deepThink,
        variables={
            "question": question,
            "question_type": questionType,
            "options": options,
            "correct_answer": correctAnswer,
        },
    )
    return StreamingResponse(chat_engine.stream_turn(db, turn), media_type="text/plain")


# ===================== 长期记忆：最近删除 / 恢复 =====================
# 与 Agent 的 `memory_manage` 工具共用**同一份**服务实现（`services/ai/memory_service.py`
# 的 `list_deleted_memories` / `restore_memory`），这里只是把「看看删了什么」和
# 「点一下恢复」开放给界面 —— 不另写一套查询/更新。
# ⚠️ 两个端点都**只信登录态**：签名里没有 userId（不是「收了但忽略」——是压根不收），
#    所以没有「传别人的 id 冒充他人」这条路（本仓库的 IDOR 红线）。记忆正文是用户数据，
#    跨用户泄漏比「删不掉」严重得多。
# ⚠️ 命名与邻居保持一致：请求体 / 响应体都是**驼峰**（`memoryId` / `memoryType` /
#    `createTime`），与同文件的 `sessionId` / `userId` 同一口径。


@router.get("/memory/deleted")
async def list_deleted_memories(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """「最近删除」：当前登录用户被逻辑删掉的长期记忆（按创建时间倒序）

    与 `memory_manage` 的 `forget` / `clear` 对称 —— 那两个动作现在只打
    `del_flag='2'`，行还在库里，所以这里能把它们列出来并逐条恢复。

    ⚠️ `total` 是**本次返回的条数**（= `len(items)`，与 `memory_search` 工具的 `count`
    同一口径）：为它单开一次 count 查询只会让「列表里 50 条、总数 137」这种不一致有地方藏。
    """
    from app.services.ai import memory_service

    user_id = int(current_user.get("user_id") or 0)
    rows = await memory_service.list_deleted_memories(db, user_id, limit=limit)
    items = [
        {
            "id": r.id,
            "memoryType": r.memory_type,
            "content": r.content,
            "createTime": r.create_time.isoformat(sep=" ") if r.create_time else None,
        }
        for r in rows
    ]
    return success({"items": items, "total": len(items)})


class RestoreMemoryBody(BaseModel):
    """恢复一条已删记忆（「最近删除」列表里点一下恢复）

    ⚠️ 只有 `memoryId` 一个字段：**没有 userId**，归属由登录态决定。
    """

    memoryId: int


@router.post("/memory/restore")
async def restore_memory(
    body: RestoreMemoryBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """把一条被逻辑删除的记忆恢复回来（`del_flag` 写回 `'0'`）

    失败一律回「记忆不存在或不属于你」—— **「不存在」与「不是你的」刻意回同一句**：
    分开说等于给攻击者一个存在性预言机（拿一串 id 试一遍就能数出别人删了多少条记忆）。

    幂等：同一条恢复两次都成功（第二次写进去的值与原值相同，PG 的 `rowcount` 仍算命中）。
    """
    from app.services.ai import memory_service

    user_id = int(current_user.get("user_id") or 0)
    memory_id = int(body.memoryId)
    if not await memory_service.restore_memory(db, user_id, memory_id):
        return error("记忆不存在或不属于你", code=400)
    return success({"restored": True, "memoryId": memory_id})


# ===================== Agent：回退「这一轮」的写操作 =====================
# 与 `services/ai/agent/rollback_service.py` 是**同一份实现的两个入口**：账本
# （`ai_agent_op_log`）由 `loop._execute_tool` 在每次成功的写操作后写一行 —— 那是两条
# 链路（api 主循环 / ds-free 单步执行）唯一的工具收口，挂一处两边都覆盖。这里只把
# 「用户点回退」这个动作开放出来，不另写一套撤销逻辑。
#
# ⚠️ 归属只认登录态：请求体里**没有 userId**（不是「收了但忽略」—— 是压根不收）。
#    账本查询与逆操作都用服务端认定的 user_id 执行（本仓库的 IDOR 红线）。
# ⚠️ 「只回退最近一轮」是**前端的交互口径**（回退组件挂在那一轮末尾）；服务端不限制轮次，
#    给了哪个 turnId 就撤哪一轮，重复点击由账本的 `undone_at` 保证幂等。


class RollbackTurnBody(BaseModel):
    """回退某一轮的全部写操作

    ⚠️ 两个字段都**不是归属凭据**：归属由登录态决定。`sessionId` 只用来把账本行缩到
    某一个会话（同一个 turnId 在不同会话里互不影响）。
    """

    sessionId: str = ""
    turnId: str = ""


@router.post("/agent/rollback")
async def rollback_agent_turn(
    body: RollbackTurnBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**回退这一轮**：把某个 (会话, 轮次) 的成功写操作按**倒序**逐条撤销

    响应 `success({reverted, skipped, failed, partial})`：

      · `reverted` 成功撤销的条数；
      · `skipped`  这一轮里**撤不了**的操作（工具没声明撤销动作，例如题库/题目那条物理删线）
                   —— 每条带 `reasonText`，界面照它列「这些回不去」；
      · `failed`   撤销动作本身失败（可以重试）；
      · `partial`  撤了但只补回一部分（如知识库：库行回来了，文档分块已被物理删）。

    ⚠️ `reverted=0` 且三个清单都空 = 这一轮没有可撤销的写操作（或已经撤过 —— 幂等），
    **不是失败**。本仓库有 `catch_all`（未匹配路径也回 HTTP 200 `{code:200,data:null}`），
    所以调用方判的是「`code===200` **且** `data` 里有 `reverted` 这个形状」，不是 HTTP 码。

    ⚠️ 不在函数内 `commit`：`get_db` 在请求结束时统一提交/回滚（与同文件的
    `/memory/restore` 同一口径）。`rollback_turn` 内部对每条逆操作包 SAVEPOINT，
    一条失败不拖垮其余（见其 docstring）。
    """
    from app.services.ai.agent import rollback_service

    user_id = int(current_user.get("user_id") or 0)
    turn_id = str(body.turnId or "").strip()
    if not turn_id:
        # 空 turnId 绝不当通配符（服务层也挡了一层，这里给出能看懂的文案）
        return error("缺少轮次 id（turnId），无法回退", code=400)

    outcome = await rollback_service.rollback_turn(
        db, user_id, str(body.sessionId or ""), turn_id
    )
    return success(outcome)
