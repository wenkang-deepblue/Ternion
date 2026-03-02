from ternion.router.prompts import EXECUTION_PROMPT, OPTIMIZER_PROMPT


def test_execution_prompt_avoids_legacy_tool_alias_examples() -> None:
    assert "run_terminal_cmd" not in EXECUTION_PROMPT
    assert "search_replace" not in EXECUTION_PROMPT
    assert "delete_file" not in EXECUTION_PROMPT
    assert "edit_notebook" not in EXECUTION_PROMPT
    assert "Tool names MUST exactly match the provided tools list" in EXECUTION_PROMPT
    assert "Use `EditNotebook` ONLY when the target is a `.ipynb` notebook" in EXECUTION_PROMPT
    assert "Prefer `StrReplace` for small focused edits" in EXECUTION_PROMPT


def test_optimizer_prompt_mentions_tool_list_name_strictness() -> None:
    assert "Tool names MUST exactly match the provided tools list" in OPTIMIZER_PROMPT
    assert "Use `EditNotebook` ONLY for `.ipynb` notebooks" in OPTIMIZER_PROMPT
