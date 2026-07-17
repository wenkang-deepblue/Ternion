/**
 * Internationalization (i18n) module for Ternion Control Panel.
 *
 * Provides multi-language translations.
 * Automatically detects browser language, with manual override for development.
 */

import EN from './locales/en'

export type Language = 'en' | 'zh' | 'es' | 'fr' | 'de' | 'ja' | 'ko';

// Translation keys organized by component/section
export interface Translations {
  // Header
  appTitle: string;
  appSubtitle: string;
  llmKeysEnabled: string;
  lightMode: string;
  darkMode: string;

  // Tabs
  tabConfig: string;
  tabPorts: string;
  tabUsage: string;
  tabLogs: string;

  // Status Bar
  statusAddApiKey: string;
  statusApiKeyAdded: string;
  statusConfigArbiter: string;
  statusConfigWriter: string;
  statusConfigReviewer: string;
  statusArbiterConfigured: string;
  statusWriterConfigured: string;
  statusReviewerConfigured: string;

  // API Key Manager
  apiKeyNameLabel: string;
  apiKeyLabel: string;
  apiKeyTitle: string;
  apiKeyDescription: string;
  apiKeyStorageNote: string;
  apiKeyPlaceholder: string;
  apiKeyTestAndSave: string;
  apiKeyTesting: string;
  apiKeySaved: string;
  apiKeyDeleted: string;
  apiKeySelected: string;
  apiKeyGetKey: string;
  enabled: string;

  // Provider names and descriptions
  providerGoogle: string;
  providerGoogleDesc: string;
  providerAnthropic: string;
  providerAnthropicDesc: string;
  providerOpenai: string;
  providerOpenaiDesc: string;
  apiKeyDuplicate: string;

  // Role Model Config
  roleConfigTitle: string;
  roleConfigDescription: string;
  roleConfigHint: string;
  ternionAName: string;
  ternionADesc: string;
  ternionBName: string;
  ternionBDesc: string;
  ternionCName: string;
  ternionCDesc: string;
  arbiterName: string;
  arbiterDesc: string;
  writerName: string;
  writerDesc: string;
  reviewerName: string;
  reviewerDesc: string;
  modelSeries: string;
  modelName: string;
  selectModel: string;
  selectSeries: string;
  currentConfig: string;
  notConfigured: string;
  apiKeyAdded: string;
  errorUnknown: string;
  successConnected: string;
  modelCatalogTitle: string;
  modelCatalogDescription: string;
  modelCatalogInitialize: string;
  modelCatalogInitializing: string;
  modelCatalogRefreshNow: string;
  modelCatalogRefreshing: string;
  modelCatalogInitSuccess: string;
  modelCatalogInitFailed: string;
  modelCatalogInitAnomaly: string;
  modelCatalogRefreshSuccess: string;
  modelCatalogRefreshFailed: string;
  modelCatalogRefreshAnomaly: string;
  modelCatalogStatus: string;
  modelCatalogStatusReady: string;
  modelCatalogStatusNeedsInitialization: string;
  modelCatalogFirstUseBanner: string;
  modelCatalogModelCount: string;
  modelCatalogCatalogUpdatedAt: string;
  modelCatalogScheduleTitle: string;
  modelCatalogScheduleDescription: string;
  modelCatalogScheduleEnabled: string;
  modelCatalogScheduleMode: string;
  modelCatalogScheduleDaily: string;
  modelCatalogScheduleDays: string;
  modelCatalogScheduleWeeks: string;
  modelCatalogScheduleTime: string;
  modelCatalogScheduleInterval: string;
  modelCatalogScheduleSaved: string;
  modelCatalogLastRefreshAt: string;
  modelCatalogNextRefreshAt: string;
  modelCatalogAnomalyBanner: string;
  modelCatalogAnomalyHelp: string;
  modelCatalogAnomalyUpdatedAt: string;
  modelCatalogRetry: string;
  modelCatalogViewDetails: string;
  modelCatalogDetailsTitle: string;

  // Status Bar - Ternion
  statusConfigTernionA: string;
  statusConfigTernionB: string;
  statusConfigTernionC: string;
  statusTernionAConfigured: string;
  statusTernionBConfigured: string;
  statusTernionCConfigured: string;
  statusTernionLine: string;

