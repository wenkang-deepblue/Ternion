from ternion.router.prompts import EXECUTION_PROMPT, OPTIMIZER_PROMPT


def test_execution_prompt_mentions_scoped_ruff_verification() -> None:
    assert "Ruff Verification Scope (MANDATORY)" in EXECUTION_PROMPT
    assert "do NOT run `ruff ... .` by default" in EXECUTION_PROMPT


def test_optimizer_prompt_mentions_scoped_ruff_verification() -> None:
    assert "Ruff Verification Scope (MANDATORY)" in OPTIMIZER_PROMPT
    assert "do NOT run `ruff ... .` by default" in OPTIMIZER_PROMPT
