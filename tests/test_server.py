"""
Tests for the FastAPI server.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from ternion.server.app import app
from ternion.core.config_store import RoleConfig


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

