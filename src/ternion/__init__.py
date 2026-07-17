"""
Ternion - A local LLM proxy gateway for multi-model technical discussions.

This package provides an OpenAI-compatible API that orchestrates discussions
between multiple LLM providers (OpenAI, Anthropic, Google) to produce
higher quality, cross-validated solutions.
"""

__version__ = "1.3.3"
__author__ = "Ternion Contributors"
__license__ = "AGPL-3.0-only"

from ternion.core.config import settings

__all__ = ["settings", "__version__"]
