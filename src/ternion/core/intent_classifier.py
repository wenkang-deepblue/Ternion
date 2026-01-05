"""
Intent classification for user confirmation responses.

Provides multi-language heuristic pattern matching to classify user intent
after receiving a Ternion analysis report. Supports confirm, reject, and
clarify intents across 7 languages.
"""

import re
import structlog
from enum import Enum


logger = structlog.get_logger(__name__)


class Intent(str, Enum):
    """Classification result for user confirmation response."""

    CONFIRM = "confirm"
    REJECT = "reject"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


# Patterns for confirmation intent (case-insensitive)
# Covers: English, Chinese, Spanish, French, German, Japanese, Korean
CONFIRM_PATTERNS = [
    # English - common confirmation phrases
    r"\b(yes|yep|yeah|yup|confirm|confirmed|proceed|continue|go\s*ahead|"
    r"approve|approved|correct|right|looks?\s*good|lgtm|do\s*it|start|"
    r"that'?s?\s*(right|correct)|sounds?\s*good|perfect|great|ok|okay|"
    r"agreed|agree|fine|sure|absolutely|definitely|precisely|exactly)\b",
    # Chinese - common confirmation phrases
    r"(是的|是|对|好的|好|可以|确认|继续|同意|正确|没问题|没错|行|"
    r"对的|开始|批准|进行|执行|确定|这就对了|分析正确|赞同)",
    # Spanish - common confirmation phrases
    r"\b(sí|si|confirmar|confirmado|continuar|aprobar|correcto|"
    r"adelante|perfecto|bien|vale|de\s*acuerdo)\b",
    # French - common confirmation phrases
    r"\b(oui|confirmer|confirmé|continuer|approuver|correct|"
    r"d'?accord|parfait|bien|ok)\b",
    # German - common confirmation phrases
    r"\b(ja|bestätigen|bestätigt|fortfahren|genehmigen|korrekt|richtig|"
    r"weiter|perfekt|gut|ok|einverstanden)\b",
    # Japanese - common confirmation phrases
    r"(はい|うん|確認|続行|承認|正しい|問題ない|いいですね|"
    r"その通り|よろしい|オッケー|大丈夫)",
    # Korean - common confirmation phrases
    r"(네|예|확인|계속|승인|맞아|좋아|문제없어|괜찮아|알겠어|진행)",
]

# Patterns for rejection intent (case-insensitive)
REJECT_PATTERNS = [
    # English - common rejection phrases
    r"\b(no|nope|reject|rejected|wrong|incorrect|not\s*right|mistake|"
    r"re-?analyze|redo|again|try\s*again|start\s*over|not\s*correct|"
    r"disagree|false|error|issue|problem|fix\s*this|that'?s?\s*wrong)\b",
    # Chinese - common rejection phrases
    r"(不对|不是|错了|错误|不正确|有问题|重新分析|再次分析|再来|"
    r"重做|重来|不同意|否|不行|这是错的|分析错误|需要修正)",
    # Spanish - common rejection phrases
    r"\b(no|rechazar|incorrecto|mal|error|problema|otra\s*vez|"
    r"de\s*nuevo|equivocado)\b",
    # French - common rejection phrases
    r"\b(non|rejeter|incorrect|faux|erreur|problème|encore|"
    r"recommencer|mauvais)\b",
    # German - common rejection phrases
    r"\b(nein|ablehnen|falsch|inkorrekt|fehler|problem|nochmal|"
    r"erneut|wiederholen)\b",
    # Japanese - common rejection phrases
    r"(いいえ|違う|間違い|エラー|問題|やり直し|もう一度|再分析|"
    r"不正解|修正)",
    # Korean - common rejection phrases
    r"(아니|아니요|틀려|틀렸어|잘못|오류|문제|다시|재분석|수정)",
]

# Patterns for clarification requests (case-insensitive)
CLARIFY_PATTERNS = [
    # English - clarification indicators
    r"\b(clarify|explain|what\s*about|how\s*about|consider|but|however|"
    r"what\s*if|also|addition|more\s*detail|elaborate|unclear|"
    r"don'?t\s*understand|confused|not\s*sure)\b",
    # Chinese - clarification indicators
    r"(解释|说明|怎么样|但是|不过|如果|另外|更多细节|不清楚|"
    r"不太明白|困惑|不确定|需要更多信息|能否解释)",
    # Japanese - clarification indicators
    r"(説明|詳細|しかし|でも|もし|また|よくわからない|不明)",
    # Korean - clarification indicators
    r"(설명|하지만|그런데|만약|또한|잘\s*모르겠어|불명확)",
]


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
    for pattern in REJECT_PATTERNS:
        if re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE):
            logger.debug("intent_classified", intent="reject", pattern=pattern[:30])
            return Intent.REJECT

    # Check for confirmation
    for pattern in CONFIRM_PATTERNS:
        if re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE):
            logger.debug("intent_classified", intent="confirm", pattern=pattern[:30])
            return Intent.CONFIRM

    # Check for clarification requests
    for pattern in CLARIFY_PATTERNS:
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

# System prompt for LLM intent classification
INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier. Classify the user's response to a Ternion analysis report.

Respond with ONLY ONE of these exact words:
- CONFIRM: User accepts the analysis and wants to proceed
- REJECT: User disagrees with the analysis and wants re-analysis
- CLARIFY: User has questions or needs more information
- UNKNOWN: Cannot determine user's intent

User's response: {user_message}

Your classification (one word only):"""


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
    from ternion.providers.manager import provider_manager
    from ternion.core.models import ChatMessage, MessageRole

    for provider_name, model_id in INTENT_FALLBACK_MODELS:
        provider = provider_manager.get_provider(provider_name)
        if not provider:
            continue

        try:
            messages = [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=INTENT_CLASSIFICATION_PROMPT.format(user_message=text[:500]),
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