  // API Response Codes
  code_SUCCESS: string;
  code_AUTH_ERROR: string;
  code_CONNECTION_ERROR: string;
  code_UNKNOWN_ERROR: string;
  code_INVALID_PROVIDER: string;
  code_PROVIDER_NOT_FOUND: string;
  code_API_KEY_NOT_FOUND: string;
  code_API_KEY_DUPLICATE: string;
  code_PROVIDER_NOT_ENABLED: string;
  code_MODEL_NOT_AVAILABLE: string;
  code_MODEL_UNAVAILABLE: string;
  code_MODEL_PROBE_AUTH_ERROR: string;
  code_MODEL_PROBE_TIMEOUT: string;
  code_MODEL_PROBE_CONNECTION_ERROR: string;
  code_INVALID_BUDGET_LIMIT: string;
  code_INVALID_BUDGET_THRESHOLD: string;
  code_BUDGET_EXCEEDED: string;
  code_BUDGET_WARNING: string;
  code_STREAM_INTERRUPTED: string;
  code_ROLES_INCOMPLETE: string;
  code_ROLES_INCOMPLETE_SUFFIX: string;
  code_MODEL_CATALOG_REFRESH_FAILED: string;
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: string;
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: string;
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: string;
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: string;
  code_INVALID_PUBLIC_ACCESS_MODE: string;
  code_INVALID_PUBLIC_BASE_URL: string;
  saveChanges: string;
  saving: string;
  noApiKey: string;
  roleNotSaved: string;
  roleSelectionPending: string;
  unsavedLabel: string;
  roleConfigValidatingModel: string;
  roleConfigRemovedSelectionHint: string;
  roleConfigRefreshSuggested: string;
  roleConfigProModelWarningPrefix: string;
  roleConfigProModelWarningLinkLabel: string;
  roleConfigProModelWarningSuffix: string;

  // Budget Settings
  budgetTitle: string;
  budgetDescription: string;
  monthlyLimit: string;
  alertThreshold: string;
  budgetLimitNote: string;
  budgetThresholdNote: string;
  preview: string;
  monthlyLimitLabel: string;
  alertTriggerLabel: string;
  budgetSaved: string;

  // Ports Settings
  portsTitle: string;
  portsDescription: string;
  portsBackend: string;
  portsWeb: string;
  portsBackendLabel: string;
  portsCurrentBackend: string;
  portsCurrentWeb: string;
  portsAdvancedSettings: string;
  portsAdvancedDescription: string;
  portsShowAdvancedSettings: string;
  portsHideAdvancedSettings: string;
  portsCloudRunManaged: string;
  portsWarning: string;
  portsRestartNote: string;
  portsSaved: string;
  portsInvalid: string;
  portsDuplicate: string;
  portsConfirmChangeTitle: string;
  portsConfirmChangeDesc: string;
  portsConfirmBtn: string;
  portsCancelBtn: string;
  portsChangedToast: string;
  publicAccessTitle: string;
  publicAccessDescription: string;
  publicAccessDeploymentEnvironment: string;
  publicAccessDeploymentEnvironmentLocal: string;
  publicAccessDeploymentEnvironmentCloudRun: string;
  publicAccessDetectedPublicUrl: string;
  publicAccessDetectedPublicUrlUnavailable: string;
  publicAccessManualFallbackTitle: string;
  publicAccessManualFallbackDescription: string;
  publicAccessManualFallbackHint: string;
  publicAccessDocsTitle: string;
  publicAccessDocsDescription: string;
  publicAccessDocsLocalTunnel: string;
  publicAccessDocsCloudRun: string;
  publicAccessDocsGitHub: string;
  publicAccessMode: string;
  publicAccessModeNone: string;
  publicAccessModeLocalTunnel: string;
  publicAccessModeCloudRun: string;
  publicAccessModeCustom: string;
  publicAccessUrlPlaceholder: string;
  publicAccessConfiguredUrl: string;
  publicAccessCursorUrl: string;
  publicAccessSource: string;
  publicAccessSourceConfig: string;
  publicAccessSourceRequestOrigin: string;
  publicAccessSourceNgrokApi: string;
  publicAccessSourceNone: string;
  publicAccessCursorHint: string;
  publicAccessCursorGuide: string;
  publicAccessAutoDetectedNote: string;
  publicAccessCopy: string;
  publicAccessCopied: string;
  publicAccessCopyFailed: string;
  publicAccessTokenLabel: string;
  publicAccessTokenHint: string;
  publicAccessTokenDescription: string;
  accessTokenGateTitle: string;
  accessTokenGateDescription: string;
  accessTokenGatePlaceholder: string;
  accessTokenGateSubmit: string;
  accessTokenGateInvalid: string;
  publicAccessSaved: string;
  publicAccessUnavailable: string;
  publicAccessConfiguredToast: string;
  publicAccessIntroTitle: string;
  publicAccessIntroBody: string;
  publicAccessIntroOk: string;
  publicAccessIntroGuide: string;
  publicAccessGuideTitle: string;
  publicAccessGuideBody: string;
  publicAccessGuideClose: string;

