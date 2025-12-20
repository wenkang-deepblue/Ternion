"""
Tests for the FastAPI server.
"""

import pytest
from fastapi.testclient import TestClient

from ternion.server.app import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


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

    def test_chat_completions_basic(self, client: TestClient) -> None:
        """Test basic chat completion request."""
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

    def test_chat_completions_streaming(self, client: TestClient) -> None:
        """Test streaming chat completion request."""
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
