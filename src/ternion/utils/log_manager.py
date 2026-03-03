"""
Log manager for Ternion observability.

Provides a centralized logging system for SSE streaming to the Web Control Panel.
"""

import asyncio
import contextlib
import os
from collections import deque
from datetime import UTC, datetime

from ternion.utils.secrets import redact_secrets


class LogManager:
    """Manages log entries for SSE streaming to observability panel."""

    def __init__(self, max_history: int = 500):
        self._history: deque[dict[str, object]] = deque(maxlen=max_history)
        self._subscribers: list[asyncio.Queue] = []

    def emit(self, level: str, category: str, message: str) -> None:
        """
        Emit a log entry to all subscribers.

        Note: Messages are automatically sanitized to redact API keys and
        other secrets before being stored or broadcast.

        Args:
            level: Log level (INFO, WARN, ERROR, DEBUG)
            category: Log category (SYSTEM, LLM, USER_ACTION, TOKEN_USAGE)
            message: Log message content
        """
        safe_message = redact_secrets(message)

        entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "category": category,
            "message": safe_message,
        }
        self._history.append(entry)
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(entry)

    def emit_token_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        thoughts_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """
        Emit a token usage log entry.

        Args:
            provider: Provider name (google, openai, anthropic)
            model: Model ID used
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            thoughts_tokens: Number of thinking tokens (Gemini 2.5+)
            total_tokens: Total token count
        """
        parts = [model]
        parts.append(f"input_token={prompt_tokens:,}")
        parts.append(f"output_token={completion_tokens:,}")
        if thoughts_tokens > 0:
            parts.append(f"thoughts_token={thoughts_tokens:,}")
        parts.append(f"total_token={total_tokens:,}")

        message = " | ".join(parts)

        self.emit("INFO", "TOKEN_USAGE", message)

    def emit_token_usage_interrupted(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        received_output_tokens: int,
        estimated_remaining: int,
        estimated_total: int,
    ) -> None:
        """
        Emit a token usage log entry for interrupted responses.

        Args:
            provider: Provider name
            model: Model ID used
            prompt_tokens: Number of input tokens
            received_output_tokens: Tokens from received content (estimated)
            estimated_remaining: Estimated tokens not received
            estimated_total: Estimated total token count
        """
        parts = [model]
        parts.append(f"input_token={prompt_tokens:,}")
        parts.append(f"output_token=~{received_output_tokens:,} (received)")
        parts.append(f"~estimated_total={estimated_total:,}")
        parts.append("⚠️ INTERRUPTED")

        message = " | ".join(parts)

        self.emit("WARN", "TOKEN_USAGE", message)

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to log stream."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from log stream."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_history(self) -> list[dict[str, object]]:
        """Get recent log history."""
        return list(self._history)


# Singleton instance
_DEFAULT_MAX_HISTORY = int(os.environ.get("TERNION_LOG_MAX_HISTORY", "500"))
log_manager = LogManager(max_history=_DEFAULT_MAX_HISTORY)
