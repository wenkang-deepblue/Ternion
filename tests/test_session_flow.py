"""
End-to-end tests for session flow scenarios.

Tests the complete flow from RCA through confirmation/rejection/clarification
with mocked providers. Verifies:
- Session stage transitions
- Output safety (no code fence triggers)
- Correct role invocation patterns
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ternion.core.config_store import RoleConfig
from ternion.core.intent_classifier import Intent
from ternion.core.session_store import ExecutionMode, Session, SessionStage
from ternion.server.app import app

# Dangerous patterns that should not appear in user-facing output
CODE_FENCE_PATTERNS = [
    r"^```",  # Code fence start
    r"^~~~",  # Alternative code fence
    r"\*\*\* Begin Patch",  # Patch trigger
    r"diff --git",  # Git diff trigger
]


def contains_code_fence_trigger(text: str) -> bool:
    """Check if text contains patterns that could trigger Cursor auto-apply."""
    return any(re.search(pattern, text, re.MULTILINE) for pattern in CODE_FENCE_PATTERNS)


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_user_config() -> MagicMock:
    """Create mock user config with all roles configured."""
    config = MagicMock()
    config.execution_mode = "cursor_handoff"
    config.show_thinking_logs = True
    config.roles = {
        "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
        "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
        "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
        "arbiter": RoleConfig(provider="openai", model="gpt-4"),
        "writer": RoleConfig(provider="openai", model="gpt-4"),
        "reviewer": RoleConfig(provider="openai", model="gpt-4"),
    }
    mock_provider = MagicMock()
    mock_provider.api_keys = [MagicMock()]
    mock_provider.selected_key_id = "test-key-id"
    config.providers = {"openai": mock_provider}
    return config


@pytest.fixture
def mock_session_awaiting() -> Session:
    """Create a mock session in AWAITING_CONFIRMATION state."""
    raw_report = """## Root Cause
- Primary verdict: A null pointer/None access is triggered under a specific runtime path.
- Confidence: Medium — limited evidence in the provided context; needs targeted verification.

## Evidence / Logs
- Symptom: crash/exception observed when executing the reported flow.
- Error keyword: "NoneType" / "null pointer" exception.
- Location hint: referenced around "line 42" in the reported stack trace.

## Scope & Non-Goals
- In Scope: minimal fix to prevent the null access and add a regression check.
- Out of Scope: broad refactors or behavior changes outside the failing path.

## Fix Plan / Recommendation
- Step 1: Identify the None/null source and add a defensive guard at the entry point.
- Step 2: Ensure the upstream caller validates inputs before invoking the failing function.
- Step 3: Add a focused regression test for the failing scenario.

## Verification
### User Verification
- Re-run the original scenario and confirm the exception no longer occurs.
- Validate the observed behavior matches expectation for the edge case.
### Implementer Verification
- Run existing unit tests and ensure the new regression test passes.
- Review edge cases around missing/empty inputs for the guarded path.

## Risks & Rollback
- Risk: over-guarding could mask an upstream data issue.
- Rollback: revert the guard change and remove the added regression test if needed.

