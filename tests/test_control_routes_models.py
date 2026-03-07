"""
Tests for control-panel model catalog integration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from ternion.core.config_store import (
    ApiKeyEntry,
    ProviderConfig,
    RoleConfig,
    UserConfig,
)
from ternion.core.model_catalog import CatalogModel
from ternion.server.app import app


def _build_enabled_openai_config() -> UserConfig:
    """Create a config with OpenAI enabled and no role assignments."""
    config = UserConfig()
    config.execution_mode = "cursor_handoff"
    config.providers["openai"] = ProviderConfig(
        api_keys=[ApiKeyEntry(id="openai-1", name="OpenAI", api_key="sk-test")],
        selected_key_id="openai-1",
    )
    return config


def _build_catalog_model(
    model_id: str = "gpt-5.2-2025-12-11",
    provider: str = "openai",
    name: str = "GPT 5.2",
) -> CatalogModel:
    """Create a normalized catalog model for tests."""
    return CatalogModel(
        id=model_id,
        name=name,
        provider=provider,
        mode="chat",
        raw_key=model_id,
    )


class TestControlRoutesModelCatalog:
    """Tests for Phase 2 catalog integration in control routes."""

    def test_get_models_uses_catalog_service(self) -> None:
        """`GET /api/models` should return the catalog payload."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.load.return_value = _build_enabled_openai_config()
            mock_catalog_service.get_models_payload = AsyncMock(
                return_value={
                    "models": {
                        "openai": [
                            {
                                "id": "gpt-5.2-2025-12-11",
                                "name": "GPT 5.2",
                                "stale": False,
                                "pricing_available": True,
                            }
                        ],
                        "google": [],
                        "anthropic": [],
                    },
                    "last_updated_at": "2026-03-06T12:00:00Z",
                    "model_count": 1,
                    "catalog_initialized": True,
                    "requires_initialization": False,
                    "catalog_anomaly_detected": False,
                    "catalog_anomaly_summary": "",
                    "catalog_anomaly_updated_at": "",
                    "catalog_anomaly_providers": [],
                    "anomaly_report_available": False,
                }
            )

            client = TestClient(app)
            response = client.get("/api/models")

            assert response.status_code == 200
            assert response.json() == {
                "models": {
                    "openai": [
                        {
                            "id": "gpt-5.2-2025-12-11",
                            "name": "GPT 5.2",
                            "stale": False,
                            "pricing_available": True,
                        }
                    ],
                    "google": [],
                    "anthropic": [],
                },
                "last_updated_at": "2026-03-06T12:00:00Z",
                "model_count": 1,
                "catalog_initialized": True,
                "requires_initialization": False,
                "catalog_anomaly_detected": False,
                "catalog_anomaly_summary": "",
                "catalog_anomaly_updated_at": "",
                "catalog_anomaly_providers": [],
                "anomaly_report_available": False,
                "enabled_providers": ["openai"],
            }
            mock_catalog_service.get_models_payload.assert_awaited_once()

    def test_get_models_exposes_uninitialized_state(self) -> None:
        """`GET /api/models` should expose bootstrap status when catalog is empty."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = []
            mock_config_store.load.return_value = UserConfig()
            mock_catalog_service.get_models_payload = AsyncMock(
                return_value={
                    "models": {"openai": [], "google": [], "anthropic": []},
                    "last_updated_at": "",
                    "model_count": 0,
                    "catalog_initialized": False,
                    "requires_initialization": True,
                    "catalog_anomaly_detected": False,
                    "catalog_anomaly_summary": "",
                    "catalog_anomaly_updated_at": "",
                    "catalog_anomaly_providers": [],
                    "anomaly_report_available": False,
                }
            )

            client = TestClient(app)
            response = client.get("/api/models")

            assert response.status_code == 200
            assert response.json()["requires_initialization"] is True
            assert response.json()["catalog_initialized"] is False

    def test_refresh_models_returns_refreshed_payload(self) -> None:
        """`POST /api/models/refresh` should force a remote refresh for initialization."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.load.return_value = _build_enabled_openai_config()
            mock_catalog_service.refresh_snapshot = AsyncMock()
            mock_catalog_service.get_models_payload = AsyncMock(
                return_value={
                    "models": {
                        "openai": [{"id": "gpt-5.2-2025-12-11", "name": "GPT 5.2"}],
                        "google": [],
                        "anthropic": [],
                    },
                    "last_updated_at": "2026-03-06T12:30:00Z",
                    "model_count": 1,
                    "catalog_initialized": True,
                    "requires_initialization": False,
                    "catalog_anomaly_detected": False,
                    "catalog_anomaly_summary": "",
                    "catalog_anomaly_updated_at": "",
                    "catalog_anomaly_providers": [],
                    "anomaly_report_available": False,
                }
            )

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["catalog_initialized"] is True
            mock_catalog_service.refresh_snapshot.assert_awaited_once()

    def test_refresh_models_returns_error_when_refresh_raises(self) -> None:
        """`POST /api/models/refresh` should map refresh failures to HTTP 503."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = []
            mock_catalog_service.refresh_snapshot = AsyncMock(
                side_effect=RuntimeError("network unavailable")
            )

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 503
            assert response.json()["detail"] == "MODEL_CATALOG_REFRESH_FAILED"
            mock_catalog_service.get_models_payload.assert_not_called()

    def test_refresh_models_returns_error_when_initialization_still_missing(self) -> None:
        """`POST /api/models/refresh` should fail when no model list is obtained."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = []
            mock_config_store.load.return_value = UserConfig()
            mock_catalog_service.refresh_snapshot = AsyncMock()
            mock_catalog_service.get_models_payload = AsyncMock(
                return_value={
                    "models": {"openai": [], "google": [], "anthropic": []},
                    "last_updated_at": "",
                    "model_count": 0,
                    "catalog_initialized": False,
                    "requires_initialization": True,
                    "catalog_anomaly_detected": True,
                    "catalog_anomaly_summary": "Model catalog anomaly detected for anthropic.",
                    "catalog_anomaly_updated_at": "2026-03-06T12:45:00Z",
                    "catalog_anomaly_providers": ["anthropic"],
                    "anomaly_report_available": True,
                }
            )

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 503
            assert response.json()["detail"] == "MODEL_CATALOG_REFRESH_FAILED"

    def test_refresh_models_returns_payload_when_last_successful_snapshot_is_preserved(
        self,
    ) -> None:
        """`POST /api/models/refresh` should surface anomaly state with preserved models."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_catalog_service.refresh_snapshot = AsyncMock()
            mock_catalog_service.get_models_payload = AsyncMock(
                return_value={
                    "models": {
                        "openai": [{"id": "gpt-5.2-2025-12-11", "name": "GPT 5.2"}],
                        "google": [{"id": "gemini-3-pro", "name": "Gemini 3 Pro"}],
                        "anthropic": [
                            {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5"}
                        ],
                    },
                    "last_updated_at": "2026-03-06T12:50:00Z",
                    "model_count": 3,
                    "catalog_initialized": True,
                    "requires_initialization": False,
                    "catalog_anomaly_detected": True,
                    "catalog_anomaly_summary": "Model catalog anomaly detected for anthropic.",
                    "catalog_anomaly_updated_at": "2026-03-06T12:50:00Z",
                    "catalog_anomaly_providers": ["anthropic"],
                    "anomaly_report_available": True,
                }
            )

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 200
            assert response.json()["success"] is False
            assert response.json()["catalog_anomaly_detected"] is True
            assert response.json()["anomaly_report_available"] is True

    def test_get_model_anomaly_report_returns_markdown(self) -> None:
        """`GET /api/models/anomaly-report` should expose the latest Markdown report."""
        with patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service:
            mock_catalog_service.get_anomaly_report_markdown.return_value = (
                "# Model Catalog Anomaly Report\n\n## Summary\n- Example"
            )

            client = TestClient(app)
            response = client.get("/api/models/anomaly-report")

            assert response.status_code == 200
            assert response.text.startswith("# Model Catalog Anomaly Report")
            assert response.headers["content-type"].startswith("text/markdown")

    def test_get_model_anomaly_report_returns_404_when_unavailable(self) -> None:
        """`GET /api/models/anomaly-report` should return 404 when no report exists."""
        with patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service:
            mock_catalog_service.get_anomaly_report_markdown.return_value = None

            client = TestClient(app)
            response = client.get("/api/models/anomaly-report")

            assert response.status_code == 404
            assert response.json()["detail"] == "MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND"

    def test_update_config_validates_roles_against_catalog(self) -> None:
        """`POST /api/config` should save when every role exists in the catalog."""
        config = _build_enabled_openai_config()
        catalog_model = _build_catalog_model()

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
            patch("ternion.server.control_routes.log_manager") as mock_log_manager,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.to_safe_dict.return_value = {"roles": "safe"}
            mock_catalog_service.get_model = AsyncMock(return_value=catalog_model)
            mock_log_manager.emit = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={
                    "execution_mode": "cursor_handoff",
                    "roles": {
                        "ternion_a": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                        "ternion_b": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                        "ternion_c": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                        "arbiter": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                    },
                },
            )

            assert response.status_code == 200
            assert response.json() == {"success": True, "config": {"roles": "safe"}}
            assert mock_config_store.save.call_count == 1

            saved_config = mock_config_store.save.call_args.args[0]
            assert saved_config.roles["ternion_a"] == RoleConfig(
                provider="openai",
                model="gpt-5.2-2025-12-11",
            )

    def test_update_config_rejects_model_outside_current_catalog(self) -> None:
        """`POST /api/config` should fail when provider/model do not match the catalog."""
        config = UserConfig()
        config.execution_mode = "cursor_handoff"
        config.providers["google"] = ProviderConfig(
            api_keys=[ApiKeyEntry(id="google-1", name="Google", api_key="google-key")],
            selected_key_id="google-1",
        )
        catalog_model = _build_catalog_model(provider="openai")

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["google"]
            mock_catalog_service.get_model = AsyncMock(return_value=catalog_model)

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={
                    "execution_mode": "cursor_handoff",
                    "roles": {
                        "ternion_a": {"provider": "google", "model": "gpt-5.2-2025-12-11"},
                        "ternion_b": {"provider": "google", "model": "gpt-5.2-2025-12-11"},
                        "ternion_c": {"provider": "google", "model": "gpt-5.2-2025-12-11"},
                        "arbiter": {"provider": "google", "model": "gpt-5.2-2025-12-11"},
                    },
                },
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "MODEL_NOT_AVAILABLE"
            mock_config_store.save.assert_not_called()

    def test_update_config_rejects_unknown_model_not_in_catalog(self) -> None:
        """`POST /api/config` should fail when the model is absent from the catalog."""
        config = _build_enabled_openai_config()

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_catalog_service.get_model = AsyncMock(return_value=None)

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={
                    "execution_mode": "cursor_handoff",
                    "roles": {
                        "ternion_a": {"provider": "openai", "model": "gpt-missing"},
                        "ternion_b": {"provider": "openai", "model": "gpt-missing"},
                        "ternion_c": {"provider": "openai", "model": "gpt-missing"},
                        "arbiter": {"provider": "openai", "model": "gpt-missing"},
                    },
                },
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "MODEL_NOT_AVAILABLE"
            mock_config_store.save.assert_not_called()

    def test_log_role_selection_uses_catalog_validation(self) -> None:
        """`POST /api/roles/selection` should validate against the catalog."""
        catalog_model = _build_catalog_model()

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
            patch("ternion.server.control_routes.log_manager") as mock_log_manager,
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_catalog_service.get_model = AsyncMock(return_value=catalog_model)
            mock_log_manager.emit = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/roles/selection",
                json={
                    "role": "arbiter",
                    "provider": "openai",
                    "model": "gpt-5.2-2025-12-11",
                },
            )

            assert response.status_code == 200
            assert response.json() == {
                "success": True,
                "message": "ROLE_MODEL_SELECTION_LOGGED",
                "pending": True,
            }

    def test_log_role_selection_rejects_provider_model_mismatch(self) -> None:
        """`POST /api/roles/selection` should reject models from another provider."""
        catalog_model = _build_catalog_model(provider="openai")

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.model_catalog_service") as mock_catalog_service,
        ):
            mock_config_store.get_enabled_providers.return_value = ["google"]
            mock_catalog_service.get_model = AsyncMock(return_value=catalog_model)

            client = TestClient(app)
            response = client.post(
                "/api/roles/selection",
                json={
                    "role": "arbiter",
                    "provider": "google",
                    "model": "gpt-5.2-2025-12-11",
                },
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "MODEL_NOT_AVAILABLE"
