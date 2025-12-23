"""
Tests for the budget management module.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

from ternion.core.budget import (
    BudgetManager,
    CostControlSettings,
    UsageRecord,
    COST_PER_1K_TOKENS,
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

    def test_calculate_cost_openai(self, budget_manager: BudgetManager) -> None:
        """Test OpenAI cost calculation."""
        cost = budget_manager.calculate_cost(
            provider="openai",
            input_tokens=1000,
            output_tokens=1000,
        )
        expected = (1000 / 1000) * 0.01 + (1000 / 1000) * 0.03
        assert cost == pytest.approx(expected)

    def test_calculate_cost_anthropic(self, budget_manager: BudgetManager) -> None:
        """Test Anthropic cost calculation."""
        cost = budget_manager.calculate_cost(
            provider="anthropic",
            input_tokens=2000,
            output_tokens=500,
        )
        expected = (2000 / 1000) * 0.015 + (500 / 1000) * 0.075
        assert cost == pytest.approx(expected)

    def test_calculate_cost_google(self, budget_manager: BudgetManager) -> None:
        """Test Google cost calculation."""
        cost = budget_manager.calculate_cost(
            provider="google",
            input_tokens=5000,
            output_tokens=1000,
        )
        expected = (5000 / 1000) * 0.00125 + (1000 / 1000) * 0.005
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
        # Pre-populate usage file with high usage
        current_month = datetime.now().strftime("%Y-%m")
        usage_data = {
            "month": current_month,
            "total_cost_usd": 9.95,
            "request_count": 100,
            "provider_costs": {},
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
        current_month = datetime.now().strftime("%Y-%m")
        usage_data = {
            "month": current_month,
            "total_cost_usd": 8.5,
            "request_count": 50,
            "provider_costs": {},
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
            provider="openai",
            input_tokens=1000,
            output_tokens=1000,
        )

        assert cost > 0
        assert temp_usage_file.exists()

        # Check saved data
        with open(temp_usage_file) as f:
            data = json.load(f)
            assert data["total_cost_usd"] == pytest.approx(cost)
            assert data["request_count"] == 1
            assert "openai" in data["provider_costs"]

    def test_track_multiple_usages(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test tracking multiple usages."""
        budget_manager.track_usage("openai", 1000, 1000)
        budget_manager.track_usage("anthropic", 500, 500)
        budget_manager.track_usage("google", 2000, 500)

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
