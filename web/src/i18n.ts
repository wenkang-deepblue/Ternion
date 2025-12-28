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
  errorUnknown: string;
  successConnected: string;

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
  code_INVALID_BUDGET_LIMIT: string;
  code_INVALID_BUDGET_THRESHOLD: string;
  code_BUDGET_EXCEEDED: string;
  code_BUDGET_WARNING: string;
  code_STREAM_INTERRUPTED: string;
  saveChanges: string;
  saving: string;
  noApiKey: string;

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
  loading: string;

  // Common UI
  unnamed: string;
  delete: string;
  confirmDeleteApiKey: string;

  // Toast messages
  toastConfigSaved: string;
  toastNotConfigured: string;

  // Footer
  footerApiDocs: string;

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

  // Settings Dropdown
  settingsTitle: string;
  settingsTheme: string;
  settingsThemeLight: string;
  settingsThemeDark: string;
  settingsThemeSystem: string;
  settingsLanguage: string;
  settingsLanguageAuto: string;
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
  saveChanges: 'Save Changes',
  saving: 'Saving...',
  noApiKey: '(No API Key)',

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
  loading: 'Loading...',

  // Common UI
  unnamed: 'Unnamed',
  delete: 'Delete',
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
  code_INVALID_BUDGET_LIMIT: 'Invalid budget limit',
  code_INVALID_BUDGET_THRESHOLD: 'Invalid budget threshold',
  code_BUDGET_EXCEEDED: 'Monthly budget exceeded',
  code_BUDGET_WARNING: 'Approaching budget limit',
  code_STREAM_INTERRUPTED: 'Stream interrupted, please retry',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Unknown error',
  successConnected: 'Connected successfully',

  // Toast messages
  toastConfigSaved: 'Configuration saved',
  toastNotConfigured: 'not configured',

  // Footer
  footerApiDocs: 'API Docs',

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

  // Settings Dropdown
  settingsTitle: 'Settings',
  settingsTheme: 'Theme',
  settingsThemeLight: 'Light',
  settingsThemeDark: 'Dark',
  settingsThemeSystem: 'System',
  settingsLanguage: 'Language',
  settingsLanguageAuto: 'Auto',
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
  saveChanges: '保存更改',
  saving: '保存中...',
  noApiKey: '(未配置 API Key)',

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
  loading: '加载中...',

  // Common UI
  unnamed: '未命名',
  delete: '删除',
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
  code_INVALID_BUDGET_LIMIT: '无效的预算上限',
  code_INVALID_BUDGET_THRESHOLD: '无效的预算阈值',
  code_BUDGET_EXCEEDED: '本月预算已用尽',
  code_BUDGET_WARNING: '接近预算上限，请注意控制用量',
  code_STREAM_INTERRUPTED: '流式传输中断，请重试',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '未知错误',
  successConnected: '连接成功',

  // Toast messages
  toastConfigSaved: '配置已保存',
  toastNotConfigured: '尚未配置',

  // Footer
  footerApiDocs: 'API 文档',

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

  // Settings Dropdown
  settingsTitle: '设置',
  settingsTheme: '主题',
  settingsThemeLight: '明亮',
  settingsThemeDark: '暗色',
  settingsThemeSystem: '跟随系统',
  settingsLanguage: '语言',
  settingsLanguageAuto: '自动',
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
  saveChanges: 'Guardar Cambios',
  saving: 'Guardando...',
  noApiKey: '(Sin Clave API)',

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
  loading: 'Cargando...',

  // Common UI
  unnamed: 'Sin nombre',
  delete: 'Eliminar',
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
  code_INVALID_BUDGET_LIMIT: 'Límite de presupuesto inválido',
  code_INVALID_BUDGET_THRESHOLD: 'Umbral de presupuesto inválido',
  code_BUDGET_EXCEEDED: 'Presupuesto mensual excedido',
  code_BUDGET_WARNING: 'Acercándose al límite de presupuesto',
  code_STREAM_INTERRUPTED: 'Transmisión interrumpida, por favor reintente',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Error desconocido',
  successConnected: 'Conectado exitosamente',

  // Toast messages
  toastConfigSaved: 'Configuración guardada',
  toastNotConfigured: 'no configurado',

  // Footer
  footerApiDocs: 'Documentación API',

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

  // Settings Dropdown
  settingsTitle: 'Configuración',
  settingsTheme: 'Tema',
  settingsThemeLight: 'Claro',
  settingsThemeDark: 'Oscuro',
  settingsThemeSystem: 'Sistema',
  settingsLanguage: 'Idioma',
  settingsLanguageAuto: 'Auto',
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
  saveChanges: 'Sauvegarder',
  saving: 'Sauvegarde...',
  noApiKey: '(Pas de Clé API)',

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
  loading: 'Chargement...',

  // Common UI
  unnamed: 'Sans nom',
  delete: 'Supprimer',
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
  code_INVALID_BUDGET_LIMIT: 'Limite de budget invalide',
  code_INVALID_BUDGET_THRESHOLD: 'Seuil de budget invalide',
  code_BUDGET_EXCEEDED: 'Budget mensuel dépassé',
  code_BUDGET_WARNING: 'Approche de la limite de budget',
  code_STREAM_INTERRUPTED: 'Transmission interrompue, veuillez réessayer',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Erreur inconnue',
  successConnected: 'Connecté avec succès',

  // Toast messages
  toastConfigSaved: 'Configuration sauvegardée',
  toastNotConfigured: 'non configuré',

  // Footer
  footerApiDocs: 'Documentation API',

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

  // Settings Dropdown
  settingsTitle: 'Paramètres',
  settingsTheme: 'Thème',
  settingsThemeLight: 'Clair',
  settingsThemeDark: 'Sombre',
  settingsThemeSystem: 'Système',
  settingsLanguage: 'Langue',
  settingsLanguageAuto: 'Auto',
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
  saveChanges: 'Änderungen speichern',
  saving: 'Speichern...',
  noApiKey: '(Kein API-Schlüssel)',

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
  loading: 'Laden...',

  // Common UI
  unnamed: 'Unbenannt',
  delete: 'Löschen',
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
  code_INVALID_BUDGET_LIMIT: 'Ungültiges Budget-Limit',
  code_INVALID_BUDGET_THRESHOLD: 'Ungültige Budget-Schwelle',
  code_BUDGET_EXCEEDED: 'Monatsbudget überschritten',
  code_BUDGET_WARNING: 'Budget-Limit nähert sich',
  code_STREAM_INTERRUPTED: 'Übertragung unterbrochen, bitte erneut versuchen',

  // Legacy error keys (for backward compatibility)
  errorUnknown: 'Unbekannter Fehler',
  successConnected: 'Erfolgreich verbunden',

  // Toast messages
  toastConfigSaved: 'Konfiguration gespeichert',
  toastNotConfigured: 'nicht konfiguriert',

  // Footer
  footerApiDocs: 'API-Dokumentation',

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

  // Settings Dropdown
  settingsTitle: 'Einstellungen',
  settingsTheme: 'Thema',
  settingsThemeLight: 'Hell',
  settingsThemeDark: 'Dunkel',
  settingsThemeSystem: 'System',
  settingsLanguage: 'Sprache',
  settingsLanguageAuto: 'Auto',
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
  saveChanges: '保存',
  saving: '保存中...',
  noApiKey: '(APIキーなし)',

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
  loading: '読み込み中...',

  // Common UI
  unnamed: '名前なし',
  delete: '削除',
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
  code_INVALID_BUDGET_LIMIT: '無効な予算上限',
  code_INVALID_BUDGET_THRESHOLD: '無効な予算閾値',
  code_BUDGET_EXCEEDED: '月間予算を超過しました',
  code_BUDGET_WARNING: '予算上限に近づいています',
  code_STREAM_INTERRUPTED: '伝送中断、再試行してください',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '不明なエラー',
  successConnected: '接続成功',

  // Toast messages
  toastConfigSaved: '設定を保存しました',
  toastNotConfigured: '未設定',

  // Footer
  footerApiDocs: 'APIドキュメント',

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

  // Settings Dropdown
  settingsTitle: '設定',
  settingsTheme: 'テーマ',
  settingsThemeLight: 'ライト',
  settingsThemeDark: 'ダーク',
  settingsThemeSystem: 'システム',
  settingsLanguage: '言語',
  settingsLanguageAuto: '自動',
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
  saveChanges: '저장',
  saving: '저장 중...',
  noApiKey: '(API 키 없음)',

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
  loading: '로딩 중...',

  // Common UI
  unnamed: '이름 없음',
  delete: '삭제',
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
  code_INVALID_BUDGET_LIMIT: '잘못된 예산 한도',
  code_INVALID_BUDGET_THRESHOLD: '잘못된 예산 임계값',
  code_BUDGET_EXCEEDED: '월간 예산 초과',
  code_BUDGET_WARNING: '예산 한도 근접',
  code_STREAM_INTERRUPTED: '전송 중단, 다시 시도해 주세요',

  // Legacy error keys (for backward compatibility)
  errorUnknown: '알 수 없는 오류',
  successConnected: '연결 성공',

  // Toast messages
  toastConfigSaved: '설정 저장됨',
  toastNotConfigured: '구성되지 않음',

  // Footer
  footerApiDocs: 'API 문서',

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

  // Settings Dropdown
  settingsTitle: '설정',
  settingsTheme: '테마',
  settingsThemeLight: '라이트',
  settingsThemeDark: '다크',
  settingsThemeSystem: '시스템',
  settingsLanguage: '언어',
  settingsLanguageAuto: '자동',
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
    const lang = (navigator.language || (navigator as any).userLanguage || 'en').toLowerCase();
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
 * Get localized error message from error code.
 * Falls back to the code itself if no translation exists.
 */
export function getErrorMessage(t: Translations, errorCode: string): string {
  // Try to find translation with code_ prefix
  const key = `code_${errorCode}` as keyof Translations;
  if (t[key]) {
    return t[key];
  }
  // Fallback to the error code itself
  return errorCode;
}
