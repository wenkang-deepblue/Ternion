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