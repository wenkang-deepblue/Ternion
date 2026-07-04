/**
 * Internationalization (i18n) module for Ternion Control Panel.
 *
 * Provides multi-language translations.
 * Automatically detects browser language, with manual override for development.
 */

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

const EN: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'Multi-Model Collaboration Gateway',
  llmKeysEnabled: 'LLM Key(s) enabled',
  lightMode: 'Switch to light mode',
  darkMode: 'Switch to dark mode',

  // Tabs
  tabConfig: 'Config',
  tabPorts: 'Ports',
  tabUsage: 'Usage',
  tabLogs: 'Logs',

  // Status Bar
  statusAddApiKey: 'Please add at least one API Key',
  statusApiKeyAdded: 'API Key added',
  statusExecModeNotSelected: 'Execution mode not selected',
  statusExecModeSelected: 'Execution mode',
  statusConfigArbiter: 'Please configure Arbiter model',
  statusConfigWriter: 'Please configure Writer model',
  statusConfigReviewer: 'Please configure Reviewer model',
  statusArbiterConfigured: 'Arbiter',
  statusWriterConfigured: 'Writer',
  statusReviewerConfigured: 'Reviewer',

  // API Key Manager
  apiKeyTitle: 'API Key Management',
  apiKeyDescription: 'Add LLM provider API Keys to enable models',
  apiKeyStorageNote: '(Saved keys stored in: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'Recommand to be same as API console',
  apiKeyNameLabel: 'Key Name',
  apiKeyLabel: 'API Key',
  apiKeyTestAndSave: 'Test & Save',
  apiKeyTesting: 'Testing...',
  apiKeySaved: 'API Key saved',
  apiKeyDeleted: 'API Key deleted',
  apiKeySelected: 'Selected API Key',
  apiKeyGetKey: 'Get Key',
  enabled: 'Enabled',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Google AI Studio API Key',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Anthropic API Key',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'OpenAI API Key',
  apiKeyDuplicate: 'This API Key already exists',

  // Role Model Config
  roleConfigTitle: 'Role Model Configuration',
  roleConfigDescription: 'Select model series and specific model for each role',
  roleConfigHint: '(Please add API Key above to enable models)',
  ternionAName: 'Ternion A',
  ternionADesc: 'First council member for parallel analysis',
  ternionBName: 'Ternion B',
  ternionBDesc: 'Second council member for parallel analysis',
  ternionCName: 'Ternion C',
  ternionCDesc: 'Third council member for parallel analysis',
  arbiterName: 'Arbiter',
  arbiterDesc: 'Synthesize opinions, resolve conflicts',
  writerName: 'Writer',
  writerDesc: 'Generate final code based on analysis',
  reviewerName: 'Reviewer',
  reviewerDesc: 'Review code security and logic',
  modelSeries: 'Model Series',
  modelName: 'Model Name',
  selectModel: 'Select model...',
  selectSeries: 'Select series...',
  currentConfig: 'Current config',
  notConfigured: 'Not configured',
  apiKeyAdded: 'API Key added',
  saveChanges: 'Save Changes',
  saving: 'Saving...',
  noApiKey: '(No API Key)',
  roleNotSaved: 'Role model not saved yet',
  roleSelectionPending: 'role model selected {model}, not saved yet',
  unsavedLabel: 'not saved',
  roleConfigValidatingModel: 'Validating model...',
  roleConfigRemovedSelectionHint: 'Some selected models were removed from the refreshed catalog. Please reselect them.',
  roleConfigRefreshSuggested: 'The model catalog may be outdated. Try refreshing the model list to resolve this issue.',
  roleConfigProModelWarningPrefix: 'OpenAI notes that ',
  roleConfigProModelWarningLinkLabel: 'Pro models',
  roleConfigProModelWarningSuffix:
    ' are the slowest, may take several minutes, and cost more. Choose carefully.',

  // Status Bar - Ternion
  statusConfigTernionA: 'Please configure Ternion A model',
  statusConfigTernionB: 'Please configure Ternion B model',
  statusConfigTernionC: 'Please configure Ternion C model',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: 'Budget Settings',
  budgetDescription: 'Recommended to set monthly budget limit and alert threshold',
  monthlyLimit: 'Monthly Limit (USD)',
  alertThreshold: 'Alert Threshold',
  budgetLimitNote: 'Reject new requests after reaching this amount',
  budgetThresholdNote: 'Show warning when reaching this percentage of budget',
  preview: 'Preview',
  monthlyLimitLabel: 'Monthly limit',
  alertTriggerLabel: 'Alert trigger amount',
  budgetSaved: 'Budget settings saved',

  // Ports Settings
  portsTitle: 'Port Configuration',
  portsDescription:
    'Public access information is shown above. Local deployments can change backend and Web UI ports from advanced settings when needed.',
  portsBackend: 'Change Ternion Backend API Port',
  portsWeb: 'Change Web UI Control Panel Port',
  portsBackendLabel: 'Backend',
  portsCurrentBackend: 'Current Ternion backend API port',
  portsCurrentWeb: 'Current Web UI control panel port',
  portsAdvancedSettings: 'Advanced port settings',
  portsAdvancedDescription:
    'Only advanced users should change backend or Web UI ports, typically when resolving local port conflicts.',
  portsShowAdvancedSettings: 'Show advanced settings',
  portsHideAdvancedSettings: 'Hide advanced settings',
  portsCloudRunManaged:
    'This service is running on Cloud Run. Container ports are managed by the platform and cannot be changed here.',
  portsWarning: 'Port changes require manual server restart to take effect',
  portsRestartNote: 'After saving, restart the server with the new configuration',
  portsSaved: 'Port configuration saved',
  portsInvalid: 'Invalid port number (1024-65535)',
  portsDuplicate: 'Backend and Web UI ports must be different.',
  portsConfirmChangeTitle: 'Confirm Port Change?',
  portsConfirmChangeDesc: 'Port changes take effect after manual restart. Save changes?',
  portsConfirmBtn: 'Confirm',
  portsCancelBtn: 'Cancel',
  portsChangedToast:
    'Ports updated. Backend: {backend}, Web UI: {web}. Please restart the ternion service manually.',
  publicAccessTitle: 'Public Access',
  publicAccessDescription:
    'View the detected public URL, copy the Cursor base URL, and use a manual fallback only when auto-detection is unavailable.',
  publicAccessDeploymentEnvironment: 'Deployment',
  publicAccessDeploymentEnvironmentLocal: 'Local deployment',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: 'Detected public URL',
  publicAccessDetectedPublicUrlUnavailable: 'Not auto-detected',
  publicAccessManualFallbackTitle: 'Manual fallback',
  publicAccessManualFallbackDescription:
    'If auto-detection is unavailable, you can store a public HTTPS URL here so it can still be displayed and copied on other devices.',
  publicAccessManualFallbackHint:
    'This does not start or configure any tunnel. It only saves a fallback value for display and copy.',
  publicAccessDocsTitle: 'Public access guides',
  publicAccessDocsDescription:
    'If no public URL is detected yet, use these guides to set up a local tunnel or review the GitHub documentation.',
  publicAccessDocsLocalTunnel: 'Local tunnel guide',
  publicAccessDocsCloudRun: 'Cloud Run deployment guide',
  publicAccessDocsGitHub: 'GitHub documentation',
  publicAccessMode: 'Deployment mode',
  publicAccessModeNone: 'None',
  publicAccessModeLocalTunnel: 'Local tunnel',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: 'Custom',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: 'Configured public URL',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: 'Effective URL source',
  publicAccessSourceConfig: 'Configured value',
  publicAccessSourceRequestOrigin: 'Detected from current request',
  publicAccessSourceNgrokApi: 'Detected from local ngrok API',
  publicAccessSourceNone: 'No public URL available',
  publicAccessCursorHint: 'Use the public HTTPS root URL in Cursor. Do not append `/v1`.',
  publicAccessCursorGuide:
    'Please copy the URL above to Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL, switch it on, open "OpenAI API Key" and enter any characters. Turn on "Add Custom Model" in "Models" and enter "ternion-team" to start using ternion!',
  publicAccessAutoDetectedNote:
    'This URL was auto-detected from the current public request or the local ngrok API, which is useful for Cloud Run, reverse proxy, and local tunnel deployments.',
  publicAccessCopy: 'Copy',
  publicAccessCopied: 'Cursor base URL copied',
  publicAccessCopyFailed: 'Failed to copy the Cursor base URL',
  publicAccessTokenLabel: 'Access Token',
  publicAccessTokenHint: 'Required for requests arriving through a public tunnel',
  publicAccessTokenDescription:
    'Paste this token into Cursor as the OpenAI API Key. Remote Control Panel access also requires it. Local requests on this machine do not.',
  accessTokenGateTitle: 'Access token required',
  accessTokenGateDescription:
    'This Control Panel is being accessed through a public tunnel. Enter the access token shown in the Ternion startup banner (or copy it from a local Control Panel session).',
  accessTokenGatePlaceholder: 'Paste the access token',
  accessTokenGateSubmit: 'Continue',
  publicAccessSaved: 'Public access settings saved',
  publicAccessUnavailable: 'Unable to load public access settings right now.',
  publicAccessConfiguredToast:
    'Public access is available. Open the Ports tab to copy the Cursor base URL.',
  publicAccessIntroTitle: 'Public HTTPS URL required',
  publicAccessIntroBody:
    "Cursor's Override OpenAI Base URL does not accept localhost or other local-only addresses.\nTo connect Cursor to Ternion, expose this service through a public HTTPS URL.",
  publicAccessIntroOk: 'OK',
  publicAccessIntroGuide: 'How to configure',
  publicAccessGuideTitle: 'How to configure public access',
  publicAccessGuideBody:
    "Example with ngrok:\n1. Install ngrok and sign in to your account.\n2. Run `ngrok http 9110` on the machine where Ternion is running.\n3. Copy the generated public HTTPS root URL.\n4. Paste that root URL into Cursor's Override OpenAI Base URL.\n5. Do not append `/v1`.\n\nIf you deploy Ternion on Cloud Run, you can use the service's public HTTPS origin directly.",
  publicAccessGuideClose: 'Close',

  // Usage Dashboard
  usageTitle: '📊 Usage Statistics',
  usageMonth: 'Month',
  usageTotal: 'Total Cost',
  usageRemaining: 'Remaining',
  usageRequests: 'Requests',
  usageByProvider: 'Cost by Provider',
  usageNoData: 'No usage data',
  usageDisclaimer: 'Usage data shown here is estimated and may not reflect actual billing. Please refer to your API provider\'s billing dashboard for accurate costs.',
  usageDontRemind: "Don't show again",
  usageDailyUsage: 'Daily Usage',
  usageMonthlyUsage: 'Monthly Usage',
  usageAllProviders: 'All Providers',
  usageAllTokens: 'All Tokens',
  usageCost: 'Cost',
  usageInputTokens: 'Input Tokens',
  usageOutputTokens: 'Output Tokens',
  usageThoughtsTokens: 'Thoughts Tokens',
  usagePercentage: 'Usage Amount',
  usageModifyBudget: 'Modify',
  usageCurrentBudget: 'Current budget limit',
  usageChangeTo: 'change to',
  usageConfirm: 'Confirm',
  loading: 'Loading...',

  // Common UI
  unnamed: 'Unnamed',
  delete: 'Delete',
  toggleVisibility: 'Toggle visibility',
  confirmDeleteApiKey: 'Delete this API Key?',

  // API Response Codes
  code_SUCCESS: 'Connected successfully',
  code_AUTH_ERROR: 'Invalid API Key',
  code_CONNECTION_ERROR: 'Connection failed',
  code_UNKNOWN_ERROR: 'Unknown error',
  code_INVALID_PROVIDER: 'Invalid provider',
  code_PROVIDER_NOT_FOUND: 'Provider not found',
  code_API_KEY_NOT_FOUND: 'API key not found',
  code_API_KEY_DUPLICATE: 'This API Key already exists',
  code_PROVIDER_NOT_ENABLED: 'Provider not enabled',
  code_MODEL_NOT_AVAILABLE: 'Model not available',
  code_MODEL_UNAVAILABLE: 'The selected model is no longer available from the provider',
  code_MODEL_PROBE_AUTH_ERROR: 'Model validation failed because the provider API key is invalid or unauthorized',
  code_MODEL_PROBE_TIMEOUT: 'Model validation timed out, please retry',
  code_MODEL_PROBE_CONNECTION_ERROR: 'Model validation failed because the provider could not be reached',
  code_INVALID_BUDGET_LIMIT: 'Invalid budget limit',
  code_INVALID_BUDGET_THRESHOLD: 'Invalid budget threshold',
  code_BUDGET_EXCEEDED: 'Monthly budget exceeded',
  code_BUDGET_WARNING: 'Approaching budget limit',
  code_STREAM_INTERRUPTED: 'Stream interrupted, please retry',
  code_ROLES_INCOMPLETE: 'Please configure all roles before saving',
  code_ROLES_INCOMPLETE_SUFFIX: ' (missing: {roles})',
  code_MODEL_CATALOG_REFRESH_FAILED: 'La actualización del catálogo de modelos falló',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'No se encontró el informe de anomalías del catálogo',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Modo de actualización automática no válido',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Hora de actualización automática no válida',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: 'Intervalo de actualización automática no válido',
  code_INVALID_PUBLIC_ACCESS_MODE: 'Invalid public access mode',
  code_INVALID_PUBLIC_BASE_URL: 'Invalid public HTTPS URL',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Unknown error',
  successConnected: 'Connected successfully',
  modelCatalogTitle: 'Catálogo de Modelos',
  modelCatalogDescription: 'Inicializa, actualiza y programa actualizaciones del catálogo de modelos de LiteLLM.',
  modelCatalogInitialize: 'Inicializar lista de modelos',
  modelCatalogInitializing: 'Inicializando...',
  modelCatalogRefreshNow: 'Actualizar lista de modelos',
  modelCatalogRefreshing: 'Actualizando...',
  modelCatalogInitSuccess: 'El catálogo de modelos se inicializó correctamente',
  modelCatalogInitFailed: 'No se pudo inicializar el catálogo de modelos',
  modelCatalogInitAnomaly: 'El catálogo de modelos se inicializó, pero se detectó una anomalía',
  modelCatalogRefreshSuccess: 'El catálogo de modelos se actualizó correctamente',
  modelCatalogRefreshFailed: 'No se pudo actualizar el catálogo de modelos',
  modelCatalogRefreshAnomaly: 'La actualización del catálogo terminó, pero se detectó una anomalía',
  modelCatalogStatus: 'Estado del catálogo',
  modelCatalogStatusReady: 'Listo',
  modelCatalogStatusNeedsInitialization: 'Se requiere inicialización',
  modelCatalogFirstUseBanner: '¿Es la primera vez que usa Ternion? Inicialice la lista de modelos.',
  modelCatalogModelCount: 'Modelos disponibles',
  modelCatalogCatalogUpdatedAt: 'Catálogo actualizado el',
  modelCatalogScheduleTitle: 'Actualización automática',
  modelCatalogScheduleDescription: 'Configure actualizaciones periódicas en segundo plano para el catálogo de modelos.',
  modelCatalogScheduleEnabled: 'Habilitar actualización automática',
  modelCatalogScheduleMode: 'Frecuencia de actualización',
  modelCatalogScheduleDaily: 'Todos los días',
  modelCatalogScheduleDays: 'Cada X días',
  modelCatalogScheduleWeeks: 'Cada X semanas',
  modelCatalogScheduleTime: 'Hora del día',
  modelCatalogScheduleInterval: 'Valor del intervalo',
  modelCatalogScheduleSaved: 'Configuración de actualización automática guardada',
  modelCatalogLastRefreshAt: 'Última actualización',
  modelCatalogNextRefreshAt: 'Próxima actualización',
  modelCatalogAnomalyBanner: 'Se detectó una anomalía en el catálogo de modelos',
  modelCatalogAnomalyHelp: 'Revise la configuración del proveedor, la conectividad de red o espere a que se actualicen las reglas de filtrado.',
  modelCatalogAnomalyUpdatedAt: 'Anomalía actualizada el',
  modelCatalogRetry: 'Reintentar',
  modelCatalogViewDetails: 'Ver detalles',
  modelCatalogDetailsTitle: 'Informe de anomalías del catálogo',

  // Toast messages
  toastConfigSaved: 'Configuration saved',
  toastNotConfigured: 'not configured',
  toastMissingRolesForTernionFull: 'Ternion Full mode selected. Please configure missing role models: {roles}',

  // Footer
  footerApiDocs: 'API Docs',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: 'Language',

  // Observability Panel
  logsTitle: 'Live Logs',
  logsDescription: 'Real-time backend processing logs',
  logsConnecting: 'Connecting...',
  logsConnected: 'Connected',
  logsDisconnected: 'Disconnected',
  logsClear: 'Clear',
  logsAutoScroll: 'Auto-scroll',
  logsNoLogs: 'No logs yet',
  logsDownload: 'Export',
  logsDownloading: 'Exporting...',
  logsDownloadSuccess: 'Logs exported successfully',
  logsDownloadError: 'Failed to export logs',
  logsDownloadedTo: 'Saved to',
  logsEntriesCount: 'entries',
  logsOpenFile: 'Show in File Manager',
  logsDismiss: 'Dismiss',

  // Settings Dropdown
  settingsTitle: 'Settings',
  settingsTheme: 'Theme',
  settingsThemeLight: 'Light',
  settingsThemeDark: 'Dark',
  settingsThemeSystem: 'System',
  settingsLanguage: 'Language',
  settingsLanguageAuto: 'Auto',
  settingsConfigLabel: 'Config',
  settingsConfigRestoreHint: 'If corrupted, restore from backup',

  // Execution Mode Selector
  execModeTitle: 'Execution Mode',
  execModeDescription: 'Select execution mode after Ternion analysis is confirmed',
  execModeRecommended: 'Recommended',
  execModeCursorTitle: 'Ternion Root Cause Analysis + Cursor Implementation',
  execModeTernionTitle: 'Ternion Root Cause Analysis + Code Implementation',
  execModePros: '✓ Pros',
  execModeCons: '✗ Cons',
  execModeCursorPro1: 'Lower cost, only analysis phase tokens consumed',
  execModeCursorPro2: 'Native Cursor code implementation experience',
  execModeCursorPro3: 'Switch to other Cursor models anytime',
  execModeCursorCon1: 'No code usability and security review',
  execModeCursorCon2: 'Code quality depends on Cursor model',
  execModeTernionPro1: 'Complete workflow with Ternion Agent code writing and review',
  execModeTernionPro2: 'Reviewer performs code usability and security review',
  execModeTernionPro3: 'Higher code quality',
  execModeTernionCon1: 'Higher cost, full workflow needs more tokens',
  execModeTernionCon2: 'Longer response time',
  execModeSave: 'Save',
  execModeSaving: 'Saving...',
  execModeDisabledHint: 'Cursor handles code generation, no configuration needed',
};

