/**
 * Model catalog management panel for initialization, refresh, and scheduling.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import api from '../api/client';
import type { Config, ModelCatalogRefreshConfig, ModelsData } from '../api/client';
import { getErrorMessage } from '../i18n';
import type { Language, Translations } from '../i18n';
import { useToast } from './toastContext';

interface ModelCatalogManagerProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  onModelsReload: () => void;
  reloadSignal?: number;
  t: Translations;
  language: Language;
}

const DEFAULT_REFRESH_CONFIG: ModelCatalogRefreshConfig = {
  enabled: false,
  mode: 'daily',
  time_of_day: '03:00',
  interval_value: 1,
  last_refresh_at: '',
  next_refresh_at: '',
};

const MODE_OPTIONS: Array<{ value: ModelCatalogRefreshConfig['mode']; labelKey: keyof Translations }> = [
  { value: 'daily', labelKey: 'modelCatalogScheduleDaily' },
  { value: 'interval_days', labelKey: 'modelCatalogScheduleDays' },
  { value: 'interval_weeks', labelKey: 'modelCatalogScheduleWeeks' },
];

function formatTimestamp(value: string | undefined, language: Language): string {
  if (!value) {
    return '--';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(language);
}

export function ModelCatalogManager({
  config,
  onConfigUpdate,
  onModelsReload,
  reloadSignal = 0,
  t,
  language,
}: ModelCatalogManagerProps) {
  const { showToast } = useToast();
  const [modelsData, setModelsData] = useState<ModelsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsMarkdown, setDetailsMarkdown] = useState('');
  const [schedule, setSchedule] = useState<ModelCatalogRefreshConfig>(
    config?.model_catalog_refresh || DEFAULT_REFRESH_CONFIG
  );
  const [scheduleDirty, setScheduleDirty] = useState(false);

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getModels();
      setModelsData(data);
    } catch (error) {
      console.error('Failed to load model catalog status:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      const updatedConfig = await api.getConfig();
      onConfigUpdate(updatedConfig);
      return updatedConfig;
    } catch (error) {
      console.error('Failed to reload config after model catalog action:', error);
      return null;
    }
  }, [onConfigUpdate]);

  useEffect(() => {
    void loadModels();
  }, [loadModels, reloadSignal]);

  useEffect(() => {
    setSchedule(config?.model_catalog_refresh || DEFAULT_REFRESH_CONFIG);
    setScheduleDirty(false);
  }, [config]);

  const refreshActionLabel = useMemo(() => {
    return modelsData?.requires_initialization
      ? t.modelCatalogInitialize
      : t.modelCatalogRefreshNow;
  }, [modelsData?.requires_initialization, t.modelCatalogInitialize, t.modelCatalogRefreshNow]);

  const handleRefresh = async () => {
    const isInitialization = Boolean(modelsData?.requires_initialization);
    setRefreshing(true);
    try {
      const payload = await api.refreshModels();
      setModelsData(payload);
      await refreshConfig();
      onModelsReload();

      if (payload.catalog_anomaly_detected) {
        showToast(
          isInitialization ? t.modelCatalogInitAnomaly : t.modelCatalogRefreshAnomaly,
          'info'
        );
      } else {
        showToast(
          isInitialization ? t.modelCatalogInitSuccess : t.modelCatalogRefreshSuccess,
          'success'
        );
      }
    } catch (error) {
      await refreshConfig();
      const errorCode = error instanceof Error ? error.message : String(error);
      const fallback = isInitialization ? t.modelCatalogInitFailed : t.modelCatalogRefreshFailed;
      const translated = getErrorMessage(t, errorCode, language);
      showToast(translated === errorCode ? fallback : `${fallback}\n${translated}`, 'error');
    } finally {
      await loadModels();
      setRefreshing(false);
    }
  };

  const handleScheduleFieldChange = <K extends keyof ModelCatalogRefreshConfig>(
    key: K,
    value: ModelCatalogRefreshConfig[K]
  ) => {
    setSchedule(prev => ({ ...prev, [key]: value }));
    setScheduleDirty(true);
  };

  const handleSaveSchedule = async () => {
    setSavingSchedule(true);
    try {
      const updatedConfig = await api.updateConfig({
        model_catalog_refresh: {
          enabled: schedule.enabled,
          mode: schedule.mode,
          time_of_day: schedule.time_of_day,
          interval_value: schedule.interval_value,
        },
      });
      onConfigUpdate(updatedConfig);
      setSchedule(updatedConfig.model_catalog_refresh || DEFAULT_REFRESH_CONFIG);
      setScheduleDirty(false);
      showToast(t.modelCatalogScheduleSaved, 'success');
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleOpenDetails = async () => {
    setDetailsLoading(true);
    try {
      const markdown = await api.getModelsAnomalyReport();
      setDetailsMarkdown(markdown);
      setDetailsOpen(true);
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setDetailsLoading(false);
    }
  };

  const modelCountText = loading ? t.loading : String(modelsData?.model_count ?? 0);
  const lastCatalogUpdateText = formatTimestamp(modelsData?.last_updated_at, language);
  const lastRefreshText = formatTimestamp(schedule.last_refresh_at, language);
  const nextRefreshText = formatTimestamp(schedule.next_refresh_at, language);
  const anomalySummary = modelsData?.catalog_anomaly_summary || t.modelCatalogAnomalyBanner;

  return (
    <>
      <div className="card">
        <div className="card-header flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{t.modelCatalogTitle}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {t.modelCatalogDescription}
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleRefresh}
            disabled={refreshing || loading}
          >
            {refreshing
              ? modelsData?.requires_initialization
                ? t.modelCatalogInitializing
                : t.modelCatalogRefreshing
              : refreshActionLabel}
          </button>
        </div>
        <div className="card-body space-y-6">
          {modelsData?.catalog_anomaly_detected && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-4 dark:border-amber-700 dark:bg-amber-950/40">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="space-y-1">
                  <div className="font-medium text-amber-900 dark:text-amber-100">
                    {t.modelCatalogAnomalyBanner}
                  </div>
                  <p className="text-sm text-amber-800 dark:text-amber-200">
                    {anomalySummary}
                  </p>
                  <p className="text-sm text-amber-800 dark:text-amber-200">
                    {t.modelCatalogAnomalyHelp}
                  </p>
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    {t.modelCatalogAnomalyUpdatedAt}: {formatTimestamp(modelsData.catalog_anomaly_updated_at, language)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button className="btn btn-primary" onClick={handleRefresh} disabled={refreshing}>
                    {t.modelCatalogRetry}
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={handleOpenDetails}
                    disabled={detailsLoading || !modelsData.anomaly_report_available}
                  >
                    {detailsLoading ? t.loading : t.modelCatalogViewDetails}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800/50">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t.modelCatalogStatus}
              </div>
              <div className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                {modelsData?.requires_initialization
                  ? t.modelCatalogStatusNeedsInitialization
                  : t.modelCatalogStatusReady}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800/50">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t.modelCatalogModelCount}
              </div>
              <div className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                {modelCountText}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-4 dark:bg-slate-800/50">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t.modelCatalogCatalogUpdatedAt}
              </div>
              <div className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                {lastCatalogUpdateText}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h3 className="font-medium text-slate-900 dark:text-slate-100">
                  {t.modelCatalogScheduleTitle}
                </h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  {t.modelCatalogScheduleDescription}
                </p>
              </div>
              <button
                className="btn btn-secondary"
                onClick={handleSaveSchedule}
                disabled={savingSchedule || !scheduleDirty}
              >
                {savingSchedule ? t.saving : t.saveChanges}
              </button>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-3 dark:border-slate-700">
                <input
                  type="checkbox"
                  checked={schedule.enabled}
                  onChange={(event) => handleScheduleFieldChange('enabled', event.target.checked)}
                  className="h-4 w-4"
                />
                <span className="text-sm text-slate-700 dark:text-slate-200">
                  {t.modelCatalogScheduleEnabled}
                </span>
              </label>

              <div>
                <label className="label">{t.modelCatalogScheduleMode}</label>
                <select
                  className="select"
                  value={schedule.mode}
                  onChange={(event) => handleScheduleFieldChange('mode', event.target.value as ModelCatalogRefreshConfig['mode'])}
                  disabled={!schedule.enabled}
                >
                  {MODE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t[option.labelKey]}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">{t.modelCatalogScheduleTime}</label>
                <input
                  type="time"
                  className="input"
                  value={schedule.time_of_day}
                  onChange={(event) => handleScheduleFieldChange('time_of_day', event.target.value)}
                  disabled={!schedule.enabled}
                />
              </div>

              <div>
                <label className="label">{t.modelCatalogScheduleInterval}</label>
                <input
                  type="number"
                  className="input"
                  min={1}
                  value={schedule.interval_value}
                  onChange={(event) =>
                    handleScheduleFieldChange(
                      'interval_value',
                      Math.max(Number.parseInt(event.target.value || '1', 10) || 1, 1)
                    )
                  }
                  disabled={!schedule.enabled || schedule.mode === 'daily'}
                />
              </div>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2 text-sm">
              <div className="rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/50">
                <span className="text-slate-500 dark:text-slate-400">
                  {t.modelCatalogLastRefreshAt}:&nbsp;
                </span>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  {lastRefreshText}
                </span>
              </div>
              <div className="rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/50">
                <span className="text-slate-500 dark:text-slate-400">
                  {t.modelCatalogNextRefreshAt}:&nbsp;
                </span>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  {nextRefreshText}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {detailsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 py-8">
          <div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {t.modelCatalogDetailsTitle}
              </h3>
              <button className="btn btn-secondary" onClick={() => setDetailsOpen(false)}>
                {t.logsDismiss}
              </button>
            </div>
            <div className="overflow-auto p-5">
              <pre className="whitespace-pre-wrap break-words text-sm text-slate-800 dark:text-slate-200">
                {detailsMarkdown}
              </pre>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ModelCatalogManager;
