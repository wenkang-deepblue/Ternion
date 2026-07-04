/**
 * Ports and public access settings for the Ternion Control Panel.
 *
 * This component manages:
 * - advanced backend and Web UI port configuration (disabled in Cloud Run environments)
 * - detection-first public access display for Cursor connectivity
 * - manual URL fallback when auto-detection is unavailable
 * - documentation entry points for local tunnel and Cloud Run setup
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api, { isApiError } from '../api/client';
import type { PortsConfig, PublicAccessMode, PublicAccessStatus } from '../api/client';
import { useToast } from './toastContext';
import type { Language, Translations } from '../i18n';
import { getErrorMessage } from '../i18n';

import portIconLight from '../assets/icons/port_light_mode_50dp.svg';
import portIconDark from '../assets/icons/port_dark_mode_50dp.svg';
import warningIconLight from '../assets/icons/warning_light_mode_50dp.svg';
import warningIconDark from '../assets/icons/warning_dark_mode_50dp.svg';
import copyIcon from '../assets/icons/copy_icon.svg';

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

const REPOSITORY_BLOB_URL = 'https://github.com/wenkang-deepblue/Ternion/blob/main';
const LOCAL_TUNNEL_DOC_URL = `${REPOSITORY_BLOB_URL}/public_tunnel_configuration.md`;
const GITHUB_DOCS_URL = `${REPOSITORY_BLOB_URL}/README.md`;

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

function getDeploymentEnvironmentLabel(
  t: Translations,
  environment: PublicAccessStatus['deployment_environment']
): string {
  if (environment === 'cloud_run') {
    return t.publicAccessDeploymentEnvironmentCloudRun;
  }
  return t.publicAccessDeploymentEnvironmentLocal;
}

function isAutoDetectedSource(source: PublicAccessStatus['effective_source']): boolean {
  return source === 'request_origin' || source === 'ngrok_api';
}

function validatePort(port: number): boolean {
  return port >= 1024 && port <= 65535;
}

const DEFAULT_PORTS: PortsConfig = { backend: 9110, web: 9120 };

function PublicAccessStatusRow({
  label,
  value,
  monospace = false,
}: {
  label: string;
  value: string;
  monospace?: boolean;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <div
        className={`rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200 ${
          monospace ? 'font-mono break-all' : ''
        }`}
      >
        {value}
      </div>
    </div>
  );
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
  const [ports, setPorts] = useState<PortsConfig>(DEFAULT_PORTS);
  const [originalPorts, setOriginalPorts] = useState<PortsConfig>(DEFAULT_PORTS);
  const [savingPorts, setSavingPorts] = useState(false);
  const [publicAccessForm, setPublicAccessForm] = useState<PublicAccessFormState>({
    mode: 'none',
    public_base_url: '',
  });
  const [originalPublicAccess, setOriginalPublicAccess] = useState<PublicAccessStatus | null>(null);
  const [savingPublicAccess, setSavingPublicAccess] = useState(false);
  const [portsReady, setPortsReady] = useState(false);
  const [portsLoadErrorCode, setPortsLoadErrorCode] = useState<string | null>(null);
  const [showAdvancedPorts, setShowAdvancedPorts] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [authToken, setAuthToken] = useState('');
  const previousFocusedElementRef = useRef<HTMLElement | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

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
    // Best effort: the endpoint is auth-protected, so unauthenticated remote
    // sessions simply do not see the token row.
    let cancelled = false;
    api
      .getAuthToken()
      .then(result => {
        if (!cancelled) {
          setAuthToken(result.auth_token || '');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuthToken('');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const hasPortChanges =
    ports.backend !== originalPorts.backend || ports.web !== originalPorts.web;

  const hasPublicAccessChanges = useMemo(() => {
    if (!originalPublicAccess) {
      return false;
    }
    return (
      publicAccessForm.mode !== originalPublicAccess.mode ||
      publicAccessForm.public_base_url !== originalPublicAccess.configured_public_base_url
    );
  }, [originalPublicAccess, publicAccessForm.mode, publicAccessForm.public_base_url]);

  const handlePortChange = (field: keyof PortsConfig, value: string) => {
    const trimmedValue = value.trim();
    if (!/^-?\d+$/.test(trimmedValue)) {
      return;
    }
    const numValue = Number(trimmedValue);
    setPorts(prev => ({ ...prev, [field]: numValue }));
  };

  const handleSave = () => {
    if (!validatePort(ports.backend) || !validatePort(ports.web)) {
      showToast(t.portsInvalid, 'error');
      return;
    }
    if (ports.backend === ports.web) {
      showToast(t.portsDuplicate, 'error');
      return;
    }
    setShowConfirm(true);
  };

  const confirmSave = async () => {
    setShowConfirm(false);
    setSavingPorts(true);
    try {
      const result = await api.updatePorts({
        backend: ports.backend,
        web: ports.web,
      });
      setOriginalPorts(result.ports);
      setPorts(result.ports);

      const toastMessage = t.portsChangedToast
        .replace('{backend}', result.ports.backend.toString())
        .replace('{web}', result.ports.web.toString());
      const message = result.restart_required ? `${t.portsSaved}\n${toastMessage}` : t.portsSaved;
      showToast(message, 'success');
    } catch (error) {
      console.error('Failed to save ports:', error);
      const errorCode = extractErrorCode(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSavingPorts(false);
    }
  };

  const cancelSave = useCallback(() => {
    setShowConfirm(false);
    setPorts(originalPorts);
  }, [originalPorts]);

  useEffect(() => {
    if (!showConfirm) {
      return undefined;
    }

    previousFocusedElementRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusableElements = [cancelButtonRef.current, confirmButtonRef.current].filter(
      (element): element is HTMLButtonElement => element !== null
    );
    focusableElements[0]?.focus();

    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelSave();
        return;
      }

      if (event.key !== 'Tab' || focusableElements.length === 0) {
        return;
      }

      const currentIndex = focusableElements.findIndex(element => element === document.activeElement);
      const fallbackIndex = event.shiftKey ? focusableElements.length - 1 : 0;
      const activeIndex = currentIndex === -1 ? fallbackIndex : currentIndex;
      const nextIndex = event.shiftKey
        ? (activeIndex - 1 + focusableElements.length) % focusableElements.length
        : (activeIndex + 1) % focusableElements.length;

      event.preventDefault();
      focusableElements[nextIndex]?.focus();
    };

    document.addEventListener('keydown', handleDialogKeyDown);

    return () => {
      document.removeEventListener('keydown', handleDialogKeyDown);
      previousFocusedElementRef.current?.focus();
    };
  }, [cancelSave, showConfirm]);

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

  const handleCopyAuthToken = async () => {
    if (!authToken) {
      return;
    }

    try {
      const clipboard = typeof window !== 'undefined' ? window.navigator.clipboard : undefined;
      if (!clipboard?.writeText) {
        throw new Error('Clipboard API unavailable');
      }
      await clipboard.writeText(authToken);
      showToast(t.publicAccessCopied, 'success');
    } catch (error) {
      console.error('Failed to copy access token:', error);
      showToast(t.publicAccessCopyFailed, 'error');
    }
  };

  const detectedPublicUrl = publicAccess?.detected_public_base_url ?? '';
  const cursorBaseUrl = publicAccess?.cursor_override_base_url ?? '';
  const showManualFallback = Boolean(publicAccess && !detectedPublicUrl);
  const isCloudRun = publicAccess?.deployment_environment === 'cloud_run';
  const showAutoDetectedNote = Boolean(
    publicAccess && isAutoDetectedSource(publicAccess.effective_source)
  );

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <img src={isDarkMode ? portIconDark : portIconLight} alt="" className="w-6 h-6" />
              {t.portsTitle}
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {t.portsDescription}
            </p>
          </div>
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
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-5 dark:border-slate-700 dark:bg-slate-900/40">
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      {t.portsCurrentBackend}
                    </p>
                    <p className="mt-2 text-2xl font-bold" style={{ color: '#4083f2' }}>
                      {originalPorts.backend}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      {t.portsCurrentWeb}
                    </p>
                    <p className="mt-2 text-2xl font-bold" style={{ color: '#4083f2' }}>
                      {originalPorts.web}
                    </p>
                    <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
                      http://localhost:{originalPorts.web}
                    </p>
                  </div>
                </div>

                {hasPortChanges && (
                  <div
                    className="mx-auto mt-5 w-full rounded-lg border border-amber-200 bg-amber-50 p-4 motion-safe:animate-pulse motion-reduce:animate-none dark:border-amber-800 dark:bg-amber-900/20"
                    style={{ animationIterationCount: 3 }}
                  >
                    <p className="text-amber-800 dark:text-amber-200 text-sm font-medium flex items-center justify-center gap-2">
                      <img src={isDarkMode ? warningIconDark : warningIconLight} alt="" className="w-6 h-6 shrink-0" />
                      {t.portsWarning}
                    </p>
                  </div>
                )}

                {isCloudRun ? (
                  <div className="mt-6">
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white">
                      {t.portsAdvancedSettings}
                    </h3>
                    <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                      {t.portsCloudRunManaged}
                    </p>
                  </div>
                ) : (
                  <div className="mt-6">
                    <button
                      type="button"
                      className="flex items-start text-left w-full group focus:outline-none -ml-[17px]"
                      onClick={() => setShowAdvancedPorts(prev => !prev)}
                      aria-label={
                        showAdvancedPorts ? t.portsHideAdvancedSettings : t.portsShowAdvancedSettings
                      }
                    >
                      <div className="mt-1 shrink-0 pt-[2px] w-[14px] flex justify-center">
                        {showAdvancedPorts ? (
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="#4083f2">
                            <polygon points="4,7 20,7 12,19" />
                          </svg>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="#4083f2">
                            <polygon points="7,4 19,12 7,20" />
                          </svg>
                        )}
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-slate-900 dark:text-white group-hover:text-[#4083f2] transition-colors">
                          {t.portsAdvancedSettings}
                        </h3>
                        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                          {t.portsAdvancedDescription}
                        </p>
                      </div>
                    </button>

                    {showAdvancedPorts && (
                      <div className="mt-5 space-y-4">
                        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                          <div>
                            <label className="label">{t.portsBackend}</label>
                            <div className="input-rainbow-glow">
                              <input
                                type="number"
                                className="input"
                                style={{ width: '100%' }}
                                value={ports.backend}
                                onChange={(e) => handlePortChange('backend', e.target.value)}
                                min="1024"
                                max="65535"
                              />
                            </div>
                          </div>

                          <div>
                            <label className="label">{t.portsWeb}</label>
                            <div className="input-rainbow-glow">
                              <input
                                type="number"
                                className="input"
                                style={{ width: '100%' }}
                                value={ports.web}
                                onChange={(e) => handlePortChange('web', e.target.value)}
                                min="1024"
                                max="65535"
                              />
                            </div>
                            <p className="text-sm text-slate-500 mt-1">
                              http://localhost:{ports.web}
                            </p>
                          </div>
                        </div>

                        {hasPortChanges && (
                          <div className="mt-2 flex justify-center w-full">
                            <button
                              style={{ minWidth: '100px', height: '36px' }}
                              className="btn btn-primary text-xs whitespace-nowrap"
                              onClick={handleSave}
                              disabled={savingPorts}
                            >
                              {savingPorts ? t.saving : t.saveChanges}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="text-lg font-semibold">{t.publicAccessTitle}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {t.publicAccessDescription}
            </p>
          </div>
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
              <div className="space-y-4">
                <PublicAccessStatusRow
                  label={t.publicAccessDeploymentEnvironment}
                  value={getDeploymentEnvironmentLabel(t, publicAccess.deployment_environment)}
                />

                <PublicAccessStatusRow
                  label={t.publicAccessDetectedPublicUrl}
                  value={detectedPublicUrl || t.publicAccessDetectedPublicUrlUnavailable}
                  monospace
                />

                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <label className="label mb-0!">{t.publicAccessCursorUrl}</label>
                    <span className="text-sm font-normal text-slate-500">{t.publicAccessCursorHint}</span>
                  </div>
                  <div className="relative rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 pr-12 font-mono text-sm break-all text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                    {cursorBaseUrl || t.notConfigured}
                    {cursorBaseUrl && (
                      <button
                        type="button"
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors"
                        onClick={handleCopyCursorUrl}
                        title={t.publicAccessCopy}
                        aria-label={t.publicAccessCopy}
                      >
                        <img src={copyIcon} alt="" className="w-4 h-4 dark:invert opacity-70 hover:opacity-100" />
                      </button>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-[#FF9800]">
                    {t.publicAccessCursorGuide}
                  </p>
                  {showAutoDetectedNote && (
                    <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                      {t.publicAccessAutoDetectedNote}
                    </p>
                  )}
                </div>

                <PublicAccessStatusRow
                  label={t.publicAccessSource}
                  value={getEffectiveSourceLabel(t, publicAccess.effective_source)}
                />

                {authToken && (
                  <div>
                    <div className="flex items-center gap-3 mb-2">
                      <label className="label mb-0!">{t.publicAccessTokenLabel}</label>
                      <span className="text-sm font-normal text-slate-500">
                        {t.publicAccessTokenHint}
                      </span>
                    </div>
                    <div className="relative rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 pr-12 font-mono text-sm break-all text-slate-700 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-200">
                      {`${authToken.slice(0, 6)}${'•'.repeat(12)}`}
                      <button
                        type="button"
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors"
                        onClick={handleCopyAuthToken}
                        title={`${t.publicAccessTokenLabel}: ${t.publicAccessCopy}`}
                        aria-label={`${t.publicAccessTokenLabel}: ${t.publicAccessCopy}`}
                      >
                        <img
                          src={copyIcon}
                          alt=""
                          className="w-4 h-4 dark:invert opacity-70 hover:opacity-100"
                        />
                      </button>
                    </div>
                    <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                      {t.publicAccessTokenDescription}
                    </p>
                  </div>
                )}
              </div>

              {showManualFallback && (
                <>
                  <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-5 dark:border-slate-700 dark:bg-slate-900/40">
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white">
                      {t.publicAccessDocsTitle}
                    </h3>
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                      {t.publicAccessDocsDescription}
                    </p>
                    <div className="mt-4 flex flex-wrap gap-3">
                      {[
                        { href: LOCAL_TUNNEL_DOC_URL, label: t.publicAccessDocsLocalTunnel },
                        { href: GITHUB_DOCS_URL, label: t.publicAccessDocsGitHub },
                      ].map(({ href, label }) => (
                        <a
                          key={href}
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-secondary text-xs whitespace-nowrap"
                        >
                          {label}
                        </a>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-5 dark:border-slate-700 dark:bg-slate-900/40">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <h3 className="text-base font-semibold text-slate-900 dark:text-white">
                          {t.publicAccessManualFallbackTitle}
                        </h3>
                        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                          {t.publicAccessManualFallbackDescription}
                        </p>
                      </div>
                    </div>

                    <div className="mt-5 grid grid-cols-1 gap-6 md:grid-cols-2">
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
                        <label className="label">{t.publicAccessConfiguredUrl}</label>
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

                    <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
                      {t.publicAccessManualFallbackHint}
                    </p>
                    {hasPublicAccessChanges && (
                      <div className="mt-6 flex justify-center w-full">
                        <button
                          style={{ minWidth: '100px', height: '36px', flexShrink: 0 }}
                          className="btn btn-primary text-xs whitespace-nowrap"
                          onClick={handlePublicAccessSave}
                          disabled={savingPublicAccess}
                        >
                          {savingPublicAccess ? t.saving : t.saveChanges}
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {showConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-6 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-slate-900/5 dark:bg-slate-900 dark:ring-white/10 text-center">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                {t.portsConfirmChangeTitle}
              </h3>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                {t.portsConfirmChangeDesc}
              </p>
              <div className="mt-6 flex justify-center gap-3">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={cancelSave}
                  ref={cancelButtonRef}
                >
                  {t.portsCancelBtn}
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={confirmSave}
                  ref={confirmButtonRef}
                >
                  {t.portsConfirmBtn}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PortsSettings;
