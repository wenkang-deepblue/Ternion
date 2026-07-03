"""
Budget management for Ternion.

Tracks API usage costs, enforces budget limits, and persists monthly usage
to a local file. Provides alerts when approaching budget thresholds.
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings

from ternion.core.model_catalog import LiteLLMModelCatalogService, model_catalog_service
from ternion.utils.i18n import MessageKey, t

logger = structlog.get_logger(__name__)


class CostControlSettings(BaseSettings):
    """Cost control configuration."""

    monthly_limit_usd: float = 50.0
    alert_threshold: float = 0.9


class CostBreakdown(BaseModel):
    """Structured pricing result for one request."""

    input_cost: float = 0.0
    output_cost: float = 0.0
    thoughts_cost: float = 0.0

    @property
    def total_cost(self) -> float:
        """Return the sum of input, output, and thoughts costs."""
        return self.input_cost + self.output_cost + self.thoughts_cost


class UsageEntry(BaseModel):
    """Single API request usage record."""

    timestamp: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    thoughts_cost: float = 0.0


class ProviderDayUsage(BaseModel):
    """Per-provider daily usage totals."""

    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0


class DailySummary(BaseModel):
    """Aggregated daily usage."""

    date: str = ""
    providers: dict[str, dict] = Field(default_factory=dict)
    total_cost: float = 0.0


class MonthlyTotal(BaseModel):
    """Monthly usage totals."""

    total_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0


class UsageStore(BaseModel):
    """Complete usage data store."""

    today: str = ""
    today_records: list[dict] = Field(default_factory=list)
    daily_summaries: list[dict] = Field(default_factory=list)
    monthly_totals: dict[str, dict] = Field(default_factory=dict)


class BudgetManager:
    """
    Manages API usage costs and budget enforcement.

    Features:
    - Track costs per request with timestamps
    - Daily aggregation of usage
    - Monthly usage totals with permanent history
    - Budget limit checking
    - Real-time usage summary for UI
    """

    def __init__(
        self,
        settings: CostControlSettings | None = None,
        usage_file: Path | None = None,
        catalog_service: LiteLLMModelCatalogService | None = None,
    ) -> None:
        """
        Initialize budget manager.

        Args:
            settings: Cost control settings
            usage_file: Path to store usage data (defaults to ~/.ternion/usage.json)
            catalog_service: Optional model catalog used for pricing lookups
        """
        self.settings = settings or CostControlSettings()
        self.usage_file = usage_file or Path.home() / ".ternion" / "usage.json"
        self.catalog_service = catalog_service or model_catalog_service
        self._test_mode = False
        self._save_failures = 0
        self._store: UsageStore | None = None
        self._load_usage()

    def _get_today(self) -> str:
        """Get current date in YYYY-MM-DD format using local timezone."""
        return datetime.now().strftime("%Y-%m-%d")

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        # Anchor month to test fixture date for deterministic results
        if self._test_mode and self._store and self._store.today:
            return self._store.today[:7]
        return datetime.now().strftime("%Y-%m")

    def _load_usage(self) -> None:
        """Load usage from file, check for day rollover."""
        today = self._get_today()

        if self.usage_file.exists():
            try:
                with open(self.usage_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._store = UsageStore.model_validate(data)

                    # Skip day rollover in test mode
                    if self._test_mode:
                        return

                    # Check for day rollover
                    if self._store.today and self._store.today != today:
                        self._perform_day_rollover()
                        self._store.today = today
                        self._save_usage()
                    elif not self._store.today:
                        self._store.today = today
            except (json.JSONDecodeError, ValidationError) as e:
                self._backup_invalid_usage_file()
                logger.warning(
                    "budget_load_invalid_data",
                    error_type=type(e).__name__,
                    error=str(e),
                    path=str(self.usage_file),
                )
                self._store = UsageStore(today=today)
            except OSError as e:
                logger.error(
                    "budget_load_error",
                    error_type=type(e).__name__,
                    error=str(e),
                    path=str(self.usage_file),
                )
                self._store = UsageStore(today=today)
        else:
            self._store = UsageStore(today=today)
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)

    def _backup_invalid_usage_file(self) -> None:
        """Preserve the current usage file before resetting an invalid store."""
        backup_path = self.usage_file.with_suffix(f"{self.usage_file.suffix}.corrupt")
        try:
            shutil.copy2(self.usage_file, backup_path)
        except OSError as e:
            logger.warning(
                "budget_corrupt_backup_failed",
                error_type=type(e).__name__,
                error=str(e),
                path=str(self.usage_file),
                backup_path=str(backup_path),
            )

    def _save_usage(self) -> bool:
        """Save current usage to file and report whether persistence succeeded."""
        if self._store is None:
            return False

        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.usage_file.parent, suffix=".tmp", prefix="usage_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._store.model_dump(), f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.usage_file)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            self._save_failures = 0
            return True
        except Exception as e:
            self._save_failures += 1
            logger.error(
                "budget_save_error",
                error_type=type(e).__name__,
                error=str(e),
                path=str(self.usage_file),
                consecutive_failures=self._save_failures,
            )
            return False

    def _round_cost_breakdown(self, breakdown: CostBreakdown) -> CostBreakdown:
        """Round stored and returned cost components to a stable precision."""
        return CostBreakdown(
            input_cost=round(breakdown.input_cost, 8),
            output_cost=round(breakdown.output_cost, 8),
            thoughts_cost=round(breakdown.thoughts_cost, 8),
        )

    def _perform_day_rollover(self) -> None:
        """Aggregate yesterday's records into daily summary."""
        if self._store is None or not self._store.today_records:
            return

        yesterday = self._store.today
        month = yesterday[:7]
        provider_totals: dict[str, dict] = {}
        total_cost = 0.0

        # Aggregate by provider
        for record in self._store.today_records:
            provider = record.get("provider", "unknown")
            if provider not in provider_totals:
                provider_totals[provider] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "thoughts_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "thoughts_cost": 0.0,
                }
            pt = provider_totals[provider]
            pt["input_tokens"] += record.get("input_tokens", 0)
            pt["output_tokens"] += record.get("output_tokens", 0)
            pt["thoughts_tokens"] += record.get("thoughts_tokens", 0)
            pt["cache_read_tokens"] += record.get("cache_read_tokens", 0)
            pt["cache_write_tokens"] += record.get("cache_write_tokens", 0)
            pt["input_cost"] += record.get("input_cost", 0)
            pt["output_cost"] += record.get("output_cost", 0)
            pt["thoughts_cost"] += record.get("thoughts_cost", 0)
            record_cost = (
                record.get("input_cost", 0)
                + record.get("output_cost", 0)
                + record.get("thoughts_cost", 0)
            )
            total_cost += record_cost

        # Create daily summary
        summary = {
            "date": yesterday,
            "providers": provider_totals,
            "total_cost": round(total_cost, 6),
        }
        self._store.daily_summaries.append(summary)

        # Update monthly totals
        month_entry = self._store.monthly_totals.get(
            month,
            {
                "total_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thoughts_tokens": 0,
            },
        )
        month_entry["total_cost"] += total_cost
        for data in provider_totals.values():
            month_entry["input_tokens"] += data.get("input_tokens", 0)
            month_entry["output_tokens"] += data.get("output_tokens", 0)
            month_entry["thoughts_tokens"] += data.get("thoughts_tokens", 0)
        self._store.monthly_totals[month] = month_entry

        # Clear today's records
        self._store.today_records = []

        logger.info(
            "usage_day_rollover",
            date=yesterday,
            total_cost=total_cost,
            providers=list(provider_totals.keys()),
        )

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        thoughts_tokens: int = 0,
        context_length: int = 0,
        audio_input_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """
        Calculate cost for a request using LiteLLM catalog pricing.

        Args:
            model: Model ID
            input_tokens: Total prompt tokens including any cached subsets
            output_tokens: Number of output tokens
            thoughts_tokens: Number of reasoning/thought tokens already included
                in output_tokens
            context_length: Total context length for 200K+ tiered pricing
            audio_input_tokens: Number of audio input tokens
            cache_read_tokens: Prompt tokens served from provider cache (subset
                of input_tokens)
            cache_write_tokens: Prompt tokens written to provider cache (subset
                of input_tokens)

        Returns:
            Estimated cost in USD
        """
        breakdown = self._round_cost_breakdown(
            self._calculate_cost_breakdown(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                context_length=context_length,
                audio_input_tokens=audio_input_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            )
        )
        return breakdown.total_cost

    def _calculate_cost_breakdown(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        thoughts_tokens: int = 0,
        context_length: int = 0,
        audio_input_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> CostBreakdown:
        """
        Calculate a structured cost breakdown using catalog pricing.

        Invalid token counts are clamped to safe ranges before cost calculation.
        When a model has no dedicated reasoning token rate, the standard output
        token rate is used for thoughts tokens. Cached prompt tokens (read and
        write subsets of input_tokens) are priced with the catalog cache rates
        when available, falling back to the standard input rate otherwise.
        """
        model_info = self.catalog_service.get_model_cached(model)
        if model_info is None:
            logger.warning("pricing_unavailable", model=model)
            return CostBreakdown()

        safe_input_tokens = max(input_tokens, 0)
        safe_output_tokens = max(output_tokens, 0)
        safe_context_length = max(context_length, 0)
        safe_thoughts_tokens = max(0, min(thoughts_tokens, safe_output_tokens))
        safe_audio_tokens = max(0, min(audio_input_tokens, safe_input_tokens))
        safe_cache_read_tokens = max(0, min(cache_read_tokens, safe_input_tokens))
        safe_cache_write_tokens = max(
            0, min(cache_write_tokens, safe_input_tokens - safe_cache_read_tokens)
        )
        if (
            safe_input_tokens != input_tokens
            or safe_output_tokens != output_tokens
            or safe_context_length != context_length
            or safe_thoughts_tokens != thoughts_tokens
            or safe_audio_tokens != audio_input_tokens
            or safe_cache_read_tokens != cache_read_tokens
            or safe_cache_write_tokens != cache_write_tokens
        ):
            logger.warning(
                "budget_tokens_clamped",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thoughts_tokens=thoughts_tokens,
                context_length=context_length,
                audio_input_tokens=audio_input_tokens,
                clamped_input_tokens=safe_input_tokens,
                clamped_output_tokens=safe_output_tokens,
                clamped_thoughts_tokens=safe_thoughts_tokens,
                clamped_context_length=safe_context_length,
                clamped_audio_input_tokens=safe_audio_tokens,
                clamped_cache_read_tokens=safe_cache_read_tokens,
                clamped_cache_write_tokens=safe_cache_write_tokens,
            )

        visible_output_tokens = max(safe_output_tokens - safe_thoughts_tokens, 0)
        text_input_tokens = max(safe_input_tokens - safe_audio_tokens, 0)

        input_rate = (
            model_info.input_cost_per_token if model_info.input_cost_per_token is not None else 0.0
        )
        output_rate = (
            model_info.output_cost_per_token
            if model_info.output_cost_per_token is not None
            else 0.0
        )
        reasoning_rate = model_info.output_cost_per_reasoning_token

        if safe_context_length > 200_000:
            input_rate = (
                model_info.input_cost_per_token_above_200k_tokens
                if model_info.input_cost_per_token_above_200k_tokens is not None
                else input_rate
            )
            output_rate = (
                model_info.output_cost_per_token_above_200k_tokens
                if model_info.output_cost_per_token_above_200k_tokens is not None
                else output_rate
            )

        effective_reasoning_rate = reasoning_rate if reasoning_rate is not None else output_rate
        cache_read_rate = (
            model_info.cache_read_input_token_cost
            if model_info.cache_read_input_token_cost is not None
            else input_rate
        )
        cache_write_rate = (
            model_info.cache_creation_input_token_cost
            if model_info.cache_creation_input_token_cost is not None
            else input_rate
        )

        if safe_audio_tokens > 0 and model_info.input_cost_per_audio_token is not None:
            # Audio-priced requests keep the legacy formula; cache discounts are
            # not combined with audio tiering (Ternion never sends audio input).
            input_cost = (
                text_input_tokens * input_rate
                + safe_audio_tokens * model_info.input_cost_per_audio_token
            )
        else:
            uncached_input_tokens = max(
                safe_input_tokens - safe_cache_read_tokens - safe_cache_write_tokens, 0
            )
            input_cost = (
                uncached_input_tokens * input_rate
                + safe_cache_read_tokens * cache_read_rate
                + safe_cache_write_tokens * cache_write_rate
            )

        output_cost = visible_output_tokens * output_rate
        thoughts_cost = safe_thoughts_tokens * effective_reasoning_rate
        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            thoughts_cost=thoughts_cost,
        )

    def check_budget(self) -> tuple[bool, str | None]:
        """
        Check if budget allows for a request.

        Returns:
            Tuple of (allowed, warning_message)
            - allowed: True if request can proceed, False if budget exceeded
            - warning_message: Warning/error key if applicable, None otherwise
        """
        if self._store is None:
            self._load_usage()

        current_cost = self._get_monthly_total()
        monthly_limit = self.settings.monthly_limit_usd

        if current_cost >= monthly_limit:
            logger.warning(
                "budget_exceeded",
                current=current_cost,
                limit=monthly_limit,
            )
            return False, "BUDGET_EXCEEDED"

        if monthly_limit > 0:
            usage_ratio = current_cost / monthly_limit
            if usage_ratio >= self.settings.alert_threshold:
                logger.info(
                    "budget_warning",
                    current=current_cost,
                    limit=monthly_limit,
                    threshold=self.settings.alert_threshold,
                    usage_pct=round(usage_ratio * 100, 1),
                )
                return True, "BUDGET_WARNING"

        return True, None

    def _get_monthly_total(self) -> float:
        """Calculate total cost for current month from store."""
        if self._store is None:
            return 0.0

        current_month = self._get_current_month()
        total = 0.0

        # Add today's records
        for record in self._store.today_records:
            total += (
                record.get("input_cost", 0)
                + record.get("output_cost", 0)
                + record.get("thoughts_cost", 0)
            )

        # Add daily summaries from current month
        for summary in self._store.daily_summaries:
            if summary.get("date", "").startswith(current_month):
                total += summary.get("total_cost", 0)

        return total

    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        thoughts_tokens: int = 0,
        context_length: int = 0,
        audio_input_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """
        Record usage for a completed API request.

        Args:
            provider: Provider name (google, openai, anthropic)
            model: Model ID for pricing lookup
            input_tokens: Total prompt tokens including any cached subsets
            output_tokens: Number of output tokens
            thoughts_tokens: Number of reasoning tokens included in output_tokens
            context_length: Total context length for 200K+ tiered pricing
            audio_input_tokens: Number of audio input tokens
            cache_read_tokens: Prompt tokens served from provider cache (subset
                of input_tokens)
            cache_write_tokens: Prompt tokens written to provider cache (subset
                of input_tokens)

        Returns:
            Total cost of this request in USD
        """
        if self._store is None:
            self._load_usage()

        # Check for day rollover
        today = self._get_today()
        if self._store and self._store.today != today:
            self._perform_day_rollover()
            self._store.today = today

        clamped_thoughts_tokens = max(0, min(thoughts_tokens, output_tokens))
        breakdown = self._round_cost_breakdown(
            self._calculate_cost_breakdown(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thoughts_tokens=clamped_thoughts_tokens,
                context_length=context_length,
                audio_input_tokens=audio_input_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            )
        )
        total_cost = breakdown.total_cost

        entry = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thoughts_tokens": clamped_thoughts_tokens,
            "cache_read_tokens": max(cache_read_tokens, 0),
            "cache_write_tokens": max(cache_write_tokens, 0),
            "input_cost": round(breakdown.input_cost, 8),
            "output_cost": round(breakdown.output_cost, 8),
            "thoughts_cost": round(breakdown.thoughts_cost, 8),
        }

        if self._store:
            self._store.today_records.append(entry)
            if not self._save_usage():
                logger.warning(
                    "usage_record_not_persisted",
                    provider=provider,
                    model=model,
                    timestamp=entry["timestamp"],
                )

        logger.info(
            "usage_recorded",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts_tokens=clamped_thoughts_tokens,
            cache_read_tokens=max(cache_read_tokens, 0),
            cache_write_tokens=max(cache_write_tokens, 0),
            cost=round(total_cost, 6),
        )

        return total_cost

    # Legacy alias for compatibility
    def track_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        context_length: int = 0,
        audio_input_tokens: int = 0,
    ) -> float:
        """Legacy method - delegates to record_usage."""
        return self.record_usage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts_tokens=0,
            context_length=context_length,
            audio_input_tokens=audio_input_tokens,
        )

    def get_usage_summary(self) -> dict[str, Any]:
        """
        Get current usage summary for UI dashboard.

        Returns:
            Dictionary containing current month usage, costs, and limits.
        """
        if self._store is None:
            self._load_usage()

        if self._store is None:
            return {}

        current_month = self._get_current_month()
        monthly_cost = self._get_monthly_total()

        # Calculate today's totals
        today_cost = 0.0
        today_requests = len(self._store.today_records)
        provider_costs: dict[str, float] = {}

        for record in self._store.today_records:
            record_cost = (
                record.get("input_cost", 0)
                + record.get("output_cost", 0)
                + record.get("thoughts_cost", 0)
            )
            today_cost += record_cost
            prov = record.get("provider", "unknown")
            provider_costs[prov] = provider_costs.get(prov, 0) + record_cost

        # Add historical provider costs from current month
        for summary in self._store.daily_summaries:
            if summary.get("date", "").startswith(current_month):
                for prov, data in summary.get("providers", {}).items():
                    # Aggregate using separate cost fields with fallback for legacy data
                    prov_cost = (
                        data.get("input_cost", 0)
                        + data.get("output_cost", 0)
                        + data.get("thoughts_cost", 0)
                    )
                    if prov_cost == 0:
                        prov_cost = data.get("cost", 0)
                    provider_costs[prov] = provider_costs.get(prov, 0) + prov_cost

        return {
            "month": current_month,
            "total_cost_usd": round(monthly_cost, 4),
            "request_count": today_requests,
            "monthly_limit_usd": self.settings.monthly_limit_usd,
            "remaining_usd": round(self.settings.monthly_limit_usd - monthly_cost, 4),
            "usage_pct": round((monthly_cost / self.settings.monthly_limit_usd) * 100, 1)
            if self.settings.monthly_limit_usd > 0
            else 0,
            "provider_costs": {k: round(v, 4) for k, v in provider_costs.items()},
        }

    def get_detailed_usage(self, month: str | None = None) -> dict[str, Any]:
        """
        Get detailed usage data for UI charts.

        Args:
            month: Optional month filter (YYYY-MM format)

        Returns:
            Extended usage data including daily_data, monthly_data, and token totals
        """
        if self._store is None:
            self._load_usage()

        if self._store is None:
            return {}

        current_month = self._get_current_month()
        target_month = month or current_month

        # Calculate current month token totals and per-provider breakdown
        input_tokens = 0
        output_tokens = 0
        thoughts_tokens = 0
        provider_details: dict[str, dict] = {
            "google": {
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thoughts_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "thoughts_cost": 0.0,
            },
            "anthropic": {
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thoughts_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "thoughts_cost": 0.0,
            },
            "openai": {
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thoughts_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "thoughts_cost": 0.0,
            },
        }

        # From today's records (if target is current month)
        if target_month == current_month:
            for record in self._store.today_records:
                input_tokens += record.get("input_tokens", 0)
                output_tokens += record.get("output_tokens", 0)
                thoughts_tokens += record.get("thoughts_tokens", 0)
                # Provider breakdown
                prov = record.get("provider", "")
                if prov in provider_details:
                    provider_details[prov]["input_tokens"] += record.get("input_tokens", 0)
                    provider_details[prov]["output_tokens"] += record.get("output_tokens", 0)
                    provider_details[prov]["thoughts_tokens"] += record.get("thoughts_tokens", 0)
                    record_input_cost = record.get("input_cost", 0)
                    record_output_cost = record.get("output_cost", 0)
                    record_thoughts_cost = record.get("thoughts_cost", 0)
                    provider_details[prov]["input_cost"] += record_input_cost
                    provider_details[prov]["output_cost"] += record_output_cost
                    provider_details[prov]["thoughts_cost"] += record_thoughts_cost
                    provider_details[prov]["cost"] += (
                        record_input_cost + record_output_cost + record_thoughts_cost
                    )

        # From daily summaries for target month
        for summary in self._store.daily_summaries:
            if summary.get("date", "").startswith(target_month):
                for prov, prov_data in summary.get("providers", {}).items():
                    input_tokens += prov_data.get("input_tokens", 0)
                    output_tokens += prov_data.get("output_tokens", 0)
                    thoughts_tokens += prov_data.get("thoughts_tokens", 0)
                    # Provider breakdown
                    if prov in provider_details:
                        provider_details[prov]["input_tokens"] += prov_data.get("input_tokens", 0)
                        provider_details[prov]["output_tokens"] += prov_data.get("output_tokens", 0)
                        provider_details[prov]["thoughts_tokens"] += prov_data.get(
                            "thoughts_tokens", 0
                        )
                        # Aggregate cost fields with fallback for legacy data
                        prov_input_cost = prov_data.get("input_cost", 0)
                        prov_output_cost = prov_data.get("output_cost", 0)
                        prov_thoughts_cost = prov_data.get("thoughts_cost", 0)
                        prov_total_cost = prov_input_cost + prov_output_cost + prov_thoughts_cost
                        if prov_total_cost == 0:
                            prov_total_cost = prov_data.get("cost", 0)
                        provider_details[prov]["input_cost"] += prov_input_cost
                        provider_details[prov]["output_cost"] += prov_output_cost
                        provider_details[prov]["thoughts_cost"] += prov_thoughts_cost
                        provider_details[prov]["cost"] += prov_total_cost

        # Build daily_data for charts (ALL data, frontend will filter)
        daily_data = []
        for summary in self._store.daily_summaries:
            day_input = sum(p.get("input_tokens", 0) for p in summary.get("providers", {}).values())
            day_output = sum(
                p.get("output_tokens", 0) for p in summary.get("providers", {}).values()
            )
            day_thoughts = sum(
                p.get("thoughts_tokens", 0) for p in summary.get("providers", {}).values()
            )
            # Per-provider breakdown for this day (with separate costs)
            providers = {}
            day_input_cost = 0.0
            day_output_cost = 0.0
            day_thoughts_cost = 0.0
            for prov, prov_data in summary.get("providers", {}).items():
                # Handle both old format (cost) and new format (input_cost, output_cost, thoughts_cost)
                prov_input_cost = prov_data.get("input_cost", 0)
                prov_output_cost = prov_data.get("output_cost", 0)
                prov_thoughts_cost = prov_data.get("thoughts_cost", 0)
                # If no separate costs, fall back to combined cost distributed by token ratio
                if prov_input_cost == 0 and prov_output_cost == 0 and prov_thoughts_cost == 0:
                    total_tokens = (
                        prov_data.get("input_tokens", 0)
                        + prov_data.get("output_tokens", 0)
                        + prov_data.get("thoughts_tokens", 0)
                    )
                    if total_tokens > 0:
                        total_cost = prov_data.get("cost", 0)
                        prov_input_cost = (
                            total_cost * prov_data.get("input_tokens", 0) / total_tokens
                        )
                        prov_output_cost = (
                            total_cost * prov_data.get("output_tokens", 0) / total_tokens
                        )
                        prov_thoughts_cost = (
                            total_cost * prov_data.get("thoughts_tokens", 0) / total_tokens
                        )

                providers[prov] = {
                    "input_tokens": prov_data.get("input_tokens", 0),
                    "output_tokens": prov_data.get("output_tokens", 0),
                    "thoughts_tokens": prov_data.get("thoughts_tokens", 0),
                    "input_cost": prov_input_cost,
                    "output_cost": prov_output_cost,
                    "thoughts_cost": prov_thoughts_cost,
                }
                day_input_cost += prov_input_cost
                day_output_cost += prov_output_cost
                day_thoughts_cost += prov_thoughts_cost

            daily_data.append(
                {
                    "date": summary.get("date"),
                    "cost": round(summary.get("total_cost", 0), 4),
                    "input_cost": round(day_input_cost, 4),
                    "output_cost": round(day_output_cost, 4),
                    "thoughts_cost": round(day_thoughts_cost, 4),
                    "input_tokens": day_input,
                    "output_tokens": day_output,
                    "thoughts_tokens": day_thoughts,
                    "providers": providers,
                }
            )

        # Add today's data
        if self._store.today_records:
            today_input_cost = sum(r.get("input_cost", 0) for r in self._store.today_records)
            today_output_cost = sum(r.get("output_cost", 0) for r in self._store.today_records)
            today_thoughts_cost = sum(r.get("thoughts_cost", 0) for r in self._store.today_records)
            today_cost = today_input_cost + today_output_cost + today_thoughts_cost
            today_input = sum(r.get("input_tokens", 0) for r in self._store.today_records)
            today_output = sum(r.get("output_tokens", 0) for r in self._store.today_records)
            today_thoughts = sum(r.get("thoughts_tokens", 0) for r in self._store.today_records)
            daily_data.append(
                {
                    "date": self._store.today,
                    "cost": round(today_cost, 4),
                    "input_cost": round(today_input_cost, 4),
                    "output_cost": round(today_output_cost, 4),
                    "thoughts_cost": round(today_thoughts_cost, 4),
                    "input_tokens": today_input,
                    "output_tokens": today_output,
                    "thoughts_tokens": today_thoughts,
                }
            )

        # Sort daily data by date
        daily_data.sort(key=lambda x: x["date"])

        # Build monthly_data from monthly_totals with per-provider breakdown
        # First, aggregate provider data from daily_summaries per month
        monthly_providers: dict[str, dict[str, dict]] = {}
        for summary in self._store.daily_summaries:
            month_key = summary.get("date", "")[:7]
            if month_key not in monthly_providers:
                monthly_providers[month_key] = {}
            for prov, prov_data in summary.get("providers", {}).items():
                if prov not in monthly_providers[month_key]:
                    monthly_providers[month_key][prov] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "thoughts_tokens": 0,
                        "input_cost": 0.0,
                        "output_cost": 0.0,
                        "thoughts_cost": 0.0,
                    }
                monthly_providers[month_key][prov]["input_tokens"] += prov_data.get(
                    "input_tokens", 0
                )
                monthly_providers[month_key][prov]["output_tokens"] += prov_data.get(
                    "output_tokens", 0
                )
                monthly_providers[month_key][prov]["thoughts_tokens"] += prov_data.get(
                    "thoughts_tokens", 0
                )
                monthly_providers[month_key][prov]["input_cost"] += prov_data.get("input_cost", 0)
                monthly_providers[month_key][prov]["output_cost"] += prov_data.get("output_cost", 0)
                monthly_providers[month_key][prov]["thoughts_cost"] += prov_data.get(
                    "thoughts_cost", 0
                )

        # Aggregate monthly totals for separate costs
        monthly_costs: dict[str, dict] = {}
        for summary in self._store.daily_summaries:
            month_key = summary.get("date", "")[:7]
            if month_key not in monthly_costs:
                monthly_costs[month_key] = {
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "thoughts_cost": 0.0,
                }
            for prov_data in summary.get("providers", {}).values():
                monthly_costs[month_key]["input_cost"] += prov_data.get("input_cost", 0)
                monthly_costs[month_key]["output_cost"] += prov_data.get("output_cost", 0)
                monthly_costs[month_key]["thoughts_cost"] += prov_data.get("thoughts_cost", 0)

        monthly_data = []
        for month_key, totals in self._store.monthly_totals.items():
            costs = monthly_costs.get(
                month_key, {"input_cost": 0, "output_cost": 0, "thoughts_cost": 0}
            )
            monthly_data.append(
                {
                    "month": month_key,
                    "cost": round(totals.get("total_cost", 0), 4),
                    "input_cost": round(costs["input_cost"], 4),
                    "output_cost": round(costs["output_cost"], 4),
                    "thoughts_cost": round(costs["thoughts_cost"], 4),
                    "input_tokens": totals.get("input_tokens", 0),
                    "output_tokens": totals.get("output_tokens", 0),
                    "thoughts_tokens": totals.get("thoughts_tokens", 0),
                    "providers": monthly_providers.get(month_key, {}),
                }
            )

        # Sort monthly data by month
        monthly_data.sort(key=lambda x: x["month"])

        # Build available months and years lists
        all_months = set()
        all_years = set()
        for summary in self._store.daily_summaries:
            date = summary.get("date", "")
            if len(date) >= 7:
                all_months.add(date[:7])
                all_years.add(date[:4])
        all_months.add(current_month)
        all_years.add(current_month[:4])

        available_months = sorted(all_months, reverse=True)
        available_years = sorted(all_years, reverse=True)

        # Merge with base summary
        base_summary = self.get_usage_summary()
        base_summary.update(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "thoughts_tokens": thoughts_tokens,
                "provider_details": {
                    k: {
                        "cost": round(v["cost"], 4),
                        "input_tokens": v["input_tokens"],
                        "output_tokens": v["output_tokens"],
                        "thoughts_tokens": v.get("thoughts_tokens", 0),
                        "input_cost": round(v.get("input_cost", 0), 4),
                        "output_cost": round(v.get("output_cost", 0), 4),
                        "thoughts_cost": round(v.get("thoughts_cost", 0), 4),
                    }
                    for k, v in provider_details.items()
                },
                "daily_data": daily_data,
                "monthly_data": monthly_data,
                "available_months": available_months,
                "available_years": available_years,
            }
        )

        return base_summary

    def format_budget_warning(self, warning: str | None) -> str:
        """
        Format budget warning for Cursor display.

        Args:
            warning: Warning message key or None

        Returns:
            Formatted markdown string for Cursor thinking display
        """
        if warning is None:
            return ""
        if warning == "BUDGET_WARNING":
            usage_summary = self.get_usage_summary()
            usage_pct = str(usage_summary.get("usage_pct", 0))
            return t(MessageKey.BUDGET_WARNING, usage_pct=usage_pct)
        if warning == "BUDGET_EXCEEDED":
            return t(MessageKey.BUDGET_EXCEEDED)
        return f"\n> ⚠️ **[Ternion]**: {warning}\n\n"


# Global budget manager instance (lazy initialized)
_budget_manager: BudgetManager | None = None


def get_budget_manager() -> BudgetManager:
    """Get or create the global budget manager."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = BudgetManager()
    return _budget_manager


# Convenience alias
budget_manager = get_budget_manager()
