"""
Node implementations for the Ternion LangGraph workflow.

Each node represents a step in the 4-step discussion flow.
"""

import ast
import asyncio
import contextlib
import hashlib
import json
import re
import shlex
import time
from pathlib import Path
from typing import Any

import structlog

from ternion.core.budget import budget_manager
from ternion.core.config import settings
from ternion.core.config_store import config_store
from ternion.core.deliverable_policy import (
    format_deliverable_policy_for_prompt,
    resolve_deliverable_policy,
)
from ternion.core.exceptions import (
    RuntimeModelUnavailableError,
)
from ternion.core.exceptions import (
    TernionTimeoutError as TernionTimeout,
)
from ternion.core.intent_classifier import get_latest_user_message
from ternion.core.model_catalog import model_catalog_service
from ternion.core.model_probe import classify_runtime_model_unavailable
from ternion.core.models import ChatMessage, MessageRole
from ternion.core.session_store import (
    ExecutionMode,
    session_store,
)
from ternion.providers.base import ProviderResponse
from ternion.providers.manager import provider_manager
from ternion.router.prompts import (
    ARBITER_EVIDENCE_PROMPT,
    ARBITER_REPORT_EVIDENCE_PROMPT,
    DIVERGENCE_PROMPT,
    EXECUTION_PROMPT,
    GLOBAL_SECURITY_RULES,
    build_convergence_prompt,
    build_optimizer_prompt,
)
from ternion.utils.cursor_safety import sanitize_for_cursor_display, sanitize_for_preview
from ternion.utils.evidence_chain import (
    canonicalize_evidence_requests_text,
    compute_missing_ranges,
    is_deterministic_range_request,
    merge_adjacent_or_overlapping_ranges,
    merge_missing_purpose_gaps,
    parse_evidence_bundle,
    parse_evidence_requests,
    reconcile_evidence_chain,
)
from ternion.utils.evidence_requests_protocol import (
    EVIDENCE_REQUESTS_BEGIN,
    extract_evidence_requests_block,
)
from ternion.utils.i18n import MessageKey, t
from ternion.utils.language_resources import (
    get_language_name,
    get_optimizer_language_instruction_template,
    get_report_language_instruction_template,
)
from ternion.utils.log_manager import log_manager
from ternion.utils.report_parser import format_report_for_display, parse_structured_report
from ternion.utils.secrets import redact_secrets
from ternion.utils.shell_policy import evaluate_shell_command
from ternion.utils.tool_calls_parser import (
    TOOL_CALLS_BEGIN,
    build_text_tool_calls_instruction,
    decode_stream_tool_calls,
    extract_tool_calls_from_text,
)
from ternion.utils.tool_policy import EXECUTION_ALLOWED_TOOL_CANONICAL, SHELL_TOOL_CANONICAL
from ternion.utils.workspace_paths import normalize_workspace_target_path, render_workspace_path
from ternion.workflow.state import TernionState, WorkflowPhase
from ternion.workflow.streaming_events import StreamEventQueue

logger = structlog.get_logger(__name__)

# Optimizer output wrapper markers (development override).
_OPTIMIZER_INTERNAL_BEGIN = "TERNION_OPTIMIZER_INTERNAL_REPORT_BEGIN"
_OPTIMIZER_INTERNAL_END = "TERNION_OPTIMIZER_INTERNAL_REPORT_END"
_OPTIMIZER_USER_BEGIN = "TERNION_OPTIMIZER_USER_SUMMARY_BEGIN"
_OPTIMIZER_USER_END = "TERNION_OPTIMIZER_USER_SUMMARY_END"
_OPTIMIZER_ACTION_REQUIRED_PREFIX = "ACTION_REQUIRED:"
_OPTIMIZER_ACTION_TAKEN_PREFIX = "ACTION_TAKEN:"
_OPTIMIZER_ACTION_REASON_PREFIX = "ACTION_REASON:"
_OPTIMIZER_REQUIRED_CHANGE_ITEMS_PREFIX = "REQUIRED_CHANGE_ITEMS:"
_OPTIMIZER_ACTION_FIELD_LINE_RE = re.compile(r"^[A-Z][A-Z0-9_]+:")
_OPTIMIZER_ACTION_TAKEN_VALUES = {"none", "tool_calls", "evidence_topup"}


def _build_runtime_model_unavailable_message(
    error: RuntimeModelUnavailableError,
) -> str:
    """Build a localized user-facing message for runtime stale-model failures."""
    return t(
        MessageKey.RUNTIME_MODEL_UNAVAILABLE,
        provider=error.provider,
        model=error.model,
    )


_ROLE_DISPLAY_NAMES = {
    "ternion_a": "Ternion A",
    "ternion_b": "Ternion B",
    "ternion_c": "Ternion C",
    "arbiter": "Arbiter",
    "writer": "Writer",
    "reviewer": "Reviewer",
    "optimizer": "Optimizer",
}


def _extract_report_scope_for_policy(report: str) -> str:
    """
    Extract Scope/Non-Goals content for deliverable classification.
    """
    parsed = parse_structured_report(report or "")
    if parsed.is_structured and parsed.scope.strip():
        return parsed.scope
    return report or ""


# Default timeout for provider calls
DEFAULT_TIMEOUT_SECONDS = settings.discussion.timeout_seconds
WRITER_TIMEOUT_SECONDS = max(DEFAULT_TIMEOUT_SECONDS, settings.discussion.writer_timeout_seconds)

_MAX_EVIDENCE_TOPUP_ROUNDS = 2


def _coerce_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_tool_name_and_arguments(tool_call: dict[str, Any]) -> tuple[str | None, str]:
    """
    Extract tool name + arguments payload (as JSON string) from a normalized tool call dict.
    """
    if not isinstance(tool_call, dict):
        return None, "{}"
    fn = tool_call.get("function")
    if isinstance(fn, dict):
        name = fn.get("name")
        arguments = fn.get("arguments")
    else:
        name = tool_call.get("name")
        arguments = tool_call.get("arguments")

    if not isinstance(name, str) or not name.strip():
        return None, "{}"

    if arguments is None:
        return name, "{}"
    if isinstance(arguments, str):
        return name, arguments
    try:
        return name, json.dumps(arguments, ensure_ascii=False)
    except Exception:
        return name, "{}"