const ZH: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: '多模型协作网关配置中心',
  llmKeysEnabled: '个 LLM Key 已启用',
  lightMode: '切换到浅色模式',
  darkMode: '切换到深色模式',

  // Tabs
  tabConfig: '配置',
  tabPorts: '端口',
  tabUsage: '用量',
  tabLogs: '日志',

  // Status Bar
  statusAddApiKey: '请添加至少一个 API Key',
  statusApiKeyAdded: '已添加 API Key',
  statusExecModeNotSelected: '推理方案未选择',
  statusExecModeSelected: '推理方案',
  statusConfigArbiter: '请配置主持人模型',
  statusConfigWriter: '请配置执笔人模型',
  statusConfigReviewer: '请配置审稿人模型',
  statusArbiterConfigured: '主持人',
  statusWriterConfigured: '执笔人',
  statusReviewerConfigured: '审稿人',

  // API Key Manager
  apiKeyTitle: 'API Key 管理',
  apiKeyDescription: '添加 LLM 提供商的 API Key 以启用对应模型',
  apiKeyStorageNote: '（已保存的 API Key 存储在：~/.ternion/config.json）',
  apiKeyPlaceholder: '建议与API控制台一致',
  apiKeyNameLabel: 'Key 名字',
  apiKeyLabel: 'API Key',
  apiKeyTestAndSave: '测试并保存',
  apiKeyTesting: '测试中...',
  apiKeySaved: 'API Key 已保存',
  apiKeyDeleted: 'API Key 已删除',
  apiKeySelected: '已选择使用 API Key',
  apiKeyGetKey: '获取 Key',
  enabled: '已启用',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Google AI Studio API Key',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Anthropic API Key',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'OpenAI API Key',
  apiKeyDuplicate: '此 API Key 已存在',

  // Role Model Config
  roleConfigTitle: '角色模型配置',
  roleConfigDescription: '为每个角色选择使用的模型系列和具体模型',
  roleConfigHint: '（请先在上方添加 API Key 以启用模型）',
  ternionAName: 'Ternion A',
  ternionADesc: '第一位Ternion，并行分析问题',
  ternionBName: 'Ternion B',
  ternionBDesc: '第二位Ternion，并行分析问题',
  ternionCName: 'Ternion C',
  ternionCDesc: '第三位Ternion，并行分析问题',
  arbiterName: '主持人 (Arbiter)',
  arbiterDesc: '综合分析各方意见，仲裁冲突',
  writerName: '执笔人 (Writer)',
  writerDesc: '基于分析报告生成最终代码',
  reviewerName: '审稿人 (Reviewer)',
  reviewerDesc: '审查代码安全性和逻辑',
  modelSeries: '模型系列',
  modelName: '模型名字',
  selectModel: '选择模型...',
  selectSeries: '选择模型系列...',
  currentConfig: '当前配置',
  notConfigured: '未配置',
  apiKeyAdded: '已添加 API Key',
  saveChanges: '保存更改',
  saving: '保存中...',
  noApiKey: '(未配置 API Key)',
  roleNotSaved: '角色模型未保存',
  roleSelectionPending: '角色模型选择 {model}，尚未保存',
  unsavedLabel: '尚未保存',
  roleConfigValidatingModel: '正在验证模型...',
  roleConfigRemovedSelectionHint: '部分已选模型已从最新模型列表中移除，请重新选择。',
  roleConfigRefreshSuggested: '模型列表可能已过期，请尝试刷新模型列表以解决此问题。',
  roleConfigProModelWarningPrefix: 'OpenAI 官方提示：',
  roleConfigProModelWarningLinkLabel: 'Pro 系列',
  roleConfigProModelWarningSuffix: ' 响应最慢，部分请求可能耗时数分钟，且成本更高，请谨慎选择。',

  // Status Bar - Ternion
  statusConfigTernionA: '请配置Ternion A 模型',
  statusConfigTernionB: '请配置Ternion B 模型',
  statusConfigTernionC: '请配置Ternion C 模型',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: '预算设置',
  budgetDescription: '建议设置每月预算上限和提醒阈值',
  monthlyLimit: '月度预算上限 (USD)',
  alertThreshold: '提醒阈值',
  budgetLimitNote: '达到此金额后将拒绝新请求',
  budgetThresholdNote: '达到预算的此比例时在响应中显示警告',
  preview: '预览',
  monthlyLimitLabel: '月度上限',
  alertTriggerLabel: '提醒触发金额',
  budgetSaved: '预算设置已保存',

  // Ports Settings
  portsTitle: '端口配置',
  portsDescription: '公网接入信息优先展示在上方。本地部署时，如确有需要，可在高级设置中修改后端端口和 Web UI 端口。',
  portsBackend: '更改 Ternion 后端 API 端口',
  portsWeb: '更改 Web UI 控制台端口',
  portsBackendLabel: '后端',
  portsCurrentBackend: '当前 Ternion 后端 API 端口',
  portsCurrentWeb: '当前 Web UI 控制台端口',
  portsAdvancedSettings: '高级端口设置',
  portsAdvancedDescription: '通常只有在本地端口冲突时，才需要由高级用户修改后端端口和 Web UI 端口。',
  portsShowAdvancedSettings: '显示高级设置',
  portsHideAdvancedSettings: '隐藏高级设置',
  portsCloudRunManaged:
    '当前服务运行在 Cloud Run 中，容器端口由平台管理，不能在这里修改。',
  portsWarning: '更改端口后需要手动重启服务才能生效',
  portsRestartNote: '保存后，请使用新配置重启服务器',
  portsSaved: '端口配置已保存',
  portsInvalid: '无效的端口号 (1024-65535)',
  portsDuplicate: '后端端口和 Web UI 端口不能相同。',
  portsConfirmChangeTitle: '是否确认更改端口？',
  portsConfirmChangeDesc: '端口重启后生效。是否保存更改？',
  portsConfirmBtn: '确认',
  portsCancelBtn: '取消',
  portsChangedToast: '端口已更新。后端：{backend}，Web UI：{web}。请手动重启 ternion 服务。',
  publicAccessTitle: '公网接入',
  publicAccessDescription: '查看当前检测到的公网 URL，复制 Cursor Base URL，并在自动检测失败时补充手动输入。',
  publicAccessDeploymentEnvironment: '当前部署方式',
  publicAccessDeploymentEnvironmentLocal: '本地部署',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: '当前检测到的公网 URL',
  publicAccessDetectedPublicUrlUnavailable: '尚未自动检测到',
  publicAccessManualFallbackTitle: '手动输入',
  publicAccessManualFallbackDescription:
    '如果当前无法自动检测到公网 URL，您可以在这里补充一个公网 HTTPS URL，便于在其他设备上继续展示和复制。',
  publicAccessManualFallbackHint:
    '这不会自动启动或配置任何 tunnel，只会保存一个用于展示和复制的文本。',
  publicAccessDocsTitle: '公网接入文档入口',
  publicAccessDocsDescription:
    '如果当前还没有检测到公网 URL，可以通过下面的入口查看本地隧道配置文档或 GitHub 文档。',
  publicAccessDocsLocalTunnel: '本地隧道配置文档',
  publicAccessDocsCloudRun: 'Cloud Run 部署文档',
  publicAccessDocsGitHub: 'GitHub 文档',
  publicAccessMode: '部署方式',
  publicAccessModeNone: '未配置',
  publicAccessModeLocalTunnel: '本地隧道',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: '自定义',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: '已配置公网 URL',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: '生效 URL 来源',
  publicAccessSourceConfig: '显式配置值',
  publicAccessSourceRequestOrigin: '根据当前请求自动推断',
  publicAccessSourceNgrokApi: '根据本机 ngrok API 自动发现',
  publicAccessSourceNone: '当前无可用公网 URL',
  publicAccessCursorHint: '在 Cursor 中填写公网 HTTPS 根 URL，不要追加 `/v1`。',
  publicAccessCursorGuide:
    '请将上面的URL复制到Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL下方的输入框中，并打开开关，打开"OpenAI API Key"并填入任意字符。在“Models”中点击“View All Models” --> "Add Custom Model"，填写“ternion-team”，即可开始使用ternion!',
  publicAccessAutoDetectedNote:
    '当前 URL 是根据本次公网请求或本机 ngrok API 自动检测得到的，适用于 Cloud Run、反向代理或本地隧道部署。',
  publicAccessCopy: '复制',
  publicAccessCopied: '已复制 Cursor Base URL',
  publicAccessCopyFailed: '复制 Cursor Base URL 失败',
  publicAccessTokenLabel: '访问令牌',
  publicAccessTokenHint: '通过公网隧道访问时必须携带',
  publicAccessTokenDescription:
    '请将此令牌粘贴到 Cursor 的 OpenAI API Key 字段。远程访问控制面板同样需要它；本机请求无需携带。',
  accessTokenGateTitle: '需要访问令牌',
  accessTokenGateDescription:
    '当前正通过公网隧道访问控制面板。请输入 Ternion 启动横幅中显示的访问令牌（也可在本机打开控制面板复制）。',
  accessTokenGatePlaceholder: '粘贴访问令牌',
  accessTokenGateSubmit: '继续',
  publicAccessSaved: '公网接入设置已保存',
  publicAccessUnavailable: '暂时无法加载公网接入配置。',
  publicAccessConfiguredToast: '已检测到可用公网接入。请打开“端口”页复制 Cursor Base URL。',
  publicAccessIntroTitle: '需要公网 HTTPS URL',
  publicAccessIntroBody:
    'Cursor 的 Override OpenAI Base URL 不接受 localhost 或其他仅本地可访问的地址。\n如果您希望在 Cursor 中连接 Ternion，需要先为该服务提供一个可公网访问的 HTTPS URL。',
  publicAccessIntroOk: '确定',
  publicAccessIntroGuide: '配置方法',
  publicAccessGuideTitle: '公网接入配置指南',
  publicAccessGuideBody:
    '以 ngrok 为例：\n1. 安装 ngrok，并完成账号登录。\n2. 在运行 Ternion 的机器上执行 `ngrok http 9110`。\n3. 复制生成的公网 HTTPS 根 URL。\n4. 将该根 URL 填入 Cursor 的 Override OpenAI Base URL。\n5. 不要在末尾追加 `/v1`。\n\n如果您将 Ternion 部署在 Cloud Run 上，也可以直接使用服务自身的公网 HTTPS 域名。',
  publicAccessGuideClose: '关闭',

  // Usage Dashboard
  usageTitle: '📊 用量统计',
  usageMonth: '月份',
  usageTotal: '总花费',
  usageRemaining: '剩余',
  usageRequests: '请求数',
  usageByProvider: '各提供商用量',
  usageNoData: '暂无用量数据',
  usageDisclaimer: '此处显示的用量数据为估算值，可能与实际账单不符。请以 API 提供商的账单为准。',
  usageDontRemind: '不再显示',
  usageDailyUsage: '每日用量',
  usageMonthlyUsage: '月度用量',
  usageAllProviders: '全部提供商',
  usageAllTokens: '全部Token',
  usageCost: '金额',
  usageInputTokens: '输入Token',
  usageOutputTokens: '输出Token',
  usageThoughtsTokens: '思考Token',
  usagePercentage: '用量金额',
  usageModifyBudget: '修改预算',
  usageCurrentBudget: '当前预算上限',
  usageChangeTo: '调整为',
  usageConfirm: '确认',
  loading: '加载中...',

  // Common UI
  unnamed: '未命名',
  delete: '删除',
  toggleVisibility: '切换可见性',
  confirmDeleteApiKey: '确定删除此 API Key？',

  // API Response Codes
  code_SUCCESS: '连接成功',
  code_AUTH_ERROR: 'API Key 无效',
  code_CONNECTION_ERROR: '连接失败',
  code_UNKNOWN_ERROR: '未知错误',
  code_INVALID_PROVIDER: '无效的提供商',
  code_PROVIDER_NOT_FOUND: '未找到提供商配置',
  code_API_KEY_NOT_FOUND: 'API Key 未找到',
  code_API_KEY_DUPLICATE: '此 API Key 已存在',
  code_PROVIDER_NOT_ENABLED: '提供商未启用',
  code_MODEL_NOT_AVAILABLE: '模型不可用',
  code_MODEL_UNAVAILABLE: '所选模型当前已无法从提供商获取',
  code_MODEL_PROBE_AUTH_ERROR: '模型校验失败：当前提供商 API Key 无效或无权限',
  code_MODEL_PROBE_TIMEOUT: '模型校验超时，请重试',
  code_MODEL_PROBE_CONNECTION_ERROR: '模型校验失败：当前无法连接到提供商',
  code_INVALID_BUDGET_LIMIT: '无效的预算上限',
  code_INVALID_BUDGET_THRESHOLD: '无效的预算阈值',
  code_BUDGET_EXCEEDED: '本月预算已用尽',
  code_BUDGET_WARNING: '接近预算上限，请注意控制用量',
  code_STREAM_INTERRUPTED: '流式传输中断，请重试',
  code_ROLES_INCOMPLETE: '请先完成所有角色的模型选择',
  code_ROLES_INCOMPLETE_SUFFIX: '（缺少：{roles}）',
  code_MODEL_CATALOG_REFRESH_FAILED: '模型列表刷新失败',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: '未找到模型目录异常报告',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: '自动刷新模式无效',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: '自动刷新时间无效',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '自动刷新间隔无效',
  code_INVALID_PUBLIC_ACCESS_MODE: '公网接入模式无效',
  code_INVALID_PUBLIC_BASE_URL: '公网 HTTPS URL 无效',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '未知错误',
  successConnected: '连接成功',
  modelCatalogTitle: '模型目录管理',
  modelCatalogDescription: '初始化、手动刷新并配置 LiteLLM 模型目录的定时更新。',
  modelCatalogInitialize: '初始化模型列表',
  modelCatalogInitializing: '初始化中...',
  modelCatalogRefreshNow: '刷新模型列表',
  modelCatalogRefreshing: '刷新中...',
  modelCatalogInitSuccess: '模型列表初始化成功',
  modelCatalogInitFailed: '模型列表初始化失败',
  modelCatalogInitAnomaly: '模型列表已初始化，但检测到目录异常',
  modelCatalogRefreshSuccess: '模型列表刷新成功',
  modelCatalogRefreshFailed: '模型列表刷新失败',
  modelCatalogRefreshAnomaly: '模型列表刷新完成，但检测到目录异常',
  modelCatalogStatus: '目录状态',
  modelCatalogStatusReady: '可用',
  modelCatalogStatusNeedsInitialization: '需要初始化',
  modelCatalogFirstUseBanner: '您是初次使用，请先初始化模型列表',
  modelCatalogModelCount: '可用模型数',
  modelCatalogCatalogUpdatedAt: '目录更新时间',
  modelCatalogScheduleTitle: '自动刷新',
  modelCatalogScheduleDescription: '配置后台定时更新模型目录的计划。',
  modelCatalogScheduleEnabled: '启用自动刷新',
  modelCatalogScheduleMode: '刷新频率',
  modelCatalogScheduleDaily: '每天固定时间',
  modelCatalogScheduleDays: '每隔 X 天',
  modelCatalogScheduleWeeks: '每隔 X 周',
  modelCatalogScheduleTime: '刷新时间',
  modelCatalogScheduleInterval: '间隔值',
  modelCatalogScheduleSaved: '自动刷新设置已保存',
  modelCatalogLastRefreshAt: '上次刷新时间',
  modelCatalogNextRefreshAt: '下次刷新时间',
  modelCatalogAnomalyBanner: '模型列表获取异常，请检查 provider 配置、网络或等待规则更新',
  modelCatalogAnomalyHelp: '建议检查 provider 配置、网络连通性，或等待过滤规则更新后再重试。',
  modelCatalogAnomalyUpdatedAt: '异常更新时间',
  modelCatalogRetry: '重试',
  modelCatalogViewDetails: '查看详情',
  modelCatalogDetailsTitle: '模型目录异常报告',

  // Toast messages
  toastConfigSaved: '配置已保存',
  toastNotConfigured: '尚未配置',
  toastMissingRolesForTernionFull: '当前已选择ternion 归因+实现，请配置缺失的角色模型：{roles}',

  // Footer
  footerApiDocs: 'API 文档',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: '语言',

  // Observability Panel
  logsTitle: '实时日志',
  logsDescription: '后端处理日志实时流',
  logsConnecting: '连接中...',
  logsConnected: '已连接',
  logsDisconnected: '已断开',
  logsClear: '清空',
  logsAutoScroll: '自动滚动',
  logsNoLogs: '暂无日志',
  logsDownload: '导出',
  logsDownloading: '导出中...',
  logsDownloadSuccess: '日志导出成功',
  logsDownloadError: '日志导出失败',
  logsDownloadedTo: '已保存至',
  logsEntriesCount: '条记录',
  logsOpenFile: '在文件管理器中显示',
  logsDismiss: '关闭',

  // Settings Dropdown
  settingsTitle: '设置',
  settingsTheme: '主题',
  settingsThemeLight: '明亮',
  settingsThemeDark: '暗色',
  settingsThemeSystem: '跟随系统',
  settingsLanguage: '语言',
  settingsLanguageAuto: '自动',
  settingsConfigLabel: '配置文件',
  settingsConfigRestoreHint: '如损坏，可从备份恢复',

  // Execution Mode Selector
  execModeTitle: '推理方案选择',
  execModeDescription: '选择 Ternion 分析报告确认后的执行方式',
  execModeRecommended: '推荐',
  execModeCursorTitle: 'Ternion 问题归因 + Cursor 代码实现',
  execModeTernionTitle: 'Ternion 问题归因 + 代码实现',
  execModePros: '✓ 优势',
  execModeCons: '✗ 劣势',
  execModeCursorPro1: '成本更低，仅消耗问题归因阶段的 token',
  execModeCursorPro2: 'Cursor 原生代码实现体验',
  execModeCursorPro3: '可随时切换至其他 Cursor 模型',
  execModeCursorCon1: '无代码可用性及安全性审查',
  execModeCursorCon2: '代码质量取决于 Cursor 模型',
  execModeTernionPro1: 'Ternion Agent 实现代码编写及代码审查完整工作流',
  execModeTernionPro2: '审稿人做代码可用性及安全性审查',
  execModeTernionPro3: '更高的代码质量',
  execModeTernionCon1: '成本更高，完整流程消耗更多 token',
  execModeTernionCon2: '响应时间更长',
  execModeSave: '保存',
  execModeSaving: '保存中...',
  execModeDisabledHint: 'Cursor 实现代码，无需配置此角色',
};

