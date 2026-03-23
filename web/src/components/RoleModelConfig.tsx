/**
 * Role Model Configuration component for Ternion Control Panel.
 *
 * Provides UI for configuring which LLM model to use for each role:
 * - Ternion A/B/C: Divergence phase analysis
 * - Arbiter: Moderator/synthesizer
 * - Writer: Code generator
 * - Reviewer: Code reviewer
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api/client';
import type { ApiErrorPayload, Config, RoleConfig, ModelsData, ModelInfo } from '../api/client';
import { isApiError } from '../api/client';
import { useToast } from './toastContext';
import type { Translations } from '../i18n';
import { getErrorMessage, isCJKLanguage } from '../i18n';
import type { Language } from '../i18n';
import {
  getCatalogModelDisplayLabel,
  getModelName,
  getModelSeriesName,
  getProviderDisplayName,
  isModelAvailableInCatalog,
} from '../modelDisplay';

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

/**
 * Props for the RoleModelConfig component.
 */
interface RoleModelConfigProps {
  /** The current global configuration object, containing role settings. */
  config: Config | null;
  /** Callback fired when the configuration is successfully updated on the server. */
  onConfigUpdate: (config: Config) => void;
  /** Translation function/object for localized strings. */
  t: Translations;
  /** Whether the application is currently in dark mode. */
  isDarkMode: boolean;
  /** The currently active execution mode to determine if some roles should be disabled. */
  executionMode?: string;
  /** The currently selected language code. */
  language: Language;
  /** Incremented when the model catalog was refreshed elsewhere. */
  modelsReloadSignal?: number;
  /** Called after the model catalog is refreshed from this panel. */
  onModelsReload: () => void;
}

const DRAFT_STORAGE_KEY = 'ternion_role_model_draft';
const CONFIG_NONEMPTY_MARKER_KEY = 'ternion_config_nonempty';
const ROLE_KEYS = ['ternion_a', 'ternion_b', 'ternion_c', 'arbiter', 'writer', 'reviewer'] as const;
interface ModelUnavailableState {
  provider: string;
  model: string;
  message: string;
  refreshSuggested: boolean;
}

const PRO_WARNING_MODEL_PATTERNS = [/^gpt-5\.2-pro(?:-|$)/, /^gpt-5\.4-pro(?:-|$)/];

function shouldShowProModelWarning(provider?: string, model?: string): boolean {
  if (provider !== 'openai' || !model) {
    return false;
  }
  return PRO_WARNING_MODEL_PATTERNS.some((pattern) => pattern.test(model));
}

function getProModelWarningUrl(model?: string): string | null {
  if (!model) {
    return null;
  }
  if (/^gpt-5\.2-pro(?:-|$)/.test(model)) {
    return 'https://developers.openai.com/api/docs/models/gpt-5.2-pro';
  }
  if (/^gpt-5\.4-pro(?:-|$)/.test(model)) {
    return 'https://developers.openai.com/api/docs/models/gpt-5.4-pro';
  }
  return null;
}

