"""
Internationalization (i18n) module for Ternion backend.

Provides localized messages for thinking stream logs and other user-facing
backend text. Language preference is stored in user configuration.
"""

from __future__ import annotations

import json
import threading
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import structlog

from ternion.core.config import (
    DEFAULT_BACKEND_PORT,
    DEFAULT_WEB_PORT,
    get_default_local_host,
    normalize_port,
)

# When adding a language, update this Literal AND the checks in
# _load_translations() and get_user_language().
Language = Literal["en", "zh", "es", "fr", "de", "ja", "ko"]

_TRANSLATIONS_PATH = Path(__file__).with_name("i18n_translations.json")
_translations_cache: dict[Language, dict[str, str]] | None = None
_translations_lock = threading.Lock()

logger = structlog.get_logger(__name__)


class MessageKey(str, Enum):
    """Keys for localized messages (logs, errors, UI text)."""

    # Evidence Stage Errors
    EVIDENCE_COLLECTION_FAILED = "evidence_collection_failed"
    REPORT_EVIDENCE_COLLECTION_FAILED = "report_evidence_collection_failed"

    DIVERGENCE_START = "divergence_start"
    DIVERGENCE_ANALYSIS = "divergence_analysis"
    DIVERGENCE_ANALYSIS_FAILED = "divergence_analysis_failed"
    CONVERGENCE_START = "convergence_start"
    CONVERGENCE_COMPLETE = "convergence_complete"
    CONVERGENCE_ERROR = "convergence_error"
    CONVERGENCE_ALL_ARBITERS_FAILED = "convergence_all_arbiters_failed"
    EXECUTION_START = "execution_start"
    EXECUTION_CONTINUE_AFTER_EVIDENCE = "execution_continue_after_evidence"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_ERROR = "execution_error"
    OPTIMIZER_START = "optimizer_start"
    OPTIMIZER_OUTPUT_PROTOCOL_ERROR = "optimizer_output_protocol_error"
    OPTIMIZER_ACTION_PROTOCOL_FAIL_CLOSE = "optimizer_action_protocol_fail_close"
    REVIEW_START = "review_start"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REVISION = "review_revision"
    FINAL_CHECK_ERROR = "final_check_error"

    # Convergence Fallback
    CONVERGENCE_FALLBACK_WARNING = "convergence_fallback_warning"
    CONVERGENCE_FALLBACK_CONFIRM = "convergence_fallback_confirm"

    # Validation Errors
    EXECUTION_MODE_MISSING = "execution_mode_missing"
    ROLE_CONFIG_INCOMPLETE = "role_config_incomplete"
    EXECUTION_REQUIRES_AGENT_MODE = "execution_requires_agent_mode"
    IMPLEMENTATION_STAGE_MISSING_FIELDS = "implementation_stage_missing_fields"

    # Provider Manager Errors
    NO_PROVIDERS_CONFIGURED = "no_providers_configured"
    ROLE_NOT_CONFIGURED = "role_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    EXECUTION_MODE_NOT_CONFIGURED = "execution_mode_not_configured"
    UNSUPPORTED_MODEL = "unsupported_model"
    NO_TERNION_ANALYSES_AVAILABLE = "no_ternion_analyses_available"

    # Budget Alerts
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_EXCEEDED_ERROR = "budget_exceeded_error"
    BUDGET_CONFIRM_REQUIRED = "budget_confirm_required"
    LOG_BUDGET_WARNING = "log_budget_warning"
    LOG_BUDGET_EXCEEDED = "log_budget_exceeded"
    LOG_BUDGET_IMPL_BLOCKED = "log_budget_impl_blocked"
    LOG_BUDGET_CONFIRM_REQUIRED = "log_budget_confirm_required"

    # Tool Loop Guardrails
    TOOL_LOOP_FAILSAFE_REACHED = "tool_loop_failsafe_reached"
    LOG_TOOL_LOOP_FAILSAFE_REACHED = "log_tool_loop_failsafe_reached"
    DELIVERABLE_POLICY_BLOCKED = "deliverable_policy_blocked"
    WORKSPACE_ROOT_UNRESOLVED = "workspace_root_unresolved"
    EXECUTION_TOOL_POLICY_BLOCKED = "execution_tool_policy_blocked"
    EVIDENCE_TOPUP_FINAL_REQUIRED = "evidence_topup_final_required"
    EVIDENCE_TOPUP_LIMIT_REACHED = "evidence_topup_limit_reached"
    EVIDENCE_TOPUP_REQUESTS_EMPTY = "evidence_topup_requests_empty"
    EVIDENCE_TOPUP_PURPOSE_REQUIRED = "evidence_topup_purpose_required"
    EVIDENCE_TOPUP_COLLECTING = "evidence_topup_collecting"
    EVIDENCE_TOPUP_COLLECTING_SECOND_ROUND = "evidence_topup_collecting_second_round"

    # Discussion Output (Cursor-facing UI text)
    DISCUSSION_NO_OUTPUT = "discussion_no_output"
    DISCUSSION_ERRORS_HEADER = "discussion_errors_header"
    DISCUSSION_WORKFLOW_ERROR = "discussion_workflow_error"

    # Workflow Errors (Cursor-facing UI text)
    ARBITER_FALLBACKS_FAILED = "arbiter_fallbacks_failed"
    EXECUTION_FAILED = "execution_failed"
    RUNTIME_MODEL_UNAVAILABLE = "runtime_model_unavailable"
    EXECUTION_NO_OUTPUT = "execution_no_output"
    REANALYSIS_COMPLETED = "reanalysis_completed"
    REVIEW_SKIPPED = "review_skipped"
    REVIEW_MAX_REVISIONS_REACHED = "review_max_revisions_reached"
    OPTIMIZER_FAILED = "optimizer_failed"

    # Tool Policy Placeholders (Cursor-facing UI text)
    TOOL_POLICY_NONE = "tool_policy_none"
    TOOL_POLICY_UNKNOWN_TOOL = "tool_policy_unknown_tool"
    TOOL_POLICY_UNKNOWN_TARGET = "tool_policy_unknown_target"
    TOOL_POLICY_SHELL = "tool_policy_shell"
    TOOL_POLICY_EMPTY_COMMAND = "tool_policy_empty_command"

    # Streaming Errors (Cursor-facing UI text)
    STREAM_ERROR_GENERIC = "stream_error_generic"
    STREAM_ERROR_INTERRUPTED = "stream_error_interrupted"

    # Authentication (API clients and tunneled Control Panel access)
    AUTH_TOKEN_REQUIRED = "auth_token_required"

    # Report Display (Cursor-facing UI text)
    REPORT_SECTION_ROOT_CAUSE_TITLE = "report_section_root_cause_title"
    REPORT_SECTION_EVIDENCE_TITLE = "report_section_evidence_title"
    REPORT_SECTION_SCOPE_TITLE = "report_section_scope_title"
    REPORT_SECTION_FIX_PLAN_TITLE = "report_section_fix_plan_title"
    REPORT_SECTION_VERIFICATION_TITLE = "report_section_verification_title"
    REPORT_SECTION_RISKS_TITLE = "report_section_risks_title"
    REPORT_SECTION_IF_NOT_EFFECTIVE_TITLE = "report_section_if_not_effective_title"
    REPORT_SECTION_MISSING_PLACEHOLDER = "report_section_missing_placeholder"
    REPORT_RAW_SESSION_NOTE = "report_raw_session_note"
    REPORT_CONFIRM_PROMPT = "report_confirm_prompt"
    REPORT_CONFIRM_PROMPT_CURSOR_HANDOFF = "report_confirm_prompt_cursor_handoff"
    EXECUTION_MODE_DESC_TERNION_FULL = "execution_mode_desc_ternion_full"
    EXECUTION_MODE_DESC_CURSOR_HANDOFF = "execution_mode_desc_cursor_handoff"

    # Clarify / Unknown intent / Session follow-up (Cursor-facing UI text)
    CLARIFY_ANSWER_WITH_EXCERPT = "clarify_answer_with_excerpt"
    CLARIFY_ANSWER_NO_EXCERPT = "clarify_answer_no_excerpt"
    CLARIFY_RESPONSE_TEMPLATE = "clarify_response_template"
    UNKNOWN_INTENT_RESPONSE = "unknown_intent_response"
    POST_EXEC_CURSOR_HANDOFF_REMINDER = "post_exec_cursor_handoff_reminder"
    POST_EXEC_TERNION_FULL_COMPLETE = "post_exec_ternion_full_complete"
    REJECTED_SESSION_GUIDANCE = "rejected_session_guidance"
    HANDOFF_PACKAGE_HEADER = "handoff_package_header"
    HANDOFF_PACKAGE_NEXT_ACTION = "handoff_package_next_action"


