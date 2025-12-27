/**
 * Role Model Configuration component for Ternion Control Panel.
 *
 * Provides UI for configuring which LLM model to use for each role:
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

interface RoleModelConfigProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  t: Translations;
  isDarkMode: boolean;
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

export function RoleModelConfig({ config, onConfigUpdate, t, isDarkMode }: RoleModelConfigProps) {
  const { showToast } = useToast();
  const [modelsData, setModelsData] = useState<ModelsData | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<Record<string, RoleConfig>>({});
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Get role icon based on dark mode
  const getRoleIcon = (role: string) => {
    switch (role) {
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

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    loadModels();
  }, [config]);

  useEffect(() => {
    if (config?.roles) {
      setSelectedRoles(config.roles);
    }
  }, [config]);

  const loadModels = async () => {
    try {
      const data = await api.getModels();
      setModelsData(data);
    } catch (error) {
      console.error('Failed to load models:', error);
    }
  };

  const handleProviderChange = (role: string, provider: string) => {
    const models = modelsData?.models[provider] || [];
    const defaultModel = models[0]?.id || '';

    setSelectedRoles(prev => ({
      ...prev,
      [role]: { provider, model: defaultModel },
    }));
    setHasChanges(true);
  };

  const handleModelChange = (role: string, model: string) => {
    setSelectedRoles(prev => ({
      ...prev,
      [role]: { ...prev[role], model },
    }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await api.updateConfig({
        roles: selectedRoles,
      });
      onConfigUpdate(result.config);
      setHasChanges(false);

      // Build toast message with role configuration status
      const lines: string[] = [];
      const roleNames = { arbiter: t.arbiterName, writer: t.writerName, reviewer: t.reviewerName };
      const enabledProviders = modelsData?.enabled_providers || [];

      for (const [role, name] of Object.entries(roleNames)) {
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
            <span className="text-slate-400 dark:text-slate-500">{t.roleConfigHint}</span>
          </p>
        </div>
        {hasChanges && enabledProviders.length > 0 && (
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
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
                    className="select"
                    value={selectedProvider || ''}
                    onChange={(e) => handleProviderChange(role, e.target.value)}
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
                    className="select"
                    value={selectedModel || ''}
                    onChange={(e) => handleModelChange(role, e.target.value)}
                    disabled={!selectedProvider}
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
                <code className="px-2 py-0.5 bg-slate-100 dark:bg-slate-700 rounded">
                  {roleConfig && enabledProviders.includes(roleConfig.provider)
                    ? `${PROVIDER_NAMES[roleConfig.provider]} / ${
                        availableModels.find(m => m.id === selectedModel)?.name || selectedModel
                      }`
                    : '--/----'}
                </code>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default RoleModelConfig;
