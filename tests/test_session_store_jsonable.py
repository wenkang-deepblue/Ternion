import json

import pytest

from ternion.core.models import TextContent
from ternion.core.session_store import ExecutionMode, SessionStage, SessionStore


def test_session_store_persists_multimodal_text_content(tmp_path) -> None:
    """
    Session persistence must support OpenAI-style content parts.

    Cursor may send message content as a list of content parts (even when it is
    text-only). The session store must serialize these parts deterministically.
    """
    store = SessionStore(sessions_dir=tmp_path)
    execution_messages = [
        {
            "role": "user",
            "content": [TextContent(text="hello")],
            "name": None,
            "tool_calls": None,
            "tool_call_id": None,
        }
    ]

    session = store.create_session(
        ternion_report="REPORT",
        execution_mode=ExecutionMode.TERNION_FULL,
        stage=SessionStage.AWAITING_TOOL_RESULTS,
        execution_messages=execution_messages,
        workflow_phase="evidence",
    )

    session_path = tmp_path / f"{session.session_id}.json"
    assert session_path.exists()

    raw = json.loads(session_path.read_text(encoding="utf-8"))
    saved_messages = raw.get("execution_messages")
    assert isinstance(saved_messages, list)
    assert saved_messages, "Expected execution_messages to be persisted"

    saved_content = saved_messages[0].get("content")
    assert isinstance(saved_content, list)
    assert saved_content[0].get("type") == "text"
    assert saved_content[0].get("text") == "hello"

