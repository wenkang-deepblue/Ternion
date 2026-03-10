"""
Tests for control-panel model catalog integration.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

from fastapi.testclient import TestClient

from ternion.core.config_store import (
    ApiKeyEntry,
    ProviderConfig,
    RoleConfig,
    UserConfig,
)
from ternion.core.model_catalog import CatalogModel
from ternion.core.model_probe import ModelAvailabilityProbeResult
from ternion.server.app import app

CONTROL_ROUTES_CONFIG_STORE = "ternion.server.control_routes.config_store"
CONTROL_ROUTES_MODEL_CATALOG = "ternion.server.control_routes.model_catalog_service"
CONTROL_ROUTES_LOG_MANAGER = "ternion.server.control_routes.log_manager"
CONTROL_ROUTES_PROBE_SERVICE = "ternion.server.control_routes.model_availability_probe_service"


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


def _build_probe_result(
    *,
    ok: bool = True,
    provider: str = "openai",
    model: str = "gpt-5.2-2025-12-11",
    code: str = "SUCCESS",
    message: str = "",
    refresh_suggested: bool = False,
) -> ModelAvailabilityProbeResult:
    """Create a model probe result for tests."""
    return ModelAvailabilityProbeResult(
        ok=ok,
        provider=provider,
        model=model,
        code=code,
        message=message,
        refresh_suggested=refresh_suggested,
    )


class TestControlRoutesModelCatalog:
    """Tests for model catalog integration in control routes."""

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
            mock_catalog_service.get_models_payload.assert_awaited_once_with(
                allow_remote_fetch=False
            )

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
            patch(
                "ternion.server.control_routes.refresh_catalog_and_update_schedule",
                new=AsyncMock(
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
                ),
            ) as mock_refresh_catalog,
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.load.return_value = _build_enabled_openai_config()

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["catalog_initialized"] is True
            mock_refresh_catalog.assert_awaited_once_with("manual")

    def test_refresh_models_returns_error_when_refresh_raises(self) -> None:
        """`POST /api/models/refresh` should map refresh failures to HTTP 503."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch(
                "ternion.server.control_routes.refresh_catalog_and_update_schedule",
                new=AsyncMock(side_effect=RuntimeError("network unavailable")),
            ) as mock_refresh_catalog,
        ):
            mock_config_store.get_enabled_providers.return_value = []

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 503
            assert response.json()["detail"] == "MODEL_CATALOG_REFRESH_FAILED"
            mock_refresh_catalog.assert_awaited_once_with("manual")

    def test_refresh_models_returns_error_when_initialization_still_missing(self) -> None:
        """`POST /api/models/refresh` should fail when no model list is obtained."""
        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch(
                "ternion.server.control_routes.refresh_catalog_and_update_schedule",
                new=AsyncMock(
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
                ),
            ),
        ):
            mock_config_store.get_enabled_providers.return_value = []
            mock_config_store.load.return_value = UserConfig()

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
            patch(
                "ternion.server.control_routes.refresh_catalog_and_update_schedule",
                new=AsyncMock(
                    return_value={
                        "models": {
                            "openai": [{"id": "gpt-5.2-2025-12-11", "name": "GPT 5.2"}],
                            "google": [{"id": "gemini-3-pro", "name": "Gemini 3 Pro"}],
                            "anthropic": [
                                {
                                    "id": "claude-sonnet-4-5-20250929",
                                    "name": "Claude Sonnet 4.5",
                                }
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
                ),
            ),
        ):
            mock_config_store.get_enabled_providers.return_value = ["openai"]

            client = TestClient(app)
            response = client.post("/api/models/refresh")

            assert response.status_code == 200
            assert response.json()["success"] is False
            assert response.json()["catalog_anomaly_detected"] is True
            assert response.json()["anomaly_report_available"] is True

    def test_update_config_accepts_model_catalog_refresh_settings(self) -> None:
        """`POST /api/config` should persist automatic refresh scheduling."""
        config = UserConfig()

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.log_manager") as mock_log_manager,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.to_safe_dict.return_value = {"model_catalog_refresh": "safe"}
            mock_log_manager.emit = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={
                    "model_catalog_refresh": {
                        "enabled": True,
                        "mode": "interval_weeks",
                        "time_of_day": "04:30",
                        "interval_value": 2,
                    }
                },
            )

            assert response.status_code == 200
            assert response.json() == {"success": True, "config": {"model_catalog_refresh": "safe"}}
            assert config.model_catalog_refresh.enabled is True
            assert config.model_catalog_refresh.mode == "interval_weeks"
            assert config.model_catalog_refresh.time_of_day == "04:30"
            assert config.model_catalog_refresh.interval_value == 2
            assert config.model_catalog_refresh.next_refresh_at
            mock_config_store.save.assert_called_once_with(config)

    def test_update_config_rejects_invalid_model_catalog_refresh_time(self) -> None:
        """`POST /api/config` should reject invalid automatic refresh times."""
        with patch("ternion.server.control_routes.config_store") as mock_config_store:
            mock_config_store.load.return_value = UserConfig()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={"model_catalog_refresh": {"enabled": True, "time_of_day": "25:61"}},
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "INVALID_MODEL_CATALOG_REFRESH_TIME"

    def test_update_config_rejects_invalid_model_catalog_refresh_mode(self) -> None:
        """`POST /api/config` should reject unknown automatic refresh modes."""
        with patch("ternion.server.control_routes.config_store") as mock_config_store:
            mock_config_store.load.return_value = UserConfig()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={"model_catalog_refresh": {"enabled": True, "mode": "hourly"}},
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "INVALID_MODEL_CATALOG_REFRESH_MODE"

    def test_update_config_rejects_non_positive_model_catalog_refresh_interval(self) -> None:
        """`POST /api/config` should reject non-positive refresh intervals."""
        with patch("ternion.server.control_routes.config_store") as mock_config_store:
            mock_config_store.load.return_value = UserConfig()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={"model_catalog_refresh": {"enabled": True, "interval_value": 0}},
            )

            assert response.status_code == 400
            assert response.json()["detail"] == "INVALID_MODEL_CATALOG_REFRESH_INTERVAL"

    def test_update_config_disabling_refresh_clears_next_refresh_at(self) -> None:
        """`POST /api/config` should clear next_refresh_at when auto-refresh is disabled."""
        config = UserConfig()
        config.model_catalog_refresh.enabled = True
        config.model_catalog_refresh.next_refresh_at = "2026-03-07T03:00:00Z"

        with (
            patch("ternion.server.control_routes.config_store") as mock_config_store,
            patch("ternion.server.control_routes.log_manager") as mock_log_manager,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.to_safe_dict.return_value = {"model_catalog_refresh": "safe"}
            mock_log_manager.emit = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={"model_catalog_refresh": {"enabled": False}},
            )

            assert response.status_code == 200
            assert config.model_catalog_refresh.enabled is False
            assert config.model_catalog_refresh.next_refresh_at == ""
            mock_config_store.save.assert_called_once_with(config)

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
            patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
            patch(CONTROL_ROUTES_MODEL_CATALOG) as mock_catalog_service,
            patch(CONTROL_ROUTES_LOG_MANAGER) as mock_log_manager,
            patch(CONTROL_ROUTES_PROBE_SERVICE) as mock_probe_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.get_provider_api_key.return_value = "sk-test"
            mock_config_store.to_safe_dict.return_value = {"roles": "safe"}
            mock_catalog_service.get_model_cached.return_value = catalog_model
            mock_probe_service.probe_model = AsyncMock(return_value=_build_probe_result())
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
            mock_probe_service.probe_model.assert_awaited_once_with(
                provider="openai",
                model="gpt-5.2-2025-12-11",
                api_key="sk-test",
            )

            saved_config = mock_config_store.save.call_args.args[0]
            assert saved_config.roles["ternion_a"] == RoleConfig(
                provider="openai",
                model="gpt-5.2-2025-12-11",
            )

    def test_update_config_does_not_save_when_probe_reports_model_unavailable(self) -> None:
        """`POST /api/config` should reject the save when provider probe fails."""
        config = _build_enabled_openai_config()
        catalog_model = _build_catalog_model()

        with (
            patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
            patch(CONTROL_ROUTES_MODEL_CATALOG) as mock_catalog_service,
            patch(CONTROL_ROUTES_PROBE_SERVICE) as mock_probe_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.get_provider_api_key.return_value = "sk-test"
            mock_catalog_service.get_model_cached.return_value = catalog_model
            mock_probe_service.probe_model = AsyncMock(
                return_value=_build_probe_result(
                    ok=False,
                    code="MODEL_UNAVAILABLE",
                    message="model not found",
                    refresh_suggested=True,
                )
            )

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

            assert response.status_code == 400
            assert response.json() == {
                "detail": "MODEL_UNAVAILABLE",
                "provider": "openai",
                "model": "gpt-5.2-2025-12-11",
                "message": "model not found",
                "refresh_suggested": True,
            }
            mock_config_store.save.assert_not_called()

    def test_update_config_probes_duplicate_provider_model_only_once(self) -> None:
        """`POST /api/config` should deduplicate repeated provider/model probes."""
        config = _build_enabled_openai_config()
        catalog_model = _build_catalog_model()

        with (
            patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
            patch(CONTROL_ROUTES_MODEL_CATALOG) as mock_catalog_service,
            patch(CONTROL_ROUTES_LOG_MANAGER) as mock_log_manager,
            patch(CONTROL_ROUTES_PROBE_SERVICE) as mock_probe_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai"]
            mock_config_store.get_provider_api_key.return_value = "sk-test"
            mock_config_store.to_safe_dict.return_value = {"roles": "safe"}
            mock_catalog_service.get_model_cached.return_value = catalog_model
            mock_probe_service.probe_model = AsyncMock(return_value=_build_probe_result())
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
            mock_probe_service.probe_model.assert_awaited_once()

    def test_update_config_probes_each_unique_provider_model_pair_once(self) -> None:
        """`POST /api/config` should probe each unique provider/model pair once."""
        config = UserConfig()
        config.execution_mode = "cursor_handoff"
        config.providers["openai"] = ProviderConfig(
            api_keys=[ApiKeyEntry(id="openai-1", name="OpenAI", api_key="sk-openai")],
            selected_key_id="openai-1",
        )
        config.providers["google"] = ProviderConfig(
            api_keys=[ApiKeyEntry(id="google-1", name="Google", api_key="google-key")],
            selected_key_id="google-1",
        )

        def get_model(model_id: str) -> CatalogModel | None:
            if model_id == "gpt-5.2-2025-12-11":
                return _build_catalog_model()
            if model_id == "gemini-3-pro":
                return _build_catalog_model(
                    model_id="gemini-3-pro",
                    provider="google",
                    name="Gemini 3 Pro",
                )
            return None

        with (
            patch(CONTROL_ROUTES_CONFIG_STORE) as mock_config_store,
            patch(CONTROL_ROUTES_MODEL_CATALOG) as mock_catalog_service,
            patch(CONTROL_ROUTES_LOG_MANAGER) as mock_log_manager,
            patch(CONTROL_ROUTES_PROBE_SERVICE) as mock_probe_service,
        ):
            mock_config_store.load.return_value = config
            mock_config_store.get_enabled_providers.return_value = ["openai", "google"]
            mock_config_store.get_provider_api_key.side_effect = lambda provider: {
                "openai": "sk-openai",
                "google": "google-key",
            }[provider]
            mock_config_store.to_safe_dict.return_value = {"roles": "safe"}
            mock_catalog_service.get_model_cached.side_effect = get_model
            mock_probe_service.probe_model = AsyncMock(
                side_effect=[
                    _build_probe_result(
                        provider="google",
                        model="gemini-3-pro",
                    ),
                    _build_probe_result(),
                ]
            )
            mock_log_manager.emit = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/config",
                json={
                    "execution_mode": "cursor_handoff",
                    "roles": {
                        "ternion_a": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                        "ternion_b": {"provider": "google", "model": "gemini-3-pro"},
                        "ternion_c": {"provider": "openai", "model": "gpt-5.2-2025-12-11"},
                        "arbiter": {"provider": "google", "model": "gemini-3-pro"},
                    },
                },
            )

            assert response.status_code == 200
            assert mock_probe_service.probe_model.await_count == 2
            mock_probe_service.probe_model.assert_has_awaits(
                [
                    call(
                        provider="google",
                        model="gemini-3-pro",
                        api_key="google-key",
                    ),
                    call(
                        provider="openai",
                        model="gpt-5.2-2025-12-11",
                        api_key="sk-openai",
                    ),
                ]
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
            mock_catalog_service.get_model_cached.return_value = catalog_model

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
            mock_catalog_service.get_model_cached.return_value = None

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
            mock_catalog_service.get_model_cached.return_value = catalog_model
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
            mock_catalog_service.get_model_cached.return_value = catalog_model

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
