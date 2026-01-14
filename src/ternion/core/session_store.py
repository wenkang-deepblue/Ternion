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
    tool_results_raw: dict[str, str] = field(default_factory=dict)
    tool_results_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    round_index: int = 0
    revision_count: int = 0
    workflow_phase: str = "execution"
    modified_files: list[str] = field(default_factory=list)
    baseline_file_snapshots: dict[str, str] = field(default_factory=dict)
    writer_output_files: dict[str, str] = field(default_factory=dict)
    optimizer_review_report: str = ""
    optimizer_todo_written: bool = False
    optimizer_phase_announced: bool = False

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
        return data

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

        return cls(**data)


def generate_session_id() -> str:
    """Generate a short, unique session ID."""
    return uuid.uuid4().hex[:12]


def compute_report_hash(report: str) -> str:
    """Compute hash of report content for verification."""
    return hashlib.sha256(report.encode()).hexdigest()[:16]


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
            pending_tool_calls=list(pending_tool_calls or []),
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
        cursor_system_prompt: str | None = None,
        cursor_tools: list[dict[str, Any]] | None = None,
        cursor_tool_choice: Any | None = None,
        execution_messages: list[dict[str, Any]] | None = None,
        pending_tool_calls: list[dict[str, Any]] | None = None,
        tool_results_raw: dict[str, str] | None = None,
        tool_results_meta: dict[str, dict[str, Any]] | None = None,
        round_index: int | None = None,
        revision_count: int | None = None,
        workflow_phase: str | None = None,
        modified_files: list[str] | None = None,
        baseline_file_snapshots: dict[str, str] | None = None,
        writer_output_files: dict[str, str] | None = None,
        optimizer_review_report: str | None = None,
        optimizer_todo_written: bool | None = None,
        optimizer_phase_announced: bool | None = None,
    ) -> Session | None:
        """
        Update a session with new values.

        Args:
            session_id: The session identifier
            stage: New stage (optional)
            last_user_feedback: User's rejection/clarification feedback (optional)
            generated_code: Generated code from Writer (optional)
            review_feedback: Feedback from Reviewer (optional)
            hash_verified: Report hash verification result (optional, for offline analysis)

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
        if tool_results_raw is not None:
            session.tool_results_raw = tool_results_raw
        if tool_results_meta is not None:
            session.tool_results_meta = tool_results_meta
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
        if optimizer_todo_written is not None:
            session.optimizer_todo_written = optimizer_todo_written
        if optimizer_phase_announced is not None:
            session.optimizer_phase_announced = optimizer_phase_announced

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

        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = 0

        for path in self.sessions_dir.glob("*.json"):
            session = self.load_session(path.stem)
            if session is not None:
                try:
                    created = datetime.fromisoformat(
                        session.created_at.replace("Z", "+00:00")
                    )
                    if created.replace(tzinfo=None) < cutoff:
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
