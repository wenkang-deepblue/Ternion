"""
Intent classification for user confirmation responses.

Provides multi-language heuristic pattern matching to classify user intent
after receiving a Ternion analysis report. Supports confirm, reject, and
clarify intents across 7 languages.
"""

import re
from enum import Enum

import structlog

from ternion.utils.language_resources import (
    get_intent_classification_prompt,
    get_intent_patterns,
)

logger = structlog.get_logger(__name__)


class Intent(str, Enum):
    """Classification result for user confirmation response."""

    CONFIRM = "confirm"
    REJECT = "reject"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


_INTENT_PATTERNS = get_intent_patterns()


def classify_intent(text: str) -> Intent:
    """
    Classify user intent from their confirmation response.

    Uses multi-language heuristic pattern matching to determine whether
    the user wants to confirm, reject, or clarify the analysis report.

    Args:
        text: The user's response text

    Returns:
        Intent enum value (CONFIRM, REJECT, CLARIFY, or UNKNOWN)
    """
    if not text or not text.strip():
        return Intent.UNKNOWN

    text_normalized = text.strip().lower()

    # Check for rejection first (higher priority than confirm)
    # This handles cases like "No, this is wrong"
    for pattern in _INTENT_PATTERNS.reject:
        if re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE):
            logger.debug("intent_classified", intent="reject", pattern=pattern[:30])
            return Intent.REJECT

    # Check for confirmation
    for pattern in _INTENT_PATTERNS.confirm:
        if re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE):
            logger.debug("intent_classified", intent="confirm", pattern=pattern[:30])
            return Intent.CONFIRM

    # Check for clarification requests
    for pattern in _INTENT_PATTERNS.clarify:
        if re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE):
            logger.debug("intent_classified", intent="clarify", pattern=pattern[:30])
            return Intent.CLARIFY

    # No clear match - return unknown
    logger.debug("intent_classified", intent="unknown", text_preview=text[:50])
    return Intent.UNKNOWN


def parse_session_marker(messages: list[dict]) -> str | None:
    """
    Parse session ID from conversation history.

    Searches through assistant messages for the TERNION_SESSION_ID marker
    embedded in previous responses.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys

    Returns:
        Session ID string if found, None otherwise
    """
    session_id_pattern = r"TERNION_SESSION_ID=([a-zA-Z0-9]+)"

    # Search in reverse order (most recent first)
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant" and content:
            match = re.search(session_id_pattern, content)
            if match:
                session_id = match.group(1)
                logger.debug("session_marker_found", session_id=session_id)
                return session_id

    return None


def parse_report_hash_marker(messages: list[dict]) -> str | None:
    """
    Parse report hash from conversation history.

    Searches through assistant messages for the TERNION_REPORT_HASH marker
    embedded in previous responses. Used for consistency verification.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys

    Returns:
        Report hash string if found, None otherwise
    """
    report_hash_pattern = r"TERNION_REPORT_HASH=([a-zA-Z0-9]+)"

    # Search in reverse order (most recent first)
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant" and content:
            match = re.search(report_hash_pattern, content)
            if match:
                report_hash = match.group(1)
                logger.debug("report_hash_marker_found", report_hash=report_hash)
                return report_hash

    return None


def get_latest_user_message(messages: list[dict]) -> str:
    """
    Extract the latest user message from conversation history.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys

    Returns:
        Content of the latest user message, or empty string if none found
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Handle multimodal content (extract text parts)
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                return " ".join(text_parts)
    return ""


# LLM models for intent classification fallback (ordered by cost, lowest first)
INTENT_FALLBACK_MODELS = [
    ("google", "gemini-flash-lite-latest"),
    ("openai", "gpt-5-nano"),
    ("anthropic", "claude-haiku-4-5-20251001"),
]

async def classify_intent_with_llm(text: str) -> Intent:
    """
    Classify user intent using LLM fallback.

    Uses the cheapest available model to classify ambiguous user responses.
    Model priority: gemini-flash-lite > gpt-5-nano > claude-haiku.

    Args:
        text: The user's response text

    Returns:
        Intent enum value from LLM classification, or UNKNOWN on failure
    """
    from ternion.core.models import ChatMessage, MessageRole
    from ternion.providers.manager import provider_manager

    prompt_template = get_intent_classification_prompt()
    if not prompt_template:
        logger.warning("intent_classifier_prompt_missing")
        return Intent.UNKNOWN

    for provider_name, model_id in INTENT_FALLBACK_MODELS:
        provider = provider_manager.get_provider(provider_name)
        if not provider:
            continue

        try:
            messages = [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=prompt_template.format(user_message=text[:500]),
                )
            ]

            response = await provider.chat_completion(
                messages=messages,
                model=model_id,
                temperature=0.0,  # Deterministic classification
                max_tokens=5,  # Only need one word
            )

            result = response.content.strip().upper()

            if result in ("CONFIRM", "YES", "PROCEED"):
                logger.info(
                    "llm_intent_classified",
                    intent="confirm",
                    provider=provider_name,
                    model=model_id,
                )
                return Intent.CONFIRM
            elif result in ("REJECT", "NO", "WRONG"):
                logger.info(
                    "llm_intent_classified",
                    intent="reject",
                    provider=provider_name,
                    model=model_id,
                )
                return Intent.REJECT
            elif result in ("CLARIFY", "QUESTION"):
                logger.info(
                    "llm_intent_classified",
                    intent="clarify",
                    provider=provider_name,
                    model=model_id,
                )
                return Intent.CLARIFY
            else:
                logger.info(
                    "llm_intent_classified",
                    intent="unknown",
                    provider=provider_name,
                    model=model_id,
                    raw_result=result,
                )
                return Intent.UNKNOWN

        except Exception as e:
            logger.warning(
                "llm_intent_classification_failed",
                provider=provider_name,
                model=model_id,
                error=str(e),
            )
            continue

    # No provider available or all failed
    logger.warning("llm_intent_classification_no_provider")
    return Intent.UNKNOWN


async def classify_intent_with_fallback(text: str) -> Intent:
    """
    Classify user intent with heuristic first, LLM fallback for unknown.

    This is the main entry point for intent classification. It first tries
    heuristic pattern matching, and only falls back to LLM when the
    heuristic returns UNKNOWN.

    Args:
        text: The user's response text

    Returns:
        Intent enum value (CONFIRM, REJECT, CLARIFY, or UNKNOWN)
    """
    # Step 1: Try heuristic classification (instant, zero-cost)
    heuristic_result = classify_intent(text)

    # If heuristic found a match, return immediately
    if heuristic_result != Intent.UNKNOWN:
        logger.debug(
            "intent_resolved_heuristic",
            intent=heuristic_result.value,
        )
        return heuristic_result

    # Step 2: Fall back to LLM classification for ambiguous cases
    logger.info("intent_fallback_to_llm", text_preview=text[:50])
    llm_result = await classify_intent_with_llm(text)

    logger.debug(
        "intent_resolved_llm",
        intent=llm_result.value,
    )
    return llm_result

