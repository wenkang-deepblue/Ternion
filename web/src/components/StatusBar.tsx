/**
 * StatusBar component for Ternion Control Panel.
 *
 * Displays configuration status indicators for API keys and role models.
 * Uses red/green dots to indicate pending/completed configuration items.
 */

import type { Config } from '../api/client';
import type { Translations } from '../i18n';

interface StatusBarProps {
  config: Config | null;
  t: Translations;
}

const PROVIDER_NAMES: Record<string, string> = {
  google: 'Gemini',
  anthropic: 'Claude',
  openai: 'OpenAI',
};

const MODEL_NAMES: Record<string, string> = {
  'gemini-3-pro-preview': 'Gemini 3.0 Pro',
  'gemini-3-flash-preview': 'Gemini 3.0 Flash',
  'gemini-flash-lite-latest': 'Gemini 2.5 Flash Lite',
  'claude-opus-4-5-20251101': 'Claude 4.5 Opus',
  'claude-sonnet-4-5-20250929': 'Claude 4.5 Sonnet',
  'claude-opus-4-1-20250805': 'Claude 4.1 Opus',
  'gpt-5.2-pro-2025-12-11': 'GPT 5.2 Pro',
  'gpt-5.2-2025-12-11': 'GPT 5.2',
  'gpt-5.1-codex-max': 'GPT 5.1 Codex Max',
  'gpt-5.1-codex': 'GPT 5.1 Codex',
};

const EXEC_MODE_DISPLAY: Record<string, (t: Translations) => string> = {
  cursor_handoff: (t) => t.execModeCursorTitle,
  ternion_full: (t) => t.execModeTernionTitle,
};

interface StatusItemProps {
  isComplete: boolean;
  pendingText: string;
  completeText: string;
}

function StatusItem({ isComplete, pendingText, completeText }: StatusItemProps) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${
          isComplete ? 'bg-emerald-500' : 'bg-red-500'
        }`}
      />
      <span className={isComplete ? 'text-slate-600 dark:text-slate-400' : 'text-red-600 dark:text-red-400'}>
        {isComplete ? completeText : pendingText}
      </span>
    </div>
  );
}

export function StatusBar({ config, t }: StatusBarProps) {
  // Check if any API key is configured
  const enabledProviders: string[] = [];
  if (config?.providers) {
    Object.entries(config.providers).forEach(([name, provider]) => {
      if (provider.enabled) {
        enabledProviders.push(PROVIDER_NAMES[name] || name);
      }
    });
  }
  const hasApiKey = enabledProviders.length > 0;

  // Check role configurations
  const roles = config?.roles || {};
  
  const isRoleConfigured = (role: string) => {
    const roleConfig = roles[role];
    if (!roleConfig || !roleConfig.provider || !roleConfig.model) {
      return false;
    }
    // Check if the provider is enabled
    const providerStatus = config?.providers[roleConfig.provider];
    return providerStatus?.enabled || false;
  };

  const getRoleConfigText = (role: string, roleName: string) => {
    const roleConfig = roles[role];
    if (!roleConfig || !isRoleConfigured(role)) {
      return '';
    }
    const providerName = PROVIDER_NAMES[roleConfig.provider] || roleConfig.provider;
    const modelName = MODEL_NAMES[roleConfig.model] || roleConfig.model;
    return `${roleName}: ${providerName} / ${modelName}`;
  };

  const arbiterConfigured = isRoleConfigured('arbiter');
  const writerConfigured = isRoleConfigured('writer');
  const reviewerConfigured = isRoleConfigured('reviewer');

  // Check council configurations
  const ternionAConfigured = isRoleConfigured('ternion_a');
  const ternionBConfigured = isRoleConfigured('ternion_b');
  const ternionCConfigured = isRoleConfigured('ternion_c');

  // Execution mode status
  const executionMode = config?.execution_mode || '';
  const hasExecutionMode = executionMode === 'cursor_handoff' || executionMode === 'ternion_full';
  const execModeDisplay = hasExecutionMode ? EXEC_MODE_DISPLAY[executionMode]?.(t) || executionMode : '';

  const writerEffectiveComplete = executionMode === 'cursor_handoff' ? true : writerConfigured;
  const reviewerEffectiveComplete = executionMode === 'cursor_handoff' ? true : reviewerConfigured;

  return (
    <div className="bg-slate-100 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700 py-2 px-4">
      {/* First row - API keys and Ternion status */}
      <div className="mx-auto flex flex-wrap items-center justify-center gap-3 text-sm">
        {/* API Key Status */}
        <StatusItem
          isComplete={hasApiKey}
          pendingText={t.statusAddApiKey}
          completeText={`${t.statusApiKeyAdded}: ${enabledProviders.join(', ')}`}
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Ternion A Status */}
        <StatusItem
          isComplete={ternionAConfigured}
          pendingText={t.statusConfigTernionA}
          completeText={getRoleConfigText('ternion_a', t.statusTernionAConfigured)}
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Ternion B Status */}
        <StatusItem
          isComplete={ternionBConfigured}
          pendingText={t.statusConfigTernionB}
          completeText={getRoleConfigText('ternion_b', t.statusTernionBConfigured)}
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Ternion C Status */}
        <StatusItem
          isComplete={ternionCConfigured}
          pendingText={t.statusConfigTernionC}
          completeText={getRoleConfigText('ternion_c', t.statusTernionCConfigured)}
        />
      </div>

      {/* Second row - Core roles status */}
      <div className="mx-auto flex flex-wrap items-center justify-center gap-3 text-sm mt-1">
        {/* Execution Mode Status */}
        <StatusItem
          isComplete={hasExecutionMode}
          pendingText={t.statusExecModeNotSelected}
          completeText={`${t.statusExecModeSelected}: ${execModeDisplay}`}
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Arbiter Status */}
        <StatusItem
          isComplete={arbiterConfigured}
          pendingText={t.statusConfigArbiter}
          completeText={getRoleConfigText('arbiter', t.statusArbiterConfigured)}
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Writer Status */}
        <StatusItem
          isComplete={writerEffectiveComplete}
          pendingText={t.statusConfigWriter}
          completeText={
            executionMode === 'cursor_handoff'
              ? `${t.statusWriterConfigured}: ${t.execModeDisabledHint}`
              : getRoleConfigText('writer', t.statusWriterConfigured)
          }
        />

        <span className="text-slate-300 dark:text-slate-600">|</span>

        {/* Reviewer Status */}
        <StatusItem
          isComplete={reviewerEffectiveComplete}
          pendingText={t.statusConfigReviewer}
          completeText={
            executionMode === 'cursor_handoff'
              ? `${t.statusReviewerConfigured}: ${t.execModeDisabledHint}`
              : getRoleConfigText('reviewer', t.statusReviewerConfigured)
          }
        />
      </div>
    </div>
  );
}

export default StatusBar;
