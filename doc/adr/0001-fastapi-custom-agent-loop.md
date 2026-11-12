# ADR 0001: FastAPI + 自研 Agent Loop

- 状态：accepted
- 日期：2026-11-12（整理既有决策）
- 决策者：OpenStudy 技术负责人

## 背景

系统需要 SSE 流式输出、工具调用、确认、回滚、记忆和 Python AI 生态；早期脚手架来自 RuoYi/Spring Boot 形态，但实际 AI 主链路已经用 Python。

## 决策

后端采用 FastAPI；Agent 采用自研 `app/services/ai/agent/loop.py` 循环，不引入 LangGraph。

## 备选

- Spring Boot + Java AI 框架：SSE/Python 生态和模型接入成本高。
- LangGraph：抽象完整，但 token/路由/执行路径可控性不如自研，且引入额外依赖。

## 后果

- 正面：流式、工具、确认、回滚、记忆可在同一循环里控制；无额外编排框架。
- 负面：`loop.py` 体积大、维护成本高，需要拆分和契约测试；不能把“自研”说成无成本优势。

## 验证

- 29 个 Agent 工具、确认卡、回滚、memory 链路有 `tests/test_agent_tool_contract.py` 等测试；
- 具体工具矩阵见 `doc/feature-map.md`。
