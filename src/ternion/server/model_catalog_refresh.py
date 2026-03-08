"""Helpers for manual and scheduled LiteLLM catalog refreshes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import get_args

import structlog

from ternion.core.config_store import (
    ModelCatalogRefreshConfig,
    ModelCatalogRefreshMode,
    UserConfig,
    config_store,
)
from ternion.core.model_catalog import model_catalog_service

logger = structlog.get_logger(__name__)

DEFAULT_REFRESH_TIME = "03:00"
RETRY_DELAY = timedelta(hours=1)
SCHEDULER_POLL_INTERVAL_SECONDS = 60
VALID_REFRESH_MODES = set(get_args(ModelCatalogRefreshMode))


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(UTC)


def format_utc_timestamp(value: datetime) -> str:
    """Serialize a UTC datetime to ISO-8601 with Z suffix."""

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp with optional Z suffix.

    Returns ``None`` for empty input or when parsing fails.
    """

    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def parse_time_of_day(value: str) -> tuple[int, int]:
    """Parse an ``HH:MM`` time-of-day string into ``(hour, minute)``.

    Raises:
        ValueError: If the value is not in ``HH:MM`` format or falls outside
            the valid 24-hour clock range.
    """

    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("TIME_OF_DAY_INVALID")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("TIME_OF_DAY_INVALID") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("TIME_OF_DAY_INVALID")
    return hour, minute


def normalize_time_of_day(value: str | None) -> str:
    """Validate and return a zero-padded ``HH:MM`` time string.

    Defaults to ``DEFAULT_REFRESH_TIME`` when ``value`` is ``None``.
    """

    hour, minute = parse_time_of_day(value or DEFAULT_REFRESH_TIME)
    return f"{hour:02d}:{minute:02d}"


def compute_next_refresh_at(
    settings: ModelCatalogRefreshConfig,
    now: datetime | None = None,
) -> str:
    """Compute the next scheduled refresh timestamp in UTC.

    Returns an empty string when automatic refresh is disabled.
    """

    if not settings.enabled:
        return ""

    current = now or utc_now()
    if settings.mode == "daily":
        try:
            hour, minute = parse_time_of_day(settings.time_of_day)
        except ValueError:
            hour, minute = parse_time_of_day(DEFAULT_REFRESH_TIME)
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        return format_utc_timestamp(candidate)

    interval = max(int(settings.interval_value or 1), 1)
    if settings.mode == "interval_weeks":
        delta = timedelta(weeks=interval)
    elif settings.mode == "interval_days":
        delta = timedelta(days=interval)
    else:
        logger.warning("model_catalog_refresh_unknown_mode", mode=settings.mode)
        delta = timedelta(days=interval)
    return format_utc_timestamp(current + delta)


def compute_retry_refresh_at(now: datetime | None = None) -> str:
    """Return the next retry time used after refresh failures."""

    return format_utc_timestamp((now or utc_now()) + RETRY_DELAY)


def is_refresh_due(
    settings: ModelCatalogRefreshConfig,
    now: datetime | None = None,
) -> bool:
    """Return whether an automatic refresh should run now.

    Invalid timestamps are treated as immediately due so the scheduler can
    recover from corrupted persisted state.
    """

    if not settings.enabled or not settings.next_refresh_at:
        return False
    next_refresh = parse_utc_timestamp(settings.next_refresh_at)
    if next_refresh is None:
        logger.warning(
            "model_catalog_refresh_invalid_timestamp",
            next_refresh_at=settings.next_refresh_at,
        )
        return True
    return next_refresh <= (now or utc_now())


def schedule_next_refresh(
    settings: ModelCatalogRefreshConfig,
    *,
    now: datetime | None = None,
) -> None:
    """Update next_refresh_at according to the configured schedule."""

    settings.next_refresh_at = compute_next_refresh_at(settings, now)


