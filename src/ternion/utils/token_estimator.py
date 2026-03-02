"""
Token estimation utilities for Ternion.

Provides fallback token estimation when API responses are interrupted
or when exact token counts are unavailable.
"""

# Estimation ratios based on typical LLM behavior
OUTPUT_RATIO = 1.5  # Expected visible output ≈ 1.5x input
THOUGHTS_RATIO = 1.0  # Thinking tokens ≈ 1x input (for thinking models)
CHARS_PER_TOKEN = 4  # UTF-8 characters per token (Google's approximation)


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate token count from text content.

    Uses the approximation of 4 UTF-8 characters per token,
    consistent with Google's documentation.

    Args:
        text: Text content to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    return len(text.encode("utf-8")) // CHARS_PER_TOKEN


def estimate_interrupted_response(
    prompt_tokens: int,
    received_text: str,
    is_thinking_model: bool = False,
) -> dict:
    """
    Estimate token usage for an interrupted response.

    Args:
        prompt_tokens: Known input token count
        received_text: Text content received before interruption
        is_thinking_model: Whether the model uses thinking tokens

    Returns:
        Dict with estimated token counts and metadata
    """
    # Estimate received output tokens
    received_output_tokens = estimate_tokens_from_text(received_text)

    # Calculate expected totals based on ratios
    if is_thinking_model:
        expected_total_output = int(prompt_tokens * (OUTPUT_RATIO + THOUGHTS_RATIO))
        estimated_thoughts = int(prompt_tokens * THOUGHTS_RATIO)
    else:
        expected_total_output = int(prompt_tokens * OUTPUT_RATIO)
        estimated_thoughts = 0

    # Estimate remaining (undelivered) tokens
    estimated_remaining = max(0, expected_total_output - received_output_tokens)

    return {
        "prompt_tokens": prompt_tokens,
        "received_output_tokens": received_output_tokens,
        "estimated_remaining_tokens": estimated_remaining,
        "estimated_thoughts_tokens": estimated_thoughts,
        "estimated_total_tokens": prompt_tokens + received_output_tokens + estimated_remaining,
        "is_estimated": True,
        "is_interrupted": True,
    }


def is_thinking_model(model: str) -> bool:
    """
    Check if a model uses thinking/reasoning tokens.

    Args:
        model: Model ID

    Returns:
        True if model uses thinking tokens
    """
    thinking_models = [
        # Gemini thinking models (2.5+)
        "gemini-2.5",
        "gemini-3",
        # OpenAI reasoning models
        "o1",
        "o3",
        "gpt-5",  # Assuming GPT 5.x series uses reasoning
    ]
    model_lower = model.lower()
    return any(tm in model_lower for tm in thinking_models)