## If not effective, then what?
- Alternative hypothesis: a different call path triggers the exception with different inputs.
- Next step: compare stack traces and isolate which input variant reproduces the crash."""
    return Session(
        session_id="test123abc",
        stage=SessionStage.AWAITING_CONFIRMATION,
        execution_mode=ExecutionMode.CURSOR_HANDOFF,
        ternion_report_raw=raw_report,
        ternion_report_safe=raw_report,  # No triggers in this simple text
        report_hash="abc123",
        created_at="2026-01-04T12:00:00Z",
        updated_at="2026-01-04T12:00:00Z",
        original_context={
            "conversation_history": [],
            "cursor_system_prompt": "You are a helpful assistant.",
        },
    )


class TestRCAToConfirmHandoff:
    """Test RCA → Report → Confirm → Handoff flow (CURSOR_HANDOFF mode)."""

    def test_confirm_generates_handoff_package(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Confirm intent should generate handoff package without code fences."""
        mock_session_awaiting.execution_mode = ExecutionMode.CURSOR_HANDOFF

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CONFIRM

            # Simulate follow-up message with session marker
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "TERNION_SESSION_ID=test123abc\nTERNION_REPORT_HASH=abc123",
                        },
                        {"role": "user", "content": "Yes, proceed with this analysis"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Verify handoff package structure
            assert "Cursor Handoff Package" in content or "Cursor 交接包" in content
            assert "Root Cause" in content or "根因" in content
            assert (
                "Fix Plan" in content
                or "Fix Plan / Recommendation" in content
                or "修复方案" in content
                or "建议" in content
            )
            assert "Verification" in content or "验证" in content
            assert "Scope & Non-Goals" in content or "范围" in content
            assert (
                "switch your model" in content.lower()
                or "switch" in content.lower()
                or "切换模型" in content
                or "专用编码模型" in content
            )

            # Verify no code fence triggers
            assert not contains_code_fence_trigger(content), (
                "Handoff package should not contain code fence triggers"
            )

            # Verify session stage was updated
            mock_session_store.update_session.assert_called()

    def test_handoff_package_contains_sanitized_report(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Handoff package should contain sanitized report content."""
        # Add potentially dangerous content to report
        mock_session_awaiting.ternion_report_raw = "Analysis:\n```python\nprint('test')\n```"
        mock_session_awaiting.ternion_report_safe = (
            "Analysis:\n`\u200b`\u200b`python\nprint('test')\n`\u200b`\u200b`"
        )

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CONFIRM

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test123abc"},
                        {"role": "user", "content": "Confirmed"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Code fences should be broken/sanitized
            assert not contains_code_fence_trigger(content)


class TestRCAToConfirmImplementation:
    """Test RCA → Report → Confirm → Implementation flow (TERNION_FULL mode)."""

    def test_confirm_triggers_implementation_stage(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Confirm in TERNION_FULL mode should run implementation stage."""
        mock_user_config.execution_mode = "ternion_full"
        mock_session_awaiting.execution_mode = ExecutionMode.TERNION_FULL

        mock_implementation_result = {
            "final_output": "def fixed_function():\n    return 42",
            "thinking_logs": ["> [Writer] Generating code...\n"],
            "generated_code": "def fixed_function():\n    return 42",
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
            patch(
                "ternion.workflow.implementation_stage.run_implementation_stage",
                new_callable=AsyncMock,
            ) as mock_impl,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CONFIRM
            mock_impl.return_value = mock_implementation_result

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test123abc"},
                        {"role": "user", "content": "Yes, implement it"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200

            # Verify implementation stage was called (not full RCA re-run)
            mock_impl.assert_called_once()

            # Verify session stage updated to EXECUTED
            mock_session_store.update_session.assert_called()


class TestRCAToRejectClarify:
    """Test RCA → Report → Reject/Clarify flows."""

    def test_reject_triggers_new_rca(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Reject intent should trigger new RCA analysis."""
        mock_new_result = {
            "final_output": "New analysis report...\nTERNION_SESSION_ID=new456def",
            "thinking_logs": ["> [Ternion A] Re-analyzing...\n"],
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.REJECT
            mock_run.return_value = mock_new_result

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test123abc"},
                        {"role": "user", "content": "No, this analysis is wrong"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200

            # Verify new RCA was triggered
            mock_run.assert_called_once()

            # Verify old session marked as rejected
            mock_session_store.update_session.assert_called()

    def test_clarify_uses_existing_report(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Clarify intent should answer using existing report without re-running RCA."""
        # Make the report very long to ensure clarify does not echo it back in full
        mock_session_awaiting.ternion_report_raw = (
            "## Root Cause\nThe root cause is a null pointer exception.\n\n"
            + ("A" * 5000)
            + "\n\n## End\nEND_OF_REPORT_TOKEN"
        )
        mock_session_awaiting.ternion_report_safe = mock_session_awaiting.ternion_report_raw

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CLARIFY

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test123abc"},
                        {"role": "user", "content": "Can you explain why this is the root cause?"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Verify RCA was NOT re-run
            mock_run.assert_not_called()

            # Verify response includes analysis content and markers
            assert "TERNION_SESSION_ID" in content
            assert "AWAITING_CONFIRMATION" in content
            # Verify clarify does not echo the entire report back
            assert "END_OF_REPORT_TOKEN" not in content

    def test_clarify_architecture_question_routes_to_fix_plan_excerpt(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """
        Clarify should route design/architecture questions to the Fix Plan excerpt.

        This reduces noise by not always echoing Root Cause for design-oriented questions.
        """
        mock_session_awaiting.ternion_report_raw = (
            "## Root Cause\n"
            "- ROOT_CAUSE_TOKEN: Architecture thesis and core decision.\n\n"
            "## Evidence / Logs\n"
            "- Requirements and constraints.\n\n"
            "## Scope & Non-Goals\n"
            "- In Scope: ...\n\n"
            "## Fix Plan / Recommendation\n"
            "- FIX_PLAN_TOKEN: Architecture and milestone roadmap.\n\n"
            "## Verification\n"
            "### User Verification\n"
            "- Acceptance criteria.\n"
            "### Implementer Verification\n"
            "- Test matrix.\n\n"
            "## Risks & Rollback\n"
            "- Risks and rollback.\n\n"
            "## If not effective, then what?\n"
            "- Fallback approaches.\n"
        )
        mock_session_awaiting.ternion_report_safe = mock_session_awaiting.ternion_report_raw

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CLARIFY

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test123abc"},
                        {"role": "user", "content": "这个架构应该怎么设计？请给出实现路径。"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Verify RCA was NOT re-run
            mock_run.assert_not_called()

            # Should include fix-plan excerpt token, and avoid echoing root-cause token for this question type
            assert "FIX_PLAN_TOKEN" in content
            assert "ROOT_CAUSE_TOKEN" not in content


class TestPostExecutionFollowup:
    """Test follow-up behavior after session completion."""

    def test_cursor_handoff_reminds_to_switch_model(
        self, client: TestClient, mock_user_config: MagicMock
    ) -> None:
        """CURSOR_HANDOFF in CONFIRMED state should remind user to switch."""
        confirmed_session = Session(
            session_id="test789ghi",
            stage=SessionStage.CONFIRMED,
            execution_mode=ExecutionMode.CURSOR_HANDOFF,
            ternion_report_raw="Analysis complete.",
            ternion_report_safe="Analysis complete.",
            report_hash="xyz789",
            created_at="2026-01-04T12:00:00Z",
            updated_at="2026-01-04T12:00:00Z",
        )

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = confirmed_session

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test789ghi"},
                        {"role": "user", "content": "Can you help me implement it?"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Should remind to switch model
            assert "switch" in content.lower() or "切换模型" in content or "切换至非" in content

    def test_ternion_full_completed_informs_user(
        self, client: TestClient, mock_user_config: MagicMock
    ) -> None:
        """TERNION_FULL in EXECUTED state should inform session is complete."""
        executed_session = Session(
            session_id="test789ghi",
            stage=SessionStage.EXECUTED,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="Analysis complete.",
            ternion_report_safe="Analysis complete.",
            report_hash="xyz789",
            created_at="2026-01-04T12:00:00Z",
            updated_at="2026-01-04T12:00:00Z",
        )
        mock_user_config.execution_mode = "ternion_full"

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = executed_session

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "assistant", "content": "TERNION_SESSION_ID=test789ghi"},
                        {"role": "user", "content": "What's next?"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]

            # Should inform session is complete
            assert "complete" in content.lower() or "executed" in content.lower()


class TestReportHashVerification:
    """Test report hash consistency verification."""

    def test_hash_mismatch_is_logged(
        self,
        client: TestClient,
        mock_user_config: MagicMock,
        mock_session_awaiting: Session,
    ) -> None:
        """Hash mismatch should be logged but processing continues."""
        mock_session_awaiting.report_hash = "stored_hash_123"

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.classify_intent_with_fallback", new_callable=AsyncMock
            ) as mock_classify,
            patch("ternion.server.routes.logger") as mock_logger,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = mock_session_awaiting
            mock_classify.return_value = Intent.CONFIRM

            # Send message with different hash in marker
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "TERNION_SESSION_ID=test123abc\nTERNION_REPORT_HASH=different_hash",
                        },
                        {"role": "user", "content": "Proceed"},
                    ],
                    "stream": False,
                },
            )

            # Should still succeed (processing continues)
            assert response.status_code == 200

            # Hash mismatch should be logged as warning
            mock_logger.warning.assert_called()


class TestRoleConfigValidation:
    """Test role configuration validation."""

    def test_empty_model_config_returns_503(self, client: TestClient) -> None:
        """Request with empty model config should return 503."""
        config = MagicMock()
        config.execution_mode = "cursor_handoff"
        config.show_thinking_logs = True
        # Role with empty model
        config.roles = {
            "ternion_a": RoleConfig(provider="openai", model=""),  # Role with empty model
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider = MagicMock()
        mock_provider.api_keys = [MagicMock()]
        mock_provider.selected_key_id = "test-key-id"
        config.providers = {"openai": mock_provider}

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
        ):
            mock_config_store.load.return_value = config
            mock_provider_mgr.has_providers = True

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "user", "content": "Fix my bug"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 503
            content = response.json()
            assert "error" in content
            assert "Ternion A" in content["error"]["message"]
            assert "not selected" in content["error"]["message"]

    def test_empty_provider_config_returns_503(self, client: TestClient) -> None:
        """Request with empty provider config should return 503."""
        config = MagicMock()
        config.execution_mode = "cursor_handoff"
        config.show_thinking_logs = True
        # Role with empty provider
        config.roles = {
            "ternion_a": RoleConfig(provider="", model="gpt-4"),  # Role with empty provider
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider = MagicMock()
        mock_provider.api_keys = [MagicMock()]
        mock_provider.selected_key_id = "test-key-id"
        config.providers = {"openai": mock_provider}

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
        ):
            mock_config_store.load.return_value = config
            mock_provider_mgr.has_providers = True

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "user", "content": "Fix my bug"},
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 503
            content = response.json()
            assert "error" in content
            assert "Ternion A" in content["error"]["message"]
            assert "not selected" in content["error"]["message"]
