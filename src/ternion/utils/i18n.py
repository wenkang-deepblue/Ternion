"""
Internationalization (i18n) module for Ternion backend.

Provides localized messages for thinking stream logs and other user-facing
backend text. Language preference is stored in user configuration.
"""

from enum import Enum
from typing import Literal

from ternion.core.config_store import config_store


Language = Literal["en", "zh", "es", "fr", "de", "ja", "ko"]


class MessageKey(str, Enum):
    """Keys for localized messages (logs, errors, UI text)."""

    DIVERGENCE_START = "divergence_start"
    DIVERGENCE_ANALYSIS = "divergence_analysis"
    CONVERGENCE_START = "convergence_start"
    CONVERGENCE_COMPLETE = "convergence_complete"
    CONVERGENCE_ERROR = "convergence_error"
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_ERROR = "execution_error"
    REVIEW_START = "review_start"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REVISION = "review_revision"
    FINAL_CHECK_ERROR = "final_check_error"

    # Validation Errors
    EXECUTION_MODE_MISSING = "execution_mode_missing"
    ROLE_CONFIG_INCOMPLETE = "role_config_incomplete"

    # Provider Manager Errors
    NO_PROVIDERS_CONFIGURED = "no_providers_configured"
    ROLE_NOT_CONFIGURED = "role_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    EXECUTION_MODE_NOT_CONFIGURED = "execution_mode_not_configured"