const ES: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'Centro de Configuración de Pasarela Multi-Modelo',
  llmKeysEnabled: 'Clave(s) LLM habilitada(s)',
  lightMode: 'Cambiar a modo claro',
  darkMode: 'Cambiar a modo oscuro',

  // Tabs
  tabConfig: 'Config',
  tabPorts: 'Puertos',
  tabUsage: 'Uso',
  tabLogs: 'Registros',

  // Status Bar
  statusAddApiKey: 'Por favor agregue al menos una clave API',
  statusApiKeyAdded: 'Clave API agregada',
  statusConfigArbiter: 'Por favor configure el modelo Árbitro',
  statusConfigWriter: 'Por favor configure el modelo Escritor',
  statusConfigReviewer: 'Por favor configure el modelo Revisor',
  statusArbiterConfigured: 'Árbitro',
  statusWriterConfigured: 'Escritor',
  statusReviewerConfigured: 'Revisor',

  // API Key Manager
  apiKeyTitle: 'Gestión de Claves API',
  apiKeyDescription: 'Agregue claves API de proveedores LLM para habilitar modelos',
  apiKeyStorageNote: '(Las claves guardadas se almacenan en: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'Mejor igual que la consola API',
  apiKeyNameLabel: 'Nombre de Clave',
  apiKeyLabel: 'Clave API',
  apiKeyTestAndSave: 'Probar y Guardar',
  apiKeyTesting: 'Probando...',
  apiKeySaved: 'Clave API guardada',
  apiKeyDeleted: 'Clave API eliminada',
  apiKeySelected: 'Clave API seleccionada',
  apiKeyGetKey: 'Obtener Clave',
  enabled: 'Habilitado',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Clave API de Google AI Studio',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Clave API de Anthropic',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'Clave API de OpenAI',
  apiKeyDuplicate: 'Esta clave API ya existe',

  // Role Model Config
  roleConfigTitle: 'Configuración de Modelos por Rol',
  roleConfigDescription: 'Seleccione serie de modelo y modelo específico para cada rol',
  roleConfigHint: '(Por favor agregue una clave API arriba para habilitar modelos)',
  ternionAName: 'Ternion A',
  ternionADesc: 'Primer miembro del consejo para análisis paralelo',
  ternionBName: 'Ternion B',
  ternionBDesc: 'Segundo miembro del consejo para análisis paralelo',
  ternionCName: 'Ternion C',
  ternionCDesc: 'Tercer miembro del consejo para análisis paralelo',
  arbiterName: 'Árbitro',
  arbiterDesc: 'Sintetizar opiniones, resolver conflictos',
  writerName: 'Escritor',
  writerDesc: 'Generar código final basado en análisis',
  reviewerName: 'Revisor',
  reviewerDesc: 'Revisar seguridad y lógica del código',
  modelSeries: 'Serie de Modelo',
  modelName: 'Nombre de Modelo',
  selectModel: 'Seleccionar modelo...',
  selectSeries: 'Seleccionar serie...',
  currentConfig: 'Configuración actual',
  notConfigured: 'No configurado',
  apiKeyAdded: 'Clave API agregada',
  saveChanges: 'Guardar Cambios',
  saving: 'Guardando...',
  noApiKey: '(Sin Clave API)',
  roleNotSaved: 'Modelo de rol aún no guardado',
  roleSelectionPending: 'Modelo de rol seleccionado {model}, aún no guardado',
  unsavedLabel: 'no guardado',
  roleConfigValidatingModel: 'Validando modelo...',
  roleConfigRemovedSelectionHint: 'Algunos modelos seleccionados fueron eliminados del catálogo actualizado. Vuelva a seleccionarlos.',
  roleConfigRefreshSuggested: 'El catálogo de modelos puede estar desactualizado. Intente actualizar la lista de modelos para resolver este problema.',
  roleConfigProModelWarningPrefix: 'OpenAI indica que ',
  roleConfigProModelWarningLinkLabel: 'los modelos Pro',
  roleConfigProModelWarningSuffix:
    ' son los más lentos, pueden tardar varios minutos y cuestan más. Elija con cuidado.',

  // Status Bar - Ternion
  statusConfigTernionA: 'Configure modelo de Ternion A',
  statusConfigTernionB: 'Configure modelo de Ternion B',
  statusConfigTernionC: 'Configure modelo de Ternion C',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: 'Configuración de Presupuesto',
  budgetDescription: 'Se recomienda establecer límite mensual y umbral de alerta',
  monthlyLimit: 'Límite Mensual (USD)',
  alertThreshold: 'Umbral de Alerta',
  budgetLimitNote: 'Rechazar nuevas solicitudes al alcanzar esta cantidad',
  budgetThresholdNote: 'Mostrar advertencia al alcanzar este porcentaje del presupuesto',
  preview: 'Vista Previa',
  monthlyLimitLabel: 'Límite mensual',
  alertTriggerLabel: 'Monto de activación de alerta',
  budgetSaved: 'Configuración de presupuesto guardada',

  // Ports Settings
  portsTitle: 'Configuración de Puertos',
  portsDescription:
    'La información de acceso público se muestra arriba. En despliegues locales, los puertos del backend y de la Web UI pueden cambiarse desde la configuración avanzada cuando sea necesario.',
  portsBackend: 'Cambiar Puerto API Backend de Ternion',
  portsWeb: 'Cambiar Puerto del Panel Web UI',
  portsBackendLabel: 'Backend',
  portsCurrentBackend: 'Puerto API Backend Actual de Ternion',
  portsCurrentWeb: 'Puerto actual del panel Web UI',
  portsAdvancedSettings: 'Configuración avanzada de puertos',
  portsAdvancedDescription:
    'Solo los usuarios avanzados deberían cambiar los puertos del backend o de la Web UI, normalmente para resolver conflictos de puertos locales.',
  portsShowAdvancedSettings: 'Mostrar configuración avanzada',
  portsHideAdvancedSettings: 'Ocultar configuración avanzada',
  portsCloudRunManaged:
    'Este servicio se está ejecutando en Cloud Run. Los puertos del contenedor están gestionados por la plataforma y no pueden cambiarse aquí.',
  portsWarning: 'Los cambios de puerto requieren reinicio manual del servidor',
  portsRestartNote: 'Después de guardar, reinicie el servidor con la nueva configuración',
  portsSaved: 'Configuración de puerto guardada',
  portsInvalid: 'Número de puerto inválido (1024-65535)',
  portsDuplicate: 'Los puertos del backend y de la Web UI deben ser diferentes.',
  portsConfirmChangeTitle: '¿Confirmar cambio de puerto?',
  portsConfirmChangeDesc: 'Los cambios de puerto surten efecto después del reinicio manual. ¿Guardar cambios?',
  portsConfirmBtn: 'Confirmar',
  portsCancelBtn: 'Cancelar',
  portsChangedToast:
    'Puertos actualizados. Backend: {backend}, Web UI: {web}. Reinicie el servicio ternion manualmente.',
  publicAccessTitle: 'Acceso Público',
  publicAccessDescription:
    'Vea la URL pública detectada, copie la URL base de Cursor y use un valor manual de respaldo solo cuando la detección automática no esté disponible.',
  publicAccessDeploymentEnvironment: 'Despliegue',
  publicAccessDeploymentEnvironmentLocal: 'Despliegue local',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: 'URL pública detectada',
  publicAccessDetectedPublicUrlUnavailable: 'No detectada automáticamente',
  publicAccessManualFallbackTitle: 'Respaldo manual',
  publicAccessManualFallbackDescription:
    'Si la detección automática no está disponible, puede guardar aquí una URL HTTPS pública para seguir mostrándola y copiándola en otros dispositivos.',
  publicAccessManualFallbackHint:
    'Esto no inicia ni configura ningún túnel. Solo guarda un valor de respaldo para mostrarlo y copiarlo.',
  publicAccessDocsTitle: 'Guías de acceso público',
  publicAccessDocsDescription:
    'Si todavía no se detecta ninguna URL pública, use estas guías para configurar un túnel local o revisar la documentación de GitHub.',
  publicAccessDocsLocalTunnel: 'Guía de túnel local',
  publicAccessDocsCloudRun: 'Guía de despliegue en Cloud Run',
  publicAccessDocsGitHub: 'Documentación de GitHub',
  publicAccessMode: 'Modo de despliegue',
  publicAccessModeNone: 'Ninguno',
  publicAccessModeLocalTunnel: 'Túnel local',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: 'Personalizado',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: 'URL pública configurada',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: 'Origen de la URL efectiva',
  publicAccessSourceConfig: 'Valor configurado',
  publicAccessSourceRequestOrigin: 'Detectada desde la solicitud actual',
  publicAccessSourceNgrokApi: 'Detectada desde la API local de ngrok',
  publicAccessSourceNone: 'No hay URL pública disponible',
  publicAccessCursorHint: 'Use la URL raíz pública HTTPS en Cursor. No agregue `/v1`.',
  publicAccessCursorGuide:
    'Copie la URL anterior en Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL, actívelo, abra "OpenAI API Key" e introduzca cualquier carácter. Active "Add Custom Model" en "Models" e introduzca "ternion-team" para empezar a usar ternion.',
  publicAccessAutoDetectedNote:
    'Esta URL se detectó automáticamente a partir de la solicitud pública actual o de la API local de ngrok, lo que resulta útil para despliegues en Cloud Run, detrás de un proxy inverso o con túneles locales.',
  publicAccessCopy: 'Copiar',
  publicAccessCopied: 'La URL base de Cursor se copió',
  publicAccessCopyFailed: 'No se pudo copiar la URL base de Cursor',
  publicAccessTokenLabel: 'Token de acceso',
  publicAccessTokenHint: 'Obligatorio para solicitudes que llegan por un túnel público',
  publicAccessTokenDescription:
    'Pega este token en Cursor como la OpenAI API Key. El acceso remoto al panel también lo requiere; las solicitudes locales no.',
  accessTokenGateTitle: 'Se requiere token de acceso',
  accessTokenGateDescription:
    'Este panel se está abriendo a través de un túnel público. Introduce el token de acceso mostrado en el banner de inicio de Ternion (o cópialo desde una sesión local del panel).',
  accessTokenGatePlaceholder: 'Pega el token de acceso',
  accessTokenGateSubmit: 'Continuar',
  publicAccessSaved: 'La configuración de acceso público se guardó',
  publicAccessUnavailable: 'No se puede cargar la configuración de acceso público en este momento.',
  publicAccessConfiguredToast:
    'El acceso público está disponible. Abra la pestaña de Puertos para copiar la URL base de Cursor.',
  publicAccessIntroTitle: 'Se requiere una URL HTTPS pública',
  publicAccessIntroBody:
    'Override OpenAI Base URL de Cursor no acepta localhost ni otras direcciones solo locales.\nPara conectar Cursor con Ternion, exponga este servicio mediante una URL HTTPS pública.',
  publicAccessIntroOk: 'Aceptar',
  publicAccessIntroGuide: 'Cómo configurarlo',
  publicAccessGuideTitle: 'Cómo configurar el acceso público',
  publicAccessGuideBody:
    'Ejemplo con ngrok:\n1. Instale ngrok e inicie sesión en su cuenta.\n2. Ejecute `ngrok http 9110` en la máquina donde se está ejecutando Ternion.\n3. Copie la URL raíz HTTPS pública generada.\n4. Pegue esa URL raíz en Override OpenAI Base URL de Cursor.\n5. No agregue `/v1`.\n\nSi despliega Ternion en Cloud Run, también puede usar directamente el origen HTTPS público del servicio.',
  publicAccessGuideClose: 'Cerrar',

  // Usage Dashboard
  usageTitle: '📊 Estadísticas de Uso',
  usageMonth: 'Mes',
  usageTotal: 'Costo Total',
  usageRemaining: 'Restante',
  usageRequests: 'Solicitudes',
  usageByProvider: 'Costo por Proveedor',
  usageNoData: 'Sin datos de uso',
  usageDisclaimer: 'Los datos de uso mostrados aquí son estimados y pueden no reflejar la facturación real. Consulte el panel de facturación de su proveedor de API para obtener costos precisos.',
  usageDontRemind: 'No volver a mostrar',
  usageDailyUsage: 'Uso Diario',
  usageMonthlyUsage: 'Uso Mensual',
  usageAllProviders: 'Todos los proveedores',
  usageAllTokens: 'Todos los Tokens',
  usageCost: 'Costo',
  usageInputTokens: 'Tokens de Entrada',
  usageOutputTokens: 'Tokens de Salida',
  usageThoughtsTokens: 'Tokens de Pensamiento',
  usagePercentage: 'Monto de Uso',
  usageModifyBudget: 'Modificar',
  usageCurrentBudget: 'Límite de presupuesto actual',
  usageChangeTo: 'cambiar a',
  usageConfirm: 'Confirmar',
  loading: 'Cargando...',

  // Common UI
  unnamed: 'Sin nombre',
  delete: 'Eliminar',
  toggleVisibility: 'Alternar visibilidad',
  confirmDeleteApiKey: '¿Eliminar esta clave API?',

  // API Response Codes
  code_SUCCESS: 'Conectado exitosamente',
  code_AUTH_ERROR: 'Clave API inválida',
  code_CONNECTION_ERROR: 'Conexión fallida',
  code_UNKNOWN_ERROR: 'Error desconocido',
  code_INVALID_PROVIDER: 'Proveedor inválido',
  code_PROVIDER_NOT_FOUND: 'Proveedor no encontrado',
  code_API_KEY_NOT_FOUND: 'Clave API no encontrada',
  code_API_KEY_DUPLICATE: 'Esta clave API ya existe',
  code_PROVIDER_NOT_ENABLED: 'Proveedor no habilitado',
  code_MODEL_NOT_AVAILABLE: 'Modelo no disponible',
  code_MODEL_UNAVAILABLE: 'El modelo seleccionado ya no está disponible en el proveedor',
  code_MODEL_PROBE_AUTH_ERROR: 'La validación del modelo falló porque la clave API del proveedor no es válida o no tiene autorización',
  code_MODEL_PROBE_TIMEOUT: 'La validación del modelo agotó el tiempo de espera, vuelva a intentarlo',
  code_MODEL_PROBE_CONNECTION_ERROR: 'La validación del modelo falló porque no se pudo conectar con el proveedor',
  code_INVALID_BUDGET_LIMIT: 'Límite de presupuesto inválido',
  code_INVALID_BUDGET_THRESHOLD: 'Umbral de presupuesto inválido',
  code_BUDGET_EXCEEDED: 'Presupuesto mensual excedido',
  code_BUDGET_WARNING: 'Acercándose al límite de presupuesto',
  code_STREAM_INTERRUPTED: 'Transmisión interrumpida, por favor reintente',
  code_ROLES_INCOMPLETE: 'Configure todos los roles antes de guardar',
  code_ROLES_INCOMPLETE_SUFFIX: ' (faltan: {roles})',
  code_MODEL_CATALOG_REFRESH_FAILED: 'L\'actualisation du catalogue de modeles a echoue',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'Rapport d\'anomalie du catalogue introuvable',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Mode d\'actualisation automatique invalide',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Heure d\'actualisation automatique invalide',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: 'Intervalle d\'actualisation automatique invalide',
  code_INVALID_PUBLIC_ACCESS_MODE: 'Modo de acceso público no válido',
  code_INVALID_PUBLIC_BASE_URL: 'URL HTTPS pública no válida',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Error desconocido',
  successConnected: 'Conectado exitosamente',
  modelCatalogTitle: 'Catalogue de modeles',
  modelCatalogDescription: 'Initialisez, actualisez et planifiez les mises a jour du catalogue de modeles LiteLLM.',
  modelCatalogInitialize: 'Initialiser la liste des modeles',
  modelCatalogInitializing: 'Initialisation...',
  modelCatalogRefreshNow: 'Actualiser la liste des modeles',
  modelCatalogRefreshing: 'Actualisation...',
  modelCatalogInitSuccess: 'Le catalogue de modeles a ete initialise avec succes',
  modelCatalogInitFailed: 'Impossible d\'initialiser le catalogue de modeles',
  modelCatalogInitAnomaly: 'Le catalogue de modeles a ete initialise, mais une anomalie a ete detectee',
  modelCatalogRefreshSuccess: 'Le catalogue de modeles a ete actualise avec succes',
  modelCatalogRefreshFailed: 'Impossible d\'actualiser le catalogue de modeles',
  modelCatalogRefreshAnomaly: 'L\'actualisation du catalogue est terminee, mais une anomalie a ete detectee',
  modelCatalogStatus: 'Etat du catalogue',
  modelCatalogStatusReady: 'Pret',
  modelCatalogStatusNeedsInitialization: 'Initialisation requise',
  modelCatalogFirstUseBanner: 'Première utilisation de Ternion ? Veuillez initialiser la liste des modèles.',
  modelCatalogModelCount: 'Modeles disponibles',
  modelCatalogCatalogUpdatedAt: 'Catalogue mis a jour le',
  modelCatalogScheduleTitle: 'Actualisation automatique',
  modelCatalogScheduleDescription: 'Configurez des actualisations periodiques en arriere-plan pour le catalogue de modeles.',
  modelCatalogScheduleEnabled: 'Activer l\'actualisation automatique',
  modelCatalogScheduleMode: 'Frequence d\'actualisation',
  modelCatalogScheduleDaily: 'Chaque jour',
  modelCatalogScheduleDays: 'Tous les X jours',
  modelCatalogScheduleWeeks: 'Toutes les X semaines',
  modelCatalogScheduleTime: 'Heure de la journee',
  modelCatalogScheduleInterval: 'Valeur de l\'intervalle',
  modelCatalogScheduleSaved: 'Parametres d\'actualisation automatique enregistres',
  modelCatalogLastRefreshAt: 'Derniere actualisation',
  modelCatalogNextRefreshAt: 'Prochaine actualisation',
  modelCatalogAnomalyBanner: 'Une anomalie du catalogue de modeles a ete detectee',
  modelCatalogAnomalyHelp: 'Verifiez la configuration du fournisseur, la connectivite reseau ou attendez la mise a jour des regles de filtrage.',
  modelCatalogAnomalyUpdatedAt: 'Anomalie mise a jour le',
  modelCatalogRetry: 'Reessayer',
  modelCatalogViewDetails: 'Voir les details',
  modelCatalogDetailsTitle: 'Rapport d\'anomalie du catalogue',

  // Toast messages
  toastConfigSaved: 'Configuración guardada',
  toastNotConfigured: 'no configurado',
  toastMissingRolesForTernionFull: 'Modo Ternion Completo seleccionado. Por favor, configure los modelos faltantes: {roles}',

  // Footer
  footerApiDocs: 'Documentación API',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: 'Idioma',

  // Observability Panel
  logsTitle: 'Registros en Vivo',
  logsDescription: 'Registros de procesamiento del backend en tiempo real',
  logsConnecting: 'Conectando...',
  logsConnected: 'Conectado',
  logsDisconnected: 'Desconectado',
  logsClear: 'Limpiar',
  logsAutoScroll: 'Auto-desplazamiento',
  logsNoLogs: 'Sin registros aún',
  logsDownload: 'Exportar',
  logsDownloading: 'Exportando...',
  logsDownloadSuccess: 'Registros exportados exitosamente',
  logsDownloadError: 'Error al exportar registros',
  logsDownloadedTo: 'Guardado en',
  logsEntriesCount: 'entradas',
  logsOpenFile: 'Mostrar en Administrador de archivos',
  logsDismiss: 'Cerrar',

  // Settings Dropdown
  settingsTitle: 'Configuración',
  settingsTheme: 'Tema',
  settingsThemeLight: 'Claro',
  settingsThemeDark: 'Oscuro',
  settingsThemeSystem: 'Sistema',
  settingsLanguage: 'Idioma',
  settingsLanguageAuto: 'Auto',
  settingsConfigLabel: 'Configuración',
  settingsConfigRestoreHint: 'Si está dañado, restaurar desde',

  // Execution Mode Selector
  execModeTitle: 'Modo de Ejecución',
  execModeDescription: 'Seleccione el modo de ejecución después de confirmar el análisis de Ternion',
  execModeRecommended: 'Recomendado',
  execModeCursorTitle: 'Análisis de Causa Raíz Ternion + Implementación Cursor',
  execModeTernionTitle: 'Análisis de Causa Raíz Ternion + Implementación de Código',
  execModePros: '✓ Ventajas',
  execModeCons: '✗ Desventajas',
  execModeCursorPro1: 'Menor costo, solo tokens de fase de análisis consumidos',
  execModeCursorPro2: 'Experiencia nativa de implementación de código Cursor',
  execModeCursorPro3: 'Cambiar a otros modelos Cursor en cualquier momento',
  execModeCursorCon1: 'Sin revisión de usabilidad y seguridad del código',
  execModeCursorCon2: 'Calidad del código depende del modelo Cursor',
  execModeTernionPro1: 'Flujo completo con escritura y revisión de código por Ternion Agent',
  execModeTernionPro2: 'Revisor realiza revisión de usabilidad y seguridad del código',
  execModeTernionPro3: 'Mayor calidad del código',
  execModeTernionCon1: 'Mayor costo, flujo completo necesita más tokens',
  execModeTernionCon2: 'Mayor tiempo de respuesta',
  execModeSave: 'Guardar',
  execModeSaving: 'Guardando...',
  execModeDisabledHint: 'Cursor genera el código, no se necesita configuración',
  statusExecModeNotSelected: 'Modo de ejecución no seleccionado',
  statusExecModeSelected: 'Modo de ejecución',
};

