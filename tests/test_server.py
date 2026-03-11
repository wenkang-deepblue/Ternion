"""
Tests for the FastAPI server.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from ternion.core.config_store import RoleConfig
from ternion.core.exceptions import RuntimeModelUnavailableError
from ternion.server.app import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_ternion_config() -> Callable[[str], RoleConfig | None]:
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
        self,
        client: TestClient,
        mock_ternion_config: Callable[[str], RoleConfig | None],
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
            patch("ternion.utils.i18n._load_user_config") as mock_i18n_loader,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_i18n_loader.return_value = mock_user_config
            mock_run.return_value = mock_result

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )
            assert response.status_code == 200

            data = response.json()
            assert data["model"] == "ternion-team"
            assert len(data["choices"]) == 1

    def test_chat_completions_streaming(
        self,
        client: TestClient,
        mock_ternion_config: Callable[[str], RoleConfig | None],
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
            patch("ternion.utils.i18n._load_user_config") as mock_i18n_loader,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_i18n_loader.return_value = mock_user_config
            mock_run.return_value = mock_result

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

                # Read some chunks
                chunks = []
                for line in response.iter_lines():
                    if line:
                        chunks.append(line)
                    if len(chunks) >= 5:
                        break

                assert len(chunks) > 0

    def test_chat_completions_returns_model_unavailable_error_payload(
        self,
        client: TestClient,
    ) -> None:
        """Non-streaming runtime stale-model failures should return a stable error payload."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-5.4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-5.4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-5.4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-5.4"),
            "writer": RoleConfig(provider="openai", model="gpt-5.4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-5.4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}
        mock_user_config.language = "en"

        mock_result = {
            "current_phase": "complete",
            "errors": ["runtime model unavailable"],
            "runtime_error_payload": {
                "code": "MODEL_UNAVAILABLE",
                "provider": "openai",
                "model": "gpt-5.4",
                "refresh_suggested": True,
            },
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
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )

        assert response.status_code == 400
        error_payload = response.json()["error"]
        assert error_payload["type"] == "model_unavailable"
        assert error_payload["code"] == "MODEL_UNAVAILABLE"
        assert error_payload["provider"] == "openai"
        assert error_payload["model"] == "gpt-5.4"
        assert error_payload["refresh_suggested"] is True
        assert "openai / gpt-5.4" in error_payload["message"]
        assert "http://localhost:9120" in error_payload["message"]

    def test_chat_completions_streaming_surfaces_model_unavailable_guidance(
        self,
        client: TestClient,
    ) -> None:
        """Streaming runtime stale-model failures should not degrade to a generic stream error."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_phase_indicators = True
        mock_user_config.roles = {
            "ternion_a": RoleConfig(provider="openai", model="gpt-5.4"),
            "ternion_b": RoleConfig(provider="openai", model="gpt-5.4"),
            "ternion_c": RoleConfig(provider="openai", model="gpt-5.4"),
            "arbiter": RoleConfig(provider="openai", model="gpt-5.4"),
            "writer": RoleConfig(provider="openai", model="gpt-5.4"),
            "reviewer": RoleConfig(provider="openai", model="gpt-5.4"),
        }
        mock_provider_config = MagicMock()
        mock_provider_config.api_keys = [MagicMock()]
        mock_provider_config.selected_key_id = "test-key-id"
        mock_user_config.providers = {"openai": mock_provider_config}
        mock_user_config.language = "en"

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.utils.i18n._load_user_config") as mock_i18n_loader,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_i18n_loader.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.side_effect = RuntimeModelUnavailableError(
                provider="openai",
                model="gpt-5.4",
                provider_message="model not found",
            )

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
                chunks: list[str] = []
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
                    chunks.append(payload)

        joined = "\n".join(chunks)
        assert "configured runtime model is no longer available" in joined
        assert "openai / gpt-5.4" in joined
        assert "Web Control Panel" in joined

    def test_chat_completions_returns_tool_calls_and_rewrites_ids(self, client: TestClient) -> None:
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
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"docs/a.md","content":"x"}',
                    },
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
            patch("ternion.utils.i18n._load_user_config") as mock_i18n_loader,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_i18n_loader.return_value = mock_user_config
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
            assert tool_calls[0]["function"]["name"] == "Write"

    def test_doc_only_blocks_mutation_tool_calls(self, client: TestClient) -> None:
        """Doc-only policy should block mutation tool calls outside docs/."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
            "conversation_history": [{"role": "user", "content": "请只输出方案文档"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"src/app.py","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "doc-only request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            assert "doc-only" in content
            assert "docs/**" in content
            assert "src/app.py" in content
            assert not message.get("tool_calls")

    def test_doc_only_allows_docs_write(self, client: TestClient) -> None:
        """Doc-only policy should allow writes under docs/."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
            "conversation_history": [{"role": "user", "content": "只要文档"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"docs/plan.md","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "doc-only request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            tool_calls = data["choices"][0]["message"]["tool_calls"]
            assert tool_calls[0]["function"]["name"] == "Write"

    def test_doc_only_allows_docs_write_with_path_key(self, client: TestClient) -> None:
        """Doc-only should allow docs writes when Write uses `path` instead of `file_path`."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
            "conversation_history": [{"role": "user", "content": "只要文档"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "arguments": '{"path":"docs/plan.md","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "doc-only request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            tool_calls = data["choices"][0]["message"]["tool_calls"]
            assert tool_calls[0]["function"]["name"] == "Write"

    def test_doc_only_blocks_write_file_tool_name(self, client: TestClient) -> None:
        """Doc-only should also block mutation calls named write_file (canonical writefile)."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Scope: documentation only. Non-goals: no code changes.",
            "conversation_history": [{"role": "user", "content": "只要文档"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"src/app.py","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "doc-only request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            assert "doc-only" in content
            assert "src/app.py" in content
            assert not message.get("tool_calls")

    def test_analysis_only_blocks_mutation_tool_calls(self, client: TestClient) -> None:
        """Analysis-only policy should block mutation tool calls."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Scope: analysis only. Non-goals: no file changes.",
            "conversation_history": [{"role": "user", "content": "只分析，不落盘"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"docs/plan.md","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "analysis-only request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            assert "analysis-only" in content
            assert not message.get("tool_calls")

    def test_code_change_allows_src_write(self, client: TestClient) -> None:
        """Code-change policy should allow writes under src/."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "ternion_report": "Fix Plan: update code.",
            "conversation_history": [{"role": "user", "content": "请修复代码"}],
            "pending_tool_calls": [
                {
                    "id": "call_doc",
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"src/app.py","content":"x"}',
                    },
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
                    "messages": [{"role": "user", "content": "code-change request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Write",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            tool_calls = data["choices"][0]["message"]["tool_calls"]
            assert tool_calls[0]["function"]["name"] == "Write"

    def test_execution_tool_policy_blocks_read_tool_calls(self, client: TestClient) -> None:
        """Execution tool policy should block read/search tool calls."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "conversation_history": [{"role": "user", "content": "do it"}],
            "pending_tool_calls": [
                {
                    "id": "call_read",
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "arguments": '{"path":"src/app.py"}',
                    },
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
                    "messages": [{"role": "user", "content": "request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "Read",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            assert "Read" in content
            assert not message.get("tool_calls")

    def test_shell_policy_blocks_read_command(self, client: TestClient) -> None:
        """Shell policy should block read/search commands."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.language = "en"
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
            "conversation_history": [{"role": "user", "content": "do it"}],
            "pending_tool_calls": [
                {
                    "id": "call_shell",
                    "type": "function",
                    "function": {
                        "name": "run_terminal_cmd",
                        "arguments": '{"command":"cat README.md"}',
                    },
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
                    "messages": [{"role": "user", "content": "request"}],
                    "stream": False,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "run_terminal_cmd",
                                "description": "dummy",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }
                    ],
                },
            )
            assert response.status_code == 200
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            assert "run_terminal_cmd" in content
            assert "cat README.md" in content
            assert not message.get("tool_calls")

    def test_report_scope_drives_policy_when_user_missing(self) -> None:
        """Scope/Non-Goals should drive policy when user message is empty."""
        from ternion.core.deliverable_policy import DeliverableType
        from ternion.server.routes import _resolve_deliverable_policy_from_context

        report = (
            "## Scope & Non-Goals\n"
            "- Documentation only\n"
            "- Do not change code\n\n"
            "## Fix Plan / Recommendation\n"
            "- Update src/app.py\n"
        )
        deliverable_type, allowed_scope = _resolve_deliverable_policy_from_context([], report)
        assert deliverable_type == DeliverableType.DOC_ONLY
        assert allowed_scope == "docs/**"

    def test_doc_only_enforces_write_scope_on_src_mutation(self) -> None:
        """Doc-only policy should block src mutations in execution guardrail."""
        from ternion.core.deliverable_policy import DeliverableType
        from ternion.server.routes import _enforce_deliverable_policy

        tool_calls = [
            {
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": '{"file_path":"src/app.py","content":"x"}',
                },
            }
        ]
        filtered, message, deliverable_type, allowed_scope = _enforce_deliverable_policy(
            workflow_phase="execution",
            tool_calls=tool_calls,
            conversation_history=[{"role": "user", "content": "doc-only request"}],
            ternion_report="Scope: documentation only. Non-goals: no code changes.",
        )

        assert filtered == []
        assert deliverable_type == DeliverableType.DOC_ONLY
        assert allowed_scope == "docs/**"
        assert message is not None
        assert "doc-only" in message
        assert "docs/**" in message
        assert "src/app.py" in message

    def test_code_change_blocks_outside_repo_mutation(self) -> None:
        """Code-change policy should block mutations outside project root."""
        from ternion.core.deliverable_policy import DeliverableType
        from ternion.server.routes import _enforce_deliverable_policy

        tool_calls = [
            {
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": '{"file_path":"/tmp/outside.py","content":"x"}',
                },
            }
        ]
        filtered, message, deliverable_type, allowed_scope = _enforce_deliverable_policy(
            workflow_phase="execution",
            tool_calls=tool_calls,
            conversation_history=[{"role": "user", "content": "please update code"}],
            ternion_report="REPORT",
        )

        assert filtered == []
        assert deliverable_type == DeliverableType.CODE_CHANGE
        assert allowed_scope == "repo/**"
        assert message is not None
        assert "repo/**" in message
        assert "/tmp/outside.py" in message

    def test_workspace_relative_path_uses_project_root(self, tmp_path: Path) -> None:
        """Relative path resolution should anchor to project root, not cwd."""
        from ternion.server.routes import _resolve_project_root, _workspace_relative_path

        root = _resolve_project_root()
        docs_path = (root / "docs" / "development_log.md").resolve()
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            relative = _workspace_relative_path(str(docs_path))
        finally:
            os.chdir(original_cwd)
        assert relative == "docs/development_log.md"

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

    def test_streaming_tool_calls_finishes_with_tool_calls(self, client: TestClient) -> None:
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
                    "function": {"name": "codebase_search", "arguments": '{"query":"foo"}'},
                }
            ],
            "conversation_history": [],
            "current_phase": "report_evidence",
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "evidence_requests": "- [P0] path=foo.py:1-2",
            "evidence_topup_round": 1,
            "report_evidence_resume_phase": "execution",
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
                    c.get("choices", [{}])[0].get("finish_reason") == "tool_calls" for c in chunks
                )
                assert saw_finish, "Expected a finish_reason='tool_calls' final SSE chunk"

            # Streaming tool-loop sessions must persist Phase 1.5 evidence state.
            mock_session_store.create_session.assert_called_once()
            kwargs = mock_session_store.create_session.call_args.kwargs
            assert kwargs.get("workflow_phase") == "report_evidence"
            assert kwargs.get("evidence_bundle") == mock_result["evidence_bundle"]
            assert kwargs.get("evidence_gaps") == mock_result["evidence_gaps"]
            assert kwargs.get("evidence_requests") == mock_result["evidence_requests"]
            assert kwargs.get("evidence_topup_round") == mock_result["evidence_topup_round"]
            assert (
                kwargs.get("report_evidence_resume_phase")
                == mock_result["report_evidence_resume_phase"]
            )
            assert kwargs.get("ternion_analyses") == mock_result["ternion_analyses"]

    def test_non_streaming_tool_calls_persist_report_evidence_resume_and_topup_round(
        self, client: TestClient
    ) -> None:
        """Non-streaming tool-loop sessions must persist Phase 1.5 resume and top-up state."""
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
                    "function": {"name": "codebase_search", "arguments": '{"query":"foo"}'},
                }
            ],
            "conversation_history": [],
            "current_phase": "report_evidence",
            "evidence_bundle": "EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            "evidence_gaps": "EVIDENCE_GAPS:\n- None",
            "evidence_requests": "- [P0] path=foo.py:1-2",
            "evidence_topup_round": 1,
            "report_evidence_resume_phase": "execution",
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

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"

            mock_session_store.create_session.assert_called_once()
            kwargs = mock_session_store.create_session.call_args.kwargs
            assert kwargs.get("workflow_phase") == "report_evidence"
            assert kwargs.get("evidence_topup_round") == mock_result["evidence_topup_round"]
            assert (
                kwargs.get("report_evidence_resume_phase")
                == mock_result["report_evidence_resume_phase"]
            )

    def test_streaming_tool_calls_emits_no_content_deltas(self, client: TestClient) -> None:
        """
        Tool-calls responses must not emit any user-visible content deltas.

        This includes server-side phase indicators: they should be buffered until
        the first TOKEN_DELTA arrives. If the workflow ends with tool_calls and
        no tokens were streamed, the SSE stream must contain no delta.content.
        """
        import json as json_lib

        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = False
        mock_user_config.show_phase_indicators = True
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
                    "function": {
                        "name": "Write",
                        "arguments": '{"file_path":"docs/a.md","content":"x"}',
                    },
                }
            ],
            "conversation_history": [],
            "current_phase": "optimizer",
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

        async def run_discussion_with_phase(ctx):  # type: ignore[no-untyped-def]
            queue = getattr(ctx, "_stream_queue", None)
            if queue is not None:
                await queue.put_phase_start("optimizer")
            return mock_result

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.provider_manager") as mock_provider_mgr,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
            patch("ternion.server.routes.session_store") as mock_session_store,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_provider_mgr.has_providers = True
            mock_run.side_effect = run_discussion_with_phase
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

                for c in chunks:
                    delta = c.get("choices", [{}])[0].get("delta", {}) or {}
                    # Tool-call chunks must never include assistant content.
                    # Phase indicators (UI hints) may be streamed as separate content deltas.
                    if isinstance(delta.get("tool_calls"), list):
                        assert not delta.get("content"), (
                            f"Unexpected delta.content in tool_calls chunk: {delta.get('content')!r}"
                        )

                tool_chunks = [
                    c
                    for c in chunks
                    if isinstance(
                        c.get("choices", [{}])[0].get("delta", {}).get("tool_calls"), list
                    )
                ]
                assert tool_chunks, "Expected a delta.tool_calls chunk in SSE stream"

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
            patch(
                "ternion.server.routes.handle_execution_followup", new_callable=AsyncMock
            ) as mock_handler,
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
            round_index=1,
            workflow_phase="report_evidence",
            cursor_system_prompt="SYS",
            execution_messages=[],
            evidence_bundle="EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests="- [P0] path=foo.py:1-2",
            ternion_analyses=[{"ternion_id": "ternion_a", "analysis": "A"}],
        )
        mock_final_state = {
            "current_phase": "report_evidence",
            "execution_mode": "ternion_full",
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": '{"query":"foo"}'},
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
            patch(
                "ternion.workflow.graph.resume_report_evidence", new_callable=AsyncMock
            ) as mock_resume,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_session_store.load_session.return_value = resume_session
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
            assert tool_calls[0]["id"] == "ternion_0123456789ab_r0002_c00"
            assert tool_calls[0]["function"]["name"] == "codebase_search"

            assert mock_session_store.create_session.call_count == 0

            saw_tool_session_update = any(
                call.args
                and call.args[0] == resume_session.session_id
                and call.kwargs.get("round_index") == 2
                and call.kwargs.get("workflow_phase") == "report_evidence"
                and call.kwargs.get("evidence_bundle") == mock_final_state["evidence_bundle"]
                and call.kwargs.get("evidence_gaps") == mock_final_state["evidence_gaps"]
                and call.kwargs.get("evidence_requests") == mock_final_state["evidence_requests"]
                and call.kwargs.get("ternion_analyses") == mock_final_state["ternion_analyses"]
                and isinstance(call.kwargs.get("pending_tool_calls"), list)
                for call in mock_session_store.update_session.call_args_list
            )
            assert saw_tool_session_update

    def test_report_evidence_followup_keeps_existing_tool_call_history(
        self, client: TestClient
    ) -> None:
        """Report-evidence follow-up must keep prior assistant tool-call history."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"
        mock_user_config.show_thinking_logs = True

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        prior_tool_call_id = "ternion_0123456789ab_r0001_c00"
        resume_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
            round_index=1,
            workflow_phase="report_evidence",
            cursor_system_prompt="SYS",
            execution_messages=[
                {"role": "user", "content": "u"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": prior_tool_call_id,
                            "type": "function",
                            "function": {
                                "name": "Read",
                                "arguments": '{"path":"/tmp/a.py"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": prior_tool_call_id,
                    "content": "RESULT_A",
                },
            ],
            evidence_bundle="EVIDENCE_BUNDLE:\n- [FILE_EXCERPT] path=foo.py | lines=1-2",
            evidence_gaps="EVIDENCE_GAPS:\n- None",
            evidence_requests="- [P0] path=foo.py:1-2",
            ternion_analyses=[{"ternion_id": "ternion_a", "analysis": "A"}],
        )
        mock_final_state = {
            "current_phase": "report_evidence",
            "execution_mode": "ternion_full",
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": '{"query":"foo"}'},
                }
            ],
            # Simulate workflow-cleaned history (tool messages stripped)
            "conversation_history": [{"role": "user", "content": "cleaned_history_only"}],
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
            patch(
                "ternion.workflow.graph.resume_report_evidence", new_callable=AsyncMock
            ) as mock_resume,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_session_store.load_session.return_value = resume_session
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
                            "tool_call_id": prior_tool_call_id,
                            "content": "RESULT_A",
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            assert (
                data["choices"][0]["message"]["tool_calls"][0]["id"]
                == "ternion_0123456789ab_r0002_c00"
            )

            matching_updates = [
                call
                for call in mock_session_store.update_session.call_args_list
                if call.args
                and call.args[0] == resume_session.session_id
                and call.kwargs.get("round_index") == 2
                and call.kwargs.get("workflow_phase") == "report_evidence"
                and isinstance(call.kwargs.get("pending_tool_calls"), list)
            ]
            assert matching_updates
            history = matching_updates[-1].kwargs.get("execution_messages") or []
            assistant_tool_call_ids = {
                tc.get("id")
                for msg in history
                if isinstance(msg, dict) and msg.get("role") == "assistant"
                for tc in (msg.get("tool_calls") or [])
                if isinstance(tc, dict)
            }
            assert prior_tool_call_id in assistant_tool_call_ids
            assert "ternion_0123456789ab_r0002_c00" in assistant_tool_call_ids

    def test_evidence_followup_keeps_existing_tool_call_history_on_phase_transition(
        self, client: TestClient
    ) -> None:
        """Evidence follow-up must keep prior tool-call history after phase transition."""
        mock_user_config = MagicMock()
        mock_user_config.execution_mode = "ternion_full"

        from ternion.core.session_store import ExecutionMode, Session, SessionStage

        prior_tool_call_id = "ternion_0123456789ab_r0001_c00"
        resume_session = Session(
            session_id="0123456789ab",
            stage=SessionStage.AWAITING_TOOL_RESULTS,
            execution_mode=ExecutionMode.TERNION_FULL,
            ternion_report_raw="REPORT",
            ternion_report_safe="REPORT",
            report_hash="hash",
            created_at="2026-01-11T00:00:00Z",
            updated_at="2026-01-11T00:00:00Z",
            round_index=1,
            workflow_phase="evidence",
            cursor_system_prompt="SYS",
            execution_messages=[
                {"role": "user", "content": "u"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": prior_tool_call_id,
                            "type": "function",
                            "function": {
                                "name": "Read",
                                "arguments": '{"path":"/tmp/a.py"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": prior_tool_call_id,
                    "content": "RESULT_A",
                },
            ],
        )
        mock_final_state = {
            "current_phase": "report_evidence",
            "ternion_report": "REPORT",
            "pending_tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "codebase_search", "arguments": '{"query":"foo"}'},
                }
            ],
            # Simulate workflow-cleaned history (tool messages stripped)
            "conversation_history": [{"role": "user", "content": "cleaned_history_only"}],
            "thinking_logs": [],
            "errors": [],
        }

        with (
            patch("ternion.server.routes.config_store") as mock_config_store,
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch("ternion.server.routes.budget_manager") as mock_budget_manager,
            patch("ternion.workflow.graph.run_discussion", new_callable=AsyncMock) as mock_run,
        ):
            mock_config_store.load.return_value = mock_user_config
            mock_session_store.load_session.return_value = resume_session
            mock_session_store.update_session.return_value = resume_session
            mock_budget_manager.check_budget.return_value = (True, None)
            mock_run.return_value = mock_final_state

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ternion-team",
                    "messages": [
                        {
                            "role": "tool",
                            "tool_call_id": prior_tool_call_id,
                            "content": "RESULT_A",
                        }
                    ],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["finish_reason"] == "tool_calls"
            assert (
                data["choices"][0]["message"]["tool_calls"][0]["id"]
                == "ternion_0123456789ab_r0002_c00"
            )

            matching_updates = [
                call
                for call in mock_session_store.update_session.call_args_list
                if call.args
                and call.args[0] == resume_session.session_id
                and call.kwargs.get("round_index") == 2
                and call.kwargs.get("workflow_phase") == "report_evidence"
                and isinstance(call.kwargs.get("pending_tool_calls"), list)
            ]
            assert matching_updates
            history = matching_updates[-1].kwargs.get("execution_messages") or []
            assistant_tool_call_ids = {
                tc.get("id")
                for msg in history
                if isinstance(msg, dict) and msg.get("role") == "assistant"
                for tc in (msg.get("tool_calls") or [])
                if isinstance(tc, dict)
            }
            assert prior_tool_call_id in assistant_tool_call_ids
            assert "ternion_0123456789ab_r0002_c00" in assistant_tool_call_ids

    def test_report_evidence_followup_with_resume_phase_routes_to_execution_followup(
        self, client: TestClient
    ) -> None:
        """Execution-time report_evidence should route to execution follow-up handler."""
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
            report_evidence_resume_phase="execution",
        )

        with (
            patch("ternion.server.routes.session_store") as mock_session_store,
            patch(
                "ternion.server.routes.handle_execution_followup", new_callable=AsyncMock
            ) as mock_exec,
            patch(
                "ternion.server.routes.handle_report_evidence_followup", new_callable=AsyncMock
            ) as mock_report_evidence,
        ):
            mock_session_store.load_session.return_value = resume_session
            mock_exec.return_value = JSONResponse(content={"ok": "execution_followup"})
            mock_report_evidence.return_value = JSONResponse(
                content={"ok": "report_evidence_followup"}
            )

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
            assert response.json() == {"ok": "execution_followup"}
            mock_exec.assert_awaited()
            mock_report_evidence.assert_not_called()

    def test_read_file_tool_call_is_paginated_by_server(self, client: TestClient) -> None:
        """Server should enforce offset/limit on read_file tool calls."""
        from ternion.server.routes import _rewrite_tool_call_ids

        tool_calls = [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"target_file":"/tmp/x"}'},
            }
        ]
        rewritten = _rewrite_tool_call_ids(tool_calls, session_id="0123456789ab", round_index=1)
        args = rewritten[0]["function"]["arguments"]
        assert '"offset": 1' in args
        assert '"limit"' in args

    def test_rewrite_tool_call_ids_preserves_responses_metadata_internally(
        self, client: TestClient
    ) -> None:
        """Internal session copies should keep Responses API metadata while public copies hide it."""
        from ternion.server.routes import _rewrite_tool_call_ids, _strip_internal_tool_call_fields

        tool_calls = [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "Read", "arguments": '{"path":"/tmp/a.py"}'},
                "responses_api_item_id": "fc_123",
                "responses_api_call_id": "call_abc",
                "responses_api_response_id": "resp_123",
            }
        ]

        rewritten = _rewrite_tool_call_ids(tool_calls, session_id="0123456789ab", round_index=1)
        public = _strip_internal_tool_call_fields(rewritten)

        assert rewritten[0]["id"] == "ternion_0123456789ab_r0001_c00"
        assert rewritten[0]["responses_api_item_id"] == "fc_123"
        assert rewritten[0]["responses_api_call_id"] == "call_abc"
        assert rewritten[0]["responses_api_response_id"] == "resp_123"
        assert public[0]["id"] == "ternion_0123456789ab_r0001_c00"
        assert "responses_api_item_id" not in public[0]
        assert "responses_api_call_id" not in public[0]
        assert "responses_api_response_id" not in public[0]

    def test_rewrite_tool_call_ids_normalizes_repo_relative_read_paths(
        self, client: TestClient
    ) -> None:
        """Server should normalize repo-relative Read paths like /docs/x.md."""
        import json as json_lib
        from pathlib import Path

        from ternion.server.routes import _rewrite_tool_call_ids

        repo_root = Path.cwd().resolve()
        tool_calls = [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "Read", "arguments": '{"path":"/docs/development_log.md"}'},
            }
        ]
        rewritten = _rewrite_tool_call_ids(
            tool_calls,
            session_id="0123456789ab",
            round_index=1,
            workflow_phase="report_evidence",
        )
        args = json_lib.loads(rewritten[0]["function"]["arguments"])
        assert args["path"] == str(repo_root / "docs" / "development_log.md")

    def test_cursor_handoff_agent_auto_switches_to_ternion_full(self, client: TestClient) -> None:
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
