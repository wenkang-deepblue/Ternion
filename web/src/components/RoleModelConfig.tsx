/**
 * Role Model Configuration component for Ternion Control Panel.
 *
 * Provides UI for configuring which LLM model to use for each role:
 * - Ternion A/B/C: Divergence phase analysis
 * - Arbiter: Moderator/synthesizer
 * - Writer: Code generator
 * - Reviewer: Code reviewer
 */

import { useState, useEffect } from 'react';
import api from '../api/client';
import type { Config, RoleConfig, ModelsData, ModelInfo } from '../api/client';
import { useToast } from './Toast';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';

// Section icon
import characterIconLight from '../assets/icons/character_light_mode_50dp.svg';
import characterIconDark from '../assets/icons/character_dark_mode_50dp.svg';

// Role icons
import arbiterIconLight from '../assets/icons/arbiter_light_mode_50dp.svg';
import arbiterIconDark from '../assets/icons/arbiter_dark_mode_50dp.svg';
import writerIconLight from '../assets/icons/writer_light_mode_50dp.svg';
import writerIconDark from '../assets/icons/writer_dark_mode_50dp.svg';
import reviewerIconLight from '../assets/icons/reviewer_light_mode_50dp.svg';
import reviewerIconDark from '../assets/icons/reviewer_dark_mode_50dp.svg';

// Ternion icons (same for light/dark mode)
import ternionAIcon from '../assets/icons/ternion_a.svg';
import ternionBIcon from '../assets/icons/ternion_b.svg';
import ternionCIcon from '../assets/icons/ternion_c.svg';

interface RoleModelConfigProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  t: Translations;
  isDarkMode: boolean;
  executionMode?: string;
}