const FR: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'Centre de Configuration de Passerelle Multi-Modèles',
  llmKeysEnabled: 'Clé(s) LLM activée(s)',
  lightMode: 'Passer en mode clair',
  darkMode: 'Passer en mode sombre',

  // Tabs
  tabConfig: 'Config',
  tabPorts: 'Ports',
  tabUsage: 'Utilisation',
  tabLogs: 'Journaux',

  // Status Bar
  statusAddApiKey: 'Veuillez ajouter au moins une clé API',
  statusApiKeyAdded: 'Clé API ajoutée',
  statusConfigArbiter: 'Veuillez configurer le modèle Arbitre',
  statusConfigWriter: 'Veuillez configurer le modèle Rédacteur',
  statusConfigReviewer: 'Veuillez configurer le modèle Réviseur',
  statusArbiterConfigured: 'Arbitre',
  statusWriterConfigured: 'Rédacteur',
  statusReviewerConfigured: 'Réviseur',

  // API Key Manager
  apiKeyTitle: 'Gestion des Clés API',
  apiKeyDescription: 'Ajoutez des clés API de fournisseurs LLM pour activer les modèles',
  apiKeyStorageNote: '(Les clés enregistrées sont stockées dans : ~/.ternion/config.json)',
  apiKeyPlaceholder: 'De préférence identique à la console API',
  apiKeyNameLabel: 'Nom de Clé',
  apiKeyLabel: 'Clé API',
  apiKeyTestAndSave: 'Tester et Sauvegarder',
  apiKeyTesting: 'Test en cours...',
  apiKeySaved: 'Clé API sauvegardée',
  apiKeyDeleted: 'Clé API supprimée',
  apiKeySelected: 'Clé API sélectionnée',
  apiKeyGetKey: 'Obtenir une Clé',
  enabled: 'Activé',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Clé API Google AI Studio',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Clé API Anthropic',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'Clé API OpenAI',
  apiKeyDuplicate: 'Cette clé API existe déjà',

  // Role Model Config
  roleConfigTitle: 'Configuration des Modèles par Rôle',
  roleConfigDescription: 'Sélectionnez la série et le modèle spécifique pour chaque rôle',
  roleConfigHint: '(Veuillez ajouter une clé API ci-dessus pour activer les modèles)',
  ternionAName: 'Ternion A',
  ternionADesc: 'Premier membre du conseil pour analyse parallèle',
  ternionBName: 'Ternion B',
  ternionBDesc: 'Deuxième membre du conseil pour analyse parallèle',
  ternionCName: 'Ternion C',
  ternionCDesc: 'Troisième membre du conseil pour analyse parallèle',
  arbiterName: 'Arbitre',
  arbiterDesc: 'Synthétiser les opinions, résoudre les conflits',
  writerName: 'Rédacteur',
  writerDesc: 'Générer le code final basé sur l\'analyse',
  reviewerName: 'Réviseur',
  reviewerDesc: 'Vérifier la sécurité et la logique du code',
  modelSeries: 'Série de Modèle',
  modelName: 'Nom du Modèle',
  selectModel: 'Sélectionner un modèle...',
  selectSeries: 'Sélectionner une série...',
  currentConfig: 'Configuration actuelle',
  notConfigured: 'Non configuré',
  apiKeyAdded: 'Clé API ajoutée',
  saveChanges: 'Sauvegarder',
  saving: 'Sauvegarde...',
  noApiKey: '(Pas de Clé API)',
  roleNotSaved: 'Modèle de rôle non enregistré',
  roleSelectionPending: 'Modèle de rôle sélectionné {model}, non enregistré',
  unsavedLabel: 'non enregistré',
  roleConfigValidatingModel: 'Validation du modèle...',
  roleConfigRemovedSelectionHint: 'Certains modèles sélectionnés ont été retirés du catalogue actualisé. Veuillez les sélectionner à nouveau.',
  roleConfigRefreshSuggested: 'Le catalogue de modèles est peut-être obsolète. Essayez d\'actualiser la liste des modèles pour résoudre ce problème.',
  roleConfigProModelWarningPrefix: 'OpenAI indique que ',
  roleConfigProModelWarningLinkLabel: 'les modèles Pro',
  roleConfigProModelWarningSuffix:
    ' sont les plus lents, peuvent prendre plusieurs minutes et coûtent plus cher. Choisissez avec prudence.',

  // Status Bar - Ternion
  statusConfigTernionA: 'Configurez le modèle Ternion A',
  statusConfigTernionB: 'Configurez le modèle Ternion B',
  statusConfigTernionC: 'Configurez le modèle Ternion C',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: 'Paramètres du Budget',
  budgetDescription: 'Il est recommandé de définir une limite mensuelle et un seuil d\'alerte',
  monthlyLimit: 'Limite Mensuelle (USD)',
  alertThreshold: 'Seuil d\'Alerte',
  budgetLimitNote: 'Refuser les nouvelles demandes après avoir atteint ce montant',
  budgetThresholdNote: 'Afficher un avertissement lorsque ce pourcentage du budget est atteint',
  preview: 'Aperçu',
  monthlyLimitLabel: 'Limite mensuelle',
  alertTriggerLabel: 'Montant de déclenchement d\'alerte',
  budgetSaved: 'Paramètres du budget sauvegardés',

  // Ports Settings
  portsTitle: 'Configuration des Ports',
  portsDescription:
    'Les informations d’accès public sont affichées ci-dessus. En déploiement local, les ports backend et Web UI peuvent être modifiés dans les paramètres avancés en cas de besoin.',
  portsBackend: 'Modifier le Port API Backend Ternion',
  portsWeb: 'Modifier le Port du panneau Web UI',
  portsBackendLabel: 'Backend',
  portsCurrentBackend: 'Port API Backend Ternion Actuel',
  portsCurrentWeb: 'Port actuel du panneau Web UI',
  portsAdvancedSettings: 'Paramètres avancés des ports',
  portsAdvancedDescription:
    'Seuls les utilisateurs avancés devraient modifier les ports backend ou Web UI, généralement pour résoudre un conflit de ports local.',
  portsShowAdvancedSettings: 'Afficher les paramètres avancés',
  portsHideAdvancedSettings: 'Masquer les paramètres avancés',
  portsCloudRunManaged:
    'Ce service s’exécute sur Cloud Run. Les ports du conteneur sont gérés par la plateforme et ne peuvent pas être modifiés ici.',
  portsWarning: 'Les modifications de port nécessitent un redémarrage manuel du serveur',
  portsRestartNote: 'Après la sauvegarde, redémarrez le serveur avec la nouvelle configuration',
  portsSaved: 'Configuration du port sauvegardée',
  portsInvalid: 'Numéro de port invalide (1024-65535)',
  portsDuplicate: 'Les ports backend et Web UI doivent être différents.',
  portsConfirmChangeTitle: 'Confirmer le changement de port ?',
  portsConfirmChangeDesc: 'Les changements de port prennent effet après un redémarrage manuel. Enregistrer les modifications ?',
  portsConfirmBtn: 'Confirmer',
  portsCancelBtn: 'Annuler',
  portsChangedToast:
    'Ports mis à jour. Backend : {backend}, Web UI : {web}. Veuillez redémarrer le service ternion manuellement.',
  publicAccessTitle: 'Accès Public',
  publicAccessDescription:
    'Affichez l’URL publique détectée, copiez l’URL de base Cursor et utilisez un secours manuel uniquement lorsque la détection automatique est indisponible.',
  publicAccessDeploymentEnvironment: 'Déploiement',
  publicAccessDeploymentEnvironmentLocal: 'Déploiement local',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: 'URL publique détectée',
  publicAccessDetectedPublicUrlUnavailable: 'Non détectée automatiquement',
  publicAccessManualFallbackTitle: 'Secours manuel',
  publicAccessManualFallbackDescription:
    'Si la détection automatique n’est pas disponible, vous pouvez enregistrer ici une URL HTTPS publique afin qu’elle puisse encore être affichée et copiée sur d’autres appareils.',
  publicAccessManualFallbackHint:
    'Cela ne démarre ni ne configure aucun tunnel. Cela enregistre seulement une valeur de secours pour l’affichage et la copie.',
  publicAccessDocsTitle: 'Guides d’accès public',
  publicAccessDocsDescription:
    'Si aucune URL publique n’est encore détectée, utilisez ces guides pour configurer un tunnel local ou consulter la documentation GitHub.',
  publicAccessDocsLocalTunnel: 'Guide du tunnel local',
  publicAccessDocsCloudRun: 'Guide de déploiement Cloud Run',
  publicAccessDocsGitHub: 'Documentation GitHub',
  publicAccessMode: 'Mode de déploiement',
  publicAccessModeNone: 'Aucun',
  publicAccessModeLocalTunnel: 'Tunnel local',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: 'Personnalisé',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: 'URL publique configurée',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: 'Source de l’URL effective',
  publicAccessSourceConfig: 'Valeur configurée',
  publicAccessSourceRequestOrigin: 'Détectée depuis la requête actuelle',
  publicAccessSourceNgrokApi: 'Détectée depuis l’API locale ngrok',
  publicAccessSourceNone: 'Aucune URL publique disponible',
  publicAccessCursorHint: 'Utilisez l’URL racine HTTPS publique dans Cursor. N’ajoutez pas `/v1`.',
  publicAccessCursorGuide:
    'Veuillez copier l\'URL ci-dessus dans Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL, activez-le, ouvrez "OpenAI API Key" et saisissez n\'importe quel caractère. Activez "Add Custom Model" dans "Models" et saisissez "ternion-team" pour commencer à utiliser ternion !',
  publicAccessAutoDetectedNote:
    'Cette URL a été détectée automatiquement à partir de la requête publique actuelle ou de l’API locale ngrok, ce qui est utile pour Cloud Run, les déploiements derrière un proxy inverse et les tunnels locaux.',
  publicAccessCopy: 'Copier',
  publicAccessCopied: 'L’URL de base Cursor a été copiée',
  publicAccessCopyFailed: 'Impossible de copier l’URL de base Cursor',
  publicAccessTokenLabel: 'Jeton d’accès',
  publicAccessTokenHint: 'Requis pour les requêtes arrivant via un tunnel public',
  publicAccessTokenDescription:
    'Collez ce jeton dans Cursor comme OpenAI API Key. L’accès distant au panneau le requiert aussi ; les requêtes locales non.',
  accessTokenGateTitle: 'Jeton d’accès requis',
  accessTokenGateDescription:
    'Ce panneau est ouvert via un tunnel public. Saisissez le jeton d’accès affiché dans la bannière de démarrage de Ternion (ou copiez-le depuis une session locale du panneau).',
  accessTokenGatePlaceholder: 'Collez le jeton d’accès',
  accessTokenGateSubmit: 'Continuer',
  publicAccessSaved: 'Les paramètres d’accès public ont été enregistrés',
  publicAccessUnavailable: 'Impossible de charger les paramètres d’accès public pour le moment.',
  publicAccessConfiguredToast:
    'Un accès public est disponible. Ouvrez l’onglet Ports pour copier l’URL de base Cursor.',
  publicAccessIntroTitle: 'Une URL HTTPS publique est requise',
  publicAccessIntroBody:
    'Override OpenAI Base URL de Cursor n’accepte pas localhost ni les autres adresses uniquement locales.\nPour connecter Cursor à Ternion, exposez ce service via une URL HTTPS publique.',
  publicAccessIntroOk: 'OK',
  publicAccessIntroGuide: 'Méthode de configuration',
  publicAccessGuideTitle: 'Comment configurer l’accès public',
  publicAccessGuideBody:
    'Exemple avec ngrok :\n1. Installez ngrok et connectez-vous à votre compte.\n2. Exécutez `ngrok http 9110` sur la machine où Ternion s’exécute.\n3. Copiez l’URL racine HTTPS publique générée.\n4. Collez cette URL racine dans Override OpenAI Base URL de Cursor.\n5. N’ajoutez pas `/v1`.\n\nSi vous déployez Ternion sur Cloud Run, vous pouvez aussi utiliser directement l’origine HTTPS publique du service.',
  publicAccessGuideClose: 'Fermer',

  // Usage Dashboard
  usageTitle: '📊 Statistiques d\'Utilisation',
  usageMonth: 'Mois',
  usageTotal: 'Coût Total',
  usageRemaining: 'Restant',
  usageRequests: 'Requêtes',
  usageByProvider: 'Coût par Fournisseur',
  usageNoData: 'Aucune donnée d\'utilisation',
  usageDisclaimer: 'Les données d\'utilisation affichées ici sont estimées et peuvent ne pas refléter la facturation réelle. Veuillez consulter le tableau de bord de facturation de votre fournisseur d\'API pour des coûts précis.',
  usageDontRemind: 'Ne plus afficher',
  usageDailyUsage: 'Utilisation Quotidienne',
  usageMonthlyUsage: 'Utilisation Mensuelle',
  usageAllProviders: 'Tous les fournisseurs',
  usageAllTokens: 'Tous les Tokens',
  usageCost: 'Coût',
  usageInputTokens: 'Tokens d\'Entrée',
  usageOutputTokens: 'Tokens de Sortie',
  usageThoughtsTokens: 'Tokens de réflexion',
  usagePercentage: 'Montant d\'Utilisation',
  usageModifyBudget: 'Modifier',
  usageCurrentBudget: 'Limite de budget actuelle',
  usageChangeTo: 'changer en',
  usageConfirm: 'Confirmer',
  loading: 'Chargement...',

  // Common UI
  unnamed: 'Sans nom',
  delete: 'Supprimer',
  toggleVisibility: 'Basculer la visibilité',
  confirmDeleteApiKey: 'Supprimer cette clé API ?',

  // API Response Codes
  code_SUCCESS: 'Connecté avec succès',
  code_AUTH_ERROR: 'Clé API invalide',
  code_CONNECTION_ERROR: 'Échec de connexion',
  code_UNKNOWN_ERROR: 'Erreur inconnue',
  code_INVALID_PROVIDER: 'Fournisseur invalide',
  code_PROVIDER_NOT_FOUND: 'Fournisseur non trouvé',
  code_API_KEY_NOT_FOUND: 'Clé API non trouvée',
  code_API_KEY_DUPLICATE: 'Cette clé API existe déjà',
  code_PROVIDER_NOT_ENABLED: 'Fournisseur non activé',
  code_MODEL_NOT_AVAILABLE: 'Modèle non disponible',
  code_MODEL_UNAVAILABLE: 'Le modèle sélectionné n’est plus disponible chez le fournisseur',
  code_MODEL_PROBE_AUTH_ERROR: 'La validation du modèle a échoué car la clé API du fournisseur est invalide ou non autorisée',
  code_MODEL_PROBE_TIMEOUT: 'La validation du modèle a expiré, veuillez réessayer',
  code_MODEL_PROBE_CONNECTION_ERROR: 'La validation du modèle a échoué car le fournisseur est inaccessible',
  code_INVALID_BUDGET_LIMIT: 'Limite de budget invalide',
  code_INVALID_BUDGET_THRESHOLD: 'Seuil de budget invalide',
  code_BUDGET_EXCEEDED: 'Budget mensuel dépassé',
  code_BUDGET_WARNING: 'Approche de la limite de budget',
  code_STREAM_INTERRUPTED: 'Transmission interrompue, veuillez réessayer',
  code_ROLES_INCOMPLETE: 'Veuillez configurer tous les rôles avant d\'enregistrer',
  code_ROLES_INCOMPLETE_SUFFIX: ' (manquant: {roles})',
  code_MODEL_CATALOG_REFRESH_FAILED: 'Aktualisierung des Modellkatalogs fehlgeschlagen',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'Anomaliebericht zum Modellkatalog nicht gefunden',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Ungueltiger automatischer Aktualisierungsmodus',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Ungueltige automatische Aktualisierungszeit',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: 'Ungueltiges automatisches Aktualisierungsintervall',
  code_INVALID_PUBLIC_ACCESS_MODE: 'Mode d’accès public invalide',
  code_INVALID_PUBLIC_BASE_URL: 'URL HTTPS publique invalide',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Erreur inconnue',
  successConnected: 'Connecté avec succès',
  modelCatalogTitle: 'Modellkatalog',
  modelCatalogDescription: 'Initialisieren, aktualisieren und planen Sie Aktualisierungen des LiteLLM-Modellkatalogs.',
  modelCatalogInitialize: 'Modellliste initialisieren',
  modelCatalogInitializing: 'Initialisierung...',
  modelCatalogRefreshNow: 'Modellliste aktualisieren',
  modelCatalogRefreshing: 'Aktualisierung...',
  modelCatalogInitSuccess: 'Der Modellkatalog wurde erfolgreich initialisiert',
  modelCatalogInitFailed: 'Der Modellkatalog konnte nicht initialisiert werden',
  modelCatalogInitAnomaly: 'Der Modellkatalog wurde initialisiert, aber es wurde eine Anomalie erkannt',
  modelCatalogRefreshSuccess: 'Der Modellkatalog wurde erfolgreich aktualisiert',
  modelCatalogRefreshFailed: 'Der Modellkatalog konnte nicht aktualisiert werden',
  modelCatalogRefreshAnomaly: 'Die Aktualisierung des Modellkatalogs wurde abgeschlossen, aber es wurde eine Anomalie erkannt',
  modelCatalogStatus: 'Katalogstatus',
  modelCatalogStatusReady: 'Bereit',
  modelCatalogStatusNeedsInitialization: 'Initialisierung erforderlich',
  modelCatalogFirstUseBanner: 'Verwenden Sie Ternion zum ersten Mal? Bitte initialisieren Sie die Modellliste.',
  modelCatalogModelCount: 'Verfuegbare Modelle',
  modelCatalogCatalogUpdatedAt: 'Katalog aktualisiert am',
  modelCatalogScheduleTitle: 'Automatische Aktualisierung',
  modelCatalogScheduleDescription: 'Konfigurieren Sie periodische Hintergrundaktualisierungen fuer den Modellkatalog.',
  modelCatalogScheduleEnabled: 'Automatische Aktualisierung aktivieren',
  modelCatalogScheduleMode: 'Aktualisierungshaeufigkeit',
  modelCatalogScheduleDaily: 'Jeden Tag',
  modelCatalogScheduleDays: 'Alle X Tage',
  modelCatalogScheduleWeeks: 'Alle X Wochen',
  modelCatalogScheduleTime: 'Uhrzeit',
  modelCatalogScheduleInterval: 'Intervallwert',
  modelCatalogScheduleSaved: 'Einstellungen fuer die automatische Aktualisierung wurden gespeichert',
  modelCatalogLastRefreshAt: 'Letzte Aktualisierung',
  modelCatalogNextRefreshAt: 'Naechste Aktualisierung',
  modelCatalogAnomalyBanner: 'Eine Anomalie im Modellkatalog wurde erkannt',
  modelCatalogAnomalyHelp: 'Bitte pruefen Sie die Anbieter-Konfiguration, die Netzwerkverbindung oder warten Sie auf aktualisierte Filterregeln.',
  modelCatalogAnomalyUpdatedAt: 'Anomalie aktualisiert am',
  modelCatalogRetry: 'Erneut versuchen',
  modelCatalogViewDetails: 'Details anzeigen',
  modelCatalogDetailsTitle: 'Anomaliebericht zum Katalog',

  // Toast messages
  toastConfigSaved: 'Configuration sauvegardée',
  toastNotConfigured: 'non configuré',
  toastMissingRolesForTernionFull: 'Mode Ternion Complet sélectionné. Veuillez configurer les modèles manquants : {roles}',

  // Footer
  footerApiDocs: 'Documentation API',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: 'Langue',

  // Observability Panel
  logsTitle: 'Journaux en Direct',
  logsDescription: 'Journaux de traitement backend en temps réel',
  logsConnecting: 'Connexion...',
  logsConnected: 'Connecté',
  logsDisconnected: 'Déconnecté',
  logsClear: 'Effacer',
  logsAutoScroll: 'Défilement auto',
  logsNoLogs: 'Aucun journal pour l\'instant',
  logsDownload: 'Exporter',
  logsDownloading: 'Exportation...',
  logsDownloadSuccess: 'Journaux exportés avec succès',
  logsDownloadError: 'Échec de l\'exportation des journaux',
  logsDownloadedTo: 'Enregistré dans',
  logsEntriesCount: 'entrées',
  logsOpenFile: 'Afficher dans le gestionnaire de fichiers',
  logsDismiss: 'Fermer',

  // Settings Dropdown
  settingsTitle: 'Paramètres',
  settingsTheme: 'Thème',
  settingsThemeLight: 'Clair',
  settingsThemeDark: 'Sombre',
  settingsThemeSystem: 'Système',
  settingsLanguage: 'Langue',
  settingsLanguageAuto: 'Auto',
  settingsConfigLabel: 'Configuration',
  settingsConfigRestoreHint: 'Si corrompu, restaurer depuis',

  // Execution Mode Selector
  execModeTitle: 'Mode d\'Exécution',
  execModeDescription: 'Sélectionnez le mode d\'exécution après confirmation de l\'analyse Ternion',
  execModeRecommended: 'Recommandé',
  execModeCursorTitle: 'Analyse des Causes Racines Ternion + Implémentation Cursor',
  execModeTernionTitle: 'Analyse des Causes Racines Ternion + Implémentation de Code',
  execModePros: '✓ Avantages',
  execModeCons: '✗ Inconvénients',
  execModeCursorPro1: 'Coût réduit, seuls les tokens de phase d\'analyse consommés',
  execModeCursorPro2: 'Expérience native d\'implémentation de code Cursor',
  execModeCursorPro3: 'Changer vers d\'autres modèles Cursor à tout moment',
  execModeCursorCon1: 'Pas de révision d\'utilisabilité et de sécurité du code',
  execModeCursorCon2: 'Qualité du code dépend du modèle Cursor',
  execModeTernionPro1: 'Flux complet avec écriture et révision de code par Ternion Agent',
  execModeTernionPro2: 'Le Réviseur effectue la révision d\'utilisabilité et de sécurité du code',
  execModeTernionPro3: 'Meilleure qualité du code',
  execModeTernionCon1: 'Coût plus élevé, flux complet nécessite plus de tokens',
  execModeTernionCon2: 'Temps de réponse plus long',
  execModeSave: 'Enregistrer',
  execModeSaving: 'Enregistrement...',
  execModeDisabledHint: 'Cursor génère le code, aucune configuration nécessaire',
  statusExecModeNotSelected: 'Mode d\'exécution non sélectionné',
  statusExecModeSelected: 'Mode d\'exécution',
};

