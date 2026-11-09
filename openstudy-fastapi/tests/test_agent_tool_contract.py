"""Contract checks for the registered Agent tools and role whitelists."""

from __future__ import annotations

import app.services.ai.agent.tools  # noqa: F401 - populate registry
from app.services.ai.agent.registry import registry
from app.services.ai.agent.roles import GLOBAL_TOOLS, OFFICIAL_ROLES


def test_registry_has_expected_tools_and_metadata():
    names = set(registry.names())
    assert len(names) >= 28
    for tool in registry.all():
        assert tool.name, f"{type(tool).__name__} missing name"
        assert tool.description.strip(), f"{tool.name} missing model-facing description"
        assert isinstance(tool.parameters, dict), f"{tool.name} parameters must be dict"
        assert tool.parameters.get("type") == "object", f"{tool.name} parameters must be object schema"
        assert tool.label.strip(), f"{tool.name} missing UI label"
        assert tool.description_zh.strip(), f"{tool.name} missing UI description_zh"


def test_artifact_tools_declare_write_operation():
    artifact_tools = {
        "document_compose",
        "document_compare",
        "micro_course_generate",
        "review_sheet",
        "study_plan",
    }
    for name in artifact_tools:
        tool = registry.get(name)
        assert tool is not None, f"missing tool {name}"
        assert tool.write_operation is True, f"{name} should declare write_operation=True"


def test_role_whitelists_only_reference_registered_tools():
    names = set(registry.names())
    for role_key, role in OFFICIAL_ROLES.items():
        for tool_name in role.tools:
            assert tool_name in names, f"{role_key} references unknown tool {tool_name}"
    for tool_name in GLOBAL_TOOLS:
        assert tool_name in names, f"GLOBAL_TOOLS references unknown tool {tool_name}"
