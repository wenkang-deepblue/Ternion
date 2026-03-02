from __future__ import annotations

import json

from ternion.server import routes as server_routes
from ternion.utils.tool_policy import EXECUTION_ALLOWED_TOOL_CANONICAL


def test_execution_allowed_tool_canonical_includes_strreplace() -> None:
    assert "strreplace" in EXECUTION_ALLOWED_TOOL_CANONICAL


def test_extract_mutation_target_path_supports_strreplace() -> None:
    args = json.dumps({"path": "docs/example.md", "old_str": "a", "new_str": "b"})
    assert server_routes._extract_mutation_target_path("StrReplace", args) == "docs/example.md"
