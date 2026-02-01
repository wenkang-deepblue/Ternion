"""
Tests for shell policy enforcement.
"""

from ternion.utils.shell_policy import evaluate_shell_command


def test_shell_policy_allows_pytest() -> None:
    result = evaluate_shell_command("python3 -m pytest -q")
    assert result.allowed


def test_shell_policy_allows_multiple_verification_commands() -> None:
    result = evaluate_shell_command("pytest -q && ruff .")
    assert result.allowed


def test_shell_policy_allows_logical_or() -> None:
    result = evaluate_shell_command("pytest -q || pytest -q")
    assert result.allowed


def test_shell_policy_blocks_read_command() -> None:
    result = evaluate_shell_command("cat README.md")
    assert not result.allowed


def test_shell_policy_blocks_non_verification_command() -> None:
    result = evaluate_shell_command("echo hello")
    assert not result.allowed


def test_shell_policy_blocks_pipes() -> None:
    result = evaluate_shell_command("pytest -q | tee out.txt")
    assert not result.allowed


def test_shell_policy_blocks_command_substitution() -> None:
    result = evaluate_shell_command("pytest -q $(cat README.md)")
    assert not result.allowed


def test_shell_policy_blocks_backticks() -> None:
    result = evaluate_shell_command("pytest -q `cat README.md`")
    assert not result.allowed


def test_shell_policy_allows_dollar_brace_variable() -> None:
    result = evaluate_shell_command("pytest -q ${HOME}")
    assert result.allowed


def test_shell_policy_allows_file_meta_tool() -> None:
    result = evaluate_shell_command("python -m ternion.utils.file_meta docs/advanced_feature_plan.md")
    assert result.allowed
