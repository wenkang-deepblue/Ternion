"""
Session storage for Human-in-the-Loop.

Provides persistent session management for the confirmation gate workflow:
- Session creation after Ternion report generation
- Session lookup for follow-up requests
- Session state updates (stage transitions)

Sessions are stored as individual JSON files in ~/.ternion/sessions/
"""

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

from ternion.utils.log_manager import log_manager

logger = structlog.get_logger(__name__)


def _to_jsonable(value: Any) -> Any:
    """
    Convert a value into a JSON-serializable structure.

    This is required because some workflow/session fields may contain Pydantic
    models (e.g., multimodal content parts) that are not directly serializable
    by json.dump().
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]

    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]

    if isinstance(value, set):
        return [_to_jsonable(v) for v in sorted(value, key=lambda x: str(x))]

    # Pydantic v2 models (e.g., TextContent/ImageContent)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return _to_jsonable(value.model_dump())
        except Exception:
            return str(value)

    # Pydantic v1 compatibility
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return _to_jsonable(value.dict())
        except Exception:
            return str(value)

    return str(value)


class SessionStage(str, Enum):
    """Stage of a Ternion session lifecycle."""

    RCA_COMPLETE = "rca_complete"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTION_IN_PROGRESS = "execution_in_progress"
    AWAITING_TOOL_RESULTS = "awaiting_tool_results"
    REVIEW_IN_PROGRESS = "review_in_progress"
    OPTIMIZER_IN_PROGRESS = "optimizer_in_progress"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ExecutionMode(str, Enum):
    """Execution mode for code generation after confirmation."""

    TERNION_FULL = "ternion_full"
    CURSOR_HANDOFF = "cursor_handoff"


@dataclass
class Session:
    """
    A Ternion session representing one analysis case.

    Tracks the lifecycle from report generation through optional implementation.

    Report Storage Strategy:
    - ternion_report_raw: Original report content for internal use (Writer/Reviewer)
    - ternion_report_safe: Sanitized report for user-visible output (handoff, clarify, display)

    The safe version is generated once at session creation using sanitize_for_cursor_display()
    to ensure Cursor auto-apply triggers are broken.
    """

    session_id: str
    stage: SessionStage
    execution_mode: ExecutionMode
    ternion_report_raw: str  # Original report for internal use (Writer/Reviewer)
    ternion_report_safe: str  # Sanitized report for user-visible output
    report_hash: str
    created_at: str
    updated_at: str
    last_user_feedback: str = ""
    original_context: dict = field(default_factory=dict)
    generated_code: str = ""
    review_feedback: str = ""
    hash_verified: bool | None = None  # Hash verification result for offline analysis
    cursor_system_prompt: str = ""
    cursor_tools: list[dict[str, Any]] = field(default_factory=list)
    cursor_tool_choice: Any | None = None
    execution_messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Step 2: When a tool_calls response contains both mutation tools and shell verification,
    # the server may transparently split it into multiple batches without re-calling the LLM.
    deferred_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_results_raw: dict[str, str] = field(default_factory=dict)
    tool_results_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Tool-loop workspace state captured before executing pending tool calls.
    # This is used to detect and attribute potential Shell side effects.
    tool_loop_pre_git_status: dict[str, Any] = field(default_factory=dict)
    round_index: int = 0
    revision_count: int = 0
    workflow_phase: str = "execution"
    modified_files: list[str] = field(default_factory=list)
    baseline_file_snapshots: dict[str, str] = field(default_factory=dict)
    writer_output_files: dict[str, str] = field(default_factory=dict)
    optimizer_review_report: str = ""
    # Cursor UI: track whether a TodoWrite list has been created in this session.
    todo_written: bool = False
    optimizer_todo_written: bool = False
    optimizer_phase_announced: bool = False
    execution_phase_announced: bool = False
    confirmation_reason: str | None = None
    # Phase 1.5 evidence state (for report_evidence tool loop)
    evidence_bundle: str = ""
    evidence_gaps: str = ""
    evidence_requests: str = ""
    evidence_chain_index: list[dict[str, Any]] = field(default_factory=list)
    # Step E: Execution/Optimizer evidence top-ups via Phase 1.5 (max 2 rounds).
    evidence_topup_round: int = 0
    # When report_evidence is used as an execution-time top-up, resume back to this phase.
    # Valid values: "execution", "optimizer", or empty (default report-stage behavior).
    report_evidence_resume_phase: str = ""
    ternion_analyses: list[dict[str, Any]] = field(default_factory=list)
    # Traceability: key guardrail events and external output pointers (append-only).
    guardrail_events: list[dict[str, Any]] = field(default_factory=list)
    external_outputs_index: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ternion_report(self) -> str:
        """
        Backward compatibility property.

        Returns raw report for internal use. For user-visible output,
        always use ternion_report_safe explicitly.
        """
        return self.ternion_report_raw

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for JSON serialization."""
        data = asdict(self)
        data["stage"] = self.stage.value
        data["execution_mode"] = self.execution_mode.value
        return _to_jsonable(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Create session from dictionary with backward compatibility."""
        data["stage"] = SessionStage(data["stage"])
        data["execution_mode"] = ExecutionMode(data["execution_mode"])

        # Backward compatibility: migrate old single-field format to dual-field
        if "ternion_report_raw" not in data and "ternion_report" in data:
            from ternion.utils.cursor_safety import sanitize_for_cursor_display

            raw_report = data.pop("ternion_report")
            data["ternion_report_raw"] = raw_report
            data["ternion_report_safe"] = sanitize_for_cursor_display(raw_report)

        data.setdefault("confirmation_reason", None)
        data.setdefault("evidence_topup_round", 0)
        data.setdefault("report_evidence_resume_phase", "")
        data.setdefault("tool_call_index", {})
        data.setdefault("tool_loop_pre_git_status", {})
        data.setdefault("deferred_tool_calls", [])
        data.setdefault("guardrail_events", [])
        data.setdefault("external_outputs_index", [])

        return cls(**data)


_MAX_GUARDRAIL_EVENTS = 200
_MAX_EXTERNAL_OUTPUTS_INDEX = 200


def _now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _append_capped(
    items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    """
    Append new items and cap the merged list length.

    Args:
        items: Existing items (treated as empty when falsy)
        new_items: Items to append (non-dict entries are ignored)
        max_items: Maximum number of items to keep (keeps newest items)

    Returns:
        The merged list capped to `max_items` from the end.
    """
    if not new_items:
        return items
    merged = list(items or [])
    for item in new_items:
        if not isinstance(item, dict):
            continue
        merged.append(item)
    if len(merged) > max_items:
        merged = merged[-max_items:]
    return merged


def generate_session_id() -> str:
    """Generate a short, unique session ID."""
    return uuid.uuid4().hex[:12]


def compute_report_hash(report: str) -> str:
    """Compute hash of report content for verification."""
    return hashlib.sha256(report.encode()).hexdigest()[:16]


_TOOL_CALL_INDEX_ARGS_MAX_CHARS = 4_000
_TOOL_CALL_INDEX_ARGS_PREVIEW_CHARS = 800


def _sha256_16(text: str) -> str:
    """Return a short, stable hash for indexing/traceability."""
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def _extract_tool_call_index_entries(
    tool_calls: list[dict[str, Any]],
    *,
    workflow_phase: str,
    round_index: int,
) -> dict[str, dict[str, Any]]:
    """
    Build a persistent tool_call_id -> meta index from tool call payloads.
    """
    entries: dict[str, dict[str, Any]] = {}
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if not isinstance(tc_id, str) or not tc_id.strip():
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = fn.get("arguments")
        if arguments is None:
            args_str = "{}"
        elif isinstance(arguments, str):
            args_str = arguments
        else:
            args_str = json.dumps(arguments, ensure_ascii=False)

        meta: dict[str, Any] = {
            "tool_name": name.strip(),
            "workflow_phase": str(workflow_phase or ""),
            "round_index": int(round_index or 0),
            "tool_arguments_sha256_16": _sha256_16(args_str),
        }
        if len(args_str) <= _TOOL_CALL_INDEX_ARGS_MAX_CHARS:
            meta["tool_arguments"] = args_str
        else:
            preview = args_str[:_TOOL_CALL_INDEX_ARGS_PREVIEW_CHARS]
            if len(args_str) > _TOOL_CALL_INDEX_ARGS_PREVIEW_CHARS:
                preview = preview.rstrip() + "…"
            meta["tool_arguments_preview"] = preview
            meta["tool_arguments_truncated"] = True
            meta["tool_arguments_chars"] = len(args_str)

        entries[tc_id.strip()] = meta
    return entries


def _merge_tool_call_index(
    existing: dict[str, dict[str, Any]] | None,
    additions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = dict(existing or {})
    for key, value in (additions or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(value, dict):
            continue
        merged[key] = value
    return merged


class SessionStore:
    """
    Persistent session storage.

    Stores each session as an individual JSON file in ~/.ternion/sessions/.
    Sessions do not expire (per design decision).
    """

    def __init__(self, sessions_dir: Path | None = None) -> None:
        """Initialize session store."""
        self.sessions_dir = sessions_dir or Path.home() / ".ternion" / "sessions"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        """Get file path for a session."""
        return self.sessions_dir / f"{session_id}.json"

    def create_session(
        self,
        ternion_report: str,
        execution_mode: ExecutionMode,
        original_context: dict | None = None,
        *,
        stage: SessionStage = SessionStage.AWAITING_CONFIRMATION,
        cursor_system_prompt: str = "",
        cursor_tools: list[dict[str, Any]] | None = None,
        cursor_tool_choice: Any | None = None,
        execution_messages: list[dict[str, Any]] | None = None,
        pending_tool_calls: list[dict[str, Any]] | None = None,
        deferred_tool_calls: list[dict[str, Any]] | None = None,
        tool_call_index: dict[str, dict[str, Any]] | None = None,
        tool_results_raw: dict[str, str] | None = None,
        tool_results_meta: dict[str, dict[str, Any]] | None = None,
        round_index: int = 0,
        revision_count: int = 0,
        workflow_phase: str = "execution",
        modified_files: list[str] | None = None,
        baseline_file_snapshots: dict[str, str] | None = None,
        writer_output_files: dict[str, str] | None = None,
        optimizer_review_report: str = "",
        optimizer_todo_written: bool = False,
        optimizer_phase_announced: bool = False,
        execution_phase_announced: bool = False,
        evidence_bundle: str = "",
        evidence_gaps: str = "",
        evidence_requests: str = "",
        evidence_chain_index: list[dict[str, Any]] | None = None,
        evidence_topup_round: int = 0,
        report_evidence_resume_phase: str = "",
        ternion_analyses: list[dict[str, Any]] | None = None,
    ) -> Session:
        """
        Create a new session after Ternion report generation.

        Generates both raw and safe versions of the report:
        - raw: Used internally by Writer/Reviewer
        - safe: Used for all user-visible output (handoff, clarify, display)

        Args:
            ternion_report: The generated Ternion analysis report
            execution_mode: The configured execution mode
            original_context: Original conversation context for potential re-analysis

        Returns:
            The created Session object
        """
        from ternion.utils.cursor_safety import sanitize_for_cursor_display

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Generate safe version once at creation time
        safe_report = sanitize_for_cursor_display(ternion_report)

        pending_calls = list(pending_tool_calls or [])
        if tool_call_index is None and pending_calls:
            tool_call_index = _extract_tool_call_index_entries(
                pending_calls,
                workflow_phase=workflow_phase,
                round_index=round_index,
            )

        session = Session(
            session_id=generate_session_id(),
            stage=stage,
            execution_mode=execution_mode,
            ternion_report_raw=ternion_report,
            ternion_report_safe=safe_report,
            report_hash=compute_report_hash(ternion_report),
            created_at=now,
            updated_at=now,
            original_context=original_context or {},
            cursor_system_prompt=cursor_system_prompt,
            cursor_tools=list(cursor_tools or []),
            cursor_tool_choice=cursor_tool_choice,
            execution_messages=list(execution_messages or []),
            pending_tool_calls=pending_calls,
            deferred_tool_calls=list(deferred_tool_calls or []),
            tool_call_index=dict(tool_call_index or {}),
            tool_results_raw=dict(tool_results_raw or {}),
            tool_results_meta=dict(tool_results_meta or {}),
            round_index=round_index,
            revision_count=revision_count,
            workflow_phase=workflow_phase,
            modified_files=list(modified_files or []),
            baseline_file_snapshots=dict(baseline_file_snapshots or {}),
            writer_output_files=dict(writer_output_files or {}),
            optimizer_review_report=optimizer_review_report,
            optimizer_todo_written=optimizer_todo_written,
            optimizer_phase_announced=optimizer_phase_announced,
            execution_phase_announced=execution_phase_announced,
            evidence_bundle=evidence_bundle,
            evidence_gaps=evidence_gaps,
            evidence_requests=evidence_requests,
            evidence_chain_index=list(evidence_chain_index or []),
            evidence_topup_round=int(evidence_topup_round or 0),
            report_evidence_resume_phase=str(report_evidence_resume_phase or ""),
            ternion_analyses=list(ternion_analyses or []),
        )

        self._save_session(session)
        logger.info(
            "session_created",
            session_id=session.session_id,
            execution_mode=execution_mode.value,
        )
        return session

    def _save_session(self, session: Session) -> None:
        """Save session to disk using atomic write (tmp + replace).

        Uses a temporary file + os.replace pattern to ensure atomicity:
        - Write completes fully to temp file first
        - os.replace is atomic on POSIX systems
        - If interrupted, only temp file is corrupted (cleaned up)
        """
        path = self._get_session_path(session.session_id)
        # Create temp file in same directory (required for atomic rename on same filesystem)
        fd, tmp_path = tempfile.mkstemp(dir=self.sessions_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)  # Atomic on POSIX
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def load_session(self, session_id: str) -> Session | None:
        """
        Load a session by ID.

        Args:
            session_id: The session identifier

        Returns:
            The Session object if found, None otherwise
        """
        path = self._get_session_path(session_id)
        if not path.exists():
            logger.debug("session_not_found", session_id=session_id)
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("session_load_failed", session_id=session_id, error=str(e))
            log_manager.emit(
                level="WARN",
                category="SESSION",
                message=f"Session load failed (corrupted or invalid) | session_id={session_id} | error={str(e)[:100]}",
            )
            return None

    def update_session(
        self,
        session_id: str,
        stage: SessionStage | None = None,
        last_user_feedback: str | None = None,
        generated_code: str | None = None,
        review_feedback: str | None = None,
        hash_verified: bool | None = None,
        ternion_report_raw: str | None = None,
        cursor_system_prompt: str | None = None,
        cursor_tools: list[dict[str, Any]] | None = None,
        cursor_tool_choice: Any | None = None,
        execution_messages: list[dict[str, Any]] | None = None,
        pending_tool_calls: list[dict[str, Any]] | None = None,
        deferred_tool_calls: list[dict[str, Any]] | None = None,
        tool_call_index: dict[str, dict[str, Any]] | None = None,
        tool_results_raw: dict[str, str] | None = None,
        tool_results_meta: dict[str, dict[str, Any]] | None = None,
        tool_loop_pre_git_status: dict[str, Any] | None = None,
        round_index: int | None = None,
        revision_count: int | None = None,
        workflow_phase: str | None = None,
        modified_files: list[str] | None = None,
        baseline_file_snapshots: dict[str, str] | None = None,
        writer_output_files: dict[str, str] | None = None,
        optimizer_review_report: str | None = None,
        todo_written: bool | None = None,
        optimizer_todo_written: bool | None = None,
        optimizer_phase_announced: bool | None = None,
        execution_phase_announced: bool | None = None,
        confirmation_reason: str | None = None,
        evidence_bundle: str | None = None,
        evidence_gaps: str | None = None,
        evidence_requests: str | None = None,
        evidence_chain_index: list[dict[str, Any]] | None = None,
        evidence_topup_round: int | None = None,
        report_evidence_resume_phase: str | None = None,
        ternion_analyses: list[dict[str, Any]] | None = None,
        append_guardrail_events: list[dict[str, Any]] | None = None,
        append_external_outputs_index: list[dict[str, Any]] | None = None,
    ) -> Session | None:
        """
        Update a session with new values.

        Args:
            session_id: The session identifier.
            stage: New session stage (optional).
            last_user_feedback: Latest user rejection/clarification feedback (optional).
            generated_code: Generated code from Writer (optional).
            review_feedback: Feedback from Reviewer/Optimizer (optional).
            hash_verified: Report hash verification result (optional, for offline analysis).
            ternion_report_raw: Raw report content used for internal phases (optional).
            cursor_system_prompt: Captured Cursor system prompt (optional).
            cursor_tools: Captured Cursor tools schema (optional).
            cursor_tool_choice: Captured Cursor tool_choice payload (optional).
            execution_messages: Execution-time conversation messages (optional).
            pending_tool_calls: Tool calls awaiting execution (optional).
            deferred_tool_calls: Tool calls deferred for later execution (optional).
            tool_call_index: tool_call_id -> meta index for traceability (optional).
            tool_results_raw: tool_call_id -> raw tool output string (optional).
            tool_results_meta: tool_call_id -> metadata dict (optional).
            tool_loop_pre_git_status: Workspace state snapshot before tool loop (optional).
            round_index: Workflow round index (optional).
            revision_count: Number of user-driven revisions (optional).
            workflow_phase: Current workflow phase label (optional).
            modified_files: Files modified during execution (optional).
            baseline_file_snapshots: Filepath -> baseline content snapshots (optional).
            writer_output_files: Writer-produced output file index (optional).
            optimizer_review_report: Optimizer review report text (optional).
            todo_written: Whether a TodoWrite list has been created (optional).
            optimizer_todo_written: Whether Optimizer TodoWrite list has been created (optional).
            optimizer_phase_announced: Whether Optimizer phase was announced (optional).
            execution_phase_announced: Whether execution phase was announced (optional).
            confirmation_reason: Explanation for confirmation gate decision (optional).
            evidence_bundle: Phase 1.5 evidence bundle content (optional).
            evidence_gaps: Phase 1.5 evidence gaps content (optional).
            evidence_requests: Phase 1.5 evidence requests content (optional).
            evidence_chain_index: Evidence chain index entries (optional).
            evidence_topup_round: Execution-time evidence top-up round counter (optional).
            report_evidence_resume_phase: Phase to resume after report_evidence (optional).
            ternion_analyses: Divergence/convergence analyses payload (optional).
            append_guardrail_events: Events appended to guardrail event log (optional).
            append_external_outputs_index: Events appended to external outputs index (optional).

        Returns:
            Updated Session object, or None if not found
        """
        session = self.load_session(session_id)
        if session is None:
            return None

        if stage is not None:
            session.stage = stage
        if last_user_feedback is not None:
            session.last_user_feedback = last_user_feedback
        if generated_code is not None:
            session.generated_code = generated_code
        if review_feedback is not None:
            session.review_feedback = review_feedback
        if hash_verified is not None:
            session.hash_verified = hash_verified
        if ternion_report_raw is not None:
            # Some sessions are created before convergence (e.g., evidence tool loops in ternion_full),
            # so the report may be initially empty and must be persisted later once available.
            from ternion.utils.cursor_safety import sanitize_for_cursor_display

            session.ternion_report_raw = ternion_report_raw
            session.ternion_report_safe = sanitize_for_cursor_display(ternion_report_raw)
            session.report_hash = compute_report_hash(ternion_report_raw)
            # Report changed -> previous hash verification is no longer meaningful.
            session.hash_verified = None
        if cursor_system_prompt is not None:
            session.cursor_system_prompt = cursor_system_prompt
        if cursor_tools is not None:
            session.cursor_tools = cursor_tools
        if cursor_tool_choice is not None:
            session.cursor_tool_choice = cursor_tool_choice
        if execution_messages is not None:
            session.execution_messages = execution_messages
        if pending_tool_calls is not None:
            session.pending_tool_calls = pending_tool_calls
        if deferred_tool_calls is not None:
            session.deferred_tool_calls = deferred_tool_calls
        if tool_results_raw is not None:
            session.tool_results_raw = tool_results_raw
        if tool_results_meta is not None:
            session.tool_results_meta = tool_results_meta
        if tool_loop_pre_git_status is not None:
            session.tool_loop_pre_git_status = tool_loop_pre_git_status
        if round_index is not None:
            session.round_index = round_index
        if revision_count is not None:
            session.revision_count = revision_count
        if workflow_phase is not None:
            session.workflow_phase = workflow_phase
        if modified_files is not None:
            session.modified_files = modified_files
        if baseline_file_snapshots is not None:
            session.baseline_file_snapshots = baseline_file_snapshots
        if writer_output_files is not None:
            session.writer_output_files = writer_output_files
        if optimizer_review_report is not None:
            session.optimizer_review_report = optimizer_review_report
        if todo_written is not None:
            session.todo_written = todo_written
        if optimizer_todo_written is not None:
            session.optimizer_todo_written = optimizer_todo_written
        if optimizer_phase_announced is not None:
            session.optimizer_phase_announced = optimizer_phase_announced
        if execution_phase_announced is not None:
            session.execution_phase_announced = execution_phase_announced
        if confirmation_reason is not None:
            session.confirmation_reason = confirmation_reason
        if evidence_bundle is not None:
            session.evidence_bundle = evidence_bundle
        if evidence_gaps is not None:
            session.evidence_gaps = evidence_gaps
        if evidence_requests is not None:
            session.evidence_requests = evidence_requests
        if evidence_chain_index is not None:
            session.evidence_chain_index = evidence_chain_index
        if evidence_topup_round is not None:
            session.evidence_topup_round = int(evidence_topup_round or 0)
        if report_evidence_resume_phase is not None:
            session.report_evidence_resume_phase = str(report_evidence_resume_phase or "")
        if ternion_analyses is not None:
            session.ternion_analyses = ternion_analyses

        if append_guardrail_events:
            normalized: list[dict[str, Any]] = []
            for event in append_guardrail_events:
                if not isinstance(event, dict):
                    continue
                item = dict(event)
                item.setdefault("ts", _now_iso_z())
                item.setdefault("phase", str(session.workflow_phase or ""))
                normalized.append(item)
            if normalized:
                session.guardrail_events = _append_capped(
                    list(getattr(session, "guardrail_events", []) or []),
                    normalized,
                    max_items=_MAX_GUARDRAIL_EVENTS,
                )

        if append_external_outputs_index:
            normalized_out: list[dict[str, Any]] = []
            for entry in append_external_outputs_index:
                if not isinstance(entry, dict):
                    continue
                item = dict(entry)
                item.setdefault("ts", _now_iso_z())
                item.setdefault("phase", str(session.workflow_phase or ""))
                normalized_out.append(item)
            if normalized_out:
                session.external_outputs_index = _append_capped(
                    list(getattr(session, "external_outputs_index", []) or []),
                    normalized_out,
                    max_items=_MAX_EXTERNAL_OUTPUTS_INDEX,
                )

        if tool_call_index is not None:
            session.tool_call_index = tool_call_index
        elif pending_tool_calls is not None and pending_tool_calls:
            entries = _extract_tool_call_index_entries(
                list(pending_tool_calls),
                workflow_phase=str(session.workflow_phase or ""),
                round_index=int(session.round_index or 0),
            )
            if entries:
                session.tool_call_index = _merge_tool_call_index(
                    getattr(session, "tool_call_index", None),
                    entries,
                )

        session.updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._save_session(session)

        logger.info(
            "session_updated",
            session_id=session_id,
            stage=session.stage.value,
        )
        return session

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: The session identifier

        Returns:
            True if deleted, False if not found
        """
        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()
            logger.info("session_deleted", session_id=session_id)
            return True
        return False

    def list_sessions(self, stage: SessionStage | None = None) -> list[Session]:
        """
        List all sessions, optionally filtered by stage.

        Args:
            stage: Filter by this stage (optional)

        Returns:
            List of Session objects
        """
        sessions = []
        for path in self.sessions_dir.glob("*.json"):
            session = self.load_session(path.stem)
            if session is not None and (stage is None or session.stage == stage):
                sessions.append(session)

        # Sort by creation time, newest first
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def get_pending_sessions(self) -> list[Session]:
        """Get all sessions awaiting user confirmation."""
        return self.list_sessions(stage=SessionStage.AWAITING_CONFIRMATION)

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """
        Clean up sessions older than specified days.

        This is optional manual cleanup - sessions do not auto-expire.

        Args:
            days: Delete sessions older than this many days

        Returns:
            Number of sessions deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)
        deleted = 0

        for path in self.sessions_dir.glob("*.json"):
            session = self.load_session(path.stem)
            if session is not None:
                try:
                    created = datetime.fromisoformat(session.created_at.replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=UTC)
                    if created < cutoff:
                        self.delete_session(session.session_id)
                        deleted += 1
                except ValueError:
                    continue

        logger.info("session_cleanup_complete", deleted_count=deleted)
        return deleted


# Global session store instance
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get or create the global session store."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


# Convenience alias
session_store = get_session_store()