TRANSLATIONS: dict[Language, dict[str, str]] = {
    "en": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[Arbiter]**: Starting parallel problem analysis...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[Arbiter]**: Synthesizing opinions, generating report...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbiter]**: Report complete: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[Arbiter]**: Error during convergence: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[Writer]**: Generating code from analysis report...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[Writer]**: Code generation complete\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[Writer]**: Error during execution: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[Reviewer]**: Reviewing code security and logic...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[Reviewer]**: Review passed\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[Reviewer]**: Revision needed, returning to Writer...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[Reviewer]**: Error during review: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Execution mode not configured. Please open Web Control Panel to configure: "
            "{web_url} (Config -> Execution Mode -> Save)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Role model configuration incomplete. Please configure: {missing_roles}. "
            "Please open Web Control Panel: {web_url}"
        ),

        # Provider Manager Errors
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
    "zh": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[Arbiter]**: 开始并发问题分析...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[Arbiter]**: 综合分析各方意见，生成报告...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbiter]**: 报告生成完成: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[Arbiter]**: 综合分析错误: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[Writer]**: 基于分析报告生成代码中...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[Writer]**: 代码生成完成\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[Writer]**: 代码生成错误: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[Reviewer]**: 审查代码安全性和逻辑...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[Reviewer]**: 审查通过\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[Reviewer]**: 需要修订，返回 Writer 重写...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[Reviewer]**: 审查错误: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "执行模式未配置。请打开 Web 控制面板配置："
            "{web_url}（配置 -> 推理方案 -> 保存）"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "角色模型配置不完整，缺少：{missing_roles}。"
            "请打开 Web 控制面板：{web_url}"
        ),

        # Provider Manager Errors
        MessageKey.NO_PROVIDERS_CONFIGURED: "请在 Web 控制面板添加 API Key：{web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "角色 '{role}' 未配置。请在 Web 控制面板配置：{web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "角色 '{role}' 的提供商 '{provider}' 不可用。请在 Web 控制面板为 {provider} 添加 API Key。",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "执行模式未配置。请在 Web 控制面板选择并保存（{web_url} -> 配置 -> 推理方案选择）。",
    },
    "es": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[Árbitro]**: Iniciando análisis paralelo del problema...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[Árbitro]**: Sintetizando opiniones, generando informe...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[Árbitro]**: Informe completo: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[Árbitro]**: Error durante convergencia: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[Escritor]**: Generando código del informe de análisis...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[Escritor]**: Generación de código completa\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[Escritor]**: Error durante ejecución: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[Revisor]**: Revisando seguridad y lógica del código...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[Revisor]**: Revisión aprobada\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[Revisor]**: Revisión necesaria, regresando a Escritor...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[Revisor]**: Error durante revisión: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Modo de ejecución no configurado. Por favor abra el Panel de Control Web: "
            "{web_url} (Configuración -> Modo de Ejecución -> Guardar)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Configuración de modelo de rol incompleta. Por favor configure: {missing_roles}. "
            "Abra el Panel de Control Web: {web_url}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
    "fr": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[Arbitre]**: Démarrage de l'analyse parallèle du problème...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[Arbitre]**: Synthèse des opinions, génération du rapport...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[Arbitre]**: Rapport complet : {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[Arbitre]**: Erreur pendant la convergence : {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[Rédacteur]**: Génération du code à partir du rapport d'analyse...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[Rédacteur]**: Génération de code terminée\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[Rédacteur]**: Erreur pendant l'exécution : {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[Réviseur]**: Vérification de la sécurité et de la logique du code...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[Réviseur]**: Révision approuvée\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[Réviseur]**: Révision nécessaire, retour à Rédacteur...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[Réviseur]**: Erreur pendant la révision : {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Mode d'exécution non configuré. Veuillez ouvrir le Panneau de Contrôle Web : "
            "{web_url} (Config -> Mode d'Exécution -> Enregistrer)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Configuration du modèle de rôle incomplète. Veuillez configurer : {missing_roles}. "
            "Ouvrez le Panneau de Contrôle Web : {web_url}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
    "de": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[Schiedsrichter]**: Starte parallele Problemanalyse...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[Schiedsrichter]**: Meinungen synthetisieren, Bericht erstellen...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[Schiedsrichter]**: Bericht fertig: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[Schiedsrichter]**: Fehler bei der Konvergenz: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[Verfasser]**: Code aus Analysebericht generieren...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[Verfasser]**: Code-Generierung abgeschlossen\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[Verfasser]**: Fehler bei der Ausführung: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[Prüfer]**: Code-Sicherheit und Logik überprüfen...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[Prüfer]**: Überprüfung bestanden\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[Prüfer]**: Revision erforderlich, zurück zu Verfasser...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[Prüfer]**: Fehler bei der Überprüfung: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "Ausführungsmodus nicht konfiguriert. Bitte öffnen Sie das Web-Kontrollfeld: "
            "{web_url} (Konfiguration -> Ausführungsmodus -> Speichern)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "Rollenmodell-Konfiguration unvollständig. Bitte konfigurieren: {missing_roles}. "
            "Öffnen Sie das Web-Kontrollfeld: {web_url}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
    "ja": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[調停者]**: 並列問題分析を開始...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[調停者]**: 意見を統合し、レポートを作成中...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[調停者]**: レポート完成: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[調停者]**: 収束中にエラー: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[執筆者]**: 分析レポートからコードを生成中...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[執筆者]**: コード生成完了\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[執筆者]**: 実行中にエラー: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[審査者]**: コードのセキュリティとロジックを確認中...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[審査者]**: レビュー通過\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[審査者]**: 修正が必要、執筆者に戻ります...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[審査者]**: レビュー中にエラー: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "実行モードが設定されていません。Webコントロールパネルを開いて設定してください："
            "{web_url}（設定 -> 実行モード -> 保存）"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "ロールモデル設定が不完全です。設定が必要：{missing_roles}。"
            "Webコントロールパネルを開いてください：{web_url}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
    "ko": {
        MessageKey.DIVERGENCE_START: "> 🟢 **[중재자]**: 병렬 문제 분석 시작...\n",
        MessageKey.DIVERGENCE_ANALYSIS: "> 🔵 **[{ternion_id}]**: {preview}\n",
        MessageKey.CONVERGENCE_START: "> 🟢 **[중재자]**: 의견 종합, 보고서 작성 중...\n",
        MessageKey.CONVERGENCE_COMPLETE: "> 📋 **[중재자]**: 보고서 완성: {preview}\n",
        MessageKey.CONVERGENCE_ERROR: "> ❌ **[중재자]**: 수렴 중 오류: {error}\n",
        MessageKey.EXECUTION_START: "> ✍️ **[작성자]**: 분석 보고서에서 코드 생성 중...\n",
        MessageKey.EXECUTION_COMPLETE: "> ✅ **[작성자]**: 코드 생성 완료\n",
        MessageKey.EXECUTION_ERROR: "> ❌ **[작성자]**: 실행 중 오류: {error}\n",
        MessageKey.REVIEW_START: "> 🔍 **[검토자]**: 코드 보안 및 로직 검토 중...\n",
        MessageKey.REVIEW_APPROVED: "> ✅ **[검토자]**: 검토 통과\n",
        MessageKey.REVIEW_REVISION: "> 🔄 **[검토자]**: 수정 필요, 작성자에게 돌아갑니다...\n",
        MessageKey.FINAL_CHECK_ERROR: "> ❌ **[검토자]**: 검토 중 오류: {error}\n",

        # Validation Errors
        MessageKey.EXECUTION_MODE_MISSING: (
            "실행 모드가 구성되지 않았습니다. 웹 제어판을 열어 구성하세요: "
            "{web_url} (설정 -> 실행 모드 -> 저장)"
        ),
        MessageKey.ROLE_CONFIG_INCOMPLETE: (
            "역할 모델 구성이 불완전합니다. 구성 필요: {missing_roles}. "
            "웹 제어판을 열어주세요: {web_url}"
        ),

        # Provider Manager Errors (Fallback to English)
        MessageKey.NO_PROVIDERS_CONFIGURED: "Please add API keys in the Web Control Panel at {web_url}",
        MessageKey.ROLE_NOT_CONFIGURED: "Role '{role}' is not configured. Please configure it in the Web Control Panel at {web_url}",
        MessageKey.PROVIDER_UNAVAILABLE: "Provider '{provider}' for role '{role}' is not available. Please add an API key for {provider} in the Web Control Panel.",
        MessageKey.EXECUTION_MODE_NOT_CONFIGURED: "Execution mode not configured. Please choose and save it in the Web Control Panel ({web_url} -> Config -> Execution Mode).",
    },
}

DEFAULT_LANGUAGE: Language = "en"


def get_web_base_url() -> str:
    """
    Get the Web Control Panel base URL dynamically from user config.
    """
    try:
        config = config_store.load()
        # access attribute directly or use getattr, ports is Pydantic model
        port = getattr(config.ports, "web", 9120)
    except Exception:
        port = 9120
    return f"http://localhost:{port}"


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


def t(key: MessageKey, **kwargs) -> str:
    """
    Get translated string for the given key.

    Args:
        key: Translation key from MessageKey enum
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated and formatted string
    """
    lang = get_user_language()

    # Fallback to English if key missing in target language
    template = TRANSLATIONS.get(lang, {}).get(key)
    if not template:
        template = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, str(key))

    # Inject Web URL if not provided
    if "{web_url}" in template and "web_url" not in kwargs:
        kwargs["web_url"] = get_web_base_url()

    try:
        return template.format(**kwargs)
    except KeyError:
        return template  # Return unformatted on error
