"""
Tests for secret redaction utilities.

Verifies that API keys and other secrets are properly redacted from text.
"""

from ternion.utils.secrets import contains_secret_pattern, redact_secrets


class TestRedactSecrets:
    """Tests for redact_secrets function."""

    def test_redact_openai_key(self) -> None:
        """OpenAI API keys (sk-...) should be redacted."""
        text = "Error with key sk-abc1234567890123456789012345678901234567890"
        result = redact_secrets(text)
        assert "sk-abc" not in result
        assert "[REDACTED:OpenAI-Key]" in result

    def test_redact_openai_proj_key(self) -> None:
        """OpenAI project keys (sk-proj-...) should be redacted."""
        text = "Error with key sk-proj-abc123-def456-ghi789-jkl012"
        result = redact_secrets(text)
        assert "sk-proj" not in result
        assert "[REDACTED:OpenAI-Key]" in result

    def test_redact_anthropic_key(self) -> None:
        """Anthropic API keys (sk-ant-...) should be redacted."""
        text = "Invalid key: sk-ant-api01-1234567890abcdefghij"
        result = redact_secrets(text)
        assert "sk-ant" not in result
        assert "[REDACTED:Anthropic-Key]" in result

    def test_redact_google_key(self) -> None:
        """Google API keys (AIza...) should be redacted."""
        text = "Google error: AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345"
        result = redact_secrets(text)
        assert "AIza" not in result
        assert "[REDACTED:Google-Key]" in result

    def test_redact_bearer_token(self) -> None:
        """Bearer tokens should be redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_secrets(text)
        assert "eyJhbGc" not in result
        assert "Bearer [REDACTED]" in result

    def test_redact_api_key_in_url(self) -> None:
        """API keys in URL query params should be redacted."""
        text = "https://api.example.com?api_key=abcdef123456789"
        result = redact_secrets(text)
        assert "abcdef123456789" not in result
        assert "api_key=[REDACTED]" in result

    def test_redact_multiple_keys(self) -> None:
        """Multiple different keys should all be redacted."""
        text = "Keys: sk-abc123456789012345678901234567890, AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345"
        result = redact_secrets(text)
        assert "sk-abc" not in result
        assert "AIza" not in result
        assert "[REDACTED:OpenAI-Key]" in result
        assert "[REDACTED:Google-Key]" in result

    def test_no_secrets_unchanged(self) -> None:
        """Text without secrets should be unchanged."""
        text = "Normal log message with no secrets"
        result = redact_secrets(text)
        assert result == text

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert redact_secrets("") == ""

    def test_none_input(self) -> None:
        """None-like input should be handled gracefully."""
        # The function requires a string, but empty string should work
        assert redact_secrets("") == ""

    def test_partial_key_not_redacted(self) -> None:
        """Partial keys that don't match pattern should not be redacted."""
        text = "Short: sk-abc (too short)"
        result = redact_secrets(text)
        # "sk-abc" is only 6 chars, pattern requires 20+
        assert "sk-abc" in result


class TestContainsSecretPattern:
    """Tests for contains_secret_pattern function."""

    def test_detects_openai_key(self) -> None:
        """Should detect OpenAI API key pattern."""
        text = "Error: sk-abc1234567890123456789012345678901234567890"
        assert contains_secret_pattern(text) is True

    def test_detects_anthropic_key(self) -> None:
        """Should detect Anthropic API key pattern."""
        text = "Error: sk-ant-api01-1234567890abcdefghij"
        assert contains_secret_pattern(text) is True

    def test_detects_google_key(self) -> None:
        """Should detect Google API key pattern."""
        text = "Error: AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345"
        assert contains_secret_pattern(text) is True

    def test_no_secrets(self) -> None:
        """Should return False when no secrets present."""
        text = "Normal log message"
        assert contains_secret_pattern(text) is False

    def test_empty_string(self) -> None:
        """Empty string should return False."""
        assert contains_secret_pattern("") is False


class TestLogManagerIntegration:
    """Integration tests for log manager redaction."""

    def test_log_manager_redacts_secrets(self) -> None:
        """log_manager.emit should automatically redact secrets."""
        from ternion.utils.log_manager import LogManager

        manager = LogManager()

        # Emit a message with an API key
        manager.emit(
            "ERROR", "TEST", "API error with key sk-abc1234567890123456789012345678901234567890"
        )

        # Check the history
        history = manager.get_history()
        assert len(history) == 1
        assert "sk-abc" not in history[0]["message"]
        assert "[REDACTED:OpenAI-Key]" in history[0]["message"]
