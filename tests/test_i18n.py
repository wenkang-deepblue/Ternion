"""
Tests for the i18n module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ternion.utils.i18n import (
    DEFAULT_LANGUAGE,
    MessageKey,
    _load_translations,
    get_user_language,
    t,
)


class TestMessageKeyCompleteness:
    """Tests to ensure translation completeness across all languages."""

    def test_all_languages_have_required_keys(self) -> None:
        """All languages should have translations for all MessageKey values."""
        required_keys = list(MessageKey)
        translations_by_language = _load_translations()

        for lang, translations in translations_by_language.items():
            for key in required_keys:
                assert key in translations or key.value in translations, (
                    f"Missing translation for {key} in language '{lang}'"
                )

    def test_no_corrupted_characters(self) -> None:
        """Translations should not contain replacement characters (U+FFFD)."""
        for lang, translations in _load_translations().items():
            for key, value in translations.items():
                assert "\ufffd" not in value, (
                    f"Corrupted character found in {lang}/{key}: {value[:50]}..."
                )


class TestTranslationFunction:
    """Tests for the t() translation function."""

    @pytest.fixture
    def mock_english_config(self) -> MagicMock:
        """Mock config to return English language."""
        config = MagicMock()
        config.language = "en"
        return config

    @pytest.fixture
    def mock_chinese_config(self) -> MagicMock:
        """Mock config to return Chinese language."""
        config = MagicMock()
        config.language = "zh"
        return config

    def test_t_returns_translated_string(self, mock_english_config: MagicMock) -> None:
        """t() should return translated string for valid key."""
        with patch("ternion.utils.i18n._load_user_config", return_value=mock_english_config):
            result = t(MessageKey.DIVERGENCE_START)

            assert "Arbiter" in result
            assert "analysis" in result.lower()

    def test_t_formats_placeholders_correctly(self, mock_english_config: MagicMock) -> None:
        """t() should correctly format placeholder values."""
        with patch("ternion.utils.i18n._load_user_config", return_value=mock_english_config):
            result = t(
                MessageKey.DIVERGENCE_ANALYSIS, ternion_id="ternion_a", preview="Test preview"
            )

            assert "ternion_a" in result
            assert "Test preview" in result

    def test_t_formats_error_placeholders(self, mock_english_config: MagicMock) -> None:
        """t() should correctly format error placeholders."""
        with patch("ternion.utils.i18n._load_user_config", return_value=mock_english_config):
            result = t(MessageKey.CONVERGENCE_ERROR, error="Test error message")

            assert "Test error message" in result
            assert "error" in result.lower() or "Error" in result

    def test_t_formats_missing_roles_placeholder(self, mock_english_config: MagicMock) -> None:
        """t() should correctly format missing_roles placeholder."""
        with patch("ternion.utils.i18n._load_user_config", return_value=mock_english_config):
            result = t(MessageKey.ROLE_CONFIG_INCOMPLETE, missing_roles="arbiter, writer")

            assert "arbiter, writer" in result

    def test_t_respects_language_setting(self, mock_chinese_config: MagicMock) -> None:
        """t() should use user's configured language."""
        with patch("ternion.utils.i18n._load_user_config", return_value=mock_chinese_config):
            result = t(MessageKey.DIVERGENCE_START)

            # Chinese translation should contain Chinese characters
            assert "开始" in result or "分析" in result

    def test_t_falls_back_to_english_on_invalid_language(self) -> None:
        """t() should fall back to English for invalid language."""
        config = MagicMock()
        config.language = "invalid_lang"

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            result = t(MessageKey.DIVERGENCE_START)

            # Should get English version
            assert "Arbiter" in result


class TestAllLanguagePlaceholderFormatting:
    """Tests to ensure all language templates can be formatted without errors."""

    @pytest.mark.parametrize("lang", ["en", "zh", "es", "fr", "de", "ja", "ko"])
    def test_divergence_analysis_formats_in_all_languages(self, lang: str) -> None:
        """DIVERGENCE_ANALYSIS should format correctly in all languages."""
        config = MagicMock()
        config.language = lang

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            # Should not raise KeyError or ValueError
            result = t(MessageKey.DIVERGENCE_ANALYSIS, ternion_id="ternion_a", preview="Test")

            assert "ternion_a" in result
            assert "Test" in result

    @pytest.mark.parametrize("lang", ["en", "zh", "es", "fr", "de", "ja", "ko"])
    def test_error_keys_format_in_all_languages(self, lang: str) -> None:
        """Error message keys should format correctly in all languages."""
        config = MagicMock()
        config.language = lang

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            # Test all error keys
            error_keys = [
                MessageKey.CONVERGENCE_ERROR,
                MessageKey.EXECUTION_ERROR,
                MessageKey.FINAL_CHECK_ERROR,
            ]

            for key in error_keys:
                result = t(key, error="test error")
                assert "test error" in result, f"{key} failed to format in {lang}"

    @pytest.mark.parametrize("lang", ["en", "zh", "es", "fr", "de", "ja", "ko"])
    def test_validation_error_keys_format_in_all_languages(self, lang: str) -> None:
        """Validation error keys should format correctly in all languages."""
        config = MagicMock()
        config.language = lang

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            # ROLE_CONFIG_INCOMPLETE has a placeholder
            result = t(MessageKey.ROLE_CONFIG_INCOMPLETE, missing_roles="arbiter")
            assert "arbiter" in result, f"ROLE_CONFIG_INCOMPLETE failed to format in {lang}"

            # EXECUTION_MODE_MISSING has no placeholder
            result = t(MessageKey.EXECUTION_MODE_MISSING)
            assert len(result) > 0, f"EXECUTION_MODE_MISSING returned empty in {lang}"


class TestGetUserLanguage:
    """Tests for get_user_language function."""

    def test_returns_configured_language(self) -> None:
        """Should return user's configured language."""
        config = MagicMock()
        config.language = "zh"

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            result = get_user_language()

            assert result == "zh"

    def test_returns_default_on_error(self) -> None:
        """Should return default language when config fails."""
        with patch("ternion.utils.i18n._load_user_config", return_value=None):
            result = get_user_language()

            assert result == DEFAULT_LANGUAGE

    def test_returns_default_for_unsupported_language(self) -> None:
        """Should return default for unsupported language codes."""
        config = MagicMock()
        config.language = "unsupported"

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            result = get_user_language()

            assert result == DEFAULT_LANGUAGE

    def test_returns_browser_language_when_auto_is_set(self) -> None:
        """Should return browser_language when language is set to 'auto'."""
        config = MagicMock()
        config.language = "auto"
        config.browser_language = "zh"

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            result = get_user_language()

            assert result == "zh"

    def test_returns_default_when_auto_and_unsupported_browser_language(self) -> None:
        """Should return default when language is 'auto' but browser_language is unsupported."""
        config = MagicMock()
        config.language = "auto"
        config.browser_language = "pt"  # Portuguese not in supported list

        with patch("ternion.utils.i18n._load_user_config", return_value=config):
            result = get_user_language()

            assert result == DEFAULT_LANGUAGE