  // Usage Dashboard
  usageTitle: string;
  usageMonth: string;
  usageTotal: string;
  usageRemaining: string;
  usageRequests: string;
  usageByProvider: string;
  usageNoData: string;
  usageDisclaimer: string;
  usageDontRemind: string;
  usageDailyUsage: string;
  usageMonthlyUsage: string;
  usageAllProviders: string;
  usageAllTokens: string;
  usageCost: string;
  usageInputTokens: string;
  usageOutputTokens: string;
  usageThoughtsTokens: string;
  usagePercentage: string;
  usageModifyBudget: string;
  usageCurrentBudget: string;
  usageChangeTo: string;
  usageConfirm: string;
  loading: string;

  // Common UI
  unnamed: string;
  delete: string;
  toggleVisibility: string;
  confirmDeleteApiKey: string;

  // Toast messages
  toastConfigSaved: string;
  toastNotConfigured: string;
  toastMissingRolesForTernionFull: string;

  // Footer
  footerApiDocs: string;
  footerVersion: string;

  // Language toggle
  languageToggle: string;

  // Observability Panel
  logsTitle: string;
  logsDescription: string;
  logsConnecting: string;
  logsConnected: string;
  logsDisconnected: string;
  logsClear: string;
  logsAutoScroll: string;
  logsNoLogs: string;
  logsDownload: string;
  logsDownloading: string;
  logsDownloadSuccess: string;
  logsDownloadError: string;
  logsDownloadedTo: string;
  logsEntriesCount: string;
  logsOpenFile: string;
  logsDismiss: string;

  // Settings Dropdown
  settingsTitle: string;
  settingsTheme: string;
  settingsThemeLight: string;
  settingsThemeDark: string;
  settingsThemeSystem: string;
  settingsLanguage: string;
  settingsLanguageAuto: string;
  settingsConfigLabel: string;
  settingsConfigRestoreHint: string;

  // Execution Mode Selector
  execModeTitle: string;
  execModeDescription: string;
  execModeRecommended: string;
  execModeCursorTitle: string;
  execModeTernionTitle: string;
  execModePros: string;
  execModeCons: string;
  execModeCursorPro1: string;
  execModeCursorPro2: string;
  execModeCursorPro3: string;
  execModeCursorCon1: string;
  execModeCursorCon2: string;
  execModeTernionPro1: string;
  execModeTernionPro2: string;
  execModeTernionPro3: string;
  execModeTernionCon1: string;
  execModeTernionCon2: string;
  execModeSave: string;
  execModeSaving: string;
  execModeDisabledHint: string;

  // Status Bar (Execution Mode)
  statusExecModeNotSelected: string;
  statusExecModeSelected: string;
}

function withReleaseMetadata(translations: Translations): Translations {
  return {
    ...translations,
    footerVersion: `Ternion v${__TERNION_VERSION__}`,
  }
}

const defaultTranslations = withReleaseMetadata(EN)
const loadedTranslations = new Map<Language, Translations>([['en', defaultTranslations]])
const pendingTranslations = new Map<Language, Promise<Translations>>()

