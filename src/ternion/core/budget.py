"""
Budget management for Ternion.

Tracks API usage costs, enforces budget limits, and persists monthly usage
to a local file. Provides alerts when approaching budget thresholds.
"""

import json
import structlog
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings

logger = structlog.get_logger(__name__)

# Approximate cost per 1K tokens (USD) - updated as of 2024
COST_PER_1K_TOKENS = {
    "openai": {
        "input": 0.01,   # GPT-4 Turbo input
        "output": 0.03,  # GPT-4 Turbo output
    },
    "anthropic": {
        "input": 0.015,  # Claude 3.5 Sonnet input
        "output": 0.075, # Claude 3.5 Sonnet output
    },
    "google": {
        "input": 0.00125,  # Gemini 1.5 Pro input
        "output": 0.005,   # Gemini 1.5 Pro output
    },
}


class CostControlSettings(BaseSettings):
    """Cost control configuration."""

    daily_limit_usd: float = 5.0
    monthly_limit_usd: float = 50.0
    request_limit_usd: float = 1.0
    alert_threshold: float = 0.9  # 90% threshold for warnings


class UsageRecord(BaseSettings):
    """Monthly usage record."""

    month: str = ""  # Format: YYYY-MM
    total_cost_usd: float = 0.0
    request_count: int = 0
    provider_costs: dict[str, float] = Field(default_factory=dict)


class BudgetManager:
    """
    Manages API usage costs and budget enforcement.

    Features:
    - Track costs per provider
    - Monthly usage persistence to file
    - Budget limit checking
    - Alert threshold monitoring
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
        self.usage_file = usage_file or Path.home() / ".ternion" / "usage.json"
        self._current_usage: UsageRecord | None = None
        self._load_usage()

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _load_usage(self) -> None:
        """Load usage from file, reset if new month."""
        current_month = self._get_current_month()

        if self.usage_file.exists():
            try:
                with open(self.usage_file) as f:
                    data = json.load(f)
                    self._current_usage = UsageRecord(**data)

                    # Check if it's a new month
                    if self._current_usage.month != current_month:
                        logger.info(
                            "budget_new_month",
                            old_month=self._current_usage.month,
                            new_month=current_month,
                        )
                        self._current_usage = UsageRecord(month=current_month)
                        self._save_usage()
            except Exception as e:
                logger.warning("budget_load_error", error=str(e))
                self._current_usage = UsageRecord(month=current_month)
        else:
            self._current_usage = UsageRecord(month=current_month)
            # Ensure directory exists
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)

    def _save_usage(self) -> None:
        """Save current usage to file."""
        if self._current_usage is None:
            return

        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_file, "w") as f:
                json.dump(self._current_usage.model_dump(), f, indent=2)
        except Exception as e:
            logger.error("budget_save_error", error=str(e))

    def calculate_cost(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate cost for a request.

        Args:
            provider: Provider name ('openai', 'anthropic', 'google')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        rates = COST_PER_1K_TOKENS.get(provider, COST_PER_1K_TOKENS["openai"])
        input_cost = (input_tokens / 1000) * rates["input"]
        output_cost = (output_tokens / 1000) * rates["output"]
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
        if self._current_usage is None:
            self._load_usage()

        current_cost = self._current_usage.total_cost_usd if self._current_usage else 0
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
        usage_ratio = projected_cost / monthly_limit
        if usage_ratio >= self.settings.alert_threshold:
            pct = int(usage_ratio * 100)
            return True, "BUDGET_WARNING"

        return True, None

    def track_usage(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Track usage for a completed request.

        Args:
            provider: Provider name
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            Cost of this request in USD
        """
        cost = self.calculate_cost(provider, input_tokens, output_tokens)

        if self._current_usage is None:
            self._load_usage()

        if self._current_usage:
            self._current_usage.total_cost_usd += cost
            self._current_usage.request_count += 1
            self._current_usage.provider_costs[provider] = (
                self._current_usage.provider_costs.get(provider, 0) + cost
            )
            self._save_usage()

        logger.debug(
            "usage_tracked",
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            total=self._current_usage.total_cost_usd if self._current_usage else 0,
        )

        return cost

    def get_usage_summary(self) -> dict[str, Any]:
        """Get current usage summary."""
        if self._current_usage is None:
            self._load_usage()

        if self._current_usage is None:
            return {}

        return {
            "month": self._current_usage.month,
            "total_cost_usd": round(self._current_usage.total_cost_usd, 4),
            "request_count": self._current_usage.request_count,
            "monthly_limit_usd": self.settings.monthly_limit_usd,
            "remaining_usd": round(
                self.settings.monthly_limit_usd - self._current_usage.total_cost_usd, 4
            ),
            "usage_pct": round(
                (self._current_usage.total_cost_usd / self.settings.monthly_limit_usd) * 100, 1
            ),
            "provider_costs": self._current_usage.provider_costs,
        }

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
