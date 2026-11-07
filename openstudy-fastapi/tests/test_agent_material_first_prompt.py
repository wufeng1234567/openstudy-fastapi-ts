"""Prompt regression: knowledge questions should check user materials first."""
from app.services.ai import prompts
from app.services.ai.agent.tools.knowledge_search import KnowledgeSearchTool


def test_agent_prompt_contains_material_first_rule():
    prompt = prompts.build_agent_system_prompt(include_tools=False)
    assert "Material-First Rule" in prompt
    assert "before composing from" in prompt
    assert "什么是梯度下降" in prompt
    assert "knowledge_search" in prompt


def test_knowledge_search_description_is_material_first():
    description = KnowledgeSearchTool.description
    assert "Use this FIRST" in description
    assert "substantive knowledge" in description
    assert "general knowledge" in description
