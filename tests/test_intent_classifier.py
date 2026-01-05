"""
Tests for the intent classifier module.
"""

import pytest

from ternion.core.intent_classifier import (
    Intent,
    classify_intent,
    parse_session_marker,
    get_latest_user_message,
)


class TestClassifyIntent:
    """Tests for intent classification."""

    # English confirmation tests
    @pytest.mark.parametrize("text", [
        "yes",
        "Yes, proceed",
        "yep",
        "confirm",
        "looks good",
        "LGTM",
        "go ahead",
        "ok",
        "sure",
        "That's correct",
        "sounds good to me",
        "perfect, let's do it",
    ])
    def test_confirm_english(self, text):
        """Should classify English confirmation phrases."""
        assert classify_intent(text) == Intent.CONFIRM

    # Chinese confirmation tests
    @pytest.mark.parametrize("text", [
        "是的",
        "好的",
        "可以",
        "确认",
        "继续",
        "没问题",
        "对的",
        "分析正确",
    ])
    def test_confirm_chinese(self, text):
        """Should classify Chinese confirmation phrases."""
        assert classify_intent(text) == Intent.CONFIRM

    # Other languages confirmation tests
    @pytest.mark.parametrize("text,lang", [
        ("sí, confirmar", "Spanish"),
        ("oui, continuer", "French"),
        ("ja, bestätigen", "German"),
        ("はい、続行", "Japanese"),
        ("네, 확인", "Korean"),
    ])
    def test_confirm_other_languages(self, text, lang):
        """Should classify confirmation in other languages."""
        assert classify_intent(text) == Intent.CONFIRM, f"Failed for {lang}"

    # English rejection tests
    @pytest.mark.parametrize("text", [
        "no",
        "nope",
        "wrong",
        "incorrect",
        "that's wrong",
        "re-analyze",
        "try again",
        "this is not right",
        "disagree",
    ])
    def test_reject_english(self, text):
        """Should classify English rejection phrases."""
        assert classify_intent(text) == Intent.REJECT

    # Chinese rejection tests
    @pytest.mark.parametrize("text", [
        "不对",
        "错了",
        "不正确",
        "有问题",
        "重新分析",
        "这是错的",
        "需要修正",
    ])
    def test_reject_chinese(self, text):
        """Should classify Chinese rejection phrases."""
        assert classify_intent(text) == Intent.REJECT

    # Other languages rejection tests
    @pytest.mark.parametrize("text,lang", [
        ("no, incorrecto", "Spanish"),
        ("non, incorrect", "French"),
        ("nein, falsch", "German"),
        ("いいえ、間違い", "Japanese"),
        ("아니, 틀렸어", "Korean"),
    ])
    def test_reject_other_languages(self, text, lang):
        """Should classify rejection in other languages."""
        assert classify_intent(text) == Intent.REJECT, f"Failed for {lang}"

    # Clarification tests
    @pytest.mark.parametrize("text", [
        "can you clarify",
        "what about the edge case",
        "but what if",
        "what if we consider another approach",
        "需要更多细节",
        "不太明白这部分",
    ])
    def test_clarify(self, text):
        """Should classify clarification requests."""
        assert classify_intent(text) == Intent.CLARIFY

    # Unknown intent tests
    @pytest.mark.parametrize("text", [
        "",
        "   ",
        "hello world",
        "random text without intent",
        "12345",
    ])
    def test_unknown(self, text):
        """Should return UNKNOWN for ambiguous input."""
        assert classify_intent(text) == Intent.UNKNOWN

    def test_reject_priority_over_confirm(self):
        """Rejection indicators should take priority over confirmation."""
        # "yes" would match confirm, but "wrong" should trigger reject
        assert classify_intent("no, this is wrong") == Intent.REJECT

    def test_case_insensitive(self):
        """Classification should be case-insensitive."""
        assert classify_intent("YES") == Intent.CONFIRM
        assert classify_intent("NO") == Intent.REJECT


class TestParseSessionMarker:
    """Tests for session marker parsing."""

    def test_find_session_id(self):
        """Should find session ID in assistant message."""
        messages = [
            {"role": "user", "content": "help me fix this bug"},
            {"role": "assistant", "content": "Analysis...\n\nTERNION_SESSION_ID=abc123xyz"},
        ]
        assert parse_session_marker(messages) == "abc123xyz"

    def test_find_latest_session_id(self):
        """Should find the most recent session ID."""
        messages = [
            {"role": "assistant", "content": "TERNION_SESSION_ID=old123"},
            {"role": "user", "content": "try again"},
            {"role": "assistant", "content": "TERNION_SESSION_ID=new456"},
        ]
        assert parse_session_marker(messages) == "new456"

    def test_no_session_id(self):
        """Should return None when no session ID found."""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        assert parse_session_marker(messages) is None

    def test_empty_messages(self):
        """Should handle empty message list."""
        assert parse_session_marker([]) is None


class TestGetLatestUserMessage:
    """Tests for user message extraction."""

    def test_get_latest_user_message(self):
        """Should get the most recent user message."""
        messages = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "second message"},
        ]
        assert get_latest_user_message(messages) == "second message"

    def test_multimodal_content(self):
        """Should handle multimodal content with text parts."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "please analyze"},
                    {"type": "image_url", "image_url": {"url": "..."}},
                ]
            },
        ]
        assert get_latest_user_message(messages) == "please analyze"

    def test_no_user_messages(self):
        """Should return empty string when no user messages."""
        messages = [
            {"role": "assistant", "content": "hello"},
        ]
        assert get_latest_user_message(messages) == ""

    def test_empty_messages(self):
        """Should handle empty message list."""
        assert get_latest_user_message([]) == ""