const DE: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'Multi-Modell-Kollaborations-Gateway-Konfiguration',
  llmKeysEnabled: 'LLM-Schlüssel aktiviert',
  lightMode: 'Zu hellem Modus wechseln',
  darkMode: 'Zu dunklem Modus wechseln',

  // Tabs
  tabConfig: 'Konfig',
  tabPorts: 'Ports',
  tabUsage: 'Nutzung',
  tabLogs: 'Protokolle',

  // Status Bar
  statusAddApiKey: 'Bitte fügen Sie mindestens einen API-Schlüssel hinzu',
  statusApiKeyAdded: 'API-Schlüssel hinzugefügt',
  statusConfigArbiter: 'Bitte konfigurieren Sie das Schiedsrichter-Modell',
  statusConfigWriter: 'Bitte konfigurieren Sie das Verfasser-Modell',
  statusConfigReviewer: 'Bitte konfigurieren Sie das Prüfer-Modell',
  statusArbiterConfigured: 'Schiedsrichter',
  statusWriterConfigured: 'Verfasser',
  statusReviewerConfigured: 'Prüfer',

  // API Key Manager
  apiKeyTitle: 'API-Schlüssel-Verwaltung',
  apiKeyDescription: 'Fügen Sie LLM-Anbieter-API-Schlüssel hinzu, um Modelle zu aktivieren',
  apiKeyStorageNote: '(Gespeicherte Schlüssel in: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'Vorzugsweise wie API-Konsole',
  apiKeyNameLabel: 'Schlüsselname',
  apiKeyLabel: 'API-Schlüssel',
  apiKeyTestAndSave: 'Testen & Speichern',
  apiKeyTesting: 'Teste...',
  apiKeySaved: 'API-Schlüssel gespeichert',
  apiKeyDeleted: 'API-Schlüssel gelöscht',
  apiKeySelected: 'API-Schlüssel ausgewählt',
  apiKeyGetKey: 'Schlüssel holen',
  enabled: 'Aktiviert',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Google AI Studio API-Schlüssel',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Anthropic API-Schlüssel',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'OpenAI API-Schlüssel',
  apiKeyDuplicate: 'Dieser API-Schlüssel existiert bereits',

  // Role Model Config
  roleConfigTitle: 'Rollenmodell-Konfiguration',
  roleConfigDescription: 'Wählen Sie Modellserie und spezifisches Modell für jede Rolle',
  roleConfigHint: '(Bitte fügen Sie oben einen API-Schlüssel hinzu, um Modelle zu aktivieren)',
  ternionAName: 'Ternion A',
  ternionADesc: 'Erstes Ternionsmitglied für Parallelanalyse',
  ternionBName: 'Ternion B',
  ternionBDesc: 'Zweites Ternionsmitglied für Parallelanalyse',
  ternionCName: 'Ternion C',
  ternionCDesc: 'Drittes Ternionsmitglied für Parallelanalyse',
  arbiterName: 'Schiedsrichter',
  arbiterDesc: 'Meinungen synthetisieren, Konflikte lösen',
  writerName: 'Verfasser',
  writerDesc: 'Finalen Code basierend auf Analyse generieren',
  reviewerName: 'Prüfer',
  reviewerDesc: 'Code-Sicherheit und Logik überprüfen',
  modelSeries: 'Modellserie',
  modelName: 'Modellname',
  selectModel: 'Modell auswählen...',
  selectSeries: 'Serie auswählen...',
  currentConfig: 'Aktuelle Konfiguration',
  notConfigured: 'Nicht konfiguriert',
  apiKeyAdded: 'API-Schlüssel hinzugefügt',
  saveChanges: 'Änderungen speichern',
  saving: 'Speichern...',
  noApiKey: '(Kein API-Schlüssel)',
  roleNotSaved: 'Rollenmodell noch nicht gespeichert',
  roleSelectionPending: 'Rollenmodell {model} ausgewählt, noch nicht gespeichert',
  unsavedLabel: 'noch nicht gespeichert',
  roleConfigValidatingModel: 'Modell wird geprüft...',
  roleConfigRemovedSelectionHint: 'Einige ausgewählte Modelle wurden aus dem aktualisierten Katalog entfernt. Bitte wählen Sie sie erneut aus.',
  roleConfigRefreshSuggested: 'Der Modellkatalog ist möglicherweise veraltet. Versuchen Sie, die Modellliste zu aktualisieren, um das Problem zu beheben.',
  roleConfigProModelWarningPrefix: 'OpenAI weist darauf hin, dass ',
  roleConfigProModelWarningLinkLabel: 'Pro-Modelle',
  roleConfigProModelWarningSuffix:
    ' am langsamsten sind, mehrere Minuten dauern können und mehr kosten. Bitte mit Bedacht wählen.',

  // Status Bar - Ternion
  statusConfigTernionA: 'Bitte konfigurieren Sie das Ternion A Modell',
  statusConfigTernionB: 'Bitte konfigurieren Sie das Ternion B Modell',
  statusConfigTernionC: 'Bitte konfigurieren Sie das Ternion C Modell',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: 'Budget-Einstellungen',
  budgetDescription: 'Empfohlen: Monatliches Limit und Warnschwelle festlegen',
  monthlyLimit: 'Monatliches Limit (USD)',
  alertThreshold: 'Warnschwelle',
  budgetLimitNote: 'Neue Anfragen ablehnen nach Erreichen dieses Betrags',
  budgetThresholdNote: 'Warnung anzeigen bei Erreichen dieses Prozentsatzes',
  preview: 'Vorschau',
  monthlyLimitLabel: 'Monatliches Limit',
  alertTriggerLabel: 'Warnauslöser-Betrag',
  budgetSaved: 'Budget-Einstellungen gespeichert',

  // Ports Settings
  portsTitle: 'Port-Konfiguration',
  portsDescription:
    'Die Informationen zum öffentlichen Zugriff werden oben angezeigt. Bei lokalen Deployments können Backend- und Web-UI-Ports bei Bedarf in den erweiterten Einstellungen geändert werden.',
  portsBackend: 'Ternion Backend-API-Port ändern',
  portsWeb: 'Web-UI-Konsolenport ändern',
  portsBackendLabel: 'Backend',
  portsCurrentBackend: 'Aktueller Ternion Backend-API-Port',
  portsCurrentWeb: 'Aktueller Web-UI-Konsolenport',
  portsAdvancedSettings: 'Erweiterte Porteinstellungen',
  portsAdvancedDescription:
    'Nur fortgeschrittene Nutzer sollten Backend- oder Web-UI-Ports ändern, typischerweise um lokale Portkonflikte zu lösen.',
  portsShowAdvancedSettings: 'Erweiterte Einstellungen anzeigen',
  portsHideAdvancedSettings: 'Erweiterte Einstellungen ausblenden',
  portsCloudRunManaged:
    'Dieser Dienst läuft auf Cloud Run. Container-Ports werden von der Plattform verwaltet und können hier nicht geändert werden.',
  portsWarning: 'Port-Änderungen erfordern manuellen Server-Neustart',
  portsRestartNote: 'Nach dem Speichern Server mit neuer Konfiguration neu starten',
  portsSaved: 'Port-Konfiguration gespeichert',
  portsInvalid: 'Ungültige Portnummer (1024-65535)',
  portsDuplicate: 'Backend- und Web-UI-Port müssen unterschiedlich sein.',
  portsConfirmChangeTitle: 'Portänderung bestätigen?',
  portsConfirmChangeDesc: 'Portänderungen werden nach einem manuellen Neustart wirksam. Änderungen speichern?',
  portsConfirmBtn: 'Bestätigen',
  portsCancelBtn: 'Abbrechen',
  portsChangedToast:
    'Ports aktualisiert. Backend: {backend}, Web UI: {web}. Bitte starten Sie den ternion-Dienst manuell neu.',
  publicAccessTitle: 'Öffentlicher Zugriff',
  publicAccessDescription:
    'Zeigen Sie die erkannte öffentliche URL an, kopieren Sie die Cursor-Basis-URL und verwenden Sie einen manuellen Fallback nur dann, wenn keine automatische Erkennung verfügbar ist.',
  publicAccessDeploymentEnvironment: 'Bereitstellung',
  publicAccessDeploymentEnvironmentLocal: 'Lokale Bereitstellung',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: 'Erkannte öffentliche URL',
  publicAccessDetectedPublicUrlUnavailable: 'Nicht automatisch erkannt',
  publicAccessManualFallbackTitle: 'Manueller Fallback',
  publicAccessManualFallbackDescription:
    'Wenn keine automatische Erkennung verfügbar ist, können Sie hier eine öffentliche HTTPS-URL speichern, damit sie auf anderen Geräten weiterhin angezeigt und kopiert werden kann.',
  publicAccessManualFallbackHint:
    'Dadurch wird kein Tunnel gestartet oder konfiguriert. Es speichert nur einen Fallback-Wert zum Anzeigen und Kopieren.',
  publicAccessDocsTitle: 'Anleitungen für öffentlichen Zugriff',
  publicAccessDocsDescription:
    'Wenn noch keine öffentliche URL erkannt wurde, verwenden Sie diese Anleitungen, um einen lokalen Tunnel einzurichten oder die GitHub-Dokumentation zu lesen.',
  publicAccessDocsLocalTunnel: 'Anleitung für lokalen Tunnel',
  publicAccessDocsCloudRun: 'Cloud Run-Bereitstellungsanleitung',
  publicAccessDocsGitHub: 'GitHub-Dokumentation',
  publicAccessMode: 'Bereitstellungsmodus',
  publicAccessModeNone: 'Keine',
  publicAccessModeLocalTunnel: 'Lokaler Tunnel',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: 'Benutzerdefiniert',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: 'Konfigurierte öffentliche URL',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: 'Quelle der effektiven URL',
  publicAccessSourceConfig: 'Konfigurierter Wert',
  publicAccessSourceRequestOrigin: 'Aus der aktuellen Anfrage erkannt',
  publicAccessSourceNgrokApi: 'Aus der lokalen ngrok-API erkannt',
  publicAccessSourceNone: 'Keine öffentliche URL verfügbar',
  publicAccessCursorHint: 'Verwenden Sie in Cursor die öffentliche HTTPS-Stamm-URL. Fügen Sie kein `/v1` an.',
  publicAccessCursorGuide:
    'Bitte kopieren Sie die obige URL in Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL, aktivieren Sie es, öffnen Sie "OpenAI API Key" und geben Sie beliebige Zeichen ein. Aktivieren Sie "Add Custom Model" unter "Models" und geben Sie "ternion-team" ein, um ternion zu nutzen!',
  publicAccessAutoDetectedNote:
    'Diese URL wurde automatisch aus der aktuellen öffentlichen Anfrage oder der lokalen ngrok-API erkannt und ist hilfreich für Cloud Run, Deployments hinter einem Reverse Proxy sowie lokale Tunnel.',
  publicAccessCopy: 'Kopieren',
  publicAccessCopied: 'Die Cursor-Basis-URL wurde kopiert',
  publicAccessCopyFailed: 'Die Cursor-Basis-URL konnte nicht kopiert werden',
  publicAccessTokenLabel: 'Zugriffstoken',
  publicAccessTokenHint: 'Erforderlich für Anfragen über einen öffentlichen Tunnel',
  publicAccessTokenDescription:
    'Fügen Sie dieses Token in Cursor als OpenAI API Key ein. Auch der Fernzugriff auf das Panel erfordert es; lokale Anfragen nicht.',
  accessTokenGateTitle: 'Zugriffstoken erforderlich',
  accessTokenGateDescription:
    'Dieses Panel wird über einen öffentlichen Tunnel geöffnet. Geben Sie das Zugriffstoken aus dem Ternion-Startbanner ein (oder kopieren Sie es aus einer lokalen Panel-Sitzung).',
  accessTokenGatePlaceholder: 'Zugriffstoken einfügen',
  accessTokenGateSubmit: 'Weiter',
  publicAccessSaved: 'Die Einstellungen für den öffentlichen Zugriff wurden gespeichert',
  publicAccessUnavailable: 'Die Einstellungen für den öffentlichen Zugriff konnten momentan nicht geladen werden.',
  publicAccessConfiguredToast:
    'Öffentlicher Zugriff ist verfügbar. Öffnen Sie die Ports-Registerkarte, um die Cursor-Basis-URL zu kopieren.',
  publicAccessIntroTitle: 'Öffentliche HTTPS-URL erforderlich',
  publicAccessIntroBody:
    'Override OpenAI Base URL in Cursor akzeptiert weder localhost noch andere nur lokal erreichbare Adressen.\nUm Cursor mit Ternion zu verbinden, muss dieser Dienst über eine öffentliche HTTPS-URL erreichbar sein.',
  publicAccessIntroOk: 'OK',
  publicAccessIntroGuide: 'So wird es eingerichtet',
  publicAccessGuideTitle: 'Öffentlichen Zugriff konfigurieren',
  publicAccessGuideBody:
    'Beispiel mit ngrok:\n1. Installieren Sie ngrok und melden Sie sich bei Ihrem Konto an.\n2. Führen Sie `ngrok http 9110` auf dem Rechner aus, auf dem Ternion läuft.\n3. Kopieren Sie die erzeugte öffentliche HTTPS-Stamm-URL.\n4. Fügen Sie diese Stamm-URL in Cursor bei Override OpenAI Base URL ein.\n5. Hängen Sie kein `/v1` an.\n\nWenn Sie Ternion auf Cloud Run bereitstellen, können Sie auch direkt den öffentlichen HTTPS-Ursprung des Dienstes verwenden.',
  publicAccessGuideClose: 'Schließen',

  // Usage Dashboard
  usageTitle: '📊 Nutzungsstatistiken',
  usageMonth: 'Monat',
  usageTotal: 'Gesamtkosten',
  usageRemaining: 'Verbleibend',
  usageRequests: 'Anfragen',
  usageByProvider: 'Kosten pro Anbieter',
  usageNoData: 'Keine Nutzungsdaten',
  usageDisclaimer: 'Die hier angezeigten Nutzungsdaten sind geschätzt und entsprechen möglicherweise nicht der tatsächlichen Abrechnung. Bitte überprüfen Sie das Abrechnungs-Dashboard Ihres API-Anbieters für genaue Kosten.',
  usageDontRemind: 'Nicht mehr anzeigen',
  usageDailyUsage: 'Tägliche Nutzung',
  usageMonthlyUsage: 'Monatliche Nutzung',
  usageAllProviders: 'Alle Anbieter',
  usageAllTokens: 'Alle Tokens',
  usageCost: 'Kosten',
  usageInputTokens: 'Eingabe-Tokens',
  usageOutputTokens: 'Ausgabe-Tokens',
  usageThoughtsTokens: 'Gedanken-Tokens',
  usagePercentage: 'Nutzungsbetrag',
  usageModifyBudget: 'Ändern',
  usageCurrentBudget: 'Aktuelles Budgetlimit',
  usageChangeTo: 'ändern zu',
  usageConfirm: 'Bestätigen',
  loading: 'Laden...',

  // Common UI
  unnamed: 'Unbenannt',
  delete: 'Löschen',
  toggleVisibility: 'Sichtbarkeit umschalten',
  confirmDeleteApiKey: 'Diesen API-Schlüssel löschen?',

  // API Response Codes
  code_SUCCESS: 'Erfolgreich verbunden',
  code_AUTH_ERROR: 'Ungültiger API-Schlüssel',
  code_CONNECTION_ERROR: 'Verbindung fehlgeschlagen',
  code_UNKNOWN_ERROR: 'Unbekannter Fehler',
  code_INVALID_PROVIDER: 'Ungültiger Anbieter',
  code_PROVIDER_NOT_FOUND: 'Anbieter nicht gefunden',
  code_API_KEY_NOT_FOUND: 'API-Schlüssel nicht gefunden',
  code_API_KEY_DUPLICATE: 'Dieser API-Schlüssel existiert bereits',
  code_PROVIDER_NOT_ENABLED: 'Anbieter nicht aktiviert',
  code_MODEL_NOT_AVAILABLE: 'Modell nicht verfügbar',
  code_MODEL_UNAVAILABLE: 'Das ausgewählte Modell ist beim Anbieter nicht mehr verfügbar',
  code_MODEL_PROBE_AUTH_ERROR: 'Die Modellprüfung ist fehlgeschlagen, weil der API-Schlüssel des Anbieters ungültig ist oder keine Berechtigung hat',
  code_MODEL_PROBE_TIMEOUT: 'Die Modellprüfung hat das Zeitlimit überschritten, bitte erneut versuchen',
  code_MODEL_PROBE_CONNECTION_ERROR: 'Die Modellprüfung ist fehlgeschlagen, weil der Anbieter nicht erreichbar ist',
  code_INVALID_BUDGET_LIMIT: 'Ungültiges Budget-Limit',
  code_INVALID_BUDGET_THRESHOLD: 'Ungültige Budget-Schwelle',
  code_BUDGET_EXCEEDED: 'Monatsbudget überschritten',
  code_BUDGET_WARNING: 'Budget-Limit nähert sich',
  code_STREAM_INTERRUPTED: 'Übertragung unterbrochen, bitte erneut versuchen',
  code_ROLES_INCOMPLETE: 'Bitte konfigurieren Sie alle Rollen, bevor Sie speichern',
  code_ROLES_INCOMPLETE_SUFFIX: ' (fehlend: {roles})',
  code_MODEL_CATALOG_REFRESH_FAILED: 'モデルカタログの更新に失敗しました',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'カタログ異常レポートが見つかりません',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: '自動更新モードが無効です',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: '自動更新時刻が無効です',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '自動更新間隔が無効です',
  code_INVALID_PUBLIC_ACCESS_MODE: 'Ungültiger Modus für öffentlichen Zugriff',
  code_INVALID_PUBLIC_BASE_URL: 'Ungültige öffentliche HTTPS-URL',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Unbekannter Fehler',
  successConnected: 'Erfolgreich verbunden',
  modelCatalogTitle: 'モデルカタログ',
  modelCatalogDescription: 'LiteLLM モデルカタログの初期化、手動更新、定期更新を設定します。',
  modelCatalogInitialize: 'モデル一覧を初期化',
  modelCatalogInitializing: '初期化中...',
  modelCatalogRefreshNow: 'モデル一覧を更新',
  modelCatalogRefreshing: '更新中...',
  modelCatalogInitSuccess: 'モデルカタログの初期化に成功しました',
  modelCatalogInitFailed: 'モデルカタログの初期化に失敗しました',
  modelCatalogInitAnomaly: 'モデルカタログは初期化されましたが、異常が検出されました',
  modelCatalogRefreshSuccess: 'モデルカタログの更新に成功しました',
  modelCatalogRefreshFailed: 'モデルカタログの更新に失敗しました',
  modelCatalogRefreshAnomaly: 'モデルカタログの更新は完了しましたが、異常が検出されました',
  modelCatalogStatus: 'カタログ状態',
  modelCatalogStatusReady: '利用可能',
  modelCatalogStatusNeedsInitialization: '初期化が必要です',
  modelCatalogFirstUseBanner: 'Ternionを初めてご利用ですか？モデル一覧を初期化してください。',
  modelCatalogModelCount: '利用可能なモデル数',
  modelCatalogCatalogUpdatedAt: 'カタログ更新日時',
  modelCatalogScheduleTitle: '自動更新',
  modelCatalogScheduleDescription: 'モデルカタログの定期バックグラウンド更新を設定します。',
  modelCatalogScheduleEnabled: '自動更新を有効化',
  modelCatalogScheduleMode: '更新頻度',
  modelCatalogScheduleDaily: '毎日',
  modelCatalogScheduleDays: 'X日ごと',
  modelCatalogScheduleWeeks: 'X週間ごと',
  modelCatalogScheduleTime: '更新時刻',
  modelCatalogScheduleInterval: '間隔値',
  modelCatalogScheduleSaved: '自動更新設定を保存しました',
  modelCatalogLastRefreshAt: '前回の更新日時',
  modelCatalogNextRefreshAt: '次回の更新日時',
  modelCatalogAnomalyBanner: 'モデルカタログの異常が検出されました',
  modelCatalogAnomalyHelp: 'プロバイダー設定やネットワーク接続を確認するか、フィルタールールの更新をお待ちください。',
  modelCatalogAnomalyUpdatedAt: '異常更新日時',
  modelCatalogRetry: '再試行',
  modelCatalogViewDetails: '詳細を見る',
  modelCatalogDetailsTitle: 'カタログ異常レポート',

  // Toast messages
  toastConfigSaved: 'Konfiguration gespeichert',
  toastNotConfigured: 'nicht konfiguriert',
  toastMissingRolesForTernionFull: 'Ternion Full-Modus ausgewählt. Bitte konfigurieren Sie die fehlenden Modelle: {roles}',

  // Footer
  footerApiDocs: 'API-Dokumentation',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: 'Sprache',

  // Observability Panel
  logsTitle: 'Live-Protokolle',
  logsDescription: 'Echtzeit-Backend-Verarbeitungsprotokolle',
  logsConnecting: 'Verbinden...',
  logsConnected: 'Verbunden',
  logsDisconnected: 'Getrennt',
  logsClear: 'Löschen',
  logsAutoScroll: 'Auto-Scrollen',
  logsNoLogs: 'Noch keine Protokolle',
  logsDownload: 'Exportieren',
  logsDownloading: 'Wird exportiert...',
  logsDownloadSuccess: 'Protokolle erfolgreich exportiert',
  logsDownloadError: 'Fehler beim Exportieren der Protokolle',
  logsDownloadedTo: 'Gespeichert unter',
  logsEntriesCount: 'Einträge',
  logsOpenFile: 'Im Dateimanager anzeigen',
  logsDismiss: 'Schließen',

  // Settings Dropdown
  settingsTitle: 'Einstellungen',
  settingsTheme: 'Thema',
  settingsThemeLight: 'Hell',
  settingsThemeDark: 'Dunkel',
  settingsThemeSystem: 'System',
  settingsLanguage: 'Sprache',
  settingsLanguageAuto: 'Auto',
  settingsConfigLabel: 'Konfiguration',
  settingsConfigRestoreHint: 'Bei Beschädigung wiederherstellen von',

  // Execution Mode Selector
  execModeTitle: 'Ausführungsmodus',
  execModeDescription: 'Wählen Sie den Ausführungsmodus nach Bestätigung der Ternion-Analyse',
  execModeRecommended: 'Empfohlen',
  execModeCursorTitle: 'Ternion Ursachenanalyse + Cursor Implementierung',
  execModeTernionTitle: 'Ternion Ursachenanalyse + Code-Implementierung',
  execModePros: '✓ Vorteile',
  execModeCons: '✗ Nachteile',
  execModeCursorPro1: 'Geringere Kosten, nur Analysephase-Token verbraucht',
  execModeCursorPro2: 'Native Cursor-Code-Implementierungserfahrung',
  execModeCursorPro3: 'Jederzeit zu anderen Cursor-Modellen wechseln',
  execModeCursorCon1: 'Keine Code-Usability- und Sicherheitsprüfung',
  execModeCursorCon2: 'Codequalität hängt vom Cursor-Modell ab',
  execModeTernionPro1: 'Vollständiger Workflow mit Ternion Agent Code-Schreiben und -Prüfung',
  execModeTernionPro2: 'Reviewer führt Code-Usability- und Sicherheitsprüfung durch',
  execModeTernionPro3: 'Höhere Codequalität',
  execModeTernionCon1: 'Höhere Kosten, vollständiger Workflow benötigt mehr Token',
  execModeTernionCon2: 'Längere Antwortzeit',
  execModeSave: 'Speichern',
  execModeSaving: 'Speichern...',
  execModeDisabledHint: 'Cursor generiert den Code, keine Konfiguration erforderlich',
  statusExecModeNotSelected: 'Ausführungsmodus nicht ausgewählt',
  statusExecModeSelected: 'Ausführungsmodus',
};

