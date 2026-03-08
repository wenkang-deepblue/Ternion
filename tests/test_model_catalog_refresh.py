"""Tests for model catalog refresh scheduling helpers."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ternion.core.config_store import ModelCatalogRefreshConfig
from ternion.server.model_catalog_refresh import (
    compute_next_refresh_at,
    compute_retry_refresh_at,
    is_refresh_due,
    normalize_time_of_day,
    parse_time_of_day,
    parse_utc_timestamp,
    refresh_catalog_and_update_schedule,
    run_model_catalog_refresh_scheduler,
)


def test_compute_next_refresh_at_daily_rolls_over_to_next_day_when_past() -> None:
    """Daily refresh should roll forward when today's slot already passed."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        mode="daily",
        time_of_day="03:00",
    )

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-07T03:00:00Z"


def test_compute_next_refresh_at_daily_targets_same_day_when_future() -> None:
    """Daily refresh should keep the current day when the slot is still ahead."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        mode="daily",
        time_of_day="23:00",
    )

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-06T23:00:00Z"


def test_compute_next_refresh_at_for_interval_days() -> None:
    """Day interval refresh should add the configured number of days."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        mode="interval_days",
        interval_value=3,
    )

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-09T04:15:00Z"


def test_compute_next_refresh_at_for_interval_weeks() -> None:
    """Weekly interval refresh should add whole weeks from the current time."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        mode="interval_weeks",
        interval_value=2,
    )

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-20T04:15:00Z"


def test_compute_next_refresh_at_returns_empty_when_disabled() -> None:
    """Disabled schedules should not emit a next refresh timestamp."""

    settings = ModelCatalogRefreshConfig(enabled=False)

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == ""


def test_compute_next_refresh_at_clamps_non_positive_interval_to_one() -> None:
    """Interval-based schedules should clamp invalid values to one unit."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        mode="interval_days",
        interval_value=0,
    )

    result = compute_next_refresh_at(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-07T04:15:00Z"


def test_compute_retry_refresh_at_adds_one_hour() -> None:
    """Retry scheduling should wait one hour after a failed refresh."""

    result = compute_retry_refresh_at(now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC))

    assert result == "2026-03-06T05:15:00Z"


def test_is_refresh_due_returns_false_when_disabled() -> None:
    """Disabled schedules should never run automatically."""

    settings = ModelCatalogRefreshConfig(
        enabled=False,
        next_refresh_at="2026-03-06T03:00:00Z",
    )

    assert is_refresh_due(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC)) is False


def test_is_refresh_due_returns_false_when_timestamp_missing() -> None:
    """Missing timestamps should keep the scheduler idle."""

    settings = ModelCatalogRefreshConfig(enabled=True, next_refresh_at="")

    assert is_refresh_due(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC)) is False


