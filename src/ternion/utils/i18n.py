"""
Internationalization (i18n) module for Ternion backend.

Provides localized messages for thinking stream logs and other user-facing
backend text. Language preference is stored in user configuration.
"""

from enum import Enum
from typing import Literal

from ternion.core.config_store import config_store


Language = Literal["en", "zh", "es", "fr", "de", "ja", "ko"]


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
    "es": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[Árbitro]**: Iniciando análisis paralelo del problema...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[Árbitro]**: Sintetizando opiniones, generando informe...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[Árbitro]**: Informe completo: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[Escritor]**: Generando código del informe de análisis...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[Escritor]**: Generación de código completa\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[Revisor]**: Revisando seguridad y lógica del código...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[Revisor]**: Revisión aprobada\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[Revisor]**: Revisión necesaria, regresando a Escritor...\n",
    },
    "fr": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[Arbitre]**: Démarrage de l'analyse parallèle du problème...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[Arbitre]**: Synthèse des opinions, génération du rapport...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbitre]**: Rapport complet : {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[Rédacteur]**: Génération du code à partir du rapport d'analyse...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[Rédacteur]**: Génération de code terminée\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[Réviseur]**: Vérification de la sécurité et de la logique du code...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[Réviseur]**: Révision approuvée\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[Réviseur]**: Révision nécessaire, retour à Rédacteur...\n",
    },
    "de": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[Schiedsrichter]**: Starte parallele Problemanalyse...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[Schiedsrichter]**: Meinungen synthetisieren, Bericht erstellen...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[Schiedsrichter]**: Bericht fertig: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[Verfasser]**: Code aus Analysebericht generieren...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[Verfasser]**: Code-Generierung abgeschlossen\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[Prüfer]**: Code-Sicherheit und Logik überprüfen...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[Prüfer]**: Überprüfung bestanden\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[Prüfer]**: Revision erforderlich, zurück zu Verfasser...\n",
    },
    "ja": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[調停者]**: 並列問題分析を開始...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[調停者]**: 意見を統合し、レポートを作成中...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[調停者]**: レポート完成: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[執筆者]**: 分析レポートからコードを生成中...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[執筆者]**: コード生成完了\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[審査者]**: コードのセキュリティとロジックを確認中...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[審査者]**: レビュー通過\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[審査者]**: 修正が必要、執筆者に戻ります...\n",
    },
    "ko": {
        ThinkingLogKey.DIVERGENCE_START: "> 🟢 **[중재자]**: 병렬 문제 분석 시작...\n",
        ThinkingLogKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{council_id}]**: {preview}\n",
        ThinkingLogKey.CONVERGENCE_START: "> 🟢 **[중재자]**: 의견 종합, 보고서 작성 중...\n",
        ThinkingLogKey.CONVERGENCE_COMPLETE: "> 📋 **[중재자]**: 보고서 완성: {preview}\n",
        ThinkingLogKey.EXECUTION_START: "> ✍️ **[작성자]**: 분석 보고서에서 코드 생성 중...\n",
        ThinkingLogKey.EXECUTION_COMPLETE: "> ✅ **[작성자]**: 코드 생성 완료\n",
        ThinkingLogKey.REVIEW_START: "> 🔍 **[검토자]**: 코드 보안 및 로직 검토 중...\n",
        ThinkingLogKey.REVIEW_APPROVED: "> ✅ **[검토자]**: 검토 통과\n",
        ThinkingLogKey.REVIEW_REVISION: "> 🔄 **[검토자]**: 수정 필요, 작성자에게 돌아갑니다...\n",
    },
}

DEFAULT_LANGUAGE: Language = "en"


def get_user_language() -> Language:
    """Get user's preferred language from configuration."""
    try:
        config = config_store.load()
        lang = getattr(config, "language", DEFAULT_LANGUAGE)
        if lang in ("en", "zh", "es", "fr", "de", "ja", "ko"):
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