const JA: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'マルチモデル連携ゲートウェイ設定',
  llmKeysEnabled: 'LLMキー有効',
  lightMode: 'ライトモードに切り替え',
  darkMode: 'ダークモードに切り替え',

  // Tabs
  tabConfig: '設定',
  tabPorts: 'ポート',
  tabUsage: '使用量',
  tabLogs: 'ログ',

  // Status Bar
  statusAddApiKey: 'APIキーを追加してください',
  statusApiKeyAdded: 'APIキー追加済み',
  statusConfigArbiter: '調停者モデルを設定してください',
  statusConfigWriter: '執筆者モデルを設定してください',
  statusConfigReviewer: '審査者モデルを設定してください',
  statusArbiterConfigured: '調停者',
  statusWriterConfigured: '執筆者',
  statusReviewerConfigured: '審査者',

  // API Key Manager
  apiKeyTitle: 'APIキー管理',
  apiKeyDescription: 'LLMプロバイダーのAPIキーを追加してモデルを有効化',
  apiKeyStorageNote: '(保存されたキー: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'APIコンソールと同じ名前推奨',
  apiKeyNameLabel: 'キー名',
  apiKeyLabel: 'APIキー',
  apiKeyTestAndSave: 'テスト＆保存',
  apiKeyTesting: 'テスト中...',
  apiKeySaved: 'APIキー保存済み',
  apiKeyDeleted: 'APIキー削除済み',
  apiKeySelected: 'APIキー選択済み',
  apiKeyGetKey: 'キー取得',
  enabled: '有効',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Google AI Studio APIキー',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Anthropic APIキー',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'OpenAI APIキー',
  apiKeyDuplicate: 'このAPIキーは既に存在します',

  // Role Model Config
  roleConfigTitle: 'ロールモデル設定',
  roleConfigDescription: '各ロールのモデルシリーズと特定モデルを選択',
  roleConfigHint: '(上記でAPIキーを追加してモデルを有効化)',
  ternionAName: 'Ternion A',
  ternionADesc: '第一のTernion、並列分析担当',
  ternionBName: 'Ternion B',
  ternionBDesc: '第二のTernion、並列分析担当',
  ternionCName: 'Ternion C',
  ternionCDesc: '第三のTernion、並列分析担当',
  arbiterName: '調停者',
  arbiterDesc: '意見を統合し、対立を解決',
  writerName: '執筆者',
  writerDesc: '分析に基づいてコードを生成',
  reviewerName: '審査者',
  reviewerDesc: 'コードのセキュリティとロジックを確認',
  modelSeries: 'モデルシリーズ',
  modelName: 'モデル名',
  selectModel: 'モデルを選択...',
  selectSeries: 'シリーズを選択...',
  currentConfig: '現在の設定',
  notConfigured: '未設定',
  apiKeyAdded: 'APIキー追加済み',
  saveChanges: '保存',
  saving: '保存中...',
  noApiKey: '(APIキーなし)',
  roleNotSaved: 'ロールモデルはまだ保存されていません',
  roleSelectionPending: 'ロールモデル {model} を選択、まだ保存されていません',
  unsavedLabel: '未保存',
  roleConfigValidatingModel: 'モデルを検証中...',
  roleConfigRemovedSelectionHint: '選択していた一部のモデルが更新後のカタログから削除されました。再選択してください。',
  roleConfigRefreshSuggested: 'モデルカタログが古くなっている可能性があります。モデルリストを更新してこの問題を解決してください。',
  roleConfigProModelWarningPrefix: 'OpenAI によると、',
  roleConfigProModelWarningLinkLabel: 'Pro モデル',
  roleConfigProModelWarningSuffix:
    'は最も遅く、数分かかる場合があり、コストも高くなります。慎重に選択してください。',

  // Status Bar - Ternion
  statusConfigTernionA: 'Ternion A モデルを設定してください',
  statusConfigTernionB: 'Ternion B モデルを設定してください',
  statusConfigTernionC: 'Ternion C モデルを設定してください',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: '予算設定',
  budgetDescription: '月間上限とアラート閾値の設定を推奨',
  monthlyLimit: '月間上限 (USD)',
  alertThreshold: 'アラート閾値',
  budgetLimitNote: 'この金額に達したら新規リクエストを拒否',
  budgetThresholdNote: 'この割合に達したら警告を表示',
  preview: 'プレビュー',
  monthlyLimitLabel: '月間上限',
  alertTriggerLabel: 'アラート発動金額',
  budgetSaved: '予算設定を保存しました',

  // Ports Settings
  portsTitle: 'ポート設定',
  portsDescription:
    '公開アクセス情報は上部に優先表示されます。ローカルデプロイでは、必要な場合のみ高度な設定でバックエンドポートと Web UI ポートを変更してください。',
  portsBackend: 'Ternionバックエンドポート変更',
  portsWeb: 'Web UI コントロールパネルポート変更',
  portsBackendLabel: 'バックエンド',
  portsCurrentBackend: '現在のTernionバックエンドAPIポート',
  portsCurrentWeb: '現在の Web UI コントロールパネルポート',
  portsAdvancedSettings: '高度なポート設定',
  portsAdvancedDescription:
    '通常、バックエンドポートまたは Web UI ポートを変更するのは、ローカルのポート競合を解消するときだけです。',
  portsShowAdvancedSettings: '高度な設定を表示',
  portsHideAdvancedSettings: '高度な設定を隠す',
  portsCloudRunManaged:
    'このサービスは Cloud Run 上で動作しています。コンテナポートはプラットフォームによって管理されており、ここでは変更できません。',
  portsWarning: 'ポート変更はサーバー再起動が必要です',
  portsRestartNote: '保存後、新しい設定でサーバーを再起動してください',
  portsSaved: 'ポート設定を保存しました',
  portsInvalid: '無効なポート番号 (1024-65535)',
  portsDuplicate: 'バックエンドポートと Web UI ポートは同じにできません。',
  portsConfirmChangeTitle: 'ポート変更を確認しますか？',
  portsConfirmChangeDesc: 'ポートの変更は手動再起動後に有効になります。変更を保存しますか？',
  portsConfirmBtn: '確認',
  portsCancelBtn: 'キャンセル',
  portsChangedToast:
    'ポートを更新しました。バックエンド: {backend}、Web UI: {web}。ternion サービスを手動で再起動してください。',
  publicAccessTitle: '公開アクセス',
  publicAccessDescription:
    '検出された公開 URL を確認し、Cursor Base URL をコピーし、自動検出できない場合にのみ手動 fallback を使います。',
  publicAccessDeploymentEnvironment: '現在のデプロイ方式',
  publicAccessDeploymentEnvironmentLocal: 'ローカルデプロイ',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: '現在検出されている公開 URL',
  publicAccessDetectedPublicUrlUnavailable: 'まだ自動検出されていません',
  publicAccessManualFallbackTitle: '手動 fallback',
  publicAccessManualFallbackDescription:
    '現在公開 URL を自動検出できない場合は、他の端末でも表示・コピーできるように、ここで公開 HTTPS URL を補足できます。',
  publicAccessManualFallbackHint:
    'これは tunnel を自動起動または設定しません。表示とコピー用の fallback 値を保存するだけです。',
  publicAccessDocsTitle: '公開アクセスのガイド',
  publicAccessDocsDescription:
    'まだ公開 URL が検出されていない場合は、これらのガイドからローカルトンネル設定または GitHub ドキュメントを確認できます。',
  publicAccessDocsLocalTunnel: 'ローカルトンネル設定ガイド',
  publicAccessDocsCloudRun: 'Cloud Run デプロイガイド',
  publicAccessDocsGitHub: 'GitHub ドキュメント',
  publicAccessMode: 'デプロイ方式',
  publicAccessModeNone: 'なし',
  publicAccessModeLocalTunnel: 'ローカルトンネル',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: 'カスタム',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: '設定済み公開 URL',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: '有効 URL の取得元',
  publicAccessSourceConfig: '明示設定値',
  publicAccessSourceRequestOrigin: '現在のリクエストから自動検出',
  publicAccessSourceNgrokApi: 'ローカル ngrok API から自動検出',
  publicAccessSourceNone: '利用可能な公開 URL はありません',
  publicAccessCursorHint: 'Cursor には公開 HTTPS のルート URL を入力し、`/v1` は付けないでください。',
  publicAccessCursorGuide:
    '上のURLを Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL の下の入力ボックスにコピーしてスイッチをオンにし、「OpenAI API Key」を開いて任意の文字を入力してください。「Models」で「View All Models」をクリックして「Add Custom Model」をオンにし、「ternion-team」と入力すると、ternionの使用を開始できます！',
  publicAccessAutoDetectedNote:
    'この URL は現在の公開リクエストまたはローカル ngrok API から自動検出されています。Cloud Run、リバースプロキシ構成、ローカルトンネルで役立ちます。',
  publicAccessCopy: 'コピー',
  publicAccessCopied: 'Cursor Base URL をコピーしました',
  publicAccessCopyFailed: 'Cursor Base URL のコピーに失敗しました',
  publicAccessTokenLabel: 'アクセストークン',
  publicAccessTokenHint: '公開トンネル経由のリクエストに必須',
  publicAccessTokenDescription:
    'このトークンを Cursor の OpenAI API Key に貼り付けてください。リモートからのコントロールパネル利用にも必要です。ローカルのリクエストには不要です。',
  accessTokenGateTitle: 'アクセストークンが必要です',
  accessTokenGateDescription:
    'このコントロールパネルは公開トンネル経由で開かれています。Ternion の起動バナーに表示されたアクセストークンを入力してください（ローカルのパネルからコピーすることもできます）。',
  accessTokenGatePlaceholder: 'アクセストークンを貼り付け',
  accessTokenGateSubmit: '続行',
  publicAccessSaved: '公開アクセス設定を保存しました',
  publicAccessUnavailable: '現在、公開アクセス設定を読み込めません。',
  publicAccessConfiguredToast:
    '公開アクセスを検出しました。Ports タブで Cursor Base URL をコピーしてください。',
  publicAccessIntroTitle: '公開 HTTPS URL が必要です',
  publicAccessIntroBody:
    'Cursor の Override OpenAI Base URL は localhost やローカル専用アドレスを受け付けません。\nCursor から Ternion に接続するには、このサービスを公開 HTTPS URL で公開する必要があります。',
  publicAccessIntroOk: 'OK',
  publicAccessIntroGuide: '設定方法',
  publicAccessGuideTitle: '公開アクセスの設定方法',
  publicAccessGuideBody:
    'ngrok の例:\n1. ngrok をインストールし、アカウントにログインします。\n2. Ternion を実行しているマシンで `ngrok http 9110` を実行します。\n3. 生成された公開 HTTPS ルート URL をコピーします。\n4. そのルート URL を Cursor の Override OpenAI Base URL に貼り付けます。\n5. `/v1` は付けないでください。\n\nTernion を Cloud Run にデプロイしている場合は、サービス自身の公開 HTTPS オリジンをそのまま使用できます。',
  publicAccessGuideClose: '閉じる',

  // Usage Dashboard
  usageTitle: '📊 使用統計',
  usageMonth: '月',
  usageTotal: '合計コスト',
  usageRemaining: '残り',
  usageRequests: 'リクエスト数',
  usageByProvider: 'プロバイダー別コスト',
  usageNoData: '使用データなし',
  usageDisclaimer: 'ここに表示される使用量データは推定値であり、実際の請求額と異なる場合があります。正確なコストについては、APIプロバイダーの請求ダッシュボードをご確認ください。',
  usageDontRemind: '今後表示しない',
  usageDailyUsage: '日別使用量',
  usageMonthlyUsage: '月別使用量',
  usageAllProviders: 'すべての提供元',
  usageAllTokens: 'すべてのトークン',
  usageCost: 'コスト',
  usageInputTokens: '入力トークン',
  usageOutputTokens: '出力トークン',
  usageThoughtsTokens: '思考トークン',
  usagePercentage: '使用金額',
  usageModifyBudget: '修正',
  usageCurrentBudget: '現在の予算上限',
  usageChangeTo: '変更先',
  usageConfirm: '確認',
  loading: '読み込み中...',

  // Common UI
  unnamed: '名前なし',
  delete: '削除',
  toggleVisibility: '表示を切り替える',
  confirmDeleteApiKey: 'このAPIキーを削除しますか？',

  // API Response Codes
  code_SUCCESS: '接続成功',
  code_AUTH_ERROR: '無効なAPIキー',
  code_CONNECTION_ERROR: '接続失敗',
  code_UNKNOWN_ERROR: '不明なエラー',
  code_INVALID_PROVIDER: '無効なプロバイダー',
  code_PROVIDER_NOT_FOUND: 'プロバイダーが見つかりません',
  code_API_KEY_NOT_FOUND: 'APIキーが見つかりません',
  code_API_KEY_DUPLICATE: 'このAPIキーは既に存在します',
  code_PROVIDER_NOT_ENABLED: 'プロバイダーが有効化されていません',
  code_MODEL_NOT_AVAILABLE: 'モデルが利用できません',
  code_MODEL_UNAVAILABLE: '選択したモデルは現在そのプロバイダーで利用できません',
  code_MODEL_PROBE_AUTH_ERROR: 'モデル検証に失敗しました。現在のプロバイダー API キーが無効か権限不足です',
  code_MODEL_PROBE_TIMEOUT: 'モデル検証がタイムアウトしました。再試行してください',
  code_MODEL_PROBE_CONNECTION_ERROR: 'モデル検証に失敗しました。現在プロバイダーに接続できません',
  code_INVALID_BUDGET_LIMIT: '無効な予算上限',
  code_INVALID_BUDGET_THRESHOLD: '無効な予算閾値',
  code_BUDGET_EXCEEDED: '月間予算を超過しました',
  code_BUDGET_WARNING: '予算上限に近づいています',
  code_STREAM_INTERRUPTED: '伝送中断、再試行してください',
  code_ROLES_INCOMPLETE: '保存する前にすべてのロールを設定してください',
  code_ROLES_INCOMPLETE_SUFFIX: '（不足：{roles}）',
  code_MODEL_CATALOG_REFRESH_FAILED: '모델 카탈로그 새로고침에 실패했습니다',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: '카탈로그 이상 보고서를 찾을 수 없습니다',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: '자동 새로고침 모드가 올바르지 않습니다',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: '자동 새로고침 시간이 올바르지 않습니다',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '자동 새로고침 간격이 올바르지 않습니다',
  code_INVALID_PUBLIC_ACCESS_MODE: '公開アクセスモードが無効です',
  code_INVALID_PUBLIC_BASE_URL: '公開 HTTPS URL が無効です',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '不明なエラー',
  successConnected: '接続成功',
  modelCatalogTitle: '모델 카탈로그',
  modelCatalogDescription: 'LiteLLM 모델 카탈로그의 초기화, 수동 새로고침, 예약 갱신을 설정합니다.',
  modelCatalogInitialize: '모델 목록 초기화',
  modelCatalogInitializing: '초기화 중...',
  modelCatalogRefreshNow: '모델 목록 새로고침',
  modelCatalogRefreshing: '새로고침 중...',
  modelCatalogInitSuccess: '모델 카탈로그가 성공적으로 초기화되었습니다',
  modelCatalogInitFailed: '모델 카탈로그를 초기화하지 못했습니다',
  modelCatalogInitAnomaly: '모델 카탈로그가 초기화되었지만 이상이 감지되었습니다',
  modelCatalogRefreshSuccess: '모델 카탈로그가 성공적으로 새로고침되었습니다',
  modelCatalogRefreshFailed: '모델 카탈로그를 새로고침하지 못했습니다',
  modelCatalogRefreshAnomaly: '모델 카탈로그 새로고침은 완료되었지만 이상이 감지되었습니다',
  modelCatalogStatus: '카탈로그 상태',
  modelCatalogStatusReady: '준비됨',
  modelCatalogStatusNeedsInitialization: '초기화 필요',
  modelCatalogFirstUseBanner: 'Ternion을 처음 사용하시나요? 모델 목록을 초기화해주세요.',
  modelCatalogModelCount: '사용 가능한 모델 수',
  modelCatalogCatalogUpdatedAt: '카탈로그 갱신 시각',
  modelCatalogScheduleTitle: '자동 새로고침',
  modelCatalogScheduleDescription: '모델 카탈로그의 주기적인 백그라운드 새로고침을 설정합니다.',
  modelCatalogScheduleEnabled: '자동 새로고침 활성화',
  modelCatalogScheduleMode: '새로고침 주기',
  modelCatalogScheduleDaily: '매일',
  modelCatalogScheduleDays: 'X일마다',
  modelCatalogScheduleWeeks: 'X주마다',
  modelCatalogScheduleTime: '시간',
  modelCatalogScheduleInterval: '간격 값',
  modelCatalogScheduleSaved: '자동 새로고침 설정이 저장되었습니다',
  modelCatalogLastRefreshAt: '마지막 새로고침 시각',
  modelCatalogNextRefreshAt: '다음 새로고침 시각',
  modelCatalogAnomalyBanner: '모델 카탈로그 이상이 감지되었습니다',
  modelCatalogAnomalyHelp: '공급자 설정과 네트워크 연결을 확인하거나 필터 규칙이 갱신될 때까지 기다려 주세요.',
  modelCatalogAnomalyUpdatedAt: '이상 갱신 시각',
  modelCatalogRetry: '다시 시도',
  modelCatalogViewDetails: '상세 보기',
  modelCatalogDetailsTitle: '카탈로그 이상 보고서',

  // Toast messages
  toastConfigSaved: '設定を保存しました',
  toastNotConfigured: '未設定',
  toastMissingRolesForTernionFull: 'Ternion Full モードが選択されました。不足しているモデルを設定してください: {roles}',

  // Footer
  footerApiDocs: 'APIドキュメント',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: '言語',

  // Observability Panel
  logsTitle: 'ライブログ',
  logsDescription: 'リアルタイムバックエンド処理ログ',
  logsConnecting: '接続中...',
  logsConnected: '接続済み',
  logsDisconnected: '切断',
  logsClear: 'クリア',
  logsAutoScroll: '自動スクロール',
  logsNoLogs: 'ログはまだありません',
  logsDownload: 'エクスポート',
  logsDownloading: 'エクスポート中...',
  logsDownloadSuccess: 'ログを正常にエクスポートしました',
  logsDownloadError: 'ログのエクスポートに失敗しました',
  logsDownloadedTo: '保存先',
  logsEntriesCount: '件',
  logsOpenFile: 'ファイルマネージャーで表示',
  logsDismiss: '閉じる',

  // Settings Dropdown
  settingsTitle: '設定',
  settingsTheme: 'テーマ',
  settingsThemeLight: 'ライト',
  settingsThemeDark: 'ダーク',
  settingsThemeSystem: 'システム',
  settingsLanguage: '言語',
  settingsLanguageAuto: '自動',
  settingsConfigLabel: '設定ファイル',
  settingsConfigRestoreHint: '破損時はバックアップから復元',

  // Execution Mode Selector
  execModeTitle: '実行モード',
  execModeDescription: 'Ternion分析確認後の実行モードを選択',
  execModeRecommended: '推奨',
  execModeCursorTitle: 'Ternion根本原因分析 + Cursor実装',
  execModeTernionTitle: 'Ternion根本原因分析 + コード実装',
  execModePros: '✓ メリット',
  execModeCons: '✗ デメリット',
  execModeCursorPro1: '低コスト、分析フェーズのトークンのみ消費',
  execModeCursorPro2: 'ネイティブCursorコード実装体験',
  execModeCursorPro3: 'いつでも他のCursorモデルに切り替え可能',
  execModeCursorCon1: 'コードの使用性とセキュリティレビューなし',
  execModeCursorCon2: 'コード品質はCursorモデルに依存',
  execModeTernionPro1: 'Ternion Agentによるコード作成とレビューの完全なワークフロー',
  execModeTernionPro2: 'レビューアーがコードの使用性とセキュリティレビューを実施',
  execModeTernionPro3: 'より高いコード品質',
  execModeTernionCon1: '高コスト、完全なワークフローはより多くのトークンが必要',
  execModeTernionCon2: '応答時間が長い',
  execModeSave: '保存',
  execModeSaving: '保存中...',
  execModeDisabledHint: 'Cursorがコード生成を担当、設定不要',
  statusExecModeNotSelected: '実行モード未選択',
  statusExecModeSelected: '実行モード',
};