def _extract_shell_command_from_arguments(arguments_json: str) -> str | None:
    args = _coerce_json_object(arguments_json)
    for key in ("command", "cmd", "commands"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            parts = [v for v in value if isinstance(v, str) and v.strip()]
            if parts:
                return " && ".join(parts)
    return None


def _detect_blocked_execution_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Detect tool calls that would be blocked by the Execution/Optimizer tool policy.

    Returns:
      (blocked_tools, blocked_shell)
      - blocked_tools: list of tool names that are not allowed in execution/optimizer
      - blocked_shell: list of dicts: {"tool": <tool_name>, "command": <cmd>, "reason": <why>}
    """
    blocked_tools: list[str] = []
    blocked_shell: list[dict[str, str]] = []

    for tc in tool_calls or []:
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if not canonical or canonical not in EXECUTION_ALLOWED_TOOL_CANONICAL:
            blocked_tools.append(name or "(unknown)")
            continue

        if canonical in SHELL_TOOL_CANONICAL:
            command = _extract_shell_command_from_arguments(args_str) or ""
            decision = evaluate_shell_command(command)
            if not decision.allowed:
                preview = command.strip().replace("\n", " ")
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                blocked_shell.append(
                    {
                        "tool": name or "Shell",
                        "command": preview or "(empty)",
                        "reason": decision.reason,
                    }
                )

    return blocked_tools, blocked_shell


def _detect_malformed_execution_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """
    Detect malformed tool calls that are likely to be rejected by Cursor tool
    schemas or server-side policies.

    This currently focuses on EditNotebook, which requires `target_notebook`
    and is intended for `.ipynb` targets only.
    """
    issues: list[dict[str, str]] = []
    for tc in tool_calls or []:
        name, args_str = _extract_tool_name_and_arguments(tc)
        canonical = re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())
        if canonical != "editnotebook":
            continue

        args = _coerce_json_object(args_str)
        target = args.get("target_notebook")
        if not isinstance(target, str) or not target.strip():
            issues.append(
                {
                    "tool": name or "EditNotebook",
                    "reason": "Missing required argument: target_notebook",
                }
            )
            continue

        if not target.strip().lower().endswith(".ipynb"):
            issues.append(
                {
                    "tool": name or "EditNotebook",
                    "reason": (
                        "EditNotebook is only allowed for `.ipynb` targets "
                        "(use StrReplace/Write for text files)"
                    ),
                }
            )

    return issues


def _normalize_tool_target_path(
    path_str: str,
    workspace_root: str | None = None,
    workspace_path_style: str | None = None,
) -> str | None:
    """Normalize a tool target path against the declared workspace boundary."""
    return normalize_workspace_target_path(
        path_str,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
    )


def _extract_mutation_target_path_for_guardrail(
    tool_name: str | None,
    arguments_json: str,
) -> str | None:
    canonical = re.sub(r"[^a-z0-9]+", "", (tool_name or "").strip().lower())
    args = _coerce_json_object(arguments_json)
    if canonical not in {"write", "writefile"}:
        return None
    for key in ("file_path", "path", "target_file", "target_path"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _collect_stabilized_document_write_paths(
    tool_calls: list[dict[str, Any]] | None,
    *,
    stabilized_document_paths: list[str] | None,
    workspace_root: str | None,
    workspace_path_style: str | None,
) -> list[str]:
    """Collect whole-file Write targets that point to stabilized documents."""
    stabilized_set = {
        str(path).strip()
        for path in (stabilized_document_paths or [])
        if isinstance(path, str) and path.strip()
    }
    if not stabilized_set:
        return []

    blocked: list[str] = []
    seen: set[str] = set()
    for tc in tool_calls or []:
        name, args_str = _extract_tool_name_and_arguments(tc)
        target = _extract_mutation_target_path_for_guardrail(name, args_str)
        normalized = _normalize_tool_target_path(
            target or "",
            workspace_root,
            workspace_path_style,
        )
        if not normalized or normalized not in stabilized_set or normalized in seen:
            continue
        seen.add(normalized)
        blocked.append(normalized)
    return blocked


def _render_stabilized_document_path(
    path_str: str,
    workspace_root: str | None,
    workspace_path_style: str | None,
) -> str:
    """Render a stabilized document path relative to the workspace when possible."""
    return render_workspace_path(
        path_str,
        workspace_root=str(workspace_root or ""),
        workspace_path_style=str(workspace_path_style or ""),
    )


def _build_stabilized_document_guardrail_feedback(
    *,
    blocked_paths: list[str],
    deliverable_type: str,
    workspace_root: str | None,
    workspace_path_style: str | None,
) -> str:
    rendered_paths = "\n".join(
        f"- {_render_stabilized_document_path(path, workspace_root, workspace_path_style)}"
        for path in blocked_paths
    )
    deliverable_label = deliverable_type or "unknown"
    return (
        "The following document outputs are already stabilized after a successful whole-file "
        "Write and MUST NOT be rewritten again in execution:\n"
        f"{rendered_paths}\n\n"
        f"Current deliverable type: `{deliverable_label}`.\n"
        "Hard rules:\n"
        "- Do NOT issue another whole-file `Write` for any stabilized document above.\n"
        "- Keep those document outputs unchanged.\n"
        "- If additional code work is still required, continue only with code/tool actions for "
        "non-document targets.\n"
        "- If the stabilized documents are complete and no more tool work is needed, finish so "
        "the workflow can continue to Optimizer.\n"
    )


def _build_tool_call_validation_guardrail_feedback(
    *,
    issues: list[dict[str, str]],
    role_label: str,
) -> str:
    issue_lines: list[str] = []
    for item in issues or []:
        tool_name = item.get("tool", "(unknown)")
        reason = item.get("reason", "")
        issue_lines.append(f"- {tool_name}: {reason}")
    issues_text = "\n".join(issue_lines) if issue_lines else "- (none)"

    return (
        f"Your previous tool calls were INVALID for {role_label} and cannot be executed safely.\n\n"
        "Issues:\n"
        f"{issues_text}\n\n"
        "Hard rules (MANDATORY):\n"
        "- For `EditNotebook`, you MUST include `target_notebook` and it MUST point to a `.ipynb` file.\n"
        "- For non-notebook files, NEVER use `EditNotebook`. Prefer `StrReplace` for small edits or "
        "`Write`/`ApplyPatch` for larger changes.\n"
        "- Now: resend ONLY corrected tool_calls with EMPTY assistant content.\n"
    )


def _format_shell_allowlist_summary_for_model() -> str:
    # Keep this short: categories only (avoid dumping regex patterns).
    return (
        "- Tests: `pytest ...`, `python -m pytest ...`\n"
        "- Lint/Format/Typecheck/Build: `ruff ...`, `black ...`, `npm|pnpm|yarn (run) lint|test|format|typecheck|check|build ...`, `make lint|test|format|check|build ...`\n"
        "- Working dir: `cd <repo_subdir> && <allowed command>` or `npm --prefix <repo_subdir> ...` / `pnpm|yarn -C <repo_subdir> ...`\n"
        "- File metadata: `python -m ternion.utils.file_meta <repo_path>`\n"
        "- Sanity: `pwd`, `python --version` / `python -V`, `node --version` / `node -v`, `npm|pnpm|yarn --version` / `-v`"
    )


def _build_scoped_ruff_verification_commands(modified_files: list[str] | None) -> list[str]:
    """
    Build Ruff verification commands scoped to modified Python files.
    """
    py_files: list[str] = []
    seen: set[str] = set()
    for path in modified_files or []:
        if not isinstance(path, str):
            continue
        cleaned = path.strip()
        if not cleaned.endswith(".py"):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        py_files.append(cleaned)

    if not py_files:
        return []

    args = " ".join(shlex.quote(p) for p in py_files)
    return [
        f"python3 -m ruff check {args}",
        f"python3 -m ruff format --check {args}",
    ]


def _build_tool_policy_guardrail_feedback(
    *,
    blocked_tools: list[str],
    blocked_shell: list[dict[str, str]],
    role_label: str,
) -> str:
    blocked_lines: list[str] = []
    for tool in blocked_tools:
        blocked_lines.append(f"- Tool not allowed in {role_label}: {tool}")
    for item in blocked_shell:
        tool_name = item.get("tool", "Shell")
        cmd = item.get("command", "")
        reason = item.get("reason", "")
        blocked_lines.append(f"- {tool_name} -> {cmd} (reason: {reason})")
    blocked_text = "\n".join(blocked_lines) if blocked_lines else "- (none)"

    return (
        "Your previous tool calls were BLOCKED by the host tool policy.\n\n"
        "Blocked items:\n"
        f"{blocked_text}\n\n"
        "Allowed Shell commands (verification-only summary):\n"
        f"{_format_shell_allowlist_summary_for_model()}\n\n"
        "Hard rules (MANDATORY):\n"
        "- Do NOT attempt any other Shell commands (especially any that read/search file contents or modify the workspace/git).\n"
        "- If you need to read/search/list directories/view file contents, you MUST request evidence top-up by outputting ONLY the "
        f"`{EVIDENCE_REQUESTS_BEGIN}`...`TERNION_EVIDENCE_REQUESTS_END` block and STOP.\n"
        "- You may use `python -m ternion.utils.file_meta <path>` for repo-internal file metadata checks only.\n"
        "- Now: replace the blocked tool calls with a compliant alternative plan.\n"
    )


def _validate_evidence_topup_request(*, used_round: int, final_request: bool) -> str | None:
    """
    Validate execution-time evidence top-up guardrails.

    Guardrails (Step E):
    - Max 2 top-up rounds across Writer + Optimizer.
    - The 2nd request must be explicitly marked as the final request.
    """
    used = int(used_round or 0)
    if used >= _MAX_EVIDENCE_TOPUP_ROUNDS:
        return t(
            MessageKey.EVIDENCE_TOPUP_LIMIT_REACHED,
            max_rounds=str(_MAX_EVIDENCE_TOPUP_ROUNDS),
        )

    if used == _MAX_EVIDENCE_TOPUP_ROUNDS - 1 and not final_request:
        return t(MessageKey.EVIDENCE_TOPUP_FINAL_REQUIRED)

    return None


def _validate_evidence_requests_payload(requests_text: str) -> str | None:
    """
    Validate evidence_requests payload format for execution-time top-ups.

    Requirements (Step E):
    - Must contain at least one actionable request.
    - Each request must include a PURPOSE line (stored as metadata, not excerpt).
    """
    entries = parse_evidence_requests(requests_text or "")
    if not entries:
        return t(MessageKey.EVIDENCE_TOPUP_REQUESTS_EMPTY)

    missing_purpose = [e.request for e in entries if not (e.purpose or "").strip()]
    if not missing_purpose:
        return None

    display = "\n".join(f"- {item}" for item in missing_purpose[:8])
    if len(missing_purpose) > 8:
        display += f"\n- ... (+{len(missing_purpose) - 8})"
    return t(MessageKey.EVIDENCE_TOPUP_PURPOSE_REQUIRED, missing_items=display)


def _tool_message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def _should_add_python3_fallback_guardrail(
    history: list[dict[str, Any]],
    *,
    tool_results_meta: dict[str, Any] | None = None,
) -> bool:
    """
    Detect whether writer instructions should force python->python3 fallback.

    Trigger when recent shell results indicate `python` is unavailable.
    """
    recent_tool_messages: list[dict[str, Any]] = []
    for msg in reversed(history or []):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        recent_tool_messages.append(msg)
        if len(recent_tool_messages) >= 24:
            break

    if not recent_tool_messages:
        return False

    meta_map = tool_results_meta if isinstance(tool_results_meta, dict) else {}

    for msg in recent_tool_messages:
        text_lower = _tool_message_text(msg.get("content")).lower()
        if "command not found: python3" in text_lower:
            return False

    saw_python_missing = False
    for msg in recent_tool_messages:
        tool_call_id = msg.get("tool_call_id")
        meta = meta_map.get(tool_call_id, {}) if isinstance(tool_call_id, str) else {}
        command = str(meta.get("shell_command") or "").strip().lower()

        exit_code_raw = meta.get("shell_exit_code")
        try:
            exit_code = int(exit_code_raw) if exit_code_raw is not None else None
        except Exception:
            exit_code = None

        text_lower = _tool_message_text(msg.get("content")).lower()
        if (
            "command not found: python" in text_lower
            and "command not found: python3" not in text_lower
        ):
            saw_python_missing = True
            continue

        if exit_code == 127 and command.startswith("python ") and "python3" not in command:
            saw_python_missing = True

        if command.startswith("python3") and exit_code == 0:
            return False

    return saw_python_missing


def _looks_like_pytest_command(command: str) -> bool:
    return "pytest" in (command or "").lower()


def _format_last_pytest_status(tool_results_meta: dict[str, Any] | None) -> str:
    meta_map = tool_results_meta if isinstance(tool_results_meta, dict) else {}
    pytest_metas: list[dict[str, Any]] = []
    for meta in meta_map.values():
        if not isinstance(meta, dict):
            continue
        command = str(meta.get("shell_command") or "")
        if command and _looks_like_pytest_command(command):
            pytest_metas.append(meta)

    if not pytest_metas:
        return ""

    last_any = pytest_metas[-1]

    def _last_str(key: str) -> str:
        for m in reversed(pytest_metas):
            v = m.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _last_list_str(key: str) -> list[str]:
        for m in reversed(pytest_metas):
            v = m.get(key)
            if isinstance(v, list):
                items = [str(x).strip() for x in v if isinstance(x, str) and str(x).strip()]
                if items:
                    return items
        return []

    command = str(last_any.get("shell_command") or "").strip()
    exit_code_raw = last_any.get("shell_exit_code")
    try:
        exit_code = int(exit_code_raw) if exit_code_raw is not None else None
    except Exception:
        exit_code = None

    failed_tests = _last_list_str("pytest_failed_tests")
    error_type = _last_str("pytest_error_type")
    summary_line = _last_str("pytest_summary_line")
    trace_tail = _last_str("pytest_trace_tail")

    lines: list[str] = ["\n\n[VERIFICATION STATUS - LAST PYTEST]\n"]
    if command:
        lines.append(f"- command: {command}\n")
    if exit_code is not None:
        lines.append(f"- exit_code: {exit_code}\n")
    if failed_tests:
        lines.append("- failed_tests:\n")
        lines.extend([f"  - {test_id}\n" for test_id in failed_tests[:12]])
        if len(failed_tests) > 12:
            lines.append(f"  - ... (+{len(failed_tests) - 12})\n")
    if error_type:
        lines.append(f"- error_type: {error_type}\n")
    if summary_line:
        lines.append(f"- summary: {summary_line}\n")
    if trace_tail:
        lines.append("- trace_tail:\n")
        lines.append(trace_tail.rstrip() + "\n")
    return "".join(lines).rstrip() + "\n"


def _format_optimizer_verification_retry_policy(tool_results_meta: dict[str, Any] | None) -> str:
    meta_map = tool_results_meta if isinstance(tool_results_meta, dict) else {}
    optimizer_failed = 0
    saw_any = False
    for meta in meta_map.values():
        if not isinstance(meta, dict):
            continue
        command = str(meta.get("shell_command") or "")
        if not command or not _looks_like_pytest_command(command):
            continue
        saw_any = True
        if str(meta.get("shell_phase") or "") != WorkflowPhase.OPTIMIZER.value:
            continue
        exit_code_raw = meta.get("shell_exit_code")
        try:
            exit_code = int(exit_code_raw) if exit_code_raw is not None else None
        except Exception:
            exit_code = None
        if exit_code is not None and exit_code != 0:
            optimizer_failed += 1

    if not saw_any:
        return ""

    max_retries = 2
    remaining = max(0, max_retries - optimizer_failed)
    return (
        "\n\n[OPTIMIZER VERIFICATION RETRY POLICY]\n"
        f"OPTIMIZER_MAX_VERIFICATION_RETRIES: {max_retries}\n"
        f"OPTIMIZER_FAILED_VERIFICATION_ATTEMPTS: {optimizer_failed}\n"
        f"OPTIMIZER_VERIFICATION_RETRIES_REMAINING: {remaining}\n"
    )


def _resolve_api_mode(provider: Any, model: str) -> str | None:
    """
    Resolve the API mode for a provider/model pair from the model catalog.

    Returns ``"responses"`` for OpenAI models that require the Responses API,
    or ``None`` when no special routing is needed.
    """
    if getattr(provider, "name", None) != "openai":
        return None
    catalog_model = model_catalog_service.get_model_cached(model)
    if catalog_model is not None and catalog_model.mode == "responses":
        return "responses"
    return None


async def _call_with_timeout(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    timeout_seconds: int | None = None,
    **kwargs: Any,
) -> Any:
    """
    Call provider.chat_completion with timeout protection.

    Automatically resolves and injects ``api_mode`` for OpenAI models
    that require the Responses API, based on the model catalog.

    Args:
        provider: Provider instance with chat_completion method
        messages: Chat messages
        model: Model to use
        temperature: Sampling temperature
        timeout_seconds: Optional timeout override

    Returns:
        ProviderResponse from the provider

    Raises:
        TernionTimeout: If request times out (status_code=504)
    """
    if "api_mode" not in kwargs:
        api_mode = _resolve_api_mode(provider, model)
        if api_mode is not None:
            kwargs["api_mode"] = api_mode

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(
            provider.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                **kwargs,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider timeout: {provider.name} did not respond within {timeout}s",
        )
        raise TernionTimeout(
            operation=f"chat_completion ({provider.name})",
            timeout_seconds=timeout,
        ) from None
    except Exception as exc:
        runtime_model_error = classify_runtime_model_unavailable(provider.name, model, exc)
        if runtime_model_error is not None:
            raise runtime_model_error from exc
        raise


async def _call_with_stream(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    stream_queue: StreamEventQueue | None = None,
    phase: str = "",
    message_id: str = "",
    timeout_seconds: int | None = None,
    detect_tool_calls: bool = False,
    tool_calls_guard_chars: int = 256,
    tool_calls_auto_retry_max: int = 1,
    **kwargs: Any,
) -> ProviderResponse:
    """
    Call provider.chat_completion_stream with real-time token forwarding.

    This function streams LLM output tokens to the provided queue while
    accumulating the full response. If no queue is provided, falls back
    to non-streaming call.

    Args:
        provider: Provider instance with chat_completion_stream method
        messages: Chat messages
        model: Model to use
        temperature: Sampling temperature
        stream_queue: Optional queue to receive incremental tokens
        phase: Current workflow phase (for event metadata)
        message_id: Message identifier (for event metadata)
        timeout_seconds: Optional timeout override

    Returns:
        ProviderResponse with the complete generated content

    Raises:
        TernionTimeout: If request times out
    """
    # If no queue provided, fall back to non-streaming call
    if stream_queue is None:
        return await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )

    if "api_mode" not in kwargs:
        api_mode = _resolve_api_mode(provider, model)
        if api_mode is not None:
            kwargs["api_mode"] = api_mode

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    full_content = ""

    try:
        await stream_queue.put_phase_start(phase, provider=provider.name, model=model)

        stream_gen = provider.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )

        async def consume_stream() -> ProviderResponse:
            nonlocal full_content

            retry_remaining = max(0, int(tool_calls_auto_retry_max or 0))
            buffered = ""
            buffered_flushed = False
            emitted_any_token = False
            tool_calls: list[dict[str, Any]] | None = None
            tool_calls_detected = False
            full_parts: list[str] = []
            marker_tail = ""
            marker_len = len(TOOL_CALLS_BEGIN)

            try:
                guard_chars = max(0, int(tool_calls_guard_chars))
            except Exception:
                guard_chars = 256
            if not detect_tool_calls:
                guard_chars = 0

            # Step E (P2-1): Short-window buffering to avoid streaming an invalid
            # evidence top-up protocol block before guardrails validate it.
            topup_marker = EVIDENCE_REQUESTS_BEGIN
            topup_probe_enabled = str(phase or "").strip().lower() in (
                WorkflowPhase.EXECUTION.value,
                WorkflowPhase.OPTIMIZER.value,
            )
            topup_decision: bool | None = None
            suppress_stream_tokens = False
            topup_notice_emitted = False

            def _maybe_is_evidence_topup_start(text: str) -> bool | None:
                probe = (text or "").lstrip()
                if not probe:
                    return None
                if probe.startswith(topup_marker):
                    return True
                # Keep buffering while the current probe is a prefix of the marker.
                if topup_marker.startswith(probe) and len(probe) < len(topup_marker):
                    return None
                return False

            async def _retry_tool_calls_only() -> list[dict[str, Any]] | None:
                nonlocal retry_remaining
                if retry_remaining <= 0:
                    return None
                retry_remaining -= 1
                retry_instruction = (
                    "[TOOL_CALLS_ONLY_RETRY]\n\n"
                    "You MUST return tool calls ONLY. The assistant content MUST be empty.\n"
                    "Do NOT output any prose, analysis, or code fences.\n"
                    "If native tool calling is available, return tool_calls.\n"
                    "If you are using a text-based tool-calls protocol, output ONLY the tool-calls block.\n"
                )
                retry_messages = list(messages)
                retry_messages.append(
                    ChatMessage(
                        role=MessageRole.USER,
                        content=retry_instruction,
                    )
                )
                try:
                    retry_response = await _call_with_timeout(
                        provider=provider,
                        messages=retry_messages,
                        model=model,
                        temperature=min(float(temperature or 0.2), 0.2),
                        timeout_seconds=timeout_seconds,
                        **kwargs,
                    )
                except Exception as e:
                    logger.warning(
                        "tool_calls_only_retry_failed",
                        phase=phase,
                        provider=provider.name,
                        error=str(e),
                    )
                    return None

                if retry_response.tool_calls:
                    return retry_response.tool_calls

                parsed = extract_tool_calls_from_text(retry_response.content)
                if parsed:
                    return parsed

                return None

            while True:
                try:
                    chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                if not chunk:
                    continue

                if detect_tool_calls:
                    decoded = decode_stream_tool_calls(chunk)
                    if decoded is not None:
                        tool_calls_detected = True
                        tool_calls = decoded
                        buffered = ""
                        continue

                full_parts.append(chunk)

                if detect_tool_calls and not tool_calls_detected:
                    scan = marker_tail + chunk
                    if TOOL_CALLS_BEGIN in scan:
                        tool_calls_detected = True
                        buffered = ""
                        marker_tail = ""
                        continue
                    if marker_len > 1:
                        marker_tail = scan[-(marker_len - 1) :]

                if tool_calls_detected:
                    continue

                if suppress_stream_tokens:
                    continue

                if topup_probe_enabled and topup_decision is None and not emitted_any_token:
                    # Buffer until we can deterministically decide whether the output is a
                    # top-up protocol block (which must be the first non-empty line).
                    buffered += chunk
                    topup_decision = _maybe_is_evidence_topup_start(buffered)
                    if topup_decision is None:
                        continue
                    if topup_decision is True:
                        # Suppress streaming for this response to avoid UI noise; the caller
                        # will parse/validate the full content and may soft-retry if needed.
                        if not topup_notice_emitted:
                            phase_lower = str(phase or "").strip().lower()
                            role = (
                                "Writer"
                                if phase_lower == WorkflowPhase.EXECUTION.value
                                else "Optimizer"
                            )
                            await stream_queue.put_token(
                                delta=t(MessageKey.EVIDENCE_TOPUP_COLLECTING, role=role),
                                phase=phase,
                                message_id=message_id,
                            )
                            topup_notice_emitted = True
                        suppress_stream_tokens = True
                        buffered = ""
                        buffered_flushed = True
                        continue

                    # Not a top-up block. Flush (or continue buffering) per the guard_chars policy.
                    if guard_chars > 0 and not buffered_flushed:
                        if len(buffered) >= guard_chars:
                            await stream_queue.put_token(
                                delta=buffered,
                                phase=phase,
                                message_id=message_id,
                            )
                            emitted_any_token = True
                            buffered = ""
                            buffered_flushed = True
                        continue

                    await stream_queue.put_token(
                        delta=buffered,
                        phase=phase,
                        message_id=message_id,
                    )
                    emitted_any_token = True
                    buffered = ""
                    buffered_flushed = True
                    continue

                if guard_chars > 0 and not buffered_flushed:
                    buffered += chunk
                    if len(buffered) >= guard_chars:
                        await stream_queue.put_token(
                            delta=buffered,
                            phase=phase,
                            message_id=message_id,
                        )
                        emitted_any_token = True
                        buffered = ""
                        buffered_flushed = True
                    continue

                await stream_queue.put_token(
                    delta=chunk,
                    phase=phase,
                    message_id=message_id,
                )
                emitted_any_token = True

            full_content = "".join(full_parts)
            if tool_calls_detected:
                if tool_calls is None:
                    tool_calls = extract_tool_calls_from_text(full_content)

                mixed_stream = bool(detect_tool_calls and emitted_any_token)
                if mixed_stream or not tool_calls:
                    retry_tool_calls = await _retry_tool_calls_only()
                    if retry_tool_calls:
                        tool_calls = retry_tool_calls
                    elif mixed_stream:
                        logger.warning(
                            "tool_calls_only_retry_mixed_stream_fallback",
                            phase=phase,
                            provider=provider.name,
                        )

                if tool_calls:
                    return ProviderResponse(
                        content="",
                        finish_reason="tool_calls",
                        tool_calls=tool_calls,
                        usage={},
                    )
                raise ValueError("stream_detected_tool_calls_but_parse_failed")

            if buffered and not buffered_flushed:
                await stream_queue.put_token(
                    delta=buffered,
                    phase=phase,
                    message_id=message_id,
                )

            return ProviderResponse(
                content=full_content,
                finish_reason="stop",
                usage={},
            )

        response = await consume_stream()
        full_content = response.content or ""

        await stream_queue.put_final(
            content=full_content,
            phase=phase,
            message_id=message_id,
        )

        # Note: Token usage is tracked inside provider.chat_completion_stream.
        return response

    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider stream timeout: {provider.name} did not complete within {timeout}s",
        )
        await stream_queue.put_error(
            f"Stream timeout after {timeout}s",
            phase=phase,
        )
        raise TernionTimeout(
            operation=f"chat_completion_stream ({provider.name})",
            timeout_seconds=timeout,
        ) from None
    except Exception as e:
        runtime_model_error = classify_runtime_model_unavailable(provider.name, model, e)
        if runtime_model_error is not None:
            await stream_queue.put_error(
                str(runtime_model_error),
                phase=phase,
                **runtime_model_error.to_payload(),
            )
            raise runtime_model_error from e
        if stream_queue is not None and stream_queue.is_closed:
            err_text = str(e).lower()
            if (
                "incomplete chunked read" in err_text
                or "peer closed connection without sending complete message body" in err_text
            ):
                raise asyncio.CancelledError() from None
        logger.exception("stream_error", provider=provider.name, error=str(e))
        await stream_queue.put_error(str(e), phase=phase)
        raise


async def _call_optimizer_with_stream(
    provider: Any,
    messages: list[ChatMessage],
    model: str,
    temperature: float,
    stream_queue: StreamEventQueue | None,
    *,
    phase: str,
    message_id: str,
    timeout_seconds: int | None = None,
    detect_tool_calls: bool = False,
    tool_calls_auto_retry_max: int = 1,
    **kwargs: Any,
) -> tuple[ProviderResponse, bool]:
    """
    Optimizer-specific streaming wrapper.

    This streams ONLY the user-visible summary section (between the Optimizer wrapper
    markers) to avoid leaking the internal optimizer report in Cursor chat output.
    """
    if stream_queue is None:
        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        return response, False

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    full_parts: list[str] = []
    emitted_any = False
    retry_remaining = max(0, int(tool_calls_auto_retry_max or 0))

    try:
        await stream_queue.put_phase_start(phase, provider=provider.name, model=model)

        stream_gen = provider.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )

        tool_calls: list[dict[str, Any]] | None = None
        tool_calls_detected = False
        marker_tail = ""
        marker_len = len(TOOL_CALLS_BEGIN)

        user_started = False
        user_done = False
        begin_tail = ""
        end_tail = ""
        begin_len = len(_OPTIMIZER_USER_BEGIN)
        begin_keep = begin_len - 1 if begin_len > 1 else 0
        end_len = len(_OPTIMIZER_USER_END)
        end_keep = end_len - 1 if end_len > 1 else 0

        # Stream-safe sanitization: keep a small tail to prevent cross-chunk trigger formation.
        tail_len = 32
        user_emit_buffer_raw = ""

        # Evidence top-up protocol suppression:
        # If the Optimizer streams a top-up protocol block (which must start at the first
        # non-empty line), do not forward protocol tokens to the UI. Emit a single short
        # placeholder line instead.
        topup_marker = EVIDENCE_REQUESTS_BEGIN
        topup_decision: bool | None = None
        topup_buffered = ""
        suppress_stream_tokens = False
        topup_notice_emitted = False

        def _maybe_is_evidence_topup_start(text: str) -> bool | None:
            probe = (text or "").lstrip()
            if not probe:
                return None
            if probe.startswith(topup_marker):
                return True
            if topup_marker.startswith(probe) and len(probe) < len(topup_marker):
                return None
            return False

        async def _retry_tool_calls_only() -> list[dict[str, Any]] | None:
            nonlocal retry_remaining
            if retry_remaining <= 0:
                return None
            retry_remaining -= 1
            retry_instruction = (
                "[TOOL_CALLS_ONLY_RETRY]\n\n"
                "You MUST return tool calls ONLY. The assistant content MUST be empty.\n"
                "Do NOT output any wrapper markers or prose.\n"
            )
            retry_messages = list(messages)
            retry_messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=retry_instruction,
                )
            )
            try:
                retry_response = await _call_with_timeout(
                    provider=provider,
                    messages=retry_messages,
                    model=model,
                    temperature=min(float(temperature or 0.2), 0.2),
                    timeout_seconds=timeout_seconds,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(
                    "optimizer_tool_calls_only_retry_failed",
                    phase=phase,
                    provider=provider.name,
                    error=str(e),
                )
                return None

            if retry_response.tool_calls:
                return retry_response.tool_calls

            parsed = extract_tool_calls_from_text(retry_response.content)
            if parsed:
                return parsed

            return None

        while True:
            try:
                chunk = await asyncio.wait_for(stream_gen.__anext__(), timeout=timeout)
            except StopAsyncIteration:
                break
            if not chunk:
                continue

            if detect_tool_calls and not tool_calls_detected:
                decoded = decode_stream_tool_calls(chunk)
                if decoded is not None:
                    tool_calls_detected = True
                    tool_calls = decoded
                    continue

            full_parts.append(chunk)

            if detect_tool_calls and not tool_calls_detected:
                scan = marker_tail + chunk
                if TOOL_CALLS_BEGIN in scan:
                    tool_calls_detected = True
                    marker_tail = ""
                    continue
                if marker_len > 1:
                    marker_tail = scan[-(marker_len - 1) :]

            if tool_calls_detected:
                continue

            if suppress_stream_tokens:
                continue

            if topup_decision is None and not emitted_any and not user_started:
                topup_buffered += chunk
                topup_decision = _maybe_is_evidence_topup_start(topup_buffered)
                if topup_decision is None:
                    continue
                if topup_decision is True:
                    if not topup_notice_emitted:
                        await stream_queue.put_token(
                            delta=t(
                                MessageKey.EVIDENCE_TOPUP_COLLECTING,
                                role="Optimizer",
                            ),
                            phase=phase,
                            message_id=message_id,
                        )
                        topup_notice_emitted = True
                    suppress_stream_tokens = True
                    topup_buffered = ""
                    continue

                # Not a top-up block. Continue streaming using the buffered content.
                chunk = topup_buffered
                topup_buffered = ""

            if user_done:
                continue

            visible_chunk = ""
            if not user_started:
                scan = begin_tail + chunk
                idx = scan.find(_OPTIMIZER_USER_BEGIN)
                if idx < 0:
                    if begin_keep > 0:
                        begin_tail = scan[-begin_keep:]
                    continue

                user_started = True
                begin_tail = ""
                visible_chunk = scan[idx + len(_OPTIMIZER_USER_BEGIN) :].lstrip("\n\r")
            else:
                visible_chunk = chunk

            if not user_started:
                continue

            if not visible_chunk:
                continue

            scan = end_tail + visible_chunk
            end_idx = scan.find(_OPTIMIZER_USER_END)
            if end_idx < 0:
                if end_keep > 0:
                    if len(scan) <= end_keep:
                        end_tail = scan
                        continue
                    visible = scan[:-end_keep]
                    end_tail = scan[-end_keep:]
                else:
                    visible = scan
                    end_tail = ""
            else:
                visible = scan[:end_idx]
                end_tail = ""
                user_done = True

            if not visible:
                continue

            user_emit_buffer_raw += visible
            if user_done or len(user_emit_buffer_raw) > tail_len:
                if user_done:
                    flush_raw = user_emit_buffer_raw
                    user_emit_buffer_raw = ""
                else:
                    flush_raw = user_emit_buffer_raw[:-tail_len]
                    user_emit_buffer_raw = user_emit_buffer_raw[-tail_len:]

                safe = sanitize_for_cursor_display(flush_raw)
                if safe:
                    await stream_queue.put_token(
                        delta=safe,
                        phase=phase,
                        message_id=message_id,
                    )
                    emitted_any = True

        full_content = "".join(full_parts)
        if tool_calls_detected:
            if tool_calls is None:
                tool_calls = extract_tool_calls_from_text(full_content)
            mixed_stream = bool(detect_tool_calls and emitted_any)
            if mixed_stream or not tool_calls:
                retry_tool_calls = await _retry_tool_calls_only()
                if retry_tool_calls:
                    tool_calls = retry_tool_calls
                elif mixed_stream:
                    logger.warning(
                        "optimizer_tool_calls_only_retry_mixed_stream_fallback",
                        phase=phase,
                        provider=provider.name,
                    )
            if tool_calls:
                return (
                    ProviderResponse(
                        content="",
                        finish_reason="tool_calls",
                        tool_calls=tool_calls,
                        usage={},
                    ),
                    False,
                )
            raise ValueError("optimizer_stream_detected_tool_calls_but_parse_failed")

        if user_started and not user_done:
            if end_tail:
                user_emit_buffer_raw += end_tail
                end_tail = ""
            safe_tail = (
                sanitize_for_cursor_display(user_emit_buffer_raw) if user_emit_buffer_raw else ""
            )
            if safe_tail:
                await stream_queue.put_token(
                    delta=safe_tail,
                    phase=phase,
                    message_id=message_id,
                )
                emitted_any = True

        await stream_queue.put_final(
            content="",
            phase=phase,
            message_id=message_id,
        )

        return (
            ProviderResponse(
                content=full_content,
                finish_reason="stop",
                usage={},
            ),
            emitted_any,
        )
    except TimeoutError:
        log_manager.emit(
            "ERROR",
            "LLM",
            f"Provider stream timeout: {provider.name} did not complete within {timeout}s",
        )
        await stream_queue.put_error(
            f"Stream timeout after {timeout}s",
            phase=phase,
        )
        raise TernionTimeout(
            operation=f"chat_completion_stream ({provider.name})",
            timeout_seconds=timeout,
        ) from None
    except Exception as e:
        runtime_model_error = classify_runtime_model_unavailable(provider.name, model, e)
        if runtime_model_error is not None:
            await stream_queue.put_error(
                str(runtime_model_error),
                phase=phase,
                **runtime_model_error.to_payload(),
            )
            raise runtime_model_error from e
        if stream_queue is not None and stream_queue.is_closed:
            err_text = str(e).lower()
            if (
                "incomplete chunked read" in err_text
                or "peer closed connection without sending complete message body" in err_text
            ):
                raise asyncio.CancelledError() from None
        logger.exception("optimizer_stream_error", provider=provider.name, error=str(e))
        await stream_queue.put_error(str(e), phase=phase)
        raise


def _prepend_global_security_rules(prompt: str) -> str:
    """
    Prepend global security rules to a phase-specific system prompt.

    This keeps provider compatibility by emitting a single system prompt string.
    """
    rules = GLOBAL_SECURITY_RULES.strip()
    if not rules:
        return prompt
    return f"{rules}\n\n{prompt}"


def _append_global_security_rules(prompt: str) -> str:
    """
    Append global security rules to an external system prompt.

    This is used for preserving the client's system prompt semantics while
    ensuring global security constraints remain present.
    """
    rules = GLOBAL_SECURITY_RULES.strip()
    if not rules:
        return prompt
    prompt = prompt.strip()
    if not prompt:
        return rules
    return f"{prompt}\n\n{rules}"


def _format_role_names(role_ids: list[str]) -> str:
    names = [_ROLE_DISPLAY_NAMES.get(role_id, role_id) for role_id in role_ids]
    return ", ".join([name for name in names if name])


def _format_evidence_section(
    lines: list[str],
    *,
    header: str,
    default_line: str,
) -> str:
    if not any(line.strip() for line in lines):
        return f"{header}\n{default_line}"
    return "\n".join([header, *lines]).rstrip()


def _build_execution_policy_context(
    *,
    ternion_report: str,
    latest_user_message: str,
    evidence_bundle: str,
    evidence_gaps: str,
    evidence_chain_index: list[dict[str, object]],
    evidence_topup_round: int,
) -> tuple[str, list[str], list[str]]:
    report_for_policy = _extract_report_scope_for_policy(ternion_report)
    deliverable_policy = resolve_deliverable_policy(latest_user_message, report_for_policy)
    deliverable_policy_text = format_deliverable_policy_for_prompt(deliverable_policy)
    try:
        evidence_index_json = json.dumps(evidence_chain_index, ensure_ascii=False, indent=2)
    except Exception:
        evidence_index_json = "[]"
    evidence_chain_lines = [
        "\n\n[REPORT_EVIDENCE_CHAIN - VERBATIM]\n\n",
        evidence_bundle,
        "\n\n",
        evidence_gaps,
        "\n\nEVIDENCE_CHAIN_INDEX_JSON:\n",
        evidence_index_json,
    ]
    topup_rounds_remaining = max(0, _MAX_EVIDENCE_TOPUP_ROUNDS - evidence_topup_round)
    topup_status_lines = [
        "\n\n[EVIDENCE_TOPUP_STATUS]\n\n",
        f"TOPUP_ROUND_USED: {evidence_topup_round}\n",
        f"TOPUP_MAX_ROUNDS: {_MAX_EVIDENCE_TOPUP_ROUNDS}\n",
        f"TOPUP_ROUNDS_REMAINING: {topup_rounds_remaining}\n",
        "RULES:\n",
        "- If evidence is insufficient and TOPUP_ROUNDS_REMAINING > 0, use the Phase 1.5 protocol block.\n",
        "- Before requesting evidence top-up, you MUST consult EVIDENCE_CHAIN_INDEX_JSON and must NOT request items already satisfied.\n",
        "- If TOPUP_ROUNDS_REMAINING == 0, you MUST proceed with the requested deliverable using existing evidence.\n",
        "- If EVIDENCE_GAPS contains [MISSING_PURPOSE], it indicates missing PURPOSE metadata (not missing code). Do NOT request additional code just to satisfy it; if PURPOSE is needed for traceability, request the SAME ref range and include a PURPOSE line.\n",
    ]
    if topup_rounds_remaining == 1:
        topup_status_lines.append(
            "- This is the LAST allowed top-up. Any top-up request MUST set FINAL_REQUEST: true.\n"
        )
    return deliverable_policy_text, evidence_chain_lines, topup_status_lines


def _parse_evidence_output(content: str) -> tuple[str, str]:
    text = (content or "").strip()
    bundle_header = "EVIDENCE_BUNDLE:"
    gaps_header = "EVIDENCE_GAPS:"
    bundle_lines: list[str] = []
    gaps_lines: list[str] = []
    section: str | None = None
    found_bundle = False
    found_gaps = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == bundle_header:
            section = "bundle"
            found_bundle = True
            continue
        if stripped == gaps_header:
            section = "gaps"
            found_gaps = True
            continue
        if section == "bundle":
            bundle_lines.append(line)
        elif section == "gaps":
            gaps_lines.append(line)

    if not found_bundle and not found_gaps:
        fallback = text if text else "- None"
        return (
            f"{bundle_header}\n{fallback}".rstrip(),
            f"{gaps_header}\n- None",
        )

    bundle = _format_evidence_section(
        bundle_lines,
        header=bundle_header,
        default_line="- None",
    )
    gaps = _format_evidence_section(
        gaps_lines,
        header=gaps_header,
        default_line="- None",
    )
    return bundle, gaps


def _extract_evidence_requests(analyses: list[dict[str, Any]]) -> str:
    requests: list[str] = []
    for analysis in analyses:
        text = (analysis.get("analysis") or "").splitlines()
        capture = False
        for line in text:
            stripped = line.strip()
            if stripped.lower().startswith("### 5. evidence_requests"):
                capture = True
                continue
            if capture and stripped.startswith("###"):
                break
            if capture and stripped:
                requests.append(stripped)
    return canonicalize_evidence_requests_text("\n".join(requests))


def _filter_conversation_history_for_analysis(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter conversation history for analysis/report phases.

    This removes tool-result messages and tool-call artifacts so that:
    - Council/Arbiter only see user/assistant dialogue context
    - Evidence is provided exclusively via evidence_bundle/evidence_gaps
    - Token usage stays predictable (avoid carrying raw tool outputs)

    Args:
        history: Conversation history list (OpenAI-compatible message dicts).

    Returns:
        Filtered history containing only user/assistant messages with content.
    """
    filtered: list[dict[str, Any]] = []
    for msg in history:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str) and not content.strip():
            continue

        filtered.append(
            {
                "role": role,
                "content": content,
                "name": msg.get("name"),
                # Intentionally omit tool_calls/tool_call_id to keep downstream context clean.
            }
        )
    return filtered


