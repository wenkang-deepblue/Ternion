"""
Model ID normalization helpers.
"""

import re

_ANTHROPIC_LATEST_SNAPSHOT_PATTERN = re.compile(
    r"^(claude-(?:opus|sonnet)-(?P<major>\d+)-(?P<minor>\d+))-(?P<date>\d{8})$"
)


def normalize_anthropic_model_id_for_api(model_id: str) -> str:
    """Return an Anthropic API-safe model identifier.

    LiteLLM may surface date-suffixed snapshot IDs for Claude 4.6+ models such
    as ``claude-opus-4-6-20260205``. Anthropic's direct API expects the
    corresponding canonical ID without the snapshot suffix, e.g.
    ``claude-opus-4-6``. Older snapshot-based IDs remain unchanged.
    """
    match = _ANTHROPIC_LATEST_SNAPSHOT_PATTERN.fullmatch(model_id)
    if match is None:
        return model_id

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    if major > 4 or (major == 4 and minor >= 6):
        return match.group(1)
    return model_id
