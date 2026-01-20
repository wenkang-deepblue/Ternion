"""
Tests for the FastAPI server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ternion.core.config_store import RoleConfig
from ternion.server.app import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_ternion_config():
    """Mock ternion configuration for all roles."""
    def get_role_config(role: str) -> RoleConfig | None:
        # Provide mock config for all roles
        configs = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        return configs.get(role)
    return get_role_config


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestModelsEndpoint:
    """Tests for models listing endpoint."""

    def test_list_models(self, client: TestClient) -> None:
        """Test models endpoint returns available models."""
        response = client.get("/v1/models")
        assert response.status_code == 200

        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1

        model_ids = [m["id"] for m in data["data"]]
        assert "ternion-team" in model_ids

    def test_head_models(self, client: TestClient) -> None:
        """HEAD /v1/models should succeed for strict clients (API-002)."""
        response = client.head("/v1/models")
        assert response.status_code == 200


class TestChatCompletions:
    """Tests for chat completions endpoint."""

    def test_chat_completions_basic(
        self, client: TestClient, mock_ternion_config
    ) -> None:
        """Test basic chat completion request with mocked workflow."""
        # Mock the workflow to avoid actual LLM calls
        mock_result = {
            "final_output": "Hello! How can I help you?",
            "thinking_logs": ["[Ternion] Starting discussion..."],
            "errors": [],
        }

        # Create mock user config with all roles configured
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {
            "openai": mock_provider_config,
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.return_value = mock_result

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "user", "content": "Hello"}
                    ],
                    "stream": False,
                },
            )
            assert response.status_code == 200

            data = response.json()
            assert data["model"] == "ternion-team"
            assert len(data["choices"]) == 1

    def test_chat_completions_streaming(
        self, client: TestClient, mock_ternion_config
    ) -> None:
        """Test streaming chat completion request with mocked workflow."""
        mock_result = {
            "final_output": "Hello! How can I help you?",
            "thinking_logs": ["[Ternion] Starting discussion..."],
            "errors": [],
        }

        # Create mock user config with all roles configured
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {
            "openai": mock_provider_config,
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.return_value = mock_result

            with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "user", "content": "Hello"}
                    ],
                    "stream": True,
                },
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

                # Read some chunks
                chunks = []
                for line in response.iter_lines():
                    if line:
                        chunks.append(line)
                    if len(chunks) >= 5:
                        break

                assert len(chunks) > 0

    def test_chat_completions_returns_tool_calls_and_rewrites_ids(
        self, client: TestClient
    ) -> None:
        """When workflow returns pending_tool_calls, respond with tool_calls and embedded session_id."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        mock_result = {
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": "{\"query\":\"foo\"}"},
                }
            ],
            "thinking_logs": [],
            "errors": [],
        }

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        fake_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
        )

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.return_value = mock_result
            mock_session_store.create_session.return_value = fake_session
            mock_session_store.update_session.return_value = fake_session

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "codebase_search",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            tool_calls = data["choices"][0]["message"]["tool_calls"]
            assert tool_calls[0]["id"] == "ternion_0123456789ab_r0001_c00"
            assert tool_calls[0]["function"]["name"] == "codebase_search"

    def test_responses_alias_accepts_input_payload(self, client: TestClient) -> None:
        """
        /v1/responses should accept OpenAI Responses-style payloads (API-004),
        coercing `input` into Chat Completions `messages`.
        """
        mock_result = {
            "final_output": "PONG",
            "thinking_logs": [],
            "errors": [],
        }

        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.return_value = mock_result

            response = client.post(
                "/v1/responses",
                json={
                    "model": "ternion-team",
                    "input": "REGTEST_CASE=API-004\n\nPing",
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["model"] == "ternion-team"
            assert data["choices"][0]["message"]["content"] == "PONG"

    def test_streaming_tool_calls_finishes_with_tool_calls(
        self, client: TestClient
    ) -> None:
        """When streaming returns tool_calls, SSE must end with finish_reason=tool_calls."""
        import json as json_lib

        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        mock_result = {
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": "{\"query\":\"foo\"}"},
                }
            ],
            "conversation_history": [],
            "current_phase": "report_evidence",
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "evidence_requests": "- [P0] path=foo.py:1-2",
            "ternion_analyses": [{"ternion_id": "ternion_a", "analysis": "A"}],
            "thinking_logs": [],
            "errors": [],
        }

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        fake_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
        )

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.return_value = mock_result
            mock_session_store.create_session.return_value = fake_session
            mock_session_store.update_session.return_value = fake_session

            with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

                chunks: list[dict] = []
                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    payload = line.removeprefix("data: ").strip()
                    if payload == "[DONE]":
                        break
                    chunks.append(json_lib.loads(payload))

                assert chunks, "Expected at least one SSE data chunk"

                saw_tool_calls = any(
                    isinstance(c.get("choices", [{}])[0].get("delta", {}).get("tool_calls"), list)
                    for c in chunks
                )
                assert saw_tool_calls, "Expected a delta.tool_calls chunk in SSE stream"

                saw_finish = any(
                    c.get("choices", [{}])[0].get("finish_reason") == "tool_calls"
                    for c in chunks
                )
                assert saw_finish, "Expected a finish_reason='tool_calls' final SSE chunk"

            # Streaming tool-loop sessions must persist Phase 1.5 evidence state.
            mock_session_store.create_session.assert_called_once()
            kwargs = mock_session_store.create_session.call_args.kwargs
            assert kwargs.get("workflow_phase") == "report_evidence"
            assert kwargs.get("evidence_bundle") == mock_result["evidence_bundle"]
            assert kwargs.get("evidence_gaps") == mock_result["evidence_gaps"]
            assert kwargs.get("evidence_requests") == mock_result["evidence_requests"]
            assert kwargs.get("ternion_analyses") == mock_result["ternion_analyses"]

    def test_execution_followup_routes_by_tool_call_id(self, client: TestClient) -> None:
        """Execution follow-ups should be routed via tool_call_id even without session markers."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        fake_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
        )

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch("ternion.server.routes.handle_execution_followup", new_callable=AsyncMock) as mock_handler,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_session_store.load_session.return_value = fake_session
            from fastapi.responses import JSONResponse
            mock_handler.return_value = JSONResponse(content={"ok": True})

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {"role": "user", "content": "Continue"},
                        {
                            "role": "tool",
                            "tool_call_id": "ternion_0123456789ab_r0001_c00",
                            "content": "RESULT",
                        },
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            assert response.json() == {"ok": True}
            mock_handler.assert_awaited()

    def test_report_evidence_followup_routes_and_persists_tool_loop(
        self, client: TestClient
    ) -> None:
        """Phase 1.5 follow-ups should route and persist tool loop state."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        resume_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
            workflow_phase="report_evidence",
            cursor_system_prompt="SYS",
            execution_messages=[],
            evidence_bundle="EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests="- [P0] path=foo.py:1-2",
            ternion_analyses=[{"ternion_id": "ternion_a", "analysis": "A"}],
        )
        tool_session = Session(
            session_id="fedcba987654",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash2",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
        )
        mock_final_state = {
            "current_phase": "report_evidence",
            "execution_mode": "ternion_full",
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": "{\"query\":\"foo\"}"},
                }
            ],
            "conversation_history": [],
            "evidence_bundle": resume_session.evidence_bundle,
            "evidence_gaps": resume_session.evidence_gaps,
            "evidence_requests": resume_session.evidence_requests,
            "ternion_analyses": resume_session.ternion_analyses,
            "thinking_logs": [],
            "errors": [],
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch("ternion.server.routes.budget_manager") as mock_budget_manager,
            patch("ternion.workflow.graph.resume_report_evidence", new_callable=AsyncMock) as mock_resume,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_session_store.load_session.return_value = resume_session
            mock_session_store.create_session.return_value = tool_session
            mock_session_store.update_session.return_value = resume_session
            mock_budget_manager.check_budget.return_value = (True, None)
            mock_resume.return_value = mock_final_state

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {
                            "role": "tool",
                            "tool_call_id": "ternion_0123456789ab_r0001_c00",
                            "content": "RESULT",
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"

            tool_calls = data["choices"][0]["message"]["tool_calls"]
            assert tool_calls[0]["id"] == "ternion_fedcba987654_r0001_c00"
            assert tool_calls[0]["function"]["name"] == "codebase_search"

            kwargs = mock_session_store.create_session.call_args.kwargs
            assert isinstance(kwargs.get("execution_mode"), ExecutionMode)
            assert kwargs.get("workflow_phase") == "report_evidence"
            assert kwargs.get("evidence_bundle") == mock_final_state["evidence_bundle"]
            assert kwargs.get("evidence_gaps") == mock_final_state["evidence_gaps"]
            assert kwargs.get("evidence_requests") == mock_final_state["evidence_requests"]
            assert kwargs.get("ternion_analyses") == mock_final_state["ternion_analyses"]

            saw_tool_session_update = any(
                call.args
                and call.args[0] == tool_session.session_id
                and call.kwargs.get("round_index") == 1
                and isinstance(call.kwargs.get("pending_tool_calls"), list)
                for call in mock_session_store.update_session.call_args_list
            )
            assert saw_tool_session_update

    def test_read_file_tool_call_is_paginated_by_server(self, client: TestClient) -> None:
        """Server should enforce offset/limit on read_file tool calls."""
        from ternion.server.routes import _rewrite_tool_call_ids

        tool_calls = [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{\"target_file\":\"/tmp/x\"}"},
            }
        ]
        rewritten = _rewrite_tool_call_ids(tool_calls, session_id="0123456789ab", round_index=1)
        args = rewritten[0]["function"]["arguments"]
        assert "\"offset\": 1" in args
        assert "\"limit\"" in args

    def test_cursor_handoff_agent_auto_switches_to_ternion_full(
        self, client: TestClient
    ) -> None:
        """
        When configured as cursor_handoff but invoked from Cursor Agent mode,
        the server should auto-switch to ternion_full and skip confirmation gate.
        """
        mock_result = {
            "final_output": "AUTO_EXECUTION_OK",
            "thinking_logs": [],
            "errors": [],
        }

        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "cursor_handoff"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
            # Required after auto-switch to ternion_full
            "writer": RoleConfig(provider="openai", model="gpt-4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        async def run_discussion_assert(ctx):  # type: ignore[no-untyped-def]
            assert getattr(ctx, "execution_mode", "") == "ternion_full"
            assert getattr(ctx, "await_confirmation", True) is False
            return mock_result

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.side_effect = run_discussion_assert

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "codebase_search",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]
            assert "AUTO_EXECUTION_OK" in content

            # Persisted mode switch so Web UI reflects it.
            assert mock_user_config.execution_mode == "ternion_full"
            mock_config_store.save.assert_called_once()

    def test_cursor_handoff_non_agent_does_not_auto_switch_even_with_tools(
        self, client: TestClient
    ) -> None:
        """
        When invoked from a non-agent Cursor mode (Ask/Plan/Debug), do not auto-switch
        cursor_handoff -> ternion_full even if the request includes tool definitions.
        """
        mock_result = {
            "final_output": "REPORT_ONLY_OK",
            "thinking_logs": [],
            "errors": [],
        }

        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "cursor_handoff"
        mock_user_config.show_thinking_logs = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}

        non_agent_reminder = (
            "<system_reminder>\n"
            "The user is in ask mode; only read-only tools are available.\n"
            "</system_reminder>"
        )

        async def run_discussion_assert(ctx):  # type: ignore[no-untyped-def]
            assert getattr(ctx, "execution_mode", "") == "cursor_handoff"
            assert getattr(ctx, "await_confirmation", False) is True
            return mock_result

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.side_effect = run_discussion_assert

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": non_agent_reminder}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "codebase_search",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            content = response.json()["choices"][0]["message"]["content"]
            assert "REPORT_ONLY_OK" in content

            assert mock_user_config.execution_mode == "cursor_handoff"
            mock_config_store.save.assert_not_called()