def _collect_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> set[str]:
    ids: set[str] = set()
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if isinstance(tc_id, str) and tc_id:
            ids.add(tc_id)
    return ids


_READ_ONLY_CURSOR_TOOL_CANONICAL = {
    "read",
    "readfile",
    "grep",
    "glob",
    "ls",
    "readlints",
    "semanticsearch",
    "codebasesearch",
}


def _filter_read_only_cursor_tools(cursor_tools: list[Any]) -> list[Any]:
    """
    Evidence collection must be read-only.

    Cursor-provided tool schemas include both read-only and mutating tools (Write/ApplyPatch/Shell/etc).
    We must not allow Arbiter evidence phases to mutate the workspace.
    """
    filtered: list[Any] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
        if canonical in _READ_ONLY_CURSOR_TOOL_CANONICAL:
            filtered.append(tool)
    return filtered


def _filter_execution_cursor_tools(cursor_tools: list[Any]) -> list[Any]:
    """
    Execution/Optimizer tools must exclude read/search tools.
    """
    filtered: list[Any] = []
    for tool in cursor_tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
        if canonical in EXECUTION_ALLOWED_TOOL_CANONICAL:
            filtered.append(tool)
    return filtered


async def evidence_node(state: TernionState) -> TernionState:
    """
    Phase 0: Evidence Gathering - Arbiter collects minimal code evidence.

    Uses tool calls only. Outputs evidence_bundle and evidence_gaps.

    Args:
        state: Current LangGraph state dict containing session variables.

    Returns:
        Updated state dict transitioning to phase 1 (divergence) or handling errors.
    """
    logger.info("workflow_evidence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Evidence phase started | Arbiter collecting evidence",
    )

    thinking_logs = list(state.get("thinking_logs", []))

    history = state.get("conversation_history", [])
    session_id = str(state.get("session_id") or "").strip()
    history_for_prompt = history
    if not session_id:
        # For a new evidence run, strip any prior tool artifacts from the inbound history.
        # Evidence should be re-collected via tools and represented in the evidence bundle.
        history_for_prompt = _filter_conversation_history_for_analysis(history)

    system_prompt = _prepend_global_security_rules(ARBITER_EVIDENCE_PROMPT)
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    for msg in history_for_prompt:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    cursor_tools = _filter_read_only_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("arbiter")

    try:
        provider = provider_manager.get_provider_for_role("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("arbiter_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [error_msg],
                "final_output": sanitize_for_cursor_display(error_msg),
                "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (
            supports_native_tools or supports_text_tools
        )

        if supports_text_tools:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "[NON-OPENAI TOOL CALLS]\n\n"
                        f"{build_text_tool_calls_instruction(cursor_tools)}"
                    ),
                )
            )
        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,
            **extra_kwargs,
        )
        tool_calls = response.tool_calls if isinstance(response.tool_calls, list) else None
        if supports_text_tools and not tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
                tool_calls = parsed_tool_calls

        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        budget_manager.record_usage(
            provider=provider.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_for_cost,
            thoughts_tokens=thoughts_tokens,
            context_length=usage.get("total_tokens", 0),
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"evidence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        if tool_calls:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "evidence_tool_calls_ready | "
                    f"session_id={state.get('session_id', '')} | "
                    f"count={len(tool_calls)}"
                ),
            )
            return {
                **state,
                "current_phase": WorkflowPhase.EVIDENCE.value,
                "pending_tool_calls": tool_calls,
                "thinking_logs": thinking_logs,
            }

        evidence_bundle, evidence_gaps = _parse_evidence_output(response.content)
        evidence_gaps = merge_missing_purpose_gaps(
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
        )
        cleaned_history = _filter_conversation_history_for_analysis(history)
        return {
            **state,
            "current_phase": WorkflowPhase.DIVERGENCE.value,
            "conversation_history": cleaned_history,
            "evidence_bundle": evidence_bundle,
            "evidence_gaps": evidence_gaps,
            "thinking_logs": thinking_logs,
        }
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.warning(
            "evidence_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("evidence_collection_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Evidence collection failed: {str(e)[:120]}",
        )
        error_msg = t(MessageKey.EVIDENCE_COLLECTION_FAILED, error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "thinking_logs": thinking_logs,
        }


def _split_optimizer_output(text: str) -> tuple[str, str]:
    """
    Split Optimizer output into internal and user-visible sections.

    The Optimizer prompt requires a strict wrapper with begin/end markers.
    This helper extracts those blocks and falls back to treating the full
    content as user summary when markers are missing.
    """
    raw = (text or "").strip()
    if not raw:
        return "", ""

    def extract_block(begin: str, end: str) -> str:
        start = raw.find(begin)
        if start < 0:
            return ""
        start += len(begin)
        stop = raw.find(end, start)
        if stop < 0:
            return ""
        return raw[start:stop].strip()

    internal = extract_block(_OPTIMIZER_INTERNAL_BEGIN, _OPTIMIZER_INTERNAL_END)
    user = extract_block(_OPTIMIZER_USER_BEGIN, _OPTIMIZER_USER_END)
    if user:
        return internal, user

    # Safety fallback: never leak the raw optimizer output to the user if the wrapper is missing.
    return internal or raw, ""


def _parse_optimizer_action_contract(internal_report: str) -> dict[str, Any]:
    """Parse structured optimizer action fields from the internal report."""
    info: dict[str, Any] = {
        "protocol_valid": False,
        "action_required": None,
        "action_taken": "",
        "action_reason": "",
        "required_change_items": [],
    }
    if not isinstance(internal_report, str) or not internal_report.strip():
        return info

    action_required: bool | None = None
    action_taken = ""
    action_reason = ""
    required_items: list[str] = []
    collecting_items = False

    for raw_line in internal_report.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(_OPTIMIZER_ACTION_REQUIRED_PREFIX):
            collecting_items = False
            value = line[len(_OPTIMIZER_ACTION_REQUIRED_PREFIX) :].strip().lower()
            if value == "true":
                action_required = True
            elif value == "false":
                action_required = False
            continue

        if line.startswith(_OPTIMIZER_ACTION_TAKEN_PREFIX):
            collecting_items = False
            value = line[len(_OPTIMIZER_ACTION_TAKEN_PREFIX) :].strip().lower()
            if value in _OPTIMIZER_ACTION_TAKEN_VALUES:
                action_taken = value
            continue

        if line.startswith(_OPTIMIZER_ACTION_REASON_PREFIX):
            collecting_items = False
            action_reason = line[len(_OPTIMIZER_ACTION_REASON_PREFIX) :].strip()
            continue

        if line.startswith(_OPTIMIZER_REQUIRED_CHANGE_ITEMS_PREFIX):
            collecting_items = True
            continue

        if not collecting_items:
            continue

        if _OPTIMIZER_ACTION_FIELD_LINE_RE.match(line):
            collecting_items = False
            continue

        if line.startswith("-") or line.startswith("*"):
            item = line[1:].strip()
            if item and item.lower() not in {"none", "n/a", "not applicable"}:
                required_items.append(item)
            continue

        collecting_items = False

    info["action_required"] = action_required
    info["action_taken"] = action_taken
    info["action_reason"] = action_reason
    info["required_change_items"] = required_items
    info["protocol_valid"] = (
        action_required is not None
        and action_taken in _OPTIMIZER_ACTION_TAKEN_VALUES
        and bool(action_reason)
    )
    return info


def _should_retry_optimizer_action_protocol(contract: dict[str, Any]) -> bool:
    """Return True when optimizer finalization violates the action protocol."""
    if not bool(contract.get("protocol_valid")):
        return True

    action_required = contract.get("action_required")
    action_taken = str(contract.get("action_taken") or "").strip().lower()
    if action_required is True:
        return True
    return action_taken in {"tool_calls", "evidence_topup"}


def _summarize_optimizer_required_change_items(
    required_change_items: list[str], *, limit: int = 5
) -> str:
    """Create a short log preview for unresolved optimizer-required changes."""
    if not required_change_items:
        return "None"
    preview = " || ".join(item.strip() for item in required_change_items[:limit] if item.strip())
    if len(required_change_items) > limit:
        preview = f"{preview} || ..."
    return preview or "None"


def _build_optimizer_action_protocol_feedback(contract: dict[str, Any]) -> str:
    """Build guardrail feedback for optimizer action-protocol violations."""
    action_required = contract.get("action_required")
    action_taken = str(contract.get("action_taken") or "").strip().lower() or "(missing)"
    action_reason = str(contract.get("action_reason") or "").strip() or "(missing)"
    required_items = [
        sanitize_for_cursor_display(str(item).strip())
        for item in list(contract.get("required_change_items") or [])
        if str(item).strip()
    ]
    lines = [
        "Your previous optimizer finalization violated the action protocol.",
        f"- protocol_valid: {bool(contract.get('protocol_valid'))}",
        f"- ACTION_REQUIRED: {action_required}",
        f"- ACTION_TAKEN: {action_taken}",
        f"- ACTION_REASON: {sanitize_for_cursor_display(action_reason)}",
    ]
    if required_items:
        lines.append("- REQUIRED_CHANGE_ITEMS:")
        lines.extend(f"  - {item}" for item in required_items[:10])
        if len(required_items) > 10:
            lines.append("  - ...")
    else:
        lines.append("- REQUIRED_CHANGE_ITEMS: None")
    lines.extend(
        [
            "",
            "Proceed as follows:",
            "- If a required change still remains, do NOT finalize. Emit tool_calls with empty assistant content.",
            "- If a required change depends on missing evidence, emit ONLY the strict evidence top-up block.",
            "- If no required change remains, finalize with ACTION_REQUIRED: false, ACTION_TAKEN: none, and a concrete ACTION_REASON.",
        ]
    )
    return "\n".join(lines)


