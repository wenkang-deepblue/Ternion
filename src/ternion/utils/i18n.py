"""
Internationalization (i18n) module for Ternion backend.

Provides localized messages for thinking stream logs and other user-facing
backend text. Language preference is stored in user configuration.
"""

from enum import Enum
from typing import Literal

from ternion.core.config_store import config_store


Language = Literal["en", "zh"]


class ThinkingLogKey(str, Enum):
    """Keys for thinking log messages."""

    DIVERGENCE_START = "divergence_start"
    DIVERGENCE_ANALYSIS = "divergence_analysis"
    CONVERGENCE_START = "convergence_start"
    CONVERGENCE_COMPLETE = "convergence_complete"
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    REVIEW_START = "review_start"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REVISION = "review_revision"


TRANSLATIONS: dict[Language, dict[str, str]] = {
    "en": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[Arbiter]**: Starting parallel problem analysis...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[Arbiter]**: Synthesizing opinions, generating report...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbiter]**: Report complete: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[Writer]**: Generating code from analysis report...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[Writer]**: Code generation complete\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[Reviewer]**: Reviewing code security and logic...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[Reviewer]**: Review passed\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[Reviewer]**: Revision needed, returning to Writer...\n",
    },
    "zh": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[Arbiter]**: 开始并发问题分析...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[Arbiter]**: 综合分析各方意见，生成报告...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbiter]**: 报告生成完成: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[Writer]**: 基于分析报告生成代码中...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[Writer]**: 代码生成完成\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[Reviewer]**: 审查代码安全性和逻辑...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[Reviewer]**: 审查通过\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[Reviewer]**: 需要修订，返回 Writer 重写...\n",
    },
}

DEFAULT_LANGUAGE: Language = "en"


def get_user_language() -> Language:
    """Get user's preferred language from configuration."""
    try:
        config = config_store.load()
        lang = getattr(config, "language", DEFAULT_LANGUAGE)
        if lang in ("en", "zh"):
            return lang
    except Exception:
        pass
    return DEFAULT_LANGUAGE


def t(key: ThinkingLogKey, **kwargs) -> str:
    """
    Get translated string for the given key.

    Args:
        key: Translation key from ThinkingLogKey enum
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated and formatted string
    """
    lang = get_user_language()
    translations = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE])
    template = translations.get(key, key.value)
    
    if kwargs:
        return template.format(**kwargs)
    return template
