/**
 * Internationalization (i18n) module for Ternion Control Panel.
 *
 * Provides translations for English and Chinese languages.
 * Automatically detects browser language, with manual override for development.
 */

export type Language = 'en' | 'zh';

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
  tabUsage: string;

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
}

const EN: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: 'Multi-Model Collaboration Gateway',
  llmKeysEnabled: 'LLM Key(s) enabled',
  lightMode: 'Switch to light mode',
  darkMode: 'Switch to dark mode',

  // Tabs
  tabConfig: '⚙️ Config',
  tabUsage: '📊 Usage',

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
  apiKeyTitle: '🔑 API Key Management',
  apiKeyDescription: 'Add LLM provider API Keys to enable models',
  apiKeyStorageNote: '(Saved keys stored in: ~/.ternion/config.json)',
  apiKeyPlaceholder: 'Better to be same as console',
  apiKeyNameLabel: 'Key Name',
  apiKeyLabel: 'API Key',
  apiKeyTestAndSave: 'Test & Save',
  apiKeyTesting: 'Testing...',
  apiKeySaved: 'API Key saved',
  apiKeyDeleted: 'API Key deleted',
  apiKeySelected: 'Selected API Key',
  apiKeyGetKey: 'Get Key',
  enabled: 'Enabled',

  // Role Model Config
  roleConfigTitle: '🎭 Role Model Configuration',
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
  budgetTitle: '💰 Budget Settings',
  budgetDescription: 'Recommended to set monthly budget limit and alert threshold',
  monthlyLimit: 'Monthly Limit (USD)',
  alertThreshold: 'Alert Threshold',
  budgetLimitNote: 'Reject new requests after reaching this amount',
  budgetThresholdNote: 'Show warning when reaching this percentage of budget',
  preview: 'Preview',
  monthlyLimitLabel: 'Monthly limit',
  alertTriggerLabel: 'Alert trigger amount',
  budgetSaved: 'Budget settings saved',

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
};

const ZH: Translations = {
  // Header
  appTitle: 'Ternion Control Panel',
  appSubtitle: '多模型协作网关配置中心',
  llmKeysEnabled: '个 LLM Key 已启用',
  lightMode: '切换到浅色模式',
  darkMode: '切换到深色模式',

  // Tabs
  tabConfig: '⚙️ 配置',
  tabUsage: '📊 用量',

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
  apiKeyTitle: '🔑 API Key 管理',
  apiKeyDescription: '添加 LLM 提供商的 API Key 以启用对应模型',
  apiKeyStorageNote: '（已保存的 API Key 存储在：~/.ternion/config.json）',
  apiKeyPlaceholder: '建议与控制台一致',
  apiKeyNameLabel: 'Key 名字',
  apiKeyLabel: 'API Key',
  apiKeyTestAndSave: '测试并保存',
  apiKeyTesting: '测试中...',
  apiKeySaved: 'API Key 已保存',
  apiKeyDeleted: 'API Key 已删除',
  apiKeySelected: '已选择使用 API Key',
  apiKeyGetKey: '获取 Key',
  enabled: '已启用',

  // Role Model Config
  roleConfigTitle: '🎭 角色模型配置',
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
  budgetTitle: '💰 预算设置',
  budgetDescription: '建议设置每月预算上限和提醒阈值',
  monthlyLimit: '月度预算上限 (USD)',
  alertThreshold: '提醒阈值',
  budgetLimitNote: '达到此金额后将拒绝新请求',
  budgetThresholdNote: '达到预算的此比例时在响应中显示警告',
  preview: '预览',
  monthlyLimitLabel: '月度上限',
  alertTriggerLabel: '提醒触发金额',
  budgetSaved: '预算设置已保存',

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
};

export const translations: Record<Language, Translations> = {
  en: EN,
  zh: ZH,
};

/**
 * Detect browser language and return appropriate language code.
 */
export function detectBrowserLanguage(): Language {
  if (typeof navigator !== 'undefined') {
    const lang = navigator.language || (navigator as any).userLanguage || 'en';
    if (lang.startsWith('zh')) {
      return 'zh';
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