async def divergence_node(state: TernionState) -> TernionState:
    """
    Step 1: The Divergence - Parallel Root Cause Analysis.

    Three user-configured ternion members analyze the problem concurrently,
    focusing on root cause analysis without writing code.

    Args:
        state: Current workflow state

    Returns:
        Updated state with ternion analyses
    """
    logger.info("workflow_divergence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Divergence phase started | Parallel ternion analysis beginning",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.DIVERGENCE_START))

    # Build messages for ternion - use Ternion RCA prompt, not Cursor's
    history = state.get("conversation_history", [])
    history_for_prompt = _filter_conversation_history_for_analysis(history)
    evidence_bundle = state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None"
    evidence_gaps = state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None"
    evidence_block = f"[EVIDENCE]\n\n{evidence_bundle}\n\n{evidence_gaps}"
    system_prompt = _prepend_global_security_rules(f"{DIVERGENCE_PROMPT}\n\n{evidence_block}")
    ternion_messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    for msg in history_for_prompt:
        ternion_messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
            )
        )

    ternion_ids = ["ternion_a", "ternion_b", "ternion_c"]
    ternion_configs = []
    unconfigured = []

    for ternion_id in ternion_ids:
        cfg = config_store.get_role_config(ternion_id)
        if cfg and cfg.provider and cfg.model:
            ternion_configs.append(
                {
                    "ternion_id": ternion_id,
                    "provider": cfg.provider,
                    "model": cfg.model,
                }
            )
        else:
            unconfigured.append(ternion_id)

    if unconfigured:
        error_msg = t(
            MessageKey.ROLE_CONFIG_INCOMPLETE,
            missing_roles=_format_role_names(unconfigured),
        )
        logger.warning("ternion_not_configured", unconfigured=unconfigured)
        thinking_logs.append(error_msg)
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "ternion_analyses": [],
            "thinking_logs": thinking_logs,
        }

    async def analyze(ternion_cfg: dict[str, Any]) -> dict[str, Any]:
        ternion_id = ternion_cfg["ternion_id"]
        provider_name = ternion_cfg["provider"]
        model = ternion_cfg["model"]
        try:
            provider = provider_manager.get_provider(provider_name)
            if not provider:
                role_name = _ROLE_DISPLAY_NAMES.get(ternion_id, ternion_id)
                return {
                    "ternion_id": ternion_id,
                    "provider": provider_name,
                    "analysis": "",
                    "error": t(
                        MessageKey.PROVIDER_UNAVAILABLE,
                        role=role_name,
                        provider=provider_name,
                    ),
                }
            response = None
            max_attempts = 3 if provider.name == "google" else 1
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await _call_with_timeout(
                        provider=provider,
                        messages=ternion_messages,
                        model=model,
                        temperature=0.7,
                    )
                    break
                except Exception as e:
                    is_last = attempt >= max_attempts
                    error_text = str(e)
                    retryable = provider.name == "google" and (
                        "503" in error_text
                        or "UNAVAILABLE" in error_text
                        or "overloaded" in error_text.lower()
                    )
                    if is_last or not retryable:
                        raise
                    wait_seconds = 1.5 * attempt
                    logger.warning(
                        "ternion_analysis_retry",
                        ternion_id=ternion_id,
                        provider=provider_name,
                        model=model,
                        attempt=attempt,
                        wait_seconds=wait_seconds,
                        error=error_text[:200],
                    )
                    await asyncio.sleep(wait_seconds)

            if response is None:
                raise RuntimeError("divergence_provider_response_missing")
            usage = response.usage or {}
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
            thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
            output_for_cost = (
                completion_tokens
                if provider.name != "google"
                else completion_tokens + thoughts_tokens
            )
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            if input_tokens or output_for_cost or thoughts_tokens:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        f"divergence_usage | provider={provider.name} | "
                        f"model={model} | "
                        f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                        f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                    ),
                )
            return {
                "ternion_id": ternion_id,
                "provider": provider_name,
                "analysis": response.content,
                "error": None,
            }
        except RuntimeModelUnavailableError:
            raise
        except Exception as e:
            logger.warning(
                "ternion_analysis_failed",
                ternion_id=ternion_id,
                provider=provider_name,
                error=str(e),
            )
            return {
                "ternion_id": ternion_id,
                "provider": provider_name,
                "analysis": "",
                "error": str(e),
            }

    tasks = [analyze(cfg) for cfg in ternion_configs]
    try:
        analyses = await asyncio.gather(*tasks)
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.warning(
            "divergence_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs,
            "ternion_analyses": [],
        }

    successful = [a for a in analyses if not a.get("error")]
    logger.info(
        "workflow_divergence_complete",
        successful_count=len(successful),
        total_count=len(analyses),
    )

    for a in successful:
        preview = sanitize_for_preview(a["analysis"], max_length=100)
        thinking_logs.append(
            t(MessageKey.DIVERGENCE_ANALYSIS, ternion_id=a["ternion_id"], preview=preview)
        )

    failed = [a for a in analyses if a.get("error")]
    for a in failed:
        err_preview = sanitize_for_preview(str(a.get("error") or ""), max_length=100)
        thinking_logs.append(
            t(
                MessageKey.DIVERGENCE_ANALYSIS_FAILED,
                ternion_id=str(a.get("ternion_id") or ""),
                provider=str(a.get("provider") or ""),
                error=err_preview,
            )
        )

    evidence_requests = _extract_evidence_requests(successful)

    return {
        **state,
        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
        "ternion_analyses": list(analyses),
        "evidence_requests": evidence_requests,
        "thinking_logs": thinking_logs,
    }


def _has_real_evidence_requests(requests: str) -> bool:
    """
    Check if evidence_requests contains real requests (not just '- [P0] None').

    Args:
        requests: The extracted evidence_requests string.

    Returns:
        True if there are real evidence requests, False otherwise.
    """
    text = canonicalize_evidence_requests_text(requests or "").strip()
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    # Strict empty marker protocol (case-insensitive).
    return not (len(lines) == 1 and lines[0].lower() in ("- [p0] none", "[p0] none"))


_DETERMINISTIC_EVIDENCE_READ_CHUNK_LINES = 200
_TOOL_TEXT_FIELD_RE = re.compile(
    r"text=(?P<quote>'|\")(?P<body>(?:\\.|(?!\1).)*)(?P=quote)",
    flags=re.DOTALL,
)
_NUMBERED_PIPE_RE = re.compile(r"^\s*(\d+)\|(.*)$")
_NUMBERED_L_PREFIX_RE = re.compile(r"^L(\d+):(.*)$")
_REPO_ROOT_CACHE: Path | None = None


def _get_repo_root() -> Path:
    """
    Best-effort repository root detection (used for absolute tool paths).
    """
    global _REPO_ROOT_CACHE
    if _REPO_ROOT_CACHE is not None:
        return _REPO_ROOT_CACHE

    start = Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            _REPO_ROOT_CACHE = candidate
            return candidate
    _REPO_ROOT_CACHE = start
    return start


def _to_repo_relative_path(raw_path: str | None) -> str:
    """
    Normalize a tool path to a repo-relative, forward-slash path when possible.
    """
    if not raw_path or not isinstance(raw_path, str):
        return ""
    cleaned = raw_path.strip().strip('"').strip("'").strip("`")
    if not cleaned:
        return ""

    p = Path(cleaned).expanduser()
    if p.is_absolute():
        try:
            rel = p.resolve(strict=False).relative_to(_get_repo_root())
            return rel.as_posix()
        except Exception:
            return cleaned.replace("\\", "/")

    cleaned = cleaned.removeprefix("./").removeprefix(".\\")
    return cleaned.replace("\\", "/")


def _to_repo_absolute_path(repo_rel_path: str) -> str:
    """
    Convert a repo-relative path to an absolute path under the repo root.
    """
    rel = (repo_rel_path or "").strip().removeprefix("./").removeprefix(".\\")
    if not rel:
        return ""
    p = Path(rel)
    if p.is_absolute():
        return str(p)
    return str((_get_repo_root() / p).resolve(strict=False))


def _extract_tool_text(tool_content: str | None) -> str:
    """
    Extract text payloads from Cursor tool outputs when they are wrapped as TextContent repr.
    """
    raw = tool_content or ""
    if not raw:
        return ""

    matches = list(_TOOL_TEXT_FIELD_RE.finditer(raw))
    if not matches:
        return raw

    parts: list[str] = []
    for m in matches:
        quote = m.group("quote")
        body = m.group("body")
        literal = f"{quote}{body}{quote}"
        try:
            value = ast.literal_eval(literal)
            if isinstance(value, str) and value:
                parts.append(value)
        except Exception:
            if body:
                parts.append(body)
    return "\n".join(parts) if parts else raw


def _extract_numbered_lines(text: str) -> list[tuple[int, str]]:
    """
    Extract numbered lines from tool output. Supports both `123|...` and `L123:...`.
    """
    parsed: list[tuple[int, str]] = []
    for raw_line in (text or "").splitlines():
        match = _NUMBERED_PIPE_RE.match(raw_line)
        if match:
            num = int(match.group(1))
            parsed.append((num, raw_line.rstrip()))
            continue
        match = _NUMBERED_L_PREFIX_RE.match(raw_line)
        if match:
            num = int(match.group(1))
            rendered = f"{num}|{match.group(2).lstrip()}"
            parsed.append((num, rendered.rstrip()))
    return parsed


def _group_contiguous_numbered_lines(
    lines: list[tuple[int, str]],
    *,
    within: tuple[int, int] | None = None,
) -> list[list[tuple[int, str]]]:
    """
    Group numbered lines into contiguous runs.
    """
    if not lines:
        return []

    if within is not None:
        r_start, r_end = within
        filtered = [(n, s) for n, s in lines if r_start <= n <= r_end]
    else:
        filtered = list(lines)

    if not filtered:
        return []

    runs: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    prev_num: int | None = None
    for num, raw in filtered:
        if prev_num is None or num == prev_num + 1:
            current.append((num, raw))
        else:
            if current:
                runs.append(current)
            current = [(num, raw)]
        prev_num = num
    if current:
        runs.append(current)
    return runs


def _sha256_16(text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def _format_purpose_for_deterministic_evidence(purposes: set[str]) -> str:
    cleaned = [p.strip() for p in purposes if isinstance(p, str) and p.strip()]
    if not cleaned:
        return "Satisfy deterministic evidence request(s)."
    unique: list[str] = []
    seen: set[str] = set()
    for p in cleaned:
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return " / ".join(unique)


async def report_evidence_node(state: TernionState) -> TernionState:
    """
    Phase 1.5: Report Evidence Verification - Arbiter collects requested evidence.

    This node collects additional evidence based on evidence_requests from council
    members before generating the final report. Uses tool calls only. Appends to
    existing evidence_bundle and evidence_gaps.

    Args:
        state: Current workflow state with evidence_requests from divergence.

    Returns:
        Updated state with appended evidence, ready for convergence.
    """
    evidence_requests = state.get("evidence_requests", "")
    thinking_logs = list(state.get("thinking_logs", []))
    resume_phase = str(state.get("report_evidence_resume_phase") or "").strip().lower()
    next_phase = (
        WorkflowPhase.OPTIMIZER.value
        if resume_phase == WorkflowPhase.OPTIMIZER.value
        else WorkflowPhase.EXECUTION.value
        if resume_phase == WorkflowPhase.EXECUTION.value
        else WorkflowPhase.CONVERGENCE.value
    )

    if not _has_real_evidence_requests(evidence_requests):
        logger.info("report_evidence_skip", reason="no_real_requests")
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message="Phase 1.5 skipped | No real evidence requests from council",
        )
        reconciled_gaps, evidence_chain_index = reconcile_evidence_chain(
            evidence_bundle=state.get("evidence_bundle") or "",
            evidence_gaps=state.get("evidence_gaps") or "",
            evidence_requests=evidence_requests,
        )
        return {
            **state,
            "current_phase": next_phase,
            "evidence_gaps": reconciled_gaps,
            "evidence_chain_index": evidence_chain_index,
            "thinking_logs": thinking_logs,
        }

    logger.info("workflow_report_evidence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Phase 1.5 started | Arbiter collecting requested evidence",
    )

    session_id = str(state.get("session_id") or "").strip()

    cursor_tools = _filter_read_only_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("arbiter")
    history = state.get("conversation_history", [])

    parsed_requests = parse_evidence_requests(evidence_requests)
    deterministic_targets: list[dict[str, Any]] = []
    non_deterministic_entries: list[Any] = []
    for req in parsed_requests:
        det = is_deterministic_range_request(req)
        if det is not None:
            path, line_range = det
            deterministic_targets.append(
                {
                    "path": path,
                    "line_range": line_range,
                    "purpose": str(getattr(req, "purpose", "") or ""),
                }
            )
        else:
            non_deterministic_entries.append(req)

    deterministic_paths = {
        str(t.get("path") or "")
        for t in deterministic_targets
        if isinstance(t, dict) and t.get("path")
    }

    existing_bundle = state.get("evidence_bundle") or ""
    updated_bundle = existing_bundle
    attempted_reads: set[tuple[str, int, int]] = set()

    if deterministic_targets:
        existing_items = parse_evidence_bundle(existing_bundle)
        existing_keys = {
            (
                _to_repo_relative_path(item.path),
                (item.lines or "").strip(),
                item.excerpt_hash_raw,
            )
            for item in existing_items
            if item.path and item.lines
        }

        tool_contents_by_id: dict[str, str] = {}
        for msg in history:
            if msg.get("role") != "tool":
                continue
            tool_call_id = msg.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                continue
            content = msg.get("content")
            tool_contents_by_id[tool_call_id] = (
                content if isinstance(content, str) else str(content)
            )

        new_item_blocks: list[str] = []

        def ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
            return not (a[1] < b[0] or a[0] > b[1])

        for msg in history:
            if msg.get("role") != "assistant":
                continue
            assistant_tool_calls = msg.get("tool_calls")
            if not isinstance(assistant_tool_calls, list) or not assistant_tool_calls:
                continue
            for tc in assistant_tool_calls:
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id")
                fn = tc.get("function")
                if not isinstance(fn, dict):
                    continue
                name = fn.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
                if canonical not in {"read", "readfile"}:
                    continue
                args_raw = fn.get("arguments")
                if not isinstance(args_raw, str) or not args_raw.strip():
                    continue
                try:
                    args = json.loads(args_raw)
                except Exception:
                    continue
                if not isinstance(args, dict):
                    continue

                raw_path = str(
                    args.get("path") or args.get("target_file") or args.get("file_path") or ""
                )
                path_rel = _to_repo_relative_path(raw_path)
                if not path_rel or path_rel not in deterministic_paths:
                    continue

                offset = args.get("offset")
                limit = args.get("limit")
                if not isinstance(offset, int) or not isinstance(limit, int) or limit <= 0:
                    continue
                start = max(1, offset)
                end = start + limit - 1
                attempted_reads.add((path_rel, start, end))

                if not isinstance(tc_id, str) or not tc_id:
                    continue
                tool_raw = tool_contents_by_id.get(tc_id) or ""
                if not tool_raw:
                    continue
                extracted = _extract_tool_text(tool_raw)
                numbered = _extract_numbered_lines(extracted)
                runs = _group_contiguous_numbered_lines(numbered, within=(start, end))
                if not runs:
                    continue

                for run in runs:
                    run_start = run[0][0]
                    run_end = run[-1][0]
                    purposes = {
                        str(t.get("purpose") or "")
                        for t in deterministic_targets
                        if t.get("path") == path_rel
                        and isinstance(t.get("line_range"), tuple)
                        and ranges_overlap(t["line_range"], (run_start, run_end))
                    }
                    purpose = _format_purpose_for_deterministic_evidence(purposes)
                    excerpt_lines = ["  " + raw for _, raw in run]
                    excerpt_raw = "\n".join(excerpt_lines).rstrip()
                    excerpt_hash_raw = _sha256_16(excerpt_raw)
                    lines_value = f"{run_start}-{run_end}"
                    key = (path_rel, lines_value, excerpt_hash_raw)
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)
                    new_item_blocks.append(
                        f"- [FILE_EXCERPT] path={path_rel} | lines={lines_value}\n"
                        f"  PURPOSE: {purpose}\n"
                        "  EXCERPT_BEGIN\n" + "\n".join(excerpt_lines) + "\n"
                        "  EXCERPT_END"
                    )

        if new_item_blocks:
            if (
                updated_bundle
                and updated_bundle.strip().startswith("EVIDENCE_BUNDLE:")
                and "- None" not in updated_bundle
            ):
                updated_bundle = updated_bundle.rstrip() + "\n\n" + "\n".join(new_item_blocks)
            else:
                updated_bundle = "EVIDENCE_BUNDLE:\n" + "\n".join(new_item_blocks)

    deterministic_tool_calls: list[dict[str, Any]] = []
    if deterministic_targets:
        bundle_items = parse_evidence_bundle(updated_bundle)
        covered_by_path: dict[str, list[tuple[int, int]]] = {}
        for bundle_item in bundle_items:
            if bundle_item.line_range is None:
                continue
            path_rel = _to_repo_relative_path(bundle_item.path)
            if not path_rel or path_rel not in deterministic_paths:
                continue
            covered_by_path.setdefault(path_rel, []).append(bundle_item.line_range)

        segments_by_path: dict[str, list[tuple[int, int, str]]] = {}
        for target in deterministic_targets:
            path = str(target.get("path") or "")
            req_range = target.get("line_range")
            if not path or not isinstance(req_range, tuple):
                continue
            missing = compute_missing_ranges(
                request_range=req_range,
                covered_ranges=covered_by_path.get(path, []),
            )
            for seg_start, seg_end in missing:
                segments_by_path.setdefault(path, []).append(
                    (seg_start, seg_end, str(target.get("purpose") or ""))
                )

        for path, segments in segments_by_path.items():
            seg_ranges = [(s, e) for s, e, _ in segments]
            merged = merge_adjacent_or_overlapping_ranges(seg_ranges)
            for seg_start, seg_end in merged:
                purposes = {p for s, e, p in segments if p and not (e < seg_start or s > seg_end)}
                chunk_start = seg_start
                while chunk_start <= seg_end:
                    chunk_end = min(
                        seg_end,
                        chunk_start + _DETERMINISTIC_EVIDENCE_READ_CHUNK_LINES - 1,
                    )
                    if (path, chunk_start, chunk_end) not in attempted_reads:
                        deterministic_tool_calls.append(
                            {
                                "path": path,
                                "start": chunk_start,
                                "end": chunk_end,
                                "purposes": purposes,
                            }
                        )
                    chunk_start = chunk_end + 1

    if deterministic_tool_calls:
        read_tool_name: str | None = None
        path_key = "path"
        offset_key = "offset"
        limit_key = "limit"
        for tool in cursor_tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            canonical = re.sub(r"[^a-z0-9]+", "", name.strip().lower())
            if canonical not in {"read", "readfile"}:
                continue
            read_tool_name = name
            params = fn.get("parameters")
            if isinstance(params, dict):
                props = params.get("properties")
                if isinstance(props, dict):
                    if "path" in props:
                        path_key = "path"
                    elif "target_file" in props:
                        path_key = "target_file"
                    elif "file_path" in props:
                        path_key = "file_path"
                    if "offset" in props:
                        offset_key = "offset"
                    if "limit" in props:
                        limit_key = "limit"
            break

        if read_tool_name:
            pending_tool_calls: list[dict[str, Any]] = []
            for idx, spec in enumerate(deterministic_tool_calls):
                rel_path = str(spec.get("path") or "")
                abs_path = _to_repo_absolute_path(rel_path)
                start = int(spec.get("start") or 0)
                end = int(spec.get("end") or 0)
                if not abs_path or start <= 0 or end < start:
                    continue
                args = {
                    path_key: abs_path,
                    offset_key: start,
                    limit_key: end - start + 1,
                }
                pending_tool_calls.append(
                    {
                        "id": f"deterministic_report_evidence_{idx}",
                        "type": "function",
                        "function": {
                            "name": read_tool_name,
                            "arguments": json.dumps(args, ensure_ascii=False),
                        },
                    }
                )

            if pending_tool_calls:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        "report_evidence_deterministic_tool_calls_ready | "
                        f"session_id={session_id} | "
                        f"count={len(pending_tool_calls)}"
                    ),
                )
                return {
                    **state,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "pending_tool_calls": pending_tool_calls,
                    "evidence_bundle": updated_bundle,
                    "thinking_logs": thinking_logs,
                }

    if non_deterministic_entries:
        non_det_lines: list[str] = []
        for entry in non_deterministic_entries:
            req_line = str(getattr(entry, "request", "") or "").strip()
            if not req_line:
                continue
            non_det_lines.append(f"- {req_line}")
            purpose = str(getattr(entry, "purpose", "") or "").strip()
            if purpose:
                non_det_lines.append(f"PURPOSE: {purpose}")
        effective_evidence_requests = canonicalize_evidence_requests_text(
            "\n".join(non_det_lines).strip()
        )
    else:
        effective_evidence_requests = canonicalize_evidence_requests_text("")

    if (
        deterministic_targets
        and not _has_real_evidence_requests(effective_evidence_requests)
        and not deterministic_tool_calls
    ):
        reconciled_gaps, evidence_chain_index = reconcile_evidence_chain(
            evidence_bundle=updated_bundle,
            evidence_gaps=state.get("evidence_gaps") or "",
            evidence_requests=evidence_requests,
        )
        return {
            **state,
            "current_phase": next_phase,
            "evidence_bundle": updated_bundle,
            "evidence_gaps": reconciled_gaps,
            "evidence_chain_index": evidence_chain_index,
            "conversation_history": _filter_conversation_history_for_analysis(
                state.get("conversation_history", [])
            ),
            "thinking_logs": thinking_logs,
        }

    if _has_real_evidence_requests(effective_evidence_requests):
        host_evidence_requests = effective_evidence_requests
    else:
        host_evidence_requests = canonicalize_evidence_requests_text(evidence_requests)

    if updated_bundle != existing_bundle:
        state = {**state, "evidence_bundle": updated_bundle}

    system_prompt = _prepend_global_security_rules(ARBITER_REPORT_EVIDENCE_PROMPT)
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
    ]
    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content=f"[EVIDENCE_REQUESTS]\n{host_evidence_requests}",
        )
    )

    assistant_with_tools_count = 0
    tool_msg_count = 0
    raw_tool_msg_count = 0
    dropped_tool_msg_count = 0
    pending_tool_call_ids: set[str] = set()
    for msg in history:
        role = msg.get("role")
        if role == "assistant":
            assistant_tool_calls = msg.get("tool_calls")
            if isinstance(assistant_tool_calls, list) and assistant_tool_calls:
                assistant_with_tools_count += 1
                pending_tool_call_ids = _collect_tool_call_ids(assistant_tool_calls)
                messages.append(
                    ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=msg.get("content"),
                        name=msg.get("name"),
                        tool_calls=assistant_tool_calls,
                    )
                )
            else:
                pending_tool_call_ids = set()
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                raw_tool_msg_count += 1
                if tool_call_id in pending_tool_call_ids:
                    tool_msg_count += 1
                    messages.append(
                        ChatMessage(
                            role=MessageRole.TOOL,
                            content=msg.get("content"),
                            name=msg.get("name"),
                            tool_call_id=tool_call_id,
                        )
                    )
                else:
                    dropped_tool_msg_count += 1
        else:
            pending_tool_call_ids = set()

    if raw_tool_msg_count > 0:
        log_manager.emit(
            level="DEBUG" if assistant_with_tools_count > 0 else "WARN",
            category="WORKFLOW",
            message=(
                f"report_evidence_messages_composed | "
                f"history_len={len(history)} | "
                f"assistant_with_tools={assistant_with_tools_count} | "
                f"tool_msgs={tool_msg_count} | "
                f"dropped_tool_msgs={dropped_tool_msg_count} | "
                f"final_msgs_len={len(messages)}"
            ),
        )
        if assistant_with_tools_count == 0 and raw_tool_msg_count > 0:
            logger.warning(
                "report_evidence_tool_messages_without_assistant",
                history_len=len(history),
                tool_msg_count=raw_tool_msg_count,
                history_roles=[msg.get("role") for msg in history],
                history_has_tool_calls=[
                    bool(msg.get("tool_calls")) for msg in history if msg.get("role") == "assistant"
                ],
            )
        if dropped_tool_msg_count > 0:
            logger.warning(
                "report_evidence_orphan_tool_messages_dropped",
                history_len=len(history),
                dropped_tool_msg_count=dropped_tool_msg_count,
            )

    try:
        provider = provider_manager.get_provider_for_role("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("arbiter_model_not_configured_report_evidence")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                # Maintain current phase on error to preserve consistency.
                "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs,
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (
            supports_native_tools or supports_text_tools
        )

        if supports_text_tools:
            messages.append(
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "[NON-OPENAI TOOL CALLS]\n\n"
                        f"{build_text_tool_calls_instruction(cursor_tools)}"
                    ),
                )
            )
        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        response = await _call_with_timeout(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.2,
            **extra_kwargs,
        )
        response_tool_calls: list[dict[str, Any]] | None = (
            response.tool_calls if isinstance(response.tool_calls, list) else None
        )
        if supports_text_tools and not response_tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
                response_tool_calls = parsed_tool_calls

        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        budget_manager.record_usage(
            provider=provider.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_for_cost,
            thoughts_tokens=thoughts_tokens,
            context_length=usage.get("total_tokens", 0),
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"report_evidence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        if response_tool_calls:
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "report_evidence_tool_calls_ready | "
                    f"session_id={session_id} | "
                    f"count={len(response_tool_calls)}"
                ),
            )
            return {
                **state,
                "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                "pending_tool_calls": response_tool_calls,
                "thinking_logs": thinking_logs,
            }

        new_bundle, new_gaps = _parse_evidence_output(response.content)
        existing_bundle = state.get("evidence_bundle") or ""
        existing_gaps = state.get("evidence_gaps") or ""

        # Strip headers when appending to prevent duplication.
        if new_bundle and "- None" not in new_bundle:
            # Strip EVIDENCE_BUNDLE: header from new_bundle to avoid duplicate headers
            new_bundle_content = new_bundle
            if new_bundle_content.startswith("EVIDENCE_BUNDLE:"):
                new_bundle_content = new_bundle_content[len("EVIDENCE_BUNDLE:") :].lstrip("\n")
            if existing_bundle and "- None" not in existing_bundle:
                # Append new evidence lines to existing bundle (after the header)
                updated_bundle = f"{existing_bundle}\n\n{new_bundle_content}"
            else:
                updated_bundle = new_bundle  # Use full new_bundle with header if no existing
        else:
            updated_bundle = existing_bundle

        # Preserve previous phase gaps when merging new ones.
        if new_gaps and "- None" not in new_gaps:
            if existing_gaps and "- None" not in existing_gaps:
                # Strip EVIDENCE_GAPS: header from new_gaps before merging
                new_gaps_content = new_gaps
                if new_gaps_content.startswith("EVIDENCE_GAPS:"):
                    new_gaps_content = new_gaps_content[len("EVIDENCE_GAPS:") :].lstrip("\n")
                # Merge: existing gaps + new gaps (dedupe handled by uniqueness of evidence items)
                updated_gaps = f"{existing_gaps}\n{new_gaps_content}"
            else:
                updated_gaps = new_gaps  # Use full new_gaps with header if no existing
        else:
            updated_gaps = existing_gaps

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message="Phase 1.5 complete | Evidence collected and appended",
        )
        reconciled_gaps, evidence_chain_index = reconcile_evidence_chain(
            evidence_bundle=updated_bundle,
            evidence_gaps=updated_gaps,
            evidence_requests=evidence_requests,
        )

        return {
            **state,
            "current_phase": next_phase,
            "evidence_bundle": updated_bundle,
            "evidence_gaps": reconciled_gaps,
            "evidence_chain_index": evidence_chain_index,
            "conversation_history": _filter_conversation_history_for_analysis(
                state.get("conversation_history", [])
            ),
            "thinking_logs": thinking_logs,
        }
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.warning(
            "report_evidence_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("report_evidence_collection_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Phase 1.5 evidence collection failed: {str(e)[:120]}",
        )
        # On failure, stop at this phase (not convergence) for consistency
        return {
            **state,
            # Maintain current phase on error to preserve consistency.
            "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
            "errors": state.get("errors", [])
            + [t(MessageKey.REPORT_EVIDENCE_COLLECTION_FAILED, error=str(e))],
            "thinking_logs": thinking_logs,
        }


