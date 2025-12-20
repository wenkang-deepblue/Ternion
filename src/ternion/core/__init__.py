"""
Core module initialization.

Provides configuration management, data models, and custom exceptions.
"""

from ternion.core.config import Settings, settings
from ternion.core.exceptions import TernionError
from ternion.core.models import ChatCompletionRequest, ChatCompletionResponse

__all__ = [
    "Settings",
    "settings",
    "TernionError",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
]
