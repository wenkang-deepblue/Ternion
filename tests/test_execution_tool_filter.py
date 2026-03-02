"""
Tests for Execution/Optimizer tool filtering.
"""

from ternion.workflow.nodes import _filter_execution_cursor_tools


def test_execution_tool_filter_removes_read_tools() -> None:
    tools = [
        {"type": "function", "function": {"name": "Read"}},
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "Grep"}},
        {"type": "function", "function": {"name": "grep"}},
        {"type": "function", "function": {"name": "Write"}},
        {"type": "function", "function": {"name": "ApplyPatch"}},
        {"type": "function", "function": {"name": "run_terminal_cmd"}},
    ]
    filtered = _filter_execution_cursor_tools(tools)
    names = [tool.get("function", {}).get("name") for tool in filtered if isinstance(tool, dict)]
    assert "Read" not in names
    assert "read_file" not in names
    assert "Grep" not in names
    assert "grep" not in names
    assert "Write" in names
    assert "ApplyPatch" in names
    assert "run_terminal_cmd" in names