async def convergence_node(state: TernionState) -> TernionState:
    """
    Step 2: The Convergence - Arbiter Synthesis.

    The Arbiter synthesizes all ternion analyses,
    resolves conflicts, and produces a unified Ternion Analysis Report.

    Args:
        state: Current workflow state with ternion analyses

    Returns:
        Updated state with synthesized report
    """
    logger.info("workflow_convergence_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Convergence phase started | Arbiter synthesizing analyses",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.CONVERGENCE_START))

    analyses = state.get("ternion_analyses", [])
    successful_analyses = [a for a in analyses if not a.get("error")]

    if not successful_analyses:
        logger.error("no_successful_analyses")
        error_msg = t(MessageKey.NO_TERNION_ANALYSES_AVAILABLE)
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "ternion_report": "",
            "is_consensus": False,
        }

    user_config = config_store.load()
    language_code = user_config.language
    if language_code == "auto":
        language_code = user_config.browser_language or "en"

    language_name = get_language_name(language_code)
    instruction_template = get_report_language_instruction_template()
    language_instruction = (
        instruction_template.format(language_name=language_name) if instruction_template else ""
    )

    convergence_prompt_with_lang = build_convergence_prompt(
        language_instruction=language_instruction
    )

    evidence_bundle = state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None"
    evidence_gaps = state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None"
    evidence_requests = _extract_evidence_requests(successful_analyses)

    synthesis_content = (
        f"{evidence_bundle}\n\n"
        f"{evidence_gaps}\n\n"
        "EVIDENCE_REQUESTS:\n"
        f"{evidence_requests}\n\n"
        "Council Analyses:\n\n"
    )
    for analysis in successful_analyses:
        synthesis_content += f"### {analysis['ternion_id'].upper()}\n"
        synthesis_content += f"{analysis['analysis']}\n\n"

    messages: list[ChatMessage] = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(convergence_prompt_with_lang),
        )
    ]

    history = state.get("conversation_history", [])
    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    messages.append(ChatMessage(role=MessageRole.USER, content=synthesis_content))

    # Use Arbiter (Gemini with fallback)
    try:
        provider = provider_manager.get_provider_for_role("arbiter")

        role_cfg = config_store.get_role_config("arbiter")
        model = role_cfg.model if role_cfg and role_cfg.model else None

        if not model:
            logger.error("arbiter_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["arbiter"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
            }

        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")
        response = await _call_with_stream(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.5,  # Lower temperature for synthesis
            stream_queue=stream_queue,
            phase="convergence",
            message_id=session_id,
        )
        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"convergence_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        preview = sanitize_for_preview(response.content, max_length=80)
        thinking_logs.append(t(MessageKey.CONVERGENCE_COMPLETE, preview=preview))

        # Determine execution mode from state or config (must be explicitly set)
        execution_mode_str = state.get("execution_mode", "") or config_store.load().execution_mode
        if execution_mode_str not in ("cursor_handoff", "ternion_full"):
            error_msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
            logger.error("execution_mode_not_configured")
            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
            }

        execution_mode = ExecutionMode(execution_mode_str)

        # Check if we should await user confirmation (Human-in-the-Loop)
        await_confirmation = state.get("await_confirmation", True)

        if await_confirmation:
            # Create a session for tracking
            session = session_store.create_session(
                ternion_report=response.content,
                execution_mode=execution_mode,
                original_context={
                    "conversation_history": state.get("conversation_history", []),
                    "cursor_system_prompt": state.get("cursor_system_prompt"),
                    "workspace_root": state.get("workspace_root", ""),
                    "local_workspace_root": state.get("local_workspace_root", ""),
                    "workspace_path_style": state.get("workspace_path_style", ""),
                    "workspace_root_source": state.get("workspace_root_source", ""),
                },
                workspace_root=str(state.get("workspace_root", "") or ""),
                local_workspace_root=str(state.get("local_workspace_root", "") or ""),
                workspace_path_style=str(state.get("workspace_path_style", "") or ""),
                workspace_root_source=str(state.get("workspace_root_source", "") or ""),
                evidence_bundle=str(state.get("evidence_bundle") or ""),
                evidence_gaps=str(state.get("evidence_gaps") or ""),
                evidence_requests=str(state.get("evidence_requests") or ""),
                evidence_chain_index=list(state.get("evidence_chain_index") or []),
                ternion_analyses=list(state.get("ternion_analyses") or []),
            )

            # Log session info and report
            log_manager.emit(
                level="INFO",
                category="SESSION",
                message=f"Session created: {session.session_id} | Mode: {execution_mode.value} | Status: AWAITING_CONFIRMATION",
            )
            log_manager.emit(
                level="INFO",
                category="REPORT",
                message=f"Ternion Report generated (Len: {len(response.content)} chars). Content Preview: {response.content[:200].replace(chr(10), ' ')}...",
            )

            # Generate a plain-text view of the report for display.
            display_report = format_report_for_display(session.ternion_report_raw)
            display_report_safe = sanitize_for_cursor_display(display_report)

            mode_description = (
                t(MessageKey.EXECUTION_MODE_DESC_TERNION_FULL)
                if execution_mode == ExecutionMode.TERNION_FULL
                else t(MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF)
            )
            session_path = f"~/.ternion/sessions/{session.session_id}.json"
            raw_note = t(
                MessageKey.REPORT_RAW_SESSION_NOTE,
                path=session_path,
                field="ternion_report_raw",
            )
            confirm_prompt_key = (
                MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF
                if execution_mode == ExecutionMode.CURSOR_HANDOFF
                else MessageKey.REPORT_CONFIRM_PROMPT
            )
            confirm_prompt = t(
                confirm_prompt_key,
                mode_desc=mode_description,
            )

            session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

            final_output_suffix = f"""

---

{raw_note}

{confirm_prompt}

{session_markers}"""

            final_output = f"""{display_report_safe}

---

{raw_note}

{confirm_prompt}

{session_markers}"""

            logger.info(
                "convergence_awaiting_confirmation",
                session_id=session.session_id,
                execution_mode=execution_mode.value,
            )

            return {
                **state,
                "current_phase": WorkflowPhase.CONVERGENCE.value,  # Stay in convergence
                "ternion_report": response.content,
                "is_consensus": len(successful_analyses) > 1,
                "thinking_logs": thinking_logs,
                "session_id": session.session_id,
                "await_confirmation": True,
                "final_output": final_output,  # This will be returned to user
                "final_output_suffix": final_output_suffix,
            }
        else:
            # Direct execution mode (no confirmation required)
            session_id_str = str(session_id or "").strip()
            if session_id_str:
                session_store.update_session(
                    session_id_str,
                    ternion_report_raw=response.content,
                )
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "ternion_report": response.content,
                "is_consensus": len(successful_analyses) > 1,
                "thinking_logs": thinking_logs,
            }
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.warning(
            "convergence_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
        }
    except Exception as e:
        logger.error("convergence_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Arbiter failed: {str(e)[:80]}... Attempting ternion fallback",
        )

        # Prioritize successful council members for fallback Arbiter.
        # Priority: ternion_a → ternion_b → ternion_c
        fallback_providers = []
        for analysis in successful_analyses:
            ternion_id = analysis.get("ternion_id")
            cfg = config_store.get_role_config(ternion_id)
            if cfg and cfg.provider and cfg.model:
                fallback_providers.append(
                    {
                        "ternion_id": ternion_id,
                        "provider": cfg.provider,
                        "model": cfg.model,
                    }
                )

        fallback_response = None
        fallback_provider_name = None
        fallback_model = None

        for fallback_cfg in fallback_providers:
            try:
                fallback_provider = provider_manager.get_provider(fallback_cfg["provider"])
                if not fallback_provider:
                    continue

                logger.info(
                    "convergence_fallback_attempt",
                    ternion_id=fallback_cfg["ternion_id"],
                    provider=fallback_cfg["provider"],
                )
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=f"Trying fallback Arbiter: {fallback_cfg['ternion_id']} ({fallback_cfg['provider']}/{fallback_cfg['model']})",
                )
                fallback_response = await _call_with_timeout(
                    provider=fallback_provider,
                    messages=messages,
                    model=fallback_cfg["model"],
                    temperature=0.5,
                )
                fallback_provider_name = fallback_provider.name
                fallback_model = fallback_cfg["model"]

                usage = fallback_response.usage or {}
                input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                completion_tokens = (
                    usage.get("completion_tokens") or usage.get("output_tokens") or 0
                )
                thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
                output_for_cost = (
                    completion_tokens
                    if fallback_provider.name != "google"
                    else completion_tokens + thoughts_tokens
                )
                budget_manager.record_usage(
                    provider=fallback_provider.name,
                    model=fallback_cfg["model"],
                    input_tokens=input_tokens,
                    output_tokens=output_for_cost,
                    thoughts_tokens=thoughts_tokens,
                    context_length=usage.get("total_tokens", 0),
                )
                if input_tokens or output_for_cost or thoughts_tokens:
                    log_manager.emit(
                        level="INFO",
                        category="WORKFLOW",
                        message=(
                            f"convergence_fallback_usage | provider={fallback_provider.name} | "
                            f"model={fallback_cfg['model']} | "
                            f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens}"
                        ),
                    )

                logger.info(
                    "convergence_fallback_success",
                    ternion_id=fallback_cfg["ternion_id"],
                    provider=fallback_cfg["provider"],
                )
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=f"Fallback Arbiter succeeded: {fallback_cfg['ternion_id']}",
                )
                break  # Success, exit fallback loop

            except RuntimeModelUnavailableError as fallback_exc:
                error_msg = _build_runtime_model_unavailable_message(fallback_exc)
                logger.warning(
                    "convergence_fallback_runtime_model_unavailable",
                    ternion_id=fallback_cfg["ternion_id"],
                    provider=fallback_exc.provider,
                    model=fallback_exc.model,
                )
                return {
                    **state,
                    "current_phase": WorkflowPhase.COMPLETE.value,
                    "errors": state.get("errors", []) + [error_msg],
                    "final_output": sanitize_for_cursor_display(error_msg),
                    "runtime_error_payload": fallback_exc.to_payload(),
                    "thinking_logs": thinking_logs
                    + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
                }
            except Exception as fallback_exc:
                logger.warning(
                    "convergence_fallback_failed",
                    ternion_id=fallback_cfg["ternion_id"],
                    error=str(fallback_exc),
                )
                log_manager.emit(
                    level="WARN",
                    category="WORKFLOW",
                    message=f"Fallback Arbiter failed: {fallback_cfg['ternion_id']} - {str(fallback_exc)[:50]}",
                )
                continue  # Try next fallback

        if fallback_response:
            thinking_logs.append(
                t(
                    MessageKey.CONVERGENCE_ERROR,
                    error=f"Used fallback: {fallback_provider_name}/{fallback_model}",
                )
            )
            preview = sanitize_for_preview(fallback_response.content, max_length=80)
            thinking_logs.append(t(MessageKey.CONVERGENCE_COMPLETE, preview=preview))

            execution_mode_str = (
                state.get("execution_mode", "") or config_store.load().execution_mode
            )
            if execution_mode_str not in ("cursor_handoff", "ternion_full"):
                error_msg = t(MessageKey.EXECUTION_MODE_NOT_CONFIGURED)
                logger.error("execution_mode_not_configured")
                return {
                    **state,
                    "current_phase": WorkflowPhase.COMPLETE.value,
                    "errors": state.get("errors", []) + [error_msg],
                    "thinking_logs": thinking_logs
                    + [t(MessageKey.CONVERGENCE_ERROR, error=error_msg)],
                }

            execution_mode = ExecutionMode(execution_mode_str)
            await_confirmation = state.get("await_confirmation", True)

            if await_confirmation:
                session = session_store.create_session(
                    ternion_report=fallback_response.content,
                    execution_mode=execution_mode,
                    original_context={
                        "conversation_history": state.get("conversation_history", []),
                        "cursor_system_prompt": state.get("cursor_system_prompt"),
                        "workspace_root": state.get("workspace_root", ""),
                        "local_workspace_root": state.get("local_workspace_root", ""),
                        "workspace_path_style": state.get("workspace_path_style", ""),
                        "workspace_root_source": state.get("workspace_root_source", ""),
                    },
                    workspace_root=str(state.get("workspace_root", "") or ""),
                    local_workspace_root=str(state.get("local_workspace_root", "") or ""),
                    workspace_path_style=str(state.get("workspace_path_style", "") or ""),
                    workspace_root_source=str(state.get("workspace_root_source", "") or ""),
                    evidence_bundle=str(state.get("evidence_bundle") or ""),
                    evidence_gaps=str(state.get("evidence_gaps") or ""),
                    evidence_requests=str(state.get("evidence_requests") or ""),
                    evidence_chain_index=list(state.get("evidence_chain_index") or []),
                    ternion_analyses=list(state.get("ternion_analyses") or []),
                )

                log_manager.emit(
                    level="INFO",
                    category="SESSION",
                    message=f"Session created (via fallback Arbiter): {session.session_id} | Mode: {execution_mode.value}",
                )

                display_report = format_report_for_display(session.ternion_report_raw)
                display_report_safe = sanitize_for_cursor_display(display_report)
                mode_description = (
                    t(MessageKey.EXECUTION_MODE_DESC_TERNION_FULL)
                    if execution_mode == ExecutionMode.TERNION_FULL
                    else t(MessageKey.EXECUTION_MODE_DESC_CURSOR_HANDOFF)
                )
                session_path = f"~/.ternion/sessions/{session.session_id}.json"
                raw_note = t(
                    MessageKey.REPORT_RAW_SESSION_NOTE,
                    path=session_path,
                    field="ternion_report_raw",
                )
                confirm_prompt_key = (
                    MessageKey.REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF
                    if execution_mode == ExecutionMode.CURSOR_HANDOFF
                    else MessageKey.REPORT_CONFIRM_PROMPT
                )
                confirm_prompt = t(
                    confirm_prompt_key,
                    mode_desc=mode_description,
                )

                session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

                final_output_suffix = f"""

---

{raw_note}

{confirm_prompt}

{session_markers}"""

                final_output = f"""{display_report_safe}

---

{raw_note}

{confirm_prompt}

{session_markers}"""

                return {
                    **state,
                    "current_phase": WorkflowPhase.CONVERGENCE.value,
                    "ternion_report": fallback_response.content,
                    "is_consensus": len(successful_analyses) > 1,
                    "thinking_logs": thinking_logs,
                    "session_id": session.session_id,
                    "await_confirmation": True,
                    "final_output": final_output,
                    "final_output_suffix": final_output_suffix,
                }
            else:
                session_id_str = str(state.get("session_id") or "").strip()
                if session_id_str:
                    session_store.update_session(
                        session_id_str,
                        ternion_report_raw=fallback_response.content,
                    )
                return {
                    **state,
                    "current_phase": WorkflowPhase.EXECUTION.value,
                    "ternion_report": fallback_response.content,
                    "is_consensus": len(successful_analyses) > 1,
                    "thinking_logs": thinking_logs,
                }

        # All fallbacks failed - use raw analysis as last resort
        fallback_report = successful_analyses[0]["analysis"]
        all_arbiters_failed_msg = t(MessageKey.CONVERGENCE_ALL_ARBITERS_FAILED)
        thinking_logs.append(t(MessageKey.CONVERGENCE_ERROR, error=all_arbiters_failed_msg))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message="All Arbiter attempts failed, using raw ternion analysis as fallback",
        )

        execution_mode_str = state.get("execution_mode", "") or config_store.load().execution_mode

        if execution_mode_str == "cursor_handoff":
            execution_mode = ExecutionMode.CURSOR_HANDOFF
            session = session_store.create_session(
                ternion_report=fallback_report,
                execution_mode=execution_mode,
                original_context={
                    "conversation_history": state.get("conversation_history", []),
                    "cursor_system_prompt": state.get("cursor_system_prompt"),
                    "workspace_root": state.get("workspace_root", ""),
                    "local_workspace_root": state.get("local_workspace_root", ""),
                    "workspace_path_style": state.get("workspace_path_style", ""),
                    "workspace_root_source": state.get("workspace_root_source", ""),
                },
                workspace_root=str(state.get("workspace_root", "") or ""),
                local_workspace_root=str(state.get("local_workspace_root", "") or ""),
                workspace_path_style=str(state.get("workspace_path_style", "") or ""),
                workspace_root_source=str(state.get("workspace_root_source", "") or ""),
                evidence_bundle=str(state.get("evidence_bundle") or ""),
                evidence_gaps=str(state.get("evidence_gaps") or ""),
                evidence_requests=str(state.get("evidence_requests") or ""),
                evidence_chain_index=list(state.get("evidence_chain_index") or []),
                ternion_analyses=list(state.get("ternion_analyses") or []),
            )

            log_manager.emit(
                level="WARN",
                category="SESSION",
                message=f"Session created with raw analysis (all Arbiters failed): {session.session_id}",
            )

            display_report = format_report_for_display(session.ternion_report_raw)
            display_report_safe = sanitize_for_cursor_display(display_report)
            fallback_warning = t(MessageKey.CONVERGENCE_FALLBACK_WARNING)
            fallback_confirm = t(MessageKey.CONVERGENCE_FALLBACK_CONFIRM)
            session_path = f"~/.ternion/sessions/{session.session_id}.json"
            raw_note = t(
                MessageKey.REPORT_RAW_SESSION_NOTE,
                path=session_path,
                field="ternion_report_raw",
            )
            session_markers = f"""TERNION_SESSION_ID={session.session_id}
TERNION_SESSION_STAGE=AWAITING_CONFIRMATION
TERNION_EXECUTION_MODE={execution_mode.value}
TERNION_REPORT_HASH={session.report_hash}"""

            final_output_suffix = f"""

---

{fallback_warning}

{raw_note}

{fallback_confirm}

{session_markers}"""

            final_output = f"""{display_report_safe}

---

{fallback_warning}

{raw_note}

{fallback_confirm}

{session_markers}"""

            return {
                **state,
                "current_phase": WorkflowPhase.CONVERGENCE.value,
                "ternion_report": fallback_report,
                "is_consensus": False,
                "thinking_logs": thinking_logs,
                "session_id": session.session_id,
                "await_confirmation": True,
                "final_output": final_output,
                "final_output_suffix": final_output_suffix,
                "errors": state.get("errors", []) + [all_arbiters_failed_msg],
            }
        else:
            session_id_str = str(state.get("session_id") or "").strip()
            if session_id_str:
                session_store.update_session(
                    session_id_str,
                    ternion_report_raw=fallback_report,
                )
            return {
                **state,
                "current_phase": WorkflowPhase.EXECUTION.value,
                "ternion_report": fallback_report,
                "is_consensus": False,
                "thinking_logs": thinking_logs,
                "errors": state.get("errors", []) + [all_arbiters_failed_msg],
            }


