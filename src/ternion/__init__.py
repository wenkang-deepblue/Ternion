"""
Ternion - A local LLM proxy gateway for multi-model technical discussions.

This package provides an OpenAI-compatible API that orchestrates discussions
between multiple LLM providers (OpenAI, Anthropic, Google) to produce
higher quality, cross-validated solutions.
"""

__version__ = "0.1.0"
__author__ = "Ternion Contributors"
__license__ = "Apache-2.0"

from ternion.core.config import settings

__all__ = ["settings", "__version__"]