DEFAULT_LANGUAGE: Language = "en"


def _load_translations() -> dict[Language, dict[str, str]]:
    """
    Load backend translations from the bundled JSON file.

    Returns:
        Mapping of language code -> {message_key -> template}.
    """
    global _translations_cache

    if _translations_cache is not None:
        return _translations_cache

    with _translations_lock:
        if _translations_cache is not None:
            return _translations_cache

        try:
            raw = _TRANSLATIONS_PATH.read_text(encoding="utf-8")
            data: Any = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "i18n_translations_load_failed", path=str(_TRANSLATIONS_PATH), exc_info=True
            )
            return {}

        if not isinstance(data, dict):
            logger.warning(
                "i18n_translations_invalid_structure",
                path=str(_TRANSLATIONS_PATH),
                actual_type=type(data).__name__,
            )
            return {}

        out: dict[Language, dict[str, str]] = {}
        for lang, mapping in data.items():
            if lang not in ("en", "zh", "es", "fr", "de", "ja", "ko"):
                continue
            if not isinstance(mapping, dict):
                continue
            cleaned: dict[str, str] = {}
            for k, v in mapping.items():
                if isinstance(k, str) and isinstance(v, str):
                    cleaned[k] = v
            out[cast(Language, lang)] = cleaned

        if out:
            _translations_cache = out
        return out


