"""
Tests for shell policy enforcement.
"""

from ternion.utils.shell_policy import evaluate_shell_command


def test_shell_policy_allows_pytest() -> None:
    result = evaluate_shell_command("python3 -m pytest -q")
    assert result.allowed


def test_shell_policy_allows_pwd() -> None:
    result = evaluate_shell_command("pwd")
    assert result.allowed


def test_shell_policy_allows_version_checks() -> None:
    assert evaluate_shell_command("python --version").allowed
    assert evaluate_shell_command("node -v").allowed
    assert evaluate_shell_command("npm -v").allowed


def test_shell_policy_blocks_pwd_and_ls_chain() -> None:
    result = evaluate_shell_command("pwd && ls")
    assert not result.allowed


def test_shell_policy_allows_cd_into_repo_subdir_and_npm_typecheck_silent() -> None:
    result = evaluate_shell_command("cd web && npm run -s typecheck")
    assert result.allowed


def test_shell_policy_allows_npm_prefix_dir_typecheck() -> None:
    result = evaluate_shell_command("npm --prefix web run typecheck")
    assert result.allowed


def test_shell_policy_allows_npm_prefix_equals_dir_typecheck() -> None:
    result = evaluate_shell_command("npm --prefix=web run typecheck")
    assert result.allowed


def test_shell_policy_blocks_npm_prefix_equals_parent_traversal() -> None:
    result = evaluate_shell_command("npm --prefix=.. run typecheck")
    assert not result.allowed


def test_shell_policy_allows_pnpm_c_dir_typecheck() -> None:
    result = evaluate_shell_command("pnpm -C web run typecheck")
    assert result.allowed


def test_shell_policy_allows_pnpm_inline_c_dir_typecheck() -> None:
    result = evaluate_shell_command("pnpm -Cweb run typecheck")
    assert result.allowed


def test_shell_policy_blocks_pnpm_inline_c_parent_traversal() -> None:
    result = evaluate_shell_command("pnpm -C.. run typecheck")
    assert not result.allowed


def test_shell_policy_allows_yarn_c_dir_typecheck() -> None:
    result = evaluate_shell_command("yarn -C web typecheck")
    assert result.allowed


def test_shell_policy_allows_yarn_cwd_equals_dir_typecheck() -> None:
    result = evaluate_shell_command("yarn --cwd=web typecheck")
    assert result.allowed


def test_shell_policy_blocks_yarn_cwd_equals_parent_traversal() -> None:
    result = evaluate_shell_command("yarn --cwd=.. typecheck")
    assert not result.allowed


def test_shell_policy_blocks_cd_parent_traversal() -> None:
    result = evaluate_shell_command("cd .. && npm run typecheck")
    assert not result.allowed


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


def test_shell_policy_blocks_npm_install() -> None:
    result = evaluate_shell_command("npm install")
    assert not result.allowed