export function RoleModelConfig({
  config,
  onConfigUpdate,
  t,
  isDarkMode,
  executionMode,
  language,
  modelsReloadSignal = 0,
  onModelsReload,
}: RoleModelConfigProps) {
  const { showToast } = useToast();
  const [modelsData, setModelsData] = useState<ModelsData | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<Record<string, RoleConfig>>({});
  const [saving, setSaving] = useState(false);
  const [refreshingModels, setRefreshingModels] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [invalidatedRoles, setInvalidatedRoles] = useState<string[]>([]);
  const [modelUnavailableState, setModelUnavailableState] = useState<ModelUnavailableState | null>(null);
  const [dismissedProWarnings, setDismissedProWarnings] = useState<Record<string, string>>({});
  const cardRef = useRef<HTMLDivElement | null>(null);
  const previousReloadSignalRef = useRef(modelsReloadSignal);
  const selfTriggeredReloadRef = useRef(false);
  const unsavedSeparator = isCJKLanguage(language) ? '，' : ', ';

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
          p?.has_keys ||
            p?.enabled ||
            p?.selected_key_id ||
            (p?.keys?.length ?? 0) > 0
        )
    );
    return !hasExecutionMode && !hasAnyRoleConfigured && !hasAnyApiKeyConfigured;
  };

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

  const ROLE_DISPLAY_NAMES: Record<string, string> = {
    ternion_a: t.ternionAName,
    ternion_b: t.ternionBName,
    ternion_c: t.ternionCName,
    arbiter: t.arbiterName,
    writer: t.writerName,
    reviewer: t.reviewerName,
  };

  const persistDraft = useCallback((draft: Record<string, RoleConfig>) => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
    }
  }, []);

  const loadModels = useCallback(async (): Promise<ModelsData | null> => {
    try {
      const data = await api.getModels();
      setModelsData(data);
      return data;
    } catch (error) {
      console.error('Failed to load models:', error);
      showToast(t.modelCatalogRefreshFailed, 'error');
      return null;
    }
  }, [showToast, t.modelCatalogRefreshFailed]);

  useEffect(() => {
    void loadModels();
  }, [config, loadModels]);

  const reconcileSelectionsAfterRefresh = useCallback((nextModelsData: ModelsData) => {
    setSelectedRoles(prevRoles => {
      const clearedRoles: string[] = [];
      const nextRoles = { ...prevRoles };

      for (const role of ROLE_KEYS) {
        const roleConfig = prevRoles[role];
        if (!roleConfig?.provider || !roleConfig?.model) continue;
        if (isModelAvailableInCatalog(nextModelsData, roleConfig.provider, roleConfig.model)) continue;
        nextRoles[role] = { ...roleConfig, model: '' };
        clearedRoles.push(role);
      }

      if (clearedRoles.length > 0) {
        persistDraft(nextRoles);
        setHasChanges(true);
        setInvalidatedRoles(prev => Array.from(new Set([...prev, ...clearedRoles])));
        setModelUnavailableState(null);
        showToast(t.roleConfigRemovedSelectionHint, 'info');
        return nextRoles;
      }
      return prevRoles;
    });
  }, [persistDraft, showToast, t.roleConfigRemovedSelectionHint]);

  useEffect(() => {
    if (modelsReloadSignal === previousReloadSignalRef.current) {
      return;
    }
    previousReloadSignalRef.current = modelsReloadSignal;
    if (selfTriggeredReloadRef.current) {
      selfTriggeredReloadRef.current = false;
      return;
    }
    void (async () => {
      const data = await loadModels();
      if (data) {
        reconcileSelectionsAfterRefresh(data);
      }
    })();
  }, [loadModels, modelsReloadSignal, reconcileSelectionsAfterRefresh]);

  useEffect(() => {
    if (!config) return;

    // Clears stale drafts when the backend configuration is empty but was previously populated, indicating a reset.
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

    // Restores draft state from the current session storage.
    if (hasChanges) return;
    const draftRaw = typeof window !== 'undefined' ? window.sessionStorage.getItem(DRAFT_STORAGE_KEY) : null;
    if (draftRaw) {
      try {
        const draft = JSON.parse(draftRaw) as Record<string, RoleConfig>;
        setSelectedRoles(draft);
        setHasChanges(true);
        return;
      } catch (e) {
        console.warn('Discarding corrupted draft from sessionStorage:', e);
      }
    }
    if (config.roles) {
      setSelectedRoles(config.roles);
    }
  }, [config, hasChanges]);

  const handleProviderChange = (role: string, provider: string) => {
    setSelectedRoles(prev => {
      const next = {
        ...prev,
        [role]: { provider, model: '' },
      };
      persistDraft(next);
      return next;
    });
    setDismissedProWarnings(prev => {
      if (!prev[role]) {
        return prev;
      }
      const next = { ...prev };
      delete next[role];
      return next;
    });
    setInvalidatedRoles(prev => prev.filter(item => item !== role));
    setModelUnavailableState(null);
    setHasChanges(true);
  };

  const handleModelChange = async (role: string, model: string) => {
    const provider = selectedRoles[role]?.provider;
    setSelectedRoles(prev => {
      const next = {
        ...prev,
        [role]: { ...prev[role], model },
      };
      persistDraft(next);
      return next;
    });
    setDismissedProWarnings(prev => {
      if (!prev[role] || prev[role] === model) {
        return prev;
      }
      const next = { ...prev };
      delete next[role];
      return next;
    });
    setInvalidatedRoles(prev => prev.filter(item => item !== role));
    setModelUnavailableState(null);
    setHasChanges(true);

    if (!provider || !model) {
      return;
    }

    try {
      await api.logRoleSelection(role, provider, model);
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    }
  };

  const handleDismissProModelWarning = (role: string, model: string) => {
    if (!model) {
      return;
    }
    setDismissedProWarnings(prev => ({
      ...prev,
      [role]: model,
    }));
  };

  const handleSave = async () => {
    if (missingRoles.length > 0 || enabledProviders.length === 0) {
      if (enabledProviders.length === 0) {
        showToast(t.code_ROLES_INCOMPLETE, 'error');
      } else {
        const missingNames = missingRoles.map(role => ROLE_DISPLAY_NAMES[role] || role).join(unsavedSeparator);
        const suffix = t.code_ROLES_INCOMPLETE_SUFFIX.replace('{roles}', missingNames);
        showToast(`${t.code_ROLES_INCOMPLETE}${suffix}`, 'error');
      }
      return;
    }

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
      setInvalidatedRoles([]);
      setModelUnavailableState(null);
      if (typeof window !== 'undefined') {
        window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      }

      const lines: string[] = [];
      const enabledProviders = modelsData?.enabled_providers || [];

      for (const [role, name] of Object.entries(ROLE_DISPLAY_NAMES)) {
        if (isRoleDisabled(role)) {
          lines.push(`${name}: ${t.execModeDisabledHint}`);
          continue;
        }
        const roleConfig = selectedRoles[role];
        if (roleConfig && enabledProviders.includes(roleConfig.provider)) {
          const seriesName = getModelSeriesName(roleConfig.provider);
          const modelName = getModelName(modelsData, roleConfig.provider, roleConfig.model);
          lines.push(`${name}: ${seriesName} / ${modelName}`);
        } else {
          lines.push(`${name} ${t.toastNotConfigured}`);
        }
      }

      showToast(lines.join('\n'), 'success');
    } catch (error) {
      console.error('Failed to save:', error);
      if (isApiError(error) && error.code === 'MODEL_UNAVAILABLE') {
        const payload: ApiErrorPayload = error.payload || {};
        setModelUnavailableState({
          provider: payload.provider || '',
          model: payload.model || '',
          message: payload.message || '',
          refreshSuggested: Boolean(payload.refresh_suggested),
        });
        showToast(t.code_MODEL_UNAVAILABLE, 'error');
        return;
      }
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshModels = async () => {
    setRefreshingModels(true);
    try {
      const payload = await api.refreshModels();
      setModelsData(payload);
      reconcileSelectionsAfterRefresh(payload);
      selfTriggeredReloadRef.current = true;
      onModelsReload();

      if (payload.catalog_anomaly_detected) {
        showToast(t.modelCatalogRefreshAnomaly, 'info');
      } else {
        showToast(t.modelCatalogRefreshSuccess, 'success');
      }
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setRefreshingModels(false);
    }
  };

  const enabledProviders = modelsData?.enabled_providers || [];
  const allProviders = Object.keys(modelsData?.models || {});
  const missingRoles = ROLE_KEYS.filter(role => {
    if (isRoleDisabled(role)) {
      // cursor_handoff: writer/reviewer are disabled and should not block saving.
      return false;
    }
    const roleConfig = selectedRoles[role];
    if (!roleConfig?.provider || !roleConfig?.model) {
      return true;
    }
    if (!enabledProviders.includes(roleConfig.provider)) {
      return true;
    }
    const available = (modelsData?.models[roleConfig.provider] || []).map(m => m.id);
    return !available.includes(roleConfig.model);
  });
  const hasIncompleteRoles = missingRoles.length > 0;
  const showSaveButton = hasChanges;
  const canSave = hasChanges && !saving;
  const saveButtonTitle = hasIncompleteRoles ? t.code_ROLES_INCOMPLETE : '';

  return (
    <div className="card relative" ref={cardRef}>
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
                  {t.apiKeyAdded}: {enabledProviders.map(p => getProviderDisplayName(p)).join(', ')}
                </span>
                <span className="text-slate-400 dark:text-slate-500">）</span>
              </span>
            )}
          </p>
        </div>
        {showSaveButton && (
          <div style={{ minWidth: '100px', height: '45px', flexShrink: 0 }} />
        )}
      </div>
      {showSaveButton && (
        <div
          style={{
            position: 'absolute',
            top: '16px',
            bottom: '24px',
            right: '24px',
            width: `100px`,
            pointerEvents: 'none',
            zIndex: 9000,
          }}
        >
          <button
            className={`btn text-xs whitespace-nowrap shadow-lg shadow-black/10 ${canSave ? 'btn-primary' : 'btn-disabled'}`}
            onClick={handleSave}
            disabled={!canSave}
            aria-label={t.saveChanges}
            title={saveButtonTitle || t.saveChanges}
            style={{
              position: 'sticky',
              top: `calc(50vh - 22.5px)`,
              height: `45px`,
              minWidth: `100px`,
              pointerEvents: 'auto',
            }}
          >
            {saving ? t.saving : t.saveChanges}
          </button>
        </div>
      )}
      <div className="card-body space-y-6">
        {modelUnavailableState && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-4 dark:border-amber-700 dark:bg-amber-950/40">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="space-y-1">
                <div className="font-medium text-amber-900 dark:text-amber-100">
                  {t.code_MODEL_UNAVAILABLE}
                </div>
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  {modelUnavailableState.refreshSuggested
                    ? t.roleConfigRefreshSuggested
                    : getErrorMessage(t, 'MODEL_UNAVAILABLE', language)}
                </p>
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  {getProviderDisplayName(modelUnavailableState.provider)} /{' '}
                  {getModelName(
                    modelsData,
                    modelUnavailableState.provider,
                    modelUnavailableState.model
                  )}
                </p>
                {modelUnavailableState.message && (
                  <p className="text-xs text-amber-700 dark:text-amber-300 wrap-break-word">
                    {modelUnavailableState.message}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2 self-start">
                <button
                  className="btn btn-primary h-11 whitespace-nowrap px-3 text-[13px] leading-none"
                  style={{ minWidth: '0' }}
                  onClick={handleSave}
                  disabled={saving || refreshingModels}
                >
                  {saving ? t.saving : t.modelCatalogRetry}
                </button>
                <button
                  className="btn btn-success h-11 whitespace-nowrap px-3 text-[13px] leading-none"
                  style={{ minWidth: '0' }}
                  onClick={handleRefreshModels}
                  disabled={refreshingModels || saving}
                >
                  {refreshingModels ? t.modelCatalogRefreshing : t.modelCatalogRefreshNow}
                </button>
              </div>
            </div>
          </div>
        )}

        {Object.entries(ROLE_INFO).map(([role, info]) => {
          const roleConfig = selectedRoles[role];
          const selectedProvider = roleConfig?.provider;
          const selectedModel = roleConfig?.model;
          const availableModels = modelsData?.models[selectedProvider] || [];
          const disabled = isRoleDisabled(role);
          const highlighted = invalidatedRoles.includes(role);
          const proModelWarningUrl = getProModelWarningUrl(selectedModel);
          const proWarningTextClass =
            language === 'zh' || language === 'ko' ? 'text-[13px] leading-5' : 'text-[11px] leading-4';
          const showProModelWarning =
            shouldShowProModelWarning(selectedProvider, selectedModel) &&
            dismissedProWarnings[role] !== selectedModel;

          return (
            <div
              key={role}
              className={`p-4 rounded-lg border ${
                highlighted
                  ? 'border-amber-400 bg-amber-50/50 dark:border-amber-700 dark:bg-amber-950/20'
                  : 'border-slate-200 dark:border-slate-700'
              }`}
            >
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="flex items-center gap-2">
                  <img src={getRoleIcon(role)} alt="" className="w-6 h-6" />
                  <div>
                    <h3 className="font-medium">{info.name}</h3>
                    <p className="text-sm text-slate-500">{info.description}</p>
                  </div>
                </div>
                {showProModelWarning && (
                  <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-[11px] dark:border-amber-700 dark:bg-amber-950/40 md:max-w-176">
                    <div className="flex items-start gap-3">
                      <p className={`flex-1 text-amber-800 dark:text-amber-200 ${proWarningTextClass}`}>
                        {t.roleConfigProModelWarningPrefix}
                        {proModelWarningUrl ? (
                          <a
                            href={proModelWarningUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium underline underline-offset-2"
                          >
                            {t.roleConfigProModelWarningLinkLabel}
                          </a>
                        ) : (
                          t.roleConfigProModelWarningLinkLabel
                        )}
                        {t.roleConfigProModelWarningSuffix}
                      </p>
                      <button
                        type="button"
                        className="shrink-0 text-lg leading-none text-amber-700 transition hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100"
                        aria-label={t.logsDismiss}
                        title={t.logsDismiss}
                        onClick={() => handleDismissProModelWarning(role, selectedModel)}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
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
                          {getModelSeriesName(provider)}
                          {!isEnabled && ` ${t.noApiKey}`}
                        </option>
                      );
                    })}
                  </select>
                </div>

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
                        {getCatalogModelDisplayLabel(model)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

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
                        ? `${getModelSeriesName(roleConfig.provider)} / ${getModelName(
                            modelsData,
                            roleConfig.provider,
                            selectedModel
                          )}`
                        : '--/----'}
                    </code>
                    {(!config?.roles?.[role] ||
                      config?.roles?.[role]?.provider !== roleConfig?.provider ||
                      config?.roles?.[role]?.model !== roleConfig?.model)
                      ? `${unsavedSeparator}${t.unsavedLabel}`
                      : ''}
                  </>
                )}
              </div>
              {highlighted && (
                <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">
                  {t.roleConfigRemovedSelectionHint}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default RoleModelConfig;