const translationLoaders: Record<Language, () => Promise<Translations>> = {
  en: async () => defaultTranslations,
  zh: async () => (await import('./locales/zh')).default,
  es: async () => (await import('./locales/es')).default,
  fr: async () => (await import('./locales/fr')).default,
  de: async () => (await import('./locales/de')).default,
  ja: async () => (await import('./locales/ja')).default,
  ko: async () => (await import('./locales/ko')).default,
}

/**
 * Detect browser language and return appropriate language code.
 */
export function detectBrowserLanguage(): Language {
  if (typeof navigator !== 'undefined') {
    const nav = navigator as Navigator & { userLanguage?: string };
    const lang = (navigator.language || nav.userLanguage || 'en').toLowerCase();
    if (lang.startsWith('zh')) {
      return 'zh';
    }
    if (lang.startsWith('es')) {
      return 'es';
    }
    if (lang.startsWith('fr')) {
      return 'fr';
    }
    if (lang.startsWith('de')) {
      return 'de';
    }
    if (lang.startsWith('ja')) {
      return 'ja';
    }
    if (lang.startsWith('ko')) {
      return 'ko';
    }
  }
  return 'en';
}

/**
 * Return a loaded translation bundle, falling back to English while a locale loads.
 */
export function getTranslations(lang: Language): Translations {
  return loadedTranslations.get(lang) ?? defaultTranslations
}

/**
 * Load and cache a translation bundle on demand.
 */
export async function loadTranslations(lang: Language): Promise<Translations> {
  const loaded = loadedTranslations.get(lang)
  if (loaded) {
    return loaded
  }

  const pending = pendingTranslations.get(lang)
  if (pending) {
    return pending
  }

  const request = translationLoaders[lang]()
    .then((translations) => {
      const versionedTranslations = withReleaseMetadata(translations)
      loadedTranslations.set(lang, versionedTranslations)
      return versionedTranslations
    })
    .finally(() => {
      pendingTranslations.delete(lang)
    })
  pendingTranslations.set(lang, request)
  return request
}

/**
 * Check if a language uses CJK (Chinese, Japanese, Korean) formatting.
 * CJK languages use different separators and parentheses.
 */
export function isCJKLanguage(lang: Language): boolean {
  return lang === 'zh' || lang === 'ja' || lang === 'ko';
}

/**
 * Get localized error message from error code.
 * Falls back to the code itself if no translation exists.
 * 
 * @param t - Translations object
 * @param errorCode - Error code string from backend
 * @param language - Optional explicit language for formatting (defaults to 'en' if not provided)
 */
export function getErrorMessage(t: Translations, errorCode: string, language?: Language): string {
  if (errorCode.startsWith('INVALID_PORT_')) {
    return t.portsInvalid;
  }

  // Special handling: include missing roles for ROLES_INCOMPLETE
  // Backend may return: "ROLES_INCOMPLETE:ternion_a,arbiter,writer"
  if (errorCode.startsWith('ROLES_INCOMPLETE:')) {
    const raw = errorCode.slice('ROLES_INCOMPLETE:'.length);
    const missingRoles = raw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    const roleNameMap: Record<string, string> = {
      ternion_a: t.ternionAName,
      ternion_b: t.ternionBName,
      ternion_c: t.ternionCName,
      arbiter: t.arbiterName,
      writer: t.writerName,
      reviewer: t.reviewerName,
    };

    // Use explicit language parameter for CJK formatting decisions
    const isCJK = language ? isCJKLanguage(language) : false;
    const sep = isCJK ? '、' : ', ';
    const missingDisplay = missingRoles.map(r => roleNameMap[r] || r).join(sep);

    const baseKey = `code_ROLES_INCOMPLETE` as keyof Translations;
    const base = (t[baseKey] as unknown as string) || 'ROLES_INCOMPLETE';
    
    // Get localized suffix template from translations
    const suffixKey = `code_ROLES_INCOMPLETE_SUFFIX` as keyof Translations;
    const suffixTemplate = (t[suffixKey] as unknown as string) || ' (missing: {roles})';
    const suffix = missingDisplay ? suffixTemplate.replace('{roles}', missingDisplay) : '';
    return `${base}${suffix}`;
  }

  // Try to find translation with code_ prefix
  const key = `code_${errorCode}` as keyof Translations;
  if (t[key]) {
    return t[key];
  }
  // Fallback to the error code itself
  return errorCode;
}
