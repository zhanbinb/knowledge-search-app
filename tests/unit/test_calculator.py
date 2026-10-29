import pytest

from app.tools.builtin import calculate


def test_calculator_supports_safe_expression():
    assert calculate("(12 + 8) * 3")["result"] == 60


def test_calculator_rejects_unsafe_expression():
    with pytest.raises(ValueError):
        calculate("__import__('os').system('ls')")


async def test_tool_registry_filters_unsupported_arguments():
    from app.config import Settings
    from app.tools.registry import ToolRegistry

    registry = ToolRegistry(Settings(mcp_enabled=False))
    result = await registry.call(
        "lookup_policy",
        {"topic": "差旅", "question": "额外参数应被过滤", "city": "深圳"},
    )

    assert result["status"] == "succeeded"
    assert result["arguments"] == {"topic": "差旅"}
