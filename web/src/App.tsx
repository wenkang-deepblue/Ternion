/**
 * Main application component for Ternion Control Panel.
 *
 * Integrates all sub-components and provides:
 * - i18n language support with preferences persistence
 * - Theme switching (light/dark/system)
 * - Configuration status bar
 * - Tab navigation
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import api from './api/client';
import type { Config, ModelsData, PublicAccessStatus, ServerStatus } from './api/client';
import { ToastProvider } from './components/Toast';
import StatusBar from './components/StatusBar';
import ModelCatalogManager from './components/ModelCatalogManager';
import ApiKeyManager from './components/ApiKeyManager';
import RoleModelConfig from './components/RoleModelConfig';
import BudgetSettings from './components/BudgetSettings';
import PortsSettings from './components/PortsSettings';
import PublicAccessNotice from './components/PublicAccessNotice';
import UsageDashboard from './components/UsageDashboard';
import ObservabilityPanel from './components/ObservabilityPanel';
import ExecutionModeSelector from './components/ExecutionModeSelector';
import SettingsDropdown from './components/SettingsDropdown';
import type { ThemeMode, LanguageMode } from './components/SettingsDropdown';
import { detectBrowserLanguage, getTranslations } from './i18n';
import type { Language } from './i18n';
import './index.css';
import ternionLogo from './assets/icons/ternion-logo-light.png';
import ternionLogoDark from './assets/icons/ternion-logo-dark.png';

// Tab icons for light/dark mode
import configIconLight from './assets/icons/configuration_light_mode_50dp.svg';
import configIconDark from './assets/icons/configuration_dark_mode_50dp.svg';
import portIconLight from './assets/icons/port_light_mode_50dp.svg';
import portIconDark from './assets/icons/port_dark_mode_50dp.svg';
import usageIconLight from './assets/icons/usage_light_mode_50dp.svg';
import usageIconDark from './assets/icons/usage_dark_mode_50dp.svg';
import logIconLight from './assets/icons/log_light_mode_dp50.svg';
import logIconDark from './assets/icons/log_dark_mode_dp50.svg';

function AppContent() {
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [modelsData, setModelsData] = useState<ModelsData | null>(null);
  const [publicAccess, setPublicAccess] = useState<PublicAccessStatus | null>(null);
  const [publicAccessReady, setPublicAccessReady] = useState(false);
  const [activeTab, setActiveTab] = useState<'config' | 'ports' | 'usage' | 'logs'>('config');
  const [modelsReloadSignal, setModelsReloadSignal] = useState(0);

  const scrollPositions = useRef<Record<string, number>>({
    config: 0,
    ports: 0,
    usage: 0,
    logs: 0,
  });

  const handleTabChange = useCallback((newTab: 'config' | 'ports' | 'usage' | 'logs') => {
    scrollPositions.current[activeTab] = window.scrollY;
    setActiveTab(newTab);
    requestAnimationFrame(() => {
      window.scrollTo(0, scrollPositions.current[newTab]);
    });
  }, [activeTab]);

  const [themeMode, setThemeMode] = useState<ThemeMode>('system');
  const [languageMode, setLanguageMode] = useState<LanguageMode>('auto');

  const effectiveLanguage: Language =
    languageMode === 'auto' ? detectBrowserLanguage() : languageMode;
  const t = getTranslations(effectiveLanguage);

  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false
  );

  const isDarkMode =
    themeMode === 'dark' || (themeMode === 'system' && systemDark);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDarkMode);
  }, [isDarkMode]);

  const loadModelsData = useCallback(async () => {
    try {
      const models = await api.getModels();
      setModelsData(models);
    } catch (error) {
      console.error('Failed to load models:', error);
      setModelsData(null);
    }
  }, []);

  const loadPublicAccess = useCallback(async () => {
    try {
      const publicAccessState = await api.getPublicAccess();
      setPublicAccess(publicAccessState);
    } catch (error) {
      console.error('Failed to load public access:', error);
      setPublicAccess(null);
    } finally {
      setPublicAccessReady(true);
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [configData, statusData] = await Promise.all([
        api.getConfig(),
        api.getStatus(),
      ]);
      setConfig(configData);
      setStatus(statusData);
      await Promise.all([
        loadModelsData(),
        loadPublicAccess(),
      ]);

      if (configData?.preferences) {
        if (configData.preferences.theme) {
          setThemeMode(configData.preferences.theme as ThemeMode);
        }
        if (configData.preferences.language) {
          setLanguageMode(configData.preferences.language as LanguageMode);

          if (configData.preferences.language === 'auto') {
            const browserLang = detectBrowserLanguage();
            api.updatePreferences({ browser_language: browserLang }).catch(console.error);
          }
        }
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  }, [loadModelsData, loadPublicAccess]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Poll config periodically so backend-initiated changes (e.g. auto-switch execution_mode)
  // become visible without requiring a manual page refresh.
  useEffect(() => {
    let cancelled = false;
    const interval = window.setInterval(async () => {
      try {
        const latest = await api.getConfig();
        if (cancelled) return;
        setConfig((prev) => {
          const prevUpdated = prev?.updated_at || '';
          const latestUpdated = latest?.updated_at || '';
          if (prev && prevUpdated && latestUpdated && prevUpdated === latestUpdated) {
            return prev;
          }
          return latest;
        });
      } catch {
        // Ignore polling errors (server may be restarting)
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const handleConfigUpdate = (newConfig: Config) => {
    setConfig(newConfig);
    api.getStatus().then(setStatus).catch(console.error);
  };

  const handleModelsReload = useCallback(() => {
    setModelsReloadSignal(prev => prev + 1);
  }, []);

  const handleThemeChange = useCallback(async (theme: ThemeMode) => {
    setThemeMode(theme);
    try {
      await api.updatePreferences({ theme });
    } catch (error) {
      console.error('Failed to save theme preference:', error);
    }
  }, []);

  const handleLanguageChange = useCallback(async (language: LanguageMode) => {
    setLanguageMode(language);
    try {
      // Keep backend report language aligned with the browser when auto mode is selected.
      if (language === 'auto') {
        const browserLang = detectBrowserLanguage();
        await api.updatePreferences({ language, browser_language: browserLang });
      } else {
        await api.updatePreferences({ language });
      }
    } catch (error) {
      console.error('Failed to save language preference:', error);
    }
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      <PublicAccessNotice publicAccess={publicAccess} ready={publicAccessReady} t={t} />
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src={isDarkMode ? ternionLogoDark : ternionLogo} alt={t.appTitle} className="h-20" />
              <div>
                <h1 className="text-xl font-bold text-slate-900 dark:text-white">
                  {t.appTitle}
                </h1>
                <p className="text-sm text-slate-500">
                  {t.appSubtitle}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Status Badge */}
              {status && (
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      status.provider_count > 0
                        ? 'bg-emerald-500 animate-pulse'
                        : 'bg-yellow-500'
                    }`}
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    {status.provider_count} {t.llmKeysEnabled}
                  </span>
                </div>
              )}
              {/* Settings Dropdown */}
              <SettingsDropdown
                t={t}
                theme={themeMode}
                language={languageMode}
                isDarkMode={isDarkMode}
                onThemeChange={handleThemeChange}
                onLanguageChange={handleLanguageChange}
              />
            </div>
          </div>
        </div>

        {/* Status Bar */}
        <StatusBar config={config} modelsData={modelsData} t={t} />

        {/* Tabs */}
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex gap-1 -mb-px">
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'config'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => handleTabChange('config')}
            >
              <img src={isDarkMode ? configIconDark : configIconLight} alt="" className="w-5 h-5" />
              {t.tabConfig}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'ports'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => handleTabChange('ports')}
            >
              <img src={isDarkMode ? portIconDark : portIconLight} alt="" className="w-5 h-5" />
              {t.tabPorts}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'usage'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => handleTabChange('usage')}
            >
              <img src={isDarkMode ? usageIconDark : usageIconLight} alt="" className="w-5 h-5" />
              {t.tabUsage}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-all border-b-2 flex items-center gap-2 transform hover:scale-105 cursor-pointer ${
                activeTab === 'logs'
                  ? 'text-blue-600 border-blue-600 dark:text-[#88b2f6] dark:border-[#88b2f6]'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => handleTabChange('logs')}
            >
              <img src={isDarkMode ? logIconDark : logIconLight} alt="" className="w-5 h-5" />
              {t.tabLogs}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        <div style={{ display: activeTab === 'config' ? 'block' : 'none' }}>
          <div className="space-y-6">
            <ModelCatalogManager
              config={config}
              onConfigUpdate={handleConfigUpdate}
              onModelsReload={handleModelsReload}
              reloadSignal={modelsReloadSignal}
              t={t}
              language={effectiveLanguage}
            />
            <ApiKeyManager config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} language={effectiveLanguage} />
            <ExecutionModeSelector config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} language={effectiveLanguage} />
            <RoleModelConfig
              config={config}
              onConfigUpdate={handleConfigUpdate}
              t={t}
              isDarkMode={isDarkMode}
              executionMode={config?.execution_mode}
              language={effectiveLanguage}
              modelsReloadSignal={modelsReloadSignal}
              onModelsReload={handleModelsReload}
            />
            <BudgetSettings config={config} onConfigUpdate={handleConfigUpdate} t={t} isDarkMode={isDarkMode} language={effectiveLanguage} />
          </div>
        </div>
        <div style={{ display: activeTab === 'ports' ? 'block' : 'none' }}>
          <PortsSettings
            t={t}
            isDarkMode={isDarkMode}
            language={effectiveLanguage}
            publicAccess={publicAccess}
            publicAccessReady={publicAccessReady}
            onPublicAccessUpdate={setPublicAccess}
          />
        </div>
        <div style={{ display: activeTab === 'usage' ? 'block' : 'none' }}>
          <UsageDashboard t={t} isDarkMode={isDarkMode} onConfigUpdate={handleConfigUpdate} />
        </div>
        <div style={{ display: activeTab === 'logs' ? 'block' : 'none' }}>
          <ObservabilityPanel t={t} isDarkMode={isDarkMode} isVisible={activeTab === 'logs'} />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-700 py-6 mt-12">
        <div className="max-w-5xl mx-auto px-4 text-center text-sm text-slate-500">
          <p>
            {t.footerVersion} • {t.appSubtitle} •{' '}
            <a
              href={`http://localhost:${config?.ports?.backend || 9110}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              {t.footerApiDocs}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;