async def execution_node(state: TernionState) -> TernionState:
    """
    Step 3: The Execution - Writer Produces Deliverables.

    The Writer produces the final deliverable(s) based on
    the Ternion Analysis Report. Uses Cursor's original system
    prompt to ensure output format compatibility.

    Args:
        state: Current workflow state with analysis report

    Returns:
        Updated state with Writer output
    """
    logger.info("workflow_execution_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Execution phase started | Writer generating deliverable(s)",
    )

    thinking_logs = list(state.get("thinking_logs", []))
    thinking_logs.append(t(MessageKey.EXECUTION_START))

    # Build messages with Cursor's system prompt (for format compliance)
    cursor_prompt = state.get("cursor_system_prompt")
    ternion_report = state.get("ternion_report", "")
    history = state.get("conversation_history", [])
    latest_user_message = get_latest_user_message(history)
    history_len_before = len(history)
    tool_context_digest = ""
    truncated_history = False
    try:
        from ternion.utils.execution_history_compaction import (
            ExecutionHistoryCompactionConfig,
            compact_execution_history_for_writer,
        )

        history, tool_context_digest = compact_execution_history_for_writer(
            history,
            config=ExecutionHistoryCompactionConfig(),
        )
        truncated_history = len(history) != history_len_before
    except Exception:
        # Best-effort: do not block execution on compaction failures.
        tool_context_digest = ""
        truncated_history = False

    cursor_tools = _filter_execution_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("writer")

    messages = []

    # Use Cursor's system prompt if available, otherwise fall back to Ternion's.
    # Note: Some provider backends only support a single system prompt. Keep exactly one.
    if cursor_prompt:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=cursor_prompt))
    else:
        messages.append(
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=_prepend_global_security_rules(EXECUTION_PROMPT),
            )
        )

    # Add conversation history
    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    # Inject Writer constraints as a final user instruction without breaking client format rules.
    # This keeps provider compatibility while ensuring the Writer sees Ternion constraints even
    # when a client system prompt is present.
    writer_instructions = _prepend_global_security_rules(EXECUTION_PROMPT)

    revision_count = state.get("revision_count", 0)
    review_feedback = state.get("review_feedback", "")
    previous_code = state.get("generated_code", "")

    evidence_bundle = str(state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None")
    evidence_gaps = str(state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None")
    evidence_chain_index = list(state.get("evidence_chain_index") or [])
    topup_round_used = int(state.get("evidence_topup_round", 0) or 0)
    report_scope_for_policy = _extract_report_scope_for_policy(ternion_report)
    deliverable_policy = resolve_deliverable_policy(latest_user_message, report_scope_for_policy)
    stabilized_document_paths = list(state.get("stabilized_document_paths") or [])
    deliverable_policy_text, evidence_chain_lines, topup_status_lines = (
        _build_execution_policy_context(
            ternion_report=ternion_report,
            latest_user_message=latest_user_message,
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
            evidence_chain_index=evidence_chain_index,
            evidence_topup_round=topup_round_used,
        )
    )

    content_parts = [
        "[TERNION WRITER INSTRUCTIONS]\n\n",
        writer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
        *evidence_chain_lines,
        "\n\n[DELIVERABLE POLICY]\n\n",
        deliverable_policy_text,
        *topup_status_lines,
    ]
    if tool_context_digest:
        content_parts.extend(
            [
                "\n\n[TERNION TOOL CONTEXT DIGEST]\n\n",
                tool_context_digest,
            ]
        )
    if stabilized_document_paths:
        rendered_paths = "\n".join(
            f"- {_render_stabilized_document_path(path, state.get('workspace_root'), state.get('workspace_path_style'))}"
            for path in stabilized_document_paths
        )
        content_parts.extend(
            [
                "\n\n[STABILIZED DOCUMENT OUTPUTS]\n\n",
                "These document-like outputs already completed a successful whole-file `Write` "
                "and are now frozen for additional whole-file rewrites:\n",
                rendered_paths,
                "\nDo not rewrite those files with `Write` again. Continue only with "
                "non-document code work, or finish if those document outputs are already complete.",
            ]
        )

    modified_files = state.get("modified_files") or []
    if not isinstance(modified_files, list):
        modified_files = []
    if modified_files:
        content_parts.extend(
            [
                "\n\n[MODIFIED FILES]\n\n",
                "\n".join(f"- {p}" for p in modified_files),
            ]
        )
        ruff_commands = _build_scoped_ruff_verification_commands(modified_files)
        if ruff_commands:
            content_parts.extend(
                [
                    "\n\n[SCOPED VERIFICATION COMMANDS]\n\n",
                    "Default Ruff verification (scoped to modified Python files; avoid `... .`):\n",
                    "\n".join(f"- {cmd}" for cmd in ruff_commands),
                ]
            )

    if revision_count > 0:
        feedback_content = (
            review_feedback.strip()
            if review_feedback
            else (
                "[NOTE] Reviewer requested revision but feedback content is empty or missing. "
                "Please carefully review your deliverable for potential issues based on "
                "the original analysis report."
            )
        )
        code_content = (
            previous_code.strip()
            if previous_code
            else (
                "[NOTE] No previous deliverable found. This may indicate an error in the "
                "workflow. Please generate a fresh deliverable based on the analysis report."
            )
        )
        content_parts.extend(
            [
                "\n\n[REVIEWER FEEDBACK - REVISION REQUIRED]\n\n",
                feedback_content,
                "\n\n[CURRENT DELIVERABLE]\n\n",
                code_content,
                "\n\nAddress the issues above and revise the deliverable(s) based on the "
                "report and reviewer feedback, following the deliverable policy and allowed "
                "write scope.",
            ]
        )
    else:
        content_parts.append(
            "\n\nProceed with the requested deliverable(s) based on the report above, "
            "and follow the deliverable policy and allowed write scope."
        )

    if _should_add_python3_fallback_guardrail(
        history,
        tool_results_meta=state.get("tool_results_meta"),
    ):
        content_parts.extend(
            [
                "\n\n[PYTHON RUNTIME FALLBACK]\n\n",
                "Environment signal: previous shell results show `command not found: python`.\n",
                "For Python module invocations and tests, use `python3` instead of `python`.\n",
                "- Preferred command: `python3 -m pytest -q`\n",
                "- Do not repeat commands that already failed with `command not found: python`.\n",
            ]
        )

    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content="".join(content_parts),
        )
    )

    # Use Writer (Claude with fallback)
    try:
        provider = provider_manager.get_provider_for_role("writer")

        model = role_cfg.model if role_cfg and role_cfg.model else None

        if not model:
            logger.error("writer_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["writer"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.EXECUTION_ERROR, error=error_msg)],
            }

        stream_queue: StreamEventQueue | None = state.get("_stream_queue")
        session_id = state.get("session_id", "")

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (
            supports_native_tools or supports_text_tools
        )
        writer_timeout = WRITER_TIMEOUT_SECONDS

        async def _retry_writer_if_empty(
            response: ProviderResponse,
            *,
            allow_tool_calls: bool,
            response_context: str,
            extra_kwargs: dict[str, Any] | None = None,
        ) -> ProviderResponse:
            has_tool_calls = bool(response.tool_calls) if allow_tool_calls else False
            has_content = bool((response.content or "").strip())
            if has_tool_calls or has_content:
                return response

            log_manager.emit(
                level="WARN",
                category="WORKFLOW",
                message=(
                    "execution_writer_empty_output_retry | "
                    f"session_id={session_id} | "
                    f"context={response_context}"
                ),
            )
            guardrail = (
                "[TERNION EMPTY OUTPUT GUARDRAIL]\n\n"
                "Your previous response was empty.\n"
                "Return exactly one of the following:\n"
                "1) A valid tool-calls response (if tools are needed), OR\n"
                "2) A non-empty deliverable response.\n"
                "Do not return an empty response."
            )
            last = messages[-1] if messages else None
            if last and last.role == MessageRole.USER and isinstance(last.content, str):
                last.content += "\n\n" + guardrail
            else:
                messages.append(ChatMessage(role=MessageRole.USER, content=guardrail))

            retry_response = await _call_with_timeout(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.3,
                timeout_seconds=writer_timeout,
                **(extra_kwargs or {}),
            )
            if supports_text_tools and allow_tool_calls and not retry_response.tool_calls:
                parsed_tool_calls = extract_tool_calls_from_text(retry_response.content)
                if parsed_tool_calls:
                    retry_response.tool_calls = parsed_tool_calls
                    retry_response.content = ""

            retry_has_tool_calls = bool(retry_response.tool_calls) if allow_tool_calls else False
            retry_has_content = bool((retry_response.content or "").strip())
            if not retry_has_tool_calls and not retry_has_content:
                log_manager.emit(
                    level="ERROR",
                    category="WORKFLOW",
                    message=(
                        "execution_writer_empty_output_retry_exhausted | "
                        f"session_id={session_id} | "
                        f"context={response_context}"
                    ),
                )
                raise ValueError("writer_returned_empty_output_after_retry")

            return retry_response

        async def _retry_writer_if_rewriting_stabilized_docs(
            response: ProviderResponse,
            *,
            extra_kwargs: dict[str, Any] | None = None,
        ) -> ProviderResponse:
            blocked_paths = _collect_stabilized_document_write_paths(
                response.tool_calls,
                stabilized_document_paths=stabilized_document_paths,
                workspace_root=state.get("workspace_root"),
                workspace_path_style=state.get("workspace_path_style"),
            )
            if not blocked_paths:
                return response

            log_manager.emit(
                level="INFO",
                category="GUARDRAIL",
                message=(
                    "execution_stabilized_document_soft_retry | "
                    f"session_id={session_id} | "
                    f"count={len(blocked_paths)}"
                ),
            )
            with contextlib.suppress(Exception):
                session_store.update_session(
                    session_id,
                    append_guardrail_events=[
                        {
                            "type": "stabilized_document_soft_retry",
                            "phase": "execution",
                            "role": "writer",
                            "blocked_paths": list(blocked_paths),
                        }
                    ],
                )

            feedback = _build_stabilized_document_guardrail_feedback(
                blocked_paths=blocked_paths,
                deliverable_type=deliverable_policy.deliverable_type.value,
                workspace_root=state.get("workspace_root"),
                workspace_path_style=state.get("workspace_path_style"),
            )
            last = messages[-1] if messages else None
            if last and last.role == MessageRole.USER and isinstance(last.content, str):
                last.content += "\n\n[TERNION DOCUMENT STABILITY GUARDRAIL]\n\n" + feedback
            else:
                messages.append(
                    ChatMessage(
                        role=MessageRole.USER,
                        content="[TERNION DOCUMENT STABILITY GUARDRAIL]\n\n" + feedback,
                    )
                )

            retry_response = await _call_with_timeout(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.3,
                timeout_seconds=writer_timeout,
                **(extra_kwargs or {}),
            )
            if supports_text_tools and not retry_response.tool_calls:
                parsed_tool_calls = extract_tool_calls_from_text(retry_response.content)
                if parsed_tool_calls:
                    retry_response.tool_calls = parsed_tool_calls
                    retry_response.content = ""
            return await _retry_writer_if_empty(
                retry_response,
                allow_tool_calls=True,
                response_context="stabilized_document_guardrail_retry",
                extra_kwargs=extra_kwargs,
            )

        if supports_text_tools and messages:
            last_msg = messages[-1]
            if last_msg.role == MessageRole.USER and isinstance(last_msg.content, str):
                last_msg.content = (
                    last_msg.content
                    + "\n\n[NON-OPENAI TOOL CALLS]\n\n"
                    + build_text_tool_calls_instruction(cursor_tools)
                )

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "execution_writer_context | "
                f"session_id={session_id} | "
                f"history_messages={len(history)} | "
                f"history_truncated={truncated_history} | "
                f"digest_chars={len(tool_context_digest)} | "
                f"tools={len(cursor_tools)} | "
                f"revision_count={revision_count} | "
                f"timeout_seconds={writer_timeout}"
            ),
        )

        if should_use_tool_calls:
            extra_kwargs: dict[str, Any] = {}
            if supports_native_tools:
                extra_kwargs["tools"] = cursor_tools
                if cursor_tool_choice is not None:
                    extra_kwargs["tool_choice"] = cursor_tool_choice

            started = time.monotonic()
            if stream_queue:
                response = await _call_with_stream(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    stream_queue=stream_queue,
                    phase="execution",
                    message_id=session_id,
                    timeout_seconds=writer_timeout,
                    detect_tool_calls=True,
                    **extra_kwargs,
                )
            else:
                response = await _call_with_timeout(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    timeout_seconds=writer_timeout,
                    **extra_kwargs,
                )
            if supports_text_tools and not response.tool_calls:
                parsed_tool_calls = extract_tool_calls_from_text(response.content)
                if parsed_tool_calls:
                    response.tool_calls = parsed_tool_calls
                    response.content = ""
            elapsed = time.monotonic() - started
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "execution_writer_call_done | "
                    f"session_id={session_id} | "
                    f"elapsed_seconds={elapsed:.2f} | "
                    f"tool_calls={len(response.tool_calls or []) if response.tool_calls else 0} | "
                    f"content_chars={len(response.content or '')}"
                ),
            )
            usage = response.usage or {}
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
            thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
            output_for_cost = (
                completion_tokens
                if provider.name != "google"
                else completion_tokens + thoughts_tokens
            )
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            if input_tokens or output_for_cost or thoughts_tokens:
                log_manager.emit(
                    level="INFO",
                    category="WORKFLOW",
                    message=(
                        f"execution_usage | provider={provider.name} | "
                        f"model={model} | "
                        f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                        f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                    ),
                )
            if response.tool_calls:
                blocked_tools, blocked_shell = _detect_blocked_execution_tool_calls(
                    response.tool_calls
                )
                if blocked_tools or blocked_shell:
                    log_manager.emit(
                        level="INFO",
                        category="GUARDRAIL",
                        message=(
                            "execution_tool_policy_soft_retry | "
                            f"session_id={session_id} | "
                            f"blocked_tools={len(blocked_tools)} | "
                            f"blocked_shell={len(blocked_shell)}"
                        ),
                    )
                    try:
                        blocked_shell_session: list[dict[str, str]] = []
                        for item in blocked_shell:
                            tool = str(item.get("tool") or "Shell")
                            cmd = str(item.get("command") or "")
                            reason = str(item.get("reason") or "")
                            blocked_shell_session.append(
                                {
                                    "tool": tool,
                                    "command_preview": redact_secrets(cmd),
                                    "reason": reason,
                                }
                            )
                        session_store.update_session(
                            session_id,
                            append_guardrail_events=[
                                {
                                    "type": "execution_tool_policy_soft_retry",
                                    "phase": "execution",
                                    "role": "writer",
                                    "blocked_tools": list(blocked_tools or []),
                                    "blocked_shell": blocked_shell_session,
                                }
                            ],
                        )
                    except Exception:
                        pass
                    last = messages[-1] if messages else None
                    feedback = _build_tool_policy_guardrail_feedback(
                        blocked_tools=blocked_tools,
                        blocked_shell=blocked_shell,
                        role_label="Writer (execution)",
                    )
                    if last and last.role == MessageRole.USER and isinstance(last.content, str):
                        last.content += "\n\n[TERNION TOOL POLICY GUARDRAIL]\n\n" + feedback
                    else:
                        messages.append(
                            ChatMessage(
                                role=MessageRole.USER,
                                content="[TERNION TOOL POLICY GUARDRAIL]\n\n" + feedback,
                            )
                        )
                    # IMPORTANT: Use non-streaming retry to avoid duplicate phase-start
                    # indicators and noisy partial output in Cursor.
                    response = await _call_with_timeout(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.3,
                        timeout_seconds=writer_timeout,
                        **extra_kwargs,
                    )
                    if supports_text_tools and not response.tool_calls:
                        parsed_tool_calls = extract_tool_calls_from_text(response.content)
                        if parsed_tool_calls:
                            response.tool_calls = parsed_tool_calls
                            response.content = ""

                response = await _retry_writer_if_empty(
                    response,
                    allow_tool_calls=True,
                    response_context="tool_mode_primary",
                    extra_kwargs=extra_kwargs,
                )
                if response.tool_calls:
                    malformed = _detect_malformed_execution_tool_calls(response.tool_calls)
                    if malformed:
                        log_manager.emit(
                            level="INFO",
                            category="GUARDRAIL",
                            message=(
                                "execution_tool_call_validation_soft_retry | "
                                f"session_id={session_id} | "
                                f"issues={len(malformed)}"
                            ),
                        )
                        with contextlib.suppress(Exception):
                            session_store.update_session(
                                session_id,
                                append_guardrail_events=[
                                    {
                                        "type": "execution_tool_call_validation_soft_retry",
                                        "phase": "execution",
                                        "role": "writer",
                                        "issues": list(malformed[:20]),
                                        "issues_truncated": len(malformed) > 20,
                                    }
                                ],
                            )
                        last = messages[-1] if messages else None
                        feedback = _build_tool_call_validation_guardrail_feedback(
                            issues=malformed,
                            role_label="Writer (execution)",
                        )
                        if last and last.role == MessageRole.USER and isinstance(last.content, str):
                            last.content += "\n\n[TERNION TOOL CALL VALIDATION]\n\n" + feedback
                        else:
                            messages.append(
                                ChatMessage(
                                    role=MessageRole.USER,
                                    content="[TERNION TOOL CALL VALIDATION]\n\n" + feedback,
                                )
                            )

                        response = await _call_with_timeout(
                            provider=provider,
                            messages=messages,
                            model=model,
                            temperature=0.3,
                            timeout_seconds=writer_timeout,
                            **extra_kwargs,
                        )
                        if supports_text_tools and not response.tool_calls:
                            parsed_tool_calls = extract_tool_calls_from_text(response.content)
                            if parsed_tool_calls:
                                response.tool_calls = parsed_tool_calls
                                response.content = ""
                        response = await _retry_writer_if_empty(
                            response,
                            allow_tool_calls=True,
                            response_context="tool_mode_validation_retry",
                            extra_kwargs=extra_kwargs,
                        )
                if response.tool_calls:
                    response = await _retry_writer_if_rewriting_stabilized_docs(
                        response,
                        extra_kwargs=extra_kwargs,
                    )
                if response.tool_calls:
                    blocked_stabilized = _collect_stabilized_document_write_paths(
                        response.tool_calls,
                        stabilized_document_paths=stabilized_document_paths,
                        workspace_root=state.get("workspace_root"),
                        workspace_path_style=state.get("workspace_path_style"),
                    )
                    if blocked_stabilized:
                        log_manager.emit(
                            level="INFO",
                            category="GUARDRAIL",
                            message=(
                                "execution_stabilized_document_forced_optimizer | "
                                f"session_id={session_id} | "
                                f"count={len(blocked_stabilized)}"
                            ),
                        )
                        with contextlib.suppress(Exception):
                            session_store.update_session(
                                session_id,
                                append_guardrail_events=[
                                    {
                                        "type": "stabilized_document_forced_optimizer",
                                        "phase": "execution",
                                        "role": "writer",
                                        "blocked_paths": list(blocked_stabilized),
                                    }
                                ],
                            )
                        return {
                            **state,
                            "current_phase": WorkflowPhase.OPTIMIZER.value,
                            "thinking_logs": thinking_logs,
                        }
                if response.tool_calls:
                    log_manager.emit(
                        level="INFO",
                        category="WORKFLOW",
                        message=(
                            "execution_writer_tool_calls_ready | "
                            f"session_id={session_id} | "
                            f"count={len(response.tool_calls)}"
                        ),
                    )
                    return {
                        **state,
                        "current_phase": WorkflowPhase.EXECUTION.value,
                        "pending_tool_calls": response.tool_calls,
                        "thinking_logs": thinking_logs,
                    }
            response = await _retry_writer_if_empty(
                response,
                allow_tool_calls=True,
                response_context="tool_mode_post_processing",
                extra_kwargs=extra_kwargs,
            )
            topup_block = extract_evidence_requests_block(
                response.content,
                default_requester="execution",
            )
            if topup_block is not None:
                used_round = int(state.get("evidence_topup_round", 0) or 0)
                payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
                policy_error = _validate_evidence_topup_request(
                    used_round=used_round,
                    final_request=topup_block.final_request,
                )
                topup_error = payload_error or policy_error
                if topup_error:
                    # Soft handling: retry once to avoid an extra user round-trip.
                    last = messages[-1] if messages else None
                    if last and last.role == MessageRole.USER and isinstance(last.content, str):
                        last.content += (
                            "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                            f"{sanitize_for_cursor_display(topup_error)}\n\n"
                            "Proceed:\n"
                            "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                            "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                        )

                    response = await _call_with_stream(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.3,
                        stream_queue=stream_queue,
                        phase="execution",
                        message_id=session_id,
                        timeout_seconds=writer_timeout,
                        detect_tool_calls=True,
                        **extra_kwargs,
                    )
                    if supports_text_tools and not response.tool_calls:
                        parsed_tool_calls = extract_tool_calls_from_text(response.content)
                        if parsed_tool_calls:
                            response.tool_calls = parsed_tool_calls
                            response.content = ""
                    if response.tool_calls:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.EXECUTION.value,
                            "pending_tool_calls": response.tool_calls,
                            "thinking_logs": thinking_logs,
                        }
                    response = await _retry_writer_if_empty(
                        response,
                        allow_tool_calls=True,
                        response_context="topup_guardrail_retry_tool_mode",
                        extra_kwargs=extra_kwargs,
                    )
                    retry_block = extract_evidence_requests_block(
                        response.content,
                        default_requester="execution",
                    )
                    if retry_block is not None:
                        used_round = int(state.get("evidence_topup_round", 0) or 0)
                        payload_error = _validate_evidence_requests_payload(
                            retry_block.requests_text
                        )
                        policy_error = _validate_evidence_topup_request(
                            used_round=used_round,
                            final_request=retry_block.final_request,
                        )
                        topup_error = payload_error or policy_error
                        if topup_error:
                            return {
                                **state,
                                "current_phase": WorkflowPhase.COMPLETE.value,
                                "errors": state.get("errors", []) + [topup_error],
                                "final_output": sanitize_for_cursor_display(topup_error),
                                "thinking_logs": thinking_logs,
                            }
                        return {
                            **state,
                            "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                            "evidence_requests": retry_block.requests_text,
                            "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                            "evidence_topup_round": used_round + 1,
                            "thinking_logs": thinking_logs,
                        }
                else:
                    return {
                        **state,
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": topup_block.requests_text,
                        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                        "evidence_topup_round": used_round + 1,
                        "thinking_logs": thinking_logs,
                    }
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    "execution_writer_deliverable_done | "
                    f"session_id={session_id} | "
                    f"content_chars={len(response.content or '')}"
                ),
            )
            thinking_logs.append(t(MessageKey.EXECUTION_COMPLETE))
            return {
                **state,
                "current_phase": WorkflowPhase.OPTIMIZER.value,
                "generated_code": response.content,
                "thinking_logs": thinking_logs,
            }
        response = await _call_with_stream(
            provider=provider,
            messages=messages,
            model=model,
            temperature=0.3,  # Lower temperature for deterministic output
            stream_queue=stream_queue,
            phase="execution",
            message_id=session_id,
            timeout_seconds=writer_timeout,
        )
        response = await _retry_writer_if_empty(
            response,
            allow_tool_calls=False,
            response_context="deliverable_mode_primary",
        )
        topup_block = extract_evidence_requests_block(
            response.content,
            default_requester="execution",
        )
        if topup_block is not None:
            used_round = int(state.get("evidence_topup_round", 0) or 0)
            payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
            policy_error = _validate_evidence_topup_request(
                used_round=used_round,
                final_request=topup_block.final_request,
            )
            topup_error = payload_error or policy_error
            if topup_error:
                last = messages[-1] if messages else None
                if last and last.role == MessageRole.USER and isinstance(last.content, str):
                    last.content += (
                        "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                        f"{sanitize_for_cursor_display(topup_error)}\n\n"
                        "Proceed:\n"
                        "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                        "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                    )
                response = await _call_with_stream(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.3,
                    stream_queue=stream_queue,
                    phase="execution",
                    message_id=session_id,
                    timeout_seconds=writer_timeout,
                )
                response = await _retry_writer_if_empty(
                    response,
                    allow_tool_calls=False,
                    response_context="topup_guardrail_retry_deliverable_mode",
                )
                retry_block = extract_evidence_requests_block(
                    response.content,
                    default_requester="execution",
                )
                if retry_block is not None:
                    used_round = int(state.get("evidence_topup_round", 0) or 0)
                    payload_error = _validate_evidence_requests_payload(retry_block.requests_text)
                    policy_error = _validate_evidence_topup_request(
                        used_round=used_round,
                        final_request=retry_block.final_request,
                    )
                    topup_error = payload_error or policy_error
                    if topup_error:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.COMPLETE.value,
                            "errors": state.get("errors", []) + [topup_error],
                            "final_output": sanitize_for_cursor_display(topup_error),
                            "thinking_logs": thinking_logs,
                        }
                    return {
                        **state,
                        "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                        "evidence_requests": retry_block.requests_text,
                        "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                        "evidence_topup_round": used_round + 1,
                        "thinking_logs": thinking_logs,
                    }
            else:
                return {
                    **state,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": topup_block.requests_text,
                    "report_evidence_resume_phase": WorkflowPhase.EXECUTION.value,
                    "evidence_topup_round": used_round + 1,
                    "thinking_logs": thinking_logs,
                }
        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        thoughts_tokens = usage.get("thoughts_tokens") or usage.get("reasoning_tokens") or 0
        output_for_cost = (
            completion_tokens if provider.name != "google" else completion_tokens + thoughts_tokens
        )
        if input_tokens or output_for_cost or thoughts_tokens:
            budget_manager.record_usage(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_for_cost,
                thoughts_tokens=thoughts_tokens,
                context_length=usage.get("total_tokens", 0),
            )
            log_manager.emit(
                level="INFO",
                category="WORKFLOW",
                message=(
                    f"execution_usage | provider={provider.name} | "
                    f"model={model} | "
                    f"input={input_tokens} | output={output_for_cost} | thoughts={thoughts_tokens} | "
                    f"total={usage.get('total_tokens', input_tokens + output_for_cost)}"
                ),
            )

        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "execution_writer_deliverable_done | "
                f"session_id={session_id} | "
                f"content_chars={len(response.content or '')}"
            ),
        )
        thinking_logs.append(t(MessageKey.EXECUTION_COMPLETE))

        return {
            **state,
            "current_phase": WorkflowPhase.OPTIMIZER.value,
            "generated_code": response.content,
            "thinking_logs": thinking_logs,
        }
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.error(
            "execution_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "generated_code": "",
            "final_output": sanitize_for_cursor_display(error_msg),
            "errors": state.get("errors", []) + [error_msg],
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs + [t(MessageKey.EXECUTION_ERROR, error=error_msg)],
        }
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        log_manager.emit(
            level="ERROR",
            category="WORKFLOW",
            message=f"Execution failed | error={str(e)}",
        )
        error_msg = t(MessageKey.EXECUTION_FAILED, error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "generated_code": "",
            "final_output": error_msg,
            "errors": state.get("errors", []) + [error_msg],
            "thinking_logs": thinking_logs + [t(MessageKey.EXECUTION_ERROR, error=str(e))],
        }