def _load_user_config() -> object | None:
    """
    Best-effort user config load with import-time safety.

    Returns:
        Loaded config object if available; otherwise None.
    """
    try:
        from ternion.core.config_store import config_store

        return config_store.load()
    except Exception:
        logger.warning("i18n_user_config_load_failed", exc_info=True)
        return None


def get_embedded_panel_base_url() -> str:
    """Return the embedded Control Panel URL served from the backend port.

    Returns:
        The Control Panel URL for the embedded `/panel` mount.
    """
    config = _load_user_config()
    backend_port = DEFAULT_BACKEND_PORT
    if config is not None:
        ports = getattr(config, "ports", None)
        configured_port = getattr(ports, "backend", backend_port)
        backend_port = normalize_port(configured_port, DEFAULT_BACKEND_PORT)

    return f"http://{get_default_local_host()}:{backend_port}/panel"


@lru_cache(maxsize=1)
def has_embedded_panel_assets() -> bool:
    """Return whether packaged Control Panel assets are available.

    Returns:
        `True` when `web_static/index.html` exists, otherwise `False`.
    """
    panel_index = Path(__file__).resolve().parents[1] / "web_static" / "index.html"
    return panel_index.exists()


def get_web_base_url() -> str:
    """Return the Control Panel base URL for the current runtime mode.

    Returns:
        The embedded `/panel` URL when packaged assets are available, otherwise
        the standalone development web server URL from `ports.web`.
    """
    if has_embedded_panel_assets():
        return get_embedded_panel_base_url()

    config = _load_user_config()
    if config is None:
        return f"http://{get_default_local_host()}:{DEFAULT_WEB_PORT}"
    ports = getattr(config, "ports", None)
    port = normalize_port(getattr(ports, "web", DEFAULT_WEB_PORT), DEFAULT_WEB_PORT)
    return f"http://{get_default_local_host()}:{port}"


def get_user_language() -> Language:
    """Get user's preferred language from configuration."""
    config = _load_user_config()
    if config is None:
        return DEFAULT_LANGUAGE

    lang = getattr(config, "language", DEFAULT_LANGUAGE)

    # Handle "auto" language setting - use browser_language
    if lang == "auto":
        browser_lang = getattr(config, "browser_language", DEFAULT_LANGUAGE)
        if browser_lang in ("en", "zh", "es", "fr", "de", "ja", "ko"):
            return browser_lang
        return DEFAULT_LANGUAGE

    if lang in ("en", "zh", "es", "fr", "de", "ja", "ko"):
        return lang

    return DEFAULT_LANGUAGE


def t(key: MessageKey, **kwargs: str) -> str:
    """
    Get translated string for the given key.

    Args:
        key: Translation key from MessageKey enum
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated and formatted string
    """
    lang = get_user_language()

    translations = _load_translations()

    template = translations.get(lang, {}).get(key.value)
    if not template:
        template = translations.get(DEFAULT_LANGUAGE, {}).get(key.value, key.value)

    if "{web_url}" in template and "web_url" not in kwargs:
        kwargs["web_url"] = get_web_base_url()

    try:
        return template.format(**kwargs)
    except KeyError:
        return template  # Return unformatted on error
