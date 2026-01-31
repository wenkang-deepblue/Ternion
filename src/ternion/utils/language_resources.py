"""
Language resource loader for localization-driven heuristics and prompts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_RESOURCE_PATH = Path(__file__).with_name("language_resources.json")


@dataclass(frozen=True)
class DeliverablePolicyPatterns:
    doc_only: list[str]
    analysis_only: list[str]
    no_code: list[str]
    doc_hints: list[str]
    code_hints: list[str]


@dataclass(frozen=True)
class IntentPatterns:
    confirm: list[str]
    reject: list[str]
    clarify: list[str]


@dataclass(frozen=True)
class ReportSectionKeywords:
    scope: list[str]
    verification: list[str]
    risks: list[str]
    requirements: list[str]
    tradeoffs: list[str]
    design: list[str]
    fix_plan: list[str]
    evidence: list[str]
    if_not_effective: list[str]


def _read_language_resources() -> dict[str, Any]:
    try:
        with _RESOURCE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.error(
            "language_resources_load_failed",
            error=str(exc),
            path=str(_RESOURCE_PATH),
        )
    return {}


@lru_cache(maxsize=1)
def load_language_resources() -> dict[str, Any]:
    """Load language resources from the bundled JSON file."""
    return _read_language_resources()


def _get_list(data: dict[str, Any], *keys: str) -> list[str]:
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    if not isinstance(node, list):
        return []
    return [item for item in node if isinstance(item, str)]


def _get_str(data: dict[str, Any], *keys: str) -> str:
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    return node if isinstance(node, str) else ""


def get_deliverable_policy_patterns() -> DeliverablePolicyPatterns:
    data = load_language_resources()
    return DeliverablePolicyPatterns(
        doc_only=_get_list(data, "deliverable_policy", "doc_only_patterns"),
        analysis_only=_get_list(data, "deliverable_policy", "analysis_only_patterns"),
        no_code=_get_list(data, "deliverable_policy", "no_code_patterns"),
        doc_hints=_get_list(data, "deliverable_policy", "doc_hints"),
        code_hints=_get_list(data, "deliverable_policy", "code_hints"),
    )


def get_intent_patterns() -> IntentPatterns:
    data = load_language_resources()
    return IntentPatterns(
        confirm=_get_list(data, "intent_classifier", "confirm_patterns"),
        reject=_get_list(data, "intent_classifier", "reject_patterns"),
        clarify=_get_list(data, "intent_classifier", "clarify_patterns"),
    )


def get_intent_classification_prompt() -> str:
    data = load_language_resources()
    return _get_str(data, "intent_classifier_prompt")


def get_report_language_instruction_template() -> str:
    data = load_language_resources()
    return _get_str(data, "report_language_instruction_template")


def get_optimizer_language_instruction_template() -> str:
    data = load_language_resources()
    return _get_str(data, "optimizer_language_instruction_template")


def get_report_section_keywords() -> ReportSectionKeywords:
    data = load_language_resources()
    return ReportSectionKeywords(
        scope=_get_list(data, "report_section_keywords", "scope"),
        verification=_get_list(data, "report_section_keywords", "verification"),
        risks=_get_list(data, "report_section_keywords", "risks"),
        requirements=_get_list(data, "report_section_keywords", "requirements"),
        tradeoffs=_get_list(data, "report_section_keywords", "tradeoffs"),
        design=_get_list(data, "report_section_keywords", "design"),
        fix_plan=_get_list(data, "report_section_keywords", "fix_plan"),
        evidence=_get_list(data, "report_section_keywords", "evidence"),
        if_not_effective=_get_list(data, "report_section_keywords", "if_not_effective"),
    )


def get_language_name(language_code: str) -> str:
    data = load_language_resources()
    names = data.get("language_names")
    if isinstance(names, dict):
        name = names.get(language_code)
        if isinstance(name, str) and name.strip():
            return name
    return language_code


def get_cursor_non_agent_mode_hints() -> list[str]:
    data = load_language_resources()
    return _get_list(data, "cursor_non_agent_mode_hints")
