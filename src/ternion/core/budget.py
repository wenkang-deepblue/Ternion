"""
Budget management for Ternion.

Tracks API usage costs, enforces budget limits, and persists monthly usage
to a local file. Provides alerts when approaching budget thresholds.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings

logger = structlog.get_logger(__name__)

# Token pricing per model (USD per 1K tokens) - updated 2025-12
MODEL_PRICING = {
    # Anthropic Claude models
    "claude-opus-4-5-20251101": {
        "input": 5.0 / 1000,
        "output": 25.0 / 1000,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0 / 1000,
        "output": 15.0 / 1000,
    },
    "claude-opus-4-1-20250805": {
        "input": 15.0 / 1000,
        "output": 75.0 / 1000,
    },
    # OpenAI GPT models
    "gpt-5.2-pro-2025-12-11": {
        "input": 21.0 / 1000,
        "output": 168.0 / 1000,
    },
    "gpt-5.2-2025-12-11": {
        "input": 1.75 / 1000,
        "output": 14.0 / 1000,
    },
    "gpt-5.1-codex-max": {
        "input": 1.25 / 1000,
        "output": 10.0 / 1000,
    },
    "gpt-5.1-codex": {
        "input": 1.25 / 1000,
        "output": 10.0 / 1000,
    },
}

# Gemini tiered pricing (context-length and media-type based)
GEMINI_PRICING = {
    "gemini-3-pro-preview": {
        "context_threshold": 200000,  # 200K tokens
        "input_standard": 2.0 / 1000,   # <=200K
        "input_extended": 4.0 / 1000,   # >200K
        "output_standard": 12.0 / 1000,
        "output_extended": 18.0 / 1000,
    },
    "gemini-3-flash-preview": {
        "input_text": 0.5 / 1000,
        "input_audio": 1.0 / 1000,
        "output": 3.0 / 1000,
    },
    "gemini-flash-lite-latest": {
        "input_text": 0.1 / 1000,
        "input_audio": 0.3 / 1000,
        "output": 0.4 / 1000,
    },
}

# Default fallback pricing if model not found
DEFAULT_PRICING = {
    "input": 0.01,
    "output": 0.03,
}


class CostControlSettings(BaseSettings):
    """Cost control configuration."""

    daily_limit_usd: float = 5.0
    monthly_limit_usd: float = 50.0
    request_limit_usd: float = 1.0
    alert_threshold: float = 0.9  # 90% threshold for warnings


class UsageEntry(BaseSettings):
    """Single API request usage record."""

    timestamp: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    thoughts_cost: float = 0.0


class ProviderDayUsage(BaseSettings):
    """Per-provider daily usage totals."""

    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    cost: float = 0.0


class DailySummary(BaseSettings):
    """Aggregated daily usage."""

    date: str = ""
    providers: dict[str, dict] = Field(default_factory=dict)
    total_cost: float = 0.0


class MonthlyTotal(BaseSettings):
    """Monthly usage totals."""

    total_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0


class UsageStore(BaseSettings):
    """Complete usage data store."""

    today: str = ""
    today_records: list[dict] = Field(default_factory=list)
    daily_summaries: list[dict] = Field(default_factory=list)
    monthly_totals: dict[str, dict] = Field(default_factory=dict)


# Legacy alias for compatibility
UsageRecord = UsageStore


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
    ) -> None:
        """
        Initialize budget manager.

        Args:
            settings: Cost control settings
            usage_file: Path to store usage data (defaults to ~/.ternion/usage.json)
        """
        self.settings = settings or CostControlSettings()
        # TODO: Switch back to ~/.ternion/usage.json after UI testing
        # self.usage_file = usage_file or Path.home() / ".ternion" / "usage.json"
        # self._test_mode = False
        self.usage_file = usage_file or Path(__file__).parent.parent.parent.parent / "usage_test.json"
        self._test_mode = True  # Skip day rollover and saving when using test data
        self._store: UsageStore | None = None
        self._load_usage()

    def _get_today(self) -> str:
        """Get current date in YYYY-MM-DD format using local timezone."""
        return datetime.now().strftime("%Y-%m-%d")

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        # In test mode, use the month from the test data
        if self._test_mode and self._store and self._store.today:
            return self._store.today[:7]
        return datetime.now().strftime("%Y-%m")

    def _load_usage(self) -> None:
        """Load usage from file, check for day rollover."""
        today = self._get_today()

        if self.usage_file.exists():
            try:
                with open(self.usage_file) as f:
                    data = json.load(f)
                    self._store = UsageStore(**data)

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
            except Exception as e:
                logger.warning("budget_load_error", error=str(e))
                self._store = UsageStore(today=today)
        else:
            self._store = UsageStore(today=today)
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)

    def _save_usage(self) -> None:
        """Save current usage to file."""
        if self._store is None:
            return

        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_file, "w") as f:
                json.dump(self._store.model_dump(), f, indent=2)
        except Exception as e:
            logger.error("budget_save_error", error=str(e))

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
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "thoughts_cost": 0.0,
                }
            pt = provider_totals[provider]
            pt["input_tokens"] += record.get("input_tokens", 0)
            pt["output_tokens"] += record.get("output_tokens", 0)
            pt["thoughts_tokens"] += record.get("thoughts_tokens", 0)
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
        context_length: int = 0,
        audio_input_tokens: int = 0,
    ) -> float:
        """
        Calculate cost for a request based on model-specific pricing.

        Args:
            model: Model ID
            input_tokens: Number of text/image/video input tokens
            output_tokens: Number of output tokens
            context_length: Total context length for Gemini Pro tiered pricing
            audio_input_tokens: Number of audio input tokens (Gemini Flash models)

        Returns:
            Estimated cost in USD
        """
        # Check for Gemini tiered pricing
        if model in GEMINI_PRICING:
            return self._calculate_gemini_cost(
                model, input_tokens, output_tokens, context_length, audio_input_tokens
            )

        # Standard flat-rate pricing
        rates = MODEL_PRICING.get(model, DEFAULT_PRICING)
        input_cost = (input_tokens / 1000) * rates["input"]
        output_cost = (output_tokens / 1000) * rates["output"]
        return input_cost + output_cost

    def _calculate_gemini_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        context_length: int,
        audio_input_tokens: int,
    ) -> float:
        """Calculate cost for Gemini models with tiered pricing."""
        pricing = GEMINI_PRICING[model]

        if model == "gemini-3-pro-preview":
            # Context-length based tiering
            threshold = pricing["context_threshold"]
            if context_length <= threshold:
                input_rate = pricing["input_standard"]
                output_rate = pricing["output_standard"]
            else:
                input_rate = pricing["input_extended"]
                output_rate = pricing["output_extended"]
            input_cost = (input_tokens / 1000) * input_rate
            output_cost = (output_tokens / 1000) * output_rate
        else:
            # Media-type based tiering (Flash and Flash-Lite)
            text_tokens = input_tokens - audio_input_tokens
            text_cost = (text_tokens / 1000) * pricing["input_text"]
            audio_cost = (audio_input_tokens / 1000) * pricing["input_audio"]
            input_cost = text_cost + audio_cost
            output_cost = (output_tokens / 1000) * pricing["output"]

        return input_cost + output_cost

    def check_budget(self, estimated_cost: float = 0.1) -> tuple[bool, str | None]:
        """
        Check if budget allows for a request.

        Args:
            estimated_cost: Estimated cost of the request in USD

        Returns:
            Tuple of (allowed, warning_message)
            - allowed: True if request can proceed
            - warning_message: Warning if approaching limit, None otherwise
        """
        if self._store is None:
            self._load_usage()

        current_cost = self._get_monthly_total()
        projected_cost = current_cost + estimated_cost
        monthly_limit = self.settings.monthly_limit_usd

        # Check if over limit
        if projected_cost > monthly_limit:
            logger.warning(
                "budget_exceeded",
                current=current_cost,
                estimated=estimated_cost,
                limit=monthly_limit,
            )
            return False, "BUDGET_EXCEEDED"

        # Check if approaching limit
        if monthly_limit > 0:
            usage_ratio = projected_cost / monthly_limit
            if usage_ratio >= self.settings.alert_threshold:
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
    ) -> float:
        """
        Record usage for a completed API request.

        Args:
            provider: Provider name (google, openai, anthropic)
            model: Model ID for pricing lookup
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            thoughts_tokens: Number of thinking tokens (for display/tracking)
            context_length: Context length for Gemini Pro tiered pricing
            audio_input_tokens: Audio input tokens for Gemini Flash

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

        # Calculate costs
        rates = MODEL_PRICING.get(model, DEFAULT_PRICING)
        if model in GEMINI_PRICING:
            pricing = GEMINI_PRICING[model]
            if model == "gemini-3-pro-preview":
                threshold = pricing["context_threshold"]
                if context_length <= threshold:
                    input_rate = pricing["input_standard"]
                    output_rate = pricing["output_standard"]
                else:
                    input_rate = pricing["input_extended"]
                    output_rate = pricing["output_extended"]
                # Gemini: thoughts are separate, charged at output rate
                input_cost = (input_tokens / 1000) * input_rate
                output_cost = ((output_tokens - thoughts_tokens) / 1000) * output_rate
                thoughts_cost = (thoughts_tokens / 1000) * output_rate
            else:
                # Flash models
                text_tokens = input_tokens - audio_input_tokens
                input_cost = (
                    (text_tokens / 1000) * pricing["input_text"]
                    + (audio_input_tokens / 1000) * pricing["input_audio"]
                )
                output_cost = ((output_tokens - thoughts_tokens) / 1000) * pricing["output"]
                thoughts_cost = (thoughts_tokens / 1000) * pricing["output"]
        else:
            input_cost = (input_tokens / 1000) * rates["input"]
            output_cost = ((output_tokens - thoughts_tokens) / 1000) * rates["output"]
            thoughts_cost = (thoughts_tokens / 1000) * rates["output"]

        total_cost = input_cost + output_cost + thoughts_cost

        # Create usage entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thoughts_tokens": thoughts_tokens,
            "input_cost": round(input_cost, 8),
            "output_cost": round(output_cost, 8),
            "thoughts_cost": round(thoughts_cost, 8),
        }

        if self._store:
            self._store.today_records.append(entry)
            self._save_usage()

        logger.info(
            "usage_recorded",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thoughts_tokens=thoughts_tokens,
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
        """Get current usage summary for UI dashboard."""
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
                    provider_costs[prov] = provider_costs.get(prov, 0) + data.get("cost", 0)

        return {
            "month": current_month,
            "total_cost_usd": round(monthly_cost, 4),
            "request_count": today_requests,
            "monthly_limit_usd": self.settings.monthly_limit_usd,
            "remaining_usd": round(
                self.settings.monthly_limit_usd - monthly_cost, 4
            ),
            "usage_pct": round(
                (monthly_cost / self.settings.monthly_limit_usd) * 100, 1
            ) if self.settings.monthly_limit_usd > 0 else 0,
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
            "google": {"cost": 0.0, "input_tokens": 0, "output_tokens": 0},
            "anthropic": {"cost": 0.0, "input_tokens": 0, "output_tokens": 0},
            "openai": {"cost": 0.0, "input_tokens": 0, "output_tokens": 0},
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
                    provider_details[prov]["cost"] += (
                        record.get("input_cost", 0) +
                        record.get("output_cost", 0) +
                        record.get("thoughts_cost", 0)
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
                        provider_details[prov]["cost"] += prov_data.get("cost", 0)

        # Build daily_data for charts (ALL data, frontend will filter)
        daily_data = []
        for summary in self._store.daily_summaries:
            day_input = sum(
                p.get("input_tokens", 0) for p in summary.get("providers", {}).values()
            )
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
                        prov_data.get("input_tokens", 0) +
                        prov_data.get("output_tokens", 0) +
                        prov_data.get("thoughts_tokens", 0)
                    )
                    if total_tokens > 0:
                        total_cost = prov_data.get("cost", 0)
                        prov_input_cost = total_cost * prov_data.get("input_tokens", 0) / total_tokens
                        prov_output_cost = total_cost * prov_data.get("output_tokens", 0) / total_tokens
                        prov_thoughts_cost = total_cost * prov_data.get("thoughts_tokens", 0) / total_tokens

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

            daily_data.append({
                "date": summary.get("date"),
                "cost": round(summary.get("total_cost", 0), 4),
                "input_cost": round(day_input_cost, 4),
                "output_cost": round(day_output_cost, 4),
                "thoughts_cost": round(day_thoughts_cost, 4),
                "input_tokens": day_input,
                "output_tokens": day_output,
                "thoughts_tokens": day_thoughts,
                "providers": providers,
            })

        # Add today's data
        if self._store.today_records:
            today_input_cost = sum(r.get("input_cost", 0) for r in self._store.today_records)
            today_output_cost = sum(r.get("output_cost", 0) for r in self._store.today_records)
            today_thoughts_cost = sum(r.get("thoughts_cost", 0) for r in self._store.today_records)
            today_cost = today_input_cost + today_output_cost + today_thoughts_cost
            today_input = sum(r.get("input_tokens", 0) for r in self._store.today_records)
            today_output = sum(r.get("output_tokens", 0) for r in self._store.today_records)
            today_thoughts = sum(r.get("thoughts_tokens", 0) for r in self._store.today_records)
            daily_data.append({
                "date": self._store.today,
                "cost": round(today_cost, 4),
                "input_cost": round(today_input_cost, 4),
                "output_cost": round(today_output_cost, 4),
                "thoughts_cost": round(today_thoughts_cost, 4),
                "input_tokens": today_input,
                "output_tokens": today_output,
                "thoughts_tokens": today_thoughts,
            })

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
                        "input_tokens": 0, "output_tokens": 0, "thoughts_tokens": 0,
                        "input_cost": 0.0, "output_cost": 0.0, "thoughts_cost": 0.0
                    }
                monthly_providers[month_key][prov]["input_tokens"] += prov_data.get("input_tokens", 0)
                monthly_providers[month_key][prov]["output_tokens"] += prov_data.get("output_tokens", 0)
                monthly_providers[month_key][prov]["thoughts_tokens"] += prov_data.get("thoughts_tokens", 0)
                monthly_providers[month_key][prov]["input_cost"] += prov_data.get("input_cost", 0)
                monthly_providers[month_key][prov]["output_cost"] += prov_data.get("output_cost", 0)
                monthly_providers[month_key][prov]["thoughts_cost"] += prov_data.get("thoughts_cost", 0)

        # Aggregate monthly totals for separate costs
        monthly_costs: dict[str, dict] = {}
        for summary in self._store.daily_summaries:
            month_key = summary.get("date", "")[:7]
            if month_key not in monthly_costs:
                monthly_costs[month_key] = {"input_cost": 0.0, "output_cost": 0.0, "thoughts_cost": 0.0}
            for prov_data in summary.get("providers", {}).values():
                monthly_costs[month_key]["input_cost"] += prov_data.get("input_cost", 0)
                monthly_costs[month_key]["output_cost"] += prov_data.get("output_cost", 0)
                monthly_costs[month_key]["thoughts_cost"] += prov_data.get("thoughts_cost", 0)

        monthly_data = []
        for month_key, totals in self._store.monthly_totals.items():
            costs = monthly_costs.get(month_key, {"input_cost": 0, "output_cost": 0, "thoughts_cost": 0})
            monthly_data.append({
                "month": month_key,
                "cost": round(totals.get("total_cost", 0), 4),
                "input_cost": round(costs["input_cost"], 4),
                "output_cost": round(costs["output_cost"], 4),
                "thoughts_cost": round(costs["thoughts_cost"], 4),
                "input_tokens": totals.get("input_tokens", 0),
                "output_tokens": totals.get("output_tokens", 0),
                "thoughts_tokens": totals.get("thoughts_tokens", 0),
                "providers": monthly_providers.get(month_key, {}),
            })

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
        base_summary.update({
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thoughts_tokens": thoughts_tokens,
            "provider_details": {
                k: {
                    "cost": round(v["cost"], 4),
                    "input_tokens": v["input_tokens"],
                    "output_tokens": v["output_tokens"],
                }
                for k, v in provider_details.items()
            },
            "daily_data": daily_data,
            "monthly_data": monthly_data,
            "available_months": available_months,
            "available_years": available_years,
        })

        return base_summary

    def format_budget_warning(self, warning: str | None) -> str:
        """
        Format budget warning for Cursor display.

        Args:
            warning: Warning message or None

        Returns:
            Formatted markdown string for Cursor thinking display
        """
        if warning is None:
            return ""
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
