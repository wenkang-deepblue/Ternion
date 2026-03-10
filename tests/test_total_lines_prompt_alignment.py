"""
Tests for total lines metadata prompt alignment.
"""

from ternion.router.prompts import EXECUTION_PROMPT, OPTIMIZER_PROMPT


def test_execution_prompt_mentions_total_lines_metadata() -> None:
    assert "total_lines" in EXECUTION_PROMPT


def test_optimizer_prompt_mentions_total_lines_metadata() -> None:
    assert "total_lines" in OPTIMIZER_PROMPT