const PROVIDER_NAMES: Record<string, string> = {
  google: 'Gemini',
  anthropic: 'Claude',
  openai: 'GPT',
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

const DRAFT_STORAGE_KEY = 'ternion_role_model_draft';
const CONFIG_NONEMPTY_MARKER_KEY = 'ternion_config_nonempty';

export function RoleModelConfig({ config, onConfigUpdate, t, isDarkMode, executionMode }: RoleModelConfigProps) {
  const { showToast } = useToast();
  const [modelsData, setModelsData] = useState<ModelsData | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<Record<string, RoleConfig>>({});
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Check if role is disabled based on execution mode
  const isRoleDisabled = (role: string) => {
    if (executionMode === 'cursor_handoff') {
      return role === 'writer' || role === 'reviewer';
    }
    return false;
  };

  const isPersistedConfigEmpty = (cfg: Config): boolean => {
    const hasExecutionMode = Boolean(cfg.execution_mode);
    const hasAnyRoleConfigured = Object.values(cfg.roles || {}).some(
      (r) => Boolean(r?.provider || r?.model)
    );
    const hasAnyApiKeyConfigured = Object.values(cfg.providers || {}).some(
      (p) =>
        Boolean(
          (p as any)?.has_keys ||
            (p as any)?.enabled ||
            (p as any)?.selected_key_id ||
            ((p as any)?.keys?.length ?? 0) > 0
        )
    );
    return !hasExecutionMode && !hasAnyRoleConfigured && !hasAnyApiKeyConfigured;
  };

  // Get role icon based on role type
  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'ternion_a':
        return ternionAIcon;
      case 'ternion_b':
        return ternionBIcon;
      case 'ternion_c':
        return ternionCIcon;
      case 'arbiter':
        return isDarkMode ? arbiterIconDark : arbiterIconLight;
      case 'writer':
        return isDarkMode ? writerIconDark : writerIconLight;
      case 'reviewer':
        return isDarkMode ? reviewerIconDark : reviewerIconLight;
      default:
        return isDarkMode ? arbiterIconDark : arbiterIconLight;
    }
  };

  const ROLE_INFO = {
    // Ternion members (Divergence phase) - placed before core roles
    ternion_a: {
      name: t.ternionAName,
      description: t.ternionADesc,
    },
    ternion_b: {
      name: t.ternionBName,
      description: t.ternionBDesc,
    },
    ternion_c: {
      name: t.ternionCName,
      description: t.ternionCDesc,
    },
    // Core roles (Convergence, Execution, Final Check phases)
    arbiter: {
      name: t.arbiterName,
      description: t.arbiterDesc,
    },
    writer: {
      name: t.writerName,
      description: t.writerDesc,
    },
    reviewer: {
      name: t.reviewerName,
      description: t.reviewerDesc,
    },
  };

  const ROLE_KEYS = Object.keys(ROLE_INFO);
  const ROLE_DISPLAY_NAMES: Record<string, string> = {
    ternion_a: t.ternionAName,
    ternion_b: t.ternionBName,
    ternion_c: t.ternionCName,
    arbiter: t.arbiterName,
    writer: t.writerName,
    reviewer: t.reviewerName,
  };

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    loadModels();
  }, [config]);

  useEffect(() => {
    if (!config) return;

    // If backend config is empty but we *previously* had non-empty persisted config,
    // this indicates a fresh start (e.g., ~/.ternion/config.json deleted/empty) -> clear stale drafts.
    if (typeof window !== 'undefined') {
      const persistedEmpty = isPersistedConfigEmpty(config);
      window.localStorage.setItem(CONFIG_NONEMPTY_MARKER_KEY, persistedEmpty ? '0' : '1');
      if (persistedEmpty) {
        window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
        setSelectedRoles(config.roles || {});
        setHasChanges(false);
        return;
      }
    }

    // Normal behavior: restore draft within the current browser tab/session.
    if (hasChanges) return;
    const draftRaw = typeof window !== 'undefined' ? window.sessionStorage.getItem(DRAFT_STORAGE_KEY) : null;
    if (draftRaw) {
      try {
        const draft = JSON.parse(draftRaw) as Record<string, RoleConfig>;
        setSelectedRoles(draft);
        setHasChanges(true);
        return;
      } catch {
        // ignore corrupted draft
      }
    }
    if (config.roles) {
      setSelectedRoles(config.roles);
    }
  }, [config, hasChanges]);

  const loadModels = async () => {
    try {
      const data = await api.getModels();
      setModelsData(data);
    } catch (error) {
      console.error('Failed to load models:', error);
    }
  };

  const handleProviderChange = (role: string, provider: string) => {
    setSelectedRoles(prev => {
      const next = {
        ...prev,
        [role]: { provider, model: '' },
      };
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(next));
      }
      return next;
    });
    setHasChanges(true);
  };

  const handleModelChange = async (role: string, model: string) => {
    const provider = selectedRoles[role]?.provider;
    setSelectedRoles(prev => {
      const next = {
        ...prev,
        [role]: { ...prev[role], model },
      };
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(next));
      }
      return next;
    });
    setHasChanges(true);

    if (!provider || !model) {
      return;
    }

    try {
      await api.logRoleSelection(role, provider, model);
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Only submit roles that are required (skip disabled roles under cursor_handoff)
      const rolesToSave: Record<string, RoleConfig> = {};
      for (const role of ROLE_KEYS) {
        if (isRoleDisabled(role)) continue;
        const roleConfig = selectedRoles[role];
        if (roleConfig?.provider && roleConfig?.model) {
          rolesToSave[role] = roleConfig;
        }
      }

      const updatedConfig = await api.updateConfig({
        roles: rolesToSave,
      });
      onConfigUpdate(updatedConfig);
      setHasChanges(false);
      if (typeof window !== 'undefined') {
        window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      }

      // Build toast message with role configuration status
      const lines: string[] = [];
      const enabledProviders = modelsData?.enabled_providers || [];

      for (const [role, name] of Object.entries(ROLE_DISPLAY_NAMES)) {
        if (isRoleDisabled(role)) {
          lines.push(`${name}: ${t.execModeDisabledHint}`);
          continue;
        }
        const roleConfig = selectedRoles[role];
        if (roleConfig && enabledProviders.includes(roleConfig.provider)) {
          const providerName = PROVIDER_NAMES[roleConfig.provider] || roleConfig.provider;
          const modelName = MODEL_NAMES[roleConfig.model] || roleConfig.model;
          lines.push(`${name}: ${providerName} / ${modelName}`);
        } else {
          lines.push(`${name} ${t.toastNotConfigured}`);
        }
      }

      showToast(lines.join('\n'), 'success');
    } catch (error) {
      console.error('Failed to save:', error);
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    } finally {
      setSaving(false);
    }
  };

  const enabledProviders = modelsData?.enabled_providers || [];
  const allProviders = Object.keys(modelsData?.models || {});
  const allRolesConfigured = ROLE_KEYS.every(role => {
    if (isRoleDisabled(role)) {
      // cursor_handoff: writer/reviewer are disabled and should not block saving.
      return true;
    }
    const roleConfig = selectedRoles[role];
    if (!roleConfig?.provider || !roleConfig?.model) {
      return false;
    }
    if (!enabledProviders.includes(roleConfig.provider)) {
      return false;
    }
    const available = (modelsData?.models[roleConfig.provider] || []).map(m => m.id);
    return available.includes(roleConfig.model);
  });
  const hasAnySelection = ROLE_KEYS.some(role => {
    const roleConfig = selectedRoles[role];
    return Boolean(roleConfig?.provider || roleConfig?.model);
  });
  const hasIncompleteRoles = !allRolesConfigured;
  const showSaveButton = enabledProviders.length > 0 && (hasAnySelection || hasChanges || allRolesConfigured);
  const canSave = hasChanges && allRolesConfigured && enabledProviders.length > 0 && !saving;
  const saveButtonTitle = hasIncompleteRoles ? t.roleNotSaved : '';

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <img src={isDarkMode ? characterIconDark : characterIconLight} alt="" className="w-6 h-6" />
            {t.roleConfigTitle}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t.roleConfigDescription}
            {enabledProviders.length === 0 ? (
              <span className="text-slate-400 dark:text-slate-500">{t.roleConfigHint}</span>
            ) : (
              <span className="inline-flex items-center gap-1 ml-1">
                <span className="text-slate-400 dark:text-slate-500">（</span>
                <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                <span className="text-green-600 dark:text-green-400">
                  {t.apiKeyAdded}: {enabledProviders.map(p => PROVIDER_NAMES[p] || p).join(', ')}
                </span>
                <span className="text-slate-400 dark:text-slate-500">）</span>
              </span>
            )}
          </p>
        </div>
        {showSaveButton && (
          <button
            style={{ minWidth: '100px', height: '45px', flexShrink: 0 }}
            className={`btn text-xs whitespace-nowrap ${canSave ? 'btn-primary' : 'btn-disabled'}`}
            onClick={handleSave}
            disabled={!canSave}
            title={saveButtonTitle}
          >
            {saving ? t.saving : t.saveChanges}
          </button>
        )}
      </div>
      <div className="card-body space-y-6">
        {Object.entries(ROLE_INFO).map(([role, info]) => {
          const roleConfig = selectedRoles[role];
          const selectedProvider = roleConfig?.provider;
          const selectedModel = roleConfig?.model;
          const availableModels = modelsData?.models[selectedProvider] || [];
          const disabled = isRoleDisabled(role);

          return (
            <div
              key={role}
              className="p-4 rounded-lg border border-slate-200 dark:border-slate-700"
            >
              <div className="flex items-center gap-2 mb-4">
                <img src={getRoleIcon(role)} alt="" className="w-6 h-6" />
                <div>
                  <h3 className="font-medium">{info.name}</h3>
                  <p className="text-sm text-slate-500">{info.description}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* Provider Selection */}
                <div>
                  <label className="label">{t.modelSeries}</label>
                  <select
                    className={`select ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    value={selectedProvider || ''}
                    onChange={(e) => handleProviderChange(role, e.target.value)}
                    disabled={disabled}
                  >
                    <option value="" disabled>
                      {t.selectSeries}
                    </option>
                    {allProviders.map((provider) => {
                      const isEnabled = enabledProviders.includes(provider);
                      return (
                        <option
                          key={provider}
                          value={provider}
                          disabled={!isEnabled}
                        >
                          {PROVIDER_NAMES[provider] || provider}
                          {!isEnabled && ` ${t.noApiKey}`}
                        </option>
                      );
                    })}
                  </select>
                </div>

                {/* Model Selection */}
                <div>
                  <label className="label">{t.modelName}</label>
                  <select
                    className={`select ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    value={selectedModel || ''}
                    onChange={(e) => handleModelChange(role, e.target.value)}
                    disabled={disabled || !selectedProvider}
                  >
                    <option value="" disabled>
                      {t.selectModel}
                    </option>
                    {availableModels.map((model: ModelInfo) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Current Config Display */}
              <div className="mt-3 text-sm text-slate-500">
                {t.currentConfig}:{' '}
                {disabled ? (
                  <span className="text-amber-600 dark:text-amber-400">
                    {t.execModeDisabledHint}
                  </span>
                ) : (
                  <>
                    <code className="px-2 py-0.5 bg-slate-100 dark:bg-slate-700 rounded">
                      {roleConfig && enabledProviders.includes(roleConfig.provider)
                        ? `${PROVIDER_NAMES[roleConfig.provider]} / ${availableModels.find(m => m.id === selectedModel)?.name || selectedModel
                        }`
                        : '--/----'}
                    </code>
                    {(!config?.roles?.[role] ||
                      config?.roles?.[role]?.provider !== roleConfig?.provider ||
                      config?.roles?.[role]?.model !== roleConfig?.model)
                      ? `，${t.unsavedLabel}`
                      : ''}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default RoleModelConfig;