const KO: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: '멀티모델 협업 게이트웨이 구성',
  llmKeysEnabled: 'LLM 키 활성화됨',
  lightMode: '라이트 모드로 전환',
  darkMode: '다크 모드로 전환',

  // Tabs
  tabConfig: '설정',
  tabPorts: '포트',
  tabUsage: '사용량',
  tabLogs: '로그',

  // Status Bar
  statusAddApiKey: 'API 키를 추가해 주세요',
  statusApiKeyAdded: 'API 키 추가됨',
  statusConfigArbiter: '중재자 모델을 구성해 주세요',
  statusConfigWriter: '작성자 모델을 구성해 주세요',
  statusConfigReviewer: '검토자 모델을 구성해 주세요',
  statusArbiterConfigured: '중재자',
  statusWriterConfigured: '작성자',
  statusReviewerConfigured: '검토자',

  // API Key Manager
  apiKeyTitle: 'API 키 관리',
  apiKeyDescription: 'LLM 공급자 API 키를 추가하여 모델 활성화',
  apiKeyStorageNote: '(저장된 키: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'API 콘솔과 동일한 이름 권장',
  apiKeyNameLabel: '키 이름',
  apiKeyLabel: 'API 키',
  apiKeyTestAndSave: '테스트 및 저장',
  apiKeyTesting: '테스트 중...',
  apiKeySaved: 'API 키 저장됨',
  apiKeyDeleted: 'API 키 삭제됨',
  apiKeySelected: 'API 키 선택됨',
  apiKeyGetKey: '키 받기',
  enabled: '활성화',

  // Provider names and descriptions
  providerGoogle: 'Google Gemini',
  providerGoogleDesc: 'Google AI Studio API 키',
  providerAnthropic: 'Anthropic Claude',
  providerAnthropicDesc: 'Anthropic API 키',
  providerOpenai: 'OpenAI GPT',
  providerOpenaiDesc: 'OpenAI API 키',
  apiKeyDuplicate: '이 API 키는 이미 존재합니다',

  // Role Model Config
  roleConfigTitle: '역할 모델 구성',
  roleConfigDescription: '각 역할의 모델 시리즈와 특정 모델 선택',
  roleConfigHint: '(위에서 API 키를 추가하여 모델 활성화)',
  ternionAName: 'Ternion A',
  ternionADesc: '첫 번째 Ternion, 병렬 분석 담당',
  ternionBName: 'Ternion B',
  ternionBDesc: '두 번째 Ternion, 병렬 분석 담당',
  ternionCName: 'Ternion C',
  ternionCDesc: '세 번째 Ternion, 병렬 분석 담당',
  arbiterName: '중재자',
  arbiterDesc: '의견을 종합하고 갈등 해결',
  writerName: '작성자',
  writerDesc: '분석 기반 코드 생성',
  reviewerName: '검토자',
  reviewerDesc: '코드 보안 및 로직 검토',
  modelSeries: '모델 시리즈',
  modelName: '모델 이름',
  selectModel: '모델 선택...',
  selectSeries: '시리즈 선택...',
  currentConfig: '현재 구성',
  notConfigured: '구성되지 않음',
  apiKeyAdded: 'API 키 추가됨',
  saveChanges: '저장',
  saving: '저장 중...',
  noApiKey: '(API 키 없음)',
  roleNotSaved: '역할 모델이 아직 저장되지 않았습니다',
  roleSelectionPending: '역할 모델 {model} 선택, 아직 저장되지 않았습니다',
  unsavedLabel: '저장되지 않음',
  roleConfigValidatingModel: '모델 검증 중...',
  roleConfigRemovedSelectionHint: '선택한 일부 모델이 새로고침된 카탈로그에서 제거되었습니다. 다시 선택해 주세요.',
  roleConfigRefreshSuggested: '모델 카탈로그가 최신이 아닐 수 있습니다. 모델 목록을 새로고침하여 이 문제를 해결해 보세요.',
  roleConfigProModelWarningPrefix: 'OpenAI 안내에 따르면 ',
  roleConfigProModelWarningLinkLabel: 'Pro 모델',
  roleConfigProModelWarningSuffix:
    '은 가장 느리고 몇 분이 걸릴 수 있으며 비용도 더 높습니다. 신중하게 선택해 주세요.',

  // Status Bar - Ternion
  statusConfigTernionA: 'Ternion A 모델을 구성해 주세요',
  statusConfigTernionB: 'Ternion B 모델을 구성해 주세요',
  statusConfigTernionC: 'Ternion C 모델을 구성해 주세요',
  statusTernionAConfigured: 'Ternion A',
  statusTernionBConfigured: 'Ternion B',
  statusTernionCConfigured: 'Ternion C',
  statusTernionLine: 'Ternion',

  // Budget Settings
  budgetTitle: '예산 설정',
  budgetDescription: '월간 한도와 알림 임계값 설정 권장',
  monthlyLimit: '월간 한도 (USD)',
  alertThreshold: '알림 임계값',
  budgetLimitNote: '이 금액에 도달하면 새 요청 거부',
  budgetThresholdNote: '이 비율에 도달하면 경고 표시',
  preview: '미리보기',
  monthlyLimitLabel: '월간 한도',
  alertTriggerLabel: '알림 발동 금액',
  budgetSaved: '예산 설정 저장됨',

  // Ports Settings
  portsTitle: '포트 설정',
  portsDescription:
    '공개 액세스 정보가 위에 우선 표시됩니다. 로컬 배포에서는 필요한 경우에만 고급 설정에서 백엔드와 Web UI 포트를 변경하세요.',
  portsBackend: 'Ternion 백엔드 포트 변경',
  portsWeb: 'Web UI 제어판 포트 변경',
  portsBackendLabel: '백엔드',
  portsCurrentBackend: '현재 Ternion 백엔드 API 포트',
  portsCurrentWeb: '현재 Web UI 제어판 포트',
  portsAdvancedSettings: '고급 포트 설정',
  portsAdvancedDescription:
    '보통 로컬 포트 충돌을 해결해야 할 때만 고급 사용자가 백엔드 또는 Web UI 포트를 변경하면 됩니다.',
  portsShowAdvancedSettings: '고급 설정 표시',
  portsHideAdvancedSettings: '고급 설정 숨기기',
  portsCloudRunManaged:
    '이 서비스는 Cloud Run에서 실행 중입니다. 컨테이너 포트는 플랫폼에서 관리되므로 여기서 변경할 수 없습니다.',
  portsWarning: '포트 변경은 서버 재시작이 필요합니다',
  portsRestartNote: '저장 후 새 구성으로 서버를 다시 시작하세요',
  portsSaved: '포트 설정 저장됨',
  portsInvalid: '잘못된 포트 번호 (1024-65535)',
  portsDuplicate: '백엔드 포트와 Web UI 포트는 서로 달라야 합니다.',
  portsConfirmChangeTitle: '포트 변경을 확인하시겠습니까?',
  portsConfirmChangeDesc: '포트 변경 사항은 수동 재시작 후 적용됩니다. 변경 사항을 저장하시겠습니까?',
  portsConfirmBtn: '확인',
  portsCancelBtn: '취소',
  portsChangedToast:
    '포트가 업데이트되었습니다. 백엔드: {backend}, Web UI: {web}. ternion 서비스를 수동으로 재시작하십시오.',
  publicAccessTitle: '공개 액세스',
  publicAccessDescription:
    '감지된 공개 URL을 확인하고 Cursor Base URL을 복사하며, 자동 감지가 불가능할 때만 수동 fallback을 사용합니다.',
  publicAccessDeploymentEnvironment: '현재 배포 방식',
  publicAccessDeploymentEnvironmentLocal: '로컬 배포',
  publicAccessDeploymentEnvironmentCloudRun: 'Cloud Run',
  publicAccessDetectedPublicUrl: '현재 감지된 공개 URL',
  publicAccessDetectedPublicUrlUnavailable: '아직 자동 감지되지 않음',
  publicAccessManualFallbackTitle: '수동 fallback',
  publicAccessManualFallbackDescription:
    '현재 공개 URL을 자동으로 감지할 수 없다면, 다른 기기에서도 계속 표시하고 복사할 수 있도록 여기에서 공개 HTTPS URL을 보완할 수 있습니다.',
  publicAccessManualFallbackHint:
    '이 작업은 어떤 터널도 자동으로 시작하거나 구성하지 않습니다. 표시와 복사용 fallback 값만 저장합니다.',
  publicAccessDocsTitle: '공개 액세스 가이드',
  publicAccessDocsDescription:
    '아직 공개 URL이 감지되지 않았다면 이 가이드를 통해 로컬 터널 설정 또는 GitHub 문서를 확인할 수 있습니다.',
  publicAccessDocsLocalTunnel: '로컬 터널 가이드',
  publicAccessDocsCloudRun: 'Cloud Run 배포 가이드',
  publicAccessDocsGitHub: 'GitHub 문서',
  publicAccessMode: '배포 방식',
  publicAccessModeNone: '없음',
  publicAccessModeLocalTunnel: '로컬 터널',
  publicAccessModeCloudRun: 'Cloud Run',
  publicAccessModeCustom: '사용자 지정',
  publicAccessUrlPlaceholder: 'https://example.com',
  publicAccessConfiguredUrl: '구성된 공개 URL',
  publicAccessCursorUrl: 'Cursor Override OpenAI Base URL',
  publicAccessSource: '유효 URL 출처',
  publicAccessSourceConfig: '명시적 구성값',
  publicAccessSourceRequestOrigin: '현재 요청에서 자동 감지',
  publicAccessSourceNgrokApi: '로컬 ngrok API에서 자동 감지',
  publicAccessSourceNone: '사용 가능한 공개 URL 없음',
  publicAccessCursorHint: 'Cursor에는 공개 HTTPS 루트 URL을 입력하고 `/v1`은 붙이지 마세요.',
  publicAccessCursorGuide:
    '위의 URL을 Cursor --> Settings --> Models --> API Keys --> Override OpenAI Base URL 아래의 입력 상자에 복사한 후 스위치를 켜고, "OpenAI API Key"를 열어 임의의 문자를 입력하세요. "Models"에서 "View All Models"를 클릭하고 "Add Custom Model"을 켠 다음 "ternion-team"을 입력하면 ternion 사용을 시작할 수 있습니다!',
  publicAccessAutoDetectedNote:
    '이 URL은 현재 공개 요청 또는 로컬 ngrok API에서 자동 감지된 값으로, Cloud Run, 리버스 프록시 배포, 로컬 터널에 유용합니다.',
  publicAccessCopy: '복사',
  publicAccessCopied: 'Cursor Base URL이 복사되었습니다',
  publicAccessCopyFailed: 'Cursor Base URL 복사에 실패했습니다',
  publicAccessTokenLabel: '액세스 토큰',
  publicAccessTokenHint: '공개 터널을 통한 요청에 필수',
  publicAccessTokenDescription:
    '이 토큰을 Cursor의 OpenAI API Key 필드에 붙여넣으세요. 원격 컨트롤 패널 접근에도 필요하며, 로컬 요청에는 필요하지 않습니다.',
  accessTokenGateTitle: '액세스 토큰이 필요합니다',
  accessTokenGateDescription:
    '현재 공개 터널을 통해 컨트롤 패널에 접근하고 있습니다. Ternion 시작 배너에 표시된 액세스 토큰을 입력하세요(로컬 패널 세션에서 복사할 수도 있습니다).',
  accessTokenGatePlaceholder: '액세스 토큰 붙여넣기',
  accessTokenGateSubmit: '계속',
  publicAccessSaved: '공개 액세스 설정이 저장되었습니다',
  publicAccessUnavailable: '현재 공개 액세스 설정을 불러올 수 없습니다.',
  publicAccessConfiguredToast:
    '공개 액세스를 감지했습니다. Ports 탭에서 Cursor Base URL을 복사하세요.',
  publicAccessIntroTitle: '공개 HTTPS URL이 필요합니다',
  publicAccessIntroBody:
    'Cursor의 Override OpenAI Base URL은 localhost나 로컬 전용 주소를 허용하지 않습니다.\nCursor에서 Ternion에 연결하려면 이 서비스를 공개 HTTPS URL로 노출해야 합니다.',
  publicAccessIntroOk: '확인',
  publicAccessIntroGuide: '설정 방법',
  publicAccessGuideTitle: '공개 액세스 설정 방법',
  publicAccessGuideBody:
    'ngrok 예시:\n1. ngrok을 설치하고 계정에 로그인합니다.\n2. Ternion이 실행 중인 머신에서 `ngrok http 9110`을 실행합니다.\n3. 생성된 공개 HTTPS 루트 URL을 복사합니다.\n4. 그 루트 URL을 Cursor의 Override OpenAI Base URL에 붙여 넣습니다.\n5. `/v1`은 추가하지 마세요.\n\nTernion을 Cloud Run에 배포한 경우에는 서비스의 공개 HTTPS origin을 그대로 사용할 수도 있습니다.',
  publicAccessGuideClose: '닫기',

  // Usage Dashboard
  usageTitle: '📊 사용 통계',
  usageMonth: '월',
  usageTotal: '총 비용',
  usageRemaining: '남은 금액',
  usageRequests: '요청 수',
  usageByProvider: '공급자별 비용',
  usageNoData: '사용 데이터 없음',
  usageDisclaimer: '여기에 표시된 사용량 데이터는 추정치이며 실제 청구 금액과 다를 수 있습니다. 정확한 비용은 API 제공업체의 청구 대시보드를 참조하세요.',
  usageDontRemind: '다시 표시 안 함',
  usageDailyUsage: '일별 사용량',
  usageMonthlyUsage: '월별 사용량',
  usageAllProviders: '모든 제공자',
  usageAllTokens: '모든 토큰',
  usageCost: '비용',
  usageInputTokens: '입력 토큰',
  usageOutputTokens: '출력 토큰',
  usageThoughtsTokens: '생각 토큰',
  usagePercentage: '사용 금액',
  usageModifyBudget: '수정',
  usageCurrentBudget: '현재 예산 한도',
  usageChangeTo: '변경',
  usageConfirm: '확인',
  loading: '로딩 중...',

  // Common UI
  unnamed: '이름 없음',
  delete: '삭제',
  toggleVisibility: '가시성 전환',
  confirmDeleteApiKey: '이 API 키를 삭제하시겠습니까?',

  // API Response Codes
  code_SUCCESS: '연결 성공',
  code_AUTH_ERROR: '잘못된 API 키',
  code_CONNECTION_ERROR: '연결 실패',
  code_UNKNOWN_ERROR: '알 수 없는 오류',
  code_INVALID_PROVIDER: '잘못된 공급자',
  code_PROVIDER_NOT_FOUND: '공급자를 찾을 수 없음',
  code_API_KEY_NOT_FOUND: 'API 키를 찾을 수 없음',
  code_API_KEY_DUPLICATE: '이 API 키는 이미 존재합니다',
  code_PROVIDER_NOT_ENABLED: '공급자가 활성화되지 않음',
  code_MODEL_NOT_AVAILABLE: '모델을 사용할 수 없음',
  code_MODEL_UNAVAILABLE: '선택한 모델은 현재 해당 공급자에서 더 이상 사용할 수 없습니다',
  code_MODEL_PROBE_AUTH_ERROR: '모델 검증에 실패했습니다. 현재 공급자 API 키가 유효하지 않거나 권한이 없습니다',
  code_MODEL_PROBE_TIMEOUT: '모델 검증 시간이 초과되었습니다. 다시 시도해 주세요',
  code_MODEL_PROBE_CONNECTION_ERROR: '모델 검증에 실패했습니다. 현재 공급자에 연결할 수 없습니다',
  code_INVALID_BUDGET_LIMIT: '잘못된 예산 한도',
  code_INVALID_BUDGET_THRESHOLD: '잘못된 예산 임계값',
  code_BUDGET_EXCEEDED: '월간 예산 초과',
  code_BUDGET_WARNING: '예산 한도 근접',
  code_STREAM_INTERRUPTED: '전송 중단, 다시 시도해 주세요',
  code_ROLES_INCOMPLETE: '저장하기 전에 모든 역할을 구성하세요',
  code_ROLES_INCOMPLETE_SUFFIX: '（누락：{roles}）',
  code_MODEL_CATALOG_REFRESH_FAILED: 'Model catalog refresh failed',
  code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'Catalog anomaly report not found',
  code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Invalid automatic refresh mode',
  code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Invalid automatic refresh time',
  code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: 'Invalid automatic refresh interval',
  code_INVALID_PUBLIC_ACCESS_MODE: '공개 액세스 모드가 올바르지 않습니다',
  code_INVALID_PUBLIC_BASE_URL: '공개 HTTPS URL이 올바르지 않습니다',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '알 수 없는 오류',
  successConnected: '연결 성공',
  modelCatalogTitle: 'Model Catalog',
  modelCatalogDescription: 'Initialize, refresh, and schedule LiteLLM model catalog updates.',
  modelCatalogInitialize: 'Initialize Model List',
  modelCatalogInitializing: 'Initializing...',
  modelCatalogRefreshNow: 'Refresh Model List',
  modelCatalogRefreshing: 'Refreshing...',
  modelCatalogInitSuccess: 'Model catalog initialized successfully',
  modelCatalogInitFailed: 'Failed to initialize model catalog',
  modelCatalogInitAnomaly: 'Model catalog initialized, but an anomaly was detected',
  modelCatalogRefreshSuccess: 'Model catalog refreshed successfully',
  modelCatalogRefreshFailed: 'Failed to refresh model catalog',
  modelCatalogRefreshAnomaly: 'Model catalog refresh completed, but an anomaly was detected',
  modelCatalogStatus: 'Catalog status',
  modelCatalogStatusReady: 'Ready',
  modelCatalogStatusNeedsInitialization: 'Initialization required',
  modelCatalogFirstUseBanner: 'First time using Ternion? Please initialize the model list.',
  modelCatalogModelCount: 'Available models',
  modelCatalogCatalogUpdatedAt: 'Catalog updated at',
  modelCatalogScheduleTitle: 'Automatic Refresh',
  modelCatalogScheduleDescription: 'Configure periodic background refreshes for the model catalog.',
  modelCatalogScheduleEnabled: 'Enable automatic refresh',
  modelCatalogScheduleMode: 'Refresh frequency',
  modelCatalogScheduleDaily: 'Every day',
  modelCatalogScheduleDays: 'Every X days',
  modelCatalogScheduleWeeks: 'Every X weeks',
  modelCatalogScheduleTime: 'Time of day',
  modelCatalogScheduleInterval: 'Interval value',
  modelCatalogScheduleSaved: 'Automatic refresh settings saved',
  modelCatalogLastRefreshAt: 'Last refresh at',
  modelCatalogNextRefreshAt: 'Next refresh at',
  modelCatalogAnomalyBanner: 'Model catalog anomaly detected',
  modelCatalogAnomalyHelp: 'Please check provider configuration, network connectivity, or wait for filtering rules to be updated.',
  modelCatalogAnomalyUpdatedAt: 'Anomaly updated at',
  modelCatalogRetry: 'Retry',
  modelCatalogViewDetails: 'View Details',
  modelCatalogDetailsTitle: 'Catalog Anomaly Report',

  // Toast messages
  toastConfigSaved: '설정 저장됨',
  toastNotConfigured: '구성되지 않음',
  toastMissingRolesForTernionFull: 'Ternion Full 모드가 선택되었습니다. 누락된 모델을 구성해 주세요: {roles}',

  // Footer
  footerApiDocs: 'API 문서',
  footerVersion: 'Ternion v0.4.8',

  // Language toggle
  languageToggle: '언어',

  // Observability Panel
  logsTitle: '실시간 로그',
  logsDescription: '백엔드 처리 실시간 로그',
  logsConnecting: '연결 중...',
  logsConnected: '연결됨',
  logsDisconnected: '연결 끊김',
  logsClear: '지우기',
  logsAutoScroll: '자동 스크롤',
  logsNoLogs: '아직 로그가 없습니다',
  logsDownload: '내보내기',
  logsDownloading: '내보내는 중...',
  logsDownloadSuccess: '로그 내보내기 완료',
  logsDownloadError: '로그 내보내기 실패',
  logsDownloadedTo: '저장 위치',
  logsEntriesCount: '개 항목',
  logsOpenFile: '파일 관리자에서 보기',
  logsDismiss: '닫기',

  // Settings Dropdown
  settingsTitle: '설정',
  settingsTheme: '테마',
  settingsThemeLight: '라이트',
  settingsThemeDark: '다크',
  settingsThemeSystem: '시스템',
  settingsLanguage: '언어',
  settingsLanguageAuto: '자동',
  settingsConfigLabel: '설정 파일',
  settingsConfigRestoreHint: '손상 시 백업에서 복원',

  // Execution Mode Selector
  execModeTitle: '실행 모드',
  execModeDescription: 'Ternion 분석 확인 후 실행 모드를 선택하세요',
  execModeRecommended: '추천',
  execModeCursorTitle: 'Ternion 근본 원인 분석 + Cursor 구현',
  execModeTernionTitle: 'Ternion 근본 원인 분석 + 코드 구현',
  execModePros: '✓ 장점',
  execModeCons: '✗ 단점',
  execModeCursorPro1: '저비용, 분석 단계 토큰만 소비',
  execModeCursorPro2: '네이티브 Cursor 코드 구현 경험',
  execModeCursorPro3: '언제든지 다른 Cursor 모델로 전환 가능',
  execModeCursorCon1: '코드 사용성 및 보안 리뷰 없음',
  execModeCursorCon2: '코드 품질은 Cursor 모델에 의존',
  execModeTernionPro1: 'Ternion Agent의 코드 작성 및 리뷰 완전한 워크플로우',
  execModeTernionPro2: '리뷰어가 코드 사용성 및 보안 리뷰 수행',
  execModeTernionPro3: '더 높은 코드 품질',
  execModeTernionCon1: '고비용, 전체 워크플로우에 더 많은 토큰 필요',
  execModeTernionCon2: '응답 시간이 더 김',
  execModeSave: '저장',
  execModeSaving: '저장 중...',
  execModeDisabledHint: 'Cursor가 코드 생성 담당, 구성 불필요',
  statusExecModeNotSelected: '실행 모드 미선택',
  statusExecModeSelected: '실행 모드',
};

type ModelCatalogTranslationOverrides = Pick<
  Translations,
  | 'code_MODEL_CATALOG_REFRESH_FAILED'
  | 'code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND'
  | 'code_INVALID_MODEL_CATALOG_REFRESH_MODE'
  | 'code_INVALID_MODEL_CATALOG_REFRESH_TIME'
  | 'code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL'
  | 'modelCatalogTitle'
  | 'modelCatalogDescription'
  | 'modelCatalogInitialize'
  | 'modelCatalogInitializing'
  | 'modelCatalogRefreshNow'
  | 'modelCatalogRefreshing'
  | 'modelCatalogInitSuccess'
  | 'modelCatalogInitFailed'
  | 'modelCatalogInitAnomaly'
  | 'modelCatalogRefreshSuccess'
  | 'modelCatalogRefreshFailed'
  | 'modelCatalogRefreshAnomaly'
  | 'modelCatalogStatus'
  | 'modelCatalogStatusReady'
  | 'modelCatalogStatusNeedsInitialization'
  | 'modelCatalogFirstUseBanner'
  | 'modelCatalogModelCount'
  | 'modelCatalogCatalogUpdatedAt'
  | 'modelCatalogScheduleTitle'
  | 'modelCatalogScheduleDescription'
  | 'modelCatalogScheduleEnabled'
  | 'modelCatalogScheduleMode'
  | 'modelCatalogScheduleDaily'
  | 'modelCatalogScheduleDays'
  | 'modelCatalogScheduleWeeks'
  | 'modelCatalogScheduleTime'
  | 'modelCatalogScheduleInterval'
  | 'modelCatalogScheduleSaved'
  | 'modelCatalogLastRefreshAt'
  | 'modelCatalogNextRefreshAt'
  | 'modelCatalogAnomalyBanner'
  | 'modelCatalogAnomalyHelp'
  | 'modelCatalogAnomalyUpdatedAt'
  | 'modelCatalogRetry'
  | 'modelCatalogViewDetails'
  | 'modelCatalogDetailsTitle'
>;

