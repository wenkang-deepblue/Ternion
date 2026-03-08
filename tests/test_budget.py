"""
Tests for the budget management module.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from ternion.core.budget import (
    BudgetManager,
    CostControlSettings,
)
from ternion.core.model_catalog import (
    CatalogModel,
    CatalogSnapshot,
    LiteLLMModelCatalogService,
)


@pytest.fixture
def temp_usage_file(tmp_path: Path) -> Path:
    """Create a temporary usage file path."""
    return tmp_path / "usage.json"


@pytest.fixture
def catalog_service(tmp_path: Path) -> LiteLLMModelCatalogService:
    """Create a seeded catalog service for budget tests."""
    service = LiteLLMModelCatalogService(
        cache_path=tmp_path / "model_catalog_cache.json",
        anomaly_report_path=tmp_path / "model_catalog_anomaly_report.json",
    )
    models = {
        "openai": [
            CatalogModel(
                id="gpt-5.2-2025-12-11",
                name="GPT 5.2",
                provider="openai",
                raw_key="gpt-5.2-2025-12-11",
                input_cost_per_token=1.75 / 1_000_000,
                output_cost_per_token=14.0 / 1_000_000,
                output_cost_per_reasoning_token=20.0 / 1_000_000,
            )
        ],
        "google": [
            CatalogModel(
                id="gemini-3-pro-preview",
                name="Gemini 3 Pro",
                provider="google",
                raw_key="gemini-3-pro-preview",
                input_cost_per_token=2.0 / 1_000_000,
                output_cost_per_token=12.0 / 1_000_000,
                input_cost_per_token_above_200k_tokens=4.0 / 1_000_000,
                output_cost_per_token_above_200k_tokens=18.0 / 1_000_000,
            ),
            CatalogModel(
                id="gemini-3-flash-preview",
                name="Gemini 3 Flash",
                provider="google",
                raw_key="gemini-3-flash-preview",
                input_cost_per_token=0.5 / 1_000_000,
                output_cost_per_token=3.0 / 1_000_000,
                input_cost_per_audio_token=1.0 / 1_000_000,
            ),
        ],
        "anthropic": [
            CatalogModel(
                id="claude-opus-4-5-20251101",
                name="Claude Opus 4.5",
                provider="anthropic",
                raw_key="claude-opus-4-5-20251101",
                input_cost_per_token=5.0 / 1_000_000,
                output_cost_per_token=25.0 / 1_000_000,
            ),
            CatalogModel(
                id="claude-sonnet-4-5-20250929",
                name="Claude Sonnet 4.5",
                provider="anthropic",
                raw_key="claude-sonnet-4-5-20250929",
                input_cost_per_token=3.0 / 1_000_000,
                output_cost_per_token=15.0 / 1_000_000,
            ),
            CatalogModel(
                id="claude-opus-4-1-20250805",
                name="Claude Opus 4.1",
                provider="anthropic",
                raw_key="claude-opus-4-1-20250805",
                input_cost_per_token=15.0 / 1_000_000,
                output_cost_per_token=75.0 / 1_000_000,
            ),
        ],
    }
    service._memory_snapshot = CatalogSnapshot(
        fetched_at=datetime.now().isoformat(),
        models_by_provider=models,
        index_by_id={model.id: model for items in models.values() for model in items},
    )
    return service


@pytest.fixture
def budget_manager(
    temp_usage_file: Path,
    catalog_service: LiteLLMModelCatalogService,
) -> BudgetManager:
    """Create a budget manager with test settings."""
    settings = CostControlSettings(
        monthly_limit_usd=10.0,
        alert_threshold=0.9,
    )
    return BudgetManager(
        settings=settings,
        usage_file=temp_usage_file,
        catalog_service=catalog_service,
    )


class TestCostCalculation:
    """Tests for cost calculation."""

    def test_calculate_cost_claude_opus_45(self, budget_manager: BudgetManager) -> None:
        """Test Claude Opus 4.5 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=1000,
            output_tokens=1000,
        )
        expected = 1000 * (5.0 / 1_000_000) + 1000 * (25.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_claude_sonnet_45(self, budget_manager: BudgetManager) -> None:
        """Test Claude Sonnet 4.5 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-sonnet-4-5-20250929",
            input_tokens=2000,
            output_tokens=500,
        )
        expected = 2000 * (3.0 / 1_000_000) + 500 * (15.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_claude_opus_41(self, budget_manager: BudgetManager) -> None:
        """Test Claude Opus 4.1 cost calculation."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-1-20250805",
            input_tokens=1000,
            output_tokens=1000,
        )
        expected = 1000 * (15.0 / 1_000_000) + 1000 * (75.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_unknown_model_returns_zero(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test that unknown models return zero cost."""
        cost = budget_manager.calculate_cost(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
        )
        assert cost == 0.0

    def test_calculate_cost_gemini_pro_standard_tier(self, budget_manager: BudgetManager) -> None:
        """Test Gemini Pro cost with context <= 200K."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-pro-preview",
            input_tokens=1000,
            output_tokens=1000,
            context_length=100000,
        )
        expected = 1000 * (2.0 / 1_000_000) + 1000 * (12.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_pro_extended_tier(self, budget_manager: BudgetManager) -> None:
        """Test Gemini Pro cost with context > 200K."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-pro-preview",
            input_tokens=1000,
            output_tokens=1000,
            context_length=250000,
        )
        expected = 1000 * (4.0 / 1_000_000) + 1000 * (18.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_flash_text_only(self, budget_manager: BudgetManager) -> None:
        """Test Gemini Flash cost with text-only input."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-flash-preview",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=0,
        )
        expected = 1000 * (0.5 / 1_000_000) + 1000 * (3.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_gemini_flash_with_audio(self, budget_manager: BudgetManager) -> None:
        """Test Gemini Flash cost with mixed text and audio input."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-flash-preview",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=400,
        )
        expected = 600 * (0.5 / 1_000_000) + 400 * (1.0 / 1_000_000) + 1000 * (3.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_reasoning_tokens_use_reasoning_rate(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test reasoning tokens use the dedicated reasoning rate."""
        cost = budget_manager.calculate_cost(
            model="gpt-5.2-2025-12-11",
            input_tokens=1000,
            output_tokens=1000,
            thoughts_tokens=400,
        )
        expected = 1000 * (1.75 / 1_000_000) + 600 * (14.0 / 1_000_000) + 400 * (20.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_reasoning_tokens_fall_back_to_output_rate(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test reasoning tokens fall back to the output rate when needed."""
        cost = budget_manager.calculate_cost(
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=1000,
            thoughts_tokens=400,
        )
        expected = 1000 * (3.0 / 1_000_000) + 1000 * (15.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_context_boundary_uses_standard_tier(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test the 200K context boundary stays on the standard tier."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-pro-preview",
            input_tokens=1000,
            output_tokens=1000,
            context_length=200000,
        )
        expected = 1000 * (2.0 / 1_000_000) + 1000 * (12.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_negative_tokens_clamped_to_zero(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test negative token counts are clamped to zero."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=-1000,
            output_tokens=-500,
            thoughts_tokens=-10,
            context_length=-1,
            audio_input_tokens=-100,
        )
        assert cost == 0.0

    def test_calculate_cost_thoughts_tokens_clamped_to_output_tokens(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test thoughts tokens are clamped to the output token count."""
        cost = budget_manager.calculate_cost(
            model="gpt-5.2-2025-12-11",
            input_tokens=1000,
            output_tokens=500,
            thoughts_tokens=800,
        )
        expected = 1000 * (1.75 / 1_000_000) + 500 * (20.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_audio_tokens_clamped_to_input_tokens(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test audio input tokens are clamped to the input token count."""
        cost = budget_manager.calculate_cost(
            model="gemini-3-flash-preview",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=1500,
        )
        expected = 1000 * (1.0 / 1_000_000) + 1000 * (3.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_calculate_cost_audio_without_audio_rate_uses_standard_input_rate(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test audio tokens fall back to the standard input rate when needed."""
        cost = budget_manager.calculate_cost(
            model="claude-opus-4-5-20251101",
            input_tokens=1000,
            output_tokens=1000,
            audio_input_tokens=400,
        )
        expected = 1000 * (5.0 / 1_000_000) + 1000 * (25.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_record_usage_matches_calculate_cost(
        self,
        budget_manager: BudgetManager,
    ) -> None:
        """Test calculate_cost and record_usage stay consistent."""
        expected = budget_manager.calculate_cost(
            model="gpt-5.2-2025-12-11",
            input_tokens=2000,
            output_tokens=1200,
            thoughts_tokens=300,
        )
        recorded = budget_manager.record_usage(
            provider="openai",
            model="gpt-5.2-2025-12-11",
            input_tokens=2000,
            output_tokens=1200,
            thoughts_tokens=300,
        )
        assert recorded == pytest.approx(expected)

    def test_record_usage_matches_persisted_cost_components(
        self,
        budget_manager: BudgetManager,
        temp_usage_file: Path,
    ) -> None:
        """Test the returned cost matches the persisted rounded components."""
        recorded = budget_manager.record_usage(
            provider="openai",
            model="gpt-5.2-2025-12-11",
            input_tokens=2000,
            output_tokens=1200,
            thoughts_tokens=300,
        )
        with open(temp_usage_file, encoding="utf-8") as f:
            data = json.load(f)

        entry = data["today_records"][0]
        persisted_total = entry["input_cost"] + entry["output_cost"] + entry["thoughts_cost"]
        assert recorded == persisted_total


class TestBudgetCheck:
    """Tests for budget checking."""

    def test_check_budget_under_limit(self, budget_manager: BudgetManager) -> None:
        """Test budget check when under limit."""
        allowed, warning = budget_manager.check_budget()
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
                    "input_cost": 5.0,  # 5.0 + 5.0 = 10.0, equals the 10.0 limit
                    "output_cost": 5.0,
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

        allowed, warning = budget_manager.check_budget()
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

        # 85% is below 90% threshold, so no warning
        allowed, warning = budget_manager.check_budget()
        assert allowed is True
        assert warning is None


class TestUsageTracking:
    """Tests for usage tracking."""

    def test_track_usage(self, budget_manager: BudgetManager, temp_usage_file: Path) -> None:
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
        budget_manager.track_usage("openai", "gpt-5.2-2025-12-11", 1000, 1000)
        budget_manager.track_usage("anthropic", "claude-sonnet-4-5-20250929", 500, 500)
        budget_manager.track_usage("google", "gemini-3-flash-preview", 2000, 500)

        summary = budget_manager.get_usage_summary()
        assert summary["request_count"] == 3
        assert len(summary["provider_costs"]) == 3
        assert summary["total_cost_usd"] > 0

    def test_record_usage_clamps_stored_thoughts_tokens(
        self,
        budget_manager: BudgetManager,
        temp_usage_file: Path,
    ) -> None:
        """Test persisted usage stores clamped thoughts tokens."""
        budget_manager.record_usage(
            provider="openai",
            model="gpt-5.2-2025-12-11",
            input_tokens=1000,
            output_tokens=500,
            thoughts_tokens=800,
        )

        with open(temp_usage_file, encoding="utf-8") as f:
            data = json.load(f)

        assert data["today_records"][0]["thoughts_tokens"] == 500


class TestMonthlyReset:
    """Tests for monthly reset functionality."""

    def test_new_month_resets_usage(
        self,
        temp_usage_file: Path,
        catalog_service: LiteLLMModelCatalogService,
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
        manager = BudgetManager(
            settings=settings,
            usage_file=temp_usage_file,
            catalog_service=catalog_service,
        )

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
        assert "[Ternion" in formatted
        assert "Control Panel" in formatted

    def test_format_budget_warning_none(self, budget_manager: BudgetManager) -> None:
        """Test formatting with no warning."""
        formatted = budget_manager.format_budget_warning(None)
        assert formatted == ""


class TestProviderCostAggregation:
    """Tests for provider cost aggregation with separate cost fields."""

    @pytest.fixture
    def temp_usage_file(self, tmp_path: Path) -> Path:
        """Create a temporary usage file path."""
        return tmp_path / "usage.json"

    @pytest.fixture
    def budget_manager(
        self,
        temp_usage_file: Path,
        catalog_service: LiteLLMModelCatalogService,
    ) -> BudgetManager:
        """Create a budget manager with test settings."""
        settings = CostControlSettings(
            monthly_limit_usd=100.0,
            alert_threshold=0.9,
        )
        return BudgetManager(
            settings=settings,
            usage_file=temp_usage_file,
            catalog_service=catalog_service,
        )

    def test_provider_costs_aggregate_separate_cost_fields(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test that provider_costs correctly aggregates input_cost+output_cost+thoughts_cost."""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = today[:7]

        # Create data with separate cost fields in daily_summaries
        usage_data = {
            "today": today,
            "today_records": [],
            "daily_summaries": [
                {
                    "date": f"{current_month}-01",
                    "providers": {
                        "google": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "thoughts_tokens": 100,
                            "input_cost": 0.002,
                            "output_cost": 0.006,
                            "thoughts_cost": 0.0012,
                        },
                        "anthropic": {
                            "input_tokens": 2000,
                            "output_tokens": 1000,
                            "thoughts_tokens": 200,
                            "input_cost": 0.006,
                            "output_cost": 0.015,
                            "thoughts_cost": 0.003,
                        },
                    },
                    "total_cost": 0.0332,
                }
            ],
            "monthly_totals": {},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        budget_manager._load_usage()
        summary = budget_manager.get_usage_summary()

        # provider_costs should aggregate input_cost + output_cost + thoughts_cost
        assert "google" in summary["provider_costs"]
        assert "anthropic" in summary["provider_costs"]
        assert summary["provider_costs"]["google"] == pytest.approx(
            0.0092, rel=0.01
        )  # 0.002+0.006+0.0012
        assert summary["provider_costs"]["anthropic"] == pytest.approx(
            0.024, rel=0.01
        )  # 0.006+0.015+0.003

    def test_provider_details_includes_separate_cost_fields(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test that provider_details output includes input_cost, output_cost, thoughts_cost."""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = today[:7]

        usage_data = {
            "today": today,
            "today_records": [],
            "daily_summaries": [
                {
                    "date": f"{current_month}-01",
                    "providers": {
                        "google": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "thoughts_tokens": 100,
                            "input_cost": 0.002,
                            "output_cost": 0.006,
                            "thoughts_cost": 0.0012,
                        },
                    },
                    "total_cost": 0.0092,
                }
            ],
            "monthly_totals": {},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        budget_manager._load_usage()
        detailed = budget_manager.get_detailed_usage()

        # provider_details should have separate cost fields
        google_details = detailed["provider_details"]["google"]
        assert "input_cost" in google_details
        assert "output_cost" in google_details
        assert "thoughts_cost" in google_details
        assert google_details["input_cost"] == pytest.approx(0.002, rel=0.01)
        assert google_details["output_cost"] == pytest.approx(0.006, rel=0.01)
        assert google_details["thoughts_cost"] == pytest.approx(0.0012, rel=0.01)
        assert google_details["cost"] == pytest.approx(0.0092, rel=0.01)

    def test_provider_costs_fallback_to_legacy_cost_field(
        self, budget_manager: BudgetManager, temp_usage_file: Path
    ) -> None:
        """Test backward compatibility with old data format using single 'cost' field."""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = today[:7]

        # Old data format with only 'cost' field (no separate input/output/thoughts costs)
        usage_data = {
            "today": today,
            "today_records": [],
            "daily_summaries": [
                {
                    "date": f"{current_month}-02",
                    "providers": {
                        "openai": {
                            "input_tokens": 1500,
                            "output_tokens": 750,
                            "thoughts_tokens": 0,
                            "cost": 0.045,  # Old format: only combined cost
                        },
                    },
                    "total_cost": 0.045,
                }
            ],
            "monthly_totals": {},
        }
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_usage_file, "w") as f:
            json.dump(usage_data, f)

        budget_manager._load_usage()
        summary = budget_manager.get_usage_summary()

        # Should fall back to 'cost' field when separate fields are 0
        assert "openai" in summary["provider_costs"]
        assert summary["provider_costs"]["openai"] == pytest.approx(0.045, rel=0.01)


class TestUsagePersistence:
    """Tests for usage persistence error handling."""

    def test_invalid_usage_file_is_backed_up(
        self,
        temp_usage_file: Path,
        catalog_service: LiteLLMModelCatalogService,
    ) -> None:
        """Test invalid usage data is backed up before reset."""
        temp_usage_file.parent.mkdir(parents=True, exist_ok=True)
        temp_usage_file.write_text("{invalid json", encoding="utf-8")

        manager = BudgetManager(
            settings=CostControlSettings(),
            usage_file=temp_usage_file,
            catalog_service=catalog_service,
        )

        backup_path = temp_usage_file.with_suffix(f"{temp_usage_file.suffix}.corrupt")
        assert backup_path.exists()
        assert manager.get_usage_summary()["total_cost_usd"] == 0.0
