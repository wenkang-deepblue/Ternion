"""
Tests for the budget management module.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from ternion.core.budget import (
    DEFAULT_PRICING,
    BudgetManager,
    CostControlSettings,
)


@pytest.fixture
def temp_usage_file(tmp_path: Path) -> Path:
    """Create a temporary usage file path."""
    return tmp_path / "usage.json"


@pytest.fixture
def budget_manager(temp_usage_file: Path) -> BudgetManager:
    """Create a budget manager with test settings."""
    settings = CostControlSettings(
        daily_limit_usd=1.0,
        monthly_limit_usd=10.0,
        request_limit_usd=0.5,
        alert_threshold=0.9,
    )
    return BudgetManager(settings=settings, usage_file=temp_usage_file)


class TestCostCalculation:
    """Tests for cost calculation."""

    def test_calculate_cost_claude_opus_45(self, budget_manager: BudgetManager) -> None:
        """Test Claude Opus 4.5 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=1000,
            output_tokens=1000,
        )
        # $5/MTok input = $0.005/1K, $25/MTok output = $0.025/1K
        expected = (1000 / 1000) * 0.005 + (1000 / 1000) * 0.025
        assert cost == pytest.approx(expected)

    def test_calculate_cost_claude_sonnet_45(self, budget_manager: BudgetManager) -> None:
        """Test Claude Sonnet 4.5 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-sonnet-4-5-20250929",
            input_tokens=2000,
            output_tokens=500,
        )
        # $3/MTok input = $0.003/1K, $15/MTok output = $0.015/1K
        expected = (2000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert cost == pytest.approx(expected)

    def test_calculate_cost_claude_opus_41(self, budget_manager: BudgetManager) -> None:
        """Test Claude Opus 4.1 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-1-20250805",
            input_tokens=1000,
            output_tokens=1000,
        )
        # $15/MTok input = $0.015/1K, $75/MTok output = $0.075/1K
        expected = (1000 / 1000) * 0.015 + (1000 / 1000) * 0.075
        assert cost == pytest.approx(expected)

    def test_calculate_cost_unknown_model_uses_default(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test that unknown models use default pricing."""
        cost = budget_manager.calculate_cost(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
        )
        # Default: $0.01/1K input, $0.03/1K output
        expected = (1000 / 1000) * DEFAULT_PRICING["input"] + \
                   (1000 / 1000) * DEFAULT_PRICING["output"]
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_pro_standard_tier(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test Gemini Pro cost with context <= 200K."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-pro-preview",
            input_tokens=1000,
            output_tokens=1000,
            context_length=100000,
        )
        # Standard tier: $2/MTok input, $12/MTok output
        expected = (1000 / 1000) * 0.002 + (1000 / 1000) * 0.012
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_pro_extended_tier(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test Gemini Pro cost with context > 200K."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-pro-preview",
            input_tokens=1000,
            output_tokens=1000,
            context_length=250000,
        )
        # Extended tier: $4/MTok input, $18/MTok output
        expected = (1000 / 1000) * 0.004 + (1000 / 1000) * 0.018
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_flash_text_only(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test Gemini Flash cost with text-only input."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-flash-preview",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=0,
        )
        # $0.5/MTok text input, $3/MTok output
        expected = (1000 / 1000) * 0.0005 + (1000 / 1000) * 0.003
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_flash_with_audio(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test Gemini Flash cost with mixed text and audio input."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-flash-preview",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=400,
        )
        # 600 text tokens @ $0.5/MTok, 400 audio tokens @ $1/MTok, output @ $3/MTok
        expected = (600 / 1000) * 0.0005 + (400 / 1000) * 0.001 + (1000 / 1000) * 0.003
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_flash_lite(
        self, budget_manager: BudgetManager
    ) -> None:
        """Test Gemini Flash Lite cost calculation."""
        cost = budget_manager.calculate_cost(
            model="gemini-flash-lite-latest",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=0,
        )
        # $0.1/MTok text input, $0.4/MTok output
        expected = (1000 / 1000) * 0.0001 + (1000 / 1000) * 0.0004
        assert cost == pytest.approx(expected)


class TestBudgetCheck:
    """Tests for budget checking."""

    def test_check_budget_under_limit(self, budget_manager: BudgetManager) -> None:
        """Test budget check when under limit."""
        allowed, warning = budget_manager.check_budget(estimated_cost=0.1)
        assert allowed is True
        assert warning is None

    def test_check_budget_over_limit(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test budget check when over limit."""
        # Pre-populate usage file with high usage in new format
        today = datetime.now().strftime("%Y-%m-%d")
        usage_data = {
            "today": today,
            "today_records": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "provider": "openai",
                    "model": "gpt-5.1-codex",
                    "input_tokens": 100000,
                    "output_tokens": 100000,
                    "thoughts_tokens": 0,
                    "input_cost": 4.975,
                    "output_cost": 4.975,
                    "thoughts_cost": 0.0,
                }
            ],
            "daily_summaries": [],
            "monthly_totals": {},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        # Reload budget manager
        budget_manager._load_usage()

        allowed, warning = budget_manager.check_budget(estimated_cost=0.1)
        assert allowed is False
        assert warning == "BUDGET_EXCEEDED"

    def test_check_budget_near_threshold(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test budget check when near alert threshold."""
        # Pre-populate usage to 85% (just below 90% threshold)
        today = datetime.now().strftime("%Y-%m-%d")
        usage_data = {
            "today": today,
            "today_records": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "provider": "openai",
                    "model": "gpt-5.1-codex",
                    "input_tokens": 50000,
                    "output_tokens": 50000,
                    "thoughts_tokens": 0,
                    "input_cost": 4.25,
                    "output_cost": 4.25,
                    "thoughts_cost": 0.0,
                }
            ],
            "daily_summaries": [],
            "monthly_totals": {},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        budget_manager._load_usage()

        # Request that pushes us over 90%
        allowed, warning = budget_manager.check_budget(estimated_cost=0.6)
        assert allowed is True
        assert warning is not None
        assert warning == "BUDGET_WARNING"


class TestUsageTracking:
    """Tests for usage tracking."""

    def test_track_usage(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test tracking usage."""
        cost = budget_manager.track_usage(
            provider="anthropic",
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=1000,
        )

        assert cost > 0
        assert temp_usage_file.exists()

        # Check saved data with new structure
        with open(temp_usage_file) as f:
            data = json.load(f)
            assert len(data["today_records"]) == 1
            record = data["today_records"][0]
            assert record["provider"] == "anthropic"
            assert record["input_tokens"] == 1000
            assert record["output_tokens"] == 1000

    def test_track_multiple_usages(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test tracking multiple usages."""
        budget_manager.track_usage("openai", "gpt-5.1-codex", 1000, 1000)
        budget_manager.track_usage("anthropic", "claude-sonnet-4-5-20250929", 500, 500)
        budget_manager.track_usage("google", "gemini-3-flash-preview", 2000, 500)

        summary = budget_manager.get_usage_summary()
        assert summary["request_count"] == 3
        assert len(summary["provider_costs"]) == 3


class TestMonthlyReset:
    """Tests for monthly reset functionality."""

    def test_new_month_resets_usage(
        self, temp_usage_file: Path
    ) -> None:
        """Test that usage resets when month changes."""
        # Create usage from previous month
        old_month = "2024-01"
        usage_data = {
            "month": old_month,
            "total_cost_usd": 50.0,
            "request_count": 500,
            "provider_costs": {"openai": 50.0},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        # Create new budget manager (should detect new month)
        settings = CostControlSettings()
        manager = BudgetManager(settings=settings, usage_file=temp_usage_file)

        # Should be reset
        summary = manager.get_usage_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["request_count"] == 0


class TestBudgetWarningFormat:
    """Tests for budget warning formatting."""

    def test_format_budget_warning(self, budget_manager: BudgetManager) -> None:
        """Test warning message formatting."""
        warning = "BUDGET_WARNING"
        formatted = budget_manager.format_budget_warning(warning)
        assert "[Ternion]" in formatted
        assert warning in formatted
        assert "⚠️" in formatted

    def test_format_budget_warning_none(self, budget_manager: BudgetManager) -> None:
        """Test formatting with no warning."""
        formatted = budget_manager.format_budget_warning(None)
        assert formatted == ""