const MODEL_CATALOG_TRANSLATIONS: Record<Language, ModelCatalogTranslationOverrides> = {
  en: {
    code_MODEL_CATALOG_REFRESH_FAILED: 'Model catalog refresh failed',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'Catalog anomaly report not found',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Invalid automatic refresh mode',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Invalid automatic refresh time',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: 'Invalid automatic refresh interval',
    modelCatalogTitle: 'Model Catalog',
    modelCatalogDescription: 'Initialize, refresh, and schedule LiteLLM model catalog updates.',
    modelCatalogInitialize: 'Initialize Model List',
    modelCatalogInitializing: 'Initializing...',
    modelCatalogRefreshNow: 'Refresh Model List',
    modelCatalogRefreshing: 'Refreshing...',
    modelCatalogInitSuccess: 'Model catalog initialized successfully',
    modelCatalogInitFailed: 'Failed to initialize model catalog',
    modelCatalogInitAnomaly: 'Model catalog initialized, but an anomaly was detected',
    modelCatalogRefreshSuccess: 'Model catalog refreshed successfully',
    modelCatalogRefreshFailed: 'Failed to refresh model catalog',
    modelCatalogRefreshAnomaly: 'Model catalog refresh completed, but an anomaly was detected',
    modelCatalogStatus: 'Catalog status',
    modelCatalogStatusReady: 'Ready',
    modelCatalogStatusNeedsInitialization: 'Initialization required',
    modelCatalogFirstUseBanner: 'First time using Ternion? Please initialize the model list.',
    modelCatalogModelCount: 'Available models',
    modelCatalogCatalogUpdatedAt: 'Catalog updated at',
    modelCatalogScheduleTitle: 'Automatic Refresh',
    modelCatalogScheduleDescription: 'Configure periodic background refreshes for the model catalog.',
    modelCatalogScheduleEnabled: 'Enable automatic refresh',
    modelCatalogScheduleMode: 'Refresh frequency',
    modelCatalogScheduleDaily: 'Every day',
    modelCatalogScheduleDays: 'Every X days',
    modelCatalogScheduleWeeks: 'Every X weeks',
    modelCatalogScheduleTime: 'Time of day',
    modelCatalogScheduleInterval: 'Interval value',
    modelCatalogScheduleSaved: 'Automatic refresh settings saved',
    modelCatalogLastRefreshAt: 'Last refresh at',
    modelCatalogNextRefreshAt: 'Next refresh at',
    modelCatalogAnomalyBanner: 'Model catalog anomaly detected',
    modelCatalogAnomalyHelp:
      'Please check provider configuration, network connectivity, or wait for filtering rules to be updated.',
    modelCatalogAnomalyUpdatedAt: 'Anomaly updated at',
    modelCatalogRetry: 'Retry',
    modelCatalogViewDetails: 'View Details',
    modelCatalogDetailsTitle: 'Catalog Anomaly Report',
  },
  zh: {
    code_MODEL_CATALOG_REFRESH_FAILED: '模型列表刷新失败',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: '未找到模型目录异常报告',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: '自动刷新模式无效',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: '自动刷新时间无效',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '自动刷新间隔无效',
    modelCatalogTitle: '模型目录管理',
    modelCatalogDescription: '初始化、手动刷新并配置 LiteLLM 模型目录的定时更新。',
    modelCatalogInitialize: '初始化模型列表',
    modelCatalogInitializing: '初始化中...',
    modelCatalogRefreshNow: '刷新模型列表',
    modelCatalogRefreshing: '刷新中...',
    modelCatalogInitSuccess: '模型列表初始化成功',
    modelCatalogInitFailed: '模型列表初始化失败',
    modelCatalogInitAnomaly: '模型列表已初始化，但检测到目录异常',
    modelCatalogRefreshSuccess: '模型列表刷新成功',
    modelCatalogRefreshFailed: '模型列表刷新失败',
    modelCatalogRefreshAnomaly: '模型列表刷新完成，但检测到目录异常',
    modelCatalogStatus: '目录状态',
    modelCatalogStatusReady: '可用',
    modelCatalogStatusNeedsInitialization: '需要初始化',
    modelCatalogFirstUseBanner: '您是初次使用，请先初始化模型列表',
    modelCatalogModelCount: '可用模型数',
    modelCatalogCatalogUpdatedAt: '目录更新时间',
    modelCatalogScheduleTitle: '自动刷新',
    modelCatalogScheduleDescription: '配置后台定时更新模型目录的计划。',
    modelCatalogScheduleEnabled: '启用自动刷新',
    modelCatalogScheduleMode: '刷新频率',
    modelCatalogScheduleDaily: '每天固定时间',
    modelCatalogScheduleDays: '每隔 X 天',
    modelCatalogScheduleWeeks: '每隔 X 周',
    modelCatalogScheduleTime: '刷新时间',
    modelCatalogScheduleInterval: '间隔值',
    modelCatalogScheduleSaved: '自动刷新设置已保存',
    modelCatalogLastRefreshAt: '上次刷新时间',
    modelCatalogNextRefreshAt: '下次刷新时间',
    modelCatalogAnomalyBanner: '模型列表获取异常，请检查 provider 配置、网络或等待规则更新',
    modelCatalogAnomalyHelp: '建议检查 provider 配置、网络连通性，或等待过滤规则更新后再重试。',
    modelCatalogAnomalyUpdatedAt: '异常更新时间',
    modelCatalogRetry: '重试',
    modelCatalogViewDetails: '查看详情',
    modelCatalogDetailsTitle: '模型目录异常报告',
  },
  es: {
    code_MODEL_CATALOG_REFRESH_FAILED: 'La actualización del catálogo de modelos falló',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND:
      'No se encontró el informe de anomalías del catálogo',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Modo de actualización automática no válido',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Hora de actualización automática no válida',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL:
      'Intervalo de actualización automática no válido',
    modelCatalogTitle: 'Catálogo de Modelos',
    modelCatalogDescription:
      'Inicializa, actualiza y programa actualizaciones del catálogo de modelos de LiteLLM.',
    modelCatalogInitialize: 'Inicializar lista de modelos',
    modelCatalogInitializing: 'Inicializando...',
    modelCatalogRefreshNow: 'Actualizar lista de modelos',
    modelCatalogRefreshing: 'Actualizando...',
    modelCatalogInitSuccess: 'El catálogo de modelos se inicializó correctamente',
    modelCatalogInitFailed: 'No se pudo inicializar el catálogo de modelos',
    modelCatalogInitAnomaly:
      'El catálogo de modelos se inicializó, pero se detectó una anomalía',
    modelCatalogRefreshSuccess: 'El catálogo de modelos se actualizó correctamente',
    modelCatalogRefreshFailed: 'No se pudo actualizar el catálogo de modelos',
    modelCatalogRefreshAnomaly:
      'La actualización del catálogo terminó, pero se detectó una anomalía',
    modelCatalogStatus: 'Estado del catálogo',
    modelCatalogStatusReady: 'Listo',
    modelCatalogStatusNeedsInitialization: 'Se requiere inicialización',
    modelCatalogFirstUseBanner: '¿Es la primera vez que usa Ternion? Inicialice la lista de modelos.',
    modelCatalogModelCount: 'Modelos disponibles',
    modelCatalogCatalogUpdatedAt: 'Catálogo actualizado el',
    modelCatalogScheduleTitle: 'Actualización automática',
    modelCatalogScheduleDescription:
      'Configure actualizaciones periódicas en segundo plano para el catálogo de modelos.',
    modelCatalogScheduleEnabled: 'Habilitar actualización automática',
    modelCatalogScheduleMode: 'Frecuencia de actualización',
    modelCatalogScheduleDaily: 'Todos los días',
    modelCatalogScheduleDays: 'Cada X días',
    modelCatalogScheduleWeeks: 'Cada X semanas',
    modelCatalogScheduleTime: 'Hora del día',
    modelCatalogScheduleInterval: 'Valor del intervalo',
    modelCatalogScheduleSaved: 'Configuración de actualización automática guardada',
    modelCatalogLastRefreshAt: 'Última actualización',
    modelCatalogNextRefreshAt: 'Próxima actualización',
    modelCatalogAnomalyBanner: 'Se detectó una anomalía en el catálogo de modelos',
    modelCatalogAnomalyHelp:
      'Revise la configuración del proveedor, la conectividad de red o espere a que se actualicen las reglas de filtrado.',
    modelCatalogAnomalyUpdatedAt: 'Anomalía actualizada el',
    modelCatalogRetry: 'Reintentar',
    modelCatalogViewDetails: 'Ver detalles',
    modelCatalogDetailsTitle: 'Informe de anomalías del catálogo',
  },
  fr: {
    code_MODEL_CATALOG_REFRESH_FAILED: 'L’actualisation du catalogue de modèles a échoué',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND:
      'Rapport d’anomalie du catalogue introuvable',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Mode d’actualisation automatique invalide',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Heure d’actualisation automatique invalide',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL:
      'Intervalle d’actualisation automatique invalide',
    modelCatalogTitle: 'Catalogue de modèles',
    modelCatalogDescription:
      'Initialisez, actualisez et planifiez les mises à jour du catalogue de modèles LiteLLM.',
    modelCatalogInitialize: 'Initialiser la liste des modèles',
    modelCatalogInitializing: 'Initialisation...',
    modelCatalogRefreshNow: 'Actualiser la liste des modèles',
    modelCatalogRefreshing: 'Actualisation...',
    modelCatalogInitSuccess: 'Le catalogue de modèles a été initialisé avec succès',
    modelCatalogInitFailed: 'Impossible d’initialiser le catalogue de modèles',
    modelCatalogInitAnomaly:
      'Le catalogue de modèles a été initialisé, mais une anomalie a été détectée',
    modelCatalogRefreshSuccess: 'Le catalogue de modèles a été actualisé avec succès',
    modelCatalogRefreshFailed: 'Impossible d’actualiser le catalogue de modèles',
    modelCatalogRefreshAnomaly:
      'L’actualisation du catalogue est terminée, mais une anomalie a été détectée',
    modelCatalogStatus: 'État du catalogue',
    modelCatalogStatusReady: 'Prêt',
    modelCatalogStatusNeedsInitialization: 'Initialisation requise',
    modelCatalogFirstUseBanner: 'Première utilisation de Ternion ? Veuillez initialiser la liste des modèles.',
    modelCatalogModelCount: 'Modèles disponibles',
    modelCatalogCatalogUpdatedAt: 'Catalogue mis à jour le',
    modelCatalogScheduleTitle: 'Actualisation automatique',
    modelCatalogScheduleDescription:
      'Configurez des actualisations périodiques en arrière-plan pour le catalogue de modèles.',
    modelCatalogScheduleEnabled: 'Activer l’actualisation automatique',
    modelCatalogScheduleMode: 'Fréquence d’actualisation',
    modelCatalogScheduleDaily: 'Chaque jour',
    modelCatalogScheduleDays: 'Tous les X jours',
    modelCatalogScheduleWeeks: 'Toutes les X semaines',
    modelCatalogScheduleTime: 'Heure de la journée',
    modelCatalogScheduleInterval: 'Valeur de l’intervalle',
    modelCatalogScheduleSaved: 'Paramètres d’actualisation automatique enregistrés',
    modelCatalogLastRefreshAt: 'Dernière actualisation',
    modelCatalogNextRefreshAt: 'Prochaine actualisation',
    modelCatalogAnomalyBanner: 'Une anomalie du catalogue de modèles a été détectée',
    modelCatalogAnomalyHelp:
      'Vérifiez la configuration du fournisseur, la connectivité réseau ou attendez la mise à jour des règles de filtrage.',
    modelCatalogAnomalyUpdatedAt: 'Anomalie mise à jour le',
    modelCatalogRetry: 'Réessayer',
    modelCatalogViewDetails: 'Voir les détails',
    modelCatalogDetailsTitle: 'Rapport d’anomalie du catalogue',
  },
  de: {
    code_MODEL_CATALOG_REFRESH_FAILED: 'Aktualisierung des Modellkatalogs fehlgeschlagen',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND:
      'Anomaliebericht zum Modellkatalog nicht gefunden',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: 'Ungültiger automatischer Aktualisierungsmodus',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: 'Ungültige automatische Aktualisierungszeit',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL:
      'Ungültiges automatisches Aktualisierungsintervall',
    modelCatalogTitle: 'Modellkatalog',
    modelCatalogDescription:
      'Initialisieren, aktualisieren und planen Sie Aktualisierungen des LiteLLM-Modellkatalogs.',
    modelCatalogInitialize: 'Modellliste initialisieren',
    modelCatalogInitializing: 'Initialisierung...',
    modelCatalogRefreshNow: 'Modellliste aktualisieren',
    modelCatalogRefreshing: 'Aktualisierung...',
    modelCatalogInitSuccess: 'Der Modellkatalog wurde erfolgreich initialisiert',
    modelCatalogInitFailed: 'Der Modellkatalog konnte nicht initialisiert werden',
    modelCatalogInitAnomaly:
      'Der Modellkatalog wurde initialisiert, aber es wurde eine Anomalie erkannt',
    modelCatalogRefreshSuccess: 'Der Modellkatalog wurde erfolgreich aktualisiert',
    modelCatalogRefreshFailed: 'Der Modellkatalog konnte nicht aktualisiert werden',
    modelCatalogRefreshAnomaly:
      'Die Aktualisierung des Modellkatalogs wurde abgeschlossen, aber es wurde eine Anomalie erkannt',
    modelCatalogStatus: 'Katalogstatus',
    modelCatalogStatusReady: 'Bereit',
    modelCatalogStatusNeedsInitialization: 'Initialisierung erforderlich',
    modelCatalogFirstUseBanner: 'Verwenden Sie Ternion zum ersten Mal? Bitte initialisieren Sie die Modellliste.',
    modelCatalogModelCount: 'Verfügbare Modelle',
    modelCatalogCatalogUpdatedAt: 'Katalog aktualisiert am',
    modelCatalogScheduleTitle: 'Automatische Aktualisierung',
    modelCatalogScheduleDescription:
      'Konfigurieren Sie periodische Hintergrundaktualisierungen für den Modellkatalog.',
    modelCatalogScheduleEnabled: 'Automatische Aktualisierung aktivieren',
    modelCatalogScheduleMode: 'Aktualisierungshäufigkeit',
    modelCatalogScheduleDaily: 'Jeden Tag',
    modelCatalogScheduleDays: 'Alle X Tage',
    modelCatalogScheduleWeeks: 'Alle X Wochen',
    modelCatalogScheduleTime: 'Uhrzeit',
    modelCatalogScheduleInterval: 'Intervallwert',
    modelCatalogScheduleSaved:
      'Einstellungen für die automatische Aktualisierung wurden gespeichert',
    modelCatalogLastRefreshAt: 'Letzte Aktualisierung',
    modelCatalogNextRefreshAt: 'Nächste Aktualisierung',
    modelCatalogAnomalyBanner: 'Eine Anomalie im Modellkatalog wurde erkannt',
    modelCatalogAnomalyHelp:
      'Bitte prüfen Sie die Anbieter-Konfiguration, die Netzwerkverbindung oder warten Sie auf aktualisierte Filterregeln.',
    modelCatalogAnomalyUpdatedAt: 'Anomalie aktualisiert am',
    modelCatalogRetry: 'Erneut versuchen',
    modelCatalogViewDetails: 'Details anzeigen',
    modelCatalogDetailsTitle: 'Anomaliebericht zum Katalog',
  },
  ja: {
    code_MODEL_CATALOG_REFRESH_FAILED: 'モデルカタログの更新に失敗しました',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: 'カタログ異常レポートが見つかりません',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: '自動更新モードが無効です',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: '自動更新時刻が無効です',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '自動更新間隔が無効です',
    modelCatalogTitle: 'モデルカタログ',
    modelCatalogDescription: 'LiteLLM モデルカタログの初期化、手動更新、定期更新を設定します。',
    modelCatalogInitialize: 'モデル一覧を初期化',
    modelCatalogInitializing: '初期化中...',
    modelCatalogRefreshNow: 'モデル一覧を更新',
    modelCatalogRefreshing: '更新中...',
    modelCatalogInitSuccess: 'モデルカタログの初期化に成功しました',
    modelCatalogInitFailed: 'モデルカタログの初期化に失敗しました',
    modelCatalogInitAnomaly: 'モデルカタログは初期化されましたが、異常が検出されました',
    modelCatalogRefreshSuccess: 'モデルカタログの更新に成功しました',
    modelCatalogRefreshFailed: 'モデルカタログの更新に失敗しました',
    modelCatalogRefreshAnomaly:
      'モデルカタログの更新は完了しましたが、異常が検出されました',
    modelCatalogStatus: 'カタログ状態',
    modelCatalogStatusReady: '利用可能',
    modelCatalogStatusNeedsInitialization: '初期化が必要です',
    modelCatalogFirstUseBanner: 'Ternionを初めてご利用ですか？モデル一覧を初期化してください。',
    modelCatalogModelCount: '利用可能なモデル数',
    modelCatalogCatalogUpdatedAt: 'カタログ更新日時',
    modelCatalogScheduleTitle: '自動更新',
    modelCatalogScheduleDescription:
      'モデルカタログの定期バックグラウンド更新を設定します。',
    modelCatalogScheduleEnabled: '自動更新を有効化',
    modelCatalogScheduleMode: '更新頻度',
    modelCatalogScheduleDaily: '毎日',
    modelCatalogScheduleDays: 'X日ごと',
    modelCatalogScheduleWeeks: 'X週間ごと',
    modelCatalogScheduleTime: '更新時刻',
    modelCatalogScheduleInterval: '間隔値',
    modelCatalogScheduleSaved: '自動更新設定を保存しました',
    modelCatalogLastRefreshAt: '前回の更新日時',
    modelCatalogNextRefreshAt: '次回の更新日時',
    modelCatalogAnomalyBanner: 'モデルカタログの異常が検出されました',
    modelCatalogAnomalyHelp:
      'プロバイダー設定やネットワーク接続を確認するか、フィルタールールの更新をお待ちください。',
    modelCatalogAnomalyUpdatedAt: '異常更新日時',
    modelCatalogRetry: '再試行',
    modelCatalogViewDetails: '詳細を見る',
    modelCatalogDetailsTitle: 'カタログ異常レポート',
  },
  ko: {
    code_MODEL_CATALOG_REFRESH_FAILED: '모델 카탈로그 새로고침에 실패했습니다',
    code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND: '카탈로그 이상 보고서를 찾을 수 없습니다',
    code_INVALID_MODEL_CATALOG_REFRESH_MODE: '자동 새로고침 모드가 올바르지 않습니다',
    code_INVALID_MODEL_CATALOG_REFRESH_TIME: '자동 새로고침 시간이 올바르지 않습니다',
    code_INVALID_MODEL_CATALOG_REFRESH_INTERVAL: '자동 새로고침 간격이 올바르지 않습니다',
    modelCatalogTitle: '모델 카탈로그',
    modelCatalogDescription:
      'LiteLLM 모델 카탈로그의 초기화, 수동 새로고침, 예약 갱신을 설정합니다.',
    modelCatalogInitialize: '모델 목록 초기화',
    modelCatalogInitializing: '초기화 중...',
    modelCatalogRefreshNow: '모델 목록 새로고침',
    modelCatalogRefreshing: '새로고침 중...',
    modelCatalogInitSuccess: '모델 카탈로그가 성공적으로 초기화되었습니다',
    modelCatalogInitFailed: '모델 카탈로그를 초기화하지 못했습니다',
    modelCatalogInitAnomaly: '모델 카탈로그가 초기화되었지만 이상이 감지되었습니다',
    modelCatalogRefreshSuccess: '모델 카탈로그가 성공적으로 새로고침되었습니다',
    modelCatalogRefreshFailed: '모델 카탈로그를 새로고침하지 못했습니다',
    modelCatalogRefreshAnomaly:
      '모델 카탈로그 새로고침은 완료되었지만 이상이 감지되었습니다',
    modelCatalogStatus: '카탈로그 상태',
    modelCatalogStatusReady: '준비됨',
    modelCatalogStatusNeedsInitialization: '초기화 필요',
    modelCatalogFirstUseBanner: 'Ternion을 처음 사용하시나요? 모델 목록을 초기화해주세요.',
    modelCatalogModelCount: '사용 가능한 모델 수',
    modelCatalogCatalogUpdatedAt: '카탈로그 갱신 시각',
    modelCatalogScheduleTitle: '자동 새로고침',
    modelCatalogScheduleDescription:
      '모델 카탈로그의 주기적인 백그라운드 새로고침을 설정합니다.',
    modelCatalogScheduleEnabled: '자동 새로고침 활성화',
    modelCatalogScheduleMode: '새로고침 주기',
    modelCatalogScheduleDaily: '매일',
    modelCatalogScheduleDays: 'X일마다',
    modelCatalogScheduleWeeks: 'X주마다',
    modelCatalogScheduleTime: '시간',
    modelCatalogScheduleInterval: '간격 값',
    modelCatalogScheduleSaved: '자동 새로고침 설정이 저장되었습니다',
    modelCatalogLastRefreshAt: '마지막 새로고침 시각',
    modelCatalogNextRefreshAt: '다음 새로고침 시각',
    modelCatalogAnomalyBanner: '모델 카탈로그 이상이 감지되었습니다',
    modelCatalogAnomalyHelp:
      '공급자 설정과 네트워크 연결을 확인하거나 필터 규칙이 갱신될 때까지 기다려 주세요.',
    modelCatalogAnomalyUpdatedAt: '이상 갱신 시각',
    modelCatalogRetry: '다시 시도',
    modelCatalogViewDetails: '상세 보기',
    modelCatalogDetailsTitle: '카탈로그 이상 보고서',
  },
};

Object.assign(EN, MODEL_CATALOG_TRANSLATIONS.en);
Object.assign(ZH, MODEL_CATALOG_TRANSLATIONS.zh);
Object.assign(ES, MODEL_CATALOG_TRANSLATIONS.es);
Object.assign(FR, MODEL_CATALOG_TRANSLATIONS.fr);
Object.assign(DE, MODEL_CATALOG_TRANSLATIONS.de);
Object.assign(JA, MODEL_CATALOG_TRANSLATIONS.ja);
Object.assign(KO, MODEL_CATALOG_TRANSLATIONS.ko);

export const translations: Record<Language, Translations> = {
  en: EN,
  zh: ZH,
  es: ES,
  fr: FR,
  de: DE,
  ja: JA,
  ko: KO,
};

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
 * Get translation function for a specific language.
 */
export function getTranslations(lang: Language): Translations {
  return translations[lang];
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