def schedule_retry_refresh(
    settings: ModelCatalogRefreshConfig,
    *,
    now: datetime | None = None,
) -> None:
    """Update next_refresh_at to the retry time after a failed refresh."""

    settings.next_refresh_at = compute_retry_refresh_at(now)


def save_refresh_state(config: UserConfig, *, trigger: str, outcome: str) -> None:
    """Persist refresh metadata and add context if saving fails."""

    try:
        config_store.save(config)
    except Exception:
        logger.warning(
            "model_catalog_refresh_state_save_failed",
            trigger=trigger,
            outcome=outcome,
            exc_info=True,
        )
        raise


async def refresh_catalog_and_update_schedule(trigger: str) -> dict:
    """Run a catalog refresh and persist scheduling metadata.

    Args:
        trigger: Refresh source, such as ``"manual"`` or ``"automatic"``.
    """

    refresh_started_at = utc_now()
    try:
        await model_catalog_service.refresh_snapshot()
        payload = await model_catalog_service.get_models_payload()
    except Exception:
        logger.warning("model_catalog_refresh_failed", trigger=trigger, exc_info=True)
        try:
            config = config_store.load()
            if config.model_catalog_refresh.enabled:
                schedule_retry_refresh(config.model_catalog_refresh, now=refresh_started_at)
                try:
                    save_refresh_state(config, trigger=trigger, outcome="retry_after_failure")
                except Exception:
                    logger.warning(
                        "model_catalog_refresh_retry_schedule_save_failed",
                        trigger=trigger,
                        exc_info=True,
                    )
        except Exception:
            logger.warning(
                "model_catalog_refresh_retry_schedule_update_failed",
                trigger=trigger,
                exc_info=True,
            )
        raise

    config = config_store.load()
    refresh_settings = config.model_catalog_refresh
    anomaly_detected = bool(payload.get("catalog_anomaly_detected"))
    requires_initialization = bool(payload.get("requires_initialization"))

    if anomaly_detected or requires_initialization:
        if refresh_settings.enabled:
            schedule_retry_refresh(refresh_settings, now=refresh_started_at)
        else:
            refresh_settings.next_refresh_at = ""
        save_refresh_state(config, trigger=trigger, outcome="anomalous")
        logger.warning(
            "model_catalog_refresh_anomalous",
            trigger=trigger,
            anomaly_detected=anomaly_detected,
            requires_initialization=requires_initialization,
            next_refresh_at=refresh_settings.next_refresh_at,
        )
        return payload

    refresh_settings.last_refresh_at = format_utc_timestamp(refresh_started_at)
    schedule_next_refresh(refresh_settings, now=refresh_started_at)
    save_refresh_state(config, trigger=trigger, outcome="completed")
    logger.info(
        "model_catalog_refresh_completed",
        trigger=trigger,
        model_count=payload.get("model_count", 0),
        last_refresh_at=refresh_settings.last_refresh_at,
        next_refresh_at=refresh_settings.next_refresh_at,
    )
    return payload


async def run_model_catalog_refresh_scheduler(stop_event: asyncio.Event) -> None:
    """Run the in-process automatic refresh loop until ``stop_event`` is set."""

    logger.info("model_catalog_refresh_scheduler_started")
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=SCHEDULER_POLL_INTERVAL_SECONDS,
                )
                break
            except TimeoutError:
                pass

            try:
                config = config_store.load()
                refresh_settings = config.model_catalog_refresh
                if refresh_settings.enabled and not refresh_settings.next_refresh_at:
                    schedule_next_refresh(refresh_settings)
                    config_store.save(config)
                elif is_refresh_due(refresh_settings):
                    try:
                        await refresh_catalog_and_update_schedule("automatic")
                    except Exception:
                        continue
            except Exception:
                logger.warning("model_catalog_refresh_scheduler_iteration_failed", exc_info=True)
    finally:
        logger.info("model_catalog_refresh_scheduler_stopped")
