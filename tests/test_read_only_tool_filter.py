"""
Tests for read-only tool filter in evidence phases.
"""

from ternion.workflow.nodes import _filter_read_only_cursor_tools


def test_read_only_filter_accepts_snake_case_names() -> None:
    tools = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "grep"}},
        {"type": "function", "function": {"name": "codebase_search"}},
        {"type": "function", "function": {"name": "Write"}},
    ]
    filtered = _filter_read_only_cursor_tools(tools)
    names = [tool.get("function", {}).get("name") for tool in filtered if isinstance(tool, dict)]
    assert "read_file" in names
    assert "grep" in names
    assert "codebase_search" in names
    assert "Write" not in names