async def optimizer_node(state: TernionState) -> TernionState:
    """
    Development override: Optimizer phase (replaces Reviewer gate).

    The Optimizer validates the implementation against acceptance criteria,
    applies only necessary improvements via tool calls, and finally outputs:
    - an internal optimizer report retained in the execution session (user-invisible)
    - a user-visible work summary report

    Args:
        state: Current LangGraph state dict containing session variables.

    Returns:
        Updated state dict transitioning to complete or handling errors.
    """
    logger.info("workflow_optimizer_start")
    log_manager.emit(
        level="INFO",
        category="WORKFLOW",
        message="Optimizer phase started | Validating and improving implementation",
    )

    thinking_logs = list(state.get("thinking_logs", []))

    user_config = config_store.load()
    language_code = user_config.language
    if language_code == "auto":
        language_code = user_config.browser_language or "en"
    language_name = get_language_name(language_code)
    instruction_template = get_optimizer_language_instruction_template()
    language_instruction = (
        instruction_template.format(language_name=language_name) if instruction_template else ""
    )
    optimizer_prompt_with_lang = build_optimizer_prompt(language_instruction=language_instruction)

    ternion_report = state.get("ternion_report", "")
    generated_code = state.get("generated_code", "")

    baseline = state.get("baseline_file_snapshots") or {}
    modified_files = state.get("modified_files") or []
    if not isinstance(modified_files, list):
        modified_files = []
    writer_output_files = state.get("writer_output_files") or {}

    history = state.get("conversation_history", [])
    latest_user_message = get_latest_user_message(history)
    history_len_before = len(history)
    tool_context_digest = ""
    truncated_history = False
    try:
        from ternion.utils.execution_history_compaction import (
            ExecutionHistoryCompactionConfig,
            compact_execution_history_for_writer,
        )

        history, tool_context_digest = compact_execution_history_for_writer(
            history,
            config=ExecutionHistoryCompactionConfig(),
        )
        truncated_history = len(history) != history_len_before
    except Exception:
        tool_context_digest = ""
        truncated_history = False

    cursor_tools = _filter_execution_cursor_tools(state.get("cursor_tools") or [])
    cursor_tool_choice = state.get("cursor_tool_choice")
    role_cfg = config_store.get_role_config("reviewer")

    messages: list[ChatMessage] = [
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=_prepend_global_security_rules(optimizer_prompt_with_lang),
        )
    ]

    for msg in history:
        messages.append(
            ChatMessage(
                role=MessageRole(msg["role"]),
                content=msg.get("content"),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
        )

    optimizer_instructions = _prepend_global_security_rules(optimizer_prompt_with_lang)
    evidence_bundle = str(state.get("evidence_bundle") or "EVIDENCE_BUNDLE:\n- None")
    evidence_gaps = str(state.get("evidence_gaps") or "EVIDENCE_GAPS:\n- None")
    evidence_chain_index = list(state.get("evidence_chain_index") or [])
    topup_round_used = int(state.get("evidence_topup_round", 0) or 0)
    deliverable_policy_text, evidence_chain_lines, topup_status_lines = (
        _build_execution_policy_context(
            ternion_report=ternion_report,
            latest_user_message=latest_user_message,
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
            evidence_chain_index=evidence_chain_index,
            evidence_topup_round=topup_round_used,
        )
    )

    content_parts: list[str] = [
        "[TERNION OPTIMIZER INSTRUCTIONS]\n\n",
        optimizer_instructions,
        "\n\n[TERNION ANALYSIS REPORT]\n\n",
        ternion_report,
        *evidence_chain_lines,
        "\n\n[DELIVERABLE POLICY]\n\n",
        deliverable_policy_text,
        *topup_status_lines,
    ]
    pytest_status = _format_last_pytest_status(state.get("tool_results_meta"))
    if pytest_status:
        content_parts.append(pytest_status)
    retry_policy = _format_optimizer_verification_retry_policy(state.get("tool_results_meta"))
    if retry_policy:
        content_parts.append(retry_policy)
    if tool_context_digest:
        content_parts.extend(
            [
                "\n\n[TERNION TOOL CONTEXT DIGEST]\n\n",
                tool_context_digest,
            ]
        )

    if modified_files:
        content_parts.extend(
            [
                "\n\n[MODIFIED FILES]\n\n",
                "\n".join(f"- {p}" for p in modified_files),
            ]
        )
        ruff_commands = _build_scoped_ruff_verification_commands(modified_files)
        if ruff_commands:
            content_parts.extend(
                [
                    "\n\n[SCOPED VERIFICATION COMMANDS]\n\n",
                    "Default Ruff verification (scoped to modified Python files; avoid `... .`):\n",
                    "\n".join(f"- {cmd}" for cmd in ruff_commands),
                ]
            )

    if baseline:
        content_parts.append("\n\n[ORIGINAL CODE BASELINE - PRE-CHANGE]\n\n")
        for path, content in baseline.items():
            content_parts.extend(
                [
                    f"\n\nFILE: {path}\n",
                    "-----\n",
                    content,
                    "\n-----\n",
                ]
            )

    if writer_output_files:
        content_parts.append("\n\n[WRITER OUTPUT FILES - POST-CHANGE]\n\n")
        for path, content in writer_output_files.items():
            content_parts.extend(
                [
                    f"\n\nFILE: {path}\n",
                    "-----\n",
                    content,
                    "\n-----\n",
                ]
            )

    if generated_code:
        content_parts.extend(
            [
                "\n\n[WRITER OUTPUT TEXT]\n\n",
                generated_code,
            ]
        )

    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content="".join(content_parts),
        )
    )

    try:
        provider = provider_manager.get_provider_for_role("reviewer")
        model = role_cfg.model if role_cfg and role_cfg.model else None
        if not model:
            logger.error("optimizer_model_not_configured")
            error_msg = t(
                MessageKey.ROLE_CONFIG_INCOMPLETE,
                missing_roles=_format_role_names(["optimizer"]),
            )
            return {
                **state,
                "errors": state.get("errors", []) + [error_msg],
                "thinking_logs": thinking_logs + [t(MessageKey.FINAL_CHECK_ERROR, error=error_msg)],
                "current_phase": WorkflowPhase.COMPLETE.value,
            }

        supports_native_tools = getattr(provider, "supports_native_tool_calls", False) is True
        supports_text_tools = bool(cursor_tools) and not supports_native_tools
        should_use_tool_calls = bool(cursor_tools) and (
            supports_native_tools or supports_text_tools
        )

        if supports_text_tools and messages:
            last_msg = messages[-1]
            if last_msg.role == MessageRole.USER and isinstance(last_msg.content, str):
                last_msg.content = (
                    last_msg.content
                    + "\n\n[NON-OPENAI TOOL CALLS]\n\n"
                    + build_text_tool_calls_instruction(cursor_tools)
                )

        session_id = state.get("session_id", "")
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "optimizer_context | "
                f"session_id={session_id} | "
                f"history_messages={len(history)} | "
                f"history_truncated={truncated_history} | "
                f"digest_chars={len(tool_context_digest)} | "
                f"tools={len(cursor_tools)} | "
                f"baseline_files={len(baseline)} | "
                f"writer_files={len(writer_output_files)}"
            ),
        )

        stream_queue: StreamEventQueue | None = state.get("_stream_queue")

        extra_kwargs: dict[str, Any] = {}
        if should_use_tool_calls and supports_native_tools:
            extra_kwargs["tools"] = cursor_tools
            if cursor_tool_choice is not None:
                extra_kwargs["tool_choice"] = cursor_tool_choice

        started = time.monotonic()
        optimizer_timeout = WRITER_TIMEOUT_SECONDS
        streamed_user_summary = False
        if stream_queue:
            response, streamed_user_summary = await _call_optimizer_with_stream(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.2,
                stream_queue=stream_queue,
                phase="optimizer",
                message_id=session_id,
                timeout_seconds=optimizer_timeout,
                detect_tool_calls=should_use_tool_calls,
                **extra_kwargs,
            )
        else:
            response = await _call_with_timeout(
                provider=provider,
                messages=messages,
                model=model,
                temperature=0.2,
                timeout_seconds=optimizer_timeout,
                **extra_kwargs,
            )
        if supports_text_tools and not response.tool_calls:
            parsed_tool_calls = extract_tool_calls_from_text(response.content)
            if parsed_tool_calls:
                response.tool_calls = parsed_tool_calls
                response.content = ""
        elapsed = time.monotonic() - started
        log_manager.emit(
            level="INFO",
            category="WORKFLOW",
            message=(
                "optimizer_call_done | "
                f"session_id={session_id} | "
                f"elapsed_seconds={elapsed:.2f} | "
                f"tool_calls={len(response.tool_calls or []) if response.tool_calls else 0} | "
                f"content_chars={len(response.content or '')}"
            ),
        )

        tool_policy_retry_used = False
        tool_call_validation_retry_used = False
        topup_guardrail_retry_used = False
        action_protocol_retry_used = False

        while True:
            if response.tool_calls:
                blocked_tools, blocked_shell = _detect_blocked_execution_tool_calls(
                    response.tool_calls
                )
                if blocked_tools or blocked_shell:
                    if tool_policy_retry_used:
                        malformed = _detect_malformed_execution_tool_calls(response.tool_calls)
                        if not malformed or tool_call_validation_retry_used:
                            return {
                                **state,
                                "current_phase": WorkflowPhase.OPTIMIZER.value,
                                "pending_tool_calls": response.tool_calls,
                                "thinking_logs": thinking_logs,
                            }
                    else:
                        tool_policy_retry_used = True
                        log_manager.emit(
                            level="INFO",
                            category="GUARDRAIL",
                            message=(
                                "optimizer_tool_policy_soft_retry | "
                                f"session_id={session_id} | "
                                f"blocked_tools={len(blocked_tools)} | "
                                f"blocked_shell={len(blocked_shell)}"
                            ),
                        )
                        try:
                            blocked_shell_session: list[dict[str, str]] = []
                            for item in blocked_shell:
                                tool = str(item.get("tool") or "Shell")
                                cmd = str(item.get("command") or "")
                                reason = str(item.get("reason") or "")
                                blocked_shell_session.append(
                                    {
                                        "tool": tool,
                                        "command_preview": redact_secrets(cmd),
                                        "reason": reason,
                                    }
                                )
                            session_store.update_session(
                                session_id,
                                append_guardrail_events=[
                                    {
                                        "type": "optimizer_tool_policy_soft_retry",
                                        "phase": "optimizer",
                                        "role": "optimizer",
                                        "blocked_tools": list(blocked_tools or []),
                                        "blocked_shell": blocked_shell_session,
                                    }
                                ],
                            )
                        except Exception:
                            pass
                        last = messages[-1] if messages else None
                        feedback = _build_tool_policy_guardrail_feedback(
                            blocked_tools=blocked_tools,
                            blocked_shell=blocked_shell,
                            role_label="Optimizer (optimizer)",
                        )
                        if last and last.role == MessageRole.USER and isinstance(last.content, str):
                            last.content += "\n\n[TERNION TOOL POLICY GUARDRAIL]\n\n" + feedback
                        else:
                            messages.append(
                                ChatMessage(
                                    role=MessageRole.USER,
                                    content="[TERNION TOOL POLICY GUARDRAIL]\n\n" + feedback,
                                )
                            )

                        response = await _call_with_timeout(
                            provider=provider,
                            messages=messages,
                            model=model,
                            temperature=0.2,
                            timeout_seconds=optimizer_timeout,
                            **extra_kwargs,
                        )
                        if supports_text_tools and not response.tool_calls:
                            parsed_tool_calls = extract_tool_calls_from_text(response.content)
                            if parsed_tool_calls:
                                response.tool_calls = parsed_tool_calls
                                response.content = ""
                        continue

                malformed = _detect_malformed_execution_tool_calls(response.tool_calls)
                if malformed:
                    if tool_call_validation_retry_used:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.OPTIMIZER.value,
                            "pending_tool_calls": response.tool_calls,
                            "thinking_logs": thinking_logs,
                        }
                    tool_call_validation_retry_used = True
                    log_manager.emit(
                        level="INFO",
                        category="GUARDRAIL",
                        message=(
                            "optimizer_tool_call_validation_soft_retry | "
                            f"session_id={session_id} | "
                            f"issues={len(malformed)}"
                        ),
                    )
                    with contextlib.suppress(Exception):
                        session_store.update_session(
                            session_id,
                            append_guardrail_events=[
                                {
                                    "type": "optimizer_tool_call_validation_soft_retry",
                                    "phase": "optimizer",
                                    "role": "optimizer",
                                    "issues": list(malformed[:20]),
                                    "issues_truncated": len(malformed) > 20,
                                }
                            ],
                        )
                    last = messages[-1] if messages else None
                    feedback = _build_tool_call_validation_guardrail_feedback(
                        issues=malformed,
                        role_label="Optimizer (optimizer)",
                    )
                    if last and last.role == MessageRole.USER and isinstance(last.content, str):
                        last.content += "\n\n[TERNION TOOL CALL VALIDATION]\n\n" + feedback
                    else:
                        messages.append(
                            ChatMessage(
                                role=MessageRole.USER,
                                content="[TERNION TOOL CALL VALIDATION]\n\n" + feedback,
                            )
                        )

                    response = await _call_with_timeout(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=0.2,
                        timeout_seconds=optimizer_timeout,
                        **extra_kwargs,
                    )
                    if supports_text_tools and not response.tool_calls:
                        parsed_tool_calls = extract_tool_calls_from_text(response.content)
                        if parsed_tool_calls:
                            response.tool_calls = parsed_tool_calls
                            response.content = ""
                    continue

                return {
                    **state,
                    "current_phase": WorkflowPhase.OPTIMIZER.value,
                    "pending_tool_calls": response.tool_calls,
                    "thinking_logs": thinking_logs,
                }

            topup_block = extract_evidence_requests_block(
                response.content,
                default_requester="optimizer",
            )
            if topup_block is not None:
                used_round = int(state.get("evidence_topup_round", 0) or 0)
                payload_error = _validate_evidence_requests_payload(topup_block.requests_text)
                policy_error = _validate_evidence_topup_request(
                    used_round=used_round,
                    final_request=topup_block.final_request,
                )
                topup_error = payload_error or policy_error
                if topup_error:
                    if topup_guardrail_retry_used:
                        return {
                            **state,
                            "current_phase": WorkflowPhase.COMPLETE.value,
                            "errors": state.get("errors", []) + [topup_error],
                            "final_output": sanitize_for_cursor_display(topup_error),
                            "thinking_logs": thinking_logs,
                        }
                    topup_guardrail_retry_used = True
                    last = messages[-1] if messages else None
                    if last and last.role == MessageRole.USER and isinstance(last.content, str):
                        last.content += (
                            "\n\n[TERNION EVIDENCE TOP-UP GUARDRAIL]\n\n"
                            f"{sanitize_for_cursor_display(topup_error)}\n\n"
                            "Proceed:\n"
                            "- If you still need evidence and TOPUP_ROUNDS_REMAINING > 0, re-issue the evidence top-up block with correct PURPOSE lines.\n"
                            "- If TOPUP_ROUNDS_REMAINING == 0, do NOT request more evidence. Proceed with the deliverable using existing evidence.\n"
                        )

                    if stream_queue:
                        response, _streamed_user_summary = await _call_optimizer_with_stream(
                            provider=provider,
                            messages=messages,
                            model=model,
                            temperature=0.2,
                            stream_queue=stream_queue,
                            phase="optimizer",
                            message_id=session_id,
                            timeout_seconds=optimizer_timeout,
                            detect_tool_calls=should_use_tool_calls,
                            **extra_kwargs,
                        )
                    else:
                        response = await _call_with_timeout(
                            provider=provider,
                            messages=messages,
                            model=model,
                            temperature=0.2,
                            timeout_seconds=optimizer_timeout,
                            **extra_kwargs,
                        )
                    if supports_text_tools and not response.tool_calls:
                        parsed_tool_calls = extract_tool_calls_from_text(response.content)
                        if parsed_tool_calls:
                            response.tool_calls = parsed_tool_calls
                            response.content = ""
                    continue

                return {
                    **state,
                    "current_phase": WorkflowPhase.REPORT_EVIDENCE.value,
                    "evidence_requests": topup_block.requests_text,
                    "report_evidence_resume_phase": WorkflowPhase.OPTIMIZER.value,
                    "evidence_topup_round": used_round + 1,
                    "thinking_logs": thinking_logs,
                }

            internal_report, user_summary = _split_optimizer_output(response.content or "")
            action_contract = _parse_optimizer_action_contract(internal_report)
            required_change_items = list(action_contract.get("required_change_items") or [])
            required_items_preview = _summarize_optimizer_required_change_items(
                required_change_items
            )

            if _should_retry_optimizer_action_protocol(action_contract):
                if action_protocol_retry_used:
                    fail_close_message = t(MessageKey.OPTIMIZER_ACTION_PROTOCOL_FAIL_CLOSE)
                    fail_close_safe = sanitize_for_cursor_display(fail_close_message)
                    log_manager.emit(
                        level="WARN",
                        category="GUARDRAIL",
                        message=(
                            "optimizer_action_protocol_fail_close | "
                            f"session_id={session_id} | "
                            f"protocol_valid={bool(action_contract.get('protocol_valid'))} | "
                            f"action_required={action_contract.get('action_required')} | "
                            f"action_taken={action_contract.get('action_taken') or '(missing)'} | "
                            f"required_items={required_items_preview}"
                        ),
                    )
                    with contextlib.suppress(Exception):
                        session_store.update_session(
                            session_id,
                            append_guardrail_events=[
                                {
                                    "type": "optimizer_action_protocol_fail_close",
                                    "phase": "optimizer",
                                    "role": "optimizer",
                                    "protocol_valid": bool(action_contract.get("protocol_valid")),
                                    "action_required": action_contract.get("action_required"),
                                    "action_taken": str(action_contract.get("action_taken") or ""),
                                    "action_reason": str(
                                        action_contract.get("action_reason") or ""
                                    ),
                                    "required_change_items": required_change_items[:20],
                                    "required_change_items_truncated": len(required_change_items)
                                    > 20,
                                }
                            ],
                        )
                    if stream_queue and fail_close_safe and not streamed_user_summary:
                        for i in range(0, len(fail_close_safe), 128):
                            await stream_queue.put_token(
                                delta=fail_close_safe[i : i + 128],
                                phase="optimizer",
                                message_id=session_id,
                            )

                    return {
                        **state,
                        "current_phase": WorkflowPhase.COMPLETE.value,
                        "optimizer_review_report": internal_report,
                        "final_output": fail_close_safe,
                        "thinking_logs": thinking_logs,
                    }

                action_protocol_retry_used = True
                log_manager.emit(
                    level="INFO",
                    category="GUARDRAIL",
                    message=(
                        "optimizer_action_protocol_soft_retry | "
                        f"session_id={session_id} | "
                        f"protocol_valid={bool(action_contract.get('protocol_valid'))} | "
                        f"action_required={action_contract.get('action_required')} | "
                        f"action_taken={action_contract.get('action_taken') or '(missing)'} | "
                        f"required_items={required_items_preview}"
                    ),
                )
                with contextlib.suppress(Exception):
                    session_store.update_session(
                        session_id,
                        append_guardrail_events=[
                            {
                                "type": "optimizer_action_protocol_soft_retry",
                                "phase": "optimizer",
                                "role": "optimizer",
                                "protocol_valid": bool(action_contract.get("protocol_valid")),
                                "action_required": action_contract.get("action_required"),
                                "action_taken": str(action_contract.get("action_taken") or ""),
                                "action_reason": str(action_contract.get("action_reason") or ""),
                                "required_change_items": required_change_items[:20],
                                "required_change_items_truncated": len(required_change_items) > 20,
                            }
                        ],
                    )
                last = messages[-1] if messages else None
                feedback = _build_optimizer_action_protocol_feedback(action_contract)
                if last and last.role == MessageRole.USER and isinstance(last.content, str):
                    last.content += "\n\n[TERNION OPTIMIZER ACTION PROTOCOL]\n\n" + feedback
                else:
                    messages.append(
                        ChatMessage(
                            role=MessageRole.USER,
                            content="[TERNION OPTIMIZER ACTION PROTOCOL]\n\n" + feedback,
                        )
                    )

                response = await _call_with_timeout(
                    provider=provider,
                    messages=messages,
                    model=model,
                    temperature=0.2,
                    timeout_seconds=optimizer_timeout,
                    **extra_kwargs,
                )
                if supports_text_tools and not response.tool_calls:
                    parsed_tool_calls = extract_tool_calls_from_text(response.content)
                    if parsed_tool_calls:
                        response.tool_calls = parsed_tool_calls
                        response.content = ""
                streamed_user_summary = False
                continue

            if not (user_summary or "").strip():
                user_summary = t(MessageKey.OPTIMIZER_OUTPUT_PROTOCOL_ERROR)
            user_summary_safe = sanitize_for_cursor_display(user_summary)
            if stream_queue and user_summary_safe and not streamed_user_summary:
                for i in range(0, len(user_summary_safe), 128):
                    await stream_queue.put_token(
                        delta=user_summary_safe[i : i + 128],
                        phase="optimizer",
                        message_id=session_id,
                    )

            return {
                **state,
                "current_phase": WorkflowPhase.COMPLETE.value,
                "optimizer_review_report": internal_report,
                "final_output": user_summary_safe,
                "thinking_logs": thinking_logs,
            }
    except RuntimeModelUnavailableError as e:
        error_msg = _build_runtime_model_unavailable_message(e)
        logger.warning(
            "optimizer_runtime_model_unavailable",
            provider=e.provider,
            model=e.model,
        )
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "runtime_error_payload": e.to_payload(),
            "thinking_logs": thinking_logs,
        }
    except Exception as e:
        logger.warning("optimizer_failed", error=str(e))
        log_manager.emit(
            level="WARN",
            category="WORKFLOW",
            message=f"Optimizer failed | error={str(e)}",
        )
        error_msg = t(MessageKey.OPTIMIZER_FAILED, error=str(e))
        return {
            **state,
            "current_phase": WorkflowPhase.COMPLETE.value,
            "errors": state.get("errors", []) + [error_msg],
            "final_output": sanitize_for_cursor_display(error_msg),
            "thinking_logs": thinking_logs,
        }
