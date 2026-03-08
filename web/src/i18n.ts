/**
 * Internationalization (i18n) module for Ternion Control Panel.
 *
 * Provides translations for English and Chinese languages.
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
  saveChanges: string;
  saving: string;
  noApiKey: string;
  roleNotSaved: string;
  roleSelectionPending: string;
  unsavedLabel: string;

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
  portsWebLabel: string;
  portsCurrentBackend: string;
  portsCurrentWeb: string;
  portsWarning: string;
  portsRestartNote: string;
  portsSaved: string;
  portsInvalid: string;

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
  portsDescription: 'View and modify server port numbers',
  portsBackend: 'Change Ternion Backend API Port',
  portsWeb: 'Change Ternion Web Control Panel Port',
  portsBackendLabel: 'Backend',
  portsWebLabel: 'Web',
  portsCurrentBackend: 'Current Ternion Backend API Port',
  portsCurrentWeb: 'Current Ternion Web Control Panel Port',
  portsWarning: 'Port changes require manual server restart to take effect',
  portsRestartNote: 'After saving, restart the server with the new configuration',
  portsSaved: 'Port configuration saved',
  portsInvalid: 'Invalid port number (1024-65535)',

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
  portsDescription: '查看和修改服务器端口号',
  portsBackend: '更改 Ternion 后端 API 端口',
  portsWeb: '更改 Ternion Web 控制面板端口',
  portsBackendLabel: '后端',
  portsWebLabel: 'Web',
  portsCurrentBackend: '当前 Ternion 后端 API 端口',
  portsCurrentWeb: '当前 Ternion Web 控制面板端口',
  portsWarning: '更改端口后需要手动重启服务才能生效',
  portsRestartNote: '保存后，请使用新配置重启服务器',
  portsSaved: '端口配置已保存',
  portsInvalid: '无效的端口号 (1024-65535)',

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
  portsDescription: 'Ver y modificar números de puerto del servidor',
  portsBackend: 'Cambiar Puerto API Backend de Ternion',
  portsWeb: 'Cambiar Puerto del Panel Web de Ternion',
  portsBackendLabel: 'Backend',
  portsWebLabel: 'Web',
  portsCurrentBackend: 'Puerto API Backend Actual de Ternion',
  portsCurrentWeb: 'Puerto del Panel Web Actual de Ternion',
  portsWarning: 'Los cambios de puerto requieren reinicio manual del servidor',
  portsRestartNote: 'Después de guardar, reinicie el servidor con la nueva configuración',
  portsSaved: 'Configuración de puerto guardada',
  portsInvalid: 'Número de puerto inválido (1024-65535)',

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
  portsDescription: 'Afficher et modifier les numéros de port du serveur',
  portsBackend: 'Modifier le Port API Backend Ternion',
  portsWeb: 'Modifier le Port du Panneau Web Ternion',
  portsBackendLabel: 'Backend',
  portsWebLabel: 'Web',
  portsCurrentBackend: 'Port API Backend Ternion Actuel',
  portsCurrentWeb: 'Port du Panneau Web Ternion Actuel',
  portsWarning: 'Les modifications de port nécessitent un redémarrage manuel du serveur',
  portsRestartNote: 'Après la sauvegarde, redémarrez le serveur avec la nouvelle configuration',
  portsSaved: 'Configuration du port sauvegardée',
  portsInvalid: 'Numéro de port invalide (1024-65535)',

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
  portsDescription: 'Server-Portnummern anzeigen und ändern',
  portsBackend: 'Ternion Backend-API-Port ändern',
  portsWeb: 'Ternion Web-Panel-Port ändern',
  portsBackendLabel: 'Backend',
  portsWebLabel: 'Web',
  portsCurrentBackend: 'Aktueller Ternion Backend-API-Port',
  portsCurrentWeb: 'Aktueller Ternion Web-Panel-Port',
  portsWarning: 'Port-Änderungen erfordern manuellen Server-Neustart',
  portsRestartNote: 'Nach dem Speichern Server mit neuer Konfiguration neu starten',
  portsSaved: 'Port-Konfiguration gespeichert',
  portsInvalid: 'Ungültige Portnummer (1024-65535)',

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
  portsDescription: 'サーバーポート番号の表示と変更',
  portsBackend: 'Ternionバックエンドポート変更',
  portsWeb: 'TernionウェブPanelポート変更',
  portsBackendLabel: 'バックエンド',
  portsWebLabel: 'ウェブ',
  portsCurrentBackend: '現在のTernionバックエンドポート',
  portsCurrentWeb: '現在のTernionウェブPanelポート',
  portsWarning: 'ポート変更はサーバー再起動が必要です',
  portsRestartNote: '保存後、新しい設定でサーバーを再起動してください',
  portsSaved: 'ポート設定を保存しました',
  portsInvalid: '無効なポート番号 (1024-65535)',

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
  portsDescription: '서버 포트 번호 보기 및 변경',
  portsBackend: 'Ternion 백엔드 포트 변경',
  portsWeb: 'Ternion 웹 패널 포트 변경',
  portsBackendLabel: '백엔드',
  portsWebLabel: '웹',
  portsCurrentBackend: '현재 Ternion 백엔드 포트',
  portsCurrentWeb: '현재 Ternion 웹 패널 포트',
  portsWarning: '포트 변경은 서버 재시작이 필요합니다',
  portsRestartNote: '저장 후 새 구성으로 서버를 다시 시작하세요',
  portsSaved: '포트 설정 저장됨',
  portsInvalid: '잘못된 포트 번호 (1024-65535)',

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
