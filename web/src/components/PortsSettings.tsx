/**
 * Ports and public access settings for the Ternion Control Panel.
 *
 * This component manages:
 * - backend/web port configuration
 * - public HTTPS URL configuration for Cursor
 * - public access status display and copy action
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import api, { isApiError } from '../api/client';
import type { PortsConfig, PublicAccessMode, PublicAccessStatus } from '../api/client';
import { useToast } from './toastContext';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';
import type { Language } from '../i18n';

// Port settings icons
import portIconLight from '../assets/icons/port_light_mode_50dp.svg';
import portIconDark from '../assets/icons/port_dark_mode_50dp.svg';
import warningIconLight from '../assets/icons/warning_light_mode_50dp.svg';
import warningIconDark from '../assets/icons/warning_dark_mode_50dp.svg';

interface PortsSettingsProps {
  t: Translations;
  isDarkMode: boolean;
  language: Language;
  publicAccess: PublicAccessStatus | null;
  publicAccessReady: boolean;
  onPublicAccessUpdate: (value: PublicAccessStatus) => void;
}

interface PublicAccessFormState {
  mode: PublicAccessMode;
  public_base_url: string;
}

const VALID_PUBLIC_ACCESS_MODES: readonly PublicAccessMode[] = [
  'none',
  'local_tunnel',
  'cloud_run',
  'custom',
];

function isPublicAccessMode(value: string): value is PublicAccessMode {
  return VALID_PUBLIC_ACCESS_MODES.includes(value as PublicAccessMode);
}

function extractErrorCode(error: unknown): string {
  if (isApiError(error)) {
    return error.code;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function getEffectiveSourceLabel(t: Translations, source: PublicAccessStatus['effective_source']): string {
  if (source === 'config') {
    return t.publicAccessSourceConfig;
  }
  if (source === 'request_origin') {
    return t.publicAccessSourceRequestOrigin;
  }
  if (source === 'ngrok_api') {
    return t.publicAccessSourceNgrokApi;
  }
  return t.publicAccessSourceNone;
}

function renderPublicAccessValue(value: string, fallback: string): string {
  return value || fallback;
}

export function PortsSettings({
  t,
  isDarkMode,
  language,
  publicAccess,
  publicAccessReady,
  onPublicAccessUpdate,
}: PortsSettingsProps) {
  const { showToast } = useToast();
  const [ports, setPorts] = useState<PortsConfig>({
    backend: 9110,
    web: 9120,
  });
  const [originalPorts, setOriginalPorts] = useState<PortsConfig>({
    backend: 9110,
    web: 9120,
  });
  const [savingPorts, setSavingPorts] = useState(false);
  const [publicAccessForm, setPublicAccessForm] = useState<PublicAccessFormState>({
    mode: 'none',
    public_base_url: '',
  });
  const [originalPublicAccess, setOriginalPublicAccess] = useState<PublicAccessStatus | null>(null);
  const [savingPublicAccess, setSavingPublicAccess] = useState(false);
  const [portsReady, setPortsReady] = useState(false);
  const [portsLoadErrorCode, setPortsLoadErrorCode] = useState<string | null>(null);

  const loadPorts = useCallback(async (): Promise<void> => {
    setPortsReady(false);
    setPortsLoadErrorCode(null);
    try {
      const data = await api.getPorts();
      setPorts(data);
      setOriginalPorts(data);
      setPortsReady(true);
    } catch (error) {
      console.error('Failed to load ports:', error);
      setPortsLoadErrorCode(extractErrorCode(error));
      setPortsReady(true);
    }
  }, []);

  useEffect(() => {
    void loadPorts();
  }, [loadPorts]);

  useEffect(() => {
    if (!publicAccess) {
      return;
    }
    setOriginalPublicAccess(publicAccess);
    setPublicAccessForm({
      mode: publicAccess.mode,
      public_base_url: publicAccess.configured_public_base_url,
    });
  }, [publicAccess]);

  const hasPortChanges = useMemo(
    () => ports.backend !== originalPorts.backend || ports.web !== originalPorts.web,
    [originalPorts.backend, originalPorts.web, ports.backend, ports.web]
  );

  const hasPublicAccessChanges = useMemo(() => {
    if (!originalPublicAccess) {
      return false;
    }
    return (
      publicAccessForm.mode !== originalPublicAccess.mode ||
      publicAccessForm.public_base_url !== originalPublicAccess.configured_public_base_url
    );
  }, [originalPublicAccess, publicAccessForm.mode, publicAccessForm.public_base_url]);

  const validatePort = (port: number): boolean => {
    return port >= 1024 && port <= 65535;
  };

  const handleBackendChange = (value: string) => {
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue)) {
      setPorts(prev => ({ ...prev, backend: numValue }));
    }
  };

  const handleWebChange = (value: string) => {
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue)) {
      setPorts(prev => ({ ...prev, web: numValue }));
    }
  };

  const handleSave = async () => {
    // Validate ports
    if (!validatePort(ports.backend) || !validatePort(ports.web)) {
      showToast(t.portsInvalid, 'error');
      return;
    }

    setSavingPorts(true);
    try {
      const result = await api.updatePorts(ports);
      setOriginalPorts(result.ports);

      // Show success toast with new port values and URLs
      const restartNote = result.restart_required ? `\n${t.portsRestartNote}` : '';
      showToast(
        `${t.portsSaved}${restartNote}\n${t.portsBackendLabel}: ${result.ports.backend} | ${t.portsWebLabel}: ${result.ports.web}`,
        'success'
      );
    } catch (error) {
      console.error('Failed to save ports:', error);
      const errorCode = extractErrorCode(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSavingPorts(false);
    }
  };

  const handlePublicAccessSave = async () => {
    setSavingPublicAccess(true);
    try {
      const result = await api.updatePublicAccess({
        mode: publicAccessForm.mode,
        public_base_url: publicAccessForm.public_base_url,
      });
      setOriginalPublicAccess(result);
      setPublicAccessForm({
        mode: result.mode,
        public_base_url: result.configured_public_base_url,
      });
      onPublicAccessUpdate(result);
      showToast(t.publicAccessSaved, 'success');
    } catch (error) {
      console.error('Failed to save public access:', error);
      const errorCode = extractErrorCode(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSavingPublicAccess(false);
    }
  };

  const handleCopyCursorUrl = async () => {
    if (!publicAccess?.cursor_override_base_url) {
      return;
    }

    try {
      const clipboard = typeof window !== 'undefined' ? window.navigator.clipboard : undefined;
      if (!clipboard?.writeText) {
        throw new Error('Clipboard API unavailable');
      }
      await clipboard.writeText(publicAccess.cursor_override_base_url);
      showToast(t.publicAccessCopied, 'success');
    } catch (error) {
      console.error('Failed to copy public access URL:', error);
      showToast(t.publicAccessCopyFailed, 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <img src={isDarkMode ? portIconDark : portIconLight} alt="" className="w-6 h-6" />
              {t.portsTitle}
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {t.portsDescription}
            </p>
          </div>
          {portsReady && !portsLoadErrorCode && hasPortChanges && (
            <button
              style={{ minWidth: '100px', height: '46px', flexShrink: 0 }}
              className="btn btn-primary text-xs whitespace-nowrap"
              onClick={handleSave}
              disabled={savingPorts}
            >
              {savingPorts ? t.saving : t.saveChanges}
            </button>
          )}
        </div>

        <div className="card-body">
          {!portsReady && (
            <p className="text-sm text-slate-500 dark:text-slate-400">{t.loading}</p>
          )}

          {portsReady && portsLoadErrorCode && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
              {getErrorMessage(t, portsLoadErrorCode, language)}
            </div>
          )}

          {portsReady && !portsLoadErrorCode && (
            <>
              <div className="mt-6 mb-12 text-center">
                <span className="text-lg font-medium text-slate-700 dark:text-slate-300">
                  {t.portsCurrentBackend}:{' '}
                  <span className="font-bold" style={{ color: '#4083f2' }}>{originalPorts.backend}</span>
                </span>
                <span className="mx-3 text-xl text-slate-400">|</span>
                <span className="text-lg font-medium text-slate-700 dark:text-slate-300">
                  {t.portsCurrentWeb}:{' '}
                  <span className="font-bold" style={{ color: '#4083f2' }}>{originalPorts.web}</span>
                </span>
              </div>

              <div className="mb-10 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <p className="text-amber-800 dark:text-amber-200 text-sm font-medium flex items-center justify-center gap-2">
                  <img src={isDarkMode ? warningIconDark : warningIconLight} alt="" className="w-6 h-6" />
                  {t.portsWarning}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                <div>
                  <label className="label">{t.portsBackend}</label>
                  <div className="input-rainbow-glow">
                    <input
                      type="number"
                      className="input"
                      style={{ width: '100%' }}
                      value={ports.backend}
                      onChange={(e) => handleBackendChange(e.target.value)}
                      min="1024"
                      max="65535"
                    />
                  </div>
                  <p className="text-sm text-slate-500 mt-1">
                    http://localhost:{ports.backend}
                  </p>
                </div>

                <div>
                  <label className="label">{t.portsWeb}</label>
                  <div className="input-rainbow-glow">
                    <input
                      type="number"
                      className="input"
                      style={{ width: '100%' }}
                      value={ports.web}
                      onChange={(e) => handleWebChange(e.target.value)}
                      min="1024"
                      max="65535"
                    />
                  </div>
                  <p className="text-sm text-slate-500 mt-1">
                    http://localhost:{ports.web}
                  </p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{t.publicAccessTitle}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {t.publicAccessDescription}
            </p>
          </div>
          {publicAccessReady && publicAccess && hasPublicAccessChanges && (
            <button
              style={{ minWidth: '100px', height: '46px', flexShrink: 0 }}
              className="btn btn-primary text-xs whitespace-nowrap"
              onClick={handlePublicAccessSave}
              disabled={savingPublicAccess}
            >
              {savingPublicAccess ? t.saving : t.saveChanges}
            </button>
          )}
        </div>

        <div className="card-body space-y-6">
          {!publicAccessReady && (
            <p className="text-sm text-slate-500 dark:text-slate-400">{t.loading}</p>
          )}

          {publicAccessReady && !publicAccess && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
              {t.publicAccessUnavailable}
            </div>
          )}

          {publicAccessReady && publicAccess && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  {t.publicAccessStatus}
                </span>
                <span
                  className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
                    publicAccess.configured
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                  }`}
                >
                  {publicAccess.configured
                    ? t.publicAccessStatusConfigured
                    : t.publicAccessStatusMissing}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                <div>
                  <label className="label">{t.publicAccessMode}</label>
                  <div className="input-rainbow-glow">
                    <select
                      className="input"
                      value={publicAccessForm.mode}
                      onChange={(event) => {
                        const nextMode = event.target.value;
                        if (!isPublicAccessMode(nextMode)) {
                          return;
                        }
                        setPublicAccessForm(prev => ({
                          ...prev,
                          mode: nextMode,
                        }));
                      }}
                    >
                      <option value="none">{t.publicAccessModeNone}</option>
                      <option value="local_tunnel">{t.publicAccessModeLocalTunnel}</option>
                      <option value="cloud_run">{t.publicAccessModeCloudRun}</option>
                      <option value="custom">{t.publicAccessModeCustom}</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="label">{t.publicAccessUrlLabel}</label>
                  <div className="input-rainbow-glow">
                    <input
                      type="url"
                      className="input"
                      value={publicAccessForm.public_base_url}
                      placeholder={t.publicAccessUrlPlaceholder}
                      onChange={(event) => {
                        setPublicAccessForm(prev => ({
                          ...prev,
                          public_base_url: event.target.value,
                        }));
                      }}
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
                <p className="text-sm text-slate-700 dark:text-slate-200">
                  {t.publicAccessCursorHint}
                </p>
                {['request_origin', 'ngrok_api'].includes(publicAccess.effective_source) && (
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    {t.publicAccessAutoDetectedNote}
                  </p>
                )}
              </div>

              <div className="space-y-4">
                <div>
                  <label className="label">{t.publicAccessConfiguredUrl}</label>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm break-all text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                    {renderPublicAccessValue(publicAccess.configured_public_base_url, t.notConfigured)}
                  </div>
                </div>

                <div>
                  <label className="label">{t.publicAccessEffectiveUrl}</label>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm break-all text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                    {renderPublicAccessValue(publicAccess.effective_public_base_url, t.notConfigured)}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between gap-3">
                    <label className="label">{t.publicAccessCursorUrl}</label>
                    {publicAccess.cursor_override_base_url && (
                      <button
                        type="button"
                        className="btn btn-secondary text-xs whitespace-nowrap"
                        onClick={handleCopyCursorUrl}
                      >
                        {t.publicAccessCopy}
                      </button>
                    )}
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm break-all text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                    {renderPublicAccessValue(publicAccess.cursor_override_base_url, t.notConfigured)}
                  </div>
                </div>

                <div>
                  <label className="label">{t.publicAccessSource}</label>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                    {getEffectiveSourceLabel(t, publicAccess.effective_source)}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default PortsSettings;