def test_is_refresh_due_returns_true_for_past_timestamp() -> None:
    """Past timestamps should trigger automatic refresh."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        next_refresh_at="2026-03-06T03:00:00Z",
    )

    assert is_refresh_due(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC)) is True


def test_is_refresh_due_returns_false_for_future_timestamp() -> None:
    """Future timestamps should not trigger refresh yet."""

    settings = ModelCatalogRefreshConfig(
        enabled=True,
        next_refresh_at="2026-03-07T03:00:00Z",
    )

    assert is_refresh_due(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC)) is False


def test_is_refresh_due_returns_true_for_invalid_timestamp() -> None:
    """Corrupted timestamps should fail open and trigger a recovery refresh."""

    settings = ModelCatalogRefreshConfig(enabled=True, next_refresh_at="not-a-timestamp")

    assert is_refresh_due(settings, now=datetime(2026, 3, 6, 4, 15, tzinfo=UTC)) is True


def test_normalize_time_of_day_pads_hours_and_minutes() -> None:
    """Time normalization should return zero-padded HH:MM values."""

    assert normalize_time_of_day("4:5") == "04:05"


def test_normalize_time_of_day_defaults_when_input_missing() -> None:
    """Missing values should fall back to the default daily refresh time."""

    assert normalize_time_of_day(None) == "03:00"


def test_normalize_time_of_day_rejects_invalid_clock_values() -> None:
    """Out-of-range hour or minute values should be rejected."""

    with pytest.raises(ValueError, match="TIME_OF_DAY_INVALID"):
        normalize_time_of_day("25:61")


def test_parse_time_of_day_rejects_non_numeric_values() -> None:
    """Non-numeric time components should raise the normalized error code."""

    with pytest.raises(ValueError, match="TIME_OF_DAY_INVALID"):
        parse_time_of_day("ab:cd")


def test_parse_utc_timestamp_returns_none_for_invalid_input() -> None:
    """Invalid timestamps should not crash schedule parsing."""

    assert parse_utc_timestamp("not-a-timestamp") is None


@pytest.mark.asyncio
async def test_refresh_catalog_success_updates_schedule() -> None:
    """Successful refresh should persist last and next refresh timestamps."""

    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(
        enabled=True,
        mode="daily",
        time_of_day="03:00",
    )

    with (
        patch("ternion.server.model_catalog_refresh.model_catalog_service") as mock_catalog_service,
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch(
            "ternion.server.model_catalog_refresh.utc_now",
            return_value=datetime(2026, 3, 6, 4, 15, tzinfo=UTC),
        ),
    ):
        mock_catalog_service.refresh_snapshot = AsyncMock()
        mock_catalog_service.get_models_payload = AsyncMock(
            return_value={
                "catalog_anomaly_detected": False,
                "requires_initialization": False,
                "model_count": 3,
            }
        )
        mock_config_store.load.return_value = config

        payload = await refresh_catalog_and_update_schedule("manual")

        assert payload["model_count"] == 3
        assert config.model_catalog_refresh.last_refresh_at == "2026-03-06T04:15:00Z"
        assert config.model_catalog_refresh.next_refresh_at == "2026-03-07T03:00:00Z"
        mock_config_store.save.assert_called_once_with(config)


@pytest.mark.asyncio
async def test_refresh_catalog_anomaly_schedules_retry_when_enabled() -> None:
    """Catalog anomalies should schedule a retry instead of the normal cadence."""

    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(enabled=True)

    with (
        patch("ternion.server.model_catalog_refresh.model_catalog_service") as mock_catalog_service,
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch(
            "ternion.server.model_catalog_refresh.utc_now",
            return_value=datetime(2026, 3, 6, 4, 15, tzinfo=UTC),
        ),
    ):
        mock_catalog_service.refresh_snapshot = AsyncMock()
        mock_catalog_service.get_models_payload = AsyncMock(
            return_value={
                "catalog_anomaly_detected": True,
                "requires_initialization": False,
                "model_count": 2,
            }
        )
        mock_config_store.load.return_value = config

        payload = await refresh_catalog_and_update_schedule("automatic")

        assert payload["catalog_anomaly_detected"] is True
        assert config.model_catalog_refresh.next_refresh_at == "2026-03-06T05:15:00Z"
        mock_config_store.save.assert_called_once_with(config)


@pytest.mark.asyncio
async def test_refresh_catalog_failure_schedules_retry_when_enabled() -> None:
    """Refresh failures should schedule a retry without swallowing the error."""

    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(enabled=True)

    with (
        patch("ternion.server.model_catalog_refresh.model_catalog_service") as mock_catalog_service,
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch(
            "ternion.server.model_catalog_refresh.utc_now",
            return_value=datetime(2026, 3, 6, 4, 15, tzinfo=UTC),
        ),
    ):
        mock_catalog_service.refresh_snapshot = AsyncMock(
            side_effect=RuntimeError("network unavailable")
        )
        mock_config_store.load.return_value = config

        with pytest.raises(RuntimeError, match="network unavailable"):
            await refresh_catalog_and_update_schedule("automatic")

        assert config.model_catalog_refresh.next_refresh_at == "2026-03-06T05:15:00Z"
        mock_config_store.save.assert_called_once_with(config)


@pytest.mark.asyncio
async def test_refresh_catalog_failure_does_not_mask_original_error_when_retry_save_fails() -> None:
    """Retry schedule persistence failures should not replace the original refresh error."""

    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(enabled=True)

    with (
        patch("ternion.server.model_catalog_refresh.model_catalog_service") as mock_catalog_service,
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch("ternion.server.model_catalog_refresh.logger") as mock_logger,
        patch(
            "ternion.server.model_catalog_refresh.utc_now",
            return_value=datetime(2026, 3, 6, 4, 15, tzinfo=UTC),
        ),
    ):
        mock_catalog_service.refresh_snapshot = AsyncMock(side_effect=RuntimeError("catalog down"))
        mock_config_store.load.return_value = config
        mock_config_store.save.side_effect = OSError("disk full")

        with pytest.raises(RuntimeError, match="catalog down"):
            await refresh_catalog_and_update_schedule("automatic")

        assert config.model_catalog_refresh.next_refresh_at == "2026-03-06T05:15:00Z"
        assert mock_logger.warning.call_count >= 2


@pytest.mark.asyncio
async def test_refresh_catalog_failure_skips_retry_when_disabled() -> None:
    """Disabled schedules should not write retry metadata after refresh failures."""

    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(enabled=False)

    with (
        patch("ternion.server.model_catalog_refresh.model_catalog_service") as mock_catalog_service,
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
    ):
        mock_catalog_service.refresh_snapshot = AsyncMock(side_effect=RuntimeError("network unavailable"))
        mock_config_store.load.return_value = config

        with pytest.raises(RuntimeError, match="network unavailable"):
            await refresh_catalog_and_update_schedule("manual")

        mock_config_store.save.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_exits_when_stop_event_is_set() -> None:
    """Scheduler should terminate immediately when the stop event is already set."""

    stop_event = asyncio.Event()
    stop_event.set()

    await asyncio.wait_for(run_model_catalog_refresh_scheduler(stop_event), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_initializes_missing_next_refresh_at() -> None:
    """Scheduler should seed the first scheduled timestamp when enabled."""

    stop_event = asyncio.Event()
    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(enabled=True, next_refresh_at="")

    def save_side_effect(_config: object) -> None:
        stop_event.set()

    with (
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch("ternion.server.model_catalog_refresh.SCHEDULER_POLL_INTERVAL_SECONDS", 0.01),
    ):
        mock_config_store.load.return_value = config
        mock_config_store.save.side_effect = save_side_effect

        await asyncio.wait_for(run_model_catalog_refresh_scheduler(stop_event), timeout=0.2)

        mock_config_store.save.assert_called_once_with(config)
        assert config.model_catalog_refresh.next_refresh_at


@pytest.mark.asyncio
async def test_scheduler_triggers_refresh_when_due() -> None:
    """Scheduler should execute an automatic refresh when the schedule is due."""

    stop_event = asyncio.Event()
    config = MagicMock()
    config.model_catalog_refresh = ModelCatalogRefreshConfig(
        enabled=True,
        next_refresh_at="2026-03-06T03:00:00Z",
    )

    async def refresh_side_effect(trigger: str) -> dict:
        stop_event.set()
        return {"trigger": trigger}

    with (
        patch("ternion.server.model_catalog_refresh.config_store") as mock_config_store,
        patch(
            "ternion.server.model_catalog_refresh.refresh_catalog_and_update_schedule",
            new=AsyncMock(side_effect=refresh_side_effect),
        ) as mock_refresh,
        patch("ternion.server.model_catalog_refresh.SCHEDULER_POLL_INTERVAL_SECONDS", 0.01),
        patch(
            "ternion.server.model_catalog_refresh.utc_now",
            return_value=datetime(2026, 3, 6, 4, 15, tzinfo=UTC),
        ),
    ):
        mock_config_store.load.return_value = config

        await asyncio.wait_for(run_model_catalog_refresh_scheduler(stop_event), timeout=0.2)

        mock_refresh.assert_awaited_once_with("automatic")
